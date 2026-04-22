import streamlit as st
import pandas as pd

def render(role):
    st.subheader("🎯 Trade Entry Planner")
    
    with st.form("entry_plan_form"):
        c1, c2 = st.columns(2)
        with c1:
            symbol = st.text_input("Stock Symbol (Optional)", placeholder="e.g., NICA")
            entry_price = st.number_input("Entry Price (Rs)", min_value=1.0, value=500.0)
            qty = st.number_input("Quantity", min_value=1, value=100)
            risk_amt = st.number_input("Max Loss You Can Tolerate (Rs)", value=2000.0, help="Used for position sizing advice.")
            cgt_rate = 7.5

        with c2:
            st.caption("Profit Targets")
            t1 = st.number_input("Target 1", value=entry_price * 1.10)
            t2 = st.number_input("Target 2", value=entry_price * 1.20)
            
            st.caption("Risk Management")
            sl1 = st.number_input("Stop Loss 1", value=entry_price * 0.95)
            sl2 = st.number_input("Stop Loss 2", value=entry_price * 0.90)

        submit = st.form_submit_button("Calculate Risk/Reward", type="primary")

    if submit:
        def calc_net(price, quantity, is_buy, wacc=0):
            amt = price * quantity
            broker_fee = amt * 0.004
            sebon_fee = amt * 0.00015
            dp_fee = 25.0
            if is_buy:
                return amt + broker_fee + sebon_fee + dp_fee
            else:
                gross_profit = amt - (wacc * quantity)
                cgt = max(0, gross_profit * (cgt_rate / 100))
                return amt - broker_fee - sebon_fee - dp_fee - cgt

        # --- Core Logic ---
        total_investment = calc_net(entry_price, qty, is_buy=True)
        effective_wacc = total_investment / qty
        
        # Proper Risk Calculation (Difference between total cost and net payout at SL)
        net_at_sl1 = calc_net(sl1, qty, is_buy=False, wacc=effective_wacc)
        actual_risk = total_investment - net_at_sl1

        # --- Visual Displays ---
        st.info(f"**Capital Required:** Rs {total_investment:,.2f} | **Effective WACC:** Rs {effective_wacc:,.2f}")
        
        cols = st.columns(4)
        targets = [("T1", t1), ("T2", t2), ("SL1", sl1), ("SL2", sl2)]
        
        for i, (label, price) in enumerate(targets):
            net_payout = calc_net(price, qty, is_buy=False, wacc=effective_wacc)
            net_profit = net_payout - total_investment
            roi = (net_profit / total_investment) * 100
            color = "normal" if i < 2 else "inverse"
            
            with cols[i]:
                st.metric(label, f"Rs {net_profit:,.2f}", f"{roi:.2f}%", delta_color=color)
                if i < 2:
                    rr = abs(net_profit / actual_risk) if actual_risk > 0 else 0
                    st.caption(f"RR: 1:{rr:.2f}")

        # --- Professional Insights ---
        with st.expander("📊 Trade Execution Insights"):
            suggested_qty = int(risk_amt / (effective_wacc - (calc_net(sl1, 1, False, effective_wacc)))) if actual_risk > 0 else 0
            
            st.write(f"**Break-even Price:** Rs {effective_wacc:,.2f}")
            st.write(f"**Total Fees (Exit at T1):** Rs {(total_investment - (entry_price*qty)) + ( (t1*qty) - calc_net(t1, qty, False, effective_wacc)):,.2f}")
            
            if qty > suggested_qty:
                st.warning(f"**Position Size Alert:** Based on your Rs {risk_amt} risk tolerance, you should only buy **{suggested_qty} shares**. Your current quantity ({qty}) is over-leveraged.")
            else:
                st.success(f"**Position Size:** Safe. You can buy up to **{suggested_qty} shares** within your risk limit.")
