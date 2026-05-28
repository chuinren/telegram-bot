import os
import sqlite3
import stripe

from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI

# ================= CONFIG =================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
BASE_URL = os.getenv("BASE_URL")

client = OpenAI(api_key=OPENAI_API_KEY)
stripe.api_key = STRIPE_SECRET_KEY

# ================= FLASK =================

app = Flask(__name__)

# ================= DATABASE =================

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    is_vip INTEGER DEFAULT 0,
    usage_count INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    role TEXT,
    content TEXT
)
""")

conn.commit()

FREE_LIMIT = 5

# ================= DB =================

def create_user(uid):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    conn.commit()

def is_vip(uid):
    cursor.execute("SELECT is_vip FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()
    return row and row[0] == 1

def activate_vip(uid):
    cursor.execute("UPDATE users SET is_vip=1 WHERE user_id=?", (uid,))
    conn.commit()

def add_usage(uid):
    cursor.execute("UPDATE users SET usage_count = usage_count + 1 WHERE user_id=?", (uid,))
    conn.commit()

def get_usage(uid):
    cursor.execute("SELECT usage_count FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()
    return row[0] if row else 0

# ================= MEMORY =================

def save_memory(uid, role, content):
    cursor.execute(
        "INSERT INTO memory (user_id, role, content) VALUES (?, ?, ?)",
        (uid, role, content)
    )
    conn.commit()

def load_memory(uid):
    cursor.execute(
        "SELECT role, content FROM memory WHERE user_id=? ORDER BY id DESC LIMIT 10",
        (uid,)
    )
    rows = cursor.fetchall()
    return list(reversed(rows))

# ================= STRIPE =================

def create_checkout(uid):
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "VIP AI RM15"},
                "unit_amount": 300
            },
            "quantity": 1
        }],
        success_url=BASE_URL,
        cancel_url=BASE_URL,
        metadata={"user_id": str(uid)}
    )
    return session.url

# ================= OPENAI =================

def ask_ai(uid, text):

    history = load_memory(uid)

    messages = [
        {"role": "system", "content": "You are a helpful AI assistant."}
    ]

    for role, content in history:
        messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": text})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=250
    )

    return response.choices[0].message.content

# ================= TELEGRAM APP =================

telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.message.from_user.id
    create_user(uid)

    keyboard = [
        [InlineKeyboardButton("💎 VIP RM15", callback_data="vip")],
        [InlineKeyboardButton("📊 Status", callback_data="status")]
    ]

    await update.message.reply_text(
        "🤖 AI BOT READY",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= BUTTONS =================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    create_user(uid)

    if q.data == "vip":
        url = create_checkout(uid)
        await q.message.reply_text(f"💳 Pay here:\n{url}")

    elif q.data == "status":
        status = "VIP 💎" if is_vip(uid) else "FREE 🆓"
        await q.message.reply_text(f"{status}\nUsage: {get_usage(uid)}")

# ================= CHAT =================

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.message.from_user.id
    text = update.message.text

    create_user(uid)

    if not is_vip(uid) and get_usage(uid) >= FREE_LIMIT:
        await update.message.reply_text("❌ Upgrade VIP RM15")
        return

    add_usage(uid)

    save_memory(uid, "user", text)

    reply = ask_ai(uid, text)

    save_memory(uid, "assistant", reply)

    await update.message.reply_text(reply)

# ================= HANDLERS =================

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(buttons))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

# ================= WEBHOOK =================

@app.route("/telegram"), methods=["POST"])
def telegram_webhook():

    data = request.get_json(force=True)

    update = Update.de_json(data, telegram_app.bot)

    telegram_app.create_task(
        telegram_app.process_update(update)
    )

    return "OK", 200

# ================= STRIPE =================

@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():

    payload = request.json

    try:
        event = stripe.Event.construct_from(payload, stripe.api_key)

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            user_id = int(session["metadata"]["user_id"])
            activate_vip(user_id)

    except Exception as e:
        return str(e), 400

    return "OK", 200

# ================= HOME =================

@app.route("/")
def home():
    return "BOT RUNNING"

# ================= MAIN (FIXED FOR PYTHON 3.14) =================

if __name__ == "__main__":

    print("BOT STARTED")

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )
