# Auditoria adversarial independente — BivarOptimalMomentum (USA)
**Data:** 2026-08-25 · **Dados:** Sharadar até 2026-05-14 · **Motor auditado:** `~/sharadar/generate_mom_gld_report.py`
**Método:** reimplementação independente (`~/momentum_research/audit_us_momentum.py`), sem reutilizar funções do original.

## A. Veredicto executivo
**Investiria capital real nesta estratégia na forma actual do MOTOR, com sizing moderado — mas não confiaria no TRACKER LIVE nem nos números de apresentação do site sem as correcções pendentes.**
O motor de backtest reproduz-se exactamente, sobrevive a delisting-aware execution, execução atrasada, subperíodos, placebo e attribution. As falhas estão na camada de apresentação e no código live — não no motor.
**Score de confiança no motor/backtest: 82/100.** No pipeline live/publicação: 45/100.

## B. Tabela de riscos
| Problema | Severidade | Evidência | Impacto | Resolvido? |
|---|---|---|---|---|
| Dados param a 14 Maio; report regenerado 22-24 Ago sobre dados velhos; Julho 2026 (-25% live) fora de todos os headline numbers | ALTA | mtime parquets vs mtime report | headline stats descrevem janela que exclui pior mês recente | NÃO |
| Tracker live selecciona de universo diferente (SNDK/LITE), sem guarda de 252d de história, mcap corrente vs filing, price-return vs total-return | ALTA | auditoria 20-Ago pts 2/4/10, código momentum_signal.py | série live não reconciliável com backtest; maior vencedor do YTD (+470% SNDK) é estruturalmente impossível no backtest | NÃO |
| Tracker live ignora o filtro de regime (calcula, mostra, nunca usa) | ALTA | momentum_signal.py `exec_tickers = sel7` | todo o valor defensivo do MA250 ausente do live | NÃO |
| "Alpha +18.3%" = CAGR total-return − S&P price-return, sem beta | MÉDIA | linha 211 do gerador; sp500_daily = ^GSPC price | alpha real CAPM vs SPY TR = +19.4pp/ano (por acaso semelhante, mas por razões erradas: beta 0.52 compensa os dividendos em falta) | NÃO |
| Sortino ×12 em vez de ×√12 + np.std sobre desvios | BAIXA | linha 265 do gerador | Sortino publicado inflacionado ~3.5x | NÃO |
| Delistings a meio do mês excluídos do retorno do mês | BAIXA (testado) | secção B da minha reimplementação | 10 meses em 339, tudo M&A (EOP, BLS, SGP...), direcção mista, CAGR inalterado (25.6→25.6) | Imaterial |
| `diag_holdings_log.csv` diverge do motor (6/246 meses iguais) | INCIDENTE | script diagnóstico de 15-Ago usa GLD-em-bear, ffill de preços e fundamentais mensais — é um artefacto de uma versão anterior | risco de confusão futura; apagar ou regenerar | NÃO |
| Parâmetros (top7, $10B, MA250, 50/50 6+12M) escolhidos in-sample; "339 months out-of-sample" é falso | MÉDIA | floor $5B→Sharpe 0.72, $20B→0.66 vs $10B→0.87: óptimo local | overfit moderado; a estrutura sobrevive aos vizinhos mas o $10B é o melhor dos três | NÃO (wording) |

## C. Bugs encontrados (novos, além dos da auditoria de 20-Ago)
1. **Exclusão de delistados intra-mês** (`common = bp.dropna() ∩ sp_p.dropna()`): a posição desaparecida é substituída pela média dos sobreviventes. Testei a correcção (vender no último trade disponível): **CAGR 25.6% → 25.6%, Sharpe 0.87 → 0.87**. Os 10 casos são aquisições, não falências — o viés é ~zero neste universo ($10B + EBIT>0). Confirmado imaterial, mas deve ser corrigido por higiene.
2. **`diag_holdings_log.csv` é de outra estratégia** (GLD, ffill, fundamentais mensais) — artefacto morto que contradiz o motor em 240/246 meses.

## D. Resultados auditados (reimplementação independente, custos 14bps)
| Versão | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| Publicado (report) | +25.6% | 0.87 | -33.2% |
| Minha reimplementação (código separado) | +25.6% | 0.87 | -33.2% |
| Delisting-aware (honesta) | +25.6% | 0.87 | -33.2% |
| Execução T+2 close | +25.3% | 0.89 | -34.7% |
| Execução no próprio close (optimista) | +29.7% | 0.95 | -30.8% |
| **2017–2026 isolado** | **+30.3%** | **0.85** | -33.2% |
| SPY total-return (mesma janela) | +8.8% | — | — |
| Alpha CAPM (beta 0.52, vs SPY TR) | **+19.4pp/ano** | — | — |

Subperíodos (todos batem o S&P): 98-03: 28.0% · 04-08: 26.5% · 09-12: 12.8% (mais fraco, S&P 11.9%) · 13-16: 23.9% · 17-20: 18.3% · 21-26: 40.0%.
Placebo: ranking invertido 2.9%/Sharpe 0.11 · random-7 do mesmo universo 6.2% · sinal desfasado 1 mês 20.4% (decay lento = sinal genuíno, não artefacto de microestrutura).
Concentração: sem top 10 meses → 14.3% CAGR; sem top 10% meses → 2.5% — mas o S&P na mesma cirurgia dá **-1.2%**; é o perfil normal de equities, não fragilidade. Nenhum outlier absurdo de dados (top contribuidores: NVDA, APP, MU, QCOM — retornos reais verificáveis).
Liquidez: ADV mediana das selecções $114M/dia; p10 $24M — investível até dezenas de milhões de capital. (BVSN/TPL com ADV baixo são casos de 1999-2004.)

## E. O que continua incerto
- **Categorias do tickers.parquet são o estado corrente**, não point-in-time (empresa reclassificada de/para "Domestic Common Stock" muda o universo retroactivamente). Sem snapshot histórico da tabela tickers não é mensurável. Risco baixo mas não provado zero.
- `marketcap` do SF1 é o do filing date (não do dia do sinal) — direcção conservadora, mas empresas em ascensão rápida entram ~2-4 meses tarde; não quantificado.
- 2026 live vs backtest permanece irreconciliável até os dados serem actualizados e as guardas de universo impostas no live.

## F. Próximas 3 auditorias mais valiosas
1. **Actualizar Sharadar → regerar → comparar Mai-Ago 2026 backtest vs conta real**, posição a posição. É o único teste que valida o pipeline inteiro de uma vez.
2. **Impor no live as guardas do backtest** (252d história, mcap do filing, total return, regime) e correr 3 meses em paralelo com a versão actual.
3. **Snapshot point-in-time da tabela tickers** (Sharadar TICKERS tem versões? senão arquivar mensalmente a partir de agora) para fechar a última porta de survivorship.
