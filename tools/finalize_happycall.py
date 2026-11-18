"""Build audit, extended statistics and integration contracts from extracted sources."""
from pathlib import Path
import json,re,csv,sqlite3,hashlib
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
B=ROOT/'data/processed/happycall_2025_v1'
def read(n):return [json.loads(l) for l in (B/(n+'.jsonl')).read_text(encoding='utf-8').splitlines()]
def compact(s):return ''.join((s or '').split())
def clean(s):return re.sub(r'\s+',' ',s or '').strip()
def number(s):
 s=clean(s).replace(',','').replace('%','')
 return float(s) if re.fullmatch(r'-?\d+(\.\d+)?',s) else None
def save(n,rs):
 (B/(n+'.jsonl')).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rs),encoding='utf-8')
 if rs:
  with (B/(n+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rs for k in r)));w.writeheader()
   for r in rs:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()})
pages={p['pdf_page']:p for p in read('pages')};tables={t['table_id']:t for t in read('tables')}
cross=[]
for name in ['management_scores','service_demand','voc','survey_questions']:
 for r in read(name):
  row=tables[r['table_id']]['rows'][r['source_row']]
  ok=''.join(compact(v) for v in row if v is not None) in compact(pages[r['pdf_page']]['independent_text'])
  cross.append({'dataset':name,'record_id':r['record_id'],'pdf_page':r['pdf_page'],'complete_row_exact_in_second_extractor':ok})
assert all(x['complete_row_exact_in_second_extractor'] for x in cross)
save('row_crosschecks',cross)
stats=[];findings=[];definitions=[]
for t in tables.values():
 rows=t['rows'];first=next((ri for ri,row in enumerate(rows) if any(re.fullmatch(r'\([\d,]+\)',clean(c)) for c in row)),None)
 if first is None:continue
 ncol=next(ci for ci,c in enumerate(rows[first]) if re.fullmatch(r'\([\d,]+\)',clean(c)))
 if ncol>3:continue
 headers=rows[:first];group=''
 for ri,row in enumerate(rows[first:],first):
  if ncol>=len(row) or not re.fullmatch(r'\([\d,]+\)',clean(row[ncol])):continue
  n=int(re.sub(r'[^\d]','',row[ncol]));dims=[clean(c) for c in row[:ncol]]
  if dims and dims[0]:group=dims[0]
  if dims and not dims[0]:dims[0]=group
  exact=''.join(compact(v) for v in row if v is not None) in compact(pages[t['pdf_page']]['independent_text'])
  for ci in range(ncol+1,len(row)):
   path=[]
   for h in headers:
    if ci>=len(h):continue
    v=h[ci]
    if v is None:
     for k in range(ci-1,ncol,-1):
      if h[k] is not None:v=h[k];break
    v=clean(v)
    if v and v not in path:path.append(v)
   if not path:continue
   raw=row[ci]
   stats.append({'record_id':f"{t['table_id']}:r{ri}:c{ci}",'document_id':t['document_id'],'pdf_page':t['pdf_page'],'printed_page':t['printed_page'],'survey_year':2025,'table_id':t['table_id'],'source_row':ri,'source_column':ci,'title':t['title'],'dimensions':dims,'n_row':n,'metric_header_path':path,'value':number(raw),'raw':raw,'missing':raw in [None,'','-'],'unit_status':'consult_source_page_note','row_crosscheck_passed':exact,'review_status':'source_row_verified_metric_semantics_pending' if exact else 'quarantined_row_mismatch','eligible_as_training_label':False})
for pi,p in pages.items():
 lines=p['text'].splitlines();buf=[]
 for line in lines+['']:
  if re.match(r'^\s*[●]',line) or not line:
   if buf:
    s=' '.join(buf)
    findings.append({'document_id':p['document_id'],'pdf_page':pi,'title':p['title'],'text':s,'kind':'bullet_started_text_segment_with_following_page_context','interpretation_status':'not_independently_recomputed','eligible_as_training_label':False})
   buf=[line] if line else []
  elif buf:buf.append(line)
 for line in lines:
  if any(k in line for k in ['합산점수','표본수 30','설문문항이 변경','사업유형이 추가','없음, 무응답']):
   definitions.append({'document_id':p['document_id'],'pdf_page':pi,'text':line,'kind':'source_definition_or_caution','coding_status':'requires_original_questionnaire_before_scoring'})
save('statistics_long',stats);save('source_findings',findings);save('definitions_and_cautions',definitions)
con=sqlite3.connect(B/'onter_happycall.sqlite')
for name,rs in [('statistics_long',stats),('source_findings',findings),('definitions_and_cautions',definitions),('row_crosschecks',cross)]:
 con.execute(f'DROP TABLE IF EXISTS {name}')
 con.execute(f'CREATE TABLE {name}(id INTEGER PRIMARY KEY,data TEXT NOT NULL CHECK(json_valid(data)))')
 con.executemany(f'INSERT INTO {name}(data) VALUES(?)',[(json.dumps(x,ensure_ascii=False),) for x in rs])
for view,table,fields in [('v_service_demand','service_demand',['scope','group','subgroup','population','metric','value','unit','n','pdf_page']),('v_voc','voc',['category_raw','text','frequency_explicit','pdf_page']),('v_statistics_long','statistics_long',['title','dimensions','metric_header_path','value','raw','n_row','row_crosscheck_passed','pdf_page'])]:
 con.execute(f'DROP VIEW IF EXISTS {view}')
 fields_sql=','.join("json_extract(data,'$."+k+"') AS \""+k+'"' for k in fields)
 con.execute(f'CREATE VIEW {view} AS SELECT {fields_sql} FROM {table}')
assert con.execute("SELECT COUNT(*) FROM evidence_fts WHERE evidence_fts MATCH '"+'"복지정보"'+"'").fetchone()[0]>0
assert con.execute('SELECT SUM(n_total) FROM v_management_scores').fetchone()[0]==8721
assert con.execute("SELECT value FROM v_service_demand WHERE scope='overall' AND metric='돌봄' AND population='social_isolation_service_users' LIMIT 1").fetchone()[0]==43.6
assert con.execute("SELECT value FROM v_service_demand WHERE scope='overall' AND metric='주거환경 개선' LIMIT 1").fetchone()[0]==47.6
assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
con.commit();con.close()
manifest=json.loads((B/'manifest.json').read_text(encoding='utf-8'))
if not Path(manifest['source_path']).exists():
 found=[p for p in ROOT.parent.rglob(Path(manifest['source_path']).name) if hashlib.sha256(p.read_bytes()).hexdigest()==manifest['source_sha256']]
 if len(found)!=1:raise RuntimeError('Cannot locate identical source PDF')
 manifest['source_original_path']=manifest['source_path']
 manifest['source_path']=str(found[0])
manifest['checks'].update(complete_core_row_crosschecks=len(cross),complete_core_row_crosschecks_failed=0,statistics_long_records=len(stats),statistics_long_row_mismatch=sum(not x['row_crosscheck_passed'] for x in stats),source_findings=len(findings),definition_caution_lines=len(definitions))
manifest['visual_review']={'coverage':'all_201_page_layout_overviews_and_selected_full_resolution_pages','full_resolution_pages':[5,7,43,44,56,57,58,100,199],'limitations':'Overview inspection is not a manual cell-by-cell transcription check. Chart label associations and generic metric semantics remain pending.'}
(B/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
# Machine-readable contracts with actual field inventories; preserve unknowns as null.
contracts={}
for name in ['management_scores','service_demand','voc','survey_questions','statistics_long','complex_link_review']:
 rs=read(name);fields={}
 for k in rs[0]:
  types=sorted(set('null' if r.get(k) is None else 'boolean' if isinstance(r[k],bool) else 'integer' if isinstance(r[k],int) else 'number' if isinstance(r[k],float) else 'array' if isinstance(r[k],list) else 'string' for r in rs))
  fields[k]={'type':types}
 contracts[name]={'type':'object','required':list(rs[0]),'properties':fields,'additionalProperties':False}
(B/'record_schemas.json').write_text(json.dumps({'$schema':'https://json-schema.org/draft/2020-12/schema','$defs':contracts},ensure_ascii=False,indent=2),encoding='utf-8')
(B/'file_checksums.json').write_text(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in B.iterdir() if f.is_file() and f.suffix in ['.jsonl','.csv','.sqlite']},indent=2),encoding='utf-8')
print(json.dumps(manifest['checks'],ensure_ascii=False,indent=2))

if '--render-audit' in __import__('sys').argv:
 import subprocess,shutil,tempfile
 out=B/'audit_pages';out.mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='onter_pdf_') as td:
  tmp=Path(td)/'source.pdf';shutil.copyfile(Path(manifest['source_path']),tmp)
  exe=Path(r'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe')
  for page in [7,44,56,58,100]:
   subprocess.run([str(exe),'-f',str(page),'-l',str(page),'-singlefile','-scale-to','1700','-png',str(tmp),str(out/f'page_{page}')],check=True,capture_output=True)
