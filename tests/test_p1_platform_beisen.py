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
            ident = kwargs['params']['jobAdId']
            if ident == 'job-campus-2':
                return FakeResponse(payload=fixture('beisen_detail.json'))
            row = next(row for page in self.pages.values() for row in page['Data']
                       if row['Id'] == ident)
            return FakeResponse(payload={'Code': 200, 'Data': row})
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


class CacheSession(FakeSession):
    def __init__(self, pages, text=None):
        super().__init__(text or entry_html(), pages)
        self.posts = []
        self.details = []

    def post(self, url, **kwargs):
        self.posts.append(kwargs['json'])
        return super().post(url, **kwargs)

    def get(self, url, **kwargs):
        if 'GetJobAdInfo' in url:
            ident = kwargs['params']['jobAdId']
            self.details.append(ident)
            row = next(row for page in self.pages.values() for row in page['Data']
                       if row['Id'] == ident)
            return FakeResponse(payload={'Code': 200, 'Data': row})
        return super().get(url, **kwargs)


def cache_pages():
    rows = [{'Id': 'campus-id', 'CategoryId': '2', 'Category': '校园招聘',
             'JobAdName': '校招', 'Duty': '职责', 'Require': '要求', 'LocNames': ['北京']},
            {'Id': 'social-id', 'CategoryId': '1', 'Category': '社会招聘',
             'JobAdName': '社招', 'Duty': '职责', 'Require': '要求', 'LocNames': ['上海']}]
    return {0: {'Code': 200, 'Count': 2, 'Data': rows},
            1: {'Code': 200, 'Count': 2, 'Data': []}}


def cached_collect(tmp_path, scope, pages=None, text=None):
    session = CacheSession(pages if pages is not None else cache_pages(), text)
    with patch.object(beisen, '_make_session', return_value=session):
        result = beisen.collect('中信建投', scope, tmp_path)
    return result, session


def enable_cache(monkeypatch, tmp_path):
    monkeypatch.setenv('QIUZHAO_P1_LOGICAL_RUN_ID', 'offline-run')
    monkeypatch.setenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(tmp_path / 'cache'))


def test_same_run_list_reuse_keeps_scope_details_evidence_and_time(tmp_path, monkeypatch):
    enable_cache(monkeypatch, tmp_path)
    first, a = cached_collect(tmp_path / 'campus', 'campus')
    second, b = cached_collect(tmp_path / 'social', 'social')
    assert len(a.posts) == 2 and b.posts == []
    assert a.details == ['campus-id'] and b.details == ['social-id']
    assert first['coverage']['complete'] and second['coverage']['complete']
    assert second['coverage']['expected_total'] == 1
    assert second['coverage']['scope_request']['scope'] == 'social'
    assert second['jobs'][0]['source_record_id'] == 'social-id'
    assert second['jobs'][0]['list_checked_at'] == first['jobs'][0]['list_checked_at']
    assert second['jobs'][0]['detail_checked_at'] != first['jobs'][0]['detail_checked_at']
    assert second['coverage']['list_cache_reused'] is True
    for evidence in second['coverage']['evidence_files']:
        assert (tmp_path / 'social' / evidence).is_file()


def test_cache_identity_changes_miss(tmp_path, monkeypatch):
    enable_cache(monkeypatch, tmp_path)
    cached_collect(tmp_path / 'initial', 'campus')
    monkeypatch.setenv('QIUZHAO_P1_LOGICAL_RUN_ID', 'another-run')
    assert len(cached_collect(tmp_path / 'new-run', 'social')[1].posts) == 2
    monkeypatch.setenv('QIUZHAO_P1_LOGICAL_RUN_ID', 'offline-run')
    # Fixture portal values are discovered without assuming their spelling.
    import re
    changed_html = re.sub(r'("PortalId"\s*:\s*")[^"]+', r'\1another-portal', entry_html())
    assert len(cached_collect(tmp_path / 'portal', 'social', text=changed_html)[1].posts) == 2
    with patch.object(beisen, 'FIELDS', beisen.FIELDS + ['AnotherField']):
        assert len(cached_collect(tmp_path / 'fields', 'social')[1].posts) == 2
    config = tmp_path / 'config.json'
    config.write_text(beisen.CONFIG_PATH.read_text(encoding='utf-8') + '\n', encoding='utf-8')
    with patch.object(beisen, 'CONFIG_PATH', config):
        assert len(cached_collect(tmp_path / 'config', 'social')[1].posts) == 2
    body = {'PortalId': 'p', 'PageIndex': 0, 'PageSize': 50, 'Category': [],
            'KeyWords': '', 'SpecialType': 0, 'DisplayFields': beisen.FIELDS}
    identity = beisen._list_identity('tenant', 'https://a.example', 'https://a.example', body)
    baseline = beisen._list_cache_path(tmp_path, identity)
    for field, value in [('PageSize', 100), ('PageIndex', 1), ('KeyWords', 'query'),
                         ('Category', ['2']), ('SpecialType', 1)]:
        changed = beisen._list_identity('tenant', 'https://a.example', 'https://a.example',
                                        dict(body, **{field: value}))
        assert beisen._list_cache_path(tmp_path, changed) != baseline
    assert beisen._list_cache_path(tmp_path, dict(identity, entry_origin='https://other:443')) != baseline
    assert beisen._list_cache_path(tmp_path, dict(identity, tenant='other')) != baseline
    assert beisen._list_cache_path(tmp_path, dict(identity, origin='https://other:443')) != baseline


def test_incomplete_drifting_duplicate_or_failed_lists_not_cached(tmp_path, monkeypatch):
    enable_cache(monkeypatch, tmp_path)
    import copy
    variants = []
    for mutation in ('drift', 'duplicate', 'truncated', 'failed', 'unknown-total'):
        pages = copy.deepcopy(cache_pages())
        if mutation == 'drift':
            pages[1]['Count'] = 3
        elif mutation == 'duplicate':
            pages[0]['Data'][1]['Id'] = 'campus-id'
        elif mutation == 'truncated':
            pages[0]['Count'] = pages[1]['Count'] = 3
        elif mutation == 'failed':
            pages[0]['Code'] = 500
        else:
            pages[0]['Count'] = None
        variants.append(pages)
    for index, pages in enumerate(variants):
        result, _ = cached_collect(tmp_path / str(index), 'campus', pages)
        assert not result['coverage']['complete']
        assert not list((tmp_path / 'cache').rglob('*.json'))
    result, session = cached_collect(tmp_path / 'budget', 'campus')
    assert result['coverage']['complete'] and len(session.posts) == 2


def test_corrupt_missing_and_invalid_cached_pages_fall_back(tmp_path, monkeypatch):
    enable_cache(monkeypatch, tmp_path)
    cached_collect(tmp_path / 'initial', 'campus')
    path = next((tmp_path / 'cache').rglob('*.json'))
    good = json.loads(path.read_text())
    import copy
    invalid = []
    for field, value in [('complete', False), ('list_checked_at', 'bad'),
                         ('fetched_on', '2000-01-01')]:
        bad = dict(good, **{field: value})
        invalid.append(json.dumps(bad))
    bad = copy.deepcopy(good)
    bad['pages'][0]['Data'][1]['Id'] = 'campus-id'
    invalid.extend([json.dumps(bad), '{broken'])
    bad = copy.deepcopy(good)
    bad['pages'][0]['Data'][0]['Duty'] = 'silently changed valid row'
    invalid.append(json.dumps(bad))
    from datetime import datetime, timedelta, timezone
    invalid.append(json.dumps(dict(good, list_checked_at=(
        datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())))
    bad = copy.deepcopy(good)
    bad['pages'].pop()
    invalid.append(json.dumps(bad))
    for index, content in enumerate(invalid):
        path.write_text(content)
        result, session = cached_collect(tmp_path / f'bad-{index}', 'social')
        assert len(session.posts) == 2 and result['coverage']['complete']
    path.unlink()
    assert len(cached_collect(tmp_path / 'missing', 'social')[1].posts) == 2


def test_budget_failure_does_not_store_snapshot(tmp_path, monkeypatch):
    enable_cache(monkeypatch, tmp_path)
    session = CacheSession(cache_pages())
    with patch.object(beisen, '_make_session', return_value=session):
        result = beisen.collect('中信建投', 'campus', tmp_path / 'scope', max_requests=2)
    assert not result['coverage']['complete']
    assert not list((tmp_path / 'cache').rglob('*.json'))


def test_list_only_hit_preserves_actual_verification_time(tmp_path, monkeypatch):
    enable_cache(monkeypatch, tmp_path)
    with patch.object(beisen, 'DETAIL_VERIFY_LIMIT', 0):
        first, _ = cached_collect(tmp_path / 'initial', 'campus')
        second, session = cached_collect(tmp_path / 'again', 'campus')
    assert session.posts == [] and session.details == []
    old = first['jobs'][0]['list_checked_at']
    job = second['jobs'][0]
    assert job['list_checked_at'] == job['verified_at'] == job['reviewed_at'] == old
    assert 'detail_checked_at' not in job


def collect_with_detail(tmp_path, detail):
    session = CacheSession(cache_pages())
    original_get = session.get
    def get(url, **kwargs):
        if 'GetJobAdInfo' in url and kwargs['params']['jobAdId'] == 'campus-id':
            return FakeResponse(payload={'Code': 200, 'Data': detail})
        return original_get(url, **kwargs)
    session.get = get
    with patch.object(beisen, '_make_session', return_value=session):
        return beisen.collect('中信建投', 'campus', tmp_path), session


def test_cached_list_fresh_detail_replaces_business_content(tmp_path, monkeypatch):
    enable_cache(monkeypatch, tmp_path)
    old, _ = cached_collect(tmp_path / 'old', 'campus')
    cache_path = next((tmp_path / 'cache').rglob('*.json'))
    raw_before = cache_path.read_bytes()
    detail = dict(cache_pages()[0]['Data'][0], JobAdName='NEW title',
                  Duty='NEW duty', Require='NEW requirement', LocNames=['深圳'],
                  Category='NEW official campus label')
    fresh, session = collect_with_detail(tmp_path / 'fresh', detail)
    job = fresh['jobs'][0]
    assert session.posts == []
    assert job['title'] == 'NEW title' and job['cities'] == ['深圳']
    assert 'NEW duty' in job['description_raw'] and 'NEW requirement' in job['description_raw']
    assert job['recruitment_type_raw']['Category'] == 'NEW official campus label'
    assert job['detail_source'] == 'official_detail' and job['detail_verified']
    assert job['verified_at'] == job['reviewed_at'] == job['detail_checked_at']
    assert job['list_checked_at'] == old['jobs'][0]['list_checked_at']
    assert job['verified_at'] != job['list_checked_at']
    assert cache_path.read_bytes() == raw_before


def test_cached_detail_category_conflict_is_quarantined(tmp_path, monkeypatch):
    enable_cache(monkeypatch, tmp_path)
    cached_collect(tmp_path / 'old', 'campus')
    detail = dict(cache_pages()[0]['Data'][0], CategoryId='1', Category='社会招聘')
    result, session = collect_with_detail(tmp_path / 'conflict', detail)
    assert session.posts == [] and result['jobs'] == []
    assert not result['coverage']['complete'] and not result['coverage']['detail_complete']
    assert result['coverage']['expected_total'] == 1
    assert any('identity/category mismatch' in error for error in result['coverage']['errors'])


def test_detail_omission_retains_list_values_without_source_missing(tmp_path, monkeypatch):
    enable_cache(monkeypatch, tmp_path)
    old, _ = cached_collect(tmp_path / 'old', 'campus')
    for missing in ('Duty', 'Require', 'LocNames', 'JobAdName', 'Category'):
        detail = dict(cache_pages()[0]['Data'][0], JobAdName='NEW title', Duty='NEW duty')
        detail.pop(missing)
        result, session = collect_with_detail(tmp_path / missing, detail)
        job = result['jobs'][0]
        assert session.posts == []
        assert job['title'] == ('校招' if missing == 'JobAdName' else 'NEW title')
        assert job['cities'] == ['北京']
        assert job['detail_source'] == 'official_list_and_detail' and job['detail_verified']
        assert job['verified_at'] == job['reviewed_at'] == old['jobs'][0]['list_checked_at']
        assert missing in job['detail_missing_fields'] and missing not in job['source_missing_fields']
        assert result['coverage']['complete']
        assert job['detail_presentation']


def test_cache_hit_failed_detail_preserves_list_fact_time(tmp_path, monkeypatch):
    enable_cache(monkeypatch, tmp_path)
    old, _ = cached_collect(tmp_path / 'old', 'campus')
    session = CacheSession(cache_pages())
    original_get = session.get
    def get(url, **kwargs):
        if 'GetJobAdInfo' in url:
            return FakeResponse(payload={'Code': 500, 'Data': {}})
        return original_get(url, **kwargs)
    session.get = get
    with patch.object(beisen, '_make_session', return_value=session):
        result = beisen.collect('中信建投', 'campus', tmp_path / 'failed')
    job = result['jobs'][0]
    assert session.posts == [] and job['title'] == '校招'
    assert job['detail_source'] == 'official_list' and not job.get('detail_verified')
    assert job['verified_at'] == job['reviewed_at'] == old['jobs'][0]['list_checked_at']
    assert 'detail_checked_at' not in job and result['coverage']['detail_fetch_errors']


def collect_rich_list_detail(tmp_path, detail, monkeypatch, list_degree='硕士'):
    row = dict(cache_pages()[0]['Data'][0], LocNames=['北京市', '上海市'], Degree=list_degree,
               Duty='负责旧职责。', Require='机械工程专业，硕士及以上。',
               PostDate='2026-09-01', EndTime='2026-12-31', YearsOfWorking='应届')
    pages = {0: {'Code': 200, 'Count': 1, 'Data': [row]},
             1: {'Code': 200, 'Count': 1, 'Data': []}}
    def call(path, payload=None):
        session = CacheSession(pages)
        original_get = session.get
        def get(url, **kwargs):
            if payload is not None and 'GetJobAdInfo' in url:
                return FakeResponse(payload={'Code': 200, 'Data': payload})
            return original_get(url, **kwargs)
        session.get = get
        with patch.object(beisen, '_make_session', return_value=session):
            return beisen.collect('中信建投', 'campus', path), session
    enable_cache(monkeypatch, tmp_path)
    old, _ = call(tmp_path / 'old')
    fresh, session = call(tmp_path / 'fresh', detail)
    return old, fresh, session


def test_detail_omitted_fields_keep_same_run_list_facts_and_public_projection(tmp_path, monkeypatch):
    from qiuzhao.v4_fields import to_item
    detail = {'Id': 'campus-id', 'CategoryId': '2', 'JobAdName': '新标题',
              'Duty': '负责新职责。', 'Require': '统计学专业。'}
    old, result, session = collect_rich_list_detail(tmp_path, detail, monkeypatch)
    job = result['jobs'][0]
    public = to_item(job)
    assert session.posts == [] and result['coverage']['complete']
    assert public['cities'] == ['北京', '上海'] and public['education_raw'] == '硕士'
    assert public['job_title'] == '新标题' and public['major_requirements_raw'] == '统计学专业'
    assert '机械工程' not in public['major_requirements_raw']
    checked = old['coverage']['list_checked_at']
    assert job['field_provenance']['cities']['source'] == 'official_list'
    assert job['field_provenance']['cities']['checked_at'] == checked
    assert job['field_provenance']['education_raw']['checked_at'] == checked
    assert public['reviewed_at'] == job['verified_at'] == checked
    assert job['field_provenance']['major_requirements_raw']['source'] == 'official_detail'
    assert job['field_provenance']['major_requirements_raw']['checked_at'] == job['detail_checked_at']
    assert 'Degree' in job['detail_missing_fields'] and 'Degree' not in job['source_missing_fields']
    assert job['detail_source'] == 'official_list_and_detail'


def test_get_dto_null_and_empty_keep_verified_facts_not_patch_clear(tmp_path, monkeypatch):
    from qiuzhao.v4_fields import to_item
    detail = {'Id': 'campus-id', 'CategoryId': '2', 'Category': '校园招聘',
              'JobAdName': '新标题', 'Duty': '新职责', 'Require': None,
              'LocNames': [], 'Degree': None, 'PostDate': None, 'EndTime': ''}
    old, result, _ = collect_rich_list_detail(tmp_path, detail, monkeypatch)
    job = result['jobs'][0]
    public = to_item(job)
    assert public['cities'] == ['北京', '上海'] and public['education_raw'] == '硕士'
    assert public['major_requirements_raw'] == '机械工程专业，硕士及以上'
    assert public['published_at'] == '2026-09-01' and job['deadline_raw'] == '2026-12-31'
    assert '新职责' in public['description_raw'] and '机械工程' in public['description_raw']
    assert job['field_provenance']['cities']['source'] == 'official_list'
    assert job['field_provenance']['cities']['checked_at'] == old['coverage']['list_checked_at']
    assert public['reviewed_at'] == old['coverage']['list_checked_at']
    assert set(job['detail_unprovided_fields']) == {'Require', 'LocNames', 'Degree', 'PostDate', 'EndTime'}
    assert not job['source_missing_fields']
    assert '未提供' in public['detail_presentation'] and '不能证明招聘方清空' in public['detail_presentation']


def test_latest_require_is_only_major_source_and_prior_degree_remains_evidence(tmp_path, monkeypatch):
    from qiuzhao.v4_fields import to_item
    detail = {'Id': 'campus-id', 'CategoryId': '2', 'JobAdName': '新标题',
              'Duty': '负责新职责。', 'Require': '计算机科学与技术专业，本科及以上学历。'}
    old, result, _ = collect_rich_list_detail(tmp_path, detail, monkeypatch)
    job = result['jobs'][0]
    public = to_item(job)
    assert public['major_requirements_raw'] == '计算机科学与技术专业，本科及以上学历'
    assert '机械工程' not in public['major_requirements_raw']
    assert public['education_raw'] == '本科及以上学历'
    assert job['source_fields']['Degree'] == '硕士'
    assert job['field_observation_differences']['education_raw']['list_checked_at'] == old['coverage']['list_checked_at']
    assert job['field_provenance']['education_raw']['source'] == 'official_detail'
    assert job['field_observation_differences']['education_raw']['relation'] == 'compatible'
    assert '硕士' in public['detail_presentation'] and '本科及以上学历' in public['detail_presentation']
    assert '兼容表述差异' in public['detail_presentation']
    from datetime import date
    from qiuzhao.tools import Jobs
    exported = Jobs.public(public, date(2026, 10, 9))
    assert exported['detail_presentation'] == public['detail_presentation']
    assert exported['reviewed_at'] == old['coverage']['list_checked_at']


def test_education_preference_is_not_a_hard_gate_and_is_publicly_explained(tmp_path, monkeypatch):
    from qiuzhao.v4_fields import to_item
    detail = {'Id': 'campus-id', 'CategoryId': '2', 'JobAdName': '新标题',
              'Duty': '新职责', 'Require': '计算机专业，本科优先或同等经验。'}
    old, result, _ = collect_rich_list_detail(tmp_path, detail, monkeypatch)
    job = result['jobs'][0]
    public = to_item(job)
    assert public['education_raw'] == '硕士'
    assert job['field_provenance']['education_raw']['source'] == 'official_list'
    assert job['field_provenance']['education_raw']['checked_at'] == old['coverage']['list_checked_at']
    assert '硬性学历门槛' in public['status_note'] and '待核验' in public['status_note']
    assert '本科优先或同等经验' in public['detail_presentation']
    assert 'Degree' not in job['source_missing_fields']


def test_true_education_difference_keeps_both_observations_and_public_note(tmp_path, monkeypatch):
    from qiuzhao.v4_fields import to_item
    detail = {'Id': 'campus-id', 'CategoryId': '2', 'JobAdName': '新标题',
              'Duty': '新职责', 'Require': '博士学历，计算机专业。'}
    old, result, _ = collect_rich_list_detail(tmp_path, detail, monkeypatch, list_degree='仅限硕士学历')
    job = result['jobs'][0]
    public = to_item(job)
    assert public['education_raw'] == '博士学历'
    difference = job['field_observation_differences']['education_raw']
    assert difference['relation'] == 'conflicting' and difference['list_degree'] == '仅限硕士学历'
    assert difference['list_checked_at'] == old['coverage']['list_checked_at']
    assert difference['detail_checked_at'] == job['detail_checked_at']
    assert '冲突' in public['status_note'] and '待核验' in public['status_note']
    assert '硕士' in public['detail_presentation'] and '博士学历' in public['detail_presentation']
    assert 'Degree' not in job['source_missing_fields']
    from datetime import date
    from qiuzhao.tools import Jobs
    assert '冲突' in Jobs.public(public, date(2026, 10, 9))['status_note']


def test_plain_degree_summary_is_not_declared_a_true_conflict(tmp_path, monkeypatch):
    from qiuzhao.v4_fields import to_item
    detail = {'Id': 'campus-id', 'CategoryId': '2', 'JobAdName': '新标题',
              'Duty': '新职责', 'Require': '博士学历，计算机专业。'}
    _, result, _ = collect_rich_list_detail(tmp_path, detail, monkeypatch)
    job = result['jobs'][0]
    assert job['field_observation_differences']['education_raw']['relation'] == 'unresolved'
    public = to_item(job)
    assert public['education_raw'] == '博士学历'
    assert '未能确认' in public['detail_presentation'] and '待核验' in public['status_note']
    assert job['source_fields']['beisen_list_Degree'] == '硕士'


def rich_collect_to_public_chain(tmp_path, detail, monkeypatch):
    from datetime import date
    from qiuzhao.collector import p1_pipeline as pipeline
    from qiuzhao.normalize import normalize_records
    from qiuzhao.v4_fields import to_item
    from qiuzhao.tools import Jobs
    old, result, _ = collect_rich_list_detail(tmp_path, detail, monkeypatch)
    before = pipeline.validate_result(old, '中信建投', 'campus', tmp_path / 'old')
    previous, _ = pipeline.merge_records([], [('中信建投', 'campus', before)])
    after = pipeline.validate_result(result, '中信建投', 'campus', tmp_path / 'fresh')
    merged, _ = pipeline.merge_records(previous, [('中信建投', 'campus', after)])
    normalize_records(merged)
    assert len(merged) == 1
    return old, merged[0], Jobs.public(to_item(merged[0]), date(2026, 10, 9))


def test_complete_qualification_sentence_does_not_drop_experience_alternative(tmp_path, monkeypatch):
    clause = '本科及以上学历，或具有同等工作经验。'
    detail = {'Id': 'campus-id', 'CategoryId': '2', 'JobAdName': '新标题',
              'Duty': '新职责', 'Require': clause}
    old, job, public = rich_collect_to_public_chain(tmp_path, detail, monkeypatch)
    assert public['education_raw'] == '硕士'
    assert clause in public['description_raw']
    assert '同等工作经验' in public['detail_presentation']
    assert '未结构化' in public['status_note']
    assert job['field_provenance']['education_raw']['source'] == 'official_list'
    assert public['reviewed_at'] == old['coverage']['list_checked_at']
    assert 'Degree' not in public.get('source_missing_fields', [])


def test_explicit_prefix_minimum_qualification_survives_public_chain(tmp_path, monkeypatch):
    clause = '学历要求不低于本科。'
    detail = {'Id': 'campus-id', 'CategoryId': '2', 'JobAdName': '新标题',
              'Duty': '新职责', 'Require': clause}
    old, job, public = rich_collect_to_public_chain(tmp_path, detail, monkeypatch)
    assert public['education_raw'] == '学历要求不低于本科'
    assert job['field_provenance']['education_raw']['source'] == 'official_detail'
    assert '硕士' in public['detail_presentation'] and '兼容表述差异' in public['detail_presentation']
    assert job['source_fields']['beisen_list_Degree'] == '硕士'
    assert public['reviewed_at'] == old['coverage']['list_checked_at']


import pytest


@pytest.mark.parametrize('disclosure', ['omitted', 'null', 'empty', 'new_value'])
def test_list_city_fact_semantics_survive_actual_merge_and_public_chain(tmp_path, monkeypatch, disclosure):
    detail = {'Id': 'campus-id', 'CategoryId': '2', 'JobAdName': '新标题',
              'Duty': '新职责', 'Require': '统计学专业。'}
    if disclosure == 'null':
        detail['LocNames'] = None
    elif disclosure == 'empty':
        detail['LocNames'] = []
    elif disclosure == 'new_value':
        detail['LocNames'] = ['深圳市']
    old, job, public = rich_collect_to_public_chain(tmp_path, detail, monkeypatch)
    if disclosure == 'new_value':
        assert public['cities'] == ['深圳']
        assert job['field_provenance']['cities']['source'] == 'official_detail'
        assert job['field_provenance']['cities']['checked_at'] == job['detail_checked_at']
    else:
        assert public['cities'] == ['北京', '上海']
        assert job['field_provenance']['cities']['source'] == 'official_list'
        assert job['field_provenance']['cities']['checked_at'] == old['coverage']['list_checked_at']
        assert public['reviewed_at'] == old['coverage']['list_checked_at']
        assert '城市' in public['detail_presentation']
    assert 'LocNames' not in public.get('source_missing_fields', [])
    assert not job.get('location_clear_marker')


def test_adjacent_qualification_alternative_is_preserved_unstructured(tmp_path, monkeypatch):
    clause = '本科及以上学历。或具有同等工作经验。'
    detail = {'Id': 'campus-id', 'CategoryId': '2', 'JobAdName': '新标题',
              'Duty': '新职责', 'Require': clause}
    _, _, public = rich_collect_to_public_chain(tmp_path, detail, monkeypatch)
    assert public['education_raw'] == '硕士'
    assert clause in public['description_raw'] and '未结构化' in public['status_note']


def test_leading_at_least_requirement_is_not_lost_in_public_chain(tmp_path, monkeypatch):
    detail = {'Id': 'campus-id', 'CategoryId': '2', 'JobAdName': '新标题',
              'Duty': '新职责', 'Require': '学历要求至少本科。'}
    _, job, public = rich_collect_to_public_chain(tmp_path, detail, monkeypatch)
    assert public['education_raw'] == '学历要求至少本科'
    assert public['education'] == '本科'
    assert job['field_provenance']['education_raw']['source'] == 'official_detail'
    assert '兼容表述差异' in public['detail_presentation']


@pytest.mark.parametrize('clause', [
    '本科及以上学历，硕士优先。',
    '本科及以上学历，计算机专业，有互联网经验者优先。',
    '本科及以上学历，具有同等岗位经验者优先。',
])
def test_independent_preference_does_not_erase_explicit_minimum_public_chain(tmp_path, monkeypatch, clause):
    detail = {'Id': 'campus-id', 'CategoryId': '2', 'JobAdName': '新标题',
              'Duty': '新职责', 'Require': clause}
    _, job, public = rich_collect_to_public_chain(tmp_path, detail, monkeypatch)
    assert public['education_raw'] == '本科及以上学历'
    assert public['education'] == '本科'
    assert clause in public['description_raw']
    assert job['field_provenance']['education_raw']['source'] == 'official_detail'
    assert '硕士优先' not in public['education_raw']


@pytest.mark.parametrize('clause, hard, ambiguous', [
    ('学历要求不低于本科。', '学历要求不低于本科', False),
    ('本科及以上学历者优先。', '', True),
    ('本科及以上学历，硕士优先。', '本科及以上学历', True),
    ('本科及以上学历，或具有同等工作经验。', '', True),
])
def test_four_narrow_qualification_semantics(clause, hard, ambiguous):
    assert beisen._hard_education(clause) == (hard, ambiguous)
