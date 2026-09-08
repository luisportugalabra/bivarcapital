# Auditoria — BivarOptimalMomentum (USA)

**Data:** 2026-08-20 · **Âmbito:** só EUA. UK e Canada saem, vais reescrever.
**Critério:** isto está pronto para correr com dinheiro real?

Verificado contra os ficheiros de produção: `~/sharadar/generate_mom_gld_report.py` (o gerador real do report), `~/sharadar_data/{SEP,SF1,tickers}.parquet`, `bivarcapital/scripts/{momentum_signal,momentum_ytd,daily-update}.py`, `.github/workflows/update-data.yml`, `research/momentum_strategy_report.html`, `momentum-data.json`, `momentum-portfolio.json`, `ytd-picks-history.json`, `momentum.html`, `strategies.html`.

Nota: o `confidential/momentum_strategy/mom_engine.py` é um artefacto morto de 21 Jul e foi ignorado. Nada aqui assenta nele.

---

## O que está certo

Vale começar por aqui porque é substancial e é o que separa os EUA dos outros dois.

- **O lag de execução está modelado.** `sig = get_day(y, m, -1)` devolve a última barra diária real do mês, `buy = next_td(sig)`, e o retorno é preçado de `buy` a `sell = next_td(sig_seguinte)`. Zero das 339 signal dates cai em dia de mercado fechado, e 30% delas não são o último dia civil (é o dia 29 ou 30 quando o 31 calha a sábado). O motor conhece o calendário. A afirmação do report é verdadeira.
- **Fundamentais sem look-ahead.** SF1 dimensão `ART` com `avail_date = datekey + 2 meses`. É conservador e está certo.
- **Dois bugs reais encontrados e corrigidos**, ambos documentados no próprio ficheiro: o `reindex().ffill()` que descartava updates trimestrais cujo `avail_date` calhava em fim-de-semana, e a expiry de staleness a 365 dias que impedia ENRNQ/WAMUQ de continuarem a passar o filtro `>$10B / EBIT>0` anos depois de irem à falência. São os dois o tipo de coisa que ninguém encontra por acaso.
- **Custos sobre turnover real**, 14bps RT, e cobrados também na transição para cash.
- **Preços em `closeadj`** — total return, correcto.

Isto é um motor sério. Os problemas abaixo não estão quase nenhum no motor — estão nos dados que ele come, no que a página diz, e no código live que corre ao lado dele.

---

## 1. O backtest publicado acaba em Abril de 2026

`tickers.parquet` dá `lastpricedate = 2026-05-13` para todos os tickers. `SEP.parquet` e `SF1.parquet` são de **14 de Maio**.

O report foi regerado **hoje**, 20 de Agosto (commit `431bf22`, o do modelo de custos), sobre dados que param há três meses.

Confirmação independente pelo próprio report: o histórico de posições tem 339 linhas, a primeira `1998-01-30`, **a última `2026-03-31`**. Como cada linha carrega o retorno do mês *seguinte* (ver ponto 5), o último mês com retorno é Abril.

Consequências:

- **A coluna "2026 +86.5%" da tabela anual são quatro meses (Jan–Abr)**, numa coluna onde todas as outras entradas são anos completos. Nada na tabela o diz. O card na `strategies.html` diz "1998–2026".
- **O backtest nunca viu Julho de 2026.** O teu tracker live dá **-25.03%** nesse mês — o pior mês que a estratégia teve ao vivo, a cacetada no factor. O CAGR de 25.6%, o Sharpe de 0.87 e o MaxDD de -33.2% que estão publicados foram calculados sem esse mês lá dentro.

Este é o ponto que eu poria primeiro. Todos os números headline do site descrevem uma janela que exclui o pior mês recente da estratégia, e foram republicados hoje como se fossem actuais.

---

## 2. O universo live contém nomes que o backtest não consegue conter

Comparação directa dos picks, mesmo mês, backtest vs live:

| sinal | BACKTEST | LIVE |
|---|---|---|
| 2025-12-31 | BE, WDC, CIEN, MU, FNMA, WBD, CDE | **SNDK**, **LITE**, WDC, MU, CIEN, WBD, STX |
| 2026-01-30/31 | BE, WDC, MU, STX, CIEN, LRCX, CDE | **SNDK**, **LITE**, MU, WDC, STX, CIEN, CDE |
| 2026-02-27/28 | BE, WDC, CIEN, MU, CDE, STX, COHR | **SNDK**, **LITE**, BE, WDC, CIEN, MU, HL |
| 2026-03-31 | WDC, CIEN, BE, STX, FIX, MU, COHR | **SNDK**, **LITE**, CIEN, WDC, BE, STX, FIX |

Sobreposição de 4 a 6 em 7. **SNDK e LITE estão no book live todos os meses e não aparecem no backtest uma única vez.**

Para o SNDK a causa está identificada: `firstpricedate = 2025-02-24` (spinoff da WDC). O motor precisa de 252 dias de trading para a perna de 12 meses — `daily.iloc[idx-252]` é NaN antes disso, `mom.notna()` exclui, e o SNDK só se torna elegível por volta de Fev 2026. Como os dados acabam em Maio, o SNDK é estruturalmente inelegível em praticamente toda a janela de sobreposição.

O script live não tem nenhuma destas guardas. Pede `Perf.Y` ao TradingView e recebe um número. No sinal de Janeiro o SNDK entra com **composite 1724.2** — quatro vezes o segundo classificado (MU, 394.0) — para uma empresa que existia há dez meses. Seja o que for que o TradingView está a devolver como "performance a 1 ano" para um título com menos de um ano de história, não é a mesma quantidade que o backtest mede.

E o SNDK é a maior posição do book live, com **+470%**. É o principal motor do +194% de YTD publicado.

O LITE tem `firstpricedate = 2015-07-23`, portanto história não é o problema — a exclusão dele vem do mcap ou do EBIT (SF1 com lag de 2 meses). Não consegui isolar qual sem carregar o SF1, que tem 1GB.

Isto não é uma discrepância de timing nem de custos. **A estratégia que estás a correr selecciona de um universo diferente daquele que foi testado**, e a diferença apanhou desta vez o maior vencedor do ano. Pela mesma porta entra, noutro mês, um IPO ou spinoff recente com um `Perf.Y` que não significa nada.

---

## 3. O tracker live ignora o filtro de regime

`momentum_signal.py` calcula o regime, escreve-o no JSON, mostra-o na página — e nunca o usa:

```python
exec_tickers = sel7                      # sem verificação de regime
...
'picks': [ ... for tk in sel7 ]          # pending_signal, idem
```

O filtro de regime é praticamente todo o valor do backtest: 83 dos 339 meses em cash, a secção inteira de Crisis Analysis, e o MaxDD de -33.2% em vez do da estratégia nua. Se o S&P fechar abaixo da MA250, a página continua a publicar sete posições compradas.

É uma linha a corrigir.

---

## 4. O tracker live preça sem o lag que o backtest modela

O `momentum_ytd.py` reconstrói os meses a partir do `ytd-picks-history.json` e preça cada período com `get_price(tk, target)` = último fecho **em ou antes** da data alvo, sobre datas que são fins de mês civis (`start: 2025-12-31`, `end: 2026-01-31`, ...).

Ou seja: **month-end → month-end, lag zero.** Exactamente a convenção que o backtest teve o cuidado de evitar.

Mas a execução real compra no dia seguinte — o `momentum_signal.py` tranca o sinal no fim do mês e executa na corrida seguinte. Portanto cada mês do track record publicado inclui o salto month-end → primeiro dia de trading que a conta real não apanhou. Em nomes de momentum extremo, esse salto é precisamente onde está a reversão de turn-of-month.

O backtest está certo e o track record live está errado, o que é o contrário do que eu tinha escrito ontem.

---

## 5. O +86.5% e o +194% não são o mesmo período

- Report 2026: **+86.5%** — Janeiro a Abril, quatro meses (ponto 1).
- Tracker live 2026: **+194.26%** — Janeiro a Agosto, oito meses, incluindo o Julho de -25.03% que o backtest não tem.

Os dois números estão no mesmo site a descrever "2026". Não são comparáveis, e nada na página o diz. Somando a isto o ponto 2 (universo diferente) e o ponto 4 (convenção de preço diferente), são duas séries que não têm por onde ser reconciliadas.

---

## 6. A tabela de posições alinha a signal date com o retorno do mês seguinte

O motor guarda `dict(date=buy, sig_date=sig, ret=<retorno de buy a sell>)`. A tabela mostra a coluna "Signal" com `sig_date`, e ao lado o `ret`, que é o retorno do mês *a seguir* a essa data.

A última linha lê-se como "2026-03-31 · WDC, CIEN, BE, STX, FIX, MU, COHR · **+53.7%**". Um leitor entende que aquelas posições fizeram +53.7% em Março. Fizeram-no em Abril. Combinado com o ponto 1, a última linha da tabela dá a impressão de que a estratégia está neste momento a subir 53.7%.

Verificação: as linhas 2025-12-31 a 2026-03-31 compõem para +86.6%, que é o que a tabela anual dá para 2026. As linhas datadas de 2026 sozinhas compõem para +55.7%.

---

## 7. O Sortino de 6.51 tem dois erros sobrepostos

```python
ds = rets[rets < rf] - rf
sortino = (np.mean(rets)-rf)/(np.std(ds,ddof=1)/np.sqrt(12))*np.sqrt(12)
```

1. `np.std(ds)` onde a definição pede `sqrt(mean(ds**2))`. O `np.std` subtrai a média dos desvios negativos antes de elevar ao quadrado — e essa média *é* a maior parte do risco de queda. Agrava-se com os 83 meses de cash, que entram no conjunto com desvio exactamente `-rf`.
2. A anualização dá **×12** em vez de ×√12: os dois `sqrt(12)` não se cancelam. Repara que o Sharpe, duas linhas acima, faz `/np.std(r,ddof=1)*np.sqrt(12)` — correcto.

Só o segundo erro é um factor de 3.46. 6.51 / 3.46 = 1.88, e corrigir o primeiro leva o resto do caminho até um número coerente com um Sharpe de 0.87.

Sanidade: Sortino/Sharpe de 7.5× implicaria desvio negativo de ~3.6% anualizado contra 26.8% de volatilidade total, numa série com -33.2% de MaxDD e 55% dos meses não positivos.

---

## 8. "+18.3% Alpha vs S&P" não é alpha

`alpha = cagr - sp_cagr`, sem ajuste de beta. E `sp500_s = sp500['close']` é **price return**, enquanto a estratégia corre sobre `closeadj`, que é **total return** — cerca de 2pp/ano só de dividendos do benchmark.

O report do Canada foi explicitamente corrigido nisto (commit `9ad145a`, "Neutralize remaining 'alpha' wording"; a tabela passou a "Relative Perf. vs TSX Price Return" com um caveat sobre a base não ser like-for-like). O dos EUA não recebeu a mesma correcção.

---

## 9. "339 months of out-of-sample backtesting"

Top 7, MA250, blend 126/252, floor de $10B — escolhidos na mesma série. O report do Canada é honesto sobre isto ("informed by in-sample sensitivity analysis on the same dataset"). O dos EUA não.

---

## 10. Momentum live é price return; o backtest é total return

Live: `Perf.6M` e `Perf.Y` do TradingView, que excluem dividendos. Backtest: `closeadj`. Num universo de $10B+ com yields baixos é ruído, mas é mais uma pequena divergência a somar às dos pontos 2 e 4 na explicação de por que é que as duas séries não reconciliam.

Relacionado: o backtest filtra por `mc_daily`, que vem do SF1 com lag de 2 meses (preço à data do filing, não o de hoje). O live filtra pelo mcap corrente do TradingView. Uma acção que passou de $8B para $14B nos últimos três meses reprova no backtest e passa no live — e é exactamente o perfil do que a estratégia compra. Não quantifiquei porque o SF1 tem 1GB, mas a direcção do enviesamento é conhecida, não é aleatória.

---

## 11. Operacional

**Um erro do yfinance mata o workflow inteiro.** `check_regime()` devolve `(None, None, True)` em qualquer excepção, e a linha seguinte é `print(f"  S&P 500: {sp_last:,.2f} ...")` → `TypeError`. O `update-data.yml` não tem `continue-on-error` em passo nenhum, portanto o job aborta e nada a seguir corre. O site serve os dados de ontem sem aviso.

**Não há kill switch nem verificação de frescura.** O Canada tem `is_live` / `not_live_reason` e um banner. Os EUA não têm nada. Se o cron falhar três dias, a página mostra o sinal de há três dias com ar de actual.

**O default em caso de falha é "fica comprado".** `check_regime()` devolve `True` (investido) em qualquer excepção e em qualquer NaN. O modo seguro é cash, ou recusar-se a publicar. O `TypeError` da linha seguinte acaba por salvar o dia por acidente, mas a intenção codificada está ao contrário.

**`close.tail(250).mean()` não verifica que existem 250 barras.** Histórico parcial do yfinance dá uma MA mais curta, em silêncio.

**Meses que acabam ao domingo saltam o lock-in.** O cron é `0 23 * * 1-6`. O teste é `tomorrow.month != today.month` sobre `datetime.now()`, sem noção de dias úteis. Se o último dia civil é domingo (31 Mai 2026, por exemplo): sábado dá "mesmo mês", domingo não corre, segunda cai no ramo `no pending end-of-month signal found — falling back to today's data`. O sinal desse mês é calculado no dia 1. O único registo é um `print` no log. Ironia: o backtest resolve o calendário de bolsa correctamente e o script live não.

**`NameError` latente.** Se o `try` de carregamento do portfolio falhar e não for mês novo, o ramo `else` faz `existing_portfolio.get('holdings', [])` com a variável nunca atribuída.

**`top20` tem 30 entradas.** `df.head(30)` sob uma chave chamada `top20`. Cosmético.

---

## 12. `confidential/` está commitado e é servido publicamente

`git ls-files confidential/` devolve 15 ficheiros, entre eles `FINAL_STRATEGY.md`, `mom_engine.py`, `generate_report.py`, `current_picks.py`, `tv_momentum.py`.

Verifiquei: `https://bivarcapital.com/confidential/momentum_strategy/FINAL_STRATEGY.md` serve o documento. Abre com `## CONFIDENCIAL`. O `robots.txt` tem `Allow: /`.

`git rm -r --cached confidential/` mais `.gitignore` resolve o presente; o histórico continua acessível pelos commits antigos.

De caminho: o `FINAL_STRATEGY.md` diz que em downtrend se "vende tudo e compra ouro (GLD)". O report publicado diz cash, e o gerador — apesar de se chamar `generate_mom_gld_report.py` — não tem lógica de GLD nenhuma, só uma menção em texto. O documento público descreve uma estratégia diferente da que está no ar.

---

## 13. Detalhe menor, já resolvido

O cabeçalho diz "247 Months in Momentum (73%)" e "83 Months in Cash (24%)" sobre 339 meses. Faltavam 9. São `WAIT` — os meses de 1998 sem lookback suficiente. 247 + 83 + 9 = 339. Não é um erro de cálculo, é uma linha em falta no cabeçalho; as percentagens somam 97% e não há terceira entrada a explicar porquê.

---

## Ordem sugerida

1. **Actualizar a Sharadar e regerar** (ponto 1). Enquanto os dados pararem em Maio, todos os números publicados descrevem uma janela que exclui o pior mês da estratégia. E vais querer ver o Sharpe e o MaxDD *com* o Julho lá dentro antes de decidir sizing.
2. **Regime no tracker live** (ponto 3). Uma linha.
3. **Reconciliar o universo** (ponto 2). Impor no live as mesmas guardas que o backtest impõe: 252 dias de história antes de um nome ser elegível, e decidir se o filtro de mcap é o corrente ou o do último filing. Sem isto, não sabes o que estás a correr.
4. **Alinhar o tracker live com a convenção do backtest** (ponto 4): preçar de `next_td(month-end)` a `next_td(month-end)`, e descontar os 14bps.
5. Sortino, "alpha", "out-of-sample", e a coluna de datas da tabela de posições (pontos 6–9). São de apresentação, mas são os que um subscritor que saiba ler consegue apanhar.
6. `continue-on-error` por passo, flag `is_live`, e `next_weekday` no lock-in (ponto 11).
7. `confidential/` (ponto 12).
