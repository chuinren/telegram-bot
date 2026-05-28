import os
import sqlite3
import asyncio
import stripe

from flask import Flask, request
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
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
# MEMORY SYSTEM
# ==================================================

def save_memory(uid, role, content):

    cursor.execute(
        "INSERT INTO memory (user_id, role, content) VALUES (?, ?, ?)",
        (uid, role, content)
    )

    conn.commit()

def load_memory(uid):

    cursor.execute(
        """
        SELECT role, content
        FROM memory
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 10
        """,
        (uid,)
    )

    rows = cursor.fetchall()

    return list(reversed(rows))

# ==================================================
# STRIPE CHECKOUT
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
                        "name": "RTK AI VIP RM15"
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
# OPENAI MEMORY CHAT
# ==================================================

def ask_ai(uid, text):

    history = load_memory(uid)

    messages = [
        {
            "role": "system",
            "content": (
                "You are RTK AI. "
                "Reply clearly, intelligently, and briefly."
            )
        }
    ]

    for role, content in history:
        messages.append({
            "role": role,
            "content": content
        })

    messages.append({
        "role": "user",
        "content": text
    })

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=250
    )

    return response.choices[0].message.content

# ==================================================
# TELEGRAM COMMANDS
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.message.from_user.id

    create_user(uid)

    keyboard = [
        [
            InlineKeyboardButton(
                "💎 VIP RM15",
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
        "🤖 RTK AI READY",
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

    # SAVE USER MEMORY
    save_memory(uid, "user", text)

    # AI REPLY
    reply = ask_ai(uid, text)

    # SAVE AI MEMORY
    save_memory(uid, "assistant", reply)

    await update.message.reply_text(reply)

# ==================================================
# TELEGRAM APP
# ==================================================

telegram_app = Application.builder().token(
    TELEGRAM_TOKEN
).build()

telegram_app.add_handler(
    CommandHandler("start", start)
)

telegram_app.add_handler(
    CallbackQueryHandler(buttons)
)

telegram_app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        chat
    )
)

# ==================================================
# TELEGRAM WEBHOOK
# ==================================================

@app.route("/telegram", methods=["POST"])
def telegram_webhook():

    data = request.get_json(force=True)

    update = Update.de_json(data, telegram_app.bot)

    asyncio.run(
        telegram_app.process_update(update)
    )

    return "OK", 200

# ==================================================
# STRIPE WEBHOOK
# ==================================================

@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():

    payload = request.json

    try:

        event = stripe.Event.construct_from(
            payload,
            stripe.api_key
        )

        if event["type"] == "checkout.session.completed":

            session = event["data"]["object"]

            user_id = int(
                session["metadata"]["user_id"]
            )

            activate_vip(user_id)

    except Exception as e:
        return str(e), 400

    return "OK", 200

# ==================================================
# HOME
# ==================================================

@app.route("/")
def home():
    return "RTK AI SAAS BOT RUNNING"

# ==================================================
# STARTUP
# ==================================================

if __name__ == "__main__":

    # Initialize telegram app
    asyncio.run(
        telegram_app.initialize()
    )

    # Set telegram webhook
    webhook_url = f"{BASE_URL}/telegram"

    asyncio.run(
        telegram_app.bot.set_webhook(
            url=webhook_url
        )
    )

    print("RTK AI WEBHOOK RUNNING")

    # Render PORT binding
    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
