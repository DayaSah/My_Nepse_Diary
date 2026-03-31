import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import date

def get_current_stock_info(conn, symbol):
    """Calculates quantity, Rolling WACC, and EXACT Holding Period using FIFO."""
    if not symbol: return 0, 0.0, date.today()
    
    try:
        df = conn.query(f"SELECT * FROM portfolio WHERE symbol = '{symbol.upper()}' ORDER BY date ASC, transaction_type DESC", ttl=0)
        if df.empty: return 0, 0.0, date.today()
        
        df.columns = [c.lower() for c in df.columns]
        df['date'] = pd.to_datetime(df['date']).dt.date
        
        if 'net_amount' not in df.columns:
            df['net_amount'] = df['qty'] * df['price']
        else:
            df['net_amount'] = df['net_amount'].fillna(df['qty'] * df['price'])
            
        current_qty = 0
        total_invested = 0.0
        
        # NEW: FIFO Queue to track the age of specific batches
        date_inventory = [] 
        
        for index, row in df.iterrows():
            if row['transaction_type'].upper() == 'BUY':
                current_qty += row['qty']
                total_invested += row['net_amount']
                # Add this specific batch and its date to the inventory
                date_inventory.append({'qty': row['qty'], 'date': row['date']})
                
            elif row['transaction_type'].upper() == 'SELL':
                current_wacc = total_invested / current_qty if current_qty > 0 else 0.0
                current_qty -= row['qty']
                total_invested -= (row['qty'] * current_wacc)
                
                if current_qty <= 0:
                    current_qty = 0
                    total_invested = 0.0
                    date_inventory = [] # Wipe inventory if fully sold
                else:
                    # NEW: Remove the oldest shares from the inventory first (FIFO)
                    rem = row['qty']
                    while rem > 0 and date_inventory:
                        if date_inventory[0]['qty'] <= rem:
                            rem -= date_inventory[0]['qty']
                            date_inventory.pop(0) # Oldest batch fully sold out
                        else:
                            date_inventory[0]['qty'] -= rem
                            rem = 0
                    
        final_wacc = total_invested / current_qty if current_qty > 0 else 0.0
        
        # The oldest date is simply the date of the first batch remaining in inventory
        first_buy_date = date_inventory[0]['date'] if date_inventory else date.today()
        
        return current_qty, final_wacc, first_buy_date
        
    except Exception as e:
        return 0, 0.0, date.today()

def calculate_fees(qty, price, trx_type, include_dp, wacc=0.0, cgt_rate=0.05, override_comm=0.0):
    """Perfected NEPSE logic with exact algebraic breakeven reversal."""
    base = qty * price
    
    # 1. Determine dynamic commission rate
    if base <= 50000:
        comm_rate = 0.0036 
    elif base <= 500000:
        comm_rate = 0.0033 
    elif base <= 2000000:
        comm_rate = 0.0031 
    elif base <= 10000000:
        comm_rate = 0.0027 
    else:
        comm_rate = 0.0024 
    
    # Check if user manually overrode the commission
    if override_comm > 0:
        broker_comm = override_comm
    else:
        broker_comm = max(10.0, base * comm_rate)
    
    sebon_fee = base * 0.00015
    dp_fee = 25.0 if include_dp else 0.0
    total_charges = broker_comm + sebon_fee + dp_fee
    
    if trx_type == "BUY":
        total_val = base + total_charges
        
        # --- NEW: PERFECT BREAKEVEN MATH ---
        # Assuming the sell side will have the same commission tier.
        if (base * comm_rate) < 10.0:
            # Exact algebraic reversal for a fixed Rs 10 commission + Rs 25 DP
            target_sell_base = (total_val + dp_fee + 10.0) / (1.0 - 0.00015)
            breakeven = target_sell_base / qty
        
        else:
            # Exact algebraic reversal for percentage-based tiers
            target_sell_base = (total_val + dp_fee) / (1.0 - comm_rate - 0.00015)
            breakeven = target_sell_base / qty
        # -----------------------------------
        
        return {
            "base": base, "broker": broker_comm, "sebon": sebon_fee, 
            "dp": dp_fee, "fees": total_charges, "total": total_val, "be": breakeven
        }
    else:
        net_sell_value = base - total_charges
        total_buy_cost = wacc * qty
        profit = net_sell_value - total_buy_cost
        
        cgt = max(0.0, profit * cgt_rate) if profit > 0 else 0.0
        receivable = net_sell_value - cgt
        
        return {
            "base": base, "broker": broker_comm, "sebon": sebon_fee, 
            "dp": dp_fee, "fees": total_charges, "total": receivable, "cgt": cgt, "profit": profit
        }
def render_page(role):
    # --- NEW: Admin Logic ---
    is_admin = (role == "Admin")
    
    st.title("📝 Trade & Settlement Engine")
    st.caption("Advanced NEPSE calculator with automated CGT and holding period analysis.")
    
    if not is_admin:
        st.warning("🕵️ Read-Only Mode: You can calculate trades but cannot save them to the ledger.")
    # ------------------------
    
    conn = st.connection("neon", type="sql")
    col_form, col_est = st.columns([1.3, 1])

    with col_form:
        with st.container(border=True):
            trx_type = st.radio("Transaction Type", ["BUY", "SELL"], horizontal=True)
            t_symbol = st.text_input("Stock Symbol", placeholder="e.g. NABIL").upper().strip()
            
            owned_qty, calc_wacc, first_date = get_current_stock_info(conn, t_symbol)
            
            c1, c2 = st.columns(2)
            t_qty = c1.number_input("Quantity", min_value=1, step=1, value=10)
            t_price = c2.number_input("Execution Price (Rs)", min_value=1.0, step=0.1, value=100.0)
            
            t_date = st.date_input("Transaction Date", value=date.today())
            t_remarks = st.text_input("Remarks / Notes", placeholder="e.g., Bought on dip, IPO sale, etc.")

            user_wacc = calc_wacc
            cgt_val = 0.05 
            
            if trx_type == "SELL":
                days_held = (date.today() - first_date).days
                st.markdown(f"**Holding Info:** Purchased on `{first_date}` ({days_held} days ago)")
                
                if t_qty > owned_qty:
                    st.error(f"⚠️ **Short Sell Warning:** You only own {owned_qty} units of {t_symbol}.")
                else:
                    st.success(f"✅ Portfolio Balance: {owned_qty} units available.")

                sc1, sc2 = st.columns(2)
                user_wacc = sc1.number_input("Adjusted WACC", value=float(calc_wacc), help="Calculated from your ledger. Edit if needed.")
                
                default_tax_idx = 0 if days_held > 365 else 1
                cgt_selection = sc2.selectbox(
                    "CGT Rate", 
                    ["5% (Long Term > 1yr)", "7.5% (Short Term < 1yr)"],
                    index=default_tax_idx
                )
                cgt_val = 0.075 if "7.5%" in cgt_selection else 0.05

            st.divider()
            c_dp, c_comm = st.columns(2)
            include_dp = c_dp.checkbox("Include DP Fee (Rs. 25)", value=True)
            override_comm = c_comm.number_input("Override Broker Comm (Rs)", value=0.0, step=1.0, help="If NEPSE split your order and charged multiple Rs 10 minimums, enter the total TMS commission here.")
            
            st.write("")
            
            btn_calc = st.button("🧮 Calculate Estimation", use_container_width=True)
            
            log_btn_label = "🚀 Buy / Average Stock" if trx_type == "BUY" else "🔻 Log Sell Transaction"
                       
            btn_save = st.button(log_btn_label, type="primary", use_container_width=True, disabled=not is_admin)


    # ==========================================
    # CALCULATION ENGINE
    # ==========================================
    res = calculate_fees(t_qty, t_price, trx_type, include_dp, user_wacc, cgt_val, override_comm)

    # --- NEW: Determine Invested vs Received ---
    if trx_type == "BUY":
        total_invested_db = res['total']
        total_received_db = 0.0
    else:
        total_invested_db = 0.0
        total_received_db = res['total']
    # -----------------------------------------

    with col_est:
        st.subheader("🧾 Settlement Bill")
        with st.container(border=True):
            if trx_type == "BUY":
                st.metric("Total Payable Amount", f"Rs {res['total']:,.2f}")
                st.metric("Breakeven Price", f"Rs {res['be']:,.2f}", help="Target price to cover both buy and sell fees.")
            else:
                st.metric("Final Receivable Amount", f"Rs {res['total']:,.2f}")
                st.write(f"⚖️ **Net Profit/Loss:** Rs {res['profit']:,.2f}")

            st.divider()
            
            st.write(f"🔸 **Base Amount:** Rs {res['base']:,.2f}")
            st.write(f"🔹 **Broker Commission:** Rs {res['broker']:,.2f}")
            st.write(f"🔹 **SEBON Fee:** Rs {res['sebon']:,.2f}")
            st.write(f"🔹 **DP Fee:** Rs {res['dp']:,.2f}")
            
            if trx_type == "SELL":
                st.write(f"🚩 **Capital Gains Tax ({cgt_val*100}%):** Rs {res['cgt']:,.2f}")
            
            st.divider()
            total_cost_of_trade = res['fees'] + (res.get('cgt', 0) if trx_type == "SELL" else 0)
            st.info(f"**Total Fees & Taxes:** Rs {total_cost_of_trade:,.2f}")

    # ==========================================
    # SAVE TO DATABASE (Portfolio + TMS Sync)
    # ==========================================
    if btn_save and is_admin:
        if not t_symbol:
            st.error("Please enter a valid Stock Symbol.")
        else:
            try:
                # Calculate the Wallet Impact for TMS
                # Buy = Negative (Money leaves wallet), Sell = Positive (Money enters wallet)
                tms_amount = -res['total'] if trx_type == "BUY" else res['total']
                
                with conn.session as s:
                    # 1. RECORD IN PORTFOLIO TABLE
                    s.execute(text("""
                        INSERT INTO portfolio (date, symbol, qty, price, transaction_type, remarks, net_amount, total_invested, total_received) 
                        VALUES (:d, :s, :q, :p, :t, :r, :n, :ti, :tr)
                    """), {
                        "d": t_date, "s": t_symbol, "q": t_qty, "p": t_price, 
                        "t": trx_type, "r": t_remarks, "n": res['total'],
                        "ti": total_invested_db, "tr": total_received_db
                    })
                    
                    # 2. AUTOMATICALLY RECORD IN TMS_TRX TABLE
                    s.execute(text("""
                        INSERT INTO tms_trx (date, stock, type, medium, amount, charge, remark, status, reference) 
                        VALUES (:d, :s, :t, :m, :a, :c, :r, :st, :ref)
                    """), {
                        "d": t_date,
                        "s": t_symbol,
                        "t": trx_type.capitalize(), # Stores as 'Buy' or 'Sell'
                        "m": "Collateral",
                        "a": tms_amount,            # Total Payable/Receivable
                        "c": 0,                     # Charges empty as requested
                        "r": f"Auto-Logged: {t_remarks}",
                        "st": "Settled",
                        "ref": ""                   # Reference empty as requested
                    })
                    
                    # 3. AUDIT LOG
                    s.execute(text("""
                        INSERT INTO audit_log (action, symbol, details) 
                        VALUES (:act, :sym, :det)
                    """), {
                        "act": f"TRADE_{trx_type}", 
                        "sym": t_symbol, 
                        "det": f"{t_qty} units @ Rs {t_price} | TMS Sync: Rs {tms_amount:,.2f}"
                    })
                    
                    s.commit()
                st.success(f"✅ {trx_type} logged and TMS Balance updated!")
                st.balloons()
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save: {e}")

    # --- RECENT TRANSACTIONS ---
    st.markdown("---")
    st.markdown("### 🕒 Recent Entries")
    try:
        recent = conn.query("SELECT date, symbol, transaction_type as type, qty, price, remarks, total_invested, total_received FROM portfolio ORDER BY date DESC LIMIT 20", ttl=0)
        if not recent.empty:
            st.dataframe(recent, use_container_width=True, hide_index=True)
        else:
            st.caption("No records found in the ledger.")
    except Exception as e:
        st.error(f"Failed to fetch recent entries: {e}")
