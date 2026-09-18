"""Fixture tests for the iCIMS Career Portal platform adapter.

The robots.txt fixture is the verbatim directive published by the China-relevant
iCIMS hosts (``careers-amd.icims.com`` / ``careers-se.icims.com``, fetched
2026-09-19). The list/detail fixtures follow the documented iCIMS Career Portal
markup (``iCIMS_JobsTable`` rows and schema.org ``JobPosting`` microdata); no live
iCIMS host serves that server-rendered markup any more, so they are shape
fixtures and the suite never contacts a live career site.
"""
import json
from pathlib import Path
from unittest.mock import patch

from qiuzhao.collector import p1_platform_icims as icims

FIXTURES = Path(__file__).parent / 'fixtures' / 'platform'


def text(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


class FakeResponse:
    def __init__(self, body, status=200):
        self.text = body
        self.status_code = status
        self.encoding = 'utf-8'

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError('http ' + str(self.status_code))


class FakeSession:
    def __init__(self, robots, listing='', details=None, status=200, robots_status=200):
        self.robots = robots
        self.listing = listing
        self.details = details or {}
        self.status = status
        self.robots_status = robots_status
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if url.endswith('/robots.txt'):
            return FakeResponse(self.robots, self.robots_status)
        for ident, payload in self.details.items():
            if f'/jobs/{ident}/' in url:
                return FakeResponse(payload)
        return FakeResponse(self.listing, self.status)


CONFIG = {'icims': {
    '_note': 'documentation key that must never become a company',
    'careers-example.icims.com': {'name': '示例公司'},
}}


def patch_config(tmp_path):
    path = tmp_path / 'p1_platform_companies.json'
    path.write_text(json.dumps(CONFIG, ensure_ascii=False), encoding='utf-8')
    return path


def run(tmp_path, fake, scope='campus'):
    with patch.object(icims, 'CONFIG_PATH', patch_config(tmp_path)):
        icims.reload_config()
        with patch.object(icims, '_make_session', return_value=fake):
            return icims.collect('示例公司', scope, tmp_path / 'out')


# ------------------------------------------------------------------ config
def test_config_keys_and_notes(tmp_path):
    with patch.object(icims, 'CONFIG_PATH', patch_config(tmp_path)):
        icims.reload_config()
        assert icims.COMPANIES == {'careers-example.icims.com': '示例公司'}
        assert icims.merged_registry() == {'示例公司': icims.MODULE_PATH}
        assert icims.resolve('示例公司') == 'careers-example.icims.com'
        try:
            icims.resolve('不存在')
        except ValueError:
            pass
        else:
            raise AssertionError('unknown company must be rejected')


def test_shipped_config_is_empty_and_documented():
    icims.reload_config()
    assert icims.COMPANIES == {}, (
        'every China-relevant iCIMS tenant publishes "Disallow: /"; see the receipt')
    assert icims.merged_registry() == {}


# ------------------------------------------------------------------ robots gate
def test_robots_disallow_stops_before_any_content_request(tmp_path):
    fake = FakeSession(text('icims_robots_disallow.txt'),
                       listing=text('icims_list_china.html'))
    result = run(tmp_path, fake)
    coverage = result['coverage']
    assert result['jobs'] == []
    assert coverage['status'] == 'blocked'
    assert coverage['robots_disallow'] is True
    assert 'Disallow' in coverage['robots_policy']
    assert [url for url in fake.calls] == ['https://careers-example.icims.com/robots.txt'], \
        'a disallowed host must not receive a single content request'
    assert any('robots' in error for error in coverage['errors'])


def test_unreadable_robots_is_not_treated_as_a_disallow(tmp_path):
    fake = FakeSession('<html>404</html>', robots_status=404,
                       listing=text('icims_list_china.html'), status=404)
    result = run(tmp_path, fake)
    assert result['coverage'].get('robots_disallow') is None
    assert len(fake.calls) > 1


# ------------------------------------------------------------------ parsing
def test_list_and_jsonld_detail_mapping(tmp_path):
    fake = FakeSession('User-agent: *\nDisallow: /jobs/99999/\n',
                       listing=text('icims_list_china.html'),
                       details={'24001': text('icims_detail_jsonld.html')})
    result = run(tmp_path, fake)
    assert [job['source_record_id'] for job in result['jobs']] == ['24001']
    job = result['jobs'][0]
    assert job['recruitment_type'] == '校园招聘'
    assert job['published_at'] == '2026-09-10'      # official datePosted
    assert job['deadline_raw'] == '2026-11-30'      # official validThrough
    assert job['cohort_raw'] == ''                  # iCIMS has no 届别 field
    assert job['cities'] == ['Shanghai']
    assert 'Graduate Engineer 2027' in job['scope_evidence']


def test_intern_scope_and_non_china_filter(tmp_path):
    fake = FakeSession('User-agent: *\nDisallow: /jobs/99999/\n',
                       listing=text('icims_list_china.html'),
                       details={'24002': text('icims_detail_intern.html')})
    intern = run(tmp_path, fake, scope='intern')
    assert [job['source_record_id'] for job in intern['jobs']] == ['24002']
    assert intern['jobs'][0]['recruitment_type'] == '实习招聘'
    assert intern['jobs'][0]['deadline_raw'] == ''   # no validThrough -> blank
    assert intern['jobs'][0]['cities'] == ['Suzhou', 'Jiangsu']  # official tokens, country dropped
    social = run(tmp_path, fake, scope='social')
    assert social['jobs'] == []


def test_non_china_card_is_filtered_out(tmp_path):
    fake = FakeSession('User-agent: *\nDisallow: /jobs/99999/\n',
                       listing=text('icims_list_china.html'),
                       details={'24001': text('icims_detail_jsonld.html'),
                                '24002': text('icims_detail_jsonld.html'),
                                '24003': text('icims_detail_nonchina.html')})
    result = run(tmp_path, fake, scope='campus')
    assert '24003' not in {job['source_record_id'] for job in result['jobs']}
    assert result['coverage']['location_filtered_count'] >= 1


def test_budget_is_honoured(tmp_path):
    fake = FakeSession('User-agent: *\nDisallow: /jobs/99999/\n',
                       listing=text('icims_list_china.html'),
                       details={'24001': text('icims_detail_jsonld.html')})
    with patch.object(icims, 'CONFIG_PATH', patch_config(tmp_path)):
        icims.reload_config()
        with patch.object(icims, '_make_session', return_value=fake):
            result = icims.collect('示例公司', 'campus', tmp_path / 'out2', max_requests=2)
    assert result['coverage']['request_budget_exhausted'] is True
    assert result['coverage']['complete'] is False
