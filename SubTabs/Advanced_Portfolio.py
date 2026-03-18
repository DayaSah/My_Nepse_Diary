import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import date

def calculate_nepse_fees(amount, side="BUY"):
    if amount <= 0: return 0
    if amount <= 50000: comm = max(10, amount * 0.0040)
    elif amount <= 500000: comm = amount * 0.0037
    else: comm = amount * 0.0033
    sebon = amount * 0.00015
    dp = 25.0
    return comm + sebon + dp

def render_advanced_view():
    st.title("🚀 Pro-Trader Analytics Dashboard")
    st.caption("Comprehensive Risk, Performance, and Tax Metrics.")

    conn = st.connection("neon", type="sql")
    
    # 1. DATA ACQUISITION & TYPE CONVERSION
    try:
        df = conn.query("SELECT * FROM portfolio", ttl=0)
        cache = conn.query("SELECT * FROM cache", ttl=600)
        wealth_history = conn.query("SELECT * FROM wealth ORDER BY snapshot_date ASC", ttl=0)
        
        df.columns = [c.lower() for c in df.columns]
        df['qty'] = pd.to_numeric(df['qty'], errors='coerce').fillna(0)
        df['price'] = pd.to_numeric(df['price'], errors='coerce').fillna(0)

        if not cache.empty: 
            cache.columns = [c.lower() for c in cache.columns]
            cache['ltp'] = pd.to_numeric(cache['ltp'], errors='coerce').fillna(0)
            cache['change'] = pd.to_numeric(cache['change'], errors='coerce').fillna(0)
            
        if not wealth_history.empty: 
            wealth_history.columns = [c.lower() for c in wealth_history.columns]
            wealth_history['current_value'] = pd.to_numeric(wealth_history['current_value'], errors='coerce').fillna(0)
            
    except Exception as e:
        st.error(f"Data Fetch Error: {e}"); return

    if df.empty:
        st.warning("No transaction data found to analyze."); return

    # 2. CALCULATION ENGINE
    df['date'] = pd.to_datetime(df['date']).dt.date
    buys = df[df['transaction_type'].str.upper() == 'BUY'].copy()
    sells = df[df['transaction_type'].str.upper() == 'SELL'].copy()

    stock_stats = []
    unique_symbols = df['symbol'].unique()

    for sym in unique_symbols:
        s_buys = buys[buys['symbol'] == sym]
        s_sells = sells[sells['symbol'] == sym]
        
        t_buy_qty = s_buys['qty'].sum()
        gross_buy_amt = (s_buys['qty'] * s_buys['price']).sum()
        total_buy_fees = sum([calculate_nepse_fees(r.qty * r.price, "BUY") for i, r in s_buys.iterrows()])
        wacc_adj = (gross_buy_amt + total_buy_fees) / t_buy_qty if t_buy_qty > 0 else 0
        
        t_sell_qty = s_sells['qty'].sum()
        net_qty = t_buy_qty - t_sell_qty
        
        realized_profit = 0
        if not s_sells.empty:
            sell_amt = (s_sells['qty'] * s_sells['price']).sum()
            sell_fees = sum([calculate_nepse_fees(r.qty * r.price, "SELL") for i, r in s_sells.iterrows()])
            realized_profit = (sell_amt - (t_sell_qty * wacc_adj)) - sell_fees

        # Live Data Match
        if not cache.empty and sym in cache['symbol'].values:
            match = cache[cache['symbol'] == sym].iloc[0]
            ltp = match['ltp']
            change_val = match['change']
        else:
            ltp = wacc_adj
            change_val = 0
        
        prev_close = ltp - change_val
        
        if net_qty > 0:
            first_buy = s_buys['date'].min()
            days_held = (date.today() - first_buy).days
            invested = net_qty * wacc_adj
            curr_val = net_qty * ltp
            unrealized = curr_val - invested
            
            stock_stats.append({
                'Symbol': sym, 'Qty': net_qty, 'WACC': wacc_adj, 'LTP': ltp,
                'Invested': invested, 'Value': curr_val, 'Unrealized': unrealized,
                'Return%': (unrealized/invested)*100 if invested > 0 else 0, 
                'Days': days_held, 'BEP': (invested * 1.005 + 25) / net_qty,
                'Day_Gain': (ltp - prev_close) * net_qty,
                'CGT_Est': max(0, unrealized * (0.05 if days_held > 365 else 0.075)),
                'Realized': realized_profit
            })
        else:
            stock_stats.append({'Symbol': sym, 'Qty': 0, 'Realized': realized_profit, 'Invested': 0, 'Value': 0})

    s_df = pd.DataFrame(stock_stats)
    active_df = s_df[s_df['Qty'] > 0].copy()

    # 3. MACRO VIEW
    total_inv = active_df['Invested'].sum()
    total_val = active_df['Value'].sum()
    total_unrealized = active_df['Unrealized'].sum()
    total_realized = s_df['Realized'].sum()
    total_fees = (df['qty'] * df['price']).sum() * 0.005 
    
    st.subheader("📊 Macro Portfolio Analytics")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Principal vs Pot", f"Rs {total_val:,.0f}", f"Net: {total_unrealized + total_realized:,.0f}")
    m2.metric("Total Realized Cash", f"Rs {total_realized:,.0f}", delta="Booked Profit")
    m3.metric("Friction Cost", f"Rs {total_fees:,.0f}", delta_color="inverse")
    m4.metric("Net Portfolio Return", f"{((total_unrealized + total_realized)/total_inv*100):.2f}%" if total_inv > 0 else "0%")

    st.divider()

    # 4. EQUITY CURVE
    if not wealth_history.empty:
        st.subheader("📈 Wealth Trajectory")
        fig_equity = px.area(wealth_history, x='snapshot_date', y='current_value', title="Equity Curve")
        st.plotly_chart(fig_equity, use_container_width=True)

    # 5. MICRO VIEW
    st.subheader("🔬 Individual Stock Micro-Health")
    active_df['Weight%'] = (active_df['Value'] / total_val) * 100 if total_val > 0 else 0
    active_df['Profit_Shield'] = active_df['Return%'].apply(lambda x: "🛡️ Trailing Stop" if x > 20 else "Normal")

    st.dataframe(
        active_df[['Symbol', 'Qty', 'WACC', 'BEP', 'LTP', 'Weight%', 'Return%', 'Unrealized', 'Day_Gain', 'Days', 'Profit_Shield']],
        use_container_width=True, hide_index=True,
        column_config={
            "Weight%": st.column_config.ProgressColumn("Weightage", format="%.1f%%", min_value=0, max_value=100),
            "Return%": st.column_config.NumberColumn("ROI%", format="%.2f%%"),
            "Unrealized": st.column_config.NumberColumn("Unrealized P/L", format="Rs %d"),
            "Day_Gain": st.column_config.NumberColumn("Today's P/L", format="Rs %d")
        }
    )

    # 6. RISK & PERFORMANCE
    col_risk, col_perf = st.columns(2)
    with col_risk:
        st.subheader("🛡️ Risk Metrics")
        heavy = active_df[active_df['Weight%'] > 25]
        for _, row in heavy.iterrows():
            st.warning(f"🚨 **Panic Meter:** {row['Symbol']} is {row['Weight%']:.1f}% of your portfolio.")
        st.info(f"💾 **Tax Reserve:** Rs {active_df['CGT_Est'].sum():,.2f}")

    with col_perf:
        st.subheader("🎯 Self-Improvement")
        closed = s_df[(s_df['Qty'] == 0) & (s_df['Realized'] != 0)]
        if not closed.empty:
            win_rate = (len(closed[closed['Realized'] > 0]) / len(closed)) * 100
            st.write(f"**Win/Loss Ratio:** {win_rate:.1f}%")
            st.write(f"**Avg Win:** Rs {closed[closed['Realized'] > 0]['Realized'].mean():,.0f}")
        else:
            st.caption("No closed trades yet.")

    # 7. SECTOR ALLOCATION (FIXED MERGE LOGIC)
    st.divider()
    st.subheader("Sector Allocation")
    if not cache.empty and not active_df.empty:
        # Determine unique columns to avoid duplicate keys
        if 'sector' in cache.columns:
            sector_map = cache[['symbol', 'sector']].drop_duplicates()
        else:
            # Fallback if sector column is missing
            sector_map = pd.DataFrame({'symbol': cache['symbol'], 'sector': 'Other'})
        
        sector_data = pd.merge(active_df, sector_map, left_on='Symbol', right_on='symbol', how='left')
        sector_data['sector'] = sector_data['sector'].fillna('Unknown')
        
        fig_sector = px.sunburst(sector_data, path=['sector', 'Symbol'], values='Value', 
                                 title="Portfolio by Sector", color='Return%',
                                 color_continuous_scale='RdYlGn')
        st.plotly_chart(fig_sector, use_container_width=True)

if __name__ == "__main__":
    render_advanced_view()
