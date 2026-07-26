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
import ssl
import urllib.request
import urllib.parse
from datetime import datetime

import pandas as pd
import numpy as np
from tradingview_screener import Query, col


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.dirname(SCRIPT_DIR)  # bivarcapital/
JSON_PATH = os.path.join(SITE_DIR, "momentum-data.json")
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

    # Update YTD picks history on the 1st trading day of each month
    _update_picks_history(sel7, output['date'])

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

    # ── Send Telegram ────────────────────────────────────────────────────────
    _send_telegram(output)

    return output


def _send_telegram(data):
    """Send monthly momentum signal via Telegram."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    tg_token = os.environ.get('TELEGRAM_TOKEN', '8528820380:AAHNc3wBp_Nm2DCKunZurOGRRvi2e3fJ-MI')
    sb_url = 'https://efiyeiwdywodjxxnslvu.supabase.co'
    sb_key = os.environ.get('SUPABASE_SERVICE_KEY', '')

    try:
        req = urllib.request.Request(
            f'{sb_url}/rest/v1/telegram_subscribers?status=eq.approved&select=chat_id',
            headers={'apikey': sb_key, 'Authorization': f'Bearer {sb_key}'}
        )
        resp = json.loads(urllib.request.urlopen(req, context=ctx, timeout=10).read())
        chat_ids = [r['chat_id'] for r in resp]
        print(f"Sending Telegram to {len(chat_ids)} subscribers...")
    except Exception as e:
        print(f"Supabase error: {e}, falling back to admin only")
        chat_ids = [5151262026]

    regime     = data.get('regime', 'momentum')
    date_str   = data.get('date', '')
    portfolio  = data.get('portfolio', [])
    sp500      = data.get('sp500')
    sp500_ma   = data.get('sp500_ma250')

    if regime == 'gld':
        emoji = '🟡'
        regime_line = '⚠️ BEAR REGIME — S&P 500 below MA250'
        action_line = 'Action: Hold GLD (gold ETF) — no equity momentum this month.'
        picks_block = '   GLD (SPDR Gold Shares ETF)'
    else:
        emoji = '🟢'
        regime_line = '✅ BULL REGIME — S&P 500 above MA250'
        action_line = 'Action: Equal weight the 7 stocks below (~14.3% each).'
        tickers_fmt = '   ' + '  ·  '.join(t['ticker'] for t in portfolio)
        picks_block = tickers_fmt

    sp_line = f'S&P 500: {sp500:,.0f}  |  MA250: {sp500_ma:,.0f}' if sp500 and sp500_ma else ''

    tg_msg = f"""{emoji} Optimal Momentum — {date_str}

{regime_line}
{sp_line}

Portfolio this month:
{picks_block}

{action_line}

📊 Strategy: Monthly rebalance, top 7 large-cap momentum
   CAGR +28.9% | Sharpe 1.03 | Invested ~90%

bivarcapital.com/momentum.html"""

    for chat_id in chat_ids:
        try:
            tg_url = f'https://api.telegram.org/bot{tg_token}/sendMessage?chat_id={chat_id}&text={urllib.parse.quote(tg_msg)}'
            urllib.request.urlopen(tg_url, context=ctx, timeout=10)
            print(f"  Sent to {chat_id}")
        except Exception as e:
            print(f"  Failed for {chat_id}: {e}")


if __name__ == "__main__":
    main()
