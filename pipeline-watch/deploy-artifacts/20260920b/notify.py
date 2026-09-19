"""飞书告警通道(cc 机器人)——秋招管线唯一的消息出口。

项目约定(交接文档 §1):要站长看见的告警走飞书消息,不走 AI 留言板。此前全仓没有
消息通道,续表告警只能落 ``continuation-alerts.jsonl``。本模块把通道补上,并被三处
共用:①飞书续表创建成功/失败(``lark_continuation.record_alert`` 的 notifier 钩子)
②数据过期告警(``deploy/freshness_notify_mac.sh``)③精灵飞书同步失败
(``lark_sync_daemon`` 与同一脚本)。

设计约束(与任务书硬约束一致):

* 凭据只从环境变量 ``CC_BOT_APP_ID`` / ``CC_BOT_APP_SECRET`` 或仓库之外的 env 文件
  (默认 ``~/.config/qiuzhao-cc-bot.env``,可用 ``QIUZHAO_CC_BOT_ENV_FILE`` 覆盖)读取;
  **凭据值绝不写进代码、配置、日志、收据、提交、测试夹具,也不进返回值**——所有对外
  字符串都过 :func:`redact`。
* ``tenant_access_token`` 进程内缓存,过期前自动刷新;被平台判失效时强制刷新一次。
* 目标会话 id 放配置 ``qiuzhao/data/notify_targets.json``(值留空 = 未配置)。
* 传输优先本机 ``lark-cli``(仅当它绑定的应用就是本机器人),否则直接调开放平台接口。
* **任何失败都降级**:发送失败重试一次,仍失败就把告警追加到 JSONL 告警文件,
  :func:`notify` 返回结果字典,绝不向调用方抛异常——主流程不许因为告警挂掉。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

LOG = logging.getLogger('qiuzhao.notify')

APP_ID_VAR = 'CC_BOT_APP_ID'
APP_SECRET_VAR = 'CC_BOT_APP_SECRET'
ENV_FILE_VAR = 'QIUZHAO_CC_BOT_ENV_FILE'
DISABLE_VAR = 'QIUZHAO_NOTIFY_DISABLE'
TARGETS_VAR = 'QIUZHAO_NOTIFY_TARGETS'
ALERT_PATH_VAR = 'QIUZHAO_NOTIFY_ALERT_PATH'
TRANSPORT_VAR = 'QIUZHAO_NOTIFY_TRANSPORT'

DEFAULT_ENV_FILE = '~/.config/qiuzhao-cc-bot.env'
DEFAULT_TARGETS_FILE = Path(__file__).resolve().parents[1] / 'qiuzhao' / 'data' / 'notify_targets.json'
DEFAULT_ALERT_NAME = 'notify-alerts.jsonl'

TOKEN_URL = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
MESSAGE_URL = 'https://open.feishu.cn/open-apis/im/v1/messages'
CHAT_LIST_URL = 'https://open.feishu.cn/open-apis/im/v1/chats'

# 平台返回的"令牌无效/过期"错误码:强制刷新一次再试。
TOKEN_INVALID_CODES = {99991661, 99991663, 99991664, 99991668}
MESSAGE_MAX_CHARS = 2000

EXIT_SENT = 0
EXIT_DEGRADED = 3
EXIT_USAGE = 2

# 事件 → (标题, 站长动作)。未登记的事件也能发,标题用事件名。
EVENTS = {
    'test': ('cc 机器人通知通道测试', '无需操作;收到这条就说明告警通道可用'),
    'continuation_created': ('飞书续表已自动创建', '无需操作;新表已逐字段校验,可正常写入'),
    'continuation_create_failed': ('飞书续表创建失败', '确认飞书 Base 容量/机器人权限后重跑同步'),
    'continuation_validation_failed': ('飞书续表字段校验失败(已删表)', '确认 Base 字段是否被人工改动,再重跑同步'),
    'continuation_live_invalid': ('飞书续表与基表字段漂移', '确认 Base 字段是否被人工改动'),
    'freshness_stale': ('岗位数据过期', '检查精灵采集与发布是否跑成功'),
    'freshness_lagging': ('飞书镜像落后于服务器库', '检查精灵飞书同步是否在跑'),
    'freshness_unreachable': ('服务器 /health 连续读不到', '检查阿里云 mcp-suite 服务与网络'),
    'freshness_multi_problem': ('管线新鲜度多项异常', '按详情逐项检查精灵与服务器'),
    'lark_sync_failed': ('精灵飞书同步失败', '看精灵 data\\lark-sync\\status.json 与 sync.log,处理后重跑同步'),
    'lark_sync_stalled': ('精灵飞书同步长时间未成功', '检查精灵同步是否卡住或未启动'),
    'notify_self_test': ('告警通道自检', '无需操作'),
}

_SECRET_PATTERNS = (
    re.compile(r't-[A-Za-z0-9_\-]{6,}'),
    re.compile(r'(?i)\b(tenant_access_token|app_secret|authorization|bearer)\b\s*[:=]?\s*[A-Za-z0-9_\-\.]{6,}'),
)


def redact(text, secrets=()):
    """Remove credential material from anything we log, store or return."""
    value = '' if text is None else str(text)
    for secret in secrets:
        if secret:
            value = value.replace(str(secret), '<redacted>')
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub('<redacted>', value)
    return value


def now_iso():
    return dt.datetime.now().astimezone().isoformat(timespec='seconds')


# ------------------------------------------------------------------ credentials

def parse_env_file(path):
    """Read ``KEY=VALUE`` lines; returns {} when the file is missing/unreadable."""
    values = {}
    try:
        text = Path(path).expanduser().read_text(encoding='utf-8')
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[len('export '):].strip()
        key, sep, raw = line.partition('=')
        if not sep:
            continue
        value = raw.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def env_file_path(env_file=None, environ=None):
    environ = os.environ if environ is None else environ
    return Path(env_file or environ.get(ENV_FILE_VAR) or DEFAULT_ENV_FILE).expanduser()


def load_credentials(env_file=None, environ=None, required=True):
    """Return ``{'app_id','app_secret','source'}`` or None.

    Environment variables win over the env file. ``required=False`` returns a
    dict with empty values instead of None (for diagnostics that must not leak).
    """
    environ = os.environ if environ is None else environ
    app_id = (environ.get(APP_ID_VAR) or '').strip()
    app_secret = (environ.get(APP_SECRET_VAR) or '').strip()
    source = 'environment' if (app_id and app_secret) else None
    if not (app_id and app_secret):
        path = env_file_path(env_file, environ)
        values = parse_env_file(path)
        if not app_id:
            app_id = (values.get(APP_ID_VAR) or '').strip()
        if not app_secret:
            app_secret = (values.get(APP_SECRET_VAR) or '').strip()
        if app_id or app_secret:
            source = str(path)
    if not app_id or not app_secret:
        return {} if not required else None
    return {'app_id': app_id, 'app_secret': app_secret, 'source': source or 'unknown'}


# --------------------------------------------------------------------- targets

def targets_path(path=None, environ=None):
    environ = os.environ if environ is None else environ
    return Path(path or environ.get(TARGETS_VAR) or DEFAULT_TARGETS_FILE).expanduser()


def load_targets(path=None, environ=None):
    """Read the target config file; missing/invalid file yields {}."""
    try:
        raw = json.loads(targets_path(path, environ).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def targets_config(targets=None, environ=None):
    """Normalise the ``targets`` argument: mapping, file path, or None → config."""
    if targets is None:
        return load_targets(environ=environ)
    if isinstance(targets, (str, Path)):
        return load_targets(path=targets, environ=environ)
    return dict(targets)


def resolve_target(targets=None, environ=None, override=None):
    """Return ``{'kind','receive_id','receive_id_type'}`` or None.

    Priority: explicit override → env → config file. ``chat_id`` (group) wins
    over ``user_id``/``email`` so one filled field is enough to go live.
    """
    if override:
        return override
    environ = os.environ if environ is None else environ
    config = targets_config(targets, environ)
    candidates = (
        ('chat_id', 'chat_id', environ.get('QIUZHAO_NOTIFY_CHAT_ID') or config.get('chat_id')),
        ('user_id', 'open_id', environ.get('QIUZHAO_NOTIFY_USER_ID') or config.get('user_id')),
        ('email', 'email', environ.get('QIUZHAO_NOTIFY_EMAIL') or config.get('email')),
    )
    for kind, receive_id_type, value in candidates:
        value = (value or '').strip()
        if value:
            return {'kind': kind, 'receive_id': value, 'receive_id_type': receive_id_type}
    return None


# --------------------------------------------------------------------- message

def _scalar(value, limit=160):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace('\n', ' ').strip()
    return text[:limit] + ('…' if len(text) > limit else '')


def flatten_fields(fields, limit=12):
    """Flat ``key=value`` pairs for the 关键数字 line (one nesting level)."""
    pairs = []
    for key in sorted(fields or {}):
        if key in ('kind', 'at', 'channel', 'text', 'action', 'notifier_error'):
            continue
        value = fields[key]
        if isinstance(value, dict):
            for inner in sorted(value):
                if value[inner] in (None, '', [], {}):
                    continue
                pairs.append('%s.%s=%s' % (key, inner, _scalar(value[inner])))
        elif isinstance(value, (list, tuple)):
            if value:
                pairs.append('%s=%s' % (key, _scalar('; '.join(_scalar(item) for item in value[:8]))))
        elif value not in (None, ''):
            pairs.append('%s=%s' % (key, _scalar(value)))
    return pairs[:limit]


def format_message(event, fields=None, text=None, action=None, at=None):
    """Time + event type + key numbers + the one thing 站长 must do."""
    title, default_action = EVENTS.get(event, (event, '查看管线日志确认'))
    pairs = flatten_fields(fields)
    lines = ['【秋招告警】' + title,
             '时间: ' + (at or now_iso()),
             '事件: ' + str(event)]
    if pairs:
        lines.append('关键数字: ' + '; '.join(pairs))
    if text:
        lines.append('详情: ' + _scalar(text, 600))
    lines.append('要站长做什么: ' + (action or default_action))
    return '\n'.join(lines)[:MESSAGE_MAX_CHARS]


# ----------------------------------------------------------------------- http

def _http_json(url, body=None, *, token=None, timeout=10, opener=None, method='POST'):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
    headers = {'Content-Type': 'application/json; charset=utf-8'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = opener or urllib.request.urlopen
    try:
        with opener(request, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:  # platform errors still carry a JSON body
        try:
            return json.loads(error.read().decode('utf-8'))
        except Exception:
            raise RuntimeError('HTTP %s from %s' % (error.code, url.split('?')[0]))


_TOKENS = {}
_TOKEN_LOCK = threading.Lock()
TOKEN_REFRESH_MARGIN = 300


def tenant_token(app_id, app_secret, *, timeout=10, opener=None, force=False):
    """Cached tenant_access_token; refreshed shortly before expiry."""
    monotonic = time.monotonic()
    with _TOKEN_LOCK:
        cached = _TOKENS.get(app_id)
        if cached and not force and cached['expires_at'] - TOKEN_REFRESH_MARGIN > monotonic:
            return cached['token']
    payload = _http_json(TOKEN_URL, {'app_id': app_id, 'app_secret': app_secret},
                         timeout=timeout, opener=opener)
    token = payload.get('tenant_access_token')
    if payload.get('code') != 0 or not token:
        raise RuntimeError('tenant_access_token rejected: code=%s msg=%s'
                           % (payload.get('code'), redact(payload.get('msg'), (app_secret,))[:200]))
    expire = int(payload.get('expire') or 7200)
    with _TOKEN_LOCK:
        _TOKENS[app_id] = {'token': token, 'expires_at': time.monotonic() + expire}
    return token


def api_send(target, message, credentials, *, timeout=10, opener=None):
    """Send one text message through the Open Platform REST API."""
    for force in (False, True):
        token = tenant_token(credentials['app_id'], credentials['app_secret'],
                             timeout=timeout, opener=opener, force=force)
        payload = _http_json(
            MESSAGE_URL + '?receive_id_type=' + target['receive_id_type'],
            {'receive_id': target['receive_id'], 'msg_type': 'text',
             'content': json.dumps({'text': message}, ensure_ascii=False)},
            token=token, timeout=timeout, opener=opener)
        code = payload.get('code')
        if code == 0:
            return (payload.get('data') or {}).get('message_id')
        if force or code not in TOKEN_INVALID_CODES:
            raise RuntimeError('send rejected: code=%s msg=%s'
                               % (code, redact(payload.get('msg'), (credentials['app_secret'],))[:200]))
    raise RuntimeError('send rejected: token refresh did not help')


def api_list_chats(credentials, *, timeout=10, opener=None, page_size=50):
    """Chats the bot itself is a member of (needs ``im:chat:readonly``)."""
    token = tenant_token(credentials['app_id'], credentials['app_secret'],
                         timeout=timeout, opener=opener)
    payload = _http_json(CHAT_LIST_URL + '?page_size=%d' % page_size, None,
                         token=token, timeout=timeout, opener=opener, method='GET')
    if payload.get('code') != 0:
        raise RuntimeError('chat list rejected: code=%s msg=%s'
                           % (payload.get('code'), redact(payload.get('msg'), (credentials['app_secret'],))[:200]))
    items = (payload.get('data') or {}).get('items') or []
    return [{'chat_id': item.get('chat_id'), 'name': item.get('name'),
             'chat_mode': item.get('chat_mode')} for item in items]


# ------------------------------------------------------------------ lark-cli

_CLI_APP_ID = None
_CLI_PROBED = False


def lark_cli_app_id(runner=None, environ=None):
    """App id the local lark-cli is bound to, or None (probe result is cached)."""
    global _CLI_APP_ID, _CLI_PROBED
    if _CLI_PROBED:
        return _CLI_APP_ID
    _CLI_PROBED = True
    if shutil.which('lark-cli') is None:
        return None
    runner = runner or _run_command
    try:
        completed = runner(['lark-cli', 'whoami'], 20, environ)
        payload = json.loads(completed.stdout.decode('utf-8', errors='replace'))
        _CLI_APP_ID = payload.get('appId') or (payload.get('profile') if str(payload.get('profile', '')).startswith('cli_') else None)
    except Exception:
        _CLI_APP_ID = None
    return _CLI_APP_ID


def _run_command(argv, timeout, environ=None):
    return subprocess.run(argv, capture_output=True, timeout=timeout, env=environ)


def lark_cli_send(target, message, *, runner=None, timeout=30, environ=None):
    """Send through lark-cli's ``im +messages-send`` (bot identity)."""
    runner = runner or _run_command
    if target['kind'] == 'chat_id':
        recipient = ['--chat-id', target['receive_id']]
    elif target['kind'] == 'user_id':
        recipient = ['--user-id', target['receive_id']]
    else:
        raise RuntimeError('lark-cli cannot send to %s' % target['kind'])
    completed = runner(['lark-cli', 'im', '+messages-send', '--as', 'bot', '--format', 'json',
                        *recipient, '--text', message], timeout, environ)
    stdout = completed.stdout.decode('utf-8', errors='replace')
    if completed.returncode != 0:
        raise RuntimeError('lark-cli exit=%s stderr=%s'
                           % (completed.returncode, completed.stderr.decode('utf-8', errors='replace')[:300]))
    try:
        payload = json.loads(stdout)
    except ValueError:
        raise RuntimeError('lark-cli returned non-JSON output')
    if payload.get('ok') is not True:
        raise RuntimeError('lark-cli rejected the send')
    return ((payload.get('data') or {}).get('message_id')
            or (payload.get('data') or {}).get('message', {}).get('message_id'))


def choose_transport(preferred='auto', credentials=None, runner=None, environ=None):
    """``lark-cli`` only when it is bound to this bot; otherwise the REST API."""
    environ = os.environ if environ is None else environ
    preferred = (preferred or environ.get(TRANSPORT_VAR) or 'auto').strip().lower()
    if preferred in ('api', 'lark-cli'):
        return preferred
    if credentials and lark_cli_app_id(runner, environ) == credentials.get('app_id'):
        return 'lark-cli'
    return 'api'


# ------------------------------------------------------------------ alert file

def default_alert_path(environ=None):
    environ = os.environ if environ is None else environ
    configured = environ.get(ALERT_PATH_VAR)
    if configured:
        return Path(configured).expanduser()
    data_dir = environ.get('QIUZHAO_DATA_DIR') or (Path(__file__).resolve().parents[1] / 'data')
    return Path(data_dir) / DEFAULT_ALERT_NAME


def write_alert_file(path, record):
    """Append one JSON line; returns the path or None. Never raises."""
    if path is None:
        return None
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n'
        descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, line.encode('utf-8'))
        finally:
            os.close(descriptor)
        return path
    except Exception as error:
        LOG.error('cannot write notify alert file %s: %s', path, type(error).__name__)
        return None


# ---------------------------------------------------------------------- notify

def notify(event, *, fields=None, text=None, action=None, targets=None, env_file=None,
           alert_path=None, transport='auto', timeout=10, retries=1, opener=None,
           runner=None, override_target=None, environ=None):
    """Deliver one alert. Returns a result dict; **never raises**.

    ``result['sent']`` is the truth; ``result['channel']`` is ``feishu`` or
    ``file``; ``result['reason']`` explains a degradation
    (``no_credentials`` / ``no_target`` / ``send_failed`` / ``internal_error``).
    """
    environ = os.environ if environ is None else environ
    event = str(event)
    at = now_iso()
    result = {'event': event, 'at': at, 'sent': False, 'channel': 'file', 'reason': None,
              'attempts': 0, 'transport': None, 'target': None, 'alert_path': None,
              'message_id': None}
    credentials = None
    message = ''
    try:
        if (environ.get(DISABLE_VAR) or '').strip().lower() in ('1', 'true', 'yes', 'on'):
            result['reason'] = 'disabled'
            return result
        credentials = load_credentials(env_file, environ)
        secrets = tuple(value for value in (credentials or {}).values() if isinstance(value, str))
        target = resolve_target(targets, environ=environ, override=override_target)
        message = format_message(event, fields, text=text, action=action, at=at)
        result['target'] = (target or {}).get('kind')
        if target is None:
            return _degrade(result, 'no_target', message, alert_path, environ, fields=fields)
        if credentials is None:
            return _degrade(result, 'no_credentials', message, alert_path, environ, fields=fields)
        transport_name = choose_transport(transport, credentials, runner, environ)
        result['transport'] = transport_name
        last_error = None
        for attempt in range(1, retries + 2):
            result['attempts'] = attempt
            try:
                if transport_name == 'lark-cli':
                    message_id = lark_cli_send(target, message, runner=runner, timeout=timeout, environ=environ)
                else:
                    message_id = api_send(target, message, credentials, timeout=timeout, opener=opener)
                result['message_id'] = message_id
                result.update(sent=True, channel='feishu', reason=None)
                LOG.info('feishu alert sent: event=%s target=%s', event, result['target'])
                return result
            except Exception as error:
                last_error = redact(str(error), secrets)[:300]
                LOG.warning('feishu alert attempt %d/%d failed: %s', attempt, retries + 1, last_error)
        return _degrade(result, 'send_failed', message, alert_path, environ,
                        error=last_error, fields=fields)
    except Exception as error:  # absolute backstop: a notifier must never break a pipeline
        result['reason'] = result.get('reason') or 'internal_error'
        result['error'] = redact(str(error), tuple(value for value in (credentials or {}).values()
                                                  if isinstance(value, str)))[:300]
        try:
            path = write_alert_file(alert_path or default_alert_path(environ),
                                    {'at': at, 'event': event, 'channel': 'file',
                                     'reason': result['reason'], 'message': message,
                                     'fields': fields or {}})
            result['alert_path'] = str(path) if path else None
        except Exception:
            pass
        LOG.error('notifier internal error: %s', result['error'])
        return result


def _degrade(result, reason, message, alert_path, environ, error=None, fields=None):
    result.update(sent=False, channel='file', reason=reason)
    if error:
        result['error'] = error
    path = write_alert_file(alert_path or default_alert_path(environ),
                            {'at': result['at'], 'event': result['event'], 'channel': 'file',
                             'reason': reason, 'error': error, 'message': message,
                             'fields': fields or {}})
    result['alert_path'] = str(path) if path else None
    LOG.warning('feishu alert degraded to file (%s): event=%s alert_path=%s',
                reason, result['event'], result['alert_path'])
    return result


def alert_notifier(event):
    """Callable for ``lark_continuation.record_alert(..., notifier=...)``."""
    payload = dict(event or {})
    kind = payload.pop('kind', 'unknown')
    detail = payload.pop('detail', None)
    payload.pop('at', None)
    payload.pop('channel', None)
    return notify(kind, fields=payload, text=detail)


def default_notifier(environ=None):
    """Process-wide notifier for hook callers, or None when disabled."""
    environ = os.environ if environ is None else environ
    if (environ.get(DISABLE_VAR) or '').strip().lower() in ('1', 'true', 'yes', 'on'):
        return None
    return alert_notifier


def notify_batch(events, *, fallback_path=None, **kwargs):
    """Notify a list of event dicts; degraded ones are appended to ``fallback_path``."""
    results = []
    for event in events:
        payload = dict(event or {})
        kind = payload.pop('kind', 'unknown')
        result = notify(kind, fields=payload.get('fields') or
                        {key: value for key, value in payload.items() if key not in ('text', 'action')},
                        text=payload.get('text'), action=payload.get('action'), **kwargs)
        results.append(result)
        if not result.get('sent') and fallback_path:
            try:
                with Path(fallback_path).open('a', encoding='utf-8') as stream:
                    stream.write((payload.get('text') or format_message(kind, payload)) + '\n')
            except OSError as error:
                LOG.error('cannot append fallback alert: %s', type(error).__name__)
    return results


# ------------------------------------------------------------------------- cli

def _read_jsonl(path):
    events = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def _parse_fields(pairs):
    fields = {}
    for pair in pairs or []:
        key, sep, value = str(pair).partition('=')
        if sep:
            fields[key.strip()] = value
    return fields


def _override_from_args(args):
    if args.chat_id:
        return {'kind': 'chat_id', 'receive_id': args.chat_id, 'receive_id_type': 'chat_id'}
    if args.user_id:
        return {'kind': 'user_id', 'receive_id': args.user_id, 'receive_id_type': 'open_id'}
    if args.email:
        return {'kind': 'email', 'receive_id': args.email, 'receive_id_type': 'email'}
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description='秋招飞书告警通道(cc 机器人)')
    parser.add_argument('--event', default='test', help='事件类型(见 EVENTS)')
    parser.add_argument('--field', action='append', default=[], help='关键数字 KEY=VALUE,可重复')
    parser.add_argument('--text', help='详情一行(可选)')
    parser.add_argument('--action', help='要站长做什么(可选,默认按事件取)')
    parser.add_argument('--targets', type=Path, help='目标配置文件(默认 qiuzhao/data/notify_targets.json)')
    parser.add_argument('--env-file', type=Path, help='凭据 env 文件(默认 ~/.config/qiuzhao-cc-bot.env)')
    parser.add_argument('--alert-path', type=Path, help='降级告警文件(默认 $QIUZHAO_DATA_DIR/notify-alerts.jsonl)')
    parser.add_argument('--transport', default='auto', choices=('auto', 'api', 'lark-cli'))
    parser.add_argument('--timeout', type=float, default=10)
    parser.add_argument('--chat-id', help='本次只发这个群(不写配置)')
    parser.add_argument('--user-id', help='本次只发这个 open_id(不写配置)')
    parser.add_argument('--email', help='本次只发这个邮箱(不写配置)')
    parser.add_argument('--batch-jsonl', type=Path, help='批量:每行一个 {"kind","text","fields"}')
    parser.add_argument('--fallback', type=Path, help='批量:降级事件追加到这个文件(给 AI 留言板兜底)')
    parser.add_argument('--list-chats', action='store_true', help='列出机器人所在群(需要 im:chat:readonly)')
    parser.add_argument('--check', action='store_true', help='只打印凭据/目标/告警文件是否就绪,不发消息')
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    credentials = load_credentials(args.env_file)
    target = resolve_target(args.targets, override=_override_from_args(args))
    alert_path = args.alert_path or default_alert_path()

    if args.check:
        print(json.dumps({
            'credentials': 'present' if credentials else 'missing',
            'credentials_source': (credentials or {}).get('source'),
            'target': ('%s:%s' % (target['kind'], target['receive_id'])) if target else 'missing',
            'targets_file': str(targets_path(args.targets)),
            'env_file': str(env_file_path(args.env_file)),
            'transport': choose_transport(args.transport, credentials),
            'alert_path': str(alert_path),
        }, ensure_ascii=False, indent=2))
        return EXIT_SENT

    if args.list_chats:
        if not credentials:
            print(json.dumps({'ok': False, 'error': 'credentials missing'}, ensure_ascii=False))
            return EXIT_DEGRADED
        try:
            print(json.dumps({'ok': True, 'chats': api_list_chats(credentials, timeout=args.timeout)},
                             ensure_ascii=False, indent=2))
            return EXIT_SENT
        except Exception as error:
            print(json.dumps({'ok': False, 'error': redact(str(error))[:300]}, ensure_ascii=False))
            return EXIT_DEGRADED

    if args.batch_jsonl:
        try:
            events = _read_jsonl(args.batch_jsonl)
        except (OSError, ValueError) as error:
            print(json.dumps({'ok': False, 'error': 'cannot read batch file: %s' % error}, ensure_ascii=False))
            return EXIT_USAGE
        results = notify_batch(events, fallback_path=args.fallback, targets=args.targets,
                               env_file=args.env_file, alert_path=alert_path,
                               transport=args.transport, timeout=args.timeout)
        print(json.dumps({'ok': True, 'sent': sum(1 for r in results if r['sent']),
                          'degraded': sum(1 for r in results if not r['sent']),
                          'results': results}, ensure_ascii=False, indent=2))
        return EXIT_SENT if all(r['sent'] for r in results) else EXIT_DEGRADED

    result = notify(args.event, fields=_parse_fields(args.field), text=args.text, action=args.action,
                    targets=args.targets, env_file=args.env_file, alert_path=alert_path,
                    transport=args.transport, timeout=args.timeout,
                    override_target=_override_from_args(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_SENT if result['sent'] else EXIT_DEGRADED


if __name__ == '__main__':
    sys.exit(main())
