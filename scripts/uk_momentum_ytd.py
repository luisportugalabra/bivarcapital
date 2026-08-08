#!/usr/bin/env python3
"""
UK Momentum — Live Portfolio Tracker

Reads uk-momentum-portfolio.json and updates via yfinance:
  - holdings: entry_price, current_price, return_pct
  - monthly_breakdown: return_pct for each month (including MTD current)
  - ytd_2026: chained return across all months
  - ftse100 / ftse100_ma200 / regime: FTSE 100 MA200 regime status

Exchange: all tickers get ".L" suffix for London Stock Exchange.
Months with no tickers (cash/gld regime) count as 0%.

Usage: python3 scripts/uk_momentum_ytd.py
"""
import os, json, warnings
from datetime import datetime
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
PORTFOLIO_PATH = os.path.join(SITE_DIR, 'uk-momentum-portfolio.json')

FTSE100_SYM = '^FTSE'

def yf_sym(ticker):
    """Append .L suffix for London Stock Exchange."""
    return ticker + '.L'

# ── Load existing portfolio ────────────────────────────────────────────────────
with open(PORTFOLIO_PATH) as f:
    portfolio = json.load(f)

monthly_breakdown = portfolio.get('monthly_breakdown', [])

today     = pd.Timestamp.today().normalize()
today_str = today.strftime('%Y-%m-%d')

# Auto-extend: only if the last period is already closed (not current) and
# stale — a genuinely missing month, e.g. uk_momentum_signal.py hasn't run
# yet this month. The current period's 'end' is expected to lag by up to a
# day between runs (it's bumped forward below); that alone is not a reason
# to append a duplicate — the main loop already extends it to today_str.
if monthly_breakdown:
    import calendar as _cal
    last_period_check = monthly_breakdown[-1]
    last_end_ts = pd.Timestamp(last_period_check['end'])
    if last_end_ts < today and not last_period_check.get('is_current', False):
        last_period = last_period_check
        new_last_day = _cal.monthrange(today.year, today.month)[1]
        new_end = pd.Timestamp(today.year, today.month, new_last_day)
        monthly_breakdown.append({
            'month':      '',  # will be set below
            'is_current': True,
            'start':      last_period['end'],
            'end':        new_end.strftime('%Y-%m-%d'),
            'regime':     last_period.get('regime', 'momentum'),
            'tickers':    last_period['tickers'],
            'return_pct': 0.0,
        })
        print(f"  Auto-extended history to {new_end.strftime('%Y-%m-%d')} (run uk_momentum_signal.py locally to update picks)")

# ── Collect all tickers ────────────────────────────────────────────────────────
all_tickers = sorted(set(t for p in monthly_breakdown for t in p.get('tickers', [])))
yf_symbols  = {tk: yf_sym(tk) for tk in all_tickers}
all_yf      = list(set(yf_symbols.values()))

print(f"Fetching price history for {len(all_yf)} UK equities...")
if all_yf:
    raw = yf.download(all_yf, start='2025-11-01', progress=False, auto_adjust=True)
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw['Close']
    else:
        # Single ticker: columns are ['Close', 'Open', ...] — extract Close
        prices = raw[['Close']].rename(columns={'Close': all_yf[0]})
else:
    prices = pd.DataFrame()

def get_price(ticker, target_date):
    sym = yf_sym(ticker)
    if prices.empty or sym not in prices.columns:
        return None
    col = prices[sym].dropna()
    valid = col[col.index <= pd.Timestamp(target_date)]
    return float(valid.iloc[-1]) if not valid.empty else None

# ── Intraday prices ────────────────────────────────────────────────────────────
print("Fetching intraday prices...")
intraday = {}
for tk, sym in yf_symbols.items():
    try:
        intraday[tk] = yf.Ticker(sym).fast_info.last_price
    except Exception:
        pass

# ── FTSE 100 regime ────────────────────────────────────────────────────────────
print("Fetching FTSE 100 for MA200 regime...")
try:
    ftse_raw = yf.download(FTSE100_SYM, start='2024-01-01', progress=False, auto_adjust=True)
    if isinstance(ftse_raw.columns, pd.MultiIndex):
        ftse_close = ftse_raw['Close'][FTSE100_SYM].dropna()
    else:
        ftse_close = ftse_raw['Close'].dropna()
    ftse_current = float(ftse_close.iloc[-1])
    ma200        = float(ftse_close.rolling(200).mean().iloc[-1])
    regime_str   = 'risk-on' if ftse_current > ma200 else 'risk-off'
    print(f"  FTSE 100: {ftse_current:.0f}  |  MA200: {ma200:.0f}  |  Regime: {regime_str}")
except Exception as e:
    print(f"  Warning: could not fetch FTSE 100 ({e})")
    ftse_current = None
    ma200        = None
    regime_str   = 'unknown'

# ── Compute monthly returns ────────────────────────────────────────────────────
print("Computing monthly returns...")
month_names = {
    '01':'Jan','02':'Feb','03':'Mar','04':'Apr','05':'May','06':'Jun',
    '07':'Jul','08':'Aug','09':'Sep','10':'Oct','11':'Nov','12':'Dec'
}

updated_breakdown = []
ytd_factor = 1.0

for period in monthly_breakdown:
    start_dt   = pd.Timestamp(period['start'])
    tickers    = period.get('tickers', [])
    regime     = period.get('regime', 'momentum')
    # Trust is_current as maintained by uk_momentum_signal.py's rollover
    # logic rather than re-deriving it from a stored 'end' date — the
    # latter only advances below when already current, so it freezes as
    # "closed" after a single day if re-derived this way.
    is_current = period.get('is_current', False)
    end_str    = today_str if is_current else period['end']
    end_dt     = pd.Timestamp(end_str)

    # Month label
    m, y = end_str[5:7], end_str[:4]
    label = f"{month_names[m]} {y}" + (' (MTD)' if is_current else '')

    if regime in ('cash', 'gld') or not tickers:
        period_ret = 0.0
        ret_str = '0.00% (cash)'
    else:
        returns = []
        for tk in tickers:
            p0 = get_price(tk, start_dt)
            p1 = (intraday.get(tk) or get_price(tk, today)) if is_current else get_price(tk, end_dt)
            if p0 and p1 and p0 > 0:
                returns.append(p1 / p0 - 1)
        period_ret = float(np.mean(returns)) if returns else 0.0
        ret_str = f"{period_ret*100:+.2f}%"

    updated_breakdown.append({
        'month':      label,
        'is_current': is_current,
        'start':      period['start'],
        'end':        end_str,
        'regime':     regime,
        'tickers':    tickers,
        'return_pct': round(period_ret * 100, 2),
    })
    ytd_factor *= (1 + period_ret)
    print(f"  {label}: {ret_str}")

ytd_return = round((ytd_factor - 1) * 100, 2)
print(f"\nYTD 2026: {ytd_return:+.2f}%")

# ── Save ───────────────────────────────────────────────────────────────────────
# holdings, pending_signal and last_rebalance are owned by uk_momentum_signal.py
# (which runs right before this script and already has the correct, end-of-
# month-aware entry prices/dates). This script only adds monthly_breakdown,
# ytd_2026 and the FTSE regime snapshot on top — it must not rebuild or
# discard the rest.
portfolio['updated']           = today_str
portfolio['ytd_2026']          = ytd_return
portfolio['ftse100']           = round(ftse_current, 2) if ftse_current else None
portfolio['ftse100_ma200']     = round(ma200, 2) if ma200 else None
portfolio['regime']            = regime_str
portfolio['monthly_breakdown'] = updated_breakdown

with open(PORTFOLIO_PATH, 'w') as f:
    json.dump(portfolio, f, indent=2, ensure_ascii=False)
print(f"Saved: {PORTFOLIO_PATH}")
