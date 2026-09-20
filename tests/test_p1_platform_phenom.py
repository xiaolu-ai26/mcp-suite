"""Fixture tests for the Phenom People public careers adapter.

The fixtures are the recorded public JSON the careers page itself receives:
``phenom_search_pg.json`` is a trimmed ``refineSearch`` response from the P&G
China site (three campus, three internship, three experienced and three Taiwan
postings, with the real ``totalHits`` of 56) and ``phenom_detail_pg*.json`` are
two ``jobDetail`` responses. Fields the adapter never reads were dropped from
the recording; no value was invented. No live request is made here.
"""
import json
from pathlib import Path

from qiuzhao.collector import p1_platform_phenom as ph

FIXTURES = Path(__file__).parent / 'fixtures' / 'platform'


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def search_data(name='phenom_search_pg.json'):
    return fixture(name)['refineSearch']['data']


def detail_job(name='phenom_detail_pg.json'):
    return fixture(name)['jobDetail']['data']['job']


def envelope(name, total_hits):
    return {'refineSearch': {'status': 200, 'totalHits': total_hits, 'data': search_data(name)}}


def run(company, scope, tmp_path, pages=None, detail=None, max_requests=None):
    """Drive collect() against the recorded envelopes instead of the network."""
    pages = pages if pages is not None else [envelope('phenom_search_pg.json', 56),
                                             envelope('phenom_search_empty.json', 56)]
    detail = detail if detail is not None else detail_job()
    by_offset = {}
    cursor = 0
    for page in pages:
        by_offset[str(cursor)] = page
        rows = page['refineSearch']['data'].get('jobs') or []
        cursor += len(rows) or 500
    calls = []

    def fake_post(session, entry, body, budget):
        if budget is not None:
            if budget['limit'] is not None and budget['used'] >= budget['limit']:
                raise ph.BudgetExhausted('reached')
            budget['used'] += 1
        calls.append(body)
        if body.get('ddoKey') == 'refineSearch':
            return by_offset.get(str(body.get('from')), envelope('phenom_search_empty.json', 56))
        return {'jobDetail': {'status': 200, 'data': {'job': {**detail, 'jobId': body['jobId']}}}}

    original = ph._post_json
    ph._post_json = fake_post
    try:
        result = ph.collect(company, scope, tmp_path, max_requests=max_requests)
    finally:
        ph._post_json = original
    return result, calls


def test_widget_bodies_use_the_official_shape():
    entry = ph._entry('PGBPGCCN')
    assert ph.widgets_url(entry) == 'https://careers.pg.com.cn/widgets'
    search = ph.search_body(entry, 500)
    assert search['ddoKey'] == 'refineSearch' and search['refNum'] == 'PGBPGCCN'
    assert search['from'] == 500 and search['size'] == ph.PAGE_SIZE
    job = {'jobId': 'CNJ002730', 'jobSeqNo': 'PGBPGCCNCNJ002730EXTERNALENCN'}
    detail = ph.detail_body(entry, job)
    assert detail['ddoKey'] == 'jobDetail' and detail['jobId'] == 'CNJ002730'
    assert detail['jobSeqNo'] == 'PGBPGCCNCNJ002730EXTERNALENCN'


def test_registry_covers_every_configured_tenant():
    registry = ph.merged_registry()
    assert set(registry) == {'宝洁', '玛氏', '罗氏', '波士顿咨询', 'ABB', '飞利浦', '默沙东', '思科'}
    assert set(registry.values()) == {ph.MODULE_PATH}
    assert ph.resolve('宝洁') == 'PGBPGCCN' and ph.resolve('PGBPGCCN') == 'PGBPGCCN'


def test_china_membership_uses_the_postings_own_country_text():
    assert ph.is_china_token('Chinese Mainland - Greater China')
    assert ph.is_china_token("China's Mainland")
    assert ph.is_china_token('Hong Kong SAR – Greater China')
    assert ph.is_china_token('Taiwan – Greater China')
    assert ph.is_china_token('Greater China')
    assert not ph.is_china_token('United Kingdom')
    assert not ph.is_china_token('')
    assert ph.is_china({'country': 'Taiwan – Greater China'})
    assert not ph.is_china({'country': 'Poland'})
    # A posting with no country still counts when its city names a China site.
    assert ph.is_china({'city': 'Shanghai', 'cityStateCountry': 'Shanghai, China'})


def test_scope_uses_only_official_early_career_labels():
    assert ph.classify_scope({'title': '(Chinese Mainland) Campus Recruiting - Finance'}) == 'campus'
    assert ph.classify_scope({'title': '2027 P&G Internship Programme'}) == 'intern'
    assert ph.classify_scope({'title': 'Electronic Engineer'}) == 'social'
    # Word boundaries: an "Internal Communications" role is not an internship.
    assert ph.classify_scope({'title': 'Manager, Internal Communications'}) == 'social'
    assert ph.classify_scope({'title': 'International Sales Lead'}) == 'social'
    # BCG files experienced hires under this catch-all; the title decides.
    assert ph.classify_scope(
        {'title': 'Experienced Hire, Full-time, Greater China',
         'subCategory': 'Co-op/Intern/Temporary'}) == 'social'
    # A tenant may pin one exact official value to a scope (Roche subCategory).
    roche = {'title': 'StartUp China - Pharma Market Access',
             'subCategory': 'Development Program'}
    assert ph.classify_scope(roche) == 'social'
    assert ph.classify_scope(roche, 'ROCHGLOBAL') == 'campus'
    assert ph.classify_scope({'title': '实习医药信息顾问', 'subCategory': 'Internship'},
                             'ROCHGLOBAL') == 'intern'


def test_recorded_campus_page_splits_scope_and_region(tmp_path):
    result, calls = run('宝洁', 'campus', tmp_path,
                        pages=[envelope('phenom_search_pg.json', 56),
                               envelope('phenom_search_empty.json', 56)],
                        detail=detail_job('phenom_detail_pg_campus.json'))
    assert result['coverage']['status'] == 'success'
    assert result['coverage']['complete'] is True
    titles = [j['job_title'] for j in result['jobs']]
    assert all(t.startswith('(Chinese Mainland) Campus Recruiting') for t in titles)
    assert len(titles) == 3
    # Taiwan rows are reported by their own official location text, never merged.
    assert all('Taiwan' not in (j['location'] or '') for j in result['jobs'])
    row = result['jobs'][0]
    assert row['recruitment_type'] == '校园招聘'
    assert row['description_source'] == 'official Phenom jobDetail description'
    assert 'Campus Recruiting' in row['scope_evidence']
    assert row['detail_url'].startswith('https://')
    assert row['description_raw'].strip()


def test_intern_scope_publishes_the_recorded_internship_rows(tmp_path):
    result, _ = run('宝洁', 'intern', tmp_path)
    assert [j['recruitment_type'] for j in result['jobs']] == ['实习招聘'] * 3
    assert all('Internship' in j['job_title'] for j in result['jobs'])
    # Phenom publishes no deadline here and no cohort year: both stay empty.
    assert all(j['deadline_raw'] == '' and j['cohort_raw'] == '' for j in result['jobs'])


def test_experienced_rows_carry_the_official_posted_date(tmp_path):
    result, _ = run('宝洁', 'social', tmp_path)
    row = next(j for j in result['jobs'] if j['source_record_id'] == 'CNJ002730')
    assert row['published_at'] == '2025-03-27'
    assert row['application_url'].startswith('https://recruit.pg.com.cn/')
    assert 'Beijing' in row['cities']


def test_exhausted_listing_with_no_matching_posting_is_an_empty_success(tmp_path):
    result, calls = run('思科', 'campus', tmp_path,
                        pages=[envelope('phenom_search_empty.json', 0)])
    assert len(calls) == 1
    assert result['jobs'] == []
    coverage = result['coverage']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['scope_evidence']
    assert 'no 校园招聘 posting' in coverage['note']


def test_pagination_advances_by_the_returned_row_count(tmp_path):
    result, calls = run('宝洁', 'intern', tmp_path,
                        pages=[envelope('phenom_search_pg.json', 56),
                               envelope('phenom_search_empty.json', 56)])
    offsets = [c['from'] for c in calls if c['ddoKey'] == 'refineSearch']
    assert offsets == [0, 12]
    assert result['coverage']['pagination_exhausted'] is True
    assert result['coverage']['expected_total'] == 3


def test_request_budget_stops_the_walk_and_reports_partial(tmp_path):
    # One page read plus one detail; the second detail is the third request.
    result, _ = run('宝洁', 'intern', tmp_path, max_requests=3)
    coverage = result['coverage']
    assert coverage['request_budget_exhausted'] is True
    assert coverage['status'] == 'partial' and coverage['complete'] is False
    assert coverage['request_budget']['used'] == 3
    assert len(result['jobs']) == 1
    assert coverage['expected_total'] == 3


def test_refused_widget_switches_to_the_public_page(tmp_path, monkeypatch):
    import qiuzhao.collector.p1_platform_phenom as module
    seen = []

    def refusing(session, entry, body, budget):
        if budget is not None:
            budget['used'] += 1
        raise module.DirectRefused('HTTP 403 on widgets')

    class FakeHeadless:
        def __init__(self, entry, budget, allow_page_loads):
            self.page_loads = 0
            self.pages = 0

        def warm_up(self):
            self.page_loads += 1
            seen.append('warm_up')

        def widget(self, body):
            seen.append(body.get('ddoKey'))
            if body.get('ddoKey') == 'refineSearch':
                self.pages += 1
                if self.pages == 1:
                    return envelope('phenom_search_pg.json', 56)
                return envelope('phenom_search_empty.json', 56)
            return {'jobDetail': {'status': 200, 'data': {
                'job': {**detail_job(), 'jobId': body['jobId']}}}}

        def close(self):
            pass

    monkeypatch.setattr(module, '_post_json', refusing)
    monkeypatch.setattr(module, '_HeadlessReader', FakeHeadless)
    result = module.collect('宝洁', 'campus', tmp_path)
    coverage = result['coverage']
    assert coverage['mode'] == 'headless'
    assert coverage['scope_request']['params']['transport'] == 'headless'
    assert 'switched to the public search page' in coverage['note']
    assert coverage['errors'] == []
    assert seen[0] == 'warm_up'


def test_evidence_files_are_the_files_actually_written(tmp_path):
    result, _ = run('宝洁', 'campus', tmp_path,
                    detail=detail_job('phenom_detail_pg_campus.json'))
    coverage = result['coverage']
    assert coverage['evidence_files'] == coverage['evidence']
    for name in coverage['evidence_files']:
        path = tmp_path / name
        assert path.is_file() and path.stat().st_size
    (tmp_path / 'adapter.log').write_text('', encoding='utf-8')
    again, _ = run('宝洁', 'campus', tmp_path,
                   detail=detail_job('phenom_detail_pg_campus.json'))
    assert 'adapter.log' not in again['coverage']['evidence_files']


def test_zero_total_hits_next_to_real_rows_never_ends_the_scan(tmp_path):
    """A ``totalHits`` of 0 next to real rows is the site contradicting itself.

    Regression: ``offset >= int(total)`` held on the first page, so the scan stopped there
    and still reported ``pagination_exhausted``.
    """
    result, calls = run('宝洁', 'campus', tmp_path,
                        pages=[envelope('phenom_search_pg.json', 0),
                               envelope('phenom_search_empty.json', 0)])
    searches = [call for call in calls if call['ddoKey'] == 'refineSearch']
    assert len(searches) == 2, 'page 2 must still be requested'
    coverage = result['coverage']
    assert coverage['pagination_exhausted'] is True     # the empty page is the real end
    assert coverage['last_page_evidence'].endswith('rows=0;totalHits=0')
    assert coverage['list_observed_ids']
