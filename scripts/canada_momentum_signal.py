#!/usr/bin/env python3
"""
Canada Momentum Signal Generator (v2 — validated strategy, 2026-08-11)
- TradingView Screener for universe, market cap, 12M momentum, current prices
- tvDatafeed for 252-day daily bars per stock (vol-exclusion filter + inverse-vol
  weights) -- no EODHD, no local-only data, runs unmodified on GitHub Actions
  (same pattern as netherlands_momentum_signal.py)
- Yahoo Finance for TSX regime (^GSPTSE vs MA75)

Strategy (see research/canada_momentum_report.html, verified 2026-08-11):
  - Universe: TSX (.TO), all CAD-denominated stocks
  - Excludes CDRs (TradingView type=='dr') and funds/ETFs (type=='fund')
  - Excludes preferred shares (ticker matches BASE.PR.x / BASE.PF.x)
  - Eligibility: market cap >= 30th percentile (top 70% by size, not an
    absolute floor). No ADV/liquidity filter (tested, dropped -- negligible).
  - Excludes the most volatile 25% of the eligible universe (252-day realized
    vol, annualized)
  - Signal: pure 12-month return (TradingView Perf.Y), no skip-month
  - Portfolio: top 15 by momentum
  - Weighting: inverse-volatility (252-day realized vol, same series as the
    vol-exclusion filter)
  - Regime: TSX Composite (^GSPTSE) vs its own 75-day MA -> 100% cash when below
  - Monthly rebalance

Saves: canada-momentum-data.json, canada-momentum-portfolio.json
"""
import os, json, re, time, warnings
from datetime import datetime, date

import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

from tradingview_screener import Query, col
from tvDatafeed import TvDatafeed, Interval
import yfinance as yf

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
SITE_DIR       = os.path.dirname(SCRIPT_DIR)
DATA_PATH      = os.path.join(SITE_DIR, "canada-momentum-data.json")
PORTFOLIO_PATH = os.path.join(SITE_DIR, "canada-momentum-portfolio.json")

MCAP_PCT     = 0.30    # keep top 70% by market cap (percentile, not absolute floor)
VOL_EXCL_PCT = 0.25    # exclude the 25% most volatile stocks before ranking
TOP_N        = 15
MA_W         = 75
VOL_LOOKBACK = 252
TODAY        = date.today().isoformat()

# TSX preferred-share ticker convention: BASE.PR.<letter> or BASE.PF.<letter>
PREF_PATTERN = re.compile(r'^[A-Z0-9]+\.P[RF]\.')


# ── tvDatafeed: sequential, single client. Parallel connections get 429'd by
# TradingView's unauthenticated websocket endpoint (tested 2026-08-11: 8
# concurrent workers -> immediate rate limit; sequential @ ~0.5s/ticker is
# reliable and fast enough -- ~600-700 tickers takes ~6 minutes). ────────────
_tv_client = None
def tv_client():
    global _tv_client
    if _tv_client is None:
        _tv_client = TvDatafeed()
    return _tv_client


def fetch_bars(code, n_bars=VOL_LOOKBACK + 40, retries=1):
    for attempt in range(retries + 1):
        try:
            bars = tv_client().get_hist(symbol=code, exchange='TSX',
                                         interval=Interval.in_daily, n_bars=n_bars)
            if bars is not None and len(bars) >= 60:
                return bars['close']
            return None
        except Exception as e:
            if attempt < retries:
                time.sleep(1.0)
                continue
            print(f"    {code}: tvDatafeed fetch failed ({e})")
            return None
    return None


def compute_vols(codes):
    """252-day annualized realized vol per ticker, sequential tvDatafeed fetch."""
    print(f"  Fetching {len(codes)} tickers' price history via tvDatafeed (sequential)...")
    vols = {}
    t0 = time.time()
    for i, code in enumerate(codes):
        closes = fetch_bars(code)
        if closes is not None:
            rets = closes.pct_change().dropna().tail(VOL_LOOKBACK)
            if len(rets) >= 60:
                vols[code] = float(rets.std()) * np.sqrt(252)
        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            print(f"    {i+1}/{len(codes)} ({elapsed:.0f}s elapsed, {len(vols)} ok)")
    elapsed = time.time() - t0
    print(f"  Done: {len(vols)}/{len(codes)} tickers with valid vol data ({elapsed:.0f}s)")
    return vols


def fetch_canada():
    print("Fetching TradingView data (Canada TSX)...")
    _, df = (Query()
        .select('name', 'description', 'market_cap_basic', 'Perf.Y', 'close', 'currency', 'type')
        .where(col('currency') == 'CAD')
        .set_markets('canada')
        .order_by('market_cap_basic', ascending=False)
        .limit(3000)
        .get_scanner_data()
    )
    print(f"  Raw rows: {len(df)}")

    df = df[df['ticker'].str.startswith('TSX:')].copy()
    df['code'] = df['ticker'].str.replace('TSX:', '', regex=False)
    df = df.dropna(subset=['Perf.Y', 'close', 'market_cap_basic']).copy()
    print(f"  With perf+mcap+close: {len(df)}")

    # Exclude CDRs (foreign mega-caps cross-listed on TSX) and funds/ETFs
    df = df[~df['type'].isin(['dr', 'fund'])].copy()
    print(f"  After CDR/fund exclusion: {len(df)}")

    # Exclude preferred shares (ticker pattern BASE.PR.x / BASE.PF.x)
    df = df[~df['code'].str.match(PREF_PATTERN)].copy()
    print(f"  After preferred-share exclusion: {len(df)}")

    # Market cap filter: percentile, not absolute floor -- keep top 70% by size
    mc_threshold = df['market_cap_basic'].quantile(MCAP_PCT)
    df = df[df['market_cap_basic'] >= mc_threshold].copy()
    print(f"  Above mcap P{int(MCAP_PCT*100)}: {len(df)}")

    return df.reset_index(drop=True)


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


def load_existing_portfolio():
    try:
        with open(PORTFOLIO_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def build_monthly_breakdown(existing, new_holdings, is_new_month, regime_str):
    breakdown = existing.get('monthly_breakdown', [])

    if is_new_month:
        cur_month_label = datetime.now().strftime('%b %Y')
        tickers = [h['ticker'] for h in new_holdings]
        weights = {h['ticker']: h['weight'] for h in new_holdings}

        for m in breakdown:
            if m.get('is_current') and m['month'] != cur_month_label:
                m['is_current'] = False

        existing_cur = next((m for m in breakdown if m['month'] == cur_month_label), None)
        if existing_cur:
            existing_cur['is_current'] = True
            existing_cur['regime']     = regime_str
            existing_cur['tickers']    = tickers
            existing_cur['weights']    = weights
            existing_cur['return_pct'] = None
        else:
            breakdown.append({
                'month':      cur_month_label,
                'is_current': True,
                'start':      TODAY,
                'end':        None,
                'regime':     regime_str,
                'tickers':    tickers,
                'weights':    weights,
                'return_pct': None,
            })
    else:
        for m in breakdown:
            if m.get('is_current'):
                m['regime']  = regime_str
                m['tickers'] = [h['ticker'] for h in new_holdings]
                m['weights'] = {h['ticker']: h['weight'] for h in new_holdings}

    return breakdown[-37:]


def main():
    universe = fetch_canada()

    # ── Vol-exclusion filter + InvVol weighting both need 252d realized vol
    # for the WHOLE eligible universe (the vol-exclusion percentile threshold
    # must be computed over the full population, not just top-momentum names).
    vols = compute_vols(universe['code'].tolist())
    universe['vol'] = universe['code'].map(vols)
    with_vol = universe.dropna(subset=['vol']).copy()
    print(f"  With valid vol data: {len(with_vol)}")

    vol_threshold = with_vol['vol'].quantile(1 - VOL_EXCL_PCT)
    df = with_vol[with_vol['vol'] <= vol_threshold].copy()
    print(f"  After excluding top {int(VOL_EXCL_PCT*100)}% most volatile: {len(df)}")

    df = df.sort_values('Perf.Y', ascending=False).reset_index(drop=True)

    regime_ok, tsx_val, tsx_ma75 = check_regime()
    regime_str = 'momentum' if regime_ok else 'defensive'
    pct_above  = round((tsx_val / tsx_ma75 - 1) * 100, 1)
    print(f"  Regime: {regime_str.upper()}  TSX: {tsx_val}  MA75: {tsx_ma75}  ({pct_above:+.1f}%)")

    top_df = df.head(TOP_N) if regime_ok else df.iloc[0:0]

    # Inverse-volatility weights for the selected top N
    if len(top_df):
        inv_v = 1.0 / top_df['vol'].clip(lower=0.01)
        w = inv_v / inv_v.sum()
        weight_map = dict(zip(top_df['code'], w.round(4)))
    else:
        weight_map = {}
    selected = set(top_df['code'].tolist())

    top20 = []
    for i, row in df.head(20).iterrows():
        code = row['code']
        top20.append({
            'rank':      int(i) + 1,
            'ticker':    code,
            'name':      str(row.get('name', code)),
            'ret_12m':   round(float(row['Perf.Y']), 2),
            'vol_ann':   round(float(row['vol']) * 100, 1),
            'mcap_b':    round(float(row['market_cap_basic']) / 1e9, 3),
            'weight':    weight_map.get(code),
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
    last_rebal_m = existing.get('last_rebalance', '')[:7]
    current_m    = datetime.now().strftime('%Y-%m')
    legacy_strategy = bool(existing.get('holdings')) and any('weight' not in h for h in existing['holdings'])
    is_new_month = current_m != last_rebal_m or legacy_strategy
    if legacy_strategy:
        print("  Existing holdings are from the pre-2026-08-11 strategy (N=10, equal-weight) "
              "-- forcing an immediate rebalance to the new N=15 InvVol strategy.")

    price_map = {row['code']: float(row['close']) for _, row in df.iterrows()}
    # fall back to the full (pre-vol-filter) universe for price lookups on
    # existing holdings that may have since failed the vol filter
    price_map_full = {row['code']: float(row['close']) for _, row in universe.iterrows()}

    if is_new_month and regime_ok:
        print(f"  Portfolio: NEW MONTH ({current_m}), rebalancing to top {TOP_N}...")

        holdings = []
        for _, row in top_df.iterrows():
            code = row['code']
            cp   = price_map.get(code)
            ep, edate = cp, TODAY
            holdings.append({
                'ticker':        code,
                'name':          str(row.get('name', code)),
                'entry_date':    edate,
                'entry_price':   round(ep, 4) if ep else None,
                'current_price': round(cp, 4) if cp else None,
                'weight':        float(weight_map.get(code, 0)),
                'return_pct':    0.0,
            })
        last_rebalance = TODAY

    elif not regime_ok:
        print(f"  Portfolio: DEFENSIVE — cash")
        holdings = []
        last_rebalance = existing.get('last_rebalance', TODAY)

    else:
        print(f"  Portfolio: same month ({current_m}), updating prices...")
        holdings = []
        for h in existing.get('holdings', []):
            h = h.copy()
            cp = price_map_full.get(h['ticker'])
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
    print(f"{'#':>3} {'':>3} {'Ticker':<10} {'Name':<28} {'12M':>8} {'Vol':>7} {'Wt':>6} {'MCap B CAD':>12}")
    print(f"{'-'*80}")
    for s in top20:
        mk = ">>>" if s['selected'] else ""
        wt = f"{s['weight']*100:.1f}%" if s['weight'] else ""
        print(f"{s['rank']:3d} {mk:>3} {s['ticker']:<10} {s['name'][:27]:<28} "
              f"{s['ret_12m']:>+7.1f}% {s['vol_ann']:>6.1f}% {wt:>6} {s['mcap_b']:>10.3f}")
    print(f"\nTop {TOP_N} selected | {len(df)} eligible (post vol-filter) | Regime: {regime_str.upper()}")


if __name__ == '__main__':
    main()
