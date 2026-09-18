"""Fixture tests for the generic Oracle Recruiting Cloud (ORC) platform adapter.

The list/detail/hierarchy JSON is a recorded fixture from the official public ORC
REST surface (Honeywell ``CX_1``, recorded 2026-09-19) and the HTTP session is a
fake, so the suite never contacts a live career site.
"""
import json
import re
from pathlib import Path
from unittest.mock import patch

from qiuzhao.collector import p1_platform_orc as orc

FIXTURES = Path(__file__).parent / 'fixtures' / 'platform'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError('http ' + str(self.status_code))


class FakeSession:
    """Serves the recorded hierarchy / China list / batched detail payloads."""

    def __init__(self, hierarchy, listing, details):
        self.hierarchy = hierarchy
        self.listing = listing
        self.details = details
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if 'recruitingHierarchyLocations' in url:
            return FakeResponse(self.hierarchy)
        if 'recruitingCEJobRequisitions' in url:
            offset = int(re.search(r'offset=(\d+)', url).group(1))
            if offset:
                return FakeResponse({'items': [{'requisitionList': [], 'TotalJobsCount': 60}]})
            return FakeResponse(self.listing)
        if 'recruitingCEJobRequisitionDetails' in url:
            finder = url.split('finder=')[1]
            wanted = set(re.findall(r'\d+', finder.split('siteNumber')[0]))
            rows = [row for row in self.details['items'] if str(row.get('Id')) in wanted]
            return FakeResponse({'items': rows})
        raise AssertionError('unexpected url ' + url)


def session():
    return FakeSession(load('orc_hierarchy_china.json'), load('orc_list_china.json'),
                       load('orc_detail_batch.json'))


def run(company='霍尼韦尔', scope='campus', tmp_path=None, fake=None, max_requests=None):
    fake = fake or session()
    with patch.object(orc, '_make_session', return_value=fake):
        result = orc.collect(company, scope, tmp_path, max_requests=max_requests)
    return result, fake


# ------------------------------------------------------------------ config
def test_real_config_registers_every_orc_tenant_without_notes():
    assert orc.COMPANIES, 'the shipped config must register the verified tenants'
    assert '_note' not in orc.COMPANIES
    for key, name in orc.COMPANIES.items():
        host, site = orc.host_and_site(key)
        assert host.endswith('oraclecloud.com') and re.fullmatch(r'CX_\d+', site)
        assert not name.startswith('Foreign batch')
    registry = orc.merged_registry()
    assert registry['霍尼韦尔'] == orc.MODULE_PATH
    assert orc.resolve('摩根大通') == 'jpmc.fa.oraclecloud.com/CX_1001'


def test_host_and_site_rejects_a_bare_host():
    for bad in ('eeho.fa.us2.oraclecloud.com', 'host/CX', 'host/XX_1', 'host/CX_1/extra'):
        try:
            orc.host_and_site(bad)
        except ValueError:
            continue
        raise AssertionError('accepted invalid key ' + bad)


# ------------------------------------------------------------------ helpers
def test_strip_country_dedupes_repeated_official_tokens():
    assert orc._strip_country('Shanghai, Shanghai, China') == 'Shanghai'
    assert orc._strip_country("Xi'an, Shaanxi, China") == "Xi'an, Shaanxi"
    assert orc._city_parts('Shanghai, Shanghai, China') == ['Shanghai']


def test_china_geography_discovery_prefers_the_country_level_node(tmp_path):
    result, _ = run('霍尼韦尔', 'social', tmp_path)
    assert result['coverage']['china_geography_id'] == 300000000469314


def test_missing_china_geography_is_blocked_without_listing(tmp_path):
    fake = FakeSession({'items': [{'GeographyId': 1, 'GeographyLevel': 3,
                                   'GeographyFlatName': 'China, Benguela, Angola'}]},
                       load('orc_list_china.json'), load('orc_detail_batch.json'))
    result, fake = run('霍尼韦尔', 'campus', tmp_path, fake=fake)
    assert result['coverage']['status'] == 'blocked'
    assert result['jobs'] == []
    assert not any('recruitingCEJobRequisitions' in url for url in fake.calls)


# ------------------------------------------------------------------ list/detail
def test_campus_scope_maps_official_university_relations_labels(tmp_path):
    result, fake = run('霍尼韦尔', 'campus', tmp_path)
    assert result['jobs'], 'the recorded China slice has University Relations postings'
    job = result['jobs'][0]
    assert job['recruitment_type'] == '校园招聘'
    assert job['cohort_raw'] == ''                 # ORC has no 届别 field -> blank
    assert job['deadline_raw'] == ''               # PostingEndDate is null -> blank
    posted = {str(row['Id']): row.get('PostedDate')
              for row in load('orc_list_china.json')['items'][0]['requisitionList']}
    assert job['published_at'] == posted[job['source_record_id']]  # official PostedDate
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', job['published_at'])
    assert job['cities'] and 'China' not in job['cities']
    assert 'University Relations' in job['scope_evidence']
    assert 'classification=campus' in job['scope_evidence']


def test_detail_request_batches_requisition_ids(tmp_path):
    _, fake = run('霍尼韦尔', 'campus', tmp_path)
    detail_calls = [url for url in fake.calls if 'recruitingCEJobRequisitionDetails' in url]
    assert detail_calls, 'details must be fetched from the official ORC endpoint'
    assert any(' or ' in url for url in detail_calls), 'ids must be batched in one request'
    assert all('siteNumber=CX_1' in url for url in detail_calls)


def test_non_china_requisition_is_filtered(tmp_path):
    listing = json.loads(json.dumps(load('orc_list_china.json')))
    rows = listing['items'][0]['requisitionList']
    rows.insert(0, {'Id': '999999', 'Title': '2027 UR Early Career Program - Austin',
                    'PostedDate': '2026-09-01', 'PostingEndDate': None,
                    'PrimaryLocation': 'Austin, Texas, United States',
                    'PrimaryLocationCountry': 'US',
                    'ShortDescriptionStr': 'US based early career role.'})
    details = json.loads(json.dumps(load('orc_detail_batch.json')))
    details['items'].append({'Id': '999999', 'Title': '2027 UR Early Career Program - Austin',
                             'PrimaryLocation': 'Austin, Texas, United States',
                             'PrimaryLocationCountry': 'US',
                             'ExternalDescriptionStr': '<p>US based early career role.</p>'})
    fake = FakeSession(load('orc_hierarchy_china.json'), listing, details)
    result, _ = run('霍尼韦尔', 'campus', tmp_path, fake=fake)
    assert '999999' not in {job['source_record_id'] for job in result['jobs']}
    assert result['coverage']['location_filtered_count'] >= 1


def test_intern_and_social_scopes_are_not_mixed(tmp_path):
    intern, _ = run('霍尼韦尔', 'intern', tmp_path)
    social, _ = run('霍尼韦尔', 'social', tmp_path)
    assert all(job['recruitment_type'] == '实习招聘' for job in intern['jobs'])
    assert all(job['recruitment_type'] == '社会招聘' for job in social['jobs'])
    campus_ids = {job['source_record_id'] for job in run('霍尼韦尔', 'campus', tmp_path)[0]['jobs']}
    assert not campus_ids & {job['source_record_id'] for job in social['jobs']}


def test_request_budget_marks_the_run_partial(tmp_path):
    result, _ = run('霍尼韦尔', 'social', tmp_path, max_requests=2)
    coverage = result['coverage']
    assert coverage['request_budget_exhausted'] is True
    assert coverage['complete'] is False
    assert coverage['status'] in ('partial', 'blocked')
