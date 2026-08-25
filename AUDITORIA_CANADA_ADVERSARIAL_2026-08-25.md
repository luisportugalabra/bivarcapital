# Auditoria adversarial independente — Canada TSX Momentum
**Data:** 2026-08-25 · **Motor auditado:** `~/eodhd_data/generate_canada_report_v3.py` + `~/momentum_research/backtest.py`
**Método:** reimplementação independente (`~/momentum_research/audit_canada_momentum.py`), variantes honestas, falsificação.

## A. Veredicto executivo
**Investiria capital real. O único bug material (lookahead no filtro de NetIncome) foi corrigido e republicado no site em 2026-08-25** — os números ao vivo já são os honestos: CAGR 34.4%, Sharpe 1.22, MaxDD -26.0% (antes: 36.1/1.35/-24.5, commit `21b7cd9`).
O edge é genuíno, persistente e sobrevive a todas as tentativas de destruição.
**Score de confiança: 85/100** (subiu de 78 depois da correção; os dois pontos restantes na secção F são refinamentos, não bugs).

## B. Tabela de riscos
| Problema | Severidade | Evidência | Impacto | Resolvido? |
|---|---|---|---|---|
| **Lookahead no NetIncome: 92.4% dos filing_date EODHD TO são ≤ fim do período** — o filtro sabia o resultado trimestral no dia em que o trimestre fechava, 1-3 meses antes de ser público | **ALTA** (era) | distribuição empírica de 16.264 filing_dates (mediana lag=0 dias); reruns A vs B | CAGR 36.1→34.4, Sharpe 1.35→1.22, MaxDD -24.5→-26.0 | **SIM — corrigido 2026-08-25** (commit `21b7cd9`). Loader do v3 passou a usar sempre period+60d, igual ao `ebit_test.py`. Site já publica os números corrigidos. |
| Gap de custos nas transições de regime (declarado no docstring como +1.1pp) | BAIXA | rerun C com custos honestos: 34.6→34.7 | ~0 — a sobrecarga nos meses cash compensa as transições grátis | Imaterial (o disclosure sobrestima o problema) |
| Posições que desaparecem a meio do mês contam 0% | BAIXA | rerun D: 12 casos em 26 anos, pior NGD -33% (Mar 2026) | CAGR 34.7→34.4 | Imaterial |
| 24% dos tickers TO com preços congelados ≥15d; 251 tickers com mcap corrompido (>20x mediana) | BAIXA no estratégia | exclusão frozen na elegibilidade: 34.4→33.7/1.20 | os filtros mcap-top80%+NI>0+momentum já evitam os contaminados | Residual aceitável |
| 1101 datas fantasma (fins de semana) no painel EODHD cru | RESOLVIDO | v3 executa no calendário ^GSPTSE limpo; réplica independente confirma | — | SIM (v3) |
| MaxDD -39% vs -26% (mistério B4 da auditoria de 20-Ago) | FECHADO | linhagem v2 morta (calendário contaminado + zero-lag); v3 reconstruído de raiz; a minha réplica independente dá -24.5% com a config de produção | — | SIM |

## C. Resultados auditados (reimplementação independente, 40bps, execução T+1 real)
| Versão | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| Publicado ANTES da correção (site/report v3, até 2026-08-24) | +36.1% | 1.35 | -24.5% |
| Minha réplica (código separado) | +36.3% | 1.35 | -24.5% |
| **+ NetIncome com lag honesto de 60d** (auditoria, dados até 24-Ago) | **+34.6%** | **1.22** | **-26.0%** |
| **PUBLICADO NO SITE desde 2026-08-25** (regeneração completa, commit `21b7cd9`) | **+34.4%** | **1.22** | **-26.0%** |
| + custos honestos (transições pagas) | +34.7% | 1.23 | -26.1% |
| + delist-aware (exit no último trade) | +34.4% | 1.21 | -26.5% |
| + exclusão de preços congelados | +33.7% | 1.20 | -26.1% |
| **2017-2026 isolado (honesta)** | **+33.9%** | **1.01** | -26.5% |

A pequena diferença entre 34.6% (auditoria) e 34.4% (site) é ruído de reamostragem TSX/yfinance entre execuções, não um bug adicional.

Subperíodos (versão honesta): 2000-03: 51.2%/1.91 · 04-08: 29.7%/1.04 · 09-12: 30.8%/1.44 · 13-16: 29.6%/1.33 · 17-20: 44.4%/1.40 · 21-26: 26.8%/0.76 (o mais fraco; pior ano 2023: -15%).
Placebo: ranking invertido 4.9%/0.07 · random-10 do mesmo universo 10.5% · sinal desfasado 1 mês 30.6%. O pipeline distingue sinal de ruído.
Concentração: sem top 10% dos meses → 10.0% (TSX na mesma cirurgia: -2.0%) — perfil normal de equities, sem outliers artificiais.

## D. Alegações anteriores
- "36.1/1.35/-24.5" → **FALSA/EXAGERADA** (continha lookahead; já não está publicada — corrigida para 34.4/1.22/-26.0 em 2026-08-25)
- "Realistic 1-day execution lag" → **CONFIRMADA** (verificada no código e na réplica)
- "mcap/NI filters independent" → **CONFIRMADA**
- "Sharpe rf-adjusted, Sortino RMS" → **CONFIRMADA**
- "+1.1pp cost gap disclosed" → **EXAGERADA** (na prática ~0; as duas pontas compensam-se)
- "MaxDD trough 2009-04" → **CONFIRMADA**
- Docstring "STATUS: not locked, 40bps not re-verified" → honesto e ainda válido

## E. O que continua incerto
- 40bps de custo herdados da config antiga (top15/EBIT); as holdings atuais (top80% mcap) são maiores — o custo real é provavelmente MENOR, direção favorável mas não medida.
- Universo TO da EODHD: sem tabela de delistings explícita; tickers extintos estão no painel (o `_old` sufixo existe) mas não há prova exaustiva de cobertura completa de mortos pré-2010 — risco de survivorship residual não mensurável com esta fonte.
- TSX via yfinance: ~0.2pp de deriva entre downloads (a diferença 36.1 vs 36.3 da minha réplica).

## F. Próximas 2 auditorias mais valiosas
*(item 1 da lista original — corrigir o loader NI — está feito e publicado; ficam os dois seguintes)*
1. **Medir o custo real das holdings atuais via IBKR** (spreads TSX das top-80%-mcap) e substituir os 40bps herdados. Tentativa em 2026-08-25 falhou — TSX fechada, dados de bid/ask não fiáveis (bid=ask idêntico em vários nomes). Repetir com a bolsa aberta (9:30-16:00 ET).
2. **Comparação live vs backtest posição-a-posição durante 3 meses** (o mesmo teste recomendado para o US) — valida o pipeline completo de uma vez.
