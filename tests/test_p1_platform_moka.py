"""Fixture tests for the generic Moka (mokahr.com) platform adapter.

Only recorded-response fixtures are used; the AES wrapper is bypassed by patching
the shared request/decrypt seam, so no live Moka tenant is contacted.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from qiuzhao.collector import p1_platform_moka as moka


@pytest.fixture(autouse=True)
def isolate_detail_cache_env(monkeypatch):
    # A pipeline test may set the persistent cache root for the process.
    # List reuse must not leak across these fixture runs.
    monkeypatch.delenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', raising=False)
    monkeypatch.delenv('QIUZHAO_P1_LOGICAL_RUN_ID', raising=False)

FIXTURES = Path(__file__).parent / 'fixtures' / 'platform'


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def entry_html(name='moka_entry.html'):
    return (FIXTURES / name).read_text(encoding='utf-8')


class FakeEntry:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, text):
        self.text = text
        self.headers = {}

    def get(self, url, **kwargs):
        return FakeEntry(self.text)


def make_request_json():
    offset0 = fixture('moka_list_offset0.json')
    offset50 = fixture('moka_list_offset50.json')

    def request_json(session, url, payload, iv):
        return offset0 if int(payload.get('offset', 0)) == 0 else offset50

    return request_json


def make_detail_lookup():
    base = fixture('moka_detail.json')
    intern = fixture('moka_detail_intern.json')

    def moka_detail_cached(company, scope, row, host, org, site, iv, output_dir):
        detail = dict(intern if 'intern' in row['id'] else base)
        detail.update(id=row['id'], title=row.get('title'), hireMode=row.get('hireMode'),
                      commitment=row.get('commitment'), status=row.get('status'),
                      openedAt=row.get('openedAt'), updatedAt=row.get('updatedAt'),
                      closedAt=row.get('closedAt'),
                      jobDescription='<p>岗位职责：官方职责。</p><p>任职要求：官方要求。</p>')
        return detail, '2026-09-18T00:00:00+00:00', False

    return moka_detail_cached


def run(company, scope, tmp_path, text=None, max_requests=20):
    session = FakeSession(text if text is not None else entry_html())
    with patch.object(moka, '_make_session', return_value=session), \
         patch.object(moka.shared, 'request_json', side_effect=make_request_json()), \
         patch.object(moka.shared, 'moka_detail_cached', side_effect=make_detail_lookup()):
        return moka.collect(company, scope, tmp_path, max_requests=max_requests)


def test_pagination_classification_and_empty_fields(tmp_path):
    result = run('信也科技', 'campus', tmp_path)
    coverage = result['coverage']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['pagination_exhausted'] is True
    by_id = {job['source_record_id']: job for job in result['jobs']}
    # The internship row belongs to the intern scope, never to campus.
    assert set(by_id) == {'moka-campus-1', 'moka-paused-1'}
    assert coverage['list_observed_ids'] == ['moka-campus-1', 'moka-paused-1']
    first = by_id['moka-campus-1']
    assert first['published_at'] == '2026-09-01T00:00'   # official openedAt
    assert first['deadline_raw'] == ''                    # closedAt absent -> stay blank
    assert first['cohort_raw'] == ''                      # no cohort inferred
    assert first['status'] == 'open' and first['source_is_active'] is True
    paused = by_id['moka-paused-1']
    assert paused['status'] == 'expired' and paused['source_is_active'] is False
    assert coverage['active_jobs'] == 1 and coverage['inactive_jobs'] == 1


def test_intern_scope_selects_internship_rows(tmp_path):
    result = run('信也科技', 'intern', tmp_path)
    by_id = {job['source_record_id']: job for job in result['jobs']}
    assert set(by_id) == {'moka-intern-1'}
    assert by_id['moka-intern-1']['recruitment_type'] == '实习招聘'


def test_waf_challenge_without_aes_iv_blocks(tmp_path):
    result = run('信也科技', 'campus', tmp_path,
                 text=entry_html('moka_entry_no_iv.html'))
    assert result['jobs'] == []
    assert result['coverage']['status'] == 'blocked'
    assert any('aesIv' in error for error in result['coverage']['errors'])


def test_request_budget_stops_after_first_list_page(tmp_path):
    result = run('信也科技', 'campus', tmp_path, max_requests=2)
    coverage = result['coverage']
    assert coverage['request_budget_exhausted'] is True
    assert coverage['complete'] is False
    assert coverage['list_observed_ids'] == ['moka-campus-1', 'moka-paused-1']


def test_real_config_moka_entries_are_resolvable():
    assert moka.COMPANIES['antahr/142914'] == '安踏集团'
    assert moka.sites_for('antahr/142914') == [
        ('https://app.mokahr.com/campus-recruitment/antahr/142914',
         'derived from configured key antahr/142914')]
    assert moka.sites_for('wps/41436') == [
        ('https://join.wps.cn/campus-recruitment/wps/41436', 'configured Moka portal for wps/41436'),
        ('https://app.mokahr.com/social-recruitment/wps/3471', 'configured Moka portal for wps/41436')]


def test_real_config_nestle_multi_entrance(monkeypatch):
    """雀巢 2026-09-19: one config row merges three official Moka tenants."""
    assert 'nestlezgc/91899' in moka.COMPANIES
    assert moka.COMPANIES['nestlezgc/91899'] == '雀巢'
    assert moka.sites_for('nestlezgc/91899') == [
        ('https://app.mokahr.com/campus-recruitment/nestlezgc/91899',
         'configured Moka portal for nestlezgc/91899'),
        ('https://app.mokahr.com/social-recruitment/nestlezgc/91898',
         'configured Moka portal for nestlezgc/91899'),
        ('https://app.mokahr.com/social-recruitment/nestlezgc/124026',
         'configured Moka portal for nestlezgc/91899'),
    ]


def test_multi_site_merge_dedups_shared_ids(tmp_path, monkeypatch):
    """Two configured sites are scanned; a posting id seen on both is emitted once."""
    sites = ['https://app.mokahr.com/campus-recruitment/merge/1',
             'https://app.mokahr.com/social-recruitment/merge/2']
    monkeypatch.setattr(moka, '_entry',
                        lambda key: {'name': '多入口测试', 'sites': sites})
    monkeypatch.setattr(moka, 'COMPANIES', {'merge/1': '多入口测试'})
    monkeypatch.setattr(moka, 'NAME_TO_SLUG', {'多入口测试': 'merge/1'})

    class Entry:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    class Session:
        def __init__(self):
            self.headers = {}
            self.visited = []

        def get(self, url, **kwargs):
            self.visited.append(url)
            iv = 'A' * 16 if '/merge/1' in url else 'B' * 16
            return Entry('{"aesIv":"%s"}' % iv)

    rows = {
        1: [{'id': 'c1', 'title': '校招A', 'hireMode': 2, 'status': 'open'},
            {'id': 's1', 'title': '社招A', 'hireMode': 1, 'status': 'open'}],
        2: [{'id': 'c1', 'title': '校招A', 'hireMode': 2, 'status': 'open'},
            {'id': 'c2', 'title': '校招B', 'hireMode': 2, 'status': 'open'}],
    }

    def request_json(session, url, payload, iv=None):
        site = int(payload['siteId'])
        if int(payload.get('offset', 0)):
            return {'jobs': [], 'jobStats': {'total': len(rows[site])}}
        return {'jobs': rows[site], 'jobStats': {'total': len(rows[site])}}

    def detail(company, scope, row, host, org, site, iv, output_dir):
        return ({'id': row['id'], 'title': row['title'], 'hireMode': row['hireMode'],
                 'commitment': row.get('commitment'), 'status': row.get('status'),
                 'jobDescription': '<p>职责</p><p>要求</p>', 'locations': []},
                '2026-09-19T00:00:00+00:00', False)

    session = Session()
    monkeypatch.setattr(moka, '_make_session', lambda: session)
    monkeypatch.setattr(moka.shared, 'request_json', request_json)
    monkeypatch.setattr(moka.shared, 'moka_detail_cached', detail)

    campus = moka.collect('多入口测试', 'campus', tmp_path / 'c', max_requests=20)
    social = moka.collect('多入口测试', 'social', tmp_path / 's', max_requests=20)

    assert sorted(j['source_record_id'] for j in campus['jobs']) == ['c1', 'c2']
    assert [j['source_record_id'] for j in social['jobs']] == ['s1']
    # both sites were actually listed and their totals recorded
    assert campus['coverage']['source_list_totals'] == {'merge/1': 2, 'merge/2': 2}
    assert any('/merge/1' in url for url in session.visited)
    assert any('/merge/2' in url for url in session.visited)


def test_real_config_ey_merges_campus_and_social_tenants():
    """安永 2026-09-19: official EY China page adds social tenant ey/102474."""
    assert moka.sites_for('ey/166374') == [
        ('https://app.mokahr.com/campus-recruitment/ey/166374',
         'configured Moka portal for ey/166374'),
        ('https://app.mokahr.com/social-recruitment/ey/102474',
         'configured Moka portal for ey/166374'),
    ]


def test_second_bounded_pass_raw_detail_cannot_skip_fingerprint(tmp_path):
    """A raw detail file is not a verified cache hit and must not skip the lookup."""
    calls = []

    def counting_lookup(company, scope, row, host, org, site, iv, output_dir):
        calls.append(row['id'])
        detail = dict(fixture('moka_detail.json'))
        detail.update(id=row['id'], title=row.get('title'), hireMode=row.get('hireMode'),
                      commitment=row.get('commitment'), status=row.get('status'),
                      openedAt=row.get('openedAt'), updatedAt=row.get('updatedAt'),
                      closedAt=row.get('closedAt'),
                      jobDescription='<p>岗位职责：官方职责。</p><p>任职要求：官方要求。</p>')
        return detail, 'checked', False

    def run_pass(limit):
        session = FakeSession(entry_html())
        with patch.object(moka, '_make_session', return_value=session), \
             patch.object(moka.shared, 'request_json', side_effect=make_request_json()), \
             patch.object(moka.shared, 'moka_detail_cached', side_effect=counting_lookup):
            return moka.collect('信也科技', 'campus', tmp_path, max_requests=limit)

    first = run_pass(4)
    assert first['coverage']['request_budget_exhausted'] is True
    assert len(first['jobs']) == 1
    assert calls == ['moka-campus-1']
    assert (tmp_path / 'detail-moka-campus-1.json').is_file()
    second = run_pass(20)
    assert second['coverage']['complete'] is True
    assert len(second['jobs']) == 2
    # The saved raw detail is not an envelope, so the first id is looked up again.
    assert calls == ['moka-campus-1', 'moka-campus-1', 'moka-paused-1']
    assert second['coverage']['request_budget']['used'] == 5   # 3 list + 2 details
