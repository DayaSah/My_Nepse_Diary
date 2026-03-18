import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime

def calculate_nepse_fees(amount, side="BUY"):
    """Calculates tiered broker commission, SEBON fee, and DP fee."""
    if amount <= 0: return 0
    # Tiered Commission
    if amount <= 50000: comm = max(10, amount * 0.0040)
    elif amount <= 500000: comm = amount * 0.0037
    else: comm = amount * 0.0033
    
    sebon = amount * 0.00015
    dp = 25.0
    return comm + sebon + dp

def render_advanced_view():
    st.title("🚀 Pro-Trader Analytics Dashboard")
    st.caption("Deep-dive into Risk, Performance, and Friction Costs.")

    conn = st.connection("neon", type="sql")
    
    # 1. DATA ACQUISITION & TYPE CONVERSION
    try:
        df = conn.query("SELECT * FROM portfolio", ttl=0)
        cache = conn.query("SELECT * FROM cache", ttl=600)
        wealth_history = conn.query("SELECT * FROM wealth ORDER BY snapshot_date ASC", ttl=0)
        
        # Standardize Columns
        df.columns = [c.lower() for c in df.columns]
        
        # IMPORTANT: Force numeric types to prevent "UFuncTypeError"
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

    # 2. CALCULATION ENGINE (PRE-PROCESSING)
    df['date'] = pd.to_datetime(df['date']).dt.date
    buys = df[df['transaction_type'].str.upper() == 'BUY'].copy()
    sells = df[df['transaction_type'].str.upper() == 'SELL'].copy()

    # --- WACC & Holding Period Logic ---
    stock_stats = []
    unique_symbols = df['symbol'].unique()

    for sym in unique_symbols:
        s_buys = buys[buys['symbol'] == sym]
        s_sells = sells[sells['symbol'] == sym]
        
        t_buy_qty = s_buys['qty'].sum()
        # Adjusted WACC: (Buy Amount + Buy Fees) / Qty
        gross_buy_amt = (s_buys['qty'] * s_buys['price']).sum()
        total_buy_fees = sum([calculate_nepse_fees(r.qty * r.price, "BUY") for i, r in s_buys.iterrows()])
        wacc_adjusted = (gross_buy_amt + total_buy_fees) / t_buy_qty if t_buy_qty > 0 else 0
        
        t_sell_qty = s_sells['qty'].sum()
        net_qty = t_buy_qty - t_sell_qty
        
        # Realized P/L Calculation
        realized_profit = 0
        if not s_sells.empty:
            sell_amt = (s_sells['qty'] * s_sells['price']).sum()
            sell_fees = sum([calculate_nepse_fees(r.qty * r.price, "SELL") for i, r in s_sells.iterrows()])
            realized_profit = (sell_amt - (t_sell_qty * wacc_adjusted)) - sell_fees

        # FIX: Live Data Match with Numeric Safety
        if sym in cache['symbol'].values:
            ltp = cache[cache['symbol'] == sym]['ltp'].values[0]
            change_val = cache[cache['symbol'] == sym]['change'].values[0]
        else:
            ltp = wacc_adjusted
            change_val = 0
        
        prev_close = ltp - change_val # This is safe now because both are floats
        
        if net_qty > 0:
            first_buy = s_buys['date'].min()
            days_held = (date.today() - first_buy).days
            invested = net_qty * wacc_adjusted
            curr_val = net_qty * ltp
            unrealized = curr_val - invested
            
            # CGT Projection
            cgt_rate = 0.05 if days_held > 365 else 0.075
            projected_cgt = max(0, unrealized * cgt_rate)
            
            stock_stats.append({
                'Symbol': sym, 'Qty': net_qty, 'WACC': wacc_adjusted, 'LTP': ltp,
                'Invested': invested, 'Value': curr_val, 'Unrealized': unrealized,
                'Return%': (unrealized/invested)*100 if invested > 0 else 0, 
                'Days': days_held,
                'BEP': (invested * 1.005 + 25) / net_qty,
                'Day_Gain': (ltp - prev_close) * net_qty,
                'CGT_Est': projected_cgt,
                'Realized': realized_profit
            })
        else:
            stock_stats.append({'Symbol': sym, 'Qty': 0, 'Realized': realized_profit, 'Invested': 0, 'Value': 0})

    s_df = pd.DataFrame(stock_stats)
    active_df = s_df[s_df['Qty'] > 0].copy()

    # 3. MACRO VIEW (PORTFOLIO WIDE)
    total_inv = active_df['Invested'].sum()
    total_val = active_df['Value'].sum()
    total_unrealized = active_df['Unrealized'].sum()
    total_realized = s_df['Realized'].sum()
    total_fees = (df['qty'] * df['price']).sum() * 0.005 
    
    st.subheader("📊 Macro Portfolio Analytics")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Principal vs Pot", f"Rs {total_val:,.0f}", f"Net: {total_unrealized + total_realized:,.0f}")
    m2.metric("Total Realized Cash", f"Rs {total_realized:,.0f}", delta="Booked Profit")
    m3.metric("Friction Cost", f"Rs {total_fees:,.0f}", help="Total Broker + SEBON + DP Fees paid", delta_color="inverse")
    m4.metric("Net Portfolio Return", f"{((total_unrealized + total_realized)/total_inv*100):.2f}%" if total_inv > 0 else "0%")

    st.divider()

    # 4. EQUITY CURVE & DRAWDOWN
    if not wealth_history.empty:
        st.subheader("📈 Wealth Trajectory & Equity Curve")
        fig_equity = px.area(wealth_history, x='snapshot_date', y='current_value', title="Equity Curve (Total Portfolio Value over Time)")
        
        # Max Drawdown Calculation
        wealth_history['peak'] = wealth_history['current_value'].cummax()
        wealth_history['drawdown'] = (wealth_history['current_value'] - wealth_history['peak']) / wealth_history['peak']
        max_dd = wealth_history['drawdown'].min() * 100
        
        st.plotly_chart(fig_equity, use_container_width=True)
        st.error(f"📉 Historical Max Drawdown: {max_dd:.2f}%")

    st.divider()

    # 5. MICRO VIEW (INDIVIDUAL PERFORMANCE)
    st.subheader("🔬 Individual Stock Micro-Health")
    active_df['Weight%'] = (active_df['Value'] / total_val) * 100 if total_val > 0 else 0
    active_df['Profit_Shield'] = active_df['Return%'].apply(lambda x: "🛡️ Trailing Stop Recommended" if x > 20 else "Normal")

    st.dataframe(
        active_df[['Symbol', 'Qty', 'WACC', 'BEP', 'LTP', 'Weight%', 'Return%', 'Unrealized', 'Day_Gain', 'Days', 'Profit_Shield']],
        use_container_width=True, hide_index=True,
        column_config={
            "Weight%": st.column_config.ProgressColumn("Weightage", format="%.1f%%", min_value=0, max_value=100),
            "Return%": st.column_config.NumberColumn("ROI%", format="%.2f%%"),
            "Unrealized": st.column_config.NumberColumn("Unrealized P/L", format="Rs %d"),
            "Day_Gain": st.column_config.NumberColumn("Today's P/L", format="Rs %d"),
            "BEP": "Breakeven"
        }
    )

    # 6. RISK & PERFORMANCE ANALYTICS
    col_risk, col_perf = st.columns(2)

    with col_risk:
        st.subheader("🛡️ Risk & Decision Metrics")
        heavy_stocks = active_df[active_df['Weight%'] > 25]
        if not heavy_stocks.empty:
            for _, row in heavy_stocks.iterrows():
                st.warning(f"🚨 **Panic Meter:** {row['Symbol']} is {row['Weight%']:.1f}% of your portfolio. Consider diversifying.")
        else:
            st.success("✅ Concentration Risk: Portfolio is well-diversified.")

        st.info(f"💾 **Tax Reserve:** Rs {active_df['CGT_Est'].sum():,.2f} (Estimated CGT if sold today)")

    with col_perf:
        st.subheader("🎯 Self-Improvement Metrics")
        closed_trades = s_df[(s_df['Qty'] == 0) & (s_df['Realized'] != 0)]
        if not closed_trades.empty:
            win_count = len(closed_trades[closed_trades['Realized'] > 0])
            win_rate = (win_count / len(closed_trades)) * 100
            st.write(f"**Win/Loss Ratio:** {win_rate:.1f}%")
            
            avg_win = closed_trades[closed_trades['Realized'] > 0]['Realized'].mean()
            avg_loss = closed_trades[closed_trades['Realized'] < 0]['Realized'].mean()
            st.write(f"**Avg Win:** Rs {avg_win:,.0f} | **Avg Loss:** Rs {abs(avg_loss) if not np.isnan(avg_loss) else 0:,.0f}")
        else:
            st.caption("Not enough closed trades to calculate win/loss metrics.")

    # 7. ASSET ALLOCATION (SECTORAL)
    st.divider()
    st.subheader("Sector Allocation")
    if not cache.empty:
        sector_col = 'sector' if 'sector' in cache.columns else 'symbol'
        sector_data = pd.merge(active_df, cache[['symbol', sector_col]], left_on='Symbol', right_on='symbol', how='left')
        
        fig_sector = px.sunburst(sector_data, path=[sector_col, 'Symbol'], values='Value', 
                                 title="Portfolio by Sector & Stock", color='Return%',
                                 color_continuous_scale='RdYlGn')
        st.plotly_chart(fig_sector, use_container_width=True)

    # 8. PERFORMANCE ANALYTICS (CAGR)
    if not wealth_history.empty and len(wealth_history) > 1:
        start_val = wealth_history['current_value'].iloc[0]
        end_val = wealth_history['current_value'].iloc[-1]
        start_date = pd.to_datetime(wealth_history['snapshot_date'].iloc[0])
        end_date = pd.to_datetime(wealth_history['snapshot_date'].iloc[-1])
        years = (end_date - start_date).days / 365.25
        
        if years > 0 and start_val > 0:
            cagr = ((end_val / start_val) ** (1/years) - 1) * 100
            st.metric("Portfolio CAGR", f"{cagr:.2f}% per year")

if __name__ == "__main__":
    render_advanced_view()
