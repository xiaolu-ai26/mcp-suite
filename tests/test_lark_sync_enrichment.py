from qiuzhao.collector import lark_sync_enrichment as E


def test_conditions_are_preserved_and_historical_tags_are_not_official_quotes():
    note=E.qualification_note({'description_raw':'面向2027届本科及以上；2026届未就业优秀毕业生。'})
    assert '2026届未就业优秀毕业生' in note
    assert '存量' in note
    note=E.qualification_note({'cohort_raw':'2027届'})
    assert '待回源核实' in note and '历史' in note


def test_new_p1_record_has_arrays_and_no_manual_remark():
    raw={'id':'p1-test','p1_company':'大疆','source_record_id':'official-id','job_title':'算法岗位',
         'recruitment_type':'校园招聘','recruitment_unit':'大疆创新','cohort_raw':'2026届或2027届',
         'description_raw':'算法研发；本科及以上学历。','detail_url':'https://careers.dji.com/job/test',
         'source_url':'https://careers.dji.com/job/test','cities':['深圳','北京'],
         'major_requirements_raw':'计算机科学、电子信息','status':'unverified'}
    table,fields=E.new_fields(raw)
    assert table==E.S.TABLES[2]
    assert fields['毕业届别']==['2027届','2026届']
    assert fields['专业']==['计算机类','电子信息类']
    assert '备注' not in fields
    assert fields['job_id']=='p1-test'


def test_role_condition_precedes_generic_campaign_and_bound_exceptions_remain():
    raw={'p1_company':'大疆','cohort_raw':'仅2026届、毕业未就业','campaign_cohort_raw':'2027届秋招',
         'recruitment_type':'校园招聘'}
    note=E.qualification_note(raw)
    assert note.startswith('官方采集岗位资格字段：仅2026届、毕业未就业')
    assert '不覆盖更具体的岗位资格' in note
    raw.update(source_record_id='role',campaign_job_ids=['role'],
               description_raw='2027届本科及以上学历',campaign_cohort_raw='2027届及优秀2026届')
    assert '绑定此岗位的官方专项条件：2027届及优秀2026届' in E.qualification_note(raw)


def test_only_definitive_capacity_rejection_can_clear_create_intent():
    import json
    error={'ok':False,'error':{'code':800040832,'subtype':'quota_exceeded'}}
    assert E.quota_rejection(RuntimeError(json.dumps(error)))
    assert not E.quota_rejection(RuntimeError('request timed out'))
    error['error']['code']=500
    assert not E.quota_rejection(RuntimeError(json.dumps(error)))


def test_continuation_is_explicit_allowlisted_and_only_routes_new_software():
    assert E.route('拼多多')[0]==E.S.INTERNET_CONTINUATION
    assert E.route('大疆')[0]==E.S.ORIGINAL_TABLES[2]
    assert E.S.valid_table_selection(E.S.ORIGINAL_TABLES)
    assert E.S.valid_table_selection(E.S.TABLES)
    assert not E.S.valid_table_selection([*E.S.TABLES,'tblUnapproved'])


def test_append_cannot_write_continuation_without_its_backup(tmp_path,monkeypatch):
    import pytest
    monkeypatch.setattr(E,'verified_backup',lambda out:{'tables':dict.fromkeys(E.S.ORIGINAL_TABLES)})
    monkeypatch.setattr(E,'ensure_note_fields',lambda *args: (_ for _ in ()).throw(AssertionError('unbacked schema mutation')))
    with pytest.raises(ValueError,match='complete backup'):
        E.append_p1(tmp_path,tmp_path/'jobs.json')
