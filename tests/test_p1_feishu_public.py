import unittest
from qiuzhao.collector.p1_feishu_public import actual_scope,public_row,response_data,collect_feishu
from pathlib import Path
class PublicSDKTests(unittest.TestCase):
 def test_same_campus_site_distinguishes_formal_and_intern(self):
  self.assertEqual(actual_scope({'recruit_type':{'id':'201'}}),'campus')
  self.assertEqual(actual_scope({'recruit_type':{'id':'202'}}),'intern')
 def test_unknown_type_is_not_assumed_social(self):
  self.assertIsNone(actual_scope({'recruit_type':{'id':'999','name':'未知'}}))
 def test_evidence_omits_staff_and_auth_metadata(self):
  r=public_row({'id':'1','title':'role','recruiter_email':'private','cookies':'private','signature':'private','job_post_info':{'required_degree':'本科','employee_profile':{'name':'private'}}})
  self.assertNotIn('private',str(r));self.assertEqual(r['required_degree'],'本科')
 def test_rejected_or_invalid_envelope_never_becomes_empty_success(self):
  for response in [[],{'code':401,'data':{}},{'code':405,'data':{'count':0,'job_post_list':[]}}]:
   with self.assertRaises(ValueError):response_data(response)
 def test_unverified_tenant_configuration_rejected_before_browser(self):
  with self.assertRaises(ValueError):collect_feishu('company','campus',[{'url':'https://example.org'}],Path('/tmp/not-written'))
class CleanupTests(unittest.TestCase):
 def test_context_cleanup_error_does_not_skip_browser_and_driver(self):
  from unittest.mock import MagicMock
  from qiuzhao.collector.p1_feishu_public import AnonymousBrowser
  browser=AnonymousBrowser(None);ctx=MagicMock();engine=MagicMock();driver=MagicMock();ctx.close.side_effect=RuntimeError('already closed')
  browser._context=ctx;browser._browser=engine;browser._pw=driver
  browser.close();engine.close.assert_called_once();driver.stop.assert_called_once();self.assertIsNone(browser._browser)
class RoleDisclosureTests(unittest.TestCase):
 def test_one_real_section_is_retained_with_missing_marker(self):
  from qiuzhao.collector.p1_feishu_public import role_body
  body,missing=role_body('负责开发用户界面','')
  self.assertEqual(body,'负责开发用户界面');self.assertEqual(missing,['requirement'])
 def test_team_introduction_cannot_replace_role(self):
  from qiuzhao.collector.p1_feishu_public import role_body
  with self.assertRaises(ValueError):role_body('团队介绍：我们是一家全球领先的科技企业。','')
  with self.assertRaises(ValueError):role_body('','')
if __name__=='__main__':unittest.main()

class NativeFieldTests(unittest.TestCase):
 def test_only_native_human_labels_are_mapped(self):
  from qiuzhao.collector.p1_feishu_public import public_label
  self.assertEqual(public_label({'name':{'zh_cn':'本科'}}),'本科')
  self.assertEqual(public_label([{'name':'计算机科学'}, {'name':'金融学'}]),'计算机科学；金融学')
  self.assertEqual(public_label(7),'');self.assertEqual(public_label({'id':7}),'');self.assertEqual(public_label('7'),'')
 def test_pending_error_does_not_persist_signature(self):
  from qiuzhao.collector.p1_feishu_public import pending_record
  row=pending_record({'id':'1','title':'Role'},'https://example.com/role/1','list.json',error='Failed https://example.com/api?_signature=sensitive&token=secret')
  self.assertNotIn('sensitive',str(row));self.assertNotIn('secret',str(row));self.assertEqual(row['source_missing_fields'],[])

class PendingFlowTests(unittest.TestCase):
 def run_flow(self,folder,empty=False,failed=False):
  from unittest.mock import patch
  from qiuzhao.collector import p1_feishu_public as F
  row={'id':'123','title':'工程师','recruit_type':{'id':'201','name':'校招'},'description':'' if empty else '开发软件','requirement':'' if empty else '技能熟练','channel_online_status':1,'city_list':[{'name':'上海'}],'job_post_info':{'required_degree':{'name':'本科'},'target_major_list':[{'name':'计算机科学'}]}}
  class Page:
   def on(self,*a):pass
   def remove_listener(self,*a):pass
   def goto(self,*a,**kw):pass
   def wait_for_function(self,*a,**kw):pass
   def wait_for_timeout(self,*a):pass
   def evaluate(self,expression,args=None):
    if 'JSON.parse(document' in expression:return {'tenant_info':{'tenant_name':'Fixture'},'website_info':{'id':'1','path':'campus','process_type':2}}
    if expression==F.INSTALL_SDK:return True
    if expression==F.LIST_CALL:return {'code':0,'data':{'count':1,'job_post_list':[row]}}
    if expression==F.DETAIL_CALL:
     if failed:return [{'id':'123','error':'network failure'}]
     return [{'id':'123','data':{'code':0,'data':{'job_post_detail':row}}}]
    raise AssertionError(expression)
  class Browser:
   def __init__(self,*a,**kw):self.page=Page()
   def _ensure(self):pass
   def __enter__(self):return self
   def __exit__(self,*a):pass
  with patch.object(F,'AnonymousBrowser',Browser),patch.dict(F.os.environ,{'QIUZHAO_BROWSER_LOCK':str(folder/'test.lock')}):
   return F.collect_feishu('Fixture','campus',[{'url':'https://example.com/campus/position/list','tenant_names':['Fixture'],'portal_type':6}],folder)
 def test_empty_official_detail_is_index_without_invented_body(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:r=self.run_flow(Path(d),empty=True)
  self.assertEqual(r['jobs'],[]);self.assertTrue(r['coverage']['complete']);self.assertEqual(r['coverage']['expected_total'],1);self.assertEqual(r['pending_index'][0]['pending_reason'],'source_empty_body');self.assertEqual(r['pending_index'][0]['detail_request_status'],'success')
 def test_failed_detail_stays_partial_and_does_not_claim_source_empty(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:r=self.run_flow(Path(d),failed=True)
  self.assertFalse(r['coverage']['complete']);self.assertEqual(r['pending_index'][0]['pending_reason'],'fetch_failed');self.assertEqual(r['pending_index'][0]['source_missing_fields'],[])
 def test_native_education_and_major_reach_job(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:r=self.run_flow(Path(d))
  self.assertEqual(r['jobs'][0]['education_raw'],'本科');self.assertEqual(r['jobs'][0]['major_requirements_raw'],'计算机科学');self.assertEqual(r['jobs'][0]['source_channel_online_status'],1)
