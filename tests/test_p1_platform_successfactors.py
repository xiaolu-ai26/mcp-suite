"""Fixture tests for the generic SAP SuccessFactors CSB platform adapter.

The list/detail HTML is recorded fixtures and the HTTP session is a fake, so the
suite never contacts a live career site.
"""
import json
import re
from pathlib import Path
from unittest.mock import patch

from qiuzhao.collector import p1_platform_successfactors as sf

FIXTURES = Path(__file__).parent / 'fixtures' / 'platform'


def html(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


class FakeResponse:
    def __init__(self, text='', status=200):
        self.text = text
        self.status_code = status
        self.encoding = 'utf-8'

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError('http ' + str(self.status_code))


class FakeSession:
    def __init__(self, lists, details):
        self.lists = lists
        self.details = details
        self.headers = {}

    def get(self, url, **kwargs):
        if '/search/' in url:
            match = re.search(r'startrow=(\d+)', url)
            row = int(match.group(1)) if match else 0
            return FakeResponse(self.lists.get(row, ''))
        for path, payload in self.details.items():
            if path in url:
                return FakeResponse(payload)
        return FakeResponse('')


def run(company, scope, tmp_path, lists=None, details=None, max_requests=20):
    if lists is None:
        lists = {0: html('sf_list_startrow0.html'), 25: html('sf_list_startrow25.html')}
    if details is None:
        details = {'/job/Shanghai-Student-Rotation-Program-2028-Graduates/1437532001/': html('sf_detail_campus.html'),
                   '/job/Dalian-iXp-Intern-Queue-Manager/1437532002/': html('sf_detail_intern.html')}
    session = FakeSession(lists, details)
    with patch.object(sf, '_make_session', return_value=session):
        return sf.collect(company, scope, tmp_path, max_requests=max_requests)


def test_campus_microdata_mapping(tmp_path):
    result = run('思爱普', 'campus', tmp_path)
    coverage = result['coverage']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['pagination_exhausted'] is True and coverage['expected_total'] == 1
    job = result['jobs'][0]
    assert job['source_record_id'] == '1437532001'
    assert job['recruitment_type'] == '校园招聘'
    assert job['published_at'] == '2026-09-16'          # official datePosted
    assert job['deadline_raw'] == '2026-11-30'           # official validThrough
    assert job['cohort_raw'] == ''                       # no cohort field -> blank
    assert '2028 届本科及以上' in job['description_raw']
    assert job['cities'] == ['Shanghai']  # official city token; CN/postal stripped


def test_intern_scope_and_missing_deadline(tmp_path):
    result = run('思爱普', 'intern', tmp_path)
    assert {j['source_record_id'] for j in result['jobs']} == {'1437532002'}
    assert result['jobs'][0]['deadline_raw'] == ''


def test_non_china_card_is_filtered(tmp_path):
    cards = ('<table><tr class="data-row"><td><a class="jobTitle-link" '
             'href="/job/Walldorf-Graduate-Programme-Germany/1437532004/">'
             'Graduate Programme - Germany</a></td><td><span class="jobLocation">'
             'Walldorf Germany</span></td></tr></table>')
    result = run('思爱普', 'campus', tmp_path, lists={0: cards})
    assert result['jobs'] == []
    assert result['coverage']['status'] == 'blocked'


def test_request_budget_stops_before_details(tmp_path):
    result = run('思爱普', 'campus', tmp_path, max_requests=1)
    coverage = result['coverage']
    assert coverage['request_budget_exhausted'] is True
    assert coverage['complete'] is False
    assert coverage['request_budget']['used'] <= 1


def test_config_line_registers_company(tmp_path):
    config = tmp_path / 'p1_platform_companies.json'
    config.write_text(json.dumps({'successfactors': {'jobs.acme.com': '新公司'}}, ensure_ascii=False),
                      encoding='utf-8')
    with patch.object(sf, 'CONFIG_PATH', config):
        sf.reload_config()
        assert sf.COMPANIES['jobs.acme.com'] == '新公司'
        assert sf.resolve('新公司') == 'jobs.acme.com'
        assert sf.merged_registry()['新公司'] == 'qiuzhao.collector.p1_platform_successfactors'
        assert sf.base_for('jobs.acme.com') == 'https://jobs.acme.com'
    sf.reload_config()
    assert '新公司' not in sf.NAME_TO_SLUG


def test_scope_keyword_precedence():
    assert sf._scope_of('Graduate Intern - 2027', 'x') == 'intern'
    assert sf._scope_of('Student Rotation Program - 2028 Graduates', 'x') == 'campus'
    assert sf._scope_of('Solution Sales Expert', 'x') == 'social'
