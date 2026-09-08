#!/usr/bin/env python3
"""
UK Momentum Grid Search — with trading costs

Grid: 625 combinations
  momentum  : 6M | 12M | 50%6M+50%12M | 50%3M+50%12M | 50%1M+50%12M
  mcap      : £100M | £250M | £500M | £1000M | £2000M
  N (top-N) : 5 | 7 | 10 | 15 | 20
  MA regime : None | 100 | 150 | 200 | 250

Trading costs (applied monthly at rebalance):
  BUY  = 0.65%  (0.5% stamp duty + 0.15% spread/commission)
  SELL = 0.15%  (spread/commission only)
  Cost per month = (buys × 0.65% + sells × 0.15%) / N

Usage: python3 uk_grid_search.py
Results saved to /tmp/uk_grid_results.csv
"""

import os, json, itertools
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# ─── Paths ────────────────────────────────────────────────────────────────────
LSE_DIR    = '/Users/luisabrantes/eodhd_data/LSE'
PRICES_DIR = os.path.join(LSE_DIR, 'prices')
FUND_DIR   = os.path.join(LSE_DIR, 'fundamentals')
TICKERS_F  = os.path.join(LSE_DIR, 'tickers.parquet')
RESULTS_F  = '/tmp/uk_grid_results.csv'

START = '2001-01'
END   = '2026-07'

BUY_COST  = 0.0065   # 0.5% stamp duty + 0.15% spread
SELL_COST = 0.0015   # 0.15% spread only
RF_MONTHLY = 0.03 / 12

# ─── Grid ─────────────────────────────────────────────────────────────────────
MOM_CONFIGS = {
    '6M':          {6: 1.0},
    '12M':         {12: 1.0},
    '6+12M':       {6: 0.5, 12: 0.5},
    '3+12M':       {3: 0.5, 12: 0.5},
    '1+12M':       {1: 0.5, 12: 0.5},
}
MCAP_FILTERS  = [100_000_000, 250_000_000, 500_000_000, 1_000_000_000, 2_000_000_000]  # GBP
N_VALUES      = [5, 7, 10, 15, 20]
MA_PERIODS    = [None, 100, 150, 200, 250]


# ─── 1. Load data (once) ──────────────────────────────────────────────────────

def load_tickers():
    t = pd.read_parquet(TICKERS_F)
    common = t[t['Type'] == 'Common Stock']['Code'].tolist()
    gbx = []
    for tkr in common:
        path = os.path.join(FUND_DIR, f'{tkr}.json')
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                d = json.load(f)
            if d.get('General', {}).get('CurrencyCode', '') == 'GBX':
                gbx.append(tkr)
        except Exception:
            pass
    print(f"  Tickers: {len(common)} common stocks → {len(gbx)} GBX-denominated")
    return gbx


def load_prices(tickers):
    print("Loading prices...")
    frames = []
    for tkr in tickers:
        path = os.path.join(PRICES_DIR, f'{tkr}.parquet')
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_parquet(path, columns=['adjusted_close'])
            df.index = pd.to_datetime(df.index)
            df = df[df['adjusted_close'] > 0].rename(columns={'adjusted_close': tkr})
            frames.append(df)
        except Exception:
            pass
    print(f"  Price files: {len(frames)}")
    daily = pd.concat(frames, axis=1).sort_index()
    eom = daily.resample('ME').last()
    eom.index = eom.index.to_period('M')
    return eom.sort_index()


def load_fundamentals(tickers, pm_index):
    print("Loading fundamentals...")
    shares_by_ticker = {}
    ebit_records = []
    for tkr in tickers:
        path = os.path.join(FUND_DIR, f'{tkr}.json')
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                d = json.load(f)
            annual_shares = {}
            for entry in d.get('outstandingShares', {}).get('annual', {}).values():
                try:
                    yr = int(entry['date'])
                    sh = entry.get('shares', 0)
                    if sh:
                        annual_shares[yr] = int(sh)
                except Exception:
                    pass
            if annual_shares:
                shares_by_ticker[tkr] = annual_shares

            qtrs = d.get('Financials', {}).get('Income_Statement', {}).get('quarterly', {})
            rows = []
            for v in qtrs.values():
                try:
                    ebit = v.get('ebit')
                    if ebit is not None:
                        rows.append({'period_end': pd.Timestamp(v['date']), 'ebit': float(ebit)})
                except Exception:
                    pass
            if len(rows) >= 4:
                qdf = (pd.DataFrame(rows).sort_values('period_end').set_index('period_end'))
                qdf['ebit_ttm'] = qdf['ebit'].rolling(4, min_periods=4).sum()
                qdf = qdf.dropna(subset=['ebit_ttm'])
                qdf['avail_date'] = qdf.index + pd.Timedelta(days=45)
                for idx, row in qdf.iterrows():
                    ebit_records.append({'ticker': tkr, 'avail_date': row['avail_date'],
                                         'ebit_ttm': row['ebit_ttm']})
        except Exception:
            pass

    if ebit_records:
        edf = pd.DataFrame(ebit_records)
        edf['ym'] = pd.to_datetime(edf['avail_date']).dt.to_period('M')
        ebit_panel = (edf.pivot_table(index='ym', columns='ticker',
                                       values='ebit_ttm', aggfunc='last')
                         .sort_index().reindex(pm_index).ffill(limit=4))
    else:
        ebit_panel = pd.DataFrame(index=pm_index)
    print(f"  EBIT panel: {ebit_panel.shape}")
    return shares_by_ticker, ebit_panel


def build_mcap_panel(pm, shares_by_ticker):
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
            sh = yr_shares.get(yr)
            if sh is None:
                prior = [y for y in yrs if y <= yr]
                sh = yr_shares[prior[-1]] if prior else None
            if sh:
                mcap.at[period, tkr] = price * sh / 100  # GBX × shares / 100 = GBP
    print(f"  MCap panel: {mcap.shape}  non-null: {mcap.notna().sum().sum():,}")
    return mcap


def load_ftse100():
    try:
        import yfinance as yf
        data = yf.download('^FTSE', start='1999-01-01', progress=False, auto_adjust=True)
        s = data['Close'].squeeze().dropna()
        s.index = pd.to_datetime(s.index)
        print(f"  FTSE 100: {len(s)} bars  ({s.index[0].date()} → {s.index[-1].date()})")
        return s
    except Exception as e:
        print(f"  FTSE 100 unavailable: {e}")
        return None


# ─── 2. Single backtest run ───────────────────────────────────────────────────

def run_one(pm, mcap_panel, ebit_panel, ftse100, mom_weights, min_mcap, top_n, ma_period):
    """Returns array of monthly returns (after trading costs)."""
    months = pm.index[(pm.index >= pd.Period(START, 'M')) &
                      (pm.index <= pd.Period(END, 'M'))]

    strat_rets = []
    prev_picks = set()

    for i, m in enumerate(months):
        m_idx = pm.index.get_loc(m)
        if m_idx + 1 >= len(pm.index):
            break
        next_m = pm.index[m_idx + 1]

        # Regime filter
        if ma_period is not None and ftse100 is not None:
            end_ts = m.to_timestamp(how='end')
            hist = ftse100.loc[:end_ts].tail(ma_period + 1)
            if len(hist) >= ma_period:
                if float(hist.iloc[-1]) < float(hist.tail(ma_period).mean()):
                    strat_rets.append(0.0)
                    prev_picks = set()
                    continue

        # Composite momentum score
        mom = pd.Series(0.0, index=pm.columns)
        valid = True
        for lb, wt in mom_weights.items():
            if m_idx - lb < 0:
                valid = False
                break
            start_p = pm.index[m_idx - lb]
            ret = pm.loc[m] / pm.loc[start_p] - 1
            mom = mom.add(ret * wt, fill_value=0)
        if not valid:
            strat_rets.append(0.0)
            continue

        # Filters
        mask = mom.notna() & (pm.loc[m] > 0)
        if not mcap_panel.empty and m in mcap_panel.index:
            mask &= (mcap_panel.loc[m] >= min_mcap)
        if not ebit_panel.empty and m in ebit_panel.index:
            mask &= (ebit_panel.loc[m] > 0)

        eligible = mom[mask]
        if eligible.empty:
            strat_rets.append(0.0)
            prev_picks = set()
            continue

        selected = set(eligible.nlargest(top_n).index.tolist())
        n_actual = len(selected)

        # Trading costs
        buys  = len(selected - prev_picks)
        sells = len(prev_picks - selected)
        cost  = (buys * BUY_COST + sells * SELL_COST) / n_actual if n_actual > 0 else 0.0

        # Forward return
        sel_list = list(selected)
        fwd = (pm.loc[next_m, sel_list] / pm.loc[m, sel_list] - 1).dropna()
        gross = float(fwd.mean()) if len(fwd) > 0 else 0.0
        strat_rets.append(gross - cost)

        prev_picks = selected

    return np.array(strat_rets)


# ─── 3. Stats from return array ───────────────────────────────────────────────

def compute_stats(rets):
    r = rets
    n = len(r)
    if n < 12:
        return None
    cum   = np.cumprod(1 + r)
    yrs   = n / 12
    cagr  = cum[-1] ** (1 / yrs) - 1
    vol   = np.std(r, ddof=1) * np.sqrt(12)
    sharpe = (np.mean(r) - RF_MONTHLY) / np.std(r, ddof=1) * np.sqrt(12) if np.std(r) > 0 else 0
    peak  = np.maximum.accumulate(cum)
    maxdd = ((cum - peak) / peak).min()
    win_r = np.mean(r > 0)
    return {
        'cagr':     round(cagr * 100, 2),
        'sharpe':   round(sharpe, 3),
        'maxdd':    round(maxdd * 100, 2),
        'vol':      round(vol * 100, 2),
        'win_rate': round(win_r * 100, 1),
        'n':        n,
    }


# ─── 4. Grid search ───────────────────────────────────────────────────────────

def grid_search(pm, mcap_panel, ebit_panel, ftse100):
    combos = list(itertools.product(
        MOM_CONFIGS.items(),
        MCAP_FILTERS,
        N_VALUES,
        MA_PERIODS,
    ))
    total = len(combos)
    print(f"\nRunning {total} combinations...")

    rows = []
    for i, ((mom_name, mom_weights), min_mcap, top_n, ma_period) in enumerate(combos, 1):
        if i % 50 == 0 or i == total:
            print(f"  {i}/{total}...", flush=True)

        rets = run_one(pm, mcap_panel, ebit_panel, ftse100,
                       mom_weights, min_mcap, top_n, ma_period)
        s = compute_stats(rets)
        if s is None:
            continue

        mcap_label = {
            100_000_000:   '£100M',
            250_000_000:   '£250M',
            500_000_000:   '£500M',
            1_000_000_000: '£1B',
            2_000_000_000: '£2B',
        }[min_mcap]

        rows.append({
            'momentum':   mom_name,
            'mcap_min':   mcap_label,
            'top_n':      top_n,
            'ma_regime':  f'MA{ma_period}' if ma_period else 'None',
            'cagr':       s['cagr'],
            'sharpe':     s['sharpe'],
            'maxdd':      s['maxdd'],
            'vol':        s['vol'],
            'win_rate':   s['win_rate'],
            'n_months':   s['n'],
        })

    return pd.DataFrame(rows)


# ─── 5. Main ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  UK Momentum Grid Search  (2001–2026, with trading costs)")
    print(f"  BUY={BUY_COST*100:.2f}%  SELL={SELL_COST*100:.2f}%")
    print("=" * 70)

    tickers                      = load_tickers()
    pm                           = load_prices(tickers)
    shares_by_ticker, ebit_panel = load_fundamentals(tickers, pm.index)
    mcap_panel                   = build_mcap_panel(pm, shares_by_ticker)
    print("Downloading FTSE 100...")
    ftse100                      = load_ftse100()

    df = grid_search(pm, mcap_panel, ebit_panel, ftse100)

    # ── Top 20 by Sharpe ──────────────────────────────────────────────────────
    top_sharpe = df.sort_values('sharpe', ascending=False).head(20)
    print(f"\n{'='*90}")
    print(f"  TOP 20 BY SHARPE  (after {BUY_COST*100:.2f}% buy / {SELL_COST*100:.2f}% sell costs)")
    print(f"{'='*90}")
    print(f"  {'Mom':<12} {'MCap':<8} {'N':>4} {'Regime':<8} {'CAGR':>7} {'Sharpe':>7} {'MaxDD':>7} {'Vol':>6} {'Win%':>5}")
    print(f"  {'-'*82}")
    for _, r in top_sharpe.iterrows():
        print(f"  {r.momentum:<12} {r.mcap_min:<8} {r.top_n:>4} {r.ma_regime:<8} "
              f"{r.cagr:>+6.1f}% {r.sharpe:>7.3f} {r.maxdd:>+6.1f}% {r.vol:>5.1f}% {r.win_rate:>5.1f}%")

    # ── Top 10 by CAGR ────────────────────────────────────────────────────────
    top_cagr = df.sort_values('cagr', ascending=False).head(10)
    print(f"\n  TOP 10 BY CAGR")
    print(f"  {'-'*82}")
    for _, r in top_cagr.iterrows():
        print(f"  {r.momentum:<12} {r.mcap_min:<8} {r.top_n:>4} {r.ma_regime:<8} "
              f"{r.cagr:>+6.1f}% {r.sharpe:>7.3f} {r.maxdd:>+6.1f}% {r.vol:>5.1f}% {r.win_rate:>5.1f}%")

    # ── Best by each dimension ────────────────────────────────────────────────
    print(f"\n  BEST SHARPE BY MOMENTUM CONFIG")
    for name, grp in df.groupby('momentum'):
        best = grp.loc[grp['sharpe'].idxmax()]
        print(f"    {name:<12}  Sharpe={best.sharpe:.3f}  CAGR={best.cagr:+.1f}%  "
              f"MCap={best.mcap_min}  N={best.top_n}  Regime={best.ma_regime}")

    print(f"\n  BEST SHARPE BY MCAP FILTER")
    for name, grp in df.groupby('mcap_min'):
        best = grp.loc[grp['sharpe'].idxmax()]
        print(f"    {name:<8}  Sharpe={best.sharpe:.3f}  CAGR={best.cagr:+.1f}%  "
              f"Mom={best.momentum}  N={best.top_n}  Regime={best.ma_regime}")

    print(f"\n  BEST SHARPE BY N")
    for name, grp in df.groupby('top_n'):
        best = grp.loc[grp['sharpe'].idxmax()]
        print(f"    N={name:<4}  Sharpe={best.sharpe:.3f}  CAGR={best.cagr:+.1f}%  "
              f"Mom={best.momentum}  MCap={best.mcap_min}  Regime={best.ma_regime}")

    print(f"\n  BEST SHARPE BY REGIME")
    for name, grp in df.groupby('ma_regime'):
        best = grp.loc[grp['sharpe'].idxmax()]
        print(f"    {name:<8}  Sharpe={best.sharpe:.3f}  CAGR={best.cagr:+.1f}%  "
              f"Mom={best.momentum}  MCap={best.mcap_min}  N={best.top_n}")

    # ── Save full results ─────────────────────────────────────────────────────
    df.sort_values('sharpe', ascending=False).to_csv(RESULTS_F, index=False)
    print(f"\nFull results saved: {RESULTS_F}  ({len(df)} combinations)")

    # ── Current optimal config ────────────────────────────────────────────────
    best = df.loc[df['sharpe'].idxmax()]
    print(f"\n{'='*70}")
    print(f"  BEST OVERALL: {best.momentum}  MCap>{best.mcap_min}  N={best.top_n}  {best.ma_regime}")
    print(f"  Sharpe={best.sharpe:.3f}  CAGR={best.cagr:+.1f}%  MaxDD={best.maxdd:.1f}%")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
