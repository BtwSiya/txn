import os, hmac, hashlib, sqlite3, requests, json
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
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
    c.execute("""CREATE TABLE IF NOT EXISTS payments(
        id TEXT PRIMARY KEY,
        name TEXT,
        amount REAL,
        utr TEXT,
        time TEXT
    )""")
    conn.commit()
    conn.close()

def save_payment(pid, name, amount, utr, time):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id FROM payments WHERE id=?", (pid,))
    if not c.fetchone():
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
        r = requests.post(url, json={
            "chat_id": cid,
            "text": text,
            "parse_mode":"HTML"
        })
        print("TG:", r.text)   # DEBUG

# ================= VERIFY =================
def verify(body, sig):
    if not sig:
        return False
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
    text = msg.get("text","")

    if text == "/start":
        send_msg("🤖 ToxicLabs Payment Alerts Bot\n\nBy Toxic — @iscxm")
        return "ok"

    if chat_id not in ADMIN_IDS:
        return "ok"

    if text == "/balance":
        bal = total_balance()
        send_msg(f"💰 **Total Balance**:</b> ₹{bal}")
    return "ok"

# ================= WEBHOOK =================
@app.route("/webhook", methods=["POST"])
def webhook():

    sig = request.headers.get("X-Razorpay-Signature")
    body = request.data

    if not verify(body, sig):
        print("BAD SIGN")
        return "Invalid",400

    data = json.loads(body)

    if data.get("event") != "payment.captured":
        return "Ignored"

    p = data.get("payload",{}).get("payment",{}).get("entity",{})

    # NAME LOGIC
    notes = p.get("notes") or {}
    if isinstance(notes,list):
        notes = notes[0] if notes else {}

    name = notes.get("name") or notes.get("Name") \
        or p.get("email") \
        or p.get("contact") \
        or "Customer"

    phone = p.get("contact","N/A")
    amount = p.get("amount",0)/100
    utr = p.get("acquirer_data",{}).get("rrn","N/A")
    pid = p.get("id")

    created = p.get("created_at")
    if created:
        ist = datetime.utcfromtimestamp(created)+timedelta(hours=5,minutes=30)
        time = ist.strftime("%d %b %Y %I:%M %p")
    else:
        time = datetime.now().strftime("%d %b %Y %I:%M %p")

    save_payment(pid,name,amount,utr,time)
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
    return jsonify({"ok":True})

# ================= START =================
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
