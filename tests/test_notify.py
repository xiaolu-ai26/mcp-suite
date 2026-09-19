"""cc 机器人告警通道的离线单测。

三条必须成立的契约:
1. 凭据/目标缺失 → 降级写告警文件,主流程不失败(不抛异常);
2. 发送失败 → 重试一次后降级;第二次成功则不降级;
3. **日志、告警文件、返回值里都不出现凭据**(用假凭据断言)。

测试全程不联网:``opener``/``runner`` 全部注入假实现,且显式传 ``environ={}``,
避免读到本机真实的 ``~/.config/qiuzhao-cc-bot.env`` 或真实目标配置。
"""
import json
import logging
import urllib.error
from pathlib import Path

import pytest

from qiuzhao import notify

FAKE_ID = 'cli_fakeappid123456'
FAKE_SECRET = 'fakesecret_value_abcdefghijklmnop'
FAKE_ENV = {'CC_BOT_APP_ID': FAKE_ID, 'CC_BOT_APP_SECRET': FAKE_SECRET}
TARGET = {'kind': 'user_id', 'receive_id': 'ou_fakeuser000000000000000000000', 'receive_id_type': 'open_id'}
MISSING_ENV_FILE = '/nonexistent/cc-bot.env'
MISSING_TARGETS = '/nonexistent/notify_targets.json'


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode('utf-8')

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Recorder:
    """Fake urlopen: returns queued payloads, raises queued exceptions."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        outcome = self.outcomes.pop(0) if self.outcomes else {'code': 0, 'data': {'message_id': 'om_default'}}
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)

    @property
    def auth_headers(self):
        return [request.get_header('Authorization') for request in self.requests]


@pytest.fixture(autouse=True)
def _clean_token_cache():
    notify._TOKENS.clear()
    yield
    notify._TOKENS.clear()


def token_payload(code=0, token='t-faketoken-0000000000'):
    return {'code': code, 'msg': 'ok' if code == 0 else 'bad', 'tenant_access_token': token, 'expire': 7200}


def send_payload(code=0):
    return {'code': code, 'msg': 'ok' if code == 0 else 'rejected', 'data': {'message_id': 'om_fake'}}


def do_notify(opener=None, runner=None, alert_path=None, credentials=True, **kwargs):
    kwargs.setdefault('text', '详情一行')
    kwargs.setdefault('fields', {'capacity': {'used': 19993, 'limit': 20000}})
    return notify.notify('continuation_created', targets=MISSING_TARGETS, env_file=MISSING_ENV_FILE,
                         alert_path=alert_path, timeout=0.01, opener=opener, runner=runner,
                         override_target=TARGET, environ=dict(FAKE_ENV) if credentials else {}, **kwargs)


# ------------------------------------------------------------ 凭据缺失/目标缺失

def test_missing_credentials_degrades_to_file(tmp_path):
    result = do_notify(alert_path=tmp_path / "alerts.jsonl", credentials=False)
    assert result['sent'] is False and result['channel'] == 'file'
    assert result['reason'] == 'no_credentials'
    lines = (tmp_path / 'alerts.jsonl').read_text(encoding='utf-8').strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record['event'] == 'continuation_created' and record['reason'] == 'no_credentials'
    assert '飞书续表已自动创建' in record['message'] and '19993' in record['message']


def test_missing_target_degrades_even_with_credentials(tmp_path):
    result = notify.notify('test', targets=MISSING_TARGETS, env_file=MISSING_ENV_FILE,
                           alert_path=tmp_path / 'a.jsonl', environ=dict(FAKE_ENV))
    assert result['sent'] is False and result['reason'] == 'no_target'
    assert result['alert_path'] == str(tmp_path / 'a.jsonl')


def test_empty_target_config_is_no_target(tmp_path):
    targets = tmp_path / 'targets.json'
    targets.write_text(json.dumps({'chat_id': '', 'user_id': ''}), encoding='utf-8')
    result = notify.notify('test', targets=targets, env_file=MISSING_ENV_FILE,
                           alert_path=tmp_path / 'a.jsonl', environ=dict(FAKE_ENV))
    assert result['reason'] == 'no_target'


def test_alert_file_write_failure_does_not_raise(tmp_path):
    blocked = tmp_path / 'alerts.jsonl'
    blocked.mkdir()  # a directory where the file should be -> OSError inside writer
    result = do_notify(alert_path=blocked)
    assert result['sent'] is False and result['alert_path'] is None


def test_default_alert_path_follows_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv('QIUZHAO_DATA_DIR', str(tmp_path))
    assert notify.default_alert_path() == tmp_path / 'notify-alerts.jsonl'


# ------------------------------------------------------------------ 发送/重试

def test_successful_send_uses_token_then_message(tmp_path):
    opener = Recorder(token_payload(), send_payload())
    result = do_notify(opener=opener, alert_path=tmp_path / 'a.jsonl')
    assert result['sent'] is True and result['channel'] == 'feishu'
    assert result['message_id'] == 'om_fake' and result['attempts'] == 1
    assert len(opener.requests) == 2
    body = json.loads(opener.requests[1].data.decode('utf-8'))
    assert body['receive_id'] == TARGET['receive_id'] and body['msg_type'] == 'text'
    assert '要站长做什么' in json.loads(body['content'])['text']
    assert not (tmp_path / 'a.jsonl').exists()  # nothing degraded


def test_send_failure_retries_once_then_degrades(tmp_path):
    opener = Recorder(token_payload(), send_payload(code=9499), send_payload(code=9499))
    result = do_notify(opener=opener, alert_path=tmp_path / 'a.jsonl')
    assert result['sent'] is False and result['reason'] == 'send_failed'
    assert result['attempts'] == 2
    assert len(opener.requests) == 3  # token once (cached) + send twice
    record = json.loads((tmp_path / 'a.jsonl').read_text(encoding='utf-8').strip())
    assert record['reason'] == 'send_failed' and '9499' in record['error']


def test_transient_failure_succeeds_on_retry(tmp_path):
    opener = Recorder(token_payload(), urllib.error.URLError('temporary'), send_payload())
    result = do_notify(opener=opener, alert_path=tmp_path / 'a.jsonl')
    assert result['sent'] is True and result['attempts'] == 2
    assert not (tmp_path / 'a.jsonl').exists()


def test_invalid_token_refreshes_once_within_one_attempt(tmp_path):
    opener = Recorder(token_payload(token='t-stale-000000000'), send_payload(code=99991663),
                      token_payload(token='t-fresh-000000000'), send_payload())
    result = do_notify(opener=opener, alert_path=tmp_path / 'a.jsonl')
    assert result['sent'] is True and result['attempts'] == 1
    assert opener.auth_headers == [None, 'Bearer t-stale-000000000', None, 'Bearer t-fresh-000000000']


def test_token_is_cached_across_sends(tmp_path):
    opener = Recorder(token_payload(), send_payload(), send_payload())
    first = do_notify(opener=opener, alert_path=tmp_path / 'a.jsonl')
    second = do_notify(opener=opener, alert_path=tmp_path / 'b.jsonl')
    assert first['sent'] and second['sent']
    assert len(opener.requests) == 3  # one token call for two sends


def test_tenant_token_rejection_is_reported_without_credentials(tmp_path):
    rejected = {'code': 10003, 'msg': 'app not found ' + FAKE_SECRET}
    opener = Recorder(rejected, rejected)
    result = do_notify(opener=opener, alert_path=tmp_path / 'a.jsonl')
    assert result['sent'] is False and result['reason'] == 'send_failed'
    assert '10003' in result['error'] and FAKE_SECRET not in result['error']


# -------------------------------------------------------------- 凭据不外泄

def test_no_credential_material_in_logs_alerts_or_results(tmp_path, caplog):
    # Worst case: the transport error text itself carries the secret.
    boom = RuntimeError('boom ' + FAKE_SECRET + ' app=' + FAKE_ID)
    opener = Recorder(token_payload(), boom, boom)
    with caplog.at_level(logging.DEBUG):
        result = do_notify(opener=opener, alert_path=tmp_path / 'a.jsonl')
    blob = json.dumps(result, ensure_ascii=False) + caplog.text
    blob += (tmp_path / 'a.jsonl').read_text(encoding='utf-8')
    assert result['sent'] is False
    assert FAKE_SECRET not in blob
    assert FAKE_ID not in blob
    assert 'Bearer' not in blob and 'tenant_access_token' not in blob


def test_redact_covers_bearer_and_token_shapes():
    text = ('Authorization: Bearer t-abcdef123456 app_secret=' + FAKE_SECRET +
            ' tenant_access_token=t-zzzzzzzzzzzz ' + FAKE_ID)
    cleaned = notify.redact(text, (FAKE_SECRET, FAKE_ID))
    for forbidden in (FAKE_SECRET, FAKE_ID, 't-abcdef123456', 't-zzzzzzzzzzzz'):
        assert forbidden not in cleaned
    assert '<redacted>' in cleaned


def test_check_cli_does_not_print_secret(tmp_path, capsys):
    env_file = tmp_path / 'cc.env'
    env_file.write_text('%s=%s\n%s=%s\n' % (notify.APP_ID_VAR, FAKE_ID, notify.APP_SECRET_VAR, FAKE_SECRET),
                        encoding='utf-8')
    code = notify.main(['--check', '--env-file', str(env_file), '--targets', MISSING_TARGETS,
                        '--transport', 'api', '--alert-path', str(tmp_path / 'a.jsonl')])
    output = capsys.readouterr().out
    assert code == notify.EXIT_SENT
    assert 'present' in output and FAKE_SECRET not in output


def test_env_file_credentials_are_loaded(tmp_path):
    env_file = tmp_path / 'cc.env'
    env_file.write_text('# cc bot\nexport %s="%s"\n%s=%s\n'
                        % (notify.APP_ID_VAR, FAKE_ID, notify.APP_SECRET_VAR, FAKE_SECRET), encoding='utf-8')
    credentials = notify.load_credentials(env_file, environ={})
    assert credentials['app_id'] == FAKE_ID and credentials['app_secret'] == FAKE_SECRET
    assert credentials['source'] == str(env_file)
    assert notify.load_credentials(env_file, environ=dict(FAKE_ENV))['source'] == 'environment'
    assert notify.load_credentials(tmp_path / 'nope.env', environ={}) is None


# ------------------------------------------------------------------ 消息格式

def test_message_contains_time_event_numbers_and_action():
    message = notify.format_message('lark_sync_failed',
                                    {'status': 'failed', 'phase': 'append', 'error': 'exit=1'},
                                    at='2026-09-20T09:00:00+08:00')
    assert '时间: 2026-09-20T09:00:00+08:00' in message
    assert '事件: lark_sync_failed' in message
    assert '关键数字: error=exit=1; phase=append; status=failed' in message
    assert '要站长做什么: ' in message and '精灵飞书同步失败' in message


def test_unknown_event_still_formats():
    message = notify.format_message('brand_new_thing', {'count': 3, 'nested': {'a': 'b'}, 'empty': ''})
    assert '事件: brand_new_thing' in message and 'count=3' in message and 'nested.a=b' in message


def test_message_is_truncated():
    message = notify.format_message('test', {'blob': 'x' * 5000})
    assert len(message) <= notify.MESSAGE_MAX_CHARS


# --------------------------------------------------------------- 批量 / 降级

def test_batch_falls_back_only_degraded_events(tmp_path):
    events = tmp_path / 'events.jsonl'
    events.write_text('\n'.join([
        json.dumps({'kind': 'freshness_stale', 'text': '【秋招】数据过期', 'fields': {'status': 'stale'}}),
        json.dumps({'kind': 'lark_sync_failed', 'text': '【秋招】同步失败', 'fields': {'status': 'failed'}}),
    ]) + '\n', encoding='utf-8')
    fallback = tmp_path / 'fallback.txt'
    codes = notify.main(['--batch-jsonl', str(events), '--fallback', str(fallback), '--targets', MISSING_TARGETS,
                         '--env-file', str(tmp_path / 'none.env'), '--alert-path', str(tmp_path / 'a.jsonl')])
    assert codes == notify.EXIT_DEGRADED
    assert fallback.read_text(encoding='utf-8').splitlines() == ['【秋招】数据过期', '【秋招】同步失败']


def test_disable_var_short_circuits(tmp_path):
    result = notify.notify('test', targets=MISSING_TARGETS, env_file=MISSING_ENV_FILE,
                           alert_path=tmp_path / 'a.jsonl', environ={notify.DISABLE_VAR: '1'})
    assert result['sent'] is False and result['reason'] == 'disabled'
    assert not (tmp_path / 'a.jsonl').exists()


# ------------------------------------------------------------------- 传输选择

def test_transport_auto_prefers_lark_cli_only_for_this_app(monkeypatch):
    monkeypatch.setattr(notify, '_CLI_PROBED', True)
    monkeypatch.setattr(notify, '_CLI_APP_ID', FAKE_ID)
    assert notify.choose_transport('auto', {'app_id': FAKE_ID}, environ={}) == 'lark-cli'
    assert notify.choose_transport('auto', {'app_id': 'cli_other'}, environ={}) == 'api'
    assert notify.choose_transport('api', {'app_id': FAKE_ID}, environ={}) == 'api'
    assert notify.choose_transport('lark-cli', {'app_id': 'cli_other'}, environ={}) == 'lark-cli'


def test_lark_cli_transport_parses_envelope(tmp_path):
    calls = []

    class Completed:
        def __init__(self, stdout, returncode=0, stderr=b''):
            self.stdout, self.returncode, self.stderr = stdout, returncode, stderr

    def runner(argv, timeout, environ=None):
        calls.append(argv)
        return Completed(json.dumps({'ok': True, 'data': {'message_id': 'om_cli'}}).encode())

    result = notify.notify('test', targets=MISSING_TARGETS, env_file=MISSING_ENV_FILE,
                           alert_path=tmp_path / 'a.jsonl', environ=dict(FAKE_ENV),
                           override_target=TARGET, transport='lark-cli', runner=runner)
    assert result['sent'] is True and result['transport'] == 'lark-cli'
    assert result['message_id'] == 'om_cli'
    assert calls[0][:4] == ['lark-cli', 'im', '+messages-send', '--as']
    assert '--user-id' in calls[0] and TARGET['receive_id'] in calls[0]


def test_lark_cli_failure_degrades_after_retry(tmp_path):
    def runner(argv, timeout, environ=None):
        class Completed:
            stdout, returncode, stderr = b'', 1, b'boom'
        return Completed()

    result = notify.notify('test', targets=MISSING_TARGETS, env_file=MISSING_ENV_FILE,
                           alert_path=tmp_path / 'a.jsonl', environ=dict(FAKE_ENV),
                           override_target=TARGET, transport='lark-cli', runner=runner)
    assert result['sent'] is False and result['reason'] == 'send_failed' and result['attempts'] == 2


# ------------------------------------------------------------ 三处告警接入点

def test_record_alert_uses_the_shared_notifier(tmp_path, monkeypatch):
    from qiuzhao.collector import lark_continuation as C

    seen = []

    def fake_notifier(event):
        seen.append(event)
        return {'sent': True, 'channel': 'feishu', 'reason': None}

    monkeypatch.setattr('qiuzhao.notify.default_notifier', lambda environ=None: fake_notifier)
    event = C.record_alert(tmp_path / 'continuation-alerts.jsonl',
                           {'kind': 'continuation_created', 'group': '互联网科技岗', 'table': '互联网科技岗·续表3'})
    assert seen and seen[0]['kind'] == 'continuation_created'
    assert event['channel'] == 'notifier'
    assert event['notifier_result'] == {'sent': True, 'channel': 'feishu', 'reason': None}
    record = json.loads((tmp_path / 'continuation-alerts.jsonl').read_text(encoding='utf-8').strip())
    assert record['kind'] == 'continuation_created'  # the run-level file record stays


def test_record_alert_stays_file_only_when_disabled(tmp_path, monkeypatch):
    from qiuzhao.collector import lark_continuation as C

    monkeypatch.setenv('QIUZHAO_NOTIFY_DISABLE', '1')
    event = C.record_alert(tmp_path / 'a.jsonl', {'kind': 'continuation_create_failed'})
    assert event['channel'] == 'file' and 'notifier_result' not in event


def test_record_alert_survives_a_broken_notifier(tmp_path):
    from qiuzhao.collector import lark_continuation as C

    def broken(event):
        raise RuntimeError('channel down')

    event = C.record_alert(tmp_path / 'a.jsonl', {'kind': 'continuation_live_invalid'}, notifier=broken)
    assert event['channel'] == 'notifier' and 'channel down' in event['notifier_error']


def test_sync_daemon_failure_alerts_and_never_raises(tmp_path, monkeypatch):
    from qiuzhao.collector import lark_sync_daemon as D

    monkeypatch.setenv('QIUZHAO_LARK_SYNC_LOCK_PATH', str(tmp_path / 'sync.lock'))
    monkeypatch.delenv('QIUZHAO_LARK_SYNC_LOCK_FD', raising=False)
    monkeypatch.chdir(tmp_path)  # run_local requires its runs dir under the cwd
    captured = []
    monkeypatch.setattr(D, 'alert_sync_failed',
                        lambda state, status_path: captured.append((state.get('status'), state.get('phase'))))
    monkeypatch.setattr(D.S, 'cli', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('base down')))

    state_dir = tmp_path / 'state'
    with pytest.raises(RuntimeError):
        D.run_local(tmp_path / 'jobs.json', state_dir, tmp_path / 'runs', apply=True)
    assert captured == [('failed', None)]
    assert json.loads((state_dir / 'status.json').read_text(encoding='utf-8'))['status'] == 'failed'


def test_alert_sync_failed_swallows_notifier_errors(monkeypatch):
    from qiuzhao.collector import lark_sync_daemon as D

    def explode(*args, **kwargs):
        raise RuntimeError('channel down')

    monkeypatch.setattr('qiuzhao.notify.notify', explode)
    D.alert_sync_failed({'status': 'failed', 'phase': 'append', 'error': 'exit=1'}, Path('/tmp/status.json'))
