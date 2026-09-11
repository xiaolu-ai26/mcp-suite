#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /opt/mcp-suite
export PYTHONUNBUFFERED=1
exec 9>/var/lib/mcp-suite/collector.lock
if ! flock -n 9; then exit 0; fi
# Python collector owns source-level alerts; this wrapper records process failures.
if /opt/mcp-suite/.venv/bin/python -m qiuzhao.collector.run --output-dir /var/lib/mcp-suite >> /var/lib/mcp-suite/collector-cron.log 2>&1; then
  /opt/mcp-suite/.venv/bin/python -c 'import json,datetime,pathlib; pathlib.Path("/var/lib/mcp-suite/cron-status.json").write_text(json.dumps({"success":True,"completed_at":datetime.datetime.now(datetime.timezone.utc).isoformat()}))'
else
  rc=$?
  /opt/mcp-suite/.venv/bin/python - "$rc" <<'PY'
import sys,json,datetime,pathlib
pathlib.Path('/var/lib/mcp-suite/cron-status.json').write_text(json.dumps({'success':False,'exit_code':int(sys.argv[1]),'completed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'alert':'Collector process failed; see collector-cron.log and alerts.json'}))
PY
  exit "$rc"
fi
