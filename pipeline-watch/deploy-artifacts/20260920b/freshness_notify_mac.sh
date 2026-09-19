#!/bin/bash
# freshness_notify_mac.sh — 秋招管线新鲜度告警(Mac 侧)
# 由 launchd com.maxzhl.qiuzhao-freshness 每小时运行:
#   1) ssh 读服务器 /var/lib/mcp-suite/freshness.json,
#      状态为 stale/lagging/unreachable(含组合)时告警,正常时不发。
#   2) ssh 读精灵 C:\mcp-suite-collector\data\lark-sync\status.json(精灵不可达时跳过并记录),
#      status==failed,或 status!=success 且距 last_success_at 超过 30 小时时告警。
# 告警出口(2026-09-20 起):先走 cc 机器人飞书消息(qiuzhao.notify,与续表告警同一通道);
# 发不出去时才退回 AI 留言板,保证"要站长看见的告警走飞书消息"这条约定不再靠文件兜底。
set -u
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PY=/usr/bin/python3
if [ -x "$REPO_ROOT/.venv/bin/python" ]; then PY="$REPO_ROOT/.venv/bin/python"; fi
JSON_TMP=$(mktemp /tmp/qiuzhao-freshness.XXXXXX.json)
SYNC_TMP=$(mktemp /tmp/qiuzhao-lark-sync.XXXXXX.json)
MSG_TMP=$(mktemp /tmp/qiuzhao-freshness.XXXXXX.txt)
EVENTS_TMP=$(mktemp /tmp/qiuzhao-notify.XXXXXX.jsonl)
trap 'rm -f "$JSON_TMP" "$SYNC_TMP" "$MSG_TMP" "$EVENTS_TMP"' EXIT

ssh -o BatchMode=yes -o ConnectTimeout=10 root@114.215.188.109 \
    'cat /var/lib/mcp-suite/freshness.json' > "$JSON_TMP" 2>/dev/null || exit 0

"$PY" - "$JSON_TMP" "$EVENTS_TMP" <<'PYEOF'
import json
import sys

with open(sys.argv[1], 'r', encoding='utf-8') as fh:
    freshness = json.load(fh)
status = freshness.get('status', 'unknown')
if status == 'ok':
    sys.exit(0)
problems = freshness.get('problems') or ['unknown']
kinds = sorted({str(problem).split(':', 1)[0] for problem in problems})
kind = 'freshness_' + kinds[0] if len(kinds) == 1 else 'freshness_multi_problem'
line = ('【秋招】管线新鲜度告警:status=%s; %s(checked_at=%s, 详情见服务器 '
        '/var/lib/mcp-suite/freshness.json)' % (status, '; '.join(problems), freshness.get('checked_at')))
event = {'kind': kind, 'text': line, 'fields': {
    'status': status, 'problems': problems, 'checked_at': freshness.get('checked_at'),
    'data_as_of': freshness.get('data_as_of'), 'data_age_hours': freshness.get('data_age_hours'),
    'receipt_age_hours': freshness.get('receipt_age_hours')}}
with open(sys.argv[2], 'a', encoding='utf-8') as fh:
    fh.write(json.dumps(event, ensure_ascii=False) + '\n')
PYEOF

# 精灵飞书同步可见性:不可达只记录不告警(避免与服务器告警混淆,也不重复刷屏)。
JINGLING_SSH=(ssh -i "$HOME/.ssh/id_ed25519_lzh_qiuzhao" -o IdentitiesOnly=yes -o BatchMode=yes \
    -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o HostKeyAlias=192.168.1.52 \
    -l 'LZH\-LZH-' 192.168.31.204)
if "${JINGLING_SSH[@]}" 'type C:\mcp-suite-collector\data\lark-sync\status.json' > "$SYNC_TMP" 2>/dev/null; then
    "$PY" - "$SYNC_TMP" "$EVENTS_TMP" <<'PYEOF'
import json
import sys
from datetime import datetime, timezone

try:
    with open(sys.argv[1], 'r', encoding='utf-8') as fh:
        sync = json.load(fh)
except (ValueError, OSError):
    sys.exit(0)
status = sync.get('status')
if status in ('success', None):
    sys.exit(0)
stalled = False
if status != 'failed':
    try:
        age_h = (datetime.now(timezone.utc) -
                 datetime.fromisoformat(sync['last_success_at'])).total_seconds() / 3600.0
    except (KeyError, TypeError, ValueError):
        age_h = float('inf')
    stalled = age_h > 30
if not (status == 'failed' or stalled):
    sys.exit(0)
error = (sync.get('error') or '')[:200]
kind = 'lark_sync_failed' if status == 'failed' else 'lark_sync_stalled'
line = ('【秋招】精灵飞书同步告警:status=%s, last_success_at=%s, phase=%s, error=%s'
        '(详情见精灵 C:\\mcp-suite-collector\\data\\lark-sync\\status.json)'
        % (status, sync.get('last_success_at'), sync.get('phase'), error or 'none'))
event = {'kind': kind, 'text': line, 'fields': {
    'status': status, 'phase': sync.get('phase'), 'last_success_at': sync.get('last_success_at'),
    'error': error}}
with open(sys.argv[2], 'a', encoding='utf-8') as fh:
    fh.write(json.dumps(event, ensure_ascii=False) + '\n')
PYEOF
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') jingling unreachable; lark-sync visibility check skipped" >&2
fi

# 飞书优先;只有发不出去的事件才追加到 MSG_TMP,退回 AI 留言板。
NOTIFY_LOG="$HOME/Library/Logs/mcp-suite/qiuzhao-notify.log"
mkdir -p "$(dirname "$NOTIFY_LOG")" 2>/dev/null || NOTIFY_LOG=/dev/null
if [ -s "$EVENTS_TMP" ]; then
    ( cd "$REPO_ROOT" && "$PY" -m qiuzhao.notify --batch-jsonl "$EVENTS_TMP" --fallback "$MSG_TMP" ) \
        >> "$NOTIFY_LOG" 2>&1 || true
fi

if [ -s "$MSG_TMP" ]; then
    /usr/bin/python3 "$HOME/Projects/ai-board/post.py" --from kimi --file "$MSG_TMP" || true
fi
