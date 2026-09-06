#!/usr/bin/env python3
"""
Druckenmiller 13F Tracker — site signal updater.

Run any day to refresh prices; on/after a 13F filing day it detects the new
filing automatically and rolls the portfolio.

  python3 scripts/druckenmiller_13f_signal.py

Filing days (45 days after quarter end): ~Feb 14, May 15, Aug 14, Nov 14.
Buy day = first trading day after the filing date. On filing day the script
writes the new portfolio with entry prices = latest close (provisional);
run it again after the buy day's close to lock real entry prices.

CUSIP->ticker map: ~/druck_13f/cusip_map.json (built from Sharadar TICKERS,
kept out of the public repo). Unmapped CUSIPs are reported and skipped.
"""
import json, re, os, sys, subprocess, datetime as dt
import xml.etree.ElementTree as ET

CIK = 1536411
SITE = os.path.join(os.path.dirname(__file__), '..')
PORT_JSON = os.path.join(SITE, 'druckenmiller-13f-portfolio.json')
DATA_JSON = os.path.join(SITE, 'druckenmiller-13f-data.json')
CUSIP_MAP = os.path.expanduser('~/druck_13f/cusip_map.json')
UA = 'Bivar Capital luisportugalabra@gmail.com'

def get(url, ua=UA):
    return subprocess.run(['curl','-s','-H',f'User-Agent: {ua}',url],capture_output=True).stdout

def latest_filing():
    sub = json.loads(get(f'https://data.sec.gov/submissions/CIK{CIK:010d}.json'))
    r = sub['filings']['recent']
    f13 = [(r['filingDate'][i], r['reportDate'][i], r['accessionNumber'][i])
           for i in range(len(r['form'])) if r['form'][i]=='13F-HR']
    return max(f13)  # (filing_date, report_date, accession)

def parse_infotable(cik, accession):
    accn = accession.replace('-','')
    idx = json.loads(get(f'https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/index.json'))
    files = [f['name'] for f in idx['directory']['item']]
    cand = [f for f in files if f.lower().endswith('.xml') and 'primary_doc' not in f.lower()]
    tgt = next((f for f in cand if 'info' in f.lower() or 'table' in f.lower()), cand[0])
    txt = get(f'https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/{tgt}').decode('utf-8','replace')
    txt = re.sub(r'(xmlns(:\w+)?|\w+:\w+)="[^"]*"', '', txt)
    txt = re.sub(r'<(/?)\w+:', r'<\1', txt)
    out = []
    for it in ET.fromstring(txt).iter('infoTable'):
        sh = it.find('shrsOrPrnAmt')
        putcall = (it.findtext('putCall','') or '').strip()
        shtype = sh.findtext('sshPrnamtType','').strip() if sh is not None else ''
        if putcall or shtype != 'SH': continue
        out.append({'cusip': it.findtext('cusip','').strip().upper(),
                    'issuer': it.findtext('nameOfIssuer','').strip(),
                    'value': float(it.findtext('value','0').replace(',',''))})
    return out

def yahoo_price(ticker):
    y = ticker.replace('.','-')
    p2 = int(dt.datetime.now().timestamp()); p1 = p2 - 86400*14
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{y}?period1={p1}&period2={p2}&interval=1d'
    try:
        d = json.loads(get(url, ua='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'))
        res = d['chart']['result'][0]
        closes = [(t,c) for t,c in zip(res['timestamp'], res['indicators']['quote'][0]['close']) if c]
        return closes  # list of (unix_ts, close)
    except Exception:
        return []

def next_trading_day(date):
    d = date + dt.timedelta(days=1)
    while d.weekday() >= 5: d += dt.timedelta(days=1)
    return d

def main():
    port = json.load(open(PORT_JSON))
    cmap = json.load(open(CUSIP_MAP))
    fdate, rdate, acc = latest_filing()
    print(f'latest 13F: report {rdate}, filed {fdate}')

    new_filing = rdate > port['report_date']
    if new_filing:
        print('NEW FILING — rolling portfolio')
        raw = parse_infotable(CIK, acc)
        agg = {}
        unmapped = []
        for r in raw:
            m = cmap.get(r['cusip'])
            if not m:
                unmapped.append((r['cusip'], r['issuer'], r['value'])); continue
            t = m[0]
            if t not in agg: agg[t] = {'ticker': t, 'name': r['issuer'], 'value': 0.0}
            agg[t]['value'] += r['value']
        if unmapped:
            tot_all = sum(r['value'] for r in raw)
            miss = sum(v for _,_,v in unmapped)
            print(f'  WARNING unmapped: {len(unmapped)} positions, {miss/tot_all*100:.2f}% of value')
            for c,n,v in unmapped: print('   ', c, n)
        entry_date = next_trading_day(dt.date.fromisoformat(fdate))
        tot = sum(a['value'] for a in agg.values())
        holdings = []
        for a in sorted(agg.values(), key=lambda x: -x['value']):
            holdings.append({'ticker': a['ticker'], 'name': a['name'],
                             'entry_date': str(entry_date), 'entry_price': None,
                             'current_price': None, 'weight': round(a['value']/tot, 4),
                             'return_pct': None})
        port.update({'report_date': rdate, 'filing_date': fdate,
                     'last_rebalance': str(entry_date), 'holdings': holdings})
        rq = dt.date.fromisoformat(rdate)
        nxt_q_end = dt.date(rq.year + (rq.month+3>12), (rq.month+3-1)%12+1, 1) - dt.timedelta(days=1)
        due = nxt_q_end + dt.timedelta(days=45)
        while due.weekday() >= 5: due += dt.timedelta(days=1)
        port['next_filing'] = str(due)

    # refresh prices
    stale = []
    for h in port['holdings']:
        closes = yahoo_price(h['ticker'])
        if not closes: stale.append(h['ticker']); continue
        entry_ts = dt.datetime.fromisoformat(h['entry_date']).timestamp()
        on_or_after = [c for t,c in closes if t >= entry_ts - 12*3600]
        if h['entry_price'] is None and on_or_after:
            h['entry_price'] = round(on_or_after[0], 2)
        h['current_price'] = round(closes[-1][1], 2)
        if h['entry_price']:
            h['return_pct'] = round((h['current_price']/h['entry_price']-1)*100, 2)
    if stale: print('no price for:', stale)

    port['updated'] = str(dt.date.today())
    json.dump(port, open(PORT_JSON,'w'), indent=1)
    data = json.load(open(DATA_JSON))
    data.update({'date': port['updated'], 'n_positions': len(port['holdings'])})
    json.dump(data, open(DATA_JSON,'w'), indent=1)
    print(f"wrote {len(port['holdings'])} holdings; next filing due {port.get('next_filing')}")
    if new_filing:
        print('>> commit + push the two JSONs, and send the Telegram alert')

if __name__ == '__main__':
    main()
