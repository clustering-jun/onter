"""Read-only projection of Onter datasets into a provenance-aware property graph."""
from pathlib import Path
import csv,json,sqlite3,hashlib,collections,datetime,os
ROOT=Path(__file__).resolve().parents[1]; HERE=Path(__file__).resolve().parent; DATA=ROOT/'data/processed'
NEEDS={'N1':'안부와 관계','N2':'생활과 경제','N3':'건강과 돌봄','N4':'주거환경과 생활안전','N5':'문화와 활동','N6':'일자리와 학습'}
TYPE_LABELS={'complex':'단지','program':'표준 프로그램','record':'운영 기록','domain':'필요 분야','family':'프로그램 계열','target':'대상 유형','partner':'협력기관 유형','resource':'필요 자원','mode':'운영 방식','service':'서비스','purpose':'목적','case':'사례집 사례','card':'실행 레시피','obstacle':'실행 걸림돌','news':'현장 소식','organization':'기사 언급 기관','survey':'수요 응답','voc':'주민 의견','office':'해피콜 관리소','recommendation':'검토 후보','source':'근거 자료','branch':'지사'}
N={};E={};sources={};aliases=[];series={};rejected=[]
def dump(v):return json.dumps(v,ensure_ascii=False,allow_nan=False,separators=(',',':'))
def read(rel):
 p=ROOT/rel;raw=p.read_bytes();rows=list(csv.DictReader(raw.decode('utf-8-sig').splitlines(keepends=True)))
 sources[rel]={'file':rel,'rows':len(rows),'sha256':hashlib.sha256(raw).hexdigest()};return rows
def ref(rel,row=None,fields=None,note=''):
 return {'file':rel,**({'row':row} if row is not None else {}),**({'fields':fields} if fields else {}),**({'note':note} if note else {})}
def num(v,default=0):
 try:return float(v) if v not in ('',None) else default
 except (TypeError,ValueError):return default
def codes(v):return [x.strip() for x in str(v or '').split('|') if x.strip()]
def pick(r,keys):return {k:r[k] for k in keys if r.get(k) not in ('',None)}
def node(id,kind,label,attrs=None,source=None):
 if not id or id.endswith(':'):return
 if id not in N:N[id]={'id':id,'kind':kind,'label':label or id,'attrs':attrs or {},'source':source or {}}
 elif attrs:N[id]['attrs'].update(attrs)
def edge(a,b,rel,status='observed',attrs=None,source=None,weight=1,year=None):
 if a not in N or b not in N:
  rejected.append({'source':a,'target':b,'relation':rel,'reason':'missing endpoint'});return
 attrs=attrs or {};key=(a,b,rel,status,str(attrs.get('kind','')))
 eid='e:'+hashlib.sha1('|'.join(key).encode()).hexdigest()[:20]
 E[eid]={'id':eid,'source':a,'target':b,'rel':rel,'status':status,'weight':weight,'year':year,'attrs':attrs,'provenance':source or {}}

def build():
 master='data/processed/complex_integrated_20261117_v1/data/complex_master.csv'
 for i,r in enumerate(read(master),2):
  attrs={k:v for k,v in r.items() if not k.startswith('고독사_') and v!=''}
  node('complex:'+r['complex_id'],'complex',r['단지명'],attrs,ref(master,i))
  branch=r.get('지사명','')
  if branch:
   bid='branch:'+branch;node(bid,'branch',branch);edge('complex:'+r['complex_id'],bid,'관할 지사',source=ref(master,i,['지사명']))
 for k,v in NEEDS.items():node('domain:'+k,'domain',v,{'code':k,'설명':'여러 지표로 추정하는 필요 분야. 실제 미충족 수요나 개인 진단이 아님.'})
 taxonomy='data/processed/community_nlp_2026_v1/codebook_taxonomy.csv';cb=read(taxonomy);maps={}
 for i,r in enumerate(cb,2):
  kind=r['code_type'].split('(')[0];kind={'op':'mode'}.get(kind,kind)
  if kind not in ['family','target','service','mode','resource','partner_org','purpose']:continue
  kind={'partner_org':'partner'}.get(kind,kind);nid=kind+':'+r['code'];maps.setdefault(kind,{})[r['label']]=nid;maps[kind][r['code']]=nid
  node(nid,kind,r['label'],{'code':r['code'],'설명':r.get('note','')},ref(taxonomy,i))
 sd='data/processed/community_nlp_2026_v1/standard_program_dictionary.csv'
 for i,r in enumerate(read(sd),2):
  pid='program:'+r['std_id'];node(pid,'program',r['std_name'],r,ref(sd,i))
  edge(pid,'family:'+r['std_family'],'프로그램 계열','defined',source=ref(sd,i,['std_family']))
  for label in codes(r.get('need_domains_def')):
   key=next((k for k,v in NEEDS.items() if v==label),None)
   if key:edge(pid,'domain:'+key,'분야와 관련','defined',source=ref(sd,i,['need_domains_def']))
  if r.get('purpose_primary') in maps.get('purpose',{}):edge(pid,maps['purpose'][r['purpose_primary']],'유형상 주 목적','defined',source=ref(sd,i,['purpose_primary']))
  for col,kind,relation in [('target_default','target','통상 대상'),('service_default','service','서비스 유형'),('mode_default','mode','통상 운영 방식'),('ops_typical','mode','통상 운영 특성'),('resource_default','resource','통상 필요 자원')]:
   for lab in codes(r.get(col)):
    if lab in maps.get(kind,{}):edge(pid,maps[kind][lab],relation,'defined',source=ref(sd,i,[col]))
 alias='data/processed/community_nlp_2026_v1/alias_dictionary.csv'
 for r in read(alias):
  pid='program:'+r['std_id']
  if pid in N:
   for a in [r.get('canonical_title','')]+r.get('variants','').split(' / '):
    if a:aliases.append((a,pid))
 records='data/processed/community_nlp_2026_v1/program_analysis.csv';groups=collections.defaultdict(list)
 record_fields=['record_id','complex_id','complex_name','std_id','std_name','scope_label','label_source','std_confidence','std_evidence','std_evidence_field','start_date','end_date','activity_count','participants_total','participants_individual','org_count_raw','program_name_masked','activity_content_masked','place_masked','partner_org_labels','target_explicit_labels','resource_explicit_labels','est_cost_mid_krw','est_flag','dup_exact_first_flag','participants_total_mismatch_flag','date_anomaly_flag','source_row','in_resident_scope']
 for i,r in enumerate(read(records),2):
  cid='complex:'+r['complex_id'];pid='program:'+r['std_id'];rid='record:'+r['record_id'];attrs=pick(r,record_fields)
  attrs['주의']='참여인원은 반복 참여가 가능한 기록 인원. 비용은 가정에 따른 추정치.'
  node(rid,'record',r['program_name_masked'],attrs,ref(records,i,note='masked fields only; source_row is original workbook row'))
  edge(cid,rid,'운영 기록','observed',source=ref(records,i,['complex_id']),year=r.get('start_year'))
  if pid in N:edge(rid,pid,'프로그램으로 분류','tentative' if 'low' in r.get('std_confidence','') else 'derived',{'confidence':r.get('std_confidence'),'label_source':r.get('label_source')},ref(records,i,['std_id','std_evidence']),year=r.get('start_year'))
  if r.get('dup_exact_first_flag')!='0' and cid in N and pid in N:groups[(cid,pid)].append(r)
  for col,kind,label in [('partner_org_codes','partner','협력기관 유형 추출'),('target_explicit','target','대상 명시'),('resource_explicit','resource','자원 명시')]:
   for code in codes(r.get(col)):
    nid=maps.get(kind,{}).get(code)
    if nid:edge(rid,nid,label,'derived',source=ref(records,i,[col]),year=r.get('start_year'))
  for col,code in [('op_always','ALW'),('op_regular','REG'),('op_event','EVT'),('op_adhoc','ADH'),('op_seasonal','SEA')]:
   if r.get(col)=='Y' and code in maps.get('mode',{}):edge(rid,maps['mode'][code],'운영 특성 분류','derived',source=ref(records,i,[col]),year=r.get('start_year'))
 for (cid,pid),rs in groups.items():
  dates=[r['start_date'] for r in rs if r.get('start_date')];attrs={'기록수':len(rs),'연도별기록수':dict(collections.Counter(r.get('start_date','')[:4] for r in rs)),'기간':min(dates)+' ~ '+max(dates) if dates else '', '주민대상기록수':sum(r.get('in_resident_scope')=='1' for r in rs),'집계':'동일 레코드 대표행만 집계. 프로그램 분류는 자동 구조화 결과이며 고유 이용자 수 아님.'}
  edge(cid,pid,'분류된 운영 이력','derived',attrs,ref(records,note='group complex_id+std_id, dup_exact_first_flag != 0'),weight=len(rs))
 profiles='model/outputs/m1_complex_profile.csv'
 for i,r in enumerate(read(profiles),2):
  cid='complex:'+r['complex_id']
  if cid in N:N[cid]['attrs']['모델 프로파일']=r
  for k in NEEDS:edge(cid,'domain:'+k,'필요 지표 추정','estimated',pick(r,[f'need_{k}',f'need_lo_{k}',f'need_hi_{k}',f'supply_share_{k}',f'gap_{k}']),ref(profiles,i,note='proxy-derived model profile, not measured unmet demand'),weight=num(r.get('need_'+k)))
 peers='model/outputs/m2_complex_peers.csv'
 for i,r in enumerate(read(peers),2):
  edge('complex:'+r['complex_id'],'complex:'+r['peer_id'],{'hybrid':'혼합 유사 단지','struct':'구성이 닮은 단지','geo':'가까운 단지'}.get(r['kind'],r['kind']),'similarity',r,ref(peers,i),weight=num(r.get('similarity')))
 requirements='model/outputs/m4_program_requirements.csv'
 for i,r in enumerate(read(requirements),2):
  pid='program:'+r['std_id']
  if pid in N:N[pid]['attrs']['실행 조건 추정']=r
  for col,value in r.items():
   if col.startswith(('res_','og_')) and num(value)>=.05:
    code=col.split('_',1)[1];kind='resource' if col.startswith('res_') else 'partner';nid=maps.get(kind,{}).get(code)
    if nid:edge(pid,nid,'기록에서 확인한 자원' if kind=='resource' else '협력 유형 이력','derived',{'기록비율':num(value),'해석':'이력이 있는 비율이며 필수 요건 또는 실제 가용성 확정이 아님'},ref(requirements,i,[col]),weight=num(value))
 cases='data/processed/casebook_programs_v1/cases.csv'
 for i,r in enumerate(read(cases),2):node('case:'+r['case_id'],'case',r['program_title'],{k:v for k,v in r.items() if k!='text_masked'},ref(cases,i,note='사례집 기술값. 효과 일반화 금지'))
 links='data/processed/casebook_programs_v1/links/case_complex.csv'
 for i,r in enumerate(read(links),2):
  if r.get('needs_review')=='0':edge('case:'+r['case_id'],'complex:'+r['complex_id'],'사례집의 단지','observed',r,ref(links,i))
 cards='data/processed/casebook_programs_v1/evidence_cards.csv'
 for i,r in enumerate(read(cards),2):
  card='card:'+r['card_id'];node(card,'card',r['headline'],r,ref(cards,i));edge('case:'+r['case_id'],card,'실행 레시피','observed',source=ref(cards,i))
  edge(card,'program:'+r['std_id'],'표준 프로그램 연결','derived',{'confidence':r['std_confidence']},ref(cards,i,['std_id']))
 obstacles='data/processed/casebook_programs_v1/case_obstacles.csv'
 for i,r in enumerate(read(obstacles),2):
  oid='obstacle:'+r['obstacle_id'];node(oid,'obstacle',r['obstacle_category']+' · '+r['obstacle'][:38],r,ref(obstacles,i));edge('case:'+r['case_id'],oid,'경험한 걸림돌','observed',source=ref(obstacles,i))
 elements='data/processed/casebook_programs_v1/case_elements.csv'
 for i,r in enumerate(read(elements),2):
  case='case:'+r['case_id']
  if case in N:N[case]['attrs'].setdefault('실행 요소',[]).append(r)
 news='data/processed/housing_welfare_news_v1/articles.csv'
 for i,r in enumerate(read(news),2):node('news:'+r['news_id'],'news',r.get('title_masked') or r['title'],pick(r,['news_id','date','title_masked','outlet','url','is_representative','reuse_policy','reuse_status_raw']),ref(news,i,note='뉴스 본문 미노출: 제목과 원문 링크만 제공'))
 for fname,target,relation in [('article_program','program','보도된 프로그램'),('article_complex','complex','기사의 단지'),('article_org','organization','기사 언급 기관')]:
  rel='data/processed/housing_welfare_news_v1/links/'+fname+'.csv'
  for i,r in enumerate(read(rel),2):
   if r.get('needs_review')=='1':continue
   if target=='organization':nid='organization:'+r['org_name'];node(nid,'organization',r['org_name'],{},ref(rel,i))
   else:nid=target+':'+r['std_id' if target=='program' else 'complex_id']
   status='tentative' if r.get('confidence')=='low' else 'derived' if target=='program' else 'observed'
   edge('news:'+r['news_id'],nid,relation,status,r,ref(rel,i))
 survey='data/processed/happycall_2025_v1/service_demand.csv';node('source:happycall','source','2025 해피콜 조사',{'주의':'전국·응답자 집계는 단지별 수요 정답이 아님. 복수응답 비율을 합해 100%로 만들지 않음.'})
 for i,r in enumerate(read(survey),2):
  sid='survey:'+r['record_id'];node(sid,'survey',f"{r['group']} · {r['metric']} {r['value']}%",r,ref(survey,i));edge('source:happycall',sid,'집계 수요 응답','observed',source=ref(survey,i))
  mapping={'주거환경 개선':'N4','경제적 지원':'N2','문화생활':'N5','일자리':'N6','이웃 소통':'N1','신체건강':'N3','돌봄':'N1','정신건강':'N3','생계':'N2','문화':'N5','의료':'N3','주거':'N4','교육 취업':'N6'}
  if r['metric'] in mapping:edge(sid,'domain:'+mapping[r['metric']],'수요 문항 분야 대응','defined',{'범위':r['scope'],'주의':'전국·응답자 구분 집계. 단지 수요 추정 아님.'},ref(survey,i,['metric','scope']))
 voc='data/processed/happycall_2025_v1/voc.csv'
 for i,r in enumerate(read(voc),2):
  vid='voc:'+r['record_id'];node(vid,'voc',r['text'][:75],r,ref(voc,i));edge('source:happycall',vid,'주민 의견','observed',source=ref(voc,i))
 office='data/processed/happycall_2025_v1/management_scores.csv';office_ids={}
 for i,r in enumerate(read(office),2):
  oid='office:'+r['record_id'];office_ids[r['source_name']]=oid;node(oid,'office',r['source_name'],r,ref(office,i))
 office_map='data/processed/complex_keys_20261117_v1/happycall_office_map_confirmed.csv'
 for i,r in enumerate(read(office_map),2):
  if r.get('match_type') in ['exact','confirmed_name_variant','confirmed_shared_office']:
   edge('complex:'+r['complex_id'],office_ids.get(r['source_name'],''),'관리소 조사 연결','observed',{'match_type':r['match_type'],'공유관리소':r.get('complexes_for_office'),'주의':'공유관리소는 점수를 단지에 복제하지 않음. 전체 사례수는 복지항목 분모가 아님.'},ref(office_map,i))
 recommendations='model/outputs/recommendations_detail.jsonl';raw=(ROOT/recommendations).read_bytes();sources[recommendations]={'file':recommendations,'sha256':hashlib.sha256(raw).hexdigest(),'rows':0}
 for i,line in enumerate(raw.decode('utf-8-sig').splitlines(),1):
  if not line:continue
  r=json.loads(line);sources[recommendations]['rows']+=1;rid='recommendation:'+r['complex_id']+':'+r['std_id'];node(rid,'recommendation',f"{r['complex']} · {r['name']} ({r['rank']}위)",r,ref(recommendations,i,note='model candidate, not executed program'))
  edge('complex:'+r['complex_id'],rid,'검토 후보','estimated',{'rank':r['rank'],'score':r['score']},ref(recommendations,i),weight=r['score']);edge(rid,'program:'+r['std_id'],'후보 프로그램','estimated',source=ref(recommendations,i))
  for rkey,prefix in [('peer_records','record'),('casebook','card'),('news','news')]:
   for e in r['evidence'].get(rkey,[]):
    key=e.get({'record':'record_id','card':'card_id','news':'news_id'}[prefix])
    if key and prefix+':'+key in N:edge(rid,prefix+':'+key,'추천에 사용한 근거','derived',{'근거종류':rkey},ref(recommendations,i),year=e.get('month','')[:4] if prefix=='record' else None)
 monthly='data/processed/complex_integrated_20261117_v1/data/home_doctor_monthly.csv'
 for r in read(monthly):series.setdefault('complex:'+r['complex_id'],[]).append(pick(r,['기간','지원내용총건수','대상세대(인원수)','지원합계대조차이']))
 HERE.joinpath('data').mkdir(exist_ok=True);temp=HERE/'data/knowledge.next.sqlite';temp.unlink(missing_ok=True)
 db=sqlite3.connect(temp);db.executescript('''CREATE TABLE nodes(id TEXT PRIMARY KEY,kind TEXT,label TEXT,attrs TEXT,source TEXT);CREATE TABLE edges(id TEXT PRIMARY KEY,src TEXT,dst TEXT,rel TEXT,status TEXT,weight REAL,year TEXT,attrs TEXT,source TEXT);CREATE TABLE aliases(alias TEXT,node TEXT);CREATE TABLE series(node TEXT PRIMARY KEY,data TEXT);CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);''')
 db.executemany('INSERT INTO nodes VALUES(?,?,?,?,?)',[(n['id'],n['kind'],n['label'],dump(n['attrs']),dump(n['source'])) for n in N.values()]);db.executemany('INSERT INTO edges VALUES(?,?,?,?,?,?,?,?,?)',[(e['id'],e['source'],e['target'],e['rel'],e['status'],e['weight'],e['year'],dump(e['attrs']),dump(e['provenance'])) for e in E.values()]);db.executemany('INSERT INTO aliases VALUES(?,?)',sorted(set(aliases)));db.executemany('INSERT INTO series VALUES(?,?)',[(k,dump(v)) for k,v in series.items()])
 db.executescript('CREATE INDEX edges_src ON edges(src);CREATE INDEX edges_dst ON edges(dst);CREATE INDEX edges_status ON edges(status);CREATE INDEX nodes_kind ON nodes(kind);CREATE INDEX aliases_node ON aliases(node);')
 stats={'built_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'nodes':len(N),'edges':len(E),'node_types':dict(collections.Counter(n['kind'] for n in N.values())),'edge_types':dict(collections.Counter(e['rel'] for e in E.values())),'statuses':dict(collections.Counter(e['status'] for e in E.values())),'type_labels':TYPE_LABELS,'sources':list(sources.values()),'rejected_links':len(rejected),'alias_count':len(set(aliases))}
 db.execute('INSERT INTO meta VALUES(?,?)',('stats',dump(stats)));db.commit();assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close();os.replace(temp,HERE/'data/knowledge.sqlite')
 (HERE/'data/manifest.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8');(HERE/'data/unlinked.json').write_text(json.dumps(rejected,ensure_ascii=False,indent=2),encoding='utf-8');print(dump({k:stats[k] for k in ['nodes','edges','node_types','rejected_links']}))

if __name__=='__main__':build()
