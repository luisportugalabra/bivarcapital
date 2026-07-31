#!/usr/bin/env python3
"""
China Momentum — Live Portfolio Tracker

Lê ytd-picks-history-china.json (picks mensais) e calcula via yfinance:
  - holdings: entry_price, current_price, return_pct
  - monthly_breakdown: return_pct para cada mês (incluindo MTD actual)
  - ytd_2026: retorno encadeado de todos os meses

Exchange mapping: SHG → ticker.SS  |  SHE → ticker.SZ
Meses cash (tickers=[]) contam como 0%.

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
HISTORY_PATH  = os.path.join(SITE_DIR, 'ytd-picks-history-china.json')
PORTFOLIO_PATH = os.path.join(SITE_DIR, 'china-momentum-portfolio.json')
DATA_PATH      = os.path.join(SITE_DIR, 'china-momentum-data.json')

def yf_sym(ticker):
    """Guess yfinance suffix: 6xxxxx/688xxx → .SS (Shanghai), rest → .SZ."""
    return ticker + ('.SS' if ticker.startswith('6') else '.SZ')

# ── Load history ───────────────────────────────────────────────────────────────
with open(HISTORY_PATH) as f:
    history = json.load(f)

# ── Load signal data for name/sector ──────────────────────────────────────────
try:
    with open(DATA_PATH) as f:
        signal = json.load(f)
    info_map = {s['ticker']: s for s in signal.get('portfolio', []) + signal.get('top30', [])}
except Exception:
    info_map = {}

today = pd.Timestamp.today().normalize()
today_str = today.strftime('%Y-%m-%d')

# ── Collect all tickers ────────────────────────────────────────────────────────
all_tickers = sorted(set(t for p in history for t in p['tickers']))
yf_symbols  = {tk: yf_sym(tk) for tk in all_tickers}
all_yf      = list(set(yf_symbols.values()))

print(f"Fetching price history for {len(all_yf)} China A-shares...")
if all_yf:
    raw = yf.download(all_yf, start='2025-11-01', progress=False, auto_adjust=True)
    prices = raw['Close'] if isinstance(raw.columns, pd.MultiIndex) else raw
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

# ── Compute monthly returns ────────────────────────────────────────────────────
print("Computing monthly returns...")
monthly_breakdown = []
ytd_factor = 1.0
month_names = {
    '01':'Jan','02':'Feb','03':'Mar','04':'Apr','05':'May','06':'Jun',
    '07':'Jul','08':'Aug','09':'Sep','10':'Oct','11':'Nov','12':'Dec'
}

for period in history:
    start_dt  = pd.Timestamp(period['start'])
    end_dt    = pd.Timestamp(period['end'])
    tickers   = period['tickers']
    regime    = period.get('regime', 'momentum')
    is_current = end_dt >= today

    # Month label
    m, y = period['end'][5:7], period['end'][:4]
    label = f"{month_names[m]} {y}" + (' (MTD)' if is_current else '')

    if regime == 'cash' or not tickers:
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

    monthly_breakdown.append({
        'month':      label,
        'is_current': is_current,
        'start':      period['start'],
        'end':        period['end'] if not is_current else today_str,
        'regime':     regime,
        'tickers':    tickers,
        'return_pct': round(period_ret * 100, 2),
    })
    ytd_factor *= (1 + period_ret)
    print(f"  {label}: {ret_str}")

ytd_return = round((ytd_factor - 1) * 100, 2)
print(f"\nYTD 2026: {ytd_return:+.2f}%")

# ── Current holdings ───────────────────────────────────────────────────────────
current_period = next((p for p in history if pd.Timestamp(p['end']) >= today), None)

# Load existing to preserve entry prices
try:
    with open(PORTFOLIO_PATH) as f:
        existing = json.load(f)
    existing_map = {h['ticker']: h for h in existing.get('holdings', [])}
except Exception:
    existing_map = {}

holdings = []
if current_period and current_period.get('tickers'):
    start_dt = pd.Timestamp(current_period['start'])

    for tk in current_period['tickers']:
        existing_h = existing_map.get(tk, {})

        # Entry price: first trading day after period start
        if existing_h.get('entry_price'):
            h = existing_h.copy()
        else:
            ep = get_price(tk, start_dt + pd.offsets.BDay(1)) or get_price(tk, start_dt)
            info = info_map.get(tk, {})
            h = {
                'ticker':      tk,
                'name':        info.get('name', tk),
                'sector':      info.get('sector', ''),
                'entry_date':  (start_dt + pd.offsets.BDay(1)).strftime('%Y-%m-%d'),
                'entry_price': round(ep, 4) if ep else None,
                'current_price': None,
                'return_pct':  0.0,
            }

        # Update name/sector
        info = info_map.get(tk, {})
        if info.get('name'):   h['name']   = info['name']
        if info.get('sector'): h['sector'] = info['sector']

        cp = intraday.get(tk) or get_price(tk, today)
        h['current_price'] = round(cp, 4) if cp else h.get('current_price')
        ep, cph = h.get('entry_price'), h.get('current_price')
        h['return_pct'] = round((cph / ep - 1) * 100, 2) if ep and cph else 0.0
        holdings.append(h)

# ── Save ───────────────────────────────────────────────────────────────────────
out = {
    'last_rebalance': current_period['start'] if current_period else today_str,
    'updated':        today_str,
    'ytd_2026':       ytd_return,
    'currency':       'CNY',
    'currency_note':  'Prices in CNY (Chinese Yuan Renminbi).',
    'monthly_breakdown': monthly_breakdown,
    'holdings':       holdings,
}
with open(PORTFOLIO_PATH, 'w') as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"Saved: {PORTFOLIO_PATH}")
