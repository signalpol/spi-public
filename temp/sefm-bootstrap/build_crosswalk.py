#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import geopandas as gpd
import pandas as pd
FIPS_TO_ST={'01':'AL','06':'CA','12':'FL','22':'LA','29':'MO','37':'NC','39':'OH','47':'TN','48':'TX','49':'UT'}
REDRAW=set(FIPS_TO_ST)
def norm_cd(s,d):
    st=FIPS_TO_ST[str(s).zfill(2)]; d=str(d).zfill(2); return f'{st}-AL' if d=='00' else f'{st}-{d}'
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--blocks',required=True); ap.add_argument('--cd119',required=True); ap.add_argument('--cd120',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    b=gpd.read_file(a.blocks); c119=gpd.read_file(a.cd119); c120=gpd.read_file(a.cd120)
    b=b[b.STATEFP20.astype(str).str.zfill(2).isin(REDRAW)].copy(); b['POP20']=pd.to_numeric(b.POP20,errors='coerce').fillna(0); b=b[b.POP20>0]
    pts=b[['GEOID20','POP20','geometry']].copy(); pts['geometry']=pts.geometry.representative_point(); pts=pts.set_crs(b.crs,allow_override=True)
    c119=c119[c119.STATEFP.astype(str).str.zfill(2).isin(REDRAW)][['STATEFP','CD119FP','geometry']].to_crs(pts.crs)
    c120=c120[c120.STATEFP.astype(str).str.zfill(2).isin(REDRAW)][['STATEFP','CD120FP','geometry']].to_crs(pts.crs)
    j119=gpd.sjoin(pts,c119,predicate='within',how='inner').drop(columns=['index_right']); j119['source_district_id']=[norm_cd(s,d) for s,d in zip(j119.STATEFP,j119.CD119FP)]
    j120=gpd.sjoin(j119[['GEOID20','POP20','source_district_id','geometry']],c120,predicate='within',how='inner'); j120['target_district_id']=[norm_cd(s,d) for s,d in zip(j120.STATEFP,j120.CD120FP)]
    x=j120.groupby(['source_district_id','target_district_id'],as_index=False).POP20.sum().rename(columns={'POP20':'pop_overlap'})
    x=x.merge(x.groupby('source_district_id').pop_overlap.sum().rename('source_population'),on='source_district_id').merge(x.groupby('target_district_id').pop_overlap.sum().rename('target_population'),on='target_district_id')
    x['source_weight']=x.pop_overlap/x.source_population; x['target_weight']=x.pop_overlap/x.target_population; x['crosswalk_status']='POPULATION_WEIGHTED_2020_BLOCKS'
    assert ((x.groupby('source_district_id').source_weight.sum()-1).abs()<1e-8).all(); assert ((x.groupby('target_district_id').target_weight.sum()-1).abs()<1e-8).all()
    assert {v.split('-')[0] for v in x.target_district_id}==set(FIPS_TO_ST.values())
    Path(a.out).parent.mkdir(parents=True,exist_ok=True); x.to_csv(a.out,index=False); print('PASS',len(x),x.source_district_id.nunique(),x.target_district_id.nunique())
if __name__=='__main__': main()
