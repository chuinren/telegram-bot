import os
import sqlite3
from flask import Flask, request
import requests
from openai import OpenAI

# ================= CONFIG =================

TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
STRIPE_LINK = os.getenv("STRIPE_LINK")

client = OpenAI(api_key=OPENAI_KEY)

app = Flask(__name__)

# ================= DB =================

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    vip INTEGER DEFAULT 0,
    usage_count INTEGER DEFAULT 0
)
""")
conn.commit()

FREE_LIMIT = 5

# ================= TELEGRAM API =================

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": text
    })

def send_buttons(chat_id):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    keyboard = {
        "inline_keyboard": [
            [{"text": "💎 VIP", "callback_data": "vip"}],
            [{"text": "📊 Status", "callback_data": "status"}],
        ]
    }

    requests.post(url, json={
        "chat_id": chat_id,
        "text": "Choose option:",
        "reply_markup": keyboard
    })

# ================= AI =================

def ask_ai(text):
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": text}
        ]
    )
    return res.choices[0].message.content

# ================= WEBHOOK =================

@app.route("/telegram", methods=["POST"])
def telegram_webhook():

    data = request.get_json()

    # ---------------- MESSAGE ----------------
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text == "/start":
            send_buttons(chat_id)
            return "OK", 200

        reply = ask_ai(text)
        send_message(chat_id, reply)

    # ---------------- CALLBACK ----------------
    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        data_cb = cq["data"]

        if data_cb == "vip":
            send_message(chat_id, f"Pay here: {STRIPE_LINK}")

        elif data_cb == "status":
            send_message(chat_id, "You are FREE user 🆓")

    return "OK", 200

# ================= HOME =================

@app.route("/")
def home():
    return "BOT RUNNING"

# ================= RUN =================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
