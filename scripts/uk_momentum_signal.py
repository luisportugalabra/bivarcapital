#!/usr/bin/env python3
"""
BivarUKMomentum — Monthly Signal Generator

Downloads live data from TradingView LSE, calculates the UK momentum strategy,
and outputs uk-momentum-data.json for the website.

Strategy:
  - Momentum = 50% × Perf.6M + 50% × Perf.12M (composite)
  - Universe: LSE, market cap > £250M (~$312M), EBIT > 0, common stock, GBX
  - Select top 12 by composite momentum
  - Regime: FTSE 100 < MA200 → GLD

Usage: python3 uk_momentum_signal.py
"""
import os
import json
import calendar
from datetime import datetime, date

import pandas as pd
import numpy as np
from tradingview_screener import Query, col

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
SITE_DIR      = os.path.dirname(SCRIPT_DIR)
JSON_PATH     = os.path.join(SITE_DIR, 'uk-momentum-data.json')
PORTFOLIO_PATH = os.path.join(SITE_DIR, 'uk-momentum-portfolio.json')

MIN_MCAP_USD = 312_500_000   # ≈ £250M
TOP_N        = 12


def fetch_stocks():
    """Fetch eligible UK stocks from TradingView."""
    _, df = (Query()
             .select('name', 'description', 'market_cap_basic',
                     'oper_income_ttm', 'sector',
                     'Perf.6M', 'Perf.Y', 'close', 'currency')
             .where(
                 col('market_cap_basic') > MIN_MCAP_USD,
                 col('is_primary') == True,
                 col('type') == 'stock',
                 col('typespecs').has('common'),
                 col('oper_income_ttm') > 0,
                 col('currency') == 'GBX',
             )
             .set_markets('uk')
             .order_by('market_cap_basic', ascending=False)
             .limit(2_000)
             .get_scanner_data())

    df['exchange'] = df['ticker'].str.split(':').str[0]
    df['ticker']   = df['ticker'].str.split(':').str[-1]
    df['name']     = df['description'].astype(str)
    df = df.drop(columns=['description'], errors='ignore')

    df = df.rename(columns={
        'market_cap_basic': 'mcap',
        'oper_income_ttm':  'ebit',
        'Perf.6M':          'ret_6m',
        'Perf.Y':           'ret_12m',
    })

    df = df.dropna(subset=['ret_6m'])
    df['composite'] = (df['ret_6m'].fillna(0) / 100) * 0.5 + (df['ret_12m'].fillna(0) / 100) * 0.5

    return df.sort_values('composite', ascending=False).reset_index(drop=True)


def check_regime():
    """Check FTSE 100 vs MA200 via yfinance."""
    try:
        import yfinance as yf, math, warnings
        warnings.filterwarnings('ignore')
        data  = yf.download('^FTSE', period='2y', progress=False)
        close = data['Close'].squeeze().dropna()
        if len(close) == 0:
            return None, None, True
        last  = float(close.iloc[-1])
        ma200 = float(close.tail(200).mean())
        if math.isnan(last) or math.isnan(ma200):
            return None, None, True
        return last, ma200, last >= ma200
    except Exception:
        return None, None, True


def select_top(df, n=TOP_N):
    return [str(t) for t in df.head(n)['ticker']]


def main():
    print("Fetching TradingView LSE data...")
    df = fetch_stocks()
    print(f"  Eligible: {len(df)} stocks")

    ftse_last, ftse_ma200, regime_ok = check_regime()
    regime = "momentum" if regime_ok else "gld"
    print(f"  FTSE 100: {ftse_last:,.1f}  MA200: {ftse_ma200:,.1f}  Regime: {regime.upper()}")

    sel7 = select_top(df, TOP_N)

    top20 = []
    for i, (_, row) in enumerate(df.head(40).iterrows(), 1):
        t = str(row['ticker'])
        entry = {
            "rank":      i,
            "ticker":    t,
            "name":      str(row['name']),
            "sector":    str(row['sector']),
            "price":     round(float(row.get('close', 0)), 2),
            "ret_6m":    round(float(row['ret_6m']), 1),
            "ret_12m":   round(float(row.get('ret_12m', 0) or 0), 1),
            "composite": round(float(row['composite'] * 100), 1),
            "mcap_b":    round(float(row['mcap'] / 1e9), 2),
            "ebit_m":    round(float(row['ebit'] / 1e6), 0),
            "selected":  t in sel7,
        }
        top20.append(entry)

    output = {
        "date":           datetime.now().strftime("%Y-%m-%d"),
        "regime":         regime,
        "ftse100":        round(ftse_last, 1) if ftse_last else None,
        "ftse100_ma200":  round(ftse_ma200, 1) if ftse_ma200 else None,
        "total_eligible": len(df),
        "portfolio":      [t for t in top20 if t["selected"]],
        "top20":          top20,
    }

    with open(JSON_PATH, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"  Saved: {JSON_PATH}")

    print(f"\n{'='*110}")
    print(f"  BivarUKMomentum — {output['date']}")
    print(f"  FTSE 100: {ftse_last:,.1f} | MA200: {ftse_ma200:,.1f} | Regime: {regime.upper()}")
    print(f"{'='*110}")
    print(f"  {'#':>3} {'':>3} {'Ticker':<8} {'Name':<30} {'Sector':<22} {'Ret6m':>7} {'Ret12m':>7} {'MCap£B':>8} {'EBIT£M':>7}")
    print(f"  {'-'*110}")
    for t in top20:
        sel = ">>>" if t['selected'] else ""
        print(f"  {t['rank']:3d} {sel:>3} {t['ticker']:<8} {t['name'][:29]:<30} {t['sector'][:21]:<22} {t['ret_6m']:>+6.1f}% {t['ret_12m']:>+6.1f}% {t['mcap_b']:>7.2f} {t['ebit_m']:>6.0f}")

    print(f"\n  >>> = Selected for portfolio (top {TOP_N})")
    print(f"  Total eligible: {len(df)}")

    # ── Monthly rollover ───────────────────────────────────────────────────────
    _rollover_portfolio(sel7, df, output['date'], regime)

    return output


def _rollover_portfolio(new_tickers, df, today_str, regime):
    """
    If a new month has started since the last rebalance:
      1. Finalize the previous month's return (prices on its end date via yfinance)
      2. Add a new month entry with the current picks
      3. Rebuild holdings with entry prices for new tickers
    """
    import yfinance as yf

    today = datetime.strptime(today_str, '%Y-%m-%d').date()
    current_month = (today.year, today.month)

    # Load existing portfolio
    try:
        with open(PORTFOLIO_PATH) as f:
            portfolio = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        portfolio = {'last_rebalance': '', 'monthly_breakdown': [], 'holdings': []}

    breakdown = portfolio.get('monthly_breakdown', [])

    # Find current open month
    last_entry = breakdown[-1] if breakdown else None
    if last_entry:
        last_end = datetime.strptime(last_entry['end'], '%Y-%m-%d').date()
        last_month = (last_end.year, last_end.month)
    else:
        last_end = None
        last_month = (0, 0)

    if current_month <= last_month:
        print(f"  UK portfolio: already up to date ({last_entry['month'] if last_entry else '-'})")
        return

    print(f"  UK portfolio: new month ({today.strftime('%b %Y')}), rolling over...")

    # 1. Finalize previous open month using end-date prices
    if last_entry and last_entry.get('is_current'):
        prev_tickers = last_entry['tickers']
        prev_end_str = last_entry['end']
        prev_end = datetime.strptime(prev_end_str, '%Y-%m-%d').date()
        prev_start = datetime.strptime(last_entry['start'], '%Y-%m-%d').date()

        # Fetch price range covering start → end
        yf_tickers = [t + '.L' for t in prev_tickers]
        try:
            raw = yf.download(
                yf_tickers,
                start=prev_start.isoformat(),
                end=(date(prev_end.year, prev_end.month, min(prev_end.day + 3, 31)) if prev_end.month < 12
                     else date(prev_end.year + 1, 1, 3)).isoformat(),
                progress=False, auto_adjust=True,
            )
            prices_hist = raw['Close'] if isinstance(raw.columns, pd.MultiIndex) else raw

            def get_price_on(ticker, target):
                yt = ticker + '.L'
                col_data = prices_hist[yt] if yt in prices_hist.columns else None
                if col_data is None:
                    return None
                valid = col_data.dropna()
                valid = valid[valid.index.date <= target]
                return float(valid.iloc[-1]) if not valid.empty else None

            rets = []
            for tk in prev_tickers:
                p0 = get_price_on(tk, prev_start)
                p1 = get_price_on(tk, prev_end)
                if p0 and p1 and p0 > 0:
                    rets.append(p1 / p0 - 1)
            if rets:
                last_entry['return_pct'] = round(sum(rets) / len(rets) * 100, 2)
        except Exception as e:
            print(f"  Warning: could not fetch final prices for {last_entry['month']}: {e}")

        last_entry['is_current'] = False

    # 2. Add new month entry
    name_map   = {str(r['ticker']): str(r['name'])   for _, r in df.head(30).iterrows()}
    sector_map = {str(r['ticker']): str(r['sector']) for _, r in df.head(30).iterrows()}

    last_day = calendar.monthrange(today.year, today.month)[1]
    new_end  = date(today.year, today.month, last_day).isoformat()
    new_start = last_end.isoformat() if last_end else today_str
    month_names = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                   7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}
    new_label = f"{month_names[today.month]} {today.year}"

    new_entry = {
        'month':      new_label,
        'start':      new_start,
        'end':        new_end,
        'tickers':    new_tickers if regime == 'momentum' else [],
        'return_pct': 0.0,
        'is_current': True,
    }
    breakdown.append(new_entry)

    # 3. Build new holdings with entry prices
    existing_map = {h['ticker']: h for h in portfolio.get('holdings', [])}
    new_entries = [t for t in new_tickers if t not in existing_map]
    entry_prices = {}
    if new_entries:
        try:
            yf_new = [t + '.L' for t in new_entries]
            ep_dl = yf.download(yf_new, period='1d', progress=False, auto_adjust=True)
            for tk in new_entries:
                yt = tk + '.L'
                try:
                    if len(new_entries) == 1:
                        entry_prices[tk] = float(ep_dl['Close'].dropna().iloc[-1])
                    else:
                        entry_prices[tk] = float(ep_dl['Close'][yt].dropna().iloc[-1])
                except Exception:
                    entry_prices[tk] = None
        except Exception as e:
            print(f"  Warning: entry price fetch failed: {e}")

    holdings = []
    for tk in (new_tickers if regime == 'momentum' else []):
        if tk in existing_map:
            h = existing_map[tk].copy()
        else:
            ep = entry_prices.get(tk)
            h = {
                'ticker':        tk,
                'name':          name_map.get(tk, tk),
                'sector':        sector_map.get(tk, ''),
                'entry_date':    today_str,
                'entry_price':   round(ep, 2) if ep else None,
                'current_price': round(ep, 2) if ep else None,
                'return_pct':    0.0,
            }
        h['name']   = name_map.get(tk, h.get('name', tk))
        h['sector'] = sector_map.get(tk, h.get('sector', ''))
        ep = h.get('entry_price'); cp = h.get('current_price')
        h['return_pct'] = round((cp / ep - 1) * 100, 2) if ep and cp else 0.0
        holdings.append(h)

    # Compute YTD
    ytd_factor = 1.0
    for m in breakdown:
        if not m.get('is_current'):
            ytd_factor *= (1 + m['return_pct'] / 100)
    ytd_return = round((ytd_factor - 1) * 100, 2)

    out = {
        'last_rebalance': new_start,
        'updated':        today_str,
        'ytd_2026':       ytd_return,
        'currency':       'GBX',
        'currency_note':  'Prices in pence (GBX). £1 = 100p.',
        'monthly_breakdown': breakdown,
        'holdings':       holdings,
    }
    with open(PORTFOLIO_PATH, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"  UK portfolio: saved {PORTFOLIO_PATH}  (YTD {ytd_return:+.2f}%)")


if __name__ == "__main__":
    main()
