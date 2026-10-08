import unittest,tempfile,json
from pathlib import Path
from unittest.mock import MagicMock,patch
from qiuzhao.collector import p1_sources_31_40 as m
class BeisenSourceTests(unittest.TestCase):
 def setup_session(self,pages):
  session=MagicMock();response=MagicMock(text='<script>var BSGlobal={"PortalId":"abc"};</script>',url='https://official.example/')
  session.get.return_value=response
  calls=[]
  for payload in pages:
   r=MagicMock();r.json.return_value=payload;calls.append(r)
  session.post.side_effect=calls;return session
 def test_official_zero_is_proven(self):
  session=self.setup_session([{'Code':200,'Count':0,'Data':[]}])
  with tempfile.TemporaryDirectory() as d,patch.object(m.shared,'make_session',return_value=session):
   result=m.collect_beisen('公司','campus','https://official.example',Path(d))
   self.assertTrue(result['coverage']['complete']);self.assertEqual(result['coverage']['expected_total'],0)
 def test_unknown_scope_is_not_zero_success(self):
  session=self.setup_session([{'Code':200,'Count':1,'Data':[{'Id':'a','CategoryId':'99'}]}])
  with tempfile.TemporaryDirectory() as d,patch.object(m.shared,'make_session',return_value=session):
   result=m.collect_beisen('公司','campus','https://official.example',Path(d))
   self.assertFalse(result['coverage']['complete']);self.assertEqual(result['coverage']['status'],'blocked')
 def test_custom_official_category_requires_explicit_mapping(self):
  row={'Id':'a','CategoryId':'4','Category':'飞星计划'};session=self.setup_session([{'Code':200,'Count':1,'Data':[row]},{'Code':200,'Count':1,'Data':[]}])
  detail=MagicMock();detail.json.return_value={'Code':200,'Data':{'Id':'a','CategoryId':'4','Category':'飞星计划','JobAdName':'岗位','Duty':'工作职责','Require':'2027届硕士','LocNames':['合肥市']}}
  with tempfile.TemporaryDirectory() as d,patch.object(m.shared,'make_session',return_value=session),patch.object(m.shared,'http_get',return_value=detail):
   result=m.collect_beisen('公司','campus','https://official.example',Path(d),category_mapping={'4':'campus'});self.assertTrue(result['coverage']['complete']);self.assertEqual(len(result['jobs']),1)
 def test_location_field_and_identity_checked(self):
  row={'Id':'a','CategoryId':'2'};session=self.setup_session([{'Code':200,'Count':1,'Data':[row]},{'Code':200,'Count':1,'Data':[]}])
  detail=MagicMock();detail.json.return_value={'Code':200,'Data':{'Id':'a','CategoryId':'2','Category':'校园招聘','JobAdName':'岗位','Duty':'工作职责','Require':'硕士学历，计算机相关专业','LocNames':['广东省·深圳市']}}
  with tempfile.TemporaryDirectory() as d,patch.object(m.shared,'make_session',return_value=session),patch.object(m.shared,'http_get',return_value=detail) as request:
   result=m.collect_beisen('公司','campus','https://official.example',Path(d));self.assertTrue(result['coverage']['complete']);self.assertEqual(result['jobs'][0]['cities'],['深圳']);self.assertIn('LocId',json.loads(request.call_args.kwargs['params']['displayFields']))
if __name__=='__main__':unittest.main()

class LiAutoScopeTests(unittest.TestCase):
 def collect(self,tmp,scope='social',hire=1,mode='102',label='外包',detail_changes=None):
  row={'id':20237,'hire_mode':hire,'job_mode':mode,'job_mode_name':label,'title':'【外援】维修专家/专员','location_title':'上海闵行区'}
  session=MagicMock()
  def listing(url,**kwargs):
   items=[row] if '/social/' in url else []
   response=MagicMock();response.json.return_value={'code':0,'data':{'items':items,'total_count':len(items),'page':1,'total_pages':1}};return response
  session.get.side_effect=listing
  data={**row,'description':'负责车辆维修工作。','requirements':'具备汽车维修技术经验。','department_title':'维修服务',**(detail_changes or {})}
  response=MagicMock();response.json.return_value={'code':0,'data':data}
  with patch.object(m.shared,'make_session',return_value=session),patch.object(m.shared,'http_get',return_value=response) as request:
   result=m.collect_lixiang(scope,Path(tmp))
  return result,request
 def test_explicit_outsource_social_is_selected_and_remains_outsource(self):
  with tempfile.TemporaryDirectory() as d:
   result,request=self.collect(d)
  self.assertTrue(result['coverage']['complete']);self.assertEqual(result['coverage']['expected_total'],1)
  self.assertEqual(request.call_count,1);job=result['jobs'][0]
  self.assertEqual(job['employment_relationship_raw'],'外包')
  self.assertIn('外包',job['description_raw']);self.assertIn('不能据此认定公司直聘',job['detail_presentation'])
 def test_outsource_not_other_scope(self):
  for scope in ('campus','intern'):
   with self.subTest(scope=scope),tempfile.TemporaryDirectory() as d:
    result,request=self.collect(d,scope)
   self.assertTrue(result['coverage']['complete']);self.assertEqual(result['coverage']['expected_total'],0);self.assertEqual(request.call_count,0)
 def test_unknown_label_or_invalid_hire_mode_not_inferred(self):
  for hire,label in ((1,'未知'),(1,'实习'),(2,'外包'),(True,'外包'),('1','外包'),(1.0,'外包')):
   with self.subTest(hire=hire,label=label),tempfile.TemporaryDirectory() as d:
    result,request=self.collect(d,hire=hire,label=label)
   self.assertFalse(result['coverage']['complete']);self.assertTrue(result['coverage']['errors']);self.assertEqual(request.call_count,0)
 def test_detail_uses_same_typed_scope_gate(self):
  for changes in ({'hire_mode':2},{'hire_mode':True},{'job_mode_name':'未知'},{'job_mode':'202'},{'id':20238}):
   with self.subTest(changes=changes),tempfile.TemporaryDirectory() as d:
    result,request=self.collect(d,detail_changes=changes)
   self.assertEqual(request.call_count,1);self.assertFalse(result['coverage']['complete']);self.assertEqual(result['jobs'],[])

 def test_existing_official_modes_are_unchanged(self):
  for mode,hire,scope in (('101',1,'social'),('101',2,'campus'),('201',2,'campus'),('202',2,'intern')):
   with self.subTest(mode=mode,hire=hire),tempfile.TemporaryDirectory() as d:
    result,request=self.collect(d,scope=scope,mode=mode,hire=hire,label='原官方模式')
   self.assertTrue(result['coverage']['complete']);self.assertEqual(request.call_count,1)
   self.assertNotIn('employment_relationship_raw',result['jobs'][0])
 def test_invalid_mode_types_are_not_outsource(self):
  for mode in (True,False,102.0,{},[]):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
    result,request=self.collect(d,mode=mode)
   self.assertFalse(result['coverage']['complete']);self.assertEqual(request.call_count,0)
 def test_real_public_projection_preserves_outsource_disclosure(self):
  from datetime import date
  from qiuzhao.v4_fields import to_item
  from qiuzhao.tools import Jobs
  with tempfile.TemporaryDirectory() as d:
   result,request=self.collect(d,detail_changes={'description':'按照标准服务流程和维修工艺流程，完成售后服务完整流程。','requirements':'中专及以上学历、C1及以上驾照，驾驶熟练。','department_title':'上海战区'})
  public=Jobs.public(to_item(result['jobs'][0]),date(2026,10,9))
  self.assertIn('外包',public['description_raw']);self.assertIn('不能据此认定公司直聘',public['detail_presentation'])
  self.assertIn('具体用工主体未披露',public['status_note'])
 def test_integer_outsource_mode_in_list_is_not_inferred(self):
  with tempfile.TemporaryDirectory() as d:
   result,request=self.collect(d,mode=102)
  self.assertFalse(result['coverage']['complete']);self.assertTrue(result['coverage']['errors'])
  self.assertEqual(result['jobs'],[]);self.assertEqual(request.call_count,0)
 def test_integer_outsource_mode_in_detail_is_quarantined(self):
  with tempfile.TemporaryDirectory() as d:
   result,request=self.collect(d,detail_changes={'job_mode':102})
  self.assertFalse(result['coverage']['complete']);self.assertEqual(result['jobs'],[])
  self.assertEqual(result['coverage']['expected_total'],1);self.assertEqual(request.call_count,1)
