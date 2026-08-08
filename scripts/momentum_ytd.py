#!/usr/bin/env python3
"""
Compute YTD 2026 return for BivarOptimalMomentum.

Uses ytd-picks-history.json (monthly picks, already recorded) + yfinance for prices.
Outputs to momentum-portfolio.json:
  - ytd_2026: total YTD return %
  - monthly_breakdown: [{month, tickers, return_pct}, ...]
  - holdings: current month holdings with entry_price, current_price, return_pct
"""
import os, json, warnings
from datetime import datetime, date, timedelta
import pandas as pd

warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    os.system("pip install yfinance -q")
    import yfinance as yf

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
SITE_DIR      = os.path.dirname(SCRIPT_DIR)
HISTORY_PATH  = os.path.join(SITE_DIR, 'ytd-picks-history.json')
PORTFOLIO_PATH= os.path.join(SITE_DIR, 'momentum-portfolio.json')
MOM_DATA_PATH = os.path.join(SITE_DIR, 'momentum-data.json')

# ── Load picks history ─────────────────────────────────────────────────────────
with open(HISTORY_PATH) as f:
    history = json.load(f)

# ── Collect all tickers across all periods ─────────────────────────────────────
all_tickers = set()
for period in history:
    all_tickers.update(period['tickers'])
all_tickers = sorted(all_tickers)
print(f"Fetching price history for {len(all_tickers)} tickers...")

# ── Download price history ─────────────────────────────────────────────────────
raw = yf.download(all_tickers, start='2025-06-01', progress=False, auto_adjust=True)
prices = raw['Close'] if isinstance(raw.columns, pd.MultiIndex) else raw

def get_price(ticker, target_date):
    """Get closing price on or before target_date (skip weekends/holidays)."""
    if isinstance(target_date, str):
        target_date = pd.Timestamp(target_date)
    col = prices.get(ticker) if hasattr(prices, 'get') else (prices[ticker] if ticker in prices.columns else None)
    if col is None:
        return None
    col = col.dropna()
    valid = col[col.index <= target_date]
    if valid.empty:
        return None
    return float(valid.iloc[-1])

# ── Fetch current intraday prices ─────────────────────────────────────────────
print("Fetching current intraday prices...")
intraday_prices = {}
for tk in all_tickers:
    try:
        intraday_prices[tk] = yf.Ticker(tk).fast_info.last_price
    except Exception:
        pass

# ── Compute monthly returns ───────────────────────────────────────────────────
today = pd.Timestamp.today().normalize()
monthly_breakdown = []
ytd_factor = 1.0

for period in history:
    start_dt = pd.Timestamp(period['start'])
    end_dt   = pd.Timestamp(period['end'])
    tickers  = period['tickers']
    is_current = end_dt > today

    # Equal-weight return: average of individual returns
    returns = []
    for tk in tickers:
        p_start = get_price(tk, start_dt)
        if is_current:
            # Use intraday price for current period
            p_end = intraday_prices.get(tk) or get_price(tk, today)
        else:
            p_end = get_price(tk, end_dt)
        if p_start and p_end and p_start > 0:
            returns.append(p_end / p_start - 1)

    if returns:
        period_ret = sum(returns) / len(returns)
    else:
        period_ret = 0.0

    # Label = month the return was EARNED (end month, or "MTD" if current)
    month_label = end_dt.strftime('%b %Y') if not is_current else today.strftime('%b %Y') + ' (MTD)'
    label = month_label

    monthly_breakdown.append({
        'month':       month_label,
        'is_current':  is_current,
        'start':       period['start'],
        'end':         period['end'] if not is_current else today.strftime('%Y-%m-%d'),
        'tickers':     tickers,
        'return_pct':  round(period_ret * 100, 2),
    })
    ytd_factor *= (1 + period_ret)
    print(f"  {label}: {period_ret*100:+.2f}%  ({', '.join(tickers)})")

ytd_return = round((ytd_factor - 1) * 100, 2)
print(f"\nYTD 2026: {ytd_return:+.2f}% (intraday)")

# ── Merge into momentum-portfolio.json ─────────────────────────────────────────
# holdings, pending_signal and last_rebalance are owned by momentum_signal.py
# (which runs right before this script and already has the correct, end-of-
# month-aware entry prices/dates). This script only adds the historical
# monthly_breakdown + ytd_2026 on top — it must not rebuild or discard them.
try:
    with open(PORTFOLIO_PATH) as f:
        existing_portfolio = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    existing_portfolio = {}

existing_portfolio['updated']           = today.strftime('%Y-%m-%d')
existing_portfolio['ytd_2026']          = ytd_return
existing_portfolio['monthly_breakdown'] = monthly_breakdown

with open(PORTFOLIO_PATH, 'w') as f:
    json.dump(existing_portfolio, f, indent=2)
print(f"\nSaved: {PORTFOLIO_PATH}")
