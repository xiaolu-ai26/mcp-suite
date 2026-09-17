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
    assert table==E.S.MANUFACTURING_CONTINUATION
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
    assert E.route('大疆')[0]==E.S.MANUFACTURING_CONTINUATION
    assert E.S.valid_table_selection(E.S.ORIGINAL_TABLES)
    assert E.S.valid_table_selection(E.S.TABLES)
    assert not E.S.valid_table_selection([*E.S.TABLES,'tblUnapproved'])


def test_append_cannot_write_continuation_without_its_backup(tmp_path,monkeypatch):
    import pytest
    monkeypatch.setattr(E,'verified_backup',lambda out:{'tables':dict.fromkeys(E.S.ORIGINAL_TABLES)})
    monkeypatch.setattr(E,'ensure_note_fields',lambda *args: (_ for _ in ()).throw(AssertionError('unbacked schema mutation')))
    with pytest.raises(ValueError,match='complete backup'):
        E.append_p1(tmp_path,tmp_path/'jobs.json')


def test_source_status_sync_backs_up_and_preserves_human_states(tmp_path,monkeypatch):
    import json
    table=E.S.ORIGINAL_TABLES[0];records=tmp_path/'records.json'
    records.write_text(json.dumps([{'record_id':'r1','job_id':'j1'},{'record_id':'r2','job_id':'j2'}]))
    jobs=tmp_path/'jobs.json';jobs.write_text(json.dumps([{'id':j,'p1_company':'大疆','status':'expired','source_is_active':False,'source_status_raw':'pause','source_status_evidence':{'list_status':'pause'}} for j in ['j1','j2']]))
    monkeypatch.setattr(E,'verified_backup',lambda out:{'tables':{table:{'records':str(records)}}})
    monkeypatch.setattr(E.S,'full_fields',lambda t:[{'name':'状态','type':'select','options':[{'name':v} for v in ['open','expired','unverified','已投递']]}])
    updates=[]
    def cli(*args):
        if args[0]=='+record-get':
            path=Path(args[args.index('--output')+1]);path=E.S.ROOT/path if not path.is_absolute() else path
            ids=json.loads(args[args.index('--json')+1])['record_id_list']
            path.write_text('\n'.join(json.dumps({'record_id':rid,'job_id':'j1' if rid=='r1' else 'j2','状态':['open' if rid=='r1' else '已投递']}) for rid in ids))
            return {}
        body=Path(args[args.index('--json')+1][1:]);body=E.S.ROOT/body if not body.is_absolute() else body
        updates.append(json.loads(body.read_text()));return {'data':{}}
    from pathlib import Path
    monkeypatch.setattr(E.S,'rel',lambda p:str(p))
    monkeypatch.setattr(E.S,'cli',cli)
    E.status_sync(tmp_path,jobs)
    assert updates==[{'update_records':{'r1':{'状态':['expired']}}}]
    result=json.loads((tmp_path/'source-status-sync.json').read_text())
    assert result['changed']==1 and len(result['human_values_preserved'])==1


def test_bare_or_inconsistent_active_flag_cannot_change_base_status():
    assert E.source_lifecycle_state({'source_is_active':True,'status':'open'}) is None
    row={'source_is_active':True,'status':'open','source_status_raw':'pause','source_status_evidence':{'list_status':'pause'}}
    assert E.source_lifecycle_state(row) is None
    row.update(source_is_active=False,status='expired')
    assert E.source_lifecycle_state(row)=='expired'


def test_url_field_markdown_echo_with_same_target_is_not_a_difference():
    old={'原链接':'[https://a.b/c](https://a.b/c)'}
    desired={'原链接':'https://a.b/c'}
    assert E.business_delta(old,desired,{'原链接':'url'})=={}


def test_url_field_markdown_echo_with_different_target_is_a_difference():
    old={'原链接':'[https://a.b/c](https://a.b/c)'}
    desired={'原链接':'https://a.b/d'}
    assert E.business_delta(old,desired,{'原链接':'url'})=={'原链接':'https://a.b/d'}


def test_url_field_link_object_and_list_echo_forms_normalize_the_same():
    desired={'原链接':'https://a.b/c'}
    assert E.business_delta({'原链接':{'link':'https://a.b/c','text':'a.b/c'}},desired,{'原链接':'url'})=={}
    assert E.business_delta({'原链接':[{'link':'https://a.b/c','text':'a.b/c'}]},desired,{'原链接':'url'})=={}
    assert E.business_delta({'原链接':['[https://a.b/c](https://a.b/c)']},desired,{'原链接':'url'})=={}


def test_url_field_empty_old_value_is_a_difference():
    assert E.business_delta({},{'原链接':'https://a.b/c'},{'原链接':'url'})=={'原链接':'https://a.b/c'}
    assert E.business_delta({'原链接':''},{'原链接':'https://a.b/c'},{'原链接':'url'})=={'原链接':'https://a.b/c'}


def test_plain_text_field_with_markdown_looking_content_is_not_normalized_as_url():
    old={'岗位描述':'[x](y)'}
    desired={'岗位描述':'[x](y)'}
    assert E.business_delta(old,desired,{'岗位描述':'text'})=={}
    assert E.business_delta(old,{'岗位描述':'[a](b)'},{'岗位描述':'text'})=={'岗位描述':'[a](b)'}


def test_link_field_is_url_aware_even_when_live_schema_type_is_text():
    # 2026-09-17 production schema check: 原链接/投递入口 are declared as plain
    # 'text' fields on every table (Feishu auto-linkifies a bare url typed into
    # a text cell and echoes it back as markdown on read), not the dedicated
    # 'url' field type. Field name membership, not schema type, must drive
    # normalization for these two fields — this is the actual bug scenario.
    old={'原链接':'[https://a.b/c](https://a.b/c)','投递入口':'[https://a.b/c](https://a.b/c)'}
    desired={'原链接':'https://a.b/c','投递入口':'https://a.b/c'}
    assert E.business_delta(old,desired,{'原链接':'text','投递入口':'text'})=={}
    assert E.business_delta(old,desired)=={}  # field_types omitted entirely, matching name fallback alone


def test_multiselect_field_comparison_is_unaffected_by_url_awareness():
    old={'岗位大类':['技术']};desired={'岗位大类':['技术','产品']}
    assert E.business_delta(old,desired,{'岗位大类':'select'})=={'岗位大类':['技术','产品']}
    assert E.business_delta(old,{'岗位大类':['技术']},{'岗位大类':'select'})=={}
