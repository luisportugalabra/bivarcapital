#!/usr/bin/env python3
"""What would the strategy buy TODAY? 6w+9 $10B t7 MA250 EBIT"""

import pandas as pd
import numpy as np

# Load data
sep = pd.read_parquet('sep_daily.parquet', columns=['ticker','date','closeadj'])
sf1 = pd.read_parquet('sf1_quarterly_ttm.parquet')
tickers = pd.read_parquet('tickers.parquet')
sp500 = pd.read_parquet('sp500_daily.parquet')

# Filter common stock
cats = ['Domestic Common Stock', 'Domestic Common Stock Primary Class']
valid_tickers = tickers[tickers['category'].isin(cats)]
valid = set(valid_tickers['ticker'])
name_map = valid_tickers.set_index('ticker')['name'].to_dict()
sector_map = valid_tickers.set_index('ticker')['sector'].to_dict()

sep = sep[sep['ticker'].isin(valid)]
sep['date'] = pd.to_datetime(sep['date'])
sep = sep[sep['closeadj'] > 0].dropna(subset=['closeadj'])

# Latest prices
latest = sep.sort_values('date').groupby('ticker').last()
latest_date = sep['date'].max()
print(f"Latest price date: {latest_date.date()}")

# EOM price matrix for momentum calc
sep['ym'] = sep['date'].dt.to_period('M')
eom = sep.sort_values('date').groupby(['ticker','ym']).last().reset_index()
pm = eom.pivot(index='ym', columns='ticker', values='closeadj').sort_index()

current_month = pm.index[-1]
print(f"Current month: {current_month}")

# MA250 check
sp500['date'] = pd.to_datetime(sp500['date'])
sp500 = sp500.sort_values('date').set_index('date')['close']
sp_recent = sp500.tail(251)
sp_last = sp_recent.iloc[-1]
sp_ma250 = sp_recent.iloc[-250:].mean()
ma_ok = sp_last >= sp_ma250
print(f"\nS&P 500: {sp_last:.0f}  MA250: {sp_ma250:.0f}  Above: {ma_ok}")

if not ma_ok:
    print("\n*** MA250 FILTER: CASH — S&P below MA250. No stocks to buy. ***")
else:
    # Fundamentals — latest available
    sf1_valid = sf1[sf1['ticker'].isin(valid)].copy()
    latest_fundies = sf1_valid.sort_values('avail_ym').groupby('ticker').last()

    # Market cap filter >$10B
    mc = latest_fundies['marketcap']
    ebit = latest_fundies['ebit']

    eligible = mc[(mc >= 10e9) & (ebit > 0)].index
    eligible = [t for t in eligible if t in pm.columns]

    # Composite momentum: 67% * 6m + 33% * 9m
    m_idx = len(pm.index) - 1
    if m_idx >= 9:
        p_now = pm.iloc[m_idx]
        p_6m = pm.iloc[m_idx - 6]
        p_9m = pm.iloc[m_idx - 9]

        mom_6 = p_now / p_6m - 1
        mom_9 = p_now / p_9m - 1
        mom_composite = 0.67 * mom_6 + 0.33 * mom_9

        # Filter
        mom_eligible = mom_composite[eligible].dropna()
        mom_eligible = mom_eligible[mom_eligible.index.isin(p_now[p_now > 0].index)]

        # Top 7
        top7 = mom_eligible.nlargest(7)

        print(f"\nEligible stocks: {len(mom_eligible)}")
        print(f"\n{'='*85}")
        print(f"PORTFOLIO — 6w+9 $10B t7 MA250 EBIT — {latest_date.date()}")
        print(f"{'='*85}")
        print(f"{'#':>2}  {'Ticker':<7} {'Name':<30} {'Sector':<22} {'Mom6':>7} {'Mom9':>7} {'Comp':>7} {'MCap':>8}")
        print(f"{'-'*85}")

        for i, (ticker, score) in enumerate(top7.items(), 1):
            name = name_map.get(ticker, '?')[:29]
            sector = sector_map.get(ticker, '?')[:21]
            m6 = mom_6.get(ticker, 0) * 100
            m9 = mom_9.get(ticker, 0) * 100
            comp = score * 100
            mcap = mc.get(ticker, 0) / 1e9
            print(f"{i:2d}  {ticker:<7} {name:<30} {sector:<22} {m6:+6.1f}% {m9:+6.1f}% {comp:+6.1f}% ${mcap:6.0f}B")

        print(f"\nEqual weight: {100/7:.1f}% each")

        # Show top 15 for context
        top15 = mom_eligible.nlargest(15)
        print(f"\n{'='*85}")
        print(f"FULL TOP 15 (for context)")
        print(f"{'='*85}")
        for i, (ticker, score) in enumerate(top15.items(), 1):
            name = name_map.get(ticker, '?')[:29]
            sector = sector_map.get(ticker, '?')[:21]
            m6 = mom_6.get(ticker, 0) * 100
            m9 = mom_9.get(ticker, 0) * 100
            comp = score * 100
            mcap = mc.get(ticker, 0) / 1e9
            marker = " <<<" if i <= 7 else ""
            print(f"{i:2d}  {ticker:<7} {name:<30} {sector:<22} {m6:+6.1f}% {m9:+6.1f}% {comp:+6.1f}% ${mcap:6.0f}B{marker}")
