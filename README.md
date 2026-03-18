# My_Nepse_Diary
# 🦅 NEPSE Terminal Pro (V2)

An enterprise-grade, localized Bloomberg Terminal tailored specifically for the Nepal Stock Exchange (NEPSE). 

This project is a massive architectural upgrade from the original V1 script. It transitions from a basic local script into a modular, cloud-database-backed, multi-page Streamlit application. **This V2 platform was co-architected and built by [Your Name] in collaboration with Google's Gemini AI.**

---

## 🚀 The Evolution (V1 vs V2)

The original project was a great proof-of-concept, but it lacked persistence and advanced analytics. This upgraded version introduces:
- **Cloud Database Integration:** Migrated from local memory to a live **Neon Serverless PostgreSQL** database.
- **Autonomous Syncing:** Uses a headless API scraper run via GitHub Actions to update market data daily, completely hands-free.
- **Multi-Model AI Consensus:** Integrates Google Gemini, OpenAI ChatGPT, and xAI Grok to analyze your live portfolio data.
- **Advanced Math Engines:** Real-time T+2 settlement tracking, dynamic WACC averaging, and exact NEPSE fee/tax deduction simulations.

---

## 🏗️ System Architecture

The application is built on a modern, decoupled data pipeline:

1. **Frontend / UI:** Streamlit (`app.py` as the main router, with distinct modules in the `/Tabs` and `/SubTabs` directories).
2. **Database:** Neon PostgreSQL (handles relational state, audit logs, and wealth snapshots).
3. **Automated Cron Job:** A GitHub Action triggers `Utility/Sync.py` daily at 3:15 PM NST to scrape Chukul/NEPSE APIs, update the `cache` table, and push a notification via Telegram.
4. **AI Processing:** API connections to multiple LLMs using system prompts injected with real-time portfolio data.

---

## 🗄️ Database Schema

The system relies on six core tables to manage state and historical data:

| Table Name | Purpose |
| :--- | :--- |
| `portfolio` | Tracks active and historical trades (Buy/Sell, Quantity, Price, WACC). |
| `tms_trx` | Logs cash deposits, withdrawals, and collateral adjustments to calculate Buying Power. |
| `cache` | The daily market snapshot. Holds the Last Traded Price (LTP) and % changes for all NEPSE tickers. |
| `wealth` | A daily historical snapshot of total account value to render the "Wealth Trajectory" drawdown charts. |
| `trading_journal` | A psychological log of trade setups, emotional states, and post-trade reflections. |
| `audit_log` | A tamper-proof system log recording data edits, sync successes, and API errors. |

---

## 🧰 Core Modules

- **Dashboard & TMS:** Real-time net worth tracking and precise broker buying power math.
- **Trade Simulation:** Pre-trade calculators. Test WACC averaging before buying, or calculate exact net payouts (after broker commissions, SEBON fees, DP charges, and CGT) before selling.
- **Risk & Journal:** Incorporates the Kelly Criterion for dynamic position sizing based on hard stop-losses and account risk percentages.
- **AI Market Analyst:** Chat directly with your portfolio using Gemini 2.0 Flash, GPT-4o, or Grok.
- **God-Mode Admin Panel:** A secure, role-based UI to visually edit or run raw SQL commands directly on the database.

---

## ⚙️ Installation & Setup

**1. Clone the repository**
```bash
git clone https://github.com/DayaSah/My_Nepse_Diary.git(https://github.com/DayaSah/My_Nepse_Diary.git)
cd My_Nepse_Diary
