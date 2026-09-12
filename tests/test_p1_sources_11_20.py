import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from qiuzhao.collector.p1_sources_11_20 import collect,_mihoyo
class FakeFetcher:
 def api(self,url,name,payload):
  typ=payload['hireType']
  if url.endswith('/list'):
   return {'total':1 if typ==1 else 0,'list':[{'id':'7','jobNature':'实习'}] if typ==1 else []},'evidence'
  return {'id':'7','hireType':1,'title':'实习','description':'职责和要求在同一字段；2028届本科生','jobRequire':'','objectName':'2028届'},'evidence'
class AdapterTests(unittest.TestCase):
 def test_missing_separate_requirements_preserves_full_detail(self):
  c={'pages_scanned':0,'errors':[]};jobs=_mihoyo('米哈游','intern',FakeFetcher(),c)
  self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]['cohort_raw'],'2028届');self.assertEqual(c['expected_total'],1)
 def test_official_internship_not_forced_into_campus(self):
  c={'pages_scanned':0,'errors':[]};self.assertEqual(_mihoyo('米哈游','campus',FakeFetcher(),c),[]);self.assertEqual(c['expected_total'],0)
 def test_network_failure_not_successful_zero(self):
  with tempfile.TemporaryDirectory() as tmp,patch('qiuzhao.collector.p1_sources_11_20.Fetcher.api',side_effect=TimeoutError('timeout')):
   result=collect('米哈游','campus',Path(tmp))
   self.assertFalse(result['coverage']['complete']);self.assertEqual(result['coverage']['status'],'blocked');self.assertIsNone(result['coverage']['expected_total'])
 def test_invalid_scope_rejected(self):
  with self.assertRaises(ValueError):collect('米哈游','all',Path('/tmp/unused'))
if __name__=='__main__':unittest.main()
