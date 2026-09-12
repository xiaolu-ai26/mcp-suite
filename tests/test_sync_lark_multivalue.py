import json
from pathlib import Path
import pytest
from qiuzhao.collector import sync_lark_multivalue as S


def fixture_plan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = Path('out'); out.mkdir()
    fields = [{'id': 'f'+str(i), 'name': n, 'type': 'select', 'multiple': False,
               'options': [{'name': '2027届', 'hue': 'Red', 'lightness': 'Lighter'}], 'default_value': None}
              for i,n in enumerate(S.TARGETS)]
    backup = {'base': S.BASE, 'tables': {}}
    for table in S.TABLES:
        records = out/(table+'.records.json'); schema = out/(table+'.fields.json')
        S.save(records, [{'record_id': 'known', 'job_id': 'job-a', '毕业届别': ['2027届'],
                          '专业': ['未披露'], '工作地点': ['北京'], '备注': 'keep'},
                         {'record_id': 'unmatched', 'job_id': 'not-found'}])
        S.save(schema, fields)
        backup['tables'][table] = {'records':str(records),'schema':str(schema),
            'records_sha256':S.digest(records),'schema_sha256':S.digest(schema),'rev':1}
    S.save(out/'backup.json',backup)
    jobs=Path('jobs.json');S.save(jobs,[{'id':'job-a','cohort_raw':'2026届、2027届',
        'recruitment_type':'校园招聘','cities':['北京','上海'],
        'major_requirements_raw':'计算机科学、电子信息','major_normalized':'计算机类'}])
    return out,jobs


def test_plan_multiselect_only_and_preserves_unmatched(tmp_path, monkeypatch):
    out,jobs=fixture_plan(tmp_path,monkeypatch)
    plan=S.make_plan(out,jobs)
    for table in plan['tables'].values():
        assert set(table['updates'])=={'known'}
        assert set(table['updates']['known'])==set(S.TARGETS)
        assert table['updates']['known']['毕业届别']==['2027届','2026届']
        assert table['updates']['known']['专业']==['计算机类','电子信息类']
        assert table['unmatched'][0]['record_id']=='unmatched'
        assert all(x['definition']['multiple'] for x in table['schema_updates'])
        assert table['schema_updates'][0]['definition']['options'][0]['hue']=='Red'


def test_conflicting_job_ids_are_not_written(tmp_path,monkeypatch):
    out,jobs=fixture_plan(tmp_path,monkeypatch)
    raw=json.loads(jobs.read_text());raw.append(dict(raw[0],cohort_raw='2028届'));S.save(jobs,raw)
    plan=S.make_plan(out,jobs)
    assert all(not t['updates'] for t in plan['tables'].values())


def test_backup_tamper_and_live_revision_drift_fail_before_write(tmp_path,monkeypatch):
    out,jobs=fixture_plan(tmp_path,monkeypatch);plan=S.make_plan(out,jobs)
    calls=[]
    def cli(*args):
        calls.append(args)
        return {'data':{'tables':[{'id':t,'rev':2} for t in S.TABLES]}}
    monkeypatch.setattr(S,'cli',cli)
    with pytest.raises(ValueError,match='changed after backup'):S.apply_plan(out)
    assert [c[0] for c in calls]==['+table-list']
    Path(plan['tables'][S.TABLES[0]]['backup']['records']).write_text('[]')
    with pytest.raises(ValueError,match='backup integrity'):S.make_plan(out,jobs)


def test_changed_target_value_blocks_but_idempotent_replay_is_allowed():
    old={'r':{'毕业届别':['2027届']}}
    desired={'r':{'毕业届别':['2027届','2026届']}}
    S.assert_current_values(old,old,desired)
    S.assert_current_values(desired,old,desired)
    with pytest.raises(ValueError,match='changed after backup'):
        S.assert_current_values({'r':{'毕业届别':['2028届']}},old,desired)
    with pytest.raises(ValueError,match='record missing'):
        S.assert_current_values({},old,desired)
