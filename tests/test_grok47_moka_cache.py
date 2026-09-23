"""Focused Moka cache checks: fingerprint, resume bypass, same-day list sharing."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from qiuzhao.collector import p1_platform_moka as moka
from qiuzhao.collector import p1_sources_01_10 as src

FIXTURES = Path(__file__).parent / 'fixtures' / 'platform'


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def entry_html():
    return (FIXTURES / 'moka_entry.html').read_text(encoding='utf-8')


class FakeSession:
    def __init__(self, text):
        self.text = text
        self.headers = {}

    def get(self, url, **kwargs):
        return self

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value

    def raise_for_status(self):
        return None


def make_request_json():
    offset0 = fixture('moka_list_offset0.json')
    offset50 = fixture('moka_list_offset50.json')

    def request_json(session, url, payload, iv=None):
        return offset0 if int(payload.get('offset', 0)) == 0 else offset50

    return request_json


def _detail_for(row):
    detail = dict(fixture('moka_detail.json'))
    detail.update(id=row['id'], title=row.get('title'), hireMode=row.get('hireMode'),
                  commitment=row.get('commitment'), status=row.get('status'),
                  openedAt=row.get('openedAt'), updatedAt=row.get('updatedAt'),
                  closedAt=row.get('closedAt'),
                  jobDescription='<p>岗位职责：官方职责。</p><p>任职要求：官方要求。</p>')
    return detail


def test_unchanged_fingerprint_reuses_and_keeps_detail_time(tmp_path, monkeypatch):
    monkeypatch.setenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(tmp_path / 'cache'))
    row = {'id': 'a', 'updatedAt': '2026-09-12T00:00:00', 'title': 'A'}
    calls = []

    def request_json(session, url, payload, iv=None):
        calls.append(payload.get('jobId'))
        return _detail_for(row)

    out = tmp_path / 'campus'
    out.mkdir()
    with patch.object(src, 'request_json', side_effect=request_json):
        first = src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', '1', None, out)
        envelope = json.loads(src.moka_detail_cache_path('dji', 'campus', 'https://example.com', 'dji', '1', 'a', out).read_text(encoding='utf-8'))
        second = src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', '1', None, out)
        after = json.loads(src.moka_detail_cache_path('dji', 'campus', 'https://example.com', 'dji', '1', 'a', out).read_text(encoding='utf-8'))
    assert first[2] is False and second[2] is True
    assert calls == ['a']
    assert second[1] == first[1] == envelope['detail_checked_at'] == after['detail_checked_at']


def test_changed_fingerprint_refetches(tmp_path, monkeypatch):
    monkeypatch.setenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(tmp_path / 'cache'))
    row = {'id': 'a', 'updatedAt': '2026-09-12', 'title': 'A'}
    calls = []

    def request_json(session, url, payload, iv=None):
        calls.append(row['title'])
        return _detail_for(row)

    out = tmp_path / 'campus'
    out.mkdir()
    with patch.object(src, 'request_json', side_effect=request_json):
        first = src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', 1, None, out)
        row['title'] = 'Changed'
        second = src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', 1, None, out)
    assert first[2] is False and second[2] is False
    assert calls == ['A', 'Changed']
    assert second[1] != first[1]


def test_resume_raw_detail_and_fingerprintless_envelope_cannot_bypass(tmp_path, monkeypatch):
    monkeypatch.setenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(tmp_path / 'cache'))
    row = {'id': 'a', 'updatedAt': '2026-09-12', 'title': 'A', 'education': '博士'}
    out = tmp_path / 'campus'
    out.mkdir()
    (out / 'detail-a.json').write_text(json.dumps({**row, 'jobDescription': '正文'}), encoding='utf-8')
    calls = []

    def request_json(session, url, payload, iv=None):
        calls.append(payload['jobId'])
        return {**row, 'jobDescription': '正文'}

    with patch.object(src, 'request_json', side_effect=request_json):
        fetched = src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', 1, None, out)
    assert fetched[2] is False and calls == ['a']

    path = src.moka_detail_cache_path('dji', 'campus', 'https://example.com', 'dji', 1, 'a', out)
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload.pop('list_fingerprint')
    path.write_text(json.dumps(payload), encoding='utf-8')
    with patch.object(src, 'request_json', side_effect=request_json):
        again = src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', 1, None, out)
    assert again[2] is False and calls == ['a', 'a']


def test_site_identity_mismatch_refetches(tmp_path, monkeypatch):
    monkeypatch.setenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(tmp_path / 'cache'))
    row = {'id': 'a', 'updatedAt': '2026-09-12', 'title': 'A'}
    calls = []

    def request_json(session, url, payload, iv=None):
        calls.append(payload['siteId'])
        return {**row, 'jobDescription': '正文'}

    out = tmp_path / 'campus'
    out.mkdir()
    with patch.object(src, 'request_json', side_effect=request_json):
        src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', 1, None, out)
        second = src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', 2, None, out)
    assert second[2] is False and calls == [1, 2]


def test_env_override_is_the_cache_directory(tmp_path, monkeypatch):
    custom = tmp_path / 'custom-root'
    monkeypatch.setenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(custom))
    row = {'id': 'a', 'updatedAt': '2026-09-12', 'title': 'A'}
    out = tmp_path / 'campus'
    out.mkdir()
    with patch.object(src, 'request_json', return_value={**row, 'jobDescription': '正文'}):
        src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', 1, None, out)
    stored = src.moka_detail_cache_path('dji', 'campus', 'https://example.com', 'dji', 1, 'a', out)
    assert stored.is_file()
    assert custom in stored.parents
    assert src.os.environ.setdefault('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(tmp_path / 'other')) == str(custom)


def test_same_run_scopes_share_list_and_keep_real_list_time(tmp_path, monkeypatch):
    monkeypatch.setenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(tmp_path / 'cache'))
    monkeypatch.setenv(src.MOKA_LOGICAL_RUN_ENV, 'run-same')
    monkeypatch.setattr(moka.time, 'sleep', lambda *_a, **_k: None)
    list_calls = []
    detail_calls = []

    def request_json(session, url, payload, iv=None):
        if payload.get('jobId'):
            detail_calls.append(payload['jobId'])
            return _detail_for({'id': payload['jobId'], 'title': payload['jobId'],
                                'hireMode': 2, 'updatedAt': '2026-09-04T18:51:20'})
        list_calls.append(int(payload.get('offset', 0)))
        return make_request_json()(session, url, payload, iv)

    def collect(scope, folder):
        with patch.object(moka, '_make_session', return_value=FakeSession(entry_html())), \
             patch.object(moka.shared, 'request_json', side_effect=request_json):
            return moka.collect('信也科技', scope, folder, max_requests=20)

    campus = collect('campus', tmp_path / 'campus')
    checked = {job['source_record_id']: job['detail_checked_at'] for job in campus['jobs']}
    intern = collect('intern', tmp_path / 'intern')
    assert list_calls == [0, 50]
    assert intern['coverage']['list_cache_reused'] is True
    assert [job['source_record_id'] for job in intern['jobs']] == ['moka-intern-1']
    assert detail_calls.count('moka-campus-1') == 1
    again = collect('campus', tmp_path / 'campus-2')
    assert list_calls == [0, 50]
    assert detail_calls.count('moka-campus-1') == 1
    reused = {job['source_record_id']: job for job in again['jobs']}
    assert reused['moka-campus-1']['detail_cache_reused'] is True
    assert reused['moka-campus-1']['detail_checked_at'] == checked['moka-campus-1']
    assert reused['moka-campus-1']['verified_at'] == checked['moka-campus-1']
    host = 'https://app.mokahr.com'
    snapshot = json.loads(src.moka_list_cache_path(
        tmp_path / 'campus', host, 'paipaidai', '168312', 'run-same').read_text(encoding='utf-8'))
    assert intern['jobs'][0]['list_checked_at'] == snapshot['fetched_at']
    assert reused['moka-campus-1']['list_checked_at'] == snapshot['fetched_at']
    assert campus['jobs'][0]['list_checked_at'] == snapshot['fetched_at']


def test_same_day_new_run_refetches_list(tmp_path, monkeypatch):
    monkeypatch.setenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(tmp_path / 'cache'))
    monkeypatch.setenv(src.MOKA_LOGICAL_RUN_ENV, 'run-a')
    monkeypatch.setattr(moka.time, 'sleep', lambda *_a, **_k: None)
    list_calls = []

    def request_json(session, url, payload, iv=None):
        if payload.get('jobId'):
            return _detail_for({'id': payload['jobId'], 'title': payload['jobId'], 'hireMode': 2,
                                'updatedAt': '2026-09-04T18:51:20'})
        list_calls.append(int(payload.get('offset', 0)))
        return make_request_json()(session, url, payload, iv)

    def collect(folder):
        with patch.object(moka, '_make_session', return_value=FakeSession(entry_html())), \
             patch.object(moka.shared, 'request_json', side_effect=request_json):
            return moka.collect('信也科技', 'campus', folder, max_requests=20)

    assert collect(tmp_path / 'a')['coverage'].get('list_cache_reused') is not True
    assert list_calls == [0, 50]
    monkeypatch.setenv(src.MOKA_LOGICAL_RUN_ENV, 'run-b')
    second = collect(tmp_path / 'b')
    assert second['coverage'].get('list_cache_reused') is not True
    assert list_calls == [0, 50, 0, 50]


def test_missing_or_default_run_id_does_not_share_list(tmp_path, monkeypatch):
    monkeypatch.setenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(tmp_path / 'cache'))
    monkeypatch.delenv(src.MOKA_LOGICAL_RUN_ENV, raising=False)
    host = 'https://app.mokahr.com'
    assert src.store_same_day_moka_list(tmp_path, host, 'paipaidai', '168312', [], 0) is None
    assert src.load_same_day_moka_list(tmp_path, host, 'paipaidai', '168312') is None
    monkeypatch.setenv(src.MOKA_LOGICAL_RUN_ENV, 'default')
    assert src.store_same_day_moka_list(tmp_path, host, 'paipaidai', '168312', [], 0) is None
    assert src.load_same_day_moka_list(tmp_path, host, 'paipaidai', '168312') is None


def test_previous_day_list_cannot_decide_removal(tmp_path, monkeypatch):
    root = tmp_path / 'cache'
    monkeypatch.setenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(root))
    monkeypatch.setenv(src.MOKA_LOGICAL_RUN_ENV, 'run-resume')
    monkeypatch.setattr(moka.time, 'sleep', lambda *_a, **_k: None)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    stale_row = {'id': 'stale-only', 'title': '旧岗位', 'hireMode': 2, 'commitment': '全职',
                 'status': 'open', 'updatedAt': '2026-09-01'}
    out = tmp_path / 'campus'
    host = 'https://app.mokahr.com'
    src._write_json(src.moka_list_cache_path(out, host, 'paipaidai', '168312', 'run-resume'), {
        'tenant': 'paipaidai', 'source': 'moka', 'site': '168312',
        'host': src.moka_host_origin(host), 'run_id': 'run-resume',
        'fetched_on': yesterday[:10], 'complete': True, 'total': 1, 'rows': [stale_row],
        'fetched_at': yesterday,
    })
    assert src.load_same_day_moka_list(out, host, 'paipaidai', '168312') is None

    def request_json(session, url, payload, iv=None):
        raise RuntimeError('list endpoint unavailable')

    with patch.object(moka, '_make_session', return_value=FakeSession(entry_html())), \
         patch.object(moka.shared, 'request_json', side_effect=request_json):
        result = moka.collect('信也科技', 'campus', out, max_requests=20)
    assert result['coverage']['complete'] is False
    assert result['coverage'].get('list_cache_reused') is not True
    assert [job['source_record_id'] for job in result['jobs']] == []
    assert 'stale-only' not in json.dumps(result['jobs'])


def _age_envelope(out, checked_at, row):
    path = src.moka_detail_cache_path('dji', 'campus', 'https://example.com', 'dji', '1', row['id'], out)
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['detail_checked_at'] = checked_at
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def test_detail_age_bounds_with_and_without_updated_at(tmp_path, monkeypatch):
    monkeypatch.setenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(tmp_path / 'cache'))
    out = tmp_path / 'campus'
    out.mkdir()
    row = {'id': 'a', 'title': 'A'}
    calls = []

    def request_json(session, url, payload, iv=None):
        calls.append(payload['jobId'])
        return {**row, 'jobDescription': '正文'}

    with patch.object(src, 'request_json', side_effect=request_json):
        first = src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', 1, None, out)
        second = src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', 1, None, out)
    assert first[2] is False and second[2] is True and calls == ['a']
    assert second[1] == first[1]

    _age_envelope(out, '2020-01-01T00:00:00+00:00', row)
    with patch.object(src, 'request_json', side_effect=request_json):
        stale = src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', 1, None, out)
    assert stale[2] is False and calls == ['a', 'a']
    assert stale[1] != '2020-01-01T00:00:00+00:00'

    fresh = datetime.now(timezone.utc).isoformat()
    _age_envelope(out, fresh, row)
    with patch.object(src, 'request_json', side_effect=request_json):
        recent = src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', 1, None, out)
    assert recent[2] is True and recent[1] == fresh and calls == ['a', 'a']

    expired = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    _age_envelope(out, expired, row)
    with patch.object(src, 'request_json', side_effect=request_json):
        aged = src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', 1, None, out)
    assert aged[2] is False and calls == ['a', 'a', 'a']

    _age_envelope(out, 'not-a-time', row)
    with patch.object(src, 'request_json', side_effect=request_json):
        illegal = src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', 1, None, out)
    assert illegal[2] is False and calls == ['a', 'a', 'a', 'a']

    future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    _age_envelope(out, future, row)
    with patch.object(src, 'request_json', side_effect=request_json):
        ahead = src.moka_detail_cached('dji', 'campus', row, 'https://example.com', 'dji', 1, None, out)
    assert ahead[2] is False and calls == ['a', 'a', 'a', 'a', 'a']

    dated = {'id': 'a', 'title': 'A', 'updatedAt': '2026-09-12T00:00:00'}
    with patch.object(src, 'request_json', return_value={**dated, 'jobDescription': '正文'}):
        src.moka_detail_cached('dji', 'campus', dated, 'https://example.com', 'dji', 1, None, out)
    _age_envelope(out, '2020-01-01T00:00:00+00:00', dated)
    calls.clear()
    with patch.object(src, 'request_json', side_effect=request_json):
        forced = src.moka_detail_cached('dji', 'campus', dated, 'https://example.com', 'dji', 1, None, out)
    assert forced[2] is False and calls == ['a']


def test_host_change_refetches_detail_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(tmp_path / 'cache'))
    monkeypatch.setenv(src.MOKA_LOGICAL_RUN_ENV, 'run-host')
    out = tmp_path / 'campus'
    out.mkdir()
    row = {'id': 'a', 'title': 'A', 'updatedAt': '2026-09-12'}
    calls = []

    def request_json(session, url, payload, iv=None):
        calls.append(url)
        return {**row, 'jobDescription': '正文'}

    with patch.object(src, 'request_json', side_effect=request_json):
        src.moka_detail_cached('dji', 'campus', row, 'https://jobs.example', 'dji', 1, None, out)
        again = src.moka_detail_cached('dji', 'campus', row, 'https://jobs.example', 'dji', 1, None, out)
        other = src.moka_detail_cached('dji', 'campus', row, 'https://other.example', 'dji', 1, None, out)
    assert again[2] is True and other[2] is False and len(calls) == 2
    assert src.moka_host_origin('HTTPS://Jobs.Example') == 'https://jobs.example:443'
    assert src.moka_host_origin('https://jobs.example:443') == 'https://jobs.example:443'
    assert src.moka_host_origin('https://jobs.example:8443') == 'https://jobs.example:8443'
    stored = src.store_same_day_moka_list(out, 'https://jobs.example', 'dji', '1', [row], 1)
    assert stored is not None
    assert src.load_same_day_moka_list(out, 'https://other.example', 'dji', '1') is None
    hit = src.load_same_day_moka_list(out, 'https://jobs.example', 'dji', '1')
    assert hit is not None and hit['host'] == 'https://jobs.example:443'
