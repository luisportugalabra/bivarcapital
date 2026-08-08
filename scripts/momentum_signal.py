#!/usr/bin/env python3
"""
BivarOptimalMomentum — Monthly Signal Generator

Downloads live data from TradingView, calculates the momentum strategy,
and outputs:
  1. momentum-data.json for the website (top 20 + selected 7)
  2. Console output with top 20

Strategy (from FINAL_STRATEGY.md):
  - Momentum = 50% × Perf.6M + 50% × Perf.1Y
  - Universe: US exchanges, market cap > $10B, EBIT > 0, common stock, primary
  - Select top 7 by composite (no sector cap)
  - Regime: S&P 500 < MA250 → buy GLD instead of stocks

Usage: python3 momentum_signal.py
"""
import os
import json
import sys
from datetime import datetime, date, timedelta

import pandas as pd
import numpy as np
from tradingview_screener import Query, col


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.dirname(SCRIPT_DIR)  # bivarcapital/
JSON_PATH = os.path.join(SITE_DIR, "momentum-data.json")
PORTFOLIO_PATH = os.path.join(SITE_DIR, "momentum-portfolio.json")
PICKS_HISTORY_PATH = os.path.join(SITE_DIR, "ytd-picks-history.json")


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
    df['exchange'] = df['ticker'].str.split(':').str[0]
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
    """Check S&P 500 vs MA250 via yfinance."""
    try:
        import yfinance as yf
        import math
        import warnings
        warnings.filterwarnings('ignore')
        data = yf.download('^GSPC', period='2y', progress=False)
        close = data['Close'].squeeze().dropna()
        if len(close) == 0:
            return None, None, True  # no data, assume OK
        last = float(close.iloc[-1])
        ma250 = float(close.tail(250).mean())
        # Guard against NaN (e.g. weekend/holiday runs with no market data)
        if math.isnan(last) or math.isnan(ma250):
            return None, None, True  # assume OK if can't determine
        return last, ma250, last >= ma250
    except Exception:
        return None, None, True  # assume OK if can't check


def select_top(df, n=7):
    """Select top N by composite (no sector cap)."""
    return [str(t) for t in df.head(n)['ticker']]


def _update_picks_history(tickers, today_str):
    """
    Append new period to ytd-picks-history.json when a new month starts.
    The previous period's end date is today, and the new period starts today.
    Only appends if the last entry's end month is before this month.
    """
    import calendar
    from datetime import datetime, date

    if not os.path.exists(PICKS_HISTORY_PATH):
        return

    with open(PICKS_HISTORY_PATH) as f:
        history = json.load(f)

    today = datetime.strptime(today_str, '%Y-%m-%d').date()
    today_ym = (today.year, today.month)

    if history:
        last_end = datetime.strptime(history[-1]['end'], '%Y-%m-%d').date()
        last_end_ym = (last_end.year, last_end.month)

        # Only add if we're in a new month vs the last period's end
        if today_ym <= last_end_ym:
            print(f"  Picks history: already up to date ({history[-1]['end']})")
            return

        # End date of new period = last day of current month
        last_day = calendar.monthrange(today.year, today.month)[1]
        new_end = date(today.year, today.month, last_day).isoformat()

        new_period = {
            "start": history[-1]['end'],
            "end": new_end,
            "tickers": list(tickers),
        }
        history.append(new_period)

        with open(PICKS_HISTORY_PATH, 'w') as f:
            json.dump(history, f, indent=2)

        print(f"  Picks history: added {new_period['start']} → {new_period['end']}: {tickers}")
    else:
        print("  Picks history: empty, skipping")


def main():
    print("Fetching TradingView data...")
    df = fetch_stocks()
    print(f"  Eligible: {len(df)} stocks")

    # Regime
    sp_last, sp_ma250, regime_ok = check_regime()
    regime = "momentum" if regime_ok else "gld"
    print(f"  S&P 500: {sp_last:,.2f}  MA250: {sp_ma250:,.2f}  Regime: {regime.upper()}")

    # Select top 7
    sel7 = select_top(df)

    # Build top 20 data
    top20 = []
    for i, (_, row) in enumerate(df.head(30).iterrows(), 1):
        t = str(row['ticker'])
        selected = t in sel7
        sector = str(row['sector'])

        entry = {
            "rank": i,
            "ticker": t,
            "name": str(row['name']),
            "sector": sector,
            "price": round(float(row.get('close', 0)), 2),
            "ret_6m": round(float(row['ret_6m']), 1),
            "ret_12m": round(float(row['ret_12m']), 1),
            "composite": round(float(row['composite'] * 100), 1),
            "mcap_b": round(float(row['mcap'] / 1e9), 1),
            "ebit_m": round(float(row['ebit'] / 1e6), 0),
            "selected": selected,
        }
        top20.append(entry)

    # Build JSON
    output = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "regime": regime,
        "sp500": round(sp_last, 2) if sp_last else None,
        "sp500_ma250": round(sp_ma250, 2) if sp_ma250 else None,
        "total_eligible": len(df),
        "portfolio": [t for t in top20 if t["selected"]],
        "top20": top20,
    }

    # Save JSON
    with open(JSON_PATH, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"  Saved: {JSON_PATH}")

    # ── PORTFOLIO TRACKER ─────────────────────────────────────────────────────
    # Signal is locked in on the last trading day of the month (whatever data
    # is fresh that day); it is executed — bought at that day's price — on the
    # next trading day, matching the backtest's end-of-month signal convention.
    try:
        with open(PORTFOLIO_PATH) as f:
            existing_portfolio = json.load(f)
        existing_holdings = {h['ticker']: h for h in existing_portfolio.get('holdings', [])}
        last_rebalance_month = existing_portfolio.get('last_rebalance', '')[:7]
        pending_signal = existing_portfolio.get('pending_signal')
    except (FileNotFoundError, json.JSONDecodeError):
        existing_holdings = {}
        last_rebalance_month = ''
        pending_signal = None

    current_month = datetime.now().strftime('%Y-%m')
    is_new_month  = current_month != last_rebalance_month

    # Build name/sector lookup from current signal
    name_map   = {str(row['ticker']): str(row['name'])   for _, row in df.head(30).iterrows()}
    sector_map = {str(row['ticker']): str(row['sector']) for _, row in df.head(30).iterrows()}

    pending_consumed = False
    if is_new_month:
        if pending_signal and pending_signal.get('for_month') == current_month:
            print(f"  Portfolio: new month ({current_month}), executing signal locked in on "
                  f"{pending_signal.get('computed_date')}...")
            exec_picks  = pending_signal['picks']  # [{ticker, name, sector}, ...]
            exec_tickers = [p['ticker'] for p in exec_picks]
            exec_name_map   = {p['ticker']: p['name']   for p in exec_picks}
            exec_sector_map = {p['ticker']: p['sector'] for p in exec_picks}
            pending_consumed = True
        else:
            print(f"  Portfolio: new month ({current_month}), no pending end-of-month signal found "
                  f"— falling back to today's data...")
            exec_tickers    = sel7
            exec_name_map   = name_map
            exec_sector_map = sector_map

        # Log the executed picks (not today's raw signal) so YTD history
        # reflects what was actually bought
        _update_picks_history(exec_tickers, output['date'])

        new_entries = [t for t in exec_tickers if t not in existing_holdings]

        entry_prices = {}
        if new_entries:
            print(f"  Fetching entry prices for: {new_entries}")
            try:
                import yfinance as yf
                ep_dl = yf.download(new_entries, period='1d', progress=False, auto_adjust=True)
                for t in new_entries:
                    try:
                        if len(new_entries) == 1:
                            entry_prices[t] = float(ep_dl['Close'].dropna().iloc[-1])
                        else:
                            entry_prices[t] = float(ep_dl['Close'][t].dropna().iloc[-1])
                    except Exception:
                        entry_prices[t] = None
            except Exception as e:
                print(f"  Warning: {e}")

        holdings = []
        for tk in exec_tickers:
            if tk in existing_holdings:
                h = existing_holdings[tk].copy()
            else:
                ep = entry_prices.get(tk)
                h = {
                    'ticker':        tk,
                    'name':          exec_name_map.get(tk, tk),
                    'sector':        exec_sector_map.get(tk, ''),
                    'entry_date':    output['date'],
                    'entry_price':   round(ep, 2) if ep else None,
                    'current_price': round(ep, 2) if ep else None,
                    'return_pct':    0.0,
                }
            # Update name/sector in case they changed
            h['name']   = exec_name_map.get(tk, h.get('name', tk))
            h['sector'] = exec_sector_map.get(tk, h.get('sector', ''))
            # Recalculate return
            ep = h.get('entry_price'); cp = h.get('current_price')
            h['return_pct'] = round((cp / ep - 1) * 100, 2) if ep and cp else 0.0
            holdings.append(h)
        last_rebalance_date = output['date']
    else:
        print(f"  Portfolio: same month ({current_month}), keeping holdings...")
        holdings = []
        for h in existing_portfolio.get('holdings', []):
            h = h.copy()
            ep = h.get('entry_price'); cp = h.get('current_price')
            h['return_pct'] = round((cp / ep - 1) * 100, 2) if ep and cp else 0.0
            holdings.append(h)
        last_rebalance_date = existing_portfolio.get('last_rebalance', output['date'])

    # Lock in tomorrow's signal if today is the last trading day of the month
    tomorrow = date.today() + timedelta(days=1)
    is_month_end_today = tomorrow.month != date.today().month or tomorrow.year != date.today().year

    if is_month_end_today:
        next_month_str = tomorrow.strftime('%Y-%m')
        new_pending_signal = {
            'for_month':     next_month_str,
            'computed_date': output['date'],
            'picks': [
                {'ticker': tk, 'name': name_map.get(tk, tk), 'sector': sector_map.get(tk, '')}
                for tk in sel7
            ],
        }
        print(f"  Today ({output['date']}) is the last trading day of the month — "
              f"locked in signal for {next_month_str}: {sel7}")
    elif pending_consumed:
        new_pending_signal = None
    else:
        new_pending_signal = pending_signal

    portfolio_output = {
        'last_rebalance':  last_rebalance_date,
        'updated':         output['date'],
        'holdings':        holdings,
        'pending_signal':  new_pending_signal,
    }
    with open(PORTFOLIO_PATH, 'w') as f:
        json.dump(portfolio_output, f, indent=2)
    print(f"  Saved: {PORTFOLIO_PATH}")

    # Print
    print(f"\n{'='*120}")
    print(f"  BivarOptimalMomentum — {output['date']}")
    print(f"  S&P 500: {sp_last:,.2f} | MA250: {sp_ma250:,.2f} | Regime: {regime.upper()}")
    print(f"{'='*120}")
    print(f"  {'#':>3} {'':>3} {'Ticker':<8} {'Name':<32} {'Sector':<24} {'Ret6m':>8} {'Ret12m':>8} {'Comp':>8} {'MCap$B':>8} {'EBIT$M':>8}")
    print(f"  {'-'*120}")
    for t in top20:
        sel = ">>>" if t['selected'] else ""
        print(f"  {t['rank']:3d} {sel:>3} {t['ticker']:<8} {t['name'][:31]:<32} {t['sector'][:23]:<24} {t['ret_6m']:>+7.1f}% {t['ret_12m']:>+7.1f}% {t['composite']:>+7.1f}% {t['mcap_b']:>7.1f} {t['ebit_m']:>7.0f}")

    print(f"\n  >>> = Selected for portfolio (top 7)")
    print(f"  Total eligible: {len(df)}")

    return output


if __name__ == "__main__":
    main()
