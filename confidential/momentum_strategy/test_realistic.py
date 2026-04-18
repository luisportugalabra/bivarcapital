#!/usr/bin/env python3
"""
Realistic test: signal day N, execution day N+1.
No look-ahead bias.
"""

import pandas as pd
import numpy as np

print("Loading...")
sep = pd.read_parquet('sep_daily.parquet', columns=['ticker','date','closeadj'])
sf1 = pd.read_parquet('sf1_quarterly_ttm.parquet')
tickers_df = pd.read_parquet('tickers.parquet')
sp500 = pd.read_parquet('sp500_daily.parquet')

cats = ['Domestic Common Stock', 'Domestic Common Stock Primary Class']
vt = tickers_df[tickers_df['category'].isin(cats)]
valid = set(vt['ticker'])
sector_map = vt.set_index('ticker')['sector'].to_dict()

sep = sep[sep['ticker'].isin(valid)]
sep['date'] = pd.to_datetime(sep['date'])
sep = sep[sep['closeadj'] > 0].dropna(subset=['closeadj'])

daily = sep.pivot_table(index='date', columns='ticker', values='closeadj', aggfunc='last').sort_index()
daily = daily.loc[daily.index >= '2004-01-01']

sf1 = sf1[sf1['ticker'].isin(valid)].copy()
sf1['avail_date'] = pd.to_datetime(sf1['avail_ym'] + '-01')
mc_m = sf1.pivot_table(index='avail_date', columns='ticker', values='marketcap', aggfunc='last')
eb_m = sf1.pivot_table(index='avail_date', columns='ticker', values='ebit', aggfunc='last')
mc_daily = mc_m.reindex(daily.index).ffill()
eb_daily = eb_m.reindex(daily.index).ffill()

sp500['date'] = pd.to_datetime(sp500['date'])
sp500_s = sp500.sort_values('date').set_index('date')['close']

daily_dates = daily.index.to_series()
daily_dates_ym = daily_dates.groupby([daily_dates.dt.year, daily_dates.dt.month]).apply(list).to_dict()

print("Ready.\n")

def get_day(year, month, n):
    days = daily_dates_ym.get((year, month), [])
    if not days: return None
    if n == -1: return days[-1]
    idx = n - 1
    return days[idx] if idx < len(days) else None

def next_trading_day(date):
    """Get the next trading day after date."""
    idx = daily.index.get_loc(date)
    if idx + 1 < len(daily.index):
        return daily.index[idx + 1]
    return None


def run(signal_day, top_n=7, max_sec=3, min_mcap=10e9,
        lb_short=126, lb_long=252, w_short=0.5, w_long=0.5,
        ma_period=250):
    """Signal on day N, buy/sell on day N+1."""
    monthly_rets = []
    sp_rets = []

    for year in range(2005, 2027):
        for month in range(1, 13):
            # Signal date
            sig_date = get_day(year, month, signal_day)
            if sig_date is None or sig_date > daily.index[-2]: continue

            # Buy date = next trading day after signal
            buy_date = next_trading_day(sig_date)
            if buy_date is None: continue

            # Next month signal and sell
            sell_year = year if month < 12 else year + 1
            sell_month = month + 1 if month < 12 else 1
            sig_date_next = get_day(sell_year, sell_month, signal_day)
            if sig_date_next is None: continue
            sell_date = next_trading_day(sig_date_next)
            if sell_date is None: continue

            # S&P return (buy to sell)
            sp_b = sp500_s.loc[:buy_date]
            sp_s = sp500_s.loc[:sell_date]
            sp_ret = (sp_s.iloc[-1] / sp_b.iloc[-1] - 1) if len(sp_b) > 0 and len(sp_s) > 0 else 0
            sp_rets.append(sp_ret)

            # MA check on SIGNAL date (known before buying)
            if ma_period:
                sp_hist = sp500_s.loc[:sig_date].tail(ma_period + 1)
                if len(sp_hist) >= ma_period and sp_hist.iloc[-1] < sp_hist.iloc[-ma_period:].mean():
                    monthly_rets.append(0.0)
                    continue

            # Momentum computed on SIGNAL date prices
            idx = daily.index.get_loc(sig_date)
            if idx < max(lb_short, lb_long):
                monthly_rets.append(0.0)
                continue

            p_sig = daily.iloc[idx]
            mom = w_short * (p_sig / daily.iloc[idx - lb_short] - 1) + \
                  w_long * (p_sig / daily.iloc[idx - lb_long] - 1)

            mc_now = mc_daily.iloc[idx]
            eb_now = eb_daily.iloc[idx]

            mask = (mc_now >= min_mcap) & (p_sig > 0) & mom.notna() & (eb_now > 0)
            eligible = mom[mask].dropna()

            if len(eligible) == 0:
                monthly_rets.append(0.0)
                continue

            ranked = eligible.nlargest(top_n * 3)
            selected = []
            sec_counts = {}
            for t in ranked.index:
                sec = sector_map.get(t, 'Unknown')
                if sec_counts.get(sec, 0) < max_sec:
                    selected.append(t)
                    sec_counts[sec] = sec_counts.get(sec, 0) + 1
                if len(selected) >= top_n: break

            if not selected:
                monthly_rets.append(0.0)
                continue

            # Returns from BUY date to SELL date (next day prices)
            buy_prices = daily.loc[buy_date, selected]
            sell_prices = daily.loc[sell_date, selected]
            common = buy_prices.dropna().index.intersection(sell_prices.dropna().index)
            if len(common) == 0:
                monthly_rets.append(0.0)
                continue

            monthly_rets.append((sell_prices[common] / buy_prices[common] - 1).mean())

    rets = np.array(monthly_rets)
    sp = np.array(sp_rets[:len(rets)])
    n = len(rets)
    if n == 0: return {}
    cum = np.cumprod(1 + rets)
    sp_cum = np.cumprod(1 + sp)
    years = n / 12
    cagr = cum[-1] ** (1/years) - 1
    sp_cagr = sp_cum[-1] ** (1/years) - 1
    vol = np.std(rets, ddof=1) * np.sqrt(12)
    rf = 0.03/12
    sharpe = (np.mean(rets) - rf) / np.std(rets, ddof=1) * np.sqrt(12) if np.std(rets) > 0 else 0
    ds = rets[rets < rf] - rf
    ds_vol = np.std(ds, ddof=1) * np.sqrt(12) if len(ds) > 1 else vol
    sortino = (np.mean(rets) - rf) / (ds_vol / np.sqrt(12)) * np.sqrt(12) if ds_vol > 0 else 0
    peak = np.maximum.accumulate(cum)
    maxdd = ((cum - peak) / peak).min()
    mid = n // 2
    h1 = rets[:mid]; h2 = rets[mid:]
    h1s = (np.mean(h1)-rf)/np.std(h1,ddof=1)*np.sqrt(12) if len(h1)>12 and np.std(h1)>0 else 0
    h2s = (np.mean(h2)-rf)/np.std(h2,ddof=1)*np.sqrt(12) if len(h2)>12 and np.std(h2)>0 else 0

    return dict(cagr=round(cagr*100,1), alpha=round((cagr-sp_cagr)*100,1),
                sharpe=round(sharpe,2), sortino=round(sortino,2),
                maxdd=round(maxdd*100,1), vol=round(vol*100,1),
                h1=round(h1s,2), h2=round(h2s,2), n=n)


def fmt(r):
    if not r: return "NO DATA"
    return (f"CAGR {r['cagr']:+.1f}%  Alpha {r['alpha']:+.1f}%  "
            f"Sharpe {r['sharpe']:.2f}  Sortino {r['sortino']:.2f}  "
            f"MaxDD {r['maxdd']:.1f}%  Vol {r['vol']:.1f}%  "
            f"H1 {r['h1']:.2f}  H2 {r['h2']:.2f}")


# Test: signal day N, buy day N+1
print("=" * 100)
print("REALISTIC: Signal day N → Buy day N+1 (6+12eq $10B t7 MA250 EBIT sec3)")
print("=" * 100)
for sd in [1, 5, 10, 15, 17, 18, 19, 20, -1]:
    r = run(signal_day=sd)
    label = f"Sig {sd} → Buy {sd}+1" if sd > 0 else "Sig Last → Buy D+1"
    print(f"  {label:25s}  {fmt(r)}")

# Best signal days x configs
print("\n" + "=" * 100)
print("CROSS: SIGNAL DAY x CONFIG (signal N, buy N+1)")
print("=" * 100)

configs = [
    ("6+12eq t7 sec3",     dict(lb_short=126, lb_long=252, w_short=0.5, w_long=0.5, top_n=7, max_sec=3)),
    ("9+12eq t7 sec3",     dict(lb_short=189, lb_long=252, w_short=0.5, w_long=0.5, top_n=7, max_sec=3)),
    ("6w+9 t7 sec3",       dict(lb_short=126, lb_long=189, w_short=0.67, w_long=0.33, top_n=7, max_sec=3)),
    ("6+12eq t10 sec3",    dict(lb_short=126, lb_long=252, w_short=0.5, w_long=0.5, top_n=10, max_sec=3)),
    ("9+12eq t10 sec3",    dict(lb_short=189, lb_long=252, w_short=0.5, w_long=0.5, top_n=10, max_sec=3)),
]

best = []
for sd in [5, 17, 18, 19, -1]:
    for cfg_label, cfg in configs:
        r = run(signal_day=sd, **cfg)
        day_label = f"D{sd}" if sd > 0 else "Last"
        full = f"{day_label} {cfg_label}"
        best.append((full, r))
        print(f"  {full:30s}  {fmt(r)}")

print("\n" + "=" * 100)
print("RANKING BY SHARPE")
print("=" * 100)
best.sort(key=lambda x: x[1].get('sharpe', 0), reverse=True)
for i, (label, r) in enumerate(best[:15], 1):
    print(f"  {i:2d}. {label:30s}  Sharpe {r['sharpe']:.2f}  CAGR {r['cagr']:+.1f}%  MaxDD {r['maxdd']:.1f}%  Sort {r['sortino']:.2f}  H1 {r['h1']:.2f} H2 {r['h2']:.2f}")

print("\nDone.")
