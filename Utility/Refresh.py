import os
import requests
from sqlalchemy import create_engine, text
import datetime
import pytz
import time

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
    start_time = time.time()
    nepal_tz = pytz.timezone('Asia/Kathmandu')
    now_dt = datetime.datetime.now(nepal_tz)
    
    print(f"🚀 [0.0s] Starting NEPSE Sync at {now_dt.strftime('%H:%M:%S')}")

    # 1. FETCH API DATA (Do this first while DB might be waking up)
    target_url = "https://chukul.com/api/data/v2/live-market/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://chukul.com/"
    }

    try:
        api_start = time.time()
        response = requests.get(target_url, headers=headers, timeout=25)
        if response.status_code != 200:
            raise Exception(f"Chukul API returned {response.status_code}")
        
        raw_data = response.json()
        print(f"📡 [{round(time.time() - api_start, 2)}s] API Data Downloaded ({len(raw_data)} symbols found).")

        # 2. DATABASE HANDSHAKE
        if not DATABASE_URL:
            print("❌ DATABASE_URL missing.")
            return

        db_start = time.time()
        engine = create_engine(DATABASE_URL)
        
        with engine.begin() as conn:
            print(f"🛢️  [{round(time.time() - db_start, 2)}s] DB Connected (Neon Wake-up).")
            
            # 3. GET ACTIVE SYMBOLS FROM YOUR CACHE
            # This is the "Filter" that prevents updating 300+ useless rows
            result = conn.execute(text("SELECT symbol FROM public.cache"))
            portfolio_symbols = {row[0].upper() for row in result}
            print(f"📋 Found {len(portfolio_symbols)} symbols in your cache to update.")

            # 4. FILTER API DATA IN MEMORY (Lightning Fast)
            updates = []
            for item in raw_data:
                symbol = str(item.get('symbol', '')).strip().upper()
                
                if symbol in portfolio_symbols:
                    ltp = item.get('ltp')
                    if ltp is not None:
                        updates.append({
                            "symbol": symbol,
                            "ltp": float(ltp),
                            "change": float(item.get('percentage_change', 0.0)),
                            "vol": int(item.get('volume', 0)),
                            "h": float(item.get('high', ltp)),
                            "l": float(item.get('low', ltp)),
                            "ts": now_dt
                        })

            # 5. EXECUTE PRECISION BATCH UPDATE
            if updates:
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
                conn.execute(update_query, updates)
                print(f"✅ [{round(time.time() - start_time, 2)}s] Sync Complete. {len(updates)} stocks updated.")
            else:
                print("⚠️ No matching symbols found in the API data.")

    except Exception as e:
        error_detail = str(e)
        print(f"🚨 CRITICAL ERROR: {error_detail}")
        send_telegram_alert(error_detail)

if __name__ == "__main__":
    update_ltp_cache()
