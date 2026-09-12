from qiuzhao.collector.p1_xiaomi_overseas import navigation_portals,align_identity

def test_only_live_official_domain_links_are_discovered():
 text='<a href="https://xiaomi.jobs.f.mioffice.cn/eastasia">Jobs</a><a href="https://other.jobs.f.mioffice.cn/global">Other</a>'
 assert navigation_portals(text)=={'https://xiaomi.jobs.f.mioffice.cn/eastasia'}

def test_domestic_identity_namespace_matches_for_jobs_and_pending():
 r={'jobs':[{'source_record_id':'123'}],'pending_index':[{'source_record_id':'456'}]}
 align_identity(r)
 assert r['jobs'][0]['source_record_id']=='feishu-xiaomi:123'
 assert r['pending_index'][0]['official_source_id']=='456'
 assert r['pending_index'][0]['source_record_id']=='feishu-xiaomi:456'

def test_unverified_source_id_cannot_become_canonical():
 import pytest
 with pytest.raises(ValueError):align_identity({'jobs':[{'source_record_id':'synthetic-title-id'}]})
