"""Regenerate the Germany sensitivity page from the N=10 battery.
Keeps the existing page's shell (head/nav/CSS) and rewrites every section
from de_sensitivity_n10_results.json + de_ma_curve_n10.json."""
import json, re
SITE='/Users/luisabrantes/bivarcapital'
A=json.load(open('/Users/luisabrantes/eodhd_data/audit2_de/de_sensitivity_n10_results.json'))
B=json.load(open('/Users/luisabrantes/eodhd_data/audit2_de/de_ma_curve_n10.json'))
old=open(f'{SITE}/research/germany_momentum_sensitivity.html').read()
head = old[:old.find('<p class="lead"')]
tail = '\n<div class="footer">\n<p>Bivar Capital &mdash; Quantitative Research. Backtested performance, not a guarantee of future results, not investment advice.</p>\n</div>\n\n</div>\n</body>\n</html>\n'

H=A['headline']
def f(x, pct=True, sign=True):
    return (f"{x:+.2f}%" if sign else f"{x:.2f}%") if pct else f"{x:.3f}"
def tbl(rows, cols, hl=None):
    o=['<div class="table-wrap"><table><thead><tr>'+''.join(f'<th>{c}</th>' for c in cols)+'</tr></thead><tbody>']
    for r in rows:
        cls=' class="hl-row"' if hl and hl(r) else ''
        o.append(f'<tr{cls}>'+''.join(f'<td>{c}</td>' for c in r)+'</tr>')
    return '\n'.join(o)+'</tbody></table></div>'
def dd(v): return f'<span class="neg">{v:.1f}%</span>'

P=[]
P.append(f'''<p class="lead">One-at-a-time sweeps across momentum lookback, market cap filter, regime window,
portfolio size, liquidity, fundamental filter and costs, plus calendar-year returns and rolling 3-year
performance, behind the <a href="/germany-momentum.html" style="color:var(--accent)">Germany XETRA momentum
strategy</a>. 2000&ndash;2026, 319 months. This run is the live configuration: German-domiciled companies
only, <strong>top 10 equal weight</strong>, DAX vs MA200, 40bps round-trip, no liquidity filter. All numbers
from an independent harness that reproduces the adversarial audit's Section&nbsp;C.2 to the decimal.
Data caveat from the delisting forensics: recorded deaths in the XETRA dataset are thin before 2015, so
pre-2015 results carry survivorship risk.</p>''')

P.append(f'''<div class="divider"></div>
<h2>I. Baseline (live config)</h2>
<p>12M lookback &middot; skip 0 &middot; mcap top 70% (P30) &middot; N=10 equal weight &middot; DAX vs MA200
&middot; 40bps &middot; no fundamental filter &middot; no liquidity filter &mdash; <strong>CAGR {H['cagr']:+.2f}%,
Sharpe {H['sharpe']:.3f}, Sortino {H['sortino']:.2f}, MaxDD {H['maxdd']:.1f}%</strong>.</p>
<p>Every sweep below moves one dimension and holds the rest at that baseline.</p>''')

P.append('<div class="divider"></div>\n<h2>II. Momentum Lookback &times; Skip</h2>\n'
 + tbl([(f"{r['lb']}M", f"skip {r['sk']}", f"{r['sharpe']:.3f}", f"{r['sortino']:.2f}",
         f"{r['cagr']:+.2f}%", dd(r['maxdd'])) for r in A['lbsk']],
       ['Lookback','Skip','Sharpe','Sortino','CAGR','MaxDD'],
       hl=lambda r: r[0]=='12M' and r[1]=='skip 0')
 + '\n<p>12M with no skip is the peak and the neighbourhood holds up; short lookbacks degrade materially.</p>')

P.append('<div class="divider"></div>\n<h2>III. Market Cap Filter</h2>\n'
 + tbl([(f"top {100-int(r['pct']*100)}% (P{int(r['pct']*100)})" if r['pct'] else "no filter",
         f"{r['sharpe']:.3f}", f"{r['sortino']:.2f}", f"{r['cagr']:+.2f}%", dd(r['maxdd'])) for r in A['mcap']],
       ['Universe','Sharpe','Sortino','CAGR','MaxDD'], hl=lambda r: 'P30' in r[0]))

P.append('<div class="divider"></div>\n<h2>IV. Regime Filter Window</h2>\n'
 + tbl([(f"MA{r['window']}", f"{r['sharpe']:.3f}", f"{r['sortino']:.2f}", f"{r['cagr']:+.2f}%", dd(r['maxdd']))
        for r in B['ma']] + [(f"MA{B['ma_band']['window']} hysteresis", f"{B['ma_band']['sharpe']:.3f}",
        f"{B['ma_band']['sortino']:.2f}", f"{B['ma_band']['cagr']:+.2f}%", dd(B['ma_band']['maxdd']))],
       ['Window','Sharpe','Sortino','CAGR','MaxDD'], hl=lambda r: r[0]=='MA200')
 + '\n<p>Sharpe rises monotonically from MA50 to MA200 and falls away on both sides &mdash; a plateau, not an isolated peak. A &plusmn;2% hysteresis band around MA200 trades a little CAGR for a materially shallower drawdown.</p>')

P.append('<div class="divider"></div>\n<h2>V. Portfolio Size (N)</h2>\n'
 + tbl([(str(r['n']), f"{r['sharpe']:.3f}", f"{r['sortino']:.2f}", f"{r['cagr']:+.2f}%", dd(r['maxdd']))
        for r in A['n']], ['N','Sharpe','Sortino','CAGR','MaxDD'], hl=lambda r: r[0]=='10')
 + f'''\n<p><strong>N=20 is the better configuration on this evidence</strong> &mdash; Sharpe 0.899 against
0.716 and MaxDD &minus;27.8% against &minus;39.1%, for essentially the same CAGR &mdash; and the adversarial
audit reached the same verdict. We run <strong>N=10 anyway, for practicality</strong>: twenty positions is a
lot of book to turn over every month, and the ten that N=20 adds are largely the ones that cannot be filled.
On 2026-09-20, four of ranks 11&ndash;20 traded under &euro;42k a day, Nuernberger at &euro;1,201 against
&euro;1.43B of market cap. The cost of that choice is stated plainly above: eleven points of drawdown.</p>''')

P.append('<div class="divider"></div>\n<h2>VI. Liquidity Floor (diagnostic)</h2>\n'
 + tbl([("none" if not r['adv'] else f"&euro;{r['adv']:,}/day", f"{r['sharpe']:.3f}", f"{r['sortino']:.2f}",
         f"{r['cagr']:+.2f}%", dd(r['maxdd'])) for r in A['adv']],
       ['ADV floor','Sharpe','Sortino','CAGR','MaxDD'], hl=lambda r: r[0]=='none')
 + '''\n<p>The live signal computes a 60-day average euro volume for every name and prints it beside the
rank, but does not filter on it: whether a name is buyable depends on position size and on how the order is
worked, which is decided at execution. The sweep is kept as a diagnostic. Note it is not monotone at N=10
&mdash; with ten names drawn from roughly 270, moving the floor swaps one or two holdings and the result
moves with them.</p>''')

P.append('<div class="divider"></div>\n<h2>VII. Fundamental Filter</h2>\n'
 + tbl([(r['filter'], f"{r['sharpe']:.3f}", f"{r['sortino']:.2f}", f"{r['cagr']:+.2f}%", dd(r['maxdd']))
        for r in A['fund']], ['Filter','Sharpe','Sortino','CAGR','MaxDD'], hl=lambda r: 'None' in r[0])
 + '\n<p>Every profitability screen lifts Sharpe and cuts the drawdown at a small cost in CAGR. None is applied live; the live config is the unfiltered row.</p>')

P.append('<div class="divider"></div>\n<h2>VIII. Transaction Costs</h2>\n'
 + tbl([(f"{r['bps']}bps RT", f"{r['sharpe']:.3f}", f"{r['sortino']:.2f}", f"{r['cagr']:+.2f}%", dd(r['maxdd']))
        for r in A['cost']], ['Round-trip cost','Sharpe','Sortino','CAGR','MaxDD'], hl=lambda r: r[0]=='40bps RT')
 + '\n<p>Each 10bps of round-trip cost is worth roughly 0.6pp of CAGR at this turnover. The 40bps assumption is a measurement, not a guess: real IBKR spreads across the German universe had a median of 35bps.</p>')

yr=A['yearly']
P.append('<div class="divider"></div>\n<h2>IX. Calendar-Year Returns vs DAX</h2>\n'
 + tbl([(str(r['year']), f"{r['strat']:+.1f}%", f"{r['dax']:+.1f}%",
         f"{r['strat']-r['dax']:+.1f}pp") for r in yr],
       ['Year','Strategy','DAX','Excess'])
 + f"\n<p>{sum(1 for r in yr if r['strat']>r['dax'])} of {len(yr)} years beat the DAX.</p>")

R3=A['rolling3y']
P.append(f'''<div class="divider"></div>
<h2>X. Rolling 3-Year Performance</h2>
<p>Mean {R3['mean']:+.1f}%, range {R3['min']:+.1f}% to {R3['max']:+.1f}%, negative in {R3['pct_neg']:.1f}%
of all 3-year windows.</p>''')

P.append('''<div class="divider"></div>
<h2>XI. Limitations</h2>
<ol class="steps">
<li><strong>Pre-2015 is survivors-only</strong> (zero delistings in the dataset before 2015; externally verified complete from 2018).</li>
<li><strong>All sweeps are in-sample</strong> over the same 2000&ndash;2026 history; the plateaus, not the peaks, are the evidence.</li>
<li><strong>One-at-a-time sweeps miss interactions.</strong></li>
<li><strong>N=10 is the practical choice, not the optimal one</strong> &mdash; see Section&nbsp;V.</li>
<li><strong>Sub-EUR-2M capacity</strong>; median position ADV ~&euro;0.4M/day.</li>
</ol>''')

open(f'{SITE}/research/germany_momentum_sensitivity.html','w').write(head+'\n'.join(P)+tail)
print("germany_momentum_sensitivity.html regenerado")
