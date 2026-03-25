import streamlit as st
import pandas as pd
import numpy as np
from SubTabs.Advanced_Portfolio import render_advanced_view 

def calculate_fifo_wacc(df):
    """
    Calculates the exact WACC using FIFO logic to match MeroShare/TMS.
    """
    active_holdings = []
    unique_symbols = df['symbol'].unique()

    for symbol in unique_symbols:
        symbol_df = df[df['symbol'] == symbol].sort_values('date')
        inventory = []  # List of dicts: {'qty': ..., 'net_amount': ...}
        
        for _, row in symbol_df.iterrows():
            qty = abs(int(row['qty']))
            net_amt = abs(float(row['net_amount']))
            
            if row['transaction_type'].upper() == 'BUY':
                inventory.append({'qty': qty, 'total_cost': net_amt})
            
            elif row['transaction_type'].upper() == 'SELL':
                remaining_to_sell = qty
                while remaining_to_sell > 0 and inventory:
                    if inventory[0]['qty'] <= remaining_to_sell:
                        remaining_to_sell -= inventory[0]['qty']
                        inventory.pop(0)
                    else:
                        # Reduce quantity and proportional cost from the oldest lot
                        unit_cost = inventory[0]['total_cost'] / inventory[0]['qty']
                        inventory[0]['qty'] -= remaining_to_sell
                        inventory[0]['total_cost'] -= (unit_cost * remaining_to_sell)
                        remaining_to_sell = 0
        
        if inventory:
            total_qty = sum(item['qty'] for item in inventory)
            total_cost = sum(item['total_cost'] for item in inventory)
            wacc = total_cost / total_qty
            active_holdings.append({
                'symbol': symbol,
                'net_qty': total_qty,
                'wacc': wacc,
                'total_cost': total_cost
            })
            
    return pd.DataFrame(active_holdings)

def style_pl_intensity(val):
    """
    Applies color intensity based on the percentage value.
    """
    try:
        # Green for profit, Red for loss
        if val > 0:
            # Scale intensity (max brightness at 15% profit)
            alpha = min(val / 15, 0.8) 
            return f'background-color: rgba(0, 255, 0, {alpha}); color: white;'
        elif val < 0:
            alpha = min(abs(val) / 15, 0.8)
            return f'background-color: rgba(255, 0, 0, {alpha}); color: white;'
    except:
        pass
    return ''

def render_page(role):
    if 'portfolio_view' not in st.session_state:
        st.session_state.portfolio_view = 'basic'

    if st.session_state.portfolio_view == 'advanced':
        if st.button("⬅️ Back to Basic Portfolio"):
            st.session_state.portfolio_view = 'basic'
            st.rerun()
        render_advanced_view()
        return

    st.title("💼 My Portfolio")
    conn = st.connection("neon", type="sql")

    try:
        port_df = conn.query("SELECT * FROM portfolio", ttl=0)
        cache_df = conn.query("SELECT * FROM cache", ttl=0) # Set ttl to 0 for live prices
        port_df.columns = [c.lower() for c in port_df.columns]
    except Exception as e:
        st.error(f"Database Error: {e}"); return

    if port_df.empty:
        st.info("Portfolio is empty."); return

    # 1. Logic: Calculate FIFO WACC
    active = calculate_fifo_wacc(port_df)
    
    if active.empty:
        st.info("No active holdings found."); return

    # 2. Join with Cache for LTP
    if not cache_df.empty:
        cache_df.columns = [c.lower() for c in cache_df.columns]
        active = pd.merge(active, cache_df[['symbol', 'ltp']], on='symbol', how='left')
        active['ltp'] = pd.to_numeric(active['ltp']).fillna(active['wacc'])
    else:
        active['ltp'] = active['wacc']

    # 3. Final Calculations
    active['current_val'] = active['net_qty'] * active['ltp']
    active['pl_amt'] = active['current_val'] - active['total_cost']
    active['pl_pct'] = (active['pl_amt'] / active['total_cost']) * 100
    
    total_invested = active['total_cost'].sum()
    total_market_val = active['current_val'].sum()
    total_pl = total_market_val - total_invested
    total_pl_pct = (total_pl / total_invested * 100) if total_invested > 0 else 0

    active['weight'] = (active['current_val'] / total_market_val) * 100
    # Breakeven: WACC + 0.5% (broker/sebon) + DP Charge (Rs 25)
    active['breakeven'] = (active['wacc'] * 1.005) + (25 / active['net_qty'])

    # --- Summary Metrics ---
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Invested", f"Rs {total_invested:,.2f}")
    m2.metric("Market Value", f"Rs {total_market_val:,.2f}")
    m3.metric("Unrealized P/L", f"Rs {total_pl:,.2f}", f"{total_pl_pct:.2f}%")

    st.divider()
    
    if st.button("🚀 Switch to Advanced Portfolio (Deep Analytics)", use_container_width=True, type="primary"):
        st.session_state.portfolio_view = 'advanced'
        st.rerun()

    st.subheader("📋 Active Holdings")
    
    # Select and rename columns for display
    display_df = active[['symbol', 'net_qty', 'wacc', 'breakeven', 'ltp', 'pl_amt', 'pl_pct', 'weight']].copy()
    
    # Apply Styling
    styled_df = display_df.style.applymap(style_pl_intensity, subset=['pl_pct']) \
                                .format({
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
            "net_qty": "Units",
            "pl_amt": "Profit/Loss",
            "pl_pct": "P/L %"
        }
    )
