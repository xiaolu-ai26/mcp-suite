"""Unit tests for the Alibaba-family headless adapter and the Tencent Music adapter.

Fixtures under ``tests/fixtures/ali_tencent`` are sanitized recordings of the real
public responses captured read-only on 2026-09-18; list fixtures are trimmed to
the fields the parser reads.  No test touches the network: every request goes
through an injected transport.
"""
import json
from pathlib import Path

import pytest

from qiuzhao.collector import alibaba_headless as ali
from qiuzhao.collector import tencent_music as tme
from qiuzhao.collector import p1_pipeline as pipeline

FIX = Path(__file__).parent / 'fixtures' / 'ali_tencent'


def fixture(name):
    return json.loads((FIX / name).read_text(encoding='utf-8'))


def ali_page(rows, total):
    return {'success': True, 'content': {'datas': rows, 'totalCount': total}}


class FakeAliTransport:
    """Routes recorded Alibaba responses; charges a request budget like the real one."""

    def __init__(self, batches=None, conditions=None, pages=None, limit=40, open_error=None):
        self.batches = batches
        self.conditions = conditions
        self.pages = pages or {}
        self.limit = limit
        self.used = 0
        self.open_error = open_error
        self.opened = None
        self.requests = []

    def _charge(self):
        if self.used >= self.limit:
            raise ali.BudgetExhausted(f'request budget {self.limit} reached')
        self.used += 1

    def open(self, url):
        self.opened = url
        self._charge()
        if self.open_error:
            raise self.open_error

    def post_json(self, path, payload):
        self.requests.append((path, payload))
        self._charge()
        if path == '/searchCondition/listBatch':
            return 200, self.batches
        if path == '/searchCondition/list':
            return 200, self.conditions
        if path == '/position/search':
            key = (str(payload['batchId']), payload.get('customDeptCode', ''), payload['pageIndex'])
            if key not in self.pages:
                raise AssertionError(f'unrouted search {key}')
            return 200, self.pages[key]
        raise AssertionError(path)

    def budget(self):
        return {'limit': self.limit, 'used': self.used}


class FakeTmeTransport:
    def __init__(self, types=None, lists=None, limit=40, type_error=None):
        self.types = types
        self.lists = lists or {}
        self.limit = limit
        self.used = 0
        self.type_error = type_error
        self.requests = []

    def _charge(self):
        if self.used >= self.limit:
            raise tme.BudgetExhausted(f'request budget {self.limit} reached')
        self.used += 1

    def get(self, path):
        self.requests.append(('GET', path))
        self._charge()
        if self.type_error:
            raise self.type_error
        return 200, self.types

    def post(self, path, payload):
        self.requests.append(('POST', path, payload))
        self._charge()
        if payload['type'] not in self.lists:
            raise AssertionError(f'unrouted TME type {payload["type"]}')
        return 200, self.lists[payload['type']]

    def budget(self):
        return {'limit': self.limit, 'used': self.used}


# --------------------------------------------------------------------------- #
# Alibaba
# --------------------------------------------------------------------------- #

def test_alibaba_paginates_parses_and_validates(monkeypatch, tmp_path):
    monkeypatch.setattr(ali, 'PAGE_SIZE', 3)
    rows1 = fixture('ali_campus_page1.json')['content']['datas']
    rows2 = fixture('ali_campus_page2.json')['content']['datas']
    transport = FakeAliTransport(
        batches=fixture('ali_batches.json'),
        conditions=fixture('ali_conditions.json'),
        pages={('100000760001', '', 1): ali_page(rows1, 6),
               ('100000760001', '', 2): ali_page(rows2, 6)})
    result = ali.collect('阿里巴巴', 'campus', tmp_path, transport=transport)
    coverage = result['coverage']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['expected_total'] == 6 and coverage['pages_scanned'] == 2
    assert len(result['jobs']) == 6
    assert len({job['source_record_id'] for job in result['jobs']}) == 6
    job = result['jobs'][0]
    assert job['job_title'] and job['description_raw']
    assert job['recruitment_type'] == '校园招聘'
    # The official list never returns publishTime, so the field must stay absent.
    assert 'published_at' not in job
    # No deadline column exists on this platform.
    assert 'deadline' not in job
    assert job['detail_url'].startswith('https://campus-talent.alibaba.com/campus/position-detail?jobId=')
    assert pipeline.validate_result(result, '阿里巴巴', 'campus')


def test_alibaba_dept_filter_uses_official_leaf_codes(monkeypatch, tmp_path):
    monkeypatch.setattr(ali, 'PAGE_SIZE', 3)
    conditions = fixture('ali_conditions.json')
    expected = ','.join(
        c['value'] for node in conditions['content']['searchItems']
        if node['type'] == 'customDept'
        for g in node['items'] if g['label'] == '淘天集团'
        for c in g['children'])
    rows = fixture('ali_taotian_page1.json')['content']['datas']
    transport = FakeAliTransport(
        batches=fixture('ali_batches.json'), conditions=conditions,
        pages={('100000760001', expected, 1): ali_page(rows, 3)})
    result = ali.collect('淘天', 'campus', tmp_path, transport=transport)
    assert result['coverage']['complete'] is True
    assert result['coverage']['dept_match']['label'] == '淘天集团'
    search = [payload for path, payload in transport.requests if path == '/position/search']
    assert search and search[0]['customDeptCode'] == expected
    assert all(job['recruitment_unit'] == '淘天集团' for job in result['jobs'])
    assert pipeline.validate_result(result, '淘天', 'campus')


def test_alibaba_empty_official_total_is_complete(tmp_path):
    empty = fixture('ali_cainiao_empty.json')
    transport = FakeAliTransport(pages={('4000000250', '', 1): empty})
    result = ali.collect('菜鸟', 'campus', tmp_path, transport=transport)
    coverage = result['coverage']
    assert result['jobs'] == []
    assert coverage['expected_total'] == 0
    assert coverage['status'] == 'success' and coverage['complete'] is True
    # batch discovery must not be attempted for the independent Cainiao site
    assert all(path != '/searchCondition/listBatch' for path, _ in transport.requests)
    assert pipeline.validate_result(result, '菜鸟', 'campus')


def test_alibaba_social_is_blocked_without_network(tmp_path):
    transport = FakeAliTransport()
    result = ali.collect('阿里巴巴', 'social', tmp_path, transport=transport)
    assert result['coverage']['status'] == 'blocked'
    assert result['jobs'] == []
    assert transport.requests == [] and transport.opened is None
    assert 'social' in result['coverage']['errors'][0]


def test_alibaba_missing_publish_time_is_not_inferred(monkeypatch, tmp_path):
    monkeypatch.setattr(ali, 'PAGE_SIZE', 3)
    row = {'id': 'NO-DATE', 'name': '测试岗位', 'status': 'recruit',
           'description': '职责', 'requirement': '要求',
           'workLocations': "['杭州']", 'batchName': '阿里巴巴2027届应届生'}
    transport = FakeAliTransport(
        batches=fixture('ali_batches.json'), conditions=fixture('ali_conditions.json'),
        pages={('100000760001', '', 1): ali_page([row], 1)})
    result = ali.collect('阿里巴巴', 'campus', tmp_path, transport=transport)
    job = result['jobs'][0]
    assert 'published_at' not in job and 'deadline' not in job
    assert job['cities'] == ['杭州']
    assert job['campaign_cohort_raw'] == '阿里巴巴2027届应届生'


def test_alibaba_headless_unavailable_is_blocked(tmp_path):
    transport = FakeAliTransport(open_error=ali.HeadlessUnavailable('no chromium'))
    result = ali.collect('高德', 'campus', tmp_path, transport=transport)
    coverage = result['coverage']
    assert coverage['status'] == 'blocked' and result['jobs'] == []
    assert 'headless unavailable' in coverage['errors'][0]


def test_alibaba_budget_exhaustion_keeps_partial_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(ali, 'PAGE_SIZE', 3)
    rows1 = fixture('ali_campus_page1.json')['content']['datas']
    # open + listBatch + first page = 3; the second page trips the cap.
    transport = FakeAliTransport(
        batches=fixture('ali_batches.json'), conditions=fixture('ali_conditions.json'),
        pages={('100000760001', '', 1): ali_page(rows1, 6)}, limit=3)
    result = ali.collect('阿里巴巴', 'campus', tmp_path, transport=transport)
    coverage = result['coverage']
    assert coverage['status'] == 'partial' and coverage['complete'] is False
    assert coverage['request_budget_exhausted'] is True
    assert coverage['request_budget'] == {'limit': 3, 'used': 3}
    assert len(result['jobs']) == 3


def test_alibaba_dept_label_missing_is_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(ali, 'PAGE_SIZE', 3)
    transport = FakeAliTransport(batches=fixture('ali_batches.json'),
                                 conditions={'success': True, 'content': {'searchItems': []}})
    result = ali.collect('阿里云', 'campus', tmp_path, transport=transport)
    assert result['coverage']['status'] == 'blocked'
    assert '阿里云' in result['coverage']['errors'][0]


def test_alibaba_unknown_entity_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        ali.collect('不存在的公司', 'campus', tmp_path, transport=FakeAliTransport())


def test_alibaba_registry_is_append_only(tmp_path):
    registry = ali.merged_registry()
    assert set(registry) == {'阿里巴巴', '淘天', '阿里云', '高德', '饿了么', '菜鸟'}
    assert all(value == ali.MODULE_PATH for value in registry.values())
    for name in registry:
        assert pipeline.REGISTRY[name] == ali.MODULE_PATH
        assert name in pipeline.DEFAULT_COMPANIES


# --------------------------------------------------------------------------- #
# Tencent Music
# --------------------------------------------------------------------------- #

def tme_lists():
    return {'10': fixture('tme_type10_page1.json'),
            '30': fixture('tme_type30_page1.json'),
            '40': fixture('tme_type40_page1.json')}


def test_tme_campus_sums_official_types(tmp_path):
    transport = FakeTmeTransport(types=fixture('tme_types.json'), lists=tme_lists())
    result = tme.collect('腾讯音乐', 'campus', tmp_path, transport=transport)
    coverage = result['coverage']
    # 应届生 33 + 技术大咖 4 = 37, straight from the official dictionary.
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['expected_total'] == 37 and len(result['jobs']) == 37
    assert len({job['source_record_id'] for job in result['jobs']}) == 37
    job = result['jobs'][0]
    assert job['published_at'] == job['source_fields']['date']
    assert job['recruitment_type'] == '校园招聘'
    assert 'deadline' not in job
    assert job['detail_url'].startswith('https://join.tencentmusic.com/campus/detail/?id=')
    assert pipeline.validate_result(result, '腾讯音乐', 'campus')


def test_tme_intern_uses_intern_type_codes(tmp_path):
    lists = tme_lists()
    lists['20'] = fixture('tme_type20_page1.json')
    transport = FakeTmeTransport(types=fixture('tme_types.json'), lists=lists)
    result = tme.collect('腾讯音乐', 'intern', tmp_path, transport=transport)
    coverage = result['coverage']
    assert coverage['complete'] is True
    assert coverage['expected_total'] == 52 + 42
    assert all(job['recruitment_type'] == '实习招聘' for job in result['jobs'])
    codes = {r[2]['type'] for r in transport.requests if r[0] == 'POST'}
    assert codes == {'20', '30'}


def test_tme_social_is_blocked_without_network(tmp_path):
    transport = FakeTmeTransport()
    result = tme.collect('腾讯音乐', 'social', tmp_path, transport=transport)
    assert result['coverage']['status'] == 'blocked' and result['jobs'] == []
    assert transport.requests == []


def test_tme_type_fetch_failure_is_blocked(tmp_path):
    transport = FakeTmeTransport(type_error=TimeoutError('network down'))
    result = tme.collect('腾讯音乐', 'campus', tmp_path, transport=transport)
    coverage = result['coverage']
    assert coverage['status'] == 'blocked' and result['jobs'] == []
    assert 'type dictionary failed' in coverage['errors'][0]


def test_tme_missing_official_type_is_blocked(tmp_path):
    types = {'code': '200', 'data': [{'value': 10, 'label': '应届生', 'num': '33'}]}
    transport = FakeTmeTransport(types=types, lists=tme_lists())
    result = tme.collect('腾讯音乐', 'campus', tmp_path, transport=transport)
    coverage = result['coverage']
    assert coverage['status'] == 'blocked'
    assert '40' in coverage['errors'][0]


def test_tme_budget_exhaustion_keeps_partial_rows(tmp_path):
    transport = FakeTmeTransport(types=fixture('tme_types.json'), lists=tme_lists(), limit=2)
    result = tme.collect('腾讯音乐', 'campus', tmp_path, transport=transport)
    coverage = result['coverage']
    # types + type10 page = 2; the 技术大咖 list request trips the cap.
    assert coverage['status'] == 'partial' and coverage['complete'] is False
    assert coverage['request_budget_exhausted'] is True
    assert coverage['request_budget'] == {'limit': 2, 'used': 2}
    assert len(result['jobs']) == 33


def test_tme_dispatch_and_result_file(tmp_path):
    transport = FakeTmeTransport(types=fixture('tme_types.json'), lists=tme_lists())
    result = tme.collect('腾讯音乐', 'campus', tmp_path, transport=transport)
    assert (tmp_path / 'result.json').exists()
    assert result['coverage']['scope_request']['company'] == '腾讯音乐'
    with pytest.raises(ValueError):
        tme.collect('腾讯', 'campus', tmp_path, transport=transport)


if __name__ == '__main__':
    pytest.main([__file__])
