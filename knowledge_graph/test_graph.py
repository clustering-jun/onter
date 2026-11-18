"""Semantic and API regression checks. Only reads source datasets."""
from pathlib import Path
from contextlib import closing
import unittest,json,hashlib,csv,urllib.request,urllib.error
import server
class GraphTests(unittest.TestCase):
 def setUp(self):self.db=server.conn()
 def tearDown(self):self.db.close()
 def test_endpoint_integrity(self):
  self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM edges e LEFT JOIN nodes a ON a.id=e.src LEFT JOIN nodes b ON b.id=e.dst WHERE a.id IS NULL OR b.id IS NULL').fetchone()[0],0)
 def test_source_hashes_unchanged(self):
  stats=json.loads(self.db.execute("SELECT value FROM meta WHERE key='stats'").fetchone()[0])
  for src in stats['sources']:self.assertEqual(hashlib.sha256((server.ROOT/src['file']).read_bytes()).hexdigest(),src['sha256'],src['file'])
 def test_no_synthetic_complex_demand(self):
  count=self.db.execute("SELECT count(*) FROM edges e JOIN nodes a ON e.src=a.id JOIN nodes b ON e.dst=b.id WHERE (a.kind='complex' AND b.kind IN ('survey','voc')) OR (b.kind='complex' AND a.kind IN ('survey','voc'))").fetchone()[0]
  self.assertEqual(count,0)
 def test_record_masking_and_news_privacy(self):
  for r in self.db.execute("SELECT kind,attrs FROM nodes WHERE kind IN ('news','record')"):
   a=json.loads(r['attrs']);self.assertNotIn('body_masked',a);self.assertNotIn('body_raw',a);self.assertNotIn('activity_content_raw',a);self.assertNotIn('program_name_raw',a)
 def test_group_count_uses_representatives(self):
  known={r[0].split(':',1)[1] for r in self.db.execute("SELECT id FROM nodes WHERE kind='program'")}
  with (server.ROOT/'data/processed/community_nlp_2026_v1/program_analysis.csv').open(encoding='utf-8-sig',newline='') as f:expected=sum(r['dup_exact_first_flag']!='0' and r['std_id'] in known for r in csv.DictReader(f))
  count=sum(json.loads(r[0])['기록수'] for r in self.db.execute("SELECT attrs FROM edges WHERE rel='분류된 운영 이력'"));self.assertEqual(count,expected)
 def test_recipe_path_and_no_hub_shortcut(self):
  g=server.shortest_path(self.db,'complex:KOH_137','card:CB01_P1',server.STATUSES);self.assertTrue(g['found']);self.assertEqual(len(g['edges']),2);self.assertIn('case:CB01',[n['id'] for n in g['nodes']])
 def test_year_filter_and_confidence(self):
  g=server.graph(self.db,'program:I02',55,server.STATUSES,'2024');self.assertTrue(g['nodes']);self.assertTrue(all(e['status']!='tentative' for e in g['edges']))
  for n in g['nodes']:
   if n['kind']=='record':self.assertTrue(n['attrs']['start_date'].startswith('2024'))
 def test_evidence_is_actual_recipe(self):
  ev=server.evidence(self.db,'program:I02',kind='card');self.assertTrue(ev['total']>=1);self.assertIn('CB01_P1',[n['attrs']['card_id'] for n in ev['items']])
 def test_unlinked_keys_not_guessed(self):
  skipped=json.loads((server.HERE/'data/unlinked.json').read_text(encoding='utf-8'));self.assertEqual(len(skipped),3);self.assertTrue(all(r['target']=='complex:' for r in skipped))
 def test_http_search_filters_and_traversal(self):
  def get(path):return json.load(urllib.request.urlopen('http://127.0.0.1:8767'+path,timeout=10))
  data=get('/api/search?q=%EC%84%B8%ED%83%81&kind=program');self.assertIn('program:I02',[n['id'] for n in data['items']])
  self.assertEqual(len(get('/api/graph?mode=overview&statuses=')['edges']),0)
  with self.assertRaises(urllib.error.HTTPError):get('/%2e%2e/server.py')

if __name__=='__main__':unittest.main(verbosity=2)
