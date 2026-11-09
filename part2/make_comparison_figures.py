"""Standalone publication/export figures from completed OOF outputs; no refitting."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch, Patch
from matplotlib.colors import TwoSlopeNorm, Normalize
from matplotlib.ticker import MaxNLocator

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/feature_comparison'
FIG=OUT/'figures'
FIG.mkdir(exist_ok=True)
df=pd.read_csv(OUT/'predictions_oof.csv',dtype={'zip':str})
m=pd.read_csv(OUT/'metrics_all_287.csv')
names=['poisson','random_forest','gradient_boosting']
labels=['Poisson','Random forest','Gradient boosting']
colors={'base':'#39749c','augmented':'#cf7840'}
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,
                     'savefig.facecolor':'white','figure.facecolor':'white'})
def save(fig,name):
    fig.savefig(FIG/f'{name}.png',dpi=220,bbox_inches='tight')
    fig.savefig(FIG/f'{name}.pdf',bbox_inches='tight')
    plt.close(fig)

fig,axes=plt.subplots(1,3,figsize=(12,3.8),layout='constrained')
for ax,key,title in zip(axes,['r2','spearman','top10_recall'],['R²','Spearman correlation','Top-10% recall']):
    x=np.arange(3)
    for j,config in enumerate(['base','augmented']):
        vals=[float(m[(m.config==config)&(m.model==name)][key].iloc[0]) for name in names]
        bars=ax.bar(x+(j-.5)*.34,vals,.32,color=colors[config],label='Base (11)' if config=='base' else 'Base + ACS (15)')
        ax.bar_label(bars,fmt='%.3f',padding=3,fontsize=8)
    ax.axhline(0,color='#666666',lw=.6)
    ax.set_xticks(x,labels,rotation=15,ha='right');ax.set_title(title)
    lo,hi=ax.get_ylim();ax.set_ylim(min(lo,0)-.02,hi+.06)
fig.legend(*axes[0].get_legend_handles_labels(),loc='outside lower center',ncol=2,fontsize=9)
fig.suptitle('Added ACS features: matched LA spatial out-of-fold comparison (287 ZIPs)')
save(fig,'model_comparison')

maxval=max(df.y_true.max(),df.filter(like='pred_').max().max())*1.06
fig,axes=plt.subplots(2,3,figsize=(10,6.7),layout='constrained',sharex=True,sharey=True)
for row,config in enumerate(['base','augmented']):
    for col,(name,label) in enumerate(zip(names,labels)):
        ax=axes[row,col];p=df[f'pred_{name}_{config}']
        ax.scatter(df.y_true,p,s=13,alpha=.58,color=colors[config],edgecolors='none')
        ax.plot([0,maxval],[0,maxval],'--',color='#666666',lw=1)
        ax.set(xlim=(0,maxval),ylim=(0,maxval),title=f'{label} · {config}')
        ax.set_aspect('equal',adjustable='box')
        if row==1: ax.set_xlabel('UCLA label')
        if col==0: ax.set_ylabel('OOF prediction')
fig.suptitle('Label versus prediction: same axes in all panels\nExcess ER visits per 10,000, UCLA category-4 historical label (2008–2018)')
save(fig,'label_vs_prediction')

geo=json.loads((ROOT/'data/zips.geojson').read_text())
lookup=df.set_index('zip')
assert {str(f['properties']['zip']).zfill(5) for f in geo['features']}==set(df.zip)
def polygon_patches(geometry):
    polygons=[geometry['coordinates']] if geometry['type']=='Polygon' else geometry['coordinates']
    for rings in polygons:
        vertices=[];codes=[]
        for ring in rings:
            if len(ring)<3:continue
            vertices.extend([xy[:2] for xy in ring]);codes.extend([MPath.MOVETO]+[MPath.LINETO]*(len(ring)-2)+[MPath.CLOSEPOLY])
        yield PathPatch(MPath(vertices,codes))

def draw_map(ax,value,colorfunc):
    for f in geo['features']:
        z=str(f['properties']['zip']).zfill(5)
        for patch in polygon_patches(f['geometry']):
            patch.set_facecolor(colorfunc(lookup.loc[z,value]));patch.set_edgecolor('#ffffff');patch.set_linewidth(.2);ax.add_patch(patch)
    ax.autoscale_view();ax.set_aspect(1/np.cos(np.deg2rad(34.1)))
    ax.set_xlabel('Longitude');ax.set_ylabel('Latitude');ax.tick_params(labelsize=8)
    ax.xaxis.set_major_locator(MaxNLocator(4))

palette=['#4c78a8','#f58518','#54a24b','#b279a2','#e45756']
fig,ax=plt.subplots(figsize=(7,6.5),layout='constrained')
draw_map(ax,'group',lambda g:palette[int(g)])
counts=df.groupby('group').size()
ax.legend(handles=[Patch(facecolor=palette[int(g)],label=f'Fold {g}: {n} ZIPs') for g,n in counts.items()],loc='upper right',fontsize=9)
ax.set_title('Five original LA spatial folds\nEach ZIP is tested once; fold assignments are unchanged')
save(fig,'LA_spatial_folds')

valuecols=['y_true']+[f'pred_{name}_{config}' for config in ['base','augmented'] for name in names]
assert np.isfinite(df[valuecols].to_numpy()).all()
value_norm=Normalize(vmin=min(0.,float(df[valuecols].min().min())),
                     vmax=float(df[valuecols].max().max()))
value_cmap=plt.get_cmap('YlOrRd')
fig,axes=plt.subplots(3,3,figsize=(12,11),layout='constrained')
for row,(name,label) in enumerate(zip(names,labels)):
    for col,(field,title) in enumerate([
        ('y_true','UCLA historical label'),
        (f'pred_{name}_base','Base (11 features)'),
        (f'pred_{name}_augmented','Base + ACS (15 features)')]):
        ax=axes[row,col]
        draw_map(ax,field,lambda v:value_cmap(value_norm(v)))
        ax.set_title(f'{label}\n{title}',fontsize=10)
fig.colorbar(plt.cm.ScalarMappable(norm=value_norm,cmap=value_cmap),
             ax=axes.ravel().tolist(),shrink=.65,
             label='Estimated excess ER visits per 10,000 residents')
fig.suptitle('LA historical category-4 label and spatial OOF predictions\n'
             '287 ZIPs; one common colour scale; UCLA target period 2008–2018')
save(fig,'label_prediction_maps')

errcols=[f'error_{name}_{config}' for config in ['base','augmented'] for name in names]
limit=float(np.abs(df[errcols].to_numpy()).max())
norm=TwoSlopeNorm(vmin=-limit,vcenter=0,vmax=limit)
cmap=plt.get_cmap('RdBu_r')
fig,axes=plt.subplots(2,3,figsize=(12,8),layout='constrained')
for row,config in enumerate(['base','augmented']):
    for col,(name,label) in enumerate(zip(names,labels)):
        ax=axes[row,col]
        draw_map(ax,f'error_{name}_{config}',lambda e:cmap(norm(e)))
        ax.set_title(f'{label} · {config}',fontsize=10)
fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),ax=axes.ravel().tolist(),shrink=.65,
             label='Prediction − UCLA label / 10,000 (blue: underprediction; red: overprediction)')
fig.suptitle('Spatial prediction errors: identical zero-centred scale in all panels')
save(fig,'spatial_errors')

fig,axes=plt.subplots(1,3,figsize=(12,3.4),layout='constrained')
fold=pd.read_csv(OUT/'metrics_per_fold.csv')
for ax,name,label in zip(axes,names,labels):
    a=fold[(fold.model==name)&(fold.config=='augmented')].set_index('group')
    b=fold[(fold.model==name)&(fold.config=='base')].set_index('group')
    delta=a.mae-b.mae
    ax.bar(delta.index.astype(str),delta,color=['#cf7840' if x>0 else '#39749c' for x in delta])
    ax.axhline(0,color='#555555',lw=.8);ax.set_title(label);ax.set_xlabel('Held-out geographic fold')
axes[0].set_ylabel('MAE change: augmented − base\nNegative means improvement')
fig.suptitle('Added-feature effect varies across held-out regions')
save(fig,'MAE_change_by_fold')
print('Saved six figures as PNG and PDF to',FIG)
