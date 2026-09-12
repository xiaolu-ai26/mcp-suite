import importlib.util
from pathlib import Path
from unittest.mock import patch
import tempfile, unittest
SPEC=importlib.util.spec_from_file_location('batch01',Path(__file__).parents[1]/'qiuzhao/collector/p1_sources_01_10.py')
m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)
class CollectorTests(unittest.TestCase):
 def test_requirement_sentences_remain_verbatim(self):
  raw={'serveRequirement':'本科及以上学历；计算机相关专业；沟通能力强。'}
  j=m.job('pdd','campus','a','岗位','https://example.com/a','职责','上海',raw)
  self.assertEqual(j['education_raw'],'本科及以上学历');self.assertEqual(j['major_requirements_raw'],'计算机相关专业')
 def test_moka_unknown_scope_never_complete_zero(self):
  from unittest.mock import MagicMock
  response=MagicMock(text='');session=MagicMock();session.get.return_value=response
  with tempfile.TemporaryDirectory() as d,patch.object(m.requests,'Session',return_value=session),patch.object(m,'request_json',return_value={'jobs':[{'id':'x','hireMode':99}],'jobStats':{'total':1}}):
   r=m.collect_moka_sites('dji','campus',[('https://example.com/campus-recruitment/dji/123','official')],Path(d));self.assertFalse(r['coverage']['complete']);self.assertEqual(r['coverage']['status'],'blocked')
 def test_moka_cache_invalidates_when_source_changes(self):
  row={'id':'a','updatedAt':'2026-09-12','title':'A'};detail={'id':'a','jobDescription':'正文'}
  with tempfile.TemporaryDirectory() as d,patch.object(m,'request_json',return_value=detail) as call,patch.dict(m.os.environ,{},clear=True):
   out=Path(d)/'campus';out.mkdir()
   self.assertFalse(m.moka_detail_cached('dji','campus',row,'https://example.com','dji',1,None,out)[2])
   self.assertTrue(m.moka_detail_cached('dji','campus',row,'https://example.com','dji',1,None,out)[2]);self.assertEqual(call.call_count,1)
   row['title']='Changed';self.assertFalse(m.moka_detail_cached('dji','campus',row,'https://example.com','dji',1,None,out)[2]);self.assertEqual(call.call_count,2)
 def test_campaign_year_is_bound_to_one_job(self):
  from qiuzhao.v4_fields import graduation_of
  target=m.job('dji','campus','093114fd-38fa-497b-ac5a-8a8f47777708','数字管理','https://example.com/a','职责')
  other=m.job('dji','campus','other','其他','https://example.com/b','职责')
  target['campaign_cohort_raw']='面向2027届及优秀2026届高校毕业生'
  self.assertIn('2026届',graduation_of(target)[0]);self.assertNotIn('2026届',graduation_of(other)[0])
 def test_cities_survive_normalize_v4(self):
  import sys
  sys.path.insert(0,str(Path(__file__).parents[1]))
  from qiuzhao.normalize import normalize_records
  from qiuzhao.v4_fields import cities_of
  row=m.job('pdd','campus','a','岗位','https://example.com/job/a','岗位说明','上海 / 北京')
  normalize_records([row]);self.assertEqual(set(cities_of(row)),{'上海','北京'})
 def test_pdd_terminal_total_zero(self):
  calls=[{'total':'1','list':[{'id':'a','graduationYear':'2027'}]}, {'id':'a','normal':True,'name':'岗位','jobDuty':'职责','serveRequirement':'要求'}, {'total':'0','list':None}]
  with tempfile.TemporaryDirectory() as d,patch.object(m,'request_json',side_effect=calls):
   r=m.collect('拼多多','campus',Path(d));self.assertTrue(r['coverage']['complete']);self.assertEqual(r['jobs'][0]['cohort_raw'],'2027届');self.assertEqual(r['coverage']['scope_request']['company'],'拼多多')
 def test_repeated_page_fails_closed(self):
  calls=[{'total':'2','list':[{'id':'a'}]}, {'id':'a','normal':True,'name':'岗位','jobDuty':'职责','serveRequirement':'要求'}, {'total':'2','list':[{'id':'a'}]}]
  with tempfile.TemporaryDirectory() as d,patch.object(m,'request_json',side_effect=calls):
   r=m.collect('pdd','campus',Path(d));self.assertFalse(r['coverage']['complete']);self.assertEqual(r['coverage']['status'],'partial')
 def test_detail_missing_requirements_not_publish(self):
  calls=[{'total':'1','list':[{'id':'a'}]}, {'id':'a','normal':True,'name':'岗位','jobDuty':'职责'}]
  with tempfile.TemporaryDirectory() as d,patch.object(m,'request_json',side_effect=calls):
   r=m.collect('pdd','campus',Path(d));self.assertFalse(r['coverage']['complete']);self.assertEqual(r['jobs'],[])
 def test_unknown_social_never_success_zero(self):
  from unittest.mock import MagicMock
  response=MagicMock(status_code=400,text='{"success":false,"errorCode":400023}')
  response.json.return_value={'success':False,'errorCode':400023}
  session=MagicMock();session.headers={};session.get.return_value=response;session.post.return_value=response
  with tempfile.TemporaryDirectory() as d,patch.object(m.requests,'Session',return_value=session):
   r=m.collect('拼多多','social',Path(d));self.assertEqual(r['coverage']['status'],'blocked');self.assertIsNone(r['coverage']['expected_total'])
if __name__=='__main__':unittest.main()
