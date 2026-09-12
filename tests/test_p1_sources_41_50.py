import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from qiuzhao.collector import p1_sources_41_50 as m
class Batch41Tests(unittest.TestCase):
 def test_not_implemented_is_never_success_zero(self):
  with tempfile.TemporaryDirectory() as d:
   r=m.collect('网易','campus',Path(d));self.assertEqual(r['coverage']['status'],'blocked');self.assertFalse(r['coverage']['complete'])
 def test_beisen_receives_verified_company_name(self):
  c=m.shared.coverage('https://career.mindray.com');c['errors']=['fixture']
  with tempfile.TemporaryDirectory() as d,patch.object(m,'collect_beisen',return_value={'jobs':[],'coverage':c}) as call:
   m.collect('迈瑞医疗','social',Path(d));self.assertEqual(call.call_args.args[:3],('迈瑞医疗','social','https://career.mindray.com'))
 def test_moka_scope_request_binds_company(self):
  c=m.shared.coverage('https://job.geely.com');c['errors']=['fixture']
  with tempfile.TemporaryDirectory() as d,patch.object(m.shared,'collect_moka_sites',return_value={'jobs':[],'coverage':c}):
   r=m.collect('吉利汽车','intern',Path(d));self.assertEqual(r['coverage']['scope_request']['company'],'吉利汽车');self.assertEqual(r['coverage']['scope_request']['scope'],'intern')
if __name__=='__main__':unittest.main()

class JDSocialInlineTests(unittest.TestCase):
 def test_full_inline_list_has_real_link_type_and_source_identity(self):
  class Response:
   def __init__(self,data=None,text=''):self.data=data;self.text=text
   def raise_for_status(self):pass
   def json(self):return self.data
  class Session:
   def get(self,*a,**k):return Response(text='<title>京东社会招聘</title>')
   def post(self,url,**kwargs):
    if url.endswith('job_count'):return Response(text='1')
    page=kwargs['data']['pageIndex']
    return Response([{'requirementId':33,'positionId':4,'positionNameOpen':'软件工程师','workContent':'负责开发业务服务并参与产品迭代。','qualification':'本科及以上学历，具备软件开发经验。','workCity':'北京市'}] if page==1 else [])
  with tempfile.TemporaryDirectory() as d,patch.object(m.shared,'make_session',return_value=Session()):
   r=m.collect_jd_social(Path(d));j=r['jobs'][0]
   self.assertEqual(r['coverage']['list_total'],1);self.assertEqual(r['coverage']['pages_scanned'],1)
   self.assertEqual(j['source_record_id'],'jd-social:33');self.assertEqual(j['application_link_type'],'list_entry');self.assertEqual(j['detail_presentation'],'inline')
   self.assertTrue(r['coverage']['complete']);self.assertNotIn('#',j['detail_url'])
