import os
import threading
import sqlite3
from flask import Flask, request
import stripe

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# ================= ENV =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
BASE_URL = os.getenv("BASE_URL")

client = OpenAI(api_key=OPENAI_API_KEY)
stripe.api_key = STRIPE_SECRET_KEY

# ================= FLASK =================
app_web = Flask(__name__)

@app_web.route("/")
def home():
    return "AI Bot Running 24/7"

@app_web.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    data = request.json

    try:
        event = stripe.Event.construct_from(data, stripe.api_key)

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            user_id = int(session["metadata"]["user_id"])
            activate_vip(user_id)

    except Exception as e:
        return str(e), 400

    return "OK", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web).start()

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

# ================= SETTINGS =================
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

# ================= STRIPE PAYMENT (RM15/month) =================
def create_checkout_session(uid):
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "VIP Access (RM15/month)"
                },
                "unit_amount": 300  # ≈ RM15
            },
            "quantity": 1
        }],
        success_url=BASE_URL,
        cancel_url=BASE_URL,
        metadata={"user_id": str(uid)}
    )
    return session.url

# ================= TELEGRAM HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    create_user(uid)

    keyboard = [
        [InlineKeyboardButton("💬 Chat AI", callback_data="chat")],
        [InlineKeyboardButton("💰 VIP RM15/month", callback_data="vip")],
        [InlineKeyboardButton("📊 Status", callback_data="status")]
    ]

    await update.message.reply_text(
        "🤖 AI BOT READY\n\nFree limit: 5 messages",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    create_user(uid)

    if q.data == "vip":
        url = create_checkout_session(uid)
        await q.message.reply_text(f"💰 Pay RM15/month:\n{url}")

    elif q.data == "status":
        status = "VIP 💎" if is_vip(uid) else "FREE 🆓"
        await q.message.reply_text(
            f"Status: {status}\nUsage: {get_usage(uid)}"
        )

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    text = update.message.text

    create_user(uid)

    if not is_vip(uid) and get_usage(uid) >= FREE_LIMIT:
        await update.message.reply_text("❌ Free limit reached. Upgrade VIP RM15/month.")
        return

    add_usage(uid)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": text}
        ]
    )

    await update.message.reply_text(response.choices[0].message.content)

# ================= RUN BOT =================
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(buttons))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

print("Bot running...")
app.run_polling()
