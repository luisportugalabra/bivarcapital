#!/usr/bin/env python3
"""
Denmark Momentum Signal Generator
Uses TradingView Screener exclusively — no EODHD, no yfinance.

Strategy:
  - Universe: Nasdaq Copenhagen (denmark market on TV), mcap > 700M DKK
  - Signal: 50% Perf.6M + 50% Perf.Y (matches TV data exactly)
  - Select top 10 by composite
  - Regime: synthetic cap-weighted index vs SMA100 (built from TV data)
  - Monthly rebalance, InvVol weighting approximated by equal weight (TV has no vol history)

Saves:
  - denmark-momentum-data.json
  - denmark-momentum-portfolio.json
"""
import os, json
from datetime import datetime, date
import calendar

from tradingview_screener import Query, col

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
SITE_DIR      = os.path.dirname(SCRIPT_DIR)
DATA_PATH      = os.path.join(SITE_DIR, "denmark-momentum-data.json")
PORTFOLIO_PATH = os.path.join(SITE_DIR, "denmark-momentum-portfolio.json")

MCAP_MIN_DKK = 700_000_000   # 700M DKK ≈ 100M USD
TOP_N        = 10
TODAY        = date.today().isoformat()

DANISH_NAMES = {
    "NOVO_B":"Novo Nordisk B","DSV":"DSV A/S","MAERSK_B":"A.P. Møller-Mærsk B",
    "MAERSK_A":"A.P. Møller-Mærsk A","ORSTED":"Ørsted A/S","CARL_A":"Carlsberg A",
    "NSIS_B":"Novonesis B","VWS":"Vestas Wind Systems","DANSKE":"Danske Bank",
    "NDA_DK":"Nordea Bank","GN":"GN Store Nord","PNDORA":"Pandora",
    "COLO_B":"Coloplast B","DEMANT":"Demant A/S","AMBU_B":"Ambu B",
    "TRYG":"Tryg A/S","JYSK":"Jyske Bank","SYDB":"Sydbank","NKT":"NKT A/S",
    "ISS":"ISS A/S","ROCK_A":"Rockwool A","DFDS":"DFDS A/S","NETC":"Netcompany",
    "BAYAS":"Bavarian Nordic","BOOZT_DKK":"Boozt","FOBANK":"Fynske Bank",
    "SPG":"Schouw & Co","TRMD_A":"Torm A","SKJE":"Skjern Bank","DJUR":"Djurslands Bank",
    "NTG":"NTG Nordic Transport","FLUG_B":"Flügger","DNORD":"D/S Norden",
    "RBREW":"Royal Unibrew","MATAS":"Matas","LASP":"Lån & Spar Bank",
    "MNBA":"Møns Bank","NLFSK":"Nordfyns Bank","GRLA":"Grønlandsbanken",
    "ALSYDB":"Als-Sydbankaktier","PAAL_B":"Per Aarsleff B",
}

def tv_to_eodhd(tv_ticker):
    """OMXCOP:BOOZT_DKK → BOOZT-DKK"""
    code = tv_ticker.split(":")[-1]
    return code.replace("_", "-")

def eodhd_to_tv(tk):
    """BOOZT-DKK → BOOZT_DKK"""
    return tk.replace("-", "_")

def dname(tv_code):
    return DANISH_NAMES.get(tv_code, tv_code.replace("_", " "))


def fetch_denmark():
    """Fetch all Danish stocks from TV Screener with momentum + regime data."""
    print("Fetching TradingView data (Denmark)...")
    _, df = (Query()
        .select('name', 'market_cap_basic', 'Perf.6M', 'Perf.Y',
                'close', 'SMA100', 'volume')
        .set_markets('denmark')
        .order_by('market_cap_basic', ascending=False)
        .limit(500)
        .get_scanner_data()
    )
    print(f"  Raw rows: {len(df)}")

    # Strip exchange prefix, keep only OMXCOP stocks
    df = df[df['ticker'].str.startswith('OMXCOP:')].copy()
    df['code'] = df['ticker'].str.replace('OMXCOP:', '', regex=False)
    df['ticker_eodhd'] = df['code'].str.replace('_', '-', regex=False)

    # Market cap filter
    df = df[df['market_cap_basic'] >= MCAP_MIN_DKK].copy()
    print(f"  After mcap filter (>700M DKK): {len(df)}")

    # Drop missing momentum
    df = df.dropna(subset=['Perf.6M', 'Perf.Y']).copy()
    print(f"  After momentum filter: {len(df)}")

    # Composite signal
    df['composite'] = 0.5 * df['Perf.6M'] + 0.5 * df['Perf.Y']

    return df.sort_values('composite', ascending=False).reset_index(drop=True)


def check_regime(df):
    """
    Synthetic cap-weighted regime: is the cap-weighted index above its SMA100?
    Uses close and SMA100 from each stock, weighted by market cap.
    """
    sub = df.dropna(subset=['close', 'SMA100', 'market_cap_basic']).copy()
    if len(sub) == 0:
        return True, None, None

    total_mcap = sub['market_cap_basic'].sum()
    w = sub['market_cap_basic'] / total_mcap

    idx_now  = (sub['close']  * w).sum()
    idx_ma100 = (sub['SMA100'] * w).sum()
    above = idx_now >= idx_ma100
    pct   = round((idx_now / idx_ma100 - 1) * 100, 2)
    return bool(above), round(idx_now, 1), round(idx_ma100, 1)


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
        # Close out the previous current month (set return to None — will be filled by history)
        for m in breakdown:
            if m.get('is_current'):
                m['is_current'] = False

        # Add new current month entry
        cur_month_label = datetime.now().strftime('%b %Y')
        tickers = [h['ticker_eodhd'] for h in new_holdings]

        # Avoid duplicate
        if not any(m['month'] == cur_month_label for m in breakdown):
            breakdown.append({
                'month': cur_month_label,
                'is_current': True,
                'start': TODAY,
                'end': None,
                'regime': regime_str,
                'tickers': tickers,
                'return_pct': None,
            })
    else:
        # Update current month tickers if regime changed
        for m in breakdown:
            if m.get('is_current'):
                m['regime'] = regime_str
                m['tickers'] = [h['ticker_eodhd'] for h in new_holdings]

    return breakdown[-37:]  # keep last 37 months


def main():
    df = fetch_denmark()

    # Regime
    regime_ok, idx_val, idx_ma100 = check_regime(df)
    regime_str = 'momentum' if regime_ok else 'defensive'
    pct_above  = round((idx_val / idx_ma100 - 1) * 100, 1) if idx_val and idx_ma100 else 0
    print(f"  Regime: {regime_str.upper()}  Index: {idx_val}  MA100: {idx_ma100}  ({pct_above:+.1f}%)")

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
            'name':      dname(code),
            'ret_6m':    round(float(row['Perf.6M']), 1),
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
        'index_ma100':    idx_ma100,
        'pct_above_ma':   pct_above,
        'total_eligible': int(len(df)),
        'portfolio':      [s for s in top20 if s['selected']],
        'top20':          top20,
    }
    with open(DATA_PATH, 'w') as f:
        json.dump(signal, f, indent=2)
    print(f"  Saved: {DATA_PATH}")

    # ── Portfolio tracker ─────────────────────────────────────────────────────
    existing      = load_existing_portfolio()
    existing_map  = {h.get('ticker_eodhd', h.get('ticker', '')): h for h in existing.get('holdings', [])}
    last_rebal_m  = existing.get('last_rebalance', '')[:7]
    current_m     = datetime.now().strftime('%Y-%m')
    is_new_month  = current_m != last_rebal_m

    # Build price lookup from TV data (code → close)
    price_map = {row['code']: float(row['close']) for _, row in df.iterrows()
                 if row['close'] is not None}

    if is_new_month and regime_ok:
        print(f"  Portfolio: NEW MONTH ({current_m}), rebalancing to top {TOP_N}...")
        holdings = []
        for _, row in top_df.iterrows():
            code = row['code']
            tk   = row['ticker_eodhd']
            cp   = price_map.get(code)
            # If stock was already held, keep entry price; otherwise entry = today's close
            if tk in existing_map:
                ep = existing_map[tk].get('entry_price') or cp
            else:
                ep = cp
            ret = round((cp / ep - 1) * 100, 2) if ep and cp else None
            holdings.append({
                'ticker':        tk,
                'ticker_tv':     f"OMXCOP:{code}",
                'ticker_eodhd':  tk,
                'name':          dname(code),
                'entry_date':    TODAY,
                'entry_price':   round(ep, 2) if ep else None,
                'current_price': round(cp, 2) if cp else None,
                'return_pct':    ret,
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
            code = eodhd_to_tv(h['ticker'])
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
    months_2026 = [m for m in breakdown if '2026' in m.get('month','') and not m.get('is_current')]
    if months_2026:
        ytd = 1.0
        for m in months_2026:
            if m.get('return_pct') is not None:
                ytd *= (1 + m['return_pct'] / 100)
        ytd_2026 = round((ytd - 1) * 100, 1)
    else:
        ytd_2026 = existing.get('ytd_2026', 0)

    portfolio = {
        'last_rebalance':   last_rebalance,
        'updated':          TODAY,
        'ytd_2026':         ytd_2026,
        'regime':           regime_str,
        'currency':         'DKK',
        'index_value':      idx_val,
        'index_ma100':      idx_ma100,
        'holdings':         holdings,
        'monthly_breakdown': breakdown,
    }
    with open(PORTFOLIO_PATH, 'w') as f:
        json.dump(portfolio, f, indent=2)
    print(f"  Saved: {PORTFOLIO_PATH}")

    # Print summary
    print(f"\n{'='*80}")
    print(f"Denmark Momentum — {TODAY} — {regime_str.upper()}")
    print(f"{'='*80}")
    print(f"{'#':>3} {'':>3} {'Ticker':<14} {'Name':<28} {'6M':>8} {'12M':>8} {'Comp':>8} {'MCap B DKK':>12}")
    print(f"{'-'*80}")
    for s in top20:
        mk = ">>>" if s['selected'] else ""
        print(f"{s['rank']:3d} {mk:>3} {s['ticker']:<14} {s['name'][:27]:<28} "
              f"{s['ret_6m']:>+7.1f}% {s['ret_12m']:>+7.1f}% {s['composite']:>+7.1f}% {s['mcap_b']:>10.1f}")
    print(f"\nTop {TOP_N} selected | {len(df)} eligible | Regime: {regime_str.upper()}")


if __name__ == '__main__':
    main()
