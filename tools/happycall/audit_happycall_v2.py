from pathlib import Path
import json,sys,subprocess,tempfile,shutil,os
ROOT=Path(__file__).resolve().parents[2];B=ROOT.parent/'전문가 지식자료/주요사업_결과보고서_정제'
def read(n):return [json.loads(l) for l in (B/(n+'.jsonl')).read_text(encoding='utf-8').splitlines()]
if '--render' in sys.argv:
 out=B/'원문대조';out.mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory() as td:
  src=Path(td)/'report.pdf';shutil.copy2(B/'원문_주요사업 결과보고서.pdf',src)
  for p in [18,22,30,33,37,39,40,53,60,63,76,84]:
   subprocess.run([os.environ.get('PDFTOPPM') or shutil.which('pdftoppm') or 'pdftoppm','-f',str(p),'-l',str(p),'-singlefile','-scale-to','1800','-png',str(src),str(out/f'page_{p}')],check=True,capture_output=True)
stats=read('statistics_clean');rows={}
for s in stats:rows.setdefault((s['table_id'],tuple(s['source_anchor_bbox'])),[]).append(s)
anomalies=[]
for k,rr in rows.items():
 coded=[];mean=None
 for r in rr:
  import re
  m=re.search(r'\((\d+)점\)',r['metric'])
  if m and r['value'] is not None:coded.append((int(m[1]),r['value']))
  if r['metric']=='[3점 평균]':mean=r
 if len(coded)==4 and mean and mean['value'] is not None:
  derived=sum(a*b for a,b in coded)/100
  if abs(derived-mean['value'])>.02:
   reverse=3-derived
   matches_reverse=abs(reverse-mean['value'])<=.02
   anomalies.append({'pdf_page':mean['pdf_page'],'dimensions':mean['dimensions'],'source_mean':mean['value'],'derived_using_printed_codes':round(derived,4),'derived_using_reverse_codes':round(reverse,4),'kind':'reported_mean_uses_reverse_of_printed_codes' if matches_reverse else 'source_mean_distribution_inconsistency','resolution':'preserve_printed_codes_and_mean_separately; reverse_direction_inferred_by_calculation' if matches_reverse else 'needs_source_review'})
(B/'source_anomalies.json').write_text(json.dumps(anomalies,ensure_ascii=False,indent=2),encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8');print('SCORING ORIENTATION NOTES',len(anomalies));print('NUMERIC FAIL',sum(not r['numeric_sequence_crosscheck'] for r in read('numeric_sequence_audit')))
