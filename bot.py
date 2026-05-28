import os
import requests
from flask import Flask, request
from openai import OpenAI

# ================= CONFIG =================

TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_KEY)

app = Flask(__name__)

# ================= TELEGRAM HELPERS =================

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": text
    })

# ================= OPENAI =================

def ask_ai(text):
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": text}
        ]
    )
    return res.choices[0].message.content

# ================= WEBHOOK ROUTE =================

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    data = request.get_json()

    # ---------------- MESSAGE ----------------
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        # /start command
        if text == "/start":
            send_message(chat_id, "🤖 Bot is running! Send me anything.")
            return "OK", 200

        # AI reply
        reply = ask_ai(text)
        send_message(chat_id, reply)

    return "OK", 200

# ================= HEALTH CHECK =================

@app.route("/")
def home():
    return "BOT IS RUNNING"

# ================= START =================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
