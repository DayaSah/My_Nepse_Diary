import streamlit as st
import pandas as pd

def render(role):
    st.subheader("Net Payout Simulator (Sell)")
    st.write("Calculate exact net profit after NEPSE fees and Capital Gains Tax (CGT).")

    conn = st.connection("neon", type="sql")
    try:
        port_df = conn.query("SELECT * FROM portfolio", ttl=0)
    except:
        return

    # [Same holding calculation logic as above for brevity]
    port_df['qty'] = pd.to_numeric(port_df['qty'])
    port_df['price'] = pd.to_numeric(port_df['price'])
    buys = port_df[port_df['transaction_type'] == 'BUY']
    sells = port_df[port_df['transaction_type'] == 'SELL'].groupby('symbol')['qty'].sum().reset_index()
    sells.rename(columns={'qty': 'sold_qty'}, inplace=True)
    holdings = buys.groupby('symbol').apply(lambda x: pd.Series({'total_qty': x['qty'].sum(), 'total_cost': (x['qty'] * x['price']).sum()})).reset_index()
    holdings = pd.merge(holdings, sells, on='symbol', how='left').fillna(0)
    holdings['net_qty'] = holdings['total_qty'] - holdings['sold_qty']
    holdings = holdings[holdings['net_qty'] > 0]
    holdings['wacc'] = holdings['total_cost'] / holdings['total_qty']

    if holdings.empty:
        st.info("No active holdings found.")
        return

    col1, col2 = st.columns([1, 2])
    with col1:
        sel_stock = st.selectbox("Select Stock to Sell", holdings['symbol'].tolist(), key="sell_sim_stk")
        stk_data = holdings[holdings['symbol'] == sel_stock].iloc[0]
        st.info(f"Available: {stk_data['net_qty']} units\nWACC: Rs {stk_data['wacc']:,.2f}")

    with col2:
        with st.form("sell_sim_form"):
            sim_sell_qty = st.number_input("Shares to Sell", min_value=1, max_value=int(stk_data['net_qty']), value=int(stk_data['net_qty']))
            sim_sell_target = st.number_input("Target Sell Price (Rs)", min_value=1.0, value=float(stk_data['wacc'] * 1.1)) # Default 10% gain
            cgt_rate = st.radio("CGT Rate", options=[5.0, 7.5], format_func=lambda x: f"{x}% (Long Term)" if x == 5.0 else f"{x}% (Short Term)", horizontal=True)
            
            if st.form_submit_button("Simulate Payout", type="primary"):
                # --- Core Financial Engine ---
                gross_amt = sim_sell_qty * sim_sell_target
                cost_basis = sim_sell_qty * stk_data['wacc']
                
                # Deductions
                broker_fee = gross_amt * 0.004  # Avg 0.4%
                sebon_fee = gross_amt * 0.00015 # 0.015%
                dp_fee = 25.0
                
                gross_profit = gross_amt - cost_basis
                cgt = max(0, gross_profit * (cgt_rate / 100)) # Only tax if profit > 0
                
                net_payout = gross_amt - broker_fee - sebon_fee - dp_fee - cgt
                net_profit = net_payout - cost_basis
                roi = (net_profit / cost_basis) * 100

                # --- Visual Display ---
                st.divider()
                rc1, rc2, rc3 = st.columns(3)
                rc1.metric("Expected Bank Deposit", f"Rs {net_payout:,.2f}")
                rc2.metric("Net Pure Profit", f"Rs {net_profit:,.2f}", f"{roi:,.2f}% ROI")
                rc3.metric("Total Deductions", f"Rs {(broker_fee+sebon_fee+dp_fee+cgt):,.2f}", "Taxes & Fees", delta_color="inverse")
                
                with st.expander("🧾 View Invoice Breakdown"):
                    st.write(f"- **Gross Revenue:** Rs {gross_amt:,.2f}")
                    st.write(f"- **Broker Commission:** Rs {broker_fee:,.2f}")
                    st.write(f"- **SEBON Fee:** Rs {sebon_fee:,.2f}")
                    st.write(f"- **DP Charge:** Rs {dp_fee:,.2f}")
                    st.write(f"- **Capital Gains Tax ({cgt_rate}%):** Rs {cgt:,.2f}")
