"""Publish candidate batches to production:
merge + dedup -> backup prod -> atomic replace -> restart -> health check.
Usage: publish.sh --batch-prefix candidate_batch_ --dry-run
"""
import argparse, json, subprocess, sys, time
from pathlib import Path
from datetime import datetime, timezone, timedelta

WORK = Path('/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-500-mvp')
CAND_DIR = WORK / 'candidate_batches'
TZ = timezone(timedelta(hours=8))
HOST = 'root@114.215.188.109'


def sh(cmd, input_data=None):
    r = subprocess.run(cmd, shell=isinstance(cmd, str), input=input_data,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print('CMD FAIL:', cmd, '\n', r.stderr[-800:])
        sys.exit(1)
    return r.stdout


def get_prod_jobs():
    out = sh(f'ssh {HOST} "cat /var/lib/mcp-suite/jobs.json"')
    return json.loads(out)


def prod_units(jobs):
    return {j.get('recruitment_unit', '') for j in jobs}


def norm_unit(u):
    import re
    return re.sub(r'[\s（()）]', '', u or '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--batch-prefix', default='candidate_batch_')
    args = ap.parse_args()

    prod = get_prod_jobs()
    seen_detail = {j.get('detail_url') or j.get('source_url') for j in prod}
    seen_apply = {j.get('application_url') for j in prod}
    units = prod_units(prod)
    units_n = {norm_unit(u) for u in units}

    new_jobs, pub_meta = [], []
    skip = {'dup_url': 0, 'dup_unit': 0, 'short_desc': 0}
    for f in sorted(CAND_DIR.glob(f'{args.batch_prefix}*.json')):
        batch = json.loads(f.read_text())
        for j in batch.get('jobs', []):
            if len(j.get('description_raw') or '') < 50:
                skip['short_desc'] += 1
                continue
            if j['source_url'] in seen_detail or j['application_url'] in seen_apply:
                skip['dup_url'] += 1
                continue
            if norm_unit(j['recruitment_unit']) in units_n:
                skip['dup_unit'] += 1
                continue
            seen_detail.add(j['source_url'])
            seen_apply.add(j['application_url'])
            units_n.add(norm_unit(j['recruitment_unit']))
            new_jobs.append(j)

    # group by company
    byco = {}
    for j in new_jobs:
        byco.setdefault(j['recruitment_unit'], []).append(j)
    for co, jobs in byco.items():
        pub_meta.append({'recruitment_unit': co, 'jobs': len(jobs),
                         'source_note': jobs[0].get('source_note'),
                         'kind': (jobs[0].get('source_note') or '')})

    print(f'prod jobs={len(prod)} prod_units={len(units)}')
    print(f'new jobs={len(new_jobs)} new companies={len(byco)} skip={skip}')
    for m in pub_meta[:200]:
        print('  +', m['recruitment_unit'], m['jobs'])
    if args.dry_run or not new_jobs:
        print('dry-run end')
        return

    merged = prod + new_jobs
    tmp_local = WORK / 'state' / 'jobs_merged.json'
    tmp_local.write_text(json.dumps(merged, ensure_ascii=False))

    ts = datetime.now(TZ).strftime('%Y%m%d-%H%M')
    sh(f'ssh {HOST} "mkdir -p /opt/mcp-suite/deploy/backup-{ts} && '
       f'cp /var/lib/mcp-suite/jobs.json /opt/mcp-suite/deploy/backup-{ts}/jobs.json"')
    print(f'backup done: /opt/mcp-suite/deploy/backup-{ts}/jobs.json')

    sh(f'scp {tmp_local} {HOST}:/var/lib/mcp-suite/jobs.json.new')
    sh(f'ssh {HOST} "mv /var/lib/mcp-suite/jobs.json.new /var/lib/mcp-suite/jobs.json && '
       f'systemctl restart mcp-suite.service"')
    time.sleep(3)
    health = sh('curl -s https://savegems.top/qiuzhao/health')
    print('health:', health.strip())

    # verification: optionally query remote count via SSH in subsequent monitoring

    # record published companies
    with open(WORK / 'published_companies.jsonl', 'a') as f:
        for m in pub_meta:
            m['published_at'] = datetime.now(TZ).isoformat(timespec='seconds')
            f.write(json.dumps(m, ensure_ascii=False) + '\n')
    print('published_companies.jsonl updated')


if __name__ == '__main__':
    main()
