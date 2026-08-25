#!/usr/bin/env python3
"""
Canada Momentum Signal Generator (v3 — re-audited strategy, 2026-08-21)
- TradingView Screener for universe, market cap, 12M momentum, net income,
  current prices -- no EODHD, no local-only data, runs unmodified on GitHub
  Actions (same pattern as netherlands_momentum_signal.py)
- Yahoo Finance for TSX regime (^GSPTSE vs MA75)

Strategy (see ~/eodhd_data/canada_momentum_final.py for the backtest this
config comes from -- STILL UNDER TEST as of 2026-08-21, not yet independently
re-verified against this exact TradingView-fed universe. Superseded the
2026-08-11 config after a two-pass external audit found the original
backtest assumed impossible zero-lag execution and ran on a contaminated
trading calendar that was forcing ~42% of months to a false 0% return --
see the module docstring history in canada_momentum_final.py for the full
bug list):
  - Universe: TSX (.TO), all CAD-denominated stocks
  - Excludes CDRs (TradingView type=='dr') and funds/ETFs (type=='fund')
  - Excludes preferred shares (ticker matches BASE.PR.x / BASE.PF.x)
  - Eligibility: market cap >= 20th percentile (top 80% by size, not an
    absolute floor). No ADV/liquidity filter (tested, dropped -- negligible).
  - Fundamental filter: NetIncome(TTM) > 0 (TradingView `net_income_ttm`).
    Switched from no fundamental filter on 2026-08-21 -- backtest sweep
    found NetIncome>0 dominates every other filter tested (EBIT>0,
    GrossProfit>0, FCF>0, ROE>0) on CAGR, Sharpe, and MaxDD simultaneously.
  - Volatility-exclusion filter REMOVED on 2026-08-21 -- backtest sweeps
    showed jagged, non-monotonic Sharpe/MaxDD across nearby vol-exclusion
    thresholds, a sign of fitting noise rather than a real effect. This also
    removes the tvDatafeed dependency entirely (was only used for the
    252-day vol calc) -- one less data source, one less way for the script
    to fail.
  - Signal: pure 12-month return (TradingView Perf.Y), no skip-month
  - Portfolio: top 10 by momentum (was top 15)
  - Weighting: equal weight (1/10 per position).
  - Regime: TSX Composite (^GSPTSE) vs its own 75-day MA -> 100% cash when below
  - Monthly rebalance, 1-trading-day execution lag (pending_signal mechanism,
    unchanged -- this was already correct)

Saves: canada-momentum-data.json, canada-momentum-portfolio.json
"""
import os, json, re, warnings
from datetime import datetime, date, timedelta

import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

from tradingview_screener import Query, col
import yfinance as yf

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
SITE_DIR       = os.path.dirname(SCRIPT_DIR)
DATA_PATH      = os.path.join(SITE_DIR, "canada-momentum-data.json")
PORTFOLIO_PATH = os.path.join(SITE_DIR, "canada-momentum-portfolio.json")

MCAP_PCT     = 0.20    # keep top 80% by market cap (percentile, not absolute floor)
TOP_N        = 10
MA_W         = 75
CONFIG_VERSION = "v3-netincome-2026-08-21"  # bump this + legacy_strategy fires an immediate migration rebalance

# Data-quality kill switch: if the TradingView universe fetch looks broken,
# treat today's run as untrustworthy -- don't rebalance, don't touch
# existing holdings, mark the signal not-live so the site shows a warning
# instead of silently trading on bad data.
MIN_UNIVERSE_ROWS = 500   # normal is ~950-990; measured right after the required-field
                          # dropna (perf/mcap/close/netincome present), BEFORE CDR/fund/
                          # preferred exclusion and the mcap-percentile/NetIncome filters
                          # (those bring the final ranking universe down to ~300-350)
TODAY        = date.today().isoformat()

# TSX preferred-share ticker convention: BASE.PR.<letter> or BASE.PF.<letter>
PREF_PATTERN = re.compile(r'^[A-Z0-9]+\.P[RF]\.')


def fetch_canada():
    print("Fetching TradingView data (Canada TSX)...")
    _, df = (Query()
        .select('name', 'description', 'market_cap_basic', 'Perf.Y', 'net_income_ttm',
                'close', 'currency', 'type')
        .where(col('currency') == 'CAD')
        .set_markets('canada')
        .order_by('market_cap_basic', ascending=False)
        .limit(3000)
        .get_scanner_data()
    )
    print(f"  Raw rows: {len(df)}")

    df = df[df['ticker'].str.startswith('TSX:')].copy()
    df['code'] = df['ticker'].str.replace('TSX:', '', regex=False)

    # BUG FIXED 2026-08-21: a genuine price fallback for existing holdings
    # that have since fallen out of the ranking universe (delisted, name
    # change, or -- with NetIncome>0 as a live filter -- simply turned
    # unprofitable while still held, the normal path for a momentum name)
    # needs a MINIMAL-requirement universe, not the fully-filtered one.
    # A prior version of this function set `universe = df` (the same,
    # already mcap+NetIncome-filtered object) as its own "fallback" -- that
    # wasn't a fallback at all, price_map_full was identical to price_map,
    # so a dropped holding's current_price silently froze with no warning.
    # broad_prices only requires a valid close, nothing else.
    broad_prices = df.dropna(subset=['close']).set_index('code')['close'].astype(float).to_dict()

    df = df.dropna(subset=['Perf.Y', 'close', 'market_cap_basic', 'net_income_ttm']).copy()
    print(f"  With perf+mcap+close+netincome: {len(df)}")
    # universe_health is measured HERE -- right after the required-field
    # dropna, BEFORE CDR/fund/preferred exclusion and BEFORE the mcap
    # percentile and NetIncome filters below. A stale comment on
    # MIN_UNIVERSE_ROWS previously implied this was the POST-filter count
    # (~950-990) -- it isn't; the post-filter count is ~300-350. Fixed.
    universe_health = len(df)

    # Exclude CDRs (foreign mega-caps cross-listed on TSX) and funds/ETFs
    df = df[~df['type'].isin(['dr', 'fund'])].copy()
    print(f"  After CDR/fund exclusion: {len(df)}")

    # Exclude preferred shares (ticker pattern BASE.PR.x / BASE.PF.x)
    df = df[~df['code'].str.match(PREF_PATTERN)].copy()
    print(f"  After preferred-share exclusion: {len(df)}")

    # Market cap filter: percentile, not absolute floor -- keep top 80% by
    # size. Threshold computed on the FULL universe BEFORE the NetIncome
    # filter below, so the two criteria stay independent (a coupling bug --
    # computing the percentile only among already-profitable names -- was
    # found and fixed in the backtest on 2026-08-20; same principle applied
    # here from the start).
    mc_threshold = df['market_cap_basic'].quantile(MCAP_PCT)
    df = df[df['market_cap_basic'] >= mc_threshold].copy()
    print(f"  Above mcap P{int(MCAP_PCT*100)}: {len(df)}")

    # Fundamental filter: NetIncome(TTM) > 0
    df = df[df['net_income_ttm'] > 0].copy()
    print(f"  After NetIncome(TTM)>0 filter: {len(df)}")

    return df.reset_index(drop=True), universe_health, broad_prices


def check_regime():
    """TSX Composite vs MA75 via yfinance. Also returns the actual date of
    the last available trading bar -- the real market date, not whatever
    the wall clock says when the cron happens to run (which can be a
    Saturday re-run of Friday's close, or a holiday).

    BUG FIXED 2026-08-21: had no try/except and no min_periods on the
    rolling mean. period='200d' gives ~138 daily bars, which happens to
    clear MA_W=75 today, but silently produces NaN the moment yfinance
    returns a shorter history (holiday-heavy stretch, API hiccup) or MA_W
    is ever raised past ~135. `last >= nan` evaluates False in Python, so
    the old code would go DEFENSIVE (cash) in total silence -- the wrong
    default. A market-data outage should refuse to publish, not assume a
    market state it doesn't actually know. Returns (None, None, None,
    None) on any failure or insufficient history; callers must treat that
    as "cannot determine regime," not as "regime is off."
    """
    try:
        tsx = yf.download('^GSPTSE', period='200d', auto_adjust=True, progress=False)
        close = tsx['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.dropna()
        if len(close) < MA_W:
            print(f"  check_regime(): only {len(close)} bars available, need >= {MA_W}")
            return None, None, None, None
        last = float(close.iloc[-1])
        ma75 = float(close.rolling(MA_W, min_periods=MA_W).mean().iloc[-1])
        if not (last == last) or not (ma75 == ma75):  # NaN check without importing math
            print("  check_regime(): NaN in last close or MA -- refusing to determine regime")
            return None, None, None, None
        market_date = close.index[-1].date()
        return last >= ma75, round(last, 1), round(ma75, 1), market_date
    except Exception as e:
        print(f"  check_regime() failed: {e}")
        return None, None, None, None


def next_weekday(d):
    """Next calendar day that isn't a Saturday or Sunday -- used to find the
    real next trading day for month-end detection, instead of naive
    tomorrow=today+1 arithmetic, which misses month boundaries that fall on
    a weekend (e.g. last trading day is Fri the 29th, tomorrow=Sat the 30th
    is still the same calendar month, so a same-month check never fires)."""
    nd = d + timedelta(days=1)
    while nd.weekday() >= 5:  # 5=Saturday, 6=Sunday
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
                # close the month at the new book's start date -- without this
                # the ytd script has no end bound for the closed month and
                # keeps extending its return window to "today" forever
                if not m.get('end'):
                    m['end'] = TODAY

        existing_cur = next((m for m in breakdown if m['month'] == cur_month_label), None)
        if existing_cur:
            # BUG FIXED 2026-08-21: this branch fires whenever the current
            # calendar month already has a breakdown entry AND we're
            # rebalancing again within it -- in ordinary operation that
            # never happens (is_new_month only flips once per real month
            # boundary), but a forced config_version migration can trigger
            # exactly this mid-month. The old code updated tickers/weights
            # but left `start` at the PRIOR book's entry date -- e.g. start
            # stayed 2026-08-04 (the old N=15 book) after a 2026-08-20
            # migration to N=10, so anyone pricing the month from `start`
            # would price 16 days of a book that no longer existed. `start`
            # must always reflect when the CURRENTLY-held book began.
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
                m['regime']         = regime_str
                m['tickers']        = [h['ticker'] for h in new_holdings]
                m['weights']        = {h['ticker']: h['weight'] for h in new_holdings}
                m.setdefault('config_version', CONFIG_VERSION)

    return breakdown[-37:]


def write_not_live(reason):
    """Data quality kill switch tripped: don't touch existing holdings or
    pending_signal, just flag both JSON files as not-live with a reason so
    the site shows a warning instead of silently trading on bad data."""
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
    # Establish the operational "today" from the latest available market
    # bar (TSX Composite close via yfinance) instead of the wall clock --
    # this is what makes month-end detection below trading-day-aware
    # (e.g. a Saturday cron re-run still keys off Friday's actual close).
    regime_ok, tsx_val, tsx_ma75, market_date = check_regime()
    if market_date is None:
        # Cannot determine regime (data outage/insufficient history) --
        # refuse to publish rather than silently defaulting to cash. TODAY
        # falls back to the wall-clock date already set at module load.
        write_not_live("check_regime() could not determine TSX/MA75 regime "
                        "(yfinance outage or insufficient history) -- refusing to publish")
        return
    TODAY = market_date.isoformat()
    regime_str = 'momentum' if regime_ok else 'defensive'
    pct_above  = round((tsx_val / tsx_ma75 - 1) * 100, 1)
    print(f"  Regime: {regime_str.upper()}  TSX: {tsx_val}  MA75: {tsx_ma75}  ({pct_above:+.1f}%)  "
          f"[market date: {TODAY}]")

    df, universe_health, broad_prices = fetch_canada()
    if universe_health < MIN_UNIVERSE_ROWS:
        write_not_live(f"TradingView universe fetch returned only {universe_health} tickers "
                        f"(expected {MIN_UNIVERSE_ROWS}+) -- likely an API issue")
        return

    df = df.sort_values('Perf.Y', ascending=False).reset_index(drop=True)

    top_df = df.head(TOP_N) if regime_ok else df.iloc[0:0]

    # Equal weight for the selected top N
    if len(top_df):
        w = 1.0 / len(top_df)
        weight_map = {code: round(w, 4) for code in top_df['code']}
    else:
        weight_map = {}
    selected = set(top_df['code'].tolist())

    top20 = []
    for i, row in df.head(20).iterrows():
        code = row['code']
        top20.append({
            'rank':      int(i) + 1,
            'ticker':    code,
            'name':      str(row.get('description') or row.get('name', code)),
            'ret_12m':   round(float(row['Perf.Y']), 2),
            'net_income_ttm_m': round(float(row['net_income_ttm']) / 1e6, 1),
            'mcap_b':    round(float(row['market_cap_basic']) / 1e9, 3),
            'weight':    weight_map.get(code),
            'selected':  code in selected,
        })

    signal = {
        'date':               TODAY,
        'regime':             regime_str,
        'tsx':                tsx_val,
        'tsx_ma75':           tsx_ma75,
        'pct_above_ma':       pct_above,
        'total_eligible':     int(len(df)),
        'portfolio':          [s for s in top20 if s['selected']],
        'top20':              top20,
        'updated':            TODAY,
        'is_live':            True,
        'not_live_reason':    None,
    }
    with open(DATA_PATH, 'w') as f:
        json.dump(signal, f, indent=2)
    print(f"  Saved: {DATA_PATH}")

    # ── Portfolio tracker ──────────────────────────────────────────────────────
    # Signal is locked in on the last trading day of the month (that day's
    # data); it is executed -- bought at the next trading day's price -- on
    # the first run that detects a new month, matching the backtest's
    # end-of-month signal convention and the USA/UK pending_signal mechanism.
    existing        = load_existing_portfolio()
    last_rebal_m    = existing.get('last_rebalance', '')[:7]
    current_m       = TODAY[:7]
    pending_signal  = existing.get('pending_signal')
    legacy_strategy = (
        (bool(existing.get('holdings')) and any('weight' not in h for h in existing['holdings']))
        or existing.get('config_version') != CONFIG_VERSION
    )
    is_new_month    = current_m != last_rebal_m or legacy_strategy
    if legacy_strategy:
        print(f"  Existing holdings predate config_version={CONFIG_VERSION!r} "
              f"(N=15/EBIT-less/mcap-P30 -> N=10/NetIncome>0/mcap-P20, 2026-08-21) "
              f"-- forcing an immediate rebalance to the current strategy.")

    price_map = {row['code']: float(row['close']) for _, row in df.iterrows()}
    # Real fallback for existing holdings that have since fallen out of the
    # ranking universe (e.g. NetIncome flipped negative while still held --
    # the normal path for a momentum name, not an edge case). broad_prices
    # only requires a valid close, so it covers names df has already
    # filtered out for any other reason.
    price_map_full = broad_prices

    today_sel = [{'ticker': row['code'], 'name': str(row.get('description') or row.get('name', row['code'])),
                  'weight': float(weight_map.get(row['code'], 0))} for _, row in top_df.iterrows()]

    # BUG FIXED 2026-08-21 (found by external Claude-app review): regime was
    # being re-applied on EVERY run (`elif not regime_ok: holdings = []`
    # fired any day, not just at month boundaries), so a mid-month regime
    # flip could dump the book to cash intra-month. The backtest reads
    # regime ONCE at signal time and holds that decision for the whole
    # month regardless of what the index does afterward -- this is the
    # matching live behavior: regime is only actioned when a new month
    # actually rebalances; a same-month re-run just marks prices, it never
    # re-decides exposure.
    if is_new_month:
        if regime_ok:
            if pending_signal and pending_signal.get('for_month') == current_m and not legacy_strategy:
                print(f"  Portfolio: NEW MONTH ({current_m}), executing signal locked in on "
                      f"{pending_signal.get('computed_date')}...")
                exec_picks = pending_signal['picks']  # [{ticker, name, weight}, ...]
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
            ep, edate = cp, TODAY
            holdings.append({
                'ticker':        code,
                'name':          p.get('name', code),
                'entry_date':    edate,
                'entry_price':   round(ep, 4) if ep else None,
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
                print(f"  WARNING: no price found for held ticker {h['ticker']!r} in "
                      f"either the ranking universe or the broad fallback -- "
                      f"current_price/return_pct frozen at last known value.")
            ep = h.get('entry_price')
            if cp:
                h['current_price'] = round(cp, 4)
            if ep and h.get('current_price'):
                h['return_pct'] = round((h['current_price'] / ep - 1) * 100, 2)
            holdings.append(h)
        last_rebalance = existing.get('last_rebalance', TODAY)

    breakdown = build_monthly_breakdown(existing, holdings, is_new_month, regime_str)

    # BUG FIXED 2026-08-21: months_2026 used to include every completed 2026
    # month regardless of which strategy config produced it, so Jan-Jul
    # 2026 (all run under the old N=15/EBIT-less/mcap-P30 config) got
    # compounded together with the new N=10/NetIncome/mcap-P20 config as if
    # it were one continuous track record -- ytd_2026 stayed pinned at the
    # dead strategy's 15.8% number. Only count months tagged with the
    # CURRENT config_version; YTD now starts fresh from the migration date.
    months_2026 = [m for m in breakdown if '2026' in m.get('month', '')
                   and not m.get('is_current')
                   and m.get('config_version') == CONFIG_VERSION]
    if months_2026:
        ytd = 1.0
        for m in months_2026:
            if m.get('return_pct') is not None:
                ytd *= (1 + m['return_pct'] / 100)
        ytd_2026 = round((ytd - 1) * 100, 2)
    else:
        ytd_2026 = None  # no completed months under the current config yet

    # Lock in next month's signal if today's market bar is the last trading
    # day of the month. "Last trading day of month" is approximated as: the
    # next weekday after today's real market date falls in a different
    # calendar month. This is trading-calendar-aware for the ordinary case
    # (Fri 29/30/31 followed by a weekend into the next month) without
    # needing a market-holiday calendar; the actual holiday case (last
    # trading day is followed by a weekday holiday, then the real next
    # trading day) is still handled correctly by the "no matching locked
    # signal -- falling back to today's data" branch on execution, since a
    # missed lock-in day just means next month's cron run recomputes fresh.
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
        new_pending_signal = None  # consumed (or stale) this run either way
    else:
        new_pending_signal = pending_signal

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
        'pending_signal':    new_pending_signal,
        'config_version':    CONFIG_VERSION,
        'is_live':           True,
        'not_live_reason':   None,
    }
    with open(PORTFOLIO_PATH, 'w') as f:
        json.dump(portfolio, f, indent=2)
    print(f"  Saved: {PORTFOLIO_PATH}")

    print(f"\n{'='*80}")
    print(f"Canada Momentum — {TODAY} — {regime_str.upper()}")
    print(f"{'='*80}")
    print(f"{'#':>3} {'':>3} {'Ticker':<10} {'Name':<28} {'12M':>8} {'NI TTM $M':>10} {'Wt':>6} {'MCap B CAD':>12}")
    print(f"{'-'*80}")
    for s in top20:
        mk = ">>>" if s['selected'] else ""
        wt = f"{s['weight']*100:.1f}%" if s['weight'] else ""
        print(f"{s['rank']:3d} {mk:>3} {s['ticker']:<10} {s['name'][:27]:<28} "
              f"{s['ret_12m']:>+7.1f}% {s['net_income_ttm_m']:>9.1f} {wt:>6} {s['mcap_b']:>10.3f}")
    print(f"\nTop {TOP_N} selected | {len(df)} eligible (mcap+netincome filtered) | Regime: {regime_str.upper()}")


if __name__ == '__main__':
    main()
