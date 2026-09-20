"""Fixture tests for the tupu360 multi-tenant platform adapter.

Every fixture under ``tests/fixtures/tupu360`` is a public page or fragment
recorded on 2026-09-19: the 14-tenant field survey (IQVIA / 礼来 / 舍弗勒 / 茵梦达
list fragments, two position/detail pages, the wxtemp WeChat QR gate and the
careersite "site disabled" notice) plus, from the full-site run, the three
康龙化成 social pages used by the pagination-depth tests
(``pharmaron-bj-SOCIALRECRUITMENT-list-1.html``, ``pharmaron-bj-social-page-2.html``,
``pharmaron-bj-social-page-56.html``). No live page is fetched here.
"""
import json
from pathlib import Path

import pytest

from qiuzhao.collector import p1_pipeline as pipeline
from qiuzhao.collector import p1_platform_tupu360 as tupu

FIXTURES = Path(__file__).parent / 'fixtures' / 'tupu360'
CONFIG = json.loads((Path(tupu.__file__).with_name('p1_platform_companies.json'))
                    .read_text(encoding='utf-8'))['tupu360']


def page(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


@pytest.fixture
def entry_override(monkeypatch):
    """Patch one config line in-memory (the module re-reads the file per call).

    The whole tupu360 section ships parked (``enabled: false``) because the
    platform robots.txt is a site-wide ``Disallow: /``, so the fixture enables
    the row by default: a collection test states that it runs an explicitly
    enabled line. Pass ``enabled=False`` to model a parked row.
    """
    original = tupu._read_platform()
    original_reader = tupu._read_platform

    def apply(key, **fields):
        data = {section: dict(value) if isinstance(value, dict) else value
                for section, value in original.items()}
        data[key] = {**data.get(key, {}), 'enabled': True, **fields}
        for field, value in fields.items():
            if value is None:
                data[key].pop(field, None)
        monkeypatch.setattr(tupu, '_read_platform', lambda: data)
        tupu.reload_config()
        return data

    yield apply
    # Restore the real reader before reloading, otherwise the teardown reload
    # would keep the overridden config alive for the next test.
    monkeypatch.setattr(tupu, '_read_platform', original_reader)
    tupu.reload_config()


# --------------------------------------------------------------------------- #
# config contract
# --------------------------------------------------------------------------- #
def test_every_configured_line_is_a_company_and_disabled_lines_stay_out():
    # 2026-09-19 站长口径：tupu360 全站 robots.txt 是平台级 `Disallow: /`，整段默认留档。
    # collector-next-6 把 20260919g 全站批次的 54 个公开 careersite 租户并进来（连同原先
    # 实测可读的 6 个，共 60 个 careersite 行），但**一行都不启用**——所以本节 68 行
    # （60 careersite + 8 个匿名侧拿不到的调查行）必须全部 enabled:false 且带 blocked_reason，
    # REGISTRY 里一个都不出现。要启用某一家只需把该行 enabled 改成 true（见 _README）。
    declared = {key: entry for key, entry in CONFIG.items() if not str(key).startswith('_')}
    assert len(declared) == 68
    enabled = [key for key, entry in declared.items() if entry.get('enabled') is not False]
    disabled = [key for key, entry in declared.items() if entry.get('enabled') is False]
    assert enabled == [] and len(disabled) == 68
    for key, entry in declared.items():
        assert entry.get('name'), key
        assert entry.get('note'), key
        assert entry.get('blocked_reason'), key
    assert tupu.COMPANIES == {}
    assert tupu.merged_registry() == {}


def test_survey_tenants_stay_on_file_and_can_be_enabled_explicitly(entry_override):
    # 六个实测可读的 careersite 租户仍然留在配置里（含入口 URL 与实测条数），
    # 只有显式 enabled=True 才会重新进 REGISTRY。
    for key in ('iqvia', 'lilly', 'schaeffler', 'bmw', 'innomotics', 'jnj'):
        assert CONFIG[key]['enabled'] is False, key
        assert CONFIG[key].get('blocked_reason'), key
    entry_override('schaeffler')
    assert set(tupu.COMPANIES) == {'schaeffler'}
    assert tupu.merged_registry() == {'舍弗勒': tupu.MODULE_PATH}
    entry_override('iqvia')
    assert tupu.resolve('IQVIA 艾昆纬') == 'iqvia'
    assert tupu.resolve('iqvia') == 'iqvia'


def test_fullsite_tenants_are_public_careersite_hosts_and_stay_parked(entry_override):
    """The 20260919g full-site batch: 60 careersite rows, all shipped disabled.

    collector-next-6 imports the batch's *configuration* (60 real tenants, all with
    real postings on their public pages) but not its enablement: the platform
    robots.txt is a site-wide ``Disallow: /``, so every row is parked until 站长
    decides.  What must still hold is that each parked careersite row is the public
    careersite product -- a wxtemp ``<slug>.tupu360.com`` host must never sit in the
    section as an enable-ready line.
    """
    declared = {key: entry for key, entry in CONFIG.items() if not str(key).startswith('_')}
    careersite = [key for key, entry in declared.items()
                  if 'careersite tenant' in str(entry.get('note'))]
    assert len(careersite) == 60
    assert {'iqvia', 'lilly', 'schaeffler', 'bmw', 'innomotics'} <= set(careersite)
    assert 'pharmaron-bj' in careersite          # the 828-posting pagination case
    public = [key for key in declared if not tupu.is_wechat_only(key)]
    assert set(public) == set(careersite) | {'jnj'}   # jnj = customer-hosted careersite
    for key in public:
        assert declared[key].get('enabled') is False, key
        host = tupu.tenant_host(key)
        # shared careersite host, or a customer-hosted careersite (jnj) -- never a
        # wxtemp <slug>.tupu360.com host.
        assert host == tupu.PUBLIC_HOST or not host.endswith('tupu360.com'), (key, host)
    # Enabling is a single-field flip, and it takes effect on the next config load.
    entry_override('pharmaron-bj')
    assert set(tupu.COMPANIES) == {'pharmaron-bj'}
    assert tupu.merged_registry() == {'康龙化成（北京）新药技术股份有限公司': tupu.MODULE_PATH}
    assert tupu.resolve('康龙化成（北京）新药技术股份有限公司') == 'pharmaron-bj'


def test_wechat_only_tenants_are_exactly_the_declared_wxtemp_hosts():
    for key in ('nestle', 'taitaile', 'autoliv', 'louisvuitton', 'jntl', 'google',
                'boschhuayu-steering'):
        assert tupu.is_wechat_only(key) is True, key
    for key in ('iqvia', 'lilly', 'schaeffler', 'bmw', 'innomotics', 'johnsonelectric'):
        assert tupu.is_wechat_only(key) is False, key
    # A customer-hosted careersite is not the wxtemp product.
    assert tupu.is_wechat_only('jnj') is False
    assert tupu.tenant_host('jnj') == 'chinacampus.jnj.com.cn'
    assert tupu.tenant_slug('taitaile') == 'nestle'


def test_channels_and_extra_channels_come_from_the_config():
    assert tupu.channel_for('schaeffler', 'campus') == 'CAMPUSRECRUITMENT'
    assert tupu.channel_for('schaeffler', 'intern') == 'INTERNSHIPRECRUITMENT'
    assert tupu.channels_for('schaeffler', 'intern') == ['INTERNSHIPRECRUITMENT',
                                                         'TECHNOLOGYRUITMENT']
    assert tupu.fallback_channels_for('iqvia', 'campus') == ['CAMPUSAMBASSADORRECRUITMENT']
    assert tupu.fallback_channels_for('iqvia', 'social') == []


def test_urls_follow_the_tenant_and_the_custom_host():
    assert tupu.list_url('iqvia', 'CAMPUSRECRUITMENT') == (
        'https://careersite.tupu360.com/iqvia/position/index?recruitmentType=CAMPUSRECRUITMENT')
    assert tupu.next_page_url('jnj') == 'https://chinacampus.jnj.com.cn/jnj/position/nextPageList'
    assert tupu.detail_url('jnj', 'abc', 'CAMPUSRECRUITMENT').startswith(
        'https://chinacampus.jnj.com.cn/jnj/position/detail?positionId=abc')


# --------------------------------------------------------------------------- #
# list parsing
# --------------------------------------------------------------------------- #
def test_template_a_maps_columns_positionally_not_by_css_class():
    # IQVIA reuses the e-salary class for 业务 / 职位类别 / 工作地点, so a class-keyed
    # lookup would return the wrong field for every one of them.
    parsed = tupu.parse_list(page('list-template-a-iqvia.html'))
    assert parsed['template'] == 'A'
    assert [label for _, label in parsed['columns']] == ['职位名称', '业务', '职位类别', '工作地点', '发布日期']
    assert len(parsed['rows']) == 12
    first = parsed['rows'][0]
    assert first['pid'] == '6a9005d87280da28da078e36'
    assert first['title'] == '大连2027日语PV校招实习生'
    assert first['city'] == '辽宁省-大连'          # 工作地点, not 业务 / 职位类别
    assert first['function'] == 'B研发解决方案'    # 业务
    assert first['published_at'] == '2026-09-15'
    assert 'positionId=6a9005d87280da28da078e36' in first['detail_url']


def test_template_a_reads_the_pager_and_the_channel_subtitle():
    parsed = tupu.parse_list(page('list-template-a-lilly.html'))
    assert parsed['template'] == 'A'
    assert parsed['sub_title'] == '校园招聘'
    assert parsed['pages'] == 2
    assert parsed['page_size'] == 15
    assert len(parsed['rows']) == 15
    assert parsed['rows'][0]['published_at'] == '2026-09-01'


def test_template_a_page_two_fragment_parses_as_a_list_too():
    parsed = tupu.parse_list(page('nextpage-template-a-lilly.html'))
    assert parsed['template'] == 'A'
    assert len(parsed['rows']) == 3          # page-2 fragment: header row is not a posting
    assert [row['title'] for row in parsed['rows']] == [
        '2027 Campus Program-Lilly CA&Policy Trainee',
        '2027 Campus- Suzhou Manufacturing Trainee (Engineering)',
        '2027 Campus- Suzhou Manufacturing Trainee (Quality)']


def test_template_b_card_fields_including_headcount_and_posted_date():
    parsed = tupu.parse_list(page('list-template-b-schaeffler.html'))
    assert parsed['template'] == 'B'
    assert parsed['total_label'] == 2
    assert parsed['pages'] == 1
    assert len(parsed['rows']) == 2
    first = parsed['rows'][0]
    assert first['pid'] == '6a9fc9d27280da28da07968f'
    assert first['title'] == '机器人关节软件开发实习生（控制/驱动方向）'
    assert first['city'] == '苏州-太仓'
    # This tenant publishes 学历 in the second e-city slot, so the card's own value
    # is reported verbatim instead of a guessed 职能类别.
    assert first['function'] == '硕士'
    assert first['published_at'] == '2026-09-08'
    assert first['headcount_raw'] == '招聘人数：1'
    assert first['detail_url'] == ''  # built from the official pid by the adapter


def test_template_b_strips_a_tenant_label_baked_into_the_city_cell():
    parsed = tupu.parse_list(page('list-template-b-innomotics.html'))
    assert parsed['template'] == 'B'
    assert parsed['total_label'] == 3
    first = parsed['rows'][0]
    assert first['title'] == 'IN LV 校园招聘 E.D.G.E 新锐项目 上海'
    assert first['city'] == '上海'      # the page itself says "城市上海"
    assert first['function'] == '公司ILD'  # plain li.ele label, no e-city class
    assert first['published_at'] == '2026-09-11'


def test_template_b_reads_a_labelled_city_line_without_an_e_city_cell():
    # 强生's campus cards carry one "工作地点：北京" line and no e-city class, so the
    # card text (not a guessed field) is what the city is read from.
    parsed = tupu.parse_list(page('list-template-b-jnj-campus.html'))
    assert parsed['template'] == 'B'
    assert parsed['total_label'] == 18
    assert len(parsed['rows']) == 18
    first = parsed['rows'][0]
    assert first['pid'] == '6aa11f1a7280da28da0797fd'
    assert first['title'] == '环境、健康与安全管理部管理培训生'
    assert first['city'] == '北京'
    assert first['function'] == ''              # the card states no 职能类别
    assert first['published_at'] == '2026-09-09'
    assert first['list_text'] == ('环境、健康与安全管理部管理培训生 工作地点：北京 发布于: 2026-09-09')
    assert '<div' not in first['list_text'] and 'pid=' not in first['list_text']
    multi = parsed['rows'][1]
    assert multi['city'] == '北京,上海'


def test_recorded_card_text_never_leaks_markup():
    for name in ('list-template-b-schaeffler.html', 'list-template-b-innomotics.html'):
        for row in tupu.parse_list(page(name))['rows']:
            assert '<' not in row['list_text'] and 'data-action' not in row['list_text']


def test_empty_and_gate_pages_yield_no_rows_and_never_guess():
    for name in ('wechat-qr-gate-nestle.html', 'careersite-disabled.html'):
        parsed = tupu.parse_list(page(name))
        assert parsed['rows'] == []
        assert parsed['template'] == ''


# --------------------------------------------------------------------------- #
# detail parsing
# --------------------------------------------------------------------------- #
def test_detail_template_a_reads_title_description_and_posted_date():
    parsed = tupu.parse_detail(page('detail-template-a-lilly.html'))
    assert parsed['title'] == '2027 Campus Program-Lilly Marketing Academy'
    assert parsed['status_raw'] == 'PUBLISHING'
    assert parsed['published_at'] == '2026-09-01'
    assert parsed['city'] == '上海'
    assert parsed['function'] == '市场'
    assert 'Lilly Marketing Academy' in parsed['description_html']
    assert '立即申请' not in parsed['description_html']


def test_detail_template_b_reads_description_and_status():
    parsed = tupu.parse_detail(page('detail-template-b-schaeffler.html'))
    assert parsed['title'] == '财务部项目协调员 Project Office Coord.（太仓）'
    assert parsed['status_raw'] == 'PUBLISHING'
    assert 'Project Office Coord.' in parsed['description_html']
    assert 'Qualifications' in parsed['description_html']


def test_iso_date_never_invents_a_value():
    assert tupu._iso_date('发布于: 2026-09-18') == '2026-09-18'
    assert tupu._iso_date('2026年9月1日') == '2026-09-01'
    assert tupu._iso_date('即将截止') == ''
    assert tupu._iso_date('') == ''
    assert tupu._iso_date('2026-13-45') == ''


def test_deadline_is_only_read_when_the_posting_states_one():
    assert tupu._deadline_from_text('投递截止日期：2026-10-31') == '2026-10-31'
    assert tupu._deadline_from_text('欢迎应届生投递') == ''


# --------------------------------------------------------------------------- #
# collect() with recorded pages
# --------------------------------------------------------------------------- #
def run(company, scope, tmp_path, routes, calls=None):
    """collect() driven by a recorded url -> html map; no network is touched."""
    seen = calls if calls is not None else []

    def fake_get(session, url, budget):
        tupu._spend(budget)
        seen.append(url)
        for needle, body in routes.items():
            if needle in url:
                return FakeResponse(body, url)
        raise AssertionError('unexpected GET ' + url)

    def fake_post(session, url, data, budget, referer=None):
        tupu._spend(budget)
        seen.append(url + '?' + '&'.join(f'{k}={v}' for k, v in data.items()))
        for needle, body in routes.items():
            if needle in url:
                return FakeResponse(body, url)
        raise AssertionError('unexpected POST ' + url)

    original = (tupu._get, tupu._post)
    tupu._get, tupu._post = fake_get, fake_post
    try:
        return tupu.collect(company, scope, tmp_path)
    finally:
        tupu._get, tupu._post = original


class FakeResponse:
    def __init__(self, text, url):
        self.text = text
        self.url = url
        self.status_code = 200
        self.content = text.encode('utf-8')


def test_collect_uses_the_public_list_plus_detail_pages(tmp_path, entry_override):
    entry_override('schaeffler', extra_channels=None, channels={'intern': 'INTERNSHIPRECRUITMENT'})
    routes = {
        '/position/index': page('list-template-b-schaeffler.html'),
        '/position/detail': page('detail-template-b-schaeffler.html'),
    }
    calls = []
    result = run('舍弗勒', 'intern', tmp_path, routes, calls)
    coverage = result['coverage']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['expected_total'] == 2 and coverage['collected_jobs'] == 2
    assert coverage['channels_used'] == ['INTERNSHIPRECRUITMENT:html']
    assert [job['source_record_id'] for job in result['jobs']] == [
        '6a9fc9d27280da28da07968f', '6a3a6a8bcf856c3f733f6d64']
    first = result['jobs'][0]
    # No 发布时间 on this tenant's detail page, so the official list column is used.
    assert first['published_at'] == '2026-09-08'
    assert first['published_at_source'] == 'official posting-list 发布日期 column'
    assert first['city'] == '苏州-太仓'
    assert first['deadline_raw'] == ''            # the posting states none
    assert first['cohort_raw'] == ''              # never inferred from the year
    assert first['recruitment_type'] == '实习招聘'
    assert first['source_status_raw'] == 'PUBLISHING'
    assert first['status'] == 'open'
    assert first['description_source'] == 'official tupu360 position/detail page'
    assert 'Project Office Coord.' in first['description_raw']
    assert '立即申请' not in first['description_raw']
    assert sum(1 for url in calls if '/position/detail' in url) == 2
    assert pipeline.validate_result(result, '舍弗勒', 'intern', tmp_path)['jobs']


def test_a_tenants_extra_official_channel_is_merged_into_the_scope(tmp_path, entry_override):
    entry_override('schaeffler')
    routes = {
        '/position/index': page('list-template-b-schaeffler.html'),
        '/position/detail': page('detail-template-b-schaeffler.html'),
    }
    calls = []
    result = run('舍弗勒', 'intern', tmp_path, routes, calls)
    assert result['coverage']['channels_used'] == ['INTERNSHIPRECRUITMENT:html',
                                                   'TECHNOLOGYRUITMENT:html']
    assert sum(1 for url in calls if '/position/index' in url) == 2


def test_collect_paginates_through_the_sites_own_next_page_endpoint(tmp_path, entry_override):
    entry_override('lilly')
    routes = {
        '/position/index': page('list-template-a-lilly.html'),
        '/position/nextPageList': page('nextpage-template-a-lilly.html'),
        '/position/detail': page('detail-template-a-lilly.html'),
    }
    calls = []
    result = run('礼来', 'campus', tmp_path, routes, calls)
    coverage = result['coverage']
    assert coverage['pagination_exhausted'] is True
    assert coverage['detail_complete'] is True
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['collected_jobs'] == 18          # 15 on page 1 + 3 on page 2
    assert coverage['expected_total'] == 18
    assert any('nextPageList' in url and 'offset=15' in url for url in calls)
    assert all(job['published_at'] for job in result['jobs'])
    assert result['jobs'][0]['published_at_source'] == 'official position/detail 发布时间 field'


def test_collect_detail_list_mode_never_fetches_a_detail_page(tmp_path, entry_override):
    entry_override('lilly', detail='list')
    routes = {
        '/position/index': page('list-template-a-lilly.html'),
        '/position/nextPageList': page('nextpage-template-a-lilly.html'),
    }
    calls = []
    result = run('礼来', 'campus', tmp_path, routes, calls)
    assert not any('/position/detail' in url for url in calls)
    assert result['coverage']['detail_source'] == 'list'
    assert result['coverage']['status'] == 'success'
    assert result['coverage']['detail_complete'] is True
    assert all(job['description_raw'] for job in result['jobs'])
    assert result['jobs'][0]['description_source'].startswith(
        'official tupu360 posting-list card')


def test_collect_falls_back_to_the_sites_own_next_page_api(tmp_path, entry_override):
    entry_override('innomotics')
    # A hash-route SPA tenant (强生) answers the list route with a redirect stub;
    # the site's own POST endpoint still returns the whole official list.
    routes = {
        '/position/index': page('careersite-disabled.html'),
        '/position/nextPageList': page('list-template-b-innomotics.html'),
        '/position/detail': page('detail-template-b-schaeffler.html'),
    }
    calls = []
    result = run('茵梦达', 'campus', tmp_path, routes, calls)
    coverage = result['coverage']
    assert coverage['channels_used'] == ['CAMPUSRECRUITMENT:api-direct']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['collected_jobs'] == 3
    assert any('nextPageList' in url and 'max=100' in url for url in calls)


def test_wechat_only_tenant_is_blocked_without_any_request(tmp_path, entry_override):
    entry_override('nestle', enabled=True)
    calls = []
    result = run('雀巢', 'campus', tmp_path, {}, calls)
    assert calls == []
    assert result['jobs'] == []
    coverage = result['coverage']
    assert coverage['status'] == 'blocked'
    assert coverage['complete'] is False
    assert 'open.weixin.qq.com' in ' '.join(coverage['errors'])
    assert coverage['request_budget'] == {'limit': None, 'used': 0}


def test_tenant_without_public_postings_is_blocked(tmp_path, entry_override):
    entry_override('johnsonelectric', enabled=True)
    routes = {'/position/index': page('careersite-disabled.html'),
              '/position/nextPageList': page('careersite-disabled.html')}
    result = run('德昌电机', 'campus', tmp_path, routes)
    assert result['jobs'] == []
    assert result['coverage']['status'] == 'blocked'
    assert any('no public posting found' in error for error in result['coverage']['errors'])


def test_request_budget_stops_detail_fetches_and_marks_partial(tmp_path, entry_override):
    entry_override('schaeffler', extra_channels=None, channels={'intern': 'INTERNSHIPRECRUITMENT'})
    routes = {
        '/position/index': page('list-template-b-schaeffler.html'),
        '/position/detail': page('detail-template-b-schaeffler.html'),
    }
    result = run('舍弗勒', 'intern', tmp_path, routes)
    assert result['coverage']['request_budget'] == {'limit': None, 'used': 3}

    def budgeted(company, scope, target):
        calls = []

        def fake_get(session, url, budget):
            tupu._spend(budget)
            calls.append(url)
            for needle, body in routes.items():
                if needle in url:
                    return FakeResponse(body, url)
            raise AssertionError(url)

        def fake_post(session, url, data, budget, referer=None):
            tupu._spend(budget)
            calls.append(url)
            for needle, body in routes.items():
                if needle in url:
                    return FakeResponse(body, url)
            raise AssertionError(url)

        tupu._get, tupu._post = fake_get, fake_post
        return tupu.collect(company, scope, target, max_requests=2)

    saved = (tupu._get, tupu._post)
    try:
        result = budgeted('舍弗勒', 'intern', tmp_path)
    finally:
        tupu._get, tupu._post = saved
    coverage = result['coverage']
    assert coverage['request_budget'] == {'limit': 2, 'used': 2}
    assert coverage['status'] == 'partial' and coverage['complete'] is False
    assert coverage['detail_complete'] is False


def test_scope_without_a_channel_on_the_site_is_blocked_with_a_note(tmp_path, entry_override):
    entry_override('lilly', scope='campus')
    routes = {'/position/index': page('list-template-a-lilly.html'),
              '/position/nextPageList': page('nextpage-template-a-lilly.html'),
              '/position/detail': page('detail-template-a-lilly.html')}
    calls = []
    result = run('礼来', 'social', tmp_path, routes, calls)
    assert calls == []
    assert result['jobs'] == []
    assert result['coverage']['status'] == 'blocked'
    assert 'campus' in result['coverage']['note']


def test_missing_detail_becomes_a_recorded_error_not_a_fabricated_row(tmp_path, entry_override):
    entry_override('schaeffler', extra_channels=None, channels={'intern': 'INTERNSHIPRECRUITMENT'})
    routes = {
        '/position/index': page('list-template-b-schaeffler.html'),
        '/position/detail': page('careersite-disabled.html'),   # no description at all
    }
    result = run('舍弗勒', 'intern', tmp_path, routes)
    coverage = result['coverage']
    assert result['jobs'] == []
    assert coverage['status'] == 'blocked'
    assert sum(1 for error in coverage['errors'] if 'empty official description' in error) == 2
    assert coverage['detail_complete'] is False


def test_an_unbudgeted_run_costs_one_list_plus_one_pagination_call(tmp_path, entry_override):
    entry_override('lilly', detail='list')
    routes = {'/position/index': page('list-template-a-lilly.html'),
              '/position/nextPageList': page('nextpage-template-a-lilly.html')}
    calls = []
    result = run('礼来', 'campus', tmp_path, routes, calls)
    assert result['coverage']['request_budget'] == {'limit': None, 'used': 2}
    assert result['coverage']['status'] == 'success'
    assert result['coverage']['collected_jobs'] == 18


def test_the_adapter_never_raises_for_an_unknown_company(tmp_path):
    with pytest.raises(ValueError):
        tupu.collect('不存在的公司', 'campus', tmp_path)


def test_fetch_channel_pins_the_method_not_the_recruitment_type(tmp_path, entry_override):
    entry_override('schaeffler')
    """fetch_channel selects how to fetch; recruitmentType always comes from config."""
    routes = {
        '/position/index': page('list-template-b-schaeffler.html'),
        '/position/nextPageList': page('list-template-b-schaeffler.html'),
        '/position/detail': page('detail-template-b-schaeffler.html'),
    }
    calls = []

    def fake_get(session, url, budget):
        tupu._spend(budget)
        calls.append(url)
        for needle, body in routes.items():
            if needle in url:
                return FakeResponse(body, url)
        raise AssertionError(url)

    def fake_post(session, url, data, budget, referer=None):
        tupu._spend(budget)
        calls.append(url + '?' + data['recruitmentType'])
        return FakeResponse(routes['/position/nextPageList'], url)

    saved = (tupu._get, tupu._post)
    tupu._get, tupu._post = fake_get, fake_post
    try:
        api = tupu.collect('舍弗勒', 'intern', tmp_path / 'api', max_requests=1,
                           fetch_channel='api')
    finally:
        tupu._get, tupu._post = saved
    # Only the site's own nextPageList is touched and the official channel value
    # stays INTERNSHIPRECRUITMENT -- never the string "api".
    assert all('position/index' not in url for url in calls)
    assert any('INTERNSHIPRECRUITMENT' in url for url in calls)
    assert not any('recruitmentType=api' in url for url in calls)
    assert api['coverage']['channels_used'] == ['INTERNSHIPRECRUITMENT:api-direct']

    calls.clear()
    saved = (tupu._get, tupu._post)
    tupu._get, tupu._post = fake_get, fake_post
    try:
        html = tupu.collect('舍弗勒', 'intern', tmp_path / 'html', max_requests=1,
                            fetch_channel='html')
    finally:
        tupu._get, tupu._post = saved
    assert calls == ['https://careersite.tupu360.com/schaeffler/position/index'
                     '?recruitmentType=INTERNSHIPRECRUITMENT']
    assert html['coverage']['channels_used'] == ['INTERNSHIPRECRUITMENT:html']


def test_headless_channel_reports_unavailable_instead_of_crashing(tmp_path, monkeypatch, entry_override):
    entry_override('schaeffler')
    monkeypatch.setattr(tupu, '_fetch_headless', lambda *a, **k: (_ for _ in ()).throw(
        tupu.ChannelUnavailable('playwright not importable')))
    routes = {'/position/index': page('careersite-disabled.html')}

    def fake_get(session, url, budget):
        tupu._spend(budget)
        return FakeResponse(routes['/position/index'], url)

    saved = tupu._get
    tupu._get = fake_get
    try:
        result = tupu.collect('舍弗勒', 'intern', tmp_path, fetch_channel='headless')
    finally:
        tupu._get = saved
    assert result['jobs'] == []
    assert result['coverage']['status'] == 'blocked'
    assert any('headless channel unavailable' in error for error in result['coverage']['errors'])


def test_collecting_a_disabled_line_requires_an_explicit_audit_flag(tmp_path):
    with pytest.raises(ValueError):
        tupu.collect('雀巢', 'campus', tmp_path)
    result = tupu.collect('雀巢', 'campus', tmp_path, include_disabled=True)
    assert result['coverage']['status'] == 'blocked'
    assert result['coverage']['request_budget'] == {'limit': None, 'used': 0}

# --------------------------------------------------------------------------- #
# pagination depth: the site's own page count, not a fixed 40-page target
# --------------------------------------------------------------------------- #
PHARMARON_LIST = 'pharmaron-bj-SOCIALRECRUITMENT-list-1.html'
PHARMARON_PAGE2 = 'pharmaron-bj-social-page-2.html'
PHARMARON_PAGE56 = 'pharmaron-bj-social-page-56.html'


def _pharmaron_pager(calls, page_two=None, page_last=None):
    """A fake nextPageList that answers each offset with a distinct real page.

    Page fragments are real recordings; only the posting ids are re-stamped so
    every page carries its own ids (the real site does exactly that).
    """
    import re

    def fake_post(session, url, data, budget, referer=None):
        tupu._spend(budget)
        offset = int(data['offset'])
        page = offset // int(data['max']) + 1
        calls.append(offset)
        if page == 56:
            return FakeResponse(page_last, url)
        body = page_two
        # keep the id shape, make it page-unique
        body = re.sub(r'pid="([0-9a-zA-Z]+)"',
                      lambda m: 'pid="p%03d%s"' % (page, m.group(1)[1:]), body)
        return FakeResponse(body, url)

    return fake_post


def _pharmaron_get(list_body):
    def fake_get(session, url, budget):
        tupu._spend(budget)
        return FakeResponse(list_body, url)

    return fake_get


def test_a_56_page_channel_is_not_truncated_at_the_old_40_page_target(tmp_path,
                                                                    entry_override,
                                                                    monkeypatch):
    # 康龙化成's public social channel is 828 postings / 56 pages.  The list page
    # states both numbers; the adapter must follow the site, not a 40-page target
    # (40 x 15 = 600, which is exactly what the 20260919g run truncated to).
    entry_override('pharmaron-bj', detail='list')
    calls = []
    saved = (tupu._get, tupu._post)
    tupu._get = _pharmaron_get(page(PHARMARON_LIST))
    tupu._post = _pharmaron_pager(calls, page(PHARMARON_PAGE2), page(PHARMARON_PAGE56))
    try:
        result = tupu.collect('康龙化成（北京）新药技术股份有限公司', 'social',
                              tmp_path, include_disabled=True)
    finally:
        tupu._get, tupu._post = saved
    coverage = result['coverage']
    assert len(calls) == 55                     # pages 2..56, not pages 2..40
    assert calls[-1] == 825                     # the real last page (3 postings)
    assert coverage['collected_jobs'] == 828
    assert coverage['expected_total'] == 828
    assert coverage['pagination_exhausted'] is True
    assert coverage['complete'] is True and coverage['status'] == 'success'
    assert not coverage.get('page_cap_hit')


def test_a_page_cap_hit_is_reported_as_truncated_and_never_as_exhausted(tmp_path,
                                                                       entry_override,
                                                                       monkeypatch):
    # If the safety valve really is reached, the unit must degrade to `partial`
    # with an explicit note instead of claiming it paginated to the end.
    entry_override('pharmaron-bj', detail='list')
    monkeypatch.setattr(tupu, 'PAGE_CAP', 3)
    calls = []
    saved = (tupu._get, tupu._post)
    tupu._get = _pharmaron_get(page(PHARMARON_LIST))
    tupu._post = _pharmaron_pager(calls, page(PHARMARON_PAGE2), page(PHARMARON_PAGE56))
    try:
        result = tupu.collect('康龙化成（北京）新药技术股份有限公司', 'social',
                              tmp_path, include_disabled=True)
    finally:
        tupu._get, tupu._post = saved
    coverage = result['coverage']
    assert len(calls) == 2                      # pages 2 and 3 only
    assert coverage['collected_jobs'] == 45     # 15 + 15 + 15
    assert coverage['page_cap_hit'] is True
    assert coverage['pagination_exhausted'] is False
    assert coverage['complete'] is False
    assert coverage['status'] == 'partial'
    assert any('safety cap' in error for error in coverage['errors'])


def test_direct_api_reports_a_cap_hit_instead_of_claiming_the_end(tmp_path):
    # The api channel has the same honesty requirement: it only stops short when
    # the site really has no further page.
    calls = []
    saved = tupu._post
    tupu._post = _pharmaron_pager(calls, page(PHARMARON_PAGE2), page(PHARMARON_PAGE56))
    try:
        parsed = tupu._fetch_direct_api(None, 'pharmaron-bj', 'SOCIALRECRUITMENT', None,
                                        [], 15, page_cap=3)
    finally:
        tupu._post = saved
    assert len(calls) == 3
    assert len(parsed['rows']) == 45
    assert parsed['total_label'] == 828
    assert parsed['page_cap_hit'] is True
