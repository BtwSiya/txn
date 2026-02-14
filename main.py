import os, hmac, hashlib, sqlite3, requests, json
from flask import Flask, request, jsonify
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(os.getenv("ADMIN1")), int(os.getenv("ADMIN2"))]
GROUP_ID = int(os.getenv("GROUP_ID"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

DB = "payments.db"
app = Flask(__name__)

# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS payments(
        id TEXT PRIMARY KEY,
        name TEXT,
        amount REAL,
        utr TEXT,
        time TEXT
    )
    """)
    conn.commit()
    conn.close()

def save_payment(pid, name, amount, utr, time):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO payments VALUES (?,?,?,?,?)",
                  (pid, name, amount, utr, time))
        conn.commit()
    except:
        pass
    conn.close()

def total_balance():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM payments")
    total = c.fetchone()[0] or 0
    conn.close()
    return round(total,2)

# ================= TELEGRAM =================
def send_msg(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for cid in ADMIN_IDS + [GROUP_ID]:
        requests.post(url, json={"chat_id": cid, "text": text, "parse_mode":"HTML"})

def send_single(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

# ================= VERIFY =================
def verify(body, sig):
    gen = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(gen, sig)

# ================= TELEGRAM COMMANDS =================
@app.route(f"/bot{BOT_TOKEN}", methods=["POST"])
def telegram_commands():

    data = request.json
    if "message" not in data:
        return "ok"

    msg = data["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")

    if text == "/start":
        welcome = """
🤖 <b>Welcome to ToxicLabs Payment Alerts Bot</b>

Commands:
💰 /balance → Show total collection

This bot sends real-time Razorpay alerts.
"""
        send_single(chat_id, welcome)
        return "ok"

    if chat_id not in ADMIN_IDS:
        send_single(chat_id, "Not Authorized Babe")
        return "ok"

    if text == "/balance":
        bal = total_balance()
        send_single(chat_id, f"💰 <b>Total Balance:</b> ₹{bal}")

    return "ok"

# ================= WEBHOOK =================
@app.route("/webhook", methods=["POST"])
def webhook():

    sig = request.headers.get("X-Razorpay-Signature")
    body = request.data

    if not verify(body, sig):
        return "Invalid", 400

    data = json.loads(body)

    if data["event"] != "payment.captured":
        return "Ignored"

    p = data["payload"]["payment"]["entity"]
    if p["status"] != "captured":
        return "Ignored"

    amount = p["amount"] / 100
    name = p.get("notes", {}).get("name", "Customer")
    utr = p.get("acquirer_data", {}).get("rrn", "N/A")
    pid = p["id"]
    time = datetime.fromtimestamp(p["created_at"]).strftime("%d %b %Y %I:%M %p")

    save_payment(pid, name, amount, utr, time)
    bal = total_balance()

    msg = f"""
━━━━━━━━━━━━━━━━━━
✅ <b>PAYMENT RECEIVED</b>

👤 <b>Customer:</b> {name}
💰 <b>Amount:</b> ₹{amount}
🧾 <b>UTR:</b> {utr}
🔗 <b>Txn ID:</b> {pid}
⏰ <b>Time:</b> {time}

📊 <b>Total Collection:</b> ₹{bal}
━━━━━━━━━━━━━━━━━━
🤖 <b>ToxicLabs Payment Alerts</b>
"""

    send_msg(msg)
    return jsonify({"status":"ok"})

# ================= START =================
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
