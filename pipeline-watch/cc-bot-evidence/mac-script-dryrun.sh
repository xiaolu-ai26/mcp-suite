#!/bin/bash
# Mac 侧新鲜度告警脚本 → cc 机器人通道的离线端到端演练(不联网、不发消息)。
#
# 做法:用一个假的 ssh 顶掉真 ssh,喂两份夹具(服务器 freshness.json + 精灵
# lark-sync/status.json),再用一个空的目标配置让 notifier 必然降级到告警文件,
# 这样既验证了脚本→qiuzhao.notify 的接线与降级兜底,又不会真给站长发消息、
# 也不会上 AI 留言板(HOME 被指到临时目录,post.py 不存在)。
#
# 用法:bash pipeline-watch/cc-bot-evidence/mac-script-dryrun.sh
set -u
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WORK=$(mktemp -d /tmp/ccbot-dryrun.XXXXXX)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/bin" "$WORK/state"

cat > "$WORK/freshness.json" <<'JSON'
{
  "checked_at": "2026-09-20T03:47:00+08:00",
  "status": "lagging+stale",
  "problems": ["stale: data_as_of 2026-09-18 is 40.2h old (> 26h)",
               "lagging: lark synced sha deadbeef != jobs.json sha cafebabe, receipt 8.5h old (> 6h)"],
  "data_as_of": "2026-09-18T11:00:00+08:00",
  "data_age_hours": 40.2,
  "receipt_age_hours": 8.5
}
JSON

cat > "$WORK/lark-sync-status.json" <<'JSON'
{
  "status": "failed",
  "phase": "append",
  "last_success_at": "2026-09-19T07:40:00+08:00",
  "error": "append failed, exit=1; see runs/20260920T061000/append.log"
}
JSON

# 假 ssh:按目标主机返回对应夹具。
cat > "$WORK/bin/ssh" <<SH
#!/bin/bash
for arg in "\$@"; do
  case "\$arg" in
    192.168.31.204) cat "$WORK/lark-sync-status.json"; exit 0 ;;
  esac
done
cat "$WORK/freshness.json"
SH
chmod +x "$WORK/bin/ssh"

cat > "$WORK/targets.json" <<'JSON'
{"version": 1, "chat_id": "", "user_id": "", "email": ""}
JSON

HOME="$WORK" PATH="$WORK/bin:$PATH" \
QIUZHAO_NOTIFY_TARGETS="$WORK/targets.json" \
QIUZHAO_NOTIFY_ALERT_PATH="$WORK/state/notify-alerts.jsonl" \
bash "$ROOT/deploy/freshness_notify_mac.sh"
echo "script_exit=$?"
echo "--- 降级告警文件(应为两条:新鲜度 + 精灵同步失败)"
cat "$WORK/state/notify-alerts.jsonl"
echo "--- 通道日志"
cat "$WORK/Library/Logs/mcp-suite/qiuzhao-notify.log"
