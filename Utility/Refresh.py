import os
import requests
from sqlalchemy import create_engine, text
import datetime
import pytz

# --- CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def update_ltp_cache():
    nepal_tz = pytz.timezone('Asia/Kathmandu')
    now_time = datetime.datetime.now(nepal_tz).strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"🚀 Starting Deep Sync at {now_time}")

    target_url = "https://chukul.com/api/data/v2/live-market/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://chukul.com/"
    }

    try:
        response = requests.get(target_url, headers=headers, timeout=25)
        if response.status_code != 200:
            print(f"❌ Failed to fetch data. Status: {response.status_code}")
            return

        data = response.json()
        
        # Prepare the list for database update
        updates = []
        for item in data:
            symbol = str(item.get('symbol', '')).strip().upper()
            ltp = item.get('ltp')
            
            # Extract the new fields Chukul provides
            # We map: percentage_change -> change_percent
            # We map: volume -> volume
            # We map: high -> day_high
            # We map: low -> day_low
            
            if symbol and ltp is not None:
                updates.append({
                    "symbol": symbol,
                    "ltp": float(ltp),
                    "change": float(item.get('percentage_change', 0.0)),
                    "vol": int(item.get('volume', 0)),
                    "h": float(item.get('high', ltp)),
                    "l": float(item.get('low', ltp))
                })

        # --- DATABASE UPDATE ---
        if not DATABASE_URL:
            print("❌ DATABASE_URL missing.")
            return

        engine = create_engine(DATABASE_URL)
        
        with engine.begin() as conn:
            # We only update rows that you've already added manually.
            # If the stock isn't in your 'cache' table, this script ignores it.
            update_query = text("""
                UPDATE public.cache 
                SET ltp = :ltp, 
                    change_percent = :change,
                    volume = :vol,
                    day_high = :h,
                    day_low = :l,
                    last_updated = NOW()
                WHERE symbol = :symbol;
            """)

            counter = 0
            for row in updates:
                result = conn.execute(update_query, row)
                if result.rowcount > 0:
                    counter += 1

        print(f"✅ Sync Complete. Updated {counter} tracking stocks in DB.")

    except Exception as e:
        print(f"🚨 CRITICAL ERROR: {str(e)}")

if __name__ == "__main__":
    update_ltp_cache()
