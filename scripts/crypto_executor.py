#!/usr/bin/env python3
"""
Executor cripto Kraken — corre diariamente ~00:05 UTC via GitHub Actions.

Sleeve (validado 2026-09-07, ver memória do projecto mechanical-trading-system):
  BTC: regra do site — LONG se RSI14>54 e preço>MA155 e vol20(anualizada)<100%
       (edge vive nas primeiras 24h → execução imediata obrigatória)
  ETH: LONG se preço>MA200; sai só após 3 fechos consecutivos abaixo (exit delay 3)
Alvo: 50% do valor do sleeve em cada moeda quando ON; senão fica em quote (USD).

Segurança:
  - DRY_RUN=1 (default): só imprime o que faria. Pôr DRY_RUN=0 para ordens reais.
  - Chave API Kraken SEM permissão de levantamento.
  - Banda de rebalanço: só negoceia se o desvio ao alvo exceder REBALANCE_BAND (5%).
Env: KRAKEN_API_KEY, KRAKEN_API_SECRET, DRY_RUN, QUOTE (default USD)
"""
import os, math, sys
import ccxt

DRY_RUN = os.environ.get('DRY_RUN', '1') != '0'
QUOTE = os.environ.get('QUOTE', 'USD')
BAND = 0.05
PAIRS = {'BTC': f'BTC/{QUOTE}', 'ETH': f'ETH/{QUOTE}'}

ex = ccxt.kraken({
    'apiKey': os.environ.get('KRAKEN_API_KEY', ''),
    'secret': os.environ.get('KRAKEN_API_SECRET', ''),
})

def daily_closes(pair, n=420):
    ohlcv = ex.fetch_ohlcv(pair, timeframe='1d', limit=n)
    closes = [c[4] for c in ohlcv]
    # a última vela é o dia em curso (incompleta) → usar só velas fechadas
    return closes[:-1]

def btc_signal(closes):
    n = len(closes)
    ma155 = sum(closes[n-155:]) / 155
    gains = sum(max(closes[i]-closes[i-1], 0) for i in range(n-14, n))
    losses = sum(max(closes[i-1]-closes[i], 0) for i in range(n-14, n))
    rsi = 100.0 if losses == 0 else 100 - 100/(1 + gains/losses)
    rets = [closes[i]/closes[i-1]-1 for i in range(n-20, n)]
    mu = sum(rets)/len(rets)
    vol = math.sqrt(sum((r-mu)**2 for r in rets)/(len(rets)-1)) * math.sqrt(365)
    on = rsi > 54 and closes[-1] > ma155 and vol < 1.0
    print(f"BTC: close={closes[-1]:.0f} RSI={rsi:.1f} MA155={ma155:.0f} vol={vol*100:.0f}% -> {'LONG' if on else 'CASH'}")
    return on

def eth_signal(closes, delay=3):
    n = len(closes)
    on, off = 0, 0
    for i in range(200, n):
        ma = sum(closes[i-199:i+1]) / 200    # MA200 incluindo o fecho i
        if closes[i] > ma:
            on, off = 1, 0
        elif on == 1:
            off += 1
            if off > delay:
                on, off = 0, 0
    print(f"ETH: close={closes[-1]:.0f} MA200={sum(closes[-200:])/200:.0f} off_count={off} -> {'LONG' if on else 'CASH'}")
    return bool(on)

def main():
    sig = {}
    for coin, pair in PAIRS.items():
        closes = daily_closes(pair)
        if len(closes) < 220:
            print(f"{coin}: histórico insuficiente ({len(closes)}) — abortar"); sys.exit(1)
        sig[coin] = btc_signal(closes) if coin == 'BTC' else eth_signal(closes)

    bal = ex.fetch_balance() if not DRY_RUN or os.environ.get('KRAKEN_API_KEY') else {}
    tickers = {c: ex.fetch_ticker(p)['last'] for c, p in PAIRS.items()}
    if bal:
        free = lambda a: float(bal.get('total', {}).get(a, 0) or 0)
        hold = {c: free('XBT' if c == 'BTC' and 'XBT' in bal.get('total', {}) else c) for c in PAIRS}
        cash = free(QUOTE) + free(f'Z{QUOTE}')
        total = cash + sum(hold[c]*tickers[c] for c in PAIRS)
        print(f"\nconta: {QUOTE} {cash:.2f} + BTC {hold['BTC']:.6f} + ETH {hold['ETH']:.4f}  (total ~{total:.2f} {QUOTE})")
    else:
        hold = {c: 0.0 for c in PAIRS}; total = float(os.environ.get('SIM_TOTAL', '1000')); cash = total
        print(f"\n(sem chave API — a simular conta de {total} {QUOTE})")

    for coin, pair in PAIRS.items():
        target_val = 0.5*total if sig[coin] else 0.0
        cur_val = hold[coin]*tickers[coin]
        drift = abs(cur_val - target_val)/total
        print(f"{coin}: alvo {target_val:.2f}, actual {cur_val:.2f}, desvio {drift*100:.1f}%")
        if drift < BAND:
            print(f"  dentro da banda ({BAND*100:.0f}%) — sem ordem"); continue
        amount = abs(target_val - cur_val)/tickers[coin]
        side = 'buy' if target_val > cur_val else 'sell'
        print(f"  ORDEM: {side} {amount:.6f} {coin} @ ~{tickers[coin]:.0f} {QUOTE}")
        if DRY_RUN:
            print("  [DRY_RUN] não enviada")
        else:
            o = ex.create_order(pair, 'market', side, round(amount, 6))
            print(f"  enviada: {o.get('id')}")

if __name__ == '__main__':
    main()
