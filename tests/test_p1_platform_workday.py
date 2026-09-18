"""Fixture tests for the generic Workday (myworkdayjobs.com CXS) platform adapter.

Only recorded-response fixtures are used: the HTTP session is a fake, so the
suite never touches a live Workday tenant.
"""
import json
from pathlib import Path
from unittest.mock import patch

from qiuzhao.collector import p1_platform_workday as workday

FIXTURES = Path(__file__).parent / 'fixtures' / 'platform'


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self._payload = payload if payload is not None else {}
        self.status_code = status
        self.encoding = 'utf-8'
        self.text = ''

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError('http ' + str(self.status_code))


class FakeSession:
    def __init__(self, pages, details):
        self.pages = pages
        self.details = details
        self.headers = {}

    def post(self, url, **kwargs):
        offset = int((kwargs.get('json') or {}).get('offset', 0))
        return FakeResponse(self.pages.get(offset, {'total': 0, 'jobPostings': []}))

    def get(self, url, **kwargs):
        for path, payload in self.details.items():
            if url.endswith(path):
                return FakeResponse(payload)
        return FakeResponse({'jobPostingInfo': {}})


def run(company, scope, tmp_path, pages=None, details=None, max_requests=20):
    if pages is None:
        pages = {0: fixture('workday_list_offset0.json'),
                 20: fixture('workday_list_offset20.json')}
    if details is None:
        details = {'/job/China-Shanghai/NCG-SWE_JR1': fixture('workday_detail_campus.json'),
                   '/job/China-Beijing/Intern_JR2': fixture('workday_detail_intern.json')}
    session = FakeSession(pages, details)
    with patch.object(workday, '_make_session', return_value=session):
        return workday.collect(company, scope, tmp_path, max_requests=max_requests)


def test_campus_classification_and_official_fields(tmp_path):
    result = run('英伟达', 'campus', tmp_path)
    coverage = result['coverage']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['expected_total'] == 1 and coverage['pagination_exhausted'] is True
    job = result['jobs'][0]
    assert job['source_record_id'] == 'wd-campus-1'
    assert job['recruitment_type'] == '校园招聘'
    assert job['published_at'] == '2026-08-19'          # official startDate
    assert job['deadline_raw'] == '2026-10-31'           # official endDate
    assert job['cohort_raw'] == ''                       # Workday has no cohort field -> blank
    assert 'BS/MS' in job['description_raw']
    assert job['cities'] == ['Shanghai', 'Beijing']
    assert 'New College Graduate' in job['scope_evidence']


def test_intern_scope_and_blank_deadline(tmp_path):
    result = run('英伟达', 'intern', tmp_path)
    assert {j['source_record_id'] for j in result['jobs']} == {'wd-intern-1'}
    job = result['jobs'][0]
    assert job['recruitment_type'] == '实习招聘'
    assert job['deadline_raw'] == ''                     # endDate null -> stay blank
    assert job['cohort_raw'] == ''


def test_social_scope_does_not_leak_campus_rows(tmp_path):
    result = run('英伟达', 'social', tmp_path)
    assert result['jobs'] == []
    assert result['coverage']['status'] == 'blocked'


def test_request_budget_stops_before_details(tmp_path):
    result = run('英伟达', 'campus', tmp_path, max_requests=1)
    coverage = result['coverage']
    assert coverage['request_budget_exhausted'] is True
    assert coverage['complete'] is False
    assert coverage['request_budget']['used'] <= 1


def test_non_china_detail_is_filtered(tmp_path):
    pages = {0: {'total': 1, 'jobPostings': [
        {'title': '2027 New College Graduate: Software Engineering',
         'externalPath': '/job/US-Santa-Clara/Grad_JR4', 'locationsText': '2 Locations'}]}}
    details = {'/job/US-Santa-Clara/Grad_JR4': fixture('workday_detail_nonchina.json')}
    result = run('英伟达', 'campus', tmp_path, pages=pages, details=details)
    assert result['jobs'] == []
    assert result['coverage']['location_filtered_count'] == 1
    assert result['coverage']['status'] == 'blocked'


def test_scope_keyword_precedence():
    assert workday._scope_of('Graduate Intern - 2027', 'x') == 'intern'
    assert workday._scope_of('2027 New College Graduate', 'x') == 'campus'
    assert workday._scope_of('Senior Software Engineer', 'x') == 'social'


def test_config_line_registers_company(tmp_path):
    config = tmp_path / 'p1_platform_companies.json'
    config.write_text(json.dumps({'workday': {'acme/wd1/AcmeCareers': '新外企'}}, ensure_ascii=False),
                      encoding='utf-8')
    with patch.object(workday, 'CONFIG_PATH', config):
        workday.reload_config()
        assert workday.COMPANIES['acme/wd1/AcmeCareers'] == '新外企'
        assert workday.resolve('新外企') == 'acme/wd1/AcmeCareers'
        assert workday.merged_registry()['新外企'] == 'qiuzhao.collector.p1_platform_workday'
        assert workday.host_for('acme/wd1/AcmeCareers') == 'https://acme.wd1.myworkdayjobs.com'
    workday.reload_config()
    assert '新外企' not in workday.NAME_TO_SLUG


def test_real_config_is_registered_in_pipeline():
    from qiuzhao.collector import p1_pipeline
    assert p1_pipeline.REGISTRY['英伟达'] == 'qiuzhao.collector.p1_platform_workday'
    assert p1_pipeline.REGISTRY['花旗银行'] == 'qiuzhao.collector.p1_platform_workday'
    assert p1_pipeline.REGISTRY['思爱普'] == 'qiuzhao.collector.p1_platform_successfactors'
