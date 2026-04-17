# Chapter 20 — Price Momentum

## What the Book Claims (1964–2009)
- D1 (best 6-month momentum) All Stocks: **14.52% CAGR**
- D10 (worst momentum): 3.67% — worse than T-bills
- "Potent but highly volatile"
- "Strongest standalone growth factor"

## What We Found (2005–2026)

Momentum uses prices only — no fundamental data changes affect it.

### Monthly Rebalance (Mom 6-1, 25 stocks)
| | CAGR | Sharpe | Max DD |
|---|---|---|---|
| >$200M | +10.8% | 0.55 | -68.6% |
| >$1B | +13.0% | 0.55 | -68.6% |
| **>$5B** | **+13.5%** | **0.68** | -64.3% |

### With MA200 Regime Overlay (>$5B)
| | CAGR | Sharpe | Max DD |
|---|---|---|---|
| No filter (25) | +13.5% | 0.68 | -57.1% |
| MA200 filter (25) | +11.3% | 0.70 | -40.0% |
| No filter (10) | +17.1% | 0.70 | -59.2% |

### With Value Exclusion Filters (>$5B, 10 stocks)
| | CAGR | Sharpe | Max DD |
|---|---|---|---|
| Pure Mom | +17.1% | 0.70 | -59.2% |
| Excl top P/S decile | **+18.1%** | 0.78 | -57.0% |
| Excl P/S+SY+MA200 | +15.2% | **0.86** | **-28.5%** |

## The Verdict

**Momentum is the strongest factor we found — confirming the book, but with caveats.**

At >$5B with monthly rebalance, Mom 6-1 delivers +13.5% CAGR (vs the book's 14.52%). The signal survives out-of-sample.

With concentration (10 stocks) and value exclusion filters: +18.1% CAGR. With MA200 overlay: Sharpe 0.86 and max DD of only -28.5%.

The book warned about volatility. We confirm: momentum crashes are real (2008: -36%, 2021: -32%). The MA200 overlay is the best risk management tool we found.

### Market Cap Is Critical
Below $1B, momentum is noise — dominated by pump-and-dumps and penny stocks. Above $5B, it captures genuine institutional flows and earnings-driven appreciation.

## O'Shaughnessy vs Ours

| | O'Shaughnessy | Our Results |
|---|---|---|
| D1 CAGR | 14.52% | 13.5% (>$5B, 25 stocks) |
| "Strongest growth factor" | Yes | **Confirmed** |
| "Highly volatile" | Yes | **Confirmed** (-64% max DD) |
| With enhancements | Not tested | +18.1% (excl filters, 10 stocks) |
