#!/usr/bin/env python3
"""
BivarUKMomentum — Monthly Signal Generator

Downloads live data from TradingView LSE, calculates the UK momentum strategy,
and outputs uk-momentum-data.json for the website.

Strategy:
  - Momentum = 100% × Perf.6M
  - Universe: LSE, market cap > £250M (~$300M), EBIT > 0, common stock, GBX
  - Select top 7 by 6M performance
  - Regime: FTSE 100 < MA200 → cash

Usage: python3 uk_momentum_signal.py
"""
import os
import json
from datetime import datetime

import pandas as pd
import numpy as np
from tradingview_screener import Query, col

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR   = os.path.dirname(SCRIPT_DIR)
JSON_PATH  = os.path.join(SITE_DIR, 'uk-momentum-data.json')

MIN_MCAP_USD = 300_000_000   # ≈ £250M
TOP_N        = 7


def fetch_stocks():
    """Fetch eligible UK stocks from TradingView."""
    _, df = (Query()
             .select('name', 'description', 'market_cap_basic',
                     'oper_income_ttm', 'sector',
                     'Perf.6M', 'Perf.Y', 'close', 'currency')
             .where(
                 col('market_cap_basic') > MIN_MCAP_USD,
                 col('is_primary') == True,
                 col('type') == 'stock',
                 col('typespecs').has('common'),
                 col('oper_income_ttm') > 0,
                 col('currency') == 'GBX',
             )
             .set_markets('uk')
             .order_by('market_cap_basic', ascending=False)
             .limit(2_000)
             .get_scanner_data())

    df['exchange'] = df['ticker'].str.split(':').str[0]
    df['ticker']   = df['ticker'].str.split(':').str[-1]
    df['name']     = df['description'].astype(str)
    df = df.drop(columns=['description'], errors='ignore')

    df = df.rename(columns={
        'market_cap_basic': 'mcap',
        'oper_income_ttm':  'ebit',
        'Perf.6M':          'ret_6m',
        'Perf.Y':           'ret_12m',
    })

    df = df.dropna(subset=['ret_6m'])
    df['composite'] = df['ret_6m'] / 100   # 6M only

    return df.sort_values('composite', ascending=False).reset_index(drop=True)


def check_regime():
    """Check FTSE 100 vs MA200 via yfinance."""
    try:
        import yfinance as yf, math, warnings
        warnings.filterwarnings('ignore')
        data  = yf.download('^FTSE', period='2y', progress=False)
        close = data['Close'].squeeze().dropna()
        if len(close) == 0:
            return None, None, True
        last  = float(close.iloc[-1])
        ma200 = float(close.tail(200).mean())
        if math.isnan(last) or math.isnan(ma200):
            return None, None, True
        return last, ma200, last >= ma200
    except Exception:
        return None, None, True


def select_top(df, n=TOP_N):
    return [str(t) for t in df.head(n)['ticker']]


def main():
    print("Fetching TradingView LSE data...")
    df = fetch_stocks()
    print(f"  Eligible: {len(df)} stocks")

    ftse_last, ftse_ma200, regime_ok = check_regime()
    regime = "momentum" if regime_ok else "cash"
    print(f"  FTSE 100: {ftse_last:,.1f}  MA200: {ftse_ma200:,.1f}  Regime: {regime.upper()}")

    sel7 = select_top(df)

    top20 = []
    for i, (_, row) in enumerate(df.head(30).iterrows(), 1):
        t = str(row['ticker'])
        entry = {
            "rank":      i,
            "ticker":    t,
            "name":      str(row['name']),
            "sector":    str(row['sector']),
            "price":     round(float(row.get('close', 0)), 2),
            "ret_6m":    round(float(row['ret_6m']), 1),
            "ret_12m":   round(float(row.get('ret_12m', 0) or 0), 1),
            "composite": round(float(row['composite'] * 100), 1),
            "mcap_b":    round(float(row['mcap'] / 1e9), 2),
            "ebit_m":    round(float(row['ebit'] / 1e6), 0),
            "selected":  t in sel7,
        }
        top20.append(entry)

    output = {
        "date":           datetime.now().strftime("%Y-%m-%d"),
        "regime":         regime,
        "ftse100":        round(ftse_last, 1) if ftse_last else None,
        "ftse100_ma200":  round(ftse_ma200, 1) if ftse_ma200 else None,
        "total_eligible": len(df),
        "portfolio":      [t for t in top20 if t["selected"]],
        "top20":          top20,
    }

    with open(JSON_PATH, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"  Saved: {JSON_PATH}")

    print(f"\n{'='*110}")
    print(f"  BivarUKMomentum — {output['date']}")
    print(f"  FTSE 100: {ftse_last:,.1f} | MA200: {ftse_ma200:,.1f} | Regime: {regime.upper()}")
    print(f"{'='*110}")
    print(f"  {'#':>3} {'':>3} {'Ticker':<8} {'Name':<30} {'Sector':<22} {'Ret6m':>7} {'Ret12m':>7} {'MCap£B':>8} {'EBIT£M':>7}")
    print(f"  {'-'*110}")
    for t in top20:
        sel = ">>>" if t['selected'] else ""
        print(f"  {t['rank']:3d} {sel:>3} {t['ticker']:<8} {t['name'][:29]:<30} {t['sector'][:21]:<22} {t['ret_6m']:>+6.1f}% {t['ret_12m']:>+6.1f}% {t['mcap_b']:>7.2f} {t['ebit_m']:>6.0f}")

    print(f"\n  >>> = Selected for portfolio (top {TOP_N})")
    print(f"  Total eligible: {len(df)}")
    return output


if __name__ == "__main__":
    main()
