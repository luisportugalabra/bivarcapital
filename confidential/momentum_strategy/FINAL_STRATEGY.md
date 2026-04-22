# Bivar Capital — Portfolio Final
## CONFIDENCIAL

---

# PORTFOLIO: 50% Momentum + 50% BTC Systematic

Capital total: dividir em duas metades iguais. Cada metade segue as suas regras independentemente.

---

## ESTRATÉGIA 1: BivarOptimalMomentum (50% do capital)

### O que é
Uma estratégia que compra as 7 stocks americanas com mais momentum (subida de preço), entre empresas grandes e lucrativas. Quando o mercado está em queda, vende tudo e compra ouro (GLD).

### Regras — Passo a Passo

#### Último dia de trading de cada mês, depois do fecho (16h EST):

**Passo 1 — Verificar o mercado**
- Pegar no preço de fecho do S&P 500
- Calcular a média dos últimos 250 dias de trading do S&P 500
- Se o preço está **ABAIXO** da média → ir para **PASSO 1B (GLD)**
- Se o preço está **ACIMA** da média → ir para **PASSO 2 (Momentum)**

**Passo 1B — Comprar GLD (modo defensivo)**
- No primeiro dia de trading do mês seguinte, vender todas as stocks de momentum
- Comprar GLD (SPDR Gold Shares ETF) com todo o capital desta metade
- Manter GLD até ao último dia de trading do mês, repetir o PASSO 1
- Nota: GLD tem fee de entrada/saída de ~0.1%. Considerar no cálculo.

**Passo 2 — Calcular momentum**
Para cada stock americana:
- Retorno 6 meses = preço hoje / preço de há 126 dias de trading − 1
- Retorno 12 meses = preço hoje / preço de há 252 dias de trading − 1
- **Momentum composto = 50% × retorno 6 meses + 50% × retorno 12 meses**

**Passo 3 — Filtrar**
Eliminar stocks que não passam TODOS estes critérios:
- Market cap > $10 biliões (10 billion USD)
- EBIT > 0 (lucro operacional positivo — último valor reportado)
- US domestic common stock (não ADRs, não preferred, não ETFs)

**Passo 4 — Selecionar**
- Ordenar as stocks restantes por momentum composto, do maior para o menor
- Selecionar as top 7
- **Regra de sector:** máximo 3 stocks do mesmo sector. Se um sector já tem 3, saltar para a próxima stock na lista.

**Passo 5 — Executar (primeiro dia de trading do mês seguinte)**
- Vender as stocks que saíram do portfolio (ou vender GLD se vinha do modo defensivo)
- Comprar as 7 stocks selecionadas
- **Equal weight:** dividir o capital igualmente por 7 (~14.3% cada)

#### Repetir no último dia de trading de cada mês.

### Performance (backtest 1999–2026, dados diários, sem look-ahead, GLD com 0.2% round-trip cost)

| Métrica | Com GLD nos bear months |
|---|---|
| CAGR | +28.7% |
| Alpha vs S&P 500 | +21.5% |
| Sharpe Ratio | 1.10 |
| Sortino Ratio | 2.01 |
| Max Drawdown | -36.2% |
| Volatilidade | 26.1% |
| Win Rate | 62.3% |
| Meses em momentum | ~83% |
| Meses em GLD | ~17% |
| Meses totais | 297 |
| $10,000 → | $5,179,808 |

Nota: o MaxDD de -36.2% ocorre no crash das dotcom (Jan–Abril 2000). De 2005 em diante o MaxDD é -29.7%.

### Custos a considerar
- ~84 trades de stocks por ano (7 stocks × 12 meses, nem todas mudam)
- Comissões de stocks: ~$0 na Tasty Trade
- GLD: ~0.1% fee de entrada + 0.1% fee de saída × ~3-4 rotações/ano ≈ 0.6-0.8%/ano
- Estimativa de impacto nos custos: -0.5% a -1.0% CAGR
- **CAGR realista pós-custos: ~+27-28%**

### Porquê funciona
- **Momentum:** stocks que subiram tendem a continuar a subir — fluxos institucionais são lentos, informação propaga-se devagar
- **Market cap >$10B:** elimina ruído de small caps. Momentum em mega-caps captura fluxos reais
- **EBIT >0:** filtra empresas que perdem dinheiro — evita meme stocks e hype
- **MA250 regime:** quando o mercado inteiro cai, sais de stocks e vais para ouro
- **GLD nos bear months:** ouro sobe em média +1.5%/mês durante crises — hedge natural
- **Max 3/sector:** evita concentração excessiva (ex: 6 stocks de tech)
- **Último dia de trading:** testado todos os dias do mês (1, 5, 10, 15, 18, 20, 25, último) — último dia tem o melhor Sharpe (1.10) e menor MaxDD (-36.2%)

---

## ESTRATÉGIA 2: BTC Systematic (50% do capital)

### O que é
Uma estratégia de trend-following em Bitcoin. Compra BTC quando está em uptrend (3 condições verdadeiras). Vende e fica em cash quando qualquer condição falha.

### Regras — Passo a Passo

#### Todos os dias, ao fecho do mercado:

**Calcular 3 indicadores:**

1. **RSI(14)** — Relative Strength Index de 14 dias
   - Mede se o BTC está sobrecomprado ou sobrevendido
   - Cálculo: média dos ganhos / média das perdas nos últimos 14 dias
   - Resultado entre 0 e 100

2. **MA155** — Média móvel simples de 155 dias
   - Média do preço de fecho dos últimos 155 dias de trading
   - Se o preço está acima, BTC está em uptrend

3. **Vol20** — Volatilidade anualizada de 20 dias
   - Desvio padrão dos retornos diários dos últimos 20 dias × √365
   - Mede quão instável o preço está

**Regra de compra (TODAS as 3 têm de ser verdadeiras):**
- RSI(14) > 54
- Preço > MA155
- Vol20 < 100%

**Se as 3 são verdadeiras → COMPRAR BTC** (ou manter se já tem)
**Se qualquer uma falha → VENDER BTC, ir para cash**

#### Verificar diariamente. Executar ao fecho.

### Performance (backtest 2015–2026)

| Métrica | Valor |
|---|---|
| CAGR | +88.8% |
| Sharpe Ratio | 2.37 |
| Max Drawdown | -30.0% |
| Volatilidade | 36.2% |
| Tempo investido | 33% |
| Tempo em cash | 67% |
| $100,000 → | $131,245,451 |

### Notas importantes
- A estratégia está em **cash 67% do tempo** — só compra quando TUDO está alinhado
- O Sharpe de 2.37 é backtested — esperar degradação para 1.2-1.5 em live
- BTC é um asset de trend-following — sobe durante meses, depois crasha. As regras evitam os crashes.
- **11 anos de dados.** BTC pode mudar de carácter.

### Status actual (17 Abril 2026)
- BTC Price: $75,152
- RSI14: 76.9 (>54 = OK)
- MA155: $80,080 (preço ABAIXO = **FALHA**)
- Vol20: 37% (<100% = OK)
- **Sinal: CASH** (preço abaixo da MA155)

---

## PORTFOLIO COMBINADO — Como funciona na prática

### Alocação
| Estratégia | % Capital | Onde |
|---|---|---|
| BivarOptMom (stocks/GLD) | 50% | Tasty Trade |
| BTC Systematic (BTC/cash) | 50% | Tasty Trade |

### Cenários possíveis cada mês

| S&P > MA250? | BTC sinais OK? | Acção |
|---|---|---|
| SIM | SIM | 50% em 7 momentum stocks + 50% em BTC |
| SIM | NÃO | 50% em 7 momentum stocks + 50% em cash/T-bills |
| NÃO | SIM | 50% em GLD + 50% em BTC |
| NÃO | NÃO | 50% em GLD + 50% em cash/T-bills |

### Performance combinada (2015–2026)

| Métrica | Valor |
|---|---|
| CAGR | ~+67% |
| Sharpe | ~1.71 |
| Max Drawdown | ~-12% |
| Correlação Mom/BTC | 0.11 |

### Calendário mensal
- **Último dia de trading do mês:** Correr modelo de momentum. Verificar S&P vs MA250.
- **Primeiro dia de trading do mês seguinte:** Executar trades de momentum (ou comprar/vender GLD).
- **Todos os dias:** Verificar sinais BTC (RSI, MA155, Vol). Executar se sinal muda.

### Rebalance entre as duas metades
- Não rebalancear entre as duas estratégias. Cada metade corre independente.
- Se uma metade crescer muito mais que a outra, considerar rebalancear anualmente (ex: Janeiro).

---

## FEES E CUSTOS

| Item | Custo estimado |
|---|---|
| Comissões stocks (Tasty Trade) | ~$0 |
| GLD entry/exit (~0.1% cada) | ~0.6-0.8%/ano no capital de momentum |
| Spread BTC | ~0.1-0.3% por trade |
| Slippage (stocks) | ~0.1-0.2% por trade |
| **Total estimado** | **~1-2% CAGR** |

---

## O QUE PODE CORRER MAL

1. **Momentum crash:** as 7 stocks caem todas ao mesmo tempo. MaxDD -29% no backtest. Na realidade pode ser pior.
2. **BTC muda de carácter:** 11 anos de dados. Se BTC se tornar estável como ouro, a estratégia para de funcionar.
3. **Overfitting:** ambas as estratégias foram optimizadas em dados históricos. Esperar 20-30% degradação no Sharpe.
4. **Correlação sobe:** se momentum e BTC ficarem mais correlacionados, a diversificação desaparece.
5. **GLD falha como hedge:** em 2013 e 2022, ouro caiu junto com stocks. Pode acontecer de novo.
6. **Expectativa realista pós-custos e degradação:** CAGR ~+35-45%, Sharpe ~1.0-1.3

---

## PROMPT PARA NOVA SESSÃO

```
Estou no directório ~/sharadar. Tenho dados Sharadar em parquet + yfinance para BTC e GLD.

## Portfolio: 50% Momentum + 50% BTC Systematic

### Estratégia 1: BivarOptimalMomentum (50%)
- Momentum: 50% × retorno 6m (126 trading days) + 50% × retorno 12m (252 trading days)
- Universo: Market cap > $10B, EBIT > 0, US domestic common stock
- Selecção: Top 7, max 3/sector
- Regime: S&P 500 < MA250 → comprar GLD (não cash)
- Signal último dia de trading do mês, execução primeiro dia do mês seguinte
- Forward fill dos fundamentais SEM limite

### Estratégia 2: BTC Systematic (50%)
- BUY quando: RSI(14) > 54 AND Price > MA155 AND Vol20 anualizada < 100%
- SELL quando qualquer condição falha
- Verificar diariamente ao fecho

### Scripts
- generate_report.py: relatório momentum com posições
- audit_report.py: audit detalhado últimos 20 meses

### O que preciso
Gera os sinais actuais de ambas as estratégias. Diz-me o que comprar/vender.
```

---

*Bivar Capital — Abril 2026*
*CONFIDENCIAL — Não distribuir*
