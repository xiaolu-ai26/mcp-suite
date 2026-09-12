import copy
import pytest
from qiuzhao.collector.p1_status_repair import repair_rows
UUID='7d6cd396-a45a-420d-a8c0-e2ad3261f0b9'

def test_only_exact_owned_identity_changes_and_dates_content_are_preserved():
    row={'id':'legacy-id','p1_company':'大疆','p1_scope':'social','source_record_id':UUID,'status':'unverified','description_raw':'original','reviewed_at':'yesterday','deadline':None}
    patch={'company':'大疆','scope':'social','source_record_id':UUID,'updates':{'status':'expired','source_is_active':False,'source_list_status_raw':'pause','status_note':'暂停'}}
    original=copy.deepcopy(row);result,changes=repair_rows([row], [patch])
    assert row==original and result[0]['status']=='expired' and result[0]['deadline'] is None
    assert result[0]['description_raw']=='original' and result[0]['reviewed_at']=='yesterday'
    assert len(changes)==1 and changes[0]['id']=='legacy-id'
    assert repair_rows(result,[patch])[1]==[]
    assert repair_rows([{**row,'p1_company':'其他'}],[patch])[1]==[]
    patch['updates']['description_raw']='forged'
    with pytest.raises(ValueError):repair_rows([row],[patch])


def test_response_must_show_same_id_and_official_status():
    from qiuzhao.collector.p1_status_repair import evidence_has_status
    response={'data':{'jobs':[{'id':UUID,'status':'pause'}]}}
    assert evidence_has_status(response,UUID,'pause')
    assert not evidence_has_status(response,UUID,'closed')
    assert not evidence_has_status(response,'other','pause')


def test_missing_status_never_counts_as_inactive_evidence():
    from qiuzhao.collector.p1_status_repair import evidence_has_status
    assert not evidence_has_status({'id':UUID},UUID,None)
    assert not evidence_has_status({'id':UUID,'status':'open'},UUID,'open')


def test_default_search_excludes_inactive_without_inventing_deadline(tmp_path):
    import json
    from datetime import date
    from qiuzhao.tools import Jobs
    raw={'id':'paused','job_title':'岗位','recruitment_unit':'大疆','recruitment_type':'社会招聘',
         'source_url':'https://example.org/job/paused','application_url':'https://example.org/job/paused',
         'description_raw':'真实职责','status':'expired','source_is_active':False,'source_status_raw':'pause','deadline':None}
    path=tmp_path/'jobs.json';path.write_text(json.dumps([raw,{**raw,'id':'open','status':'open','source_is_active':True,'source_status_raw':'open'}]))
    jobs=Jobs(path,today=date(2026,9,13))
    result=jobs.search(company='大疆')
    assert result['total']==1 and result['jobs'][0]['id']=='open'
    result=jobs.search(company='大疆',include_expired=True)
    assert result['total']==2
    paused=next(r for r in result['jobs'] if r['id']=='paused')
    assert paused['deadline'] is None and paused['source_status_raw']=='pause'


def test_streamed_write_input_retains_strict_json_grammar(tmp_path):
    from qiuzhao.v4_fields import iter_json_file
    import json
    good=[{'id':'中文😀','nested':[1,2]}, {'id':'b'}]
    path=tmp_path/'jobs.json';path.write_text(json.dumps(good,ensure_ascii=False))
    assert list(iter_json_file(path,chunk_bytes=3,strict=True))==good
    for text in ['[{"id":"a"}{"id":"b"}]','[{"id":"a"},]','[,{}]','[{}]\u00a0']:
        path.write_text(text)
        with pytest.raises(ValueError):list(iter_json_file(path,chunk_bytes=3,strict=True))
