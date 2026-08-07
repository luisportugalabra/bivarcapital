#!/usr/bin/env python3
"""
Canada Momentum Signal Generator
- TradingView Screener for stock selection and current prices
- Yahoo Finance for TSX regime (^GSPTSE vs MA75)
- EODHD API for start-of-month entry prices

Strategy: MA75, top10, 250M CAD mcap, 50% 6M + 50% 12M composite

Saves: canada-momentum-data.json, canada-momentum-portfolio.json
"""
import os, json, warnings
from datetime import datetime, date
import pandas as pd
import numpy as np
import requests

warnings.filterwarnings('ignore')

from tradingview_screener import Query, col
import yfinance as yf

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
SITE_DIR       = os.path.dirname(SCRIPT_DIR)
DATA_PATH      = os.path.join(SITE_DIR, "canada-momentum-data.json")
PORTFOLIO_PATH = os.path.join(SITE_DIR, "canada-momentum-portfolio.json")

MCAP_MIN_CAD = 250_000_000
TOP_N        = 10
MA_W         = 75
TODAY        = date.today().isoformat()
EODHD_KEY    = '67405949053cf1.71181783'


def fetch_canada():
    print("Fetching TradingView data (Canada TSX)...")
    _, df = (Query()
        .select('name', 'description', 'market_cap_basic', 'Perf.6M', 'Perf.Y', 'close', 'currency')
        .where(
            col('market_cap_basic') > MCAP_MIN_CAD,
            col('currency') == 'CAD',
        )
        .set_markets('canada')
        .order_by('market_cap_basic', ascending=False)
        .limit(2000)
        .get_scanner_data()
    )
    print(f"  Raw rows: {len(df)}")

    df = df[df['ticker'].str.startswith('TSX:')].copy()
    df['code'] = df['ticker'].str.replace('TSX:', '', regex=False)
    df = df.dropna(subset=['Perf.6M', 'Perf.Y', 'close']).copy()

    # Exclude CDRs (Canadian Depositary Receipts = US stocks cross-listed)
    cdr_mask = df['description'].fillna('').str.contains('Deposit', case=False, na=False)
    df = df[~cdr_mask].copy()
    print(f"  After CDR filter: {len(df)}")

    df['composite'] = 0.5 * df['Perf.6M'] + 0.5 * df['Perf.Y']
    print(f"  Eligible: {len(df)}")

    return df.sort_values('composite', ascending=False).reset_index(drop=True)


def check_regime():
    """TSX Composite vs MA75 via yfinance."""
    tsx = yf.download('^GSPTSE', period='200d', auto_adjust=True, progress=False)
    close = tsx['Close']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.dropna()
    last = float(close.iloc[-1])
    ma75 = float(close.rolling(MA_W).mean().iloc[-1])
    return last >= ma75, round(last, 1), round(ma75, 1)


def get_som_prices_eodhd(tickers):
    """Get start-of-month prices for TSX tickers via EODHD API."""
    month_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
    result = {}
    for tk in tickers:
        url = (f'https://eodhd.com/api/eod/{tk}.TO'
               f'?api_token={EODHD_KEY}&fmt=json&from={month_start}&to={TODAY}')
        try:
            r = requests.get(url, timeout=10)
            rows = r.json()
            if rows:
                first = rows[0]
                result[tk] = (float(first['adjusted_close']), first['date'])
        except Exception as e:
            print(f"  EODHD fail {tk}: {e}")
    return result


def load_existing_portfolio():
    try:
        with open(PORTFOLIO_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def build_monthly_breakdown(existing, new_holdings, is_new_month, regime_str):
    breakdown = existing.get('monthly_breakdown', [])

    if is_new_month:
        for m in breakdown:
            if m.get('is_current'):
                m['is_current'] = False

        cur_month_label = datetime.now().strftime('%b %Y')
        tickers = [h['ticker'] for h in new_holdings]

        if not any(m['month'] == cur_month_label for m in breakdown):
            breakdown.append({
                'month':      cur_month_label,
                'is_current': True,
                'start':      TODAY,
                'end':        None,
                'regime':     regime_str,
                'tickers':    tickers,
                'return_pct': None,
            })
    else:
        for m in breakdown:
            if m.get('is_current'):
                m['regime'] = regime_str
                m['tickers'] = [h['ticker'] for h in new_holdings]

    return breakdown[-37:]


def main():
    df = fetch_canada()

    regime_ok, tsx_val, tsx_ma75 = check_regime()
    regime_str = 'momentum' if regime_ok else 'defensive'
    pct_above  = round((tsx_val / tsx_ma75 - 1) * 100, 1)
    print(f"  Regime: {regime_str.upper()}  TSX: {tsx_val}  MA75: {tsx_ma75}  ({pct_above:+.1f}%)")

    top_df   = df.head(TOP_N) if regime_ok else df.iloc[0:0]
    selected = set(top_df['code'].tolist())

    top20 = []
    for i, row in df.head(20).iterrows():
        code = row['code']
        top20.append({
            'rank':      int(i) + 1,
            'ticker':    code,
            'name':      str(row.get('name', code)),
            'ret_6m':    round(float(row['Perf.6M']), 2),
            'ret_12m':   round(float(row['Perf.Y']), 2),
            'composite': round(float(row['composite']), 2),
            'mcap_b':    round(float(row['market_cap_basic']) / 1e9, 3),
            'selected':  code in selected,
        })

    signal = {
        'date':           TODAY,
        'regime':         regime_str,
        'tsx':            tsx_val,
        'tsx_ma75':       tsx_ma75,
        'pct_above_ma':   pct_above,
        'total_eligible': int(len(df)),
        'portfolio':      [s for s in top20 if s['selected']],
        'top20':          top20,
        'updated':        TODAY,
    }
    with open(DATA_PATH, 'w') as f:
        json.dump(signal, f, indent=2)
    print(f"  Saved: {DATA_PATH}")

    # ── Portfolio tracker ──────────────────────────────────────────────────────
    existing     = load_existing_portfolio()
    existing_map = {h['ticker']: h for h in existing.get('holdings', [])}
    last_rebal_m = existing.get('last_rebalance', '')[:7]
    current_m    = datetime.now().strftime('%Y-%m')
    is_new_month = current_m != last_rebal_m

    price_map = {row['code']: float(row['close']) for _, row in df.iterrows()}

    if is_new_month and regime_ok:
        print(f"  Portfolio: NEW MONTH ({current_m}), rebalancing to top {TOP_N}...")
        top_tickers = [row['code'] for _, row in top_df.iterrows()]
        print(f"  Fetching start-of-month prices from EODHD...")
        som = get_som_prices_eodhd(top_tickers)

        holdings = []
        for _, row in top_df.iterrows():
            code = row['code']
            cp   = price_map.get(code)
            if code in som:
                ep, edate = som[code]
            else:
                ep, edate = cp, TODAY
            ret = round((cp / ep - 1) * 100, 2) if ep and cp else None
            holdings.append({
                'ticker':        code,
                'name':          str(row.get('name', code)),
                'entry_date':    edate,
                'entry_price':   round(ep, 4) if ep else None,
                'current_price': round(cp, 4) if cp else None,
                'return_pct':    ret,
            })
        last_rebalance = min(v[1] for v in som.values()) if som else TODAY

    elif not regime_ok:
        print(f"  Portfolio: DEFENSIVE — cash")
        holdings = []
        last_rebalance = existing.get('last_rebalance', TODAY)

    else:
        print(f"  Portfolio: same month ({current_m}), updating prices...")
        holdings = []
        for h in existing.get('holdings', []):
            h = h.copy()
            cp = price_map.get(h['ticker'])
            ep = h.get('entry_price')
            if cp:
                h['current_price'] = round(cp, 4)
            if ep and h.get('current_price'):
                h['return_pct'] = round((h['current_price'] / ep - 1) * 100, 2)
            holdings.append(h)
        last_rebalance = existing.get('last_rebalance', TODAY)

    breakdown = build_monthly_breakdown(existing, holdings, is_new_month, regime_str)

    months_2026 = [m for m in breakdown if '2026' in m.get('month', '') and not m.get('is_current')]
    if months_2026:
        ytd = 1.0
        for m in months_2026:
            if m.get('return_pct') is not None:
                ytd *= (1 + m['return_pct'] / 100)
        ytd_2026 = round((ytd - 1) * 100, 2)
    else:
        ytd_2026 = existing.get('ytd_2026', 0)

    portfolio = {
        'last_rebalance':    last_rebalance,
        'updated':           TODAY,
        'ytd_2026':          ytd_2026,
        'regime':            regime_str,
        'currency':          'CAD',
        'tsx':               tsx_val,
        'tsx_ma75':          tsx_ma75,
        'holdings':          holdings,
        'monthly_breakdown': breakdown,
        'tsx_annual':        existing.get('tsx_annual', {}),
    }
    with open(PORTFOLIO_PATH, 'w') as f:
        json.dump(portfolio, f, indent=2)
    print(f"  Saved: {PORTFOLIO_PATH}")

    print(f"\n{'='*80}")
    print(f"Canada Momentum — {TODAY} — {regime_str.upper()}")
    print(f"{'='*80}")
    print(f"{'#':>3} {'':>3} {'Ticker':<10} {'Name':<28} {'6M':>8} {'12M':>8} {'Comp':>8} {'MCap B CAD':>12}")
    print(f"{'-'*80}")
    for s in top20:
        mk = ">>>" if s['selected'] else ""
        print(f"{s['rank']:3d} {mk:>3} {s['ticker']:<10} {s['name'][:27]:<28} "
              f"{s['ret_6m']:>+7.1f}% {s['ret_12m']:>+7.1f}% {s['composite']:>+7.1f}% {s['mcap_b']:>10.3f}")
    print(f"\nTop {TOP_N} selected | {len(df)} eligible | Regime: {regime_str.upper()}")


if __name__ == '__main__':
    main()
