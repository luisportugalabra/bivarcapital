#!/usr/bin/env python3
"""
Download VC2 World data directly from TradingView API.
Replaces the manual CSV download from the TradingView website.

Output: vc2 world_YYYY-MM-DD_<hash>.csv in the same folder,
with the exact same columns as the manual download, so
vc2_trending_value.py works unchanged.
"""
import os
import sys
from datetime import datetime
import hashlib
import pandas as pd
from tradingview_screener import Query, col

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Markets split into buckets (each bucket < 50K stocks to avoid pagination bug)
MARKET_BUCKETS = [
    # Americas — big because USA has ~15K+ stocks alone
    ('Americas', ['america', 'canada', 'brazil', 'mexico', 'chile', 'colombia', 'peru', 'argentina']),
    # Europe
    ('Europe', ['uk', 'germany', 'france', 'italy', 'spain', 'netherlands',
                'switzerland', 'sweden', 'norway', 'denmark', 'finland', 'belgium',
                'austria', 'ireland', 'portugal', 'greece', 'poland', 'czech', 'hungary',
                'romania', 'turkey', 'russia']),
    # Asia-Pacific
    ('Asia-Pacific', ['japan', 'china', 'hongkong', 'taiwan', 'korea', 'india', 'indonesia',
                      'thailand', 'malaysia', 'philippines', 'vietnam', 'pakistan', 'srilanka',
                      'bangladesh', 'singapore', 'australia', 'newzealand']),
    # Middle East & Africa
    ('MEA', ['saudiarabia', 'uae', 'qatar', 'kuwait', 'bahrain', 'israel',
             'southafrica', 'nigeria', 'kenya', 'egypt', 'morocco']),
]

# TradingView API columns -> CSV column names (matching the manual export exactly)
COL_MAP = {
    'name':                             'Symbol',
    'description':                      'Description',
    'market_cap_basic':                 'Market capitalization',
    'market_cap_basic|currency':        'Market capitalization - Currency',
    'enterprise_value_current':         'Enterprise value',
    'enterprise_value_current|currency':'Enterprise value - Currency',
    'price_earnings_ttm':               'Price to earnings ratio',
    'price_sales_current':              'Price to sales ratio',
    'price_book_fq':                    'Price to book ratio',
    'price_cash_flow_current':          'Price to cash flow ratio',
    'enterprise_value_ebitda_ttm':      'Enterprise value to EBITDA ratio, Trailing 12 months',
    'buyback_yield':                    'Buyback yield %',
    'dividend_yield_recent':            'Dividend yield %, Trailing 12 months',
    'Perf.6M':                          'Performance % 6 months',
    'country':                          'Country or region of registration',
    'oper_income_ttm':                  'Operating income, Trailing 12 months',
    'oper_income_ttm|currency':         'Operating income, Trailing 12 months - Currency',
    'enterprise_value_to_ebit_ttm':     'Enterprise value to EBIT ratio, Trailing 12 months',
    'return_on_invested_capital':       'Return on invested capital %, Trailing 12 months',
    'sector':                           'Sector',
    'Perf.3M':                          'Performance % 3 months',
    'Perf.Y':                           'Performance % 1 year',
}

# Columns to request from API (use base name, not |currency suffix)
API_COLS = [c.split('|')[0] for c in COL_MAP.keys() if '|currency' not in c]

def fetch_all():
    """Fetch all stocks by querying each market bucket separately and concatenating."""
    print("Querying TradingView API by region...")
    all_dfs = []

    for bucket_name, markets in MARKET_BUCKETS:
        q = (Query()
             .select(*API_COLS)
             .where(
                 col('market_cap_basic') > 200_000_000,
                 col('is_primary') == True,
                 col('type') == 'stock',
                 col('typespecs').has('common'),
             )
             .set_markets(*markets)
             .order_by('market_cap_basic', ascending=False)
             .limit(50_000)
             .get_scanner_data()
        )
        total, df = q
        if df is None:
            df = pd.DataFrame()
        print(f"  {bucket_name:<14} available: {total:>6,}  downloaded: {len(df):>6,}")
        if len(df) > 0:
            all_dfs.append(df)

    combined = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
    # Drop duplicates (same ticker in multiple buckets — shouldn't happen but safe)
    if 'ticker' in combined.columns:
        combined = combined.drop_duplicates(subset=['ticker'], keep='first')
    print(f"\n  Total downloaded: {len(combined):,} rows")
    return combined

def reshape_to_csv_format(df):
    """Rename columns and add currency columns to match manual export."""
    # Rename API columns to the CSV names
    rename_map = {k: v for k, v in COL_MAP.items() if '|currency' not in k}
    out = df.rename(columns=rename_map).copy()

    # The TV API returns "ticker" field like "NASDAQ:AAPL" — we want just the symbol
    # which it already is via 'name' -> 'Symbol'. Drop the ticker col.
    if 'ticker' in out.columns:
        out = out.drop(columns=['ticker'])

    # Add currency columns — TV returns currency in a separate field for monetary values.
    # For simplicity we infer/set to USD by default (same convention used by the old CSV
    # for most stocks — currency is only used cosmetically by the downstream script).
    # Actual per-ticker currency is available via API but the downstream script doesn't use it.
    out['Market capitalization - Currency'] = 'USD'
    out['Enterprise value - Currency'] = 'USD'
    out['Operating income, Trailing 12 months - Currency'] = 'USD'

    # Reorder columns to match original CSV order exactly
    final_cols = [
        'Symbol', 'Description',
        'Market capitalization', 'Market capitalization - Currency',
        'Enterprise value', 'Enterprise value - Currency',
        'Price to earnings ratio', 'Price to sales ratio', 'Price to book ratio',
        'Price to cash flow ratio',
        'Enterprise value to EBITDA ratio, Trailing 12 months',
        'Buyback yield %', 'Dividend yield %, Trailing 12 months',
        'Performance % 6 months',
        'Country or region of registration',
        'Operating income, Trailing 12 months',
        'Operating income, Trailing 12 months - Currency',
        'Enterprise value to EBIT ratio, Trailing 12 months',
        'Return on invested capital %, Trailing 12 months',
        'Sector',
        'Performance % 3 months',
        'Performance % 1 year',
    ]
    # Keep only columns we have (some might be missing if API changes)
    final_cols = [c for c in final_cols if c in out.columns]
    out = out[final_cols]
    return out

def main():
    df = fetch_all()
    out = reshape_to_csv_format(df)

    # Build filename matching the old pattern: "vc2 world_YYYY-MM-DD_XXXXX.csv"
    date_str = datetime.now().strftime("%Y-%m-%d")
    # 5-char hash to mimic the TV download filename style
    h = hashlib.md5(str(datetime.now()).encode()).hexdigest()[:5]
    filename = f"vc2 world_{date_str}_{h}.csv"
    out_path = os.path.join(SCRIPT_DIR, filename)

    out.to_csv(out_path, index=False)
    size_mb = os.path.getsize(out_path) / 1e6
    print(f"\n  Saved: {filename}")
    print(f"  Rows:  {len(out):,}")
    print(f"  Size:  {size_mb:.1f} MB")
    return out_path

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERRO: {e}")
        sys.exit(1)
