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

@app.route("/")
def home():
    return "SAAS BOT RUNNING"

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
conn.commit()

FREE_LIMIT = 5

# ================= DB FUNCTIONS =================
def create_user(uid):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    conn.commit()

def is_vip(uid):
    cursor.execute("SELECT is_vip FROM users WHERE user_id=?", (uid,))
    r = cursor.fetchone()
    return r and r[0] == 1

def activate_vip(uid):
    cursor.execute("UPDATE users SET is_vip=1 WHERE user_id=?", (uid,))
    conn.commit()

def add_usage(uid):
    cursor.execute("UPDATE users SET usage_count = usage_count + 1 WHERE user_id=?", (uid,))
    conn.commit()

def get_usage(uid):
    cursor.execute("SELECT usage_count FROM users WHERE user_id=?", (uid,))
    r = cursor.fetchone()
    return r[0] if r else 0

# ================= STRIPE =================
def create_checkout(uid):
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "VIP AI Access RM15"},
                "unit_amount": 300
            },
            "quantity": 1
        }],
        success_url=BASE_URL,
        cancel_url=BASE_URL,
        metadata={"user_id": str(uid)}
    )
    return session.url

# ================= STRIPE WEBHOOK =================
@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.json

    try:
        event = stripe.Event.construct_from(payload, stripe.api_key)

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            uid = int(session["metadata"]["user_id"])
            activate_vip(uid)

    except Exception as e:
        return str(e), 400

    return "OK", 200

# ================= TELEGRAM START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    create_user(uid)

    keyboard = [
        [InlineKeyboardButton("💬 Chat AI", callback_data="chat")],
        [InlineKeyboardButton("💎 VIP RM15", callback_data="vip")],
        [InlineKeyboardButton("📊 Status", callback_data="status")]
    ]

    await update.message.reply_text(
        "🤖 SAAS AI BOT READY\nFree limit: 5 messages",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= BUTTONS =================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    create_user(uid)

    if q.data == "vip":
        session = create_checkout(uid)
        await q.message.reply_text(f"💳 Pay here:\n{session}")

    elif q.data == "status":
        status = "VIP 💎" if is_vip(uid) else "FREE 🆓"
        await q.message.reply_text(f"{status}\nUsage: {get_usage(uid)}")

# ================= AI ENGINE =================
def ask_ai(text):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are RTK AI. Reply short, useful, and clear."},
            {"role": "user", "content": text}
        ],
        max_tokens=200
    )
    return response.choices[0].message.content

# ================= CHAT =================
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    text = update.message.text

    create_user(uid)

    if not is_vip(uid) and get_usage(uid) >= FREE_LIMIT:
        await update.message.reply_text("❌ Free limit reached. Upgrade VIP RM15.")
        return

    add_usage(uid)

    reply = ask_ai(text)

    await update.message.reply_text(reply)

# ================= TELEGRAM APP =================
app_bot = Application.builder().token(TELEGRAM_TOKEN).build()

app_bot.add_handler(CommandHandler("start", start))
app_bot.add_handler(CallbackQueryHandler(buttons))
app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

# ================= RUN =================
if __name__ == "__main__":
    print("SAAS BOT RUNNING")
    app_bot.run_polling()
