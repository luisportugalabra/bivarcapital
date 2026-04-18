#!/usr/bin/env python3
"""
Generate "What Still Works on Wall Street" — v2.
Goldman/JPM research style. White background. Serif fonts. Full decile bars.
"""

import json
import io
import base64
import os
from pathlib import Path
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ── Config ──────────────────────────────────────────────────────────────────
DATA_PATH = Path.home() / "bivarcapital/book/data/all_deciles.json"
OUTPUT_HTML = Path.home() / "Desktop/what_still_works_on_wall_street.html"
OUTPUT_PDF = Path.home() / "Desktop/what_still_works_on_wall_street.pdf"

# Colors — muted, professional
NAVY = '#1a2332'
DARK = '#2c3e50'
MID = '#5a6c7d'
LIGHT = '#95a5a6'
ACCENT = '#c0392b'  # deep red
ACCENT2 = '#2471a3'  # steel blue
GREEN_MUTED = '#27ae60'
RED_MUTED = '#c0392b'
GOLD_MUTED = '#b7950b'
BG_CHART = '#fafbfc'
GRID_COLOR = '#e5e8eb'

# ── Load data ───────────────────────────────────────────────────────────────
with open(DATA_PATH) as f:
    ALL_DATA = json.load(f)

# ── Chart styling ───────────────────────────────────────────────────────────
plt.rcParams.update({
    'font.family': ['Georgia', 'Times New Roman', 'serif'],
    'font.size': 9,
    'axes.titlesize': 11,
    'axes.titleweight': 'bold',
    'axes.labelsize': 9,
    'figure.facecolor': BG_CHART,
    'axes.facecolor': BG_CHART,
    'axes.edgecolor': '#ccd1d9',
    'axes.grid': True,
    'grid.color': GRID_COLOR,
    'grid.linewidth': 0.5,
    'grid.alpha': 0.7,
    'xtick.color': MID,
    'ytick.color': MID,
    'text.color': NAVY,
})

def fig_to_base64(fig, dpi=180):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                facecolor=BG_CHART, edgecolor='none', pad_inches=0.15)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def make_decile_bar(title, data_200, data_5b=None):
    """Full D1–D10 CAGR bar chart."""
    deciles = data_200.get('decile_cagrs', {})
    if not deciles:
        return None

    ds = sorted(deciles.keys(), key=lambda x: int(x))
    vals = [deciles[d] for d in ds]
    univ = data_200.get('univ_cagr', 0)

    fig, ax = plt.subplots(figsize=(7.5, 3.2))

    # Color gradient: D1 green-ish, D10 red-ish, with intermediate grays
    n = len(vals)
    colors = []
    for i, v in enumerate(vals):
        if v > univ + 1:
            colors.append(ACCENT2)
        elif v < univ - 1:
            colors.append(RED_MUTED)
        else:
            colors.append(LIGHT)

    bars = ax.bar(range(n), vals, color=colors, width=0.72, edgecolor='white', linewidth=0.5)

    # Universe line
    ax.axhline(y=univ, color=NAVY, linewidth=1.2, linestyle='--', alpha=0.6,
               label=f'Universe: {univ:+.1f}%')

    # Labels on bars
    for i, (bar, v) in enumerate(zip(bars, vals)):
        va = 'bottom' if v >= 0 else 'top'
        offset = 0.25 if v >= 0 else -0.25
        ax.text(bar.get_x() + bar.get_width()/2, v + offset,
                f'{v:.1f}', ha='center', va=va, fontsize=7.5,
                fontweight='bold', color=NAVY)

    ax.set_xticks(range(n))
    ax.set_xticklabels([f'D{d}' for d in ds], fontsize=8)
    ax.set_ylabel('CAGR (%)', fontsize=8)
    ax.set_title(title, fontsize=10, fontweight='bold', color=NAVY, pad=8)
    ax.legend(fontsize=7.5, loc='upper right', framealpha=0.8, edgecolor=GRID_COLOR)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    return fig_to_base64(fig)


def make_annual_spread(title, data_200):
    """Year-by-year D1 return, D10 return, and spread bars."""
    d1 = data_200.get('d1_annual', {})
    d10 = data_200.get('d10_annual', {})
    if not d1 or not d10:
        return None

    years = sorted(d1.keys())
    d1_vals = [d1.get(y, 0) for y in years]
    d10_vals = [d10.get(y, 0) for y in years]
    spreads = [d1.get(y, 0) - d10.get(y, 0) for y in years]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 5), height_ratios=[1.6, 1],
                                    gridspec_kw={'hspace': 0.35})

    # Top: D1 vs D10
    x = np.arange(len(years))
    w = 0.38
    ax1.bar(x - w/2, d1_vals, w, color=ACCENT2, alpha=0.8, label='D1 (Cheap/Best)', edgecolor='white', linewidth=0.3)
    ax1.bar(x + w/2, d10_vals, w, color=RED_MUTED, alpha=0.7, label='D10 (Expensive/Worst)', edgecolor='white', linewidth=0.3)
    ax1.axhline(y=0, color=MID, linewidth=0.6)
    ax1.set_xticks(x)
    ax1.set_xticklabels([y[-2:] for y in years], fontsize=7)
    ax1.set_ylabel('Annual Return (%)', fontsize=8)
    ax1.set_title(f'{title} — D1 vs D10 Annual Returns', fontsize=10,
                  fontweight='bold', color=NAVY, pad=8)
    ax1.legend(fontsize=7, loc='best', framealpha=0.8, edgecolor=GRID_COLOR)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)

    # Bottom: Spread
    spread_colors = [GREEN_MUTED if s > 0 else RED_MUTED for s in spreads]
    ax2.bar(x, spreads, color=spread_colors, width=0.65, edgecolor='white', linewidth=0.3)
    ax2.axhline(y=0, color=NAVY, linewidth=0.8)

    # Cumulative spread line
    cum = np.cumsum(spreads)
    ax2_twin = ax2.twinx()
    ax2_twin.plot(x, cum, color=GOLD_MUTED, linewidth=1.8, marker='o', markersize=3,
                  label='Cumulative Spread')
    ax2_twin.set_ylabel('Cumulative (%)', fontsize=7, color=GOLD_MUTED)
    ax2_twin.tick_params(colors=GOLD_MUTED, labelsize=7)
    ax2_twin.spines['top'].set_visible(False)
    ax2_twin.spines['right'].set_color(GOLD_MUTED)
    ax2_twin.spines['right'].set_linewidth(0.5)

    ax2.set_xticks(x)
    ax2.set_xticklabels([y[-2:] for y in years], fontsize=7)
    ax2.set_ylabel('D1 − D10 (%)', fontsize=8)
    ax2.set_title('Annual Spread & Cumulative', fontsize=9, fontweight='bold', color=NAVY, pad=6)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)

    return fig_to_base64(fig)


def make_master_scorecard():
    """Horizontal bar chart — all factors sorted by spread."""
    items = []
    for key, data in ALL_DATA.items():
        if '>$200M' in key:
            name = key.replace(' >$200M', '')
            items.append((name, data.get('spread', 0), data.get('alpha_vs_univ', 0),
                         data.get('r5_pos_pct', 0)))

    items.sort(key=lambda x: x[1], reverse=True)
    names = [x[0] for x in items]
    spreads = [x[1] for x in items]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    colors = [GREEN_MUTED if s > 1.5 else (RED_MUTED if s < -1 else LIGHT) for s in spreads]

    y_pos = range(len(names))
    bars = ax.barh(y_pos, spreads, color=colors, height=0.65,
                   edgecolor='white', linewidth=0.5)

    for i, (bar, s) in enumerate(zip(bars, spreads)):
        x_pos = s + (0.2 if s >= 0 else -0.2)
        ha = 'left' if s >= 0 else 'right'
        ax.text(x_pos, i, f'{s:+.1f}%', va='center', ha=ha,
                fontsize=7.5, fontweight='bold', color=NAVY)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=8)
    ax.axvline(x=0, color=NAVY, linewidth=0.8)
    ax.set_xlabel('D1 − D10 Spread (%)', fontsize=8)
    ax.set_title('Factor Spread Scorecard — >$200M Universe (2005–2025)',
                 fontsize=10, fontweight='bold', color=NAVY, pad=10)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.invert_yaxis()

    return fig_to_base64(fig)


def make_decile_comparison(title, data_200, data_5b):
    """Side-by-side D1-D10 for both universes."""
    d200 = data_200.get('decile_cagrs', {})
    d5b = data_5b.get('decile_cagrs', {})
    if not d200 or not d5b:
        return None

    ds = sorted(d200.keys(), key=lambda x: int(x))
    vals_200 = [d200.get(d, 0) for d in ds]
    vals_5b = [d5b.get(d, 0) for d in ds]

    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    x = np.arange(len(ds))
    w = 0.35

    ax.bar(x - w/2, vals_200, w, color=ACCENT2, alpha=0.8, label='>$200M',
           edgecolor='white', linewidth=0.3)
    ax.bar(x + w/2, vals_5b, w, color=GOLD_MUTED, alpha=0.8, label='>$5B',
           edgecolor='white', linewidth=0.3)

    for i, (v200, v5b) in enumerate(zip(vals_200, vals_5b)):
        ax.text(i - w/2, v200 + 0.2, f'{v200:.1f}', ha='center', va='bottom',
                fontsize=6.5, color=ACCENT2, fontweight='bold')
        ax.text(i + w/2, v5b + 0.2, f'{v5b:.1f}', ha='center', va='bottom',
                fontsize=6.5, color=GOLD_MUTED, fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels([f'D{d}' for d in ds], fontsize=8)
    ax.set_ylabel('CAGR (%)', fontsize=8)
    ax.set_title(title, fontsize=10, fontweight='bold', color=NAVY, pad=8)
    ax.legend(fontsize=7.5, loc='upper right', framealpha=0.8, edgecolor=GRID_COLOR)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    return fig_to_base64(fig)


# ── Chapter definitions ─────────────────────────────────────────────────────

def fmt_spread(s):
    if s > 1.5: return f'<span class="positive">{s:+.1f}%</span>'
    elif s < -1: return f'<span class="negative">{s:+.1f}%</span>'
    else: return f'<span class="neutral">{s:+.1f}%</span>'

def fmt_pct(v, threshold=0):
    if v > threshold: return f'<span class="positive">{v:+.1f}%</span>'
    elif v < -threshold: return f'<span class="negative">{v:+.1f}%</span>'
    return f'{v:+.1f}%'

def status_badge(status):
    colors = {
        'WORKS': GREEN_MUTED,
        'DEAD': RED_MUTED,
        'INVERTED': RED_MUTED,
        'MARGINAL': GOLD_MUTED,
        'WEAK': GOLD_MUTED,
        'DIMINISHED': GOLD_MUTED,
    }
    c = colors.get(status, MID)
    return f'<span class="badge" style="color:{c}; border-color:{c}">{status}</span>'


CHAPTERS = [
    {
        'num': '01', 'title': 'Price-to-Earnings',
        'key200': 'P/E >$200M', 'key5b': 'P/E >$5B',
        'status': 'DEAD',
        'book': {'d1': '16.25%', 'spread': '~10.7%', 'sharpe': '0.61', 'br5': '92%', 'br10': '99%'},
        'book_verdict': 'Low P/E stocks earn enormous premiums across all periods tested.',
        'body': """
<p>O'Shaughnessy found low P/E stocks turned $10,000 into $10.2M over 46 years.
The lowest decile beat the universe 92% of rolling five-year periods and 99% of ten-year periods.
High P/E stocks returned 5.53% — worse than Treasury bills.</p>

<p>The spread has collapsed to near zero. At >$200M, D1 barely edges D10 by {spread_200}. At >$5B,
cheap P/E stocks actually <em>trail</em> expensive ones. The five-year base rate has fallen from
92% to {br5_200} — indistinguishable from noise.</p>

<p>The mechanism failure is clear: earnings are the most manipulated line item on the income
statement. Stock-based compensation, restructuring charges, tax strategies, and one-time items
all distort the denominator. In an era of accounting complexity, P/E captures noise as much as
signal. Metrics built on harder-to-game fundamentals — revenue, shares outstanding — have
maintained their edge where P/E has not.</p>
""",
    },
    {
        'num': '02', 'title': 'EBITDA / Enterprise Value',
        'key200': 'EBITDA/EV >$200M', 'key5b': 'EBITDA/EV >$5B',
        'status': 'DEAD',
        'book': {'d1': '16.58%', 'spread': '~11%', 'sharpe': '0.65', 'br5': '96%', 'br10': '100%'},
        'book_verdict': '"Best on an absolute basis for all individual value factors."',
        'body': """
<p>The crown jewel of O'Shaughnessy's value arsenal. EBITDA/EV beat the universe 96% of rolling
five-year windows and 100% of ten-year windows. No other single factor came close.</p>

<p>The collapse is striking. At >$200M the spread is {spread_200} — a fraction of the 11% the book
reported. The factor's structural advantage — capital structure neutrality — became irrelevant in
the zero-rate era (2009–2022) when leverage stopped differentiating companies.</p>

<p>A deeper issue: EBITDA ignores stock-based compensation. When the book was written, SBC was
negligible. Today it represents billions in real economic cost at technology companies, making them
appear cheaper on EBITDA/EV than their true earnings power warrants. The metric's blind spot has
become the market's largest sector.</p>
""",
    },
    {
        'num': '03', 'title': 'Price-to-Cash Flow',
        'key200': 'P/CF (FCF) >$200M', 'key5b': 'P/CF (FCF) >$5B',
        'status': 'MARGINAL',
        'book': {'d1': '16.25%', 'spread': '~12.8%', 'sharpe': '0.61', 'br5': '91%', 'br10': '100%'},
        'book_verdict': '"Uniformly high base rates." 100% of rolling ten-year windows positive.',
        'body': """
<p>Cash flow was the book's second-tier value metric — nearly identical returns to P/E but with
the appeal of being "harder to manipulate." The 100% ten-year base rate was among the strongest
of any single factor.</p>

<p>Our results show a modest {spread_200} spread at >$200M and {spread_5b} at >$5B.
The signal hasn't fully died — the five-year base rate of {br5_200} suggests some residual
predictive power — but the magnitude has shrunk by roughly 85% from the book's claim.</p>

<p>Free cash flow remains a cleaner fundamental than net income, which likely explains why P/CF
retains more signal than P/E. But capex timing and working capital volatility inject noise that
revenue (P/S) avoids entirely.</p>
""",
    },
    {
        'num': '04', 'title': 'Price-to-Sales',
        'key200': 'P/S >$200M', 'key5b': 'P/S >$5B',
        'status': 'WORKS',
        'book': {'d1': '14.49%', 'spread': '~11.1%', 'sharpe': '0.46', 'br5': '75%', 'br10': '89%'},
        'book_verdict': '"Best single factor in the first edition. Lost to EBITDA/EV after 2007–2008."',
        'body': """
<p>In the first edition, P/S was the best single value factor. O'Shaughnessy demoted it in the
fourth edition after 2007–2008 hurt low P/S stocks disproportionately. He noted that "a few
bad years dramatically changed results."</p>

<p>The irony is complete: <strong>P/S is the only traditional value factor that retains a
meaningful spread</strong>. D1 delivers {d1_200} CAGR at >$200M — a {spread_200} edge over D10
and {alpha_200} alpha over the universe. The five-year base rate of {br5_200} is the highest among
all value metrics tested.</p>

<p>Revenue is the hardest fundamental to manipulate. You can manage earnings through accounting
elections. You can shift cash flows through capex timing. Revenue is revenue — it requires
actual transactions with actual customers. In a market that has become efficient at pricing
through accounting noise, the cleanest fundamental retains the strongest signal.</p>

<p>The first edition was right. The fourth edition's demotion was a mistake driven by
recency bias from a single crisis.</p>
""",
    },
    {
        'num': '05', 'title': 'Price-to-Book',
        'key200': 'P/B >$200M', 'key5b': 'P/B >$5B',
        'status': 'INVERTED',
        'book': {'d1': '11.33%', 'spread': '~5.3%', 'sharpe': '0.22', 'br5': '66%', 'br10': '77%'},
        'book_verdict': '"Works but with long subperiods of underperformance." Fama-French HML foundation.',
        'body': """
<p>Price-to-book is the academic foundation of value investing. Fama and French's HML factor —
the basis of thousands of papers and trillions in assets — sorts on book-to-market. Even in
O'Shaughnessy's data, P/B was erratic: decile 2 outperformed decile 1, and the 1927–1963
subperiod showed underperformance.</p>

<p>The factor has fully inverted. Expensive stocks (high P/B) outperform cheap stocks by {spread_200}
at >$200M and {spread_5b} at >$5B. The five-year base rate of {br5_5b} at >$5B means buying
low P/B stocks has been a losing strategy in roughly two-thirds of five-year windows.</p>

<p>The structural explanation: in 1990, tangible assets comprised 68% of S&P 500 market
capitalization. Today the figure is below 10%. A low price-to-book ratio in 2025 identifies
companies whose value resides in physical plant — factories, inventory, real estate in
declining industries. High P/B identifies companies with enormous intangible assets
(intellectual property, brand equity, network effects, software) that never appear on the
balance sheet. Book value has become a marker for the wrong kind of company.</p>
""",
    },
    {
        'num': '06', 'title': 'Dividend Yield',
        'key200': 'Div Yield >$200M', 'key5b': 'Div Yield >$5B',
        'status': 'WEAK',
        'book': {'d1': '11.77%', 'spread': '~1.3%', 'sharpe': '0.34', 'br5': '67%', 'br10': '75%'},
        'book_verdict': '"Modest alpha." Best results come from high-yield stocks with strong financials.',
        'body': """
<p>The book found only modest alpha from dividend yield — 11.77% vs 10.46% for the universe.
O'Shaughnessy noted that "decile 3 actually outperformed decile 1" and recommended combining
dividend yield with quality screens rather than using it standalone.</p>

<p>Our results show a {spread_200} spread at >$200M and {spread_5b} at >$5B — the signal is
thin but modestly positive. However, this partly reflects sector composition: high-yield stocks
are concentrated in utilities, energy, and staples, which had specific tailwinds during parts
of our sample period.</p>

<p>The book's modest alpha has shrunk further. Dividend yield alone is not a sufficient stock
selection criterion in any market cap range.</p>
""",
    },
    {
        'num': '07', 'title': 'Buyback Yield',
        'key200': 'Buyback Yield >$200M', 'key5b': 'Buyback Yield >$5B',
        'status': 'INVERTED',
        'book': {'d1': '13.69%', 'spread': '~7.75%', 'sharpe': '0.36', 'br5': '89%', 'br10': '89%'},
        'book_verdict': '"One of the best single factors." Buyback signals management confidence.',
        'body': """
<p>The book found buyback yield among the strongest standalone factors, with D1 delivering 13.69%
CAGR and 89% positive rolling windows. The thesis: companies buying back shares signal
confidence and return real cash to shareholders.</p>

<p>Our results show the relationship has inverted. D1 (highest buyback yield) returns {d1_200} at
>$200M while D10 returns {d10_200} — a {spread_200} spread in the wrong direction. The five-year
base rate is {br5_200}.</p>

<p>The likely explanation: the buyback yield calculation in the Sharadar TTM dataset captures
share count changes that include equity issuance for acquisitions, compensation, and convertible
instruments — not just open-market repurchases. When measured with a shares-outstanding method
(as in our earlier single-factor analysis), the signal may differ. Additionally, the most
aggressive buyback programs in recent years have been at mega-cap technology companies whose
outperformance may be driven by growth rather than the repurchase itself.</p>

<p>This result warrants further investigation with alternative calculation methods. The divergence
from the original analysis suggests sensitivity to measurement methodology.</p>
""",
    },
    {
        'num': '08', 'title': 'Shareholder Yield',
        'key200': 'SH Yield >$200M', 'key5b': 'SH Yield >$5B',
        'status': 'INVERTED',
        'book': {'d1': '13.22%', 'spread': '~7.15%', 'sharpe': '0.42', 'br5': '86%', 'br10': '93%'},
        'book_verdict': '"Superior to dividend or buyback alone." Better risk-adjusted returns.',
        'body': """
<p>Shareholder yield (dividends plus buybacks) was O'Shaughnessy's preferred total-return-to-
shareholders metric. The book found it delivered 13.22% CAGR with a Sharpe of 0.42 — the
best risk-adjusted return among single yield factors.</p>

<p>Our results mirror the buyback yield inversion: D1 (highest SH yield) returns {d1_200}
at >$200M while D10 returns {d10_200}. The spread is {spread_200} with a five-year base rate
of {br5_200}.</p>

<p>As with buyback yield, the result is sensitive to measurement methodology. The pre-computed
shareholder yield in the Sharadar dataset may capture compositional effects that differ from the
shares-outstanding approach used in the book. The core finding remains that this factor's
performance is method-dependent and unreliable as a standalone signal in its current form.</p>
""",
    },
    {
        'num': '09', 'title': 'Accruals',
        'key200': 'Accruals >$200M', 'key5b': 'Accruals >$5B',
        'status': 'MARGINAL',
        'book': {'d1': 'Positive', 'spread': 'Modest', 'sharpe': 'N/A', 'br5': 'N/A', 'br10': 'N/A'},
        'book_verdict': 'Low accruals (high earnings quality) predict modest outperformance.',
        'body': """
<p>The accruals anomaly captures earnings quality: companies where cash flow tracks earnings
closely (low accruals) tend to outperform those where earnings exceed cash flow (high accruals,
suggesting potential manipulation).</p>

<p>The signal shows a modest {spread_200} spread at >$200M with a {br5_200} five-year base rate.
At >$5B, the spread narrows to {spread_5b}. The predictive power exists but is insufficient
for a standalone strategy.</p>

<p>Earnings quality may add marginal value as a secondary screen in a multi-factor model.
As a primary selection criterion, the signal-to-noise ratio is too low.</p>
""",
    },
    {
        'num': '10', 'title': 'Earnings Growth',
        'key200': 'EPS Growth >$200M', 'key5b': 'EPS Growth >$5B',
        'status': 'INVERTED',
        'book': {'d1': '11.88%', 'spread': '~0.66%', 'sharpe': '0.31', 'br5': '58%', 'br10': '61%'},
        'book_verdict': '"Not a good investment factor." High growth expectations are priced in.',
        'body': """
<p>This was one of the book's negative findings. O'Shaughnessy argued that stocks with the
highest EPS growth don't systematically outperform — investors bid them up too far, and
when growth decelerates, they crash. Base rates were barely above a coin flip.</p>

<p>Our data confirms and extends this finding. The spread is {spread_200} at >$200M — actually
<em>negative</em>, meaning the highest-growth stocks underperform the lowest. The five-year base
rate of {br5_200} remains near random.</p>

<p>Backward-looking earnings growth remains a poor predictor of forward returns. Strong past
growth typically means the easy gains have been captured and priced in. The book was right:
buying stocks for their growth track record is not a reliable strategy.</p>
""",
    },
    {
        'num': '11', 'title': 'Profit Margins',
        'key200': 'Profit Margin >$200M', 'key5b': 'Profit Margin >$5B',
        'status': 'INVERTED',
        'book': {'d1': '10.31%', 'spread': '-0.91%', 'sharpe': '0.31', 'br5': '47%', 'br10': '48%'},
        'book_verdict': '"High net profit margins underperform All Stocks." Negative finding.',
        'body': """
<p>The book found that high-margin companies returned 10.31% versus 11.22% for the universe — a
negative finding. Base rates were below 50%. O'Shaughnessy noted that mid-range margins (decile 7)
actually outperformed the highest margins.</p>

<p>The finding has intensified. At >$200M, the spread is {spread_200} with a five-year base rate
of {br5_200}. High margins signal mature businesses with limited reinvestment opportunities —
companies extracting rather than creating value. In a market that rewards growth and reinvestment,
being highly profitable but static is a liability.</p>

<p>The book was right. Time has made this finding stronger, not weaker.</p>
""",
    },
    {
        'num': '12', 'title': 'Return on Equity',
        'key200': 'ROE >$200M', 'key5b': 'ROE >$5B',
        'status': 'INVERTED',
        'book': {'d1': '12.29%', 'spread': '~6.1%', 'sharpe': '0.35', 'br5': '63%', 'br10': '51%'},
        'book_verdict': '"Not a reliable standalone factor." Base rates deteriorate over longer periods.',
        'body': """
<p>O'Shaughnessy found ROE delivered a +1.07% alpha over the universe but warned that base rates
deteriorated over longer periods — from 63% at three years to 51% at ten. He concluded it was
"not reliable standalone."</p>

<p>Our results show the factor has inverted: D1 (highest ROE) returns {d1_200} while D10
returns {d10_200}, producing a {spread_200} spread. The five-year base rate of {br5_200}
confirms negative predictive power.</p>

<p>The likely driver: high ROE in isolation conflates genuine operational excellence with
financial engineering (high leverage amplifies ROE). Without controlling for balance sheet
quality, the metric picks up leveraged companies that are fragile rather than excellent.</p>
""",
    },
]


# ── HTML generation ─────────────────────────────────────────────────────────

def build_decile_table(data, label):
    """Build a full D1-D10 table row."""
    deciles = data.get('decile_cagrs', {})
    ds = sorted(deciles.keys(), key=lambda x: int(x))
    univ = data.get('univ_cagr', 0)

    cells = f'<td class="row-label">{label}</td>'
    for d in ds:
        v = deciles.get(d, 0)
        cls = 'positive' if v > univ + 1.5 else ('negative' if v < univ - 1.5 else '')
        cells += f'<td class="{cls}">{v:+.1f}%</td>'
    cells += f'<td class="universe">{univ:+.1f}%</td>'
    spread = data.get('spread', 0)
    cls = 'positive' if spread > 1.5 else ('negative' if spread < -1 else '')
    cells += f'<td class="{cls} bold">{spread:+.1f}%</td>'
    alpha = data.get('alpha_vs_univ', 0)
    cls = 'positive' if alpha > 0.5 else ('negative' if alpha < -0.5 else '')
    cells += f'<td class="{cls} bold">{alpha:+.1f}%</td>'
    return f'<tr>{cells}</tr>'

def build_summary_row(name, data, status, status_color):
    """Build compact summary row: Factor | D1 | D5 | D10 | Univ | Spread | Alpha | 5yr BR | Status."""
    deciles = data.get('decile_cagrs', {})
    univ = data.get('univ_cagr', 0)
    d1 = deciles.get('1', 0)
    d5 = deciles.get('5', 0)
    d10 = deciles.get('10', 0)
    spread = data.get('spread', 0)
    alpha = data.get('alpha_vs_univ', 0)
    br5 = data.get('r5_pos_pct', 0)

    sp_cls = 'positive' if spread > 1.5 else ('negative' if spread < -1 else '')
    al_cls = 'positive' if alpha > 0.5 else ('negative' if alpha < -0.5 else '')
    br_cls = 'positive' if br5 >= 70 else ('negative' if br5 < 50 else '')

    return f"""<tr>
        <td style="text-align:left"><strong>{name}</strong></td>
        <td>{d1:+.1f}%</td><td>{d5:+.1f}%</td><td>{d10:+.1f}%</td>
        <td class="universe">{univ:+.1f}%</td>
        <td class="{sp_cls} bold">{spread:+.1f}%</td>
        <td class="{al_cls} bold">{alpha:+.1f}%</td>
        <td class="{br_cls}">{br5:.0f}%</td>
        <td style="color:{status_color}; font-weight:700; font-size:0.65rem">{status}</td>
    </tr>"""


def generate_html():
    scorecard_img = make_master_scorecard()

    html = []

    css = """
    @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600;0,8..60,700;1,8..60,400&family=Inter:wght@400;500;600&display=swap');

    @page {
        size: A4;
        margin: 20mm 16mm 20mm 16mm;
        @bottom-right {
            content: counter(page);
            font-family: 'Inter', sans-serif;
            font-size: 8px;
            color: #95a5a6;
        }
        @bottom-left {
            content: 'Bivar Capital Research';
            font-family: 'Inter', sans-serif;
            font-size: 8px;
            color: #95a5a6;
        }
    }

    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
        font-family: 'Source Serif 4', Georgia, 'Times New Roman', serif;
        background: #ffffff;
        color: #1a2332;
        font-size: 10.5pt;
        line-height: 1.7;
        -webkit-font-smoothing: antialiased;
    }

    .page-break { break-after: page; }
    .new-page { break-before: page; }
    .avoid-break { break-inside: avoid; }

    /* ─── Cover ─── */
    .cover {
        min-height: 92vh;
        display: flex;
        flex-direction: column;
        justify-content: center;
        padding: 0 1rem;
    }
    .cover-rule {
        width: 60px;
        height: 3px;
        background: #1a2332;
        margin-bottom: 2rem;
    }
    .cover h1 {
        font-size: 2.6rem;
        font-weight: 700;
        color: #1a2332;
        line-height: 1.15;
        letter-spacing: -0.03em;
        margin-bottom: 0.75rem;
    }
    .cover .subtitle {
        font-size: 1.05rem;
        color: #5a6c7d;
        font-weight: 300;
        line-height: 1.5;
        max-width: 480px;
        margin-bottom: 3.5rem;
    }
    .cover .meta {
        font-family: 'Inter', sans-serif;
        font-size: 0.8rem;
        color: #5a6c7d;
        line-height: 2;
    }
    .cover .meta strong { color: #1a2332; font-weight: 600; }

    /* ─── Section headers ─── */
    .section-header {
        border-bottom: 2px solid #1a2332;
        padding-bottom: 0.75rem;
        margin-bottom: 1.5rem;
        margin-top: 0.5rem;
    }
    .section-num {
        font-family: 'Inter', sans-serif;
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.2em;
        color: #95a5a6;
        font-weight: 600;
    }
    .section-title {
        font-size: 1.65rem;
        font-weight: 700;
        color: #1a2332;
        line-height: 1.2;
        letter-spacing: -0.02em;
    }
    .badge {
        font-family: 'Inter', sans-serif;
        display: inline-block;
        font-size: 0.65rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        padding: 0.15rem 0.6rem;
        border: 1.5px solid;
        border-radius: 3px;
        margin-left: 0.75rem;
        vertical-align: middle;
    }

    /* ─── Typography ─── */
    h3 {
        font-family: 'Inter', sans-serif;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #5a6c7d;
        margin: 1.8rem 0 0.6rem 0;
        padding-bottom: 0.3rem;
        border-bottom: 1px solid #e5e8eb;
    }
    p { margin-bottom: 0.7rem; }
    em { font-style: italic; }
    strong { font-weight: 600; }
    ul { margin: 0.4rem 0 0.8rem 1.2rem; }
    li { margin-bottom: 0.3rem; }

    /* ─── Tables ─── */
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 0.8rem 0 1.2rem 0;
        font-family: 'Inter', sans-serif;
        font-size: 0.78rem;
    }
    /* Wide decile tables (D1-D10 per chapter) */
    table.wide {
        font-size: 0.62rem;
    }
    table.wide th { padding: 0.25rem 0.2rem; font-size: 0.55rem; letter-spacing: 0; }
    table.wide td { padding: 0.2rem 0.2rem; font-size: 0.62rem; }
    th {
        font-weight: 600;
        text-align: right;
        padding: 0.45rem 0.5rem;
        border-bottom: 2px solid #1a2332;
        color: #1a2332;
        font-size: 0.7rem;
        letter-spacing: 0.03em;
    }
    th:first-child { text-align: left; }
    td {
        padding: 0.35rem 0.5rem;
        border-bottom: 1px solid #e5e8eb;
        text-align: right;
        color: #2c3e50;
    }
    td:first-child { text-align: left; font-weight: 500; }
    td.row-label { text-align: left; font-weight: 600; color: #1a2332; }
    td.universe { color: #95a5a6; font-style: italic; }
    td.bold { font-weight: 700; }
    tr:last-child td { border-bottom: 2px solid #1a2332; }

    .positive { color: #27ae60; }
    .negative { color: #c0392b; }
    .neutral { color: #b7950b; }

    /* ─── Verdict box ─── */
    .verdict {
        background: #f7f9fa;
        border-left: 3px solid #1a2332;
        padding: 0.8rem 1rem;
        margin: 1rem 0 1.2rem 0;
        font-family: 'Inter', sans-serif;
        font-size: 0.82rem;
        line-height: 1.6;
    }
    .verdict.green { border-left-color: #27ae60; background: #f0faf4; }
    .verdict.red { border-left-color: #c0392b; background: #fdf2f2; }

    /* ─── Charts ─── */
    .chart {
        margin: 1rem 0;
        text-align: center;
    }
    .chart img {
        max-width: 100%;
        border: 1px solid #e5e8eb;
    }

    /* ─── TOC ─── */
    .toc-entry {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        padding: 0.35rem 0;
        border-bottom: 1px dotted #ccd1d9;
        font-size: 0.95rem;
    }
    .toc-entry .toc-status {
        font-family: 'Inter', sans-serif;
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.05em;
    }

    /* ─── Comparison table (book vs ours) ─── */
    .comparison th { background: #f7f9fa; }

    /* ─── Footer ─── */
    .footer {
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        color: #95a5a6;
        text-align: center;
        margin-top: 3rem;
        padding-top: 1rem;
        border-top: 1px solid #e5e8eb;
    }
    """

    html.append(f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<title>What Still Works on Wall Street — Bivar Capital Research</title>
<style>{css}</style>
</head><body>
""")

    # ── COVER ──
    html.append("""
<div class="cover">
    <div class="cover-rule"></div>
    <h1>What Still Works<br>on Wall Street</h1>
    <p class="subtitle">
        A systematic retest of every factor from O'Shaughnessy's
        <em>What Works on Wall Street</em> using 21 years of out-of-sample data.
    </p>
    <div class="meta">
        <strong>Bivar Capital Research</strong><br>
        Lu&iacute;s Abrantes Portugal<br>
        April 2026<br><br>
        Data: Nasdaq Data Link / Sharadar Core US Equities<br>
        Period: 2005&ndash;2025 &nbsp;|&nbsp; Universe: US domestic common stock<br>
        Methodology: Quarterly TTM fundamentals, decile sort, 12-month averaged annual rebalance<br>
        Coverage: 15,456 domestic common stocks (12,151 delisted + 3,305 active)
    </div>
</div>
""")

    # ── TABLE OF CONTENTS ──
    html.append("""<div class="section-header new-page"><div class="section-title">Contents</div></div>""")
    toc_entries = [
        ('Executive Summary', '', NAVY),
    ]
    for ch in CHAPTERS:
        colors = {
            'WORKS': GREEN_MUTED, 'DEAD': RED_MUTED, 'INVERTED': RED_MUTED,
            'MARGINAL': GOLD_MUTED, 'WEAK': GOLD_MUTED,
        }
        toc_entries.append((ch['title'], ch['status'], colors.get(ch['status'], MID)))
    toc_entries.append(('Price Momentum', 'WORKS', GREEN_MUTED))
    toc_entries.append(('Value Composites', 'DIMINISHED', GOLD_MUTED))
    toc_entries.append(('Trending Value', 'WORKS*', GREEN_MUTED))
    toc_entries.append(('Conclusions & Implications', '', NAVY))

    for title, status, color in toc_entries:
        status_html = f'<span class="toc-status" style="color:{color}">{status}</span>' if status else ''
        html.append(f'<div class="toc-entry"><span>{title}</span>{status_html}</div>')


    # ── EXECUTIVE SUMMARY ──
    html.append(f"""
<div class="section-header new-page">
    <div class="section-num">Executive Summary</div>
    <div class="section-title">The Value Premium Is Largely Dead</div>
</div>

<div class="verdict red">
<strong>Central Finding:</strong> Of 12 single factors tested, only one traditional value metric
(P/S) retains a meaningful spread between cheap and expensive deciles. P/E, EBITDA/EV, and P/B
— the pillars of value investing — produce zero or negative spreads over 2005–2025. The factors
that survive share a common trait: they measure fundamentals that are hardest to manipulate.
</div>

<p>We replicate every single-factor strategy from O'Shaughnessy's <em>What Works on Wall Street</em>
(4th Edition, 2012) using Sharadar US equity data from 2005 to 2025. Our methodology mirrors the
book's: annual rebalance with decile portfolios, using 12 monthly cohorts averaged to eliminate
start-date bias. We apply two universe filters (&gt;$200M and &gt;$5B market capitalization) and
exclude financials for value metrics.</p>

<h3>Factor Scorecard — D1 vs D10 Annual Spread</h3>
<div class="chart avoid-break">
    <img src="data:image/png;base64,{scorecard_img}" alt="Scorecard">
</div>

<h3>Factor Summary — >$200M Universe (CAGR %, 2005–2025)</h3>
<table>
    <tr>
        <th style="text-align:left">Factor</th>
        <th>D1</th><th>D5</th><th>D10</th>
        <th>Univ</th><th>Spread</th><th>Alpha</th><th>5yr BR</th><th>Status</th>
    </tr>
""")

    status_map = {
        'P/S': ('WORKS', GREEN_MUTED), 'Accruals': ('MARGINAL', GOLD_MUTED),
        'Div Yield': ('WEAK', GOLD_MUTED), 'P/CF (FCF)': ('MARGINAL', GOLD_MUTED),
        'EBITDA/EV': ('DEAD', RED_MUTED), 'P/E': ('DEAD', RED_MUTED),
        'P/B': ('INVERTED', RED_MUTED), 'Buyback Yield': ('INVERTED', RED_MUTED),
        'SH Yield': ('INVERTED', RED_MUTED), 'EPS Growth': ('INVERTED', RED_MUTED),
        'Profit Margin': ('INVERTED', RED_MUTED), 'ROE': ('INVERTED', RED_MUTED),
    }

    for key in sorted(ALL_DATA.keys(), key=lambda k: ALL_DATA[k].get('spread', 0), reverse=True):
        if '>$200M' not in key:
            continue
        name = key.replace(' >$200M', '')
        st, sc = status_map.get(name, ('—', MID))
        html.append(build_summary_row(name, ALL_DATA[key], st, sc))

    html.append('</table>')

    html.append(f"""
<h3>Factor Summary — >$5B Universe (CAGR %, 2005–2025)</h3>
<table>
    <tr>
        <th style="text-align:left">Factor</th>
        <th>D1</th><th>D5</th><th>D10</th>
        <th>Univ</th><th>Spread</th><th>Alpha</th><th>5yr BR</th><th>Status</th>
    </tr>
""")

    for key in sorted(ALL_DATA.keys(), key=lambda k: ALL_DATA[k].get('spread', 0), reverse=True):
        if '>$5B' not in key:
            continue
        name = key.replace(' >$5B', '')
        st, sc = status_map.get(name, ('—', MID))
        html.append(build_summary_row(name, ALL_DATA[key], st, sc))

    html.append('</table>')

    # ── INDIVIDUAL CHAPTERS ──
    for ch in CHAPTERS:
        d200 = ALL_DATA.get(ch['key200'], {})
        d5b = ALL_DATA.get(ch['key5b'], {})

        spread_200 = d200.get('spread', 0)
        spread_5b = d5b.get('spread', 0)
        alpha_200 = d200.get('alpha_vs_univ', 0)
        alpha_5b = d5b.get('alpha_vs_univ', 0)
        d1_200 = d200.get('decile_cagrs', {}).get('1', 0)
        d10_200 = d200.get('decile_cagrs', {}).get('10', 0)
        d1_5b = d5b.get('decile_cagrs', {}).get('1', 0)
        br5_200 = d200.get('r5_pos_pct', 0)
        br5_5b = d5b.get('r5_pos_pct', 0)

        verdict_class = 'green' if ch['status'] == 'WORKS' else ('red' if ch['status'] in ('DEAD', 'INVERTED') else '')

        # Format body with data
        body = ch['body'].format(
            spread_200=f'{spread_200:+.1f}%',
            spread_5b=f'{spread_5b:+.1f}%',
            alpha_200=f'{alpha_200:+.1f}%',
            alpha_5b=f'{alpha_5b:+.1f}%',
            d1_200=f'{d1_200:+.1f}%',
            d10_200=f'{d10_200:+.1f}%',
            d1_5b=f'{d1_5b:+.1f}%',
            br5_200=f'{br5_200:.0f}%',
            br5_5b=f'{br5_5b:.0f}%',
        )

        # Charts
        decile_img = make_decile_comparison(
            f'{ch["title"]} — CAGR by Decile (2005–2025)', d200, d5b)
        annual_img = make_annual_spread(ch['title'], d200)

        html.append(f"""
<div class="section-header new-page">
    <div class="section-num">Chapter {ch['num']}</div>
    <div class="section-title">{ch['title']} {status_badge(ch['status'])}</div>
</div>

<div class="verdict {verdict_class}">
<strong>{ch['status']}</strong> &mdash;
Book D1 CAGR: {ch['book']['d1']} &rarr; Our D1: {d1_200:+.1f}% (&gt;$200M), {d1_5b:+.1f}% (&gt;$5B).
Spread: {spread_200:+.1f}% (&gt;$200M), {spread_5b:+.1f}% (&gt;$5B).
Alpha vs universe: {alpha_200:+.1f}% (&gt;$200M), {alpha_5b:+.1f}% (&gt;$5B).
</div>

<h3>Original Book Claims (1964–2009)</h3>
<table class="comparison">
    <tr><th style="text-align:left">Metric</th><th style="text-align:left">Book Value</th></tr>
    <tr><td>D1 CAGR</td><td>{ch['book']['d1']}</td></tr>
    <tr><td>D1–D10 Spread</td><td>{ch['book']['spread']}</td></tr>
    <tr><td>Sharpe Ratio</td><td>{ch['book']['sharpe']}</td></tr>
    <tr><td>5yr / 10yr Base Rate</td><td>{ch['book']['br5']} / {ch['book']['br10']}</td></tr>
    <tr><td>Conclusion</td><td><em>{ch['book_verdict']}</em></td></tr>
</table>

<h3>Our Results — Full Decile Breakdown</h3>
<table class="wide">
    <tr>
        <th style="text-align:left"></th>
        <th>D1</th><th>D2</th><th>D3</th><th>D4</th><th>D5</th>
        <th>D6</th><th>D7</th><th>D8</th><th>D9</th><th>D10</th>
        <th>Univ</th><th>Spread</th><th>Alpha</th>
    </tr>
    {build_decile_table(d200, '&gt;$200M')}
    {build_decile_table(d5b, '&gt;$5B')}
</table>

<table class="comparison">
    <tr><th style="text-align:left">Metric</th><th>Book</th><th>Our (&gt;$200M)</th><th>Our (&gt;$5B)</th></tr>
    <tr><td>D1 CAGR</td><td>{ch['book']['d1']}</td><td>{d1_200:+.1f}%</td><td>{d1_5b:+.1f}%</td></tr>
    <tr><td>D1–D10 Spread</td><td>{ch['book']['spread']}</td><td>{spread_200:+.1f}%</td><td>{spread_5b:+.1f}%</td></tr>
    <tr><td>5yr Base Rate</td><td>{ch['book']['br5']}</td><td>{br5_200:.0f}%</td><td>{br5_5b:.0f}%</td></tr>
    <tr><td>D1 Alpha vs Universe</td><td>Positive</td><td>{alpha_200:+.1f}%</td><td>{alpha_5b:+.1f}%</td></tr>
</table>
""")

        if decile_img:
            html.append(f'<div class="chart avoid-break"><img src="data:image/png;base64,{decile_img}"></div>')
        if annual_img:
            html.append(f'<div class="chart avoid-break"><img src="data:image/png;base64,{annual_img}"></div>')

        html.append(f"""
<h3>Analysis</h3>
{body}
""")

    # ── MOMENTUM ──
    html.append(f"""
<div class="section-header new-page">
    <div class="section-num">Chapter 13</div>
    <div class="section-title">Price Momentum {status_badge('WORKS')}</div>
</div>

<div class="verdict green">
<strong>WORKS</strong> &mdash; Momentum 6-1 delivers +13.5% CAGR at &gt;$5B with monthly
rebalance (book: 14.52%). The strongest standalone factor in both the book and our tests.
With concentration and regime filters: up to +18.1% CAGR, Sharpe 0.86.
</div>

<h3>Original Book Claims (1927–2009)</h3>
<table class="comparison">
    <tr><th style="text-align:left">Metric</th><th style="text-align:left">Book Value</th></tr>
    <tr><td>D1 CAGR (6-month momentum)</td><td>14.11%</td></tr>
    <tr><td>D10 CAGR (worst momentum)</td><td>4.15% &mdash; worse than T-bills</td></tr>
    <tr><td>5yr / 10yr Base Rate</td><td>87% / 98%</td></tr>
    <tr><td>Sharpe</td><td>0.37</td></tr>
    <tr><td>Conclusion</td><td><em>"Strongest standalone growth factor. Potent but highly volatile."</em></td></tr>
</table>

<h3>Our Results (2005–2025, Monthly Rebalance)</h3>
<table>
    <tr><th style="text-align:left">Configuration</th><th>CAGR</th><th>Sharpe</th><th>Max DD</th></tr>
    <tr><td>Mom 6-1, 25 stocks, &gt;$200M</td><td>+10.8%</td><td>0.55</td><td>&minus;68.6%</td></tr>
    <tr><td>Mom 6-1, 25 stocks, &gt;$1B</td><td>+13.0%</td><td>0.55</td><td>&minus;68.6%</td></tr>
    <tr><td><strong>Mom 6-1, 25 stocks, &gt;$5B</strong></td>
        <td class="positive bold">+13.5%</td><td class="bold">0.68</td><td>&minus;64.3%</td></tr>
</table>

<h3>Enhanced Variants (&gt;$5B)</h3>
<table>
    <tr><th style="text-align:left">Variant</th><th>CAGR</th><th>Sharpe</th><th>Max DD</th></tr>
    <tr><td>Pure momentum, 10 stocks</td>
        <td class="positive">+17.1%</td><td>0.70</td><td>&minus;59.2%</td></tr>
    <tr><td>Excl. top P/S decile, 10 stocks</td>
        <td class="positive bold">+18.1%</td><td class="bold">0.78</td><td>&minus;57.0%</td></tr>
    <tr><td>Excl. P/S + SY + MA200 regime filter</td>
        <td>+15.2%</td><td class="positive bold">0.86</td><td class="positive bold">&minus;28.5%</td></tr>
    <tr><td>MA200 regime filter only, 25 stocks</td>
        <td>+11.3%</td><td>0.70</td><td>&minus;40.0%</td></tr>
</table>

<h3>Analysis</h3>
<p>Momentum is the strongest factor in both the book and our dataset. At &gt;$5B with monthly
rebalance, 6-month price momentum with a 1-month skip delivers +13.5% CAGR &mdash; within 1% of
the book's 14.52%. The signal survives 21 years of out-of-sample data.</p>

<p>Concentration amplifies returns: narrowing to 10 stocks pushes CAGR to +17.1%. Excluding the
most expensive stocks by P/S &mdash; removing the "momentum into overvaluation" trap &mdash; adds
another percentage point to reach +18.1%.</p>

<p>The MA200 regime overlay is the most effective risk management tool we tested. When the broad
market trades below its 200-day moving average, the strategy holds cash. This reduces maximum
drawdown from &minus;64.3% to &minus;28.5% at the cost of ~2% CAGR, pushing the Sharpe ratio to
0.86. The rule is simple, mechanical, and has no parameters to overfit.</p>

<p>Market capitalization matters. Below $1B, momentum captures pump-and-dump artifacts and illiquid
micro-cap noise. Above $5B, it captures genuine institutional capital flows, earnings-driven
re-ratings, and persistent factor momentum. The implementable universe (&gt;$5B) produces
both higher returns and higher Sharpe ratios than the broader set.</p>

<h3>Book vs Reality</h3>
<table class="comparison">
    <tr><th style="text-align:left">Metric</th><th>O'Shaughnessy</th><th>Our Results</th></tr>
    <tr><td>D1 CAGR</td><td>14.52%</td><td>+13.5% (&gt;$5B, 25 stocks)</td></tr>
    <tr><td>"Strongest growth factor"</td><td>Yes</td><td class="positive bold">Confirmed</td></tr>
    <tr><td>"Highly volatile"</td><td>Yes</td><td class="negative bold">Confirmed (&minus;64% max DD)</td></tr>
    <tr><td>Enhanced variants</td><td>Not tested</td><td>+18.1% / Sharpe 0.86 with filters</td></tr>
</table>
""")

    # ── VALUE COMPOSITES ──
    html.append(f"""
<div class="section-header new-page">
    <div class="section-num">Chapter 14</div>
    <div class="section-title">Value Composites {status_badge('DIMINISHED')}</div>
</div>

<div class="verdict">
<strong>DIMINISHED</strong> &mdash; VC2 delivers +12.1% CAGR at &gt;$200M with monthly rebalance
(book: 17.30%). The composite underperforms its best single component because 4 of 6 constituent
factors are broken or inverted.
</div>

<h3>Original Book Claims (1964–2009)</h3>
<table class="comparison">
    <tr><th style="text-align:left">Composite</th><th>Components</th><th>CAGR</th><th>Sharpe</th><th>5yr BR</th></tr>
    <tr><td>VC1</td><td>P/B + P/E + P/S + EBITDA/EV + P/CF</td><td>17.18%</td><td>0.67</td><td>98%</td></tr>
    <tr><td>VC2</td><td>VC1 + Shareholder Yield</td><td>17.30%</td><td>0.72</td><td>98%</td></tr>
</table>

<h3>Our Results (2005–2025)</h3>
<table>
    <tr><th style="text-align:left">Composite</th><th>Annual &gt;$200M</th><th>Annual &gt;$5B</th>
        <th>Monthly &gt;$200M</th><th>Monthly &gt;$5B</th></tr>
    <tr><td>VC1</td><td>+4.9%</td><td>+9.7%</td><td>+10.8%</td><td>+10.2%</td></tr>
    <tr><td>VC2</td><td>+5.6%</td><td>+9.8%</td>
        <td class="positive bold">+12.1%</td><td>+10.0%</td></tr>
    <tr><td>VC3</td><td>+5.2%</td><td>+9.3%</td><td>+8.9%</td><td>+11.8%</td></tr>
</table>

<h3>Analysis</h3>
<p>With annual rebalance, the book's methodology, VC1 and VC2 deliver roughly +5% CAGR at
&gt;$200M &mdash; a 12 percentage point shortfall from the book's 17%. Monthly rebalance improves
results (VC2 reaches +12.1%) but represents a different strategy with higher turnover.</p>

<p>The composite's underperformance relative to its best component is the key diagnostic.
VC2 at &gt;$5B (+10.0%) <em>trails</em> P/S alone (+12.0%) because the composite averages a
working factor with several broken ones:</p>
<ul>
    <li>P/E: +0.0% spread at &gt;$5B</li>
    <li>EBITDA/EV: +1.0% spread</li>
    <li>P/B: &minus;3.8% spread (actively harmful)</li>
    <li>P/CF: +1.9% spread (marginal)</li>
    <li>SH Yield: &minus;3.7% spread (inverted)</li>
    <li><strong>P/S: +4.4% spread (the only strong contributor)</strong></li>
</ul>
<p>A composite of six factors where four are broken will always underperform a strategy using
only the one that works. The diversification benefit assumed by the composite framework has
become a diversification <em>penalty</em>.</p>
""")

    # ── TRENDING VALUE ──
    html.append(f"""
<div class="section-header new-page">
    <div class="section-num">Chapter 15</div>
    <div class="section-title">Trending Value {status_badge('WORKS')}</div>
</div>

<div class="verdict green">
<strong>WORKS &mdash; with expectations adjusted.</strong> The book promised 21.19% CAGR.
Our best configuration delivers +13.8%. The alpha is real (+5.4% over the S&amp;P 500),
but investors should expect roughly 35% less than the book's claims.
</div>

<h3>Original Book Claims (1964–2009)</h3>
<table class="comparison">
    <tr><th style="text-align:left">Metric</th><th>25-Stock</th><th>50-Stock</th></tr>
    <tr><td>CAGR</td><td class="bold">21.19%</td><td>19.85%</td></tr>
    <tr><td>Sharpe</td><td>0.93</td><td>0.82</td></tr>
    <tr><td>$10,000 &rarr;</td><td>$69,098,587</td><td>$41,411,163</td></tr>
    <tr><td>Max Drawdown</td><td>&minus;50.55%</td><td>&minus;52.87%</td></tr>
    <tr><td>5yr Base Rate</td><td>100%</td><td>100%</td></tr>
</table>

<h3>Our Results (2005–2025)</h3>
<table>
    <tr><th style="text-align:left">Variant</th><th>&gt;$200M</th><th>Sharpe</th>
        <th>&gt;$5B</th><th>Sharpe</th><th>Max DD</th></tr>
    <tr><td>TV1 (VC1 + Mom) &mdash; annual</td><td>+8.3%</td><td>&mdash;</td>
        <td>+9.3%</td><td>&mdash;</td><td>&mdash;</td></tr>
    <tr><td>TV2 (VC2 + Mom) &mdash; annual</td><td>+8.1%</td><td>&mdash;</td>
        <td>+10.3%</td><td>&mdash;</td><td>&mdash;</td></tr>
    <tr><td>TV1 &mdash; monthly</td><td>+10.7%</td><td>0.55</td>
        <td>+12.2%</td><td>0.71</td><td>&minus;47.0%</td></tr>
    <tr><td>TV2 &mdash; monthly</td><td>+10.7%</td><td>0.56</td>
        <td>+12.7%</td><td>0.75</td><td>&minus;46.7%</td></tr>
    <tr><td><strong>TV3 &mdash; monthly</strong></td><td>+10.5%</td><td>0.55</td>
        <td class="positive bold">+13.8%</td><td class="positive bold">0.82</td>
        <td>&minus;43.2%</td></tr>
</table>

<h3>Momentum's Contribution</h3>
<table>
    <tr><th style="text-align:left">&gt;$5B</th><th>Pure Value</th><th>+ Momentum</th><th>Lift</th></tr>
    <tr><td>VC1 / TV1</td><td>+10.2%</td><td>+12.2%</td><td class="positive">+2.0%</td></tr>
    <tr><td>VC2 / TV2</td><td>+10.0%</td><td>+12.7%</td><td class="positive">+2.7%</td></tr>
    <tr><td>VC3 / TV3</td><td>+11.8%</td><td>+13.8%</td><td class="positive">+2.0%</td></tr>
</table>

<h3>Analysis</h3>
<p>The gap between the book and reality is 7.4 percentage points. Even the most favorable
configuration (TV3, &gt;$5B, monthly rebalance) delivers +13.8%, not 21%. With annual
rebalance &mdash; the book's actual methodology &mdash; results fall to +8&ndash;10%, barely
above the S&amp;P 500's ~8.4%.</p>

<p>Momentum adds +2.0 to +2.7% CAGR and reduces drawdowns by 11&ndash;17 percentage points.
The momentum overlay avoids value traps by only buying cheap stocks that are also trending
upward. This contribution is genuine and consistent.</p>

<p>The degradation has four sources: (1) the value components have weakened, with 4 of 6
factors broken; (2) out-of-sample degradation of ~30&ndash;50% is typical in academic
literature; (3) our dataset includes 12,151 delisted stocks that may be more comprehensive
than the book's; (4) 2005&ndash;2025 is structurally different from 1964&ndash;2009, dominated
by growth and technology.</p>

<h3>Book vs Reality</h3>
<table class="comparison">
    <tr><th style="text-align:left">Metric</th><th>O'Shaughnessy</th><th>Our Results (best)</th></tr>
    <tr><td>CAGR</td><td class="bold">21.19%</td><td>+13.8% (TV3, &gt;$5B, monthly)</td></tr>
    <tr><td>Sharpe</td><td>0.93</td><td>0.82</td></tr>
    <tr><td>Max Drawdown</td><td>&minus;50.55%</td><td>&minus;43.2%</td></tr>
    <tr><td>Alpha vs S&amp;P 500</td><td>~+12%</td><td>+5.4%</td></tr>
</table>
""")

    # ── CONCLUSIONS ──
    html.append(f"""
<div class="section-header new-page">
    <div class="section-num">Conclusions</div>
    <div class="section-title">What Actually Works in 2026</div>
</div>

<h3>The Survivors</h3>
<table>
    <tr><th style="text-align:left">Factor</th><th>Spread (&gt;$200M)</th><th>Spread (&gt;$5B)</th>
        <th>5yr Base Rate</th><th>Mechanism</th></tr>
    <tr>
        <td class="positive bold">Price / Sales</td>
        <td class="positive bold">+9.6%</td>
        <td class="positive bold">+4.4%</td>
        <td>88%</td>
        <td>Revenue is hardest to manipulate</td>
    </tr>
    <tr>
        <td class="positive bold">Momentum 6-1</td>
        <td colspan="2" class="positive bold">+13.5% CAGR (&gt;$5B)</td>
        <td>N/A (monthly)</td>
        <td>Captures institutional capital flows</td>
    </tr>
    <tr>
        <td>Accruals</td>
        <td>+1.1%</td><td>+1.7%</td>
        <td>71%</td>
        <td>Earnings quality (weak signal)</td>
    </tr>
</table>

<h3>The Common Thread</h3>
<p>The surviving factors are built on inputs the market cannot easily game:</p>
<ul>
    <li><strong>Revenue</strong> &mdash; requires actual transactions with actual customers</li>
    <li><strong>Price</strong> &mdash; the market's real-time consensus, driven by institutional flows</li>
    <li><strong>Cash vs accruals gap</strong> &mdash; a simple measure of earnings reliability</li>
</ul>
<p>Factors built on more manipulable inputs &mdash; earnings (P/E), EBITDA (ignores SBC),
book value (ignores intangibles), cash flow (capex timing) &mdash; have lost their edge.
Markets have become more efficient at pricing through accounting noise. Only the cleanest
signals survive.</p>

<h3>Implications for Portfolio Construction</h3>
<ol>
    <li><strong>Simplify value screens.</strong> Use P/S as the primary value metric. Drop P/E,
    P/B, EBITDA/EV from composites &mdash; they add noise, not signal.</li>
    <li><strong>Momentum is the primary alpha source.</strong> Six-month price momentum with
    monthly rebalance at &gt;$5B delivers the highest risk-adjusted returns in the dataset.</li>
    <li><strong>Use regime filters for drawdown control.</strong> The 200-day moving average
    overlay reduces maximum drawdown by 35+ percentage points with minimal return sacrifice.</li>
    <li><strong>Concentrate.</strong> Alpha resides in the tails. Portfolios of 10&ndash;25
    positions outperform broader baskets of 50+.</li>
    <li><strong>Calibrate expectations.</strong> Implementable, post-cost alpha over the S&amp;P 500
    is 3&ndash;6% per annum &mdash; meaningful but not the 10%+ the book's backtests implied.</li>
</ol>

<h3>What O'Shaughnessy Got Right</h3>
<ul>
    <li>Systematic, rules-based investing outperforms discretionary stock selection</li>
    <li>Momentum is the strongest standalone factor</li>
    <li>Combining value and momentum (Trending Value) produces genuine alpha</li>
    <li>High-growth stocks are overpriced (confirmed)</li>
    <li>High-margin stocks underperform (confirmed and worsened)</li>
</ul>

<h3>What Has Changed</h3>
<ul>
    <li>P/E &mdash; from "one true faith" to zero spread</li>
    <li>EBITDA/EV &mdash; from "best single factor" to no edge</li>
    <li>P/B &mdash; from Fama-French foundation to inverted signal</li>
    <li>Value composites &mdash; from 17% to 5&ndash;12%, worse than their best component</li>
    <li>Trending Value &mdash; from 21% to 14%, still alpha but 35% less than claimed</li>
</ul>

<div style="text-align:center; margin:3rem 0 1rem 0; color:#95a5a6;">&#9670; &nbsp; &#9670; &nbsp; &#9670;</div>

<p style="text-align:center; max-width:520px; margin:0 auto; color:#5a6c7d; font-style:italic;">
The market has not stopped rewarding cheapness and momentum. It has become more efficient at
seeing through the accounting metrics that once defined "cheap." Value investing works in 2026
&mdash; but only when value is measured with fundamentals the market cannot game.
</p>

<div class="footer">
    <strong>Bivar Capital Research</strong> &nbsp;|&nbsp; bivarcapital.com<br>
    Data: Nasdaq Data Link / Sharadar Core US Equities &nbsp;|&nbsp;
    Period: 2005&ndash;2025 &nbsp;|&nbsp; 15,456 US domestic common stocks<br>
    Quarterly TTM fundamentals, decile sort, 12-month averaged annual rebalance
</div>
""")

    html.append("</body></html>")
    return ''.join(html)


if __name__ == '__main__':
    print("Generating HTML...")
    content = generate_html()

    print(f"Writing HTML ({len(content)//1024} KB)...")
    with open(OUTPUT_HTML, 'w') as f:
        f.write(content)

    print("Generating PDF with weasyprint...")
    try:
        import weasyprint
        doc = weasyprint.HTML(filename=str(OUTPUT_HTML))
        doc.write_pdf(str(OUTPUT_PDF))
        print(f"  PDF saved to {OUTPUT_PDF}")
    except Exception as e:
        print(f"  PDF failed: {e}")
        print("  Open the HTML in browser and print to PDF.")

    print("Done.")
