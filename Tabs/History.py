import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import date, timedelta

def render_page(role):
    st.title("🏛️ Trade History & Settlement")
    st.caption("Track your closed positions, exact realized P/L, and T+2 settlement status.")

    conn = st.connection("neon", type="sql")

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
        # Sort ASCENDING first for accurate chronological FIFO calculation
        port_df = conn.query("SELECT * FROM portfolio ORDER BY date ASC, transaction_type DESC", ttl=0)
        port_df.columns = [c.lower() for c in port_df.columns]
        
        if 'remarks' not in port_df.columns: port_df['remarks'] = "-"
        if 'total_invested' not in port_df.columns: port_df['total_invested'] = port_df['qty'] * port_df['price']
        if 'total_received' not in port_df.columns: port_df['total_received'] = port_df['qty'] * port_df['price']
            
    except Exception as e:
        st.error("⚠️ Failed to load trade history.")
        log_system_error(f"History Load Error: {e}")
        return

    if port_df.empty:
        st.info("No trades found. Go to 'Add Transaction' to log your first trade.")
        return

    # --- Data Wrangling ---
    port_df['date'] = pd.to_datetime(port_df['date'])
    port_df['qty'] = pd.to_numeric(port_df['qty'])
    port_df['price'] = pd.to_numeric(port_df['price'])
    port_df['total_invested'] = pd.to_numeric(port_df['total_invested']).fillna(0)
    port_df['total_received'] = pd.to_numeric(port_df['total_received']).fillna(0)
    
    # Calculate T+2 Settlement Status
    cutoff_date = pd.to_datetime(date.today() - timedelta(days=3))
    port_df['status'] = port_df['date'].apply(lambda x: "Settled ✅" if x <= cutoff_date else "Unsettled ⏳")

    # --- PERFECT FIFO REALIZED P/L ENGINE ---
    inventory = {} # Dictionary to hold FIFO queues per symbol
    sell_records = []

    for index, row in port_df.iterrows():
        sym = row['symbol'].upper()
        if sym not in inventory: inventory[sym] = []
        
        if row['transaction_type'].upper() == 'BUY':
            # Calculate exact net cost per share for this specific batch
            unit_cost = row['total_invested'] / row['qty'] if row['qty'] > 0 else 0
            inventory[sym].append({'qty': row['qty'], 'unit_cost': unit_cost})
            
        elif row['transaction_type'].upper() == 'SELL':
            sell_qty = row['qty']
            cost_basis = 0.0
            
            # FIFO Extraction: Pop oldest shares first to determine exact cost basis
            rem = sell_qty
            while rem > 0 and inventory[sym]:
                if inventory[sym][0]['qty'] <= rem:
                    batch_qty = inventory[sym][0]['qty']
                    cost_basis += batch_qty * inventory[sym][0]['unit_cost']
                    rem -= batch_qty
                    inventory[sym].pop(0)
                else:
                    cost_basis += rem * inventory[sym][0]['unit_cost']
                    inventory[sym][0]['qty'] -= rem
                    rem = 0
            
            # Because total_received is already net of taxes/fees, Net P/L is simple subtraction
            net_profit = row['total_received'] - cost_basis
            roi = (net_profit / cost_basis * 100) if cost_basis > 0 else 0
            
            sell_records.append({
                'date': row['date'],
                'symbol': sym,
                'qty': sell_qty,
                'sell_price': row['price'],
                'total_received': row['total_received'],
                'cost_basis': cost_basis,
                'net_pl': net_profit,
                'roi_pct': roi,
                'remarks': row['remarks']
            })

    # Create Sells DataFrame and sort DESCENDING for UI display
    sells_df = pd.DataFrame(sell_records).sort_values(by='date', ascending=False) if sell_records else pd.DataFrame()
    
    # Sort port_df DESCENDING for the Ledger and Settlement UI tabs
    port_df = port_df.sort_values(by='date', ascending=False)

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
            
            # NEW: Uses exact total_invested and total_received instead of qty * price
            pending_buys = unsettled_df[unsettled_df['transaction_type'].str.upper() == 'BUY']
            pending_sells = unsettled_df[unsettled_df['transaction_type'].str.upper() == 'SELL']
            
            cash_needed = pending_buys['total_invested'].sum()
            cash_incoming = pending_sells['total_received'].sum()
            
            c1, c2 = st.columns(2)
            c1.metric("💸 Cash Payable to Broker", f"Rs {cash_needed:,.2f}", help="Exact cash required including commissions & SEBON.")
            c2.metric("💰 Cash Receivable from Broker", f"Rs {cash_incoming:,.2f}", help="Exact cash incoming after CGT & commissions.")
            
            st.divider()
            display_unsettled = unsettled_df[['date', 'symbol', 'transaction_type', 'qty', 'price', 'remarks']].copy()
            display_unsettled['date'] = display_unsettled['date'].dt.strftime('%Y-%m-%d')
            st.dataframe(display_unsettled, use_container_width=True, hide_index=True)

    # --- TAB 2: REALIZED P/L (CLOSED TRADES) ---
    with tabs[1]:
        if sells_df.empty:
            st.info("You haven't sold any stocks yet. No realized P/L to display.")
        else:
            total_net_pl = sells_df['net_pl'].sum()
            win_rate = (len(sells_df[sells_df['net_pl'] > 0]) / len(sells_df)) * 100
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Realized Net Profit", f"Rs {total_net_pl:,.2f}")
            c2.metric("Total Trades Closed", f"{len(sells_df)} Sells")
            c3.metric("Win Rate", f"{win_rate:.1f}%", help="Percentage of sell trades that were profitable.")
            
            st.markdown("#### Closed Trades Breakdown")
            
            display_sells = sells_df[['date', 'symbol', 'qty', 'sell_price', 'cost_basis', 'total_received', 'net_pl', 'roi_pct', 'remarks']].copy()
            display_sells['date'] = display_sells['date'].dt.strftime('%Y-%m-%d')
            
            display_sells.rename(columns={
                'date': 'Sell Date', 'symbol': 'Symbol', 'qty': 'Qty', 'sell_price': 'Sell Price',
                'cost_basis': 'FIFO Cost Basis', 'total_received': 'Net Cash In', 'net_pl': 'Net P/L (Rs)', 
                'roi_pct': 'ROI %', 'remarks': 'Remarks'
            }, inplace=True)
            
            # Styling for Profit (Green) and Loss (Red)
            def color_pl(val):
                color = 'rgba(0,255,0,0.2)' if val > 0 else 'rgba(255,0,0,0.2)' if val < 0 else ''
                return f'background-color: {color}'

            styled_sells = display_sells.style.map(color_pl, subset=['Net P/L (Rs)', 'ROI %']).format({
                'FIFO Cost Basis': '{:,.2f}',
                'Net Cash In': '{:,.2f}',
                'Net P/L (Rs)': '{:,.2f}',
                'ROI %': '{:.2f}%'
            })
            
            st.dataframe(styled_sells, use_container_width=True, hide_index=True)

    # --- TAB 3: COMPLETE LEDGER ---
    with tabs[2]:
        st.markdown("#### Master Transaction Ledger")
        display_all = port_df[['date', 'symbol', 'transaction_type', 'qty', 'price', 'total_invested', 'total_received', 'status', 'remarks']].copy()
        display_all['date'] = display_all['date'].dt.strftime('%Y-%m-%d')
        
        display_all.columns = [c.replace('_', ' ').title() for c in display_all.columns]
        
        st.dataframe(display_all, use_container_width=True, hide_index=True, height=500)
