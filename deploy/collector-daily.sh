#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /opt/mcp-suite
export PYTHONUNBUFFERED=1
exec 9>/var/lib/mcp-suite/collector.lock
if ! flock -n 9; then exit 0; fi

PY=/opt/mcp-suite/.venv/bin/python
LOG=/var/lib/mcp-suite/collector-cron.log
STATUS=/var/lib/mcp-suite/cron-status.json

# Write cron-status.json atomically (temp file + rename).
# Usage: write_status <true|false> <exit_code> <alert>
write_status() {
  "$PY" - "$STATUS" "$1" "$2" "$3" <<'PYEOF'
import sys, json, datetime, pathlib, os, tempfile
path = pathlib.Path(sys.argv[1])
payload = {
    'success': sys.argv[2] == 'true',
    'completed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
if not payload['success']:
    payload['exit_code'] = int(sys.argv[3])
    payload['alert'] = sys.argv[4]
fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='.cron-status.', suffix='.tmp')
with os.fdopen(fd, 'w') as f:
    f.write(json.dumps(payload))
os.replace(tmp, path)
PYEOF
}

# Run one pipeline step; on failure record status and stop the chain.
run_step() {
  local name="$1"; shift
  if "$@" >> "$LOG" 2>&1; then
    return 0
  else
    local rc=$?
    write_status false "$rc" "Step ${name} failed (exit ${rc}); see collector-cron.log and alerts.json"
    exit "$rc"
  fi
}

# Python collector owns source-level alerts; this wrapper records process failures.
# run.py exits 1 when any source alerts — that is treated as failure by design.
run_step collector.run      "$PY" -m qiuzhao.collector.run --output-dir /var/lib/mcp-suite
run_step auto_collect       "$PY" -m qiuzhao.collector.auto_collect --skip-basic-collectors
run_step normalize          "$PY" -m qiuzhao.normalize --path /var/lib/mcp-suite/jobs.json

write_status true 0 ""
exit 0
