#!/usr/bin/env python3
"""
China Momentum — Live Portfolio Tracker

Reads china-momentum-data.json (current signal) and china-momentum-portfolio.json
(historical picks), fetches prices via yfinance, and updates:
  - holdings: entry_price, current_price, return_pct for each position
  - monthly_breakdown[is_current].return_pct  ← MTD
  - ytd_2026  ← YTD (chain of completed months × current MTD)

Exchange mapping: SHG → ticker.SS  |  SHE → ticker.SZ

Usage: python3 scripts/china_momentum_ytd.py
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

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
SITE_DIR      = os.path.dirname(SCRIPT_DIR)
PORTFOLIO_PATH = os.path.join(SITE_DIR, 'china-momentum-portfolio.json')
DATA_PATH      = os.path.join(SITE_DIR, 'china-momentum-data.json')

def yf_symbol(ticker, exchange):
    """Convert ticker + exchange to yfinance symbol."""
    suffix = '.SS' if exchange == 'SHG' else '.SZ'
    return ticker + suffix

# ── Load portfolio state ───────────────────────────────────────────────────────
with open(PORTFOLIO_PATH) as f:
    portfolio = json.load(f)

# ── Load signal data for name/sector/exchange info ────────────────────────────
with open(DATA_PATH) as f:
    signal = json.load(f)

info_map = {s['ticker']: s for s in signal.get('portfolio', []) + signal.get('top30', [])}

today = pd.Timestamp.today().normalize()
today_str = today.strftime('%Y-%m-%d')

# ── Process monthly breakdown ──────────────────────────────────────────────────
monthly_breakdown = portfolio.get('monthly_breakdown', [])
ytd_factor = 1.0

# Collect all tickers across all months
all_tickers_meta = {}  # ticker -> exchange
for m in monthly_breakdown:
    for tk in m.get('tickers', []):
        if tk not in all_tickers_meta:
            info = info_map.get(tk, {})
            all_tickers_meta[tk] = info.get('exchange', 'SHG')

# Build yfinance symbols
yf_symbols = {tk: yf_symbol(tk, exch) for tk, exch in all_tickers_meta.items()}
all_yf = list(set(yf_symbols.values()))

print(f"Fetching price history for {len(all_yf)} China A-shares...")

# Download price history (from Dec 2025 to cover any 2026 months)
if all_yf:
    raw = yf.download(all_yf, start='2025-12-01', progress=False, auto_adjust=True)
    prices = raw['Close'] if isinstance(raw.columns, pd.MultiIndex) else raw
else:
    prices = pd.DataFrame()

def get_price(ticker, exchange, target_date):
    """Get closing price on or before target_date."""
    sym = yf_symbol(ticker, exchange)
    if prices.empty or sym not in prices.columns:
        return None
    col = prices[sym].dropna()
    valid = col[col.index <= pd.Timestamp(target_date)]
    if valid.empty:
        return None
    return float(valid.iloc[-1])

# ── Fetch intraday prices ──────────────────────────────────────────────────────
print("Fetching intraday prices...")
intraday = {}
for tk, sym in yf_symbols.items():
    try:
        intraday[tk] = yf.Ticker(sym).fast_info.last_price
    except Exception:
        pass

# ── Compute monthly returns ────────────────────────────────────────────────────
print("Computing monthly returns...")
updated_breakdown = []

for m in monthly_breakdown:
    start_dt = pd.Timestamp(m['start'])
    end_dt   = pd.Timestamp(m['end'])
    tickers  = m['tickers']
    is_current = end_dt >= today  # >= so last day of month still shows as current

    returns = []
    for tk in tickers:
        exch = all_tickers_meta.get(tk, 'SHG')
        p_start = get_price(tk, exch, start_dt)
        if is_current:
            p_end = intraday.get(tk) or get_price(tk, exch, today)
        else:
            p_end = get_price(tk, exch, end_dt)
        if p_start and p_end and p_start > 0:
            returns.append(p_end / p_start - 1)

    period_ret = float(np.mean(returns)) if returns else None

    month_label = m.get('month', end_dt.strftime('%b %Y'))
    if is_current and 'MTD' not in month_label:
        month_label = end_dt.strftime('%b %Y') + ' (MTD)'

    updated_breakdown.append({
        'month':      month_label,
        'is_current': is_current,
        'start':      m['start'],
        'end':        m['end'] if not is_current else today_str,
        'tickers':    tickers,
        'return_pct': round(period_ret * 100, 2) if period_ret is not None else None,
    })

    factor = (1 + period_ret) if period_ret is not None else 1.0
    ytd_factor *= factor
    label = month_label
    ret_str = f"{period_ret*100:+.2f}%" if period_ret is not None else "n/a"
    print(f"  {label}: {ret_str}  ({', '.join(tickers[:3])}{'...' if len(tickers)>3 else ''})")

ytd_return = round((ytd_factor - 1) * 100, 2)
print(f"\nYTD 2026: {ytd_return:+.2f}%")

# ── Build current-month holdings ───────────────────────────────────────────────
current_month = next((m for m in monthly_breakdown if pd.Timestamp(m['end']) >= today), None)
existing_holdings = {h['ticker']: h for h in portfolio.get('holdings', [])}

holdings = []
if current_month:
    for tk in current_month['tickers']:
        exch = all_tickers_meta.get(tk, 'SHG')
        start_dt = pd.Timestamp(current_month['start'])

        # Keep existing entry price if available
        existing = existing_holdings.get(tk, {})
        entry_date_str = (start_dt + pd.offsets.BDay(1)).strftime('%Y-%m-%d')

        if existing.get('entry_price') and existing.get('entry_date'):
            h = existing.copy()
        else:
            ep = get_price(tk, exch, start_dt + pd.offsets.BDay(1))
            if ep is None:
                ep = get_price(tk, exch, start_dt)
            info = info_map.get(tk, {})
            h = {
                'ticker':        tk,
                'name':          info.get('name', tk),
                'exchange':      exch,
                'sector':        info.get('sector', ''),
                'entry_date':    entry_date_str,
                'entry_price':   round(ep, 4) if ep else None,
                'current_price': None,
                'return_pct':    0.0,
            }

        # Update name/sector from signal
        info = info_map.get(tk, {})
        if info.get('name'):   h['name']   = info['name']
        if info.get('sector'): h['sector'] = info['sector']

        # Update current price
        cp = intraday.get(tk) or get_price(tk, exch, today)
        h['current_price'] = round(cp, 4) if cp else h.get('current_price')

        ep = h.get('entry_price')
        cph = h.get('current_price')
        h['return_pct'] = round((cph / ep - 1) * 100, 2) if ep and cph else 0.0
        holdings.append(h)

# ── Save ───────────────────────────────────────────────────────────────────────
out = {
    'last_rebalance': current_month['start'] if current_month else today_str,
    'updated':        today_str,
    'ytd_2026':       ytd_return,
    'currency':       'CNY',
    'currency_note':  'Prices in CNY (Chinese Yuan Renminbi).',
    'monthly_breakdown': updated_breakdown,
    'holdings':       holdings,
}
with open(PORTFOLIO_PATH, 'w') as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"\nSaved: {PORTFOLIO_PATH}")
