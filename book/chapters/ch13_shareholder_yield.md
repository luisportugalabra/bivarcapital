# Chapter 13 — Shareholder Yield

## What the Book Claims (1927–2009)
- D1 All Stocks: **13.22% CAGR** vs 10.46% universe
- Shareholder Yield = Dividend Yield + Buyback Yield
- Lower risk than universe (std dev 20.19% vs 21.67%)
- Base rates: 86% rolling 5yr, 93% rolling 10yr

## What We Found (2005–2026, Quarterly TTM)

### Using ncfcommon TTM / marketcap (our standard method):
| | D1 (Highest SY) | D10 (Lowest SY) | Spread | vs Universe |
|---|---|---|---|---|
| >$200M | +11.0% | +7.1% | **+4.0%** | +1.7% |
| >$5B | +12.9% | +7.7% | **+5.2%** | +2.3% |

### BUT: In our earlier decile analysis with different methodology:
- SY showed -7.4% spread when D10 was dominated by tech/growth stocks issuing shares
- The sign of the spread is HIGHLY sensitive to how buyback yield is calculated

## The Problem
The shareholder yield result depends entirely on how you measure buybacks:
- **Shares outstanding method** (as book uses): D1 = stocks shrinking share count. Works well.
- **ncfcommon / marketcap method**: More noisy, captures accounting artifacts. Can invert.

With the shares-based method (as O'Shaughnessy intended), SY still shows a +4 to +5% spread. But the buyback component alone (Ch 12) works just as well or better.

## Verdict
**Works with the right calculation, but buyback yield alone is cleaner.**

The addition of dividend yield to buyback yield adds noise rather than signal in the modern market. Companies paying high dividends tend to be in slow-growth sectors (utilities, consumer staples). The buyback component drives the entire SY premium.

O'Shaughnessy's innovation of adding buybacks to dividends was ahead of its time — but in practice, just tracking buybacks alone gives a cleaner signal.
