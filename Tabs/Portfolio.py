import streamlit as st
import pandas as pd
import numpy as np
from SubTabs.Advanced_Portfolio import render_advanced_view 

def calculate_fifo_wacc(df):
    active_holdings = []
    for symbol in df['symbol'].unique():
        symbol_df = df[df['symbol'] == symbol].sort_values('date')
        inventory = [] 
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
                        rem = 0
        if inventory:
            t_qty = sum(i['qty'] for i in inventory)
            t_cost = sum(i['total_cost'] for i in inventory)
            active_holdings.append({'symbol': symbol, 'net_qty': t_qty, 'wacc': t_cost/t_qty, 'total_cost': t_cost})
    return pd.DataFrame(active_holdings)

def style_pl(val):
    # Intensity based on % (Green for Profit, Red for Loss)
    if val > 0:
        opacity = min(val / 10, 1.0) # Full color at 10% profit
        return f'background-color: rgba(0, 128, 0, {opacity}); color: white;'
    elif val < 0:
        opacity = min(abs(val) / 10, 1.0) # Full color at 10% loss
        return f'background-color: rgba(200, 0, 0, {opacity}); color: white;'
    return ''

def render_page(role):
    if st.session_state.get('portfolio_view') == 'advanced':
        if st.button("⬅️ Back"): st.session_state.portfolio_view = 'basic'; st.rerun()
        render_advanced_view(); return

    st.title("💼 My Portfolio")
    conn = st.connection("neon", type="sql")
    
    port_df = conn.query("SELECT * FROM portfolio", ttl=0)
    cache_df = conn.query("SELECT * FROM cache", ttl=0)
    port_df.columns = [c.lower() for c in port_df.columns]

    if port_df.empty: st.info("Empty"); return

    active = calculate_fifo_wacc(port_df)
    if not cache_df.empty:
        cache_df.columns = [c.lower() for c in cache_df.columns]
        active = pd.merge(active, cache_df[['symbol', 'ltp']], on='symbol', how='left')
        active['ltp'] = pd.to_numeric(active['ltp']).fillna(active['wacc'])
    
    active['current_val'] = active['net_qty'] * active['ltp']
    active['pl_amt'] = active['current_val'] - active['total_cost']
    active['pl_pct'] = (active['pl_amt'] / active['total_cost']) * 100
    active['weight'] = (active['current_val'] / active['current_val'].sum()) * 100

    # Display Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("Invested", f"Rs {active['total_cost'].sum():,.0f}")
    c2.metric("Value", f"Rs {active['current_val'].sum():,.0f}")
    c3.metric("P/L", f"Rs {active['pl_amt'].sum():,.0f}", f"{(active['pl_amt'].sum()/active['total_cost'].sum()*100):.2f}%")

    # STYLING THE DATAFRAME
    st.subheader("📋 Active Holdings")
    display_df = active[['symbol', 'net_qty', 'wacc', 'ltp', 'pl_amt', 'pl_pct', 'weight']]
    
    # Use .map() instead of .applymap() for Pandas 2.1+
    styled_df = display_df.style.map(style_pl, subset=['pl_pct']).format({
        'wacc': '{:.2f}', 'ltp': '{:.2f}', 'pl_amt': '{:.2f}', 'pl_pct': '{:.2f}%', 'weight': '{:.1f}%'
    })

    st.dataframe(styled_df, use_container_width=True, hide_index=True)
