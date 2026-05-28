import os
import threading
from flask import Flask

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

from openai import OpenAI

# ================= ENV =================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_KEY)

# ================= FLASK =================

app_web = Flask(__name__)

@app_web.route("/")
def home():
    return "Bot is running"

def run_web():
    app_web.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )

# ================= BOT DATA =================

VIP_USERS = set()
user_usage = {}

FREE_LIMIT = 5

STRIPE_LINK = "https://buy.stripe.com/aFadR84afcNQ2N59dSgA802"

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [InlineKeyboardButton("💬 Chat AI", callback_data="chat")],
        [InlineKeyboardButton("💰 VIP", callback_data="vip")],
        [InlineKeyboardButton("📊 Status", callback_data="status")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]

    await update.message.reply_text(
        "🤖 AI BOT READY",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= BUTTONS =================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data == "vip":

        keyboard = [
            [InlineKeyboardButton("💳 Pay VIP", url=STRIPE_LINK)],
            [InlineKeyboardButton("✅ I Paid", callback_data="paid")]
        ]

        await query.message.reply_text(
            "💎 VIP PLAN",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "paid":

        VIP_USERS.add(user_id)

        await query.message.reply_text(
            "✅ VIP Activated!"
        )

    elif query.data == "status":

        status = "VIP 💎" if user_id in VIP_USERS else "FREE 🆓"

        await query.message.reply_text(
            f"Status: {status}\nUsage: {user_usage.get(user_id, 0)}"
        )

    elif query.data == "help":

        await query.message.reply_text(
            "Send any message to chat with AI."
        )

# ================= CHAT =================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        user_id = update.message.from_user.id
        user_text = update.message.text

        user_usage[user_id] = user_usage.get(user_id, 0) + 1

        # FREE LIMIT
        if user_id not in VIP_USERS:

            if user_usage[user_id] > FREE_LIMIT:

                await update.message.reply_text(
                    "❌ Free limit reached.\nUpgrade VIP."
                )

                return

        # OPENAI
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant."
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ]
        )

        reply = response.choices[0].message.content

        await update.message.reply_text(reply)

    except Exception as e:

        print("CHAT ERROR:", e)

        await update.message.reply_text(
            "❌ Error occurred."
        )

# ================= TELEGRAM APP =================

telegram_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

telegram_app.add_handler(
    CommandHandler("start", start)
)

telegram_app.add_handler(
    CallbackQueryHandler(button_handler)
)

telegram_app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    )
)

# ================= START =================

print("Bot running...")

# Flask for Render health check
threading.Thread(
    target=run_web,
    daemon=True
).start()

# Telegram polling
telegram_app.run_polling(
    drop_pending_updates=True
)
