import json, numpy as np
SITE='/Users/luisabrantes/bivarcapital'
D=json.load(open('article_data.json')); C=json.load(open('art_charts.json'))
shell=open(f'{SITE}/research/germany_momentum_sensitivity.html').read()
head=shell[:shell.find('<p class="lead"')]
head=head.replace('Germany Momentum<span class="it">Parameter sensitivity analysis</span>',
                  'The Regime Filter<span class="it">130 rules, three markets, and why we changed nothing</span>')
import re
head=re.sub(r'(<title>)[^<]*(</title>)', r'\1Does the Regime Filter Work? — Bivar Capital\2', head)
head=re.sub(r'(content=")[^"]*(")', lambda m: m.group(1)+'We tested 130 ways to time three momentum strategies. The filters already running won in two of three, re-optimising lost everywhere, and two of our own results turned out to be look-ahead.'+m.group(2), head, count=3)
tail='\n<div class="footer">\n<p>Bivar Capital &mdash; Quantitative Research. Backtested performance, not a guarantee of future results, not investment advice.</p>\n</div>\n\n</div>\n</body>\n</html>\n'
MK=['USA','ALEMANHA','CANADA']; EN={'USA':'USA','ALEMANHA':'Germany','CANADA':'Canada'}
LIVE={'USA':'S&amp;P 500 MA250','ALEMANHA':'DAX MA200','CANADA':'TSX MA75'}
def n(x,d=1,s=False): return f"{x:+.{d}f}%" if s else f"{x:.{d}f}%"
def neg(x): return f'<span class="neg">{x:.1f}%</span>'
def tbl(rows,cols,hl=None):
    o=['<div class="table-wrap"><table><thead><tr>'+''.join(f'<th>{c}</th>' for c in cols)+'</tr></thead><tbody>']
    for r in rows: o.append(f'<tr{" class=\"hl-row\"" if hl and hl(r) else ""}>'+''.join(f'<td>{c}</td>' for c in r)+'</tr>')
    return '\n'.join(o)+'</tbody></table></div>'
S=[]
S.append('''<p class="lead">Every one of our momentum strategies stands aside when its index falls below a moving
average &mdash; MA250 in the US, MA200 in Germany, MA75 in Canada. Those windows were chosen years ago and never
revisited. This is what happened when we tried to beat them: roughly 130 rules across the three markets, including
everything in the literature we could implement. Two markets had nothing better. One had a single candidate that
survived. And the most useful result has nothing to do with which rule wins.</p>''')

S.append('<div class="divider"></div>\n<h2>I. What Was Tested</h2>\n'
 + tbl([('Moving-average windows','50 to 350 days, each market'),
        ('Hysteresis bands','&plusmn;2%, &plusmn;3%, &plusmn;5% around the average'),
        ('Crossovers','MA20/MA100, MA50/MA200, MA100/MA250'),
        ('Index momentum','6- and 12-month index return above zero'),
        ('Cross-market gates','the S&amp;P 500 as the gate for the DAX'),
        ('The strategy&rsquo;s own curve','its equity above its own 4- to 18-month average'),
        ('Asymmetric rules','one signal to enter, a different one to exit'),
        ('Convergence / divergence','the four states of index-signal &times; self-signal'),
        ('Volatility gates','index vol, strategy vol, downside vol, 3m/12m ratio, vol-of-vol, rising vol &mdash; at three thresholds each'),
        ('Barroso &amp; Santa-Clara (2015)','scale exposure to a constant strategy volatility'),
        ('Daniel &amp; Moskowitz (2016)','weight by &mu;/&sigma;&sup2;, and their bear-market-plus-high-vol crash state')],
       ['Family','Detail'])
 + '<p>Each was scored on the full history and on an out-of-sample window that drops the first five years, then put through a walk-forward.</p>')

S.append(f'''<div class="divider"></div>
<h2>II. The Windows That Run Are Not Peaks</h2>
<img src="{C['sweep']}">
<p>Sharpe against the moving-average window, one panel per market. In all three the live setting sits on a
broad shelf rather than a spike, and the curve falls away on both sides &mdash; MA50 and MA350 are materially
worse everywhere. Germany&rsquo;s best single window is MA150 at a Sharpe of 0.80 against MA200&rsquo;s 0.72, but the
standard error of a Sharpe estimated from 26 years is <strong>0.08</strong>, so that is one standard error, found
after trying eleven windows.</p>''')

rows=[]
for m in MK:
    f_,o=D[m]['full'],D[m]['oos']
    for l in ['MA que corre','MA na propria curva (9m)','os dois concordam','vol constante cap 1.0x','vol constante cap 1.5x','sempre investido']:
        rows.append((EN[m] if l=='MA que corre' else '', l.replace('MA que corre',LIVE[m]).replace('MA na propria curva (9m)','strategy&rsquo;s own 9m MA').replace('os dois concordam','both signals agree').replace('vol constante cap 1.0x','constant vol, cap 1.0&times;').replace('vol constante cap 1.5x','constant vol, cap 1.5&times;').replace('sempre investido','no filter at all'),
                     n(f_[l]['cagr'],1,True), f"{f_[l]['sharpe']:.2f}", neg(f_[l]['maxdd']),
                     n(o[l]['cagr'],1,True), f"{o[l]['sharpe']:.2f}", neg(o[l]['maxdd'])))
S.append('<div class="divider"></div>\n<h2>III. The Main Contenders</h2>\n'
 + tbl(rows, ['Market','Rule','CAGR','Sharpe','MaxDD','CAGR','Sharpe','MaxDD'],
       hl=lambda r: 'MA250' in r[1] or 'MA200' in r[1] or 'MA75' in r[1])
 + '<p>The first three numeric columns are the full history; the last three drop the first five years. '
   'Highlighted rows are the filters currently running.</p>')

S.append(f'''<div class="divider"></div>
<h2>IV. The Result That Matters</h2>
<img src="{C['wf']}">
<p>Re-optimising the rule every January on the previous sixty months, then holding it for twelve, repeated
across the sample. In all three markets the optimiser <strong>loses to simply leaving the filter alone</strong>:
{D['USA']['wf']['chosen']['sharpe']:.2f} against {D['USA']['wf']['fixed']['sharpe']:.2f} in the US,
{D['ALEMANHA']['wf']['chosen']['sharpe']:.2f} against {D['ALEMANHA']['wf']['fixed']['sharpe']:.2f} in Germany,
{D['CANADA']['wf']['chosen']['sharpe']:.2f} against {D['CANADA']['wf']['fixed']['sharpe']:.2f} in Canada.</p>
<p>This is the same finding that has now appeared four separate times in our work: on portfolio weights across
the three sleeves, on an S&amp;P put-writing study, on the Germany portfolio size, and here. <strong>The rule
that adapts arrives after the thing it was chasing has stopped working.</strong> It is a more reliable result
than anything about which moving average is best, because it reproduces.</p>''')

S.append(f'''<div class="divider"></div>
<h2>V. Two Results of Ours That Were Wrong</h2>
<h3>The self-referential filter that could never turn back on</h3>
<p>Gating on the strategy&rsquo;s own equity curve looked promising: it is the only family that catches Germany&rsquo;s
2023 and 2026, where the momentum cohort unwound while the index rose &mdash; a case a 200-day average cannot
see by construction. The first implementation returned &minus;1.5% a year with a Sharpe of &minus;25.8, identical
for every window, which is not a result but a symptom. When the filter switches off the book earns nothing and
pays costs, so the curve declines; a declining curve is always below its own average; it never switches back on.
The fix is to gate on the <em>unfiltered</em> curve &mdash; what the book would have done fully invested &mdash;
which asks &ldquo;is the strategy working&rdquo; rather than &ldquo;has my account been going up&rdquo;.</p>
<h3>A target volatility that knew the future</h3>
<p>Constant-volatility scaling needs a target. Ours was the median of the strategy&rsquo;s own volatility &mdash;
over the whole sample. That is look-ahead, and it was worth a great deal:</p>
{tbl([('US, cap 1.0&times;','0.95','&minus;24.1%','0.86','&minus;37.6%'),
      ('US, cap 1.5&times;','1.03','&minus;27.7%','0.95','&minus;37.6%')],
     ['','Sharpe','MaxDD','Sharpe','MaxDD'])}
<p>The first pair uses the full-sample median, the second an expanding median of past data only. The look-ahead
inflated Sharpe by 0.08 and <strong>invented the entire 13-point drawdown improvement</strong>. We had already
reported the first version before catching it.</p>''')

S.append(f'''<div class="divider"></div>
<h2>VI. The One Candidate That Survived</h2>
<img src="{C['expo']}">
<p>Scaling exposure by the inverse of the strategy&rsquo;s own six-month volatility, with an honest target, is the
only rule out of roughly 130 that improves the US sleeve on both return and risk out of sample:
Sharpe {D['USA']['oos']['vol constante cap 1.5x']['sharpe']:.2f} against
{D['USA']['oos']['MA que corre']['sharpe']:.2f}, drawdown
{D['USA']['oos']['vol constante cap 1.5x']['maxdd']:.1f}% against
{D['USA']['oos']['MA que corre']['maxdd']:.1f}%, winning {D['USA']['win_cap15'][0]}
of {D['USA']['win_cap15'][1]} rolling five-year windows.</p>
<p>It does not work in the other two. Canada&rsquo;s apparent gain disappears at cap 1.0&times;
(Sharpe {D['CANADA']['full']['vol constante cap 1.0x']['sharpe']:.2f} against
{D['CANADA']['full']['MA que corre']['sharpe']:.2f}) &mdash; what looked like risk management was leverage.
Germany wins {D['ALEMANHA']['win_cap15'][0]} of {D['ALEMANHA']['win_cap15'][1]} windows, a coin toss.</p>
<p>The lower panel shows what the rule would have done. It is at full exposure or above in 57% of months and
below half in 10%. It cut to 56% through Lehman. It also held <strong>36% to 55% exposure through most of the
run that produced this year&rsquo;s +221%</strong>, including 45% in a month the strategy returned +58.9%. The
Sharpe improves because volatility falls further than return does. This is not a rule that earns more; it is a
rule that swings less, and it is honest about the trade.</p>''')

S.append(f'''<div class="divider"></div>
<h2>VII. What We Changed</h2>
<p><strong>Nothing.</strong></p>
<p>Two of three markets had no rule that beat the filter already running, on either window. The third had one,
by 0.09 of Sharpe, found after roughly 130 attempts on a single 26-year history &mdash; which is about what one
would expect to find by chance at that number of trials. Adopting it would mean rebalancing exposure every month,
at a transaction cost the backtest charges and a margin cost it does not.</p>
<img src="{C['dd']}">
<p>There were two alternatives worth naming, both of which buy lower drawdown by giving up return, and neither of
which we took. Requiring both signals to agree cuts the drawdown in the US and Germany and makes it worse in
Canada. Constant-vol scaling at cap 1.0&times; &mdash; reduce only, never lever &mdash; cuts it in all three, at
a cost of 4 to 6 points of CAGR.</p>
<p>The case for changing nothing is not that the current filters are optimal. It is that we cannot demonstrate
anything is better, and the one piece of evidence that reproduced across every market and every test we ran is
that the rule which adapts does worse than the rule which does not.</p>''')

S.append('''<div class="divider"></div>
<h2>VIII. Limitations</h2>
<ol class="steps">
<li><strong>One history each.</strong> 26 years per market, heavily overlapping in time. Three markets is not
three independent tests of a regime rule &mdash; 2008 is in all of them.</li>
<li><strong>Roughly 130 trials.</strong> At a Sharpe standard error near 0.08, differences under 0.16 are noise
and should be read as such, including the one candidate we called a survivor.</li>
<li><strong>The self-curve rules are fitted to the drawdowns they are judged on.</strong> They were built after
seeing 2023 and 2026 fail.</li>
<li><strong>Costs are modelled, financing is not.</strong> Any rule with exposure above 100% borrows, and the
backtest charges no interest for it.</li>
<li><strong>Germany&rsquo;s pre-2015 data records no delistings at all</strong>, so its regime results before then
run on survivors.</li>
</ol>''')
open(f'{SITE}/research/regime_filter_study.html','w').write(head+'\n'.join(S)+tail)
print(f"escrito: {len(head+''.join(S)+tail):,} bytes")
