import os
import requests
from sqlalchemy import create_engine, text
import datetime
import pytz

# --- CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def send_telegram_alert(message):
    """Sends a failure alert to your Telegram."""
    if BOT_TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        try:
            requests.post(url, data={"chat_id": CHAT_ID, "text": f"⚠️ NEPSE Sync Failure:\n{message}"}, timeout=10)
        except Exception as e:
            print(f"Failed to send Telegram: {e}")

def update_ltp_cache():
    nepal_tz = pytz.timezone('Asia/Kathmandu')
    now_dt = datetime.datetime.now(nepal_tz)
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"🚀 Syncing NEPSE at {now_str}")

    # Direct URL - No Proxy
    target_url = "https://chukul.com/api/data/v2/live-market/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://chukul.com/"
    }

    try:
        # 1. FETCH DATA
        response = requests.get(target_url, headers=headers, timeout=20)
        if response.status_code != 200:
            error_msg = f"Chukul API returned {response.status_code}"
            print(f"❌ {error_msg}")
            send_telegram_alert(error_msg)
            return

        data = response.json()
        
        # 2. PREPARE DATA BATCH
        updates = []
        for item in data:
            symbol = str(item.get('symbol', '')).strip().upper()
            ltp = item.get('ltp')
            
            if symbol and ltp is not None:
                updates.append({
                    "symbol": symbol,
                    "ltp": float(ltp),
                    "change": float(item.get('percentage_change', 0.0)),
                    "vol": int(item.get('volume', 0)),
                    "h": float(item.get('high', ltp)),
                    "l": float(item.get('low', ltp)),
                    "ts": now_dt  # Database uses this timestamp
                })

        # 3. FAST BATCH DATABASE UPDATE
        if not DATABASE_URL:
            print("❌ DATABASE_URL missing.")
            return

        engine = create_engine(DATABASE_URL)
        with engine.begin() as conn:
            # Batch Update Logic: Much faster than a loop
            update_query = text("""
                UPDATE public.cache 
                SET ltp = :ltp, 
                    change_percent = :change,
                    volume = :vol,
                    day_high = :h,
                    day_low = :l,
                    last_updated = :ts
                WHERE symbol = :symbol;
            """)
            
            result = conn.execute(update_query, updates)
            updated_count = result.rowcount

        print(f"✅ Sync Complete. {updated_count} stocks updated.")

    except Exception as e:
        error_detail = str(e)
        print(f"🚨 CRITICAL ERROR: {error_detail}")
        send_telegram_alert(error_detail)

if __name__ == "__main__":
    update_ltp_cache()
