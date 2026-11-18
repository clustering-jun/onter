"""Reproducible, source-preserving Happycall PDF ingestion. No source mutations."""
from pathlib import Path
import csv, json, re, hashlib, sqlite3, sys, difflib
from collections import Counter
import pdfplumber
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'C:\Users\user\Desktop\2026 DRIVE\전문가 자료\주요사업 결과보고서.pdf')
if not SOURCE.exists():
    found=list(ROOT.parent.rglob(SOURCE.name))
    if len(found)!=1:raise RuntimeError('Cannot uniquely locate source PDF')
    SOURCE=found[0]
OUT = ROOT / 'data/processed/happycall_2025_v1'
OUT.mkdir(parents=True, exist_ok=True)
SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
DOC = 'happycall2025_' + SHA[:12]
def clean(s): return re.sub(r'\s+', ' ', s or '').strip()
def num(s):
    s = clean(s).replace(',', '').replace('%', '')
    return float(s) if re.fullmatch(r'-?\d+(\.\d+)?', s) else None
def emit(name, records):
    (OUT/(name+'.jsonl')).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in records),encoding='utf-8')
    if records:
        keys=list(dict.fromkeys(k for x in records for k in x))
        with (OUT/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
            for x in records:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in x.items()})
def tags(text):
    rules={'안부·관계':['고립','외로','소외','안부','독거','연락'], '생활물자':['생계','경제','물품','음식','나눔'], '활동·교류':['문화','교류','소통','공동체','프로그램','행사'], '건강·일상':['건강','의료','돌봄','생활','장애','주거환경'], '정보·연계':['정보','안내','공지','기관','연계','상담']}
    return [k for k,v in rules.items() if any(t in text for t in v)]
pages=[];tables=[];cells=[];chunks=[];scores=[];demands=[];voc=[];questions=[];candidates=[];issues=[]
reader=PdfReader(SOURCE)
metrics=['overall_satisfaction','overall_rank','branch_rank','pcsi','major_service_satisfaction','welfare_satisfaction','housing_management_satisfaction','rental_operation_satisfaction','municipal_housing_satisfaction']
with pdfplumber.open(SOURCE) as pdf:
    for pi,p in enumerate(pdf.pages,1):
        text=p.extract_text(x_tolerance=2,y_tolerance=3) or ''
        independent=reader.pages[pi-1].extract_text() or ''
        words=p.extract_words(x_tolerance=2,y_tolerance=3)
        title=next((clean(s) for s in text.splitlines() if re.match(r'^\d+\.',s.strip())),clean(text.splitlines()[0]) if text else '')
        common={'document_id':DOC,'pdf_page':pi,'printed_page':pi-1 if pi>1 else None,'survey_year':2025}
        nums=[{'raw':w['text'],'value':num(w['text']),'bbox':[w['x0'],w['top'],w['x1'],w['bottom']]} for w in words if num(w['text']) is not None]
        pages.append(dict(common,page_id=f'{DOC}:p{pi}',title=title,text=text,independent_text=independent,words=words,numeric_tokens=nums,width=p.width,height=p.height))
        # Page-local evidence, with overlap only inside the same page; never mix scopes.
        for j,start in enumerate(range(0,len(text),1000)):
            body=text[max(0,start-150):start+1000]
            chunks.append(dict(common,chunk_id=f'{DOC}:p{pi}:c{j}',title=title,text=body,need_tags_suggested=tags(body),tag_method='keyword_rules_unreviewed',scope='page_context_only',eligible_as_training_label=False))
        for ti,t in enumerate(p.find_tables()):
            rows=t.extract(x_tolerance=2,y_tolerance=3)
            if not any(clean(c) for row in rows for c in row):continue
            tid=f'{DOC}:p{pi}:t{ti}'
            tables.append(dict(common,table_id=tid,title=title,bbox=list(t.bbox),rows=rows,status='raw_extraction_requires_semantic_review'))
            for ri,row in enumerate(rows):
                for ci,raw in enumerate(row):
                    bbox=t.rows[ri].cells[ci] if ci<len(t.rows[ri].cells) else None
                    cells.append(dict(common,table_id=tid,row_index=ri,column_index=ci,raw=raw,value=num(raw),cell_kind='merged_or_absent' if raw is None else ('blank' if raw=='' else 'text_or_value'),bbox=list(bbox) if bbox else None))
            if '관리소별 주요점수' in text and len(rows[0])==11:
                branch=''
                for ri,row in enumerate(rows):
                    if len(row)!=11 or not re.fullmatch(r'\(\d+\)',clean(row[1])):continue
                    name=clean(row[0]);n=int(clean(row[1])[1:-1])
                    if name=='전체':continue
                    if '지사' in name:branch=name;continue
                    scores.append(dict(common,record_id=f'{tid}:r{ri}',table_id=tid,source_row=ri,source_name=name,branch=branch,n_total=n,n_welfare=None,small_sample=n<30,**{m:num(v) for m,v in zip(metrics,row[2:])},review_status='geometry_extracted_automatically_crosschecked'))
            if pi in [44,45,46,58,59,60]:
                if len(rows)<3 or not any('사례수' in clean(c) for c in rows[0]):continue
                labels=[clean(c) for c in rows[1][3:]];group=''
                for ri,row in enumerate(rows[2:],2):
                    if len(row)<4 or not re.fullmatch(r'\(\d+\)',clean(row[2])):continue
                    if clean(row[0]):group=clean(row[0])
                    subgroup=clean(row[1]);n=int(clean(row[2])[1:-1])
                    scope='overall' if group=='전체' else ('branch' if ('지사' in group or '지사' in subgroup) else 'respondent_subgroup')
                    for ci,label in enumerate(labels,3):
                        if not label:continue
                        demands.append(dict(common,record_id=f'{tid}:r{ri}:c{ci}',table_id=tid,source_row=ri,source_column=ci,population='social_isolation_service_users' if pi<50 else 'residential_life_support_service_users',scope=scope,group=group,subgroup=subgroup,metric=label,value=num(row[ci]),unit='percent',n=n,multiple_response=True,multiple_response_basis='printed_note' if pi>=58 else 'sum_exceeds_100_inferred',complex_id=None,eligible_as_complex_training_label=False,review_status='geometry_extracted_automatically_crosschecked'))
            if len(rows[0])==2 and any('세부 VOC' in clean(c) for c in rows[0]):
                category=''
                for ri,row in enumerate(rows[1:],1):
                    if len(row)!=2 or not clean(row[1]):continue
                    if clean(row[0]):category=clean(row[0])
                    body=clean(row[1]);m=re.search(r'\((\d+)\)\s*$',body)
                    voc.append(dict(common,record_id=f'{tid}:r{ri}',table_id=tid,source_row=ri,category_raw=category,text=body,frequency_explicit=int(m.group(1)) if m else None,frequency_missing_policy='unknown_not_one',scope='service_group_aggregate',complex_id=None,need_tags_suggested=tags(body),tag_method='keyword_rules_unreviewed',eligible_as_training_label=False))
            if pi in [7,8] and any('세부 평가내용' in clean(c) for c in rows[0]):
                parents=['']*(len(rows[0])-2)
                for ri,row in enumerate(rows[1:],1):
                    if len(row)!=len(rows[0]) or not clean(row[-1]):continue
                    for k,v in enumerate(row[:-2]):
                        if v is not None and clean(v):
                            parents[k]=clean(v)
                            for z in range(k+1,len(parents)):parents[z]=''
                    questions.append(dict(common,record_id=f'{tid}:r{ri}',table_id=tid,source_row=ri,hierarchy=parents.copy(),item=clean(row[-2]),question=clean(row[-1]),response_coding=None,need_tags_suggested=tags(clean(row[-1])),status='source_question_not_new_unmet_need_label'))
            # Preserve every numeric table value with its literal column/header context.
            first_data=next((ri for ri,row in enumerate(rows) if any(re.fullmatch(r'\([\d,]+\)',clean(c)) for c in row)),None)
            if first_data is not None:
                header=rows[:first_data]
                for ri,row in enumerate(rows[first_data:],first_data):
                    for ci,raw in enumerate(row):
                        value=num(raw)
                        if value is None:continue
                        candidates.append(dict(common,record_id=f'{tid}:r{ri}:c{ci}',table_id=tid,source_row=ri,source_column=ci,row_context=[clean(c) for c in row[:3]],header_context=[clean(h[ci]) for h in header if ci<len(h)],value=value,raw=raw,status='candidate_not_approved_for_model_input',unit=None))
        if pi%25==0:print('Extracted',pi,flush=True)

# Match only literal names. Similarity suggestions never become automatic joins.
mf=next((ROOT/'data/raw').glob('*_임대단지 관리현황_*.csv'))
master=list(csv.DictReader(mf.open(encoding='cp949')))
names={r['단지명']:r for r in master}
links=[]
for s in scores:
    exact=s['source_name'] in names
    links.append({'record_id':s['record_id'],'source_name':s['source_name'],'branch':s['branch'],'master_name':s['source_name'] if exact else None,'match_status':'exact_name_only_requires_identity_check' if exact else 'unresolved','suggestions':difflib.get_close_matches(s['source_name'],list(names),n=3,cutoff=.45) if not exact else [],'canonical_complex_id':None,'approved_join':False})

# Cross-check table numeric strings against a second PDF text extractor for every page.
def tokens(s):return Counter(re.findall(r'(?<!\d)-?\d+(?:\.\d+)?%?',s.replace(',','')))
for t in tables:
    pt=pages[t['pdf_page']-1]; available=tokens(pt['independent_text'])
    demanded=Counter()
    for row in t['rows']:
        for v in row:
            if num(v) is not None:demanded.update(tokens(clean(v)))
    missing=demanded-available
    if missing:issues.append({'pdf_page':t['pdf_page'],'table_id':t['table_id'],'type':'numeric_token_count_difference','details':dict(missing),'status':'review_required'})
checks={'page_count':len(pages),'nonempty_pages':sum(bool(p['text']) for p in pages),'tables':len(tables),'table_cells':len(cells),'score_rows':len(scores),'unique_score_names':len(set(s['source_name'] for s in scores)),'score_n_total_sum':sum(s['n_total'] for s in scores),'score_small_sample_rows':sum(s['small_sample'] for s in scores),'demand_values':len(demands),'voc_records':len(voc),'question_items':len(questions),'numeric_table_candidates':len(candidates),'evidence_chunks':len(chunks),'cross_extractor_issues':len(issues),'exact_name_links':sum(l['master_name'] is not None for l in links),'unresolved_name_links':sum(l['master_name'] is None for l in links)}
assert checks['page_count']==201
assert checks['score_rows']==319,checks
assert checks['score_n_total_sum']==8721,checks
assert all(v is None or 0<=v<=100 for s in scores for k,v in s.items() if k in metrics and 'rank' not in k)
assert all(d['value'] is None or 0<=d['value']<=100 for d in demands)
for name,data in [('pages',pages),('tables',tables),('table_cells',cells),('management_scores',scores),('service_demand',demands),('voc',voc),('survey_questions',questions),('numeric_table_candidates',candidates),('evidence_chunks',chunks),('complex_link_review',links),('extraction_issues',issues)]:
    emit(name,data)
dbpath=OUT/'onter_happycall.sqlite'
if dbpath.exists():dbpath.unlink()
con=sqlite3.connect(dbpath)
for name,data in [('pages',pages),('tables_raw',tables),('management_scores',scores),('service_demand',demands),('voc',voc),('survey_questions',questions),('numeric_table_candidates',candidates),('complex_link_review',links)]:
    con.execute(f'CREATE TABLE {name} (id INTEGER PRIMARY KEY, data TEXT NOT NULL CHECK(json_valid(data)))')
    con.executemany(f'INSERT INTO {name}(data) VALUES(?)',[(json.dumps(d,ensure_ascii=False),) for d in data])
con.execute('CREATE VIRTUAL TABLE evidence_fts USING fts5(chunk_id UNINDEXED,pdf_page UNINDEXED,title,text,tokenize="trigram")')
con.executemany('INSERT INTO evidence_fts VALUES(?,?,?,?)',[(c['chunk_id'],c['pdf_page'],c['title'],c['text']) for c in chunks])
con.execute('CREATE VIEW v_management_scores AS SELECT json_extract(data,\'$.source_name\') source_name,json_extract(data,\'$.branch\') branch,json_extract(data,\'$.n_total\') n_total,json_extract(data,\'$.welfare_satisfaction\') welfare_satisfaction,json_extract(data,\'$.pdf_page\') pdf_page FROM management_scores')
con.commit();assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok';con.close()
manifest={'document_id':DOC,'source_path':str(SOURCE),'source_sha256':SHA,'survey_period':['2025-10-15','2025-11-12'],'source_population':'service_users_not_all_residents','dataset_version':'1.0.0','checks':checks,'validation_scope':'all_pages_extracted; numeric_table_tokens_crosschecked_with_pypdf; selected_visual_review; candidate_tables_not_semantically_validated','training_label_policy':'Neither satisfaction nor aggregate demand is a complex-level unmet-need or program-effect label.','source_master_path':str(mf)}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,ensure_ascii=False,indent=2))
