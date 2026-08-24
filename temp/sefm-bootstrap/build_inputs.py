#!/usr/bin/env python3
import argparse, io, json, re, zipfile
from pathlib import Path
import pandas as pd, requests
HOUSE_URL='https://crproject.org/data/jsoncsv/mit-1976-2024-house.csv'; FEC_CN26='https://www.fec.gov/files/bulk-downloads/2026/cn26.zip'
REDRAW_2024={'AL','GA','LA','NY','NC'}; REDRAW_2026={'AL','CA','FL','LA','MO','NC','OH','TN','TX','UT'}
NATIONAL={2018:{'generic':.087,'approval':-.14},2020:{'generic':.073,'approval':-.06},2024:{'generic':-.003,'approval':-.15},2026:{'generic':.067,'approval':-.31}}
HOUSE_SEATS={'AL':7,'AK':1,'AZ':9,'AR':4,'CA':52,'CO':8,'CT':5,'DE':1,'FL':28,'GA':14,'HI':2,'ID':2,'IL':17,'IN':9,'IA':4,'KS':4,'KY':6,'LA':6,'ME':2,'MD':8,'MA':9,'MI':13,'MN':8,'MS':4,'MO':8,'MT':2,'NE':3,'NV':4,'NH':2,'NJ':12,'NM':3,'NY':26,'NC':14,'ND':1,'OH':15,'OK':5,'OR':6,'PA':17,'RI':2,'SC':7,'SD':1,'TN':9,'TX':38,'UT':4,'VT':1,'VA':11,'WA':10,'WV':2,'WI':8,'WY':1}
def norm(s):
 s=str(s or '').upper(); s=re.sub(r'[^A-Z0-9 ]+',' ',s); s=re.sub(r'\b(JR|SR|II|III|IV)\b',' ',s); return re.sub(r'\s+',' ',s).strip()
def did(st,d):
 n=int(float(d)); return f'{st}-AL' if n==0 else f'{st}-{n:02d}'
def universe():
 return [did(st,0 if n==1 else i) for st,n in sorted(HOUSE_SEATS.items()) for i in range(1,n+1)]
def load_house():
 r=requests.get(HOUSE_URL,timeout=120); r.raise_for_status(); d=pd.read_csv(io.BytesIO(r.content),low_memory=False)
 d=d[(d.stage.astype(str).str.upper()=='GEN') & (~d.special.astype(str).str.upper().eq('TRUE')) & d.year.isin([2016,2018,2020,2022,2024])].copy()
 d['district_id']=[did(s,x) for s,x in zip(d.state_po,d.district)]; d['party_norm']=d.party.astype(str).str.upper(); d['candidate_norm']=d.candidate.map(norm); d['votes']=pd.to_numeric(d.candidatevotes,errors='coerce').fillna(0); return d
def summaries(d):
 rows=[]
 for (yr,st,di),g in d.groupby(['year','state_po','district_id']):
  dem=g[g.party_norm.str.startswith('DEMOCRAT')].votes.sum(); rep=g[g.party_norm.str.startswith('REPUBLICAN')].votes.sum(); den=dem+rep
  if den<=0: continue
  cg=g.groupby(['candidate_norm','party_norm'],as_index=False).votes.sum().sort_values('votes',ascending=False); w=cg.iloc[0]
  rows.append({'cycle':int(yr),'state':st,'district_id':di,'dem_two_party_share':float(dem/den),'winner_name':w.candidate_norm,'winner_party':w.party_norm})
 return pd.DataFrame(rows)
def inc(raw,summ,cyc,exclude):
 prev=summ[summ.cycle==cyc-2]; names={(r.state,r.winner_name):r.winner_party for r in prev.itertuples()}; cand=raw[raw.year==cyc]; bg={k:g for k,g in cand.groupby('district_id')}; rows=[]
 for r in summ[(summ.cycle==cyc)&(~summ.state.isin(exclude))].itertuples():
  party=None
  for x in bg.get(r.district_id,[]).itertuples() if r.district_id in bg else []:
   if (r.state,x.candidate_norm) in names: party=x.party_norm; break
  de=int(bool(party and str(party).startswith('DEMOCRAT'))); rp=int(bool(party and str(party).startswith('REPUBLICAN'))); rows.append((r.district_id,de,rp,int(de+rp==0)))
 return pd.DataFrame(rows,columns=['district_id','incumbent_dem','incumbent_rep','open_seat'])
def historical(raw,summ):
 out=[]
 for cyc,ex in [(2018,{'PA'}),(2020,set()),(2024,REDRAW_2024)]:
  cur=summ[(summ.cycle==cyc)&(~summ.state.isin(ex))].copy(); prev=summ[summ.cycle==cyc-2][['district_id','dem_two_party_share']].rename(columns={'dem_two_party_share':'prior_dem_two_party_share'}); cur=cur.merge(prev,on='district_id').merge(inc(raw,summ,cyc,ex),on='district_id')
  cur['national_generic_dem_margin']=NATIONAL[cyc]['generic']; cur['presidential_net_approval']=NATIONAL[cyc]['approval']; cur['poll_dem_margin']=0.; cur['poll_available']=0; cur['crosswalk_status']='DIRECTLY_COMPARABLE_SAME_MAP'
  out.append(cur[['cycle','district_id','dem_two_party_share','prior_dem_two_party_share','national_generic_dem_margin','presidential_net_approval','incumbent_dem','incumbent_rep','open_seat','poll_dem_margin','poll_available','crosswalk_status']])
 return pd.concat(out,ignore_index=True)
def load_fec():
 r=requests.get(FEC_CN26,timeout=120); r.raise_for_status(); z=zipfile.ZipFile(io.BytesIO(r.content)); name=[n for n in z.namelist() if n.lower().endswith('.txt')][0]; cols=['CAND_ID','CAND_NAME','PARTY','ELECTION_YR','STATE','OFFICE','DISTRICT','ICI','STATUS','PCC','ST1','ST2','CITY','MAIL_ST','ZIP']; d=pd.read_csv(z.open(name),sep='|',header=None,names=cols,dtype=str,encoding='latin1'); d=d[(d.OFFICE=='H')&(d.ELECTION_YR=='2026')].copy(); d['district_id']=[did(s,x or 0) for s,x in zip(d.STATE,d.DISTRICT.fillna('0'))]; return d
def status(fec):
 rows=[]
 for di in universe():
  g=fec[fec.district_id==di]; ii=g[g.ICI=='I']; oo=g[g.ICI=='O']; de=int(any(ii.PARTY.fillna('').str.upper().str.startswith('DEM'))); rp=int(any(ii.PARTY.fillna('').str.upper().str.startswith('REP'))); op=int(len(oo)>0 and de+rp==0); rows.append({'district_id':di,'incumbent_dem':de,'incumbent_rep':rp,'open_seat':op,'status':'READY' if de+rp+op==1 else 'UNRESOLVED'})
 return pd.DataFrame(rows)
def current(summ,crosswalk,fec):
 base=summ[summ.cycle==2024][['district_id','state','dem_two_party_share']]; direct=base[~base.state.isin(REDRAW_2026)][['district_id','dem_two_party_share']].rename(columns={'dem_two_party_share':'prior_dem_two_party_share'}); direct['crosswalk_status']='DIRECT_119_TO_120_UNCHANGED'; x=pd.read_csv(crosswalk).merge(base[['district_id','dem_two_party_share']].rename(columns={'district_id':'source_district_id'}),on='source_district_id'); x['weighted']=x.dem_two_party_share*x.target_weight; mapped=x.groupby('target_district_id',as_index=False).weighted.sum().rename(columns={'target_district_id':'district_id','weighted':'prior_dem_two_party_share'}); mapped['crosswalk_status']='POPULATION_WEIGHTED_119_TO_120'; cur=pd.concat([direct,mapped],ignore_index=True); st=status(fec); cur=cur.merge(st,on='district_id',how='left'); cur['national_generic_dem_margin']=NATIONAL[2026]['generic']; cur['presidential_net_approval']=NATIONAL[2026]['approval']; cur['poll_dem_margin']=0.; cur['poll_available']=0; cur.loc[cur.status!='READY','crosswalk_status']='UNRESOLVED'; return cur[['district_id','prior_dem_two_party_share','national_generic_dem_margin','presidential_net_approval','incumbent_dem','incumbent_rep','open_seat','poll_dem_margin','poll_available','crosswalk_status']],st
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--crosswalk',required=True); ap.add_argument('--outdir',required=True); a=ap.parse_args(); od=Path(a.outdir); od.mkdir(parents=True,exist_ok=True); raw=load_house(); summ=summaries(raw); h=historical(raw,summ); c,s=current(summ,a.crosswalk,load_fec()); h.to_csv(od/'house_historical_training.csv',index=False); c.to_csv(od/'house_2026_features.csv',index=False); s.to_csv(od/'fec_2026_district_status.csv',index=False); (od/'input_provenance.json').write_text(json.dumps({'house':HOUSE_URL,'fec':FEC_CN26,'national':NATIONAL},indent=2)); print({'historical':len(h),'current':len(c),'unresolved':int((s.status!='READY').sum())})
if __name__=='__main__': main()
