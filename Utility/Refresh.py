import os
import requests
import pandas as pd
from sqlalchemy import create_engine, text
from urllib.parse import quote
import datetime
import pytz

# --- 1. CONFIGURATION ---
# GitHub Actions will provide this from your Repo Secrets
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def update_ltp_cache():
    nepal_tz = pytz.timezone('Asia/Kathmandu')
    now_time = datetime.datetime.now(nepal_tz).strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"🚀 Starting NEPSE Sync at {now_time}")

    # --- 2. FETCH DATA VIA PROXY ---
    target_url = "https://chukul.com/api/data/v2/live-market/"
    proxy_url = f"https://api.allorigins.win/raw?url={quote(target_url)}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        print(f"📡 Fetching from Chukul via Proxy...")
        response = requests.get(proxy_url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch data. Status: {response.status_code}")
            return

        data = response.json()
        if not isinstance(data, list):
            print("❌ Unexpected data format received.")
            return

        # Prepare data for Database
        # We only need Symbol and LTP
        updates = []
        for item in data:
            symbol = str(item.get('symbol', '')).strip().upper()
            ltp = item.get('ltp')
            if symbol and ltp is not None:
                updates.append((symbol, float(ltp)))

        print(f"✅ Scraped {len(updates)} symbols successfully.")

        # --- 3. DATABASE UPDATE (UPSERT) ---
        if not DATABASE_URL:
            print("❌ DATABASE_URL not found. Skipping DB update.")
            return

        engine = create_engine(DATABASE_URL)
        
        with engine.begin() as conn:
            # Create table if it doesn't exist
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS public.cache (
                    symbol VARCHAR(20) PRIMARY KEY,
                    ltp NUMERIC,
                    last_updated TIMESTAMP
                );
            """))

            # Use PostgreSQL UPSERT logic (Insert or Update on Conflict)
            upsert_query = text("""
                INSERT INTO public.cache (symbol, ltp, last_updated)
                VALUES (:symbol, :ltp, NOW())
                ON CONFLICT (symbol) 
                DO UPDATE SET 
                    ltp = EXCLUDED.ltp,
                    last_updated = NOW();
            """)

            # Execute in batch for speed
            for symbol, ltp in updates:
                conn.execute(upsert_query, {"symbol": symbol, "ltp": ltp})

        print(f"🎉 Database Cache Updated successfully at {now_time}!")

    except Exception as e:
        print(f"🚨 CRITICAL ERROR: {str(e)}")

if __name__ == "__main__":
    update_ltp_cache()
