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
    # Ensure date is datetime for sorting
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
                        inventory.pop(0) # Oldest lot fully sold
                    else:
                        # Deduct from oldest lot partially
                        unit_cost = inventory[0]['total_cost'] / inventory[0]['qty']
                        inventory[0]['qty'] -= rem
                        inventory[0]['total_cost'] -= (unit_cost * rem)
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

    # 2. Integrate Live Prices (LTP)
    if not cache_df.empty:
        cache_df.columns = [c.lower() for c in cache_df.columns]
        active = pd.merge(active, cache_df[['symbol', 'ltp']], on='symbol', how='left')
        active['ltp'] = pd.to_numeric(active['ltp']).fillna(active['wacc'])
    else:
        active['ltp'] = active['wacc']

    # 3. Financial Metrics
    active['current_val'] = active['net_qty'] * active['ltp']
    active['pl_amt'] = active['current_val'] - active['total_cost']
    active['pl_pct'] = (active['pl_amt'] / active['total_cost']) * 100
    active['weight'] = (active['current_val'] / active['current_val'].sum()) * 100
    active['breakeven'] = (active['wacc'] * 1.005) + (25 / active['net_qty'])

    # 4. Summary Dashboard
    c1, c2, c3 = st.columns(3)
    c1.metric("Invested", f"Rs {active['total_cost'].sum():,.0f}")
    c2.metric("Market Value", f"Rs {active['current_val'].sum():,.0f}")
    
    total_pl = active['pl_amt'].sum()
    total_pct = (total_pl / active['total_cost'].sum() * 100) if active['total_cost'].sum() > 0 else 0
    c3.metric("Unrealized P/L", f"Rs {total_pl:,.0f}", f"{total_pct:.2f}%")

    st.divider()
    
    if st.button("🚀 Switch to Advanced Portfolio (Deep Analytics)", use_container_width=True, type="primary"):
        st.session_state.portfolio_view = 'advanced'
        st.rerun()

    # 5. Styled Data Table
    st.subheader("📋 Active Holdings")
    
    # Selecting columns for clean display
    display_df = active[['symbol', 'net_qty', 'wacc', 'breakeven', 'ltp', 'pl_amt', 'pl_pct', 'weight']]
    
    # Format and Style
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
