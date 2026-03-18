import streamlit as st
import pandas as pd
import plotly.express as px

def render_page(role):
    # Initialize the Neon database connection
    conn = st.connection("neon", type="sql")
    
    # 1. Load All Data using fast SQL Queries
    try:
        port = conn.query("SELECT * FROM portfolio",ttl=0)
        cache = conn.query("SELECT * FROM cache",ttl=3600)
        hist = conn.query("SELECT * FROM history",ttl=0)
        wl = conn.query("SELECT * FROM watchlist",ttl=0)
    except Exception as e:
        st.error(f"Database connection error: {e}")
        port = pd.DataFrame()
        cache = pd.DataFrame()
        hist = pd.DataFrame()
        wl = pd.DataFrame()

    # 2. Merge Portfolio with Market Data Cache
    if not port.empty and not cache.empty:
        df = pd.merge(port, cache, left_on="symbol", right_on="symbol", how="left").fillna(0)
    else:
        df = port.copy() if not port.empty else pd.DataFrame()
        if not df.empty: 
            df["ltp"] = 0

    last_up = cache["lastupdated"].iloc[0] if not cache.empty and "lastupdated" in cache.columns else "Never"
    
    st.title("📊 Market Dashboard")
    st.caption(f"Last Updated: {last_up} (Nepal Time)")

    if df.empty:
        st.info("Portfolio is empty. Go to the 'Add Trade' tab to start logging trades.")
    else:
        # ==========================================
        # METRIC CALCULATIONS
        # ==========================================
        
        # A. Current Holdings (Unrealized)
        curr_inv = float(df["total_cost"].sum()) if "total_cost" in df.columns else 0.0
        curr_val = 0
        day_change = 0
        alerts = []
        sector_data = {}
        
        for _, row in df.iterrows():
            ltp = float(row.get("ltp", 0))
            if ltp == 0: 
                ltp = float(row.get("wacc", 0))
            
            # Use lowercase for standard PostgreSQL column returns
            units = float(row.get("units", 0))
            val = units * ltp
            d_chg = units * float(row.get("change", 0))
            
            curr_val += val
            day_change += d_chg
            
            # Sector
            sec = row.get("sector", "Unclassified")
            sector_data[sec] = sector_data.get(sec, 0) + val
            
            # Stop Loss Logic
            sl = float(row.get("stop_loss", 0))
            if sl > 0 and ltp < sl:
                alerts.append(f"⚠️ **STOP LOSS HIT:** {row['symbol']} @ Rs {ltp} (SL: {sl})")
        
        curr_pl = curr_val - curr_inv
        curr_ret = (curr_pl / curr_inv * 100) if curr_inv else 0

        # B. Closed Holdings (Realized)
        realized_pl = 0
        realized_inv = 0
        realized_recv = 0
        
        if not hist.empty:
            realized_pl = float(hist["net_pl"].sum()) if "net_pl" in hist.columns else 0
            if "invested_amount" in hist.columns:
                realized_inv = float(hist["invested_amount"].sum())
                realized_recv = float(hist["received_amount"].sum())
            elif "buy_price" in hist.columns:
                realized_inv = float((hist["units"] * hist["buy_price"]).sum())
                realized_recv = float((hist["units"] * hist["sell_price"]).sum())

        realized_ret = (realized_pl / realized_inv * 100) if realized_inv > 0 else 0

        # C. Lifetime Stats
        lifetime_invested = curr_inv + realized_inv
        lifetime_received = realized_recv 
        net_exposure = lifetime_received - lifetime_invested 

        # ==========================================
        # DASHBOARD UI RENDER
        # ==========================================
        
        # Row 1: Snapshot
        st.markdown("### 🏦 Net Worth Snapshot")
        m1, m2, m3 = st.columns(3)
        m1.metric("Current Portfolio Value", f"Rs {curr_val:,.0f}")
        m2.metric("Total Active Investment", f"Rs {curr_inv:,.0f}")
        m3.metric("Today's Change", f"Rs {day_change:,.0f}", delta=f"{day_change:,.0f}")
        
        st.markdown("---")
        
        # Row 2: P/L Analysis
        st.markdown("### ⚖️ Profit/Loss Analysis")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Net Realized P/L", f"Rs {realized_pl:,.0f}", delta=f"{realized_ret:.2f}%")
        c2.metric("📈 Unrealized P/L", f"Rs {curr_pl:,.0f}", delta=f"{curr_ret:.2f}%")
        c3.metric("🏆 Lifetime P/L", f"Rs {realized_pl + curr_pl:,.0f}", help="Realized + Unrealized")
        
        # Best Winner Logic
        best_stock = "-"
        if not hist.empty and "net_pl" in hist.columns:
            # Find row with max net_pl
            best_trade = hist.loc[hist["net_pl"].idxmax()]
            best_stock = f"{best_trade['symbol']} (+{best_trade['net_pl']:.0f})"
        c4.metric("🥇 Best Trade", best_stock)

        st.markdown("---")

        # Row 3: Investment Snapshot
        st.markdown("### 💼 Investment Cycle (Lifetime)")
        i1, i2, i3, i4 = st.columns(4)
        
        i1.metric("Total Capital Deployed", f"Rs {lifetime_invested:,.0f}", 
                  help="Sum of Cost of Sold Stocks + Cost of Held Stocks.")
        i2.metric("Total Cash Recycled", f"Rs {lifetime_received:,.0f}", 
                  help="Total money returned to bank from sales.")
        i3.metric("Net Cash Flow", f"Rs {net_exposure:,.0f}", 
                  help="Total Received - Total Invested. Negative means this amount is currently 'at risk'.")
        
        turnover = (realized_inv / curr_inv * 100) if curr_inv else 0
        i4.metric("Capital Turnover", f"{turnover:.1f}%", help="How many times you have rotated your capital.")

        st.markdown("---")
        
        # Row 4: Visuals & Alerts
        col_chart, col_alert = st.columns([2, 1])
        
        with col_chart:
            st.subheader("Sector Allocation")
            sec_df = pd.DataFrame(list(sector_data.items()), columns=["Sector", "Value"])
            if not sec_df.empty:
                fig = px.pie(sec_df, values="Value", names="Sector", hole=0.4)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No sector data available.")
                
        with col_alert:
            st.subheader("📢 Alerts")
            if alerts:
                for a in alerts: st.error(a)
            else:
                st.info("System Normal.")
                
            # Watchlist Hit Logic
            if not wl.empty and not cache.empty:
                wl_m = pd.merge(wl, cache, on="symbol", how="left")
                if "target" in wl_m.columns and "ltp" in wl_m.columns:
                    hits = wl_m[(wl_m["ltp"] <= wl_m["target"]) & (wl_m["ltp"] > 0)]
                    if not hits.empty:
                        st.markdown("---")
                        for _, h in hits.iterrows():
                            st.success(f"🎯 **BUY TARGET HIT:** {h['symbol']} @ Rs {h['ltp']}")
