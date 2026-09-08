# Auditoria — sinais US / UK / Canada (bivarcapital.com)

**Data:** 2026-08-20 · **Âmbito:** consistência entre backtest, strategy report, código do sinal live e o que a página mostra.
**Critério usado:** isto está pronto para correr com dinheiro real?

Ficheiros auditados: `scripts/{momentum,uk_momentum,canada_momentum}_signal.py`, `scripts/*_ytd.py`, `scripts/daily-update.py`, `.github/workflows/update-data.yml`, `research/{momentum_strategy,uk_momentum,canada_momentum}_report.html`, `~/sharadar/{generate_mom_gld_report,generate_uk_report}.py` (os geradores reais), `momentum_research/{backtest,config,canada_from_scratch}.py`, `confidential/momentum_strategy/*.py`, os 6 JSON de sinal/portfolio, `strategies.html` e as 3 páginas de estratégia, mais o histórico git e os preços EODHD TO.

---

## 1. Bloqueadores

### B1 — UK e Canada não modelam o atraso de execução de 1 dia. Os EUA modelam.

**Correcção (verificada 2026-08-20):** a versão anterior desta secção acusava também os EUA, com base no `confidential/momentum_strategy/mom_engine.py`. Esse ficheiro é de 21 Jul, corta o price matrix em `2004-01` e não tem custos nenhuns — não pode ter produzido um report que começa em 1998 e que ganhou custos hoje. Não é o motor de produção. **Os EUA estão correctos.**

**Teste usado.** Um backtest que executa no primeiro dia de trading do mês seguinte tem de resolver o calendário de bolsa. Contagem das signal dates no histórico de posições de cada report publicado:

| | linhas | signal date ao fim-de-semana | último dia **civil** do mês |
|---|---|---|---|
| USA | 339 | **0** (0.0%) | 237 (69.9%) |
| UK | 302 | **87** (28.8%) | 302 (100%) |
| Canada | 319 | **91** (28.5%) | 319 (100%) |

Isto sai do HTML publicado, não do código — portanto vale para o Canada apesar de o `generate_canada_report_v2.py` não existir em disco em nenhuma pasta acessível (procurado por nome e por conteúdo).

**USA — correcto.** `~/sharadar/generate_mom_gld_report.py` (20 Ago 09:57):

```python
sig  = get_day(year, month, signal_day)   # signal_day=-1 -> última barra diária do mês
buy  = next_td(sig)                       # dia de trading SEGUINTE
sell = next_td(get_day(sy, sm, signal_day))
mom  = w_short*(p_sig/daily.iloc[idx-126]-1) + w_long*(p_sig/daily.iloc[idx-252]-1)
bp   = daily.loc[buy, selected];  sp_p = daily.loc[sell, selected]
gross_ret = (sp_p/bp - 1).mean()
```

Barras diárias, lookbacks de 126/252 dias de trading (o que o report diz), custos sobre turnover real e cobrados também na saída para cash. Zero signal dates em dias de mercado fechado, e 30% delas não são o último dia civil — assinatura de calendário real. A afirmação do report é verdadeira.

**UK — bug confirmado.** `~/sharadar/generate_uk_report.py` (20 Ago 09:32, o que produziu os 79/29bps publicados):

```python
sig_date = pd.Period(ym, 'M').to_timestamp('M')       # fim do mês do sinal
buy_date = pd.Period(ret_ym, 'M').to_timestamp('M')   # fim do mês SEGUINTE
r1_next  = pm_ret1m.loc[ret_ym]                       # retorno month-end -> month-end
gross_ret = np.mean([r1_next[t] for t in selected])
```

`buy_date` não é a data de compra, é o fim do período de detenção — o nome esconde o problema. O report afirma o contrário em dois sítios (linhas 793 e 981). 87 signal dates em sábados e domingos.

**Canada — bug confirmado pelo report.** 91 signal dates em sábados e domingos, 100% último dia civil. O `canada_from_scratch.py` (`next_ret = eom_monthly_ret.shift(-1)`) tem a mesma convenção, mas é a reimplementação de verificação, não o gerador — a prova que conta é a do calendário.

**Nota de método.** O teste numérico alternativo (recalcular cada mês do Canada nas duas convenções com preços EODHD) não discrimina: só 10-13 dos 15 nomes por mês têm preço nas duas pontas, e esse ruído de 2-3pp tapa a diferença entre convenções, que é tipicamente <1pp. Confirmou a direcção — os retornos calculados batem com a linha anterior, ou seja cada linha mostra o retorno futuro — mas não serve como prova.

### B2 — Canada: o filtro de regime é diário no live e mensal no backtest.

```python
# canada_from_scratch.py:147  — backtest
regime_eom = above_ma.resample('ME').last().reindex(port_ret.index).ffill().fillna(0.0)
port_ret   = port_ret * regime_eom
```

Estado no fim do mês `T` governa o mês inteiro `T+1`. Uma decisão por mês.

```python
# canada_momentum_signal.py — live, corre todos os dias
elif not regime_ok:
    print(f"  Portfolio: DEFENSIVE — cash")
    holdings = []
    last_rebalance = existing.get('last_rebalance', TODAY)
```

Sai para cash no dia em que o TSX fecha abaixo da MA75. E a reentrada é pior: em defensive o `last_rebalance` não é atualizado, portanto `is_new_month` fica `True` indefinidamente — assim que o regime volta, o ramo `is_new_month and regime_ok` dispara e rebalanceia **a meio do mês** com os dados desse dia.

Com uma MA de 75 dias num índice, os cruzamentos diários são frequentes. O CAGR 31.9% / Sharpe 1.32 / MaxDD -26.3% descreve a versão mensal. Não descreve o que o código faz.

E o report reforça o erro em vez de o apanhar:

> *"The TSX Composite (^GSPTSE) is compared to its 75-day moving average **daily**. When below MA75, portfolio moves to 100% cash."*

Descreve o live. Os números por baixo vêm do mensal.

---

### B3 — USA: o tracker live ignora o filtro de regime por completo.

`momentum_signal.py` calcula o regime, escreve-o no JSON, mostra-o na página — e depois não o usa:

```python
exec_tickers = sel7                      # sem verificação de regime
...
'picks': [ ... for tk in sel7 ]          # pending_signal, idem
```

Comparação directa:

| | regime aplicado às holdings? |
|---|---|
| UK | `exec_tickers = new_tickers if regime == 'momentum' else []` ✓ |
| Canada | `elif not regime_ok: holdings = []` ✓ (mas diário, ver B2) |
| **USA** | **não existe** |

O regime filter é praticamente todo o valor do backtest US — 83 meses em cash, toda a secção IX (Crisis Analysis), o MaxDD de -33.2% em vez do da estratégia nua. Se o S&P fechar abaixo da MA250, a página do US continua a publicar 7 posições compradas.

---

### B4 — Canada: o MaxDD publicado passou de -39.0% para -26.3% e a diferença nunca foi explicada.

Histórico do headline no git:

| commit | data | CAGR | Sharpe | MaxDD |
|---|---|---|---|---|
| `d42e7a8` | 07 Ago | +29.9% | 1.18 | **-33.1%** |
| `a8c272e` | 11 Ago | +31.4% | 1.38 | **-39.0%** |
| `8f22e10` | 12 Ago | +32.9% | 1.37 | **-36.4%** |
| `2885a6b` | 13 Ago | +33.0% | 1.36 | **-26.1%** |
| `25492c3` | 13 Ago | — | — | **revert → -36.4%** |
| `85ea04e` | 13 Ago | +33.0% | 1.36 | **-26.1%** |
| `09c08cf` | 20 Ago | +31.9% | 1.32 | **-26.3%** ← no ar |

A mensagem do `2885a6b`, palavras dele próprio:

> *"only MaxDD was wrong, isolated to a narrow discrepancy in the earliest months of the backtest window (Jan-May 2000) **that hasn't been root-caused yet**"*

E no dia anterior, `8f22e10` tinha encontrado isto:

> *"a 'trim to first nonzero return' bug in the report generator ... the trim silently extended the backtest back to 1981 instead of 2000"*

Ou seja: há um problema conhecido e não resolvido exactamente na fronteira inicial da janela, e é aí que os dois MaxDD divergem. A correcção foi aplicada, revertida por suspeita de erro, e reinstaurada — sem que a causa tenha sido encontrada em nenhum dos passos.

Tu vais dimensionar com 25–30% de MaxDD. Se o número certo for -36/-39%, o sizing está errado em ~40%. `canada_from_scratch.py` — a reimplementação independente escrita para validar isto — ainda tem `-39.0%` no docstring como o número que estava a verificar.

---

### B5 — UK: cinco tickers foram excluídos à mão por contaminação de dados. Não há detector.

commit `9900940`, hoje:

> *"Excluded MFAI, BIOM, NBB, IGAS, VELA at the data-loading level: confirmed EODHD sentinel-value/bad-tick contamination faking ~97% monthly crashes, which had inflated the 'Remove EBIT' ablation's apparent drawdown."*

Foram encontrados porque **pioravam** um resultado. Um bad tick que fabrica um crash de -97% aparece como um drawdown estranho e chama a atenção.

Um bad tick que fabrica +900% num microcap não piora nada. É *selecionado* — o ranking de momentum vai buscá-lo de propósito. Por construção, os erros que ajudam são invisíveis a menos que sejam procurados directamente. Nunca foram.

O universo é LSE com floor de £100M, ou seja microcaps. O pick #1 de hoje, `SML`, tem mcap £0.13B, `ret_6m` +38.8% e um `ret_12m` implícito de ~+1460%. Não estou a dizer que é um bad tick — estou a dizer que não há nada no pipeline que consiga distinguir.

---

## 2. Live ≠ backtest (estrutural)

**C1 — UK: o "Ret 9M" da página não é um retorno de 9 meses.**

```python
p_9m_ago = np.sqrt(p_6m_ago * p_12m_ago)
```

Isto dá `1+r9 = sqrt((1+r6)(1+r12))` — uma função determinística de r6 e r12, não um preço observado. O composite resultante é ≈ `0.75×r6 + 0.25×r12`, não 50/50 6M/9M. O erro é máximo quando a trajetória não é log-uniforme, que é precisamente o perfil dos nomes que a estratégia escolhe (SML: r6 +38.8%, "r9" +365.8%).

A aproximação está documentada no docstring do script. Não está na página (coluna intitulada "Ret 9M", rodapé "50% × 6-month return + 50% × 9-month return") nem no report.

**C2 — Momentum live é price return; backtest é total return.**
TradingView `Perf.6M`/`Perf.Y` excluem dividendos. Backtest usa `closeadj` (Sharadar) e EODHD adjusted. Nos EUA é ruído. No UK, com yields de 4-5%, penaliza sistematicamente os nomes de yield alto e muda o ranking.

**C3 — Universo US: mcap stale no backtest, corrente no live.**
`mom_engine.py` filtra com `mc.loc[m]`, construído do `marketcap` do SF1 indexado por `avail_ym` com `ffill(limit=4)` — o mcap à data do report. Uma ação que triplicou desde o último report tem mcap baixo e falha o floor de $10B no backtest; live passa. O universo live é maior e mais quente do que o testado, e o viés é direcional porque a estratégia compra exactamente o que acabou de triplicar.
(À parte: usar `avail_ym` é a escolha certa e evita look-ahead nos fundamentais. O problema aqui é a comparação live-vs-backtest, não look-ahead.)

**C4 — Canada: duas convenções de ajuste a alimentar o mesmo percentil de vol.**
Live: `tvDatafeed` closes **não ajustados**, com fallback `yfinance(auto_adjust=True)` **ajustado**, misturados no mesmo `vols{}` que depois vai a `quantile(1 - 0.25)`. Backtest: EODHD adjusted. Um split fabrica vol enorme na série não ajustada e atira o nome para o top-25% excluído.

**C5 — Canada: há um closed-end fund no book.**
`BK — Canadian Banc Corp` é um split-share corp alavancado. O filtro exclui `type in ['dr','fund']` do TradingView, que classifica split-shares como `stock`. O backtest EODHD não tem exclusão equivalente. "Momentum 12M" num split-share alavancado não é o mesmo sinal.

**C6 — Nenhum tracker live aplica custos.**
US 14bps RT (só existe no backtest desde hoje — `431bf22`: *"previously had none — 'Transaction costs not included' caveat was literal"*), ~1.5%/ano, irrelevante. UK 108bps RT com turnover mensal quase total → da ordem de 10pp/ano. O -32.75% YTD do UK é bruto.

**C7 — Floor de mcap UK: quatro valores em quatro sítios.**

| sítio | valor |
|---|---|
| `momentum_research/config.py` | `MCAP_MIN['LSE'] = 10e9` pence = £100M |
| report + página | £100M |
| `scripts/uk_momentum_signal.py` | `MIN_MCAP_USD = 125_000_000` com comentário `≈ £100M` |
| `confidential/.../uk_momentum_backtest.py` | `MIN_MCAP_GBP = 250_000_000` |

O comentário do signal script assume que `market_cap_basic` vem em USD. No screener UK vem em GBP — vale a pena confirmar, porque se vier em GBP o floor live é £125M e não £100M.

Nota separada: o book UK de hoje é SML £0.13B, DIA £0.22B, SFOR £0.35B, ACG £0.48B, ENQ £0.47B. Mediana bem abaixo de £500M. Se a tua ideia era um floor de ~£200M com média ~£1B, não é isso que a estratégia está a comprar.

---

## 3. Números publicados que não fecham

**N1 — Sortino de 6.51 (US) e 5.11 (UK) são impossíveis.**
Sortino/Sharpe = 7.5× implica downside deviation ≈ 3.6% anualizado contra 26.8% de vol total, numa série com -33.2% de MaxDD e 55% de meses não positivos. Não pode ser.

O motor que está no repo usa, em ambos os sítios:

```python
downside     = rets[rets < rf_monthly] - rf_monthly
downside_vol = np.std(downside, ddof=1) * np.sqrt(12)
```

A definição de Sortino pede a **raiz do valor quadrático médio** dos desvios negativos, `sqrt(mean(downside**2))`. `np.std` subtrai a média dos desvios antes de elevar ao quadrado — e a média dos desvios negativos *é* a maior parte do risco de queda. O efeito é agravado pelos 83 meses de cash, que entram no conjunto `downside` com desvio exactamente `-rf`.

O Canada dá 2.72 contra Sharpe 1.32 (2.06×), que é plausível — gerador diferente. Não consegui reproduzir o 6.51 exacto porque `generate_mom_gld_report.py` não está em nenhuma das pastas a que tenho acesso.

**N2 — US: os meses não somam.** 247 em momentum + 83 em cash = 330, mas o cabeçalho diz 339 meses; 73% + 24% = 97%. Faltam 9. UK (200+102=302) e Canada (213+106=319) fecham.

**N3 — US: "+18.3% Alpha vs S&P" não é alpha.** É diferença de CAGR sem ajuste de beta, e compara a estratégia em total return (`closeadj`) contra o S&P em price return (`sp500['close']`) — ~2pp/ano só de dividendos do benchmark. O report do Canada foi explicitamente corrigido nisto (`9ad145a`, *"Neutralize remaining 'alpha' wording"*; a tabela passou a dizer "Relative Perf. vs TSX Price Return" e há um caveat sobre a base não ser like-for-like). O report US não recebeu a mesma correcção.

**N4 — "out-of-sample" nos reports US e UK.** 339 e 302 meses descritos como out-of-sample, quando top_n, janela de MA, blend de lookbacks e floor de mcap foram escolhidos na mesma série. O report do Canada é honesto sobre isto (*"informed by in-sample sensitivity analysis on the same dataset"*). Os outros dois não.

**N5 — Mesmo ano civil, dois números no mesmo site.**

| | report 2026 | tracker live 2026 |
|---|---|---|
| US | +86.5% | **+194.26%** |
| UK | -8.0% | **-32.75%** |
| Canada | -8.0% | **+15.81%** |

Nenhuma destas diferenças se explica por custos. O UK é o alarme mais alto: 25pp de diferença no mesmo período.

**N6 — O YTD live do US inclui retorno que nunca capturaste.**
`momentum_ytd.py` reconstrói os meses a partir de `ytd-picks-history.json` e preça cada período de fecho de fim-de-mês a fecho de fim-de-mês, com os picks *novos*. Ou seja, cada mês inclui o salto month-end → primeiro dia de trading, que tu não apanhas porque só compras no dia seguinte. É o mesmo gap do B1, mas a inflar o track record publicado em vez do backtest.

**N7 — Backfill misturado com live sem distinção.**
Canada: `monthly_breakdown` tem 37 meses e `ytd_2026 = +15.81%`, mas o book existe desde `2026-08-04`. US: holdings desde `2026-01-02`. UK: breakdown desde Dez 2025. As páginas não separam o que foi simulado do que foi executado.

---

## 4. Operacional

**O1 — Um hiccup do yfinance nos EUA mata a UK e o Canada, em silêncio.**

```python
# momentum_signal.py
except Exception:
    return None, None, True
...
print(f"  S&P 500: {sp_last:,.2f}  MA250: {sp_ma250:,.2f} ...")   # TypeError com None
```

O passo rebenta. `update-data.yml` não tem `continue-on-error` em passo nenhum, portanto o job aborta e os passos seguintes — UK, Canada, `daily-update.py` — não chegam a correr. O kill switch do Canada nem dispara, porque o script do Canada nunca arranca. O site serve os dados de ontem sem qualquer aviso.

**O2 — Só o Canada tem kill switch.** `is_live` / `not_live_reason` / banner "Do not rebalance based on this page until this clears" existem só lá. US e UK não têm flag, nem verificação de frescura, nem aviso. Se o cron falhar três dias, a página do US mostra o sinal de há três dias com ar de actual.

**O3 — O default em caso de falha é "fica comprado".** `check_regime()` no US e no UK devolve `True` (investido) em qualquer excepção e em qualquer NaN. O modo seguro é cash ou "não sei". No US o `TypeError` da linha seguinte acaba por salvar o dia por acidente, mas a intenção codificada está ao contrário.

**O4 — MA sem verificação de comprimento.** `close.tail(250).mean()` (US) e `.tail(200).mean()` (UK) não verificam que existem 250/200 barras. Histórico parcial do yfinance → MA mais curta, calculada em silêncio. O Canada usa `rolling(MA_W, min_periods=int(MA_W*0.8))`.

**O5 — Meses que acabam ao domingo saltam o lock-in, no US e no UK.**
Cron é `0 23 * * 1-6` (Seg–Sáb). O teste de fim de mês é `tomorrow.month != today.month` sobre `datetime.now()`, sem noção de dias úteis. Se o último dia civil é domingo (ex.: 31 Mai 2026): sábado dá "mesmo mês", domingo não corre, segunda cai no ramo *"no pending end-of-month signal found — falling back to today's data"*. O sinal desses meses é calculado no dia 1, não no fim do mês, e o único registo é um `print` no log.

O Canada resolve isto correctamente — `next_weekday()` mais `market_date` tirado da última barra do índice em vez do relógio. US e UK não foram actualizados com a mesma correcção.

**O6 — UK: posições sem preço contam como 0% e desaparecem da média.**
`FERG` está no book desde Dez 2025 com `current_price: null` e `return_pct: 0.0` — Ferguson saiu da LSE para a NYSE, `FERG.L` não resolve. No `holdings` aparece como 0.00%. No cálculo do retorno mensal, `rets` só recebe nomes com p0 e p1 válidos, portanto o mês é a média de 6 nomes num book de 7 a 1/7 cada: a posição impreciável fica implicitamente com o retorno médio das outras.
À parte: `entry_price: 234.33` para o FERG são dólares da NYSE, não pence. Há duas moedas dentro do mesmo book, e o resto do ficheiro está marcado `"currency": "GBX"`.

**O7 — `NameError` latente em `momentum_signal.py`.** Se o `try` de carregamento do portfolio falhar (ficheiro em falta ou corrompido) e não for mês novo, o ramo `else` faz `existing_portfolio.get('holdings', [])` com a variável nunca atribuída.

**O8 — `confidential/` está commitado e é servido publicamente.**

`git ls-files confidential/` devolve 15 ficheiros, entre eles `FINAL_STRATEGY.md`, `mom_engine.py`, `generate_report.py`, `current_picks.py`, `tv_momentum.py`.

Verifiquei: `https://bivarcapital.com/confidential/momentum_strategy/FINAL_STRATEGY.md` serve o documento. Abre com `## CONFIDENCIAL`. `robots.txt` tem `Allow: /`.

E revela outra inconsistência pelo caminho: o `FINAL_STRATEGY.md` diz que em downtrend o US *"vende tudo e compra ouro (GLD)"*. O report publicado diz cash. O gerador do report chama-se `generate_mom_gld_report.py`.

**O9 — `strategies.html` marca o UK como "Live".** Pelo que disseste, o UK está em espera por causa do stamp duty. A página diz Live, com Sharpe 0.99 / CAGR +21.1% ao lado.

---

## 5. O que está bem

Vale a pena separar, porque não é tudo mau e há coisas aqui que só o Canada faz e deviam ser copiadas para os outros dois.

- Fundamentais no US via `avail_ym` com `ffill(limit=4)` — sem look-ahead, é a forma certa.
- Custos aplicados como `turnover_one_way × round_trip_bps` — correcto, não é o erro habitual de dividir por dois.
- Regime sempre aplicado T→T+1 nos backtests — sem look-ahead.
- Canada, o conjunto todo: kill switch com `MIN_UNIVERSE_ROWS` e `MAX_VOL_FAIL_PCT`, data operacional tirada da última barra de mercado e não do relógio, `next_weekday()` para o fim do mês, fallback yfinance por ticker para não deixar cair nomes do universo em silêncio.
- O report do Canada é o único honesto sobre in-sample, sobre o benchmark ser price-return, e sobre a convenção de Sharpe (geométrica vs aritmética).
- `canada_from_scratch.py` como reimplementação independente, sem importar nada do motor original, é exactamente a prática certa — e foi ela que apanhou a discrepância do MaxDD.

---

## 6. Ordem sugerida

1. **B3** — regime no US. É uma linha (`exec_tickers = sel7 if regime == 'momentum' else []`) e é a diferença entre ter e não ter o filtro que produz metade dos números publicados.
2. **B1** — medir o custo do lag de 1 dia nas três configs publicadas (não na config antiga do `uk_exec_day_sensitivity.py`). Até isto estar medido, os três CAGR são optimistas por um valor desconhecido.
3. **B2** — decidir se o Canada é regime diário ou mensal, e alinhar backtest, código e report na mesma escolha.
4. **B4** — root-cause do MaxDD Jan–Mai 2000 antes de dimensionar seja o que for em Canada.
5. **B5** — detector de bad ticks no UK, a procurar saltos para cima e não só para baixo.
6. **O1/O2/O5** — portar do Canada para US e UK: `continue-on-error` por passo no workflow, flag `is_live`, e `next_weekday` + market date.
7. **O8** — `git rm -r --cached confidential/` e meter no `.gitignore`. Reescrever o histórico se importar, porque continua acessível pelos commits antigos.
