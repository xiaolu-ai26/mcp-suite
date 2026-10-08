"""Offline public contract replay; representative fixture is not a full snapshot."""
import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from qiuzhao.collector import chinahr_public as C
from qiuzhao.collector import run as R

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/banks/boc_chinahr_representative.json').read_text(encoding='utf-8'))


def bootstrap(nodes=None):
    nodes = nodes or FIXTURE['nodes']
    config = {'jobs': {'token': 'offline-selector', 'firstId': nodes[0]['id'], 'show': True},
              'gonggao': [{'tabs': [{'title': R.BOC_CONDITIONS_TITLE, 'content': FIXTURE['conditions']}]}]}
    return R.BOC_CAMPAIGN_NAME + '<script>window.chinahr_cmp_json_data=' + json.dumps(config, ensure_ascii=False) + ';</script>'


def response(rows, total=None):
    return C.CALLBACK + '(' + json.dumps({'code': 1, 'retMsg': rows, 'totalCount': len(rows) if total is None else total}, ensure_ascii=False) + ');'


def replay(tmp_path, *, pages=None, nodes=None):
    collector = R.Collector(tmp_path, delay=0)
    nodes = nodes or copy.deepcopy(FIXTURE['nodes'])
    pages = pages or [response([copy.deepcopy(FIXTURE['job'])])]
    calls = []
    def fetch(url, *_):
        calls.append(url)
        if url == R.BOC_CAMPAIGN_PAGE:
            return bootstrap(nodes)
        parsed = urlsplit(url)
        params = parse_qs(parsed.query)
        if parsed.path.endswith('company/list'):
            return response(nodes)
        assert parsed.path.endswith('job/list')
        page = int(params['page'][0])
        value = pages(params) if callable(pages) else pages[page - 1]
        if isinstance(value, Exception):
            raise value
        return value
    collector.fetch = fetch
    jobs, state = C.collect_campaign(collector, page_url=R.BOC_CAMPAIGN_PAGE,
        campaign=R.BOC_CAMPAIGN_NAME, conditions_title=R.BOC_CONDITIONS_TITLE, group='中国银行股份有限公司')
    return collector, jobs, state, calls


def test_native_sample_embedded_content_and_parent_unit(tmp_path):
    collector, jobs, state, calls = replay(tmp_path)
    assert state['complete'] and state['status'] == 'success'
    job = jobs[0]
    assert job['source_record_id'] == '6a8ee5893f91030978ec0aab'
    assert job['job_no'] == 'Z0231'
    assert job['recruiting_unit_raw'] == '总行部门'
    assert job['job_category'] == '管理培训生（信息科技）'
    assert job['cities'] == ['北京']
    assert job['education_summary_raw'] == '本科'
    assert '大学本科及以上学历' in job['education_raw']
    assert '网络安全' in job['major_requirements_raw']
    assert job['deadline'] == '2026-10-09'
    assert '国家大学英语六级' in job['description_raw']
    assert '网络安全' in job['description_raw']
    assert '管理培训生（风险合规）岗位主要招收' not in job['description_raw']
    assert len(calls) == 3
    assert not any('/job/detail/' in x for x in calls)
    for file in collector.evidence.iterdir():
        assert 'offline-selector' not in file.read_text(encoding='utf-8')


def test_unknown_branch_does_not_inherit_hq_conditions(tmp_path):
    nodes = copy.deepcopy(FIXTURE['nodes']); next(x for x in nodes if x['name'] == '总行部门')['name'] = '未知分行'
    _, jobs, state, _ = replay(tmp_path, nodes=nodes)
    assert state['listing_complete'] and not state['complete']
    assert jobs[0]['description_raw'].startswith('职位介绍：')
    assert '国家大学英语六级' not in jobs[0]['description_raw']
    assert '需核验' in jobs[0]['detail_presentation']


@pytest.mark.parametrize('later', [response([], 2), response([FIXTURE['job']], 2),
                                 response([], 3), TimeoutError('offline failure')])
def test_partial_pages_keep_valid_roles_without_complete(tmp_path, later):
    _, jobs, state, _ = replay(tmp_path, pages=[response([FIXTURE['job']], 2), later])
    assert len(jobs) == 1
    assert not state['complete'] and state['errors']


@pytest.mark.parametrize('bad', [None, {}, {'id': {}}, {'id': True}])
def test_bad_rows_no_false_complete(tmp_path, bad):
    _, jobs, state, _ = replay(tmp_path, pages=[response([bad], 1)])
    assert not jobs and not state['complete'] and state['errors']


def test_page_two_native_id_and_total(tmp_path):
    other = copy.deepcopy(FIXTURE['job']); other['id'] = 'second-id'; other['jobNo'] = 'Z0232'
    _, jobs, state, calls = replay(tmp_path, pages=[response([FIXTURE['job']], 2), response([other], 2)])
    assert state['complete'] and len(jobs) == 2 and len(calls) == 4


@pytest.mark.parametrize('raw', ['other({"code":1});', C.CALLBACK+'({"code":1});evil()', C.CALLBACK+'([]);'])
def test_jsonp_never_evaluates_extra_script(raw):
    with pytest.raises(ValueError):
        C.jsonp(raw)


def test_old_announcement_id_not_removed_on_native_complete(tmp_path, monkeypatch):
    old = R.base_job('boc-stable-announcement', '中国银行股份有限公司', '信息科技岗位', 'https://www.boc.cn/', R.now())
    old.update(record_kind='announcement_explicit_role', status='open')
    stale = R.base_job('boc-ats-old-native', '中国银行股份有限公司', '旧岗位', 'https://campus.chinahr.com/', R.now())
    (tmp_path/'jobs.json').write_text(json.dumps([old, stale], ensure_ascii=False))
    collector = R.Collector(tmp_path, delay=0)
    def source():
        collector.states['boc'] = {'status':'success', 'complete':True}
        return [R.base_job('boc-ats-new', old['recruitment_unit'], '新岗位', old['source_url'], R.now())]
    monkeypatch.setattr(collector, 'boc', source)
    assert collector.run('boc', 0) == 0
    jobs = {x['id']:x for x in json.loads((tmp_path/'jobs.json').read_text(encoding='utf-8'))}
    assert jobs[old['id']]['status'] != 'removed'
    assert jobs[stale['id']]['status'] == 'removed'


def test_real_announcement_fourteen_stable_roles_and_partial_native(tmp_path):
    collector = R.Collector(tmp_path, delay=0)
    announcement = (Path(__file__).parent/'fixtures/banks/boc_announcement_roles.txt').read_text(encoding='utf-8')
    collector.fetch = lambda *_: announcement
    old = collector.boc_announcements()
    assert len(old) == 14
    expected_ids = {x['id'] for x in old}
    assert all(x['record_kind'] == 'announcement_explicit_role' for x in old)
    assert not collector.states['boc']['complete']
    def fetch(url, *_):
        if 'www.boc.cn' in url:
            return announcement
        if url == R.BOC_CAMPAIGN_PAGE:
            return bootstrap()
        if '/company/list' in url:
            return response(FIXTURE['nodes'])
        raise TimeoutError('offline listing interrupted')
    collector.fetch = fetch
    rows = collector.boc()
    assert {x['id'] for x in rows} == expected_ids
    assert collector.states['boc']['status'] == 'partial'
    assert not collector.states['boc']['complete']
    assert collector.states['boc']['native_directory']['errors']


def test_failure_receipt_does_not_leak_project_selector(tmp_path):
    _, jobs, state, _ = replay(tmp_path, pages=[TimeoutError('https://ats.chinahr.com/?token=offline-selector')])
    assert not jobs and not state['complete']
    assert 'offline-selector' not in json.dumps(state)


@pytest.mark.parametrize('data', [
    {'code': 1, 'retMsg': {}, 'totalCount': 0},
    {'code': 1, 'retMsg': [], 'totalCount': True},
    {'code': 1, 'retMsg': [], 'totalCount': 1},
    {'code': 1, 'retMsg': []},
])
def test_invalid_or_premature_empty_listing_not_complete(tmp_path, data):
    _, jobs, state, _ = replay(tmp_path, pages=[C.CALLBACK+'('+json.dumps(data)+');'])
    assert not jobs and not state['complete'] and state['errors']


@pytest.mark.parametrize('field,value', [('id', []), ('jobDesc', {}), ('education', {}),
                                        ('workPlaceList', {}), ('applyEndTime', True)])
def test_native_typed_fields_fail_closed(tmp_path, field, value):
    job = copy.deepcopy(FIXTURE['job']); job[field] = value
    _, jobs, state, _ = replay(tmp_path, pages=[response([job])])
    assert not jobs and not state['complete'] and state['errors']


def test_positive_total_failure_retains_original_denominator(tmp_path):
    _, jobs, state, _ = replay(tmp_path, pages=[response([FIXTURE['job']], 2), response([], 2)])
    assert len(jobs) == 1
    assert state['scopes'][0]['expected_total'] == 2
    assert state['scopes'][0]['observed_unique_ids'] == 1
    assert not state['scopes'][0]['complete']


def test_orphan_metadata_not_complete(tmp_path):
    nodes = copy.deepcopy(FIXTURE['nodes']); nodes[-1]['parentId'] = 'unknown-parent'
    _, jobs, state, _ = replay(tmp_path, nodes=nodes)
    assert not jobs and not state['complete'] and state['errors']


def test_valid_empty_native_selector_is_complete(tmp_path):
    _, jobs, state, _ = replay(tmp_path, pages=[response([], 0)])
    assert not jobs and state['complete']
    assert state['scopes'][0]['expected_total'] == 0


@pytest.mark.parametrize('conflict', [False, True])
def test_cross_selector_native_identity_dedup_or_conflict(tmp_path, conflict):
    nodes = copy.deepcopy(FIXTURE['nodes'])
    second = next(x['id'] for x in nodes if x['name'] == '总行部门')
    nodes.append({'id':'another-leaf', 'parentId':second, 'name':'另一个公开岗位类别'})
    def page(params):
        value = copy.deepcopy(FIXTURE['job'])
        value['companyId'] = params['companyId'][0]
        if conflict and value['companyId'] == 'another-leaf':
            value['jobDesc'] += '新职责'
        return response([value])
    _, jobs, state, calls = replay(tmp_path, nodes=nodes, pages=page)
    assert len(jobs) == 1
    assert len(state['scopes']) == 2 and len(calls) == 4
    assert state['complete'] is (not conflict)
    assert bool(state['errors']) is conflict


@pytest.mark.parametrize('title', ['管理培训生', '未知专门岗位'])
def test_actual_collect_generic_or_unknown_role_conditions_are_partial(tmp_path, title):
    value = copy.deepcopy(FIXTURE['job']); value['name'] = title
    _, jobs, state, _ = replay(tmp_path, pages=[response([value])])
    assert len(jobs) == 1 and not state['complete']
    assert not jobs[0]['detail_complete']
    assert '需核验' in jobs[0]['detail_presentation']
    assert '国家大学英语六级' not in jobs[0]['description_raw']
    assert R.BOC_CONDITIONS_TITLE in jobs[0]['description_raw']


def test_actual_collect_duplicate_unit_header_is_partial(tmp_path, monkeypatch):
    lines = list(FIXTURE['conditions'])
    pos = next(i for i,x in enumerate(lines) if x.startswith('&三'))
    lines[pos:pos] = ['（十）总行部门岗位', '1．大学本科及以上学历。',
                     '管理培训生（信息科技）岗位主要招收计算机专业毕业生；']
    monkeypatch.setitem(FIXTURE, 'conditions', lines)
    _, jobs, state, _ = replay(tmp_path)
    assert len(jobs) == 1 and not state['complete']
    assert '唯一匹配' in jobs[0]['detail_presentation']


def test_old_fourteen_role_kind_is_explained_in_real_public_projection(tmp_path):
    from datetime import date
    from qiuzhao.v4_fields import to_item
    from qiuzhao.tools import Jobs
    collector = R.Collector(tmp_path, delay=0)
    collector.fetch = lambda *_: (Path(__file__).parent/'fixtures/banks/boc_announcement_roles.txt').read_text(encoding='utf-8')
    rows = collector.boc_announcements()
    assert len(rows) == 14
    for row in rows:
        public = Jobs.public(to_item(row), date(2026,10,9))
        assert '公告' in public['detail_presentation']
        assert '岗位类别' in public['detail_presentation']
        assert '原生具体岗位' in public['status_note']
        assert public['id'] == row['id']
