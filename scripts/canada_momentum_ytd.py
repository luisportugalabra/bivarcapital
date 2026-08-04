#!/usr/bin/env python3
"""
Canada Momentum — Daily Portfolio Tracker

Uses TradingView screener for current prices of holdings.
Completed monthly returns are kept from the EODHD backtest (generated locally).
Only updates: current prices, current month MTD, YTD 2026, TSX regime.

Usage: python3 scripts/canada_momentum_ytd.py
"""
import os, json, warnings
from datetime import date as _date
import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

try:
    from tradingview_screener import Query, col
except ImportError:
    os.system("pip install tradingview-screener -q")
    from tradingview_screener import Query, col

try:
    import yfinance as yf
except ImportError:
    os.system("pip install yfinance -q")
    import yfinance as yf

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
SITE_DIR       = os.path.dirname(SCRIPT_DIR)
PORTFOLIO_PATH = os.path.join(SITE_DIR, 'canada-momentum-portfolio.json')
DATA_PATH      = os.path.join(SITE_DIR, 'canada-momentum-data.json')

MA_W    = 75
TSX_SYM = '^GSPTSE'
TODAY   = _date.today().isoformat()

# ── Load existing data ─────────────────────────────────────────────────────────
with open(PORTFOLIO_PATH) as f:
    portfolio = json.load(f)

monthly_breakdown = portfolio.get('monthly_breakdown', [])
tsx_annual        = portfolio.get('tsx_annual', {})

# ── Fetch current prices from TradingView ─────────────────────────────────────
print("Fetching current prices from TradingView (TSX)...")
cur_period = next((p for p in monthly_breakdown if p.get('is_current')), None)
current_tickers = cur_period.get('tickers', []) if cur_period else []

tv_prices = {}
if current_tickers:
    try:
        _, df_tv = (Query()
                    .select('name', 'close', 'change_abs', 'Perf.1M')
                    .where(
                        col('is_primary') == True,
                        col('type') == 'stock',
                    )
                    .set_markets('canada')
                    .limit(5_000)
                    .get_scanner_data())
        # TV names for TSX look like "TSX:AII"
        if df_tv is not None and not df_tv.empty:
            for _, row in df_tv.iterrows():
                sym = row.get('name', '')
                tk  = sym.split(':')[-1] if ':' in sym else sym
                if tk in current_tickers and pd.notna(row.get('close')):
                    tv_prices[tk] = float(row['close'])
        print(f"  Found prices for {len(tv_prices)}/{len(current_tickers)} tickers from TV")
    except Exception as e:
        print(f"  TV fetch failed: {e}")

# Fallback to yfinance for any missing current tickers
missing = [tk for tk in current_tickers if tk not in tv_prices]
if missing:
    print(f"  Fetching {len(missing)} missing tickers from yfinance...")
    for tk in missing:
        try:
            p = yf.Ticker(tk + '.TO').fast_info.last_price
            if p and not np.isnan(float(p)):
                tv_prices[tk] = float(p)
        except Exception:
            pass

# ── TSX regime via yfinance ────────────────────────────────────────────────────
print("Fetching TSX Composite for MA75 regime...")
tsx_current = None
tsx_ma75_val = None
regime_str   = 'unknown'
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

    # Refresh tsx_annual
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

# ── Update current month MTD return ───────────────────────────────────────────
# Fetch start-of-month prices via yfinance for the 10 current holdings (one date fetch)
cur_tickers = cur_period.get('tickers', []) if cur_period else []
period_start = pd.Timestamp(cur_period['start']) if cur_period else None
month_entry_prices = {}
if cur_tickers and period_start:
    print(f"Fetching start-of-month prices for MTD (from {period_start.date()})...")
    syms_to = [tk + '.TO' for tk in cur_tickers]
    try:
        raw_m = yf.download(syms_to, start=period_start - pd.Timedelta(days=5),
                            end=period_start + pd.Timedelta(days=10),
                            progress=False, auto_adjust=True)
        if isinstance(raw_m.columns, pd.MultiIndex):
            prices_m = raw_m['Close']
        else:
            prices_m = raw_m[['Close']].rename(columns={'Close': syms_to[0]})
        for tk in cur_tickers:
            sym = tk + '.TO'
            if sym in prices_m.columns:
                col_s = prices_m[sym].dropna()
                valid = col_s[col_s.index <= period_start]
                if not valid.empty:
                    month_entry_prices[tk] = float(valid.iloc[-1])
    except Exception as e:
        print(f"  Warning: MTD entry price fetch failed ({e})")

updated_breakdown = []
for period in monthly_breakdown:
    if not period.get('is_current'):
        updated_breakdown.append(period)
        continue

    tickers = period.get('tickers', [])
    returns = []

    for tk in tickers:
        ep = month_entry_prices.get(tk)   # price at start of current month
        cp = tv_prices.get(tk)
        if ep and cp and ep > 0:
            returns.append(cp / ep - 1)

    mtd_ret = float(np.mean(returns)) if returns else 0.0
    updated_breakdown.append({
        **period,
        'return_pct': round(mtd_ret * 100, 4),
    })
    print(f"  {period['month']} (MTD): {mtd_ret*100:+.2f}%  [{len(returns)}/{len(tickers)} prices]")

# ── Recompute YTD 2026 ─────────────────────────────────────────────────────────
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

# ── Update current holdings with TV prices ────────────────────────────────────
existing_map = {h['ticker']: h for h in portfolio.get('holdings', [])}
holdings = []
for tk in current_tickers:
    h = dict(existing_map.get(tk, {'ticker': tk, 'name': '', 'sector': '',
                                   'entry_date': (cur_period or {}).get('start', TODAY),
                                   'entry_price': None, 'current_price': None, 'return_pct': 0.0}))
    cp = tv_prices.get(tk)
    h['current_price'] = round(cp, 4) if cp else h.get('current_price')
    ep, cp_val = h.get('entry_price'), h.get('current_price')
    h['return_pct'] = round((cp_val / ep - 1) * 100, 2) if ep and cp_val else 0.0
    holdings.append(h)

# ── Save portfolio JSON ────────────────────────────────────────────────────────
out = {
    'last_rebalance':    cur_period['start'] if cur_period else portfolio.get('last_rebalance'),
    'updated':           TODAY,
    'ytd_2026':          ytd_return,
    'holdings':          holdings,
    'monthly_breakdown': updated_breakdown,
    'tsx_annual':        tsx_annual,
}

with open(PORTFOLIO_PATH, 'w') as f:
    json.dump(out, f, indent=2)
print(f"Saved: {PORTFOLIO_PATH}")

# ── Update canada-momentum-data.json ──────────────────────────────────────────
try:
    with open(DATA_PATH) as f:
        data_json = json.load(f)
    data_json['updated'] = TODAY
    data_json['regime']  = regime_str
    if tsx_current:    data_json['tsx']      = round(tsx_current, 2)
    if tsx_ma75_val:   data_json['tsx_ma75'] = round(tsx_ma75_val, 2)
    with open(DATA_PATH, 'w') as f:
        json.dump(data_json, f, indent=2)
    print(f"Saved: {DATA_PATH}")
except Exception as e:
    print(f"Warning: could not update data JSON: {e}")

print("Done.")
