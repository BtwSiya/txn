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
    if not sig:
        return False
    gen = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(gen, sig)

# ================= WEBHOOK =================
@app.route("/webhook", methods=["POST"])
def webhook():

    sig = request.headers.get("X-Razorpay-Signature")
    body = request.data

    if not verify(body, sig):
        return "Invalid Signature", 400

    data = json.loads(body)

    if data.get("event") != "payment.captured":
        return "Ignored"

    p = data.get("payload", {}).get("payment", {}).get("entity", {})
    if p.get("status") != "captured":
        return "Ignored"

    # ===== NOTES FIX =====
    notes = p.get("notes", {})
    if isinstance(notes, list):
        notes = notes[0] if notes else {}

    name = notes.get("name", "Customer")
    phone = notes.get("phone", "N/A")

    # ===== PAYMENT INFO =====
    amount = p.get("amount", 0) / 100
    utr = p.get("acquirer_data", {}).get("rrn", "N/A")
    pid = p.get("id", "N/A")

    # ===== TIME FIX =====
    created = p.get("created_at")
    if created:
        time = datetime.fromtimestamp(created).strftime("%d %b %Y %I:%M %p")
    else:
        time = datetime.now().strftime("%d %b %Y %I:%M %p")

    save_payment(pid, name, amount, utr, time)
    bal = total_balance()

    msg = f"""
━━━━━━━━━━━━━━━━━━
✅ **PAYMENT RECEIVED**

👤 **Name**: {name}
📞 **Phone**: {phone}
💰 **Amount**: ₹{amount}
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
