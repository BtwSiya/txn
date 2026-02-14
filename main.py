import os, hmac, hashlib, sqlite3, requests, json
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(os.getenv("ADMIN1")), int(os.getenv("ADMIN2"))]
GROUP_ID = -1002843633996
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
    c.execute("SELECT id FROM payments WHERE id=?", (pid,))
    if c.fetchone():
        conn.close()
        return

    c.execute("INSERT INTO payments VALUES (?,?,?,?,?)",
              (pid, name, amount, utr, time))
    conn.commit()
    conn.close()

def total_balance():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(amount),0) FROM payments")
    total = c.fetchone()[0]
    conn.close()
    return round(total,2)

# ================= TELEGRAM =================
def send_msg(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for cid in ADMIN_IDS + [GROUP_ID]:
        requests.post(url, json={
            "chat_id": cid,
            "text": text,
            "parse_mode":"Markdown"
        })

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

    # ===== NAME FIX =====
    notes = p.get("notes") or {}
    if isinstance(notes, list):
        notes = notes[0] if notes else {}

    name = notes.get("name") or notes.get("Name") or "Customer"
    phone = notes.get("phone") or notes.get("Phone") or "N/A"

    # ===== PAYMENT =====
    amount = p.get("amount", 0) / 100
    utr = p.get("acquirer_data", {}).get("rrn", "N/A")
    pid = p.get("id")

    # ===== TIME FIX (UTC → IST) =====
    created = p.get("created_at")
    if created:
        ist_time = datetime.utcfromtimestamp(created) + timedelta(hours=5, minutes=30)
        time = ist_time.strftime("%d %b %Y %I:%M %p")
    else:
        time = datetime.now().strftime("%d %b %Y %I:%M %p")

    save_payment(pid, name, amount, utr, time)
    bal = total_balance()

    msg = f"""
━━━━━━━━━━━━━━━━━━
✅ 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗥𝗘𝗖𝗘𝗜𝗩𝗘𝗗

👤 𝗡𝗮𝗺𝗲: {name}
📞 𝗣𝗵𝗼𝗻𝗲: {phone}
💰 𝗔𝗺𝗼𝘂𝗻𝘁: ₹{amount}
🧾 𝗨𝗧𝗥: {utr}
🔗 𝗧𝘅𝗻 𝗜𝗗: {pid}
⏰ 𝗧𝗶𝗺𝗲: {time}

📊 𝗧𝗼𝘁𝗮𝗹 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ₹{bal}
━━━━━━━━━━━━━━━━━━
𝙏𝙤𝙭𝙞𝙘𝙇𝙖𝙗𝙨 𝙋𝙖𝙮𝙢𝙚𝙣𝙩 𝘼𝙡𝙚𝙧𝙩𝙨 🌷🫧🌾
"""

    send_msg(msg)
    return jsonify({"status":"ok"})

# ================= START =================
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
