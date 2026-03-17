import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import date, timedelta

def render_page(role):
    st.title("🏛️ Trade History & Settlement")
    st.caption("Track your closed positions, realized P/L, and T+2 settlement status.")

    # Initialize Database Connection
    conn = st.connection("neon", type="sql")

    # ==========================================
    # 0. SYSTEM LOGGING UTILITY
    # ==========================================
    def log_system_error(error_msg):
        """Silently logs errors to the audit_log table."""
        try:
            with conn.session as s:
                sql = text("INSERT INTO audit_log (action, details) VALUES ('SYSTEM_ERROR', :msg)")
                s.execute(sql, {"msg": str(error_msg)})
                s.commit()
        except:
            pass

    # ==========================================
    # 1. FETCH AND PROCESS DATA
    # ==========================================
    try:
        port_df = conn.query("SELECT * FROM portfolio ORDER BY date DESC")
        port_df.columns = [c.lower() for c in port_df.columns]
        
        # Ensure remarks column exists in pandas even if DB is lagging
        if 'remarks' not in port_df.columns:
            port_df['remarks'] = "-"
            
    except Exception as e:
        st.error("⚠️ Failed to load trade history.")
        log_system_error(f"History Load Error: {e}")
        port_df = pd.DataFrame()

    if port_df.empty:
        st.info("No trades found. Go to 'Add Transaction' to log your first trade.")
        return

    # --- Data Wrangling ---
    port_df['date'] = pd.to_datetime(port_df['date'])
    port_df['qty'] = pd.to_numeric(port_df['qty'])
    port_df['price'] = pd.to_numeric(port_df['price'])
    
    # Calculate T+2 Settlement Status
    # Using 3 days as a safe buffer for NEPSE T+2 (excluding complex holiday logic for now)
    cutoff_date = pd.to_datetime(date.today() - timedelta(days=3))
    
    port_df['status'] = port_df['date'].apply(
        lambda x: "Settled ✅" if x <= cutoff_date else "Unsettled ⏳"
    )

    # --- Realized P/L Calculation Engine ---
    buys = port_df[port_df['transaction_type'].str.upper() == 'BUY']
    sells = port_df[port_df['transaction_type'].str.upper() == 'SELL'].copy()

    # Calculate WACC per symbol from Buys
    wacc_dict = {}
    if not buys.empty:
        for sym, group in buys.groupby('symbol'):
            total_cost = (group['qty'] * group['price']).sum()
            total_qty = group['qty'].sum()
            wacc_dict[sym] = total_cost / total_qty if total_qty > 0 else 0

    # Match Sells against WACC to find Profit
    if not sells.empty:
        sells['wacc'] = sells['symbol'].map(wacc_dict).fillna(0)
        sells['gross_revenue'] = sells['qty'] * sells['price']
        sells['cost_basis'] = sells['qty'] * sells['wacc']
        
        sells['gross_pl'] = sells['gross_revenue'] - sells['cost_basis']
        
        # Pro Feature: Estimate Taxes & Fees on closed trades
        # 0.4% approx broker fee + 25 DP + 5% CGT on profits
        sells['est_fees'] = (sells['gross_revenue'] * 0.004) + 25
        sells['est_cgt'] = sells['gross_pl'].apply(lambda x: x * 0.05 if x > 0 else 0)
        
        sells['net_pl'] = sells['gross_pl'] - sells['est_fees'] - sells['est_cgt']
        sells['roi_pct'] = (sells['net_pl'] / sells['cost_basis']) * 100

    # ==========================================
    # 2. UI TABS SETUP
    # ==========================================
    tabs = st.tabs(["⏳ Pending Settlements", "🏆 Realized P/L", "📜 Complete Ledger"])

    # --- TAB 1: PENDING SETTLEMENTS (T+2) ---
    with tabs[0]:
        unsettled_df = port_df[port_df['status'] == "Unsettled ⏳"].copy()
        
        if unsettled_df.empty:
            st.success("🎉 All your trades are fully settled! No pending deliveries or cash receivables.")
        else:
            st.warning(f"You have {len(unsettled_df)} unsettled transactions in the clearing pipeline.")
            
            # Summarize cash flows tied up in settlement
            pending_buys = unsettled_df[unsettled_df['transaction_type'] == 'BUY']
            pending_sells = unsettled_df[unsettled_df['transaction_type'] == 'SELL']
            
            cash_needed = (pending_buys['qty'] * pending_buys['price']).sum()
            cash_incoming = (pending_sells['qty'] * pending_sells['price']).sum()
            
            c1, c2 = st.columns(2)
            c1.metric("💸 Cash Required (Payable to Broker)", f"Rs {cash_needed:,.2f}", help="Money you need to pay for recent buys.")
            c2.metric("💰 Cash Incoming (Receivable from Broker)", f"Rs {cash_incoming:,.2f}", help="Money you will receive for recent sells.")
            
            st.divider()
            
            display_unsettled = unsettled_df[['date', 'symbol', 'transaction_type', 'qty', 'price', 'remarks']].copy()
            display_unsettled['date'] = display_unsettled['date'].dt.strftime('%Y-%m-%d')
            display_unsettled.rename(columns={'transaction_type': 'Type', 'remarks': 'Remarks'}, inplace=True)
            
            st.dataframe(display_unsettled, use_container_width=True, hide_index=True)

    # --- TAB 2: REALIZED P/L (CLOSED TRADES) ---
    with tabs[1]:
        if sells.empty:
            st.info("You haven't sold any stocks yet. No realized P/L to display.")
        else:
            total_net_pl = sells['net_pl'].sum()
            win_rate = (len(sells[sells['net_pl'] > 0]) / len(sells)) * 100
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Realized Net Profit", f"Rs {total_net_pl:,.2f}")
            c2.metric("Total Trades Closed", f"{len(sells)} Sells")
            c3.metric("Win Rate", f"{win_rate:.1f}%", help="Percentage of sell trades that were profitable.")
            
            st.markdown("#### Closed Trades Breakdown")
            display_sells = sells[['date', 'symbol', 'qty', 'price', 'wacc', 'est_cgt', 'net_pl', 'roi_pct', 'remarks']].copy()
            display_sells['date'] = display_sells['date'].dt.strftime('%Y-%m-%d')
            
            display_sells.rename(columns={
                'date': 'Sell Date', 'symbol': 'Symbol', 'qty': 'Qty', 'price': 'Sell Price',
                'wacc': 'Avg Buy Cost', 'est_cgt': 'Est. Tax (5%)', 'net_pl': 'Net P/L (Rs)', 
                'roi_pct': 'ROI %', 'remarks': 'Sell Remarks'
            }, inplace=True)
            
            st.dataframe(
                display_sells,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Net P/L (Rs)": st.column_config.NumberColumn(format="%.2f"),
                    "ROI %": st.column_config.NumberColumn(format="%.2f%%"),
                    "Avg Buy Cost": st.column_config.NumberColumn(format="%.2f"),
                }
            )

    # --- TAB 3: COMPLETE LEDGER ---
    with tabs[2]:
        st.markdown("#### Master Transaction Ledger")
        display_all = port_df[['date', 'symbol', 'transaction_type', 'qty', 'price', 'status', 'remarks']].copy()
        display_all['date'] = display_all['date'].dt.strftime('%Y-%m-%d')
        
        # Clean up column names for display
        display_all.columns = [c.replace('_', ' ').title() for c in display_all.columns]
        
        st.dataframe(
            display_all,
            use_container_width=True,
            hide_index=True,
            height=500
        )
