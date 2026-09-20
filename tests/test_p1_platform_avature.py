"""Fixture tests for the generic Avature platform adapter.

The list/detail HTML is recorded from the official public portals (HSBC portal 88
and Siemens portal 144, recorded 2026-09-19) and the HTTP session is a fake, so the
suite never contacts a live career site.
"""
import json
import re
from pathlib import Path
from unittest.mock import patch

from qiuzhao.collector import p1_platform_avature as av

FIXTURES = Path(__file__).parent / 'fixtures' / 'platform'

HSBC_KEY = 'mycareer.hsbc.com/en_GB/external'
SIEMENS_KEY = 'jobs.siemens.com/en_US/externaljobs'


def html(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


CONFIG = {'avature': {
    '_note': 'documentation key that must never become a company',
    SIEMENS_KEY: {'name': '西门子', 'search': 'China'},
    HSBC_KEY: {'name': '汇丰', 'search': '', 'offset_param': 'pipelineOffset',
               'page_size_param': 'pipelineRecordsPerPage'},
}}


def patch_config(tmp_path):
    path = tmp_path / 'p1_platform_companies.json'
    path.write_text(json.dumps(CONFIG, ensure_ascii=False), encoding='utf-8')
    return path


class FakeResponse:
    def __init__(self, text='', status=200):
        self.text = text
        self.status_code = status
        self.encoding = 'utf-8'

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError('http ' + str(self.status_code))


class FakeSession:
    """Serves the recorded HSBC page for every search request unless overridden."""

    def __init__(self, lists=None, details=None, fallback=''):
        self.lists = lists if lists is not None else {'': html('avature_list_hsbc.html')}
        self.details = details or {}
        self.fallback = fallback
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if 'SearchJobs' in url:
            return FakeResponse(self.lists.get(url, self.lists.get('', '')))
        for ident, payload in self.details.items():
            if f'/{ident}' in url:
                return FakeResponse(payload)
        return FakeResponse(self.fallback)


def run(tmp_path, fake, company, scope):
    with patch.object(av, 'CONFIG_PATH', patch_config(tmp_path)):
        av.reload_config()
        with patch.object(av, '_make_session', return_value=fake):
            return av.collect(company, scope, tmp_path / ('out-' + scope))


# ------------------------------------------------------------------ config
def test_shipped_config_registers_the_verified_portals_only():
    av.reload_config()
    assert len(av.COMPANIES) == 4, av.COMPANIES
    assert '汇丰' not in av.COMPANIES.values(), 'portal 88 has 0 China rows today'
    assert '_note' not in av.COMPANIES
    assert av.merged_registry()['西门子'] == av.MODULE_PATH
    assert av.resolve('贝恩') == 'careers.bain.com/en_US/jobs'
    for key in av.COMPANIES:
        host, locale, portal = av.parts_for(key)
        assert '.' in host and re.fullmatch(r'[a-z]{2}_[A-Z]{2}', locale) and portal


def test_parts_for_rejects_a_short_key():
    for bad in ('mycareer.hsbc.com', 'mycareer.hsbc.com/en_GB'):
        try:
            av.parts_for(bad)
        except ValueError:
            continue
        raise AssertionError('accepted invalid key ' + bad)


# ------------------------------------------------------------------ urls
def test_search_url_uses_the_portal_paging_parameter_names(tmp_path):
    with patch.object(av, 'CONFIG_PATH', patch_config(tmp_path)):
        av.reload_config()
        assert av.search_url(HSBC_KEY, '', 10, 10) == (
            'https://mycareer.hsbc.com/en_GB/external/SearchJobs/'
            '?pipelineOffset=10&pipelineRecordsPerPage=10')
        siemens = av.search_url(SIEMENS_KEY, 'China', 0, 20)
        assert siemens.startswith('https://jobs.siemens.com/en_US/externaljobs/SearchJobs/?search=China&')
        assert 'jobOffset=0' in siemens and 'jobRecordsPerPage=20' in siemens


# ------------------------------------------------------------------ parsing
def test_parse_list_reads_official_cards_and_skips_navigation_links():
    cards = av.parse_list(html('avature_list_hsbc.html'))
    assert cards, 'the recorded HSBC page carries pipeline cards'
    assert all(card['ident'].isdigit() for card in cards)
    assert all('/PipelineDetail/' in card['href'] for card in cards)
    assert 'talentcommunity' not in {card['ident'] for card in cards}


def test_pagination_follows_the_portals_own_offset_parameter():
    current, links = av.parse_pagination(html('avature_list_hsbc.html'))
    assert current == 1
    nxt = av.next_page_url(html('avature_list_hsbc.html'), 'fallback')
    assert 'pipelineOffset=10' in nxt and 'pipelineRecordsPerPage=10' in nxt


def test_parse_detail_maps_official_labels_and_description():
    parsed = av.parse_detail(html('avature_detail_campus.html'))
    assert parsed['title'].startswith('Siemens Graduate Program')
    assert parsed['fields']['job id'] == '521566'
    assert parsed['fields']['experience level'] == 'Recent College Graduate'
    assert parsed['posted'] == '2026-09-07'          # official "Posted since"
    assert parsed['deadline'] == ''                  # no closing date -> blank
    assert len(parsed['description']) > 200
    assert 'Siemens Graduate Program' in parsed['description']


def test_value_only_theme_yields_official_location_tokens():
    # L'Oreal publishes the same detail blocks without labels and wraps each value
    # in a <span>; the location tokens must still be readable (and the official
    # posting date must survive as published_at).
    parsed = av.parse_detail(html('avature_detail_loreal.html'))
    assert parsed['locations'] == ['Shanghai Shi', 'Shanghai']
    assert av._china_locations(parsed, {'location': ''}) == ['Shanghai Shi', 'Shanghai']
    assert parsed['posted'] == '2026-05-19'
    assert len(parsed['description']) > 100


def test_china_location_gate_keeps_china_and_drops_other_countries():
    china = av.parse_detail(html('avature_detail_campus.html'))
    assert av._china_locations(china, {'location': 'Shenzhen - Guangdong Sheng - China'})
    other = av.parse_detail(html('avature_detail_nonchina.html'))
    assert other['fields']['location'] == 'Poland'
    assert av._china_locations(other, {'location': 'Poland'}) == []


def test_scope_mapping_prefers_intern_then_campus_labels():
    key = SIEMENS_KEY
    assert av._scope_of('Summer Intern - Engineering', {}, key) == 'intern'
    assert av._scope_of('Siemens Graduate Program - Digital Sales', {}, key) == 'campus'
    assert av._scope_of('Sr. Commodity Manager', {}, key) == 'social'
    # the official Experience level label alone is enough
    assert av._scope_of('Engineer', {'experience level': 'Recent College Graduate'},
                        key) == 'campus'
    assert av._scope_of('Engineer', {'experience level': 'Intern'}, key) == 'intern'


# ------------------------------------------------------------------ collect
def test_collect_keeps_the_china_job_and_reports_official_fields(tmp_path):
    # the recorded HSBC page plus one official Siemens China card on top
    listing = (
        '<article class="article article--result">'
        '<h3 class="t"><a href="https://jobs.siemens.com/en_US/externaljobs/JobDetail/521566">'
        'Siemens Graduate Program - Digital Sales</a></h3>'
        '<div class="list-controls__text__legend">1 - 1 of 1 results</div></article>'
        + html('avature_list_hsbc.html'))
    fake = FakeSession({'': listing}, {'521566': html('avature_detail_campus.html')},
                       fallback=html('avature_detail_nonchina.html'))
    with patch.object(av, 'CONFIG_PATH', patch_config(tmp_path)):
        av.reload_config()
        with patch.object(av, '_make_session', return_value=fake):
            result = av.collect('西门子', 'campus', tmp_path / 'siemens')
    assert len(result['jobs']) == 1
    job = result['jobs'][0]
    assert job['source_record_id'] == '521566'
    assert job['recruitment_type'] == '校园招聘'
    assert job['published_at'] == '2026-09-07'
    assert job['cohort_raw'] == '' and job['deadline_raw'] == ''
    assert job['cities'] == ['Shenzhen', 'Guangdong Sheng']


def test_collect_filters_a_non_china_requisition(tmp_path):
    fake = FakeSession(details={'288693': html('avature_detail_nonchina.html')},
                       fallback=html('avature_detail_nonchina.html'))
    with patch.object(av, 'CONFIG_PATH', patch_config(tmp_path)):
        av.reload_config()
        with patch.object(av, '_make_session', return_value=fake):
            result = av.collect('汇丰', 'social', tmp_path / 'hsbc')
    coverage = result['coverage']
    assert result['jobs'] == []
    assert coverage['status'] == 'blocked'
    assert coverage['location_filtered_count'] >= 1


def test_detail_pages_are_cached_across_scopes(tmp_path):
    fake = FakeSession(details={'288693': html('avature_detail_nonchina.html')},
                       fallback=html('avature_detail_nonchina.html'))
    with patch.object(av, 'CONFIG_PATH', patch_config(tmp_path)):
        av.reload_config()
        with patch.object(av, '_make_session', return_value=fake):
            av.collect('汇丰', 'social', tmp_path / 'scope-a')
            first = len([u for u in fake.calls if '/PipelineDetail/' in u])
            av.collect('汇丰', 'campus', tmp_path / 'scope-b')
            second = len([u for u in fake.calls if '/PipelineDetail/' in u]) - first
    assert first >= 1
    assert second == 0, 'the per-company page cache must serve the other scopes'


# ------------------------------------------------- pagination honesty (audit)
def test_a_truncated_avature_page_never_claims_the_list_was_read(tmp_path):
    """A degraded/empty page is not the end of the list when the legend says otherwise.

    Regression: ``if not page_cards or not new_cards`` set ``list_complete`` on its own, so
    an empty answer (or a repeating pager) after page 1 was reported as an exhausted
    listing even though the portal still counted 36 results.
    """
    page_one = html('avature_list_hsbc.html')            # legend "1-10 of 36 results"
    page_two = '<html><body><div class="no-results">no results</div></body></html>'
    following = av.next_page_url(page_one, 'fallback')
    fake = FakeSession({'': page_one, following: page_two},
                       {'288693': html('avature_detail_campus.html')},
                       fallback=html('avature_detail_nonchina.html'))
    with patch.object(av, 'CONFIG_PATH', patch_config(tmp_path)):
        av.reload_config()
        with patch.object(av, '_make_session', return_value=fake):
            result = av.collect('西门子', 'campus', tmp_path / 'capped')
    coverage = result['coverage']
    assert coverage['search_total'] == 36                # the portal's own count survives
    assert coverage['pagination_exhausted'] is False
    assert coverage['page_cap_hit'] is True
    assert coverage['list_truncated'] is True
    assert coverage['complete'] is False
    assert 'truncated' in coverage['last_page_evidence']
    # Everything read before the truncation is kept.
    assert len(result['jobs']) == 1


def test_a_repeating_pager_that_contradicts_the_legend_is_truncation(tmp_path):
    """The same rule covers a pager that repeats page 1 while the legend still counts more."""
    page_one = html('avature_list_hsbc.html')
    fake = FakeSession({'': page_one}, {'288693': html('avature_detail_campus.html')},
                       fallback=html('avature_detail_nonchina.html'))
    with patch.object(av, 'CONFIG_PATH', patch_config(tmp_path)):
        av.reload_config()
        with patch.object(av, '_make_session', return_value=fake):
            result = av.collect('西门子', 'campus', tmp_path / 'repeat')
    coverage = result['coverage']
    assert coverage['pagination_exhausted'] is False
    assert coverage['list_truncated'] is True
    assert 'new=0;seen=10;legend_total=36' in coverage['last_page_evidence']


def test_a_list_whose_legend_is_reached_is_still_complete(tmp_path):
    """Control: an empty page after the legend is satisfied stays a proven end."""
    listing = (
        '<article class="article article--result">'
        '<h3 class="t"><a href="https://jobs.siemens.com/en_US/externaljobs/JobDetail/521566">'
        'Siemens Graduate Program - Digital Sales</a></h3>'
        '<div class="list-controls__text__legend">1 - 1 of 1 results</div></article>')
    fake = FakeSession({'': listing}, {'521566': html('avature_detail_campus.html')},
                       fallback=html('avature_detail_nonchina.html'))
    with patch.object(av, 'CONFIG_PATH', patch_config(tmp_path)):
        av.reload_config()
        with patch.object(av, '_make_session', return_value=fake):
            result = av.collect('西门子', 'campus', tmp_path / 'complete')
    coverage = result['coverage']
    assert coverage['pagination_exhausted'] is True
    assert 'list_truncated' not in coverage
    assert coverage['complete'] is True
