#!/usr/bin/env python3
"""
Fetches live prices for all portfolio positions and generates portfolio-data.json.
Runs daily via GitHub Actions.
"""
import json, os, sys
from datetime import datetime

try:
    import yfinance as yf
except ImportError:
    os.system("pip install yfinance -q")
    import yfinance as yf

# Load positions
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

with open(os.path.join(ROOT_DIR, "portfolio-positions.json")) as f:
    positions = json.load(f)

# Map tickers to yfinance format
YF_MAP = {
    "BRK-B": "BRK-B",
    "2330": "2330.TW",
    "WISE": "WISE.L",
    "CLNX": "CLNX.MC",
    "PRX": "PRX.AS",
    "EXO": "EXO.MI",
}

# Collect all tickers
all_tickers = set()
for strat in positions.values():
    for p in strat:
        t = p["ticker"]
        yf_t = YF_MAP.get(t, t)
        all_tickers.add(yf_t)

print(f"Fetching {len(all_tickers)} tickers...")

# Fetch all prices in one batch
data = yf.download(list(all_tickers), period="1d", progress=False)
if hasattr(data, 'xs'):
    # Multi-ticker format
    prices = {}
    for t in all_tickers:
        try:
            close = data["Close"][t].dropna()
            if len(close) > 0:
                prices[t] = float(close.iloc[-1])
        except:
            pass
else:
    # Single ticker fallback
    prices = {}

# Also get FX rates
fx_data = yf.download(["EURUSD=X", "GBPUSD=X", "TWDUSD=X"], period="1d", progress=False)
fx = {}
for pair in ["EURUSD=X", "GBPUSD=X", "TWDUSD=X"]:
    try:
        close = fx_data["Close"][pair].dropna()
        if len(close) > 0:
            fx[pair] = float(close.iloc[-1])
    except:
        pass

eur_usd = fx.get("EURUSD=X", 1.13)
gbp_usd = fx.get("GBPUSD=X", 1.27)
twd_usd = 1.0 / 32.0  # approximate

print(f"Got {len(prices)} prices, EUR/USD={eur_usd:.4f}")

# Build portfolio data
def get_price_usd(ticker, ccy):
    yf_t = YF_MAP.get(ticker, ticker)
    price_local = prices.get(yf_t)
    if price_local is None:
        return None
    if ccy == "EUR":
        return price_local * eur_usd
    elif ccy == "GBP":
        # WISE.L and other LSE stocks are quoted in pence (GBx), not pounds
        return (price_local / 100) * gbp_usd
    elif ccy == "TWD":
        return price_local * twd_usd
    return price_local

output = {"updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "strategies": {}}

for strat_name, strat_positions in positions.items():
    strat_data = {"positions": [], "total_value": 0, "total_cost": 0}

    for p in strat_positions:
        price_usd = get_price_usd(p["ticker"], p["ccy"])
        if price_usd is None:
            print(f"  WARNING: no price for {p['ticker']}")
            price_usd = p["avg_cost"]  # fallback to cost

        # Cost in USD
        if p["ccy"] == "EUR":
            cost_usd = p["avg_cost"] * eur_usd
        elif p["ccy"] == "GBP":
            cost_usd = p["avg_cost"] * gbp_usd
        elif p["ccy"] == "TWD":
            cost_usd = p["avg_cost"] * twd_usd
        else:
            cost_usd = p["avg_cost"]

        mkt_value = price_usd * p["qty"]
        cost_basis = cost_usd * p["qty"]
        pnl_pct = ((price_usd / cost_usd) - 1) * 100 if cost_usd > 0 else 0

        strat_data["positions"].append({
            "ticker": p["ticker"],
            "qty": p["qty"],
            "price": round(price_usd, 2),
            "mkt_value": round(mkt_value, 2),
            "cost_basis": round(cost_basis, 2),
            "pnl_pct": round(pnl_pct, 1),
            "weight": 0  # calculated after total
        })
        strat_data["total_value"] += mkt_value
        strat_data["total_cost"] += cost_basis

    # Calculate weights
    for pos in strat_data["positions"]:
        pos["weight"] = round((pos["mkt_value"] / strat_data["total_value"]) * 100, 1) if strat_data["total_value"] > 0 else 0

    # Sort by weight descending
    strat_data["positions"].sort(key=lambda x: x["weight"], reverse=True)

    strat_data["total_value"] = round(strat_data["total_value"], 2)
    strat_data["total_cost"] = round(strat_data["total_cost"], 2)
    strat_data["total_pnl_pct"] = round(((strat_data["total_value"] / strat_data["total_cost"]) - 1) * 100, 1) if strat_data["total_cost"] > 0 else 0
    strat_data["n_positions"] = len(strat_data["positions"])

    output["strategies"][strat_name] = strat_data

# Calculate YTD 2026 returns per strategy
# YTD = (current_value + realized_pnl) / jan1_value - 1
realized_pnl = positions.get("realized_pnl_2026", {})
annual_returns = positions.get("annual_returns", {})
sp500_returns = positions.get("sp500_returns", {})

output["returns"] = {}
for strat_name, strat_positions in positions.items():
    if strat_name in ("realized_pnl_2026", "annual_returns", "sp500_returns"):
        continue

    # Calculate Jan 1 value for this strategy
    jan1_value = 0
    for p in strat_positions:
        jan1_price = p.get("price_jan1_2026")
        if jan1_price is None:
            continue
        # Convert to USD same way as current price
        if p["ccy"] == "GBP":
            jan1_usd = (jan1_price / 100) * gbp_usd
        elif p["ccy"] == "EUR":
            jan1_usd = jan1_price * eur_usd
        elif p["ccy"] == "TWD":
            jan1_usd = jan1_price * twd_usd
        else:
            jan1_usd = jan1_price
        jan1_value += jan1_usd * p["qty"]

    current_value = output["strategies"][strat_name]["total_value"]
    real_pnl = realized_pnl.get(strat_name, 0)

    if jan1_value > 0:
        ytd = ((current_value + real_pnl) / jan1_value - 1) * 100
    else:
        ytd = 0

    strat_returns = annual_returns.get(strat_name, {})
    strat_returns["2026_ytd"] = round(ytd, 1)
    output["returns"][strat_name] = strat_returns

    if strat_name in output["strategies"]:
        output["strategies"][strat_name]["ytd_2026"] = round(ytd, 1)
        output["strategies"][strat_name]["jan1_value"] = round(jan1_value, 2)

# S&P 500 YTD (fetch live)
try:
    spy = yf.download("SPY", start="2026-01-02", end="2026-01-06", progress=False)
    spy_now = yf.download("SPY", period="1d", progress=False)
    spy_jan1 = float(spy["Close"].iloc[0])
    spy_current = float(spy_now["Close"].iloc[-1])
    sp500_ytd = round(((spy_current / spy_jan1) - 1) * 100, 1)
except:
    sp500_ytd = -0.6  # fallback

sp500_returns["2026_ytd"] = sp500_ytd
output["returns"]["sp500"] = sp500_returns

# Grand total
total_val = sum(s["total_value"] for s in output["strategies"].values())
total_cost = sum(s["total_cost"] for s in output["strategies"].values())
output["total_value"] = round(total_val, 2)
output["total_cost"] = round(total_cost, 2)
output["total_pnl_pct"] = round(((total_val / total_cost) - 1) * 100, 1) if total_cost > 0 else 0
output["n_positions"] = sum(s["n_positions"] for s in output["strategies"].values())

# Save
out_path = os.path.join(ROOT_DIR, "portfolio-data.json")
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)

print(f"\nSaved to {out_path}")
print(f"Total: ${total_val:,.0f} | Cost: ${total_cost:,.0f} | P&L: {output['total_pnl_pct']:+.1f}%")
for s_name, s_data in output["strategies"].items():
    ytd = s_data.get('ytd_2026', 0)
    print(f"  {s_name}: {s_data['n_positions']} pos, ${s_data['total_value']:,.0f}, YTD:{ytd:+.1f}%")
print(f"  S&P 500 YTD: {sp500_ytd:+.1f}%")
