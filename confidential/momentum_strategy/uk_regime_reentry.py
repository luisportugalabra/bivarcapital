#!/usr/bin/env python3
"""
UK Momentum — Asymmetric Regime Filter Test

Standard: FTSE >= MA200 → equity, else cash
Modified: also re-enter when FTSE is X% BELOW MA200 (deep dip / oversold)

Logic:
  - regime = OK  if FTSE >= MA200  (normal momentum)
  - regime = OK  if FTSE < MA200 AND FTSE <= MA200 * (1 - X/100)  (deep dip re-entry)
  - regime = CASH otherwise (below MA but not deep enough)

Tests X in [3%, 5%, 8%, 10%, 12%, 15%, 20%]
Baseline: standard MA200 (no re-entry)
"""

import os, json
import pandas as pd
import numpy as np

LSE_DIR    = '/Users/luisabrantes/eodhd_data/LSE'
PRICES_DIR = os.path.join(LSE_DIR, 'prices')
FUND_DIR   = os.path.join(LSE_DIR, 'fundamentals')
TICKERS_F  = os.path.join(LSE_DIR, 'tickers.parquet')

TOP_N             = 7
COMPOSITE_WEIGHTS = {6: 1.0}
MIN_MCAP          = 250e6
MA_PERIOD         = 200
START             = '2001-01'
END               = '2026-07'


def load_tickers():
    t = pd.read_parquet(TICKERS_F)
    common = t[t['Type'] == 'Common Stock']['Code'].tolist()
    gbx = []
    for tkr in common:
        path = os.path.join(FUND_DIR, f'{tkr}.json')
        if not os.path.exists(path): continue
        try:
            with open(path) as f: d = json.load(f)
            if d.get('General', {}).get('CurrencyCode') == 'GBX':
                gbx.append(tkr)
        except: pass
    return gbx

def load_prices(tickers):
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

def load_fundamentals(tickers, pm_index):
    shares_by_ticker = {}
    ebit_records = []
    for tkr in tickers:
        path = os.path.join(FUND_DIR, f'{tkr}.json')
        if not os.path.exists(path): continue
        try:
            with open(path) as f: d = json.load(f)
            annual_shares = {}
            for entry in d.get('outstandingShares', {}).get('annual', {}).values():
                try:
                    yr = int(entry['date']); sh = entry.get('shares', 0)
                    if sh: annual_shares[yr] = int(sh)
                except: pass
            if annual_shares: shares_by_ticker[tkr] = annual_shares

            qtrs = d.get('Financials', {}).get('Income_Statement', {}).get('quarterly', {})
            rows = []
            for v in qtrs.values():
                try:
                    ebit = v.get('ebit')
                    if ebit is not None:
                        rows.append({'period_end': pd.Timestamp(v['date']), 'ebit': float(ebit)})
                except: pass
            if len(rows) >= 4:
                qdf = pd.DataFrame(rows).sort_values('period_end').set_index('period_end')
                qdf['ebit_ttm'] = qdf['ebit'].rolling(4, min_periods=4).sum()
                qdf = qdf.dropna(subset=['ebit_ttm'])
                for idx, row in qdf.iterrows():
                    ebit_records.append({'ticker': tkr,
                                         'avail_date': idx + pd.Timedelta(days=45),
                                         'ebit_ttm': row['ebit_ttm']})
        except: pass

    if ebit_records:
        edf = pd.DataFrame(ebit_records)
        edf['ym'] = pd.to_datetime(edf['avail_date']).dt.to_period('M')
        ebit_panel = (edf.pivot_table(index='ym', columns='ticker', values='ebit_ttm', aggfunc='last')
                        .sort_index().reindex(pm_index).ffill(limit=4))
    else:
        ebit_panel = pd.DataFrame(index=pm_index)
    return shares_by_ticker, ebit_panel

def build_mcap_panel(pm, shares_by_ticker):
    mcap = pd.DataFrame(np.nan, index=pm.index, columns=pm.columns)
    for tkr, yr_shares in shares_by_ticker.items():
        if tkr not in pm.columns: continue
        yrs = sorted(yr_shares.keys())
        for period in pm.index:
            price = pm.at[period, tkr]
            if pd.isna(price) or price <= 0: continue
            yr = period.year
            sh = yr_shares.get(yr)
            if sh is None:
                prior = [y for y in yrs if y <= yr]
                sh = yr_shares[prior[-1]] if prior else None
            if sh: mcap.at[period, tkr] = price * sh / 100
    return mcap

def load_ftse100():
    import yfinance as yf, warnings
    warnings.filterwarnings('ignore')
    data = yf.download('^FTSE', start='1999-01-01', progress=False)
    s = data['Close'].squeeze().dropna()
    s.index = pd.to_datetime(s.index)
    return s

def regime_ok(ftse_daily, month, ma_period, reentry_pct=None):
    """
    Returns True if strategy should be invested.
    reentry_pct: if set, also invest when FTSE <= MA * (1 - reentry_pct/100)
    """
    if ma_period == 0: return True
    end = month.to_timestamp(how='end')
    hist = ftse_daily.loc[:end].tail(ma_period + 1)
    if len(hist) < ma_period: return True
    ftse_now = float(hist.iloc[-1])
    ma_now   = float(hist.tail(ma_period).mean())

    if ftse_now >= ma_now:
        return True  # normal momentum regime

    if reentry_pct is not None:
        threshold = ma_now * (1 - reentry_pct / 100)
        if ftse_now <= threshold:
            return True  # deep dip — re-enter

    return False  # below MA but not deep enough → stay cash


def run(pm, mcap_panel, ebit_panel, ftse_daily, ftse_eom, reentry_pct=None):
    months = pm.index[(pm.index >= pd.Period(START,'M')) &
                      (pm.index <= pd.Period(END,  'M'))]
    strat_rets, bm_rets = [], []
    regime_log = []

    for i, m in enumerate(months):
        m_idx = pm.index.get_loc(m)
        if m_idx + 1 >= len(pm.index): break
        next_m = pm.index[m_idx + 1]

        bm_ret = (float(ftse_eom[next_m] / ftse_eom[m] - 1)
                  if (m in ftse_eom.index and next_m in ftse_eom.index) else 0.0)
        bm_rets.append(bm_ret)

        ok = regime_ok(ftse_daily, m, MA_PERIOD, reentry_pct)
        regime_log.append(ok)

        if not ok:
            strat_rets.append(0.0); continue

        mom = pd.Series(0.0, index=pm.columns)
        for lb, wt in COMPOSITE_WEIGHTS.items():
            if m_idx - lb < 0: continue
            ret = pm.loc[m] / pm.loc[pm.index[m_idx - lb]] - 1
            mom = mom.add(ret * wt, fill_value=0)

        mask = (mom.notna() & (pm.loc[m] > 0) &
                (mcap_panel.loc[m] >= MIN_MCAP) &
                (ebit_panel.loc[m] > 0))
        eligible = mom[mask]
        if eligible.empty:
            strat_rets.append(0.0); continue

        selected = eligible.nlargest(TOP_N).index.tolist()
        fwd = (pm.loc[next_m, selected] / pm.loc[m, selected] - 1).dropna()
        strat_rets.append(float(fwd.mean()) if len(fwd) > 0 else 0.0)

    r   = np.array(strat_rets)
    bm  = np.array(bm_rets[:len(r)])
    invested = sum(regime_log)
    cash_months = len(regime_log) - invested
    return r, bm, cash_months, len(regime_log)


def stats(r, bm):
    n = len(r); rf_m = 0.03 / 12
    cum  = np.cumprod(1 + r); yrs = n / 12
    cagr = cum[-1] ** (1/yrs) - 1
    bm_cagr = np.cumprod(1 + bm)[-1] ** (1/yrs) - 1
    vol = np.std(r, ddof=1) * np.sqrt(12)
    sharpe = (np.mean(r) - rf_m) / np.std(r, ddof=1) * np.sqrt(12)
    downside = r[r < rf_m] - rf_m
    ds_vol = np.std(downside, ddof=1) * np.sqrt(12) if len(downside) > 1 else vol
    sortino = (np.mean(r) - rf_m) / (ds_vol / np.sqrt(12)) * np.sqrt(12)
    peak = np.maximum.accumulate(cum)
    maxdd = ((cum - peak) / peak).min()
    return {
        'cagr':    round(cagr * 100, 1),
        'alpha':   round((cagr - bm_cagr) * 100, 1),
        'sharpe':  round(sharpe, 2),
        'sortino': round(sortino, 2),
        'maxdd':   round(maxdd * 100, 1),
        'vol':     round(vol * 100, 1),
    }


def main():
    print("Loading data...")
    tickers = load_tickers()
    pm = load_prices(tickers)
    shares, ebit_panel = load_fundamentals(tickers, pm.index)
    mcap_panel = build_mcap_panel(pm, shares)
    ftse_daily = load_ftse100()
    ftse_eom = ftse_daily.resample('ME').last()
    ftse_eom.index = ftse_eom.index.to_period('M')
    print(f"  {len(tickers)} tickers | PM {pm.shape}\n")

    reentry_pcts = [None, 3, 5, 8, 10, 12, 15, 20]

    results = []
    for rp in reentry_pcts:
        r, bm, cash_months, total = run(pm, mcap_panel, ebit_panel, ftse_daily, ftse_eom, rp)
        s = stats(r, bm)
        label = 'Baseline (no re-entry)' if rp is None else f'Re-enter at -{rp}% below MA'
        s['label'] = label
        s['cash_months'] = cash_months
        results.append(s)

    W = 110
    print('=' * W)
    print(f"  UK Momentum — Asymmetric Regime Re-entry Test  (6M, £250M, EBIT>0, MA200, top7)")
    print(f"  Logic: invest if FTSE>=MA200  OR  FTSE <= MA200×(1-X%)  — else cash")
    print('=' * W)
    print(f"  {'Strategy':<30} {'CAGR':>7} {'Alpha':>7} {'Sharpe':>7} {'Sortino':>8} {'MaxDD':>7} {'Vol':>6} {'Cash mo':>8}")
    print(f"  {'-'*W}")
    for s in results:
        print(f"  {s['label']:<30} {s['cagr']:>+6.1f}% {s['alpha']:>+6.1f}% "
              f"{s['sharpe']:>7.2f} {s['sortino']:>8.2f} {s['maxdd']:>6.1f}% "
              f"{s['vol']:>5.1f}% {s['cash_months']:>7}mo")
    print('=' * W)


if __name__ == '__main__':
    main()
