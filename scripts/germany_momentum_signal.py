#!/usr/bin/env python3
"""
Germany Momentum Signal Generator (v1, 2026-08-25)
- TradingView Screener for universe, market cap, 12M momentum, current
  prices -- no EODHD, no local-only data, runs unmodified on GitHub Actions
  (same pattern as canada_momentum_signal.py / netherlands_momentum_signal.py)
- Yahoo Finance for DAX regime (^GDAXI vs MA200)

Strategy (see ~/eodhd_data/germany_final_locked.py for the backtest this
config comes from -- CAGR +20.41%, Sharpe 0.945, MaxDD -28.19%, 2000-2026,
audited: two bugs found and fixed (US-ADR mistagging, weekend-calendar
contamination in the signal), plus an adversarial second audit that found
no lookahead/survivorship inflation but flagged real capacity/liquidity
constraints in the smaller names -- see the audit report for detail):
  - Universe: XETRA, primary listing only (`is_primary==True`,
    `exchange=='XETR'`) -- this alone excludes the ~226 US megacaps
    (Apple, Microsoft, Tesla, etc.) cross-listed on XETRA whose primary
    listing is NASDAQ/NYSE, without needing an ISIN-prefix lookup live
    (TradingView doesn't expose ISIN in this query; is_primary does the
    same job for the live signal).
  - Eligibility: market cap >= 30th percentile (top 70% by size)
  - No fundamental filter (backtest: EBIT/NetIncome/GrossProfit/ROE all
    reduce Sharpe at this N/mcap/MA combination)
  - Signal: pure 12-month return (TradingView Perf.Y), no skip-month
  - Portfolio: top 20 by momentum, equal weight
  - Regime: DAX (^GDAXI) vs its own 200-day MA -> 100% cash when below
  - Monthly rebalance, 1-trading-day execution lag (pending_signal
    mechanism, same convention as Canada/USA/UK)

Known liquidity caveat (from the adversarial audit): median EUR ADV of
held names ~EUR 0.43M/day; several names carry real spreads well above
the 40bps backtest assumption (measured via IBKR: median 22bps but up to
245bps on the thinnest names). Not a capacity strategy above roughly
EUR 1-2M; position-sizing and execution should account for this per name,
not assume uniform 40bps.

Saves: germany-momentum-data.json, germany-momentum-portfolio.json
"""
import os, json, warnings
from datetime import date, timedelta

import pandas as pd

warnings.filterwarnings('ignore')

from tradingview_screener import Query, col
import yfinance as yf

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
SITE_DIR       = os.path.dirname(SCRIPT_DIR)
DATA_PATH      = os.path.join(SITE_DIR, "germany-momentum-data.json")
PORTFOLIO_PATH = os.path.join(SITE_DIR, "germany-momentum-portfolio.json")

MCAP_PCT       = 0.30   # keep top 70% by market cap (percentile, not absolute floor)
TOP_N          = 20
MA_W           = 200
CONFIG_VERSION = "v1-2026-08-25"

MIN_UNIVERSE_ROWS = 250   # normal is ~400-420 primary-listed XETRA common stocks
                          # with perf+mcap+close present; post-mcap-filter ~280-300
TODAY = date.today().isoformat()


def fetch_germany():
    print("Fetching TradingView data (Germany XETRA)...")
    _, df = (Query()
        .select('name', 'description', 'market_cap_basic', 'Perf.Y', 'close', 'type', 'typespecs')
        .where(
            col('type') == 'stock',
            col('typespecs').has('common'),
            col('is_primary') == True,
            col('exchange') == 'XETR',
        )
        .set_markets('germany')
        .order_by('market_cap_basic', ascending=False)
        .limit(3000)
        .get_scanner_data()
    )
    print(f"  Raw rows: {len(df)}")

    df = df[df['ticker'].str.startswith('XETR:')].copy()
    df['code'] = df['ticker'].str.replace('XETR:', '', regex=False)

    # Genuine fallback for existing holdings that fall out of the ranking
    # universe (e.g. delisted, name change) -- minimal-requirement set,
    # same pattern as Canada's broad_prices fix.
    broad_prices = df.dropna(subset=['close']).set_index('code')['close'].astype(float).to_dict()

    df = df.dropna(subset=['Perf.Y', 'close', 'market_cap_basic']).copy()
    print(f"  With perf+mcap+close: {len(df)}")
    universe_health = len(df)

    mc_threshold = df['market_cap_basic'].quantile(MCAP_PCT)
    df = df[df['market_cap_basic'] >= mc_threshold].copy()
    print(f"  Above mcap P{int(MCAP_PCT*100)}: {len(df)}")

    return df.reset_index(drop=True), universe_health, broad_prices


def check_regime():
    """DAX vs MA200 via yfinance. Same refuse-to-publish-on-failure
    convention as Canada's check_regime()."""
    try:
        dax = yf.download('^GDAXI', period='400d', auto_adjust=True, progress=False)
        close = dax['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.dropna()
        if len(close) < MA_W:
            print(f"  check_regime(): only {len(close)} bars available, need >= {MA_W}")
            return None, None, None, None
        last = float(close.iloc[-1])
        ma200 = float(close.rolling(MA_W, min_periods=MA_W).mean().iloc[-1])
        if not (last == last) or not (ma200 == ma200):
            print("  check_regime(): NaN in last close or MA -- refusing to determine regime")
            return None, None, None, None
        market_date = close.index[-1].date()
        return last >= ma200, round(last, 1), round(ma200, 1), market_date
    except Exception as e:
        print(f"  check_regime() failed: {e}")
        return None, None, None, None


def next_weekday(d):
    nd = d + timedelta(days=1)
    while nd.weekday() >= 5:
        nd += timedelta(days=1)
    return nd


def load_existing_portfolio():
    try:
        with open(PORTFOLIO_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def build_monthly_breakdown(existing, new_holdings, is_new_month, regime_str):
    breakdown = existing.get('monthly_breakdown', [])

    if is_new_month:
        cur_month_label = date.fromisoformat(TODAY).strftime('%b %Y')
        tickers = [h['ticker'] for h in new_holdings]
        weights = {h['ticker']: h['weight'] for h in new_holdings}

        for m in breakdown:
            if m.get('is_current') and m['month'] != cur_month_label:
                m['is_current'] = False

        existing_cur = next((m for m in breakdown if m['month'] == cur_month_label), None)
        if existing_cur:
            existing_cur['is_current']     = True
            existing_cur['regime']         = regime_str
            existing_cur['tickers']        = tickers
            existing_cur['weights']        = weights
            existing_cur['return_pct']     = None
            existing_cur['start']          = TODAY
            existing_cur['config_version'] = CONFIG_VERSION
        else:
            breakdown.append({
                'month':          cur_month_label,
                'is_current':     True,
                'start':          TODAY,
                'end':            None,
                'regime':         regime_str,
                'tickers':        tickers,
                'weights':        weights,
                'return_pct':     None,
                'config_version': CONFIG_VERSION,
            })
    else:
        for m in breakdown:
            if m.get('is_current'):
                m['regime']  = regime_str
                m['tickers'] = [h['ticker'] for h in new_holdings]
                m['weights'] = {h['ticker']: h['weight'] for h in new_holdings}
                m.setdefault('config_version', CONFIG_VERSION)

    return breakdown[-37:]


def write_not_live(reason):
    print(f"  *** NOT LIVE: {reason} -- leaving holdings/pending_signal untouched ***")
    try:
        with open(DATA_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data['is_live'] = False
    data['not_live_reason'] = reason
    data['not_live_since'] = TODAY
    with open(DATA_PATH, 'w') as f:
        json.dump(data, f, indent=2)

    portfolio = load_existing_portfolio()
    portfolio['is_live'] = False
    portfolio['not_live_reason'] = reason
    portfolio['not_live_since'] = TODAY
    with open(PORTFOLIO_PATH, 'w') as f:
        json.dump(portfolio, f, indent=2)


def main():
    global TODAY
    regime_ok, dax_val, dax_ma200, market_date = check_regime()
    if market_date is None:
        write_not_live("check_regime() could not determine DAX/MA200 regime "
                        "(yfinance outage or insufficient history) -- refusing to publish")
        return
    TODAY = market_date.isoformat()
    regime_str = 'momentum' if regime_ok else 'defensive'
    pct_above  = round((dax_val / dax_ma200 - 1) * 100, 1)
    print(f"  Regime: {regime_str.upper()}  DAX: {dax_val}  MA200: {dax_ma200}  ({pct_above:+.1f}%)  "
          f"[market date: {TODAY}]")

    df, universe_health, broad_prices = fetch_germany()
    if universe_health < MIN_UNIVERSE_ROWS:
        write_not_live(f"TradingView universe fetch returned only {universe_health} tickers "
                        f"(expected {MIN_UNIVERSE_ROWS}+) -- likely an API issue")
        return

    df = df.sort_values('Perf.Y', ascending=False).reset_index(drop=True)
    top_df = df.head(TOP_N) if regime_ok else df.iloc[0:0]

    if len(top_df):
        w = 1.0 / len(top_df)
        weight_map = {code: round(w, 4) for code in top_df['code']}
    else:
        weight_map = {}
    selected = set(top_df['code'].tolist())

    top30 = []
    for i, row in df.head(30).iterrows():
        code = row['code']
        top30.append({
            'rank':      int(i) + 1,
            'ticker':    code,
            'name':      str(row.get('description') or row.get('name', code)),
            'ret_12m':   round(float(row['Perf.Y']), 2),
            'mcap_b':    round(float(row['market_cap_basic']) / 1e9, 3),
            'weight':    weight_map.get(code),
            'selected':  code in selected,
        })

    signal = {
        'date':               TODAY,
        'regime':             regime_str,
        'dax':                dax_val,
        'dax_ma200':          dax_ma200,
        'pct_above_ma':       pct_above,
        'total_eligible':     int(len(df)),
        'portfolio':          [s for s in top30 if s['selected']],
        'top30':              top30,
        'updated':            TODAY,
        'is_live':            True,
        'not_live_reason':    None,
    }
    with open(DATA_PATH, 'w') as f:
        json.dump(signal, f, indent=2)
    print(f"  Saved: {DATA_PATH}")

    existing        = load_existing_portfolio()
    last_rebal_m    = existing.get('last_rebalance', '')[:7]
    current_m       = TODAY[:7]
    pending_signal  = existing.get('pending_signal')
    legacy_strategy = existing.get('config_version') != CONFIG_VERSION
    is_new_month    = current_m != last_rebal_m or legacy_strategy
    if legacy_strategy and existing:
        print(f"  Existing holdings predate config_version={CONFIG_VERSION!r} "
              f"-- forcing an immediate rebalance to the current strategy.")

    price_map = {row['code']: float(row['close']) for _, row in df.iterrows()}
    price_map_full = broad_prices

    today_sel = [{'ticker': row['code'], 'name': str(row.get('description') or row.get('name', row['code'])),
                  'weight': float(weight_map.get(row['code'], 0))} for _, row in top_df.iterrows()]

    if is_new_month:
        if regime_ok:
            if pending_signal and pending_signal.get('for_month') == current_m and not legacy_strategy:
                print(f"  Portfolio: NEW MONTH ({current_m}), executing signal locked in on "
                      f"{pending_signal.get('computed_date')}...")
                exec_picks = pending_signal['picks']
            else:
                print(f"  Portfolio: NEW MONTH ({current_m}), no matching locked signal "
                      f"-- falling back to today's data...")
                exec_picks = today_sel
        else:
            print(f"  Portfolio: NEW MONTH ({current_m}), regime DEFENSIVE — moving to cash...")
            exec_picks = []

        holdings = []
        for p in exec_picks:
            code = p['ticker']
            cp   = price_map.get(code) or price_map_full.get(code)
            holdings.append({
                'ticker':        code,
                'name':          p.get('name', code),
                'entry_date':    TODAY,
                'entry_price':   round(cp, 4) if cp else None,
                'current_price': round(cp, 4) if cp else None,
                'weight':        float(p.get('weight', 0)),
                'return_pct':    0.0,
            })
        last_rebalance = TODAY
    else:
        print(f"  Portfolio: same month ({current_m}), updating prices...")
        holdings = []
        for h in existing.get('holdings', []):
            h = h.copy()
            cp = price_map_full.get(h['ticker'])
            if cp is None:
                print(f"  WARNING: no price found for held ticker {h['ticker']!r} -- "
                      f"current_price/return_pct frozen at last known value.")
            ep = h.get('entry_price')
            if cp:
                h['current_price'] = round(cp, 4)
            if ep and h.get('current_price'):
                h['return_pct'] = round((h['current_price'] / ep - 1) * 100, 2)
            holdings.append(h)
        last_rebalance = existing.get('last_rebalance', TODAY)

    breakdown = build_monthly_breakdown(existing, holdings, is_new_month, regime_str)

    months_this_year = [m for m in breakdown if str(date.fromisoformat(TODAY).year) in m.get('month', '')
                         and not m.get('is_current')
                         and m.get('config_version') == CONFIG_VERSION]
    if months_this_year:
        ytd = 1.0
        for m in months_this_year:
            if m.get('return_pct') is not None:
                ytd *= (1 + m['return_pct'] / 100)
        ytd_pct = round((ytd - 1) * 100, 2)
    else:
        ytd_pct = None

    today_date = date.fromisoformat(TODAY)
    next_trading_candidate = next_weekday(today_date)
    is_month_end_today = (next_trading_candidate.month != today_date.month
                           or next_trading_candidate.year != today_date.year)

    if is_month_end_today and regime_ok:
        next_month_str = next_trading_candidate.strftime('%Y-%m')
        new_pending_signal = {
            'for_month':     next_month_str,
            'computed_date': TODAY,
            'picks':         today_sel,
        }
        print(f"  Today ({TODAY}) is the last trading day of the month -- "
              f"locked in signal for {next_month_str}: {[p['ticker'] for p in today_sel]}")
    elif is_new_month:
        new_pending_signal = None
    else:
        new_pending_signal = pending_signal

    portfolio = {
        'last_rebalance':    last_rebalance,
        'updated':           TODAY,
        'ytd_2026':          ytd_pct,
        'regime':            regime_str,
        'currency':          'EUR',
        'dax':               dax_val,
        'dax_ma200':         dax_ma200,
        'holdings':          holdings,
        'monthly_breakdown': breakdown,
        'pending_signal':    new_pending_signal,
        'config_version':    CONFIG_VERSION,
        'is_live':           True,
        'not_live_reason':   None,
    }
    with open(PORTFOLIO_PATH, 'w') as f:
        json.dump(portfolio, f, indent=2)
    print(f"  Saved: {PORTFOLIO_PATH}")

    print(f"\n{'='*80}")
    print(f"Germany Momentum — {TODAY} — {regime_str.upper()}")
    print(f"{'='*80}")
    print(f"{'#':>3} {'':>3} {'Ticker':<8} {'Name':<32} {'12M':>8} {'Wt':>6} {'MCap B EUR':>12}")
    print(f"{'-'*80}")
    for s in top30:
        mk = ">>>" if s['selected'] else ""
        wt = f"{s['weight']*100:.1f}%" if s['weight'] else ""
        print(f"{s['rank']:3d} {mk:>3} {s['ticker']:<8} {s['name'][:31]:<32} "
              f"{s['ret_12m']:>+7.1f}% {wt:>6} {s['mcap_b']:>10.3f}")
    print(f"\nTop {TOP_N} selected | {len(df)} eligible | Regime: {regime_str.upper()}")


if __name__ == '__main__':
    main()
