import os
import sqlite3
import requests
import pandas as pd

from flask import Flask, request
from openai import OpenAI
from ta.momentum import RSIIndicator

# ================= CONFIG =================

TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_KEY)

app = Flask(__name__)

# ================= DATABASE =================

conn = sqlite3.connect("crypto_saas.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    vip INTEGER DEFAULT 0,
    usage_count INTEGER DEFAULT 0
)
""")

conn.commit()

FREE_LIMIT = 10

# ================= DB FUNCTIONS =================

def create_user(uid):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    conn.commit()

def get_user(uid):
    cursor.execute("SELECT vip, usage_count FROM users WHERE user_id=?", (uid,))
    return cursor.fetchone()

def add_usage(uid):
    cursor.execute("UPDATE users SET usage_count = usage_count + 1 WHERE user_id=?", (uid,))
    conn.commit()

# ================= TELEGRAM =================

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": text
    })

# ================= CRYPTO DATA =================

def get_market_data(symbol="bitcoin"):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/market_chart"
    params = {"vs_currency": "usd", "days": 7}

    r = requests.get(url, params=params).json()

    prices = r.get("prices", [])
    if not prices:
        return None

    df = pd.DataFrame(prices, columns=["timestamp", "price"])
    return df

# ================= TECHNICAL ANALYSIS =================

def analyze_market(symbol="bitcoin"):

    df = get_market_data(symbol)

    if df is None:
        return None

    df["rsi"] = RSIIndicator(df["price"], window=14).rsi()

    price = df["price"].iloc[-1]
    rsi = df["rsi"].iloc[-1]

    if rsi < 30:
        signal = "🟢 BUY ZONE (Oversold)"
    elif rsi > 70:
        signal = "🔴 RISK ZONE (Overbought)"
    else:
        signal = "🟡 NEUTRAL / HOLD"

    return {
        "price": float(price),
        "rsi": float(rsi),
        "signal": signal
    }

# ================= AI ANALYSIS =================

def ai_report(symbol, data):

    prompt = f"""
You are a professional crypto trading analyst.

Coin: {symbol}
Price: {data['price']}
RSI: {data['rsi']}
Signal: {data['signal']}

Rules:
- No guaranteed predictions
- Explain clearly
- Focus on risk and probability
"""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a crypto trading analyst."},
            {"role": "user", "content": prompt}
        ]
    )

    return res.choices[0].message.content

# ================= TELEGRAM WEBHOOK =================

@app.route("/telegram", methods=["POST"])
def telegram():

    data = request.get_json()

    if "message" in data:

        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        uid = data["message"]["from"]["id"]

        create_user(uid)
        user = get_user(uid)

        vip = user[0] if user else 0
        usage = user[1] if user else 0

        # ================= START =================
        if text == "/start":
            send_message(chat_id,
                "🚀 Crypto Pro Trading AI Bot\n\n"
                "Commands:\n"
                "/trade bitcoin\n"
                "/trade ethereum\n\n"
                "Free limit active"
            )
            return "OK", 200

        # ================= LIMIT =================
        if vip == 0 and usage >= FREE_LIMIT:
            send_message(chat_id,
                "❌ Free limit reached\n💎 Upgrade VIP to continue"
            )
            return "OK", 200

        # ================= TRADE COMMAND =================
        if text.startswith("/trade"):

            symbol = text.replace("/trade", "").strip().lower()
            if not symbol:
                symbol = "bitcoin"

            data = analyze_market(symbol)

            if data is None:
                send_message(chat_id, "❌ Invalid coin or API error")
                return "OK", 200

            report = ai_report(symbol, data)

            add_usage(uid)

            final_msg = f"""
📊 {symbol.upper()} ANALYSIS

Price: ${data['price']}
RSI: {data['rsi']:.2f}
Signal: {data['signal']}

🧠 AI Insight:
{report}
"""

            send_message(chat_id, final_msg)
            return "OK", 200

        # ================= DEFAULT CHAT =================
        send_message(chat_id, "Use /trade bitcoin or /trade ethereum")

    return "OK", 200

# ================= HEALTH =================

@app.route("/")
def home():
    return "CRYPTO AI SAAS BOT RUNNING"

# ================= RUN =================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
