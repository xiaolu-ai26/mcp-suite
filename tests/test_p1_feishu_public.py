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
