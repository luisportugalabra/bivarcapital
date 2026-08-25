#!/usr/bin/env python3
"""
Indonesia Momentum Signal Generator
Uses TradingView Screener exclusively for the live signal — no EODHD, no yfinance.
(EODHD JK parquets are used only as a start-of-month price fallback for the
paper-portfolio return tracker, same convention as Denmark's script.)

Strategy:
  - Universe: Indonesia (IDX:) common stocks — TV `type=='stock'` + `typespecs
    has 'common'` — market cap >= 1,000,000,000,000 IDR (1 trillion)
  - Signal: pure 12-month momentum, no skip — TradingView's `Perf.Y` field
    (trailing 12-month performance) used directly as the composite. Single
    factor, not a blend (unlike Denmark's 50/50 Perf.6M+Perf.Y).
  - Select top 15 by Perf.Y
  - Regime: TradingView Screener only exposes a current snapshot per ticker,
    not historical daily bars for ~800 names, so a literal JCI/^JKSE chart
    reconstruction isn't possible from this data source. Instead: cap-weighted
    average of (close / SMA200) across the full IDX common-stock universe (not
    just the mcap-eligible subset) as a synthetic, snapshot-based cross-
    sectional proxy for "index vs its own 200-day MA". Momentum regime when
    the weighted ratio >= 1.0, else 100% cash.
  - Equal weight top 15, monthly rebalance

BETA (2026-08-25): launched with the HONEST audited numbers, not the inflated
raw backtest. The raw full-period (2004-2026) backtest showed CAGR +28.0% /
Sharpe 0.99, but a hostile adversarial audit found this inflated by confirmed
survivorship bias in the 2004-2016 data (-1.5 to -2.5pp CAGR haircut,
quantified via an official IDX delistings cross-reference — the EODHD JK
download has ~0 coverage of real pre-2017 delistings). The survivorship-clean
2017-2026 standalone window is the number to cite: CAGR +19.1% / Sharpe 0.66
gross, or +15.1% / Sharpe 0.56 net of ~100bps estimated transaction costs and
a realistic IDR risk-free rate. Liquidity/capacity caveat: at $1M position
sizing, ~28% of positions would exceed 100% of daily ADV (top P&L contributors
like MGLV/PGUN/POLU trade only $10-40k/day) — this is a capacity-constrained
signal, not yet validated as fully investable at scale. Top-5 holdings have
historically driven ~79% of total P&L (concentrated). EBIT filter intentionally
NOT applied — the audit found EBIT data coverage too thin below a 5T mcap floor
to trust it at this 1T floor. See ~/eodhd_data/AUDIT_INDONESIA_HOSTILE.md and
~/.claude memory project_indonesia_momentum.md for the full writeup.

Saves:
  - indonesia-momentum-data.json
  - indonesia-momentum-portfolio.json
"""
import os, json
from datetime import datetime, date

import pandas as pd
from tradingview_screener import Query, col

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
SITE_DIR       = os.path.dirname(SCRIPT_DIR)
DATA_PATH      = os.path.join(SITE_DIR, "indonesia-momentum-data.json")
PORTFOLIO_PATH = os.path.join(SITE_DIR, "indonesia-momentum-portfolio.json")

MCAP_MIN_IDR = 1_000_000_000_000   # 1 trillion IDR
TOP_N        = 15
MA_WINDOW    = 200
TODAY        = date.today().isoformat()


def fetch_indonesia():
    """Fetch all IDX common stocks from TV Screener with momentum + regime data."""
    print("Fetching TradingView data (Indonesia)...")
    _, df = (Query()
        .select('name', 'description', 'market_cap_basic', 'Perf.Y',
                'close', 'SMA200', 'volume')
        .where(
            col('type') == 'stock',
            col('typespecs').has('common'),
        )
        .set_markets('indonesia')
        .order_by('market_cap_basic', ascending=False)
        .limit(3000)
        .get_scanner_data()
    )
    print(f"  Raw rows: {len(df)}")

    df = df[df['ticker'].str.startswith('IDX:')].copy()
    df['code'] = df['ticker'].str.replace('IDX:', '', regex=False)
    df['ticker_eodhd'] = df['code']

    # Broad universe (before mcap filter) — used only for the regime calc,
    # mirrors how a real market index includes far more names than the
    # investable momentum universe.
    broad = df.dropna(subset=['market_cap_basic', 'close', 'SMA200']).copy()
    broad = broad[(broad['SMA200'] > 0) & (broad['market_cap_basic'] > 0)]
    print(f"  Broad universe (regime calc): {len(broad)}")

    # Signal universe
    df = df.dropna(subset=['Perf.Y', 'close', 'market_cap_basic']).copy()
    print(f"  With perf+mcap+close: {len(df)}")

    df = df[df['market_cap_basic'] >= MCAP_MIN_IDR].copy()
    print(f"  After mcap filter (>=1T IDR): {len(df)}")

    df['composite'] = df['Perf.Y']

    return df.sort_values('composite', ascending=False).reset_index(drop=True), broad


def check_regime(broad):
    """
    Synthetic cap-weighted regime proxy: cap-weighted average of (close/SMA200)
    across the full IDX common-stock universe, vs its own baseline of 1.0
    (equivalent to "index vs its own 200-day MA", scaled to a base-1000 index
    for JSON-schema parity with the other market scripts).
    """
    if len(broad) < 50:
        print("  WARNING: insufficient universe for regime calc, defaulting to momentum")
        return True, None, None

    w     = broad['market_cap_basic'].astype(float)
    ratio = broad['close'].astype(float) / broad['SMA200'].astype(float)
    weighted_ratio = float((w * ratio).sum() / w.sum())

    index_value = round(weighted_ratio * 1000, 1)
    index_ma200 = 1000.0
    return weighted_ratio >= 1.0, index_value, index_ma200


def load_existing_portfolio():
    try:
        with open(PORTFOLIO_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def build_monthly_breakdown(existing, new_holdings, is_new_month, regime_str):
    """Update monthly breakdown list."""
    breakdown = existing.get('monthly_breakdown', [])

    if is_new_month:
        cur_month_label = datetime.now().strftime('%b %Y')
        tickers = [h.get('ticker_eodhd', h.get('ticker', '')) for h in new_holdings]

        for m in breakdown:
            if m.get('is_current') and m['month'] != cur_month_label:
                m['is_current'] = False

        existing_cur = next((m for m in breakdown if m['month'] == cur_month_label), None)
        if existing_cur:
            existing_cur['is_current'] = True
            existing_cur['regime']     = regime_str
            existing_cur['tickers']    = tickers
            existing_cur['return_pct'] = None
        else:
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
        # Update current month tickers if regime changed
        for m in breakdown:
            if m.get('is_current'):
                m['regime'] = regime_str
                m['tickers'] = [h.get('ticker_eodhd', h.get('ticker', '')) for h in new_holdings]

    return breakdown[-37:]  # keep last 37 months


def main():
    df, broad = fetch_indonesia()

    # Regime
    regime_ok, idx_val, idx_ma200 = check_regime(broad)
    regime_str = 'momentum' if regime_ok else 'defensive'
    pct_above  = round((idx_val / idx_ma200 - 1) * 100, 1) if idx_val and idx_ma200 else 0
    print(f"  Regime: {regime_str.upper()}  Index: {idx_val}  MA200: {idx_ma200}  ({pct_above:+.1f}%)")

    # Select top N (or cash if defensive)
    top_df   = df.head(TOP_N) if regime_ok else df.iloc[0:0]
    selected = set(top_df['code'].tolist())

    # Build top 20 list
    top20 = []
    for i, row in df.head(20).iterrows():
        code = row['code']
        top20.append({
            'rank':      int(i) + 1,
            'ticker':    row['ticker_eodhd'],
            'name':      row['description'] or code,
            'ret_12m':   round(float(row['Perf.Y']), 1),
            'composite': round(float(row['composite']), 1),
            'mcap_b':    round(float(row['market_cap_basic']) / 1e9, 2),
            'selected':  code in selected,
        })

    # Signal JSON
    signal = {
        'date':           TODAY,
        'regime':         regime_str,
        'index_value':    idx_val,
        'index_ma200':    idx_ma200,
        'pct_above_ma':   pct_above,
        'total_eligible': int(len(df)),
        'portfolio':      [s for s in top20 if s['selected']],
        'top20':          top20,
    }
    with open(DATA_PATH, 'w') as f:
        json.dump(signal, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {DATA_PATH}")

    # ── Portfolio tracker ─────────────────────────────────────────────────────
    existing      = load_existing_portfolio()
    existing_map  = {h.get('ticker_eodhd', h.get('ticker', '')): h for h in existing.get('holdings', [])}
    last_rebal_m  = existing.get('last_rebalance', '')[:7]
    current_m     = datetime.now().strftime('%Y-%m')
    is_new_month  = current_m != last_rebal_m

    # Price lookup from TV data (code -> close)
    price_map = {row['code']: float(row['close']) for _, row in df.iterrows()
                 if row['close'] is not None}
    # Also include broad universe closes so existing holdings that fell out of
    # the top-mcap ranking universe can still be priced/updated.
    for _, row in broad.iterrows():
        price_map.setdefault(row['code'], float(row['close']))

    def get_som_price(code):
        """Get start-of-month price from EODHD parquet (first trading day of current month)."""
        fpath = os.path.join(SCRIPT_DIR, '..', '..', 'eodhd_data', 'JK', 'prices', f'{code}.parquet')
        fpath = os.path.normpath(fpath)
        try:
            p = pd.read_parquet(fpath)['adjusted_close']
            month_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
            som = p[p.index >= month_start]
            if len(som) > 0:
                return float(som.iloc[0]), som.index[0].strftime('%Y-%m-%d')
        except Exception:
            pass
        return None, None

    if is_new_month and regime_ok:
        print(f"  Portfolio: NEW MONTH ({current_m}), rebalancing to top {TOP_N}...")
        holdings = []
        edate = TODAY
        for _, row in top_df.iterrows():
            code = row['code']
            tk   = row['ticker_eodhd']
            cp   = price_map.get(code)
            ep, edate_i = get_som_price(code)
            if ep is None:
                ep, edate_i = cp, TODAY
            edate = edate_i or TODAY
            ret = round((cp / ep - 1) * 100, 2) if ep and cp else None
            holdings.append({
                'ticker':        tk,
                'ticker_tv':     f"IDX:{code}",
                'ticker_eodhd':  tk,
                'name':          row['description'] or code,
                'entry_date':    edate,
                'entry_price':   round(ep, 2) if ep else None,
                'current_price': round(cp, 2) if cp else None,
                'return_pct':    ret,
            })
        last_rebalance = edate or TODAY

    elif not regime_ok:
        print(f"  Portfolio: DEFENSIVE — cash")
        holdings = []
        last_rebalance = existing.get('last_rebalance', TODAY)

    else:
        print(f"  Portfolio: same month ({current_m}), updating prices...")
        holdings = []
        for h in existing.get('holdings', []):
            h = h.copy()
            code = h.get('ticker_eodhd', h.get('ticker', ''))
            cp   = price_map.get(code)
            ep   = h.get('entry_price')
            if cp:
                h['current_price'] = round(cp, 2)
            if ep and h.get('current_price'):
                h['return_pct'] = round((h['current_price'] / ep - 1) * 100, 2)
            holdings.append(h)
        last_rebalance = existing.get('last_rebalance', TODAY)

    # YTD 2026
    breakdown = build_monthly_breakdown(existing, holdings, is_new_month, regime_str)
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
        'currency':          'IDR',
        'index_value':       idx_val,
        'index_ma200':       idx_ma200,
        'holdings':          holdings,
        'monthly_breakdown': breakdown,
    }
    with open(PORTFOLIO_PATH, 'w') as f:
        json.dump(portfolio, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {PORTFOLIO_PATH}")

    # Print summary
    print(f"\n{'='*90}")
    print(f"Indonesia Momentum — {TODAY} — {regime_str.upper()}")
    print(f"{'='*90}")
    print(f"{'#':>3} {'':>3} {'Ticker':<10} {'Name':<32} {'12M':>8} {'MCap B IDR':>14}")
    print(f"{'-'*90}")
    for s in top20:
        mk = ">>>" if s['selected'] else ""
        print(f"{s['rank']:3d} {mk:>3} {s['ticker']:<10} {s['name'][:31]:<32} "
              f"{s['ret_12m']:>+7.1f}% {s['mcap_b']:>13.1f}")
    print(f"\nTop {TOP_N} selected | {len(df)} eligible | Regime: {regime_str.upper()}")


if __name__ == '__main__':
    main()
