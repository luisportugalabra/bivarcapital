#!/usr/bin/env python3
"""
Process Telegram /start commands — register new subscribers in Supabase.
Runs before btc_signal.py in the GitHub Action workflow.
"""
import json
import os
import urllib.request
import urllib.parse
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

TG_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8528820380:AAHNc3wBp_Nm2DCKunZurOGRRvi2e3fJ-MI')
SB_URL = 'https://efiyeiwdywodjxxnslvu.supabase.co'
SB_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')

def tg_api(method, params=None):
    url = f'https://api.telegram.org/bot{TG_TOKEN}/{method}'
    if params:
        url += '?' + urllib.parse.urlencode(params)
    return json.loads(urllib.request.urlopen(url, context=ctx).read())

def sb_request(endpoint, method='GET', data=None):
    url = f'{SB_URL}/rest/v1/{endpoint}'
    headers = {
        'apikey': SB_KEY,
        'Authorization': f'Bearer {SB_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    return urllib.request.urlopen(req, context=ctx)

# Get existing subscribers
existing = set()
try:
    req = urllib.request.Request(
        f'{SB_URL}/rest/v1/telegram_subscribers?select=chat_id',
        headers={'apikey': SB_KEY, 'Authorization': f'Bearer {SB_KEY}'}
    )
    rows = json.loads(urllib.request.urlopen(req, context=ctx).read())
    existing = {r['chat_id'] for r in rows}
    print(f"Existing subscribers: {len(existing)}")
except Exception as e:
    print(f"Error fetching subscribers: {e}")

# Get Telegram updates
updates = tg_api('getUpdates', {'timeout': 0})
if not updates.get('ok'):
    print("Failed to get updates")
    exit(0)

results = updates.get('result', [])
print(f"Pending updates: {len(results)}")

max_update_id = 0
new_count = 0

for update in results:
    max_update_id = max(max_update_id, update['update_id'])
    msg = update.get('message', {})
    text = msg.get('text', '')
    chat = msg.get('chat', {})
    chat_id = chat.get('id')

    if not chat_id:
        continue

    if text == '/start':
        username = msg.get('from', {}).get('username', '')
        first_name = msg.get('from', {}).get('first_name', '')

        if chat_id in existing:
            # Already subscribed — send confirmation
            tg_api('sendMessage', {
                'chat_id': chat_id,
                'text': 'You are already subscribed to BTC signal alerts.\n\nYou will receive a message when the signal changes (BUY/CASH).\n\nhttps://bivarcapital.com/btc.html'
            })
            print(f"  Already subscribed: {chat_id} ({first_name})")
        else:
            # New subscriber — add to Supabase with approved status
            try:
                sb_request('telegram_subscribers', 'POST', {
                    'chat_id': chat_id,
                    'username': username,
                    'first_name': first_name,
                    'status': 'approved'
                })
                existing.add(chat_id)
                new_count += 1
                tg_api('sendMessage', {
                    'chat_id': chat_id,
                    'text': f'Welcome {first_name}!\n\nYou are now subscribed to Bivar Capital BTC signal alerts.\n\nYou will receive a Telegram message whenever the signal changes between BUY and CASH.\n\nCurrent signal: check https://bivarcapital.com/btc.html'
                })
                print(f"  New subscriber: {chat_id} ({first_name} @{username})")
            except Exception as e:
                print(f"  Error adding {chat_id}: {e}")

    elif text == '/stop':
        if chat_id in existing:
            try:
                sb_request(f'telegram_subscribers?chat_id=eq.{chat_id}', 'DELETE')
                existing.discard(chat_id)
                tg_api('sendMessage', {
                    'chat_id': chat_id,
                    'text': 'You have been unsubscribed. Send /start to resubscribe.'
                })
                print(f"  Unsubscribed: {chat_id}")
            except Exception as e:
                print(f"  Error removing {chat_id}: {e}")

    elif text == '/status':
        # Load current signal
        try:
            signal_file = os.path.join(os.path.dirname(__file__), '..', 'btc-signal.json')
            with open(signal_file, 'r') as f:
                sig = json.load(f)
            emoji = '\U0001f7e2' if sig['signal'] == 'BUY' else '\U0001f534'
            status_msg = f"{emoji} Current signal: {sig['signal']}\n\nPrice: ${sig['price']:,.0f}\nRSI14: {sig['rsi']}\nMA155: ${sig['ma155']:,.0f}\nVol: {sig['vol']}%\nDate: {sig['date']}\n\nhttps://bivarcapital.com/btc.html"
        except Exception:
            status_msg = "Signal data not available. Check https://bivarcapital.com/btc.html"
        tg_api('sendMessage', {'chat_id': chat_id, 'text': status_msg})
        print(f"  Status sent to: {chat_id}")

# Acknowledge processed updates
if max_update_id > 0:
    tg_api('getUpdates', {'offset': max_update_id + 1, 'timeout': 0})
    print(f"Acknowledged updates up to {max_update_id}")

print(f"Done. {new_count} new subscribers added.")
