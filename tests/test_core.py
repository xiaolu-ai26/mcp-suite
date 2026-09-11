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


def test_qiuzhao_code_and_key_format_unchanged(store):
    code = store.generate_codes(1, 'qiuzhao-2026')[0]
    assert code.startswith('QZ-') and len(code) == 35
    result = store.redeem(code)
    assert result['api_key'].startswith('qz_')
    assert result['product'] == 'qiuzhao'
    assert result['valid_through'] == '2026-12-31'
    assert result['expires_at'] == '2027-01-01T00:00:00+08:00'
    assert result['daily_limit'] == 200
    with pytest.raises(AccessError, match='兑换码无效，请检查输入。'):
        store.redeem('QZ-TOO-SHORT')


def test_bench_plan_is_thirty_days_from_activation(store, monkeypatch):
    import core.store as module
    activated = datetime(2026, 9, 10, 15, 0, 0, tzinfo=TZ)
    monkeypatch.setattr(module, 'now', lambda: activated)
    code = store.generate_codes(1, 'bench-monthly')[0]
    assert code.startswith('BM-') and len(code) == 35
    result = store.redeem(code)
    assert result['api_key'].startswith('bm_') and result['product'] == 'bench'
    assert result['expires_at'] == (activated + timedelta(days=30)).isoformat()
    assert result['valid_through'] == '2026-10-10'
    assert store.consume(result['api_key'], 'bench', 'bench_search')['remaining_today'] == 199
    with pytest.raises(AccessError, match='没有该产品权限'):
        store.consume(result['api_key'], 'qiuzhao', 'jobs_search')


def test_quota_message_uses_plan_limit(store):
    token = store.redeem(store.generate_codes(1, 'bench-monthly')[0])['api_key']
    with store.connect() as db:
        db.execute('UPDATE entitlements SET daily_limit=1 WHERE product=?', ('bench',))
    store.consume(token, 'bench', 'bench_search')
    with pytest.raises(AccessError, match='今日 1 次调用额度已用完'):
        store.consume(token, 'bench', 'bench_search')


def test_bench_returns_links_tags_and_no_body(tmp_path):
    from bench.tools import Bench
    payload = {'data_as_of': '2026-09-03', 'taxonomy': {'topic_category': ['AI工具']},
               'records': [
                   {'id': 'a', 'url': 'https://example.org/a', 'platform': '小红书', 'note_type': '图文',
                    'title': '标题A', 'published_at': '2026-08-01', 'topic_category': 'AI工具',
                    'title_formula': '数字清单+必备感', 'follower_band': '0-1k', 'breakout_level': '强',
                    'takeaway': '爆点：…', 'observed_at': '2026-09-01', 'source_batch': 'viral_radar',
                    'tagging': {'mode': 'ai_filled'}, 'transcript': '这段逐字稿绝不能出现在返回里'},
                   {'id': 'b', 'url': '', 'title': '没有链接的记录'},
                   {'id': 'c', 'url': 'https://example.org/c', 'platform': '抖音', 'note_type': '视频',
                    'title': '标题C', 'published_at': '', 'topic_category': 'AI变现',
                    'observed_at': '2026-09-03', 'tagging': {'mode': 'url_only'}}]}
    path = tmp_path / 'bench.json'
    path.write_text(json.dumps(payload, ensure_ascii=False))
    bench = Bench(path)
    result = bench.search()
    assert result['total'] == 2 and result['数据截至时间'] == '2026-09-03'
    assert all('transcript' not in row for row in result['records'])
    assert bench.search(platform='抖音')['records'][0]['id'] == 'c'
    assert bench.search(tag='数字清单+必备感')['records'][0]['id'] == 'a'
    # A record with no publish date is excluded from a time window instead of guessed.
    assert [r['id'] for r in bench.search(time_window='2026-08')['records']] == ['a']
    assert bench.search(topic='不存在的分类')['suggestion']
    assert bench.detail('a')['found'] and not bench.detail('zzz')['found']
    taxonomy = bench.taxonomy()
    assert taxonomy['total_records'] == 2
    assert taxonomy['topic_category']['counts']['AI工具'] == 1
    assert taxonomy['cover_hook']['counts']['未标注'] == 2
