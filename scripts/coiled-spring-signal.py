#!/usr/bin/env python3
"""
Coiled Spring v3 — Live Signal Generator
=========================================
Sinal: (roic_lvl + nm_growth + fcf_growth + fcf_lvl) / 4

Fonte de dados: TradingView Screener (100% — sem yfinance)
  roic_lvl   = rank(return_on_invested_capital)
  nm_growth  = rank(net_income_yoy_growth_ttm)
  fcf_growth = rank(free_cash_flow_yoy_growth_ttm)
  fcf_lvl    = rank(free_cash_flow_margin_ttm)

Filtros:
  MCap >= $1B | Net Income > 0 | Ret 6m in [-15%, +15%] | SP500 > MA225

Output: coiled-spring-data.json
"""
import os, json, warnings
from datetime import datetime
import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

SITE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(SITE_DIR, 'coiled-spring-data.json')

# ── DEPENDÊNCIAS ───────────────────────────────────────────────────────────────
for pkg in ['tradingview_screener', 'yfinance']:
    try: __import__(pkg)
    except ImportError: os.system(f"pip install {pkg} -q")

from tradingview_screener import Query, col
import yfinance as yf

# ── REGIME SP500 > MA225 ───────────────────────────────────────────────────────
print("Regime SP500...")
sp_data  = yf.download('^GSPC', period='2y', progress=False)
sp_close = sp_data['Close'].squeeze().dropna()
sp_last  = float(sp_close.iloc[-1])
sp_ma225 = float(sp_close.tail(225).mean())
is_bull  = sp_last >= sp_ma225
regime   = 'momentum' if is_bull else 'gld'
print(f"  S&P: {sp_last:,.0f}  MA225: {sp_ma225:,.0f}  → {regime.upper()}")

# ── UNIVERSO VIA TRADINGVIEW ───────────────────────────────────────────────────
print("TradingView screener...")
_, df = (Query()
  .select('name', 'market_cap_basic', 'oper_income_ttm', 'sector',
          'return_on_invested_capital',       # roic_lvl
          'free_cash_flow_margin_ttm',        # fcf_lvl
          'free_cash_flow_yoy_growth_ttm',    # fcf_growth
          'net_income_yoy_growth_ttm',        # nm_growth
          'after_tax_margin',                 # nm level (info)
          'Perf.6M', 'close')
  .where(
      col('market_cap_basic') > 1_000_000_000,
      col('is_primary') == True,
      col('type') == 'stock',
      col('typespecs').has('common'),
      col('oper_income_ttm') > 0,
  )
  .set_markets('america')
  .order_by('market_cap_basic', ascending=False)
  .limit(5_000)
  .get_scanner_data())

# Limpar tickers
us = ('NASDAQ:', 'NYSE:', 'AMEX:', 'NYSE ARCA:')
df = df[df['ticker'].str.startswith(us)].copy()
df['ticker'] = df['ticker'].str.split(':').str[-1]
df['name']   = df['description'] if 'description' in df.columns else df.get('name', df['ticker'])
df = df.rename(columns={
    'market_cap_basic':               'mcap',
    'oper_income_ttm':                'ebit',
    'return_on_invested_capital':     'roic_tv',
    'free_cash_flow_margin_ttm':      'fcf_tv',
    'free_cash_flow_yoy_growth_ttm':  'fcf_growth_tv',
    'net_income_yoy_growth_ttm':      'nm_growth_tv',
    'after_tax_margin':               'nm_tv',
    'Perf.6M':                        'ret_6m',
})

# Filtros de elegibilidade
BAND = 15.0
df = df.dropna(subset=['roic_tv', 'fcf_tv', 'ret_6m'])
df = df[(df['ret_6m'] >= -BAND) & (df['ret_6m'] <= BAND)].copy()
print(f"  Após filtros: {len(df)} acções")

# ── RANKINGS ───────────────────────────────────────────────────────────────────
def winsor(s):
    lo, hi = s.quantile(0.01), s.quantile(0.99)
    return s.clip(lo, hi)

def rnk(s):
    return winsor(s.replace([np.inf, -np.inf], np.nan)).rank(pct=True)

df['roic_r']      = rnk(df['roic_tv'])
df['fcf_lvl_r']   = rnk(df['fcf_tv'])
df['nm_growth_r']  = rnk(df['nm_growth_tv'])  if df['nm_growth_tv'].notna().sum()  > 10 else pd.Series(0.5, index=df.index)
df['fcf_growth_r'] = rnk(df['fcf_growth_tv']) if df['fcf_growth_tv'].notna().sum() > 10 else df['roic_r']

# Composite: pesos iguais 4 factores
df['composite'] = (df['roic_r'].fillna(0.5) +
                   df['nm_growth_r'].fillna(0.5) +
                   df['fcf_growth_r'].fillna(0.5) +
                   df['fcf_lvl_r'].fillna(0.5)) / 4

df = df.sort_values('composite', ascending=False).reset_index(drop=True)
total_eligible = len(df)

# ── CONSTRUIR JSON ─────────────────────────────────────────────────────────────
TOP_N = 10
selected = set(df.head(TOP_N)['ticker'].tolist())

top20_data = []
for i, row in df.head(20).iterrows():
    tk  = row['ticker']
    sel = tk in selected
    entry = {
        "rank":           len(top20_data) + 1,
        "ticker":         tk,
        "name":           str(row.get('name', tk)),
        "sector":         str(row.get('sector', '')),
        "roic":           round(float(row['roic_r']), 3)       if pd.notna(row['roic_r'])      else None,
        "nm_growth":      round(float(row['nm_growth_r']), 3)  if pd.notna(row['nm_growth_r']) else None,
        "fcf_growth":     round(float(row['fcf_growth_r']), 3) if pd.notna(row['fcf_growth_r']) else None,
        "fcf_lvl":        round(float(row['fcf_lvl_r']), 3)    if pd.notna(row['fcf_lvl_r'])   else None,
        "composite":      round(float(row['composite']), 3),
        "ret_6m":         round(float(row['ret_6m']), 1)        if pd.notna(row['ret_6m'])      else None,
        "mcap_b":         round(float(row['mcap']) / 1e9, 1)    if pd.notna(row.get('mcap'))    else None,
        "roic_pct":       round(float(row['roic_tv']), 1)       if pd.notna(row['roic_tv'])     else None,
        "fcf_margin_pct": round(float(row['fcf_tv']), 1)        if pd.notna(row['fcf_tv'])      else None,
        "fcf_growth_pct": round(float(row['fcf_growth_tv']), 1) if pd.notna(row.get('fcf_growth_tv')) else None,
        "nm_growth_pct":  round(float(row['nm_growth_tv']), 1)  if pd.notna(row.get('nm_growth_tv'))  else None,
        "selected":       sel,
    }
    top20_data.append(entry)

portfolio = [s for s in top20_data if s['selected']]

output = {
    "date":           datetime.now().strftime('%Y-%m-%d'),
    "regime":         regime,
    "sp500":          round(sp_last, 0),
    "sp500_ma225":    round(sp_ma225, 0),
    "total_eligible": total_eligible,
    "portfolio":      portfolio,
    "top20":          top20_data,
}

with open(JSON_PATH, 'w') as f:
    json.dump(output, f, indent=2)
print(f"\nSaved: {JSON_PATH}")

# ── PRINT ──────────────────────────────────────────────────────────────────────
print(f"\n{'='*110}")
print(f"  COILED SPRING v3 — {output['date']} — {regime.upper()}")
print(f"  S&P: {sp_last:,.0f} | MA225: {sp_ma225:,.0f} | Elegíveis: {total_eligible}")
print(f"{'='*110}")
print(f"  {'#':>2}  {'':>4} {'Ticker':<7} {'Nome':<28} {'Sector':<20} {'ROIC':>6} {'NMg':>6} {'FCFg':>6} {'FCFl':>6}  {'Score':>6}  {'MCap':>7}  {'Ret6m':>7}")
print(f"  {'-'*108}")
for s in top20_data:
    sel = ">>>" if s['selected'] else ""
    def f(v): return f"{v:.3f}" if v is not None else "  — "
    print(f"  {s['rank']:2d}  {sel:>4} {s['ticker']:<7} {s['name'][:27]:<28} {s['sector'][:19]:<20} "
          f"{f(s['roic']):>6} {f(s['nm_growth']):>6} {f(s['fcf_growth']):>6} {f(s['fcf_lvl']):>6}  "
          f"{f(s['composite']):>6}  ${s['mcap_b']:>5.0f}B  {s['ret_6m']:>+6.1f}%")
print(f"\n  >>> = Seleccionado (Top {TOP_N})")
