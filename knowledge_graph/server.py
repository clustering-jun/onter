"""Local, read-only graph explorer. Does not call Ollama or import model code."""
from pathlib import Path
import sqlite3,json,collections,urllib.parse,http.server,argparse,time,threading,mimetypes
from contextlib import closing
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;WEB=HERE/'web';DB=HERE/'data/knowledge.sqlite'
STATUSES=['observed','defined','derived','estimated','similarity'];LLM_CACHE={'time':0,'rows':{}}
def conn():
 d=sqlite3.connect('file:'+DB.as_posix()+'?mode=ro',uri=True);d.row_factory=sqlite3.Row;return d
def nobj(r):return {'id':r['id'],'kind':r['kind'],'label':r['label'],'attrs':json.loads(r['attrs']),'source':json.loads(r['source'])}
def eobj(r):return {'id':r['id'],'source':r['src'],'target':r['dst'],'rel':r['rel'],'status':r['status'],'weight':r['weight'],'year':r['year'],'attrs':json.loads(r['attrs']),'provenance':json.loads(r['source'])}
def nodes(db,ids):
 ids=list(dict.fromkeys(ids));return [nobj(r) for r in db.execute('SELECT * FROM nodes WHERE id IN ('+','.join('?' for _ in ids)+')',ids)] if ids else []
def edges_for(db,id):return [eobj(r) for r in db.execute('SELECT * FROM edges WHERE src=? OR dst=?',(id,id))]
def allowed(e,statuses,year):
 if e['status'] not in statuses:return False
 if year and e['rel']=='분류된 운영 이력':
  count=e['attrs'].get('연도별기록수',{}).get(year,0)
  if not count:return False
  e['weight']=count;e['attrs']['현재연도기록수']=count
 if year and e['year'] and not str(e['year']).startswith(year):return False
 return True
def graph(db,id='program:I02',limit=55,statuses=None,year='',mode='focus'):
 statuses=statuses or STATUSES
 if mode=='overview':
  ns=[nobj(r) for r in db.execute("SELECT * FROM nodes WHERE kind IN ('program','domain')")];ids={n['id'] for n in ns}
  es=[eobj(r) for r in db.execute("SELECT * FROM edges WHERE rel='분야와 관련'")];es=[e for e in es if e['source'] in ids and e['target'] in ids and e['status'] in statuses]
  total=len(ns)
  if limit<120:
   domains=[n['id'] for n in ns if n['kind']=='domain'];selected=set(domains);per=8 if limit<=55 else 12
   for did in domains:
    connected={e['source'] for e in es if e['target']==did};programs=sorted([n for n in ns if n['id'] in connected and n['attrs'].get('recommendable')=='1'],key=lambda n:-float(n['attrs'].get('n_records') or 0));selected.update(n['id'] for n in programs[:per])
   ns=[n for n in ns if n['id'] in selected];es=[e for e in es if e['source'] in selected and e['target'] in selected]
  return {'nodes':ns,'edges':es,'center':None,'total_neighbors':total,'truncated':len(ns)<total}
 if not db.execute('SELECT 1 FROM nodes WHERE id=?',(id,)).fetchone():raise ValueError('대상을 찾을 수 없습니다.')
 es=[e for e in edges_for(db,id) if allowed(e,statuses,year)]
 priority={'실행 레시피':0,'표준 프로그램 연결':0,'추천에 사용한 근거':0 if id.startswith('recommendation:') else 7,'후보 프로그램':0 if id.startswith('recommendation:') else 7,'기사의 단지':1,'보도된 프로그램':1,'사례집의 단지':0,'경험한 걸림돌':1,'분야와 관련':2,'통상 필요 자원':3,'협력 유형 이력':3,'분류된 운영 이력':4,'검토 후보':1,'운영 기록':6,'프로그램으로 분류':6,'필요 지표 추정':5}
 es.sort(key=lambda e:(priority.get(e['rel'],4),e['attrs'].get('rank',999) if e['rel']=='검토 후보' else -float(e['weight'] or 0),e['id']))
 chosen=[];seen={id};counts=collections.Counter();quotas={'분류된 운영 이력':18,'운영 기록':8,'프로그램으로 분류':8,'혼합 유사 단지':4,'구성이 닮은 단지':4,'가까운 단지':4}
 if not id.startswith('recommendation:'):quotas.update({'후보 프로그램':5,'추천에 사용한 근거':5})
 for e in es:
  if counts[e['rel']]>=quotas.get(e['rel'],999):continue
  other=e['target'] if e['source']==id else e['source']
  if other not in seen and len(seen)>=limit+1:continue
  seen.add(other);chosen.append(e);counts[e['rel']]+=1
 # Bring case detail behind the recipe and a few sampled records behind programs.
 if id.startswith('program:'):
  for n in nodes(db,seen):
   if n['kind']=='card':
    for e in edges_for(db,n['id']):
     if e['source'].startswith('case:') and e['rel']=='실행 레시피' and allowed(e,statuses,year):seen.add(e['source']);chosen.append(e)
  record_count=sum(x.startswith('record:') for x in seen)
  for r in db.execute("SELECT * FROM edges WHERE dst=? AND rel='프로그램으로 분류' ORDER BY rowid DESC LIMIT 20",(id,)):
   if record_count>=8:break
   e=eobj(r)
   if not allowed(e,statuses,year):continue
   rec=nodes(db,[e['source']])[0]
   if year and not rec['attrs'].get('start_date','').startswith(year):continue
   if rec['id'] in seen:continue
   seen.add(rec['id']);chosen.append(e);record_count+=1
   cid='complex:'+rec['attrs'].get('complex_id','')
   if cid in seen:
    for x in edges_for(db,rec['id']):
     if x['source']==cid and x['rel']=='운영 기록':chosen.append(x)
 ns=nodes(db,seen);valid={n['id'] for n in ns};chosen={e['id']:e for e in chosen if e['source'] in valid and e['target'] in valid}
 return {'nodes':ns,'edges':list(chosen.values()),'center':id,'total_neighbors':len({e['target'] if e['source']==id else e['source'] for e in es}),'truncated':len(es)>len(chosen)}
def evidence(db,id,offset=0,limit=12,kind='',year='',statuses=None):
 n=nodes(db,[id]);
 if not n:return {'items':[],'total':0}
 mode=n[0]['kind'];statuses=statuses or STATUSES;es=[e for e in edges_for(db,id) if e['status'] in statuses];ids=set()
 for e in es:
  if mode=='recommendation' and e['rel']!='추천에 사용한 근거':continue
  other=e['target'] if e['source']==id else e['source']
  if other.split(':')[0] in ['record','card','case','news','obstacle','survey','voc']:ids.add(other)
 if mode=='record':
  for e in es:
   if e['target'].startswith('program:'):
    for x in [x for x in edges_for(db,e['target']) if x['status'] in statuses]:
     other=x['source'] if x['target']==e['target'] else x['target']
     if other.startswith(('card:','news:')):ids.add(other)
 items=nodes(db,ids)
 if kind:items=[n for n in items if n['kind']==kind]
 if year:items=[n for n in items if n['kind']!='record' or n['attrs'].get('start_date','').startswith(year)]
 order={'card':0,'case':1,'obstacle':2,'news':3,'record':4,'survey':5,'voc':6}
 items.sort(key=lambda n:(order.get(n['kind'],9),str(n['attrs'].get('start_date',n['attrs'].get('date','')))),reverse=False)
 if kind=='record':items.sort(key=lambda n:n['attrs'].get('start_date',''),reverse=True)
 return {'items':items[offset:offset+limit],'total':len(items),'offset':offset,'limit':limit,'scope':'동일 유형의 참고 근거' if mode=='record' else '직접 연결된 근거','kinds':dict(collections.Counter(x['kind'] for x in items))}
def llm_status():
 if time.time()-LLM_CACHE['time']<8:return LLM_CACHE
 p=ROOT/'model/outputs/llm/explanations_llm.jsonl';rows={}
 if p.exists():
  with p.open(encoding='utf-8-sig') as f:
   for line in f:
    try:
     r=json.loads(line);rows[r['complex_id']+':'+r['std_id']]=r
    except (json.JSONDecodeError,KeyError):continue
 LLM_CACHE.update(time=time.time(),rows=rows,completed=len(rows),accepted=sum(r.get('source')=='llm' for r in rows.values()),fallback=sum(r.get('source')!='llm' for r in rows.values()),expected=3180,readonly=True)
 return LLM_CACHE
def shortest_path(db,src,dst,statuses,depth=5):
 if not nodes(db,[src]) or not nodes(db,[dst]):raise ValueError('출발점 또는 도착점이 없습니다.')
 queue=collections.deque([(src,0)]);parent={src:None};seen_edges={};stop=False
 while queue and len(parent)<15000:
  x,d=queue.popleft()
  if x==dst:stop=True;break
  if d>=depth:continue
  around=edges_for(db,x);priority={'사례집의 단지':0,'실행 레시피':0,'추천에 사용한 근거':1,'표준 프로그램 연결':2,'분류된 운영 이력':3,'프로그램으로 분류':5,'운영 기록':6}
  around.sort(key=lambda e:priority.get(e['rel'],4))
  for e in around:
   if e['status'] not in statuses or e['rel'] in ['관할 지사','관리소 조사 연결','필요 지표 추정']:continue
   y=e['target'] if e['source']==x else e['source']
   # Avoid paths through generic hubs giving meaningless 'same domain' shortcuts.
   if y.startswith(('family:','domain:','target:','resource:','partner:','organization:','source:')) and y!=dst:continue
   if y not in parent:
    parent[y]=(x,e);queue.append((y,d+1))
    if y==dst:stop=True;queue.clear();break
 if not stop:return {'nodes':nodes(db,[src,dst]),'edges':[],'found':False,'message':'현재 연결 규칙에서 5단계 안의 구체적 근거 경로가 없습니다.'}
 ids=[dst];es=[];cur=dst
 while parent[cur]:cur,e=parent[cur];ids.append(cur);es.append(e)
 return {'nodes':nodes(db,ids),'edges':es,'center':src,'found':True,'message':'관계 경로입니다. 인과관계 또는 효과 검증 경로가 아닙니다.'}
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send_json(self,value,status=200):
  raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  path=urllib.parse.urlsplit(self.path);q={k:v[-1] for k,v in urllib.parse.parse_qs(path.query,keep_blank_values=True).items()};route=path.path
  if route.startswith('/api/'):
   try:
    with closing(conn()) as db:
     id=q.get('id','program:I02');statuses=q.get('statuses',','.join(STATUSES)).split(',');year=q.get('year','');limit=max(5,min(120,int(q.get('limit','55'))))
     if route=='/api/stats':result=json.loads(db.execute("SELECT value FROM meta WHERE key='stats'").fetchone()[0]);result['service']='onter-knowledge-graph'
     elif route=='/api/search':
      query=q.get('q','').strip()[:100];kind=q.get('kind','');sql='SELECT DISTINCT n.* FROM nodes n LEFT JOIN aliases a ON a.node=n.id WHERE (n.label LIKE ? ESCAPE "\\" OR n.id LIKE ? ESCAPE "\\" OR a.alias LIKE ? ESCAPE "\\" OR (n.kind IN ("record","card","case","obstacle","voc","survey") AND n.attrs LIKE ? ESCAPE "\\"))';safe=query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_');params=['%'+safe+'%']*4
      if kind:sql+=' AND n.kind=?';params.append(kind)
      sql+=" ORDER BY CASE n.kind WHEN 'program' THEN 0 WHEN 'complex' THEN 1 WHEN 'card' THEN 2 ELSE 3 END,n.label LIMIT ?";params.append(limit);result={'items':[nobj(r) for r in db.execute(sql,params)]}
     elif route=='/api/graph':result=graph(db,id,limit,statuses,year,q.get('mode','focus'))
     elif route=='/api/node':
      result=nodes(db,[id]);
      if not result:raise ValueError('대상이 없습니다.')
      result=result[0];es=edges_for(db,id);result['relations']=dict(collections.Counter(e['rel'] for e in es));result['neighbor_count']=len({e['target'] if e['source']==id else e['source'] for e in es})
      monthly=db.execute('SELECT data FROM series WHERE node=?',(id,)).fetchone();result['monthly']=json.loads(monthly[0]) if monthly else []
      if id.startswith('recommendation:'):
       llm=llm_status()['rows'].get(id.split(':',1)[1]);result['local_explanation']={k:llm.get(k) for k in ['text','source','attempts']} if llm else None
     elif route=='/api/evidence':result=evidence(db,id,max(0,int(q.get('offset',0))),limit,q.get('kind',''),year,statuses)
     elif route=='/api/path':result=shortest_path(db,q.get('from',''),q.get('to',''),statuses)
     elif route=='/api/llm-status':result={k:v for k,v in llm_status().items() if k not in ['rows','time']}
     else:self.send_json({'error':'없는 경로'},404);return
    self.send_json(result)
   except (ValueError,sqlite3.Error) as e:self.send_json({'error':str(e)},400)
   return
  rel=urllib.parse.unquote(route).lstrip('/') or 'index.html';target=(WEB/rel).resolve()
  if not target.is_relative_to(WEB.resolve()) or not target.is_file():self.send_error(404);return
  raw=target.read_bytes();self.send_response(200);self.send_header('Content-Type',(mimetypes.guess_type(target)[0] or 'application/octet-stream')+('; charset=utf-8' if target.suffix in ['.html','.css','.js'] else ''));self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8767);args=parser.parse_args()
 if not DB.exists():raise SystemExit('먼저 python build_graph.py를 실행하세요.')
 print(f'Onter knowledge graph: http://127.0.0.1:{args.port}',flush=True);http.server.ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
