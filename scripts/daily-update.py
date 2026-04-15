#!/usr/bin/env python3
"""
Daily price update (runs via GitHub Action).

Fetches live prices, recalculates portfolio values, and updates YTD:
  YTD_live = (1 + sync_ytd/100) × (value_today / sync_value) - 1

The sync baseline comes from the last time the user ran sync.py locally.
"""
import json, os, sys
from datetime import datetime, timezone

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT_DIR)

try:
    import yfinance as yf
except ImportError:
    os.system("pip install yfinance -q")
    import yfinance as yf

# Load current data
with open("portfolio-data.json") as f:
    data = json.load(f)

if "sync" not in data or "strategies" not in data:
    print("No sync data found. Run sync.py first.")
    sys.exit(1)

# Collect all tickers
YF_MAP = {
    "BRK-B": "BRK-B", "2330": "2330.TW", "WISE": "WISE.L",
    "CLNX": "CLNX.MC", "PRX": "PRX.AS", "EXO": "EXO.MI",
}

all_tickers = set()
for strat in data["strategies"].values():
    for p in strat["positions"]:
        all_tickers.add(YF_MAP.get(p["ticker"], p["ticker"]))

print(f"Fetching {len(all_tickers)} prices...")
dl = yf.download(list(all_tickers), period="1d", progress=False)
prices = {}
for t in all_tickers:
    try:
        close = dl["Close"][t].dropna()
        if len(close) > 0: prices[t] = float(close.iloc[-1])
    except: pass

fx_dl = yf.download(["EURUSD=X", "GBPUSD=X"], period="1d", progress=False)
eur_usd = float(fx_dl["Close"]["EURUSD=X"].dropna().iloc[-1]) if "EURUSD=X" in fx_dl["Close"] else 1.13
gbp_usd = float(fx_dl["Close"]["GBPUSD=X"].dropna().iloc[-1]) if "GBPUSD=X" in fx_dl["Close"] else 1.27
twd_usd = 1.0 / 32.0

print(f"Got {len(prices)} prices, EUR/USD={eur_usd:.4f}")

def price_usd(ticker, ccy):
    yf_t = YF_MAP.get(ticker, ticker)
    p = prices.get(yf_t)
    if p is None: return None
    if ccy == "EUR": return p * eur_usd
    if ccy == "GBP": return (p / 100) * gbp_usd
    if ccy == "TWD": return p * twd_usd
    return p

# Infer CCY from position data (stored tickers)
CCY_MAP = {"CLNX": "EUR", "PRX": "EUR", "EXO": "EUR", "WISE": "GBP", "2330": "TWD"}

# Update each strategy
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
data["updated"] = now

for strat_name, strat in data["strategies"].items():
    new_total = 0
    for pos in strat["positions"]:
        ccy = CCY_MAP.get(pos["ticker"], "USD")
        pu = price_usd(pos["ticker"], ccy)
        if pu is not None:
            pos["price"] = round(pu, 2)
            pos["mkt_value"] = round(pu * pos["qty"], 2)
        new_total += pos["mkt_value"]

    # Update weights
    for pos in strat["positions"]:
        pos["weight"] = round((pos["mkt_value"] / new_total) * 100, 1) if new_total > 0 else 0
    strat["positions"].sort(key=lambda x: x["weight"], reverse=True)
    strat["total_value"] = round(new_total, 2)

    # Calculate live YTD
    sync = data["sync"].get(strat_name, {})
    sync_value = sync.get("value", 0)
    sync_ytd = sync.get("ytd_at_sync", 0)

    if sync_value > 0:
        # YTD_live = (1 + sync_ytd/100) × (value_today / sync_value) - 1
        ytd_live = ((1 + sync_ytd / 100) * (new_total / sync_value) - 1) * 100
        strat["ytd_2026"] = round(ytd_live, 1)
    else:
        strat["ytd_2026"] = sync_ytd

    print(f"  {strat_name}: ${new_total:,.0f} | sync=${sync_value:,.0f} | sync_ytd={sync_ytd}% | live_ytd={strat.get('ytd_2026',0)}%")

# Update returns with live YTD
for strat_name in ["discretionary", "vc2", "vc2trend"]:
    if strat_name in data["strategies"] and strat_name in data.get("returns", {}):
        data["returns"][strat_name]["2026_ytd"] = data["strategies"][strat_name].get("ytd_2026", 0)

# S&P 500 live YTD
try:
    SP500_DEC31_2025 = 6845.5  # S&P 500 index close Dec 31, 2025 (fixed)
    sp_now_data = yf.download("^GSPC", period="1d", progress=False)
    sp_now = float(sp_now_data["Close"].iloc[-1])
    sp_ytd = round(((sp_now / SP500_DEC31_2025) - 1) * 100, 1)
    data["sp500_returns"]["2026_ytd"] = sp_ytd
    print(f"  S&P 500: YTD={sp_ytd}%")
except Exception as e:
    print(f"  S&P 500: error {e}")

# Update activity log
date_short = datetime.now(timezone.utc).strftime("%b %-d")
activity = data.get("activity", [])
# Replace or add today's price update entry
activity = [a for a in activity if not (a.get("date") == date_short and "Prices updated" in a.get("text", ""))]
activity.insert(0, {"date": date_short, "text": "Prices updated from market close"})
data["activity"] = activity[:5]

# Save
with open("portfolio-data.json", "w") as f:
    json.dump(data, f, indent=2)

print(f"\n✅ Updated {now}")
