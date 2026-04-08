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


def check_watchlist_triggers(conn):
    """Compares fresh LTP from cache against user-defined Watchlist targets/SL."""
    print("🔍 Checking Watchlist for hits...")
    
    # Query to join fresh prices with your targets
    trigger_query = text("""
        SELECT 
            w.symbol, 
            c.ltp, 
            w.target_price, 
            w.stop_loss, 
            w.notes
        FROM public.watchlist w
        JOIN public.cache c ON w.symbol = c.symbol
    """)
    
    results = conn.execute(trigger_query)
    
    for row in results:
        symbol, ltp, target, sl, notes = row
        
        # 1. Check Target Hit
        if target and ltp >= target:
            msg = f"🎯 TARGET HIT: {symbol}\nPrice: {ltp} (Target: {target})\nNote: {notes}"
            send_telegram_alert(msg)
            print(f"  -> {symbol} hit Target!")

        # 2. Check Stop Loss Hit
        elif sl and ltp <= sl:
            msg = f"🛑 STOP LOSS HIT: {symbol}\nPrice: {ltp} (SL: {sl})\nNote: {notes}"
            send_telegram_alert(msg)
            print(f"  -> {symbol} hit SL!")


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

        # 2. DATABASE HANDSHAKE
        if not DATABASE_URL:
            print("❌ DATABASE_URL missing.")
            return

        db_start = time.time()
        engine = create_engine(DATABASE_URL)
        
        with engine.begin() as conn:
            print(f"🛢️  [{round(time.time() - db_start, 2)}s] DB Connected.")
            
            # 3. GET SYMBOLS FROM BOTH CACHE AND WATCHLIST
            # This ensures we have data for both portfolio tracking and alerts
            sym_query = text("SELECT symbol FROM public.cache UNION SELECT symbol FROM public.watchlist")
            tracked_symbols = {row[0].upper() for row in conn.execute(sym_query)}
            print(f"📋 Tracking {len(tracked_symbols)} unique symbols.")

            # 4. FILTER API DATA IN MEMORY
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

            # 5. EXECUTE BATCH UPDATE
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
                print(f"✅ [{round(time.time() - start_time, 2)}s] Sync Complete.")

                # 6. WATCHLIST ALERT CHECK
                # We join fresh prices in cache with watchlist targets
                alert_query = text("""
                    SELECT w.symbol, c.ltp, w.target_price, w.stop_loss, w.notes
                    FROM public.watchlist w
                    JOIN public.cache c ON w.symbol = c.symbol
                    WHERE c.ltp >= w.target_price OR c.ltp <= w.stop_loss;
                """)
                
                hits = conn.execute(alert_query).fetchall()
                for hit in hits:
                    symbol, ltp, target, sl, notes = hit
                    
                    if ltp >= target:
                        msg = f"🎯 TARGET REACHED: {symbol}\nLTP: {ltp} (Target: {target})\nNote: {notes}"
                        send_telegram_alert(msg, is_error=False)
                        print(f"📢 Notification Sent: {symbol} Target Hit")
                    
                    elif ltp <= sl:
                        msg = f"🛑 STOP LOSS HIT: {symbol}\nLTP: {ltp} (SL: {sl})\nNote: {notes}"
                        send_telegram_alert(msg, is_error=False)
                        print(f"📢 Notification Sent: {symbol} SL Hit")
            else:
                print("⚠️ No matching symbols found in the API data.")

    except Exception as e:
        error_detail = str(e)
        print(f"🚨 CRITICAL ERROR: {error_detail}")
        send_telegram_alert(error_detail, is_error=True)

if __name__ == "__main__":
    update_ltp_cache()
