"""Combined portfolio, rebuilt from the three published series.
USA  : midcap_series $10B+ monthly       (published 25.6/0.87/-33.2; reads 26.1/0.87/-35.5)
CAN  : canada_harness_returns.csv        (published 33.8/1.19/-26.0 -- exact)
GER  : germany_n10_live_returns.csv      (published 19.1/0.72/-39.1 -- exact)"""
import warnings; warnings.filterwarnings('ignore')
import pandas as pd, numpy as np, pickle, json, itertools
RF=0.03
SP='/private/tmp/claude-501/-Users-luisabrantes/8886b953-a92e-4174-8656-fa856169a782/scratchpad'

u=pickle.load(open('/Users/luisabrantes/trending_value_us/midcap_series.pkl','rb'))['$10B+ (o do site)']
usa=((1+u).resample('ME').prod()-1); usa.index=usa.index.to_period('M'); usa=usa[:'2026-04']
def ld(f):
    d=pd.read_csv(f'/Users/luisabrantes/eodhd_data/{f}')
    s=pd.Series(pd.to_numeric(d.iloc[:,1],errors='coerce').values,
                index=pd.to_datetime(d.iloc[:,0]).dt.to_period('M')).dropna()
    return s[~s.index.duplicated()]
X=pd.concat([usa.rename('USA'), ld('canada_harness_returns.csv').rename('Canada'),
             ld('germany_n10_live_returns.csv').rename('Germany')], axis=1).dropna()
X.to_csv(f'{SP}/combo_clean.csv')

def st(r):
    r=r.dropna(); n=len(r)/12; c=(1+r).prod()**(1/n)-1; v=r.std()*np.sqrt(12)
    eq=(1+r).cumprod(); dn=(r-((1+RF)**(1/12)-1)).clip(upper=0)
    so=(c-RF)/(np.sqrt((dn**2).mean())*np.sqrt(12))
    return dict(cagr=c, vol=v, sharpe=(c-RF)/v, sortino=so, maxdd=(eq/eq.cummax()-1).min(),
                worst=r.min(), best=r.max(), pos=(r>0).mean())
R={'window': [str(X.index.min()), str(X.index.max())], 'n': len(X)}
R['sleeves']={c: st(X[c]) for c in X.columns}
R['corr']=X.corr().round(3).to_dict()
dn=X.mean(axis=1) < X.mean(axis=1).quantile(0.20)
R['corr_tail']=X[dn].corr().round(3).to_dict()

grid=[(a,b,100-a-b) for a in range(0,101,5) for b in range(0,101-a,5)]
rows=[]
for w in grid:
    r=(X*np.array(w)/100).sum(axis=1); s=st(r); s['w']=w; rows.append(s)
best=max(rows,key=lambda x:x['sharpe'])
se=np.sqrt((1+best['sharpe']**2/2)/len(X))
R['grid_best']=best; R['se']=se
R['tied']=[x['w'] for x in rows if x['sharpe']>=best['sharpe']-se]
R['grid']=[{'w':x['w'],'cagr':x['cagr'],'sharpe':x['sharpe'],'maxdd':x['maxdd']} for x in rows]
for lbl,w in [('equal',(33,33,34)),('35/40/25',(35,40,25)),('best',best['w'])]:
    R.setdefault('cands',{})[lbl]={'w':w, **st((X*np.array(w)/100).sum(axis=1))}
iv=1/X.std(); iv=(iv/iv.sum()*100).round(0)
R['cands']['inv-vol']={'w':tuple(iv), **st((X*iv.values/100).sum(axis=1))}

# walk-forward: does optimising beat a fixed weight out of sample?
g10=[(a,b,100-a-b) for a in range(0,101,10) for b in range(0,101-a,10)]
oo,oe,of_=[],[],[]
for i in range(60,len(X)-11,12):
    tr,te=X.iloc[i-60:i],X.iloc[i:i+12]
    b=max(g10,key=lambda w: st((tr*np.array(w)/100).sum(axis=1))['sharpe'])
    oo.append((te*np.array(b)/100).sum(axis=1))
    oe.append((te*np.array([33,33,34])/100).sum(axis=1))
    of_.append((te*np.array([35,40,25])/100).sum(axis=1))
R['wf']={k: st(pd.concat(v)) for k,v in [('otimizado',oo),('equal',oe),('35/40/25',of_)]}
R['wf']['n']=len(pd.concat(oo))

p=(X*np.array([35,40,25])/100).sum(axis=1)
ann = {k: ((1+X[k]).groupby(X.index.year).prod()-1) for k in X.columns}
annp = (1+p).groupby(p.index.year).prod()-1
R['yearly']=[{'y':int(y), 'usa':float(ann['USA'][y]), 'can':float(ann['Canada'][y]),
              'ger':float(ann['Germany'][y]), 'port':float(annp[y])} for y in annp.index]
R['worst_months']=[{'m':str(m), **{c: float(X.loc[m,c]) for c in X.columns}, 'port': float(p[m])}
                   for m in p.nsmallest(8).index]
json.dump(R, open(f'{SP}/combo_results.json','w'), default=float, indent=1)
print(f"janela {R['window'][0]} a {R['window'][1]}  ({R['n']} meses)")
print("\nsleeves:")
for k,v in R['sleeves'].items():
    print(f"  {k:<8} CAGR {v['cagr']*100:5.1f}%  Sharpe {v['sharpe']:.2f}  MaxDD {v['maxdd']*100:6.1f}%")
print(f"\ncorrelacoes:\n{X.corr().round(2).to_string()}")
print(f"\nmelhor do grid: {best['w']}  Sharpe {best['sharpe']:.3f}  (SE {se:.3f}, {len(R['tied'])} empatadas de {len(rows)})")
for k,v in R['cands'].items():
    print(f"  {k:<10} {str(v['w']):<14} CAGR {v['cagr']*100:5.1f}%  Sharpe {v['sharpe']:.2f}  MaxDD {v['maxdd']*100:6.1f}%")
print(f"\nwalk-forward ({R['wf']['n']} meses OOS):")
for k in ('otimizado','equal','35/40/25'):
    v=R['wf'][k]; print(f"  {k:<12} CAGR {v['cagr']*100:5.1f}%  Sharpe {v['sharpe']:.2f}  MaxDD {v['maxdd']*100:6.1f}%")
