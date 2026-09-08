#!/usr/bin/env python3
"""
UK Momentum — Execution Day Sensitivity

Signal always at EOM (end of month M).
Buy on business day N of month M+1 (N = 1, 2, 3, ... 10).
Sell at EOM of month M+1.

Fixed params: 6+12M | £100M | N=12 | MA200 | GLD
"""

import os, json
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

LSE_DIR    = '/Users/luisabrantes/eodhd_data/LSE'
PRICES_DIR = os.path.join(LSE_DIR, 'prices')
FUND_DIR   = os.path.join(LSE_DIR, 'fundamentals')
TICKERS_F  = os.path.join(LSE_DIR, 'tickers.parquet')

START = '2004-12'
END   = '2026-06'

BUY_COST   = 0.0065
SELL_COST  = 0.0015
RF_MONTHLY = 0.03 / 12
MIN_MCAP   = 100_000_000   # GBP
TOP_N      = 12
MA_PERIOD  = 200
MOM_LBS    = {6: 0.5, 12: 0.5}


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
    print(f"  Tickers: {len(gbx)} GBX common stocks")
    return gbx


def load_daily(tickers):
    """Load full daily price panel."""
    print("Loading daily prices...")
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
    daily = pd.concat(frames, axis=1).sort_index()
    daily = daily.ffill()
    print(f"  Daily panel: {daily.shape}")
    return daily


def load_eom(daily):
    """EOM prices as period index."""
    eom = daily.resample('ME').last()
    eom.index = eom.index.to_period('M')
    return eom.sort_index()


def load_fundamentals(tickers, pm_index):
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
                qdf = pd.DataFrame(rows).sort_values('period_end').set_index('period_end')
                qdf['ebit_ttm'] = qdf['ebit'].rolling(4, min_periods=4).sum()
                qdf = qdf.dropna(subset=['ebit_ttm'])
                qdf['avail_date'] = qdf.index + pd.Timedelta(days=45)
                for idx, row in qdf.iterrows():
                    ebit_records.append({'ticker': tkr, 'avail_date': row['avail_date'],
                                         'ebit_ttm': row['ebit_ttm']})
        except Exception:
            pass

    edf = pd.DataFrame(ebit_records)
    edf['ym'] = pd.to_datetime(edf['avail_date']).dt.to_period('M')
    ebit_panel = (edf.pivot_table(index='ym', columns='ticker',
                                   values='ebit_ttm', aggfunc='last')
                     .sort_index().reindex(pm_index).ffill(limit=4))
    return shares_by_ticker, ebit_panel


def build_mcap_panel(pm, shares_by_ticker):
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
                mcap.at[period, tkr] = price * sh / 100  # GBX→GBP
    return mcap


def load_ftse100():
    import yfinance as yf
    data = yf.download('^FTSE', start='1999-01-01', progress=False, auto_adjust=True)
    s = data['Close'].squeeze().dropna()
    s.index = pd.to_datetime(s.index)
    return s


def get_nth_bday(daily_index, year, month, n):
    """Return the n-th business day (1-based) in (year, month) from the actual trading calendar."""
    days_in_month = daily_index[
        (daily_index.year == year) & (daily_index.month == month)
    ]
    if len(days_in_month) >= n:
        return days_in_month[n - 1]
    elif len(days_in_month) > 0:
        return days_in_month[-1]
    return None


def run_exec_day(pm, daily, mcap_panel, ebit_panel, ftse100, exec_day):
    """
    Signal always at EOM of month M.
    exec_day=0  → buy EOM(M),      sell EOM(M+1)       [baseline]
    exec_day=N  → buy Day-N(M+1),  sell Day-N(M+2)     [consistent ~1-month hold]
    """
    months = pm.index[(pm.index >= pd.Period(START, 'M')) &
                      (pm.index <= pd.Period(END, 'M'))]
    daily_dates = daily.index

    strat_rets = []
    prev_picks = set()
    overlap_log = []  # for diagnostics

    for i, m in enumerate(months):
        m_idx = pm.index.get_loc(m)
        if m_idx + 2 >= len(pm.index):
            break
        next_m  = pm.index[m_idx + 1]
        next2_m = pm.index[m_idx + 2]

        # Regime check at EOM of signal month
        end_ts = m.to_timestamp(how='end')
        hist = ftse100.loc[:end_ts].tail(MA_PERIOD + 1)
        if len(hist) >= MA_PERIOD:
            if float(hist.iloc[-1]) < float(hist.tail(MA_PERIOD).mean()):
                strat_rets.append(0.0)
                prev_picks = set()
                continue

        # Signal: composite momentum at EOM of m
        mom = pd.Series(0.0, index=pm.columns)
        valid = True
        for lb, wt in MOM_LBS.items():
            if m_idx - lb < 0:
                valid = False
                break
            ret = pm.loc[m] / pm.loc[pm.index[m_idx - lb]] - 1
            mom = mom.add(ret * wt, fill_value=0)
        if not valid:
            strat_rets.append(0.0)
            continue

        mask = mom.notna() & (pm.loc[m] > 0)
        if m in mcap_panel.index:
            mask &= (mcap_panel.loc[m] >= MIN_MCAP)
        if m in ebit_panel.index:
            mask &= (ebit_panel.loc[m] > 0)

        eligible = mom[mask]
        if eligible.empty:
            strat_rets.append(0.0)
            prev_picks = set()
            continue

        selected = set(eligible.nlargest(TOP_N).index.tolist())
        n_actual = len(selected)
        buys  = len(selected - prev_picks)
        sells = len(prev_picks - selected)
        cost  = (buys * BUY_COST + sells * SELL_COST) / n_actual if n_actual > 0 else 0.0

        sel_list = list(selected)

        if exec_day == 0:
            # Buy at EOM(M), sell at EOM(M+1)
            buy_prices  = pm.loc[m, sel_list]
            sell_prices = pm.loc[next_m, sel_list]
        else:
            # Buy at Day-N of M+1, sell at Day-N of M+2  → same ~1-month hold
            buy_date  = get_nth_bday(daily_dates, next_m.year,  next_m.month,  exec_day)
            sell_date = get_nth_bday(daily_dates, next2_m.year, next2_m.month, exec_day)

            if buy_date is None or sell_date is None or buy_date >= sell_date:
                strat_rets.append(0.0)
                prev_picks = selected
                continue

            buy_prices  = daily.loc[buy_date,  sel_list]
            sell_prices = daily.loc[sell_date, sel_list]

            if prev_picks:
                overlap_log.append(len(selected & prev_picks) / TOP_N)

        fwd = (sell_prices / buy_prices - 1).dropna()
        gross = float(fwd.mean()) if len(fwd) > 0 else 0.0
        strat_rets.append(gross - cost)
        prev_picks = selected

    return np.array(strat_rets), overlap_log


def stats(rets):
    r = rets
    if len(r) < 12:
        return None
    cum   = np.cumprod(1 + r)
    yrs   = len(r) / 12
    cagr  = cum[-1] ** (1 / yrs) - 1
    vol   = np.std(r, ddof=1) * np.sqrt(12)
    sharpe = (np.mean(r) - RF_MONTHLY) / np.std(r, ddof=1) * np.sqrt(12)
    peak  = np.maximum.accumulate(cum)
    maxdd = ((cum - peak) / peak).min()
    return {
        'cagr':   round(cagr * 100, 1),
        'sharpe': round(sharpe, 3),
        'maxdd':  round(maxdd * 100, 1),
        'vol':    round(vol * 100, 1),
    }


def main():
    tickers = load_tickers()
    daily   = load_daily(tickers)
    pm      = load_eom(daily)
    pm      = pm[(pm.index >= pd.Period('2001-01', 'M')) &
                 (pm.index <= pd.Period(END, 'M'))]

    print("Loading fundamentals...")
    shares_by_ticker, ebit_panel = load_fundamentals(tickers, pm.index)
    print("Building mcap panel...")
    mcap_panel = build_mcap_panel(pm, shares_by_ticker)
    print("Loading FTSE 100...")
    ftse100 = load_ftse100()

    print(f"\nExecution day sensitivity — signal EOM, hold ~1 month (buy Day-N → sell Day-N next month)")
    print(f"\n{'Day':<8} {'CAGR':>8} {'Sharpe':>8} {'MaxDD':>8} {'Vol':>8}  {'Overlap':>8}")
    print(f"{'-'*56}")

    results = {}
    for d in [0, 1, 2, 3, 4, 5, 7, 10]:
        label = 'EOM' if d == 0 else f'Day {d}'
        rets, ovlp = run_exec_day(pm, daily, mcap_panel, ebit_panel, ftse100, d)
        s = stats(rets)
        ovlp_str = f'{np.mean(ovlp)*100:.1f}%' if ovlp else 'N/A'
        if s:
            results[label] = s
            print(f"{label:<8} {s['cagr']:>+7.1f}%  {s['sharpe']:>7.3f}  {s['maxdd']:>+7.1f}%  {s['vol']:>6.1f}%  {ovlp_str:>8}")

    print(f"\nNote: EOM uses exact monthly prices. Day N uses daily prices buy→sell same weekday.")


if __name__ == '__main__':
    main()
