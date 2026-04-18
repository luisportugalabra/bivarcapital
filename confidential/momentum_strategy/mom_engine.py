"""
Vectorized momentum backtest engine.
Usage: from mom_engine import run_momentum, build_data; data = build_data(); run_momentum(data, ...)
"""

import pandas as pd
import numpy as np
from functools import lru_cache

def build_data():
    """Load and prepare all data. Call once, pass to run_momentum."""
    print("Loading data...")
    sep = pd.read_parquet('sep_daily.parquet', columns=['ticker','date','closeadj'])
    sf1 = pd.read_parquet('sf1_quarterly_ttm.parquet')
    tickers = pd.read_parquet('tickers.parquet')
    sp500 = pd.read_parquet('sp500_daily.parquet')

    # Filter common stock
    cats = ['Domestic Common Stock', 'Domestic Common Stock Primary Class']
    valid = set(tickers[tickers['category'].isin(cats)]['ticker'])
    sep = sep[sep['ticker'].isin(valid)]

    # EOM price matrix
    sep['date'] = pd.to_datetime(sep['date'])
    sep = sep[sep['closeadj'] > 0].dropna(subset=['closeadj'])
    sep['ym'] = sep['date'].dt.to_period('M')
    eom = sep.sort_values('date').groupby(['ticker','ym']).last().reset_index()
    pm = eom.pivot(index='ym', columns='ticker', values='closeadj')
    pm = pm.sort_index()
    pm = pm.loc[pm.index >= pd.Period('2004-01','M')]
    print(f"  Price matrix: {pm.shape}")

    # Fundamentals pivots
    sf1 = sf1[sf1['ticker'].isin(valid)].copy()
    mc = sf1.pivot_table(index='avail_ym', columns='ticker', values='marketcap', aggfunc='last')
    mc.index = pd.PeriodIndex(mc.index, freq='M')
    mc = mc.sort_index().reindex(pm.index).ffill(limit=4)

    eb = sf1.pivot_table(index='avail_ym', columns='ticker', values='ebit', aggfunc='last')
    eb.index = pd.PeriodIndex(eb.index, freq='M')
    eb = eb.sort_index().reindex(pm.index).ffill(limit=4)

    # Sector mapping
    sector_map = tickers.set_index('ticker')['sector'].to_dict()

    # S&P 500
    sp500['date'] = pd.to_datetime(sp500['date'])
    sp500 = sp500.sort_values('date').set_index('date')['close']

    print("  Data ready.")
    return {
        'pm': pm, 'mc': mc, 'eb': eb,
        'sp500': sp500, 'sector_map': sector_map,
    }


def _check_ma(sp500, month, ma_period):
    """Check if S&P 500 is above MA at end of month."""
    end_date = month.to_timestamp(how='end')
    hist = sp500.loc[:end_date].tail(ma_period + 1)
    if len(hist) < ma_period:
        return True
    return hist.iloc[-1] >= hist.iloc[-ma_period:].mean()


def run_momentum(data, lookback=6, skip=0, top_n=20, min_mcap=5e9,
                 ma_period=200, use_ebit=True, cash_rate=0.0,
                 max_per_sector=None, dual_mom=False,
                 hold_months=1, composite_weights=None,
                 start='2005-01', end='2026-03'):
    """
    Run momentum backtest.

    composite_weights: dict like {6: 0.5, 12: 0.5} to blend multiple lookbacks.
                       If set, 'lookback' is ignored.
    dual_mom: if True, only buy if stock mom > 0 AND stock mom > S&P mom.
    max_per_sector: int, max stocks per sector.
    hold_months: rebalance every N months (1=monthly, 2=bimonthly, 3=quarterly).
    """
    pm = data['pm']
    mc = data['mc']
    eb = data['eb']
    sp500 = data['sp500']
    sector_map = data['sector_map']

    months = pm.index[(pm.index >= pd.Period(start,'M')) & (pm.index <= pd.Period(end,'M'))]

    monthly_rets = []
    dates = []
    sp500_rets = []
    last_rebal_month = None

    # For hold_months > 1, we need to track current holdings
    current_holdings = None

    for i, m in enumerate(months):
        # Forward return month
        m_idx = pm.index.get_loc(m)
        if m_idx + 1 >= len(pm.index):
            break
        next_m = pm.index[m_idx + 1]

        # S&P return
        m_end = m.to_timestamp(how='end')
        next_end = next_m.to_timestamp(how='end')
        sp_slice = sp500.loc[:next_end]
        sp_m = sp500.loc[:m_end]
        if len(sp_m) > 0 and len(sp_slice) > 0:
            sp_ret = sp_slice.iloc[-1] / sp_m.iloc[-1] - 1
        else:
            sp_ret = 0.0
        sp500_rets.append(sp_ret)
        dates.append(m)

        # MA filter
        if ma_period and not _check_ma(sp500, m, ma_period):
            monthly_rets.append(cash_rate / 12)
            current_holdings = None
            last_rebal_month = None
            continue

        # Check if we need to rebalance
        need_rebal = True
        if hold_months > 1 and last_rebal_month is not None:
            months_since = (m.year - last_rebal_month.year) * 12 + (m.month - last_rebal_month.month)
            if months_since < hold_months and current_holdings is not None:
                need_rebal = False

        if need_rebal:
            # Compute momentum
            if composite_weights:
                mom = pd.Series(0.0, index=pm.columns)
                for lb, wt in composite_weights.items():
                    lb_total = lb + skip
                    if m_idx - lb_total < 0:
                        continue
                    start_m = pm.index[m_idx - lb_total]
                    end_m = pm.index[m_idx - skip] if skip > 0 else m
                    m_ret = pm.loc[end_m] / pm.loc[start_m] - 1
                    mom = mom.add(m_ret * wt, fill_value=0)
            else:
                lb_total = lookback + skip
                if m_idx - lb_total < 0:
                    monthly_rets.append(cash_rate / 12)
                    continue
                start_m = pm.index[m_idx - lb_total]
                end_m = pm.index[m_idx - skip] if skip > 0 else m
                mom = pm.loc[end_m] / pm.loc[start_m] - 1

            # Filters
            mask = (mc.loc[m] >= min_mcap) & (pm.loc[m] > 0) & mom.notna()
            if use_ebit:
                mask = mask & (eb.loc[m] > 0)

            eligible = mom[mask]

            # Dual momentum filter
            if dual_mom and len(eligible) > 0:
                # Stock must have positive absolute momentum
                eligible = eligible[eligible > 0]
                # Stock must beat S&P momentum
                if not composite_weights:
                    sp_mom_start = sp500.loc[:pm.index[m_idx - lb_total].to_timestamp(how='end')]
                    sp_mom_end = sp500.loc[:m.to_timestamp(how='end')]
                    if len(sp_mom_start) > 0 and len(sp_mom_end) > 0:
                        sp_mom = sp_mom_end.iloc[-1] / sp_mom_start.iloc[-1] - 1
                        eligible = eligible[eligible > sp_mom]

            if len(eligible) == 0:
                monthly_rets.append(cash_rate / 12)
                continue

            # Sort by momentum
            ranked = eligible.nlargest(top_n * 3 if max_per_sector else top_n)

            if max_per_sector:
                # Apply sector limits
                selected = []
                sector_counts = {}
                for ticker in ranked.index:
                    sec = sector_map.get(ticker, 'Unknown')
                    cnt = sector_counts.get(sec, 0)
                    if cnt < max_per_sector:
                        selected.append(ticker)
                        sector_counts[sec] = cnt + 1
                    if len(selected) >= top_n:
                        break
                current_holdings = selected
            else:
                current_holdings = ranked.index[:top_n].tolist()

            last_rebal_month = m

        # Compute return from current holdings
        if current_holdings:
            fwd = pm.loc[next_m, current_holdings] / pm.loc[m, current_holdings] - 1
            fwd = fwd.dropna()
            if len(fwd) > 0:
                monthly_rets.append(fwd.mean())
            else:
                monthly_rets.append(cash_rate / 12)
        else:
            monthly_rets.append(cash_rate / 12)

    return _calc_stats(monthly_rets, sp500_rets, dates)


def _calc_stats(monthly_rets, sp500_rets, dates):
    """Calculate strategy statistics."""
    rets = np.array(monthly_rets)
    sp_rets = np.array(sp500_rets[:len(rets)])
    n = len(rets)
    if n == 0:
        return {}

    # Cumulative
    cum = np.cumprod(1 + rets)
    sp_cum = np.cumprod(1 + sp_rets)

    # CAGR
    years = n / 12
    cagr = cum[-1] ** (1/years) - 1
    sp_cagr = sp_cum[-1] ** (1/years) - 1

    # Volatility
    vol = np.std(rets, ddof=1) * np.sqrt(12)

    # Sharpe (rf=3%)
    rf_monthly = 0.03 / 12
    sharpe = (np.mean(rets) - rf_monthly) / np.std(rets, ddof=1) * np.sqrt(12) if np.std(rets) > 0 else 0

    # Sortino
    downside = rets[rets < rf_monthly] - rf_monthly
    downside_vol = np.std(downside, ddof=1) * np.sqrt(12) if len(downside) > 1 else vol
    sortino = (np.mean(rets) - rf_monthly) / (downside_vol / np.sqrt(12)) * np.sqrt(12) if downside_vol > 0 else 0

    # Max drawdown
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    maxdd = dd.min()

    # Sub-period Sharpe (H1: first half, H2: second half)
    mid = n // 2
    h1_rets = rets[:mid]
    h2_rets = rets[mid:]
    h1_sharpe = (np.mean(h1_rets) - rf_monthly) / np.std(h1_rets, ddof=1) * np.sqrt(12) if len(h1_rets) > 12 and np.std(h1_rets) > 0 else 0
    h2_sharpe = (np.mean(h2_rets) - rf_monthly) / np.std(h2_rets, ddof=1) * np.sqrt(12) if len(h2_rets) > 12 and np.std(h2_rets) > 0 else 0

    # Win rate
    win_rate = np.mean(rets > 0)

    # Monthly rets for further analysis
    return {
        'cagr': round(cagr * 100, 1),
        'alpha': round((cagr - sp_cagr) * 100, 1),
        'sharpe': round(sharpe, 2),
        'sortino': round(sortino, 2),
        'maxdd': round(maxdd * 100, 1),
        'vol': round(vol * 100, 1),
        'h1_sharpe': round(h1_sharpe, 2),
        'h2_sharpe': round(h2_sharpe, 2),
        'win_rate': round(win_rate * 100, 1),
        'n_months': n,
        'sp_cagr': round(sp_cagr * 100, 1),
    }


def fmt(r):
    """Format result dict as one-line string."""
    if not r:
        return "NO DATA"
    return (f"CAGR {r['cagr']:+.1f}%  Alpha {r['alpha']:+.1f}%  "
            f"Sharpe {r['sharpe']:.2f}  Sortino {r['sortino']:.2f}  "
            f"MaxDD {r['maxdd']:.1f}%  Vol {r['vol']:.1f}%  "
            f"H1 {r['h1_sharpe']:.2f}  H2 {r['h2_sharpe']:.2f}  "
            f"Win {r['win_rate']:.0f}%")
