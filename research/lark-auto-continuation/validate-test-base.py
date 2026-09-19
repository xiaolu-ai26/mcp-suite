"""Real end-to-end validation of automatic continuation creation.

Runs against the *test* Base only (task hard constraint: the production Base is
read-only). It cleans the test group's continuation tables, triggers automatic
creation because the base table is within the capacity threshold, checks the
field-by-field 19/19 validation, then writes rows through the same
``+record-batch-create`` path the incremental sync uses. A second run proves
idempotency. Every lark-cli call is counted and timed.

Usage:
    /Users/maxzhl/Projects/mcp-suite/.venv/bin/python \
        research/lark-auto-continuation/validate-test-base.py --run-dir <dir>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from qiuzhao.collector import lark_continuation as C
from qiuzhao.collector import sync_lark_multivalue as S

TEST_BASE = 'ThAxbM3QAazvJLsJfKpcPKOwnyd'
GROUP = '互联网科技岗'


class CountingCli:
    def __init__(self):
        self.calls = []
        self.t0 = None

    def __call__(self, *args):
        started = time.monotonic()
        result = S.cli(*args)
        self.calls.append({'command': args[0], 'sec': round(time.monotonic() - started, 2)})
        return result

    def summary(self):
        buckets = {}
        for call in self.calls:
            bucket = buckets.setdefault(call['command'], {'calls': 0, 'sec': 0.0})
            bucket['calls'] += 1
            bucket['sec'] = round(bucket['sec'] + call['sec'], 2)
        return {'total': len(self.calls), 'by_command': buckets}


def cleanup(cli):
    """Delete only this group's continuation tables on the test Base."""
    tables = cli('+table-list', '--base-token', TEST_BASE, '--format', 'json')['data']['tables']
    plan, problems = C.discover(tables)
    if problems:
        raise SystemExit('test Base has ambiguous table names: ' + json.dumps(problems, ensure_ascii=False))
    removed = []
    for slot in plan[GROUP]:
        if slot['index'] == 0:
            continue
        cli('+table-delete', '--base-token', TEST_BASE, '--table-id', slot['table_id'], '--yes')
        removed.append(slot['name'])
    return removed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--keep', action='store_true', help='do not clean existing continuations first')
    parser.add_argument('--rows', type=int, default=5)
    args = parser.parse_args()
    args.run_dir.mkdir(parents=True, exist_ok=True)
    report = {'base': TEST_BASE, 'group': GROUP, 'run_dir': str(args.run_dir)}

    cli = CountingCli()
    if not args.keep:
        report['cleaned_continuations'] = cleanup(cli)
    state_path = args.run_dir / 'continuation-state.json'
    alert_path = args.run_dir / 'continuation-alerts.jsonl'
    for path in (state_path, alert_path):
        path.unlink(missing_ok=True)

    tables = cli('+table-list', '--base-token', TEST_BASE, '--format', 'json')['data']['tables']
    template = next(t for t in tables if t['name'] == GROUP)
    report['before'] = {'template_table_id': template['id'],
                        'records_count': template['records_count'],
                        'free': C.TABLE_RECORD_LIMIT - template['records_count'],
                        'threshold': C.CAPACITY_THRESHOLD}

    started = time.monotonic()
    result = C.ensure_capacity(cli, TEST_BASE, GROUP, args.rows,
                               state_path=state_path, alert_path=alert_path, poll_timeout=120)
    report['create_seconds'] = round(time.monotonic() - started, 2)
    created = result['created']
    report['created'] = [{key: record.get(key) for key in
                          ('name', 'table_id', 'validated', 'status', 'deleted',
                           'field_count', 'view_order', 'template_table_id')}
                         for record in created]
    if not created:
        raise SystemExit('capacity threshold did not trigger creation: ' + json.dumps(result, default=str))
    report['diff'] = created[0].get('diff')
    report['diff_fatal_count'] = len(C.fatal_diffs(created[0].get('diff') or []))
    report['validation_ok'] = created[0].get('validated') is True and report['diff_fatal_count'] == 0
    report['target_table_id'] = result['table_id']
    report['create_calls'] = cli.summary()

    # Write rows through the exact incremental-sync create path.
    rows = [{'job_id': f'auto-cont-real-{i}', '岗位名称': f'自动续表实测岗位{i}',
             '公司名称': '自动续表实测公司', '招聘单位': '自动续表实测公司',
             '行业': ['互联网/科技'],
             '招聘性质': ['校招'], '岗位大类': ['技术/研发'], '状态': ['unverified'],
             '原链接': f'https://example.com/real/{i}', '投递入口': f'https://example.com/real/apply/{i}',
             '来源': '自动续表实测', '工作地点': ['北京'], '毕业届别': ['2026届'],
             '专业': ['计算机类'], '届别条件说明': '自动续表端到端真实验证行'} for i in range(1, args.rows + 1)]
    write_started = time.monotonic()
    response = cli('+record-batch-create', '--base-token', TEST_BASE,
                   '--table-id', result['table_id'],
                   '--json', json.dumps({'create_records': rows}, ensure_ascii=False))
    record_ids = response.get('data', {}).get('record_id_list', [])
    report['write'] = {'requested': len(rows), 'created': len(record_ids),
                       'seconds': round(time.monotonic() - write_started, 2),
                       'record_ids': record_ids}
    report['write_ok'] = len(record_ids) == len(rows)

    # A second run must not create another table.
    second_started = time.monotonic()
    second = C.ensure_capacity(cli, TEST_BASE, GROUP, args.rows,
                               state_path=state_path, alert_path=alert_path, poll_timeout=120)
    report['idempotent_second_run'] = {'created': len(second['created']),
                                       'target_table_id': second['table_id'],
                                       'seconds': round(time.monotonic() - second_started, 2)}
    report['idempotent_ok'] = second['created'] == []

    after = cli('+table-list', '--base-token', TEST_BASE, '--format', 'json')['data']['tables']
    report['after'] = {t['name']: t['records_count'] for t in after
                       if C.parse_table_name(t['name'])}
    report['calls'] = cli.summary()
    (args.run_dir / 'validation-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in
                      ('validation_ok', 'diff_fatal_count', 'write_ok', 'idempotent_ok',
                       'create_seconds', 'before', 'created', 'after', 'calls')},
                     ensure_ascii=False, indent=2))
    return 0 if report['validation_ok'] and report['write_ok'] and report['idempotent_ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
