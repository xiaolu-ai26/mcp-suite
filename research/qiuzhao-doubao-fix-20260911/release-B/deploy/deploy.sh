#!/usr/bin/env bash
# Project-specific deploy: no shared registry mutation, default dry-run.
set -euo pipefail
cd "$(dirname "$0")/.."
HOST=root@114.215.188.109
BASE_SHA=235b60cf8f3d53cc63edfacb39dc2aee7fe2b0e0e3dd8fd33f1839b25fcb7bca
if [[ "${1:-}" != --apply ]]; then
  cat <<'PLAN'
Dry-run only. --apply requires completed local validation and code review.
Upload core/, qiuzhao Python/source configuration (exclude runtime data), requirements.txt and deploy/ to /opt/mcp-suite.
Preserve /opt/mcp-suite/.venv and python; never use rsync --delete.
First install only: copy private/access.sqlite3 and qiuzhao/data/jobs.json to /var/lib/mcp-suite.
Create restricted mcp-suite user; install mcp-suite.service and collector cron.
Install only extension/savegems.top/mcp-suite-qiuzhao.conf; verify original vhost checksum.
Test/reload Baota nginx; start only mcp-suite.service; verify /qiuzhao/health and /shuju/.
PLAN
  exit 0
fi
for required in core/server.py requirements.txt private/access.sqlite3 qiuzhao/data/jobs.json deploy/collector-daily.sh deploy/mcp-suite-qiuzhao.cron; do
  test -f "$required" || { echo "Missing required artifact: $required" >&2; exit 1; }
done
ssh "$HOST" "set -eu; test \"\$(sha256sum /www/server/panel/vhost/nginx/savegems.top.conf | cut -d' ' -f1)\" = '$BASE_SHA'; test \"\$(df --output=pcent / | tail -1 | tr -dc 0-9)\" -lt 85"
ssh "$HOST" 'set -eu; install -d -m 755 /opt/mcp-suite; install -d -m 700 /var/lib/mcp-suite; if ! id mcp-suite >/dev/null 2>&1; then useradd --system --home-dir /var/lib/mcp-suite --no-create-home --shell /usr/sbin/nologin mcp-suite; fi'
rsync -az --exclude=__pycache__ --exclude='*.pyc' core "$HOST:/opt/mcp-suite/"
rsync -az --exclude=__pycache__ --exclude='*.pyc' --exclude=data --exclude=logs qiuzhao "$HOST:/opt/mcp-suite/"
rsync -az --exclude=private --exclude=remote-latest requirements.txt deploy "$HOST:/opt/mcp-suite/"
# Return only explicit states; SSH failure propagates before any upload.
remote_presence() {
  local result
  result=$(ssh "$HOST" "set -eu; if test -e '$1' || test -L '$1'; then printf present; else printf absent; fi") || return $?
  case "$result" in present|absent) printf '%s' "$result" ;; *) echo "Invalid remote presence response" >&2; return 1 ;; esac
}
install_data_once() {
  local source=$1 destination=$2 remote_tmp
  remote_tmp=$(ssh "$HOST" 'set -eu; umask 077; mktemp /var/lib/mcp-suite/.bootstrap.XXXXXXXX') || return $?
  [[ "$remote_tmp" =~ ^/var/lib/mcp-suite/\.bootstrap\.[A-Za-z0-9]+$ ]] || return 1
  if ! scp -q "$source" "$HOST:$remote_tmp"; then
    ssh "$HOST" "rm -f '$remote_tmp'" || true
    return 1
  fi
  # ln creates the final name atomically and fails if it already exists.
  ssh "$HOST" "set -eu; trap 'rm -f $remote_tmp' EXIT; chmod 600 '$remote_tmp'; ln '$remote_tmp' '$destination'"
}
# SQLite backup provides a consistent snapshot even when a WAL exists.
db_presence=$(remote_presence /var/lib/mcp-suite/access.sqlite3)
if [[ "$db_presence" == absent ]]; then
  snapshot=$(mktemp "${TMPDIR:-/tmp}/mcp-suite-db.XXXXXX")
  trap 'rm -f "$snapshot"' EXIT
  chmod 600 "$snapshot"
  python3 - "$snapshot" <<'PYBACKUP'
import sqlite3, sys
with sqlite3.connect("file:private/access.sqlite3?mode=ro", uri=True) as source:
    with sqlite3.connect(sys.argv[1]) as target:
        source.backup(target)
PYBACKUP
  install_data_once "$snapshot" /var/lib/mcp-suite/access.sqlite3
  rm -f "$snapshot"
  trap - EXIT
fi
jobs_presence=$(remote_presence /var/lib/mcp-suite/jobs.json)
if [[ "$jobs_presence" == absent ]]; then
  install_data_once qiuzhao/data/jobs.json /var/lib/mcp-suite/jobs.json
fi
ssh "$HOST" 'set -eu; uv pip install --python /opt/mcp-suite/.venv/bin/python -r /opt/mcp-suite/requirements.txt; chown -R mcp-suite:mcp-suite /var/lib/mcp-suite; chmod 700 /var/lib/mcp-suite; chmod 600 /var/lib/mcp-suite/access.sqlite3; chmod 755 /opt/mcp-suite/deploy/collector-daily.sh; install -m 644 /opt/mcp-suite/deploy/mcp-suite.service /etc/systemd/system/mcp-suite.service; install -m 644 /opt/mcp-suite/deploy/mcp-suite-qiuzhao.cron /etc/cron.d/mcp-suite-qiuzhao; systemctl daemon-reload; systemctl enable --now mcp-suite.service; systemctl restart mcp-suite.service; for attempt in 1 2 3 4 5 6 7 8 9 10; do if curl --fail -s http://127.0.0.1:8768/health; then break; fi; sleep 1; done; curl --fail -s http://127.0.0.1:8768/health'
ssh "$HOST" 'set -eu; target=/www/server/panel/vhost/nginx/extension/savegems.top/mcp-suite-qiuzhao.conf; if test -f "$target"; then cp -p "$target" /opt/mcp-suite/deploy/nginx-previous.conf; fi; install -m 644 /opt/mcp-suite/deploy/mcp-suite-qiuzhao.conf "$target"; if ! /www/server/nginx/sbin/nginx -t; then if test -f /opt/mcp-suite/deploy/nginx-previous.conf; then cp -p /opt/mcp-suite/deploy/nginx-previous.conf "$target"; else unlink "$target"; fi; exit 1; fi; /www/server/nginx/sbin/nginx -s reload'
ssh "$HOST" "set -eu; test \"\$(sha256sum /www/server/panel/vhost/nginx/savegems.top.conf | cut -d' ' -f1)\" = '$BASE_SHA'; systemctl is-active mcp-suite.service; curl --fail -s https://savegems.top/qiuzhao/health; curl --fail -s -o /dev/null https://savegems.top/shuju/"
