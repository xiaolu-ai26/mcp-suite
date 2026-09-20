"""Fixture tests for the Dayee (hotjob.cn) foreign-company adapter.

Only recorded official responses are used (``tests/fixtures/platform/dayee_*``)
and the module's own request seam is patched, so no live tenant is contacted.
"""
import json
from pathlib import Path

from qiuzhao.collector import p1_foreign_01 as dayee

FIXTURES = Path(__file__).parent / 'fixtures' / 'platform'
DELOITTE_SU = 'REDACTED'


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def run(company, scope, tmp_path, pages=None, details=None, max_requests=None, calls=None):
    pages = pages if pages is not None else {1: fixture('dayee_list_campus_p1.json'),
                                            2: fixture('dayee_list_campus_p2.json')}
    details = details if details is not None else {
        fixture('dayee_detail_1.json')['postId']: fixture('dayee_detail_1.json'),
        fixture('dayee_detail_2.json')['postId']: fixture('dayee_detail_2.json'),
        fixture('dayee_detail_3.json')['postId']: fixture('dayee_detail_3.json'),
    }
    seen = calls if calls is not None else []

    def fake_post(session, host, path, data, budget, referer):
        if budget is not None:
            if budget['limit'] is not None and budget['used'] >= budget['limit']:
                raise dayee.BudgetExhausted('reached')
            budget['used'] += 1
        if 'listPositionDetail' in path:
            seen.append(('detail', data['postId'], data['recruitType']))
            return {'state': '200', 'data': details[data['postId']]}
        seen.append(('list', data['currentPage'], data['recruitType']))
        return pages.get(data['currentPage'], fixture('dayee_list_empty.json'))

    original = dayee._post
    dayee._post = fake_post
    try:
        return dayee.collect(company, scope, tmp_path, max_requests=max_requests)
    finally:
        dayee._post = original


def test_two_page_scan_maps_official_fields_and_never_infers_cohort(tmp_path):
    result = run('德勤', 'campus', tmp_path)
    coverage = result['coverage']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['pagination_exhausted'] is True and coverage['detail_complete'] is True
    assert coverage['expected_total'] == 3
    by_id = {job['source_record_id']: job for job in result['jobs']}
    assert set(by_id) == {'6aa8be60b6fae46f6751e264', '6a87aa131ad6db7cf81f4fba',
                          '6a75a5e44315481304891635'}
    first = by_id['6aa8be60b6fae46f6751e264']
    assert first['job_title'] == 'Deloitte Tax Open Day - Hong Kong'
    assert first['published_at'] == '2026-09-15 11:40'          # official publishDate
    assert first['deadline_raw'] == '2027-09-15 23:59:59'       # official endDate
    assert first['cohort_raw'] == ''                            # never inferred
    assert first['cities'] == ['香港']
    assert first['recruitment_type'] == '校园招聘'
    assert len(first['description_raw']) > 100


def test_detail_missing_end_date_stays_blank(tmp_path):
    page = fixture('dayee_list_campus_p1.json')
    page['data']['pageForm'].update(totalPage=1, pageData=page['data']['pageForm']['pageData'][:1])
    page['data']['pageForm']['pageData'][0].update(endDate='', publishDate='')
    detail = fixture('dayee_detail_1.json')
    detail['endDate'] = ''
    detail['publishDate'] = ''
    result = run('德勤', 'campus', tmp_path, pages={1: page},
                 details={detail['postId']: detail})
    assert result['coverage']['status'] == 'success'
    job = result['jobs'][0]
    assert job['deadline_raw'] == '' and job['published_at'] == ''


def test_scope_uses_the_official_recruit_type_mapping(tmp_path):
    calls = []
    run('德勤', 'campus', tmp_path, calls=calls)
    assert all(call[2] == 1 for call in calls if call[0] == 'list')
    calls.clear()
    run('德勤', 'intern', tmp_path,
        pages={1: fixture('dayee_list_empty.json')}, calls=calls)
    assert calls and all(call[2] == 12 for call in calls)
    calls.clear()
    run('德勤', 'social', tmp_path,
        pages={1: fixture('dayee_list_empty.json')}, calls=calls)
    assert calls and all(call[2] == 2 for call in calls)


def test_request_budget_keeps_partial_rows(tmp_path):
    result = run('德勤', 'campus', tmp_path, max_requests=3)
    coverage = result['coverage']
    assert coverage['request_budget_exhausted'] is True
    assert coverage['complete'] is False
    assert coverage['status'] == 'partial'
    assert len(result['jobs']) >= 1           # interleaved detail read keeps rows
    assert coverage['request_budget']['used'] == 3


def test_unknown_company_is_rejected(tmp_path):
    try:
        dayee.collect('不存在的公司', 'campus', tmp_path)
    except ValueError as error:
        assert 'unknown Dayee company' in str(error)
    else:  # pragma: no cover - the adapter must not silently succeed
        raise AssertionError('unknown company must raise')


def test_real_config_registers_the_big_four_tenants():
    assert dayee.COMPANIES[DELOITTE_SU] == '德勤'
    assert dayee.merged_registry()['德勤'] == 'qiuzhao.collector.p1_foreign_01'
    assert dayee.resolve('德勤') == DELOITTE_SU
    for name in ('康师傅', 'ZARA', '广汽集团', '益海嘉里', '迪卡侬', 'ZURU'):
        assert name in dayee.merged_registry()


def test_repeated_pagination_page_is_terminal_not_an_error(tmp_path):
    """Dayee can repeat a whole page; that is a duplicate, not a fatal error.

    Observed live on 益海嘉里 / ZURU (2026-09-18): the same postId came back on a
    later page. The adapter must skip the duplicate, stop paging and keep the
    postings it already read instead of aborting the tenant.
    """
    page = fixture('dayee_list_campus_p1.json')          # totalPage=2, two rows
    result = run('德勤', 'campus', tmp_path, pages={1: page, 2: page})
    coverage = result['coverage']
    assert coverage['errors'] == []
    assert 'repeated' in (coverage['note'] or '')
    assert coverage['complete'] is False                 # completeness unconfirmed
    assert len(result['jobs']) == 2
    assert coverage['list_observed_ids'] == sorted(
        row['postId'] for row in page['data']['pageForm']['pageData'])


def test_zero_total_page_next_to_real_rows_never_ends_the_scan(tmp_path):
    """A ``totalPage`` of 0 next to real rows must not end the scan after page 1.

    Regression: ``page >= total_page`` held on the first page, so the adapter stopped
    there and still reported ``pagination_exhausted``.
    """
    first = fixture('dayee_list_campus_p1.json')
    first['data']['pageForm']['totalPage'] = 0
    calls = []
    result = run('德勤', 'campus', tmp_path,
                 pages={1: first, 2: fixture('dayee_list_campus_p2.json')}, calls=calls)
    assert [c for c in calls if c[0] == 'list' and c[1] == 2], 'page 2 must be requested'
    coverage = result['coverage']
    assert coverage['pagination_exhausted'] is True
    assert coverage['status'] == 'success' and coverage['complete'] is True
