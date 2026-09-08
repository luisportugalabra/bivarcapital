#!/usr/bin/env python3
"""
UK Momentum — Signal Enhancement Tests
Tests fundamentals, accelerations, and absolute values vs baseline.

Baseline: 6+12M | £100M | N=15 | MA200 | GLD in cash
Look-ahead protection: all fundamentals use 45-day filing lag from period end.

Variants tested:
  A. MOMENTUM ACCELERATIONS (price only, no LAB):
     A1. Skip-1 month (use price[-1] to price[-7] / price[-13])
     A2. Acceleration: rank by score = 0.5*mom_6_12 + 0.5*(3M - prior_3M)
     A3. Momentum of momentum (12M vs prior 12M)

  B. FUNDAMENTAL FILTERS / SCORING (45-day lag):
     B1. Revenue growth YoY > 0 (filter)
     B2. EBIT growth YoY > 0 (filter, on top of EBIT > 0)
     B3. Score = 50% momentum + 50% z(revenue_growth_yoy)
     B4. Score = 70% momentum + 30% z(revenue_growth_yoy)
     B5. Score = 50% momentum + 50% z(ebit_growth_yoy)

  C. ABSOLUTE MOMENTUM (price filter):
     C1. Require 12M return > 0%
     C2. Require 6M return > 0%
     C3. Require BOTH 6M and 12M > 0%

  D. COMBINATIONS:
     D1. Skip-1 + abs 12M > 0
     D2. Skip-1 + 50% rev growth score
     D3. Accel + abs 12M > 0
"""

import os, json
import pandas as pd, numpy as np
import yfinance as yf, warnings
warnings.filterwarnings('ignore')

LSE_DIR    = '/Users/luisabrantes/eodhd_data/LSE'
PRICES_DIR = os.path.join(LSE_DIR, 'prices')
FUND_DIR   = os.path.join(LSE_DIR, 'fundamentals')
TICKERS_F  = os.path.join(LSE_DIR, 'tickers.parquet')

START      = '2004-12'
END        = '2026-07'
MIN_MCAP   = 100_000_000    # £100M GBP
TOP_N      = 15
MA_PERIOD  = 200
BUY_COST   = 0.0065
SELL_COST  = 0.0015
RF_M       = 0.03 / 12

# ─── 1. Load data ─────────────────────────────────────────────────────────────

def load_tickers():
    t = pd.read_parquet(TICKERS_F)
    common = t[t['Type'] == 'Common Stock']['Code'].tolist()
    gbx = []
    for tkr in common:
        path = os.path.join(FUND_DIR, f'{tkr}.json')
        if not os.path.exists(path): continue
        try:
            with open(path) as f: d = json.load(f)
            if d.get('General', {}).get('CurrencyCode', '') == 'GBX':
                gbx.append(tkr)
        except: pass
    print(f"  Tickers: {len(gbx)} GBX")
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
    print(f"  Prices: {eom.shape}")
    return eom.sort_index()


def load_fundamentals(tickers, pm_index):
    """Loads EBIT TTM, Revenue TTM with 45-day lag. Returns point-in-time panels."""
    shares_by_ticker = {}
    ebit_records, rev_records = [], []

    for tkr in tickers:
        path = os.path.join(FUND_DIR, f'{tkr}.json')
        if not os.path.exists(path): continue
        try:
            with open(path) as f: d = json.load(f)

            # Shares outstanding (annual)
            annual_shares = {}
            for entry in d.get('outstandingShares', {}).get('annual', {}).values():
                try:
                    yr = int(entry['date']); sh = entry.get('shares', 0)
                    if sh: annual_shares[yr] = int(sh)
                except: pass
            if annual_shares: shares_by_ticker[tkr] = annual_shares

            # Quarterly income statement
            qtrs = d.get('Financials', {}).get('Income_Statement', {}).get('quarterly', {})
            rows = []
            for v in qtrs.values():
                try:
                    period_end = pd.Timestamp(v['date'])
                    ebit = v.get('ebit')
                    rev  = v.get('totalRevenue')
                    if ebit is not None or rev is not None:
                        rows.append({
                            'period_end': period_end,
                            'ebit': float(ebit) if ebit is not None else np.nan,
                            'rev':  float(rev)  if rev  is not None else np.nan,
                        })
                except: pass

            if len(rows) >= 4:
                qdf = (pd.DataFrame(rows)
                         .sort_values('period_end')
                         .set_index('period_end'))
                # TTM rolling 4-quarter sum
                qdf['ebit_ttm'] = qdf['ebit'].rolling(4, min_periods=4).sum()
                qdf['rev_ttm']  = qdf['rev'].rolling(4, min_periods=4).sum()
                # Year-ago TTM (4 quarters back)
                qdf['ebit_ttm_ya'] = qdf['ebit_ttm'].shift(4)
                qdf['rev_ttm_ya']  = qdf['rev_ttm'].shift(4)
                # Growth rates
                qdf['ebit_growth'] = (qdf['ebit_ttm'] / qdf['ebit_ttm_ya'] - 1).where(
                    qdf['ebit_ttm_ya'].abs() > 0)
                qdf['rev_growth']  = (qdf['rev_ttm']  / qdf['rev_ttm_ya']  - 1).where(
                    qdf['rev_ttm_ya'].abs() > 0)
                # 45-day availability lag (no filing_date → use period_end + 45d)
                qdf = qdf.dropna(subset=['ebit_ttm'])
                qdf['avail_date'] = qdf.index + pd.Timedelta(days=45)
                for idx, row in qdf.iterrows():
                    rec = {'ticker': tkr, 'avail_date': row['avail_date'],
                           'ebit_ttm': row['ebit_ttm'], 'rev_ttm': row['rev_ttm'],
                           'ebit_growth': row['ebit_growth'], 'rev_growth': row['rev_growth']}
                    ebit_records.append(rec)
        except: pass

    def make_panel(records, col):
        if not records: return pd.DataFrame(index=pm_index)
        df = pd.DataFrame(records)
        df['ym'] = pd.to_datetime(df['avail_date']).dt.to_period('M')
        return (df.pivot_table(index='ym', columns='ticker', values=col, aggfunc='last')
                  .sort_index().reindex(pm_index).ffill(limit=4))

    ebit_panel  = make_panel(ebit_records, 'ebit_ttm')
    rev_panel   = make_panel(ebit_records, 'rev_ttm')
    egrow_panel = make_panel(ebit_records, 'ebit_growth')
    rgrow_panel = make_panel(ebit_records, 'rev_growth')

    print(f"  EBIT panel: {ebit_panel.shape} | Rev panel: {rev_panel.shape}")
    print(f"  EBIT growth: {egrow_panel.notna().sum().sum():,} obs | Rev growth: {rgrow_panel.notna().sum().sum():,} obs")
    return shares_by_ticker, ebit_panel, rev_panel, egrow_panel, rgrow_panel


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
    print(f"  MCap: {mcap.shape}")
    return mcap


def load_market_data():
    ftse = yf.download('^FTSE', start='1999-01-01', progress=False, auto_adjust=True)['Close'].squeeze().dropna()
    ftse.index = pd.to_datetime(ftse.index)

    gld = yf.download('GLD', start='2001-01-01', progress=False, auto_adjust=True)['Close'].squeeze().dropna()
    gld.index = pd.to_datetime(gld.index)
    gld_eom = gld.resample('ME').last()
    gld_eom.index = gld_eom.index.to_period('M')
    print(f"  FTSE: {len(ftse)} bars | GLD: {len(gld_eom)} months")
    return ftse, gld_eom


# ─── 2. Backtest engine ───────────────────────────────────────────────────────

def run_backtest(pm, mcap, ebit_panel, ftse, gld_eom,
                 score_fn,          # fn(m_idx, pm, ebit_panel, ...) → pd.Series scores
                 extra_filter=None, # fn(m_idx, pm, ...) → pd.Series bool mask
                 label=''):
    months = pm.index[(pm.index >= pd.Period(START,'M')) & (pm.index <= pd.Period(END,'M'))]
    rets = []
    prev_picks = set()

    for i, m in enumerate(months):
        m_idx = pm.index.get_loc(m)
        if m_idx + 1 >= len(pm.index): break
        next_m = pm.index[m_idx + 1]

        # Regime: FTSE vs MA200, use GLD in cash
        end_ts = m.to_timestamp(how='end')
        hist = ftse.loc[:end_ts].tail(MA_PERIOD + 1)
        in_regime = len(hist) < MA_PERIOD or float(hist.iloc[-1]) >= float(hist.tail(MA_PERIOD).mean())

        if not in_regime:
            if m in gld_eom.index and next_m in gld_eom.index:
                rets.append(float(gld_eom[next_m] / gld_eom[m] - 1))
            else:
                rets.append(0.0)
            prev_picks = set()
            continue

        # Base filters: valid price + mcap
        mask = (pm.loc[m] > 0)
        if not mcap.empty and m in mcap.index:
            mask &= (mcap.loc[m] >= MIN_MCAP)
        if not ebit_panel.empty and m in ebit_panel.index:
            mask &= (ebit_panel.loc[m] > 0)

        # Extra filter (absolute momentum, fundamental filter, etc.)
        if extra_filter is not None:
            ef = extra_filter(m_idx, pm, ebit_panel)
            mask &= ef.reindex(pm.columns, fill_value=False)

        # Score
        scores = score_fn(m_idx, pm, ebit_panel)
        scores = scores[mask & scores.notna()]

        if scores.empty:
            rets.append(0.0); prev_picks = set(); continue

        selected = set(scores.nlargest(TOP_N).index.tolist())
        n_actual = len(selected)
        buys  = len(selected - prev_picks)
        sells = len(prev_picks - selected)
        cost  = (buys * BUY_COST + sells * SELL_COST) / n_actual if n_actual else 0

        fwd = (pm.loc[next_m, list(selected)] / pm.loc[m, list(selected)] - 1).dropna()
        gross = float(fwd.mean()) if len(fwd) else 0.0
        rets.append(gross - cost)
        prev_picks = selected

    return np.array(rets)


def stats(r, label):
    n = len(r)
    cum    = np.cumprod(1 + r)
    yrs    = n / 12
    cagr   = cum[-1] ** (1 / yrs) - 1
    vol    = np.std(r, ddof=1) * np.sqrt(12)
    sharpe = (np.mean(r) - RF_M) / np.std(r, ddof=1) * np.sqrt(12) if np.std(r) > 0 else 0
    peak   = np.maximum.accumulate(cum)
    maxdd  = ((cum - peak) / peak).min()
    win_r  = np.mean(r > 0) * 100
    return {
        'label':  label,
        'cagr':   round(cagr   * 100, 2),
        'sharpe': round(sharpe, 3),
        'maxdd':  round(maxdd  * 100, 2),
        'vol':    round(vol    * 100, 2),
        'win':    round(win_r,  1),
        'n':      n,
    }


# ─── 3. Score functions ───────────────────────────────────────────────────────

def mom_6_12(m_idx, pm, *_):
    """Baseline: 50% 6M + 50% 12M momentum."""
    s = pd.Series(0.0, index=pm.columns)
    for lb, wt in {6: 0.5, 12: 0.5}.items():
        if m_idx - lb < 0: return pd.Series(dtype=float)
        ret = pm.iloc[m_idx] / pm.iloc[m_idx - lb] - 1
        s = s.add(ret * wt, fill_value=0)
    return s


def mom_skip1_6_12(m_idx, pm, *_):
    """Skip-1: 50% × (p[-1]/p[-7]-1) + 50% × (p[-1]/p[-13]-1).
    Avoids short-term reversal — standard in academic momentum literature."""
    if m_idx < 13: return pd.Series(dtype=float)
    m6  = pm.iloc[m_idx - 1] / pm.iloc[m_idx - 7]  - 1
    m12 = pm.iloc[m_idx - 1] / pm.iloc[m_idx - 13] - 1
    return 0.5 * m6 + 0.5 * m12


def mom_accel(m_idx, pm, *_):
    """Acceleration: 50% standard 6+12M + 50% recent 3M vs prior 3M.
    'Prior 3M' = months [-6] to [-3], 'recent 3M' = months [-3] to [0].
    All lookbacks use only past prices (no LAB)."""
    if m_idx < 12: return pd.Series(dtype=float)
    # standard signal
    base = mom_6_12(m_idx, pm)
    # acceleration: recent 3M relative to prior 3M
    recent = pm.iloc[m_idx]     / pm.iloc[m_idx - 3]  - 1
    prior  = pm.iloc[m_idx - 3] / pm.iloc[m_idx - 6]  - 1
    accel  = recent - prior
    return 0.5 * base.add(accel * 0.5, fill_value=0)


def mom_of_mom(m_idx, pm, *_):
    """Momentum of momentum: 12M_now / 12M_prior_year - 1 as tiebreaker.
    Score = 50% current 12M + 50% (12M_now vs 12M_12m_ago).
    All past prices only."""
    if m_idx < 24: return pd.Series(dtype=float)
    mom_now  = pm.iloc[m_idx]      / pm.iloc[m_idx - 12] - 1
    mom_prev = pm.iloc[m_idx - 12] / pm.iloc[m_idx - 24] - 1
    mom_delta = mom_now - mom_prev
    return 0.5 * mom_now + 0.5 * mom_delta


def _make_rev_score(mom_weight, rev_weight):
    """Factory: composite score with revenue growth (z-scored) and momentum."""
    def fn(m_idx, pm, ebit_panel, rgrow_panel_ref=[None]):
        base = mom_6_12(m_idx, pm)
        if base.empty: return base
        m = pm.index[m_idx]
        if rgrow_panel is None or m not in rgrow_panel.index:
            return base
        rg = rgrow_panel.loc[m].dropna()
        if rg.empty: return base
        # z-score revenue growth cross-sectionally
        rg_z = (rg - rg.mean()) / rg.std() if rg.std() > 0 else rg * 0
        score = base * mom_weight + rg_z.reindex(base.index, fill_value=0) * rev_weight
        return score
    return fn


def _make_egrow_score(mom_weight, eg_weight):
    """Factory: composite score with EBIT growth (z-scored)."""
    def fn(m_idx, pm, ebit_panel):
        base = mom_6_12(m_idx, pm)
        if base.empty: return base
        m = pm.index[m_idx]
        if egrow_panel is None or m not in egrow_panel.index:
            return base
        eg = egrow_panel.loc[m].dropna()
        if eg.empty: return base
        eg_z = (eg - eg.mean()) / eg.std() if eg.std() > 0 else eg * 0
        score = base * mom_weight + eg_z.reindex(base.index, fill_value=0) * eg_weight
        return score
    return fn


# Absolute momentum filters (no LAB: only uses past prices)
def abs_filter_12m(m_idx, pm, *_):
    if m_idx < 12: return pd.Series(False, index=pm.columns)
    return (pm.iloc[m_idx] / pm.iloc[m_idx - 12] - 1) > 0

def abs_filter_6m(m_idx, pm, *_):
    if m_idx < 6: return pd.Series(False, index=pm.columns)
    return (pm.iloc[m_idx] / pm.iloc[m_idx - 6] - 1) > 0

def abs_filter_both(m_idx, pm, *_):
    if m_idx < 12: return pd.Series(False, index=pm.columns)
    r6  = (pm.iloc[m_idx] / pm.iloc[m_idx - 6]  - 1) > 0
    r12 = (pm.iloc[m_idx] / pm.iloc[m_idx - 12] - 1) > 0
    return r6 & r12

def ebit_growth_filter(m_idx, pm, *_):
    """Require EBIT TTM growing YoY (positive growth)."""
    m = pm.index[m_idx]
    if egrow_panel is None or m not in egrow_panel.index:
        return pd.Series(True, index=pm.columns)
    return egrow_panel.loc[m].reindex(pm.columns).fillna(True) > 0

def rev_growth_filter(m_idx, pm, *_):
    """Require Revenue TTM growing YoY."""
    m = pm.index[m_idx]
    if rgrow_panel is None or m not in rgrow_panel.index:
        return pd.Series(True, index=pm.columns)
    return rgrow_panel.loc[m].reindex(pm.columns).fillna(True) > 0


# ─── 4. Main ──────────────────────────────────────────────────────────────────

# Module-level panels (set after loading)
rgrow_panel = None
egrow_panel = None

def main():
    global rgrow_panel, egrow_panel

    print("=" * 70)
    print("  UK Momentum — Signal Variants  (2004-12 → 2026-07)")
    print(f"  Base: 6+12M | £100M | N=15 | MA200 | GLD in cash")
    print("=" * 70)

    print("\nLoading data...")
    tickers  = load_tickers()
    pm       = load_prices(tickers)
    (shares_by_ticker, ebit_panel,
     rev_panel, egrow_panel, rgrow_panel) = load_fundamentals(tickers, pm.index)
    mcap     = build_mcap_panel(pm, shares_by_ticker)
    ftse, gld_eom = load_market_data()

    # ── Define all variants ───────────────────────────────────────────────────
    def rev_score_50(m_idx, pm, ep):
        base = mom_6_12(m_idx, pm)
        if base.empty: return base
        m = pm.index[m_idx]
        if rgrow_panel is None or m not in rgrow_panel.index: return base
        rg = rgrow_panel.loc[m].dropna()
        if rg.empty: return base
        rg_z = (rg - rg.mean()) / rg.std() if rg.std() > 0 else rg * 0
        return base * 0.5 + rg_z.reindex(base.index, fill_value=0) * 0.5

    def rev_score_70(m_idx, pm, ep):
        base = mom_6_12(m_idx, pm)
        if base.empty: return base
        m = pm.index[m_idx]
        if rgrow_panel is None or m not in rgrow_panel.index: return base
        rg = rgrow_panel.loc[m].dropna()
        if rg.empty: return base
        rg_z = (rg - rg.mean()) / rg.std() if rg.std() > 0 else rg * 0
        return base * 0.7 + rg_z.reindex(base.index, fill_value=0) * 0.3

    def egrow_score_50(m_idx, pm, ep):
        base = mom_6_12(m_idx, pm)
        if base.empty: return base
        m = pm.index[m_idx]
        if egrow_panel is None or m not in egrow_panel.index: return base
        eg = egrow_panel.loc[m].dropna()
        if eg.empty: return base
        eg_z = (eg - eg.mean()) / eg.std() if eg.std() > 0 else eg * 0
        return base * 0.5 + eg_z.reindex(base.index, fill_value=0) * 0.5

    def egrow_score_70(m_idx, pm, ep):
        base = mom_6_12(m_idx, pm)
        if base.empty: return base
        m = pm.index[m_idx]
        if egrow_panel is None or m not in egrow_panel.index: return base
        eg = egrow_panel.loc[m].dropna()
        if eg.empty: return base
        eg_z = (eg - eg.mean()) / eg.std() if eg.std() > 0 else eg * 0
        return base * 0.7 + eg_z.reindex(base.index, fill_value=0) * 0.3

    def skip1_rev_score(m_idx, pm, ep):
        base = mom_skip1_6_12(m_idx, pm)
        if isinstance(base, pd.Series) and base.empty: return base
        m = pm.index[m_idx]
        if rgrow_panel is None or m not in rgrow_panel.index: return base
        rg = rgrow_panel.loc[m].dropna()
        if rg.empty: return base
        rg_z = (rg - rg.mean()) / rg.std() if rg.std() > 0 else rg * 0
        return base * 0.5 + rg_z.reindex(base.index, fill_value=0) * 0.5

    variants = [
        # (label, score_fn, extra_filter)
        ('Baseline: 6+12M',                mom_6_12,         None),
        ('A1. Skip-1M 6+12M',              mom_skip1_6_12,   None),
        ('A2. Acceleration (3M vs prior)',  mom_accel,        None),
        ('A3. Momentum-of-momentum 12M',   mom_of_mom,       None),
        ('B1. +Rev growth filter (>0)',     mom_6_12,         rev_growth_filter),
        ('B2. +EBIT growth filter (>0)',    mom_6_12,         ebit_growth_filter),
        ('B3. Score 50% mom+50% rev_z',    rev_score_50,     None),
        ('B4. Score 70% mom+30% rev_z',    rev_score_70,     None),
        ('B5. Score 50% mom+50% ebit_z',   egrow_score_50,   None),
        ('B6. Score 70% mom+30% ebit_z',   egrow_score_70,   None),
        ('C1. Abs filter: 12M>0',          mom_6_12,         abs_filter_12m),
        ('C2. Abs filter: 6M>0',           mom_6_12,         abs_filter_6m),
        ('C3. Abs filter: 6M>0 AND 12M>0', mom_6_12,         abs_filter_both),
        ('D1. Skip-1 + abs 12M>0',         mom_skip1_6_12,   abs_filter_12m),
        ('D2. Skip-1 + 50% rev_z',         skip1_rev_score,  None),
        ('D3. Accel + abs 12M>0',          mom_accel,        abs_filter_12m),
    ]

    print(f"\nRunning {len(variants)} variants...\n")

    results = []
    for label, score_fn, extra_filter in variants:
        r = run_backtest(pm, mcap, ebit_panel, ftse, gld_eom,
                         score_fn, extra_filter, label)
        s = stats(r, label)
        results.append(s)
        print(f"  {label:<42}  Sharpe={s['sharpe']:.3f}  CAGR={s['cagr']:>+6.1f}%  "
              f"MaxDD={s['maxdd']:>6.1f}%  Vol={s['vol']:.1f}%")

    # ── Summary table ─────────────────────────────────────────────────────────
    print(f"\n{'='*90}")
    print(f"  RESULTS SORTED BY SHARPE")
    print(f"  {'Label':<42} {'Sharpe':>7} {'CAGR':>7} {'MaxDD':>7} {'Vol':>6} {'Win%':>5}")
    print(f"  {'-'*80}")
    baseline = results[0]
    for s in sorted(results, key=lambda x: -x['sharpe']):
        d_sharpe = s['sharpe'] - baseline['sharpe']
        d_cagr   = s['cagr']   - baseline['cagr']
        flag = ' ◄ baseline' if s['label'] == baseline['label'] else \
               f' ▲ +{d_sharpe:.3f} sharpe' if d_sharpe > 0.005 else \
               f' ▼ {d_sharpe:.3f} sharpe' if d_sharpe < -0.005 else ' ≈'
        print(f"  {s['label']:<42} {s['sharpe']:>7.3f} {s['cagr']:>+6.1f}% "
              f"{s['maxdd']:>6.1f}% {s['vol']:>5.1f}% {s['win']:>4.1f}%{flag}")

    best = max(results, key=lambda x: x['sharpe'])
    print(f"\n{'='*70}")
    print(f"  WINNER: {best['label']}")
    print(f"  Sharpe={best['sharpe']:.3f}  CAGR={best['cagr']:+.1f}%  MaxDD={best['maxdd']:.1f}%")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
