#!/usr/bin/env python3
"""
Germany Momentum — Daily YTD / MTD updater
Same pattern as canada_momentum_ytd.py (.TO -> .DE suffix).

Uses monthly_breakdown from germany-momentum-portfolio.json as picks history.
Downloads prices via yfinance (.DE suffix, auto_adjust=True so monthly
returns are dividend-adjusted like the backtest, unlike TradingView Perf.Y).
Computes actual monthly returns and updates the portfolio JSON.
"""
import os, json, warnings
import pandas as pd

warnings.filterwarnings('ignore')
import yfinance as yf

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
SITE_DIR       = os.path.dirname(SCRIPT_DIR)
PORTFOLIO_PATH = os.path.join(SITE_DIR, 'germany-momentum-portfolio.json')

today = pd.Timestamp.today().normalize()

with open(PORTFOLIO_PATH) as f:
    portfolio = json.load(f)

breakdown = portfolio.get('monthly_breakdown', [])
periods   = [m for m in breakdown if m.get('start') and m.get('tickers')]

all_tickers = set()
for p in periods:
    all_tickers.update(p['tickers'])

yf_tickers = [tk + '.DE' for tk in sorted(all_tickers)]
print(f"Fetching price history for {len(yf_tickers)} tickers (yfinance .DE)...")

raw = yf.download(yf_tickers, start='2026-01-01', progress=False, auto_adjust=True)
prices = raw['Close'] if isinstance(raw.columns, pd.MultiIndex) else raw

def get_price(ticker, target_date):
    yt = ticker + '.DE'
    col = prices[yt] if yt in prices.columns else None
    if col is None:
        return None
    col = col.dropna()
    valid = col[col.index <= target_date]
    return float(valid.iloc[-1]) if not valid.empty else None

print("Fetching intraday prices...")
intraday = {}
for tk in all_tickers:
    try:
        intraday[tk] = yf.Ticker(tk + '.DE').fast_info.last_price
    except Exception:
        pass

updated_breakdown = []

for m in breakdown:
    if not m.get('start') or not m.get('tickers'):
        updated_breakdown.append(m)
        continue

    start_dt   = pd.Timestamp(m['start'])
    end_str    = m.get('end')
    is_current = bool(m.get('is_current', False))

    if is_current:
        end_dt = today
    elif end_str:
        end_dt = pd.Timestamp(end_str)
    else:
        # closed month with no recorded end (signal script sets it on close,
        # but guard against a missed run): bound at a few days past that
        # calendar month's end, never at "today", so the return window can't
        # silently keep growing
        end_dt = min(today, start_dt + pd.offsets.MonthEnd(0) + pd.Timedelta(days=4))

    # cash months (defensive, no tickers) are skipped by the `periods` filter
    # above only for ticker collection; here an empty tickers list would have
    # been filtered at the top of the loop -- defensive months carry
    # tickers=[] and fall through with return 0 via the rets==[] branch.
    tickers = m['tickers']
    weights = m.get('weights') or {}
    rets = []
    for tk in tickers:
        p0 = get_price(tk, start_dt)
        p1 = (intraday.get(tk) or get_price(tk, end_dt)) if is_current else get_price(tk, end_dt)
        if p0 and p1 and p0 > 0:
            w = weights.get(tk, 1.0 / len(tickers))
            rets.append((p1 / p0 - 1, w))

    if rets:
        wsum = sum(w for _, w in rets)
        ret = sum(r * w for r, w in rets) / wsum if wsum > 0 else 0.0
    else:
        ret = 0.0
    ret_pct = round(ret * 100, 2)

    updated = dict(m)
    updated['return_pct'] = ret_pct
    updated_breakdown.append(updated)

    label = m['month'] + (' (MTD)' if is_current else '')
    print(f"  {label}: {ret_pct:+.2f}%  [{len(rets)}/{len(tickers)}]")

# Only compound months tagged with the live config_version (written by
# germany_momentum_signal.py -- single source of truth, not hardcoded here).
current_entry   = next((m for m in updated_breakdown if m.get('is_current')), None)
live_config_ver = current_entry.get('config_version') if current_entry else None

months_2026 = [m for m in updated_breakdown
               if m.get('start') and m.get('tickers') and not m.get('is_current')
               and '2026' in m.get('month', '') and m.get('config_version') == live_config_ver]
if months_2026:
    ytd_factor = 1.0
    for m in months_2026:
        if m.get('return_pct') is not None:
            ytd_factor *= (1 + m['return_pct'] / 100)
    ytd_2026 = round((ytd_factor - 1) * 100, 2)
else:
    ytd_2026 = None
print(f"\nYTD 2026: {ytd_2026}")

holdings = []
for h in portfolio.get('holdings', []):
    h = h.copy()
    tk = h['ticker']
    cp = intraday.get(tk) or get_price(tk, today)
    ep = h.get('entry_price')
    if cp:
        h['current_price'] = round(cp, 4)
    if ep and h.get('current_price'):
        h['return_pct'] = round((h['current_price'] / ep - 1) * 100, 2)
    holdings.append(h)

# regime / dax / dax_ma200 are NOT recomputed here -- germany_momentum_signal.py
# is the single source of truth for the regime decision (same convention as
# Canada; see the comment there for the drift incident that motivated it).
out = {**portfolio,
       'updated':           today.strftime('%Y-%m-%d'),
       'ytd_2026':          ytd_2026,
       'monthly_breakdown': updated_breakdown,
       'holdings':          holdings}

with open(PORTFOLIO_PATH, 'w') as f:
    json.dump(out, f, indent=2)
print(f"Saved: {PORTFOLIO_PATH}")
