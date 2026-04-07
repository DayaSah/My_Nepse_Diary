import os
import requests
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta, timezone

# ==========================================
# 1. DATABASE CONNECTION MANAGER
# ==========================================
def get_engine():
    db_url = os.environ.get("DATABASE_URL")
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
        print(f"Failed to send Telegram: {e}")

# ==========================================
# 3. CORE SYNC ENGINE
# ==========================================
def run_sync(headless=False):
    engine = get_engine()
    np_tz = timezone(timedelta(hours=5, minutes=45))
    current_np_time = datetime.now(np_tz) # Keep as object for DB timestamp compatibility

    # A. Fetch Symbols from all tracking tables
    symbols_list = []
    with engine.connect() as conn:
        for table in ['portfolio', 'history', 'watchlist']:
            try:
                res = conn.execute(text(f"SELECT DISTINCT symbol FROM public.{table}"))
                symbols_list.extend([row[0] for row in res if row[0]])
            except Exception:
                pass 

    symbols = set([s.strip().upper() for s in symbols_list if s and s not in ('-', 'N/A')])

    if not symbols:
        print("⚠️ No symbols found to sync.")
        return

    # B. Fetch Market Data (High Speed - Single Request)
    updated_data = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    
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
                        "change": float(item.get("percentage_change", 0.0)),
                        "vol": int(item.get("volume", 0)),
                        "h": float(item.get("high", 0)),
                        "l": float(item.get("low", 0)),
                        "ts": current_np_time
                    })
    except Exception as e:
        send_telegram_message(f"❌ Market Fetch Error: {e}")
        return

    # C. Update Cache (FIXED: Type Mismatch & Column Mapping)
    if updated_data:
        with engine.begin() as conn:
            # Explicitly mapping Python :change to DB change_percent and adding numeric cast
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
    
    # D. Take Wealth Snapshot
    take_wealth_snapshot(engine)

    if headless:
        send_telegram_message(f"✅ *Daily Sync Complete*\nUpdated {len(updated_data)} symbols and Wealth Snapshot.")

# ==========================================
# 4. WEALTH SNAPSHOT CALCULATOR
# ==========================================
def take_wealth_snapshot(engine):
    try:
        with engine.connect() as conn:
            port_df = pd.read_sql("SELECT * FROM public.portfolio", conn)
            cache_df = pd.read_sql("SELECT * FROM public.cache", conn)
            tms_df = pd.read_sql("SELECT amount FROM public.tms_trx", conn)
            
        if port_df.empty: return

        tms_cash = tms_df['amount'].sum() if not tms_df.empty else 0.0
        
        # Calculate WACC Holdings
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
        
        # Merge with Cache for current value
        active = pd.merge(active, cache_df[['symbol', 'ltp']], on='symbol', how='left').fillna(0)
        
        total_invested = (active['net_qty'] * (active['cost']/active['qty'])).sum()
        current_wealth = (active['net_qty'] * active['ltp']).sum() + tms_cash

        np_tz = timezone(timedelta(hours=5, minutes=45))
        today_date = datetime.now(np_tz).date()
        
        with engine.begin() as conn:
            sql = text("""
                INSERT INTO public.wealth (snapshot_date, total_investment, current_value)
                VALUES (:date, :inv, :val)
                ON CONFLICT (snapshot_date) DO UPDATE 
                SET total_investment = EXCLUDED.total_investment, current_value = EXCLUDED.current_value
            """)
            conn.execute(sql, {"date": today_date, "inv": total_invested, "val": current_wealth})
            
    except Exception as e:
        print(f"Wealth Snapshot Failed: {e}")
