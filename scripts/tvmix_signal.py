#!/usr/bin/env python3
"""
TV-Mix Signal Generator (2026-09-10) -- Trending Value US, duas pernas.

Estrategia (backtest: ~/trending_value_us/, auditoria hostil em 06_audit_hostil.py):
  - Universo: US primary common stocks, mcap >= $500M, ADV >= $2M, preco > $1
  - Composito de valor (percentis, media): P/E, P/B, P/S, EV/EBITDA, EV/FCF.
    Denominador <= 0 -> percentil 1.0 (mais caro). Metricas em falta -> 0.5 (neutro);
    exige >= 3 metricas validas. Yield (dividendos/recompras) testado e REMOVIDO:
    nao acrescentava retorno e tornava a superficie de parametros irregular.
  - PERNA CLASSICA (TV-C): 5% mais baratos -> 5 com melhor momentum 12M
  - PERNA INVERSA  (TV-M): 30% melhor momentum 12M -> 5 mais baratas
  - Carteira: as 10 juntas, equal weight (nome repetido = peso duplo)
  - Regime: S&P 500 vs MA200 (dias de negociacao) -> 100% cash abaixo
  - Rebalance mensal, execucao no dia util seguinte ao sinal

Backtest 2005-2026 (diario, custos 20bps rt, N=5/perna): CAGR 16,8% | Sharpe 0,83 | MaxDD -33,1%
NOTA: estrategia NOVA, sem holdout selado e sem track record real. Publicada
para verificacao/monitorizacao, nao como recomendacao.

Guarda: tvmix-data.json, tvmix-portfolio.json
"""
import os, json, sys
from datetime import datetime, date
import pandas as pd
import numpy as np
from tradingview_screener import Query, col

SITE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(SITE_DIR, "tvmix-data.json")
PORT_PATH = os.path.join(SITE_DIR, "tvmix-portfolio.json")

CHEAP_PCT, MOM_PCT, N_PER_LEG = 0.05, 0.30, 5
MIN_MCAP, MIN_ADV = 500e6, 2e6


def fetch_universe():
    q = (Query()
         .select('name','description','market_cap_basic','sector','close',
                 'Perf.Y','price_earnings_ttm','price_book_fq','price_sales_current',
                 'enterprise_value_ebitda_ttm','enterprise_value_fq','free_cash_flow_ttm',
                 'average_volume_10d_calc')
         .where(col('market_cap_basic') > MIN_MCAP,
                col('is_primary') == True,
                col('type') == 'stock',
                col('typespecs').has('common'))
         .set_markets('america').order_by('market_cap_basic', ascending=False)
         .limit(5000).get_scanner_data())
    _, df = q
    us = ('NASDAQ:','NYSE:','AMEX:','NYSE ARCA:')
    df = df[df['ticker'].str.startswith(us)].copy()
    df['exchange'] = df['ticker'].str.split(':').str[0]
    df['ticker'] = df['ticker'].str.split(':').str[-1]
    df['name'] = df['description'].astype(str)
    df['adv'] = df['average_volume_10d_calc'] * df['close']
    df = df[(df.adv >= MIN_ADV) & (df.close > 1)]
    return df.dropna(subset=['Perf.Y']).reset_index(drop=True)


def value_composite(df):
    """percentis: menor = mais barato. den<=0 -> 1.0 (caro). ausente -> 0.5."""
    out = {}
    def cheap(series, positive_only=True):
        s = pd.to_numeric(series, errors='coerce')
        s = s.where(s > 0) if positive_only else s
        r = s.rank(pct=True)
        return r.where(s.notna(), np.nan), s
    for lbl, s in (('pe', df['price_earnings_ttm']), ('pb', df['price_book_fq']),
                   ('ps', df['price_sales_current']), ('evebitda', df['enterprise_value_ebitda_ttm'])):
        r, raw = cheap(s)
        out[lbl] = r.where(raw.notna(), np.where(pd.to_numeric(s, errors='coerce').notna(), 1.0, np.nan))
    evfcf = pd.to_numeric(df['enterprise_value_fq'], errors='coerce') / pd.to_numeric(df['free_cash_flow_ttm'], errors='coerce')
    r, raw = cheap(evfcf)
    out['evfcf'] = r.where(raw.notna(), np.where(evfcf.notna(), 1.0, np.nan))
    M = pd.DataFrame(out)
    nval = M.notna().sum(axis=1)
    comp = M.fillna(0.5).mean(axis=1).where(nval >= 3)
    return comp, M


def regime_on():
    import yfinance as yf, warnings
    warnings.filterwarnings('ignore')
    h = yf.Ticker('^GSPC').history(period='2y')['Close']
    ma = h.rolling(200).mean()
    return bool(h.iloc[-1] > ma.iloc[-1]), float(h.iloc[-1]), float(ma.iloc[-1])


def main():
    df = fetch_universe()
    comp, M = value_composite(df)
    df['composite'] = comp
    d = df.dropna(subset=['composite']).copy()
    d['mom12'] = pd.to_numeric(d['Perf.Y'], errors='coerce')/100
    d = d.dropna(subset=['mom12'])

    cheap_cut = d.composite.quantile(CHEAP_PCT)
    classic = d[d.composite <= cheap_cut].nlargest(N_PER_LEG, 'mom12')
    mom_cut = d.mom12.quantile(1-MOM_PCT)
    inverse = d[d.mom12 >= mom_cut].nsmallest(N_PER_LEG, 'composite')

    on, spx, spx_ma = regime_on()
    def rows(sub, leg):
        return [dict(ticker=r.ticker, name=r['name'], sector=r.sector, leg=leg,
                     price=round(float(r.close),2), mcap_musd=round(float(r.market_cap_basic)/1e6),
                     mom12_pct=round(float(r.mom12)*100,1), value_pct=round(float(r.composite)*100,1),
                     adv_musd=round(float(r.adv)/1e6,1))
                for _, r in sub.iterrows()]
    cl, inv = rows(classic,'classic'), rows(inverse,'inverse')
    both = sorted({x['ticker'] for x in cl} & {x['ticker'] for x in inv})
    allp = cl + inv
    # peso: cada slot vale 1/len(allp); nome repetido acumula (peso duplo) e a soma fica 1.0
    w = {}
    for p in allp: w[p['ticker']] = w.get(p['ticker'],0) + 1/len(allp)
    # lista de holdings UNICOS para o portfolio json (sem duplicar linhas)
    seen = set(); uniq = []
    for p in allp:
        if p['ticker'] in seen: continue
        seen.add(p['ticker'])
        q = dict(p); q['weight'] = round(w[p['ticker']],4)
        q['legs'] = 'both' if p['ticker'] in both else p['leg']
        uniq.append(q)
    for p in allp: p['weight'] = round(w[p['ticker']],4)

    payload = dict(
        strategy="TV-Mix (Trending Value US, duas pernas)", updated=datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        signal_date=date.today().isoformat(), regime=('invested' if on else 'cash'),
        spx=round(spx,1), spx_ma200=round(spx_ma,1),
        universe_size=int(len(d)), cheap_cut_pct=round(float(cheap_cut)*100,1),
        mom_cut_pct=round(float(mom_cut)*100,1),
        overlap=both, legs=dict(classic=cl, inverse=inv),
        note="Estrategia nova (2026-09-10), sem holdout selado nem track record. Backtest 2005-2026: CAGR 16,8%, Sharpe 0,83, MaxDD -33,1%.")
    json.dump(payload, open(DATA_PATH,'w'), indent=1)
    json.dump(dict(updated=payload['updated'], regime=payload['regime'],
                   holdings=uniq), open(PORT_PATH,'w'), indent=1)
    print(f"universo elegivel: {len(d)} | regime: {payload['regime']} (SPX {spx:.0f} vs MA200 {spx_ma:.0f})")
    print(f"corte valor: percentil {CHEAP_PCT*100:.0f}% | corte momentum: top {MOM_PCT*100:.0f}%")
    print(f"\nPERNA CLASSICA ({CHEAP_PCT*100:.0f}% mais baratos -> {N_PER_LEG} melhor momentum):")
    for p in cl: print(f"  {p['ticker']:>6} {p['name'][:28]:<28} mom12 {p['mom12_pct']:>7.1f}% | valor pct {p['value_pct']:>5.1f} | mcap ${p['mcap_musd']:,}M")
    print(f"\nPERNA INVERSA (top {MOM_PCT*100:.0f}% momentum -> {N_PER_LEG} mais baratas):")
    for p in inv: print(f"  {p['ticker']:>6} {p['name'][:28]:<28} mom12 {p['mom12_pct']:>7.1f}% | valor pct {p['value_pct']:>5.1f} | mcap ${p['mcap_musd']:,}M")
    print(f"\nsobreposicao entre pernas: {both if both else 'nenhuma'}")
    print(f"guardado: {DATA_PATH}, {PORT_PATH}")

if __name__ == '__main__':
    main()
