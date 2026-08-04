#!/usr/bin/env python3
"""
Canada Momentum — Live Portfolio Tracker (daily update)

Updates:
  - Current holdings: current_price, return_pct (via yfinance .TO)
  - 2026 monthly returns: re-compute from yfinance prices
  - YTD 2026: chained return across 2026 months
  - TSX regime: tsx / tsx_ma75 in data JSON

Pre-2026 monthly returns are kept as-is (already computed from EODHD data).

Usage: python3 scripts/canada_momentum_ytd.py
"""
import os, json, warnings
from datetime import date as _date, datetime
import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    os.system("pip install yfinance -q")
    import yfinance as yf

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
SITE_DIR       = os.path.dirname(SCRIPT_DIR)
PORTFOLIO_PATH = os.path.join(SITE_DIR, 'canada-momentum-portfolio.json')
DATA_PATH      = os.path.join(SITE_DIR, 'canada-momentum-data.json')

TSX_SYM = '^GSPTSE'
MA_W    = 75

def yf_sym(ticker):
    return ticker + '.TO'

# ── Load existing portfolio ────────────────────────────────────────────────────
with open(PORTFOLIO_PATH) as f:
    portfolio = json.load(f)

monthly_breakdown = portfolio.get('monthly_breakdown', [])
tsx_annual = portfolio.get('tsx_annual', {})
today     = pd.Timestamp.today().normalize()
today_str = today.strftime('%Y-%m-%d')

# ── Collect tickers for 2026+ and current holdings only ───────────────────────
recent_tickers = set()
for p in monthly_breakdown:
    try:
        yr = int(p['month'].split(' ')[1])
    except Exception:
        continue
    if yr >= 2026 or p.get('is_current'):
        recent_tickers.update(p.get('tickers', []))

# Also include current holdings
current_holdings = portfolio.get('holdings', [])
for h in current_holdings:
    recent_tickers.add(h['ticker'])

recent_tickers = sorted(recent_tickers)
print(f"Fetching prices for {len(recent_tickers)} recent TSX equities (2026+)...")

yf_symbols = {tk: yf_sym(tk) for tk in recent_tickers}
all_yf = list(yf_symbols.values())

prices = pd.DataFrame()
if all_yf:
    raw = yf.download(all_yf, start='2025-12-01', progress=False, auto_adjust=True)
    if not raw.empty:
        if isinstance(raw.columns, pd.MultiIndex):
            prices = raw['Close']
        else:
            prices = raw[['Close']].rename(columns={'Close': all_yf[0]})

def get_price(ticker, target_date):
    sym = yf_sym(ticker)
    if prices.empty or sym not in prices.columns:
        return None
    col = prices[sym].dropna()
    valid = col[col.index <= pd.Timestamp(target_date)]
    return float(valid.iloc[-1]) if not valid.empty else None

# ── Intraday prices for current holdings ──────────────────────────────────────
print("Fetching intraday prices for current holdings...")
intraday = {}
for tk in recent_tickers:
    sym = yf_sym(tk)
    try:
        p = yf.Ticker(sym).fast_info.last_price
        if p and not np.isnan(p):
            intraday[tk] = float(p)
    except Exception:
        pass

# ── TSX regime (MA75) ─────────────────────────────────────────────────────────
print("Fetching TSX Composite for MA75 regime...")
tsx_current = None
tsx_ma75_val = None
regime_str = 'unknown'
try:
    tsx_raw = yf.download(TSX_SYM, start='2024-01-01', progress=False, auto_adjust=True)
    if isinstance(tsx_raw.columns, pd.MultiIndex):
        tsx_close = tsx_raw['Close'][TSX_SYM].dropna()
    else:
        tsx_close = tsx_raw['Close'].dropna()
    tsx_current  = float(tsx_close.iloc[-1])
    tsx_ma75_val = float(tsx_close.rolling(MA_W).mean().iloc[-1])
    regime_str   = 'momentum' if tsx_current > tsx_ma75_val else 'defensive'
    print(f"  TSX: {tsx_current:.0f}  |  MA75: {tsx_ma75_val:.0f}  |  Regime: {regime_str}")

    # Refresh TSX annual returns
    tsx_annual_new = {}
    for yr in range(2001, _date.today().year + 1):
        yr_data = tsx_close[tsx_close.index.year == yr]
        if len(yr_data) < 2:
            continue
        r = yr_data.iloc[-1] / yr_data.iloc[0] - 1
        tsx_annual_new[yr] = round(float(r) * 100, 2)
    tsx_annual = tsx_annual_new
except Exception as e:
    print(f"  Warning: could not fetch TSX ({e})")

# ── Update monthly breakdown (only 2026 and current months) ───────────────────
print("Updating 2026 monthly returns...")
updated_breakdown = []

for period in monthly_breakdown:
    try:
        yr = int(period['month'].split(' ')[1])
    except Exception:
        updated_breakdown.append(period)
        continue

    is_current = period.get('is_current', False)

    # Only recompute 2026 months
    if yr < 2026 and not is_current:
        updated_breakdown.append(period)
        continue

    tickers = period.get('tickers', [])
    start_dt = pd.Timestamp(period['start'])
    end_raw  = period.get('end')

    if not tickers:
        updated_breakdown.append(period)
        continue

    # Compute return
    returns = []
    for tk in tickers:
        p0 = get_price(tk, start_dt)
        if is_current or not end_raw:
            p1 = intraday.get(tk) or get_price(tk, today)
        else:
            p1 = get_price(tk, pd.Timestamp(end_raw))
        if p0 and p1 and p0 > 0:
            returns.append(p1 / p0 - 1)

    period_ret = float(np.mean(returns)) if returns else period.get('return_pct', 0.0) / 100
    updated_breakdown.append({
        **period,
        'return_pct': round(period_ret * 100, 4),
    })
    print(f"  {period['month']}{'(MTD)' if is_current else ''}: {period_ret*100:+.2f}%")

# ── YTD 2026 ───────────────────────────────────────────────────────────────────
ytd_factor = 1.0
for p in updated_breakdown:
    if p.get('is_current'):
        continue
    try:
        yr = int(p['month'].split(' ')[1])
    except Exception:
        continue
    if yr == 2026:
        ytd_factor *= (1 + p['return_pct'] / 100)
ytd_return = round((ytd_factor - 1) * 100, 2)
print(f"\nYTD 2026: {ytd_return:+.2f}%")

# ── Update current holdings ────────────────────────────────────────────────────
existing_map = {h['ticker']: h for h in current_holdings}
cur_period   = next((p for p in updated_breakdown if p.get('is_current')), None)

holdings = []
if cur_period and cur_period.get('tickers'):
    start_dt = pd.Timestamp(cur_period['start'])
    for tk in cur_period['tickers']:
        h = dict(existing_map.get(tk, {
            'ticker':      tk,
            'name':        '',
            'sector':      '',
            'entry_date':  start_dt.strftime('%Y-%m-%d'),
            'entry_price': get_price(tk, start_dt),
            'current_price': None,
            'return_pct':  0.0,
        }))
        cp = intraday.get(tk) or get_price(tk, today)
        h['current_price'] = round(cp, 4) if cp else h.get('current_price')
        ep, cp_val = h.get('entry_price'), h.get('current_price')
        h['return_pct'] = round((cp_val / ep - 1) * 100, 2) if ep and cp_val else 0.0
        holdings.append(h)

# ── Save portfolio JSON ────────────────────────────────────────────────────────
out_portfolio = {
    'last_rebalance':    cur_period['start'] if cur_period else portfolio.get('last_rebalance'),
    'updated':           today_str,
    'ytd_2026':          ytd_return,
    'holdings':          holdings,
    'monthly_breakdown': updated_breakdown,
    'tsx_annual':        tsx_annual,
}

with open(PORTFOLIO_PATH, 'w') as f:
    json.dump(out_portfolio, f, indent=2)
print(f"Saved: {PORTFOLIO_PATH}")

# ── Update canada-momentum-data.json ──────────────────────────────────────────
try:
    with open(DATA_PATH) as f:
        data_json = json.load(f)
    data_json['updated'] = today_str
    data_json['regime']  = regime_str
    if tsx_current:    data_json['tsx']      = round(tsx_current, 2)
    if tsx_ma75_val:   data_json['tsx_ma75'] = round(tsx_ma75_val, 2)
    with open(DATA_PATH, 'w') as f:
        json.dump(data_json, f, indent=2)
    print(f"Saved: {DATA_PATH}")
except Exception as e:
    print(f"Warning: could not update data JSON: {e}")

print("Done.")
