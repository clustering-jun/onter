"""Package release with original-issue closure, contracts, database and checks."""
from pathlib import Path
import json,csv,sqlite3,hashlib,re,shutil
from collections import Counter
ROOT=Path(r'C:\Users\user\Desktop\2026 DRIVE\project');B=ROOT.parent/'전문가 지식자료/주요사업_결과보고서_정제';OLD=ROOT/'data/processed/happycall_2025_v1'
if (B/'source_archive/manifest.json').exists():OLD=B/'source_archive'
def read(n,base=B):return [json.loads(l) for l in (base/(n+'.jsonl')).read_text(encoding='utf-8').splitlines()]
def save(n,rs):
 (B/(n+'.jsonl')).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rs),encoding='utf-8')
 if rs:
  with (B/(n+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
   w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rs for k in r)));w.writeheader()
   for r in rs:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})
facts=read('statistics_clean')
for r in facts:
 if len(r['dimensions'])==2 and r['dimensions'][0]==r['dimensions'][1]:r['dimensions']=r['dimensions'][:1]
 if '관리소별 주요점수' in r['source_title'] and any(d.endswith('지사') for d in r['dimensions']):r['scope']='branch'
save('statistics_clean',facts)
inv={r['table_id']:r for r in read('table_inventory')};audit=read('numeric_sequence_audit');assert all(r['numeric_sequence_crosscheck'] for r in audit)
assert not read('spatial_review')
closures=[]
for r in read('statistics_long',OLD):
 if not r['row_crosscheck_passed']:
  closures.append({'old_record_id':r['record_id'],'pdf_page':r['pdf_page'],'old_issue':'row_mismatch','resolution':'rebuilt_header_spans_and_sample_anchors; discarded_annotation_fragments','replacement_table_id':r['table_id'],'numeric_rows_rechecked':all(x['numeric_sequence_crosscheck'] for x in audit if x['table_id']==r['table_id']),'status':'closed'})
for r in read('extraction_issues',OLD):
 kind=inv[r['table_id']]['kind']
 closures.append({'old_record_id':r['table_id'],'pdf_page':r['pdf_page'],'old_issue':'numeric_token_difference_in_detected_table','resolution':'chart_geometry_fragments_not_statistical_cells; retain_complete_page_tokens' if kind=='non_sample_table_or_graph_fragment' else 'reconstructed_statistical_cells','replacement_table_id':r['table_id'],'status':'closed'})
save('v1_issue_closure',closures)
# Response codebook as printed; direction of means is a separate derived audit.
codebook=[]
for r in facts:
 m=re.search(r'(.+?)\s*\((\d+)점\)',r['metric'])
 if m and not any(x['table_id']==r['table_id'] and x['response_label']==m.group(1).strip() for x in codebook):
  codebook.append({'pdf_page':r['pdf_page'],'table_id':r['table_id'],'question_context':r['source_title'],'response_label':m.group(1).strip(),'printed_response_code':int(m.group(2)),'mean_direction':'see scoring_direction_audit; do not automatically reuse printed code for reported mean'})
save('response_codebook',codebook)
anomalies=json.loads((B/'source_anomalies.json').read_text(encoding='utf-8'))
save('scoring_direction_audit',anomalies)
# Page-level annotation and complete numeric tokens, without grid clipping.
charttokens=[];cells=read('table_cells',OLD);cm={(c['table_id'],c['row_index'],c['column_index']):c for c in cells};chartseries=[]
pages={p['pdf_page']:p for p in read('pages',OLD)}
for pi,p in pages.items():
 for ni,w in enumerate(p['words']):
  raw=w['text'];m=re.fullmatch(r'([▲▼]?)(-?(?:\d+(?:\.\d+)?|\.\d+))(%p|%)?',raw)
  if m:charttokens.append({'document_id':p['document_id'],'pdf_page':pi,'token_id':f'p{pi}:n{ni}','raw':raw,'value':float(m.group(2))*(-1 if m.group(1)=='▼' else 1),'unit_explicit':m.group(3),'bbox':[w['x0'],w['top'],w['x1'],w['bottom']],'role':'page_numeric_token_not_automatically_a_statistic'})
for t in read('tables',OLD):
 pi=t['pdf_page'];p=pages[pi]
 if pi in [7,8] or any(c and '사례수' in c for row in t['rows'][:2] for c in row):continue
 for ri,row in enumerate(t['rows']):
  if not row or row[0]!='구분' or len([x for x in row if x])<4:continue
  for ci,label in enumerate(row[1:],1):
   if not label:continue
   c=cm.get((t['table_id'],ri,ci));box=c['bbox'] if c else None
   if not box:continue
   ws=[w for w in p['words'] if 170<=w['top']<box[1]-5 and box[0]<=(w['x0']+w['x1'])/2<box[2] and re.fullmatch(r'\d{1,3}\.\d',w['text'])]
   ws.sort(key=lambda w:w['x0'])
   if len(ws)==2:
    for j,w in enumerate(ws):chartseries.append({'pdf_page':pi,'table_id':t['table_id'],'metric':re.sub(r'\s+',' ',label),'bar_position':'left' if j==0 else 'right','value':float(w['text']),'raw':w['text'],'bbox':[w['x0'],w['top'],w['x1'],w['bottom']],'unit':'score_100','period':None,'period_policy':'position_preserved_no_unverified_year_assignment','category_link_method':'header_column_geometry'})
for r in chartseries:
 text=re.sub(r'\s+','',pages[r['pdf_page']]['text'])
 assert '24년' in text and '25년' in text,r
 r['period']=2024 if r['bar_position']=='left' else 2025
 r['period_policy']='source_24년_25년_legend_and_left_right_bar_order; visually_checked_template_pages_18_84'
 r['metric_context']=pages[r['pdf_page']]['title']
save('page_numeric_tokens',charttokens);save('chart_bar_observations',chartseries)
trend=[{'pdf_page':11,'metric':'종합만족도','period':y,'wave':wave,'value':v,'n':n,'unit':'score_100','comparability_note':'2023 question changes; 2024 business types added'} for y,wave,v,n in [(2021,None,70.3,3330),(2022,1,73.5,5129),(2022,2,72.8,966),(2023,None,77.6,6625),(2024,None,77.6,6012),(2025,None,78.6,8721)]]
save('overall_satisfaction_trend',trend)
# Clean original core facts and join resolved entities, without expanding consolidated scores.
links={x['record_id']:x for x in read('entity_resolution')};management=[]
for r in read('management_scores'):
 e=links[r['record_id']]
 r.update(entity_id=e['entity_id'],entity_type=e['entity_type'],master_name=e['master_name'],eligible_for_complex_join=e['eligible_for_complex_join'],review_status='source_row_verified_identity_resolved')
 management.append(r)
save('management_scores',management)
assert len(management)==319 and sum(r['n_total'] for r in management)==8721
assert len(set(e['entity_id'] for e in links.values()))==319
assert sum(e['entity_type']=='consolidated_management_office' for e in links.values())==4
assert all(e['eligible_for_complex_join']==(e['entity_type']=='complex') for e in links.values())
for r in facts:
 assert r['metric'].strip(),r
 assert r['unit'] in ['rank','count','percentage_point','score_point','percent','score_100','score_3','score_4','score_source_scale']
 if r['value'] is not None and r['unit'] in ['score_100','percent']:assert 0<=r['value']<=100,r
 if r['unit']=='score_3' and r['value'] is not None:assert 0<=r['value']<=3,r
assert all(r['resolution']!='needs_source_review' for r in anomalies),anomalies
db=B/'onter_happycall.sqlite'
if db.exists():db.unlink()
con=sqlite3.connect(db)
names=['statistics_clean','management_scores','service_demand','voc','survey_questions','ipa_scores','voc_aggregates','entity_resolution','response_codebook','scoring_direction_audit','v1_issue_closure','chart_bar_observations','page_numeric_tokens','overall_satisfaction_trend']
schemas={}
for name in names:
 rs=read(name)
 con.execute(f'CREATE TABLE {name}(id INTEGER PRIMARY KEY,data TEXT NOT NULL CHECK(json_valid(data)))')
 con.executemany(f'INSERT INTO {name}(data) VALUES(?)',[(json.dumps(r,ensure_ascii=False),) for r in rs])
 if rs:
  properties={}
  for k in set(k for r in rs for k in r):
   def typ(v):return 'null' if v is None else 'boolean' if isinstance(v,bool) else 'integer' if isinstance(v,int) else 'number' if isinstance(v,float) else 'array' if isinstance(v,list) else 'object' if isinstance(v,dict) else 'string'
   properties[k]={'type':sorted(set(typ(r.get(k)) for r in rs))}
  schemas[name]={'type':'object','properties':properties,'required':list(set.intersection(*(set(r) for r in rs))),'additionalProperties':False}
con.execute('CREATE VIRTUAL TABLE evidence_fts USING fts5(chunk_id UNINDEXED,pdf_page UNINDEXED,title,text,tokenize="trigram")')
con.executemany('INSERT INTO evidence_fts VALUES(?,?,?,?)',[(r['chunk_id'],r['pdf_page'],r['title'],r['text']) for r in read('evidence_chunks')])
for name,fields in [('statistics_clean',['pdf_page','table_id','scope','dimensions','n_row','metric','value','raw','unit','numeric_sequence_crosscheck']),('management_scores',['source_name','entity_id','entity_type','master_name','n_total','welfare_satisfaction','pdf_page']),('service_demand',['scope','population','group','subgroup','metric','value','n','pdf_page'])]:
 col=','.join("json_extract(data,'$."+k+"') AS \""+k+'"' for k in fields)
 con.execute(f'CREATE VIEW v_{name} AS SELECT {col} FROM {name}')
con.execute("CREATE VIEW v_complex_management_scores AS SELECT * FROM v_management_scores WHERE entity_type='complex'")
assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert con.execute('SELECT COUNT(*) FROM v_complex_management_scores').fetchone()[0]==315
con.commit();con.close()
(B/'record_schemas.json').write_text(json.dumps({'$schema':'https://json-schema.org/draft/2020-12/schema','$defs':schemas},ensure_ascii=False,indent=2),encoding='utf-8')
report=json.loads((B/'validation.json').read_text(encoding='utf-8'))
report.update(dataset_version='2.0.0',v1_85_record_issues_closed=85,v1_42_table_fragment_issues_classified=42,source_scoring_orientation_notes=len(anomalies),unresolved_source_values=0,entity_identity_confirmations_pending=0,chart_bar_observations=len(chartseries),page_numeric_tokens=len(charttokens),schema_validation='field_types_generated_from_release_records',user_confirmations={'consolidated_offices':'keep_four_separate_no_replication','ambiguous_13_aliases':'all_confirmed_same_complex'},warnings=['Reported means and printed response codes are distinct; inferred reverse coding is documented.','Graph observations overlap table statistics; do not add together.'])
(B/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
original_manifest=json.loads((OLD/'manifest.json').read_text(encoding='utf-8'))
archive=B/'source_archive';archive.mkdir(exist_ok=True)
for name in ['management_scores','service_demand','voc','survey_questions','evidence_chunks','definitions_and_cautions']:
 if OLD.resolve()!=archive.resolve():shutil.copy2(OLD/(name+'.jsonl'),archive/(name+'.jsonl'))
master_path=Path(original_manifest['source_master_path'])
if master_path.resolve()!=(archive/'master_complex_input.csv').resolve():shutil.copy2(master_path,archive/'master_complex_input.csv')
original_manifest['source_master_path']=str(archive/'master_complex_input.csv')
original_manifest['source_path']=str(B/'원문_주요사업 결과보고서.pdf')
(archive/'manifest.json').write_text(json.dumps(original_manifest,ensure_ascii=False,indent=2),encoding='utf-8')
code=B/'재실행도구';code.mkdir(exist_ok=True)
for name in ['refine_happycall.py','audit_happycall_v2.py','package_happycall_v2.py']:shutil.copy2(ROOT/'tools'/name,code/name)
(B/'file_checksums.json').write_text(json.dumps({str(f.relative_to(B)):hashlib.sha256(f.read_bytes()).hexdigest() for f in B.rglob('*') if f.is_file() and f.name!='file_checksums.json'},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
