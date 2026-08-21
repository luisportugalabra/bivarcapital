#!/usr/bin/env python3
"""
Canada Momentum — Daily YTD / MTD updater
Follows the exact same pattern as momentum_ytd.py (US).

Uses monthly_breakdown from canada-momentum-portfolio.json as picks history.
Downloads prices via yfinance (.TO suffix).
Computes actual monthly returns and updates the portfolio JSON.
"""
import os, json, warnings
from datetime import datetime
import pandas as pd

warnings.filterwarnings('ignore')
import yfinance as yf

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
SITE_DIR       = os.path.dirname(SCRIPT_DIR)
PORTFOLIO_PATH = os.path.join(SITE_DIR, 'canada-momentum-portfolio.json')
DATA_PATH      = os.path.join(SITE_DIR, 'canada-momentum-data.json')

today = pd.Timestamp.today().normalize()

# ── Load portfolio (picks history) ────────────────────────────────────────────
with open(PORTFOLIO_PATH) as f:
    portfolio = json.load(f)

breakdown = portfolio.get('monthly_breakdown', [])
periods   = [m for m in breakdown if m.get('start') and m.get('tickers')]

# ── Collect all tickers ───────────────────────────────────────────────────────
all_tickers = set()
for p in periods:
    all_tickers.update(p['tickers'])

yf_tickers = [tk + '.TO' for tk in sorted(all_tickers)]
print(f"Fetching price history for {len(yf_tickers)} tickers (yfinance .TO)...")

raw = yf.download(yf_tickers, start='2023-01-01', progress=False, auto_adjust=True)
prices = raw['Close'] if isinstance(raw.columns, pd.MultiIndex) else raw

def get_price(ticker, target_date):
    yt = ticker + '.TO'
    col = prices[yt] if yt in prices.columns else None
    if col is None:
        return None
    col = col.dropna()
    valid = col[col.index <= target_date]
    return float(valid.iloc[-1]) if not valid.empty else None

# ── Intraday prices ───────────────────────────────────────────────────────────
print("Fetching intraday prices...")
intraday = {}
for tk in all_tickers:
    try:
        intraday[tk] = yf.Ticker(tk + '.TO').fast_info.last_price
    except Exception:
        pass

# ── Compute monthly returns ───────────────────────────────────────────────────
updated_breakdown = []

for m in breakdown:
    if not m.get('start') or not m.get('tickers'):
        updated_breakdown.append(m)
        continue

    start_dt   = pd.Timestamp(m['start'])
    end_str    = m.get('end')
    is_current = bool(m.get('is_current', False))

    end_dt = today if (is_current or not end_str) else pd.Timestamp(end_str)

    tickers = m['tickers']
    weights = m.get('weights') or {}
    rets = []
    for tk in tickers:
        p0 = get_price(tk, start_dt)
        p1 = intraday.get(tk) or get_price(tk, end_dt) if is_current else get_price(tk, end_dt)
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

# Only compound months tagged with the strategy's CURRENT config_version --
# Jan-Jul 2026 were produced under the old N=15/EBIT-less/mcap-P30 config
# and must not be spliced onto the N=10/NetIncome/mcap-P20 track record.
# The reference version is whatever the live (is_current) entry carries,
# since that's written by canada_momentum_signal.py and is the single
# source of truth for which config is currently live -- not hardcoded here,
# so the two scripts can't drift out of sync with each other.
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
    ytd_2026 = None  # no completed months under the current config yet
print(f"\nYTD 2026: {ytd_2026}")

# ── Update current holdings ───────────────────────────────────────────────────
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

# regime / tsx / tsx_ma75 are NOT recomputed here. canada_momentum_signal.py
# is the single source of truth for the regime decision -- it decides once
# at signal time and holds that decision for the month; a second daily
# recompute here previously overwrote its value with a same-day live read,
# which is redundant at best and a source of display/decision drift at
# worst if the two computations ever diverge. {**portfolio, ...} below
# already carries the signal script's regime/tsx/tsx_ma75 forward unchanged.

# ── Save ──────────────────────────────────────────────────────────────────────
out = {**portfolio,
       'updated':           today.strftime('%Y-%m-%d'),
       'ytd_2026':          ytd_2026,
       'monthly_breakdown': updated_breakdown,
       'holdings':          holdings}

with open(PORTFOLIO_PATH, 'w') as f:
    json.dump(out, f, indent=2)
print(f"Saved: {PORTFOLIO_PATH}")
