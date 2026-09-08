#!/usr/bin/env python3
"""
UK Optimal Momentum Backtest — EODHD LSE data

Same strategy as US Optimal Momentum:
  - Composite = 50% 6M + 50% 12M return
  - Universe: LSE common stocks (incl. delisted), market cap > £1B, TTM EBIT > 0
  - Top 7 by composite
  - Regime: FTSE 100 < MA250 → cash
  - Monthly rebalance on last trading day of month (evaluated at EOM prices)

Usage: python3 uk_momentum_backtest.py
"""

import os, json
import pandas as pd
import numpy as np

LSE_DIR     = '/Users/luisabrantes/eodhd_data/LSE'
PRICES_DIR  = os.path.join(LSE_DIR, 'prices')
FUND_DIR    = os.path.join(LSE_DIR, 'fundamentals')
TICKERS_F   = os.path.join(LSE_DIR, 'tickers.parquet')

MIN_MCAP_GBP        = 250_000_000     # £250 M  (prices in GBX pence → ÷ 100 = GBP)
TOP_N               = 7
MA_PERIOD           = 200
COMPOSITE_WEIGHTS   = {6: 0.5, 12: 0.5}
START               = '2001-01'
END                 = '2026-07'


# ─── 1. TICKERS ────────────────────────────────────────────────────────────────

def load_tickers():
    t = pd.read_parquet(TICKERS_F)
    # include delisted to reduce survivorship bias
    common = t[t['Type'] == 'Common Stock']['Code'].tolist()
    print(f"  Common stocks (incl. delisted): {len(common)}")

    # Filter to GBX-denominated stocks (true UK-listed equities)
    fund_dir = FUND_DIR
    gbx_tickers = []
    for tkr in common:
        path = os.path.join(fund_dir, f'{tkr}.json')
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                d = json.load(f)
            currency = d.get('General', {}).get('CurrencyCode', '')
            if currency == 'GBX':
                gbx_tickers.append(tkr)
        except Exception:
            pass
    print(f"  GBX-denominated (true UK): {len(gbx_tickers)}")
    return gbx_tickers


# ─── 2. PRICE MATRIX ───────────────────────────────────────────────────────────

def load_prices(tickers):
    print("Loading prices...")
    frames = []
    missing = 0
    for tkr in tickers:
        path = os.path.join(PRICES_DIR, f'{tkr}.parquet')
        if not os.path.exists(path):
            missing += 1
            continue
        try:
            df = pd.read_parquet(path, columns=['adjusted_close'])
            df.index = pd.to_datetime(df.index)
            df = df[df['adjusted_close'] > 0].rename(columns={'adjusted_close': tkr})
            frames.append(df)
        except Exception:
            missing += 1

    print(f"  Loaded {len(frames)} price files  ({missing} missing)")
    if not frames:
        return pd.DataFrame()

    daily = pd.concat(frames, axis=1).sort_index()

    # End-of-month prices
    eom = daily.resample('ME').last()
    eom.index = eom.index.to_period('M')
    return eom.sort_index()


# ─── 3. FUNDAMENTALS ───────────────────────────────────────────────────────────

def load_fundamentals(tickers, pm_index):
    """
    Returns:
      mcap_panel  – (months × tickers) historical market cap in GBP
                    = annual_shares × price_GBX / 100
      ebit_panel  – (months × tickers) TTM EBIT (point-in-time, 45-day lag)
    """
    print("Loading fundamentals...")

    shares_by_ticker = {}   # ticker → {year: shares}
    ebit_records     = []   # list of dicts

    for tkr in tickers:
        path = os.path.join(FUND_DIR, f'{tkr}.json')
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                d = json.load(f)

            # Annual shares outstanding
            annual_shares = {}
            for entry in d.get('outstandingShares', {}).get('annual', {}).values():
                try:
                    yr  = int(entry['date'])
                    sh  = entry.get('shares', 0)
                    if sh:
                        annual_shares[yr] = int(sh)
                except Exception:
                    pass
            if annual_shares:
                shares_by_ticker[tkr] = annual_shares

            # Quarterly EBIT (TTM = rolling 4-quarter sum, 45-day filing lag)
            qtrs = d.get('Financials', {}).get('Income_Statement', {}).get('quarterly', {})
            rows = []
            for v in qtrs.values():
                try:
                    ebit = v.get('ebit')
                    if ebit is not None:
                        rows.append({'period_end': pd.Timestamp(v['date']),
                                     'ebit': float(ebit)})
                except Exception:
                    pass

            if len(rows) >= 4:
                qdf = (pd.DataFrame(rows)
                         .sort_values('period_end')
                         .set_index('period_end'))
                qdf['ebit_ttm'] = qdf['ebit'].rolling(4, min_periods=4).sum()
                qdf = qdf.dropna(subset=['ebit_ttm'])
                qdf['avail_date'] = qdf.index + pd.Timedelta(days=45)
                for idx, row in qdf.iterrows():
                    ebit_records.append({'ticker': tkr,
                                         'avail_date': row['avail_date'],
                                         'ebit_ttm': row['ebit_ttm']})
        except Exception:
            pass

    # ── EBIT panel ──────────────────────────────────────────────────────────────
    if ebit_records:
        edf = pd.DataFrame(ebit_records)
        edf['avail_date'] = pd.to_datetime(edf['avail_date'])
        edf['ym'] = edf['avail_date'].dt.to_period('M')
        ebit_panel = (edf.pivot_table(index='ym', columns='ticker',
                                       values='ebit_ttm', aggfunc='last')
                         .sort_index()
                         .reindex(pm_index)
                         .ffill(limit=4))
        print(f"  EBIT panel: {ebit_panel.shape}")
    else:
        ebit_panel = pd.DataFrame(index=pm_index)
        print("  EBIT panel: empty")

    return shares_by_ticker, ebit_panel


def build_mcap_panel(pm, shares_by_ticker):
    """Historical market cap = annual_shares × EOM_price_GBX / 100  (in GBP)."""
    print("Building market cap panel...")
    mcap = pd.DataFrame(np.nan, index=pm.index, columns=pm.columns)

    for tkr, yr_shares in shares_by_ticker.items():
        if tkr not in pm.columns:
            continue
        yrs = sorted(yr_shares.keys())
        for period in pm.index:
            price = pm.at[period, tkr]
            if pd.isna(price) or price <= 0:
                continue
            yr = period.year
            # Use shares from this year, else closest prior year
            sh = yr_shares.get(yr)
            if sh is None:
                prior = [y for y in yrs if y <= yr]
                sh = yr_shares[prior[-1]] if prior else None
            if sh:
                mcap.at[period, tkr] = price * sh / 100   # GBP

    print(f"  MCap panel: {mcap.shape}  non-null values: {mcap.notna().sum().sum():,}")
    return mcap


# ─── 4. FTSE 100 ───────────────────────────────────────────────────────────────

def load_ftse100():
    try:
        import yfinance as yf, warnings
        warnings.filterwarnings('ignore')
        data = yf.download('^FTSE', start='1999-01-01', progress=False)
        s = data['Close'].squeeze().dropna()
        s.index = pd.to_datetime(s.index)
        print(f"  FTSE 100: {len(s)} daily bars  ({s.index[0].date()} → {s.index[-1].date()})")
        return s
    except Exception as e:
        print(f"  Warning: FTSE 100 unavailable ({e})")
        return None


def regime_ok(ftse100, month, ma_period):
    if ftse100 is None:
        return True
    end = month.to_timestamp(how='end')
    hist = ftse100.loc[:end].tail(ma_period + 1)
    if len(hist) < ma_period:
        return True
    return float(hist.iloc[-1]) >= float(hist.tail(ma_period).mean())


# ─── 5. BACKTEST ───────────────────────────────────────────────────────────────

def run_backtest(pm, mcap_panel, ebit_panel, ftse100):
    months = pm.index[(pm.index >= pd.Period(START,'M')) &
                      (pm.index <= pd.Period(END,  'M'))]

    # FTSE EOM for benchmark returns
    ftse_eom = None
    if ftse100 is not None:
        ftse_eom = ftse100.resample('ME').last()
        ftse_eom.index = ftse_eom.index.to_period('M')

    strat_rets, bm_rets, dates, holdings_log = [], [], [], []

    for i, m in enumerate(months):
        m_idx = pm.index.get_loc(m)
        if m_idx + 1 >= len(pm.index):
            break
        next_m = pm.index[m_idx + 1]
        dates.append(m)

        # Benchmark return
        if (ftse_eom is not None and
                m in ftse_eom.index and next_m in ftse_eom.index):
            bm_ret = float(ftse_eom[next_m] / ftse_eom[m] - 1)
        else:
            bm_ret = 0.0
        bm_rets.append(bm_ret)

        # Regime
        if not regime_ok(ftse100, m, MA_PERIOD):
            strat_rets.append(0.0)
            holdings_log.append([])
            continue

        # Composite momentum
        mom = pd.Series(0.0, index=pm.columns)
        for lb, wt in COMPOSITE_WEIGHTS.items():
            if m_idx - lb < 0:
                continue
            start_p = pm.index[m_idx - lb]
            ret = pm.loc[m] / pm.loc[start_p] - 1
            mom = mom.add(ret * wt, fill_value=0)

        # Filters
        mask = mom.notna() & (pm.loc[m] > 0)

        if not mcap_panel.empty and m in mcap_panel.index:
            mask &= (mcap_panel.loc[m] >= MIN_MCAP_GBP)

        if not ebit_panel.empty and m in ebit_panel.index:
            mask &= (ebit_panel.loc[m] > 0)

        eligible = mom[mask]

        if eligible.empty:
            strat_rets.append(0.0)
            holdings_log.append([])
            continue

        selected = eligible.nlargest(TOP_N).index.tolist()
        holdings_log.append(selected)

        fwd = (pm.loc[next_m, selected] / pm.loc[m, selected] - 1).dropna()
        strat_rets.append(float(fwd.mean()) if len(fwd) > 0 else 0.0)

    return strat_rets, bm_rets, dates, holdings_log


# ─── 6. STATS ──────────────────────────────────────────────────────────────────

def _period_stats(r, bm, label):
    """Compute stats for a slice of monthly returns."""
    n = len(r)
    if n < 6:
        return None
    rf_m   = 0.03 / 12
    cum    = np.cumprod(1 + r)
    bm_cum = np.cumprod(1 + bm)
    yrs    = n / 12
    cagr   = cum[-1] ** (1/yrs) - 1
    bm_cagr= bm_cum[-1] ** (1/yrs) - 1
    vol    = np.std(r, ddof=1) * np.sqrt(12)
    sharpe = (np.mean(r) - rf_m) / np.std(r, ddof=1) * np.sqrt(12) if np.std(r) > 0 else 0
    peak   = np.maximum.accumulate(cum)
    maxdd  = ((cum - peak) / peak).min()
    return {
        'label':    label,
        'n':        n,
        'cagr':     round(cagr    * 100, 1),
        'bm_cagr':  round(bm_cagr * 100, 1),
        'alpha':    round((cagr - bm_cagr) * 100, 1),
        'sharpe':   round(sharpe,  2),
        'maxdd':    round(maxdd   * 100, 1),
        'vol':      round(vol     * 100, 1),
    }


def calc_stats(strat_rets, bm_rets, dates):
    r  = np.array(strat_rets)
    bm = np.array(bm_rets[:len(r)])
    n  = len(r)
    if n == 0:
        return {}, []

    cum    = np.cumprod(1 + r)
    bm_cum = np.cumprod(1 + bm)
    yrs    = n / 12
    cagr   = cum[-1] ** (1/yrs) - 1
    bm_cagr= bm_cum[-1] ** (1/yrs) - 1
    vol    = np.std(r, ddof=1) * np.sqrt(12)
    rf_m   = 0.03 / 12
    sharpe = (np.mean(r) - rf_m) / np.std(r, ddof=1) * np.sqrt(12) if np.std(r) > 0 else 0
    ds     = r[r < rf_m] - rf_m
    ds_vol = np.std(ds, ddof=1) * np.sqrt(12) if len(ds) > 1 else vol
    sortino= (np.mean(r) - rf_m) / (ds_vol / np.sqrt(12)) * np.sqrt(12) if ds_vol > 0 else 0
    peak   = np.maximum.accumulate(cum)
    maxdd  = ((cum - peak) / peak).min()

    overall = {
        'cagr':     round(cagr    * 100, 1),
        'bm_cagr':  round(bm_cagr * 100, 1),
        'alpha':    round((cagr - bm_cagr) * 100, 1),
        'sharpe':   round(sharpe,  2),
        'sortino':  round(sortino, 2),
        'maxdd':    round(maxdd   * 100, 1),
        'vol':      round(vol     * 100, 1),
        'win_rate': round(np.mean(r > 0) * 100, 1),
        'n_months': n,
        'start':    str(dates[0]),
        'end':      str(dates[-1]),
        'cum_return': round((cum[-1] - 1) * 100, 1),
    }

    # 5-year sub-periods
    dates_arr = np.array([d.year + (d.month - 1) / 12 for d in dates])
    periods = []
    start_yr = dates[0].year
    # Align to nearest 5-year boundary
    while start_yr % 5 != 0 and start_yr > dates[0].year - 5:
        start_yr -= 1
    # But actually just use fixed 5-year windows from the actual start
    # Use calendar year boundaries: 2001, 2006, 2011, 2016, 2021, 2026
    bounds = [y for y in range(2000, 2031, 5)]
    for i in range(len(bounds) - 1):
        y0, y1 = bounds[i], bounds[i+1]
        label = f'{y0}–{y1-1}'
        mask = np.array([(d.year >= y0 and d.year < y1) for d in dates])
        if mask.sum() < 6:
            continue
        ps = _period_stats(r[mask], bm[mask], label)
        if ps:
            periods.append(ps)

    return overall, periods


# ─── 7. MAIN ───────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  UK Optimal Momentum — EODHD LSE")
    print("=" * 70)

    tickers = load_tickers()
    pm      = load_prices(tickers)
    if pm.empty:
        print("ERROR: no price data")
        return

    shares_by_ticker, ebit_panel = load_fundamentals(tickers, pm.index)
    mcap_panel                   = build_mcap_panel(pm, shares_by_ticker)

    print("Downloading FTSE 100...")
    ftse100 = load_ftse100()

    print("Running backtest...")
    strat_rets, bm_rets, dates, holdings_log = run_backtest(
        pm, mcap_panel, ebit_panel, ftse100)

    s, periods = calc_stats(strat_rets, bm_rets, dates)
    if not s:
        print("No results.")
        return

    print(f"\n{'='*80}")
    print(f"  Results  {s['start']} → {s['end']}  ({s['n_months']} months)")
    print(f"{'='*80}")
    print(f"  CAGR           {s['cagr']:>+7.1f}%   (FTSE 100: {s['bm_cagr']:>+5.1f}%   Alpha: {s['alpha']:>+5.1f}%)")
    print(f"  Sharpe         {s['sharpe']:>7.2f}   Sortino: {s['sortino']:.2f}")
    print(f"  Max DD         {s['maxdd']:>7.1f}%   Vol: {s['vol']:.1f}%")
    print(f"  Win Rate       {s['win_rate']:>7.1f}%   Cum Return: {s['cum_return']:>+.1f}%")

    # Sub-period breakdown
    if periods:
        w = 80
        print(f"\n{'─'*w}")
        hdr = f"  {'Period':<12} {'CAGR':>7} {'FTSE':>7} {'Alpha':>7} {'Sharpe':>7} {'MaxDD':>7} {'Vol':>7}"
        print(hdr)
        print(f"{'─'*w}")
        for p in periods:
            print(f"  {p['label']:<12} {p['cagr']:>+6.1f}% {p['bm_cagr']:>+6.1f}% {p['alpha']:>+6.1f}% {p['sharpe']:>7.2f} {p['maxdd']:>6.1f}% {p['vol']:>6.1f}%")
        print(f"{'─'*w}")

    in_cash = sum(1 for h in holdings_log if len(h) == 0)
    invested = sum(1 for h in holdings_log if len(h) > 0)
    print(f"\n  Cash months: {in_cash}  |  Invested months: {invested}")

    last_picks = holdings_log[-1] if holdings_log else []
    print(f"\n  Current picks ({str(dates[-1]) if dates else 'n/a'}):")
    for i, t in enumerate(last_picks, 1):
        print(f"    {i}. {t}")

    return s


if __name__ == '__main__':
    main()
