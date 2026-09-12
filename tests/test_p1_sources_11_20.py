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

class AntCoverageTests(unittest.TestCase):
 def test_duplicate_page_never_complete(self):
  import json
  from qiuzhao.collector.p1_sources_11_20 import _ant
  class F:
   def get(self,url,name,payload):
    return json.dumps({'success':True,'totalCount':2,'content':[{'id':'1','name':'engineer','description':'duties','requirement':'requirements'}]}),'evidence'
  c={'errors':[],'pages_scanned':0}
  with patch('qiuzhao.collector.p1_sources_11_20.time.sleep'):
   rows=_ant('蚂蚁集团','social',F(),c)
  self.assertEqual(len(rows),1);self.assertTrue(c['errors'])
 def test_team_intro_cannot_replace_job_detail(self):
  import json
  from qiuzhao.collector.p1_sources_11_20 import _ant
  class F:
   def get(self,url,name,payload):
    return json.dumps({'success':True,'totalCount':1,'content':[{'id':'1','name':'engineer','teamDescription':'team introduction'}]}),'evidence'
  c={'errors':[],'pages_scanned':0};rows=_ant('蚂蚁集团','social',F(),c)
  self.assertFalse(rows);self.assertTrue(c['errors'])

class FullSourceRegressionTests(unittest.TestCase):
 def test_didi_different_jd_number_rejects_wrong_detail(self):
  import json
  from qiuzhao.collector.p1_sources_11_20 import _didi
  class F:
   def get(self,url,name,payload=None):
    if name.startswith('list'):
     return json.dumps({'meta':{'code':0},'data':{'total':1,'items':[{'jdId':1,'jdNo':'A'}]}}),'list'
    if name.startswith('detail'):
     return json.dumps({'meta':{'code':0},'data':{'recruitType':'1','jdNo':'B','jobDesc':'duties','qualification':'requirements'}}),'detail'
    raise TimeoutError('global unavailable')
  c={'errors':[],'pages_scanned':0};rows=_didi('滴滴','social',F(),c)
  self.assertFalse(rows);self.assertTrue(any('JD number mismatch' in e for e in c['errors']))
 def test_lenovo_numeric_total_detects_missing_next_page(self):
  from qiuzhao.collector.p1_sources_11_20 import _lenovo
  class F:
   def get(self,*args):
    return '<p>1-1 of 2 jobs</p><article><h3><a href="https://jobs.lenovo.com/en_US/careers/JobDetail/Role/1">Graduate</a></h3></article>','list'
  with self.assertRaisesRegex(ValueError,'official total'):
   _lenovo('联想','campus',F(),{'errors':[],'pages_scanned':0})

class GraduationDateTests(unittest.TestCase):
 def test_official_midnight_utc_dates_use_china_calendar_window(self):
  from qiuzhao.collector.p1_sources_11_20 import graduation_window
  self.assertEqual(graduation_window({'from':'2026-08-31T16:00:00.000+00:00','to':'2030-10-30T16:00:00.000+00:00'}),'毕业时间 2026-09-01 至 2030-10-31')
 def test_unknown_and_reversed_windows_not_guessed(self):
  from qiuzhao.collector.p1_sources_11_20 import graduation_window
  self.assertEqual(graduation_window({'from':None,'to':None}),'')
  with self.assertRaises(ValueError):graduation_window({'from':'2028-01-01','to':'2027-01-01'})
if __name__=='__main__':unittest.main()

class BilibiliAnonymousTests(unittest.TestCase):
 def run_source(self,tmp,wrong=False,duplicate=False):
  from unittest.mock import patch
  from qiuzhao.collector.p1_sources_11_20 import _bilibili,Fetcher
  class Response:
   def __init__(self,data):self.data=data
   def raise_for_status(self):pass
   def json(self):return self.data
  class Session:
   def __init__(self):self.headers={}
   def get(self,url,**kw):
    if url.endswith('token'):return Response({'code':0,'data':'ephemeral-do-not-persist'})
    return Response({'code':0,'data':{'id':99 if wrong else 1,'positionName':'工程师','positionTypeName':'全职','positionDescription':'工作职责:研发\n工作要求:本科','workLocation':'上海','leaderList':['not-needed']}})
   def post(self,url,json,**kw):
    self_test.assertEqual(json['positionTypeList'],[])
    rows=[] if '/srs/' in url else [{'id':1,'positionTypeName':'全职'}]
    return Response({'code':0,'data':{'total':2 if duplicate and rows else len(rows),'list':rows}})
   def close(self):pass
  self_test=self;c={'errors':[],'pages_scanned':0};f=Fetcher(tmp)
  with patch('qiuzhao.collector.p1_sources_11_20.requests.Session',Session):rows=_bilibili('哔哩哔哩','campus',f,c)
  return rows,c
 def test_guest_protocol_and_no_token_or_staff_evidence(self):
  import tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory() as d:
   rows,c=self.run_source(Path(d));self.assertEqual(len(rows),1);self.assertEqual(rows[0]['detail_url'],'https://jobs.bilibili.com/campus/positions/1')
   evidence=''.join(p.read_text() for p in Path(d).glob('*.json'));self.assertNotIn('ephemeral-do-not-persist',evidence);self.assertNotIn('leaderList',evidence)
 def test_wrong_detail_identity_preserves_partial(self):
  import tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory() as d:
   rows,c=self.run_source(Path(d),wrong=True);self.assertEqual(rows,[]);self.assertTrue(c['errors'])
 def test_duplicate_pagination_fails_closed(self):
  import tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaisesRegex(ValueError,'duplicate'):self.run_source(Path(d),duplicate=True)
