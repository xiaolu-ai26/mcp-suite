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
