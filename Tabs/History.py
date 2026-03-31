import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import date, timedelta

def render_page(role):
    st.title("🏛️ Trade History & Settlement")
    st.caption("Track closed positions, active open lots (Unrealized), and T+2 settlement.")

    conn = st.connection("neon", type="sql")

    def log_system_error(error_msg):
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
        
        # Fetch Live Prices for Unrealized P/L
        try:
            cache_df = conn.query("SELECT symbol, ltp FROM cache", ttl=0)
            ltp_dict = dict(zip(cache_df['symbol'].str.upper(), pd.to_numeric(cache_df['ltp'])))
        except:
            ltp_dict = {}

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

    # ==========================================
    # 2. PERFECT TAX-LOT FIFO ENGINE
    # ==========================================
    inventory = {} # Active holding queues per symbol
    realized_records = []
    
    for index, row in port_df.iterrows():
        sym = row['symbol'].upper()
        if sym not in inventory: inventory[sym] = []
        
        if row['transaction_type'].upper() == 'BUY':
            unit_cost = row['total_invested'] / row['qty'] if row['qty'] > 0 else 0
            inventory[sym].append({
                'qty': row['qty'], 
                'buy_rate': row['price'],
                'unit_cost': unit_cost, 
                'buy_date': row['date'],
                'buy_remark': row['remarks']
            })
            
        elif row['transaction_type'].upper() == 'SELL':
            sell_qty = row['qty']
            # Prorate the total received across the units sold in case they match multiple buys
            rec_per_unit = row['total_received'] / sell_qty if sell_qty > 0 else 0
            
            rem = sell_qty
            while rem > 0 and inventory[sym]:
                buy_lot = inventory[sym][0]
                
                if buy_lot['qty'] <= rem:
                    matched_qty = buy_lot['qty']
                    rem -= matched_qty
                    inventory[sym].pop(0) # Lot fully consumed
                else:
                    matched_qty = rem
                    buy_lot['qty'] -= rem
                    rem = 0
                
                # Math for this specific matched lot
                invested = matched_qty * buy_lot['unit_cost']
                received = matched_qty * rec_per_unit
                net_pl = received - invested
                roi = (net_pl / invested * 100) if invested > 0 else 0
                
                realized_records.append({
                    'Symbol': sym,
                    'Qty': matched_qty,
                    'Buy Date': buy_lot['buy_date'],
                    'Sell Date': row['date'],
                    'Buy Rate': buy_lot['buy_rate'],
                    'Sell Rate': row['price'],
                    'Total Invested': invested,
                    'Total Received': received,
                    'Net P/L': net_pl,
                    '%': roi,
                    'Buy Remark': buy_lot['buy_remark'],
                    'Sell Remark': row['remarks']
                })

    # Whatever is left in the inventory is "Unrealized"
    unrealized_records = []
    for sym, lots in inventory.items():
        for lot in lots:
            if lot['qty'] > 0:
                ltp = ltp_dict.get(sym, lot['unit_cost']) # Fallback to cost if no LTP
                current_val = lot['qty'] * ltp
                invested = lot['qty'] * lot['unit_cost']
                net_pl = current_val - invested
                roi = (net_pl / invested * 100) if invested > 0 else 0
                
                unrealized_records.append({
                    'Symbol': sym,
                    'Qty': lot['qty'],
                    'Buy Date': lot['buy_date'],
                    'Buy Rate': lot['buy_rate'],
                    'LTP': ltp,
                    'Total Invested': invested,
                    'Current Value': current_val,
                    'Net P/L': net_pl,
                    '%': roi,
                    'Buy Remark': lot['buy_remark']
                })

    # Build DataFrames
    realized_df = pd.DataFrame(realized_records).sort_values(by='Sell Date', ascending=False) if realized_records else pd.DataFrame()
    unrealized_df = pd.DataFrame(unrealized_records).sort_values(by='Buy Date', ascending=False) if unrealized_records else pd.DataFrame()
    port_df = port_df.sort_values(by='date', ascending=False) # For Master Ledger

    # Format Dates for Display
    if not realized_df.empty:
        realized_df['Buy Date'] = realized_df['Buy Date'].dt.strftime('%Y-%m-%d')
        realized_df['Sell Date'] = realized_df['Sell Date'].dt.strftime('%Y-%m-%d')
    if not unrealized_df.empty:
        unrealized_df['Buy Date'] = unrealized_df['Buy Date'].dt.strftime('%Y-%m-%d')

    # ==========================================
    # 3. UI TABS SETUP
    # ==========================================
    tabs = st.tabs(["🏆 Realized History", "📈 Unrealized History", "⏳ Settlements", "📜 Ledger"])

    def color_pl(val):
        color = 'rgba(0,255,0,0.2)' if val > 0 else 'rgba(255,0,0,0.2)' if val < 0 else ''
        return f'background-color: {color}'

    # --- TAB 1: REALISED HISTORY ---
with tabs[0]:
    if realized_df.empty:
        st.info("No closed trades yet. Sell a stock to see Realized P/L.")
    else:
        # 1. Top Level Metrics
        total_net_pl = realized_df['Net P/L'].sum()
        win_rate = (len(realized_df[realized_df['Net P/L'] > 0]) / len(realized_df)) * 100
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Realized Profit", f"Rs {total_net_pl:,.2f}")
        c2.metric("Tax Lots Closed", f"{len(realized_df)}")
        c3.metric("Trade Win Rate", f"{win_rate:.1f}%")
        
        st.divider()

        # --- 2. Aggregated Summary View (By Symbol) ---
        st.markdown("#### 📊 Aggregated Realized Summary (By Symbol)")
        
        # Grouping realized trades to see total performance per stock
        agg_realized = realized_df.groupby('Symbol').agg(
            Total_Qty=('Qty', 'sum'),
            Total_Invested=('Total Invested', 'sum'),
            Total_Received=('Total Received', 'sum'),
            Net_PL=('Net P/L', 'sum')
        ).reset_index()
        
        # Calculate Weighted Averages for the summary
        agg_realized['Avg Buy'] = agg_realized['Total_Invested'] / agg_realized['Total_Qty']
        agg_realized['Avg Sell'] = agg_realized['Total_Received'] / agg_realized['Total_Qty']
        agg_realized['Total ROI %'] = (agg_realized['Net_PL'] / agg_realized['Total_Invested']) * 100
        
        # Reorder columns for better readability
        agg_realized = agg_realized[['Symbol', 'Total_Qty', 'Avg Buy', 'Avg Sell', 'Total_Invested', 'Total_Received', 'Net_PL', 'Total_ROI %']]

        styled_agg_realized = agg_realized.style.map(color_pl, subset=['Net_PL', 'Total_ROI %']).format({
            'Total_Qty': '{:,.0f}', 
            'Avg Buy': '{:,.2f}', 
            'Avg Sell': '{:,.2f}',
            'Total_Invested': '{:,.2f}', 
            'Total_Received': '{:,.2f}',
            'Net_PL': '{:,.2f}', 
            'Total_ROI %': '{:.2f}%'
        })
        st.dataframe(styled_agg_realized, use_container_width=True, hide_index=True)

        st.divider()

        # --- 3. Detailed Tax-Lot View ---
        st.markdown("#### 🔬 Detailed Closed Tax-Lots")
        styled_realized = realized_df.style.map(color_pl, subset=['Net P/L', '%']).format({
            'Buy Rate': '{:,.2f}', 
            'Sell Rate': '{:,.2f}',
            'Total Invested': '{:,.2f}', 
            'Total Received': '{:,.2f}',
            'Net P/L': '{:,.2f}', 
            '%': '{:.2f}%'
        })
        st.dataframe(styled_realized, use_container_width=True, hide_index=True)

    # --- TAB 2: UNREALISED HISTORY ---
    with tabs[1]:
        if unrealized_df.empty:
            st.info("Your portfolio is empty. Buy some stocks to see open positions here.")
        else:
            total_unreal_pl = unrealized_df['Net P/L'].sum()
            total_open_inv = unrealized_df['Total Invested'].sum()
            unreal_roi = (total_unreal_pl / total_open_inv * 100) if total_open_inv > 0 else 0
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Open Invested Capital", f"Rs {total_open_inv:,.2f}")
            c2.metric("Total Unrealized P/L", f"Rs {total_unreal_pl:,.2f}", f"{unreal_roi:.2f}%")
            c3.metric("Active Lots", f"{len(unrealized_df)}")
            
            st.divider()
            
            # --- NEW: Aggregated Summary View ---
            st.markdown("#### 📊 Aggregated Positions (By Symbol)")
            
            agg_df = unrealized_df.groupby('Symbol').agg(
                Total_Qty=('Qty', 'sum'),
                Total_Invested=('Total Invested', 'sum'),
                Current_Value=('Current Value', 'sum'),
                Net_PL=('Net P/L', 'sum'),
                LTP=('LTP', 'first') # LTP is same for all lots of a symbol
            ).reset_index()
            
            agg_df['WACC'] = agg_df['Total_Invested'] / agg_df['Total_Qty']
            agg_df['ROI %'] = (agg_df['Net_PL'] / agg_df['Total_Invested']) * 100
            
            styled_agg = agg_df.style.map(color_pl, subset=['Net_PL', 'ROI %']).format({
                'Total_Invested': '{:,.2f}', 'Current_Value': '{:,.2f}',
                'Net_PL': '{:,.2f}', 'ROI %': '{:.2f}%', 'WACC': '{:.2f}', 'LTP': '{:.2f}'
            })
            st.dataframe(styled_agg, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # --- Detailed Tax-Lot View (Your Original Code) ---
            st.markdown("#### 🔬 Detailed Tax-Lot Breakdown")
            styled_unrealized = unrealized_df.style.map(color_pl, subset=['Net P/L', '%']).format({
                'Buy Rate': '{:,.2f}', 'LTP': '{:,.2f}',
                'Total Invested': '{:,.2f}', 'Current Value': '{:,.2f}',
                'Net P/L': '{:,.2f}', '%': '{:.2f}%'
            })
            st.dataframe(styled_unrealized, use_container_width=True, hide_index=True)

    # --- TAB 3: PENDING SETTLEMENTS ---
    with tabs[2]:
        unsettled_df = port_df[port_df['status'] == "Unsettled ⏳"].copy()
        
        if unsettled_df.empty:
            st.success("🎉 All trades fully settled! No pending deliveries or cash receivables.")
        else:
            pending_buys = unsettled_df[unsettled_df['transaction_type'].str.upper() == 'BUY']
            pending_sells = unsettled_df[unsettled_df['transaction_type'].str.upper() == 'SELL']
            
            c1, c2 = st.columns(2)
            c1.metric("💸 Cash Payable to Broker", f"Rs {pending_buys['total_invested'].sum():,.2f}")
            c2.metric("💰 Cash Receivable from Broker", f"Rs {pending_sells['total_received'].sum():,.2f}")
            
            display_unsettled = unsettled_df[['date', 'symbol', 'transaction_type', 'qty', 'price', 'remarks']].copy()
            display_unsettled['date'] = display_unsettled['date'].dt.strftime('%Y-%m-%d')
            st.dataframe(display_unsettled, use_container_width=True, hide_index=True)

    # --- TAB 4: COMPLETE LEDGER ---
    with tabs[3]:
        st.markdown("#### Master Raw Ledger")
        display_all = port_df[['date', 'symbol', 'transaction_type', 'qty', 'price', 'total_invested', 'total_received', 'status', 'remarks']].copy()
        display_all['date'] = display_all['date'].dt.strftime('%Y-%m-%d')
        display_all.columns = [c.replace('_', ' ').title() for c in display_all.columns]
        st.dataframe(display_all, use_container_width=True, hide_index=True, height=500)
