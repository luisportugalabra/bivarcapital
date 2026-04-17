# Chapter 27 — Trending Value

## What the Book Claims (1964–2009)

The flagship strategy of the entire book.

| Metric | Trending Value (25 stocks) | All Stocks |
|---|---|---|
| **CAGR** | **21.19%** | 11.22% |
| **Sharpe** | **0.93** | 0.33 |
| **$10,000 →** | $69,098,587 | $1,329,513 |
| Max Drawdown | -50.55% | -55.54% |

- VC2 decile 1 → top 25 by 6-month momentum
- "Never had a 5-year period in which it lost money"
- Beat universe **100% of rolling 5yr and 10yr periods**
- 50-stock version: 19.85% CAGR, $10,000 → $41,411,163

O'Shaughnessy called this "the power of combining Value Factor Two and six-month price appreciation."

## What We Found (2005–2026, Quarterly TTM)

### Annual Rebalance (12 portfolios averaged)
| | >$200M | >$5B |
|---|---|---|
| TV1 (VC1 + Mom) | +8.3% | +9.3% |
| TV2 (VC2 + Mom) | +8.1% | +10.3% |
| TV3 (VC3 + Mom) | +8.8% | +9.9% |

### Monthly Rebalance
| | >$200M CAGR | >$200M Sharpe | >$5B CAGR | >$5B Sharpe | >$5B Max DD |
|---|---|---|---|---|---|
| TV1 | +10.7% | 0.55 | +12.2% | 0.71 | -47.0% |
| TV2 | +10.7% | 0.56 | +12.7% | 0.75 | -46.7% |
| **TV3** | +10.5% | 0.55 | **+13.8%** | **0.82** | **-43.2%** |

## The Verdict

**The book promised 21% CAGR. We got 13.8% at best.**

The gap is enormous — nearly 7 percentage points. Even with the most favorable configuration (TV3, >$5B, monthly rebalance with quarterly TTM data), the Trending Value strategy delivers +13.8% CAGR, not the 21% the book claimed.

With annual rebalance (the book's methodology), results drop to +8–10% — barely beating the S&P.

### What the Momentum Adds

| | Pure Value (VC) | + Momentum (TV) | Improvement |
|---|---|---|---|
| VC1/TV1 >$5B | +10.2% | +12.2% | +2.0% |
| VC2/TV2 >$5B | +10.0% | +12.7% | +2.7% |
| VC3/TV3 >$5B | +11.8% | +13.8% | +2.0% |

Momentum adds +2.0 to +2.7% CAGR and reduces drawdowns by 11–17 percentage points. This is genuine value — the momentum filter avoids value traps by only buying cheap stocks that are also trending upward.

### Why 21% → 13.8%

1. **The value premium has shrunk.** The composite relies on 6 value factors, 4 of which are now broken. This weakens the value screen.
2. **Out-of-sample degradation.** All backtested strategies lose edge when applied to new data. ~30-50% decay is typical.
3. **Survivorship bias in the original.** We use 12,151 delisted stocks; the book's dataset may have gaps.
4. **Different period.** 1964–2009 included multiple value-friendly decades. 2005–2026 is dominated by growth/tech.

### The Best Variant: TV3

Replacing shareholder yield with dividend yield alone (TV3) improves results at >$5B from +12.7% to +13.8%. This is because the shareholder yield component is unstable at the quarterly level while dividend yield is cleaner.

## O'Shaughnessy's Conclusion vs Ours

| | O'Shaughnessy | Our Results (best) |
|---|---|---|
| CAGR | 21.19% | 13.8% (TV3 >$5B monthly) |
| Sharpe | 0.93 | 0.82 |
| Max DD | -50.55% | -43.2% |
| "Never lost in 5yr" | Yes | Not tested monthly yet |
| Verdict | "Eye-popping" | Real alpha, but overstated |

The alpha is real (+5.4% over S&P). The strategy works. But 13.8% is not 21%. Investors expecting to double the book's claims need to adjust their expectations by roughly 35%.
