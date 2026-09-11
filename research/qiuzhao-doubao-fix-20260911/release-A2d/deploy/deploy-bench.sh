#!/usr/bin/env bash
# Second product on the same host. Default dry-run; --apply required.
# Hard constraints: never restart or reconfigure mcp-suite.service (recruitment),
# never overwrite /var/lib/mcp-suite/access.sqlite3, never touch other vhost locations.
set -euo pipefail
cd "$(dirname "$0")/.."
HOST=root@114.215.188.109
BASE_SHA=235b60cf8f3d53cc63edfacb39dc2aee7fe2b0e0e3dd8fd33f1839b25fcb7bca
PORT=8769
if [[ "${1:-}" != --apply ]]; then
  cat <<'PLAN'
Dry-run only. --apply requires green pytest, green bench/assert_clean.py and a local e2e run.
Upload core/ (generalised, product selected by MCP_PRODUCT), bench/ Python and static
  (exclude data/, sources/, receipts/), requirements.txt and deploy/ to /opt/mcp-suite.
Never use rsync --delete; never re-run pip (requirements unchanged, venv is shared).
Push bench/data/bench.json to /var/lib/mcp-suite/bench.json atomically on every deploy
  (built offline, never mutated server-side). access.sqlite3 is left exactly as it is.
Install mcp-suite-bench.service on 127.0.0.1:8769; start ONLY that unit.
Install extension/savegems.top/mcp-suite-bench.conf; verify original vhost checksum
  before and after; nginx -t then reload, rolling the file back if the test fails.
Verify: both services active, /bench/health, /qiuzhao/health and /shuju/ all still OK.
PLAN
  exit 0
fi
for required in core/server.py core/store.py bench/tools.py bench/data/bench.json \
                bench/static/index.html bench/static/guide.html bench/static/app.js \
                bench/static/site.css deploy/mcp-suite-bench.service deploy/mcp-suite-bench.conf; do
  test -f "$required" || { echo "Missing required artifact: $required" >&2; exit 1; }
done
ssh "$HOST" "set -eu; test \"\$(sha256sum /www/server/panel/vhost/nginx/savegems.top.conf | cut -d' ' -f1)\" = '$BASE_SHA'; test \"\$(df --output=pcent / | tail -1 | tr -dc 0-9)\" -lt 85; id mcp-suite >/dev/null; systemctl is-active mcp-suite.service"
rsync -az --exclude=__pycache__ --exclude='*.pyc' core "$HOST:/opt/mcp-suite/"
rsync -az --exclude=__pycache__ --exclude='*.pyc' --exclude=data --exclude=sources \
      --exclude=receipts --exclude=PROGRESS.md bench "$HOST:/opt/mcp-suite/"
rsync -az --exclude=private --exclude=remote-latest --exclude=final-online \
      requirements.txt deploy "$HOST:/opt/mcp-suite/"
# Product data is generated offline and is safe to replace; the entitlement database is not.
ssh "$HOST" 'set -eu; test -s /var/lib/mcp-suite/access.sqlite3'
remote_tmp=$(ssh "$HOST" 'set -eu; umask 077; mktemp /var/lib/mcp-suite/.bench.XXXXXXXX')
[[ "$remote_tmp" =~ ^/var/lib/mcp-suite/\.bench\.[A-Za-z0-9]+$ ]] || { echo "bad remote temp path" >&2; exit 1; }
if ! scp -q bench/data/bench.json "$HOST:$remote_tmp"; then
  ssh "$HOST" "rm -f '$remote_tmp'" || true
  exit 1
fi
ssh "$HOST" "set -eu; chown mcp-suite:mcp-suite '$remote_tmp'; chmod 600 '$remote_tmp'; mv -f '$remote_tmp' /var/lib/mcp-suite/bench.json"
ssh "$HOST" "set -eu
  chown -R mcp-suite:mcp-suite /var/lib/mcp-suite/bench.json
  install -m 644 /opt/mcp-suite/deploy/mcp-suite-bench.service /etc/systemd/system/mcp-suite-bench.service
  systemctl daemon-reload
  systemctl enable --now mcp-suite-bench.service
  systemctl restart mcp-suite-bench.service
  for attempt in \$(seq 1 15); do if curl --fail -s http://127.0.0.1:$PORT/health >/dev/null; then break; fi; sleep 1; done
  curl --fail -s http://127.0.0.1:$PORT/health; echo
  systemctl is-active mcp-suite.service"
ssh "$HOST" 'set -eu; target=/www/server/panel/vhost/nginx/extension/savegems.top/mcp-suite-bench.conf; if test -f "$target"; then cp -p "$target" /opt/mcp-suite/deploy/nginx-bench-previous.conf; fi; install -m 644 /opt/mcp-suite/deploy/mcp-suite-bench.conf "$target"; if ! /www/server/nginx/sbin/nginx -t; then if test -f /opt/mcp-suite/deploy/nginx-bench-previous.conf; then cp -p /opt/mcp-suite/deploy/nginx-bench-previous.conf "$target"; else unlink "$target"; fi; exit 1; fi; /www/server/nginx/sbin/nginx -s reload'
ssh "$HOST" "set -eu
  test \"\$(sha256sum /www/server/panel/vhost/nginx/savegems.top.conf | cut -d' ' -f1)\" = '$BASE_SHA'
  systemctl is-active mcp-suite-bench.service
  systemctl is-active mcp-suite.service
  curl --fail -s https://savegems.top/bench/health; echo
  curl --fail -s https://savegems.top/qiuzhao/health; echo
  curl --fail -s -o /dev/null -w 'shuju:%{http_code}\n' https://savegems.top/shuju/
  curl --fail -s -o /dev/null -w 'bench-page:%{http_code}\n' https://savegems.top/bench/
  curl --fail -s -o /dev/null -w 'bench-guide:%{http_code}\n' https://savegems.top/bench/guide"
