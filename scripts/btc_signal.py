#!/usr/bin/env python3
"""
BTC Signal Checker — runs daily via GitHub Actions
Computes RSI14 + MA155 + Vol20, compares with previous signal,
sends email alert if signal changed (CASH→BUY or BUY→CASH).
"""
import json
import os
import urllib.request
import urllib.parse
import ssl
from datetime import datetime

# Binance API
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

end = int(__import__('time').time() * 1000)
start = end - 220 * 86400 * 1000
url = f'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&startTime={start}&endTime={end}&limit=220'
data = json.loads(urllib.request.urlopen(url, context=ctx).read())
closes = [float(k[4]) for k in data]
n = len(closes)

# MA155
ma155 = sum(closes[n-155:n]) / 155

# RSI14 (SMA)
period = 14
gains = sum(max(closes[i]-closes[i-1], 0) for i in range(n-period, n))
losses = sum(max(closes[i-1]-closes[i], 0) for i in range(n-period, n))
avg_gain = gains / period
avg_loss = losses / period
rs = avg_gain / avg_loss if avg_loss > 0 else 100
rsi = 100 - 100 / (1 + rs)

# Vol20
import math
rets = [(closes[i]/closes[i-1]-1) for i in range(n-20, n)]
mean_ret = sum(rets) / len(rets)
variance = sum((r - mean_ret)**2 for r in rets) / (len(rets)-1)
vol = math.sqrt(variance) * math.sqrt(365)

# Signal
price = closes[-1]
signal = "BUY" if rsi > 54 and price > ma155 and vol < 1.0 else "CASH"
date = datetime.utcfromtimestamp(data[-1][0]/1000).strftime('%Y-%m-%d')

print(f"Date: {date}")
print(f"Price: ${price:,.0f}")
print(f"RSI14: {rsi:.1f} (need >54)")
print(f"MA155: ${ma155:,.0f} (price {'ABOVE' if price > ma155 else 'BELOW'})")
print(f"Vol20: {vol*100:.0f}% (need <100%)")
print(f"Signal: {signal}")

# Load previous signal
signal_file = os.path.join(os.path.dirname(__file__), '..', 'btc-signal.json')
prev_signal = None
try:
    with open(signal_file, 'r') as f:
        prev_data = json.load(f)
        prev_signal = prev_data.get('signal')
except (FileNotFoundError, json.JSONDecodeError):
    pass

# Save current signal
signal_data = {
    'date': date,
    'price': round(price, 2),
    'rsi': round(rsi, 1),
    'ma155': round(ma155, 2),
    'vol': round(vol * 100, 1),
    'signal': signal,
    'updated': datetime.utcnow().isoformat() + 'Z'
}
with open(signal_file, 'w') as f:
    json.dump(signal_data, f, indent=2)

print(f"\nPrevious signal: {prev_signal}")
print(f"Current signal: {signal}")

# Send alert if signal changed
if prev_signal and prev_signal != signal:
    print(f"\n*** SIGNAL CHANGED: {prev_signal} → {signal} ***")

    # Send Telegram alert
    tg_token = os.environ.get('TELEGRAM_TOKEN', '8528820380:AAHNc3wBp_Nm2DCKunZurOGRRvi2e3fJ-MI')
    tg_chat = os.environ.get('TELEGRAM_CHAT_ID', '5151262026')

    if signal == 'BUY':
        emoji = '🟢'
        action = 'BUY NOW — all conditions met.'
    else:
        emoji = '🔴'
        action = 'SELL / GO TO CASH — conditions no longer met.'

    tg_msg = f"""{emoji} BTC Signal: {prev_signal} → {signal}

Price: ${price:,.0f}
RSI14: {rsi:.1f}
MA155: ${ma155:,.0f}
Vol20: {vol*100:.0f}%

{action}

https://bivarcapital.com/btc.html"""

    try:
        tg_url = f'https://api.telegram.org/bot{tg_token}/sendMessage?chat_id={tg_chat}&text={urllib.parse.quote(tg_msg)}'
        urllib.request.urlopen(tg_url, context=ctx)
        print("Telegram alert sent!")
    except Exception as e:
        print(f"Telegram failed: {e}")
else:
    print("No change. No alert needed.")
