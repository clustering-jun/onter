"""Second-pass spatial reconstruction and explicit entity resolution."""
from pathlib import Path
import json,csv,re,hashlib,shutil,sqlite3,sys
from collections import Counter
import pdfplumber
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'data/processed/happycall_2025_v1'
OUT=ROOT.parent/'전문가 지식자료/주요사업_결과보고서_정제'
OUT.mkdir(parents=True,exist_ok=True)
if (OUT/'source_archive/manifest.json').exists():OLD=OUT/'source_archive'
def read(n):return [json.loads(l) for l in (OLD/(n+'.jsonl')).read_text(encoding='utf-8').splitlines()]
def clean(x):return re.sub(r'\s+',' ',x or '').strip()
def comp(x):return re.sub(r'\s+','',x or '')
def val(x):
 x=clean(x).replace(',','').replace('%p','').replace('%','').replace('▲','').replace('▼','-')
 return float(x) if re.fullmatch(r'-?(?:\d+(?:\.\d+)?|\.\d+)',x) else None
def save(n,rs):
 (OUT/(n+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rs),encoding='utf-8')
 if rs:
  with (OUT/(n+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
   w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rs for k in r)));w.writeheader()
   for r in rs:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})
manifest=json.loads((OLD/'manifest.json').read_text(encoding='utf-8'));src=Path(manifest['source_path'])
if not src.exists():src=OUT/'원문_주요사업 결과보고서.pdf'
assert hashlib.sha256(src.read_bytes()).hexdigest()==manifest['source_sha256']
pages={p['pdf_page']:p for p in read('pages')};oldtables=read('tables');stats=[];review=[];inventory=[];vocagg=[];ipa=[]
def wtext(words):return clean(' '.join(w['text'] for w in sorted(words,key=lambda w:(round(w['top']/3),w['x0']))))
def unit(label,title):
 if '순위' in label:return 'rank'
 if '빈도' in label or '개수' in label:return 'count'
 if 'GAP' in label:return 'percentage_point' if 'VOC' in title else 'score_point'
 if '중요도' in label:return 'percent'
 if '100점' in label and '평균' in label:return 'score_100'
 if '3점' in label and '평균' in label:return 'score_3'
 if '4점' in label and '평균' in label:return 'score_4'
 if '평균' in label:return 'score_source_scale'
 if any(k in title for k in ['수요','고위험군','기타 문항','소외감','연락','의지 정도','도움 받을','외로움 정도']):return 'percent'
 return 'score_100'
with pdfplumber.open(src) as pdf:
 for pi,page in enumerate(pdf.pages,1):
  if pi%25==0:print('Refined',pi,flush=True)
  words=page.extract_words(x_tolerance=2,y_tolerance=3)
  for ti,t in enumerate(page.find_tables()):
   raw=t.extract(x_tolerance=2,y_tolerance=3)
   if not any(clean(c) for row in raw for c in row):continue
   tid=f"{manifest['document_id']}:p{pi}:t{ti}";title=pages[pi]['title']
   header_n=[]
   for ri,row in enumerate(raw[:3]):
    for ci,c in enumerate(row):
     if clean(c) in ['사례수','(Base)','Base']:
      box=t.rows[ri].cells[ci]
      if box:header_n.append(box)
   if not header_n:
    # Non-sample tables with explicit semantic rows are independently retained.
    if raw and any('중요도' in clean(c) for c in raw[0]):
     for ri,row in enumerate(raw[1:],1):
      if len(row)==3 and val(row[1]) is not None:
       ipa.append({'pdf_page':pi,'table_id':tid,'item':clean(row[0]),'importance_percent':val(row[1]),'satisfaction_score_100':val(row[2]),'raw_row':row,'row_text_crosscheck':comp(''.join(c or '' for c in row)) in comp(pages[pi]['independent_text'])})
    if any('빈도' in clean(c) for row in raw[:2] for c in row) and 'VOC' in pages[pi]['text']:
     group=''
     for ri,row in enumerate(raw[2:],2):
      if len(row)<6:continue
      if clean(row[0]):group=clean(row[0])
      vocagg.append({'pdf_page':pi,'table_id':tid,'category':group,'item':clean(row[1]) if len(row)==7 else group,'overall_count':val(row[-5]),'overall_percent':val(row[-4]),'branch_count':val(row[-3]),'branch_percent':val(row[-2]),'gap_percentage_points':val(row[-1]),'raw_row':row,'gap_basis':'source_printed_rounded_values','row_text_crosscheck':comp(''.join(c or '' for c in row)) in comp(pages[pi]['independent_text'])})
    inventory.append({'table_id':tid,'pdf_page':pi,'kind':'non_sample_table_or_graph_fragment','preserved_in':'source_archive/tables.jsonl'})
    continue
   nb=header_n[0];nx0,nx1=nb[0],nb[2]
   anchors=[w for w in words if nx0<=((w['x0']+w['x1'])/2)<nx1 and w['top']>=nb[3]-1 and (re.fullmatch(r'\([\d,]+\)',w['text']) or w['text']=='-') and w['bottom']<=t.bbox[3]+2]
   if not anchors:continue
   anchors.sort(key=lambda w:w['top']);firsty=anchors[0]['top']
   headercells=[]
   for ri,row in enumerate(raw):
    for ci,c in enumerate(row):
     box=t.rows[ri].cells[ci]
     if not box or box[3]>firsty+1 or box[0]<nx1-1 or not clean(c):continue
     headercells.append((box,clean(c),ri,ci))
   leaves=[h for h in headercells if not any(k[2]>h[2] and k[0][0]>=h[0][0]-1 and k[0][2]<=h[0][2]+1 for k in headercells)]
   leaves.sort(key=lambda h:h[0][0]);seen=set();cols=[]
   for h in leaves:
    key=round(h[0][0],1),round(h[0][2],1)
    if key not in seen:cols.append(h);seen.add(key)
   group=''
   for ai,a in enumerate(anchors):
    yc=(a['top']+a['bottom'])/2
    lo=(anchors[ai-1]['bottom']+a['top'])/2 if ai else a['top']-3
    hi=(a['bottom']+anchors[ai+1]['top'])/2 if ai+1<len(anchors) else min(t.bbox[3],a['bottom']+8)
    rowwords=[w for w in words if lo<=((w['top']+w['bottom'])/2)<hi and t.bbox[0]-1<=w['x0'] and w['x1']<=t.bbox[2]+1]
    # First two source columns contain dimensions; annotation columns occur after them.
    xsplit=t.rows[0].cells[0][2] if t.rows[0].cells[0] else nx0
    # For a merged '구분' header, take actual first data-row dimension boundary.
    dimsboxes=[c for r in t.rows for c in r.cells if c and c[0]<nx0 and c[2]<=nx0 and c[2]>c[0]+8]
    splits=sorted(set(round(c[2],3) for c in dimsboxes if c[2]<nx0-2))
    split=splits[0] if splits else nx0
    g=wtext([w for w in rowwords if (w['x0']+w['x1'])/2<split])
    sub=wtext([w for w in rowwords if split<=(w['x0']+w['x1'])/2<nx0])
    for rr,source_row in enumerate(raw):
     gb=t.rows[rr].cells[0]
     if gb and gb[1]<=yc<gb[3] and clean(source_row[0]):
      g=clean(source_row[0]);break
    if comp(g) in ['지사별','직원친절도','관리소소속','서비스횟수']:g=comp(g)
    for bad in ['인적응대 만족','인적응대','여부에 따른','만족 여부에 따른']:
     g=g.replace(bad,'');sub=sub.replace(bad,'')
    sub=re.sub(r'GAP\s*±\s*[\d.]+','',sub).strip();g=clean(g);sub=clean(sub)
    if g:group=g
    dims=[group,sub] if sub else [group]
    scope='overall' if '전체' in dims else ('management_office' if '관리소별 주요점수' in pages[pi]['text'] else ('branch' if any('지사' in d.replace(' ','') for d in dims) else 'respondent_subgroup'))
    for ci,(box,label,_,_) in enumerate(cols):
     ws=[w for w in rowwords if box[0]<=((w['x0']+w['x1'])/2)<box[2]]
     numeric=[w for w in ws if val(w['text']) is not None or w['text']=='-']
     numeric.sort(key=lambda w:abs((w['top']+w['bottom'])/2-yc))
     chosen=numeric[0]['text'] if numeric else ''
     parents=[h[1] for h in headercells if h[2]<cols[ci][2] and h[0][0]<=box[0]+1 and h[0][2]>=box[2]-1]
     label=re.sub(r'\[단위\s*:\s*점\]','',label).strip()
     origin=next((v for v in oldtables if v['table_id']==tid),None)
     datum={'record_id':f'{tid}:a{ai}:m{ci}','document_id':manifest['document_id'],'pdf_page':pi,'table_id':tid,'source_anchor_bbox':[a['x0'],a['top'],a['x1'],a['bottom']],'metric_bbox':[box[0],lo,box[2],hi],'dimensions':dims,'scope':scope,'n_row':int(a['text'][1:-1].replace(',','')) if a['text']!='-' else None,'n_raw':a['text'],'metric':label,'metric_parent':parents,'value':val(chosen),'raw':chosen,'missing':chosen in ['','-'],'unit':unit(label,title),'source_title':title,'validation':'spatial_reconstruction','eligible_as_training_label':False}
     if len(numeric)>1:review.append({'type':'multiple_values_in_metric_region','record_id':datum['record_id'],'pdf_page':pi,'values':[w['text'] for w in numeric]})
     stats.append(datum)
   inventory.append({'table_id':tid,'pdf_page':pi,'kind':'sample_statistical_table','anchors':len(anchors),'metric_columns':len(cols)})
rows={}
for s in stats:rows.setdefault((s['table_id'],tuple(s['source_anchor_bbox'])),[]).append(s)
rowchecks=[]
for key,rr in rows.items():
 target=rr[0]['n_raw']+''.join(r['raw'] for r in rr)
 ok=comp(target) in comp(pages[rr[0]['pdf_page']]['independent_text'])
 rowchecks.append({'table_id':key[0],'pdf_page':rr[0]['pdf_page'],'dimensions':rr[0]['dimensions'],'n_raw':rr[0]['n_raw'],'target':target,'numeric_sequence_crosscheck':ok})
 for r in rr:r['numeric_sequence_crosscheck']=ok
save('statistics_clean',stats);save('table_inventory',inventory);save('spatial_review',review);save('ipa_scores',ipa);save('voc_aggregates',vocagg);save('numeric_sequence_audit',rowchecks)
# Name aliases are explicit, unique mappings; consolidated offices remain separate entities.
alias={'부산동삼':'부산동삼1','부산금곡주공7단지':'부산금곡7','부산해운대주공1':'부산해운대1','부산당감':'부산당감1','기장교리':'부산기장교리','부산화명율리':'부산율리','칠곡왜관4':'칠곡왜관4휴먼시아','대구태전1':'대구태전휴먼시아1','구미도산':'구미도산휴먼시아','경산백천':'경산백천1','양산대석':'양산대석휴먼시아','밀양가곡':'밀양가곡1','밀양삼문':'밀양삼문휴먼시아','김해구산':'김해구산1','거제장평3':'거제장평','광주하남(영구)':'광주하남1','무안회룡마을':'무안남악회룡마을','여수소호(주택관리공단)':'여수소호','여수문수':'여수문수1','영암용앙1':'영암용앙','영동가마실1':'영동가마실','대전반석4':'반석마을4','아산읍내1':'아산읍내','전주효자4-3단지':'전주효자4-3','정읍상동2·3':'정읍상동2,3','나라키움영등포복합청사':'나라키움영등포복합청사관리소','나라키움남양주복합청사':'나라키움남양주복합청사관리소','오산운암6단지':'오산운암6','분당하얀6단지':'분당하얀6','의정부장암':'의정부장암1','파주운정11휴먼시아':'파주운정11','문산당동1':'문산당동','남양주호평23':'남양주호평','김포장기':'김포장기1','인천논현2':'인천논현휴먼시아2','옹진연평마을정비형공공주택':'옹진연평(마을정비형)','화천신읍(공공실버) 영구임 대':'화천신읍공공실버주택','홍천북방 고령자복지(영구임 대)':'홍천북방(고령자복지)'}
mf=Path(manifest['source_master_path']);master=list(csv.DictReader(mf.open(encoding='cp949')));names={r['단지명']:r for r in master};links=[]
for s in read('management_scores'):
 name=s['source_name'];target=name if name in names else alias.get(name)
 agg='통합' in name
 assert agg or target in names,name
 confirmed={'부산동삼','부산당감','경산백천','밀양가곡','김해구산','광주하남(영구)','여수문수','영암용앙1','영동가마실1','아산읍내1','의정부장암','문산당동1','김포장기'}
 links.append({'source_name':name,'branch':s['branch'],'entity_id':('office_group_' if agg else 'onter_complex_')+hashlib.sha256((name if agg else target).encode()).hexdigest()[:16],'entity_type':'consolidated_management_office' if agg else 'complex','master_name':target,'source_master_village':names[target]['마을명'] if target else None,'source_master_address':names[target]['기본주소'] if target else None,'resolution_method':'user_confirmed_keep_consolidated' if agg else ('exact_name' if target==name else ('user_confirmed_alias' if name in confirmed else 'explicit_alias_master_name_village_type_correspondence')),'alias_needs_identity_confirmation':False,'eligible_for_complex_join':not agg,'record_id':s['record_id'],'pdf_page':s['pdf_page'],'individual_scores_not_duplicated':True})
save('entity_resolution',links)
archive=OUT/'source_archive';archive.mkdir(exist_ok=True)
for n in ['pages','tables','table_cells','numeric_table_candidates','extraction_issues','statistics_long']:
 if OLD.resolve()!=archive.resolve():shutil.copy2(OLD/(n+'.jsonl'),archive/(n+'.jsonl'))
for n in ['management_scores','service_demand','voc','survey_questions','evidence_chunks','definitions_and_cautions']:
 rs=read(n);save(n,rs)
if src.resolve()!=(OUT/'원문_주요사업 결과보고서.pdf').resolve():shutil.copy2(src,OUT/'원문_주요사업 결과보고서.pdf')
audit={'source_sha256':manifest['source_sha256'],'source_path':str(src),'source_pages':201,'sample_statistics':len(stats),'sample_tables':sum(x['kind']=='sample_statistical_table' for x in inventory),'ipa_scores':len(ipa),'voc_aggregates':len(vocagg),'spatial_conflicts':len(review),'numeric_rows':len(rowchecks),'numeric_row_mismatches':sum(not x['numeric_sequence_crosscheck'] for x in rowchecks),'entity_counts':dict(Counter(x['entity_type'] for x in links)),'alias_confirmations_needed':sum(x['alias_needs_identity_confirmation'] for x in links)}
(OUT/'validation.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(audit,ensure_ascii=False))
