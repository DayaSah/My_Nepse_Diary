import streamlit as st
import pandas as pd
from datetime import date

def render_page():
    st.title("🚀 Advanced Portfolio Analytics")
    conn = st.connection("neon", type="sql")
    
    port_df = conn.query("SELECT * FROM portfolio", ttl=0)
    port_df.columns = [c.lower() for c in port_df.columns]
    cache_df = conn.query("SELECT * FROM cache", ttl=600)
    if not cache_df.empty: cache_df.columns = [c.lower() for c in cache_df.columns]

    # --- ADVANCED CALCULATIONS ---
    # 1. Realized P/L Logic
    buys = port_df[port_df['transaction_type'].str.upper() == 'BUY'].copy()
    sells = port_df[port_df['transaction_type'].str.upper() == 'SELL'].copy()
    
    # Get WACC per symbol
    wacc_map = buys.groupby('symbol').apply(lambda x: (x['qty']*x['price']).sum() / x['qty'].sum()).to_dict()
    
    # Realized P/L = (Sell Price - WACC) * Qty - Approx Fees (0.5%)
    sells['realized_pl'] = ((sells['price'] - sells['symbol'].map(wacc_map)) * sells['qty']) - (sells['price'] * sells['qty'] * 0.005)
    total_realized = sells['realized_pl'].sum()

    # 2. Friction Costs (Fees)
    # Total Volume * approx 0.5% NEPSE fees
    total_vol = (buys['qty']*buys['price']).sum() + (sells['qty']*sells['price']).sum()
    est_fees = total_vol * 0.005

    # 3. Projected CGT (On Unrealized Profit only)
    # Using basic logic: if current profit > 0, reserve 7.5%
    active_invested = sum([v * qty for symbol, v in wacc_map.items() for qty in [port_df[port_df['symbol']==symbol]['qty'].sum()]]) # Simplified for example
    # (In real app, use the active_holdings logic from Basic)
    
    # --- UI: THE TRADER DASHBOARD ---
    st.markdown("### 🏆 Performance Scorecard")
    c1, c2, c3 = st.columns(3)
    
    c1.metric("Realized Profit (Cash)", f"Rs {total_realized:,.2f}")
    c2.metric("Total Fees Paid", f"Rs {est_fees:,.2f}", delta="Friction Cost", delta_color="inverse")
    
    win_rate = (len(sells[sells['realized_pl'] > 0]) / len(sells) * 100) if not sells.empty else 0
    c3.metric("Win Rate", f"{win_rate:.1f}%")

    st.divider()

    col_a, col_b = st.columns(2)
    
    with col_a:
        st.subheader("🛡️ Risk Analysis")
        # Example: Concentration Risk
        st.info("Concentration Risk: Your top stock covers X% of portfolio.")
        st.warning("Projected CGT: Rs. XXX will be deducted upon selling.")

    with col_b:
        st.subheader("📈 Profit Analytics")
        st.write(f"Total Net Wealth (Realized + Unrealized): Rs {total_realized + 0:,.2f}") # Replace 0 with unrealized
        st.write(f"Average Profit per Trade: Rs {(total_realized / len(sells)) if not sells.empty else 0:,.2f}")

    st.subheader("📜 Realized Trade History")
    st.dataframe(sells[['date', 'symbol', 'qty', 'price', 'realized_pl']], use_container_width=True)
