#!/usr/bin/env python3
"""
Update ytd-data.json with live YTD performance of Optimal Momentum strategy.
Run daily via GitHub Actions.
"""

import yfinance as yf
import pandas as pd
import json
import numpy as np
from datetime import date

# Monthly picks for 2026 — update each month after rebalance
PERIODS = [
    ('2025-12-31', '2026-01-31', ['LITE', 'WDC', 'SNDK', 'MU', 'CIEN', 'WBD', 'STX']),
    ('2026-01-31', '2026-02-28', ['SNDK', 'MU', 'WDC', 'LITE', 'STX', 'CIEN', 'CDE']),
    ('2026-02-28', '2026-03-31', ['SNDK', 'LITE', 'BE', 'WDC', 'CIEN', 'MU', 'HL']),
    ('2026-03-31', '2026-04-30', ['SNDK', 'LITE', 'CIEN', 'WDC', 'BE', 'STX', 'FIX']),
    ('2026-04-30', '2026-05-31', ['SNDK', 'LITE', 'BE', 'WDC', 'CIEN', 'STX', 'MU']),
    ('2026-05-31', '2026-06-30', ['SNDK', 'LITE', 'BE', 'WDC', 'CIEN', 'STX', 'MU']),
    ('2026-06-30', '2026-07-31', ['SNDK', 'MU', 'LITE', 'BE', 'WDC', 'STX', 'DOCN']),
    # Add new period here at each monthly rebalance:
    # ('2026-07-31', '2026-08-31', [...]),
]

today = date.today().isoformat()
all_tickers = list(set(t for _, _, ts in PERIODS for t in ts)) + ['SPY']

print(f"Downloading prices ({today})...")
prices = yf.download(all_tickers, start='2025-12-30', end=today, auto_adjust=True, progress=False)['Close']
prices = prices.sort_index()

output_dates = []
output_strat = []
output_spy = []

strat_before_period = 1.0
spy_before_period = 1.0

for period_start, period_end, tickers in PERIODS:
    ps_date = pd.Timestamp(period_start)
    pe_date = pd.Timestamp(period_end)

    avail_base = prices.loc[:ps_date]
    if len(avail_base) == 0:
        continue
    base_prices = avail_base.iloc[-1]

    mask = (prices.index > ps_date) & (prices.index <= pe_date)
    period_prices = prices.loc[mask]

    for dt, row in period_prices.iterrows():
        date_str = dt.strftime('%Y-%m-%d')

        rets = []
        for t in tickers:
            if t in row.index and t in base_prices.index:
                bp = base_prices[t]
                cp = row[t]
                if pd.notna(bp) and pd.notna(cp) and bp > 0:
                    rets.append(cp / bp - 1)

        period_ret = float(np.mean(rets)) if rets else 0.0

        spy_ret = 0.0
        if 'SPY' in row.index and 'SPY' in base_prices.index:
            bp = base_prices['SPY']
            cp = row['SPY']
            if pd.notna(bp) and pd.notna(cp) and bp > 0:
                spy_ret = float(cp / bp - 1)

        output_dates.append(date_str)
        output_strat.append(round((strat_before_period * (1 + period_ret)) * 100 - 100, 2))
        output_spy.append(round((spy_before_period * (1 + spy_ret)) * 100 - 100, 2))

    # Update cumulative at end of period
    if len(period_prices) > 0:
        last_row = period_prices.iloc[-1]

        rets = []
        for t in tickers:
            if t in last_row.index and t in base_prices.index:
                bp = base_prices[t]
                cp = last_row[t]
                if pd.notna(bp) and pd.notna(cp) and bp > 0:
                    rets.append(cp / bp - 1)

        strat_before_period *= (1 + (float(np.mean(rets)) if rets else 0.0))

        if 'SPY' in last_row.index and 'SPY' in base_prices.index:
            bp = base_prices['SPY']
            cp = last_row['SPY']
            if pd.notna(bp) and pd.notna(cp) and bp > 0:
                spy_before_period *= float(cp / bp)

if not output_dates:
    print("No data generated.")
    exit(1)

data = {
    "updated": output_dates[-1],
    "ytd_strat": output_strat[-1],
    "ytd_spy": output_spy[-1],
    "dates": output_dates,
    "strat": output_strat,
    "spy": output_spy,
}

with open('ytd-data.json', 'w') as f:
    json.dump(data, f)

print(f"Saved {len(output_dates)} points — YTD: Momentum={output_strat[-1]}%, SPY={output_spy[-1]}%")
