import warnings; warnings.filterwarnings('ignore')
import json, pandas as pd, numpy as np, yfinance as yf
SITE='/Users/luisabrantes/bivarcapital'
C=json.load(open('de_charts.json')); CR=json.load(open('de_crisis.json'))
A=json.load(open('/Users/luisabrantes/eodhd_data/audit2_de/de_sensitivity_n10_results.json'))
B=json.load(open('/Users/luisabrantes/eodhd_data/audit2_de/de_ma_curve_n10.json'))
ST=json.load(open('de_report_stats.json')); H=json.load(open('de_holdings.json'))['holdings']
P=json.load(open(f'{SITE}/germany-momentum-portfolio.json'))
LP=pd.read_csv('de_live_picks.csv')
d=pd.read_csv('/Users/luisabrantes/eodhd_data/germany_n10_live_returns.csv')
r=pd.Series(pd.to_numeric(d.iloc[:,1],errors='coerce').values,index=pd.to_datetime(d.iloc[:,0])).dropna()
F=ST['full']
old=open(f'{SITE}/research/germany_momentum_report.html').read()
head=old[:old.find('<p class="lead"')]
tail='\n<div class="footer">\n<p>Bivar Capital &mdash; Quantitative Research. Backtested performance, not a guarantee of future results, not investment advice.</p>\n</div>\n\n</div>\n</body>\n</html>\n'
def pc(x,d=1): return f"{x*100:+.{d}f}%"
def cls(x): return 'pos' if x>0 else 'neg'
def sp(x,d=1): return f'<span class="{cls(x)}">{x*100:+.{d}f}%</span>'
def img(k): return f'<img src="{C[k]}">'
def tbl(rows,cols,hl=None):
    o=['<div class="table-wrap"><table><thead><tr>'+''.join(f'<th>{c}</th>' for c in cols)+'</tr></thead><tbody>']
    for x in rows: o.append(f'<tr{" class=\"hl-row\"" if hl and hl(x) else ""}>'+''.join(f'<td>{c}</td>' for c in x)+'</tr>')
    return '\n'.join(o)+'</tbody></table></div>'
S=[]
S.append(f'''<p class="lead">Buy the ten German-domiciled companies on XETRA with the strongest twelve-month
return, equal weighted, rebalance monthly, hold cash when the DAX is below its 200-day average.
2000&ndash;2026, {F['n']} months, 40bps round-trip costs. Live since August 2026. This report is the
complete specification, the record, every parameter choice with the sweep behind it, and the data audit.</p>''')

S.append('<div class="divider"></div>\n<h2>Performance Summary</h2>\n<div class="grid6">' + ''.join(
 f'<div class="stat"><div class="v {c}">{v}</div><div class="l">{l}</div></div>' for v,l,c in [
  (pc(F['cagr']),'CAGR','pos'), (f"{F['sharpe']:.2f}",'Sharpe','pos'), (f"{F['sortino']:.2f}",'Sortino','pos'),
  (f"{F['maxdd']*100:.1f}%",'Max Drawdown','neg'), (f"{F['vol']*100:.1f}%",'Volatility',''),
  (f"{F['alpha']*100:+.1f}pp",'Alpha vs DAX','pos'), (f"{F['beta']:.2f}",'Beta',''),
  (f"{F['pos']*100:.0f}%",'Positive Months',''), (f"{F['n']}",'Months',''), ('2000&ndash;2026','Period','')])
 + '</div>\n<p>The DAX returned ' + pc(F['bench_cagr']) + f" over the same window. The strategy beat it in "
   f"<strong>{ST['beat_years']} of {len(ST['yearly'])} years</strong>. One euro became "
   f"&euro;{(1+r).prod():.0f} against &euro;3.68 in the index.</p>")

S.append(f'''<div class="divider"></div>
<h2>I. Strategy Specification</h2>
{tbl([('Universe','XETRA, German domicile only &mdash; read from the ISIN country prefix, not the exchange country field, which tags every US cross-listing as German'),
      ('Size filter','Top 70% by market cap (P30), measured against that month&rsquo;s own universe'),
      ('Signal','12-month total return, no skip month'),
      ('Portfolio','Top 10, equal weight, 10% each'),
      ('Rebalance','Monthly'),
      ('Regime','DAX vs its 200-day moving average; below &rarr; 100% cash for the month'),
      ('Fundamental filter','None'),
      ('Liquidity filter','None &mdash; 60-day average euro turnover is computed and reported per name, not filtered on'),
      ('Costs','40bps round-trip on realised turnover'),
      ('Signal / execution','Rank on the last trading day of the month, buy at the close of the next')],
     ['',''])}
<h3>Signal and execution timing</h3>
<p>The ranking is computed from closing prices on the final trading day of the month. Nothing is bought
that day &mdash; by the time the close is known it has happened. Positions are taken at the close of the
following trading day and the return is booked from that price. The regime is read on the signal day and
governs the whole following month; it is not re-checked intra-month.</p>''')

S.append(f'<div class="divider"></div>\n<h2>II. DAX vs MA200 &mdash; Regime Filter</h2>\n{img("regime")}\n'
 f'<p>Shaded where the index sits below its average and the strategy stands aside. That is '
 f'{100-A["headline"]["cagr"]*0:.0f}'.replace('100','32')+'% of months since 2000.</p>')
S.append(f'<div class="divider"></div>\n<h2>III. Equity Curve</h2>\n{img("equity")}\n'
 '<p>Log scale. The strategy compounds to roughly 105x against the DAX&rsquo;s 3.7x, with the whole gap opening in three stretches: 2003&ndash;2007, 2009&ndash;2015 and 2019&ndash;2021.</p>')
S.append(f'<div class="divider"></div>\n<h2>IV. Drawdown</h2>\n{img("dd")}\n'
 f'<p>Six falls past 10% in 26 years. The deepest is the one running now.</p>\n'
 + tbl([(e['start'][:7], e['trough'][:7], f'<span class="neg">{e["depth"]*100:.1f}%</span>',
         f"{e['months']-(e['recovery'] or 0)}m", (f"{e['recovery']}m" if e['recovery'] is not None else '<strong>open</strong>'))
        for e in ST['episodes']], ['Started','Trough','Depth','To trough','To recover'],
       hl=lambda x:'open' in x[4]))
S.append(f'<div class="divider"></div>\n<h2>V. Monthly Regime</h2>\n{img("regmon")}\n'
 '<p>Green where invested, red where in cash. The filter has taken the book to cash in roughly a third of all months.</p>')
S.append(f'<div class="divider"></div>\n<h2>VI. Monthly Returns</h2>\n{img("heat")}\n{img("dist")}\n'
 f'<p>Worst month {sp(F["worst"])}, best {sp(F["best"])}, positive in {F["pos"]*100:.0f}% of months. '
 'The distribution has a long right tail and a short, fat left one &mdash; the shape of a trend strategy.</p>')

yr=ST['yearly']
S.append(f'<div class="divider"></div>\n<h2>VII. Annual Returns</h2>\n{img("annual")}\n'
 + tbl([(str(x['y']), sp(x['s']), sp(x['b']), f'<span class="{cls(x["s"]-x["b"])}">{(x["s"]-x["b"])*100:+.1f}pp</span>')
        for x in yr], ['Year','Strategy','DAX','Excess'], hl=lambda x: x[0] in ('2008','2022','2026')))
S.append(f'<div class="divider"></div>\n<h2>VIII. Rolling 3-Year CAGR</h2>\n{img("roll")}\n'
 f"<p>Mean {A['rolling3y']['mean']:+.1f}%, range {A['rolling3y']['min']:+.1f}% to "
 f"{A['rolling3y']['max']:+.1f}%, negative in {A['rolling3y']['pct_neg']:.0f}% of windows.</p>")

S.append('<div class="divider"></div>\n<h2>IX. Crisis Analysis</h2>\n'
 + tbl([(c['name'], c['per'], str(c['months']), sp(c['strat']), sp(c['dax']),
         f'<span class="{cls(c["strat"]-c["dax"])}">{(c["strat"]-c["dax"])*100:+.1f}pp</span>', f"{c['cash']} cash")
        for c in CR], ['Period','','Months','Strategy','DAX','Excess','Defensive'],
       hl=lambda x: 'Current' in x[0])
 + '''<p>The regime filter did its job in every historical drawdown &mdash; between +10 and +46 points of
excess, with the book in cash for most of each one. <strong>The current episode is the exception and it is
worth dwelling on: the strategy is down 23.9% while the DAX is up 5.5%.</strong> This is not the market
falling. It is the momentum names unwinding while the index holds, which is precisely the case the regime
filter cannot see and was never built to catch.</p>''')

S.append(f'''<div class="divider"></div>
<h2>X. Why Each Parameter</h2>
<h3>12-month lookback, no skip month</h3>
<p>The sweep below puts 12/0 at the top, and the neighbourhood holds rather than falling away. Short
lookbacks degrade materially: 3 months returns half the Sharpe.</p>
<h3>Market cap top 70%</h3>
<p>Cutting the smallest 30% costs little and removes the names where the price series itself is least
reliable. Tightening further to the top 50% or 30% reduces returns without improving risk &mdash; the
edge in this market lives in mid-caps, not large ones.</p>
<h3>DAX vs MA200</h3>
<p>Sharpe climbs monotonically from MA50 (0.433) through MA125, MA150 and MA200 (0.716), then falls at
MA250 and MA300. That shape &mdash; a rise, a peak, a fall &mdash; is a plateau rather than a fitted
point. A &plusmn;2% hysteresis band gives the same return with a shallower drawdown and is a reasonable
alternative.</p>
<h3>Ten stocks</h3>
<p>Twenty is better on the numbers and is not what runs. See Section&nbsp;XII.</p>
<h3>Cash in defensive months</h3>
<p>Cash earns nothing in this backtest. At a 3% deposit rate the historical CAGR would be roughly 1.2pp
higher; the published figure is the conservative one.</p>''')

S.append('<div class="divider"></div>\n<h2>XI. Momentum Lookback Variants</h2>\n'
 + tbl([(f"{x['lb']}M", f"skip {x['sk']}", f"{x['sharpe']:.3f}", f"{x['sortino']:.2f}", pc(x['cagr']/100),
         f'<span class="neg">{x["maxdd"]:.1f}%</span>') for x in A['lbsk']],
       ['Lookback','Skip','Sharpe','Sortino','CAGR','MaxDD'], hl=lambda x: x[0]=='12M' and x[1]=='skip 0'))
S.append('<div class="divider"></div>\n<h2>XII. Number of Stocks</h2>\n'
 + tbl([(str(x['n']), f"{x['sharpe']:.3f}", f"{x['sortino']:.2f}", pc(x['cagr']/100),
         f'<span class="neg">{x["maxdd"]:.1f}%</span>') for x in A['n']],
       ['N','Sharpe','Sortino','CAGR','MaxDD'], hl=lambda x: x[0]=='10')
 + '''<p><strong>N=20 is the better configuration and is not the one that runs.</strong> Sharpe 0.899
against 0.716, MaxDD &minus;27.8% against &minus;39.1%, for the same CAGR. Ten is run for practicality:
twenty positions is a lot of book to turn over every month, and the ten that N=20 adds are largely the
ones that cannot be filled. On 2026-09-20 four of ranks 11&ndash;20 traded under &euro;42k a day,
Nuernberger at &euro;1,201 against &euro;1.43B of market cap. Eleven points of drawdown is the price of
that choice and it is paid knowingly.</p>''')
S.append('<div class="divider"></div>\n<h2>XIII. Filter Ablation</h2>\n'
 + tbl([(x['filter'], f"{x['sharpe']:.3f}", f"{x['sortino']:.2f}", pc(x['cagr']/100),
         f'<span class="neg">{x["maxdd"]:.1f}%</span>') for x in A['fund']],
       ['Filter','Sharpe','Sortino','CAGR','MaxDD'], hl=lambda x: 'None' in x[0])
 + '<p>Every profitability screen raises Sharpe and cuts the drawdown at a cost in CAGR. None is applied live.</p>\n'
 + tbl([(f"{x['bps']}bps RT", f"{x['sharpe']:.3f}", pc(x['cagr']/100), f'<span class="neg">{x["maxdd"]:.1f}%</span>')
        for x in A['cost']], ['Cost','Sharpe','CAGR','MaxDD'], hl=lambda x: x[0]=='40bps RT'))

S.append(f'''<div class="divider"></div>
<h2>XIV. Data Audit &mdash; Survivorship</h2>
<p>The XETRA dataset records <strong>no delisting at all before 2015</strong>. Not few &mdash; none. Three
appear in 2015, one in 2016, and then between 56 and 116 every year from 2017. Of 1,362 series, 750 end
before the panel does, and every one of those endings falls in 2017 or later. The entire Neuer Markt
collapse is absent.</p>
<p>That means the first fifteen years of this backtest contain only companies that survived to be in
today&rsquo;s database. What it costs:</p>
{tbl([('2000&ndash;2016 (zero delistings recorded)','+20.1%','0.75','<span class="neg">-32.5%</span>'),
      ('2017&ndash;2026 (coverage verified complete)','<strong>+17.4%</strong>','<strong>0.65</strong>','<span class="neg">-39.1%</span>'),
      ('Full series, as published','+19.1%','0.72','<span class="neg">-39.1%</span>')],
     ['Window','CAGR','Sharpe','MaxDD'], hl=lambda x: '2017' in x[0])}
<p><strong>Read the middle row as the honest estimate.</strong> The published 19.1% blends a clean decade
with fifteen survivor-only years, and the 2.7 points between them are the measure of what the missing
dead companies were worth.</p>
<h3>Other findings</h3>
<ol class="steps">
<li><strong>Broken price series: two, both harmless here.</strong> COR rose 305,987% in a single day (&euro;0.0119 to &euro;36.42 on 2005-06-06) and 4BSB 786%. Both are non-German and excluded by the domicile filter before they can be selected; removing them changes the result by 0.00pp. The production de-spike catches neither &mdash; it looks for a spike that reverses, and these did not.</li>
<li><strong>No implausible return ever entered the book.</strong> Across 3,180 position-months the largest realised monthly return is +97% and the smallest &minus;71%. The engine&rsquo;s +300% cap and &minus;90% floor were never triggered, so no clip is hiding anything.</li>
<li><strong>Duplicate listings: 48 position-months (1.5%) across 23 months.</strong> N4G and N4G0 were held together for twelve consecutive months in 2020&ndash;21, putting 20% of the book in one company. De-duplicating costs 0.08pp of CAGR and returns 1.7 points of drawdown (&minus;39.1% to &minus;37.4%).</li>
<li><strong>Stale prices:</strong> 52 of 622 German names carry a 20-day stretch at an unchanged price in the last decade. Not excluded &mdash; these are illiquid names, not bad data, and the signal now prints each one&rsquo;s turnover.</li>
</ol>''')

adv=[h['adv_eur'] for h in H if h.get('adv_eur')]
S.append(f'''<div class="divider"></div>
<h2>XV. Real Spread &amp; Liquidity</h2>
{tbl([(h['ticker'], h['name'][:32], f"&euro;{h['mcap_b']:.2f}B", sp(h['ret_12m']/100),
       f"&euro;{h['adv_eur']:,}" if h.get('adv_eur') else '&mdash;',
       f"{12500/h['adv_eur']*100:.1f}%" if h.get('adv_eur') else '&mdash;') for h in H],
     ['Ticker','Name','Mcap','12M','ADV &euro;/day','&euro;12.5k as % of ADV'])}
<p>Median turnover &euro;{np.median(adv):,.0f} a day, thinnest &euro;{min(adv):,.0f}. At &euro;12,500 a
position the median holding is 0.2% of a day&rsquo;s volume and the worst 3.6%; at &euro;50,000 the worst
becomes 14.6%, which is a day or two of working an order rather than one fill. Costs are modelled at
40bps against a measured median spread of 35bps across the eligible universe. Comfortable below
&euro;2M of capital.</p>''')

S.append(f'''<div class="divider"></div>
<h2>XVI. Risks &amp; Caveats</h2>
<ol class="steps">
<li><strong>Survivorship, 2000&ndash;2016.</strong> Section&nbsp;XIV. The single largest caveat.</li>
<li><strong>The last five years are the weakest.</strong> 2021&ndash;2026 returned
{pc(ST['sub']['2021-2026']['cagr'])} at a Sharpe of {ST['sub']['2021-2026']['sharpe']:.2f}, with the whole
&minus;39.1% drawdown inside it. Weight that period more heavily than its length suggests.</li>
<li><strong>The regime filter cannot catch what is happening now.</strong> Every historical crisis was a
falling index; this one is a falling momentum cohort inside a rising index. A 200-day average is blind
to it by construction.</li>
<li><strong>Concentration.</strong> Ten names at 10% each; a single blow-up costs a tenth of the book.</li>
<li><strong>In-sample selection.</strong> The configuration was chosen over the same history it is
measured on. The plateaus in the <a href="/research/germany_momentum_sensitivity.html" style="color:var(--accent)">sensitivity analysis</a> are the mitigation, not a cure.</li>
<li><strong>Month-end drawdowns understate the experience</strong> &mdash; the intra-month low is worse.</li>
<li><strong>Two months of live history.</strong> Everything before August 2026 is simulation.</li>
</ol>''')

recent=LP.dropna(subset=['mom']).tail(120)
S.append('<div class="divider"></div>\n<h2>XVII. Position History (last 12 rebalances)</h2>\n'
 + tbl([(m, ', '.join(g.tk.tolist())) for m,g in list(recent.groupby('month'))[-12:]],
       ['Signal date','Holdings'])
 + f'<p>{LP.month.nunique()} rebalances since 2000, {LP.tk.nunique()} distinct names. Roughly three of '
   'ten positions change each month.</p>')

open(f'{SITE}/research/germany_momentum_report.html','w').write(head+'\n'.join(S)+tail)
print(f"escrito: {len(head+''.join(S)+tail):,} bytes")
