#!/bin/bash
# freshness_notify_mac.sh — 秋招管线新鲜度告警(Mac 侧)
# 由 launchd com.maxzhl.qiuzhao-freshness 每小时运行:
#   ssh 读服务器 /var/lib/mcp-suite/freshness.json,
#   状态为 stale/lagging(含组合)时写一句话摘要到 AI 留言板,正常时不发。
set -u
JSON_TMP=$(mktemp /tmp/qiuzhao-freshness.XXXXXX.json)
MSG_TMP=$(mktemp /tmp/qiuzhao-freshness.XXXXXX.txt)
trap 'rm -f "$JSON_TMP" "$MSG_TMP"' EXIT

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
with open(sys.argv[2], 'w', encoding='utf-8') as fh:
    fh.write(line + '\n')
PYEOF

if [ -s "$MSG_TMP" ]; then
    /usr/bin/python3 "$HOME/Projects/ai-board/post.py" --from kimi --file "$MSG_TMP" || true
fi
