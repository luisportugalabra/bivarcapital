#!/usr/bin/env python3
"""
Generate full HTML report for combined portfolio:
50% BivarOptimalMomentum (with GLD hedge) + 50% BTC Systematic
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.dates as mdates
from matplotlib.patches import Patch
import io, base64
import yfinance as yf

# ── Chart helpers ──
def fig_to_b64(fig, dpi=180):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', facecolor='#060608', edgecolor='none', pad_inches=0.2)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

def style_ax(ax, title=''):
    ax.set_facecolor('#060608')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#1a1a22')
    ax.spines['bottom'].set_color('#1a1a22')
    ax.tick_params(colors='#5a5a68', labelsize=8)
    ax.grid(True, color='#1a1a22', linewidth=0.5, alpha=0.7)
    if title:
        ax.set_title(title, color='#e8e8ec', fontsize=11, fontweight='bold', pad=10)

# ── Load data ──
print("Loading all data...")
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
mc_daily = sf1.pivot_table(index='avail_date', columns='ticker', values='marketcap', aggfunc='last').reindex(daily.index).ffill()
eb_daily = sf1.pivot_table(index='avail_date', columns='ticker', values='ebit', aggfunc='last').reindex(daily.index).ffill()

sp500['date'] = pd.to_datetime(sp500['date'])
sp500_s = sp500.sort_values('date').set_index('date')['close']

gld = yf.download('GLD', start='2004-01-01', end='2026-04-18', progress=False)
gld_close = gld['Close'].squeeze()
btc = yf.download('BTC-USD', start='2014-01-01', end='2026-04-18', progress=False)
btc_close = btc['Close'].squeeze()

daily_dates = daily.index.to_series()
daily_dates_ym = daily_dates.groupby([daily_dates.dt.year, daily_dates.dt.month]).apply(list).to_dict()

def get_day(y, m, n):
    days = daily_dates_ym.get((y, m), [])
    if not days: return None
    if n == -1: return days[-1]
    idx = n - 1
    return days[idx] if idx < len(days) else None

def next_td(date):
    idx = daily.index.get_loc(date)
    return daily.index[idx + 1] if idx + 1 < len(daily.index) else None

print("Computing strategies...")

# ── Strategy 1: Momentum + GLD ──
mom_data = []
for year in range(2015, 2027):
    for month in range(1, 13):
        sig = get_day(year, month, 18)
        if sig is None or sig > daily.index[-2]: continue
        buy = next_td(sig)
        if buy is None: continue
        sy = year if month < 12 else year + 1
        sm = month + 1 if month < 12 else 1
        sig_n = get_day(sy, sm, 18)
        if sig_n is None: continue
        sell = next_td(sig_n)
        if sell is None: continue

        idx = daily.index.get_loc(sig)
        sp_hist = sp500_s.loc[:sig].tail(251)
        sp_val = sp_hist.iloc[-1]
        ma250 = sp_hist.iloc[-250:].mean() if len(sp_hist) >= 250 else sp_val
        is_bear = sp_val < ma250

        sp_b = sp500_s.loc[:buy]; sp_s = sp500_s.loc[:sell]
        sp_ret = (sp_s.iloc[-1] / sp_b.iloc[-1] - 1) if len(sp_b) > 0 and len(sp_s) > 0 else 0

        if is_bear:
            gb = gld_close.loc[:buy]; gs = gld_close.loc[:sell]
            ret = (gs.iloc[-1]/gb.iloc[-1]-1) if len(gb)>0 and len(gs)>0 else 0
            mom_data.append(dict(date=buy, ret=ret, sp_ret=sp_ret, mode='GLD', stocks=[]))
            continue

        if idx < 252:
            mom_data.append(dict(date=buy, ret=0, sp_ret=sp_ret, mode='WAIT', stocks=[])); continue

        p_sig = daily.iloc[idx]
        mom = 0.5*(p_sig/daily.iloc[idx-126]-1) + 0.5*(p_sig/daily.iloc[idx-252]-1)
        mc_now = mc_daily.iloc[idx]; eb_now = eb_daily.iloc[idx]
        mask = (mc_now >= 10e9) & (p_sig > 0) & mom.notna() & (eb_now > 0)
        eligible = mom[mask].dropna()

        if len(eligible) == 0:
            mom_data.append(dict(date=buy, ret=0, sp_ret=sp_ret, mode='EMPTY', stocks=[])); continue

        ranked = eligible.nlargest(21)
        selected = []; sec_counts = {}
        for t in ranked.index:
            sec = sector_map.get(t, 'Unknown')
            if sec_counts.get(sec, 0) < 3:
                selected.append(t); sec_counts[sec] = sec_counts.get(sec, 0) + 1
            if len(selected) >= 7: break

        bp = daily.loc[buy, selected]; sp_p = daily.loc[sell, selected]
        common = bp.dropna().index.intersection(sp_p.dropna().index)
        ret = (sp_p[common]/bp[common]-1).mean() if len(common) > 0 else 0
        stocks_info = [(t, name_map.get(t,'?')[:20], round(mom.get(t,0)*100,1)) for t in selected]
        mom_data.append(dict(date=buy, ret=ret, sp_ret=sp_ret, mode='MOM', stocks=stocks_info))

# ── Strategy 2: BTC Systematic ──
rsi_delta = btc_close.diff()
gain = rsi_delta.where(rsi_delta > 0, 0).rolling(14).mean()
loss = (-rsi_delta.where(rsi_delta < 0, 0)).rolling(14).mean()
rsi = 100 - (100 / (1 + gain / loss))
ma155 = btc_close.rolling(155).mean()
vol20 = btc_close.pct_change().rolling(20).std() * np.sqrt(365) * 100
btc_signal = (rsi > 54) & (btc_close > ma155) & (vol20 < 100)
btc_daily_ret = btc_close.pct_change()
btc_strat_ret = btc_daily_ret.where(btc_signal.shift(1), 0)

btc_data = []
for year in range(2015, 2027):
    for month in range(1, 13):
        key = f'{year}-{month:02d}'
        start = pd.Timestamp(year, month, 1)
        end = pd.Timestamp(year + (1 if month == 12 else 0), (month % 12) + 1, 1)
        chunk = btc_strat_ret.loc[start:end]
        sig_chunk = btc_signal.loc[start:end]
        if len(chunk) > 0:
            ret = (1 + chunk).prod() - 1
            invested_pct = sig_chunk.mean() * 100
            btc_data.append(dict(ym=key, ret=ret, invested_pct=invested_pct))

# ── Align and combine ──
mom_dates = [d['date'] for d in mom_data]
mom_rets = np.array([d['ret'] for d in mom_data])
mom_modes = [d['mode'] for d in mom_data]
sp_rets = np.array([d['sp_ret'] for d in mom_data])

btc_dict = {d['ym']: d['ret'] for d in btc_data}
btc_rets_aligned = []
for d in mom_data:
    ym = f"{d['date'].year}-{d['date'].month:02d}"
    btc_rets_aligned.append(btc_dict.get(ym, 0))
btc_rets_aligned = np.array(btc_rets_aligned)

combined = 0.5 * mom_rets + 0.5 * btc_rets_aligned

cum_mom = np.cumprod(1 + mom_rets)
cum_btc = np.cumprod(1 + btc_rets_aligned)
cum_comb = np.cumprod(1 + combined)
cum_sp = np.cumprod(1 + sp_rets)

n = len(combined)
years = n / 12

def stats(r):
    cum = np.cumprod(1 + r)
    yrs = len(r)/12
    cagr = cum[-1]**(1/yrs)-1
    vol = np.std(r,ddof=1)*np.sqrt(12)
    rf = 0.03/12
    sharpe = (np.mean(r)-rf)/np.std(r,ddof=1)*np.sqrt(12) if np.std(r)>0 else 0
    pk = np.maximum.accumulate(cum)
    maxdd = ((cum-pk)/pk).min()
    return round(cagr*100,1), round(sharpe,2), round(maxdd*100,1), round(vol*100,1)

s_mom = stats(mom_rets)
s_btc = stats(btc_rets_aligned)
s_comb = stats(combined)
s_sp = stats(sp_rets)

print(f"Mom:  CAGR {s_mom[0]:+.1f}%  Sharpe {s_mom[1]:.2f}  MaxDD {s_mom[2]:.1f}%")
print(f"BTC:  CAGR {s_btc[0]:+.1f}%  Sharpe {s_btc[1]:.2f}  MaxDD {s_btc[2]:.1f}%")
print(f"Comb: CAGR {s_comb[0]:+.1f}%  Sharpe {s_comb[1]:.2f}  MaxDD {s_comb[2]:.1f}%")

# ── CHART 1: Equity Curves ──
print("Generating charts...")
fig, ax = plt.subplots(figsize=(14, 5), facecolor='#060608')
style_ax(ax, 'Portfolio Equity Curves (2015–2026)')
ax.plot(mom_dates, cum_mom, color='#c4a265', linewidth=1.8, label=f'Momentum+GLD  CAGR {s_mom[0]:+.1f}%  Sharpe {s_mom[1]:.2f}')
ax.plot(mom_dates, cum_btc, color='#f7931a', linewidth=1.8, label=f'BTC Systematic  CAGR {s_btc[0]:+.1f}%  Sharpe {s_btc[1]:.2f}')
ax.plot(mom_dates, cum_comb, color='#4ade80', linewidth=2.2, label=f'Combined 50/50  CAGR {s_comb[0]:+.1f}%  Sharpe {s_comb[1]:.2f}')
ax.plot(mom_dates, cum_sp, color='#5a5a68', linewidth=1, linestyle='--', label=f'S&P 500  CAGR {s_sp[0]:+.1f}%', alpha=0.7)
ax.set_yscale('log')
ax.set_ylabel('Growth of $1', color='#5a5a68', fontsize=9)
ax.legend(fontsize=7.5, loc='upper left', facecolor='#0c0c10', edgecolor='#1a1a22', labelcolor='#e8e8ec')
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x:.0f}' if x >= 1 else f'${x:.2f}'))
chart1 = fig_to_b64(fig)

# ── CHART 2: Drawdown ──
fig, ax = plt.subplots(figsize=(14, 3), facecolor='#060608')
style_ax(ax, 'Drawdown')
for rets_arr, color, label in [(mom_rets, '#c4a265', 'Momentum'), (btc_rets_aligned, '#f7931a', 'BTC'), (combined, '#4ade80', 'Combined')]:
    cum = np.cumprod(1 + rets_arr)
    pk = np.maximum.accumulate(cum)
    dd = (cum - pk) / pk * 100
    ax.fill_between(mom_dates[:len(dd)], dd, 0, color=color, alpha=0.15)
    ax.plot(mom_dates[:len(dd)], dd, color=color, linewidth=1, alpha=0.8, label=label)
ax.set_ylabel('Drawdown (%)', color='#5a5a68', fontsize=9)
ax.set_ylim(-40, 5)
ax.legend(fontsize=7, loc='lower left', facecolor='#0c0c10', edgecolor='#1a1a22', labelcolor='#e8e8ec')
chart2 = fig_to_b64(fig)

# ── CHART 3: Regime map (when in cash/gld/mom/btc) ──
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 3), facecolor='#060608', gridspec_kw={'hspace': 0.4})
style_ax(ax1, 'Momentum: Mode per Month')
mode_colors = {'MOM': '#4ade80', 'GLD': '#c4a265', 'CASH': '#5a5a68', 'WAIT': '#1a1a22', 'EMPTY': '#f87171'}
for i, (d, mode) in enumerate(zip(mom_dates, mom_modes)):
    ax1.bar(d, 1, width=28, color=mode_colors.get(mode, '#5a5a68'), alpha=0.8)
ax1.set_yticks([])
patches = [Patch(facecolor=c, label=l) for l, c in [('Momentum','#4ade80'),('GLD','#c4a265'),('Cash','#5a5a68')]]
ax1.legend(handles=patches, fontsize=7, loc='upper right', facecolor='#0c0c10', edgecolor='#1a1a22', labelcolor='#e8e8ec')

style_ax(ax2, 'BTC: Invested vs Cash')
for bd in btc_data:
    y, m = int(bd['ym'][:4]), int(bd['ym'][5:])
    d = pd.Timestamp(y, m, 15)
    if d >= mom_dates[0]:
        color = '#f7931a' if bd['invested_pct'] > 50 else '#5a5a68'
        ax2.bar(d, 1, width=28, color=color, alpha=0.8)
ax2.set_yticks([])
patches2 = [Patch(facecolor='#f7931a', label='BTC Invested'), Patch(facecolor='#5a5a68', label='Cash')]
ax2.legend(handles=patches2, fontsize=7, loc='upper right', facecolor='#0c0c10', edgecolor='#1a1a22', labelcolor='#e8e8ec')
chart3 = fig_to_b64(fig)

# ── CHART 4: Monthly returns ──
fig, ax = plt.subplots(figsize=(14, 3), facecolor='#060608')
style_ax(ax, 'Combined Portfolio — Monthly Returns')
colors_bar = ['#4ade80' if r >= 0 else '#f87171' for r in combined]
ax.bar(mom_dates, combined * 100, width=25, color=colors_bar, alpha=0.7)
ax.axhline(y=0, color='#5a5a68', linewidth=0.5)
ax.set_ylabel('Return (%)', color='#5a5a68', fontsize=9)
chart4 = fig_to_b64(fig)

# ── CHART 5: Annual returns ──
annual = {}
for d, r_m, r_b, r_s in zip(mom_dates, mom_rets, btc_rets_aligned, sp_rets):
    yr = d.year
    if yr not in annual:
        annual[yr] = {'mom':[], 'btc':[], 'comb':[], 'sp':[]}
    annual[yr]['mom'].append(r_m)
    annual[yr]['btc'].append(r_b)
    annual[yr]['comb'].append(0.5*r_m + 0.5*r_b)
    annual[yr]['sp'].append(r_s)

fig, ax = plt.subplots(figsize=(12, 4), facecolor='#060608')
style_ax(ax, 'Annual Returns')
yrs = sorted(annual.keys())
x = np.arange(len(yrs))
w = 0.2
for i, (key, color, label) in enumerate([('mom','#c4a265','Momentum'), ('btc','#f7931a','BTC'), ('comb','#4ade80','Combined'), ('sp','#5a5a68','S&P')]):
    vals = [(np.prod([1+r for r in annual[yr][key]])-1)*100 for yr in yrs]
    ax.bar(x + i*w, vals, w, color=color, alpha=0.8, label=label)
ax.set_xticks(x + 1.5*w)
ax.set_xticklabels(yrs, fontsize=8)
ax.set_ylabel('Return (%)', color='#5a5a68', fontsize=9)
ax.axhline(y=0, color='#5a5a68', linewidth=0.5)
ax.legend(fontsize=7, loc='upper left', facecolor='#0c0c10', edgecolor='#1a1a22', labelcolor='#e8e8ec')
chart5 = fig_to_b64(fig)

# ── Position history table ──
pos_rows = ""
cum_val = 1.0
for i, d in enumerate(mom_data[-24:]):  # last 24 months
    date_str = d['date'].strftime('%Y-%m-%d')
    mode = d['mode']
    ret = d['ret'] * 100
    ym = f"{d['date'].year}-{d['date'].month:02d}"
    btc_r = btc_dict.get(ym, 0) * 100
    comb_r = 0.5 * d['ret'] + 0.5 * btc_dict.get(ym, 0)
    cum_val *= (1 + comb_r)

    if mode == 'MOM':
        stocks_str = ', '.join([f"{s[0]}" for s in d['stocks']])
        mode_class = 'mom'
    elif mode == 'GLD':
        stocks_str = 'GLD'
        mode_class = 'gld'
    else:
        stocks_str = '—'
        mode_class = 'cash'

    btc_inv = btc_data_dict.get(ym, 0) if 'btc_data_dict' in dir() else 0

    pos_rows += f"""<tr>
        <td>{date_str}</td>
        <td class="{mode_class}">{mode}</td>
        <td>{stocks_str}</td>
        <td class="{'pos' if ret >= 0 else 'neg'}">{ret:+.1f}%</td>
        <td class="{'pos' if btc_r >= 0 else 'neg'}">{btc_r:+.1f}%</td>
        <td class="{'pos' if comb_r >= 0 else 'neg'}">{comb_r*100:+.1f}%</td>
    </tr>"""

# Build btc_data_dict
btc_data_dict = {d['ym']: d['invested_pct'] for d in btc_data}

# Redo position history properly
pos_rows = ""
cum_val = 1.0
for d in mom_data[-24:]:
    date_str = d['date'].strftime('%Y-%m-%d')
    mode = d['mode']
    ret = d['ret'] * 100
    ym = f"{d['date'].year}-{d['date'].month:02d}"
    btc_r = btc_dict.get(ym, 0) * 100
    comb_r = (0.5 * d['ret'] + 0.5 * btc_dict.get(ym, 0))
    cum_val *= (1 + comb_r)

    mode_class = 'mom' if mode == 'MOM' else ('gld' if mode == 'GLD' else 'cash')
    stocks_str = ', '.join([s[0] for s in d['stocks']]) if mode == 'MOM' else ('GLD' if mode == 'GLD' else '—')
    btc_mode = 'BTC' if btc_data_dict.get(ym, 0) > 50 else 'Cash'

    pos_rows += f"""<tr>
        <td>{date_str}</td>
        <td class="{mode_class}">{mode}</td>
        <td style="font-size:0.65rem">{stocks_str}</td>
        <td class="{'pos' if ret >= 0 else 'neg'}">{ret:+.1f}%</td>
        <td class="{'btc-in' if btc_mode == 'BTC' else 'cash'}">{btc_mode}</td>
        <td class="{'pos' if btc_r >= 0 else 'neg'}">{btc_r:+.1f}%</td>
        <td class="{'pos' if comb_r >= 0 else 'neg'}">{comb_r*100:+.1f}%</td>
    </tr>"""

# Annual returns table
annual_rows = ""
for yr in sorted(annual.keys()):
    m_r = (np.prod([1+r for r in annual[yr]['mom']])-1)*100
    b_r = (np.prod([1+r for r in annual[yr]['btc']])-1)*100
    c_r = (np.prod([1+r for r in annual[yr]['comb']])-1)*100
    s_r = (np.prod([1+r for r in annual[yr]['sp']])-1)*100
    annual_rows += f"""<tr>
        <td>{yr}</td>
        <td class="{'pos' if m_r>=0 else 'neg'}">{m_r:+.1f}%</td>
        <td class="{'pos' if b_r>=0 else 'neg'}">{b_r:+.1f}%</td>
        <td class="{'pos' if c_r>=0 else 'neg'}">{c_r:+.1f}%</td>
        <td>{s_r:+.1f}%</td>
    </tr>"""

# ── HTML ──
html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<title>Bivar Capital — Combined Portfolio Report</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{{--bg:#060608;--card:#0c0c10;--border:#1a1a22;--text:#e8e8ec;--muted:#5a5a68;--accent:#c4a265;--green:#4ade80;--red:#f87171;--btc:#f7931a}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);line-height:1.7;font-size:14px}}
.container{{max-width:1100px;margin:0 auto;padding:40px 24px 80px}}
h1{{font-size:2rem;font-weight:700;margin-bottom:4px}}
h1 span{{color:var(--accent);font-style:italic}}
.lead{{color:var(--muted);font-size:0.85rem;margin-bottom:32px}}
h2{{font-size:1.2rem;font-weight:600;margin:40px 0 12px;color:var(--accent)}}
h3{{font-family:'JetBrains Mono',monospace;font-size:0.6rem;text-transform:uppercase;letter-spacing:0.15em;color:var(--muted);margin:24px 0 8px}}
p{{color:var(--muted);margin-bottom:10px;font-size:0.82rem}}
strong{{color:var(--text)}}
.grid4{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:16px 0}}
.grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:16px 0}}
.stat{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px;text-align:center}}
.stat .v{{font-family:'JetBrains Mono',monospace;font-size:1.1rem;font-weight:600}}
.stat .l{{font-size:0.5rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.1em;margin-top:2px}}
.pos{{color:var(--green)}}
.neg{{color:var(--red)}}
img{{max-width:100%;border-radius:8px;border:1px solid var(--border);margin:12px 0}}
table{{width:100%;border-collapse:collapse;font-size:0.72rem;margin:8px 0}}
th{{text-align:left;padding:6px 8px;font-family:'JetBrains Mono',monospace;font-size:0.55rem;text-transform:uppercase;letter-spacing:0.08em;color:var(--muted);border-bottom:1px solid var(--border)}}
td{{padding:5px 8px;border-bottom:1px solid var(--border);font-family:'JetBrains Mono',monospace;font-size:0.65rem}}
th:not(:first-child),td:not(:first-child){{text-align:right}}
td.mom{{color:var(--green)}}
td.gld{{color:var(--accent)}}
td.cash{{color:var(--muted)}}
td.btc-in{{color:var(--btc)}}
.callout{{background:var(--card);border-left:3px solid var(--accent);padding:14px 18px;margin:18px 0;border-radius:0 8px 8px 0;font-size:0.8rem}}
.rule-box{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:18px;margin:12px 0;font-size:0.78rem}}
.rule-box ol{{margin-left:16px;color:var(--muted)}}
.rule-box li{{margin-bottom:6px}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0}}
@media(max-width:700px){{.grid4,.grid3{{grid-template-columns:repeat(2,1fr)}}.two-col{{grid-template-columns:1fr}}}}
.footer{{margin-top:48px;padding-top:16px;border-top:1px solid var(--border);text-align:center}}
.footer p{{font-size:0.55rem;color:var(--muted);font-family:'JetBrains Mono',monospace}}
</style>
</head><body><div class="container">

<p style="font-family:'JetBrains Mono',monospace;font-size:0.65rem;letter-spacing:0.2em;text-transform:uppercase;color:var(--muted)">Bivar Capital &mdash; Confidential</p>
<h1>Combined Portfolio <span>Report</span></h1>
<p class="lead">50% BivarOptimalMomentum (with GLD hedge) + 50% BTC Systematic &nbsp;|&nbsp; 2015&ndash;2026</p>

<h2>Summary</h2>
<div class="grid4">
    <div class="stat"><div class="v pos">{s_comb[0]:+.1f}%</div><div class="l">Combined CAGR</div></div>
    <div class="stat"><div class="v pos">{s_comb[1]:.2f}</div><div class="l">Sharpe Ratio</div></div>
    <div class="stat"><div class="v neg">{s_comb[2]:.1f}%</div><div class="l">Max Drawdown</div></div>
    <div class="stat"><div class="v">{s_comb[3]:.1f}%</div><div class="l">Volatility</div></div>
</div>

<div class="grid3">
    <div class="stat"><div class="v" style="color:var(--accent)">{s_mom[0]:+.1f}%</div><div class="l">Momentum CAGR</div></div>
    <div class="stat"><div class="v" style="color:var(--btc)">{s_btc[0]:+.1f}%</div><div class="l">BTC Sys CAGR</div></div>
    <div class="stat"><div class="v" style="color:var(--muted)">{s_sp[0]:+.1f}%</div><div class="l">S&P 500 CAGR</div></div>
</div>

<div class="callout">
    <strong>Correlation between strategies: {np.corrcoef(mom_rets, btc_rets_aligned)[0,1]:.3f}</strong>
    &mdash; Near zero. The two strategies are almost completely independent, making the combined
    portfolio significantly better risk-adjusted than either alone.
</div>

<h2>Equity Curves</h2>
<img src="data:image/png;base64,{chart1}">

<h2>Drawdown</h2>
<img src="data:image/png;base64,{chart2}">

<h2>Regime Map &mdash; When Each Strategy Is Invested</h2>
<img src="data:image/png;base64,{chart3}">
<p>Green = Momentum stocks. Gold = GLD (bear hedge). Grey = Cash. Orange = BTC invested.</p>

<h2>Monthly Returns</h2>
<img src="data:image/png;base64,{chart4}">

<h2>Annual Returns</h2>
<img src="data:image/png;base64,{chart5}">
<table>
    <tr><th>Year</th><th>Momentum</th><th>BTC Sys</th><th>Combined</th><th>S&P 500</th></tr>
    {annual_rows}
</table>

<h2>Strategy Rules</h2>
<div class="two-col">
    <div class="rule-box">
        <h3>BivarOptimalMomentum (50%)</h3>
        <p><strong>Monthly, signal day 18, execute day 19:</strong></p>
        <ol>
            <li>Check S&P 500 vs MA250. Below → <strong>buy GLD</strong></li>
            <li>Momentum = 50% &times; 6-month return + 50% &times; 12-month return</li>
            <li>Filter: mcap &gt;$10B, EBIT &gt; 0, US common stock</li>
            <li>Select top 7 by momentum, max 3 per sector</li>
            <li>Equal weight (~14.3% each)</li>
        </ol>
    </div>
    <div class="rule-box">
        <h3>BTC Systematic (50%)</h3>
        <p><strong>Daily, check at close:</strong></p>
        <ol>
            <li>RSI(14) &gt; 54</li>
            <li>Price &gt; 155-day Moving Average</li>
            <li>20-day Annualised Volatility &lt; 100%</li>
            <li>All three true → <strong>BUY BTC</strong></li>
            <li>Any fails → <strong>SELL, go to cash</strong></li>
        </ol>
    </div>
</div>

<h2>Position History (Last 24 Months)</h2>
<table>
    <tr><th style="text-align:left">Date</th><th>Mom Mode</th><th style="text-align:left">Stocks</th><th>Mom Ret</th><th>BTC Mode</th><th>BTC Ret</th><th>Combined</th></tr>
    {pos_rows}
</table>

<div class="footer">
    <p>Bivar Capital &nbsp;|&nbsp; April 2026 &nbsp;|&nbsp; Confidential</p>
</div>

</div></body></html>"""

with open('/Users/luisabrantes/Desktop/combined_portfolio_report.html', 'w') as f:
    f.write(html)
print("\nSaved: ~/Desktop/combined_portfolio_report.html")
