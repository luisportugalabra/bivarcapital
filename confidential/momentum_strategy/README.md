# Momentum Strategy — Bivar Capital
## CONFIDENCIAL

---

## Estratégia Final

**6+12eq Composite Momentum | >$10B | Top 7 | MA250 | EBIT>0 | Signal D18 → Buy D19**

### Backtest (2005–2026, dados diários, sem look-ahead bias)

| Métrica | Valor |
|---|---|
| CAGR | +24.5% |
| Alpha vs S&P 500 | +16.1% |
| Sharpe Ratio | 0.93 |
| Sortino Ratio | 1.64 |
| Max Drawdown | -26.2% |
| Volatilidade | 23.3% |
| Win Rate | 51% |
| Meses invested | 199 (78%) |
| Meses cash | 55 (22%) |
| $10,000 → | $1,035,223 |

---

## Regras (passo a passo)

### 1. Dia 18 de cada mês — Correr o modelo

Depois do fecho do mercado (16h EST), usar os preços de fecho desse dia para:

**a) Verificar o filtro de regime (MA250):**
- Pegar no preço de fecho do S&P 500
- Calcular a média dos últimos 250 dias de trading do S&P 500
- Se o close está **abaixo** da média → CASH. Não comprar nada. Vender tudo. Esperar até dia 18 do mês seguinte.
- Se o close está **acima** → continuar para o passo seguinte

**b) Calcular o momentum composto para cada stock:**
- Retorno 6 meses = preço hoje / preço de há 126 dias de trading - 1
- Retorno 12 meses = preço hoje / preço de há 252 dias de trading - 1
- Momentum composto = 50% × retorno 6 meses + 50% × retorno 12 meses

**c) Filtrar o universo:**
- Market cap > $10 biliões (dólares)
- EBIT > 0 (lucro operacional positivo, usar o último valor reportado)
- Apenas US domestic common stock

**d) Rankear e selecionar:**
- Ordenar por momentum composto, do maior para o menor
- Selecionar as top 7 (sem limite de sector)

### 2. Dia 19 de cada mês — Executar

- Vender as stocks que saíram do portfolio
- Comprar as stocks que entraram
- Equal weight: dividir o capital total por 7 (~14.3% cada)
- Se dia 19 cai num fim de semana, comprar na segunda seguinte

### 3. Repetir todos os meses

---

## Como Funciona (explicação detalhada)

### O que é momentum?
Stocks que subiram nos últimos meses tendem a continuar a subir. Este efeito é documentado em centenas de papers académicos e funciona porque:
- **Fluxos institucionais são lentos** — fundos grandes demoram semanas/meses a construir posições
- **Informação propaga-se lentamente** — nem todos os investidores reagem ao mesmo tempo
- **Behavioural bias** — investidores vendem winners cedo demais e seguram losers

### Porque 50% 6m + 50% 12m?
Combinar dois horizontes captura momentum de curto e médio prazo. O componente de 6 meses reage mais rápido a mudanças; o de 12 meses filtra ruído e captura tendências mais duradouras. Em testes com dados diários, este blend deu melhor Sharpe que qualquer lookback isolado.

### Porque >$10B?
Abaixo de $10B, o momentum captura muito ruído — pump-and-dumps, stocks ilíquidas, micro-caps com dados questionáveis. Acima de $10B estás a comprar empresas como Apple, Nvidia, Meta — stocks reais com liquidez real. O momentum neste universo captura fluxos institucionais genuínos.

### Porque EBIT > 0?
Filtra empresas que perdem dinheiro. Sem este filtro, o momentum apanha stocks hyped sem fundamentais (tipo meme stocks). Com EBIT > 0, garantes que a empresa pelo menos tem lucro operacional. Nos testes, tirar o EBIT reduz o Sharpe em ~0.10-0.15.

### Porque sem sector cap?
Testámos max 2, 3, 4, 5 e sem limite. O sector cap não melhora a performance — na verdade piora o drawdown (de -41.9% sem cap para -53.1% com max 3). Forçar diversificação para fora do sector dominante coloca stocks piores no portfolio que caem mais nos crashes. Além disso, os sectores do Sharadar (backtest) e do TradingView (produção) usam taxonomias diferentes, o que faz o sector cap comportar-se de forma inconsistente entre backtest e live.

### Porque MA250?
A média móvel de 250 dias do S&P 500 é um filtro de regime simples: se o mercado está em tendência de baixa (abaixo da MA), a estratégia vai para cash. Isto evita os piores drawdowns:
- **2008**: ficou em cash de Nov 2007 a Jul 2009 (~20 meses). Evitou -55% do S&P.
- **2020**: ficou em cash Fev-Abr. Evitou -34% do crash COVID.
- **2022**: ficou em cash Abr-Dez. Evitou bear market prolongado.
- **2025 Abril**: cash durante a correção recente.

Sem o filtro MA, o MaxDD vai a -60%+. Com ele, fica em -26%.

### Porque dia 18?
Testámos todos os dias do mês (1, 5, 10, 15, 17, 18, 19, 20, último) com sinal no dia N e compra no dia N+1 (sem look-ahead bias). O dia 18 deu consistentemente o melhor Sharpe. Provavelmente porque:
- É antes do rebalance de fim de mês dos fundos institucionais
- Captura o momentum antes do "rush" dos últimos dias do mês
- Tem tempo suficiente para evitar o noise dos primeiros dias do mês

### Porque 7 stocks?
Mais concentração = mais retorno E melhor Sharpe, até certo ponto:
- Top 5: CAGR +27%, Sharpe 0.98, MaxDD -26% — mais retorno mas 20% por posição
- Top 7: CAGR +24.5%, Sharpe 0.93, MaxDD -26% — bom equilíbrio
- Top 10: CAGR +20%, Sharpe 0.87, MaxDD -23% — mais defensivo
- Top 20: CAGR +15%, Sharpe 0.80, MaxDD -17% — conservador

Top 7 é o sweet spot entre concentração e diversificação.

---

## O que pode correr mal

1. **Custos de transação.** ~84 trades/ano. Estimar -0.5% a -1% CAGR.
2. **Out-of-sample degradation.** Testámos muitas variações e escolhemos a melhor. Esperar 20-30% degradação no Sharpe em dados futuros.
3. **2024 infla os números.** A estratégia fez +189% em 2024 (SMCI, APP, COIN, VRT). Sem esse ano, o CAGR seria ~20%.
4. **21 anos, 2 bear markets.** Ambos V-shaped (2008, 2020). Num bear lento tipo 2000-2003, a MA250 pode não proteger tão bem.
5. **Concentração.** 7 stocks = 14% por posição. Um blowup numa stock custa ~14%.
6. **Expectativa realista pós-custos:** +18-22% CAGR, Sharpe ~0.70-0.80.

---

## Live Portfolio

**Desde 17 Abril 2026, $100,000.**

Portfolio actual (sinal 15 Abril, compra 17 Abril):

| # | Ticker | Empresa | Sector | Peso |
|---|--------|---------|--------|------|
| 1 | SNDK | Sandisk | Technology | 14.3% |
| 2 | LITE | Lumentum | Technology | 14.3% |
| 3 | CIEN | Ciena | Technology | 14.3% |
| 4 | BE | Bloom Energy | Industrials | 14.3% |
| 5 | HL | Hecla Mining | Basic Materials | 14.3% |
| 6 | AA | Alcoa | Basic Materials | 14.3% |
| 7 | FIX | Comfort Systems | Industrials | 14.3% |

**Nota:** Portfolio calculado com dados de 15 Abril (últimos disponíveis). Com sinal de dia 16 (o correcto para compra dia 17), o portfolio seria ligeiramente diferente: CIEN e HL saem, entram WDC e FTI. Corrigir no próximo rebalance dia 19 Maio.

**Próximo rebalance: 19 Maio 2026** (sinal dia 18 Maio).

**Potencial aumento para $200k em Maio.**

---

## Retornos Anuais

| Ano | Estratégia | S&P 500 | Alpha |
|---|---|---|---|
| 2005 | +60.7% | +9.7% | +51.0% |
| 2006 | -18.6% | +11.2% | -29.8% |
| 2007 | +56.8% | -4.7% | +61.5% |
| 2008 | 0.0% | -38.0% | +38.0% |
| 2009 | +1.4% | +27.1% | -25.6% |
| 2010 | +9.5% | +18.9% | -9.3% |
| 2011 | -11.0% | +2.9% | -13.8% |
| 2012 | +37.4% | +14.8% | +22.5% |
| 2013 | +31.5% | +17.7% | +13.9% |
| 2014 | +39.2% | +13.9% | +25.2% |
| 2015 | +9.5% | -4.0% | +13.5% |
| 2016 | +21.7% | +17.6% | +4.1% |
| 2017 | +49.6% | +25.1% | +24.5% |
| 2018 | -7.2% | -7.5% | +0.3% |
| 2019 | +17.1% | +24.0% | -6.9% |
| 2020 | +58.1% | +13.5% | +44.6% |
| 2021 | -13.6% | +19.3% | -32.9% |
| 2022 | +16.1% | -9.3% | +25.5% |
| 2023 | +44.5% | +22.7% | +21.8% |
| 2024 | +188.9% | +23.2% | +165.7% |
| 2025 | +42.2% | +14.8% | +27.5% |
| 2026 | -0.5% | -7.1% | +6.5% |

**Anos negativos:** 2006 (-18.6%), 2011 (-11.0%), 2018 (-7.2%), 2021 (-13.6%). Em 3 desses 4, o S&P também foi negativo ou flat.

---

## Ficheiros

| Ficheiro | Descrição |
|---|---|
| `generate_report.py` | Gera o relatório completo com gráficos e position history |
| `test_realistic.py` | Testes com sinal dia N, compra dia N+1 (sem look-ahead) |
| `current_picks.py` | Gera portfolio do mês actual (usa dados EOM, actualizar para D18) |
| `mom_engine.py` | Engine de backtest mensal (versão antiga com EOM) |
| `momentum_full_report.png` | Gráfico: S&P vs MA250, equity curve, drawdown, monthly returns |

---

## Prompt para continuar em nova sessão

```
Estou no directório ~/sharadar. Tenho dados Sharadar em parquet (sep_daily.parquet, sf1_quarterly_ttm.parquet, tickers.parquet, sp500_daily.parquet).

## Estratégia FINAL (live com $100k desde 17 Abril 2026)
6+12eq Composite Momentum | >$10B | Top 7 | MA250 | EBIT>0 | Signal D18 → Buy D19

Regras:
- Momentum: 50% × retorno 6 meses (126 trading days) + 50% × retorno 12 meses (252 trading days)
- Universo: Market cap > $10B, EBIT > 0, US domestic common stock
- Selecção: Top 7 por momentum composto (sem sector cap)
- Regime: Se S&P 500 close < MA250 dias → 100% cash
- Signal: Dia 18 do mês (usar preços de fecho)
- Execução: Dia 19 do mês (comprar na abertura)
- Rebalance: Mensal
- Pesos: Equal weight (~14.3% cada)
- Forward fill dos fundamentais SEM limite

Backtest (dados diários, sem look-ahead): CAGR +24.5%, Sharpe 0.93, MaxDD -26.2%

## Portfolio actual (Abril 2026)
SNDK, LITE, CIEN, BE, HL, AA, FIX

## Scripts
- generate_report.py: relatório completo
- test_realistic.py: testes signal N buy N+1
- current_picks.py: picks do mês (PRECISA SER ACTUALIZADO para D18 em vez de EOM)

## O que preciso
Gera o portfolio do próximo mês com sinal dia 18. Diz-me o que vender e o que comprar vs o portfolio actual.
```

---

*Bivar Capital — Abril 2026*
*CONFIDENCIAL — Não distribuir*
