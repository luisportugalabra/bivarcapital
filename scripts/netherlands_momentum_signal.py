#!/usr/bin/env python3
"""
Netherlands Momentum Signal Generator
Ranking signal comes exclusively from TradingView Screener. Regime comes
exclusively from Yahoo Finance (real AEX index). EODHD is used only for
historical data that TradingView's live snapshot doesn't carry: start-of-month
entry prices and 252-day realized volatility for the inverse-vol weights.

Strategy (see research/netherlands_momentum_report.html):
  - Universe: Euronext Amsterdam (AS), all listed stocks
  - Eligibility: mcap > 92M EUR (absolute floor) AND in the top 60% by mcap
    among floor-passing stocks (i.e. above their 40th percentile of mcap)
  - Signal: 12-1 momentum (12-month return excluding the most recent month),
    derived from TradingView's Perf.Y and Perf.1M via
    composite = (1+Perf.Y/100)/(1+Perf.1M/100) - 1
  - Select top 10 by composite
  - Weighting: inverse volatility (252-day daily realized vol), normalized to 1
  - Regime: AEX index (Yahoo Finance) vs its own 100-day moving average
  - Monthly rebalance

Saves:
  - netherlands-momentum-data.json
  - netherlands-momentum-portfolio.json
"""
import os, json, statistics
from datetime import datetime, date

import pandas as pd
from tradingview_screener import Query, col

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
SITE_DIR       = os.path.dirname(SCRIPT_DIR)
DATA_PATH      = os.path.join(SITE_DIR, "netherlands-momentum-data.json")
PORTFOLIO_PATH = os.path.join(SITE_DIR, "netherlands-momentum-portfolio.json")
EODHD_DIR      = os.path.normpath(os.path.join(os.path.expanduser("~"), "eodhd_data", "AS", "prices"))

MCAP_FLOOR_EUR = 92_000_000
MCAP_PCTILE    = 0.40   # drop bottom 40% by mcap among floor-passers
TOP_N          = 10
VOL_LOOKBACK   = 252
TODAY          = date.today().isoformat()


def fetch_netherlands():
    """Fetch Euronext Amsterdam stocks from TV Screener with 12-1 momentum."""
    print("Fetching TradingView data (Netherlands)...")
    _, df = (Query()
        .select('name', 'description', 'market_cap_basic', 'Perf.1M', 'Perf.6M', 'Perf.Y', 'close')
        .set_markets('netherlands')
        .order_by('market_cap_basic', ascending=False)
        .limit(500)
        .get_scanner_data()
    )
    print(f"  Raw rows: {len(df)}")

    df = df[df['ticker'].str.startswith('EURONEXT:')].copy()
    df['code'] = df['ticker'].str.replace('EURONEXT:', '', regex=False)

    df = df.dropna(subset=['Perf.1M', 'Perf.Y', 'market_cap_basic']).copy()
    print(f"  With perf + mcap data: {len(df)}")

    floor = df[df['market_cap_basic'] > MCAP_FLOOR_EUR].copy()
    print(f"  Above {MCAP_FLOOR_EUR/1e6:.0f}M EUR floor: {len(floor)}")

    pctile_val = floor['market_cap_basic'].quantile(MCAP_PCTILE)
    elig = floor[floor['market_cap_basic'] >= pctile_val].copy()
    print(f"  After top-60%-by-mcap filter: {len(elig)}")

    # 12-1 momentum: skip the most recent month
    elig['composite'] = ((1 + elig['Perf.Y'] / 100) / (1 + elig['Perf.1M'] / 100) - 1) * 100

    return elig.sort_values('composite', ascending=False).reset_index(drop=True)


def check_regime():
    """AEX vs MA100 via yfinance (real index, not synthetic)."""
    import yfinance as yf, warnings
    warnings.filterwarnings('ignore')
    df = yf.download('^AEX', period='200d', auto_adjust=True, progress=False)
    close = df['Close'].dropna()
    if len(close) < 100:
        return True, None, None
    last  = float(close.iloc[-1])
    ma100 = float(close.rolling(100).mean().iloc[-1])
    return last >= ma100, round(last, 2), round(ma100, 2)


def load_eodhd_returns(code):
    """Daily returns for the trailing VOL_LOOKBACK sessions from EODHD parquet."""
    fpath = os.path.join(EODHD_DIR, f'{code}.parquet')
    try:
        p = pd.read_parquet(fpath)['adjusted_close']
        rets = p.pct_change().dropna().tail(VOL_LOOKBACK)
        if len(rets) >= 60:
            return rets
    except Exception:
        pass
    return None


def compute_invvol_weights(codes):
    """Inverse-volatility weights from EODHD history; missing data -> median vol fallback."""
    vols = {}
    for code in codes:
        rets = load_eodhd_returns(code)
        vols[code] = float(rets.std()) if rets is not None else None

    known = [v for v in vols.values() if v is not None]
    fallback = statistics.median(known) if known else 0.02
    for code in codes:
        if vols[code] is None or vols[code] <= 0:
            vols[code] = fallback
            print(f"    {code}: no EODHD history, using median vol fallback")

    inv = {code: 1.0 / v for code, v in vols.items()}
    total = sum(inv.values())
    return {code: round(w / total, 4) for code, w in inv.items()}


def get_som_price(code):
    """Start-of-month price from EODHD parquet (first trading day of current month)."""
    fpath = os.path.join(EODHD_DIR, f'{code}.parquet')
    try:
        p = pd.read_parquet(fpath)['adjusted_close']
        month_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
        som = p[p.index >= month_start]
        if len(som) > 0:
            return float(som.iloc[0]), som.index[0].strftime('%Y-%m-%d')
    except Exception:
        pass
    return None, None


def load_existing_portfolio():
    try:
        with open(PORTFOLIO_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def build_monthly_breakdown(existing, new_holdings, is_new_month, regime_str, cur_return_pct):
    breakdown = existing.get('monthly_breakdown', [])

    if is_new_month:
        cur_month_label = datetime.now().strftime('%b %Y')
        tickers = [h['ticker'] for h in new_holdings]

        for m in breakdown:
            if m.get('is_current') and m['month'] != cur_month_label:
                m['is_current'] = False

        existing_cur = next((m for m in breakdown if m['month'] == cur_month_label), None)
        if existing_cur:
            existing_cur['is_current'] = True
            existing_cur['regime']     = regime_str
            existing_cur['tickers']    = tickers
            existing_cur['return_pct'] = cur_return_pct
        else:
            breakdown.append({
                'month':      cur_month_label,
                'is_current': True,
                'start':      TODAY,
                'end':        None,
                'regime':     regime_str,
                'tickers':    tickers,
                'return_pct': cur_return_pct,
            })
    else:
        for m in breakdown:
            if m.get('is_current'):
                m['regime']     = regime_str
                m['tickers']    = [h['ticker'] for h in new_holdings]
                m['return_pct'] = cur_return_pct

    return breakdown[-37:]


def main():
    df = fetch_netherlands()

    regime_ok, idx_val, idx_ma100 = check_regime()
    regime_str = 'momentum' if regime_ok else 'defensive'
    pct_above  = round((idx_val / idx_ma100 - 1) * 100, 1) if idx_val and idx_ma100 else 0
    print(f"  Regime: {regime_str.upper()}  AEX: {idx_val}  MA100: {idx_ma100}  ({pct_above:+.1f}%)")

    top_df   = df.head(TOP_N) if regime_ok else df.iloc[0:0]
    selected = set(top_df['code'].tolist())

    top20 = []
    for i, row in df.head(20).iterrows():
        top20.append({
            'rank':      int(i) + 1,
            'ticker':    row['code'],
            'name':      row['description'],
            'ret_6m':    round(float(row['Perf.6M']), 1),
            'ret_12m':   round(float(row['Perf.Y']), 1),
            'composite': round(float(row['composite']), 1),
            'mcap_b':    round(float(row['market_cap_basic']) / 1e9, 2),
            'selected':  row['code'] in selected,
        })

    signal = {
        'date':           TODAY,
        'regime':         regime_str,
        'index_value':    idx_val,
        'index_ma100':    idx_ma100,
        'total_eligible': int(len(df)),
        'portfolio':      [s for s in top20 if s['selected']],
        'top20':          top20,
    }
    with open(DATA_PATH, 'w') as f:
        json.dump(signal, f, indent=2)
    print(f"  Saved: {DATA_PATH}")

    # ── Portfolio tracker ─────────────────────────────────────────────────────
    existing     = load_existing_portfolio()
    last_rebal_m = existing.get('last_rebalance', '')[:7]
    current_m    = datetime.now().strftime('%Y-%m')
    is_new_month = current_m != last_rebal_m

    price_map = {row['code']: float(row['close']) for _, row in df.iterrows() if row['close'] is not None}

    if is_new_month and regime_ok:
        print(f"  Portfolio: NEW MONTH ({current_m}), rebalancing to top {TOP_N}...")
        weights = compute_invvol_weights(top_df['code'].tolist())
        holdings = []
        last_rebalance = TODAY
        for _, row in top_df.iterrows():
            code = row['code']
            cp   = price_map.get(code)
            ep, edate = get_som_price(code)
            if ep is None:
                ep, edate = cp, TODAY
            ret = round((cp / ep - 1) * 100, 2) if ep and cp else None
            holdings.append({
                'ticker':        code,
                'name':          row['description'],
                'entry_date':    edate,
                'entry_price':   round(ep, 2) if ep else None,
                'current_price': round(cp, 2) if cp else None,
                'weight':        weights.get(code),
                'return_pct':    ret,
            })
            if edate:
                last_rebalance = edate

    elif not regime_ok:
        print("  Portfolio: DEFENSIVE — cash")
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
                h['current_price'] = round(cp, 2)
            if ep and h.get('current_price'):
                h['return_pct'] = round((h['current_price'] / ep - 1) * 100, 2)
            holdings.append(h)
        last_rebalance = existing.get('last_rebalance', TODAY)

    # Weighted current-month return (falls back to equal weight if unset)
    cur_return_pct = None
    priced = [h for h in holdings if h.get('return_pct') is not None]
    if priced:
        wsum = sum(h.get('weight') or (1.0 / len(priced)) for h in priced)
        cur_return_pct = round(
            sum(h['return_pct'] * (h.get('weight') or (1.0 / len(priced))) for h in priced) / wsum, 2
        ) if wsum else None

    breakdown = build_monthly_breakdown(existing, holdings, is_new_month, regime_str, cur_return_pct)
    months_2026 = [m for m in breakdown if '2026' in m.get('month', '') and not m.get('is_current')]
    if months_2026:
        ytd = 1.0
        for m in months_2026:
            if m.get('return_pct') is not None:
                ytd *= (1 + m['return_pct'] / 100)
        ytd_2026 = round((ytd - 1) * 100, 1)
    else:
        ytd_2026 = existing.get('ytd_2026', 0)

    portfolio = {
        'last_rebalance':    last_rebalance,
        'updated':           TODAY,
        'ytd_2026':          ytd_2026,
        'regime':            regime_str,
        'currency':          'EUR',
        'index_value':       idx_val,
        'index_ma100':       idx_ma100,
        'holdings':          holdings,
        'monthly_breakdown': breakdown,
    }
    with open(PORTFOLIO_PATH, 'w') as f:
        json.dump(portfolio, f, indent=2)
    print(f"  Saved: {PORTFOLIO_PATH}")

    print(f"\n{'='*80}")
    print(f"Netherlands Momentum — {TODAY} — {regime_str.upper()}")
    print(f"{'='*80}")
    print(f"{'#':>3} {'':>3} {'Ticker':<10} {'Name':<30} {'6M':>8} {'12M':>8} {'12-1':>8} {'MCap B EUR':>12}")
    print(f"{'-'*80}")
    for s in top20:
        mk = ">>>" if s['selected'] else ""
        print(f"{s['rank']:3d} {mk:>3} {s['ticker']:<10} {s['name'][:29]:<30} "
              f"{s['ret_6m']:>+7.1f}% {s['ret_12m']:>+7.1f}% {s['composite']:>+7.1f}% {s['mcap_b']:>10.2f}")
    print(f"\nTop {TOP_N} selected | {len(df)} eligible | Regime: {regime_str.upper()}")


if __name__ == '__main__':
    main()
