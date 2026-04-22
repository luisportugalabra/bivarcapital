#!/usr/bin/env python3
"""
Generate full strategy report with equity curve, drawdown,
cash periods, MA overlay, position history, and monthly returns.
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle

print("Loading...")
sep = pd.read_parquet('sep_daily.parquet', columns=['ticker','date','closeadj'])
sf1 = pd.read_parquet('sf1_quarterly_ttm.parquet')
tickers_df = pd.read_parquet('tickers.parquet')
sp500 = pd.read_parquet('sp500_daily.parquet')

cats = ['Domestic Common Stock', 'Domestic Common Stock Primary Class']
vt = tickers_df[tickers_df['category'].isin(cats)]
valid = set(vt['ticker'])
sector_map = vt.set_index('ticker')['sector'].to_dict()
name_map = vt.set_index('ticker')['name'].to_dict()

sep = sep[sep['ticker'].isin(valid)]
sep['date'] = pd.to_datetime(sep['date'])
sep = sep[sep['closeadj'] > 0].dropna(subset=['closeadj'])

daily = sep.pivot_table(index='date', columns='ticker', values='closeadj', aggfunc='last').sort_index()
daily = daily.loc[daily.index >= '2004-01-01']

sf1 = sf1[sf1['ticker'].isin(valid)].copy()
sf1['avail_date'] = pd.to_datetime(sf1['avail_ym'] + '-01')
mc_m = sf1.pivot_table(index='avail_date', columns='ticker', values='marketcap', aggfunc='last')
eb_m = sf1.pivot_table(index='avail_date', columns='ticker', values='ebit', aggfunc='last')
mc_daily = mc_m.reindex(daily.index).ffill()
eb_daily = eb_m.reindex(daily.index).ffill()

sp500['date'] = pd.to_datetime(sp500['date'])
sp500_s = sp500.sort_values('date').set_index('date')['close']

daily_dates = daily.index.to_series()
daily_dates_ym = daily_dates.groupby([daily_dates.dt.year, daily_dates.dt.month]).apply(list).to_dict()

def get_day(year, month, n):
    days = daily_dates_ym.get((year, month), [])
    if not days: return None
    if n == -1: return days[-1]
    idx = n - 1
    return days[idx] if idx < len(days) else None

def next_trading_day(date):
    idx = daily.index.get_loc(date)
    return daily.index[idx + 1] if idx + 1 < len(daily.index) else None

print("Running backtest...")

# Strategy params
TOP_N = 7
MAX_SEC = None  # no sector cap
MIN_MCAP = 10e9
LB_SHORT = 126
LB_LONG = 252
W_SHORT = 0.5
W_LONG = 0.5
MA_PERIOD = 250
SIGNAL_DAY = 18

monthly_rets = []
sp_rets = []
dates = []
positions = []
ma_status = []  # (date, sp_close, ma250, is_above)

for year in range(2005, 2027):
    for month in range(1, 13):
        sig_date = get_day(year, month, SIGNAL_DAY)
        if sig_date is None or sig_date > daily.index[-2]: continue
        buy_date = next_trading_day(sig_date)
        if buy_date is None: continue

        sell_year = year if month < 12 else year + 1
        sell_month = month + 1 if month < 12 else 1
        sig_next = get_day(sell_year, sell_month, SIGNAL_DAY)
        if sig_next is None: continue
        sell_date = next_trading_day(sig_next)
        if sell_date is None: continue

        sp_b = sp500_s.loc[:buy_date]
        sp_s = sp500_s.loc[:sell_date]
        sp_ret = (sp_s.iloc[-1] / sp_b.iloc[-1] - 1) if len(sp_b) > 0 and len(sp_s) > 0 else 0
        sp_rets.append(sp_ret)
        dates.append(buy_date)

        # MA check
        sp_hist = sp500_s.loc[:sig_date].tail(MA_PERIOD + 1)
        sp_close = sp_hist.iloc[-1]
        ma_val = sp_hist.iloc[-MA_PERIOD:].mean() if len(sp_hist) >= MA_PERIOD else sp_close
        is_above = sp_close >= ma_val

        ma_status.append({
            'date': sig_date, 'buy_date': buy_date,
            'sp_close': round(sp_close, 1), 'ma250': round(ma_val, 1),
            'above': is_above, 'pct_diff': round((sp_close/ma_val - 1)*100, 1)
        })

        if not is_above:
            monthly_rets.append(0.0)
            positions.append({'date': buy_date, 'status': 'CASH', 'stocks': [], 'return': 0.0})
            continue

        idx = daily.index.get_loc(sig_date)
        if idx < max(LB_SHORT, LB_LONG):
            monthly_rets.append(0.0)
            positions.append({'date': buy_date, 'status': 'WAIT', 'stocks': [], 'return': 0.0})
            continue

        p_sig = daily.iloc[idx]
        mom = W_SHORT * (p_sig / daily.iloc[idx - LB_SHORT] - 1) + \
              W_LONG * (p_sig / daily.iloc[idx - LB_LONG] - 1)

        mc_now = mc_daily.iloc[idx]
        eb_now = eb_daily.iloc[idx]
        mask = (mc_now >= MIN_MCAP) & (p_sig > 0) & mom.notna() & (eb_now > 0)
        eligible = mom[mask].dropna()

        if len(eligible) == 0:
            monthly_rets.append(0.0)
            positions.append({'date': buy_date, 'status': 'EMPTY', 'stocks': [], 'return': 0.0})
            continue

        selected = eligible.nlargest(TOP_N).index.tolist()

        if not selected:
            monthly_rets.append(0.0)
            positions.append({'date': buy_date, 'status': 'EMPTY', 'stocks': [], 'return': 0.0})
            continue

        buy_prices = daily.loc[buy_date, selected]
        sell_prices = daily.loc[sell_date, selected]
        common = buy_prices.dropna().index.intersection(sell_prices.dropna().index)
        if len(common) == 0:
            monthly_rets.append(0.0)
            positions.append({'date': buy_date, 'status': 'NO_PRICE', 'stocks': selected, 'return': 0.0})
            continue

        ret = (sell_prices[common] / buy_prices[common] - 1).mean()
        monthly_rets.append(ret)

        stock_details = []
        for t in selected:
            stock_details.append({
                'ticker': t,
                'name': name_map.get(t, '?')[:20],
                'sector': sector_map.get(t, '?')[:12],
                'mom': round(mom.get(t, 0) * 100, 1),
                'ret': round((sell_prices.get(t, 0) / buy_prices.get(t, 1) - 1) * 100, 1) if t in common else None,
            })
        positions.append({'date': buy_date, 'status': 'INVESTED', 'stocks': stock_details, 'return': round(ret*100, 1)})

# Stats
rets = np.array(monthly_rets)
sp = np.array(sp_rets[:len(rets)])
cum = np.cumprod(1 + rets)
sp_cum = np.cumprod(1 + sp)
n = len(rets)
years = n / 12
cagr = cum[-1] ** (1/years) - 1
sp_cagr = sp_cum[-1] ** (1/years) - 1
vol = np.std(rets, ddof=1) * np.sqrt(12)
rf = 0.03/12
sharpe = (np.mean(rets) - rf) / np.std(rets, ddof=1) * np.sqrt(12)
ds = rets[rets < rf] - rf
ds_vol = np.std(ds, ddof=1) * np.sqrt(12) if len(ds) > 1 else vol
sortino = (np.mean(rets) - rf) / (ds_vol / np.sqrt(12)) * np.sqrt(12)
peak = np.maximum.accumulate(cum)
maxdd = ((cum - peak) / peak).min()

print(f"\nStrategy: Signal D{SIGNAL_DAY} → Buy D{SIGNAL_DAY}+1 | 6+12eq | >${MIN_MCAP/1e9:.0f}B | t{TOP_N} | MA{MA_PERIOD} | EBIT | no sector cap")
print(f"CAGR: {cagr*100:+.1f}%  Alpha: {(cagr-sp_cagr)*100:+.1f}%  Sharpe: {sharpe:.2f}  Sortino: {sortino:.2f}")
print(f"MaxDD: {maxdd*100:.1f}%  Vol: {vol*100:.1f}%  Months: {n}")

# ═══════════════════════════════════════════════════════════════
# CHART 1: S&P 500 with MA250 + Cash/Invested periods
# ═══════════════════════════════════════════════════════════════
fig, axes = plt.subplots(4, 1, figsize=(16, 18), height_ratios=[2, 2.5, 1, 1.5],
                          gridspec_kw={'hspace': 0.3})
fig.patch.set_facecolor('#fafbfc')
fig.suptitle(f'Momentum Strategy Report — Signal D{SIGNAL_DAY}, Buy D{SIGNAL_DAY+1}  |  6+12eq  |  >${MIN_MCAP/1e9:.0f}B  |  Top {TOP_N}  |  MA{MA_PERIOD}  |  EBIT>0  |  no sector cap',
             fontsize=14, fontweight='bold', color='#1a2332', y=0.98)

# Panel 1: S&P 500 + MA250 + Cash/Invested shading
ax = axes[0]
sp_plot = sp500_s.loc['2005-01-01':]
ax.plot(sp_plot.index, sp_plot.values, color='#1a2332', linewidth=1, label='S&P 500')

# MA250 line
ma250_series = sp_plot.rolling(250).mean()
ax.plot(ma250_series.index, ma250_series.values, color='#e67e22', linewidth=1.2, label=f'MA{MA_PERIOD}', alpha=0.8)

# Shade cash periods
for ms in ma_status:
    if not ms['above']:
        d = ms['buy_date']
        ax.axvspan(d, d + pd.Timedelta(days=32), color='#c0392b', alpha=0.08)

# Add small dots for signal dates
for ms in ma_status:
    color = '#27ae60' if ms['above'] else '#c0392b'
    ax.plot(ms['date'], ms['sp_close'], 'o', color=color, markersize=2.5, alpha=0.6)

ax.set_ylabel('S&P 500', fontsize=10)
ax.set_title('S&P 500 vs MA250 — Green dots = Invested, Red dots/shading = Cash', fontsize=11, fontweight='bold', color='#1a2332', pad=8)
ax.legend(fontsize=8, loc='upper left')
ax.grid(True, alpha=0.3); ax.set_facecolor('#fafbfc')
ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)

# Panel 2: Equity curve
ax = axes[1]
ax.plot(dates[:len(cum)], cum, color='#c0392b', linewidth=2, label=f'Strategy  CAGR {cagr*100:+.1f}%  Sharpe {sharpe:.2f}')
ax.plot(dates[:len(sp_cum)], sp_cum, color='#95a5a6', linewidth=1.2, linestyle='--',
        label=f'S&P 500  CAGR {sp_cagr*100:+.1f}%')
ax.set_yscale('log')
ax.set_ylabel('Growth of $1 (log)', fontsize=10)
ax.set_title('Equity Curve', fontsize=11, fontweight='bold', color='#1a2332', pad=8)
ax.legend(fontsize=9, loc='upper left')
ax.grid(True, alpha=0.3); ax.set_facecolor('#fafbfc')
ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x:.0f}' if x >= 1 else f'${x:.2f}'))

# Shade cash periods
for p in positions:
    if p['status'] == 'CASH':
        ax.axvspan(p['date'], p['date'] + pd.Timedelta(days=32), color='#c0392b', alpha=0.05)

# Panel 3: Drawdown
ax = axes[2]
dd = (cum - peak) / peak * 100
ax.fill_between(dates[:len(dd)], dd, 0, color='#c0392b', alpha=0.3)
ax.plot(dates[:len(dd)], dd, color='#c0392b', linewidth=1)
ax.set_ylabel('Drawdown (%)', fontsize=10)
ax.set_title(f'Drawdown (Max: {maxdd*100:.1f}%)', fontsize=11, fontweight='bold', color='#1a2332', pad=8)
ax.grid(True, alpha=0.3); ax.set_facecolor('#fafbfc')
ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
ax.set_ylim(min(dd) * 1.2, 5)

# Panel 4: Monthly returns bar chart
ax = axes[3]
colors_bar = ['#27ae60' if r >= 0 else '#c0392b' for r in rets]
ax.bar(dates[:len(rets)], rets * 100, color=colors_bar, width=25, alpha=0.7)
ax.axhline(y=0, color='#1a2332', linewidth=0.5)
ax.set_ylabel('Monthly Return (%)', fontsize=10)
ax.set_title('Monthly Returns', fontsize=11, fontweight='bold', color='#1a2332', pad=8)
ax.grid(True, alpha=0.3); ax.set_facecolor('#fafbfc')
ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)

plt.savefig('/Users/luisabrantes/Desktop/momentum_full_report.png', dpi=180,
            bbox_inches='tight', facecolor='#fafbfc')
print("\nChart saved: ~/Desktop/momentum_full_report.png")

# ═══════════════════════════════════════════════════════════════
# TEXT REPORT: MA status + positions month by month
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print(f"MA STATUS & POSITIONS — Month by Month")
print(f"{'='*120}")
print(f"{'Signal Date':>12} {'S&P':>8} {'MA250':>8} {'Diff':>7} {'Status':>8} {'Return':>7}  Holdings")
print(f"{'-'*120}")

for i, (ms, pos) in enumerate(zip(ma_status, positions)):
    sp_str = f"{ms['sp_close']:,.0f}"
    ma_str = f"{ms['ma250']:,.0f}"
    diff_str = f"{ms['pct_diff']:+.1f}%"
    status = 'CASH' if not ms['above'] else 'INVEST'
    ret_str = f"{pos['return']:+.1f}%" if pos['status'] == 'INVESTED' else '0.0%'

    if pos['status'] == 'INVESTED':
        stocks_str = ', '.join([f"{s['ticker']}({s['ret']:+.1f}%)" if s['ret'] is not None else s['ticker']
                                for s in pos['stocks']])
    elif pos['status'] == 'CASH':
        stocks_str = '— cash —'
    else:
        stocks_str = pos['status']

    print(f"  {ms['date'].strftime('%Y-%m-%d'):>12} {sp_str:>8} {ma_str:>8} {diff_str:>7} {status:>8} {ret_str:>7}  {stocks_str}")

# Summary stats
print(f"\n{'='*120}")
print(f"SUMMARY STATS")
print(f"{'='*120}")
cash_months = sum(1 for p in positions if p['status'] == 'CASH')
invested_months = sum(1 for p in positions if p['status'] == 'INVESTED')
print(f"  Total months: {n}")
print(f"  Invested: {invested_months} ({invested_months/n*100:.0f}%)")
print(f"  Cash: {cash_months} ({cash_months/n*100:.0f}%)")
print(f"  CAGR: {cagr*100:+.1f}%")
print(f"  Alpha vs S&P: {(cagr-sp_cagr)*100:+.1f}%")
print(f"  Sharpe: {sharpe:.2f}")
print(f"  Sortino: {sortino:.2f}")
print(f"  Max Drawdown: {maxdd*100:.1f}%")
print(f"  Volatility: {vol*100:.1f}%")
print(f"  Win Rate: {np.mean(rets>0)*100:.0f}%")
print(f"  Best Month: {max(rets)*100:+.1f}%")
print(f"  Worst Month: {min(rets)*100:+.1f}%")
print(f"  $10,000 → ${10000*cum[-1]:,.0f}")
print(f"  S&P $10,000 → ${10000*sp_cum[-1]:,.0f}")

# Annual returns
print(f"\n{'='*120}")
print(f"ANNUAL RETURNS")
print(f"{'='*120}")
print(f"  {'Year':>6} {'Strategy':>10} {'S&P':>10} {'Alpha':>10}")
for yr in range(2005, 2027):
    yr_mask = [d.year == yr for d in dates[:len(rets)]]
    if not any(yr_mask):
        continue
    yr_rets = rets[yr_mask]
    yr_sp = sp[yr_mask]
    yr_strat = (np.prod(1 + yr_rets) - 1) * 100
    yr_sp_ret = (np.prod(1 + yr_sp) - 1) * 100
    print(f"  {yr:>6} {yr_strat:>+9.1f}% {yr_sp_ret:>+9.1f}% {yr_strat-yr_sp_ret:>+9.1f}%")

print("\nDone.")
