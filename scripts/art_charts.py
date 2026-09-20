import warnings; warnings.filterwarnings('ignore')
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt, numpy as np, pandas as pd, json, io, base64
BG='#060608';BORD='#1a1a22';TXT='#e8e8ec';MUT='#5a5a68';ACC='#c4a265';GRN='#4ade80';RED='#f87171';BLU='#7aa2f7'
plt.rcParams.update({'figure.facecolor':BG,'axes.facecolor':BG,'savefig.facecolor':BG,'text.color':TXT,
 'axes.labelcolor':TXT,'xtick.color':MUT,'ytick.color':MUT,'axes.edgecolor':BORD,'grid.color':BORD,
 'font.size':9,'axes.titlesize':11,'legend.frameon':False,'figure.dpi':110})
def b64(f):
    b=io.BytesIO(); f.savefig(b,format='png',bbox_inches='tight',pad_inches=.3); plt.close(f)
    return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
D=json.load(open('article_data.json')); C={}
MK=['USA','ALEMANHA','CANADA']; COL={'USA':ACC,'ALEMANHA':BLU,'CANADA':GRN}
EN={'USA':'USA','ALEMANHA':'Germany','CANADA':'Canada'}
LIVE={'USA':250,'ALEMANHA':200,'CANADA':75}

f,ax=plt.subplots(1,3,figsize=(13,3.6))
for i,m in enumerate(MK):
    s=D[m]['ma_sweep']; w=[int(k) for k in s]; v=[s[k]['sharpe'] for k in s]
    ax[i].plot(w,v,color=COL[m],lw=1.8,marker='o',ms=4)
    ax[i].axvline(LIVE[m],color=RED,ls=':',lw=1)
    ax[i].annotate(f'MA{LIVE[m]}\n(live)',xy=(LIVE[m],max(v)),xytext=(LIVE[m]+18,max(v)*0.96),
                   color=RED,fontsize=7.5)
    ax[i].set_title(EN[m]); ax[i].set_xlabel('moving-average window (days)'); ax[i].grid(alpha=.25,lw=.5)
    if i==0: ax[i].set_ylabel('Sharpe')
f.suptitle('Sharpe by moving-average window — the live setting sits on a shelf, not a spike', y=1.04)
C['sweep']=b64(f)

f,a=plt.subplots(figsize=(11,3.8)); x=np.arange(len(MK)); w=.35
ch=[D[m]['wf']['chosen']['sharpe'] for m in MK]; fx=[D[m]['wf']['fixed']['sharpe'] for m in MK]
a.bar(x-w/2,ch,w,color=RED,alpha=.85,label='re-optimised every January')
a.bar(x+w/2,fx,w,color=ACC,alpha=.9,label='filter left alone')
for i,(c,fv) in enumerate(zip(ch,fx)):
    a.text(i-w/2,c+.02,f'{c:.2f}',ha='center',fontsize=8,color=TXT)
    a.text(i+w/2,fv+.02,f'{fv:.2f}',ha='center',fontsize=8,color=TXT)
a.set_xticks(x); a.set_xticklabels([EN[m] for m in MK]); a.set_ylabel('Sharpe, out of sample'); a.legend()
a.set_title('Re-optimising the rule each year loses in all three markets'); a.grid(alpha=.2,lw=.5,axis='y')
C['wf']=b64(f)

e=pd.Series(D['USA']['exposure']); e.index=pd.to_datetime(e.index)
g=pd.Series(D['USA']['gross']); g.index=pd.to_datetime(g.index); eq=(1+g).cumprod()
f,(a1,a2)=plt.subplots(2,1,figsize=(12,5.4),sharex=True,gridspec_kw={'height_ratios':[2,1]})
a1.plot(eq.index,eq.values,color=ACC,lw=1.4); a1.set_yscale('log')
a1.set_title('USA — the strategy (top) and the exposure constant-vol scaling would have set (bottom)')
a1.grid(alpha=.25,lw=.5); a1.set_ylabel('growth of 1 (log)')
a2.fill_between(e.index,e.values*100,100,where=e.values>=1,color=GRN,alpha=.35,lw=0)
a2.fill_between(e.index,e.values*100,100,where=e.values<1,color=RED,alpha=.4,lw=0)
a2.plot(e.index,e.values*100,color=TXT,lw=.8); a2.axhline(100,color=BORD,lw=.9)
a2.set_ylabel('exposure %'); a2.grid(alpha=.25,lw=.5)
C['expo']=b64(f)

f,a=plt.subplots(figsize=(11,3.6)); x=np.arange(len(MK)); w=.26
for k,(lab,col,en) in enumerate([('MA que corre',ACC,'live MA filter'),('vol constante cap 1.0x',BLU,'constant vol, cap 1.0x'),('os dois concordam',GRN,'both signals agree')]):
    v=[D[m]['oos'][lab]['maxdd'] for m in MK]
    a.bar(x+(k-1)*w,v,w,color=col,alpha=.9,label=en)
a.set_xticks(x); a.set_xticklabels([EN[m] for m in MK]); a.set_ylabel('MaxDD, out of sample (%)')
a.legend(); a.grid(alpha=.2,lw=.5,axis='y'); a.set_title('The two alternatives that cut drawdown, and what they cost')
C['dd']=b64(f)
json.dump(C,open('art_charts.json','w')); print(f"{len(C)} graficos")
