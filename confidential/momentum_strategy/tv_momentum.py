#!/usr/bin/env python3
"""
BivarOptimalMomentum — TradingView live signal generator.

Strategy (from FINAL_STRATEGY.md):
  - Momentum = 50% × Perf.6M + 50% × Perf.1Y
  - Universe: US exchanges, market cap > $10B, EBIT > 0, common stock, primary
  - Select top 7 by momentum composite (no sector cap)
  - Regime: S&P 500 < MA250 → buy GLD instead of stocks

Usage: python3 tv_momentum.py
"""
import pandas as pd
import numpy as np
from collections import defaultdict
from tradingview_screener import Query, col

def fetch_stocks():
    """Fetch eligible stocks from TradingView."""
    q = (Query()
         .select('name', 'description', 'market_cap_basic',
                 'oper_income_ttm', 'sector',
                 'Perf.6M', 'Perf.Y', 'close')
         .where(
             col('market_cap_basic') > 10_000_000_000,
             col('is_primary') == True,
             col('type') == 'stock',
             col('typespecs').has('common'),
             col('oper_income_ttm') > 0,
         )
         .set_markets('america')
         .order_by('market_cap_basic', ascending=False)
         .limit(5_000)
         .get_scanner_data()
    )
    _, df = q

    # US exchanges only
    us = ('NASDAQ:', 'NYSE:', 'AMEX:', 'NYSE ARCA:')
    df = df[df['ticker'].str.startswith(us)].copy()

    # Clean ticker and name
    df['ticker'] = df['ticker'].str.split(':').str[-1]
    df['name'] = df['description'].astype(str)
    df = df.drop(columns=['description'], errors='ignore')

    # Rename
    df = df.rename(columns={
        'market_cap_basic': 'mcap',
        'oper_income_ttm': 'ebit',
        'Perf.6M': 'ret_6m',
        'Perf.Y': 'ret_12m',
    })

    # Drop missing momentum
    df = df.dropna(subset=['ret_6m', 'ret_12m'])

    # Composite: TV returns % (50 = 50%), convert to decimal
    df['composite'] = 0.5 * df['ret_6m'] / 100 + 0.5 * df['ret_12m'] / 100

    return df.sort_values('composite', ascending=False).reset_index(drop=True)


def check_regime():
    """Check S&P 500 vs MA250 using TradingView."""
    q = (Query()
         .select('close', 'SMA250')
         .where(col('name') == 'SPX')
         .set_markets('america')
         .limit(1)
         .get_scanner_data()
    )
    _, sp = q
    if len(sp) == 0:
        # Fallback: try yfinance
        try:
            import yfinance as yf
            data = yf.download('^GSPC', period='2y', progress=False)
            close = data['Close'].squeeze()
            last = close.iloc[-1]
            ma250 = close.tail(250).mean()
            return last, ma250, last >= ma250
        except:
            return None, None, True  # assume OK if can't check

    last = sp.iloc[0]['close']
    ma250 = sp.iloc[0].get('SMA250', None)

    if ma250 is None or pd.isna(ma250):
        try:
            import yfinance as yf
            data = yf.download('^GSPC', period='2y', progress=False)
            close = data['Close'].squeeze()
            ma250 = close.tail(250).mean()
        except:
            ma250 = 0

    return last, ma250, last >= ma250


def select_top(df, n=7):
    """Select top N by composite (no sector cap)."""
    return [str(t) for t in df.head(n)['ticker']]


def main():
    # Fetch data
    df = fetch_stocks()
    print(f"Eligible stocks: {len(df)}")

    # Regime check
    sp_last, sp_ma250, regime_ok = check_regime()
    print(f"\nS&P 500: {sp_last:.2f}  MA250: {sp_ma250:.2f}  Above: {regime_ok}")

    # Select top 7
    sel7 = select_top(df)

    # Print regime
    print(f"\n{'='*140}")
    print(f"  S&P 500: {sp_last:.2f}  |  MA250: {sp_ma250:.2f}  |  Diff: {(sp_last/sp_ma250-1)*100:+.1f}%")
    if regime_ok:
        print(f"  REGIME: MOMENTUM — S&P 500 acima da MA250")
    else:
        print(f"  REGIME: DEFENSIVO — S&P 500 abaixo da MA250 → COMPRAR GLD")
    print(f"{'='*140}")

    # Print top 7
    print(f"\n  PORTFOLIO — Top 7 (equal weight 14.3%)")
    print(f"  {'#':>2}  {'Ticker':<8} {'Name':<35} {'Sector':<25} {'Ret6m':>8} {'Ret12m':>8} {'Comp':>8} {'MCap$B':>8}")
    print(f"  {'-'*115}")
    for i, t in enumerate(sel7, 1):
        row = df[df['ticker'] == t].iloc[0]
        name = str(row['name'])[:34]
        sector = str(row['sector'])[:24]
        mcap = row['mcap'] / 1e9
        print(f"  {i:>2}  {t:<8} {name:<35} {sector:<25} {row['ret_6m']:>+7.1f}% {row['ret_12m']:>+7.1f}% {row['composite']*100:>+7.1f}% {mcap:>7.1f}")

    if not regime_ok:
        print(f"\n  ⚠ MAS: S&P < MA250 → NÃO COMPRAR STOCKS → COMPRAR GLD")

    # Print top 50
    print(f"\n{'='*140}")
    print(f"  TOP 50")
    print(f"{'='*140}")
    print(f"  {'#':>3} {'SEL':>3} {'Ticker':<8} {'Name':<32} {'Sector':<23} {'Ret6m':>8} {'Ret12m':>8} {'Comp':>8} {'MCap$B':>8} {'EBIT$M':>9} {'Price':>9}")
    print(f"  {'-'*140}")

    for i, (_, row) in enumerate(df.head(50).iterrows(), 1):
        t = str(row['ticker'])
        name = str(row['name'])[:31]
        sector = str(row['sector'])[:22]
        sel = ">>>" if t in sel7 else ""
        mcap = row['mcap'] / 1e9
        ebit = row['ebit'] / 1e6
        price = row.get('close', 0)
        print(f"  {i:3d} {sel:>3} {t:<8} {name:<32} {sector:<23} {row['ret_6m']:>+7.1f}% {row['ret_12m']:>+7.1f}% {row['composite']*100:>+7.1f}% {mcap:>7.1f} {ebit:>8.0f} {price:>9.2f}")

    print(f"\n  Total eligible: {len(df)}")

    # Save CSV
    out_path = '/Users/luisabrantes/sharadar/momentum_tradingview_full.csv'
    out = df[['ticker', 'name', 'sector', 'mcap', 'ebit', 'ret_6m', 'ret_12m', 'composite']].copy()
    out.to_csv(out_path, index=False)
    print(f"  Saved: {out_path}")


if __name__ == "__main__":
    main()
