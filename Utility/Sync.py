import os
import time
import requests
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta, timezone

# ==========================================
# 1. DATABASE CONNECTION MANAGER
# ==========================================
def get_engine():
    db_url = os.environ.get("DATABASE_URL")
    # If using Streamlit locally
    if not db_url:
        try:
            import streamlit as st
            db_url = st.secrets["connections"]["neon"]["url"]
        except:
            pass
    
    if not db_url:
        raise ValueError("❌ DATABASE_URL missing from Environment/Secrets.")
    
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    return create_engine(db_url)

# ==========================================
# 2. TELEGRAM NOTIFIER (Improved)
# ==========================================
def send_telegram_message(message):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to send Telegram: {e}")

# ==========================================
# 3. CORE SYNC ENGINE
# ==========================================
def run_sync(headless=False):
    engine = get_engine()
    np_tz = timezone(timedelta(hours=5, minutes=45))
    current_np_time = datetime.now(np_tz).strftime("%Y-%m-%d %H:%M:%S")

    # A. Fetch Symbols
    symbols_list = []
    with engine.connect() as conn:
        for table in ['portfolio', 'history', 'watchlist']:
            try:
                res = conn.execute(text(f"SELECT DISTINCT symbol FROM {table}"))
                symbols_list.extend([row[0] for row in res if row[0]])
            except Exception:
                pass 

    symbols = set([s.strip().upper() for s in symbols_list if s and s not in ('-', 'N/A')])

    if not symbols:
        print("⚠️ No symbols found to sync.")
        return

    # B. Fetch Market Data (Optimized)
    # Instead of looping through symbols, we hit the Live Market once 
    # and filter for your symbols. This is 10x faster and safer.
    updated_data = []
    headers = {"User-Agent": "Mozilla/5.0..."}
    
    try:
        market_url = "https://chukul.com/api/data/v2/live-market/"
        resp = requests.get(market_url, headers=headers, timeout=20)
        
        if resp.status_code == 200:
            all_market_data = {item['symbol']: item for item in resp.json()}
            
            for sym in symbols:
                item = all_market_data.get(sym)
                if item:
                    updated_data.append({
                        "symbol": sym,
                        "ltp": float(item.get("ltp", 0)),
                        "change": float(item.get("percentage_change", 0)),
                        "last_updated": current_np_time
                    })
    except Exception as e:
        send_telegram_message(f"❌ Market Fetch Error: {e}")
        return

    # C. Update Cache
    if updated_data:
        with engine.begin() as conn:
            sql = text("""
                INSERT INTO cache (symbol, ltp, change_percent, last_updated) 
                VALUES (:symbol, :ltp, :change, :last_updated)
                ON CONFLICT (symbol) DO UPDATE 
                SET ltp = EXCLUDED.ltp, change_percent = EXCLUDED.change, last_updated = EXCLUDED.last_updated
            """)
            conn.execute(sql, updated_data)
    
    # D. Take Wealth Snapshot
    take_wealth_snapshot(engine)

    if headless:
        send_telegram_message(f"✅ *Daily Sync Complete*\nUpdated {len(updated_data)} symbols.")

# ... (Wealth Snapshot Function remains largely the same)
