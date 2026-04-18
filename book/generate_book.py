#!/usr/bin/env python3
"""
Generate "What Still Works on Wall Street" as a professional PDF.
Uses matplotlib for charts (base64-embedded), weasyprint for PDF.
"""

import json
import io
import base64
import os
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ── Config ──────────────────────────────────────────────────────────────────
DATA_PATH = Path.home() / "bivarcapital/book/data/all_single_factors.json"
OUTPUT_HTML = Path.home() / "Desktop/what_still_works_on_wall_street.html"
OUTPUT_PDF = Path.home() / "Desktop/what_still_works_on_wall_street.pdf"

# Colors
BG = '#060608'
CARD_BG = '#0e0e12'
BORDER = '#1a1a22'
TEXT = '#e8e6e3'
TEXT_MUTED = '#8a8a8a'
GOLD = '#c4a265'
GREEN = '#4ade80'
RED = '#f87171'
BLUE = '#60a5fa'
PURPLE = '#a78bfa'

# ── Load data ───────────────────────────────────────────────────────────────
with open(DATA_PATH) as f:
    ALL_DATA = json.load(f)

# ── Chart helpers ───────────────────────────────────────────────────────────
def fig_to_base64(fig, dpi=150):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                facecolor=BG, edgecolor='none', pad_inches=0.3)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')

def style_ax(ax, title='', ylabel=''):
    ax.set_facecolor(BG)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color(BORDER)
    ax.spines['bottom'].set_color(BORDER)
    ax.tick_params(colors=TEXT_MUTED, labelsize=9)
    ax.yaxis.label.set_color(TEXT_MUTED)
    ax.xaxis.label.set_color(TEXT_MUTED)
    if title:
        ax.set_title(title, color=TEXT, fontsize=12, fontweight='bold', pad=12)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(axis='y', color=BORDER, linewidth=0.5, alpha=0.5)

def make_cagr_bar_chart(factor_name, d200m, d5b):
    """3-group bar chart: D1, Universe, D10 for both universes."""
    fig, ax = plt.subplots(figsize=(7, 3.5), facecolor=BG)
    style_ax(ax, f'{factor_name} — CAGR by Decile (2005–2026)', 'CAGR (%)')

    x = np.arange(3)
    w = 0.32
    labels = ['D1 (Cheap/Best)', 'Universe', 'D10 (Expensive/Worst)']

    vals_200 = [d200m['d1_cagr'], d200m['univ_cagr'], d200m['d10_cagr']]
    vals_5b = [d5b['d1_cagr'], d5b['univ_cagr'], d5b['d10_cagr']]

    colors_200 = [GREEN if d200m['spread'] > 1 else GOLD,
                  TEXT_MUTED,
                  RED if d200m['spread'] > 1 else GOLD]
    colors_5b = [GREEN if d5b['spread'] > 1 else BLUE,
                 TEXT_MUTED,
                 RED if d5b['spread'] > 1 else BLUE]

    bars1 = ax.bar(x - w/2, vals_200, w, color=GOLD, alpha=0.85, label='>$200M')
    bars2 = ax.bar(x + w/2, vals_5b, w, color=BLUE, alpha=0.85, label='>$5B')

    for bars in [bars1, bars2]:
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, h + 0.2,
                    f'{h:+.1f}%', ha='center', va='bottom',
                    color=TEXT, fontsize=8, fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.legend(loc='upper right', fontsize=8, facecolor=CARD_BG,
              edgecolor=BORDER, labelcolor=TEXT)
    ax.axhline(y=0, color=BORDER, linewidth=0.8)
    return fig_to_base64(fig)

def make_annual_chart(factor_name, d200m, d5b=None):
    """Year-by-year D1 vs D10 returns."""
    d1 = d200m['d1_annual']
    d10 = d200m['d10_annual']
    years = sorted(d1.keys())
    d1_vals = [d1[y] for y in years]
    d10_vals = [d10[y] for y in years]

    fig, ax = plt.subplots(figsize=(9, 3.5), facecolor=BG)
    style_ax(ax, f'{factor_name} — Annual Returns: D1 vs D10 (>$200M)', 'Return (%)')

    x = np.arange(len(years))
    w = 0.35
    ax.bar(x - w/2, d1_vals, w, color=GREEN, alpha=0.8, label='D1 (Cheap/Best)')
    ax.bar(x + w/2, d10_vals, w, color=RED, alpha=0.8, label='D10 (Expensive/Worst)')

    ax.set_xticks(x)
    ax.set_xticklabels(years, rotation=45, ha='right', fontsize=7)
    ax.legend(loc='best', fontsize=8, facecolor=CARD_BG,
              edgecolor=BORDER, labelcolor=TEXT)
    ax.axhline(y=0, color=TEXT_MUTED, linewidth=0.6, linestyle='--')
    return fig_to_base64(fig)

def make_spread_chart(factor_name, d200m, d5b=None):
    """Cumulative spread (D1 - D10) year by year."""
    d1 = d200m['d1_annual']
    d10 = d200m['d10_annual']
    years = sorted(d1.keys())
    spreads = [d1[y] - d10[y] for y in years]
    cum_spread = np.cumsum(spreads)

    fig, ax = plt.subplots(figsize=(9, 3), facecolor=BG)
    style_ax(ax, f'{factor_name} — Cumulative Spread (D1 − D10, >$200M)', 'Cumulative Spread (%)')

    colors = [GREEN if s >= 0 else RED for s in spreads]
    ax.bar(range(len(years)), spreads, color=colors, alpha=0.6, width=0.7)
    ax.plot(range(len(years)), cum_spread, color=GOLD, linewidth=2, marker='o',
            markersize=3, label='Cumulative')
    ax.axhline(y=0, color=TEXT_MUTED, linewidth=0.6, linestyle='--')

    ax.set_xticks(range(len(years)))
    ax.set_xticklabels(years, rotation=45, ha='right', fontsize=7)
    ax.legend(loc='best', fontsize=8, facecolor=CARD_BG,
              edgecolor=BORDER, labelcolor=TEXT)
    return fig_to_base64(fig)

def make_scorecard_chart():
    """Master scorecard: spread for all factors."""
    factors_200 = [
        ('P/S', ALL_DATA.get('P/S >$200M', {})),
        ('Buyback Y.', ALL_DATA.get('Buyback Yield >$200M', {})),
        ('SH Yield', ALL_DATA.get('SH Yield >$200M', {})),
        ('ROE', ALL_DATA.get('ROE >$200M', {})),
        ('EPS Growth', ALL_DATA.get('EPS Growth >$200M', {})),
        ('P/CF', ALL_DATA.get('P/CF (FCF) >$200M', {})),
        ('Accruals', ALL_DATA.get('Accruals/Price >$200M', {})),
        ('P/E', ALL_DATA.get('P/E >$200M', {})),
        ('EBITDA/EV', ALL_DATA.get('EBITDA/EV >$200M', {})),
        ('P/B', ALL_DATA.get('P/B >$200M', {})),
        ('Div Yield', ALL_DATA.get('Div Yield >$200M', {})),
        ('Profit Mgn', ALL_DATA.get('Profit Margin >$200M', {})),
    ]

    factors_5b = [
        ('P/S', ALL_DATA.get('P/S >$5B', {})),
        ('Buyback Y.', ALL_DATA.get('Buyback Yield >$5B', {})),
        ('SH Yield', ALL_DATA.get('SH Yield >$5B', {})),
        ('ROE', ALL_DATA.get('ROE >$5B', {})),
        ('EPS Growth', ALL_DATA.get('EPS Growth >$5B', {})),
        ('P/CF', ALL_DATA.get('P/CF (FCF) >$5B', {})),
        ('Accruals', ALL_DATA.get('Accruals/Price >$5B', {})),
        ('P/E', ALL_DATA.get('P/E >$5B', {})),
        ('EBITDA/EV', ALL_DATA.get('EBITDA/EV >$5B', {})),
        ('P/B', ALL_DATA.get('P/B >$5B', {})),
        ('Div Yield', ALL_DATA.get('Div Yield >$5B', {})),
        ('Profit Mgn', ALL_DATA.get('Profit Margin >$5B', {})),
    ]

    names = [f[0] for f in factors_200]
    spreads_200 = [f[1].get('spread', 0) for f in factors_200]
    spreads_5b = [f[1].get('spread', 0) for f in factors_5b]

    fig, ax = plt.subplots(figsize=(10, 5), facecolor=BG)
    style_ax(ax, 'Factor Scorecard — D1 vs D10 Spread (2005–2026)', 'Annual Spread (%)')

    x = np.arange(len(names))
    w = 0.35

    colors_200 = [GREEN if s > 1.5 else (RED if s < -0.5 else GOLD) for s in spreads_200]
    colors_5b = [GREEN if s > 1.5 else (RED if s < -0.5 else BLUE) for s in spreads_5b]

    bars1 = ax.bar(x - w/2, spreads_200, w, color=colors_200, alpha=0.85, label='>$200M')
    bars2 = ax.bar(x + w/2, spreads_5b, w, color=[c.replace('80', '60') if '#' in c else c for c in colors_5b], alpha=0.65, label='>$5B', edgecolor=colors_5b, linewidth=1.2)

    for bars in [bars1, bars2]:
        for bar in bars:
            h = bar.get_height()
            va = 'bottom' if h >= 0 else 'top'
            offset = 0.15 if h >= 0 else -0.15
            ax.text(bar.get_x() + bar.get_width()/2, h + offset,
                    f'{h:+.1f}', ha='center', va=va,
                    color=TEXT_MUTED, fontsize=6.5, fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=35, ha='right', fontsize=8)
    ax.axhline(y=0, color=TEXT_MUTED, linewidth=0.8, linestyle='--')
    ax.legend(loc='upper right', fontsize=8, facecolor=CARD_BG,
              edgecolor=BORDER, labelcolor=TEXT)
    return fig_to_base64(fig)

def make_base_rate_chart():
    """Rolling 5yr positive % for all factors."""
    factors = [
        ('P/S', ALL_DATA.get('P/S >$200M', {}), ALL_DATA.get('P/S >$5B', {})),
        ('Buyback', ALL_DATA.get('Buyback Yield >$200M', {}), ALL_DATA.get('Buyback Yield >$5B', {})),
        ('SH Yield', ALL_DATA.get('SH Yield >$200M', {}), ALL_DATA.get('SH Yield >$5B', {})),
        ('ROE', ALL_DATA.get('ROE >$200M', {}), ALL_DATA.get('ROE >$5B', {})),
        ('P/CF', ALL_DATA.get('P/CF (FCF) >$200M', {}), ALL_DATA.get('P/CF (FCF) >$5B', {})),
        ('EPS Gr.', ALL_DATA.get('EPS Growth >$200M', {}), ALL_DATA.get('EPS Growth >$5B', {})),
        ('Accruals', ALL_DATA.get('Accruals/Price >$200M', {}), ALL_DATA.get('Accruals/Price >$5B', {})),
        ('P/E', ALL_DATA.get('P/E >$200M', {}), ALL_DATA.get('P/E >$5B', {})),
        ('EBITDA/EV', ALL_DATA.get('EBITDA/EV >$200M', {}), ALL_DATA.get('EBITDA/EV >$5B', {})),
        ('P/B', ALL_DATA.get('P/B >$200M', {}), ALL_DATA.get('P/B >$5B', {})),
        ('Div Yield', ALL_DATA.get('Div Yield >$200M', {}), ALL_DATA.get('Div Yield >$5B', {})),
        ('Profit M.', ALL_DATA.get('Profit Margin >$200M', {}), ALL_DATA.get('Profit Margin >$5B', {})),
    ]

    names = [f[0] for f in factors]
    r5_200 = [f[1].get('r5_pos_pct', 0) for f in factors]
    r5_5b = [f[2].get('r5_pos_pct', 0) for f in factors]

    fig, ax = plt.subplots(figsize=(10, 4), facecolor=BG)
    style_ax(ax, 'Rolling 5-Year Base Rates — % of Windows Where D1 > D10', '% Positive')

    x = np.arange(len(names))
    w = 0.35
    ax.bar(x - w/2, r5_200, w, color=GOLD, alpha=0.85, label='>$200M')
    ax.bar(x + w/2, r5_5b, w, color=BLUE, alpha=0.85, label='>$5B')

    ax.axhline(y=50, color=RED, linewidth=1, linestyle='--', alpha=0.7, label='50% (coin flip)')
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=35, ha='right', fontsize=8)
    ax.set_ylim(0, 105)
    ax.legend(loc='upper right', fontsize=8, facecolor=CARD_BG,
              edgecolor=BORDER, labelcolor=TEXT)

    for i, (v200, v5b) in enumerate(zip(r5_200, r5_5b)):
        ax.text(i - w/2, v200 + 1.5, f'{v200:.0f}%', ha='center', va='bottom',
                color=TEXT_MUTED, fontsize=6.5)
        ax.text(i + w/2, v5b + 1.5, f'{v5b:.0f}%', ha='center', va='bottom',
                color=TEXT_MUTED, fontsize=6.5)

    return fig_to_base64(fig)


# ── Chapter content ─────────────────────────────────────────────────────────
# Each chapter: (id, title, factor_key_200m, factor_key_5b, book_claims, our_verdict, analysis)

CHAPTERS = [
    {
        'id': 'ch06',
        'title': 'Price-to-Earnings',
        'subtitle': 'The Most Popular Metric Has Zero Edge',
        'key200': 'P/E >$200M',
        'key5b': 'P/E >$5B',
        'status': 'DEAD',
        'status_color': RED,
        'book_claims': {
            'd1_cagr': '16.25%',
            'spread': '~10.7%',
            'base_rate_5yr': '92%',
            'base_rate_10yr': '99%',
            'sharpe': '0.61',
            'verdict': 'Low P/E stocks earn enormous premiums. "One true faith."',
        },
        'body': """
<p>O'Shaughnessy found that low P/E stocks turned $10,000 into $10.2 million over 46 years —
nearly $9M more than the All Stocks universe. The lowest P/E decile beat the universe 92% of
rolling 5-year periods and 99% of rolling 10-year periods. High P/E stocks returned just 5.53% —
worse than T-bills.</p>

<p>Our data tells a completely different story. The spread between cheap and expensive P/E stocks
is <strong>+0.5% at &gt;$200M and negative (-0.3%) at &gt;$5B</strong>. D1 barely beats D10 in 52%
of years — a coin flip. Rolling 5-year windows are positive only 47% of the time at &gt;$200M
and 35% at &gt;$5B.</p>

<h4>Why It Broke</h4>
<ul>
<li><strong>Earnings are the most manipulated line item.</strong> One-time charges, restructuring costs,
stock-based compensation, tax benefits — all distort EPS. A low P/E can mean genuinely cheap, or
temporarily inflated earnings about to revert.</li>
<li><strong>Non-monotonic relationship.</strong> In the book's data, returns declined smoothly D1→D10.
In our data, middle deciles often outperform both extremes.</li>
<li><strong>Period matters.</strong> 1964–2009 included long stretches where value dominated.
2005–2026 is dominated by growth/tech. P/E may be cyclical — but 21 years is a long drought.</li>
<li><strong>Low signal-to-noise.</strong> Other metrics (P/S, P/FCF) capture cheapness more cleanly
because they use less manipulable fundamentals.</li>
</ul>

<p>The factor that O'Shaughnessy called the foundation of value investing has produced
<strong>zero alpha</strong> in 21 years.</p>
""",
    },
    {
        'id': 'ch07',
        'title': 'EBITDA / Enterprise Value',
        'subtitle': 'The "Best Single Factor" Collapses',
        'key200': 'EBITDA/EV >$200M',
        'key5b': 'EBITDA/EV >$5B',
        'status': 'DEAD',
        'status_color': RED,
        'book_claims': {
            'd1_cagr': '16.58%',
            'spread': '~11%',
            'base_rate_5yr': '96%',
            'base_rate_10yr': '100%',
            'sharpe': '0.65',
            'verdict': '"Best on an absolute basis for all individual value factors."',
        },
        'body': """
<p>This was the crown jewel. O'Shaughnessy called EBITDA/EV "the best on an absolute basis for all
individual value factors." D1 beat the universe 96% of rolling 5-year periods and <strong>100% of
rolling 10-year periods</strong>. The best single value factor by every measure.</p>

<p>The collapse is total. At &gt;$200M, the spread is <strong>literally 0.0%</strong>. Cheap
EBITDA/EV stocks and expensive ones returned the identical amount over 21 years. At &gt;$5B there's
a marginal +0.6% spread — irrelevant compared to the +5.4% the book reported.</p>

<h4>Why It Broke</h4>
<ul>
<li><strong>EBITDA ignores stock-based compensation.</strong> In 1964, SBC was negligible. In 2025,
tech companies pay billions in SBC that doesn't flow through EBITDA. This makes tech look cheaper
on EV/EBITDA than it actually is, distorting the ranking.</li>
<li><strong>Enterprise value edge cases.</strong> Companies with large cash positions (tech) have
artificially low EV, inflating their EBITDA/EV. Companies with debt have higher EV, making them
look expensive even if earnings are strong.</li>
<li><strong>Capital structure neutrality became a bug.</strong> O'Shaughnessy praised EBITDA/EV for
being "neutral to capital structure." But in the zero-rate era (2009–2022), capital structure
stopped mattering. The metric's advantage vanished with its raison d'être.</li>
</ul>

<p>From the best single factor to zero spread. The collapse is complete.</p>
""",
    },
    {
        'id': 'ch08',
        'title': 'Price-to-Cash Flow',
        'subtitle': 'Once Reliable, Now Marginal',
        'key200': 'P/CF (FCF) >$200M',
        'key5b': 'P/CF (FCF) >$5B',
        'status': 'MARGINAL',
        'status_color': GOLD,
        'book_claims': {
            'd1_cagr': '16.25%',
            'spread': '~12.8%',
            'base_rate_5yr': '91%',
            'base_rate_10yr': '100%',
            'sharpe': '0.61',
            'verdict': '"Uniformly high base rates." 100% of rolling 10yr beat All Stocks.',
        },
        'body': """
<p>The book reported 100% of rolling 10-year periods where low P/CF beat the universe. D1 turned
$10,000 into $10.2 million. Cash flow was supposed to be "harder to manipulate than earnings" —
the same argument that supports P/S.</p>

<p>Our results show a near-zero spread. At &gt;$200M, D1 actually <em>underperforms</em> D10 by
0.4%. At &gt;$5B there's a thin +1.2% spread — down from the 12.8% the book reported.</p>

<p>The factor that beat the universe 100% of rolling 10-year periods now produces noise. Cash flow
calculations are sensitive to capex timing and working capital changes, which adds volatility
to the signal. P/S captures a cleaner version of the same "hard-to-manipulate fundamental" thesis.</p>
""",
    },
    {
        'id': 'ch09',
        'title': 'Price-to-Sales',
        'subtitle': 'The Dethroned King Reclaims the Crown',
        'key200': 'P/S >$200M',
        'key5b': 'P/S >$5B',
        'status': 'WORKS',
        'status_color': GREEN,
        'book_claims': {
            'd1_cagr': '14.49%',
            'spread': '~11.1%',
            'base_rate_5yr': '75%',
            'base_rate_10yr': '89%',
            'sharpe': '0.46',
            'verdict': '"Best single factor in 1st edition. Lost to EBITDA/EV in the 4th edition."',
        },
        'body': """
<p>In the 1st edition of <em>What Works on Wall Street</em>, P/S was the best single value factor.
By the 4th edition, O'Shaughnessy demoted it below EBITDA/EV after 2007–2008 hurt P/S stocks
disproportionately. He noted that "a few bad years dramatically changed results."</p>

<p>Irony: <strong>P/S is now the only single value factor that still works.</strong></p>

<p>The spread of +8.3% at &gt;$200M and +5.0% at &gt;$5B is the strongest of any individual metric
we tested. The rolling 5-year base rate of 82% is the highest in our dataset. D1 delivers
+14.1% CAGR at &gt;$200M — nearly matching the book's 14.49%.</p>

<h4>Why It Survived</h4>
<ul>
<li><strong>Revenue is the hardest fundamental to manipulate.</strong> You can game earnings with
accounting choices. You can game cash flow with capex timing. Revenue is revenue. The cleanest
signal survives the most crowded market.</li>
<li><strong>Revenue captures structural cheapness.</strong> A low P/S stock is genuinely cheap
relative to its economic footprint. It hasn't been inflated by leverage (unlike EBITDA/EV) or
distorted by one-time items (unlike P/E).</li>
<li><strong>Less arbitraged.</strong> Quantitative funds overwhelmingly screen on P/E and EV/EBITDA.
P/S gets less attention, preserving the premium.</li>
</ul>

<p>The dethroned king reclaims the crown. O'Shaughnessy's 1st edition was right all along.</p>
""",
    },
    {
        'id': 'ch10',
        'title': 'Price-to-Book',
        'subtitle': 'The Fama-French Foundation Is Inverted',
        'key200': 'P/B >$200M',
        'key5b': 'P/B >$5B',
        'status': 'INVERTED',
        'status_color': RED,
        'book_claims': {
            'd1_cagr': '11.33% (1927–2009)',
            'spread': '~5.3%',
            'base_rate_5yr': '66%',
            'base_rate_10yr': '77%',
            'sharpe': '0.22',
            'verdict': '"Works but with long subperiods of underperformance." Foundation of HML factor.',
        },
        'body': """
<p>Price-to-book is the academic foundation of value investing. The Fama-French HML (High Minus
Low book-to-market) factor has generated thousands of papers and trillions in AUM. O'Shaughnessy
noted it "works but with long subperiods of underperformance" — even in his data, decile 2
outperformed decile 1, and the 1927–1963 subperiod showed underperformance.</p>

<p>In our data, the factor has <strong>fully inverted</strong>. Expensive stocks (high P/B)
outperform cheap stocks (low P/B) by 0.7% at &gt;$200M and <strong>2.8% at &gt;$5B</strong>.
Only 32% of rolling 3-year windows show a positive value premium. The foundation of academic
value investing has negative returns.</p>

<h4>Why It Inverted</h4>
<p>In 1990, tangible assets made up 68% of S&amp;P 500 market value. Today, less than 10%.
A low P/B in 2025 means a company's only assets are physical — factories, inventory, real
estate in declining industries. High P/B means enormous intangible value (brand, IP, network
effects, software) that doesn't appear on the balance sheet.</p>

<p>Book value has become a marker for the <em>wrong</em> kind of company. P/B should be
<strong>removed from any value composite</strong> used today.</p>
""",
    },
    {
        'id': 'ch11',
        'title': 'Dividend Yield',
        'subtitle': 'Inverted at Small/Mid, Dead at Large',
        'key200': 'Div Yield >$200M',
        'key5b': 'Div Yield >$5B',
        'status': 'DEAD',
        'status_color': RED,
        'book_claims': {
            'd1_cagr': '11.77%',
            'spread': '~1.3%',
            'base_rate_5yr': '67%',
            'base_rate_10yr': '75%',
            'sharpe': '0.34',
            'verdict': '"Modest alpha but positive." Best when combined with quality screens.',
        },
        'body': """
<p>The book found modest alpha from high dividend yield — 11.77% vs 10.46% for the universe.
Even then, O'Shaughnessy noted that "decile 3 actually outperformed decile 1" (12.23% vs 11.77%),
suggesting the highest-yield stocks carry risk.</p>

<p>In our data, the modest edge has disappeared entirely. At &gt;$200M, high dividend stocks
<strong>underperform</strong> no-dividend stocks by 2.9% per year. D10 (low/no dividend) is
dominated by tech and growth — the biggest winners of 2005–2026.</p>

<p>At &gt;$5B the spread is -0.5% — essentially noise. Dividend yield has gone from modest
alpha generator to a contrarian indicator at smaller market caps.</p>

<p>The mechanism is clear: companies paying high dividends are often in slow-growth sectors
(utilities, staples, energy). Companies reinvesting every dollar into growth have dominated
the last two decades. The dividend premium requires a regime where income stocks are valued —
that regime hasn't existed since 2005.</p>
""",
    },
    {
        'id': 'ch12',
        'title': 'Buyback Yield',
        'subtitle': 'Share Shrinkage Still Signals Alpha',
        'key200': 'Buyback Yield >$200M',
        'key5b': 'Buyback Yield >$5B',
        'status': 'WORKS',
        'status_color': GREEN,
        'book_claims': {
            'd1_cagr': '13.69%',
            'spread': '~7.75%',
            'base_rate_5yr': '89%',
            'base_rate_10yr': '89%',
            'sharpe': '0.36',
            'verdict': '"One of the best single factors." Buyback indicates management confidence.',
        },
        'body': """
<p>The book found buyback yield delivered 13.69% CAGR with 89% positive rolling windows — one of
the strongest and most consistent factors tested. The mechanism: companies buying back shares
signal management confidence in undervaluation and return real cash to shareholders.</p>

<p>This is one of only two factors (with P/S) that <strong>fully survive out of sample</strong>.</p>

<p>Our spread of +7.9% at &gt;$200M and +5.2% at &gt;$5B is robust. The base rates are
extraordinary: <strong>100% of rolling 5-year windows are positive at &gt;$200M</strong>,
94% at &gt;$5B. D1 wins in 76% of individual years.</p>

<p>The flip side is equally powerful: D10 (net share issuers) return just +3.7% CAGR at &gt;$200M —
the worst-performing group in our entire dataset. <strong>Dilution is destruction.</strong></p>

<h4>Why It Survived</h4>
<ul>
<li><strong>Shares outstanding is objective and hard to manipulate.</strong> Unlike earnings or
cash flow, the share count is a simple fact. When it goes down, real value accrues to remaining
shareholders.</li>
<li><strong>Skin in the game signal.</strong> Management teams buying back stock at scale are
making a capital allocation bet. If they're wrong, they waste corporate cash. The signal is
credible precisely because it has consequences.</li>
<li><strong>Less crowded.</strong> Dividend yield is on every Bloomberg terminal screen. Buyback
yield requires computation. Less attention = more persistent alpha.</li>
</ul>
""",
    },
    {
        'id': 'ch13',
        'title': 'Shareholder Yield',
        'subtitle': 'Works — But Buyback Alone Is Cleaner',
        'key200': 'SH Yield >$200M',
        'key5b': 'SH Yield >$5B',
        'status': 'WORKS*',
        'status_color': GOLD,
        'book_claims': {
            'd1_cagr': '13.22%',
            'spread': '~7.15%',
            'base_rate_5yr': '86%',
            'base_rate_10yr': '93%',
            'sharpe': '0.42',
            'verdict': '"Superior to dividend or buyback alone." Lower risk, better risk-adjusted returns.',
        },
        'body': """
<p>O'Shaughnessy's innovation was combining dividends and buybacks into shareholder yield.
The book found it delivered 13.22% CAGR with better risk-adjusted returns than either
component alone — Sharpe of 0.42 vs 0.36 for buybacks and 0.34 for dividends.</p>

<p>Our results show SH yield works with the right calculation — a +4.0% spread at &gt;$200M
and +5.2% at &gt;$5B using ncfcommon TTM / marketcap. However, the sign of the spread is
<strong>highly sensitive to methodology</strong>. With different buyback calculations,
the spread can invert.</p>

<p>The core issue: <strong>buyback yield alone works just as well or better</strong> than the
combined shareholder yield. Adding dividend yield introduces noise from slow-growth sectors.
Companies paying high dividends tend to be in utilities and staples — the addition dilutes the
cleaner buyback signal.</p>

<p>O'Shaughnessy's innovation of combining dividends and buybacks was ahead of its time.
But in practice, just tracking buybacks alone gives a more robust signal.</p>
""",
    },
    {
        'id': 'ch14',
        'title': 'Accruals-to-Price',
        'subtitle': 'The Earnings Quality Signal Is Too Weak',
        'key200': 'Accruals/Price >$200M',
        'key5b': 'Accruals/Price >$5B',
        'status': 'MARGINAL',
        'status_color': GOLD,
        'book_claims': {
            'd1_cagr': 'Positive (not precisely stated)',
            'spread': 'Modest',
            'base_rate_5yr': 'N/A',
            'base_rate_10yr': 'N/A',
            'sharpe': 'N/A',
            'verdict': 'Low accruals = high earnings quality → outperformance.',
        },
        'body': """
<p>The accruals anomaly is rooted in earnings quality research: companies with high accruals
(large gap between earnings and cash flow) are more likely to have manipulated earnings. Low
accruals signal genuine, cash-backed profitability.</p>

<p>The signal exists but it's too weak to trade on. A +0.9% spread at &gt;$200M and +1.2% at
&gt;$5B is barely above noise. Rolling 5-year windows are positive 65% of the time — better
than a coin flip, but not reliable enough for a standalone strategy.</p>

<p>Earnings quality matters in theory. In practice, the accruals-to-price ratio doesn't generate
enough differentiation to be useful alone. It may add marginal value in a multi-factor model,
but it's not a factor you'd build a strategy around.</p>
""",
    },
    {
        'id': 'ch17',
        'title': 'Earnings Growth',
        'subtitle': 'Confirmed: Growth Expectations Are Priced In',
        'key200': 'EPS Growth >$200M',
        'key5b': 'EPS Growth >$5B',
        'status': 'WEAK',
        'status_color': GOLD,
        'book_claims': {
            'd1_cagr': '11.88%',
            'spread': '~0.66%',
            'base_rate_5yr': '58%',
            'base_rate_10yr': '61%',
            'sharpe': '0.31',
            'verdict': '"Not a good investment factor." High growth expectations get bid up too far.',
        },
        'body': """
<p>This was one of O'Shaughnessy's <em>negative</em> findings. He argued that stocks with
the highest EPS growth don't systematically outperform — investors bid up high-growth stocks
too far, and when growth slows, they crash. Base rates were barely above a coin flip at
58% (5yr) and 61% (10yr).</p>

<p>Our data confirms this finding. The +3.0% spread at &gt;$200M and +1.8% at &gt;$5B
is modest and inconsistent — only 59% of 5-year windows at &gt;$200M and just 35% at &gt;$5B
are positive.</p>

<p>Earnings growth is backward-looking. Strong past growth often means the easy gains
have already been captured and priced in. The book was right: buying stocks solely for
their growth track record is not a reliable strategy.</p>
""",
    },
    {
        'id': 'ch18',
        'title': 'Profit Margins',
        'subtitle': 'Confirmed and Worsened: High Margins Predict Underperformance',
        'key200': 'Profit Margin >$200M',
        'key5b': 'Profit Margin >$5B',
        'status': 'INVERTED',
        'status_color': RED,
        'book_claims': {
            'd1_cagr': '10.31%',
            'spread': '-0.91%',
            'base_rate_5yr': '47%',
            'base_rate_10yr': '48%',
            'sharpe': '0.31',
            'verdict': '"High net profit margins underperform All Stocks." Negative finding confirmed.',
        },
        'body': """
<p>O'Shaughnessy found that high-margin stocks returned 10.31% vs 11.22% for the universe —
a negative finding. Base rates were below 50%, worse than random. He noted that mid-range
margin deciles (especially decile 7) actually outperformed the highest margins.</p>

<p>Our data shows this has <strong>gotten significantly worse</strong>. At &gt;$200M, the spread
is -1.1%. At &gt;$5B, it's <strong>-3.0%</strong> — the most negative of any factor.
Only <strong>6% of rolling 5-year windows at &gt;$5B are positive</strong>. Six percent.
This is the worst base rate in our entire dataset.</p>

<p>High margins often signal "no reinvestment opportunities" — the company is extracting
value rather than creating it. In a market that rewards growth and reinvestment, being highly
profitable but static is a liability.</p>

<p>The book was right. The finding has gotten worse, not better.</p>
""",
    },
    {
        'id': 'ch19',
        'title': 'Return on Equity',
        'subtitle': 'Modest and Inconsistent, as Predicted',
        'key200': 'ROE >$200M',
        'key5b': 'ROE >$5B',
        'status': 'WEAK',
        'status_color': GOLD,
        'book_claims': {
            'd1_cagr': '12.29%',
            'spread': '~6.1%',
            'base_rate_5yr': '63% (3yr)',
            'base_rate_10yr': '51%',
            'sharpe': '0.35',
            'verdict': '"Not a reliable standalone factor." Base rates deteriorate over longer periods.',
        },
        'body': """
<p>O'Shaughnessy found ROE delivered 12.29% CAGR but warned that base rates deteriorated over
longer periods — from 63% at 3 years down to 51% at 10 years. He concluded it was "not reliable
standalone" and that the main value was avoiding the lowest ROE decile (6.16% CAGR).</p>

<p>Our data confirms: +2.8% spread at &gt;$200M, fading to +1.3% at &gt;$5B. The 82% rolling
5-year positive rate at &gt;$200M is actually decent, but at &gt;$5B it drops to 65%.</p>

<p>ROE works better as part of a quality composite than alone. The book's assessment stands:
not reliable standalone, but useful as a secondary signal.</p>
""",
    },
]

# Momentum doesn't have standard decile data in the JSON — use custom content
MOMENTUM_CHAPTER = {
    'id': 'ch20',
    'title': 'Price Momentum',
    'subtitle': 'The Strongest Factor — Confirmed',
    'status': 'WORKS',
    'status_color': GREEN,
}

COMPOSITES_CHAPTER = {
    'id': 'ch15',
    'title': 'Value Composites',
    'subtitle': 'The Whole Is Less Than Its Best Parts',
    'status': 'DIMINISHED',
    'status_color': GOLD,
}

TV_CHAPTER = {
    'id': 'ch27',
    'title': 'Trending Value',
    'subtitle': '13.8%, Not 21% — But Still Real Alpha',
    'status': 'WORKS*',
    'status_color': GREEN,
}


# ── HTML generation ─────────────────────────────────────────────────────────

def generate_html():
    # Pre-generate charts
    scorecard_img = make_scorecard_chart()
    baserate_img = make_base_rate_chart()

    chapter_charts = {}
    for ch in CHAPTERS:
        k200 = ch['key200']
        k5b = ch['key5b']
        d200 = ALL_DATA.get(k200, {})
        d5b = ALL_DATA.get(k5b, {})
        if d200 and d5b:
            cagr_img = make_cagr_bar_chart(ch['title'], d200, d5b)
            annual_img = make_annual_chart(ch['title'], d200)
            spread_img = make_spread_chart(ch['title'], d200)
            chapter_charts[ch['id']] = (cagr_img, annual_img, spread_img)

    # Build HTML
    html_parts = []

    # --- CSS ---
    css = f"""
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    @page {{
        size: A4;
        margin: 2cm 2.5cm;
        @bottom-center {{
            content: counter(page);
            color: {TEXT_MUTED};
            font-family: 'Inter', sans-serif;
            font-size: 9px;
        }}
    }}

    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        background: {BG};
        color: {TEXT};
        font-size: 11pt;
        line-height: 1.65;
        -webkit-font-smoothing: antialiased;
    }}

    .page-break {{ page-break-after: always; }}

    /* Cover */
    .cover {{
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        min-height: 90vh;
        text-align: center;
        padding: 4rem 2rem;
    }}
    .cover h1 {{
        font-size: 2.8rem;
        font-weight: 700;
        color: {GOLD};
        line-height: 1.2;
        margin-bottom: 0.5rem;
        letter-spacing: -0.02em;
    }}
    .cover .subtitle {{
        font-size: 1.15rem;
        color: {TEXT_MUTED};
        font-weight: 300;
        margin-bottom: 3rem;
        max-width: 500px;
    }}
    .cover .meta {{
        font-size: 0.9rem;
        color: {TEXT_MUTED};
        line-height: 1.8;
    }}
    .cover .meta strong {{ color: {TEXT}; font-weight: 500; }}
    .cover .rule {{
        width: 80px;
        height: 2px;
        background: {GOLD};
        margin: 2rem auto;
    }}

    /* Chapter headers */
    .chapter {{
        padding: 0 0 2rem 0;
        margin-bottom: 1rem;
    }}
    .chapter-header {{
        border-bottom: 2px solid {GOLD};
        padding-bottom: 1rem;
        margin-bottom: 1.5rem;
    }}
    .chapter-num {{
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.15em;
        color: {GOLD};
        font-weight: 600;
        margin-bottom: 0.25rem;
    }}
    .chapter-title {{
        font-size: 1.8rem;
        font-weight: 700;
        color: {TEXT};
        line-height: 1.2;
        margin-bottom: 0.25rem;
    }}
    .chapter-subtitle {{
        font-size: 1rem;
        color: {TEXT_MUTED};
        font-weight: 300;
        font-style: italic;
    }}

    /* Status badge */
    .status-badge {{
        display: inline-block;
        padding: 0.2rem 0.8rem;
        border-radius: 4px;
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        margin-top: 0.5rem;
    }}

    /* Content */
    h3 {{
        font-size: 1.1rem;
        font-weight: 600;
        color: {GOLD};
        margin: 1.5rem 0 0.75rem 0;
        letter-spacing: -0.01em;
    }}
    h4 {{
        font-size: 0.95rem;
        font-weight: 600;
        color: {TEXT};
        margin: 1.2rem 0 0.5rem 0;
    }}
    p {{
        margin-bottom: 0.75rem;
    }}
    ul {{
        margin: 0.5rem 0 1rem 1.5rem;
    }}
    li {{
        margin-bottom: 0.4rem;
    }}
    strong {{ color: {TEXT}; }}

    /* Tables */
    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 1rem 0 1.5rem 0;
        font-size: 0.85rem;
    }}
    th {{
        background: {CARD_BG};
        color: {GOLD};
        font-weight: 600;
        text-align: left;
        padding: 0.5rem 0.75rem;
        border-bottom: 2px solid {BORDER};
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    td {{
        padding: 0.4rem 0.75rem;
        border-bottom: 1px solid {BORDER};
        color: {TEXT};
    }}
    tr:hover {{ background: {CARD_BG}; }}
    .num-positive {{ color: {GREEN}; font-weight: 600; }}
    .num-negative {{ color: {RED}; font-weight: 600; }}
    .num-neutral {{ color: {GOLD}; font-weight: 600; }}

    /* Charts */
    .chart-container {{
        margin: 1.5rem 0;
        text-align: center;
    }}
    .chart-container img {{
        max-width: 100%;
        border-radius: 4px;
        border: 1px solid {BORDER};
    }}

    /* Verdict box */
    .verdict-box {{
        background: {CARD_BG};
        border-left: 4px solid {GOLD};
        padding: 1rem 1.25rem;
        margin: 1.5rem 0;
        border-radius: 0 4px 4px 0;
    }}
    .verdict-box.green {{ border-left-color: {GREEN}; }}
    .verdict-box.red {{ border-left-color: {RED}; }}

    /* Section divider */
    .section-divider {{
        text-align: center;
        margin: 2rem 0;
        color: {GOLD};
        font-size: 1.2rem;
        letter-spacing: 0.5em;
    }}

    /* TOC */
    .toc {{
        padding: 2rem 0;
    }}
    .toc h2 {{
        font-size: 1.4rem;
        color: {GOLD};
        margin-bottom: 1.5rem;
        font-weight: 600;
    }}
    .toc-item {{
        display: flex;
        justify-content: space-between;
        padding: 0.4rem 0;
        border-bottom: 1px dotted {BORDER};
        font-size: 0.9rem;
    }}
    .toc-item .toc-status {{
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.05em;
    }}
    """

    html_parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>What Still Works on Wall Street</title>
<style>{css}</style>
</head>
<body>
""")

    # ─── COVER ───
    html_parts.append(f"""
<div class="cover">
    <h1>What Still Works<br>on Wall Street</h1>
    <p class="subtitle">A Retest of Every Strategy from O'Shaughnessy's Classic with 21 Years of Modern Data</p>
    <div class="rule"></div>
    <div class="meta">
        <strong>Bivar Capital Research</strong><br>
        Luís Abrantes Portugal<br>
        April 2026<br><br>
        <em>Data: Sharadar US Equities (2005–2026)</em><br>
        <em>Universe: US common stocks, ex-financials for value tests</em><br>
        <em>Methodology: Quarterly TTM, 12-monthly averaged annual rebalance</em>
    </div>
</div>
<div class="page-break"></div>
""")

    # ─── TABLE OF CONTENTS ───
    toc_items = []
    for ch in CHAPTERS:
        color = ch['status_color']
        toc_items.append(f"""
        <div class="toc-item">
            <span>{ch['title']}</span>
            <span class="toc-status" style="color:{color}">{ch['status']}</span>
        </div>""")
    toc_items.append(f"""
        <div class="toc-item">
            <span>Price Momentum</span>
            <span class="toc-status" style="color:{GREEN}">WORKS</span>
        </div>""")
    toc_items.append(f"""
        <div class="toc-item">
            <span>Value Composites</span>
            <span class="toc-status" style="color:{GOLD}">DIMINISHED</span>
        </div>""")
    toc_items.append(f"""
        <div class="toc-item">
            <span>Trending Value</span>
            <span class="toc-status" style="color:{GREEN}">WORKS*</span>
        </div>""")

    html_parts.append(f"""
<div class="toc">
    <h2>Contents</h2>
    {''.join(toc_items)}
</div>
<div class="page-break"></div>
""")

    # ─── EXECUTIVE SUMMARY ───
    html_parts.append(f"""
<div class="chapter">
    <div class="chapter-header">
        <div class="chapter-num">Executive Summary</div>
        <div class="chapter-title">The Value Premium Is Dead. Long Live What Survives.</div>
    </div>

    <div class="verdict-box red">
        <strong>Central Finding:</strong> The value premium, as traditionally measured, has largely
        disappeared. Of the 6 value factors in O'Shaughnessy's VC2 composite, 4 are broken or inverted.
        The factors that survive — P/S, Buyback Yield, and Momentum — share one trait: they're built on
        the hardest-to-manipulate fundamentals.
    </div>

    <p>We retested every single-factor strategy from <em>What Works on Wall Street</em> (4th Edition)
    using Sharadar US equity data from 2005 to 2026. Our methodology: quarterly TTM fundamentals,
    decile portfolios, 12-month averaged annual rebalance to eliminate timing bias, with universe
    filters of &gt;$200M and &gt;$5B market capitalization. Financials excluded for value tests.</p>

    <h3>The Scorecard</h3>
    <div class="chart-container">
        <img src="data:image/png;base64,{scorecard_img}" alt="Factor Scorecard">
    </div>

    <table>
        <tr>
            <th>Factor</th><th>Book CAGR</th><th>Our D1 CAGR (&gt;$200M)</th>
            <th>Spread</th><th>5yr Base Rate</th><th>Status</th>
        </tr>""")

    scorecard_rows = [
        ('P/S', '14.49%', 'P/S >$200M', GREEN, 'WORKS'),
        ('Buyback Yield', '13.69%', 'Buyback Yield >$200M', GREEN, 'WORKS'),
        ('SH Yield', '13.22%', 'SH Yield >$200M', GOLD, 'WORKS*'),
        ('Momentum 6-1', '14.52%', None, GREEN, 'WORKS'),
        ('ROE', '12.29%', 'ROE >$200M', GOLD, 'WEAK'),
        ('EPS Growth', '11.88%', 'EPS Growth >$200M', GOLD, 'WEAK'),
        ('P/CF', '16.25%', 'P/CF (FCF) >$200M', GOLD, 'MARGINAL'),
        ('Accruals', 'Positive', 'Accruals/Price >$200M', GOLD, 'MARGINAL'),
        ('P/E', '16.25%', 'P/E >$200M', RED, 'DEAD'),
        ('EBITDA/EV', '16.58%', 'EBITDA/EV >$200M', RED, 'DEAD'),
        ('Div Yield', '11.77%', 'Div Yield >$200M', RED, 'DEAD'),
        ('P/B', '11.33%', 'P/B >$200M', RED, 'INVERTED'),
        ('Profit Margin', '10.31%', 'Profit Margin >$200M', RED, 'INVERTED'),
    ]

    for name, book_cagr, key, color, status in scorecard_rows:
        if key and key in ALL_DATA:
            d = ALL_DATA[key]
            d1 = f"+{d['d1_cagr']:.1f}%" if d['d1_cagr'] > 0 else f"{d['d1_cagr']:.1f}%"
            sp = d['spread']
            sp_str = f"+{sp:.1f}%" if sp > 0 else f"{sp:.1f}%"
            sp_class = 'num-positive' if sp > 1.5 else ('num-negative' if sp < -0.5 else 'num-neutral')
            r5 = f"{d['r5_pos_pct']:.0f}%"
        elif name == 'Momentum 6-1':
            d1 = '+13.5%'
            sp_str = '+10.9%'
            sp_class = 'num-positive'
            r5 = 'N/A (monthly)'
        else:
            d1 = sp_str = r5 = 'N/A'
            sp_class = 'num-neutral'

        html_parts.append(f"""
        <tr>
            <td><strong>{name}</strong></td>
            <td>{book_cagr}</td>
            <td>{d1}</td>
            <td class="{sp_class}">{sp_str}</td>
            <td>{r5}</td>
            <td style="color:{color}; font-weight:700;">{status}</td>
        </tr>""")

    html_parts.append(f"""
    </table>

    <h3>Base Rates Tell the Real Story</h3>
    <div class="chart-container">
        <img src="data:image/png;base64,{baserate_img}" alt="Base Rate Chart">
    </div>

    <p>The red dashed line at 50% represents a coin flip. Any factor below that line has
    <em>negative</em> predictive power in rolling 5-year windows. P/B, Dividend Yield, and
    Profit Margin are firmly below. Only P/S (82%), Buyback Yield (100%), and ROE (82%)
    show reliable long-term consistency at &gt;$200M.</p>

    <h3>What This Means for Investors</h3>
    <p>A modern value composite should use <strong>only P/S + Buyback Yield</strong>. Adding
    P/E, P/B, EBITDA/EV, or Dividend Yield makes the composite worse by diluting the two
    signals that actually work. Combined with momentum, the surviving factors still generate
    meaningful alpha — but the era of 17–21% backtested CAGRs from broad value composites
    is over.</p>
</div>
<div class="page-break"></div>
""")

    # ─── INDIVIDUAL FACTOR CHAPTERS ───
    for ch in CHAPTERS:
        k200 = ch['key200']
        k5b = ch['key5b']
        d200 = ALL_DATA.get(k200, {})
        d5b = ALL_DATA.get(k5b, {})

        verdict_class = 'green' if ch['status'] in ('WORKS',) else ('red' if ch['status'] in ('DEAD', 'INVERTED') else '')

        html_parts.append(f"""
<div class="chapter">
    <div class="chapter-header">
        <div class="chapter-num">Chapter {ch['id'][2:]}</div>
        <div class="chapter-title">{ch['title']}</div>
        <div class="chapter-subtitle">{ch['subtitle']}</div>
        <span class="status-badge" style="background:{ch['status_color']}22; color:{ch['status_color']}">{ch['status']}</span>
    </div>

    <div class="verdict-box {verdict_class}">
        <strong>Verdict: {ch['status']}</strong> — Book D1 CAGR: {ch['book_claims']['d1_cagr']} → Our D1:
        +{d200.get('d1_cagr', 0):.1f}% (&gt;$200M), +{d5b.get('d1_cagr', 0):.1f}% (&gt;$5B).
        Spread: {d200.get('spread', 0):+.1f}% (&gt;$200M), {d5b.get('spread', 0):+.1f}% (&gt;$5B).
    </div>

    <h3>What the Book Claims (1964–2009)</h3>
    <table>
        <tr><th>Metric</th><th>Book Value</th></tr>
        <tr><td>D1 CAGR (All Stocks)</td><td>{ch['book_claims']['d1_cagr']}</td></tr>
        <tr><td>D1–D10 Spread</td><td>{ch['book_claims']['spread']}</td></tr>
        <tr><td>Rolling 5yr Base Rate</td><td>{ch['book_claims']['base_rate_5yr']}</td></tr>
        <tr><td>Rolling 10yr Base Rate</td><td>{ch['book_claims']['base_rate_10yr']}</td></tr>
        <tr><td>Sharpe Ratio</td><td>{ch['book_claims']['sharpe']}</td></tr>
        <tr><td>Conclusion</td><td><em>{ch['book_claims']['verdict']}</em></td></tr>
    </table>

    <h3>What We Found (2005–2026, Quarterly TTM)</h3>
    <table>
        <tr><th></th><th>D1 CAGR</th><th>D10 CAGR</th><th>Spread</th><th>vs Universe</th><th>D1 Wins</th><th>5yr Base Rate</th></tr>
        <tr>
            <td><strong>&gt;$200M</strong></td>
            <td class="{'num-positive' if d200.get('d1_cagr',0) > d200.get('univ_cagr',0) else 'num-neutral'}">{d200.get('d1_cagr',0):+.1f}%</td>
            <td>{d200.get('d10_cagr',0):+.1f}%</td>
            <td class="{'num-positive' if d200.get('spread',0)>1.5 else ('num-negative' if d200.get('spread',0)<-0.5 else 'num-neutral')}">{d200.get('spread',0):+.1f}%</td>
            <td>{d200.get('alpha_vs_univ',0):+.1f}%</td>
            <td>{d200.get('d1_wins_pct',0):.0f}%</td>
            <td>{d200.get('r5_pos_pct',0):.0f}%</td>
        </tr>
        <tr>
            <td><strong>&gt;$5B</strong></td>
            <td class="{'num-positive' if d5b.get('d1_cagr',0) > d5b.get('univ_cagr',0) else 'num-neutral'}">{d5b.get('d1_cagr',0):+.1f}%</td>
            <td>{d5b.get('d10_cagr',0):+.1f}%</td>
            <td class="{'num-positive' if d5b.get('spread',0)>1.5 else ('num-negative' if d5b.get('spread',0)<-0.5 else 'num-neutral')}">{d5b.get('spread',0):+.1f}%</td>
            <td>{d5b.get('alpha_vs_univ',0):+.1f}%</td>
            <td>{d5b.get('d1_wins_pct',0):.0f}%</td>
            <td>{d5b.get('r5_pos_pct',0):.0f}%</td>
        </tr>
    </table>
""")

        # Charts
        if ch['id'] in chapter_charts:
            cagr_img, annual_img, spread_img = chapter_charts[ch['id']]
            html_parts.append(f"""
    <div class="chart-container">
        <img src="data:image/png;base64,{cagr_img}" alt="{ch['title']} CAGR">
    </div>
    <div class="chart-container">
        <img src="data:image/png;base64,{annual_img}" alt="{ch['title']} Annual">
    </div>
    <div class="chart-container">
        <img src="data:image/png;base64,{spread_img}" alt="{ch['title']} Spread">
    </div>
""")

        # Body text
        html_parts.append(f"""
    <h3>Analysis</h3>
    {ch['body']}

    <h3>Book vs Reality</h3>
    <table>
        <tr><th>Metric</th><th>O'Shaughnessy (1964–2009)</th><th>Our Results (2005–2026)</th></tr>
        <tr><td>D1 CAGR</td><td>{ch['book_claims']['d1_cagr']}</td><td>{d200.get('d1_cagr',0):+.1f}% (&gt;$200M)</td></tr>
        <tr><td>D1–D10 Spread</td><td>{ch['book_claims']['spread']}</td><td>{d200.get('spread',0):+.1f}%</td></tr>
        <tr><td>5yr Base Rate</td><td>{ch['book_claims']['base_rate_5yr']}</td><td>{d200.get('r5_pos_pct',0):.0f}%</td></tr>
        <tr><td>Sharpe</td><td>{ch['book_claims']['sharpe']}</td><td>N/A (annual)</td></tr>
    </table>
</div>
<div class="page-break"></div>
""")

    # ─── MOMENTUM CHAPTER ───
    html_parts.append(f"""
<div class="chapter">
    <div class="chapter-header">
        <div class="chapter-num">Chapter 20</div>
        <div class="chapter-title">Price Momentum</div>
        <div class="chapter-subtitle">The Strongest Factor — Confirmed</div>
        <span class="status-badge" style="background:{GREEN}22; color:{GREEN}">WORKS</span>
    </div>

    <div class="verdict-box green">
        <strong>Verdict: WORKS</strong> — Momentum 6-1 delivers +13.5% CAGR at &gt;$5B with monthly
        rebalance (book: 14.52%). The strongest standalone factor in both the book and our data.
        With concentration and filters: up to +18.1% CAGR.
    </div>

    <h3>What the Book Claims (1927–2009)</h3>
    <table>
        <tr><th>Metric</th><th>Book Value</th></tr>
        <tr><td>D1 CAGR (6-month momentum)</td><td>14.11% (1927–2009) / 14.52% (subperiod)</td></tr>
        <tr><td>D10 CAGR (worst momentum)</td><td>4.15% — worse than T-bills</td></tr>
        <tr><td>Rolling 5yr Base Rate</td><td>87%</td></tr>
        <tr><td>Rolling 10yr Base Rate</td><td>98%</td></tr>
        <tr><td>Sharpe Ratio</td><td>0.37</td></tr>
        <tr><td>Conclusion</td><td><em>"Strongest standalone growth factor. Potent but highly volatile."</em></td></tr>
    </table>

    <h3>What We Found (2005–2026, Monthly Rebalance)</h3>
    <table>
        <tr><th>Configuration</th><th>CAGR</th><th>Sharpe</th><th>Max DD</th></tr>
        <tr>
            <td>Mom 6-1, 25 stocks, &gt;$200M</td>
            <td>+10.8%</td><td>0.55</td><td>-68.6%</td>
        </tr>
        <tr>
            <td>Mom 6-1, 25 stocks, &gt;$1B</td>
            <td>+13.0%</td><td>0.55</td><td>-68.6%</td>
        </tr>
        <tr>
            <td><strong>Mom 6-1, 25 stocks, &gt;$5B</strong></td>
            <td class="num-positive"><strong>+13.5%</strong></td><td><strong>0.68</strong></td><td>-64.3%</td>
        </tr>
    </table>

    <h3>Enhanced Variants (&gt;$5B)</h3>
    <table>
        <tr><th>Variant</th><th>CAGR</th><th>Sharpe</th><th>Max DD</th></tr>
        <tr>
            <td>Pure Mom, 10 stocks</td>
            <td class="num-positive">+17.1%</td><td>0.70</td><td>-59.2%</td>
        </tr>
        <tr>
            <td>Excl top P/S decile, 10 stocks</td>
            <td class="num-positive"><strong>+18.1%</strong></td><td><strong>0.78</strong></td><td>-57.0%</td>
        </tr>
        <tr>
            <td>Excl P/S + SY + MA200 filter</td>
            <td>+15.2%</td><td class="num-positive"><strong>0.86</strong></td><td class="num-positive"><strong>-28.5%</strong></td>
        </tr>
        <tr>
            <td>MA200 filter only, 25 stocks</td>
            <td>+11.3%</td><td>0.70</td><td>-40.0%</td>
        </tr>
    </table>

    <h3>Analysis</h3>
    <p>Momentum is the strongest factor we found — confirming the book across a completely different
    time period. At &gt;$5B with monthly rebalance, Mom 6-1 delivers +13.5% CAGR vs the book's 14.52%.
    The signal survives out-of-sample.</p>

    <p>With concentration (10 stocks) and value exclusion filters, the strategy reaches
    <strong>+18.1% CAGR</strong> — the highest single-strategy return in our dataset. Excluding the
    most expensive stocks by P/S from the momentum portfolio removes the "momentum into overvaluation"
    trap.</p>

    <p>The MA200 regime overlay is the most effective risk management tool: it reduces max drawdown
    from -64.3% to -28.5% at the cost of ~2% CAGR, pushing the Sharpe to <strong>0.86</strong>.</p>

    <h4>Market Cap Is Critical</h4>
    <p>Below $1B, momentum is noise — dominated by pump-and-dumps and penny stocks. Above $5B, it
    captures genuine institutional flows and earnings-driven appreciation. The book tested "All Stocks"
    which included micro-caps; our &gt;$5B results are both more robust and more implementable.</p>

    <h4>The Crash Risk</h4>
    <p>The book warned about volatility. We confirm: momentum crashes are real (2008: -36%,
    2020–2021 reversals). The MA200 overlay handles this — when the broad market is below its
    200-day moving average, go to cash. Simple, mechanical, effective.</p>

    <h3>Book vs Reality</h3>
    <table>
        <tr><th>Metric</th><th>O'Shaughnessy</th><th>Our Results</th></tr>
        <tr><td>D1 CAGR</td><td>14.52%</td><td>+13.5% (&gt;$5B, 25 stocks)</td></tr>
        <tr><td>"Strongest growth factor"</td><td>Yes</td><td><strong>Confirmed</strong></td></tr>
        <tr><td>"Highly volatile"</td><td>Yes</td><td><strong>Confirmed</strong> (-64% max DD)</td></tr>
        <tr><td>With enhancements</td><td>Not tested</td><td>+18.1% (excl filters, 10 stocks)</td></tr>
    </table>
</div>
<div class="page-break"></div>
""")

    # ─── VALUE COMPOSITES CHAPTER ───
    html_parts.append(f"""
<div class="chapter">
    <div class="chapter-header">
        <div class="chapter-num">Chapter 15</div>
        <div class="chapter-title">Value Composites</div>
        <div class="chapter-subtitle">The Whole Is Less Than Its Best Parts</div>
        <span class="status-badge" style="background:{GOLD}22; color:{GOLD}">DIMINISHED</span>
    </div>

    <div class="verdict-box">
        <strong>Verdict: DIMINISHED</strong> — VC2 delivers +12.1% at &gt;$200M monthly (book: 17.30%).
        The composite underperforms its best single component (Buyback Yield +12.5% at &gt;$5B) because
        4 of 6 constituent factors are broken.
    </div>

    <h3>What the Book Claims (1964–2009)</h3>
    <table>
        <tr><th>Composite</th><th>Components</th><th>CAGR</th><th>Sharpe</th><th>5yr Base Rate</th></tr>
        <tr>
            <td><strong>VC1</strong></td>
            <td>P/B + P/E + P/S + EBITDA/EV + P/CF</td>
            <td>17.18%</td><td>0.67</td><td>98%</td>
        </tr>
        <tr>
            <td><strong>VC2</strong></td>
            <td>VC1 + Shareholder Yield</td>
            <td>17.30%</td><td>0.72</td><td>98%</td>
        </tr>
    </table>
    <p>O'Shaughnessy concluded: "Better than any single value factor." VC2 beat the universe
    <strong>100% of rolling 10-year periods</strong>.</p>

    <h3>What We Found (2005–2026)</h3>
    <table>
        <tr><th>Composite</th><th>Annual &gt;$200M</th><th>Annual &gt;$5B</th><th>Monthly &gt;$200M</th><th>Monthly &gt;$5B</th></tr>
        <tr>
            <td><strong>VC1</strong></td>
            <td>+4.9%</td><td>+9.7%</td>
            <td>+10.8%</td><td>+10.2%</td>
        </tr>
        <tr>
            <td><strong>VC2</strong></td>
            <td>+5.6%</td><td>+9.8%</td>
            <td class="num-positive"><strong>+12.1%</strong></td><td>+10.0%</td>
        </tr>
        <tr>
            <td><strong>VC3</strong></td>
            <td>+5.2%</td><td>+9.3%</td>
            <td>+8.9%</td><td>+11.8%</td>
        </tr>
    </table>

    <h3>Analysis</h3>
    <p>With annual rebalance (the book's methodology), VC1/VC2 deliver ~+5% CAGR at &gt;$200M —
    a <strong>12 percentage point shortfall</strong> from the book's 17%. Monthly rebalance
    improves results significantly (VC2 reaches +12.1%), but that's a different strategy.</p>

    <h4>Why the Composite Underperforms Its Components</h4>
    <p>Counter-intuitively, VC2 at &gt;$5B (+10.0%) <strong>underperforms</strong> its best single
    component (Buyback Yield at +12.5%). This happens because:</p>
    <ul>
        <li><strong>P/E contributes zero spread</strong> (+0.5% at &gt;$200M) — diluter</li>
        <li><strong>EBITDA/EV is dead</strong> (0.0% spread at &gt;$200M) — diluter</li>
        <li><strong>P/B is inverted</strong> (-0.7% at &gt;$200M) — actively harmful</li>
        <li><strong>Dividend Yield is inverted</strong> (-2.9% at &gt;$200M) — actively harmful</li>
        <li>Only <strong>P/S and Buyback Yield carry the weight</strong> — 2 out of 6 factors</li>
    </ul>
    <p>A composite of 6 factors where 4 are broken will <em>always</em> underperform a strategy
    using only the 2 that work. This is the central quantitative finding of our research.</p>

    <h3>Book vs Reality</h3>
    <table>
        <tr><th>Metric</th><th>O'Shaughnessy</th><th>Our Results (best config)</th></tr>
        <tr><td>VC1 CAGR</td><td>17.18%</td><td>4.9–10.8%</td></tr>
        <tr><td>VC2 CAGR</td><td>17.30%</td><td>5.6–12.1%</td></tr>
        <tr><td>Sharpe</td><td>0.67–0.72</td><td>0.46–0.64</td></tr>
        <tr><td>"Better than any single factor"</td><td>Yes</td><td class="num-negative"><strong>No — P/S alone beats the composite</strong></td></tr>
    </table>
</div>
<div class="page-break"></div>
""")

    # ─── TRENDING VALUE CHAPTER ───
    html_parts.append(f"""
<div class="chapter">
    <div class="chapter-header">
        <div class="chapter-num">Chapter 27</div>
        <div class="chapter-title">Trending Value</div>
        <div class="chapter-subtitle">13.8%, Not 21% — But Still Real Alpha</div>
        <span class="status-badge" style="background:{GREEN}22; color:{GREEN}">WORKS*</span>
    </div>

    <div class="verdict-box green">
        <strong>Verdict: WORKS — with expectations adjusted.</strong> The book promised 21.19% CAGR.
        We got 13.8% at best (TV3, &gt;$5B, monthly). The alpha is real (+5.4% over S&amp;P 500),
        but investors should expect roughly 35% less than the book claims.
    </div>

    <h3>What the Book Claims (1964–2009)</h3>
    <p>The flagship strategy of the entire book.</p>
    <table>
        <tr><th>Metric</th><th>25-Stock TV</th><th>50-Stock TV</th></tr>
        <tr><td>CAGR</td><td><strong>21.19%</strong></td><td>19.85%</td></tr>
        <tr><td>Sharpe</td><td>0.93</td><td>0.82</td></tr>
        <tr><td>$10,000 →</td><td>$69,098,587</td><td>$41,411,163</td></tr>
        <tr><td>Max Drawdown</td><td>-50.55%</td><td>-52.87%</td></tr>
        <tr><td>5yr Base Rate</td><td>100%</td><td>100%</td></tr>
    </table>
    <p>O'Shaughnessy: <em>"The power of combining Value Factor Two and six-month price appreciation.
    Never had a 5-year period in which it lost money."</em></p>

    <h3>What We Found (2005–2026)</h3>
    <h4>Annual Rebalance (12 portfolios averaged)</h4>
    <table>
        <tr><th>Variant</th><th>&gt;$200M</th><th>&gt;$5B</th></tr>
        <tr><td>TV1 (VC1 + Mom)</td><td>+8.3%</td><td>+9.3%</td></tr>
        <tr><td>TV2 (VC2 + Mom)</td><td>+8.1%</td><td>+10.3%</td></tr>
        <tr><td>TV3 (VC3 + Mom)</td><td>+8.8%</td><td>+9.9%</td></tr>
    </table>

    <h4>Monthly Rebalance</h4>
    <table>
        <tr><th>Variant</th><th>&gt;$200M CAGR</th><th>Sharpe</th><th>&gt;$5B CAGR</th><th>Sharpe</th><th>Max DD</th></tr>
        <tr>
            <td>TV1</td>
            <td>+10.7%</td><td>0.55</td><td>+12.2%</td><td>0.71</td><td>-47.0%</td>
        </tr>
        <tr>
            <td>TV2</td>
            <td>+10.7%</td><td>0.56</td><td>+12.7%</td><td>0.75</td><td>-46.7%</td>
        </tr>
        <tr>
            <td><strong>TV3</strong></td>
            <td>+10.5%</td><td>0.55</td>
            <td class="num-positive"><strong>+13.8%</strong></td>
            <td class="num-positive"><strong>0.82</strong></td>
            <td><strong>-43.2%</strong></td>
        </tr>
    </table>

    <h3>Analysis</h3>
    <p>The gap between book and reality is enormous — nearly 7 percentage points. Even with the most
    favorable configuration (TV3, &gt;$5B, monthly rebalance), Trending Value delivers +13.8%, not 21%.</p>

    <p>With annual rebalance (the book's methodology), results drop to +8–10% — barely above the
    S&amp;P 500's ~8.4%.</p>

    <h4>What the Momentum Adds</h4>
    <table>
        <tr><th></th><th>Pure Value (VC)</th><th>+ Momentum (TV)</th><th>Improvement</th></tr>
        <tr><td>VC1/TV1 &gt;$5B</td><td>+10.2%</td><td>+12.2%</td><td class="num-positive">+2.0%</td></tr>
        <tr><td>VC2/TV2 &gt;$5B</td><td>+10.0%</td><td>+12.7%</td><td class="num-positive">+2.7%</td></tr>
        <tr><td>VC3/TV3 &gt;$5B</td><td>+11.8%</td><td>+13.8%</td><td class="num-positive">+2.0%</td></tr>
    </table>
    <p>Momentum adds +2.0 to +2.7% CAGR and reduces drawdowns by 11–17 percentage points. This is
    genuine value — the momentum filter avoids value traps by only buying cheap stocks trending upward.</p>

    <h4>Why 21% → 13.8%</h4>
    <ul>
        <li><strong>The value premium has shrunk.</strong> The composite relies on 6 value factors,
        4 of which are now broken. This weakens the value screen.</li>
        <li><strong>Out-of-sample degradation.</strong> All backtested strategies lose edge when applied
        to new data. ~30–50% decay is typical in academic literature.</li>
        <li><strong>Survivorship bias.</strong> We use 12,151 delisted stocks; the book's dataset
        may have gaps in delisted coverage.</li>
        <li><strong>Different period.</strong> 1964–2009 included multiple value-friendly decades.
        2005–2026 is dominated by growth/tech.</li>
    </ul>

    <h3>Book vs Reality</h3>
    <table>
        <tr><th>Metric</th><th>O'Shaughnessy</th><th>Our Results (best)</th></tr>
        <tr><td>CAGR</td><td><strong>21.19%</strong></td><td>13.8% (TV3, &gt;$5B, monthly)</td></tr>
        <tr><td>Sharpe</td><td>0.93</td><td>0.82</td></tr>
        <tr><td>Max DD</td><td>-50.55%</td><td>-43.2%</td></tr>
        <tr><td>Alpha vs S&amp;P</td><td>~+12%</td><td>+5.4%</td></tr>
    </table>

    <p>The alpha is real. The strategy works. But 13.8% is not 21%. Investors expecting the book's
    claims need to adjust expectations by roughly 35%.</p>
</div>
<div class="page-break"></div>
""")

    # ─── CONCLUSION ───
    html_parts.append(f"""
<div class="chapter">
    <div class="chapter-header">
        <div class="chapter-num">Conclusion</div>
        <div class="chapter-title">What Actually Works in 2026</div>
    </div>

    <h3>The Survivors</h3>
    <p>Out of 12 single factors tested, only three generate consistent, reliable alpha:</p>

    <table>
        <tr><th>Factor</th><th>Spread (&gt;$200M)</th><th>Spread (&gt;$5B)</th><th>5yr Base Rate</th><th>Why It Works</th></tr>
        <tr>
            <td style="color:{GREEN}"><strong>Price/Sales</strong></td>
            <td class="num-positive">+8.3%</td>
            <td class="num-positive">+5.0%</td>
            <td>82%</td>
            <td>Revenue is hardest to manipulate</td>
        </tr>
        <tr>
            <td style="color:{GREEN}"><strong>Buyback Yield</strong></td>
            <td class="num-positive">+7.9%</td>
            <td class="num-positive">+5.2%</td>
            <td>100%</td>
            <td>Shares outstanding is objective fact</td>
        </tr>
        <tr>
            <td style="color:{GREEN}"><strong>Momentum 6-1</strong></td>
            <td colspan="2" class="num-positive">+13.5% CAGR (&gt;$5B)</td>
            <td>N/A</td>
            <td>Captures institutional flows</td>
        </tr>
    </table>

    <h3>The Common Thread</h3>
    <p>The surviving factors share one characteristic: <strong>they're built on the
    hardest-to-manipulate data</strong>.</p>
    <ul>
        <li><strong>Revenue</strong> — you can't create sales from accounting choices</li>
        <li><strong>Shares outstanding</strong> — a simple, objective count</li>
        <li><strong>Price</strong> — the market's real-time consensus, driven by actual transactions</li>
    </ul>
    <p>Factors that rely on more manipulable inputs — earnings (P/E), EBITDA (SBC distortion),
    book value (intangibles era), cash flow (capex timing) — have lost their edge. The market
    has gotten better at seeing through accounting noise. Only the cleanest signals survive.</p>

    <h3>A Modern Allocation</h3>
    <p>Based on our results, a quantitative equity allocation in 2026 should:</p>
    <ol>
        <li><strong>Screen for value using P/S and Buyback Yield only.</strong> Drop P/E, P/B,
        EBITDA/EV, and Dividend Yield from any value composite.</li>
        <li><strong>Apply momentum as the primary timing/selection overlay.</strong> 6-month
        momentum with 1-month skip, monthly rebalance, &gt;$5B market cap.</li>
        <li><strong>Use MA200 for risk management.</strong> When the broad market is below its
        200-day average, go to cash. Reduces max drawdown from -64% to -29% with minimal
        CAGR sacrifice.</li>
        <li><strong>Concentrate.</strong> 10–25 positions, not 50+. The alpha is in the extremes
        of the distribution.</li>
        <li><strong>Expect 12–15% CAGR, not 20%+.</strong> The era of backtested value premiums
        above 15% is over. Real, implementable alpha is 3–6% above the S&amp;P 500.</li>
    </ol>

    <h3>What O'Shaughnessy Got Right</h3>
    <ul>
        <li>Systematic, factor-based investing works better than stock-picking</li>
        <li>Momentum is the strongest standalone factor</li>
        <li>Combining value and momentum (Trending Value) is powerful</li>
        <li>High-growth stocks are overpriced (confirmed)</li>
        <li>High-margin stocks underperform (confirmed and worsened)</li>
        <li>Buyback yield is one of the best single factors (confirmed)</li>
    </ul>

    <h3>What Changed</h3>
    <ul>
        <li>P/E — from "one true faith" to zero spread</li>
        <li>EBITDA/EV — from "best single factor" to dead</li>
        <li>P/B — from academic foundation to inverted signal</li>
        <li>Value composites — from 17% to 5–12%, worse than their best component</li>
        <li>Trending Value — from 21% to 14%, still alpha but 35% less</li>
    </ul>

    <div class="section-divider">◆ ◆ ◆</div>

    <p style="text-align:center; color:{TEXT_MUTED}; font-style:italic; max-width:600px; margin:0 auto;">
        The market hasn't stopped rewarding cheapness and momentum. It has gotten better at
        seeing through the accounting metrics that once defined "cheap." In 2026, value investing
        works — but only if you measure value with metrics the market can't game.
    </p>

    <div class="section-divider" style="margin-top:3rem;">◆</div>

    <div style="text-align:center; margin-top:2rem; color:{TEXT_MUTED}; font-size:0.85rem;">
        <p><strong style="color:{GOLD}">Bivar Capital Research</strong></p>
        <p>bivarcapital.com</p>
        <p style="margin-top:1rem; font-size:0.75rem;">
            Data: Nasdaq Data Link / Sharadar Core US Equities<br>
            Period: 2005–2026 | Universe: US common stocks<br>
            Methodology: Quarterly TTM, decile sort, 12-month averaged annual rebalance<br>
            12,151 delisted + 5,467 active tickers
        </p>
    </div>
</div>
""")

    html_parts.append("</body></html>")
    return ''.join(html_parts)


# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("Generating HTML...")
    html = generate_html()

    print(f"Writing HTML to {OUTPUT_HTML}...")
    with open(OUTPUT_HTML, 'w') as f:
        f.write(html)
    print(f"  ✓ HTML saved ({len(html) / 1024:.0f} KB)")

    print(f"Generating PDF with weasyprint...")
    try:
        import weasyprint
        doc = weasyprint.HTML(filename=str(OUTPUT_HTML))
        doc.write_pdf(str(OUTPUT_PDF))
        print(f"  ✓ PDF saved to {OUTPUT_PDF}")
    except Exception as e:
        print(f"  ✗ PDF generation failed: {e}")
        print("  → Open the HTML file in a browser and print to PDF as fallback.")

    print("\nDone.")
