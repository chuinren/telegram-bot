import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")

telegram_app = Application.builder().token(TOKEN).build()


async def start(update, context):
    await update.message.reply_text("Bot is working")


async def chat(update, context):
    await update.message.reply_text("Received: " + update.message.text)


telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT, chat))


@app.route("/telegram", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)

    # ✅ THIS IS THE ONLY CORRECT WAY IN PTB v20+
    telegram_app.update_queue.put_nowait(update)

    return "OK", 200


@app.route("/")
def home():
    return "OK"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
