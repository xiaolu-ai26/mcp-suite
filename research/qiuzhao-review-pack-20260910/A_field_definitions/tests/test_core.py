from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
import sqlite3
import pytest
from core.store import Store, AccessError, TZ, digest
from qiuzhao.tools import Jobs


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'access.sqlite3')


def test_atomic_redemption(store):
    code = store.generate_codes(1)[0]
    def redeem(_):
        try:
            return store.redeem(code)
        except AccessError:
            return None
    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(redeem, range(12)))
    assert sum(x is not None for x in results) == 1
    token = next(x['api_key'] for x in results if x)
    assert store.authorize(token)['remaining_today'] == 200
    # Database and SQLite WAL must not contain raw credentials.
    with store.connect() as db:
        dump = '\n'.join(db.iterdump())
    assert code not in dump and token not in dump


def test_atomic_daily_limit(store):
    token = store.redeem(store.generate_codes(1)[0])['api_key']
    def consume(_):
        try:
            store.consume(token, 'qiuzhao', 'jobs_search')
            return True
        except AccessError as exc:
            assert exc.status == 429
            return False
    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(consume, range(220)))
    assert sum(results) == 200
    assert store.authorize(token)['remaining_today'] == 0
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM usage_log').fetchone()[0] == 200


def test_expiry_product_and_invalid(store):
    token = store.redeem(store.generate_codes(1)[0])['api_key']
    with pytest.raises(AccessError, match='没有该产品权限'):
        store.consume(token, 'other', 'jobs_search')
    with pytest.raises(AccessError, match='无效'):
        store.authorize('invalid')
    with store.connect() as db:
        db.execute('UPDATE entitlements SET expires_at=?', ((datetime.now(TZ)-timedelta(seconds=1)).isoformat(),))
    with pytest.raises(AccessError, match='过期'):
        store.consume(token, 'qiuzhao', 'jobs_search')


def test_midnight_resets_and_handshake_free(store, monkeypatch):
    import core.store as module
    time = datetime(2026, 9, 10, 23, 59, 59, tzinfo=TZ)
    monkeypatch.setattr(module, 'now', lambda: time)
    token = store.redeem(store.generate_codes(1)[0])['api_key']
    store.consume(token, 'qiuzhao', 'jobs_search')
    for _ in range(3):
        assert store.authorize(token)['remaining_today'] == 199
    time += timedelta(seconds=2)
    assert store.authorize(token)['remaining_today'] == 200
    assert store.consume(token, 'qiuzhao', 'jobs_search')['remaining_today'] == 199


def test_jobs_preserve_facts_and_deadline_order(tmp_path):
    today = datetime.now(TZ).date()
    rows = []
    for i, delta in enumerate((2, 5, -1)):
        rows.append(dict(id=str(i), job_title='测试 fixture', cities=['北京'], major_requirements_raw=None,
                         cohort_raw=None, source_url='https://example.org/official', application_url='https://example.org/apply',
                         reviewed_at=datetime.now(TZ).isoformat(), published_at='2026-09-10',
                         deadline=(today+timedelta(days=delta)).isoformat(), deadline_type='explicit', status='open'))
    rows.append(dict(rows[0], id='undisclosed', deadline=None, deadline_type='undisclosed'))
    path = tmp_path / 'jobs.json'
    path.write_text(json.dumps(rows))
    jobs = Jobs(path)
    result = jobs.deadlines(7)
    assert [r['id'] for r in result['jobs']] == ['1', '0']
    assert result['source_urls'] and result['数据截至时间']
    assert jobs.search(cohort='2027')['jobs'] == []
    assert jobs.search(major='计算机')['suggestion']
    assert jobs.detail('2')['jobs'][0]['status'] == 'expired'
    assert jobs.detail('missing')['source_urls'] == []


def test_role_cohort_overrides_campaign_title(tmp_path):
    common = dict(source_url='https://example.org/official', application_url='https://example.org/apply',
                  reviewed_at='2026-09-10T10:00:00+08:00', campaign_cohort_raw='2027届校园招聘')
    rows = [dict(common, id='explicit-2026', cohort_raw='2026届应届毕业生'),
            dict(common, id='campaign-only', cohort_raw='')]
    path = tmp_path / 'jobs.json'
    path.write_text(json.dumps(rows))
    jobs = Jobs(path)
    matches = jobs.search(cohort='2027')['jobs']
    assert [row['id'] for row in matches] == ['campaign-only']
    assert matches[0]['cohort_filter_scope'] == 'campaign_title_only'
    assert jobs.search(cohort='2026')['jobs'][0]['id'] == 'explicit-2026'
    assert jobs.detail('explicit-2026')['jobs'][0]['cohort_filter_scope'] == 'role_record'
