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
strat_cum_before_current = 1.0  # strat_cum locked at end of last completed period
spy_cum_before_current = 1.0

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

        if not rets:
            continue  # skip days with no price data (e.g. yfinance delay)

        period_ret = float(np.mean(rets))

        spy_ret = 0.0
        if 'SPY' in row.index and 'SPY' in base_prices.index:
            bp, cp = base_prices['SPY'], row['SPY']
            if pd.notna(bp) and pd.notna(cp) and bp > 0:
                spy_ret = float(cp / bp - 1)

        output_dates.append(date_str)
        output_strat.append(round((strat_cum * (1 + period_ret)) * 100 - 100, 2))
        output_spy.append(round((spy_cum * (1 + spy_ret)) * 100 - 100, 2))

    # Save cumulative before updating with current (open) period
    if pd.Timestamp(period['end']) > pd.Timestamp(today):
        strat_cum_before_current = strat_cum
        spy_cum_before_current = spy_cum

    # Update cumulative at end of period (use last row with valid data)
    valid_rows = period_prices.dropna(how='all')
    if len(valid_rows) > 0:
        last_row = valid_rows.iloc[-1]
        rets = []
        for t in tickers:
            if t in last_row.index and t in base_prices.index:
                bp, cp = base_prices[t], last_row[t]
                if pd.notna(bp) and pd.notna(cp) and bp > 0:
                    rets.append(float(cp / bp - 1))
        if rets:
            strat_cum *= (1 + float(np.mean(rets)))

        if 'SPY' in last_row.index and 'SPY' in base_prices.index:
            bp, cp = base_prices['SPY'], last_row['SPY']
            if pd.notna(bp) and pd.notna(cp) and bp > 0:
                spy_cum *= float(cp / bp)

if not output_dates:
    print("No data generated.")
    exit(1)

# ── Append intraday point for today ──────────────────────────────────────────
# Replaces or adds today's entry using live prices so the chart is always current.
current_period = next((p for p in periods if pd.Timestamp(p['end']) > pd.Timestamp(today)), None)
if current_period:
    print("Fetching intraday prices for today's chart point...")
    cp_tickers = current_period['tickers']
    ps_date = pd.Timestamp(current_period['start'])
    avail_base = prices.loc[:ps_date]
    if len(avail_base) > 0:
        base_prices_cur = avail_base.iloc[-1]
        intraday_rets = []
        spy_intraday_ret = 0.0
        for tk in cp_tickers:
            try:
                live = yf.Ticker(tk).fast_info.last_price
                bp = base_prices_cur.get(tk) if hasattr(base_prices_cur, 'get') else (base_prices_cur[tk] if tk in base_prices_cur.index else None)
                if live and bp and pd.notna(bp) and bp > 0:
                    intraday_rets.append(live / float(bp) - 1)
            except Exception:
                pass
        try:
            spy_live = yf.Ticker('SPY').fast_info.last_price
            spy_bp = base_prices_cur.get('SPY') if hasattr(base_prices_cur, 'get') else (base_prices_cur['SPY'] if 'SPY' in base_prices_cur.index else None)
            if spy_live and spy_bp and pd.notna(spy_bp) and spy_bp > 0:
                spy_intraday_ret = spy_live / float(spy_bp) - 1
        except Exception:
            pass

        if intraday_rets:
            intraday_period_ret = float(np.mean(intraday_rets))
            # Use strat_cum BEFORE current period to avoid double-counting July
            intraday_strat = round((strat_cum_before_current * (1 + intraday_period_ret)) * 100 - 100, 2)
            intraday_spy = round((spy_cum_before_current * (1 + spy_intraday_ret)) * 100 - 100, 2)
            # Replace last entry if it's already today, else append
            if output_dates and output_dates[-1] == today:
                output_dates[-1] = today
                output_strat[-1] = intraday_strat
                output_spy[-1] = intraday_spy
            else:
                output_dates.append(today)
                output_strat.append(intraday_strat)
                output_spy.append(intraday_spy)
            print(f"  Intraday point added: {today} strat={intraday_strat}% spy={intraday_spy}%")

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
