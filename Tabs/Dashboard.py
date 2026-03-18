import streamlit as st
import pandas as pd
import plotly.express as px

def render_page(role):
    # Initialize the Neon database connection
    conn = st.connection("neon", type="sql")
    
    # ==========================================
    # 1. LOAD DATA & SAFEGUARD COLUMNS
    # ==========================================
    try:
        port = conn.query("SELECT * FROM portfolio", ttl=0)
        cache = conn.query("SELECT * FROM cache", ttl=3600)
        hist = conn.query("SELECT * FROM history", ttl=0)
        wl = conn.query("SELECT * FROM watchlist", ttl=0)
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return

    # Force lowercase columns to prevent case-sensitivity bugs
    if not port.empty: port.columns = [c.lower() for c in port.columns]
    if not cache.empty: cache.columns = [c.lower() for c in cache.columns]
    if not hist.empty: hist.columns = [c.lower() for c in hist.columns]
    if not wl.empty: wl.columns = [c.lower() for c in wl.columns]

    # Find last updated time gracefully
    last_up = "Never"
    if not cache.empty:
        if "last_updated" in cache.columns: last_up = cache["last_updated"].iloc[0]
        elif "lastupdated" in cache.columns: last_up = cache["lastupdated"].iloc[0]

    st.title("📊 Market Dashboard")
    st.caption(f"Last Market Sync: {last_up} (Nepal Time)")

    if port.empty:
        st.info("Portfolio is empty. Go to the 'Add Transaction' tab to start logging trades.")
        return

    # ==========================================
    # 2. CALCULATE ACTIVE HOLDINGS & WACC
    # ==========================================
    port['qty'] = pd.to_numeric(port['qty'], errors='coerce').fillna(0)
    port['price'] = pd.to_numeric(port['price'], errors='coerce').fillna(0)

    buys = port[port['transaction_type'].str.upper() == 'BUY'].copy()
    sells = port[port['transaction_type'].str.upper() == 'SELL'].copy()

    if buys.empty:
        st.warning("No BUY transactions found. Add some to view your portfolio.")
        return

    # Calculate Total Cost and WACC
    buys['cost'] = buys['qty'] * buys['price']
    holdings = buys.groupby('symbol').agg({'qty': 'sum', 'cost': 'sum'}).reset_index()
    holdings['wacc'] = holdings['cost'] / holdings['qty']

    # Subtract Sells to find Net Active Quantity
    if not sells.empty:
        sold = sells.groupby('symbol')['qty'].sum().reset_index().rename(columns={'qty': 'sold_qty'})
        holdings = pd.merge(holdings, sold, on='symbol', how='left').fillna(0)
        holdings['net_qty'] = holdings['qty'] - holdings['sold_qty']
    else:
        holdings['net_qty'] = holdings['qty']

    # Filter only stocks you currently own
    active = holdings[holdings['net_qty'] > 0].copy()

    # Merge with Live Market Data (Cache)
    if not active.empty and not cache.empty:
        df = pd.merge(active, cache, on="symbol", how="left").fillna(0)
        df['ltp'] = pd.to_numeric(df['ltp'], errors='coerce').fillna(0)
        df['change'] = pd.to_numeric(df['change'], errors='coerce').fillna(0)
        # If LTP is 0 (missing cache), fallback to WACC so net worth doesn't drop to 0
        df['ltp'] = df.apply(lambda x: x['wacc'] if x['ltp'] == 0 else x['ltp'], axis=1)
    else:
        df = active.copy()
        df['ltp'] = df['wacc']
        df['change'] = 0

    # ==========================================
    # 3. METRIC CALCULATIONS
    # ==========================================
    
    # A. Current Holdings (Unrealized)
    curr_inv = (df['net_qty'] * df['wacc']).sum() if not df.empty else 0
    curr_val = (df['net_qty'] * df['ltp']).sum() if not df.empty else 0
    day_change = (df['net_qty'] * df['change']).sum() if not df.empty else 0
    
    curr_pl = curr_val - curr_inv
    curr_ret = (curr_pl / curr_inv * 100) if curr_inv > 0 else 0

    # B. Closed Holdings (Realized History)
    realized_pl = 0
    realized_inv = 0
    realized_recv = 0
    
    if not hist.empty:
        hist['sold_qty'] = pd.to_numeric(hist.get('sold_qty', 0), errors='coerce').fillna(0)
        hist['wacc'] = pd.to_numeric(hist.get('wacc', 0), errors='coerce').fillna(0)
        hist['sell_price'] = pd.to_numeric(hist.get('sell_price', 0), errors='coerce').fillna(0)
        hist['realized_profit'] = pd.to_numeric(hist.get('realized_profit', 0), errors='coerce').fillna(0)

        realized_pl = hist['realized_profit'].sum()
        realized_inv = (hist['sold_qty'] * hist['wacc']).sum()
        realized_recv = (hist['sold_qty'] * hist['sell_price']).sum()

    realized_ret = (realized_pl / realized_inv * 100) if realized_inv > 0 else 0

    # C. Lifetime Stats
    lifetime_invested = curr_inv + realized_inv
    lifetime_received = realized_recv 
    net_exposure = lifetime_received - lifetime_invested 

    # ==========================================
    # 4. DASHBOARD UI RENDER
    # ==========================================
    
    # Row 1: Snapshot
    st.markdown("### 🏦 Net Worth Snapshot")
    m1, m2, m3 = st.columns(3)
    m1.metric("Current Portfolio Value", f"Rs {curr_val:,.2f}")
    m2.metric("Total Active Investment", f"Rs {curr_inv:,.2f}")
    m3.metric("Today's Change", f"Rs {day_change:,.2f}", delta=f"{day_change:,.2f}")
    
    st.markdown("---")
    
    # Row 2: P/L Analysis
    st.markdown("### ⚖️ Profit/Loss Analysis")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Net Realized P/L", f"Rs {realized_pl:,.2f}", delta=f"{realized_ret:.2f}%")
    c2.metric("📈 Unrealized P/L", f"Rs {curr_pl:,.2f}", delta=f"{curr_ret:.2f}%")
    c3.metric("🏆 Lifetime P/L", f"Rs {realized_pl + curr_pl:,.2f}", help="Realized + Unrealized")
    
    # Best Winner Logic
    best_stock = "-"
    if not hist.empty and "realized_profit" in hist.columns and realized_pl > 0:
        best_trade = hist.loc[hist["realized_profit"].idxmax()]
        best_stock = f"{best_trade['symbol']} (+{best_trade['realized_profit']:.0f})"
    c4.metric("🥇 Best Closed Trade", best_stock)

    st.markdown("---")

    # Row 3: Investment Snapshot
    st.markdown("### 💼 Investment Cycle (Lifetime)")
    i1, i2, i3, i4 = st.columns(4)
    
    i1.metric("Total Capital Deployed", f"Rs {lifetime_invested:,.0f}", 
              help="Sum of Cost of Sold Stocks + Cost of Held Stocks.")
    i2.metric("Total Cash Recycled", f"Rs {lifetime_received:,.0f}", 
              help="Total money returned to bank from sales.")
    i3.metric("Net Cash Flow", f"Rs {net_exposure:,.0f}", 
              help="Total Received - Total Invested. Negative means this amount is currently 'at risk'.")
    
    turnover = (realized_inv / curr_inv * 100) if curr_inv > 0 else 0
    i4.metric("Capital Turnover", f"{turnover:.1f}%", help="How many times you have rotated your capital.")

    st.markdown("---")
    
    # Row 4: Visuals & Alerts
    col_chart, col_alert = st.columns([2, 1])
    
    with col_chart:
        st.subheader("Portfolio Allocation (By Asset)")
        if not df.empty:
            df['Current Value'] = df['net_qty'] * df['ltp']
            fig = px.pie(df, values="Current Value", names="symbol", hole=0.4, 
                         color_discrete_sequence=px.colors.qualitative.Set3)
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No active assets to display.")
            
    with col_alert:
        st.subheader("📢 Market Alerts")
        alerts_found = False
        
        # Stop Loss Logic (If you ever add a stop_loss column later)
        if 'stop_loss' in df.columns:
            for _, row in df.iterrows():
                sl = float(row.get('stop_loss', 0))
                if sl > 0 and row['ltp'] < sl:
                    st.error(f"⚠️ **STOP LOSS:** {row['symbol']} @ Rs {row['ltp']} (SL: {sl})")
                    alerts_found = True

        # Watchlist Target Logic
        if not wl.empty and not cache.empty:
            wl_m = pd.merge(wl, cache, on="symbol", how="left")
            if "target" in wl_m.columns and "ltp" in wl_m.columns:
                wl_m['target'] = pd.to_numeric(wl_m['target'], errors='coerce')
                wl_m['ltp'] = pd.to_numeric(wl_m['ltp'], errors='coerce')
                
                hits = wl_m[(wl_m["ltp"] >= wl_m["target"]) & (wl_m["target"] > 0)]
                for _, h in hits.iterrows():
                    st.success(f"🎯 **TARGET HIT:** {h['symbol']} @ Rs {h['ltp']}")
                    alerts_found = True
                    
        if not alerts_found:
            st.info("System Normal. No alerts triggered.")
