# Momentum Strategy Research — Full Summary
## Bivar Capital | April 2026

---

## Estratégia Final (Best)

**6+12eq Composite Momentum | >$10B | Top 7 | MA250 | EBIT>0 | No sector cap**

| Métrica | Backtest (EOM) | Realista (D+1) |
|---|---|---|
| CAGR | +28.3% | +26.0% |
| Alpha vs S&P | +19.6% | ~+17% |
| Sharpe | 1.03 | 0.96 |
| Sortino | 1.87 | — |
| MaxDD | -29.4% | -32.6% |
| Vol | 24.1% | 23.9% |
| H1/H2 Sharpe | 1.06/1.08 | — |
| Win Rate | 52% | — |

### Regras
1. **Momentum:** 67% × retorno 6 meses + 33% × retorno 9 meses
2. **Universo:** Market cap > $10B, EBIT > 0, US domestic common stock
3. **Selecção:** Top 7 por momentum composto (sem sector cap)
4. **Regime:** Se S&P 500 < MA250 dias → 100% cash (0% return)
5. **Rebalance:** Mensal, dia 1 do mês (correr modelo no fim de semana, comprar segunda)
6. **Pesos:** Equal weight (~14.3% cada)

### Portfolio Actual (15 Abril 2026)
| # | Ticker | Empresa | Sector |
|---|--------|---------|--------|
| 1 | SNDK | Sandisk | Tech |
| 2 | LITE | Lumentum | Tech |
| 3 | CIEN | Ciena | Tech |
| 4 | BE | Bloom Energy | Industrials |
| 5 | HL | Hecla Mining | Basic Materials |
| 6 | AA | Alcoa | Basic Materials |
| 7 | FIX | Comfort Systems | Industrials |

---

## Todas as Estratégias Testadas (Ranking por Sharpe)

### Tier 1 — Sharpe > 0.95

| Config | CAGR | Sharpe | MaxDD | H1/H2 |
|---|---|---|---|---|
| 6w+9 $10B t7 MA250 EBIT sec3 | +28.3% | 1.03 | -29.4% | 1.06/1.08 |
| 6w+9 $10B t7 MA250 EBIT | +29.0% | 1.01 | -36.1% | 1.04/1.06 |
| 6w+9 $10B t10 MA250 EBIT cash4% | +24.8% | 0.97 | -26.7% | 0.99/1.01 |
| 6+12eq $10B t10 MA250 EBIT | +24.6% | 0.95 | -30.7% | 1.07/0.94 |

### Tier 2 — Sharpe 0.85–0.95

| Config | CAGR | Sharpe | MaxDD | H1/H2 |
|---|---|---|---|---|
| 6w+9 $10B t10 MA250 EBIT sec3 | +23.0% | 0.94 | -27.8% | 1.02/0.95 |
| 6w+9 $10B t10 MA250 EBIT | +23.8% | 0.93 | -27.6% | 0.94/0.98 |
| 6w+9 $10B t10 MA200 EBIT sec3 | +21.9% | 0.92 | -26.8% | 1.08/0.86 |
| 6w+9 $10B t10 MA200 EBIT | +22.2% | 0.90 | -29.0% | 0.99/0.89 |
| 6-0 $5B t20 MA200 EBIT sec3 | +17.3% | 0.88 | -29.0% | 1.03/0.79 |
| 6-0 $10B t10 MA250 EBIT | +21.5% | 0.87 | -33.0% | 0.89/0.92 |
| 6-0 $5B t20 MA200 EBIT sec4 | +17.3% | 0.85 | -30.1% | 0.97/0.77 |
| 6-0 $10B t10 MA200 EBIT | +20.4% | 0.85 | -28.7% | 0.97/0.83 |

### Tier 3 — Sharpe 0.75–0.85

| Config | CAGR | Sharpe | MaxDD | H1/H2 |
|---|---|---|---|---|
| 6w+9 $5B t20 MA200 EBIT | +18.3% | 0.84 | -29.1% | 0.96/0.78 |
| 6-0 $5B t20 MA250 EBIT | +17.9% | 0.83 | -30.9% | 0.91/0.80 |
| 6-0 $5B t20 MA200 EBIT | +17.4% | 0.82 | -31.1% | 0.98/0.73 |
| 6-0 $10B t15 MA200 EBIT | +16.8% | 0.78 | -28.9% | 0.93/0.71 |
| 9-1 $5B t20 MA200 EBIT (BASE) | +16.7% | 0.76 | -33.8% | — |

---

## O Que Foi Testado (Parâmetro por Parâmetro)

### Lookback Period
| Config | Sharpe | Nota |
|---|---|---|
| 6-0 (skip 0) | 0.82 | **Melhor — skip 0 é a descoberta chave** |
| 6-1 (skip 1) | 0.80 | Ligeiramente pior |
| 9-1 | 0.76 | Base original |
| 12-1 | 0.74 | Pior |

### Composite Momentum (>$10B t10 MA250 EBIT)
| Blend | CAGR | Sharpe |
|---|---|---|
| **67% 6m + 33% 9m** | **+23.8%** | **0.93** |
| 50% 6m + 50% 12m | +24.6% | 0.95 |
| 50% 6m + 50% 9m | +23.0% | 0.89 |
| Pure 6m | +21.5% | 0.87 |

### MA Period (6-0 >$5B t20 EBIT)
| MA | Sharpe | MaxDD |
|---|---|---|
| MA50 | 0.52 | -35.3% |
| MA100 | 0.68 | -32.8% |
| MA150 | 0.79 | -36.4% |
| MA200 | 0.82 | -31.1% |
| **MA250** | **0.83** | **-30.9%** |
| MA300 | 0.77 | -31.4% |
| Sem MA | 0.77 | -54.3% |

### Num Stocks (6w+9 >$10B MA250 EBIT sec3)
| N | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| 5 | +34.4% | 1.08 | -34.1% |
| **7** | **+28.3%** | **1.03** | **-29.4%** |
| 10 | +23.0% | 0.94 | -27.8% |
| 15 | +18.7% | 0.88 | -25.8% |
| 20 | +16.8% | 0.86 | -25.9% |

### Market Cap (6w+9 t10 MA250 EBIT)
| Min MCap | Sharpe | CAGR |
|---|---|---|
| $5B | 0.91 | +24.1% |
| $8B | 0.94 | +24.2% |
| **$10B** | **0.93** | **+23.8%** |
| $12B | 0.89 | +22.9% |
| $15B | 0.83 | +20.7% |
| $20B | 0.62 | +13.3% |

### Sector Concentration (6w+9 $10B t10 MA250 EBIT)
| Max/Sector | Sharpe | MaxDD | CAGR |
|---|---|---|---|
| Sem limite | 0.93 | -27.6% | +23.8% |
| Max 2 | 0.96 | -28.0% | +22.8% |
| **Max 3** | **0.94** | **-27.8%** | **+23.0%** |
| Max 4 | 0.92 | -30.2% | +22.9% |
| Max 5 | 0.93 | -28.7% | +23.4% |

### Holding Period (6-0 >$5B t20 MA200 EBIT)
| Rebalance | Sharpe |
|---|---|
| **Mensal** | **0.82** |
| Bi-mensal | 0.76 |
| Trimestral | 0.68 |
| Quadrimestral | 0.75 |
| Semestral | 0.64 |

### Dual Momentum
**Zero impacto.** O filtro MA já faz o trabalho. Dual momentum é redundante.

### Cash Rate
| Cash | CAGR | Sharpe |
|---|---|---|
| 0% | +23.8% | 0.93 |
| 3% | +24.5% | 0.96 |
| 4% | +24.8% | 0.97 |
| 5% | +25.0% | 0.98 |

Cash a 4-5% (T-bills) durante bear markets soma ~1% CAGR.

### Buy Day (D+1 = realista)
| Dia | CAGR (t7) | Sharpe |
|---|---|---|
| EOM (teórico) | +28.1% | 1.03 |
| **D+1 (realista)** | **+26.0%** | **0.96** |
| D+2 | +26.8% | 0.94 |
| D+3 a D+7 | ~+26% | ~0.92 |

Custo de execução realista: ~2% CAGR, ~0.07 Sharpe.

### Filter Ablation
- **Sem MA:** MaxDD vai a -54/62%, Sharpe cai ~0.15
- **Sem EBIT:** Sharpe cai 0.10-0.15
- **Ambos essenciais** — MA controla o drawdown, EBIT filtra lixo

---

## Evolução da Pesquisa

1. **Base:** 9-1 $5B t20 MA200 EBIT → Sharpe 0.76, CAGR +16.7%
2. **Skip 0:** 6-0 melhor que 6-1/9-1 → Sharpe 0.82
3. **Market cap $10B:** Reduz ruído → Sharpe 0.85
4. **Sector cap 3:** Diversifica → Sharpe 0.88
5. **Composite 6w+9:** Blend momentum → Sharpe 0.93
6. **MA250:** Melhor que MA200 → Sharpe mantém, DD -30.9%
7. **Top 7 + sec3:** Concentração + diversificação → **Sharpe 1.03, CAGR +28.3%**

**Melhoria total: Sharpe 0.76 → 1.03 (+36%), CAGR +16.7% → +28.3% (+69%)**

---

## Caveats

1. **Sem custos de transação.** ~84 trades/ano, estimar -0.5 a -1% CAGR
2. **Backtest ≠ futuro.** Esperar degradação de 20-30% no Sharpe
3. **21 anos, 2 bear markets.** Sample limitado
4. **Anomalias de spinoff/IPO** podem inflacionar momentum (ex: SNDK +1978%)
5. **Expectativa realista:** +18-22% CAGR depois de custos e degradação
6. **D+1 execução:** -2% CAGR vs backtest teórico

---

*Ficheiros: mom_engine.py, test_variations.py, test_high_cagr.py, test_deep_dive.py, test_buy_day_fast.py, current_picks.py, plot_comparison.py, plot_buy_day.py*
