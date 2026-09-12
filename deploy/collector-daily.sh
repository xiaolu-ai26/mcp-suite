#!/usr/bin/env bash
set -uo pipefail
umask 077
cd /opt/mcp-suite
export PYTHONUNBUFFERED=1
exec 9>/var/lib/mcp-suite/collector.lock
if ! flock -n 9; then exit 0; fi

PY=/opt/mcp-suite/.venv/bin/python
LOG=/var/lib/mcp-suite/collector-cron.log
STATUS=/var/lib/mcp-suite/cron-status.json

# Write cron-status.json atomically (temp file + rename).
# Usage: write_status <true|false> <exit_code> <alert> <steps_json>
write_status() {
  "$PY" - "$STATUS" "$1" "$2" "$3" "$4" <<'PYEOF'
import sys, json, datetime, pathlib, os, tempfile
path = pathlib.Path(sys.argv[1])
payload = {
    'success': sys.argv[2] == 'true',
    'completed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'steps': json.loads(sys.argv[5]),
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

RUN_RC=0
AC_RC=0
P1_RC=0
NORM_RC=0

# Source failures remain visible but do not prevent independent sources running.
"$PY" -m qiuzhao.collector.run --output-dir /var/lib/mcp-suite >> "$LOG" 2>&1
RUN_RC=$?
"$PY" -m qiuzhao.collector.auto_collect --skip-basic-collectors >> "$LOG" 2>&1
AC_RC=$?
"$PY" -m qiuzhao.collector.p1_pipeline --data-dir /var/lib/mcp-suite --apply --resume-latest >> "$LOG" 2>&1
P1_RC=$?
"$PY" -m qiuzhao.normalize --path /var/lib/mcp-suite/jobs.json >> "$LOG" 2>&1
NORM_RC=$?

STEPS="{\"collector.run\": ${RUN_RC}, \"auto_collect\": ${AC_RC}, \"p1_pipeline\": ${P1_RC}, \"normalize\": ${NORM_RC}}"
for RC in "$RUN_RC" "$AC_RC" "$P1_RC" "$NORM_RC"; do
  if [ "$RC" -ne 0 ]; then
    write_status false "$RC" "Partial failure; see step exit codes, collector-cron.log and p1-status.json" "$STEPS"
    exit "$RC"
  fi
done
write_status true 0 "" "$STEPS"
exit 0
