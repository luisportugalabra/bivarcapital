"""Collect every regime result into one JSON for the article."""
import warnings; warnings.filterwarnings('ignore')
import numpy as np, pandas as pd, os, json, collections
SP='/private/tmp/claude-501/-Users-luisabrantes/8886b953-a92e-4174-8656-fa856169a782/scratchpad'
RF=0.03
def st_(x):
    x=x.dropna(); n=len(x)/12; c=(1+x).prod()**(1/n)-1; v=x.std()*np.sqrt(12); e=(1+x).cumprod()
    return dict(cagr=c*100, sharpe=(c-RF)/v, maxdd=(e/e.cummax()-1).min()*100, n=len(x))
def load(mkt):
    if mkt=='USA':
        os.chdir('/Users/luisabrantes/trending_value_us'); g={}
        exec(open(f'{SP}/usa_regimes.py').read().split("V=[('SPX MA250")[0], g)
        return g['G'], g['ks'], g['D250'], g['COST'], (1+g['bench']).cumprod(), 250
    os.chdir('/Users/luisabrantes/eodhd_data/audit2_de'); g={}
    if mkt=='ALEMANHA':
        exec(open('de_states.py').read().split('print(f"=== os quatro')[0], g)
        return g['G'], sorted(g['G']), g['D200'], g['COST']/10_000, g['idx'], 200
    exec(open(f'{SP}/ca_regimes.py').read().split('V={}')[0], g)
    return g['G'], g['ks'], g['R75'], g['COSTD'], g['idx'], 75
OUT={}
for MKT in ('USA','ALEMANHA','CANADA'):
    G,ks,D,C,idx,W0=load(MKT)
    gross=pd.Series({k:G[k][0] for k in ks}).sort_index(); geq=(1+gross).cumprod()
    sv6=gross.rolling(6,min_periods=4).std()*np.sqrt(12)
    tgt=sv6.expanding(min_periods=36).median().shift(1)
    def base(Dx=None):
        Dx=D if Dx is None else Dx; o={}
        for k in ks:
            g,tv,t=G[k]; on=float(Dx.get(t,0)); o[k]=g*on-(tv*C if on else 0.0)
        return pd.Series(o).dropna()
    def selfma(Wm=9):
        o={}
        for j,k in enumerate(ks):
            g,tv,t=G[k]
            on=1.0 if (j<Wm or geq.iloc[:j].iloc[-1]>=geq.iloc[:j].tail(Wm).mean()) else 0.0
            o[k]=g*on-(tv*C if on else 0.0)
        return pd.Series(o).dropna()
    def both(Wm=9):
        o={}
        for j,k in enumerate(ks):
            g,tv,t=G[k]
            se=1.0 if (j<Wm or geq.iloc[:j].iloc[-1]>=geq.iloc[:j].tail(Wm).mean()) else 0.0
            on=float(D.get(t,0))*se; o[k]=g*on-(tv*C if on else 0.0)
        return pd.Series(o).dropna()
    def volsc(cap):
        o={}
        for k in ks:
            g,tv,t=G[k]; on=float(D.get(t,0))
            s=sv6.shift(1).get(k,np.nan); tt=tgt.get(k,np.nan)
            w=float(np.clip(tt/s,0,cap)) if np.isfinite(s) and s>0 and np.isfinite(tt) else 1.0
            o[k]=g*on*w-(tv*C*w if on else 0.0)
        return pd.Series(o).dropna()
    def always():
        o={}
        for k in ks: g,tv,t=G[k]; o[k]=g-tv*C
        return pd.Series(o).dropna()
    V={'MA que corre':base(),'MA na propria curva (9m)':selfma(),'os dois concordam':both(),
       'vol constante cap 1.0x':volsc(1.0),'vol constante cap 1.5x':volsc(1.5),'sempre investido':always()}
    oos=ks[60:]
    OUT[MKT]={'window':W0,'n':len(ks),'start':str(pd.Timestamp(ks[0]).date()),'end':str(pd.Timestamp(ks[-1]).date()),
              'full':{l:st_(s) for l,s in V.items()}, 'oos':{l:st_(s.reindex(oos)) for l,s in V.items()}}
    # MA window sweep
    sweep={}
    for w in (50,75,100,125,150,200,250,300,350):
        m=(idx>=idx.rolling(w,min_periods=int(w*.8)).mean()).astype(int)
        Dx=m.resample('ME').last().reindex([G[k][2] for k in ks]).ffill().fillna(0)
        Dx.index=[G[k][2] for k in ks]
        sweep[w]=st_(base(Dx))
    OUT[MKT]['ma_sweep']=sweep
    # walk-forward: pick among all variants each year
    oo=[];picks=[]
    for i in range(60,len(ks)-11,12):
        tr=ks[i-60:i]; te=ks[i:i+12]
        best,bs=None,-9
        for l,s in V.items():
            v=s.reindex(tr).dropna()
            if len(v)<24: continue
            sh=st_(v)['sharpe']
            if sh>bs: bs,best=sh,l
        if best: oo.append(V[best].reindex(te).dropna()); picks.append(best)
    sel=pd.concat(oo)
    OUT[MKT]['wf']={'chosen':st_(sel),'fixed':st_(V['MA que corre'].reindex(sel.index)),
                    'picks':dict(collections.Counter(picks))}
    # rolling 5y win rate of vol scaling
    for cap,lab in ((1.0,'cap1'),(1.5,'cap15')):
        s_=volsc(cap); B=V['MA que corre']; w=t=0
        for i in range(60,len(ks),6):
            win=ks[i-60:i]
            a=st_(s_.reindex(win))['sharpe']; b=st_(B.reindex(win))['sharpe']
            if np.isfinite(a) and np.isfinite(b): t+=1; w+= a>b
        OUT[MKT][f'win_{lab}']=[w,t]
    if MKT=='USA':
        W={}
        for k in ks:
            s=sv6.shift(1).get(k,np.nan); tt=tgt.get(k,np.nan)
            W[str(pd.Timestamp(k).date())]=float(np.clip(tt/s,0,1.5)) if np.isfinite(s) and s>0 and np.isfinite(tt) else 1.0
        OUT[MKT]['exposure']=W
        OUT[MKT]['gross']={str(pd.Timestamp(k).date()):float(gross[k]) for k in ks}
    print(f"{MKT}: {len(ks)} meses, {len(V)} variantes, sweep de {len(sweep)} janelas", flush=True)
json.dump(OUT, open(f'{SP}/article_data.json','w'), indent=1, default=float)
print("guardado")
