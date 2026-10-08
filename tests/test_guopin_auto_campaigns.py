"""Dynamic 2027 campus-campaign discovery for the Guopin collector.

Only "where campaigns come from" is under test: the daily banner directory with
the guarantee list as fallback. Per-campaign fetching, completeness validation
and merge semantics are unchanged and covered elsewhere.
"""
import json

from qiuzhao.collector import run as R
from qiuzhao.collector import guopin as G


# --- discovery filter: 2027 + campus marker, from title or link --------------

MIXED_BANNERS = [
    # kept: 2027 + campus marker + resolvable alias
    {'id': '1', 'title': '中国工商银行江苏分行2027届校园招聘',
     'link_url': 'https://icbcjs.iguopin.com/campus', 'content_url': ''},
    {'id': '2', 'title': '2027年秋季校园招聘',
     'link_url': 'https://chd.iguopin.com/', 'content_url': ''},
    # skipped: social / wrong year / job fair / questionnaire without an alias
    {'id': '3', 'title': '2027届社会招聘',
     'link_url': 'https://social.iguopin.com/', 'content_url': ''},
    {'id': '4', 'title': '2026届校园招聘',
     'link_url': 'https://old.iguopin.com/', 'content_url': ''},
    {'id': '5', 'title': '2027届毕业生双选会',
     'link_url': 'https://fair.iguopin.com/', 'content_url': ''},
    {'id': '6', 'title': '2027届校园招聘问卷',
     'link_url': 'https://www.iguopin.com/survey/1', 'content_url': ''},
]


def test_discover_keeps_only_2027_campus_and_reports_skips(tmp_path):
    collector = R.Collector(tmp_path, delay=0)
    campaigns, skipped = G.discover_campaigns(collector, ads=MIXED_BANNERS)
    assert campaigns == [('chd', '2027年秋季校园招聘'),
                         ('icbcjs', '中国工商银行江苏分行2027届校园招聘')]
    reasons = {row['id']: row['reason'] for row in skipped}
    assert set(reasons) == {'3', '4', '5', '6'}
    assert 'no 2027 marker' in reasons['4']
    assert 'not an unambiguous campus campaign' in reasons['3']
    assert 'not an unambiguous campus campaign' in reasons['5']
    assert 'cannot resolve' in reasons['6']


# --- alias parsing: one success and one failure ------------------------------

def test_campaign_alias_accepts_single_label_iguopin_hosts():
    assert G.campaign_alias({'link_url': 'https://zgyd.iguopin.com/campus'}) == 'zgyd'
    assert G.campaign_alias({'link_url': '', 'content_url': 'https://cam2027.iguopin.com/x'}) == 'cam2027'


def test_campaign_alias_never_guesses():
    assert G.campaign_alias({'link_url': 'https://www.iguopin.com/job'}) is None
    assert G.campaign_alias({'link_url': 'https://a.b.iguopin.com/x'}) is None
    assert G.campaign_alias({'link_url': 'https://example.com/campus'}) is None
    assert G.campaign_alias({'link_url': '', 'content_url': ''}) is None


# --- fallback: banner directory failure must not sink the source -------------

def _banner(alias, title=None, content_url=''):
    return {'id': alias, 'title': title or alias + '2027届校园招聘',
            'link_url': 'https://%s.iguopin.com/campus' % alias, 'content_url': content_url}


def _fake_api(advertised, fail_ads=False):
    calls = {'config': []}
    counter = iter(range(100000))

    def api(collector, url, payload=None):
        path = url.split('gp-api.iguopin.com')[1].split('?')[0]
        if path == '/api/base/ads/v1/list':
            if fail_ads:
                raise RuntimeError('banner directory exploded')
            return {'list': advertised}
        if path == '/api/activity/exclusive/v1/info':
            calls['config'].append(url.split('domain=')[1].split('&')[0])
            return {'company_id': 'c1', 'title': '2027校园招聘',
                    'company': {'id': 'c1', 'name': '某集团', 'show_name': '某', 'nature_cn': '央企'},
                    'content': json.dumps({'params': {'nav': [{'type': 'job', 'props': {}, 'route': '/campus'}]}})}
        if path == '/api/jobs/v1/list':
            ident = 'job-%d' % next(counter)
            return {'total': 1, 'list': [{
                'job_id': ident, 'job_name': '工程师', 'company_id': 'c1', 'company_name': '某子公司',
                'recruitment_type_cn': '校园招聘', 'nature_cn': '校招', 'category_cn': '技术',
                'education_cn': '本科', 'experience_cn': '应届', 'is_graduates': True,
                'department_cn': '技术部', 'start_time': '2026-09-01 00:00:00',
                'end_time': '2027-06-30 23:59:59', 'district_list': [{'area_cn': '北京'}],
                'contents': '岗位职责：开发。\n2027届应届毕业生', 'status': 1, 'is_apply': True,
                'apply_instruction': '', 'refresh_time': '', 'update_time': ''}]}
        raise AssertionError('unexpected guopin API path: ' + path)

    return api, calls


def test_banner_failure_falls_back_to_guarantee_list(tmp_path, monkeypatch):
    api, calls = _fake_api([], fail_ads=True)
    monkeypatch.setattr(G, 'public_api', api)
    collector = R.Collector(tmp_path, delay=0)
    rows = G.collect_guopin(collector)
    state = collector.states['guopin']
    assert state['fallback_used'] is True
    assert set(state['campaigns']) == {alias for alias, _ in G.CAMPAIGNS}
    assert set(calls['config']) == {alias for alias, _ in G.CAMPAIGNS}
    assert len(rows) == len(G.CAMPAIGNS)
    assert [a['source'] for a in collector.alerts] == ['guopin:discovery']
    assert 'cgnpc' not in {alias for alias, _ in G.CAMPAIGNS}


# --- dedup: an alias in both the guarantee list and discovery runs once ------

def test_alias_in_both_guarantee_and_discovered_is_collected_once(tmp_path, monkeypatch):
    advertised = [_banner(alias) for alias, _ in G.CAMPAIGNS] + [_banner('brandnew')]
    api, calls = _fake_api(advertised)
    monkeypatch.setattr(G, 'public_api', api)
    collector = R.Collector(tmp_path, delay=0)
    rows = G.collect_guopin(collector)
    state = collector.states['guopin']
    assert state['discovered'] == sorted([alias for alias, _ in G.CAMPAIGNS] + ['brandnew'])
    assert calls['config'].count('zgyd') == 1
    assert len(calls['config']) == len(G.CAMPAIGNS) + 1
    assert set(state['campaigns']) == {alias for alias, _ in G.CAMPAIGNS} | {'brandnew'}
    assert len(rows) == len(calls['config'])
    assert state['fallback_used'] is False


# --- merge stability and end-to-end discovery --------------------------------

def test_merge_campaigns_union_is_alias_sorted_and_deduped():
    discovered = [('zglt', '联通2027校招'), ('aaa', 'AAA2027校招'), ('zgyd', '移动2027校招')]
    merged = G.merge_campaigns(discovered)
    aliases = [alias for alias, _ in merged]
    assert aliases == sorted(aliases)
    assert len(aliases) == len(set(aliases))
    assert set(aliases) == {alias for alias, _ in G.CAMPAIGNS} | {'aaa'}
    # Guarantee-list titles win for an alias that is discovered as well.
    assert dict(merged)['zglt'] == dict(G.CAMPAIGNS)['zglt']
    assert dict(merged)['aaa'] == 'AAA2027校招'


def test_advertised_2027_banner_is_discovered_end_to_end(tmp_path, monkeypatch):
    """Banner is the only source of the campaign set: the alias is not hardcoded."""
    api, _ = _fake_api([_banner('brandnew2027', '某集团2027届秋季校园招聘')])
    monkeypatch.setattr(G, 'public_api', api)
    collector = R.Collector(tmp_path, delay=0)
    rows = G.collect_guopin(collector)
    assert 'brandnew2027' in collector.states['guopin']['discovered']
    assert any(j['source_group_key'] == 'brandnew2027'
               and j['campaign_url'].startswith('https://brandnew2027.iguopin.com') for j in rows)


def test_missing_job_navigation_keeps_restricted_config_and_typed_phase(tmp_path, monkeypatch):
    api, _ = _fake_api([_banner('zgyd')])
    def missing_navigation(collector, url, payload=None):
        data = api(collector, url, payload)
        if '/api/activity/exclusive/v1/info' in url:
            data['content'] = json.dumps({'params': {'nav': [{'type': 'other', 'route': '/info'}]}})
            data['access_token'] = 'DO_NOT_RECORD_CREDENTIAL'
        return data
    monkeypatch.setattr(G, 'public_api', missing_navigation)
    monkeypatch.setattr(G, 'CAMPAIGNS', (('zgyd', '测试集团'),))
    collector = R.Collector(tmp_path, delay=0)
    assert G.collect_guopin(collector) == []
    state = collector.states['guopin']['campaigns']['zgyd']
    assert state['error_type'] == 'ValueError' and state['failure_phase'] == 'navigation_parse'
    assert 'job navigation missing' in state['error'] and state['complete'] is False
    evidence = json.loads((collector.evidence / 'guopin-zgyd-config-raw.json').read_text())
    assert json.loads(evidence['content'])['params']['nav'][0]['type'] == 'other'
    assert 'access_token' not in evidence
    assert 'DO_NOT_RECORD_CREDENTIAL' not in json.dumps(evidence)
    alert = collector.alerts[0]
    assert alert['failure_phase'] == 'navigation_parse' and alert['error_type'] == 'ValueError'
    assert all(set(frame) == {'file', 'function', 'line'} for frame in alert['error_stack'])


def test_bad_config_json_keeps_preparse_evidence(tmp_path, monkeypatch):
    api, _ = _fake_api([_banner('zgyd')])
    def bad_config(collector, url, payload=None):
        data = api(collector, url, payload)
        if '/api/activity/exclusive/v1/info' in url:
            data['content'] = '{broken navigation json'
        return data
    monkeypatch.setattr(G, 'public_api', bad_config)
    monkeypatch.setattr(G, 'CAMPAIGNS', (('zgyd', '测试集团'),))
    collector = R.Collector(tmp_path, delay=0)
    assert G.collect_guopin(collector) == []
    state = collector.states['guopin']['campaigns']['zgyd']
    assert state['error_type'] == 'JSONDecodeError' and state['failure_phase'] == 'navigation_parse'
    evidence = json.loads((collector.evidence / 'guopin-zgyd-config-raw.json').read_text())
    assert evidence['content'] == '{broken navigation json'


def test_restricted_preparse_config_bounds_and_redacts_content(tmp_path, monkeypatch):
    api, _ = _fake_api([_banner('zgyd')])
    def config_with_extra_credentials(collector, url, payload=None):
        data = api(collector, url, payload)
        if '/api/activity/exclusive/v1/info' in url:
            data['content'] = '{"accessToken":"SYNTHETIC_CONTENT_SECRET","padding":"' + 'x' * 66000
            data['appSecret'] = 'SYNTHETIC_OUTSIDE_SECRET'
        return data
    monkeypatch.setattr(G, 'public_api', config_with_extra_credentials)
    monkeypatch.setattr(G, 'CAMPAIGNS', (('zgyd', '测试集团'),))
    collector = R.Collector(tmp_path, delay=0)
    G.collect_guopin(collector)
    evidence = json.loads((collector.evidence / 'guopin-zgyd-config-raw.json').read_text())
    assert evidence['content_truncated'] and evidence['content_redacted']
    assert len(evidence['content']) <= 65536
    assert len(evidence['content_sha256']) == 64
    assert 'SYNTHETIC_CONTENT_SECRET' not in json.dumps(evidence)
    assert 'SYNTHETIC_OUTSIDE_SECRET' not in json.dumps(evidence)


def test_short_repeated_secret_redaction_cannot_expand_saved_content_past_cap(tmp_path, monkeypatch):
    api, _ = _fake_api([_banner('zgyd')])
    content = '[' + ','.join(['{"token":"x"}'] * 4680) + ']'
    assert len(content) < 65536
    def repeated_secrets(collector, url, payload=None):
        data = api(collector, url, payload)
        if '/api/activity/exclusive/v1/info' in url:
            data['content'] = content
        return data
    monkeypatch.setattr(G, 'public_api', repeated_secrets)
    monkeypatch.setattr(G, 'CAMPAIGNS', (('zgyd', '测试集团'),))
    collector = R.Collector(tmp_path, delay=0)
    G.collect_guopin(collector)
    evidence = json.loads((collector.evidence / 'guopin-zgyd-config-raw.json').read_text())
    assert evidence['content_redacted']
    assert not evidence['content_truncated']
    assert evidence['redacted_content_truncated']
    assert len(evidence['content']) <= 65536
    assert '"token":"x"' not in evidence['content']
