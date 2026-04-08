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

def send_telegram_alert(message, prefix_type="alert"):
    """Sends price notifications with specific icons."""
    if not (BOT_TOKEN and CHAT_ID):
        return
    
    prefixes = {
        "error": "🚨 CRITICAL ERROR:\n",
        "alert": "🔔 NEPSE Price Alert:\n",
        "buy": "🛒 BUYING OPPORTUNITY:\n",
        "emergency": "☢️ EMERGENCY EXIT:\n"
    }
    
    msg_prefix = prefixes.get(prefix_type, "🔔 Alert:\n")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": f"{msg_prefix}{message}"}, timeout=10)
    except Exception as e:
        print(f"Failed to send Telegram: {e}")

def update_ltp_cache():
    start_time = time.time()
    nepal_tz = pytz.timezone('Asia/Kathmandu')
    now_dt = datetime.datetime.now(nepal_tz)
    
    print(f"🚀 Starting Sync at {now_dt.strftime('%H:%M:%S')}")

    try:
        # 1. FETCH API DATA
        target_url = "https://chukul.com/api/data/v2/live-market/"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://chukul.com/"}
        response = requests.get(target_url, headers=headers, timeout=25)
        if response.status_code != 200:
            raise Exception(f"API Error: {response.status_code}")
        
        raw_data = response.json()

        if not DATABASE_URL:
            print("❌ DATABASE_URL missing.")
            return

        engine = create_engine(DATABASE_URL)
        
        with engine.begin() as conn:
            # 2. GET TRACKED SYMBOLS (Cache + Watchlist)
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
                            "symbol": symbol, "ltp": float(ltp),
                            "change": float(item.get('percentage_change', 0.0)),
                            "vol": int(item.get('volume', 0)),
                            "h": float(item.get('high', ltp)),
                            "l": float(item.get('low', ltp)), "ts": now_dt
                        })

            if updates:
                # 4. UPSERT TO CACHE (Ensures new watchlist items exist in cache)
                upsert_query = text("""
                    INSERT INTO public.cache (symbol, ltp, change_percent, volume, day_high, day_low, last_updated)
                    VALUES (:symbol, :ltp, :change, :vol, :h, :l, :ts)
                    ON CONFLICT (symbol) DO UPDATE SET
                        ltp = EXCLUDED.ltp, change_percent = EXCLUDED.change_percent, volume = EXCLUDED.volume,
                        day_high = EXCLUDED.day_high, day_low = EXCLUDED.day_low, last_updated = EXCLUDED.last_updated;
                """)
                conn.execute(upsert_query, updates)

                # 5. MULTI-TIER WATCHLIST ALERT LOGIC
                alert_query = text("""
                    SELECT w.symbol, c.ltp, w.target_price, w.stop_loss, w.notes, 
                           w.hard_target, w.hard_sl, w.entry_1, w.entry_must
                    FROM public.watchlist w
                    JOIN public.cache c ON w.symbol = c.symbol
                    WHERE (w.target_price > 0 AND c.ltp >= w.target_price)
                       OR (w.stop_loss > 0 AND c.ltp <= w.stop_loss)
                       OR (w.hard_target > 0 AND c.ltp >= w.hard_target)
                       OR (w.hard_sl > 0 AND c.ltp <= w.hard_sl)
                       OR (w.entry_1 > 0 AND c.ltp <= w.entry_1)
                       OR (w.entry_must > 0 AND c.ltp <= w.entry_must);
                """)
                
                hits = conn.execute(alert_query).fetchall()
                for row in hits:
                    s, ltp, tp, sl, note, h_tp, h_sl, e1, em = row
                    
                    # --- SELL SIDE ALERTS (Prioritizing "Hard" exits) ---
                    if h_tp and ltp >= h_tp:
                        send_telegram_alert(f"🚨 HARD TARGET HIT: {s}\nPrice: {ltp}\nNote: {note}", "emergency")
                    elif h_sl and ltp <= h_sl:
                        send_telegram_alert(f"💀 HARD STOP LOSS HIT: {s}\nPrice: {ltp}\nNote: {note}", "emergency")
                    elif tp and ltp >= tp:
                        send_telegram_alert(f"🎯 TARGET REACHED: {s}\nPrice: {ltp}\nNote: {note}", "alert")
                    elif sl and ltp <= sl:
                        send_telegram_alert(f"🛑 STOP LOSS HIT: {s}\nPrice: {ltp}\nNote: {note}", "alert")

                    # --- BUY SIDE ALERTS ---
                    if em and ltp <= em:
                        send_telegram_alert(f"🔥 MUST BUY ENTRY: {s}\nPrice: {ltp}\nNote: {note}", "buy")
                    elif e1 and ltp <= e1:
                        send_telegram_alert(f"🛒 ENTRY 1 REACHED: {s}\nPrice: {ltp}\nNote: {note}", "buy")

                print(f"✅ Sync Complete. {len(updates)} symbols updated. {len(hits)} alerts triggered.")
            else:
                print("⚠️ No symbols matched API data.")

    except Exception as e:
        print(f"Error: {e}")
        send_telegram_alert(str(e), "error")

if __name__ == "__main__":
    update_ltp_cache()
