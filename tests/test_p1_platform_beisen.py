"""Fixture tests for the generic Beisen (zhiye.com) platform adapter.

Parsing and budget only: the HTTP session is a recorded-response fake, so the
suite never touches a zhiye.com tenant.
"""
import json
from pathlib import Path
from unittest.mock import patch

from qiuzhao.collector import p1_platform_beisen as beisen
from qiuzhao.collector import p1_platform_moka as moka

FIXTURES = Path(__file__).parent / 'fixtures' / 'platform'


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def entry_html(name='beisen_entry.html'):
    return (FIXTURES / name).read_text(encoding='utf-8')


class FakeResponse:
    def __init__(self, payload=None, text='', url='https://csc108.zhiye.com/', status=200):
        self._payload = payload
        self.text = text
        self.url = url
        self.status_code = status
        self.encoding = 'utf-8'

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError('http ' + str(self.status_code))


class FakeSession:
    def __init__(self, text, pages):
        self.text = text
        self.pages = pages
        self.headers = {}

    def get(self, url, **kwargs):
        if 'GetJobAdInfo' in url:
            return FakeResponse(payload=fixture('beisen_detail.json'))
        return FakeResponse(text=self.text)

    def post(self, url, **kwargs):
        index = int((kwargs.get('json') or {}).get('PageIndex', 0))
        payload = self.pages.get(index, {'Code': 200, 'Count': len(self.pages), 'Data': []})
        return FakeResponse(payload=payload)


def run(company, pages, text=None, max_requests=20):
    session = FakeSession(text if text is not None else entry_html(), pages)
    with patch.object(beisen, '_make_session', return_value=session):
        return beisen.collect(company, 'campus', run.tmp, max_requests=max_requests)


def test_pagination_field_mapping_and_empty_fields(tmp_path):
    run.tmp = tmp_path
    pages = {0: fixture('beisen_list_page0.json'), 1: fixture('beisen_list_page1.json')}
    result = run('中信建投', pages)
    coverage = result['coverage']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['expected_total'] == 2 and coverage['pagination_exhausted'] is True
    by_id = {job['source_record_id']: job for job in result['jobs']}
    assert set(by_id) == {'job-campus-1', 'job-campus-2'}
    first = by_id['job-campus-1']
    assert first['published_at'] == '2026-08-31'
    assert first['deadline_raw'] == '2026-10-12'
    assert first['cohort_raw'] == ''            # no cohort inferred from requirement text
    assert first['cities'] == ['北京', '上海']
    assert first['recruitment_type'] == '校园招聘'
    # The second campus row carries no list description, so its official detail is fetched.
    second = by_id['job-campus-2']
    assert '风险管理' in second['description_raw']
    assert second['published_at'] == '2026-09-01'
    assert second['deadline_raw'] == ''          # 2222 sentinel is not a real deadline
    assert second['source_updated_at'] == '2026-09-02'


def test_unknown_official_category_is_not_a_zero_success(tmp_path):
    run.tmp = tmp_path
    row = {'Id': 'unknown-1', 'JobAdName': '未知分类岗位', 'CategoryId': '9',
           'Category': '神秘计划', 'Duty': '职责', 'Require': '要求'}
    pages = {0: {'Code': 200, 'Count': 1, 'Data': [row]}, 1: {'Code': 200, 'Count': 1, 'Data': []}}
    result = run('中信建投', pages)
    coverage = result['coverage']
    assert coverage['complete'] is False
    assert coverage['status'] == 'blocked'
    assert coverage['unmapped_categories'] == {'9': '神秘计划'}
    assert any('Unknown official Beisen category 9' in error for error in coverage['errors'])


def test_waf_challenge_without_portal_id_blocks(tmp_path):
    run.tmp = tmp_path
    result = run('中信建投', {0: {'Code': 200, 'Count': 0, 'Data': []}},
                 text=entry_html('beisen_entry_no_portal.html'))
    assert result['jobs'] == []
    assert result['coverage']['status'] == 'blocked'
    assert any('PortalId' in error for error in result['coverage']['errors'])


def test_request_budget_stops_pagination(tmp_path):
    run.tmp = tmp_path
    pages = {0: fixture('beisen_list_page0.json'), 1: fixture('beisen_list_page1.json')}
    result = run('中信建投', pages, max_requests=2)
    coverage = result['coverage']
    assert coverage['request_budget_exhausted'] is True
    assert coverage['complete'] is False
    assert coverage['request_budget']['used'] <= 2


def test_config_line_registers_company(tmp_path):
    config = tmp_path / 'p1_platform_companies.json'
    config.write_text(json.dumps({'beisen': {'newco': '新公司'},
                                  'moka': {'neworg/1': '新Moka公司'}}, ensure_ascii=False),
                      encoding='utf-8')
    with patch.object(beisen, 'CONFIG_PATH', config), patch.object(moka, 'CONFIG_PATH', config):
        beisen.reload_config()
        moka.reload_config()
        assert beisen.COMPANIES['newco'] == '新公司'
        registry = beisen.merged_registry()
        assert registry['新公司'] == 'qiuzhao.collector.p1_platform_beisen'
        assert registry['新Moka公司'] == 'qiuzhao.collector.p1_platform_moka'
    beisen.reload_config()
    moka.reload_config()
    assert '新公司' not in beisen.NAME_TO_SLUG


def test_real_config_is_registered_in_pipeline():
    from qiuzhao.collector import p1_pipeline
    assert p1_pipeline.REGISTRY['中信建投'] == 'qiuzhao.collector.p1_platform_beisen'
    assert p1_pipeline.REGISTRY['浙江民泰商业银行'] == 'qiuzhao.collector.p1_platform_beisen'
    assert p1_pipeline.REGISTRY['安踏集团'] == 'qiuzhao.collector.p1_platform_moka'
