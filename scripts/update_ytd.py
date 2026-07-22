#!/usr/bin/env python3
"""
Update ytd-data.json with live YTD performance of Optimal Momentum strategy.
Run daily via GitHub Actions.

Picks history is stored in ytd-picks-history.json and updated automatically
by momentum_signal.py on the 1st trading day of each month.
"""

import yfinance as yf
import pandas as pd
import json
import numpy as np
import os
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.dirname(SCRIPT_DIR)

PICKS_PATH = os.path.join(SITE_DIR, 'ytd-picks-history.json')
OUTPUT_PATH = os.path.join(SITE_DIR, 'ytd-data.json')

today = date.today().isoformat()

# Load picks history
with open(PICKS_PATH) as f:
    periods = json.load(f)

all_tickers = list(set(t for p in periods for t in p['tickers'])) + ['SPY']

print(f"Downloading prices for {len(all_tickers)} tickers ({today})...")
prices = yf.download(all_tickers, start='2025-12-30', end=today, auto_adjust=True, progress=False)['Close']
prices = prices.sort_index()

output_dates = []
output_strat = []
output_spy = []

strat_cum = 1.0
spy_cum = 1.0

for period in periods:
    ps_date = pd.Timestamp(period['start'])
    pe_date = pd.Timestamp(period['end'])
    tickers = period['tickers']

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
                bp, cp = base_prices[t], row[t]
                if pd.notna(bp) and pd.notna(cp) and bp > 0:
                    rets.append(float(cp / bp - 1))

        period_ret = float(np.mean(rets)) if rets else 0.0

        spy_ret = 0.0
        if 'SPY' in row.index and 'SPY' in base_prices.index:
            bp, cp = base_prices['SPY'], row['SPY']
            if pd.notna(bp) and pd.notna(cp) and bp > 0:
                spy_ret = float(cp / bp - 1)

        output_dates.append(date_str)
        output_strat.append(round((strat_cum * (1 + period_ret)) * 100 - 100, 2))
        output_spy.append(round((spy_cum * (1 + spy_ret)) * 100 - 100, 2))

    # Update cumulative at end of period
    if len(period_prices) > 0:
        last_row = period_prices.iloc[-1]
        rets = []
        for t in tickers:
            if t in last_row.index and t in base_prices.index:
                bp, cp = base_prices[t], last_row[t]
                if pd.notna(bp) and pd.notna(cp) and bp > 0:
                    rets.append(float(cp / bp - 1))
        strat_cum *= (1 + (float(np.mean(rets)) if rets else 0.0))

        if 'SPY' in last_row.index and 'SPY' in base_prices.index:
            bp, cp = base_prices['SPY'], last_row['SPY']
            if pd.notna(bp) and pd.notna(cp) and bp > 0:
                spy_cum *= float(cp / bp)

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

with open(OUTPUT_PATH, 'w') as f:
    json.dump(data, f)

print(f"Saved {len(output_dates)} points — YTD: Momentum={output_strat[-1]}%, SPY={output_spy[-1]}%")
