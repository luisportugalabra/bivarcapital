#!/usr/bin/env python3
"""
China Momentum — Backfill histórico de picks 2026

Usa a mesma lógica do china_momentum_signal.py (EODHD data) mas para
datas históricas, gerando ytd-picks-history-china.json.

Sinal: 21m-1 momentum | mcap >= 20B CNY | top 10 | CSI300 MA150
"""
import os, json, warnings
from datetime import date
import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
SITE_DIR     = os.path.dirname(SCRIPT_DIR)
EODHD_DIR    = '/Users/luisabrantes/eodhd_data'
CSI300_PATH  = '/Users/luisabrantes/china_momentum/csi300_daily.parquet'
OUTPUT_PATH  = os.path.join(SITE_DIR, 'ytd-picks-history-china.json')

EXCHANGES    = ['SHG', 'SHE']
MIN_MCAP     = 20e9
TOP_N        = 10
WINSOR_CAP   = 0.50
MA_WINDOW    = 150

# ── Signal months: para cada data de sinal, o portfolio é para o mês seguinte ─
# Dec 31 2025 → Jan 2026 | Jan 31 2026 → Feb 2026 | ... | Jun 30 2026 → Jul 2026
SIGNAL_MONTHS = [
    ('2025-12', '2025-12-31', '2026-01-31'),
    ('2026-01', '2026-01-31', '2026-02-28'),
    ('2026-02', '2026-02-28', '2026-03-31'),
    ('2026-03', '2026-03-31', '2026-04-30'),
    ('2026-04', '2026-04-30', '2026-05-31'),
    ('2026-05', '2026-05-31', '2026-06-30'),
    ('2026-06', '2026-06-30', '2026-07-31'),
]

# ── Load CSI300 regime ─────────────────────────────────────────────────────────
print("Loading CSI300...")
csi = pd.read_parquet(CSI300_PATH)
csi['date'] = pd.to_datetime(csi['date'])
csi = csi.sort_values('date').set_index('date')['close']
csi_ma150 = csi.rolling(MA_WINDOW).mean()

def regime_at(signal_date):
    """CSI300 close >= MA150 on signal date (or closest prior day)."""
    dt = pd.Timestamp(signal_date)
    valid = csi[csi.index <= dt]
    if valid.empty: return True
    last = valid.iloc[-1]
    ma   = csi_ma150[csi_ma150.index <= dt].iloc[-1]
    return bool(last >= ma)

# ── Load monthly prices (once, full history) ───────────────────────────────────
print("Loading EODHD prices (SHG + SHE)...")

def load_monthly(exchange):
    price_dir = os.path.join(EODHD_DIR, exchange, 'prices')
    frames = {}
    for fname in os.listdir(price_dir):
        if not fname.endswith('.parquet'): continue
        ticker = fname.replace('.parquet', '')
        try:
            df = pd.read_parquet(os.path.join(price_dir, fname), columns=['adjusted_close'])
            s  = df['adjusted_close'].dropna()
            if len(s) < 30: continue
            monthly = s.resample('ME').last().dropna()
            # winsorize
            ret = monthly.pct_change()
            ret_c = ret.clip(-WINSOR_CAP, WINSOR_CAP)
            prices = [monthly.iloc[0]]
            for r in ret_c.iloc[1:]:
                prices.append(prices[-1] * (1 + r))
            clean = pd.Series(prices, index=monthly.index)
            frames[f'{exchange}:{ticker}'] = clean
        except Exception:
            continue
    return pd.DataFrame(frames)

parts = [load_monthly(e) for e in EXCHANGES]
pm = pd.concat(parts, axis=1).sort_index()
pm.index = pm.index.to_period('M').astype(str)
print(f"  {pm.shape[1]} tickers | {pm.index[0]} → {pm.index[-1]}")

# ── Load shares for mcap ───────────────────────────────────────────────────────
print("Loading shares outstanding...")

def load_shares(exchange):
    fund_dir = os.path.join(EODHD_DIR, exchange, 'fundamentals')
    out = {}
    if not os.path.isdir(fund_dir): return out
    for fname in os.listdir(fund_dir):
        if not fname.endswith('.json'): continue
        ticker = fname.replace('.json', '')
        try:
            with open(os.path.join(fund_dir, fname)) as f:
                d = json.load(f)
            q = d.get('outstandingShares', {}).get('quarterly', {})
            items = list(q.values()) if isinstance(q, dict) else q
            if not items: continue
            items_sorted = sorted(items, key=lambda x: x.get('dateFormatted', x.get('date','')), reverse=True)
            s = items_sorted[0].get('shares')
            if s and float(s) > 0:
                out[f'{exchange}:{ticker}'] = float(s)
        except Exception:
            continue
    return out

shares = {}
for e in EXCHANGES:
    shares.update(load_shares(e))
shares_s = pd.Series(shares)
print(f"  {len(shares_s)} tickers with shares data")

# ── Load company info ──────────────────────────────────────────────────────────
def load_info(exchange):
    fund_dir = os.path.join(EODHD_DIR, exchange, 'fundamentals')
    out = {}
    if not os.path.isdir(fund_dir): return out
    for fname in os.listdir(fund_dir):
        if not fname.endswith('.json'): continue
        ticker = fname.replace('.json', '')
        try:
            with open(os.path.join(fund_dir, fname)) as f:
                d = json.load(f)
            g = d.get('General', {})
            out[f'{exchange}:{ticker}'] = {'name': g.get('Name',''), 'sector': g.get('Sector','')}
        except Exception:
            continue
    return out

info = {}
for e in EXCHANGES:
    info.update(load_info(e))

# ── Run signal for each month ──────────────────────────────────────────────────
print("\nComputing signals for each month...\n")

history = []

for signal_ym, signal_date, end_date in SIGNAL_MONTHS:
    # Truncate price matrix to signal month
    pm_cut = pm[pm.index <= signal_ym].copy()

    if pm_cut.shape[0] < 23:
        print(f"  {signal_ym}: not enough history, skipping")
        continue

    # Regime check
    in_regime = regime_at(signal_date)
    if not in_regime:
        print(f"  {signal_ym}: CSI300 < MA150 — CASH")
        history.append({
            'signal_date': signal_date,
            'start': signal_date,
            'end':   end_date,
            'regime': 'cash',
            'tickers': [],
        })
        continue

    # Signal: price[-2] / price[-23] - 1  (21m, skip 1M)
    p_now  = pm_cut.iloc[-2]   # 1M ago (skip last month)
    p_22m  = pm_cut.iloc[-23]  # 22M ago

    mom = p_now / p_22m - 1

    # Mcap filter
    common = shares_s.index.intersection(mom.index)
    mcap = p_now[common] * shares_s[common]
    eligible = mcap[mcap >= MIN_MCAP].index
    mom_elig = mom[eligible].dropna()
    mom_elig = mom_elig[mom_elig.index.isin(p_now[p_now > 0].index)]

    top = mom_elig.nlargest(TOP_N)
    tickers_raw = [t.split(':')[1] for t in top.index]  # strip exchange prefix

    print(f"  {signal_ym} ({signal_date}): {len(mom_elig)} eligible → top {len(tickers_raw)}: {', '.join(tickers_raw)}")

    history.append({
        'signal_date': signal_date,
        'start': signal_date,
        'end':   end_date,
        'regime': 'momentum',
        'tickers': tickers_raw,
    })

# ── Save ───────────────────────────────────────────────────────────────────────
with open(OUTPUT_PATH, 'w') as f:
    json.dump(history, f, indent=2, ensure_ascii=False)
print(f"\nSaved: {OUTPUT_PATH}")
print(json.dumps(history, indent=2, ensure_ascii=False))
