import numpy as np
import json, re
SITE='/Users/luisabrantes/bivarcapital'
R=json.load(open('/private/tmp/claude-501/-Users-luisabrantes/8886b953-a92e-4174-8656-fa856169a782/scratchpad/combo_results.json'))
old=open(f'{SITE}/research/combined_portfolio_report.html').read()
head=old[:old.find('<p class="lead"')]
tail=('\n<div class="footer">\n<p>Bivar Capital &mdash; Quantitative Research. Backtested performance, '
      'not a guarantee of future results, not investment advice.</p>\n</div>\n\n</div>\n</body>\n</html>\n')
def pc(x,d=1,s=True): return f"{x*100:+.{d}f}%" if s else f"{x*100:.{d}f}%"
def neg(x): return f'<span class="neg">{x*100:.1f}%</span>'
def tbl(rows,cols,hl=None):
    o=['<div class="table-wrap"><table><thead><tr>'+''.join(f'<th>{c}</th>' for c in cols)+'</tr></thead><tbody>']
    for r in rows:
        o.append(f'<tr{" class=\"hl-row\"" if hl and hl(r) else ""}>'+''.join(f'<td>{c}</td>' for c in r)+'</tr>')
    return '\n'.join(o)+'</tbody></table></div>'
S=R['sleeves']; C=R['cands']; W=R['wf']; P=[]
w0,w1=R['window']

P.append(f'''<p class="lead">The three live momentum sleeves &mdash;
<a href="/momentum.html" style="color:var(--accent)">USA</a> (top 7 large caps),
<a href="/canada-momentum.html" style="color:var(--accent)">Canada</a> (top 10 TSX) and
<a href="/germany-momentum.html" style="color:var(--accent)">Germany</a> (top 10 XETRA) &mdash; combined.
{w0} to {w1}, {R['n']} months. Rebuilt {('2026-09-20')} from the series each strategy publishes, after the
previous version was found to be running a Canada series contaminated by a look-ahead in the fundamental
filter and a Germany variant that no longer exists. Every sleeve's own caveats carry through: survivorship
windows, capacity limits, in-sample config selection.</p>''')

P.append('<div class="divider"></div>\n<h2>I. The Three Sleeves</h2>\n'
 + tbl([(k, pc(v['cagr']), f"{v['vol']*100:.1f}%", f"{v['sharpe']:.2f}", f"{v['sortino']:.2f}",
         neg(v['maxdd']), neg(v['worst'])) for k,v in S.items()],
       ['Sleeve','CAGR','Vol','Sharpe','Sortino','MaxDD','Worst month'])
 + '''\n<p>Canada carries the book and Germany is the weakest leg on every measure. That is the starting
point, not the conclusion &mdash; what follows is about whether the mix beats its parts.</p>''')

cm=R['corr']; ct=R['corr_tail']; ks=list(S)
P.append('<div class="divider"></div>\n<h2>II. Correlations</h2>\n'
 + tbl([[k]+[f"{cm[k][j]:.2f}" for j in ks] for k in ks], ['']+ks)
 + '<p style="margin-top:14px">And in the worst fifth of months for the portfolio:</p>\n'
 + tbl([[k]+[f"{ct[k][j]:.2f}" for j in ks] for k in ks], ['']+ks)
 + f'''\n<p>The pairwise average falls from
{np.mean([cm[a][b] for a in ks for b in ks if a<b]):.2f} to
{np.mean([ct[a][b] for a in ks for b in ks if a<b]):.2f} in the tail &mdash; the sleeves do not sink
together on a bad month. That is the whole reason the combination exists, and it is also the claim to
distrust first: three long-equity momentum books will correlate in a genuine systemic crash however they
behaved in this sample.</p>''')

best=R['grid_best']; se=R['se']
srt=sorted(R['grid'], key=lambda x:-x['sharpe'])[:14]
P.append('<div class="divider"></div>\n<h2>III. Weight Grid</h2>\n'
 + tbl([(f"{w['w'][0]}/{w['w'][1]}/{w['w'][2]}", pc(w['cagr']), f"{w['sharpe']:.3f}", neg(w['maxdd']))
        for w in srt], ['USA/CAN/GER','CAGR','Sharpe','MaxDD'], hl=lambda r: r[0]=='35/40/25')
 + f'''\n<p>Top of {len(R['grid'])} combinations on a 5% grid. The best reads Sharpe
{best['sharpe']:.3f} at {best['w'][0]}/{best['w'][1]}/{best['w'][2]}, but the standard error of a Sharpe
estimated from {R['n']} months is <strong>{se:.3f}</strong> &mdash; so <strong>{len(R['tied'])} of
{len(R['grid'])} combinations are statistically tied with it</strong>. Choosing between them on this
evidence is choosing noise.</p>''')

P.append('<div class="divider"></div>\n<h2>IV. Candidates</h2>\n'
 + tbl([(k, f"{v['w'][0]:.0f}/{v['w'][1]:.0f}/{v['w'][2]:.0f}", pc(v['cagr']), f"{v['vol']*100:.1f}%",
         f"{v['sharpe']:.2f}", neg(v['maxdd'])) for k,v in C.items()],
       ['','USA/CAN/GER','CAGR','Vol','Sharpe','MaxDD'], hl=lambda r: r[0]=='35/40/25')
 + '''\n<p>All four sit inside the tie. Every one roughly halves the drawdown of the best single sleeve
while landing between its CAGR and the weakest sleeve's.</p>''')

P.append('<div class="divider"></div>\n<h2>V. Walk-Forward &mdash; the test that decides</h2>\n'
 + f'''<p>Re-optimising the weights every January on the previous 60 months and holding them for the next
twelve, repeated across the sample &mdash; {W['n']} months out of sample:</p>\n'''
 + tbl([(k, pc(W[k]['cagr']), f"{W[k]['sharpe']:.2f}", neg(W[k]['maxdd']))
        for k in ('otimizado','equal','35/40/25')],
       ['Rule','CAGR','Sharpe','MaxDD'], hl=lambda r: r[0]=='35/40/25')
 + f'''\n<p><strong>Re-optimising loses.</strong> It gives up {W['equal']['sharpe']-W['otimizado']['sharpe']:.2f}
of Sharpe against simply holding equal weights and digs a drawdown
{(W['otimizado']['maxdd']-W['35/40/25']['maxdd'])*100:.1f} points deeper than the fixed 35/40/25. The
optimiser chases whatever did well in the training window and arrives after it has stopped working.
A fixed 35/40/25 beats both on every column.</p>''')

P.append('<div class="divider"></div>\n<h2>VI. The Optimal Balance</h2>\n'
 + f'''<p><strong>35/40/25 &mdash; USA, Canada, Germany.</strong> It is not the in-sample peak
({best['w'][0]}/{best['w'][1]}/{best['w'][2]} is, by {best['sharpe']-C['35/40/25']['sharpe']:.3f} of Sharpe,
a quarter of one standard error). It is the weight that wins the only test that looks forward: Sharpe
{W['35/40/25']['sharpe']:.2f} against {W['otimizado']['sharpe']:.2f} for the optimiser and
{W['equal']['sharpe']:.2f} for equal weights, with the shallowest drawdown of the three.</p>
<p>In-sample it delivers CAGR {pc(C['35/40/25']['cagr'])}, Sharpe {C['35/40/25']['sharpe']:.2f},
MaxDD {C['35/40/25']['maxdd']*100:.1f}% &mdash; against {neg(S['Canada']['maxdd'])} for the best sleeve
standing alone. Roughly two thirds of the return of the strongest leg, at half its drawdown.</p>
<p>Two things this does not say. It does not say 35/40/25 is better than 30/40/30 or 35/45/20 &mdash;
those are inside the tie and the data cannot separate them. And the drawdowns here are measured on
month-end values: the intra-month low is worse, by a factor of roughly 1.5 on the one sleeve where daily
data exists to check it.</p>''')

P.append('<div class="divider"></div>\n<h2>VII. Year by Year (35/40/25)</h2>\n'
 + tbl([(str(r['y']), pc(r['usa']), pc(r['can']), pc(r['ger']), f"<strong>{pc(r['port'])}</strong>")
        for r in R['yearly']], ['Year','USA','Canada','Germany','Portfolio'])
 + f"\n<p>{sum(1 for r in R['yearly'] if r['port']>0)} of {len(R['yearly'])} years positive.</p>")

P.append('<div class="divider"></div>\n<h2>VIII. Worst Months</h2>\n'
 + tbl([(r['m'], pc(r['USA']), pc(r['Canada']), pc(r['Germany']), f"<strong>{pc(r['port'])}</strong>",
         f"{sum(1 for k in ('USA','Canada','Germany') if r[k]<0)}/3")
        for r in R['worst_months']],
       ['Month','USA','Canada','Germany','Portfolio','Sleeves down'])
 + '''\n<p>Read the last column. Most bad months are one sleeve having a bad time; the months where all
three fall together are the ones that set the drawdown.</p>''')

P.append(f'''<div class="divider"></div>
<h2>IX. Provenance and Limitations</h2>
<ol class="steps">
<li><strong>Canada</strong> uses the harness series that the strategy publishes: CAGR +33.8%, Sharpe 1.19,
MaxDD &minus;26.0% &mdash; reproduced here exactly. The previous version of this report used a series with
a look-ahead in the NetIncome filter (it read the quarter's results on the day the quarter closed), which
showed &minus;24.5% and about 3pp more CAGR.</li>
<li><strong>Germany</strong> uses the live N=10 config with no liquidity filter: +19.1%, 0.72,
&minus;39.1%, reproduced exactly. The previous version used a fourth variant that exists nowhere else.</li>
<li><strong>USA does not reproduce exactly.</strong> The series here reads
{pc(S['USA']['cagr'])}/{S['USA']['sharpe']:.2f}/{S['USA']['maxdd']*100:.1f}% against the published
+25.6%/0.87/&minus;33.2%. The Sharpe matches to the decimal; the CAGR is 0.5pp and the drawdown 2.3pp
apart, and I could not locate which script produced the published pair. Treat the USA leg as
approximate.</li>
<li><strong>All weights are chosen in-sample</strong> over the same history the sleeves were built on.
The walk-forward in Section&nbsp;V is the mitigation, not a cure.</li>
<li><strong>Month-end drawdowns understate the experience.</strong></li>
<li><strong>The tail correlations are a sample, not a law.</strong> One systemic crash is in this window
(2008); the diversification held then, which is one observation.</li>
</ol>''')

import numpy as np
open(f'{SITE}/research/combined_portfolio_report.html','w').write(head+'\n'.join(P)+tail)
print("combined_portfolio_report.html regenerado")
