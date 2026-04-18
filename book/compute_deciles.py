#!/usr/bin/env python3
"""
Compute full D1–D10 decile backtests for all single factors.
Annual rebalance, 12 monthly cohorts averaged (eliminates timing bias).
Outputs all_deciles.json with CAGR for every decile.
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

HOME = Path.home()
DATA_DIR = HOME / 'sharadar'
OUT = HOME / 'bivarcapital/book/data/all_deciles.json'

# ── Step 1: Build EOM price cache ───────────────────────────────────────────
print("Loading SEP daily prices...")
sep = pd.read_parquet(DATA_DIR / 'sep_daily.parquet', columns=['ticker', 'date', 'closeadj'])
sep['date'] = pd.to_datetime(sep['date'])
sep = sep.dropna(subset=['closeadj'])
sep = sep[sep['closeadj'] > 0]

print("Building EOM price cache...")
sep['ym'] = sep['date'].dt.to_period('M')
eom = sep.sort_values('date').groupby(['ticker', 'ym']).last().reset_index()
eom = eom[['ticker', 'ym', 'closeadj']].rename(columns={'closeadj': 'price'})
eom['ym_str'] = eom['ym'].astype(str)
print(f"  EOM cache: {len(eom):,} rows")

# Build price lookup: ticker -> {ym_str: price}
print("Building price lookup dict...")
price_dict = {}
for ticker, grp in eom.groupby('ticker'):
    price_dict[ticker] = dict(zip(grp['ym_str'], grp['price']))
print(f"  {len(price_dict):,} tickers in price dict")

# ── Step 2: Load fundamentals ──────────────────────────────────────────────
print("Loading SF1 quarterly TTM...")
sf1 = pd.read_parquet(DATA_DIR / 'sf1_quarterly_ttm.parquet')
sf1 = sf1[sf1['avail_ym'] >= '2005-01'].copy()

# Load tickers for filtering
tickers_df = pd.read_parquet(DATA_DIR / 'tickers.parquet')
# Common stock only
common_cats = ['Domestic Common Stock', 'Domestic Common Stock Primary Class']
common_tickers = set(tickers_df[tickers_df['category'].isin(common_cats)]['ticker'])

# Sector mapping for ex-financials
fin_tickers = set(tickers_df[tickers_df['sector'] == 'Financial Services']['ticker'])

# Filter sf1
sf1 = sf1[sf1['ticker'].isin(common_tickers)].copy()
print(f"  SF1 after common stock filter: {len(sf1):,}")

# ── Step 3: Factor definitions ─────────────────────────────────────────────
# For each factor: (name, column, ascending=True means low value = D1, ex_fin=True)
FACTORS = [
    ('P/E',          'pe_q',             True,  True),
    ('EBITDA/EV',    'evebitda_q',       False, True),   # high EBITDA/EV = cheap
    ('P/CF (FCF)',   'pfcf_q',           True,  True),
    ('P/S',          'ps_q',             True,  True),
    ('P/B',          'pb_q',             True,  True),
    ('Div Yield',    'dy_q',             False, True),   # high div = D1
    ('Buyback Yield','buyback_yield_q',  False, True),   # high buyback = D1
    ('SH Yield',     'sy_q',             False, True),   # high SY = D1
    ('EPS Growth',   'epsgrowth_q',      False, False),  # high growth = D1, all sectors
    ('Profit Margin','netmargin_q',      False, False),   # high margin = D1
    ('ROE',          'roe_q',            False, False),
]

# Check which columns exist, compute missing ones
if 'epsgrowth_q' not in sf1.columns:
    # Compute EPS growth: (eps_ttm - eps_ttm_4q_ago) / abs(eps_ttm_4q_ago)
    # We need to compute from epsdil TTM
    if 'epsdil' in sf1.columns:
        sf1 = sf1.sort_values(['ticker', 'avail_ym'])
        sf1['epsdil_lag4'] = sf1.groupby('ticker')['epsdil'].shift(4)
        sf1['epsgrowth_q'] = (sf1['epsdil'] - sf1['epsdil_lag4']) / sf1['epsdil_lag4'].abs()
        sf1.loc[sf1['epsdil_lag4'].abs() < 0.01, 'epsgrowth_q'] = np.nan
        print("  Computed epsgrowth_q")

if 'netmargin_q' not in sf1.columns:
    if 'netinc' in sf1.columns and 'revenue' in sf1.columns:
        sf1['netmargin_q'] = sf1['netinc'] / sf1['revenue']
        sf1.loc[sf1['revenue'].abs() < 1e6, 'netmargin_q'] = np.nan
        print("  Computed netmargin_q")

if 'roe_q' not in sf1.columns:
    if 'netinc' in sf1.columns and 'equity' in sf1.columns:
        sf1['roe_q'] = sf1['netinc'] / sf1['equity']
        sf1.loc[sf1['equity'].abs() < 1e6, 'roe_q'] = np.nan
        print("  Computed roe_q")

# Accruals: not in standard TTM, compute if possible
if 'accruals_q' not in sf1.columns:
    # Accruals = (netinc - ncfo) / assets (Sloan accrual ratio)
    if all(c in sf1.columns for c in ['netinc', 'ncfo', 'assets']):
        sf1['accruals_q'] = (sf1['netinc'] - sf1['ncfo']) / sf1['assets']
        sf1.loc[sf1['assets'] < 1e6, 'accruals_q'] = np.nan
        FACTORS.append(('Accruals', 'accruals_q', True, True))  # low accruals = D1
        print("  Computed accruals_q")


# ── Step 4: Forward return calculation ──────────────────────────────────────
def get_fwd_return(ticker, ym_str, months=12):
    """Get forward return from ym_str over N months."""
    prices = price_dict.get(ticker)
    if not prices:
        return np.nan
    p0 = prices.get(ym_str)
    if not p0 or p0 <= 0:
        return np.nan
    # Forward month
    y, m = int(ym_str[:4]), int(ym_str[5:7])
    m += months
    while m > 12:
        m -= 12
        y += 1
    fwd_ym = f"{y:04d}-{m:02d}"
    p1 = prices.get(fwd_ym)
    if not p1 or p1 <= 0:
        return np.nan
    return (p1 / p0) - 1


# ── Step 5: Run decile backtest ─────────────────────────────────────────────
def run_factor_backtest(factor_name, col, ascending, ex_financials, min_mcap):
    """
    For each month from 2005-01 to 2025-03:
    - Filter universe (common stock, mcap > min_mcap, ex-financials if needed)
    - Sort by factor, split into deciles
    - Get 12-month forward return for each stock
    - Average within each decile
    Result: for each decile (1-10), list of annual returns per cohort month.
    Then average across 12 monthly cohorts for each calendar year.
    """
    print(f"  Running {factor_name} (mcap>{min_mcap/1e9:.0f}B, ex_fin={ex_financials})...")

    data = sf1[['ticker', 'avail_ym', col, 'marketcap']].dropna(subset=[col, 'marketcap']).copy()
    data = data[data['marketcap'] >= min_mcap]

    if ex_financials:
        data = data[~data['ticker'].isin(fin_tickers)]

    # Filter to valid factor values
    if ascending and col in ('pe_q', 'ps_q', 'pb_q', 'pfcf_q'):
        # For price ratios - remove negatives (meaningless)
        data = data[data[col] > 0]

    if col == 'evebitda_q':
        # Remove negative EBITDA/EV (negative EBITDA = money-losing)
        data = data[data[col] > 0]

    # Clip extremes
    data = data[(data[col] > data[col].quantile(0.005)) &
                (data[col] < data[col].quantile(0.995))]

    # Get unique months
    months = sorted(data['avail_ym'].unique())
    months = [m for m in months if '2005-01' <= m <= '2025-03']

    # For each month, compute decile returns
    decile_returns = {d: [] for d in range(1, 11)}  # {decile: [(ym, return), ...]}
    universe_returns = []

    for ym in months:
        snap = data[data['avail_ym'] == ym].copy()
        if len(snap) < 50:
            continue

        # Sort and assign deciles
        snap = snap.sort_values(col, ascending=ascending)
        snap['decile'] = pd.qcut(snap[col].rank(method='first'), 10, labels=range(1, 11))

        # Get forward 12m return for each stock
        snap['fwd_ret'] = snap['ticker'].apply(lambda t: get_fwd_return(t, ym))
        snap = snap.dropna(subset=['fwd_ret'])

        # Clip extreme returns (likely data errors)
        snap = snap[snap['fwd_ret'].between(-0.95, 10.0)]

        if len(snap) < 30:
            continue

        # Average return per decile
        for d in range(1, 11):
            dec_data = snap[snap['decile'] == d]
            if len(dec_data) >= 3:
                decile_returns[d].append((ym, dec_data['fwd_ret'].mean()))

        universe_returns.append((ym, snap['fwd_ret'].mean()))

    # Now aggregate by calendar year (average the 12 monthly cohorts)
    # Each cohort starting in month M of year Y matures in month M of year Y+1
    # We assign each cohort to the year it starts

    decile_annual = {d: {} for d in range(1, 11)}  # {decile: {year: avg_return}}
    univ_annual = {}

    years = sorted(set(ym[:4] for ym, _ in universe_returns))

    for yr in years:
        yr_int = int(yr)
        if yr_int > 2025:
            continue
        for d in range(1, 11):
            yr_rets = [r for ym, r in decile_returns[d] if ym[:4] == yr]
            if yr_rets:
                decile_annual[d][yr] = round(np.mean(yr_rets) * 100, 1)

        yr_rets_u = [r for ym, r in universe_returns if ym[:4] == yr]
        if yr_rets_u:
            univ_annual[yr] = round(np.mean(yr_rets_u) * 100, 1)

    # Compute CAGR for each decile
    decile_cagrs = {}
    for d in range(1, 11):
        rets = list(decile_annual[d].values())
        if rets:
            # Geometric mean
            growth = np.prod([1 + r/100 for r in rets]) ** (1/len(rets)) - 1
            decile_cagrs[d] = round(growth * 100, 1)

    # Universe CAGR
    u_rets = list(univ_annual.values())
    if u_rets:
        univ_cagr = round((np.prod([1 + r/100 for r in u_rets]) ** (1/len(u_rets)) - 1) * 100, 1)
    else:
        univ_cagr = 0

    # Win rates
    d1_wins = sum(1 for yr in decile_annual[1] if yr in decile_annual[10] and
                  decile_annual[1][yr] > decile_annual[10][yr])
    total_yrs = sum(1 for yr in decile_annual[1] if yr in decile_annual[10])
    d1_wins_pct = round(d1_wins / total_yrs * 100, 0) if total_yrs else 0

    # Rolling 3yr and 5yr positive spread
    sorted_years = sorted(decile_annual[1].keys())

    def rolling_positive(window):
        count_pos = 0
        count_total = 0
        for i in range(len(sorted_years) - window + 1):
            yrs = sorted_years[i:i+window]
            d1_sum = sum(decile_annual[1].get(y, 0) for y in yrs)
            d10_sum = sum(decile_annual[10].get(y, 0) for y in yrs)
            count_total += 1
            if d1_sum > d10_sum:
                count_pos += 1
        return round(count_pos / count_total * 100, 0) if count_total else 0

    r3 = rolling_positive(3)
    r5 = rolling_positive(5)

    result = {
        'decile_cagrs': decile_cagrs,
        'univ_cagr': univ_cagr,
        'spread': round(decile_cagrs.get(1, 0) - decile_cagrs.get(10, 0), 1),
        'alpha_vs_univ': round(decile_cagrs.get(1, 0) - univ_cagr, 1),
        'd1_wins_pct': d1_wins_pct,
        'r3_pos_pct': r3,
        'r5_pos_pct': r5,
        'decile_annual': {str(d): decile_annual[d] for d in range(1, 11)},
        'univ_annual': univ_annual,
        'd1_annual': decile_annual[1],
        'd10_annual': decile_annual[10],
        'n_years': len(sorted_years),
    }

    print(f"    D1={decile_cagrs.get(1,0):+.1f}%, D10={decile_cagrs.get(10,0):+.1f}%, "
          f"spread={result['spread']:+.1f}%, alpha={result['alpha_vs_univ']:+.1f}%, "
          f"5yr={r5}%")

    return result


# ── Step 6: Run all factors ────────────────────────────────────────────────
print("\n=== Running all factor backtests ===\n")

results = {}

for factor_name, col, ascending, ex_fin in FACTORS:
    if col not in sf1.columns:
        print(f"  SKIP {factor_name} — column {col} not found")
        continue

    for min_mcap, label in [(200e6, '>$200M'), (5e9, '>$5B')]:
        key = f"{factor_name} {label}"
        results[key] = run_factor_backtest(factor_name, col, ascending, ex_fin, min_mcap)

# ── Step 7: Save ───────────────────────────────────────────────────────────
print(f"\nSaving to {OUT}...")
with open(OUT, 'w') as f:
    json.dump(results, f, indent=2)
print(f"  ✓ Saved {len(results)} factor results")
print("\nDone!")
