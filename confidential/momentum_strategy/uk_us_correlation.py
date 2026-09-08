#!/usr/bin/env python3
"""
UK vs US Optimal Momentum — Correlation & Regime Analysis

UK:  100% 6M, £250M mcap, EBIT>0, FTSE MA200, cash when OUT, top 7
US:  50%6M+50%12M, $10B mcap, EBIT>0, S&P MA250, cash when OUT, top 7
"""

import os, json, sys
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# ── US strategy (mom_engine) ───────────────────────────────────────────────────
sys.path.insert(0, '/Users/luisabrantes/sharadar')
os.chdir('/Users/luisabrantes/sharadar')
from mom_engine import build_data

LSE_DIR    = '/Users/luisabrantes/eodhd_data/LSE'
PRICES_DIR = os.path.join(LSE_DIR, 'prices')
FUND_DIR   = os.path.join(LSE_DIR, 'fundamentals')
TICKERS_F  = os.path.join(LSE_DIR, 'tickers.parquet')

START = '2005-01'
END   = '2026-06'


# ─── US monthly returns ────────────────────────────────────────────────────────

def run_us(data, start=START, end=END):
    pm      = data['pm']
    mc      = data['mc']
    eb      = data['eb']
    sp500   = data['sp500']
    CW      = {6: 0.5, 12: 0.5}
    TOP_N   = 7
    MA      = 250
    MIN_MC  = 10e9

    months = pm.index[(pm.index >= pd.Period(start,'M')) &
                      (pm.index <= pd.Period(end,  'M'))]

    rets, dates, in_equity = [], [], []

    for i, m in enumerate(months):
        m_idx = pm.index.get_loc(m)
        if m_idx + 1 >= len(pm.index): break
        next_m = pm.index[m_idx + 1]
        dates.append(m)

        # Regime
        end_d = m.to_timestamp(how='end')
        hist  = sp500.loc[:end_d].tail(MA + 1)
        regime_ok = len(hist) >= MA and float(hist.iloc[-1]) >= float(hist.tail(MA).mean())

        if not regime_ok:
            rets.append(0.0); in_equity.append(False); continue

        mom = pd.Series(0.0, index=pm.columns)
        for lb, wt in CW.items():
            if m_idx - lb < 0: continue
            ret = pm.loc[m] / pm.loc[pm.index[m_idx - lb]] - 1
            mom = mom.add(ret * wt, fill_value=0)

        mask = (mc.loc[m] >= MIN_MC) & (pm.loc[m] > 0) & mom.notna() & (eb.loc[m] > 0)
        eligible = mom[mask]
        if eligible.empty:
            rets.append(0.0); in_equity.append(False); continue

        selected = eligible.nlargest(TOP_N).index.tolist()
        fwd = (pm.loc[next_m, selected] / pm.loc[m, selected] - 1).dropna()
        rets.append(float(fwd.mean()) if len(fwd) > 0 else 0.0)
        in_equity.append(True)

    return pd.Series(rets, index=dates), pd.Series(in_equity, index=dates)


# ─── UK monthly returns ────────────────────────────────────────────────────────

def load_uk_tickers():
    t = pd.read_parquet(TICKERS_F)
    gbx = []
    for tkr in t[t['Type'] == 'Common Stock']['Code'].tolist():
        path = os.path.join(FUND_DIR, f'{tkr}.json')
        if not os.path.exists(path): continue
        try:
            with open(path) as f:
                d = json.load(f)
            if d.get('General', {}).get('CurrencyCode') == 'GBX':
                gbx.append(tkr)
        except: pass
    return gbx

def load_uk_prices(tickers):
    frames = []
    for tkr in tickers:
        path = os.path.join(PRICES_DIR, f'{tkr}.parquet')
        if not os.path.exists(path): continue
        try:
            df = pd.read_parquet(path, columns=['adjusted_close'])
            df.index = pd.to_datetime(df.index)
            df = df[df['adjusted_close'] > 0].rename(columns={'adjusted_close': tkr})
            frames.append(df)
        except: pass
    daily = pd.concat(frames, axis=1).sort_index()
    eom = daily.resample('ME').last()
    eom.index = eom.index.to_period('M')
    return eom.sort_index()

def load_uk_fundamentals(tickers, pm_index):
    shares_by_ticker, ebit_records = {}, []
    for tkr in tickers:
        path = os.path.join(FUND_DIR, f'{tkr}.json')
        if not os.path.exists(path): continue
        try:
            with open(path) as f: d = json.load(f)
            sh = {}
            for e in d.get('outstandingShares',{}).get('annual',{}).values():
                try:
                    yr = int(e['date']); s = e.get('shares',0)
                    if s: sh[yr] = int(s)
                except: pass
            if sh: shares_by_ticker[tkr] = sh
            qtrs = d.get('Financials',{}).get('Income_Statement',{}).get('quarterly',{})
            rows = []
            for v in qtrs.values():
                try:
                    eb = v.get('ebit')
                    if eb is not None: rows.append({'period_end': pd.Timestamp(v['date']), 'ebit': float(eb)})
                except: pass
            if len(rows) >= 4:
                qdf = pd.DataFrame(rows).sort_values('period_end').set_index('period_end')
                qdf['ebit_ttm'] = qdf['ebit'].rolling(4, min_periods=4).sum()
                qdf = qdf.dropna(subset=['ebit_ttm'])
                for idx, row in qdf.iterrows():
                    ebit_records.append({'ticker': tkr, 'avail_date': idx + pd.Timedelta(days=45), 'ebit_ttm': row['ebit_ttm']})
        except: pass

    if ebit_records:
        edf = pd.DataFrame(ebit_records)
        edf['ym'] = pd.to_datetime(edf['avail_date']).dt.to_period('M')
        ebit_panel = (edf.pivot_table(index='ym', columns='ticker', values='ebit_ttm', aggfunc='last')
                        .sort_index().reindex(pm_index).ffill(limit=4))
    else:
        ebit_panel = pd.DataFrame(index=pm_index)
    return shares_by_ticker, ebit_panel

def build_uk_mcap(pm, shares_by_ticker):
    mcap = pd.DataFrame(np.nan, index=pm.index, columns=pm.columns)
    for tkr, yr_sh in shares_by_ticker.items():
        if tkr not in pm.columns: continue
        yrs = sorted(yr_sh.keys())
        for period in pm.index:
            price = pm.at[period, tkr]
            if pd.isna(price) or price <= 0: continue
            yr = period.year
            sh = yr_sh.get(yr)
            if sh is None:
                prior = [y for y in yrs if y <= yr]
                sh = yr_sh[prior[-1]] if prior else None
            if sh: mcap.at[period, tkr] = price * sh / 100
    return mcap

def run_uk(pm, mcap_panel, ebit_panel, ftse100, start=START, end=END):
    import yfinance as yf
    ftse_eom = ftse100.resample('ME').last()
    ftse_eom.index = ftse_eom.index.to_period('M')

    MIN_MC = 250e6
    TOP_N  = 7
    MA     = 200

    months = pm.index[(pm.index >= pd.Period(start,'M')) &
                      (pm.index <= pd.Period(end,  'M'))]

    rets, dates, in_equity = [], [], []

    for m in months:
        m_idx = pm.index.get_loc(m)
        if m_idx + 1 >= len(pm.index): break
        next_m = pm.index[m_idx + 1]
        dates.append(m)

        end_d = m.to_timestamp(how='end')
        hist  = ftse100.loc[:end_d].tail(MA + 1)
        regime_ok = len(hist) >= MA and float(hist.iloc[-1]) >= float(hist.tail(MA).mean())

        if not regime_ok:
            rets.append(0.0); in_equity.append(False); continue

        mom = pd.Series(0.0, index=pm.columns)
        if m_idx - 6 >= 0:
            mom = pm.loc[m] / pm.loc[pm.index[m_idx - 6]] - 1

        mask = mom.notna() & (pm.loc[m] > 0)
        if m in mcap_panel.index: mask &= (mcap_panel.loc[m] >= MIN_MC)
        if m in ebit_panel.index: mask &= (ebit_panel.loc[m] > 0)
        eligible = mom[mask]

        if eligible.empty:
            rets.append(0.0); in_equity.append(False); continue

        selected = eligible.nlargest(TOP_N).index.tolist()
        fwd = (pm.loc[next_m, selected] / pm.loc[m, selected] - 1).dropna()
        rets.append(float(fwd.mean()) if len(fwd) > 0 else 0.0)
        in_equity.append(True)

    return pd.Series(rets, index=dates), pd.Series(in_equity, index=dates)


# ─── Analysis ─────────────────────────────────────────────────────────────────

def sharpe(r):
    r = np.array(r)
    if len(r) < 6 or np.std(r) == 0: return 0.0
    rf = 0.03/12
    return (np.mean(r) - rf) / np.std(r, ddof=1) * np.sqrt(12)

def cagr(r):
    r = np.array(r)
    if len(r) == 0: return 0.0
    return np.cumprod(1+r)[-1]**(12/len(r)) - 1

def maxdd(r):
    cum = np.cumprod(1 + np.array(r))
    peak = np.maximum.accumulate(cum)
    return ((cum - peak)/peak).min()

def print_stats(label, r):
    r = np.array(r)
    if len(r) == 0: return
    print(f"  {label:<30}  CAGR {cagr(r)*100:>+6.1f}%   Sharpe {sharpe(r):>5.2f}   MaxDD {maxdd(r)*100:>6.1f}%   n={len(r)}")

def corr_label(c):
    if c > 0.7: return "high"
    if c > 0.4: return "moderate"
    if c > 0.2: return "low"
    return "very low"


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Loading US data...")
    us_data = build_data()

    print("Loading UK data...")
    tickers = load_uk_tickers()
    pm_uk   = load_uk_prices(tickers)
    sh, ep  = load_uk_fundamentals(tickers, pm_uk.index)
    mc_uk   = build_uk_mcap(pm_uk, sh)
    import yfinance as yf
    ftse = yf.download('^FTSE', start='1999-01-01', progress=False)['Close'].squeeze().dropna()
    ftse.index = pd.to_datetime(ftse.index)

    print("Running strategies...")
    us_rets, us_eq = run_us(us_data)
    uk_rets, uk_eq = run_uk(pm_uk, mc_uk, ep, ftse)

    # Align
    idx = us_rets.index.intersection(uk_rets.index)
    us_r = us_rets[idx]; us_e = us_eq[idx]
    uk_r = uk_rets[idx]; uk_e = uk_eq[idx]

    W = 80
    print(f"\n{'='*W}")
    print(f"  UK vs US Optimal Momentum  —  {idx[0]} → {idx[-1]}  ({len(idx)} months)")
    print(f"{'='*W}")

    # Overall stats
    print("\n  OVERALL")
    print_stats("UK  (6M, £250M, EBIT, MA200)", uk_r)
    print_stats("US  (6+12M, $10B, EBIT, MA250)", us_r)
    equal_weight = (uk_r.values + us_r.values) / 2
    print_stats("Combined 50/50", equal_weight)

    # Correlation
    corr_all = np.corrcoef(uk_r, us_r)[0,1]
    print(f"\n  Correlation (all months):   {corr_all:+.3f}  [{corr_label(corr_all)}]")

    # Equity-only correlation
    both_eq = us_e & uk_e
    if both_eq.sum() > 12:
        c_eq = np.corrcoef(uk_r[both_eq], us_r[both_eq])[0,1]
        print(f"  Correlation (equity months only): {c_eq:+.3f}  [{corr_label(c_eq)}]  n={both_eq.sum()}")

    # ── Regime breakdown ──────────────────────────────────────────────────────
    print(f"\n{'─'*W}")
    print("  REGIME BREAKDOWN")
    print(f"{'─'*W}")

    both_eq_mask   = us_e & uk_e
    us_out_uk_eq   = ~us_e & uk_e
    uk_out_us_eq   = us_e & ~uk_e
    both_out       = ~us_e & ~uk_e

    scenarios = [
        ("Both IN equities",     both_eq_mask),
        ("US OUT, UK IN",        us_out_uk_eq),
        ("UK OUT, US IN",        uk_out_us_eq),
        ("Both OUT (cash)",      both_out),
    ]

    print(f"\n  {'Scenario':<28} {'Months':>6}  {'% time':>6}  {'UK CAGR':>8}  {'US CAGR':>8}  {'50/50 CAGR':>10}  {'Corr':>6}")
    print(f"  {'-'*W}")
    for label, mask in scenarios:
        n = mask.sum()
        if n == 0:
            print(f"  {label:<28} {n:>6}  {'0%':>6}")
            continue
        pct = n / len(idx) * 100
        uk_s  = uk_r[mask].values
        us_s  = us_r[mask].values
        ew    = (uk_s + us_s) / 2
        c     = np.corrcoef(uk_s, us_s)[0,1] if n >= 6 else float('nan')
        print(f"  {label:<28} {n:>6}  {pct:>5.0f}%  {cagr(uk_s)*100:>+7.1f}%  {cagr(us_s)*100:>+7.1f}%  {cagr(ew)*100:>+9.1f}%  {c:>+6.3f}")

    # ── Equity months correlation detail ──────────────────────────────────────
    print(f"\n{'─'*W}")
    print("  EQUITY MONTHS DETAIL  (both IN equities)")
    print(f"{'─'*W}")
    n_eq = both_eq_mask.sum()
    uk_eq_r = uk_r[both_eq_mask].values
    us_eq_r = us_r[both_eq_mask].values
    ew_eq   = (uk_eq_r + us_eq_r) / 2

    # Rolling 12-month correlation
    uk_eq_s = pd.Series(uk_eq_r)
    us_eq_s = pd.Series(us_eq_r)
    roll_corr = uk_eq_s.rolling(24).corr(us_eq_s).dropna()

    print(f"\n  n = {n_eq} months")
    print(f"  Rolling 24M corr — mean: {roll_corr.mean():+.3f}  min: {roll_corr.min():+.3f}  max: {roll_corr.max():+.3f}")

    # Worst months alignment
    uk_worst = set(uk_eq_r.argsort()[:10])
    us_worst = set(us_eq_r.argsort()[:10])
    overlap = len(uk_worst & us_worst)
    print(f"  Top-10 worst months overlap: {overlap}/10  (both crash together)")

    # Combined equity stats
    print(f"\n  When both in equities:")
    print_stats("  UK", uk_eq_r)
    print_stats("  US", us_eq_r)
    print_stats("  50/50", ew_eq)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*W}")
    print("  SUMMARY")
    print(f"{'='*W}")
    print(f"  Both OUT simultaneously: {both_out.sum()} months ({both_out.sum()/len(idx)*100:.0f}% of time)")
    print(f"  Only US out:             {uk_out_us_eq.sum()} months")
    print(f"  Only UK out:             {us_out_uk_eq.sum()} months")
    print(f"  Correlation all months:  {corr_all:+.3f}  → diversification {'good' if corr_all < 0.5 else 'limited'}")
    ew_all = (uk_r.values + us_r.values) / 2
    print(f"\n  50/50 combined portfolio:")
    print_stats("  ", ew_all)

if __name__ == '__main__':
    main()
