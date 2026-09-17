#!/bin/bash
# freshness_watch.sh — 秋招管线新鲜度监控(服务器侧)
# 由 /etc/cron.d/mcp-suite-freshness 以 mcp-suite 用户每 2 小时运行。
# 判定规则:
#   stale       — /health 的 data_as_of 距今 > 26h(采集/推送停了)
#   lagging     — lark-sync-receipt.json 存在,其 synced_source_sha256 与当前
#                 jobs.json sha256 不一致,且 receipt 的 synced_at 距今 > 6h(飞书没跟上)
#   unreachable — /health 连续 3 次(间隔 10s)读不到;保留上次成功的 data_as_of 供参考
# 结果原子写入 /var/lib/mcp-suite/freshness.json。只读 jobs.json,不改任何其他文件。
set -u
export DATA_DIR=/var/lib/mcp-suite
export HEALTH_URL=http://127.0.0.1:8768/health
export STALE_HOURS=26
export LAG_HOURS=6
exec /usr/bin/python3 - <<'PYEOF'
import hashlib
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

data_dir = os.environ['DATA_DIR']
stale_hours = float(os.environ['STALE_HOURS'])
lag_hours = float(os.environ['LAG_HOURS'])
now = time.time()
now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')

result = {
    'checked_at': now_iso,
    'status': 'ok',
    'problems': [],
    'data_as_of': None,
    'data_age_hours': None,
    'jobs_sha256': None,
    'receipt_present': False,
    'receipt': None,
}

# 单次超时不告警:最多 3 次、间隔 10 秒;三次都失败才记 unreachable,
# 并从上一次 freshness.json 里带出最后一次成功读到的 data_as_of。
health = None
last_error = None
for attempt in range(3):
    try:
        with urllib.request.urlopen(os.environ['HEALTH_URL'], timeout=10) as resp:
            health = json.loads(resp.read().decode('utf-8'))
        break
    except Exception as exc:
        last_error = exc
        if attempt < 2:
            time.sleep(10)

if health is not None:
    data_as_of = health.get('data_as_of')
    result['data_as_of'] = data_as_of
    result['jobs'] = health.get('jobs')
    if data_as_of:
        ts = datetime.fromisoformat(data_as_of).timestamp()
        age_h = (now - ts) / 3600.0
        result['data_age_hours'] = round(age_h, 2)
        if age_h > stale_hours:
            result['problems'].append(
                'stale: data_as_of %s is %.1fh old (> %dh)' % (data_as_of, age_h, stale_hours))
    else:
        result['problems'].append('stale: /health returned no data_as_of')
else:
    previous_path = os.path.join(data_dir, 'freshness.json')
    try:
        with open(previous_path, 'r', encoding='utf-8') as fh:
            previous = json.load(fh)
        if previous.get('data_as_of'):
            result['last_known_data_as_of'] = previous['data_as_of']
    except Exception:
        pass
    result['problems'].append(
        'unreachable: cannot read %s after 3 attempts: %s' % (os.environ['HEALTH_URL'], last_error))

jobs_path = os.path.join(data_dir, 'jobs.json')
try:
    h = hashlib.sha256()
    with open(jobs_path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    result['jobs_sha256'] = h.hexdigest()
    result['jobs_mtime'] = datetime.fromtimestamp(
        os.path.getmtime(jobs_path), timezone.utc).astimezone().isoformat(timespec='seconds')
except Exception as exc:
    result['problems'].append('cannot hash jobs.json: %s' % exc)

receipt_path = os.path.join(data_dir, 'lark-sync-receipt.json')
# receipt 格式(同步方成功后写入):
#   {"synced_source_sha256": "...", "synced_at": "<ISO8601>", "tables": {"<表名>": <行数>}}
if os.path.exists(receipt_path):
    result['receipt_present'] = True
    try:
        with open(receipt_path, 'r', encoding='utf-8') as fh:
            receipt = json.load(fh)
        result['receipt'] = receipt
        synced_sha = receipt.get('synced_source_sha256')
        synced_at = receipt.get('synced_at')
        if result['jobs_sha256'] and synced_sha and synced_sha != result['jobs_sha256']:
            try:
                receipt_age_h = (now - datetime.fromisoformat(synced_at).timestamp()) / 3600.0
            except Exception:
                receipt_age_h = float('inf')
            result['receipt_age_hours'] = round(receipt_age_h, 2)
            if receipt_age_h > lag_hours:
                result['problems'].append(
                    'lagging: lark synced sha %s != jobs.json sha %s, receipt %.1fh old (> %dh)'
                    % (str(synced_sha)[:12], result['jobs_sha256'][:12], receipt_age_h, lag_hours))
    except Exception as exc:
        result['problems'].append('cannot parse lark-sync-receipt.json: %s' % exc)

if result['problems']:
    kinds = sorted({p.split(':', 1)[0] for p in result['problems']})
    result['status'] = '+'.join(kinds)

out_path = os.path.join(data_dir, 'freshness.json')
tmp_path = out_path + '.tmp'
with open(tmp_path, 'w', encoding='utf-8') as fh:
    json.dump(result, fh, ensure_ascii=False, indent=2)
    fh.write('\n')
os.replace(tmp_path, out_path)
print(json.dumps({'status': result['status'], 'problems': result['problems']}, ensure_ascii=False))
PYEOF
