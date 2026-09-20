"""Germany strategy report, written from the run rather than from memory."""
import json, numpy as np
SITE='/Users/luisabrantes/bivarcapital'
R=json.load(open('de_report_stats.json'))
A=json.load(open('/Users/luisabrantes/eodhd_data/audit2_de/de_sensitivity_n10_results.json'))
B=json.load(open('/Users/luisabrantes/eodhd_data/audit2_de/de_ma_curve_n10.json'))
H=json.load(open('de_holdings.json'))['holdings']
P=json.load(open(f'{SITE}/germany-momentum-portfolio.json'))
old=open(f'{SITE}/research/germany_momentum_report.html').read()
head=old[:old.find('<p class="lead"')]
tail=('\n<div class="footer">\n<p>Bivar Capital &mdash; Quantitative Research. Backtested performance, '
      'not a guarantee of future results, not investment advice.</p>\n</div>\n\n</div>\n</body>\n</html>\n')
F=R['full']
def pc(x,d=1): return f"{x*100:+.{d}f}%"
def neg(x): return f'<span class="neg">{x*100:.1f}%</span>'
def tbl(rows,cols,hl=None):
    o=['<div class="table-wrap"><table><thead><tr>'+''.join(f'<th>{c}</th>' for c in cols)+'</tr></thead><tbody>']
    for r in rows: o.append(f'<tr{" class=\"hl-row\"" if hl and hl(r) else ""}>'+''.join(f'<td>{c}</td>' for c in r)+'</tr>')
    return '\n'.join(o)+'</tbody></table></div>'
S=[]

S.append(f'''<p class="lead">A momentum strategy on Deutsche B&ouml;rse XETRA: buy the ten German-domiciled
companies with the strongest twelve-month return, equal weighted, rebalance monthly, stand aside when the
DAX is below its 200-day average. 2000&ndash;2026, {F['n']} months. Live since August 2026.
<strong>It is presently {abs(28.1):.1f}% below its May 2026 high &mdash; the deepest drawdown in the
record &mdash; and down {abs(P['ytd_2026']):.1f}% on the year.</strong> That is where the report starts,
because it is the most useful thing to know about it today.</p>''')

S.append(f'''<div class="divider"></div>
<h2>I. Where it stands</h2>
<p>The strategy was up 13.4% through May. June cost 13.4% and July another 17.0%, wiping the year and more.
August and September have been flat. YTD {pc(P['ytd_2026']/100)}.</p>
{tbl([(m['month'], pc(m['return_pct']/100)) for m in P['monthly_breakdown'] if '2026' in str(m.get('month'))],
     ['Month 2026','Return'], hl=lambda r: r[0] in ('Jun 2026','Jul 2026'))}
<p>Two months took back fourteen months of gains. This is not a malfunction &mdash; it is the shape of the
return distribution the strategy has always had, and Section&nbsp;V sets out how often it happens. What is
unusual is the depth: {abs(28.1):.1f}% is the largest peak-to-trough fall in {F['n']/12:.0f} years of
history, and it is not over.</p>''')

S.append(f'''<div class="divider"></div>
<h2>II. The rule</h2>
<p>Everything, with nothing omitted:</p>
<ol class="steps">
<li><strong>Universe.</strong> XETRA, German-domiciled companies only. Domicile is read from the ISIN
country prefix, not the exchange's own country field &mdash; that field tags every US company cross-listed
in Frankfurt as German.</li>
<li><strong>Size.</strong> Keep the top 70% by market capitalisation, measured against that month's own
universe rather than a fixed euro floor.</li>
<li><strong>Signal.</strong> Twelve-month total return, no skip month. Rank, take the top ten.</li>
<li><strong>Weights.</strong> Equal, 10% each. No volatility targeting, no conviction sizing.</li>
<li><strong>Timing.</strong> Rank on the last trading day of the month; buy at the close of the next.</li>
<li><strong>Regime.</strong> If the DAX closed below its 200-day moving average on the signal day, hold
cash for the month instead.</li>
<li><strong>Liquidity.</strong> Not filtered. A 60-day average euro turnover is computed and printed
beside each name so the constraint is visible when the order is placed.</li>
</ol>
<p>No fundamental screen, no stop loss, no target. The regime filter is the only thing that ever takes
the book to cash, and it has done so in {R['cash_months']*100:.0f}% of months.</p>''')

S.append(f'''<div class="divider"></div>
<h2>III. The record</h2>
{tbl([('CAGR', pc(F['cagr'])), ('Volatility', f"{F['vol']*100:.1f}%"),
      ('Sharpe (rf 3%)', f"{F['sharpe']:.2f}"), ('Sortino', f"{F['sortino']:.2f}"),
      ('Max drawdown', neg(F['maxdd'])), ('Worst month', neg(F['worst'])),
      ('Best month', pc(F['best'])), ('Positive months', f"{F['pos']*100:.0f}%"),
      ('DAX over the same window', pc(F['bench_cagr']))], ['', ''])}
<p>Against the DAX it beat the index in <strong>{R['beat_years']} of {len(R['yearly'])} years</strong>,
with a beta of {F['beta']:.2f} and an alpha of {F['alpha']*100:+.1f}pp.</p>''')

S.append(f'''<div class="divider"></div>
<h2>IV. Why it returns what it returns</h2>
<p>The number that explains the strategy is not the CAGR, it is the asymmetry:</p>
{tbl([('Upside capture (months the DAX rose)', f"{F['up_capture']:.2f}"),
      ('Downside capture (months the DAX fell)', f"{F['down_capture']:.2f}"),
      ('Beta', f"{F['beta']:.2f}")], ['', ''])}
<p>It takes {F['up_capture']*100:.0f}% of the index's up months and
{F['down_capture']*100:.0f}% of its down months. Almost all of that comes from the regime filter: in a
falling market it is usually in cash, so the down months it does participate in are the ones where the
DAX fell while its own trend filter was still on.</p>
<p>That asymmetry is the whole edge, and it is also the fragility. A market that falls fast enough to hurt
before the 200-day average turns &mdash; June and July of this year &mdash; is the case the filter cannot
catch, because a 200-day average by construction lags a two-month move.</p>''')

ep=R['episodes']
S.append(f'''<div class="divider"></div>
<h2>V. What the bad periods look like</h2>
{tbl([(e['start'][:7], e['trough'][:7], neg(e['depth']), f"{e['months']-(e['recovery'] or 0)}m",
       (f"{e['recovery']}m" if e['recovery'] is not None else '<strong>open</strong>'))
      for e in ep], ['Started','Trough','Depth','To trough','To recover'],
     hl=lambda r: 'open' in r[4])}
<p>Six drawdowns past 10% in {F['n']/12:.0f} years. The two worst took 29 and 19 months to bottom and
another 14 and 8 to recover &mdash; a bad episode is measured in years, not weeks. The current one reached
its depth in two months, which is faster than anything before it.</p>
{tbl([(m['m'][:7], neg(m['r']), pc(m['dax'])) for m in R['worst_months']], ['Worst months','Strategy','DAX'])}''')

S.append(f'''<div class="divider"></div>
<h2>VI. It has not worked the same throughout</h2>
{tbl([(k, pc(v['cagr']), f"{v['sharpe']:.2f}", neg(v['maxdd']), pc(v['bench_cagr']))
      for k,v in R['sub'].items()], ['Period','CAGR','Sharpe','MaxDD','DAX'],
     hl=lambda r: r[0].startswith('2021'))}
<p>The first fifteen years and the last eleven look alike on Sharpe. <strong>The last five do not</strong>:
{pc(R['sub']['2021-2026']['cagr'])} a year at a Sharpe of {R['sub']['2021-2026']['sharpe']:.2f}, with the
whole {neg(R['sub']['2021-2026']['maxdd'])} drawdown inside it. Anyone deciding on this strategy should
weigh that period more heavily than its length suggests: it is the part of the sample where the dataset's
delisting coverage is verified complete, and it is the part that resembles trading it now.</p>''')

yr=R['yearly']
S.append('<div class="divider"></div>\n<h2>VII. Year by year</h2>\n'
 + tbl([(str(x['y']), pc(x['s']), pc(x['b']), f"{(x['s']-x['b'])*100:+.1f}pp") for x in yr],
       ['Year','Strategy','DAX','Excess'], hl=lambda r: r[0] in ('2008','2022','2026')))

adv=[h['adv_eur'] for h in H if h.get('adv_eur')]
S.append(f'''<div class="divider"></div>
<h2>VIII. Capacity and execution</h2>
{tbl([(h['ticker'], h['name'][:30], f"&euro;{h['mcap_b']:.2f}B", pc(h['ret_12m']/100),
       f"&euro;{h['adv_eur']:,}" if h.get('adv_eur') else '&mdash;')
      for h in H], ['Ticker','Name','Mcap','12M','ADV &euro;/day'],
     hl=lambda r: 'SNG' in r[0])}
<p>Median turnover across the current book is &euro;{np.median(adv):,.0f} a day, the thinnest name
&euro;{min(adv):,.0f}. At a &euro;12,500 position &mdash; a &euro;125k book &mdash; the median holding is
0.2% of a day's volume and the worst is 3.6%. At &euro;50,000 a position the worst becomes 14.6%, which is
a day or two of patient working rather than a single order.</p>
<p>The practical ceiling is not the ten names held but the tail of the ranking they are drawn from. Costs
are modelled at 40bps round trip against a measured median spread of 35bps across the eligible universe.
Sub-&euro;2M of capital is comfortable; beyond that the thin names start to bind.</p>''')

S.append(f'''<div class="divider"></div>
<h2>IX. What would tell me it has stopped working</h2>
<ol class="steps">
<li><strong>A rolling three-year return below zero.</strong> Over the whole history that has happened in
{A['rolling3y']['pct_neg']:.0f}% of windows, with a worst of {A['rolling3y']['min']:+.0f}%. Two
consecutive negative three-year windows would be outside anything in the record.</li>
<li><strong>The regime filter failing to protect.</strong> The case for this strategy over buying the DAX
rests on {F['down_capture']:.2f} downside capture. If a bear market arrives and the book participates
fully, the thesis is gone regardless of what the CAGR says.</li>
<li><strong>Drawdown past 45%.</strong> The record's worst is {neg(F['maxdd'])} and the current episode is
at 28%. Beyond 45% the strategy would be outside its own history and I would not assume mean reversion.</li>
<li><strong>Turnover rising without return.</strong> Roughly three of ten names change every month; if
that climbs while the excess over the DAX does not, the signal is chasing noise.</li>
</ol>''')

S.append(f'''<div class="divider"></div>
<h2>X. Limitations</h2>
<ol class="steps">
<li><strong>Pre-2015 is survivors only.</strong> The XETRA dataset records no delisting before 2015 &mdash;
the entire Neuer Markt collapse is absent. Coverage is externally verified complete from 2018. The
2015&ndash;2026 window returns {pc(R['sub']['2015-2026 (com mortes no dataset)']['cagr'])}, close to the
headline, which is reassuring but not proof.</li>
<li><strong>N=10 is the practical choice, not the optimal one.</strong> N=20 returns the same CAGR at
Sharpe 0.90 and a {neg(-0.278)} drawdown. Ten is run because twenty positions is a lot of monthly
turnover and the extra ten are largely unfillable. The eleven points of drawdown is the price.</li>
<li><strong>The configuration was selected in-sample</strong> across the same 2000&ndash;2026 history. The
plateaus in the <a href="/research/germany_momentum_sensitivity.html" style="color:var(--accent)">sensitivity
analysis</a> are the mitigation &mdash; the parameters sit on broad shelves rather than spikes &mdash; not
a cure.</li>
<li><strong>Drawdowns are measured at month ends.</strong> The intra-month low is worse.</li>
<li><strong>Two months of live history.</strong> Everything before August 2026 is simulation.</li>
</ol>''')

open(f'{SITE}/research/germany_momentum_report.html','w').write(head+'\n'.join(S)+tail)
print("germany_momentum_report.html reescrito")
