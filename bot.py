import os
import sqlite3
import stripe
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from openai import OpenAI

# ==================================================
# ENV VARIABLES
# ==================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
BASE_URL = os.getenv("BASE_URL")

# ==================================================
# OPENAI + STRIPE
# ==================================================

client = OpenAI(api_key=OPENAI_API_KEY)
stripe.api_key = STRIPE_SECRET_KEY

# ==================================================
# FLASK APP
# ==================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Telegram AI Bot Running"

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

# ==================================================
# DATABASE
# ==================================================

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

# ==================================================
# SETTINGS
# ==================================================

FREE_LIMIT = 5

# ==================================================
# DATABASE FUNCTIONS
# ==================================================

def create_user(uid):
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (uid,)
    )
    conn.commit()

def is_vip(uid):
    cursor.execute(
        "SELECT is_vip FROM users WHERE user_id=?",
        (uid,)
    )

    row = cursor.fetchone()

    return row and row[0] == 1

def activate_vip(uid):
    cursor.execute(
        "UPDATE users SET is_vip=1 WHERE user_id=?",
        (uid,)
    )
    conn.commit()

def add_usage(uid):
    cursor.execute(
        "UPDATE users SET usage_count = usage_count + 1 WHERE user_id=?",
        (uid,)
    )
    conn.commit()

def get_usage(uid):
    cursor.execute(
        "SELECT usage_count FROM users WHERE user_id=?",
        (uid,)
    )

    row = cursor.fetchone()

    if row:
        return row[0]

    return 0

# ==================================================
# STRIPE PAYMENT
# ==================================================

def create_checkout(uid):

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": "VIP Access RM15"
                    },
                    "unit_amount": 300
                },
                "quantity": 1
            }
        ],
        success_url=BASE_URL,
        cancel_url=BASE_URL,
        metadata={
            "user_id": str(uid)
        }
    )

    return session.url

# ==================================================
# TELEGRAM COMMANDS
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.message.from_user.id

    create_user(uid)

    keyboard = [
        [
            InlineKeyboardButton(
                "💰 VIP RM15",
                callback_data="vip"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Status",
                callback_data="status"
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🤖 AI BOT READY\n\nFree limit: 5 messages",
        reply_markup=reply_markup
    )

# ==================================================
# BUTTONS
# ==================================================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    uid = query.from_user.id

    create_user(uid)

    # VIP BUTTON
    if query.data == "vip":

        checkout_url = create_checkout(uid)

        await query.message.reply_text(
            f"💳 Pay VIP here:\n{checkout_url}"
        )

    # STATUS BUTTON
    elif query.data == "status":

        status = "VIP 💎" if is_vip(uid) else "FREE 🆓"

        usage = get_usage(uid)

        await query.message.reply_text(
            f"📊 Status: {status}\nMessages Used: {usage}"
        )

# ==================================================
# CHAT
# ==================================================

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.message.from_user.id

    text = update.message.text

    create_user(uid)

    # FREE LIMIT
    if not is_vip(uid):

        if get_usage(uid) >= FREE_LIMIT:

            await update.message.reply_text(
                "❌ Free limit reached.\nUpgrade VIP RM15."
            )

            return

    add_usage(uid)

    # OPENAI RESPONSE
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant."
            },
            {
                "role": "user",
                "content": text
            }
        ],
        max_tokens=200
    )

    reply = response.choices[0].message.content

    await update.message.reply_text(reply)

# ==================================================
# TELEGRAM APP
# ==================================================

telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

telegram_app.add_handler(CommandHandler("start", start))

telegram_app.add_handler(CallbackQueryHandler(buttons))

telegram_app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        chat
    )
)

# ==================================================
# START BOT
# ==================================================

if __name__ == "__main__":

    print("Bot running...")

    telegram_app.run_polling()
