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

def send_telegram_alert(message, is_error=True):
    """Sends a failure alert or price notification to your Telegram."""
    if BOT_TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        prefix = "⚠️ NEPSE Sync Failure:\n" if is_error else "🔔 NEPSE Price Alert:\n"
        try:
            requests.post(url, data={"chat_id": CHAT_ID, "text": f"{prefix}{message}"}, timeout=10)
        except Exception as e:
            print(f"Failed to send Telegram: {e}")

def update_ltp_cache():
    start_time = time.time()
    nepal_tz = pytz.timezone('Asia/Kathmandu')
    now_dt = datetime.datetime.now(nepal_tz)
    
    print(f"🚀 [0.0s] Starting NEPSE Sync at {now_dt.strftime('%H:%M:%S')}")

    # 1. FETCH API DATA
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

        if not DATABASE_URL:
            print("❌ DATABASE_URL missing.")
            return

        engine = create_engine(DATABASE_URL)
        
        with engine.begin() as conn:
            # 2. GET ALL SYMBOLS WE CARE ABOUT
            sym_query = text("SELECT symbol FROM public.cache UNION SELECT symbol FROM public.watchlist")
            tracked_symbols = {row[0].upper() for row in conn.execute(sym_query)}
            
            # 3. FILTER API DATA
            updates = []
            for item in raw_data:
                symbol = str(item.get('symbol', '')).strip().upper()
                if symbol in tracked_symbols:
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

            if updates:
                # 4. UPSERT DATA (Handles new watchlist items automatically)
                upsert_query = text("""
                    INSERT INTO public.cache (symbol, ltp, change_percent, volume, day_high, day_low, last_updated)
                    VALUES (:symbol, :ltp, :change, :vol, :h, :l, :ts)
                    ON CONFLICT (symbol) DO UPDATE SET
                        ltp = EXCLUDED.ltp,
                        change_percent = EXCLUDED.change_percent,
                        volume = EXCLUDED.volume,
                        day_high = EXCLUDED.day_high,
                        day_low = EXCLUDED.day_low,
                        last_updated = EXCLUDED.last_updated;
                """)
                conn.execute(upsert_query, updates)
                print(f"✅ Sync Complete. {len(updates)} symbols processed.")

                # 5. WATCHLIST ALERT LOGIC
                alert_query = text("""
                    SELECT w.symbol, c.ltp, w.target_price, w.stop_loss, w.notes
                    FROM public.watchlist w
                    JOIN public.cache c ON w.symbol = c.symbol
                    WHERE (w.target_price > 0 AND c.ltp >= w.target_price) 
                       OR (w.stop_loss > 0 AND c.ltp <= w.stop_loss);
                """)
                
                hits = conn.execute(alert_query).fetchall()
                for symbol, ltp, target, sl, notes in hits:
                    if target > 0 and ltp >= target:
                        send_telegram_alert(f"🎯 TARGET REACHED: {symbol}\nLTP: {ltp} (Target: {target})\nNote: {notes}", is_error=False)
                    elif sl > 0 and ltp <= sl:
                        send_telegram_alert(f"🛑 STOP LOSS HIT: {symbol}\nLTP: {ltp} (SL: {sl})\nNote: {notes}", is_error=False)
            else:
                print("⚠️ No matching symbols found.")

    except Exception as e:
        send_telegram_alert(str(e), is_error=True)

if __name__ == "__main__":
    update_ltp_cache()
