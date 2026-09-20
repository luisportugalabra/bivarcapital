"""Charts for the Germany strategy report, in the USA report's house style."""
import warnings; warnings.filterwarnings('ignore')
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt, matplotlib.dates as mdates
import pandas as pd, numpy as np, json, io, base64, yfinance as yf
BG='#060608'; CARD='#0c0c10'; BORD='#1a1a22'; TXT='#e8e8ec'; MUT='#5a5a68'
ACC='#c4a265'; GRN='#4ade80'; RED='#f87171'
plt.rcParams.update({'figure.facecolor':BG,'axes.facecolor':BG,'savefig.facecolor':BG,
 'text.color':TXT,'axes.labelcolor':TXT,'xtick.color':MUT,'ytick.color':MUT,
 'axes.edgecolor':BORD,'grid.color':BORD,'font.size':9,'axes.titlesize':11,
 'axes.titleweight':'600','legend.frameon':False,'figure.dpi':110})
def b64(fig):
    b=io.BytesIO(); fig.savefig(b,format='png',bbox_inches='tight',pad_inches=.3); plt.close(fig)
    return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()

d=pd.read_csv('/Users/luisabrantes/eodhd_data/germany_n10_live_returns.csv')
r=pd.Series(pd.to_numeric(d.iloc[:,1],errors='coerce').values,index=pd.to_datetime(d.iloc[:,0])).dropna()
dax=yf.download('^GDAXI',start='1998-06-01',progress=False,auto_adjust=True)['Close'].squeeze()
dax.index=pd.to_datetime(dax.index)
ma=dax.rolling(200,min_periods=160).mean()
bm=dax.resample('ME').last().pct_change().reindex(r.index).fillna(0)
eq=(1+r).cumprod(); beq=(1+bm).cumprod(); dd=eq/eq.cummax()-1
reg=(dax>=ma).resample('ME').last().reindex(r.index).ffill().fillna(0)
C={}

f,a=plt.subplots(figsize=(12,4.2))
a.plot(dax.index,dax.values,color=TXT,lw=.9,label='DAX')
a.plot(ma.index,ma.values,color=ACC,lw=1.1,label='MA200')
a.fill_between(dax.index,0,dax.max()*1.05,where=(dax<ma).reindex(dax.index).fillna(False),
               color=RED,alpha=.07,lw=0)
a.set_yscale('log'); a.set_ylim(dax.min()*.9,dax.max()*1.1); a.legend(loc='upper left')
a.set_title('DAX vs 200-day moving average — shaded where the strategy stands aside')
a.grid(alpha=.25,lw=.5); C['regime']=b64(f)

f,a=plt.subplots(figsize=(12,4.6))
a.plot(eq.index,eq.values,color=ACC,lw=1.6,label='Strategy')
a.plot(beq.index,beq.values,color=MUT,lw=1.1,label='DAX')
a.set_yscale('log'); a.legend(loc='upper left'); a.grid(alpha=.25,lw=.5)
a.set_title(f'Growth of 1 — strategy {eq.iloc[-1]:.0f}x vs DAX {beq.iloc[-1]:.1f}x')
C['equity']=b64(f)

f,a=plt.subplots(figsize=(12,3.4))
a.fill_between(dd.index,dd.values*100,0,color=RED,alpha=.5,lw=0)
a.plot(dd.index,dd.values*100,color=RED,lw=.8)
a.axhline(-39.1,color=MUT,ls=':',lw=.8); a.text(dd.index[5],-41,'-39.1% worst',color=MUT,fontsize=8)
a.set_title('Drawdown from peak'); a.set_ylabel('%'); a.grid(alpha=.25,lw=.5)
C['dd']=b64(f)

f,a=plt.subplots(figsize=(12,2.1))
a.fill_between(reg.index,0,1,where=reg.values>0,color=GRN,alpha=.55,lw=0)
a.fill_between(reg.index,0,1,where=reg.values==0,color=RED,alpha=.45,lw=0)
a.set_yticks([]); a.set_title(f'Monthly regime — invested {reg.mean()*100:.0f}% of months, cash the rest')
C['regmon']=b64(f)

piv=pd.DataFrame({'y':r.index.year,'m':r.index.month,'v':r.values*100}).pivot(index='y',columns='m',values='v')
f,a=plt.subplots(figsize=(12,7))
im=a.imshow(piv.values,cmap='RdYlGn',vmin=-25,vmax=25,aspect='auto')
a.set_xticks(range(12)); a.set_xticklabels(['J','F','M','A','M','J','J','A','S','O','N','D'])
a.set_yticks(range(len(piv))); a.set_yticklabels(piv.index,fontsize=7)
for i in range(piv.shape[0]):
    for j in range(piv.shape[1]):
        v=piv.values[i,j]
        if np.isfinite(v): a.text(j,i,f'{v:.0f}',ha='center',va='center',fontsize=6,
                                  color='#111' if abs(v)>8 else TXT)
a.set_title('Monthly returns (%)'); f.colorbar(im,ax=a,shrink=.5)
C['heat']=b64(f)

ann=(1+r).groupby(r.index.year).prod()-1; annb=(1+bm).groupby(bm.index.year).prod()-1
f,a=plt.subplots(figsize=(12,4.2)); x=np.arange(len(ann))
a.bar(x-.2,ann.values*100,.4,color=[GRN if v>0 else RED for v in ann.values],label='Strategy')
a.bar(x+.2,annb.reindex(ann.index).values*100,.4,color=MUT,alpha=.75,label='DAX')
a.set_xticks(x); a.set_xticklabels(ann.index,rotation=90,fontsize=7); a.axhline(0,color=BORD,lw=.8)
a.legend(); a.set_ylabel('%'); a.set_title('Annual returns'); a.grid(alpha=.2,lw=.5,axis='y')
C['annual']=b64(f)

roll=((1+r).rolling(36).apply(np.prod,raw=True)**(12/36)-1).dropna()*100
f,a=plt.subplots(figsize=(12,3.6))
a.fill_between(roll.index,roll.values,0,where=roll.values>0,color=GRN,alpha=.35,lw=0)
a.fill_between(roll.index,roll.values,0,where=roll.values<0,color=RED,alpha=.45,lw=0)
a.plot(roll.index,roll.values,color=ACC,lw=1.1); a.axhline(0,color=BORD,lw=.8)
a.set_title(f'Rolling 3-year CAGR — negative in {(roll<0).mean()*100:.0f}% of windows')
a.set_ylabel('%'); a.grid(alpha=.25,lw=.5); C['roll']=b64(f)

f,a=plt.subplots(figsize=(12,3.6))
a.hist(r.values*100,bins=45,color=ACC,alpha=.8)
a.axvline(r.mean()*100,color=GRN,lw=1.2,label=f'mean {r.mean()*100:+.1f}%')
a.axvline(0,color=BORD,lw=.8)
a.set_title('Distribution of monthly returns'); a.set_xlabel('%'); a.legend()
a.grid(alpha=.2,lw=.5,axis='y'); C['dist']=b64(f)

json.dump(C,open('de_charts.json','w'))
print(f"{len(C)} graficos: {', '.join(C)}")
print(f"equity final: {eq.iloc[-1]:.1f}x   DAX: {beq.iloc[-1]:.2f}x   invested {reg.mean()*100:.0f}% dos meses")
