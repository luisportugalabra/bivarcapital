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

# SSL context for API calls
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

from datetime import timedelta

def fetch_coinmetrics():
    start_date = (datetime.utcnow() - timedelta(days=220)).strftime('%Y-%m-%d')
    cm_url = f'https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=PriceUSD&frequency=1d&start_time={start_date}&page_size=10000'
    cm_data = json.loads(urllib.request.urlopen(cm_url, context=ctx).read())
    closes = [float(d['PriceUSD']) for d in cm_data['data']]
    print(f"CoinMetrics: {len(closes)} daily closes loaded")
    return closes

def fetch_coingecko():
    url = 'https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=220&interval=daily'
    data = json.loads(urllib.request.urlopen(url, context=ctx).read())
    closes = [p[1] for p in data['prices']]
    print(f"CoinGecko: {len(closes)} daily closes loaded")
    return closes

# Try multiple sources with fallback
closes = None
for source_fn in [fetch_coinmetrics, fetch_coingecko]:
    try:
        closes = source_fn()
        if closes and len(closes) >= 155:
            break
    except Exception as e:
        print(f"  {source_fn.__name__} failed: {e}")
        closes = None

if not closes or len(closes) < 155:
    raise RuntimeError("All data sources failed — cannot compute signal")

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

# Signal (uses daily close for calculation)
price = closes[-1]
signal = "BUY" if rsi > 54 and price > ma155 and vol < 1.0 else "CASH"
date = datetime.utcnow().strftime('%Y-%m-%d')

# Fetch live price for display
live_price = price
try:
    cg = json.loads(urllib.request.urlopen('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd', context=ctx).read())
    live_price = cg['bitcoin']['usd']
    print(f"Live price (CoinGecko): ${live_price:,.0f}")
except Exception as e:
    print(f"Live price fetch failed: {e}, using daily close")

print(f"Date: {date}")
print(f"Daily close: ${price:,.0f}")
print(f"Live price: ${live_price:,.0f}")
print(f"RSI14: {rsi:.1f} (need >54)")
print(f"MA155: ${ma155:,.0f} (price {'ABOVE' if price > ma155 else 'BELOW'})")
print(f"Vol20: {vol*100:.0f}% (need <100%)")
print(f"Signal: {signal}")

# Load previous signal
signal_file = os.path.join(os.path.dirname(__file__), '..', 'btc-signal.json')
prev_signal = None
prev_date = None
try:
    with open(signal_file, 'r') as f:
        prev_data = json.load(f)
        prev_signal = prev_data.get('signal')
        prev_date = prev_data.get('date')
except (FileNotFoundError, json.JSONDecodeError):
    pass

already_ran_today = (prev_date == date)

# Save current signal
signal_data = {
    'date': date,
    'price': round(live_price, 2),
    'rsi': round(rsi, 1),
    'ma155': round(ma155, 2),
    'vol': round(vol * 100, 1),
    'signal': signal,
    'updated': datetime.utcnow().isoformat() + 'Z'
}
with open(signal_file, 'w') as f:
    json.dump(signal_data, f, indent=2)

print(f"\nPrevious signal: {prev_signal} (date: {prev_date})")
print(f"Current signal: {signal} (date: {date})")
print(f"Already ran today: {already_ran_today}")

# Send Telegram alert (skip if already sent today and signal unchanged)
if already_ran_today and prev_signal == signal:
    print("Telegram already sent today with same signal — skipping.")
else:
    tg_token = os.environ.get('TELEGRAM_TOKEN', '8528820380:AAHNc3wBp_Nm2DCKunZurOGRRvi2e3fJ-MI')

    # Get approved subscribers from Supabase
    sb_url = 'https://efiyeiwdywodjxxnslvu.supabase.co'
    sb_key = os.environ.get('SUPABASE_SERVICE_KEY', '')

    try:
        req = urllib.request.Request(
            f'{sb_url}/rest/v1/telegram_subscribers?status=eq.approved&select=chat_id',
            headers={'apikey': sb_key, 'Authorization': f'Bearer {sb_key}'}
        )
        resp = json.loads(urllib.request.urlopen(req, context=ctx).read())
        chat_ids = [r['chat_id'] for r in resp]
        print(f"Sending to {len(chat_ids)} approved subscribers...")
    except Exception as e:
        print(f"Supabase error: {e}, falling back to admin only")
        chat_ids = [5151262026]

    if prev_signal and prev_signal != signal:
        print(f"\n*** SIGNAL CHANGED: {prev_signal} → {signal} ***")
        if signal == 'BUY':
            emoji = '🟢'
            action = 'BUY NOW — all conditions met.'
        else:
            emoji = '🔴'
            action = 'SELL / GO TO CASH — conditions no longer met.'
        tg_msg = f"""{emoji} SIGNAL CHANGED: {prev_signal} → {signal}

Price: ${live_price:,.0f}
RSI14: {rsi:.1f}
MA155: ${ma155:,.0f}
Vol20: {vol*100:.0f}%

{action}

https://bivarcapital.com/btc.html"""
    else:
        emoji = '🟢' if signal == 'BUY' else '🔴'
        rsi_icon = '✓' if rsi > 54 else '✗'
        ma_icon = '✓' if price > ma155 else '✗'
        vol_icon = '✓' if vol < 1.0 else '✗'
        tg_msg = f"""{emoji} Daily BTC: {signal}

Price: ${live_price:,.0f}
{rsi_icon} RSI14: {rsi:.1f} (>54)
{ma_icon} MA155: ${ma155:,.0f} ({'above' if price > ma155 else 'below'})
{vol_icon} Vol20: {vol*100:.0f}% (<100%)

No change from yesterday.
https://bivarcapital.com/btc.html"""

    for chat_id in chat_ids:
        try:
            tg_url = f'https://api.telegram.org/bot{tg_token}/sendMessage?chat_id={chat_id}&text={urllib.parse.quote(tg_msg)}'
            urllib.request.urlopen(tg_url, context=ctx)
            print(f"  Sent to {chat_id}")
        except Exception as e:
            print(f"  Failed for {chat_id}: {e}")
