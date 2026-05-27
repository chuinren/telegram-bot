import os
import threading
import sqlite3
from flask import Flask

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

from openai import OpenAI

# =========================
# ENV VARIABLES
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# FLASK WEB SERVER
# (Fix Render free port issue)
# =========================
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Telegram AI Bot Running"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web).start()

# =========================
# DATABASE
# =========================
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

# =========================
# SETTINGS
# =========================
FREE_LIMIT = 5

STRIPE_LINK = "https://buy.stripe.com/aFadR84afcNQ2N59dSgA802"

# =========================
# MEMORY
# =========================
chat_memory = {}

# =========================
# DATABASE FUNCTIONS
# =========================
def get_user(user_id):
    cursor.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,)
    )
    return cursor.fetchone()

def create_user(user_id):
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, is_vip, usage_count) VALUES (?, 0, 0)",
        (user_id,)
    )
    conn.commit()

def get_usage(user_id):
    cursor.execute(
        "SELECT usage_count FROM users WHERE user_id = ?",
        (user_id,)
    )

    result = cursor.fetchone()

    if result:
        return result[0]

    return 0

def increase_usage(user_id):
    cursor.execute(
        "UPDATE users SET usage_count = usage_count + 1 WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()

def is_vip(user_id):
    cursor.execute(
        "SELECT is_vip FROM users WHERE user_id = ?",
        (user_id,)
    )

    result = cursor.fetchone()

    if result:
        return result[0] == 1

    return False

def activate_vip(user_id):
    cursor.execute(
        "UPDATE users SET is_vip = 1 WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()

# =========================
# START COMMAND
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id
    create_user(user_id)

    keyboard = [
        [InlineKeyboardButton("💬 Chat AI", callback_data="chat")],
        [InlineKeyboardButton("💰 VIP", callback_data="vip")],
        [InlineKeyboardButton("📊 Status", callback_data="status")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🤖 AI BOT READY",
        reply_markup=reply_markup
    )

# =========================
# BUTTON HANDLER
# =========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    create_user(user_id)

    if query.data == "vip":

        keyboard = [
            [InlineKeyboardButton("💳 Pay VIP", url=STRIPE_LINK)],
            [InlineKeyboardButton("I Paid", callback_data="paid")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(
            "💰 VIP PLAN\n\nRM10/month",
            reply_markup=reply_markup
        )

    elif query.data == "paid":

        activate_vip(user_id)

        await query.message.reply_text(
            "✅ VIP Activated!"
        )

    elif query.data == "status":

        status = "VIP 💎" if is_vip(user_id) else "FREE 🆓"

        usage = get_usage(user_id)

        await query.message.reply_text(
            f"📊 STATUS\n\n"
            f"Plan: {status}\n"
            f"Messages Used: {usage}"
        )

    elif query.data == "chat":

        await query.message.reply_text(
            "💬 Send me a message."
        )

    elif query.data == "help":

        await query.message.reply_text(
            "ℹ️ HELP MENU\n\n"
            "• Send message to chat AI\n"
            "• VIP removes limits\n"
            "• Status checks account"
        )

# =========================
# CHAT HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id
    user_text = update.message.text

    create_user(user_id)

    if not is_vip(user_id):

        usage = get_usage(user_id)

        if usage >= FREE_LIMIT:

            await update.message.reply_text(
                "❌ Free limit reached.\n"
                "Upgrade to VIP."
            )

            return

    increase_usage(user_id)

    # =========================
    # MEMORY
    # =========================
    if user_id not in chat_memory:
        chat_memory[user_id] = []

    chat_memory[user_id].append({
        "role": "user",
        "content": user_text
    })

    messages = [
        {
            "role": "system",
            "content": (
                "You are a smart, friendly, short Telegram AI assistant."
            )
        }
    ] + chat_memory[user_id][-10:]

    try:

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=300
        )

        reply = response.choices[0].message.content

        chat_memory[user_id].append({
            "role": "assistant",
            "content": reply
        })

        await update.message.reply_text(reply)

    except Exception as e:

        await update.message.reply_text(
            f"Error:\n{str(e)}"
        )

# =========================
# RUN TELEGRAM BOT
# =========================
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))

app.add_handler(
    CallbackQueryHandler(button_handler)
)

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    )
)

print("Bot running...")

app.run_polling()
