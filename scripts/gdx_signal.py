#!/usr/bin/env python3
"""
GDX Weekly Signal — runs every Friday after market close via GitHub Actions
Logic: if GDX ETF returns >+2% this week → BUY Gold+Silver next week (Mon open → Fri close)
       otherwise → CASH
Data source: Yahoo Finance API (no key required)
"""
import json
import os
import math
import urllib.request
import urllib.parse
import ssl
from datetime import datetime, timedelta, timezone

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def yf_weekly(ticker, weeks=10):
    """Fetch weekly closes from Yahoo Finance (no API key needed)."""
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?interval=1wk&range={weeks+2}wk'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    data = json.loads(urllib.request.urlopen(req, context=ctx, timeout=15).read())
    result = data['chart']['result'][0]
    closes = result['indicators']['quote'][0]['close']
    timestamps = result['timestamp']
    # Filter out None values
    pairs = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
    return pairs  # list of (unix_ts, close)

# ── Fetch GDX weekly closes ──────────────────────────────────────────────────
print("Fetching GDX weekly data...")
gdx_pairs = yf_weekly('GDX', weeks=12)

if len(gdx_pairs) < 2:
    raise RuntimeError("Not enough GDX data to compute weekly return")

# Last completed week return
prev_close = gdx_pairs[-2][1]
this_close = gdx_pairs[-1][1]
gdx_weekly_ret = (this_close / prev_close) - 1

# Week date (last Friday)
week_date = datetime.fromtimestamp(gdx_pairs[-1][0], tz=timezone.utc).strftime('%Y-%m-%d')

THR = 0.02
signal = "BUY" if gdx_weekly_ret > THR else "CASH"

print(f"GDX prev close: ${prev_close:.2f}")
print(f"GDX this close: ${this_close:.2f}")
print(f"GDX weekly return: {gdx_weekly_ret*100:+.2f}%")
print(f"Threshold: >{THR*100:.0f}%")
print(f"Signal: {signal}")
print(f"Week ending: {week_date}")

# ── Fetch Gold and Silver current prices (for display) ───────────────────────
gold_price = None
silver_price = None
try:
    gold_pairs = yf_weekly('GC=F', weeks=2)
    gold_price = gold_pairs[-1][1]
    print(f"Gold: ${gold_price:,.1f}")
except Exception as e:
    print(f"Gold fetch failed: {e}")

try:
    silv_pairs = yf_weekly('SI=F', weeks=2)
    silver_price = silv_pairs[-1][1]
    print(f"Silver: ${silver_price:.2f}")
except Exception as e:
    print(f"Silver fetch failed: {e}")

# ── Load previous signal ─────────────────────────────────────────────────────
signal_file = os.path.join(os.path.dirname(__file__), '..', 'gdx-signal.json')
prev_signal = None
prev_week = None
try:
    with open(signal_file, 'r') as f:
        prev_data = json.load(f)
        prev_signal = prev_data.get('signal')
        prev_week = prev_data.get('week')
except (FileNotFoundError, json.JSONDecodeError):
    pass

already_ran_this_week = (prev_week == week_date)

# ── Save current signal ──────────────────────────────────────────────────────
signal_data = {
    'week': week_date,
    'gdx_close': round(this_close, 2),
    'gdx_prev_close': round(prev_close, 2),
    'gdx_weekly_ret': round(gdx_weekly_ret * 100, 2),
    'threshold': THR * 100,
    'signal': signal,
    'gold_price': round(gold_price, 1) if gold_price else None,
    'silver_price': round(silver_price, 3) if silver_price else None,
    'updated': datetime.now(timezone.utc).isoformat()
}
with open(signal_file, 'w') as f:
    json.dump(signal_data, f, indent=2)

print(f"\nPrevious: {prev_signal} (week: {prev_week})")
print(f"Current:  {signal} (week: {week_date})")
print(f"Already ran this week: {already_ran_this_week}")

# ── Send Telegram alert ──────────────────────────────────────────────────────
if already_ran_this_week and prev_signal == signal:
    print("Already sent this week with same signal — skipping Telegram.")
else:
    tg_token = os.environ.get('TELEGRAM_TOKEN', '8528820380:AAHNc3wBp_Nm2DCKunZurOGRRvi2e3fJ-MI')
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

    chk   = '✅' if gdx_weekly_ret > THR else '❌'
    gold_str   = ('$' + f'{gold_price:,.1f}') if gold_price else '—'
    silver_str = ('$' + f'{silver_price:.2f}') if silver_price else '—'

    if prev_signal and prev_signal != signal:
        emoji  = '🟢' if signal == 'BUY' else '🔴'
        action = 'Long Gold + Silver — entry Friday close / Monday open.' if signal == 'BUY' else 'Go to CASH — no position next week.'
        tg_msg = f"""{emoji} GDX SIGNAL CHANGED: {prev_signal} → {signal}
Week ending {week_date}

{chk} GDX weekly return: {gdx_weekly_ret:+.2f}% (need >+{THR*100:.0f}%)
   GDX close:  ${this_close:.2f}
   Gold (GC):  {gold_str}
   Silver (SI): {silver_str}

⚡ Action: {action}

📊 Strategy: GDX Weekly → Gold + Silver
   CAGR +10.2% | Active CAGR +32.1% | Sharpe 1.23

bivarcapital.com/gdx.html"""
    else:
        emoji = '🟢' if signal == 'BUY' else '🔴'
        next_action = 'Long Gold + Silver next week.' if signal == 'BUY' else 'No position next week — cash.'
        tg_msg = f"""{emoji} GDX Weekly Signal — {week_date}
Signal: {signal} (no change)

{chk} GDX this week: {gdx_weekly_ret:+.2f}% (threshold >+{THR*100:.0f}%)
   GDX close:   ${this_close:.2f}  (prev ${prev_close:.2f})
   Gold (GC):   {gold_str}
   Silver (SI):  {silver_str}

→ {next_action}

bivarcapital.com/gdx.html"""

    for chat_id in chat_ids:
        try:
            tg_url = f'https://api.telegram.org/bot{tg_token}/sendMessage?chat_id={chat_id}&text={urllib.parse.quote(tg_msg)}'
            urllib.request.urlopen(tg_url, context=ctx, timeout=10)
            print(f"  Sent to {chat_id}")
        except Exception as e:
            print(f"  Failed for {chat_id}: {e}")
