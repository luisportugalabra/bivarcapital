#!/usr/bin/env python3
"""
Coiled Spring v3 — Live Signal Generator
=========================================
Sinal: (roic_lvl + nm_growth + fcf_growth + fcf_lvl) / 4

Dados:
  - TradingView Screener: ROIC, FCF margin agora, Ret 6m, universo
  - Sharadar (actualizado 1x/ano): NM e FCF margin de há 12 meses

Crescimento calculado exactamente igual ao backtest:
  nm_growth  = nm_margin_now  / nm_margin_1y_ago  - 1  (só se base > 0)
  fcf_growth = fcf_margin_now / fcf_margin_1y_ago - 1  (só se base > 0)

Output: coiled-spring-data.json
"""
import os, json, warnings
from datetime import datetime
import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

SITE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH     = os.path.join(SITE_DIR, 'coiled-spring-data.json')
SHARADAR_DIR  = os.environ.get('SHARADAR_DIR', '/Users/luisabrantes/sharadar')

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

# ── SHARADAR: NM e FCF margin de há 12 meses ──────────────────────────────────
print("Sharadar (dados 12m atrás)...")
cutoff = (pd.Timestamp.today() - pd.DateOffset(months=12)).strftime('%Y-%m')

sf1q = pd.read_parquet(os.path.join(SHARADAR_DIR, 'sf1_quarterly_ttm.parquet'),
                        columns=['ticker','datekey','avail_ym','revenue_ttm','netinc_ttm','fcf_ttm'])
tkdf = pd.read_parquet(os.path.join(SHARADAR_DIR, 'tickers.parquet'),
                        columns=['ticker','category'])

valid = set(tkdf.loc[tkdf['category'].isin(
    ['Domestic Common Stock','Domestic Common Stock Primary Class']), 'ticker'])

sf1q = sf1q[sf1q['ticker'].isin(valid)].dropna(subset=['avail_ym'])
sf1q['net_margin_1y'] = sf1q['netinc_ttm'] / sf1q['revenue_ttm'].replace(0, np.nan)
sf1q['fcf_margin_1y'] = sf1q['fcf_ttm']    / sf1q['revenue_ttm'].replace(0, np.nan)

lag = (sf1q[sf1q['avail_ym'] <= cutoff]
         .sort_values('avail_ym')
         .groupby('ticker')
         .last()[['net_margin_1y', 'fcf_margin_1y']])

print(f"  Tickers com dados 12m atrás: {len(lag)}")

# ── UNIVERSO VIA TRADINGVIEW (dados actuais) ───────────────────────────────────
print("TradingView screener...")
_, df = (Query()
  .select('name', 'market_cap_basic', 'oper_income_ttm', 'sector',
          'return_on_invested_capital',    # roic_lvl
          'after_tax_margin',              # nm agora (%)
          'free_cash_flow_margin_ttm',     # fcf_lvl + fcf agora (%)
          'Perf.6M')
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

us = ('NASDAQ:', 'NYSE:', 'AMEX:', 'NYSE ARCA:')
df = df[df['ticker'].str.startswith(us)].copy()
df['ticker'] = df['ticker'].str.split(':').str[-1]
df['name']   = df['description'] if 'description' in df.columns else df.get('name', df['ticker'])
df = df.rename(columns={
    'market_cap_basic':           'mcap',
    'oper_income_ttm':            'ebit',
    'return_on_invested_capital': 'roic_tv',
    'after_tax_margin':           'nm_now_pct',
    'free_cash_flow_margin_ttm':  'fcf_now_pct',
    'Perf.6M':                    'ret_6m',
})

# TV devolve margens em % → converter para decimal
df['nm_now']  = df['nm_now_pct']  / 100
df['fcf_now'] = df['fcf_now_pct'] / 100

# Filtros base
BAND = 15.0
df = df.dropna(subset=['roic_tv', 'fcf_now', 'ret_6m'])
df = df[(df['ret_6m'] >= -BAND) & (df['ret_6m'] <= BAND)].copy()
print(f"  Após filtros TV: {len(df)} acções")

# ── JUNTAR DADOS 12M ATRÁS ────────────────────────────────────────────────────
df = df.join(lag, on='ticker', how='left')

# ── CALCULAR CRESCIMENTOS (igual ao backtest: base > 0) ───────────────────────
df['nm_growth']  = np.where(df['net_margin_1y'] > 0,
                             df['nm_now']  / df['net_margin_1y']  - 1, np.nan)
df['fcf_growth'] = np.where(df['fcf_margin_1y'] > 0,
                             df['fcf_now'] / df['fcf_margin_1y'] - 1, np.nan)

matched = df[['net_margin_1y','fcf_margin_1y']].notna().all(axis=1).sum()
print(f"  Match TV↔Sharadar: {matched}/{len(df)} ({matched/len(df)*100:.0f}%)")

# ── RANKINGS ──────────────────────────────────────────────────────────────────
def winsor(s):
    lo, hi = s.quantile(0.01), s.quantile(0.99)
    return s.clip(lo, hi)

def rnk(s):
    return winsor(s.replace([np.inf, -np.inf], np.nan)).rank(pct=True)

df['roic_r']      = rnk(df['roic_tv'])
df['fcf_lvl_r']   = rnk(df['fcf_now'])
df['nm_growth_r']  = rnk(df['nm_growth'])  if df['nm_growth'].notna().sum()  > 10 else pd.Series(0.5, index=df.index)
df['fcf_growth_r'] = rnk(df['fcf_growth']) if df['fcf_growth'].notna().sum() > 10 else pd.Series(0.5, index=df.index)

df['composite'] = (df['roic_r'].fillna(0.5) +
                   df['nm_growth_r'].fillna(0.5) +
                   df['fcf_growth_r'].fillna(0.5) +
                   df['fcf_lvl_r'].fillna(0.5)) / 4

df = df.sort_values('composite', ascending=False).reset_index(drop=True)
total_eligible = len(df)

# ── CONSTRUIR JSON ─────────────────────────────────────────────────────────────
TOP_N    = 10
selected = set(df.head(TOP_N)['ticker'].tolist())

top20_data = []
for _, row in df.head(20).iterrows():
    tk  = row['ticker']
    entry = {
        "rank":           len(top20_data) + 1,
        "ticker":         tk,
        "name":           str(row.get('name', tk)),
        "sector":         str(row.get('sector', '')),
        "roic":           round(float(row['roic_r']), 3)        if pd.notna(row['roic_r'])       else None,
        "nm_growth":      round(float(row['nm_growth_r']), 3)   if pd.notna(row['nm_growth_r'])  else None,
        "fcf_growth":     round(float(row['fcf_growth_r']), 3)  if pd.notna(row['fcf_growth_r']) else None,
        "fcf_lvl":        round(float(row['fcf_lvl_r']), 3)     if pd.notna(row['fcf_lvl_r'])    else None,
        "composite":      round(float(row['composite']), 3),
        "ret_6m":         round(float(row['ret_6m']), 1)         if pd.notna(row['ret_6m'])       else None,
        "mcap_b":         round(float(row['mcap']) / 1e9, 1)     if pd.notna(row.get('mcap'))     else None,
        "roic_pct":       round(float(row['roic_tv']), 1)        if pd.notna(row['roic_tv'])      else None,
        "fcf_margin_pct": round(float(row['fcf_now_pct']), 1)   if pd.notna(row.get('fcf_now_pct')) else None,
        "nm_growth_pct":  round(float(row['nm_growth']) * 100, 1)  if pd.notna(row.get('nm_growth'))  else None,
        "fcf_growth_pct": round(float(row['fcf_growth']) * 100, 1) if pd.notna(row.get('fcf_growth')) else None,
        "selected":       tk in selected,
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

# ── PORTFOLIO TRACKER (entry prices + stop losses) ────────────────────────────
PORTFOLIO_PATH = os.path.join(SITE_DIR, 'coiled-spring-portfolio.json')

try:
    with open(PORTFOLIO_PATH) as f:
        existing_portfolio = json.load(f)
    existing_holdings = {h['ticker']: h for h in existing_portfolio.get('holdings', [])}
    last_rebalance_month = existing_portfolio.get('last_rebalance', '')[:7]
except (FileNotFoundError, json.JSONDecodeError):
    existing_holdings = {}
    last_rebalance_month = ''

current_month   = datetime.now().strftime('%Y-%m')
is_new_month    = current_month != last_rebalance_month

# Score lookup for current signal (all universe tickers)
score_lookup  = df.set_index('ticker')['composite'].to_dict()
name_lookup   = df.set_index('ticker')['name'].to_dict() if 'name' in df.columns else {}
sector_lookup = df.set_index('ticker')['sector'].to_dict() if 'sector' in df.columns else {}

if is_new_month:
    # ── NEW MONTH: rebalance — new top 10, fetch entry prices for new tickers ──
    print(f"New month detected ({current_month}). Rebalancing portfolio...")
    new_tickers = [s['ticker'] for s in portfolio]
    new_entries = [t for t in new_tickers if t not in existing_holdings]

    entry_prices = {}
    if new_entries:
        print(f"  Fetching entry prices for {len(new_entries)} new position(s): {new_entries}")
        try:
            ep_dl = yf.download(new_entries, period='1d', progress=False, auto_adjust=True)
            for t in new_entries:
                try:
                    if len(new_entries) == 1:
                        entry_prices[t] = float(ep_dl['Close'].dropna().iloc[-1])
                    else:
                        entry_prices[t] = float(ep_dl['Close'][t].dropna().iloc[-1])
                except Exception:
                    entry_prices[t] = None
        except Exception as e:
            print(f"  Warning: could not fetch entry prices: {e}")

    holdings = []
    for tk in new_tickers:
        if tk in existing_holdings:
            h = existing_holdings[tk].copy()
        else:
            ep = entry_prices.get(tk)
            h = {
                'ticker':        tk,
                'name':          name_lookup.get(tk, tk),
                'sector':        sector_lookup.get(tk, ''),
                'entry_date':    output['date'],
                'entry_price':   round(ep, 2) if ep else None,
                'stop_loss':     round(ep * 0.75, 2) if ep else None,
                'current_price': round(ep, 2) if ep else None,
            }
        h['score']      = round(float(score_lookup.get(tk, 0)), 3)
        h['score_exit'] = h['score'] < 0.40
        cp = h.get('current_price'); sl = h.get('stop_loss')
        if cp and sl:
            h['stop_triggered'] = cp <= sl
            h['pct_from_stop']  = round((cp / sl - 1) * 100, 1)
        else:
            h['stop_triggered'] = False
            h['pct_from_stop']  = None
        holdings.append(h)

    last_rebalance_date = output['date']
else:
    # ── SAME MONTH: keep existing portfolio, only refresh scores ─────────────
    print(f"Same month ({current_month}). Keeping portfolio, refreshing scores only...")
    holdings = []
    for h in existing_portfolio.get('holdings', []):
        h = h.copy()
        tk = h['ticker']
        if tk in score_lookup:
            h['score']      = round(float(score_lookup[tk]), 3)
            h['score_exit'] = h['score'] < 0.40
        holdings.append(h)
    last_rebalance_date = existing_portfolio.get('last_rebalance', output['date'])

portfolio_output = {
    'last_rebalance': last_rebalance_date,
    'updated':        output['date'],
    'holdings':       holdings,
}
with open(PORTFOLIO_PATH, 'w') as f:
    json.dump(portfolio_output, f, indent=2)
print(f"Saved: {PORTFOLIO_PATH}")

# ── PRINT ──────────────────────────────────────────────────────────────────────
print(f"\n{'='*112}")
print(f"  COILED SPRING v3 — {output['date']} — {regime.upper()}")
print(f"  S&P: {sp_last:,.0f} | MA225: {sp_ma225:,.0f} | Elegíveis: {total_eligible}")
print(f"{'='*112}")
print(f"  {'#':>2}  {'':>4} {'Ticker':<7} {'Nome':<28} {'Sector':<20} {'ROIC':>6} {'NMg':>6} {'FCFg':>6} {'FCFl':>6}  {'Score':>6}  {'MCap':>7}  {'Ret6m':>7}")
print(f"  {'-'*110}")
for s in top20_data:
    sel = ">>>" if s['selected'] else ""
    def f(v): return f"{v:.3f}" if v is not None else "  — "
    print(f"  {s['rank']:2d}  {sel:>4} {s['ticker']:<7} {s['name'][:27]:<28} {s['sector'][:19]:<20} "
          f"{f(s['roic']):>6} {f(s['nm_growth']):>6} {f(s['fcf_growth']):>6} {f(s['fcf_lvl']):>6}  "
          f"{f(s['composite']):>6}  ${s['mcap_b']:>5.0f}B  {s['ret_6m']:>+6.1f}%")
print(f"\n  >>> = Seleccionado (Top {TOP_N})")
