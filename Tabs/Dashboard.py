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
    # 2. CALCULATE ROLLING LEDGER (WACC & REALIZED P/L)
    # ==========================================
    if port.empty:
        st.info("Portfolio is empty. Go to the 'Add Transaction' tab to start logging trades.")
        return

    # Sort chronologically: Sells before Buys on the same day
    port['date'] = pd.to_datetime(port['date'])
    port['type_sort'] = port['transaction_type'].apply(lambda x: 0 if str(x).upper() == 'SELL' else 1)
    port = port.sort_values(by=['date', 'type_sort']).reset_index(drop=True)

    portfolio_state = {}
    realized_pl = 0.0
    realized_inv = 0.0
    realized_recv = 0.0
    best_trade_val = -float('inf')
    best_trade_sym = "-"

    for _, row in port.iterrows():
        sym = str(row['symbol']).upper()
        qty = float(row['qty'])
        trx = str(row['transaction_type']).upper()
        
        # Safely get net_amount (fallback to base price if old data lacks it)
        if 'net_amount' in row and pd.notnull(row['net_amount']):
            net_amt = float(row['net_amount'])
        else:
            net_amt = float(row['qty'] * row['price'])
            
        if sym not in portfolio_state:
            portfolio_state[sym] = {'qty': 0, 'invested': 0.0}
            
        curr_qty = portfolio_state[sym]['qty']
        curr_inv = portfolio_state[sym]['invested']
        wacc = curr_inv / curr_qty if curr_qty > 0 else 0.0
        
        if trx == 'BUY':
            if curr_qty <= 0:
                portfolio_state[sym]['invested'] = net_amt
                portfolio_state[sym]['qty'] = qty
            else:
                portfolio_state[sym]['invested'] += net_amt
                portfolio_state[sym]['qty'] += qty
                
        elif trx == 'SELL':
            sell_wacc = wacc
            cost_of_goods_sold = qty * sell_wacc
            profit = net_amt - cost_of_goods_sold  # Net Amount on a Sell is what you RECEIVE after tax/fees
            
            realized_pl += profit
            realized_inv += cost_of_goods_sold
            realized_recv += net_amt
            
            # Track Best Trade
            if profit > best_trade_val:
                best_trade_val = profit
                best_trade_sym = sym
                
            portfolio_state[sym]['qty'] -= qty
            portfolio_state[sym]['invested'] -= cost_of_goods_sold
            
            # Zero-Reset Logic
            if portfolio_state[sym]['qty'] <= 0:
                portfolio_state[sym]['qty'] = 0
                portfolio_state[sym]['invested'] = 0.0

    # Extract Active Holdings into DataFrame
    active_records = []
    for sym, data in portfolio_state.items():
        if data['qty'] > 0:
            active_records.append({
                'symbol': sym,
                'net_qty': data['qty'],
                'wacc': data['invested'] / data['qty'],
                'total_cost': data['invested']
            })
            
    active = pd.DataFrame(active_records)

    # Merge with Live Market Data (Cache)
    if not active.empty and not cache.empty:
        df = pd.merge(active, cache, on="symbol", how="left").fillna(0)
        df['ltp'] = pd.to_numeric(df['ltp'], errors='coerce').fillna(0)
        df['change'] = pd.to_numeric(df['change'], errors='coerce').fillna(0)
        df['ltp'] = df.apply(lambda x: x['wacc'] if x['ltp'] == 0 else x['ltp'], axis=1)
    else:
        df = active.copy()
        if not df.empty:
            df['ltp'] = df['wacc']
            df['change'] = 0

    # ==========================================
    # 3. METRIC CALCULATIONS
    # ==========================================
    curr_inv = df['total_cost'].sum() if not df.empty else 0
    curr_val = (df['net_qty'] * df['ltp']).sum() if not df.empty else 0
    day_change = (df['net_qty'] * df['change']).sum() if not df.empty else 0
    
    curr_pl = curr_val - curr_inv
    curr_ret = (curr_pl / curr_inv * 100) if curr_inv > 0 else 0

    realized_ret = (realized_pl / realized_inv * 100) if realized_inv > 0 else 0

    lifetime_invested = curr_inv + realized_inv
    lifetime_received = realized_recv 
    net_exposure = lifetime_received - lifetime_invested 
    
    best_stock = f"{best_trade_sym} (+Rs {best_trade_val:.0f})" if best_trade_sym != "-" else "-" 

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
