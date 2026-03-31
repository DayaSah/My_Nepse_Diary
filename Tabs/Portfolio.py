import streamlit as st
import pandas as pd
import numpy as np
from SubTabs.Advanced_Portfolio import render_advanced_view 

def calculate_fifo_wacc(df):
    """
    NEPSE-Standard FIFO Calculation.
    Handles partial sells correctly and accounts for fees via net_amount.
    """
    active_holdings = []
    df['date'] = pd.to_datetime(df['date'])
    
    for symbol in df['symbol'].unique():
        symbol_df = df[df['symbol'] == symbol].sort_values('date')
        inventory = [] # List of buy lots
        
        for _, row in symbol_df.iterrows():
            qty = abs(int(row['qty']))
            net_amt = abs(float(row['net_amount']))
            
            if row['transaction_type'].upper() == 'BUY':
                inventory.append({'qty': qty, 'total_cost': net_amt})
            
            elif row['transaction_type'].upper() == 'SELL':
                rem = qty
                while rem > 0 and inventory:
                    if inventory[0]['qty'] <= rem:
                        rem -= inventory[0]['qty']
                        inventory.pop(0) 
                    else:
                        unit_cost = inventory[0]['total_cost'] / inventory[0]['qty']
                        inventory[0]['qty'] -= rem
                        inventory[0]['total_cost'] -= (unit_cost * rem)
                        # FIX: Prevent floating point trailing decimals
                        inventory[0]['total_cost'] = round(inventory[0]['total_cost'], 4)
                        rem = 0
        
        if inventory:
            t_qty = sum(i['qty'] for i in inventory)
            t_cost = sum(i['total_cost'] for i in inventory)
            active_holdings.append({
                'symbol': symbol, 
                'net_qty': t_qty, 
                'wacc': t_cost/t_qty, 
                'total_cost': t_cost
            })
            
    return pd.DataFrame(active_holdings)

# --- NEW: EXACT NEPSE SIMULATOR ---
def calculate_exact_metrics(row):
    qty = row['net_qty']
    total_cost = row['total_cost']
    ltp = row['ltp']
    
    # 1. EXACT BREAKEVEN REVERSAL
    if total_cost <= 50000: comm_rate = 0.0036 
    elif total_cost <= 500000: comm_rate = 0.0033 
    elif total_cost <= 2000000: comm_rate = 0.0031 
    elif total_cost <= 10000000: comm_rate = 0.0027 
    else: comm_rate = 0.0024
    
    if (total_cost * comm_rate) < 10.0:
        target_sell = (total_cost + 25.0 + 10.0) / (1.0 - 0.00015)
    else:
        target_sell = (total_cost + 25.0) / (1.0 - comm_rate - 0.00015)
        
    breakeven = target_sell / qty if qty > 0 else 0.0
    
    # 2. EXACT NET P/L AT CURRENT LTP (Includes all fees and CGT)
    base_sell = qty * ltp
    if base_sell <= 50000: s_comm = 0.0036 
    elif base_sell <= 500000: s_comm = 0.0033 
    elif base_sell <= 2000000: s_comm = 0.0031 
    elif base_sell <= 10000000: s_comm = 0.0027 
    else: s_comm = 0.0024
    
    broker_fee = max(10.0, base_sell * s_comm)
    sebon_fee = base_sell * 0.00015
    dp_fee = 25.0
    total_sell_fees = broker_fee + sebon_fee + dp_fee
    
    net_sell_before_tax = base_sell - total_sell_fees
    profit_for_tax = net_sell_before_tax - total_cost
    
    # Apply conservative 7.5% CGT (Short term assumption for safety)
    cgt = max(0.0, profit_for_tax * 0.075) if profit_for_tax > 0 else 0.0
    
    net_receivable = net_sell_before_tax - cgt
    true_pl_amt = net_receivable - total_cost
    true_pl_pct = (true_pl_amt / total_cost) * 100 if total_cost > 0 else 0.0
    
    return pd.Series([breakeven, net_receivable, true_pl_amt, true_pl_pct])
# ----------------------------------

def style_pl_selective(val):
    """
    Discrete Intensity Logic:
    0-2% Light | 2-5% Clear | 5-15% Dark | 15%+ Very Dark
    """
    try:
        if val > 0:
            if val <= 2: opacity = 0.3
            elif val <= 5: opacity = 0.5
            elif val <= 15: opacity = 0.7
            else: opacity = 0.9
            return f'background-color: rgba(0, 128, 0, {opacity}); color: white; font-weight: bold;'
        elif val < 0:
            v = abs(val)
            if v <= 2: opacity = 0.3
            elif v <= 5: opacity = 0.5
            elif v <= 15: opacity = 0.7
            else: opacity = 0.9
            return f'background-color: rgba(200, 0, 0, {opacity}); color: white; font-weight: bold;'
    except:
        pass
    return ''

def render_page(role):
    # Navigation logic
    if st.session_state.get('portfolio_view') == 'advanced':
        if st.button("⬅️ Back to Basic Portfolio"):
            st.session_state.portfolio_view = 'basic'
            st.rerun()
        render_advanced_view()
        return

    st.title("💼 My Portfolio")
    conn = st.connection("neon", type="sql")
    
    try:
        port_df = conn.query("SELECT * FROM portfolio", ttl=0)
        cache_df = conn.query("SELECT * FROM cache", ttl=0)
        port_df.columns = [c.lower() for c in port_df.columns]
    except:
        st.error("Database Connection Error"); return

    if port_df.empty:
        st.info("Portfolio ledger is empty."); return

    # 1. FIFO Calculation
    active = calculate_fifo_wacc(port_df)
    
    if active.empty:
        st.info("No active holdings found."); return

    # 2. FIX: Safely Integrate Live Prices (LTP)
    if not cache_df.empty and 'symbol' in cache_df.columns and 'ltp' in cache_df.columns:
        cache_df.columns = [c.lower() for c in cache_df.columns]
        active = pd.merge(active, cache_df[['symbol', 'ltp']], on='symbol', how='left')
        active['ltp'] = pd.to_numeric(active['ltp'], errors='coerce')
        active['ltp'] = active['ltp'].fillna(active['wacc'])
    else:
        active['ltp'] = active['wacc']

    # 3. FIX: Exact Financial Metrics
    active[['breakeven', 'current_val', 'pl_amt', 'pl_pct']] = active.apply(calculate_exact_metrics, axis=1)
    active['weight'] = (active['current_val'] / active['current_val'].sum()) * 100

    # 4. Summary Dashboard
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Invested", f"Rs {active['total_cost'].sum():,.0f}")
    c2.metric("Net Receivable (at LTP)", f"Rs {active['current_val'].sum():,.0f}", help="Total cash you would receive in bank after ALL fees and taxes.")
    
    total_pl = active['pl_amt'].sum()
    total_pct = (total_pl / active['total_cost'].sum() * 100) if active['total_cost'].sum() > 0 else 0
    c3.metric("True Unrealized P/L", f"Rs {total_pl:,.0f}", f"{total_pct:.2f}%")

    st.divider()
    
    if st.button("🚀 Switch to Advanced Portfolio (Deep Analytics)", use_container_width=True, type="primary"):
        st.session_state.portfolio_view = 'advanced'
        st.rerun()

    # 5. Styled Data Table
    st.subheader("📋 Active Holdings")
    
    display_df = active[['symbol', 'net_qty', 'wacc', 'breakeven', 'ltp', 'pl_amt', 'pl_pct', 'weight']]
    
    styled_df = display_df.style.map(style_pl_selective, subset=['pl_pct']).format({
        'wacc': '{:.2f}',
        'breakeven': '{:.2f}',
        'ltp': '{:.2f}',
        'pl_amt': 'Rs {:,.2f}',
        'pl_pct': '{:.2f}%',
        'weight': '{:.1f}%'
    })

    st.dataframe(
        styled_df, 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "weight": st.column_config.ProgressColumn("Weightage", format="%.1f%%", min_value=0, max_value=100),
            "symbol": "Ticker",
            "net_qty": "Units"
        }
    )
