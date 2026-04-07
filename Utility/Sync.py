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
    try:
        import streamlit as st
        db_url = st.secrets["connections"]["neon"]["url"]
    except Exception:
        db_url = os.environ.get("DATABASE_URL")
        
    if not db_url:
        raise ValueError("Database URL not found in secrets or environment variables.")
        
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    return create_engine(db_url)

# ==========================================
# 2. TELEGRAM NOTIFIER
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
        print(f"Failed to send Telegram message: {e}")

# ==========================================
# 3. CORE SYNC ENGINE
# ==========================================
def run_sync(headless=False):
    engine = get_engine()
    
    symbols_list = []
    with engine.connect() as conn:
        for table in ['portfolio', 'history', 'watchlist']:
            try:
                df = pd.read_sql(text(f"SELECT DISTINCT symbol FROM {table}"), conn)
                symbols_list.extend(df['symbol'].tolist())
            except Exception:
                pass 
        
    symbols = set([s.strip().upper() for s in symbols_list if s and str(s).strip() not in ('-', 'N/A')])

    if not symbols:
        if not headless:
            import streamlit as st
            st.warning("No symbols found.")
        return

    updated_data = []
    np_tz = timezone(timedelta(hours=5, minutes=45))
    current_np_time = datetime.now(np_tz) # Keep as object for proper TIMESTAMP storage

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Fetch all at once to avoid being blocked (Faster & Safer)
    try:
        resp = requests.get("https://chukul.com/api/data/v2/live-market/", headers=headers, timeout=25)
        if resp.status_code == 200:
            all_data = {item['symbol']: item for item in resp.json()}
            for sym in symbols:
                item = all_data.get(sym)
                if item:
                    updated_data.append({
                        "symbol": sym,
                        "ltp": float(item.get("ltp", 0)),
                        "change": float(item.get("percentage_change", 0)),
                        "vol": int(item.get("volume", 0)),
                        "h": float(item.get("high", 0)),
                        "l": float(item.get("low", 0)),
                        "ts": current_np_time
                    })
    except Exception as e:
        print(f"Market Fetch Failed: {e}")

    if updated_data:
        with engine.begin() as conn:
            # Matches your DB: change is VARCHAR, change_percent is NUMERIC
            # Using casting (::numeric) to prevent the "varying character" error
            sql = text("""
                INSERT INTO public.cache (symbol, ltp, change_percent, volume, day_high, day_low, last_updated) 
                VALUES (:symbol, :ltp, :change, :vol, :h, :l, :ts)
                ON CONFLICT (symbol) DO UPDATE 
                SET ltp = EXCLUDED.ltp, 
                    change_percent = EXCLUDED.change_percent::numeric,
                    volume = EXCLUDED.volume,
                    day_high = EXCLUDED.day_high,
                    day_low = EXCLUDED.day_low,
                    last_updated = EXCLUDED.last_updated
            """)
            conn.execute(sql, updated_data)
    
    take_wealth_snapshot(engine)

    msg = f"✅ *NEPSE Terminal Sync Complete*\n\n📊 Updated {len(updated_data)} symbols."
    if headless:
        send_telegram_message(msg)
    else:
        import streamlit as st
        st.success(f"Synchronized {len(updated_data)} stocks!")

# ==========================================
# 4. WEALTH SNAPSHOT CALCULATOR (FIXED)
# ==========================================
def take_wealth_snapshot(engine):
    try:
        with engine.connect() as conn:
            port_df = pd.read_sql(text("SELECT * FROM public.portfolio"), conn)
            cache_df = pd.read_sql(text("SELECT * FROM public.cache"), conn)
            tms_df = pd.read_sql(text("SELECT amount FROM public.tms_trx"), conn)
            
        if port_df.empty: return

        tms_cash = float(tms_df['amount'].sum()) if not tms_df.empty else 0.0

        port_df['qty'] = pd.to_numeric(port_df['qty'])
        port_df['price'] = pd.to_numeric(port_df['price'])
        
        buys = port_df[port_df['transaction_type'].str.upper() == 'BUY'].copy()
        sells = port_df[port_df['transaction_type'].str.upper() == 'SELL'].copy()
        
        buys['cost'] = buys['qty'] * buys['price']
        buy_grouped = buys.groupby('symbol').agg({'qty': 'sum', 'cost': 'sum'}).reset_index()
        sell_grouped = sells.groupby('symbol')['qty'].sum().reset_index().rename(columns={'qty': 'sold_qty'})
        
        holdings = pd.merge(buy_grouped, sell_grouped, on='symbol', how='left').fillna(0)
        holdings['net_qty'] = holdings['qty'] - holdings['sold_qty']
        active = holdings[holdings['net_qty'] > 0].copy()
        
        active = pd.merge(active, cache_df[['symbol', 'ltp']], on='symbol', how='left').fillna(0)
        
        # WACC Calculation
        active['wacc'] = active['cost'] / active['qty']
        
        # CRITICAL FIX: Convert np.float64 to standard Python float to avoid "schema np" error
        total_inv = float((active['net_qty'] * active['wacc']).sum())
        current_val = float((active['net_qty'] * active['ltp']).sum() + tms_cash)

        np_tz = timezone(timedelta(hours=5, minutes=45))
        today_date = datetime.now(np_tz).date()
        
        with engine.begin() as conn:
            sql = text("""
                INSERT INTO public.wealth (snapshot_date, total_investment, current_value)
                VALUES (:date, :inv, :val)
                ON CONFLICT (snapshot_date) DO UPDATE 
                SET total_investment = EXCLUDED.total_investment, 
                    current_value = EXCLUDED.current_value
            """)
            conn.execute(sql, {"date": today_date, "inv": total_inv, "val": current_val})
            
    except Exception as e:
        print(f"Wealth Snapshot Failed: {e}")
