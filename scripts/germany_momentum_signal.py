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
  - Universe: all XETRA common-stock lines EXCEPT US-domiciled companies
    (`exchange=='XETR'`, `country != 'United States'`). v1 used
    `is_primary==True`, which excluded the US megacaps but ALSO threw out
    every non-US foreign cross-listing (Vestas, Nokia, ASML, ~250 names)
    that the backtest deliberately keeps -- the explicit design intent is
    to exclude ONLY the Americans (to avoid raising USA correlation), not
    all foreigners. TradingView's `country` (domicile) matches the
    backtest's ISIN-prefix exclusion closely enough, and the resulting
    universe (~690 names with data) now matches the backtest's EODHD
    cross-section (~610) instead of v1's ~410, so the mcap percentile is
    computed over the same population.
  - Eligibility: market cap >= 30th percentile (top 70% by size)
  - No fundamental filter (backtest: EBIT/NetIncome/GrossProfit/ROE all
    reduce Sharpe at this N/mcap/MA combination)
  - Signal: pure 12-month return, no skip-month -- computed from yfinance
    (.DE lines, auto_adjust=True so it is dividend-adjusted like the
    backtest's adjusted_close momentum), NOT TradingView Perf.Y. Perf.Y
    proved unusable on non-primary XETR cross-listing lines: dormant or
    recently-activated lines (46-233 days of real history) reported
    fictitious +300..+1100% "12M returns" (Trane, Chubb, Danske, KBC...)
    and would have filled the entire top-20. The backtest convention --
    a line must have a real price ~12 months ago or it is ineligible --
    is enforced here explicitly (>=230 daily closes AND a non-stale
    price at the 365d anchor).
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
CONFIG_VERSION = "v2-2026-08-25"   # v2: universe = all non-US XETR lines (was primary-only)

MIN_UNIVERSE_ROWS = 400   # normal is ~690 non-US XETR common-stock lines with
                          # mcap+close present; post-mcap-filter ~480
MIN_MOMENTUM_ROWS = 250   # of those, how many must yield a valid 12M momentum
                          # (>=230d of real quotes) before we trust the ranking
TODAY = date.today().isoformat()


def fetch_germany():
    print("Fetching TradingView data (Germany XETRA)...")
    _, df = (Query()
        .select('name', 'description', 'market_cap_basic', 'close', 'type', 'typespecs', 'country')
        .where(
            col('type') == 'stock',
            col('typespecs').has('common'),
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
    # same pattern as Canada's broad_prices fix. Built BEFORE the country
    # filter so even a US-line holding from an older config stays priced.
    broad_prices = df.dropna(subset=['close']).set_index('code')['close'].astype(float).to_dict()

    df = df[df['country'] != 'United States'].copy()
    print(f"  Non-US: {len(df)}")

    df = df.dropna(subset=['close', 'market_cap_basic']).copy()
    print(f"  With mcap+close: {len(df)}")
    universe_health = len(df)

    mc_threshold = df['market_cap_basic'].quantile(MCAP_PCT)
    df = df[df['market_cap_basic'] >= mc_threshold].copy()
    print(f"  Above mcap P{int(MCAP_PCT*100)}: {len(df)}")

    return df.reset_index(drop=True), universe_health, broad_prices


def compute_momentum(codes):
    """12M total-return momentum from yfinance .DE lines (auto_adjust=True,
    dividend-adjusted -- same convention as the backtest's adjusted_close).

    Backtest eligibility rule enforced explicitly: a line must have a real
    price ~12 months ago, or it has no momentum and is ineligible. This is
    what protects the backtest from dormant/recently-activated XETR
    cross-listing lines, and what TradingView's Perf.Y does NOT do (it
    reported +300..+1100% fictitious returns on lines with 46-233 days of
    history -- the v2 incident of 2026-08-25).
    """
    yf_map = {c: c + '.DE' for c in codes}
    tickers = list(yf_map.values())
    frames = []
    for i in range(0, len(tickers), 150):
        chunk = tickers[i:i + 150]
        print(f"  yfinance momentum batch {i//150 + 1}/{(len(tickers)-1)//150 + 1} "
              f"({len(chunk)} tickers)...")
        raw = yf.download(chunk, period='500d', auto_adjust=True, progress=False)
        if raw is None or len(raw) == 0:
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            px = raw['Close']
        else:
            px = raw[['Close']].rename(columns={'Close': chunk[0]})
        frames.append(px)
    if not frames:
        return {}
    px = pd.concat(frames, axis=1)
    px = px.loc[:, ~px.columns.duplicated()]
    last_date = px.index.max()
    anchor = last_date - pd.Timedelta(days=365)

    mom = {}
    for c, yt in yf_map.items():
        if yt not in px.columns:
            continue
        s = px[yt].dropna()
        if len(s) < 230:                       # needs ~a full year of real quotes
            continue
        past = s[s.index <= anchor]
        if past.empty or (anchor - past.index[-1]).days > 10:   # stale anchor
            continue
        mom[c] = round(float(s.iloc[-1] / past.iloc[-1] - 1) * 100, 2)
    return mom


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
                # close the month at the new book's start date -- without this,
                # the ytd script has no end bound and would keep extending the
                # closed month's return window to "today" forever
                if not m.get('end'):
                    m['end'] = TODAY

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

    mom = compute_momentum(df['code'].tolist())
    df['ret_12m'] = df['code'].map(mom)
    df = df.dropna(subset=['ret_12m']).copy()
    print(f"  With valid 12M momentum (>=230d history, non-stale anchor): {len(df)}")
    if len(df) < MIN_MOMENTUM_ROWS:
        write_not_live(f"Only {len(df)} tickers with valid 12M momentum "
                        f"(expected {MIN_MOMENTUM_ROWS}+) -- likely a yfinance outage")
        return

    df = df.sort_values('ret_12m', ascending=False).reset_index(drop=True)
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
            'ret_12m':   round(float(row['ret_12m']), 2),
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
        # Backtest convention: the regime is evaluated at the month-end SIGNAL
        # close and held for the month -- not re-evaluated on the execution
        # day. A locked pending_signal therefore carries its own regime
        # decision and wins over today's regime read; today's regime is only
        # a fallback when no signal was locked (first run, outage at EOM).
        if pending_signal and pending_signal.get('for_month') == current_m and not legacy_strategy:
            locked_regime_ok = pending_signal.get('regime', 'momentum') == 'momentum'
            if locked_regime_ok:
                print(f"  Portfolio: NEW MONTH ({current_m}), executing signal locked in on "
                      f"{pending_signal.get('computed_date')}...")
                exec_picks = pending_signal['picks']
            else:
                print(f"  Portfolio: NEW MONTH ({current_m}), locked signal was DEFENSIVE "
                      f"-- moving to cash...")
                exec_picks = []
        elif regime_ok:
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

    if is_month_end_today:
        # Lock the signal EVEN when defensive: the regime decision belongs to
        # the signal date (backtest convention), so a defensive close must be
        # carried into next month as "cash" rather than letting the execution
        # day's regime re-read decide (which the backtest never does).
        next_month_str = next_trading_candidate.strftime('%Y-%m')
        new_pending_signal = {
            'for_month':     next_month_str,
            'computed_date': TODAY,
            'regime':        regime_str,
            'picks':         today_sel if regime_ok else [],
        }
        print(f"  Today ({TODAY}) is the last trading day of the month -- "
              f"locked in {regime_str.upper()} signal for {next_month_str}: "
              f"{[p['ticker'] for p in today_sel] if regime_ok else 'CASH'}")
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
