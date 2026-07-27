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
    month_label = end_dt.strftime('%b %Y') if not is_current else 'Jul 2026 (MTD)'
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

# ── Build current-month holdings with entry prices ────────────────────────────
current_period = next((p for p in history if pd.Timestamp(p['end']) > today), None)

# Load existing portfolio to preserve entry prices if tickers haven't changed
try:
    with open(PORTFOLIO_PATH) as f:
        existing = json.load(f)
    existing_map = {h['ticker']: h for h in existing.get('holdings', [])}
except (FileNotFoundError, json.JSONDecodeError):
    existing_map = {}

# Load name/sector from momentum-data.json
try:
    with open(MOM_DATA_PATH) as f:
        mom_data = json.load(f)
    name_map   = {s['ticker']: s['name']   for s in mom_data.get('top20', [])}
    sector_map = {s['ticker']: s['sector'] for s in mom_data.get('top20', [])}
except Exception:
    name_map = {}; sector_map = {}

# ── Find first consecutive entry date for each current ticker ─────────────────
def first_consecutive_period_start(ticker, current_idx):
    """Walk back through history to find the start of the first consecutive period."""
    first_start = history[current_idx]['start']
    for i in range(current_idx - 1, -1, -1):
        if ticker in history[i]['tickers']:
            first_start = history[i]['start']
        else:
            break
    return first_start

def first_trading_day_after(period_start_str):
    """Return the first trading day (close) after period_start — i.e. entry day."""
    start_ts = pd.Timestamp(period_start_str)
    # Find first date in price history strictly after period_start with valid data
    col = prices.iloc[:, 0]  # any ticker column to get trading dates
    valid_dates = prices.index[prices.index > start_ts]
    # Filter to dates that have at least some non-NaN data
    for d in valid_dates:
        if prices.loc[d].notna().any():
            return d
    return start_ts  # fallback

current_idx = len(history) - 1  # index of July period

holdings = []
if current_period:
    for tk in current_period['tickers']:
        period_start = first_consecutive_period_start(tk, current_idx)
        entry_ts = first_trading_day_after(period_start)
        entry_date_str = entry_ts.strftime('%Y-%m-%d')
        existing = existing_map.get(tk, {})

        # Keep existing entry if unchanged
        if existing.get('entry_date') == entry_date_str and existing.get('entry_price'):
            h = existing.copy()
        else:
            ep = get_price(tk, entry_ts)
            h = {
                'ticker':        tk,
                'name':          name_map.get(tk, tk),
                'sector':        sector_map.get(tk, ''),
                'entry_date':    entry_date_str,
                'entry_price':   round(ep, 2) if ep else None,
                'current_price': None,
            }
        # Update name/sector
        if tk in name_map:   h['name']   = name_map[tk]
        if tk in sector_map: h['sector'] = sector_map[tk]
        # Update current price (intraday preferred over last close)
        cp = intraday_prices.get(tk) or get_price(tk, today)
        h['current_price'] = round(cp, 2) if cp else h.get('current_price')
        ep = h.get('entry_price'); cph = h.get('current_price')
        h['return_pct'] = round((cph / ep - 1) * 100, 2) if ep and cph else 0.0
        holdings.append(h)

# ── Save to momentum-portfolio.json ──────────────────────────────────────────
portfolio_out = {
    'last_rebalance': current_period['start'] if current_period else today.strftime('%Y-%m-%d'),
    'updated':        today.strftime('%Y-%m-%d'),
    'ytd_2026':       ytd_return,
    'monthly_breakdown': monthly_breakdown,
    'holdings':       holdings,
}
with open(PORTFOLIO_PATH, 'w') as f:
    json.dump(portfolio_out, f, indent=2)
print(f"\nSaved: {PORTFOLIO_PATH}")
