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
NORM_RC=0

# run.py exits 1 when any source alerts, but by then it has finished
# normalizing and atomically written a complete jobs.json; record the exit
# code and continue the chain. auto_collect / normalize failures abort.
"$PY" -m qiuzhao.collector.run --output-dir /var/lib/mcp-suite >> "$LOG" 2>&1
RUN_RC=$?

if "$PY" -m qiuzhao.collector.auto_collect --skip-basic-collectors >> "$LOG" 2>&1; then
  AC_RC=0
else
  AC_RC=$?
  write_status false "$AC_RC" "Step auto_collect failed (exit ${AC_RC}); see collector-cron.log and alerts.json" "{\"collector.run\": ${RUN_RC}, \"auto_collect\": ${AC_RC}}"
  exit "$AC_RC"
fi

if "$PY" -m qiuzhao.normalize --path /var/lib/mcp-suite/jobs.json >> "$LOG" 2>&1; then
  NORM_RC=0
else
  NORM_RC=$?
  write_status false "$NORM_RC" "Step normalize failed (exit ${NORM_RC}); see collector-cron.log" "{\"collector.run\": ${RUN_RC}, \"auto_collect\": ${AC_RC}, \"normalize\": ${NORM_RC}}"
  exit "$NORM_RC"
fi

STEPS="{\"collector.run\": ${RUN_RC}, \"auto_collect\": ${AC_RC}, \"normalize\": ${NORM_RC}}"
if [ "$RUN_RC" -ne 0 ]; then
  write_status false "$RUN_RC" "Partial failure: step collector.run exited ${RUN_RC} (source alerts); auto_collect and normalize completed successfully" "$STEPS"
  exit "$RUN_RC"
fi

write_status true 0 "" "$STEPS"
exit 0
