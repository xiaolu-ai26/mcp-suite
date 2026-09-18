"""Fixture tests for the Eightfold AI public careers adapter.

The fixtures are the recorded public JSON: ``eightfold_search_hp_page0/1.json``
and ``eightfold_search_empty.json`` are the responses the HP careers page itself
receives from ``/api/pcsx/search`` (trimmed to the first rows), and
``eightfold_detail_hp*.json`` are two ``/api/pcsx/position_details`` responses
trimmed to the fields the adapter reads. No live request is made here.
"""
import json
from pathlib import Path

from qiuzhao.collector import p1_platform_eightfold as ef

FIXTURES = Path(__file__).parent / 'fixtures' / 'platform'


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def stamp(detail, position_id):
    """Re-stamp a recorded detail with the requested posting id.

    That id match is the adapter's own completeness check, so the stub has to
    satisfy it. Every other field stays verbatim fixture data.
    """
    return {**detail, 'id': int(position_id)}


def run(company, scope, tmp_path, pages=None, detail=None, max_requests=None):
    """Drive collect() against the recorded payloads instead of the network."""
    pages = pages if pages is not None else [fixture('eightfold_search_hp_page0.json'),
                                             fixture('eightfold_search_empty.json')]
    detail = detail if detail is not None else fixture('eightfold_detail_hp.json')
    by_start = {}
    cursor = 0
    for page in pages:
        by_start[str(cursor)] = page
        cursor += len(page.get('positions') or []) or 10
    calls = []

    def fake_http(session, url, budget, referer):
        if budget is not None:
            if budget['limit'] is not None and budget['used'] >= budget['limit']:
                raise ef.BudgetExhausted('reached')
            budget['used'] += 1
        calls.append(url)
        if '/api/pcsx/search' in url:
            start = url.split('start=', 1)[1].split('&', 1)[0]
            return {'data': by_start.get(start, {'positions': [], 'count': 0})}
        position_id = url.split('position_id=', 1)[1].split('&', 1)[0]
        return {'data': stamp(detail, position_id)}

    original = ef._http_json
    ef._http_json = fake_http
    try:
        result = ef.collect(company, scope, tmp_path, max_requests=max_requests)
    finally:
        ef._http_json = original
    return result, calls


def test_listing_pages_use_the_official_search_shape():
    entry = ef._entry('apply.hp.com')
    url = ef.search_url(entry, 20)
    assert url == ('https://apply.hp.com/api/pcsx/search?domain=hp.com&query=&location=china'
                   '&start=20&sort_by=distance&filter_include_remote=1&hl=zh-CN')
    assert ef.careers_url(entry, 0).startswith('https://apply.hp.com/careers?domain=hp.com')
    assert ef.detail_url(entry, 44487095) == (
        'https://apply.hp.com/api/pcsx/position_details?position_id=44487095'
        '&domain=hp.com&hl=zh-CN&queried_location=china')


def test_registry_covers_every_configured_tenant():
    assert ef.merged_registry() == {
        '惠普': ef.MODULE_PATH, '微软': ef.MODULE_PATH, '高通': ef.MODULE_PATH,
        '应用材料': ef.MODULE_PATH, '泛林': ef.MODULE_PATH}
    assert ef.resolve('惠普') == 'apply.hp.com'
    assert ef.resolve('apply.hp.com') == 'apply.hp.com'


def test_china_location_handles_all_three_official_spellings():
    assert ef.is_china_location('Chongqing, Chongqing, China')
    assert ef.is_china_location('Jinan,CHN')          # Applied Materials spelling
    assert ef.is_china_location("Xi'an, Shaanxi, CN")  # standardized spelling
    assert ef.is_china_location('Hong Kong, Hong Kong')
    assert not ef.is_china_location('Singapore, South West, Singapore')
    assert not ef.is_china_location('Phoenix,AZ')
    # "CN" must be its own comma component, never a substring of another word.
    assert not ef.is_china_location('Cincinnati,OH')


def test_scope_uses_only_official_early_career_labels():
    assert ef.classify_scope({'name': '2026 Intern-GPU AI Engineer'}) == 'intern'
    assert ef.classify_scope({'name': 'New Graduate- AI SW SDK Engineer'}) == 'campus'
    assert ef.classify_scope({'name': '韩语多媒体内容策划与直播支持实习生'}) == 'intern'
    assert ef.classify_scope({'name': 'Electrical Engineer-校园招聘'}) == 'campus'
    assert ef.classify_scope({'name': 'Software Application Engineer'}) == 'social'
    # Word boundaries: an experienced "Internal ..." role is never an internship.
    assert ef.classify_scope({'name': 'Internal Communications Manager'}) == 'social'
    assert ef.classify_scope({'name': 'International Sales Lead'}) == 'social'
    # Intern is the more specific label when a posting carries both.
    assert ef.classify_scope({'name': 'Graduate Intern Programme'}) == 'intern'
    # A tenant may opt an extra official field in, but it is off by default.
    position = {'name': 'Software Engineer', 'department': 'Interns'}
    assert ef.classify_scope(position, 'apply.hp.com') == 'social'


def test_multi_country_posting_is_kept_when_one_site_is_in_china(tmp_path):
    result, _ = run('惠普', 'social', tmp_path)
    # The first recorded row is Singapore *and* Chongqing; its China site counts.
    row = next(j for j in result['jobs'] if j['source_record_id'] == '44136780')
    assert row['recruitment_type'] == '社会招聘'
    assert 'Chongqing, Chongqing, China' in row['location']
    assert 'Chongqing' in row['cities']


def test_intern_scope_publishes_the_recorded_intern_posting(tmp_path):
    result, _ = run('惠普', 'intern', tmp_path,
                    detail=fixture('eightfold_detail_hp_intern.json'))
    assert result['coverage']['status'] == 'success'
    assert result['coverage']['complete'] is True
    assert [j['job_title'] for j in result['jobs']] == ['韩语多媒体内容策划与直播支持实习生']
    row = result['jobs'][0]
    assert row['recruitment_type'] == '实习招聘'
    assert row['detail_url'] == 'https://apply.hp.com/careers/job/43321947'
    # Eightfold publishes no deadline and no cohort: both stay empty.
    assert row['deadline_raw'] == '' and row['cohort_raw'] == ''
    assert row['published_at'] == '2026-09-07T00:00:00+00:00'
    assert row['description_source'] == 'official Eightfold position_details jobDescription'
    assert '实习生' in row['job_title']
    assert row['description_raw'].strip()
    # The official ATS application link wins over the public detail page.
    assert row['application_url'].startswith('http')


def test_scope_without_a_matching_posting_is_an_empty_success(tmp_path):
    result, _ = run('惠普', 'campus', tmp_path)
    assert result['jobs'] == []
    coverage = result['coverage']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['scope_evidence']            # a complete read needs official evidence
    assert 'no 校园招聘 posting' in coverage['note']


def test_pagination_walks_start_until_the_official_count_is_reached(tmp_path):
    pages = [fixture('eightfold_search_hp_page0.json'),
             fixture('eightfold_search_hp_page1.json'),
             fixture('eightfold_search_empty.json')]
    result, calls = run('惠普', 'social', tmp_path, pages=pages)
    starts = [c.split('start=', 1)[1].split('&', 1)[0]
              for c in calls if '/api/pcsx/search' in c]
    assert starts == ['0', '10']
    assert result['coverage']['pagination_exhausted'] is True
    # 16 recorded rows over two pages; the one intern posting is not social.
    assert result['coverage']['expected_total'] == 15
    assert len(result['jobs']) == 15


def test_request_budget_stops_the_walk_and_reports_partial(tmp_path):
    pages = [fixture('eightfold_search_hp_page0.json'),
             fixture('eightfold_search_hp_page1.json'),
             fixture('eightfold_search_empty.json')]
    # Two page reads plus one detail: the third request is the first detail.
    result, calls = run('惠普', 'social', tmp_path, pages=pages, max_requests=3)
    coverage = result['coverage']
    assert coverage['request_budget_exhausted'] is True
    assert coverage['status'] == 'partial' and coverage['complete'] is False
    assert coverage['request_budget']['used'] == 3
    # The posting read before the budget ran out is still published.
    assert len(result['jobs']) == 1
    assert coverage['expected_total'] == 15


def test_direct_refusal_switches_to_the_public_page_and_keeps_evidence(tmp_path, monkeypatch):
    import qiuzhao.collector.p1_platform_eightfold as module
    seen = []

    def refusing(session, url, budget, referer):
        if budget is not None:
            budget['used'] += 1
        seen.append(url)
        raise module.DirectRefused('HTTP 403 on ' + url)

    class FakeHeadless:
        def __init__(self, entry, budget, allow_page_loads):
            self.page_loads = 0

        def search_page(self, start):
            self.page_loads += 1
            seen.append(f'headless:{start}')
            if start == 0:
                return fixture('eightfold_search_hp_page0.json')
            return fixture('eightfold_search_empty.json')

        def get_json(self, url):
            seen.append('headless-detail')
            position_id = url.split('position_id=', 1)[1].split('&', 1)[0]
            return {'data': stamp(fixture('eightfold_detail_hp.json'), position_id)}

        def close(self):
            pass

    monkeypatch.setattr(module, '_http_json', refusing)
    monkeypatch.setattr(module, '_HeadlessReader', FakeHeadless)
    result = module.collect('惠普', 'social', tmp_path)
    coverage = result['coverage']
    assert coverage['mode'] == 'headless'
    assert coverage['scope_request']['params']['transport'] == 'headless'
    assert 'switched to the public careers page' in coverage['note']
    assert any(s.startswith('headless:') for s in seen)
    assert coverage['errors'] == []


def test_evidence_files_are_the_files_actually_written(tmp_path):
    result, _ = run('惠普', 'intern', tmp_path,
                    detail=fixture('eightfold_detail_hp_intern.json'))
    coverage = result['coverage']
    assert coverage['evidence_files'] == coverage['evidence']
    for name in coverage['evidence_files']:
        path = tmp_path / name
        assert path.is_file() and path.stat().st_size
    # A directory glob would sweep in the pipeline's own empty adapter.log.
    (tmp_path / 'adapter.log').write_text('', encoding='utf-8')
    result2, _ = run('惠普', 'intern', tmp_path,
                     detail=fixture('eightfold_detail_hp_intern.json'))
    assert 'adapter.log' not in result2['coverage']['evidence_files']
