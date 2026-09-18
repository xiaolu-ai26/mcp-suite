"""Unit tests for the bank-specific adapters (batch 1).

Fixtures under ``tests/fixtures/banks`` are sanitized recordings of the real
public responses captured on 2026-09-18; list fixtures are trimmed to the fields
the parser reads and to <= 200 rows. No test touches the network: every request
goes through an injected transport.
"""
import json
from pathlib import Path

import pytest

from qiuzhao.collector import p1_banks_01 as banks
from qiuzhao.collector import p1_pipeline as pipeline

FIX = Path(__file__).parent / 'fixtures' / 'banks'


def fixture(name):
    return json.loads((FIX / name).read_text(encoding='utf-8'))


class FakeResponse:
    def __init__(self, payload, status=200, content=None):
        self._payload = payload
        self.status_code = status
        self.content = content if content is not None else json.dumps(payload).encode('utf-8')

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


def client_for(router, max_requests=None):
    return banks.make_client(interval=0, max_requests=max_requests,
                             session=object(), transport=router)


def test_citic_campus_paginates_and_parses(tmp_path):
    page1, page2 = fixture('citic_campus_page1.json'), fixture('citic_campus_page2.json')

    def router(method, url, **kwargs):
        assert method == 'POST' and url.endswith('/recruitportal/portal/recruitQuery')
        assert kwargs['json']['recruitmentType'] == '02'
        return FakeResponse(page1 if kwargs['json']['page'] == 1 else page2)

    result = banks.collect_citic('citic', 'campus', tmp_path, client=client_for(router))
    coverage = result['coverage']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['expected_total'] == 20 and coverage['pages_scanned'] == 2
    assert len(result['jobs']) == 20
    # Every row keeps a unique official ID and a real detail URL.
    assert len({job['source_record_id'] for job in result['jobs']}) == 20
    assert all(job['detail_url'].startswith('https://job.citicbank.com/') for job in result['jobs'])
    job = result['jobs'][0]
    assert job['job_title'] and job['description_raw']
    assert job['recruitment_type'] == '校园招聘'
    # published_at comes from the official FBZWDATE field, never invented.
    assert job['published_at'] == '2026-09-01'
    # CITIC's list has no deadline column, so the field must stay absent.
    assert 'deadline' not in job
    assert pipeline.validate_result(result, '中信银行', 'campus')


def test_citic_intern_is_blocked(tmp_path):
    result = banks.collect_citic('citic', 'intern', tmp_path,
                                 client=client_for(lambda *a, **k: FakeResponse({})))
    assert result['coverage']['status'] == 'blocked'
    assert result['jobs'] == []
    assert '实习频道' in result['coverage']['errors'][0]


def test_cmb_campus_paginates_and_enriches_detail(tmp_path):
    page1, page2 = fixture('cmb_campus_page1.json'), fixture('cmb_campus_page2.json')
    detail = fixture('cmb_campus_detail.json')

    def router(method, url, **kwargs):
        if url.endswith('/job/getList'):
            return FakeResponse(page1 if kwargs['json']['pageIndex'] == 1 else page2)
        if url.endswith('/job/getDetail'):
            return FakeResponse(detail)
        raise AssertionError(url)

    result = banks.collect_cmb('cmb', 'campus', tmp_path, client=client_for(router))
    coverage = result['coverage']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert len(result['jobs']) == 6 and coverage['pages_scanned'] == 2
    job = next(j for j in result['jobs'] if j['source_record_id'] == detail['body']['publishGID'])
    assert '任职要求' in job['description_raw']
    assert job['deadline'] == '2026-10-10'
    assert job['detail_url'].startswith('https://career.cmbchina.com/')
    # CMB never returns a publish timestamp, so it must stay empty.
    assert 'published_at' not in job
    assert pipeline.validate_result(result, '招商银行', 'campus')


def test_cmb_missing_fields_are_not_inferred(tmp_path):
    list_payload = {'returnCode': 'SUC0000', 'errorMsg': None, 'body': {
        'total': 1, 'data': [{'publishGID': 'NO-DEADLINE', 'jobDisplay': '测试岗位',
                              'branchCode': '1', 'branchCodeName': '某分行',
                              'locationName': '某市'}]}}
    detail_payload = {'returnCode': 'SUC0000', 'errorMsg': None, 'body': {
        'publishGID': 'NO-DEADLINE', 'jobDisplay': '测试岗位',
        'jobResponsibility': '<p>职责</p>', 'jobRequirement': '<p>要求</p>',
        'branchCodeName': '某分行', 'locationName': '某市'}}

    def router(method, url, **kwargs):
        return FakeResponse(list_payload if url.endswith('/getList') else detail_payload)

    result = banks.collect_cmb('cmb', 'campus', tmp_path, client=client_for(router))
    job = result['jobs'][0]
    assert 'deadline' not in job and 'published_at' not in job
    assert job['cohort_raw'] == ''


def test_cmb_intern_is_blocked(tmp_path):
    result = banks.collect_cmb('cmb', 'intern', tmp_path,
                               client=client_for(lambda *a, **k: FakeResponse({})))
    assert result['coverage']['status'] == 'blocked'
    assert '实习频道' in result['coverage']['errors'][0]


def test_bocom_campus_paginates_and_parses(tmp_path):
    page1, page2 = fixture('bocom_campus_page1.json'), fixture('bocom_campus_page2.json')
    calls = {'n': 0}

    def router(method, url, **kwargs):
        assert 'querySocietyRecruitInfo.do' in url
        assert 'engageType' in kwargs['data'].decode('utf-8')
        calls['n'] += 1
        return FakeResponse(page1 if calls['n'] == 1 else page2)

    result = banks.collect_bocom('bocom', 'campus', tmp_path, client=client_for(router))
    coverage = result['coverage']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert len(result['jobs']) == 55 and coverage['pages_scanned'] == 2
    job = result['jobs'][0]
    assert job['job_title'] and job['description_raw']
    assert job['published_at'] and job['deadline']
    assert job['recruitment_unit']
    assert '/#/school/recruitmentInfo/' in job['detail_url']
    assert pipeline.validate_result(result, '交通银行', 'campus')


def test_bocom_intern_is_blocked(tmp_path):
    result = banks.collect_bocom('bocom', 'intern', tmp_path,
                                 client=client_for(lambda *a, **k: FakeResponse({})))
    assert result['coverage']['status'] == 'blocked'
    assert '实习频道' in result['coverage']['errors'][0]


def test_icbc_is_blocked_with_login_evidence(tmp_path):
    posttypes = fixture('icbc_posttypes.json')
    blocked = fixture('icbc_postlist_blocked.json')
    user = fixture('icbc_userinfo_blocked.json')

    def router(method, url, **kwargs):
        if url.endswith('/post/qryPostType'):
            return FakeResponse(posttypes)
        if url.endswith('/post/qryPostList'):
            return FakeResponse(blocked)
        if url.endswith('/api/userInfo'):
            return FakeResponse(user)
        raise AssertionError(url)

    result = banks.collect_icbc('icbc', 'campus', tmp_path, client=client_for(router))
    coverage = result['coverage']
    assert coverage['status'] == 'blocked' and result['jobs'] == []
    assert coverage['channel_probe']['list_retCode'] == '90'
    assert coverage['channel_probe']['userinfo_retCode'] == 'TOKEN_001'
    assert 'token' in coverage['errors'][0]


def test_abc_is_blocked_with_encryption_evidence(tmp_path):
    def router(method, url, **kwargs):
        return FakeResponse({}, content=b'<html>entry</html>')

    result = banks.collect_abc('abc', 'campus', tmp_path, client=client_for(router))
    coverage = result['coverage']
    assert coverage['status'] == 'blocked' and result['jobs'] == []
    assert 'RSA' in coverage['errors'][0] or '加密' in coverage['errors'][0]
    assert coverage['channel_probe']['request_helper'] == 'fetchPost'


def test_request_budget_stops_politely_and_keeps_partial_rows(tmp_path):
    page1 = fixture('cmb_campus_page1.json')
    detail = fixture('cmb_campus_detail.json')
    seen = []

    def router(method, url, **kwargs):
        seen.append(url)
        return FakeResponse(page1 if url.endswith('/getList') else detail)

    client = banks.make_client(interval=0, max_requests=1, session=object(), transport=router)
    result = banks.collect_cmb('cmb', 'campus', tmp_path, client=client)
    coverage = result['coverage']
    assert coverage['request_budget'] == {'limit': 1, 'used': 1}
    assert coverage['request_budget_exhausted'] is True
    assert coverage['status'] == 'partial' and coverage['complete'] is False
    assert len(seen) == 1 and len(result['jobs']) == 5


def test_collect_dispatches_by_chinese_name(tmp_path):
    page1, page2 = fixture('citic_campus_page1.json'), fixture('citic_campus_page2.json')

    def router(method, url, **kwargs):
        return FakeResponse(page1 if kwargs['json']['page'] == 1 else page2)

    client = banks.make_client(interval=0, session=object(), transport=router)
    # collect() builds its own client; patch make_client for the dispatch check.
    import unittest.mock as mock
    with mock.patch.object(banks, 'make_client', return_value=client):
        result = banks.collect('中信银行', 'campus', tmp_path)
    assert len(result['jobs']) == 20
    assert result['coverage']['status'] == 'success'
    assert (tmp_path / 'result.json').exists()


def test_banks_register_without_moving_hardcoded_ordinals():
    for name in banks.COMPANIES.values():
        assert name in pipeline.REGISTRY
        assert pipeline.REGISTRY[name] == 'qiuzhao.collector.p1_banks_01'
        assert name in pipeline.DEFAULT_COMPANIES
        assert name not in pipeline.COMPANIES
    # The hardcoded 50 keep their exact approved order.
    assert pipeline.DEFAULT_COMPANIES[:len(pipeline.COMPANIES)] == pipeline.COMPANIES
    # Bank companies keep their relative order as one block; later appended
    # platform blocks (config-driven Feishu) may follow them.
    bank_names = set(banks.COMPANIES.values())
    assert list(banks.COMPANIES.values()) == [n for n in pipeline.DEFAULT_COMPANIES
                                              if n in bank_names]


def test_unknown_company_and_scope_raise():
    with pytest.raises(ValueError):
        banks.collect('不存在的银行', 'campus', Path('/tmp/nope'))
    with pytest.raises(ValueError):
        banks.collect('中信银行', 'unknown', Path('/tmp/nope'))


def test_complete_result_passes_validate_with_evidence_dir(tmp_path):
    """Guards the pipeline contract: a complete result must ship evidence_files."""
    page1, page2 = fixture('citic_campus_page1.json'), fixture('citic_campus_page2.json')

    def router(method, url, **kwargs):
        return FakeResponse(page1 if kwargs['json']['page'] == 1 else page2)

    result = banks.collect_citic('citic', 'campus', tmp_path, client=client_for(router))
    validated = pipeline.validate_result(result, '中信银行', 'campus', tmp_path)
    assert validated['coverage']['status'] == 'success'
    assert validated['coverage']['evidence_files']
