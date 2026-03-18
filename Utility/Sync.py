import os
import requests
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date

# ==========================================
# 1. DATABASE CONNECTION MANAGER
# ==========================================
def get_engine():
    """Handles connection for both Streamlit and GitHub Actions."""
    try:
        # Try fetching from Streamlit secrets (Local UI mode)
        import streamlit as st
        db_url = st.secrets["connections"]["neon"]["url"]
    except Exception:
        # Fallback to Environment Variables (GitHub Actions headless mode)
        db_url = os.environ.get("DATABASE_URL")
        
    if not db_url:
        raise ValueError("Database URL not found in secrets or environment variables.")
        
    return create_engine(db_url)

# ==========================================
# 2. TELEGRAM NOTIFIER
# ==========================================
def send_telegram_message(message):
    """Sends a message via Telegram Bot using GitHub Secrets."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("Telegram credentials missing. Skipping notification.")
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
    
    # A. Fetch all symbols from Portfolio and Watchlist
    with engine.connect() as conn:
        port_df = pd.read_sql("SELECT DISTINCT symbol FROM portfolio", conn)
        wl_df = pd.read_sql("SELECT DISTINCT symbol FROM watchlist", conn)
        
    symbols = set(port_df['symbol'].tolist() + wl_df['symbol'].tolist())
    symbols = [s.strip().upper() for s in symbols if s and s.strip() != '-']

    if not symbols:
        if not headless:
            import streamlit as st
            st.warning("No symbols found in portfolio or watchlist to sync.")
        return

    # B. Fetch Live Market Data from Chukul API
    updated_data = []
    for sym in symbols:
        try:
            url = f"https://chukul.com/api/data/v2/market-summary/bysymbol/?symbol={sym}"
            resp = requests.get(url, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    item = data[0]
                    # ONLY extracting the essential values needed
                    updated_data.append({
                        "symbol": sym,
                        "ltp": float(item.get("close", 0)),
                        "change": float(item.get("point_change", 0)),
                        "last_updated": item.get("date", str(date.today()))
                    })
        except Exception as e:
            print(f"Failed to fetch {sym}: {e}")

    # C. Push Updates to Cache Table
    if updated_data:
        with engine.begin() as conn:
            # Ensure table exists
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS cache (
                    symbol VARCHAR(20) PRIMARY KEY,
                    ltp NUMERIC(10, 2),
                    change NUMERIC(10, 2),
                    last_updated VARCHAR(50)
                )
            """))
            
            for item in updated_data:
                sql = text("""
                    INSERT INTO cache (symbol, ltp, change, last_updated) 
                    VALUES (:symbol, :ltp, :change, :last_updated)
                    ON CONFLICT (symbol) DO UPDATE 
                    SET ltp = EXCLUDED.ltp, change = EXCLUDED.change, last_updated = EXCLUDED.last_updated
                """)
                conn.execute(sql, item)
    
    # D. Take Daily Wealth Snapshot
    take_wealth_snapshot(engine)

    # E. Handle Notifications based on environment
    msg = f"✅ *NEPSE Terminal Sync Complete*\n\n📊 Successfully updated market data for {len(updated_data)} symbols and took the daily Wealth Snapshot."
    if headless:
        send_telegram_message(msg)
        print("Sync complete. Message sent.")
    else:
        import streamlit as st
        st.success("Database successfully synchronized with Chukul API!")

# ==========================================
# 4. WEALTH SNAPSHOT CALCULATOR
# ==========================================
def take_wealth_snapshot(engine):
    """Calculates total net worth and logs it for the charts."""
    try:
        with engine.connect() as conn:
            port_df = pd.read_sql("SELECT * FROM portfolio", conn)
            cache_df = pd.read_sql("SELECT * FROM cache", conn)
            
        if port_df.empty: return

        # Format types
        port_df['qty'] = pd.to_numeric(port_df['qty'])
        port_df['price'] = pd.to_numeric(port_df['price'])
        
        # Calculate Active Holdings WACC
        buys = port_df[port_df['transaction_type'].str.upper() == 'BUY']
        sells = port_df[port_df['transaction_type'].str.upper() == 'SELL']
        
        buy_grouped = buys.groupby('symbol').apply(lambda x: pd.Series({'qty': x['qty'].sum(), 'cost': (x['qty']*x['price']).sum()})).reset_index()
        buy_grouped['wacc'] = buy_grouped['cost'] / buy_grouped['qty']
        
        sell_grouped = sells.groupby('symbol')['qty'].sum().reset_index().rename(columns={'qty': 'sold_qty'})
        
        holdings = pd.merge(buy_grouped, sell_grouped, on='symbol', how='left').fillna(0)
        holdings['net_qty'] = holdings['qty'] - holdings['sold_qty']
        active = holdings[holdings['net_qty'] > 0].copy()
        
        # Match with LTP to find current value
        if not cache_df.empty:
            active = pd.merge(active, cache_df[['symbol', 'ltp']], on='symbol', how='left').fillna(0)
        else:
            active['ltp'] = active['wacc']

        total_invested = (active['net_qty'] * active['wacc']).sum()
        current_value = (active['net_qty'] * active['ltp']).sum()

        # Save to DB
        today = str(date.today())
        with engine.begin() as conn:
            sql = text("""
                INSERT INTO wealth (snapshot_date, total_investment, current_value)
                VALUES (:date, :inv, :val)
                ON CONFLICT (snapshot_date) DO UPDATE 
                SET total_investment = EXCLUDED.total_investment, current_value = EXCLUDED.current_value
            """)
            conn.execute(sql, {"date": today, "inv": total_invested, "val": current_value})
    except Exception as e:
        print(f"Wealth Snapshot Failed: {e}")
