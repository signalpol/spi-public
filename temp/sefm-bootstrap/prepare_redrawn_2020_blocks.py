#!/usr/bin/env python3
from __future__ import annotations
import argparse, time
from pathlib import Path
import geopandas as gpd
import pandas as pd
import requests
STATES={'01':'AL','06':'CA','12':'FL','22':'LA','29':'MO','37':'NC','39':'OH','47':'TN','48':'TX','49':'UT'}
API='https://api.census.gov/data/2020/dec/pl'
def api_json(params,retries=5):
    last=None
    for i in range(retries):
        r=requests.get(API,params=params,timeout=120,headers={'User-Agent':'SPI-SEFM-GE-US/1.0'})
        last=r
        ctype=r.headers.get('content-type','')
        if r.ok and 'json' in ctype.lower():
            j=r.json(); return pd.DataFrame(j[1:],columns=j[0])
        time.sleep(2**i)
    raise RuntimeError(f'Census API failed/non-JSON: status={last.status_code if last else None} type={last.headers.get("content-type") if last else None} body={(last.text[:300] if last else "")!r}')
def population_for_state(fips):
    counties=api_json({'get':'NAME','for':'county:*','in':f'state:{fips}'})
    parts=[]
    for county in counties['county']:
        d=api_json({'get':'P1_001N','for':'block:*','in':f'state:{fips} county:{county} tract:*'})
        d['GEOID20']=d['state']+d['county']+d['tract']+d['block']
        parts.append(d[['GEOID20','P1_001N']].rename(columns={'P1_001N':'POP20'}))
    return pd.concat(parts,ignore_index=True)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); a=ap.parse_args()
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True); tmp=out.parent/'_blocks_tmp'; tmp.mkdir(parents=True,exist_ok=True)
    allg=[]
    for fips,st in STATES.items():
        url=f'https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_{fips}_tabblock20.zip'
        r=requests.get(url,timeout=300); r.raise_for_status(); zpath=tmp/f'{st}.zip'; zpath.write_bytes(r.content)
        g=gpd.read_file(f'zip://{zpath}')
        print(st,'BLOCK_COLUMNS',list(g.columns))
        if 'POP20' in g.columns:
            g['POP20']=pd.to_numeric(g['POP20'],errors='coerce')
            if g.POP20.isna().any(): raise SystemExit(f'{st} POP20 contains NA')
            pop_source='TIGER_POP20'
        else:
            p=population_for_state(fips); p['POP20']=pd.to_numeric(p.POP20,errors='coerce')
            g=g.merge(p,on='GEOID20',how='left')
            if g.POP20.isna().any(): raise SystemExit(f'{st} population join NA')
            pop_source='PL_API_P1'
        print(st,'blocks',len(g),'population',int(g.POP20.sum()),'source',pop_source)
        allg.append(g[['STATEFP20','GEOID20','POP20','geometry']])
    merged=pd.concat(allg,ignore_index=True)
    gpd.GeoDataFrame(merged,geometry='geometry',crs=allg[0].crs).to_file(out,driver='GPKG')
    print('PASS',len(merged),int(merged.POP20.sum()))
if __name__=='__main__': main()
