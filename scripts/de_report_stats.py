import warnings; warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, json, yfinance as yf
RF=0.03
d=pd.read_csv('/Users/luisabrantes/eodhd_data/germany_n10_live_returns.csv')
r=pd.Series(pd.to_numeric(d.iloc[:,1],errors='coerce').values,
            index=pd.to_datetime(d.iloc[:,0])).dropna()
dax=yf.download('^GDAXI',start='1999-01-01',progress=False,auto_adjust=True)['Close'].squeeze()
dax.index=pd.to_datetime(dax.index)
b=(dax.resample('ME').last().pct_change()).reindex(r.index).fillna(0)

def st(x, bench=None):
    n=len(x)/12; c=(1+x).prod()**(1/n)-1; v=x.std()*np.sqrt(12); eq=(1+x).cumprod()
    rfm=(1+RF)**(1/12)-1; dn=(x-rfm).clip(upper=0)
    o=dict(cagr=c, vol=v, sharpe=(c-RF)/v, sortino=(c-RF)/(np.sqrt((dn**2).mean())*np.sqrt(12)),
           maxdd=(eq/eq.cummax()-1).min(), worst=x.min(), best=x.max(), pos=(x>0).mean(), n=len(x))
    if bench is not None:
        bb=bench.reindex(x.index).fillna(0)
        up=bb>0; dnm=bb<0
        o['up_capture']=float((x[up].mean()/bb[up].mean())) if up.sum() else np.nan
        o['down_capture']=float((x[dnm].mean()/bb[dnm].mean())) if dnm.sum() else np.nan
        o['bench_cagr']=(1+bb).prod()**(1/(len(bb)/12))-1
        o['beta']=float(np.cov(x,bb)[0,1]/bb.var())
        o['alpha']=o['cagr']-(RF+o['beta']*(o['bench_cagr']-RF))
    return o

R={'full': st(r,b), 'cash_months': float((r.abs()<1e-12).mean())}
R['sub']={lbl: st(r[a:c], b) for lbl,a,c in
          [('2000-2007','2000','2007'),('2008-2014','2008','2014'),
           ('2015-2026 (com mortes no dataset)','2015','2026'),('2021-2026','2021','2026')]}
eq=(1+r).cumprod(); dd=eq/eq.cummax()-1
ep=[]; inn=False
for t,v in dd.items():
    if v<-0.10 and not inn: inn=True; s0=t; lo=v; lot=t
    elif inn:
        if v<lo: lo, lot = v, t
        if v>=-0.001:
            ep.append(dict(start=str(s0.date()), trough=str(lot.date()), end=str(t.date()),
                           depth=float(lo), months=int(round((t-s0).days/30.44)),
                           recovery=int(round((t-lot).days/30.44)))); inn=False
if inn: ep.append(dict(start=str(s0.date()), trough=str(lot.date()), end=None, depth=float(lo),
                       months=int(round((dd.index[-1]-s0).days/30.44)), recovery=None))
R['episodes']=sorted(ep,key=lambda x:x['depth'])[:6]
R['worst_months']=[{'m':str(m.date()),'r':float(r[m]),'dax':float(b[m])} for m in r.nsmallest(6).index]
R['best_months']=[{'m':str(m.date()),'r':float(r[m]),'dax':float(b[m])} for m in r.nlargest(4).index]
ann=(1+r).groupby(r.index.year).prod()-1; annb=(1+b).groupby(b.index.year).prod()-1
R['yearly']=[{'y':int(y),'s':float(ann[y]),'b':float(annb.get(y,np.nan))} for y in ann.index]
R['beat_years']=int(sum(1 for x in R['yearly'] if x['s']>x['b']))
json.dump(R, open('de_report_stats.json','w'), default=float, indent=1)
f=R['full']
print(f"CAGR {f['cagr']*100:.1f}%  Sharpe {f['sharpe']:.2f}  Sortino {f['sortino']:.2f}  MaxDD {f['maxdd']*100:.1f}%")
print(f"beta {f['beta']:.2f}  alpha {f['alpha']*100:+.1f}pp  up-capture {f['up_capture']:.2f}  down-capture {f['down_capture']:.2f}")
print(f"DAX no periodo: {f['bench_cagr']*100:.1f}%  |  bate o DAX em {R['beat_years']}/{len(R['yearly'])} anos")
print(f"meses em cash: {R['cash_months']*100:.0f}%")
print("\nsubperiodos:")
for k,v in R['sub'].items(): print(f"  {k:<34} CAGR {v['cagr']*100:5.1f}%  Sharpe {v['sharpe']:5.2f}  MaxDD {v['maxdd']*100:6.1f}%")
print("\nepisodios de drawdown >10%:")
for e in R['episodes']: print(f"  {e['start']} -> {e['trough']} ({e['depth']*100:.1f}%) fundo em {e['months']-(e['recovery'] or 0)}m, recuperou em {e['recovery'] if e['recovery'] is not None else '(em curso)'}m")
