"""One authority/Result: actual Covestro JSON samples, no network."""
import copy
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from qiuzhao.collector import p1_platform_workday as W,p1_pipeline as P
from qiuzhao.normalize import normalize_records
from qiuzhao.v4_fields import to_item,RECRUITMENT_TYPES,enum_report
from qiuzhao.tools import Jobs,Dataset,FILTER_DEFAULTS
from qiuzhao.collector import lark_sync_enrichment as E

FIX=Path(__file__).parent/'fixtures/platform/covestro'
CONFIG={'key':'covestro/wd3/cov_external','search_text':'','applied_facets':{'Location_Country':['6cb77610a8a543aea2d6bc10457e35d4']},'country':'China','region_confirmed':True,'max_list_pages':1}


def replay(tmp_path,monkeypatch,scope='social',intern=False,mutate=None,controlled_complete=False,different_native=False):
    listing=json.loads((FIX/('student-limit1-original.json' if intern else 'china-limit1-original.json')).read_text(encoding='utf-8'))
    detail=json.loads((FIX/('student-detail-original.json' if intern else 'regular-detail-original.json')).read_text(encoding='utf-8'))
    if different_native:
        posting=listing['jobPostings'][0];info=detail['jobPostingInfo']
        posting.update(title='Other official role',externalPath='/job/Pudong-Shanghai-China/Other_JR-TEST',bulletFields=['JR-TEST'])
        info.update(id='11111111111111111111111111111111',title=posting['title'],jobReqId='JR-TEST',externalUrl='https://covestro.wd3.myworkdayjobs.com/cov_external'+posting['externalPath'])
    if controlled_complete:listing['total']=1
    if mutate:mutate(detail['jobPostingInfo'])
    calls=[]
    class Response:
        status_code=200
        def __init__(self,data):self.data=data
        def json(self):return self.data
        def raise_for_status(self):pass
    class Session:
        def post(self,url,**kwargs):calls.append(('POST',kwargs['json']));return Response(listing)
        def get(self,url,**kwargs):calls.append(('GET',url));return Response(detail)
    monkeypatch.setattr(W,'_make_session',Session)
    result=W.collect('科思创',scope,tmp_path,source_config=CONFIG)
    return result,calls


def validated(tmp_path,monkeypatch,**kwargs):
    result,calls=replay(tmp_path,monkeypatch,**kwargs)
    return P.validate_result(result,'科思创',kwargs.get('scope','social'),tmp_path),calls


def test_actual_unknown_collect_full_authority_public_and_base_chain(tmp_path,monkeypatch):
    result,calls=validated(tmp_path,monkeypatch)
    assert result['coverage']['status']=='partial' and not result['coverage']['complete']
    assert result['coverage']['unclassified_count']==1 and result['coverage']['list_total']==50
    assert calls[0][1]['searchText']=='' and calls[0][1]['appliedFacets']==CONFIG['applied_facets']
    merged,_=P.merge_records([], [('科思创','social',result)]);normalize_records(merged)
    row=merged[0];public=Jobs.public(to_item(row),date(2026,10,9))
    assert row['p1_scope'] is None and row['collection_scope']=='social'
    assert public['recruitment_type']=='未注明' and 'Technical Service' in public['description_raw']
    assert public['graduation_year_note']!='社招不限届别'
    assert E.business_fields(row)['招聘性质']==['未知']
    assert E.new_fields(row)[1]['招聘性质']==['未知']
    assert '未注明' in RECRUITMENT_TYPES
    data=Dataset((0,0),[public],None,{},0);service=Jobs('/unused',today='2026-10-09')
    found,_=service.evaluate(data,dict(FILTER_DEFAULTS),date(2026,10,9));assert len(found)==1
    for rtype in ('社会招聘','校园招聘','实习招聘'):
        f={**FILTER_DEFAULTS,'recruitment_type':rtype};assert service.evaluate(data,f,date(2026,10,9))[0]==[]
    assert service._choice('recruitment_type','未注明',RECRUITMENT_TYPES,[])=='未注明'


def test_actual_known_intern_still_strict_normal_scope(tmp_path,monkeypatch):
    result,_=validated(tmp_path,monkeypatch,scope='intern',intern=True)
    row=result['jobs'][0]
    assert row['recruitment_type']=='实习招聘' and row['p1_scope']=='intern'
    assert E.business_fields(row)['招聘性质']==['实习']
    assert 'Current undergraduate' in row['description_raw']


@pytest.mark.parametrize('damage',['missing-proof','bad-sha','changed-body','complete','missing-list','wrong-id'])
def test_unknown_insufficient_evidence_rejected(tmp_path,monkeypatch,damage):
    result,_=replay(tmp_path,monkeypatch)
    row=result['jobs'][0]
    if damage=='missing-proof':row.pop('classification_evidence')
    elif damage=='bad-sha':row['classification_evidence']['detail_sha256']='0'*64
    elif damage=='changed-body':row['description_raw']='Only a fabricated title'
    elif damage=='complete':result['coverage']['complete']=True
    elif damage=='missing-list':(tmp_path/row['classification_evidence']['list_file']).unlink()
    else:row['source_record_id']='incorrect'
    with pytest.raises(ValueError):P.validate_result(result,'科思创','social',tmp_path)


def test_cross_scope_one_native_record_then_known_keeps_id(tmp_path,monkeypatch):
    one,_=validated(tmp_path/'one',monkeypatch)
    two,_=validated(tmp_path/'two',monkeypatch,scope='intern')
    rows,_=P.merge_records([], [('科思创','social',one),('科思创','intern',two)])
    assert len(rows)==1;identity=rows[0]['id']
    known,_=validated(tmp_path/'known',monkeypatch,mutate=lambda i:i.update(recruitmentType='社会招聘'))
    rows,_=P.merge_records(rows,[('科思创','social',known)])
    assert len(rows)==1 and rows[0]['id']==identity and rows[0]['recruitment_type']=='社会招聘'
    unknown,_=validated(tmp_path/'unknown-again',monkeypatch)
    rows,_=P.merge_records(rows,[('科思创','social',unknown)])
    assert rows[0]['recruitment_type']=='未注明'
    assert rows[0]['last_confirmed_recruitment_type']['value']=='社会招聘'
    assert '历史官网确认' in to_item(rows[0])['detail_presentation']
    assert '历史官网确认' in E.qualification_note(rows[0])
    assert '本轮未披露' in E.new_fields(rows[0])[1][E.NOTE_FIELD]
    assert rows[0]['last_confirmed_recruitment_type']['checked_at']==known['jobs'][0]['classification_evidence']['observed_at']


def test_scope_negative_never_removes_unknown(tmp_path,monkeypatch):
    result,_=validated(tmp_path,monkeypatch);rows,_=P.merge_records([], [('科思创','social',result)])
    snapshot,_=validated(tmp_path/'complete',monkeypatch,controlled_complete=True,different_native=True,mutate=lambda i:i.update(recruitmentType='社会招聘'))
    assert snapshot['coverage']['complete']
    rows,_=P.merge_records(rows,[('科思创','social',snapshot)])
    original=next(r for r in rows if r['classification_status']=='unclassified')
    assert original.get('status')!='removed'


def test_explicit_unclassified_empty_type_cannot_default_campus():
    with pytest.raises(ValueError):normalize_records([{'classification_status':'unclassified','recruitment_type':''}])


@pytest.mark.parametrize('change',[{'region_confirmed':False},{'search_text':None},{'unknown':1},{'applied_facets':{'Location_Country':'not-list'}}])
def test_typed_config_bad_or_pending_rejected_before_http(tmp_path,change):
    with pytest.raises(ValueError):W.collect('科思创','social',tmp_path,source_config={**CONFIG,**change})


def test_plan_three_scope_keys_unchanged():
    units=sorted((n,s) for n in P.DEFAULT_COMPANIES for s in P.SCOPES)
    assert len(units)==3372 and len(P.DEFAULT_COMPANIES)==1124
    assert hashlib.sha256(json.dumps(units,ensure_ascii=False).encode()).hexdigest()=='81e6f011def97866350dcb3c221ceb9cf5a0d7b8d42b79a786960a5638ee0150'



def test_normal_type_cannot_use_unknown_status_marker(tmp_path,monkeypatch):
    result,_=replay(tmp_path,monkeypatch)
    result['jobs'][0]['recruitment_type']='社会招聘'
    with pytest.raises(ValueError):P.validate_result(result,'科思创','social',tmp_path)


def test_false_verified_type_not_supported_by_real_detail_rejected(tmp_path,monkeypatch):
    result,_=replay(tmp_path,monkeypatch)
    row=result['jobs'][0];row.update(recruitment_type='社会招聘',classification_status='verified')
    row['classification_evidence']['reason']='official_title_body'
    with pytest.raises(ValueError):P.validate_result(result,'科思创','social',tmp_path)


def test_last_default_social_is_not_official_history(tmp_path,monkeypatch):
    result,_=validated(tmp_path,monkeypatch)
    rows,_=P.merge_records([], [('科思创','social',result)])
    old=copy.deepcopy(rows[0]);old.update(recruitment_type='社会招聘',classification_status='legacy_default')
    old.pop('classification_evidence')
    rows,_=P.merge_records([old],[('科思创','social',result)])
    assert rows[0]['recruitment_type']=='未注明' and 'last_confirmed_recruitment_type' not in rows[0]


def legacy_authority_rows():
    listing=json.loads((FIX/'china-limit1-original.json').read_text(encoding='utf-8'))
    info=json.loads((FIX/'regular-detail-original.json').read_text(encoding='utf-8'))['jobPostingInfo']
    row=W._job('科思创','social',info,listing['jobPostings'][0],'https://covestro.wd3.myworkdayjobs.com','cov_external',CONFIG['key'],'China')
    assert 'native_identity_key' not in row and 'classification_evidence' not in row
    result={'jobs':[row],'coverage':{'status':'partial','complete':False,'detail_complete':True,
        'expected_total':1,'collected_jobs':1,'pages_scanned':1,'errors':['controlled legacy sample'],
        'scope_evidence':row['scope_evidence']}}
    checked=P.validate_result(result,'科思创','social')
    return P.merge_records([], [('科思创','social',checked)])[0]


def test_actual_legacy_schema_migrates_all_request_scopes_with_old_canonical_id(tmp_path,monkeypatch):
    rows=legacy_authority_rows();old_id=rows[0]['id'];old_identity=rows[0]['p1_identity']
    for scope in ('campus','intern','social'):
        incoming,_=validated(tmp_path/scope,monkeypatch,scope=scope)
        rows,_=P.merge_records(rows,[('科思创',scope,incoming)])
        assert len(rows)==1 and rows[0]['id']==old_id and rows[0]['p1_identity']==old_identity
        assert rows[0]['recruitment_type']=='未注明' and 'last_confirmed_recruitment_type' not in rows[0]
    known,_=validated(tmp_path/'known-complete',monkeypatch,controlled_complete=True,mutate=lambda i:i.update(recruitmentType='社会招聘'))
    assert known['coverage']['complete']
    rows,_=P.merge_records(rows,[('科思创','social',known)])
    assert len(rows)==1 and rows[0]['id']==old_id and rows[0]['status']!='removed'


@pytest.mark.parametrize('known_type,scope',[('社会招聘','social'),('校园招聘','campus'),('实习招聘','intern')])
def test_copied_native_key_without_proof_cannot_promote(tmp_path,monkeypatch,known_type,scope):
    incoming,_=validated(tmp_path,monkeypatch)
    row=incoming['jobs'][0];row.update(recruitment_type=known_type,classification_status='verified')
    row.pop('classification_evidence')
    with pytest.raises(ValueError,match='evidence|proof'):
        P.validate_result(incoming,'科思创',scope,tmp_path)


def test_actual_legacy_native_bridge_ambiguity_rejected(tmp_path,monkeypatch):
    old=legacy_authority_rows();duplicate=copy.deepcopy(old[0]);duplicate.update(id='distinct-old-id',p1_identity='distinct-old-id')
    incoming,_=validated(tmp_path,monkeypatch,scope='campus')
    with pytest.raises(ValueError,match='ambiguous'):
        P.merge_records([*old,duplicate],[('科思创','campus',incoming)])



@pytest.mark.parametrize('title,body',[
 ('Intern Program Manager','Manage undergraduate internship programmes. Ten years experience required. This is a regular staff position, not an internship.'),
 ('Graduate Recruitment Manager','Manage recruitment of recent graduates. Ten years professional experience required. This is a regular staff position.'),
 ('Research Intern','This is not an internship. Current undergraduate students are our research subjects.'),
])
def test_management_object_or_negation_not_applicant_nature(tmp_path,monkeypatch,title,body):
    def mutate(info):info.update(title=title,jobDescription='<p>'+body+'</p>')
    result,_=validated(tmp_path,monkeypatch,scope='intern',mutate=mutate,controlled_complete=True)
    row=result['jobs'][0]
    assert row['recruitment_type']=='未注明' and row['classification_status']=='unclassified'
    assert body in row['description_raw']
    assert result['coverage']['status']=='partial' and not result['coverage']['complete']


def native_scale_case(incoming_count, unrelated_count=179000):
    """Synthetic rows through the real merge interface, no persistent/global cache."""
    import sys
    import time
    operations={'unrelated_owner_gets':0,'target_owner_gets':0}
    class Counted(dict):
        def get(self,key,default=None):
            if key=='canonical_company':
                operations['unrelated_owner_gets' if self['canonical_company']=='无关企业' else 'target_owner_gets']+=1
            return super().get(key,default)
    previous=[Counted(id='unrelated-'+str(i),canonical_company='无关企业',source_record_id=str(i),
                      detail_url='https://unrelated.example/job/'+str(i),recruitment_type='社会招聘')
              for i in range(unrelated_count)]
    incoming=[]
    for i in range(incoming_count):
        native='native-'+str(i);url='https://covestro.wd3.myworkdayjobs.com/cov_external/job/'+native
        identity=hashlib.sha256(('科思创|covestro/wd3/cov_external|'+native).encode()).hexdigest()
        previous.append(Counted(id='legacy-'+str(i),p1_identity='legacy-'+str(i),canonical_company='科思创',
            p1_company='科思创',p1_scope='social',source_record_id=native,detail_url=url,recruitment_type='社会招聘'))
        incoming.append({'id':'p1n-'+identity[:24],'p1_identity':'p1n-'+identity[:24],
            'native_identity_key':identity,'source_record_id':native,'canonical_company':'科思创',
            'p1_company':'科思创','p1_scope':None,'collection_scope':'campus','recruitment_type':'未注明',
            'classification_status':'unclassified','detail_url':url,'source_url':url,'application_url':url,
            'job_title':'真实合成岗位','recruitment_unit':'科思创','description_raw':'岗位正文与资格要求。',
            'reviewed_at':'2026-10-09T00:00:00+00:00'})
    result={'jobs':incoming,'coverage':{'status':'partial','complete':False},'pending_index':[]}
    started=time.perf_counter();merged,_=P.merge_records(previous,[('科思创','campus',result)])
    elapsed=time.perf_counter()-started
    if sys.platform=='win32':
        import psutil
        peak=psutil.Process().memory_info().peak_wset
    else:
        import resource
        peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform!='darwin':peak*=1024
    assert len(merged)==unrelated_count+incoming_count
    assert all(merged[unrelated_count+i]['id']=='legacy-'+str(i) for i in range(incoming_count))
    return {'unrelated_rows':unrelated_count,'incoming':incoming_count,'seconds':round(elapsed,4),
            'process_peak_rss_bytes':peak,**operations}


@pytest.mark.parametrize('incoming_count',[2,200])
def test_native_bridge_scale_candidate_lookup_bounded(incoming_count):
    metrics=native_scale_case(incoming_count)
    # Two setup owner passes over unrelated rows, independent of M. Candidate
    # matching never rereads an unrelated owner for each incoming.
    assert metrics['unrelated_owner_gets']==2*metrics['unrelated_rows']
    assert metrics['target_owner_gets']<=4*incoming_count
    print(json.dumps(metrics,ensure_ascii=False))
