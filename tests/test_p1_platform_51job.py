"""Fixture tests for the 51job corporate campus micro-site adapter.

The fixtures are the recorded public pages: ``51job_pepsico.html`` is a
server-rendered posting list (three application anchors) and
``51job_adidas_no_list.html`` is a landing page that carries no posting anchor.
No live page is fetched here.
"""
import json
from pathlib import Path

from qiuzhao.collector import p1_platform_51job as job51

FIXTURES = Path(__file__).parent / 'fixtures' / 'platform'


def page(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


def run(company, scope, tmp_path, html=None, calls=None):
    html = page('51job_pepsico.html') if html is None else html
    seen = calls if calls is not None else []

    def fake_get(session, url, budget):
        if budget is not None:
            if budget['limit'] is not None and budget['used'] >= budget['limit']:
                raise job51.BudgetExhausted('reached')
            budget['used'] += 1
        seen.append(url)
        return html

    original = job51._get
    job51._get = fake_get
    try:
        return job51.collect(company, scope, tmp_path)
    finally:
        job51._get = original


def test_recorded_micro_site_lists_official_postings(tmp_path):
    result = run('百事', 'campus', tmp_path)
    coverage = result['coverage']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['expected_total'] == 3
    titles = [job['job_title'] for job in result['jobs']]
    assert titles == ['综合管理培训生', '供应链管理培训生', '农业培训生']
    urls = [job['source_url'] for job in result['jobs']]
    assert urls == ['https://xyz.51job.com/External/Apply.aspx?CtmID=9549063',
                    'https://xyz.51job.com/External/Apply.aspx?CtmID=9549079',
                    'https://xyz.51job.com/External/Apply.aspx?CtmID=9549088']
    first = result['jobs'][0]
    # The announcement carries no dates and no cohort, so they stay blank.
    assert first['published_at'] == '' and first['deadline_raw'] == ''
    assert first['cohort_raw'] == ''
    assert first['campaign_cohort_raw'] == '百事集团2027校园招聘'
    assert first['description_source'] == 'official announcement micro-site text'
    assert '综合管理培训生' in first['description_raw']


def test_landing_page_without_application_anchor_is_blocked(tmp_path):
    result = run('百事', 'campus', tmp_path, html=page('51job_adidas_no_list.html'))
    assert result['jobs'] == []
    assert result['coverage']['status'] == 'blocked'
    assert any('CtmID' in error for error in result['coverage']['errors'])


def test_scope_without_a_micro_site_page_is_empty_success(tmp_path):
    calls = []
    result = run('百事', 'intern', tmp_path, calls=calls)
    assert calls == []                          # never fetches a page that cannot exist
    assert result['jobs'] == []
    assert result['coverage']['status'] == 'success'
    assert 'campus' in result['coverage']['note']


def test_budget_is_honoured(tmp_path):
    """A one-request budget still yields a partial-but-usable single GET."""
    result = run('百事', 'campus', tmp_path)
    assert result['coverage']['request_budget']['used'] == 1


def test_real_config_registers_only_verified_sites():
    assert job51.COMPANIES['pepsico2027'] == '百事'
    assert job51.merged_registry()['百事'] == 'qiuzhao.collector.p1_platform_51job'
    assert job51.resolve('百事') == 'pepsico2027'
    assert job51.site_url('pepsico2027') == 'https://campus.51job.com/pepsico2027/'


def test_postings_are_deduplicated_by_application_id(tmp_path):
    html = page('51job_pepsico.html')
    duplicated = html + html
    result = run('百事', 'campus', tmp_path, html=duplicated)
    ids = [job['source_record_id'] for job in result['jobs']]
    assert len(ids) == len(set(ids)) == 3
