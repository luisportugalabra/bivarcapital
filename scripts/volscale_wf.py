"""Constant-vol scaling done without look-ahead: the target is an expanding
median of past strategy vol, never the full sample. Then walk-forward."""
import warnings; warnings.filterwarnings('ignore')
import numpy as np, pandas as pd, os
SP='/private/tmp/claude-501/-Users-luisabrantes/8886b953-a92e-4174-8656-fa856169a782/scratchpad'
RF=0.03
def st_(x):
    x=x.dropna(); n=len(x)/12; c=(1+x).prod()**(1/n)-1; v=x.std()*np.sqrt(12); e=(1+x).cumprod()
    return c*100,(c-RF)/v,(e/e.cummax()-1).min()*100
def load(mkt):
    if mkt=='USA':
        os.chdir('/Users/luisabrantes/trending_value_us'); g={}
        exec(open(f'{SP}/usa_regimes.py').read().split("V=[('SPX MA250")[0], g)
        return g['G'], g['ks'], g['D250'], g['COST']
    os.chdir('/Users/luisabrantes/eodhd_data/audit2_de'); g={}
    if mkt=='ALEMANHA':
        exec(open('de_states.py').read().split('print(f"=== os quatro')[0], g)
        return g['G'], sorted(g['G']), g['D200'], g['COST']/10_000
    exec(open(f'{SP}/ca_regimes.py').read().split('V={}')[0], g)
    return g['G'], g['ks'], g['R75'], g['COSTD']
for MKT in ('USA','CANADA','ALEMANHA'):
    G,ks,D,C=load(MKT)
    gross=pd.Series({k:G[k][0] for k in ks}).sort_index()
    sv6=gross.rolling(6,min_periods=4).std()*np.sqrt(12)
    tgt_exp=sv6.expanding(min_periods=36).median().shift(1)     # past only
    tgt_full=sv6.median()                                        # the look-ahead version
    def ser(cap=None, tgt=None):
        o={}
        for k in ks:
            g,tv,t=G[k]; on=float(D.get(t,0)); w=1.0
            if cap is not None:
                s=sv6.shift(1).get(k,np.nan)
                tv_=tgt.get(k,np.nan) if hasattr(tgt,'get') else tgt
                if np.isfinite(s) and s>0 and np.isfinite(tv_): w=float(np.clip(tv_/s,0,cap))
            o[k]=g*on*w-(tv*C*w if on else 0.0)
        return pd.Series(o).dropna()
    B=ser()
    print(f"\n{'='*84}\n{MKT}\n{'='*84}")
    print(f"{'variante':<40} {'CAGR':>7} {'Sharpe':>7} {'MaxDD':>8}")
    print('-'*68)
    cb,sb,mb=st_(B); print(f"{'MA sozinha (baseline)':<40} {cb:6.1f}% {sb:7.2f} {mb:7.1f}%")
    for cap in (1.0,1.5,2.0):
        a=ser(cap,tgt_full); b=ser(cap,tgt_exp)
        c1,s1,m1=st_(a); c2,s2,m2=st_(b)
        print(f"{f'cap {cap}x, alvo = mediana TOTAL (lookahead)':<40} {c1:6.1f}% {s1:7.2f} {m1:7.1f}%")
        print(f"{f'cap {cap}x, alvo = mediana do PASSADO':<40} {c2:6.1f}% {s2:7.2f} {m2:7.1f}%  <-- honesto")
    # walk-forward: fixed rule vs fixed rule, no selection
    oos=ks[60:]
    print(f"\n   fora da amostra ({len(oos)} meses), regras FIXAS:")
    cb2,sb2,mb2=st_(B.reindex(oos))
    print(f"      {'MA sozinha':<34} CAGR {cb2:5.1f}%  Sharpe {sb2:5.2f}  MaxDD {mb2:6.1f}%")
    for cap in (1.0,1.5):
        c,s,m=st_(ser(cap,tgt_exp).reindex(oos))
        print(f"      {f'vol constante cap {cap}x (honesto)':<34} CAGR {c:5.1f}%  Sharpe {s:5.2f}  MaxDD {m:6.1f}%  {s-sb2:+.3f}")
    # rolling 5y win rate, honest version
    for cap in (1.0,1.5):
        s_=ser(cap,tgt_exp); w=t=0
        for i in range(60,len(ks),6):
            win=ks[i-60:i]; a=st_(s_.reindex(win))[1]; b=st_(B.reindex(win))[1]
            if np.isfinite(a) and np.isfinite(b): t+=1; w+= a>b
        print(f"      janelas 5a em que cap {cap}x bate a MA: {w}/{t} ({w/t*100:.0f}%)")
