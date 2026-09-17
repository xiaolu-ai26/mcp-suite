#!/bin/bash
# freshness_notify_mac.sh — 秋招管线新鲜度告警(Mac 侧)
# 由 launchd com.maxzhl.qiuzhao-freshness 每小时运行:
#   1) ssh 读服务器 /var/lib/mcp-suite/freshness.json,
#      状态为 stale/lagging/unreachable(含组合)时写一句话摘要到 AI 留言板,正常时不发。
#   2) ssh 读精灵 C:\mcp-suite-collector\data\lark-sync\status.json(精灵不可达时跳过并记录),
#      status==failed,或 status!=success 且距 last_success_at 超过 30 小时时发一句话摘要。
set -u
JSON_TMP=$(mktemp /tmp/qiuzhao-freshness.XXXXXX.json)
SYNC_TMP=$(mktemp /tmp/qiuzhao-lark-sync.XXXXXX.json)
MSG_TMP=$(mktemp /tmp/qiuzhao-freshness.XXXXXX.txt)
trap 'rm -f "$JSON_TMP" "$SYNC_TMP" "$MSG_TMP"' EXIT

ssh -o BatchMode=yes -o ConnectTimeout=10 root@114.215.188.109 \
    'cat /var/lib/mcp-suite/freshness.json' > "$JSON_TMP" 2>/dev/null || exit 0

/usr/bin/python3 - "$JSON_TMP" "$MSG_TMP" <<'PYEOF'
import json
import sys

with open(sys.argv[1], 'r', encoding='utf-8') as fh:
    freshness = json.load(fh)
status = freshness.get('status', 'unknown')
if status == 'ok':
    sys.exit(0)
problems = '; '.join(freshness.get('problems') or ['unknown'])
line = ('【kimi→max】秋招管线新鲜度告警:status=%s; %s(checked_at=%s, 详情见服务器 '
        '/var/lib/mcp-suite/freshness.json)' % (status, problems, freshness.get('checked_at')))
with open(sys.argv[2], 'a', encoding='utf-8') as fh:
    fh.write(line + '\n')
PYEOF

# 精灵飞书同步可见性:不可达只记录不告警(避免与服务器告警混淆,也不重复刷屏)。
JINGLING_SSH=(ssh -i "$HOME/.ssh/id_ed25519_lzh_qiuzhao" -o IdentitiesOnly=yes -o BatchMode=yes \
    -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o HostKeyAlias=192.168.1.52 \
    -l 'LZH\-LZH-' 192.168.31.204)
if "${JINGLING_SSH[@]}" 'type C:\mcp-suite-collector\data\lark-sync\status.json' > "$SYNC_TMP" 2>/dev/null; then
    /usr/bin/python3 - "$SYNC_TMP" "$MSG_TMP" <<'PYEOF'
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
alert = status == 'failed'
if not alert:
    try:
        age_h = (datetime.now(timezone.utc) -
                 datetime.fromisoformat(sync['last_success_at'])).total_seconds() / 3600.0
    except (KeyError, TypeError, ValueError):
        age_h = float('inf')
    alert = age_h > 30
if not alert:
    sys.exit(0)
error = (sync.get('error') or '')[:200]
line = ('【kimi→max】精灵飞书同步告警:status=%s, last_success_at=%s, phase=%s, error=%s'
        '(详情见精灵 C:\\mcp-suite-collector\\data\\lark-sync\\status.json)'
        % (status, sync.get('last_success_at'), sync.get('phase'), error or 'none'))
with open(sys.argv[2], 'a', encoding='utf-8') as fh:
    fh.write(line + '\n')
PYEOF
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') jingling unreachable; lark-sync visibility check skipped" >&2
fi

if [ -s "$MSG_TMP" ]; then
    /usr/bin/python3 "$HOME/Projects/ai-board/post.py" --from kimi --file "$MSG_TMP" || true
fi
