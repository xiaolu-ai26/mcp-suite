import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from qiuzhao.collector import p1_sources_41_50 as m
class Batch41Tests(unittest.TestCase):
 def test_not_implemented_is_never_success_zero(self):
  with tempfile.TemporaryDirectory() as d:
   r=m.collect('长城汽车','campus',Path(d));self.assertEqual(r['coverage']['status'],'blocked');self.assertFalse(r['coverage']['complete'])
 def test_beisen_receives_verified_company_name(self):
  c=m.shared.coverage('https://career.mindray.com');c['errors']=['fixture']
  with tempfile.TemporaryDirectory() as d,patch.object(m,'collect_beisen',return_value={'jobs':[],'coverage':c}) as call:
   m.collect('迈瑞医疗','social',Path(d));self.assertEqual(call.call_args.args[:3],('迈瑞医疗','social','https://career.mindray.com'))
 def test_moka_scope_request_binds_company(self):
  c=m.shared.coverage('https://job.geely.com');c['errors']=['fixture']
  with tempfile.TemporaryDirectory() as d,patch.object(m.shared,'collect_moka_sites',return_value={'jobs':[],'coverage':c}):
   r=m.collect('吉利汽车','intern',Path(d));self.assertEqual(r['coverage']['scope_request']['company'],'吉利汽车');self.assertEqual(r['coverage']['scope_request']['scope'],'intern')
if __name__=='__main__':unittest.main()
