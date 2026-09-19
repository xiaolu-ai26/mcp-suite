"""Fixed-table full-reload Feishu Base mirror for the published Qiuzhao job library.

Why this shape
--------------
The industry tables are shared with paying users, so their links must never
change: ``table_id``/``view_id`` are part of the URL the users hold. The mirror
can therefore not be rebuilt by importing a fresh spreadsheet (that creates a
new table with a new id). Instead every run rebuilds the *records* of the
existing tables in place::

    backup all records -> batch_delete all -> batch_create the new snapshot -> verify

``jobs.json`` as published by the production server is the only truth. The Base
is display-only: nothing is ever read back into the server, no human edit in the
Base is preserved, and no table, field, option or view is ever created, renamed
or deleted by this module. A group of rows that no longer fits its existing
tables is reported as a capacity blocker and left unwritten instead of silently
growing a new table.

Call budget
-----------
lark-cli charges roughly one second of process/auth overhead per invocation, so
what matters is calls, not rows. The ``base +...`` shortcuts cap a create batch
at 200 records, so the reload drives the raw endpoints through ``lark-cli api``
instead and uses the platform maxima: 1000 records per ``batch_create`` and 500
ids per ``batch_delete``. Credentials stay inside lark-cli; this module never
reads, stores or prints a token.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from qiuzhao import v4_fields as V
from qiuzhao.collector import lark_sync_enrichment as E
from qiuzhao.collector import lark_sync_index as L
from qiuzhao.collector import sync_lark_multivalue as S

BASE = S.BASE
STATE_VERSION = 1
RECEIPT_VERSION = 1

CREATE_BATCH_LIMIT = 1000
DELETE_BATCH_LIMIT = 500
# Batches inside one table may overlap. The platform allows 50 calls/s on both
# endpoints, so a few workers stay far below the limit; what it buys is the ~3 s
# of fixed cost each call spends before the server does any real work.
DEFAULT_WORKERS = 3
LIST_PAGE_LIMIT = 2000
NETWORK_RETRY_DELAYS = S.NETWORK_RETRY_DELAYS
RATE_LIMIT_RETRY_DELAYS = (10, 30, 60)
# `1254607 Data not ready, please try again later` is a transient the Base starts
# returning once several create batches land on one table at the same time
# (observed at --workers 6; see RECEIPT-lark-reload.md). It is explicitly
# retryable, and it is NOT the capacity rejection 800040832, which must never be
# retried: that one needs an operator decision, not a retry.
TRANSIENT_CODES = {1254607}
TRANSIENT_HINTS = ('please try again later', 'try again later')

# 行业 -> 目标表基名。组内超过单表上限时依次用 `<基名>·续表N`。
# 没有单独分组的行业(能源/电力、金融、医药/医疗、教育、物流/运输、传媒/广告、
# 消费/零售、农业、房地产、其他)统一进「其他行业岗」,与线上现有分布一致。
GROUP_TABLES = {'互联网/科技': '互联网科技岗', '国企/央企': '国企央企岗',
                '制造/工业': '制造工业岗'}
FALLBACK_TABLE = '其他行业岗'
BASE_TABLE_NAMES = ('互联网科技岗', '国企央企岗', '制造工业岗', FALLBACK_TABLE)

SELECT_FIELDS = ('行业', '岗位大类', '招聘性质', '状态', '截止类型', '专业', '毕业届别', '工作地点')
MULTI_SELECT_FIELDS = ('专业', '毕业届别', '工作地点')
LINK_FIELDS = ('原链接', '投递入口')
# 19 列对外字段里同步必须写得出来的那些;`备注` 是站长人工列,同步永不写。
REQUIRED_FIELDS = ('job_id', '岗位名称', '公司名称', '招聘单位', '行业', '岗位大类', '招聘性质',
                   '状态', '投递截止', '毕业届别', '专业', '工作地点', '原链接', '投递入口',
                   '来源', '届别条件说明', '复核时间')


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def save(path, value):
    S.save(Path(path), value)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def continuation_name(base, index):
    return f'{base}·续表{index}'


# --------------------------------------------------------------------- transport

class Lark:
    """Counted, retried lark-cli transport for one reload run."""

    def __init__(self, workdir, timeout=300):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.records = []
        self.rate_limited = 0
        self.transient = 0
        self._lock = threading.Lock()

    @property
    def count(self):
        return len(self.records)

    @property
    def seconds(self):
        return round(sum(r['sec'] for r in self.records), 2)

    def by_kind(self):
        out = {}
        for record in self.records:
            bucket = out.setdefault(record['kind'], {'calls': 0, 'sec': 0.0})
            bucket['calls'] += 1
            bucket['sec'] = round(bucket['sec'] + record['sec'], 2)
        return out

    @staticmethod
    def _error(proc):
        for text in (proc.stdout, proc.stderr):
            try:
                value = json.loads(text or '')
            except ValueError:
                continue
            if isinstance(value, dict) and isinstance(value.get('error'), dict):
                return value['error']
        return None

    def _record(self, entry):
        with self._lock:
            self.records.append(entry)

    @staticmethod
    def _rate_limited(error):
        code = error.get('code')
        message = str(error.get('message') or '')
        return (error.get('type') == 'rate_limit' or code in {99991400, 1254290, 1254291}
                or 'frequency' in message.lower() or 'too many request' in message.lower())

    @staticmethod
    def _transient(error):
        message = str(error.get('message') or '').lower()
        return (error.get('code') in TRANSIENT_CODES
                or any(hint in message for hint in TRANSIENT_HINTS))

    def _invoke(self, argv, kind, cwd=None):
        env = dict(os.environ, LARKSUITE_CLI_NO_UPDATE_NOTIFIER='1',
                   LARKSUITE_CLI_NO_SKILLS_NOTIFIER='1')
        network_attempt = 0
        limit_attempt = 0
        while True:
            started = time.monotonic()
            timed_out = None
            try:
                proc = subprocess.run([shutil.which('lark-cli') or 'lark-cli', *argv,
                                       '--as', 'user'], capture_output=True, text=True,
                                      encoding='utf-8', env=env, timeout=self.timeout,
                                      cwd=str(cwd or self.workdir))
            except subprocess.TimeoutExpired as error:
                proc, timed_out = None, error
            elapsed = round(time.monotonic() - started, 2)
            if proc is None:
                error = {'type': 'network', 'subtype': 'timeout', 'message': str(timed_out)}
            elif proc.returncode:
                error = self._error(proc) or {'type': 'exit',
                                              'message': (proc.stderr or '')[:2000]}
            else:
                try:
                    result = json.loads(proc.stdout or '')
                except ValueError:
                    error = {'type': 'protocol', 'message': (proc.stdout or '')[:2000]}
                else:
                    if result.get('ok') is not False:
                        self._record({'kind': kind, 'argv': argv[:3], 'sec': elapsed,
                                      'ok': True})
                        return result
                    error = result.get('error') or {'type': 'unknown'}
            self._record({'kind': kind, 'argv': argv[:3], 'sec': elapsed, 'ok': False,
                          'error': json.dumps(error, ensure_ascii=False)[:400]})
            if error.get('type') == 'network' and network_attempt < len(NETWORK_RETRY_DELAYS):
                delay = NETWORK_RETRY_DELAYS[network_attempt]
                network_attempt += 1
                print(json.dumps({'lark_retry': 'network', 'attempt': network_attempt,
                                  'delay_seconds': delay, 'command': kind}, ensure_ascii=False),
                      flush=True)
                time.sleep(delay)
                continue
            if ((self._rate_limited(error) or self._transient(error))
                    and limit_attempt < len(RATE_LIMIT_RETRY_DELAYS)):
                delay = RATE_LIMIT_RETRY_DELAYS[limit_attempt]
                limit_attempt += 1
                with self._lock:
                    if self._rate_limited(error):
                        self.rate_limited += 1
                    else:
                        self.transient += 1
                print(json.dumps({'lark_retry': 'rate_limit' if self._rate_limited(error)
                                  else 'transient', 'attempt': limit_attempt,
                                  'delay_seconds': delay, 'command': kind,
                                  'error': json.dumps(error, ensure_ascii=False)[:200]}),
                      flush=True)
                time.sleep(delay)
                continue
            raise RuntimeError('lark-cli rejected ' + kind + ': '
                               + json.dumps(error, ensure_ascii=False)[:2000])

    def base(self, *args, cwd=None, kind=None):
        return self._invoke(['base', *args], kind or ('base' + str(args[0])), cwd)

    def api(self, method, path, body=None, cwd=None, kind=None):
        argv = ['api', method, path]
        temporary = None
        if body is not None:
            handle, name = tempfile.mkstemp(prefix='body-', suffix='.json',
                                            dir=cwd or self.workdir)
            temporary = Path(name)
            with os.fdopen(handle, 'w', encoding='utf-8') as stream:
                json.dump(body, stream, ensure_ascii=False)
            argv += ['--data', '@' + temporary.name]
        try:
            return self._invoke(argv, kind or ('api ' + method), cwd)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


# ------------------------------------------------------------------- table plan

def discover_tables(tables):
    """{base table name: [table_id, ...]} from the live Base inventory.

    Continuation tables are picked up in numeric order. A missing base table or a
    missing continuation simply means less capacity — never a reason to create one.
    """
    by_name = {t['name']: t['id'] for t in tables}
    plan = {}
    for name in BASE_TABLE_NAMES:
        ids = [by_name[name]] if name in by_name else []
        index = 1
        while continuation_name(name, index) in by_name:
            ids.append(by_name[continuation_name(name, index)])
            index += 1
        plan[name] = ids
    return plan


def plan_placement(grouped, plan, limit):
    """Fill each group's existing tables in order; overflow is blocked, not created.

    Every table the group owns takes part, including a continuation table that
    this snapshot no longer needs: it is reloaded with zero rows so yesterday's
    overflow cannot linger next to a shrunken first table.
    """
    placement, blocked = {}, {}
    for name in BASE_TABLE_NAMES:
        rows = grouped.get(name) or []
        tables = plan.get(name) or []
        capacity = limit * len(tables)
        for slot, table_id in enumerate(tables):
            placement[table_id] = rows[slot * limit:(slot + 1) * limit]
        if len(rows) > capacity:
            blocked[name] = {'rows': len(rows), 'capacity': capacity, 'tables': tables,
                             'overflow': len(rows) - capacity}
    return placement, blocked


# ------------------------------------------------------------------ row mapping

def mirror_industry(raw):
    """(base table name, 行业 cell value, warning kind) for one published row."""
    value = str(raw.get('industry') or '').strip()
    if not value:
        return FALLBACK_TABLE, '其他', 'missing_industry'
    if value in V.INDUSTRIES:
        return GROUP_TABLES.get(value, FALLBACK_TABLE), value, None
    return FALLBACK_TABLE, '其他', 'unknown_industry:' + value


def mirror_row(raw):
    """(base table name, 19-column create payload, warnings).

    The payload is exactly what the established incremental sync writes
    (`lark_sync_index.append_row`), except that the owning table and the `行业`
    cell come from the row's own normalized industry instead of the simplified
    company-name router used for newly discovered records.
    """
    _routed, row = L.append_row(raw)
    table, industry, warning = mirror_industry(raw)
    row['行业'] = [industry]
    warnings = []
    if warning:
        warnings.append({'job_id': row.get('job_id'), 'field': '行业', 'kind': warning})
    return table, row, warnings


def build_snapshot(jobs_path):
    """(grouped rows, build report) for the published snapshot.

    Membership and ordering follow `lark_sync_index.build_desired` exactly (the
    same validity rules that decide what the online query may return), then a
    second pass over the same file materializes each accepted row's create
    payload. The comparison is a hard gate: a divergence means the two passes
    disagree and the run refuses to write.
    """
    desired, report = L.build_desired(V.iter_json_file(jobs_path))
    grouped = {name: [] for name in BASE_TABLE_NAMES}
    warnings = []
    for raw in V.iter_json_file(jobs_path):
        identity = str(raw.get('id') or '').strip()
        if identity not in desired:
            continue
        desired.pop(identity)
        table, row, row_warnings = mirror_row(raw)
        grouped[table].append(row)
        warnings.extend(row_warnings)
    if desired:
        raise RuntimeError('snapshot rebuild diverged from build_desired for '
                           + str(len(desired)) + ' ids')
    report['rows_by_table'] = {name: len(rows) for name, rows in grouped.items()}
    return grouped, report, warnings


# ---------------------------------------------------------------------- schema

def field_options(lark, base, table_id):
    """{'name': {'type','multiple','options'}} with the full option list.

    `+field-list` truncates at 50 options, so any select with
    `remaining_options_count` is paged to completion — otherwise a legal city
    would look like a missing option and get dropped.
    """
    fields = lark.base('+field-list', '--base-token', base, '--table-id', table_id,
                       '--format', 'json')['data']['fields']
    schema = {}
    for field in fields:
        style = field.get('style')
        entry = {'type': field.get('type'), 'field_id': field.get('id'),
                 'multiple': bool(field.get('multiple')),
                 'style': style.get('type') if isinstance(style, dict) else style}
        if field.get('type') == 'select':
            declared = [option['name'] for option in field.get('options') or []]
            total = len(declared) + (field.get('remaining_options_count') or 0)
            if total <= len(declared):
                options = declared
            else:
                # `+field-search-options` paginates over the whole option list, so
                # the truncated 50 from `+field-list` are not a prefix to extend —
                # they are replaced by the paged result, offset from zero.
                options, offset = [], 0
                while len(options) < total:
                    data = lark.base('+field-search-options', '--base-token', base,
                                     '--table-id', table_id, '--field-id', field['id'],
                                     '--limit', '200', '--offset', str(offset),
                                     '--format', 'json')['data']
                    if data.get('total') != total or not data.get('options'):
                        raise RuntimeError('select option pagination stalled: ' + field['name'])
                    options.extend(option['name'] for option in data['options'])
                    if len(options) > total:
                        raise RuntimeError('select option pagination overflow: ' + field['name'])
                    offset = len(options)
            if len(set(options)) != total:
                raise RuntimeError('select option count mismatch: ' + field['name'])
            entry['options'] = set(options)
        schema[field['name']] = entry
    missing = [name for name in REQUIRED_FIELDS if name not in schema]
    if missing:
        raise RuntimeError('schema drift in ' + table_id + ': missing ' + ','.join(missing))
    for name in SELECT_FIELDS:
        if schema[name]['type'] != 'select':
            raise RuntimeError('schema drift in ' + table_id + ': ' + name + ' is not a select')
        if schema[name]['multiple'] != (name in MULTI_SELECT_FIELDS):
            raise RuntimeError('schema drift in ' + table_id + ': ' + name + ' multiple flag')
    return schema


def sanitize(rows, schema, table_id):
    """Keep only the fields and options the target table already declares.

    Nothing is created here. A field the table does not have is dropped (the
    established row builder emits one such field, `岗位描述`, which is not part
    of the 19 mirrored columns), and an option the table does not declare is
    removed from the cell while the row is still written, so a new vocabulary
    value can never make a job silently disappear. Every drop is aggregated into
    an alert instead of being applied quietly.
    """
    dropped_fields, missing_options, truncated = Counter(), Counter(), Counter()
    for row in rows:
        for name in [name for name in row if name not in schema]:
            dropped_fields[name] += 1
            row.pop(name)
        for name in SELECT_FIELDS:
            if name not in row:
                continue
            values = row[name] if isinstance(row[name], list) else [row[name]]
            allowed = schema[name]['options']
            unknown = sorted({str(value) for value in values if value not in allowed})
            kept = [value for value in values if value in allowed]
            if unknown:
                missing_options[(name, tuple(unknown[:3]))] += 1
            if not schema[name]['multiple'] and len(kept) > 1:
                truncated[name] += 1
                kept = kept[:1]
            if kept:
                row[name] = kept
            else:
                row.pop(name)
    alerts = [{'table_id': table_id, 'kind': 'field_not_in_table', 'field': name, 'rows': count}
              for name, count in sorted(dropped_fields.items())]
    alerts += [{'table_id': table_id, 'kind': 'option_missing', 'field': name,
                'values': list(values), 'rows': count}
               for (name, values), count in sorted(missing_options.items())]
    alerts += [{'table_id': table_id, 'kind': 'single_select_truncated', 'field': name,
                'rows': count} for name, count in sorted(truncated.items())]
    return alerts


# ------------------------------------------------------------------- table work

def manifest(result):
    """`+record-list --output` answers with a flat manifest, other commands with
    an {"ok":..,"data":..} envelope; unwrap whichever arrived."""
    data = result.get('data')
    return data if isinstance(data, dict) else result


def backup_rows(lark, base, table_id, run_dir):
    """Full read-only export of one table; the restore source for that table."""
    pages = run_dir / (table_id + '.before.pages')
    pages.mkdir(parents=True, exist_ok=True)
    rows, offset, revision = [], 0, None
    for page in range(1000):
        name = f'{page:05d}.ndjson'
        data = manifest(lark.base('+record-list', '--base-token', base, '--table-id', table_id,
                                  '--format', 'ndjson', '--output', name, '--limit',
                                  str(LIST_PAGE_LIMIT), '--offset', str(offset), '--overwrite',
                                  cwd=pages, kind='backup'))
        if revision is None:
            revision = data.get('rev')
        elif revision != data.get('rev'):
            raise RuntimeError('table changed during backup: ' + table_id)
        path = pages / name
        if path.exists():
            rows.extend(json.loads(line) for line
                        in path.read_text(encoding='utf-8').splitlines() if line.strip())
            path.unlink()
        if not data.get('has_more'):
            break
        next_offset = data.get('next_offset')
        if next_offset is None or next_offset <= offset:
            raise RuntimeError('nonadvancing backup pagination: ' + table_id)
        offset = next_offset
    else:
        raise RuntimeError('backup pagination limit: ' + table_id)
    identities = [row.get('record_id') for row in rows]
    if None in identities or len(set(identities)) != len(identities):
        raise RuntimeError('backup record identity mismatch: ' + table_id)
    return rows, revision


def restore_payload(record):
    """A backup record re-shaped into a create payload.

    Read-back echoes url cells as markdown, so link cells are reduced to their
    target; empty cells are omitted rather than written as blanks.
    """
    fields = {}
    for name, value in record.items():
        if name == 'record_id':
            continue
        if name in LINK_FIELDS:
            value = E.normalize_url_field(value)
        if value is None or value == '' or value == []:
            continue
        fields[name] = value
    return {'fields': fields}


def write_payload(row, schema):
    """One mirror row in the cell format the *raw* record endpoints accept.

    This is deliberately not the `base +record-batch-create` format. That
    shortcut normalises cells before sending, so it accepts `["校招"]` for a
    single-select and a bare url for a url-styled text cell; the raw endpoint
    rejects both with 1254062 SingleSelectFieldConvFail / 1254068
    URLFieldConvFail (reproduced on two independently created tables in the test
    Base). Going through the raw endpoint is what buys the 1000-record batch, so
    the conversion lives here:

    * single-select -> the option name as a plain string
    * multi-select  -> a list of option names (unchanged)
    * url-styled text -> {"link": url, "text": url}, matching the echo the Base
      itself produces on read-back
    """
    fields = {}
    for name, value in row.items():
        spec = schema.get(name)
        if spec is None:
            continue
        scalar = value[0] if isinstance(value, list) and len(value) == 1 else value
        if spec['type'] == 'select' and not spec['multiple']:
            fields[name] = scalar
        elif spec['type'] == 'text' and spec.get('style') == 'url':
            link = str(scalar)
            fields[name] = {'link': link, 'text': link}
        else:
            fields[name] = value
    return fields


def run_batches(work, chunks, workers):
    """Apply one batch function per chunk, overlapping at most `workers` of them.

    Chunks are independent (each carries its own ids or its own records), so
    overlapping only trades wall time for concurrency. The first failure stops
    the run and the caller's restore path re-reads the table, which is what makes
    a half-finished concurrent pass recoverable.
    """
    if workers <= 1 or len(chunks) <= 1:
        return [work(chunk) for chunk in chunks]
    results = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='reload') as pool:
        futures = [pool.submit(work, chunk) for chunk in chunks]
        try:
            for future in futures:
                results.append(future.result())
        except Exception:
            for future in futures:
                future.cancel()
            raise
    return results


def delete_records(lark, base, table_id, record_ids, workers=1):
    """batch_delete at the platform maximum; returns the ids the server confirmed."""

    def batch(chunk):
        response = lark.api('POST',
                            f'/open-apis/bitable/v1/apps/{base}/tables/{table_id}/records/batch_delete',
                            {'records': chunk}, kind='delete')['data']
        confirmed = {item['record_id'] for item in response.get('records') or []
                     if item.get('deleted')}
        missing = [rid for rid in chunk if rid not in confirmed]
        if missing:
            raise RuntimeError('batch_delete did not confirm ' + str(len(missing))
                               + ' records in ' + table_id)
        return chunk

    chunks = [record_ids[start:start + DELETE_BATCH_LIMIT]
              for start in range(0, len(record_ids), DELETE_BATCH_LIMIT)]
    return [rid for chunk in run_batches(batch, chunks, workers) for rid in chunk]


def create_records(lark, base, table_id, rows, schema, workers=1):
    """batch_create at the platform maximum; returns the created record ids."""

    def batch(chunk):
        response = lark.api('POST',
                            f'/open-apis/bitable/v1/apps/{base}/tables/{table_id}/records/batch_create',
                            {'records': [{'fields': write_payload(row, schema)} for row in chunk]},
                            kind='create')['data']
        records = response.get('records') or []
        if len(records) != len(chunk):
            raise RuntimeError('batch_create returned ' + str(len(records)) + ' of '
                               + str(len(chunk)) + ' records in ' + table_id)
        return [record['record_id'] for record in records]

    chunks = [rows[start:start + CREATE_BATCH_LIMIT]
              for start in range(0, len(rows), CREATE_BATCH_LIMIT)]
    return [rid for chunk in run_batches(batch, chunks, workers) for rid in chunk]


def recount(lark, base, table_id):
    """Exact row count by pagination, used only when the cached count disagrees."""
    total, offset = 0, 0
    for _ in range(1000):
        data = manifest(lark.base('+record-list', '--base-token', base, '--table-id', table_id,
                                  '--format', 'ndjson', '--output', 'count.ndjson', '--limit',
                                  str(LIST_PAGE_LIMIT), '--offset', str(offset), '--overwrite',
                                  kind='recount'))
        total += int(data.get('records_count') or 0)
        if not data.get('has_more'):
            return total
        next_offset = data.get('next_offset')
        if next_offset is None or next_offset <= offset:
            raise RuntimeError('nonadvancing recount pagination: ' + table_id)
        offset = next_offset
    raise RuntimeError('recount pagination limit: ' + table_id)


def reload_table(lark, base, table_id, rows, schema, run_dir, expected_after, workers=1):
    """backup -> delete -> create -> verify for one table, with per-table rollback.

    Every failure is contained: the other tables keep reloading, and this table is
    either put back from its own backup or left flagged as partial.
    """
    started = time.monotonic()
    receipt = {'table_id': table_id, 'calls_before': lark.count, 'sec_before': lark.seconds,
               'expected_after': expected_after, 'alerts': [], 'restore': None}
    rows_before, revision = backup_rows(lark, base, table_id, run_dir)
    receipt['records_before'] = len(rows_before)
    receipt['rev'] = revision
    backup_path = run_dir / (table_id + '.before.ndjson')
    with backup_path.open('w', encoding='utf-8') as stream:
        for record in rows_before:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
    receipt['backup_sha256'] = digest(backup_path)
    if not rows and rows_before:
        receipt['emptied'] = True
    created, deleted = [], []
    try:
        deleted = delete_records(lark, base, table_id,
                                 [record['record_id'] for record in rows_before], workers)
        receipt['deleted'] = len(deleted)
        created = create_records(lark, base, table_id, rows, schema, workers)
        receipt['created'] = len(created)
        count = expected_after
        data = manifest(lark.base('+table-list', '--base-token', base, '--format', 'json',
                                  kind='verify'))['tables']
        live = {t['id']: t.get('records_count') for t in data}.get(table_id)
        if live != expected_after:
            count = recount(lark, base, table_id)
            receipt['table_list_count'] = live
        receipt['records_after'] = count
        receipt['verified'] = count == expected_after
        if not receipt['verified']:
            raise RuntimeError('row count mismatch after reload: ' + str(count) + ' != '
                               + str(expected_after))
        receipt['status'] = 'ok'
    except Exception as error:
        receipt['error'] = type(error).__name__ + ': ' + str(error)[:500]
        receipt['status'] = 'failed'
        try:
            # Roll back to the pre-run state exactly: whatever the failed attempt
            # left behind is removed by a fresh read, then the backup is written
            # back. Re-reading (instead of trusting the ids we think we created)
            # is what makes a half-finished delete or create recoverable.
            receipt['restore'] = {'from': receipt['backup_sha256']}
            leftover, _ = backup_rows(lark, base, table_id, run_dir / (table_id + '.restore'))
            if leftover:
                delete_records(lark, base, table_id,
                               [record['record_id'] for record in leftover])
            if rows_before:
                create_records(lark, base, table_id,
                               [restore_payload(record) for record in rows_before], schema)
            restored = recount(lark, base, table_id)
            receipt['restore'].update({'records': restored,
                                       'exact': restored == len(rows_before)})
            if restored != len(rows_before):
                receipt['alerts'].append({'table_id': table_id, 'kind': 'partial_data',
                                          'detail': receipt['error']})
        except Exception as restore_error:
            receipt['restore'] = {'error': type(restore_error).__name__ + ': '
                                  + str(restore_error)[:500],
                                  'from': receipt['backup_sha256']}
            receipt['alerts'].append({'table_id': table_id, 'kind': 'partial_data',
                                      'detail': receipt['error']})
    # `sec` is wall time for this table (what a reader wants); `cli_sec` is the
    # summed duration of its calls, which exceeds wall time once batches overlap.
    receipt['calls'] = lark.count - receipt.pop('calls_before')
    receipt['cli_sec'] = round(lark.seconds - receipt.pop('sec_before'), 2)
    receipt['sec'] = round(time.monotonic() - started, 2)
    return receipt


# ------------------------------------------------------------------------ state

def load_state(path):
    path = Path(path)
    if not path.exists():
        return {'state_version': STATE_VERSION, 'last_success_sha256': None, 'tables': {}}
    state = json.loads(path.read_text(encoding='utf-8'))
    if state.get('state_version') != STATE_VERSION:
        raise ValueError('reload state version migration required: '
                         + str(state.get('state_version')))
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--source-path', type=Path, required=True,
                        help='published jobs.json (the only truth)')
    parser.add_argument('--base-token', default=BASE)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--runs-dir', type=Path, required=True)
    parser.add_argument('--max-rows-per-table', type=int, default=L.TABLE_RECORD_LIMIT)
    parser.add_argument('--table-plan', type=Path,
                        help='optional {"group base name": ["tbl...", ...]} override')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS,
                        help='overlapping delete/create batches inside one table')
    parser.add_argument('--force', action='store_true', help='reload even when the source sha256 is unchanged')
    parser.add_argument('--apply', action='store_true', help='write; without it nothing is mutated')
    args = parser.parse_args(argv)

    started = dt.datetime.now(dt.timezone.utc)
    state_path = args.state_dir / 'reload-state.json'
    # A same-second retry must not collide with the previous run's artifacts.
    stamp = started.strftime('%Y%m%dT%H%M%SZ')
    run_dir = args.runs_dir / stamp
    suffix = 0
    while run_dir.exists():
        suffix += 1
        run_dir = args.runs_dir / f'{stamp}-{suffix}'
    run_dir.mkdir(parents=True, exist_ok=False)
    receipt = {'receipt_version': RECEIPT_VERSION, 'started_at': now(), 'run_dir': str(run_dir),
               'source_path': str(args.source_path), 'base_token': args.base_token,
               'max_rows_per_table': args.max_rows_per_table, 'workers': args.workers,
               'apply': bool(args.apply),
               'base_tables': {}, 'tables': {}, 'alerts': [], 'capacity_blocked': {}}

    def flush():
        save(run_dir / 'receipt.json', receipt)
        save(run_dir / 'calls.json', {'calls': lark.records,
                                      'rate_limited_retries': lark.rate_limited,
                                      'transient_retries': lark.transient} if lark else {})

    lark = None
    try:
        source_sha = digest(args.source_path)
        receipt['source_sha256'] = source_sha
        state = load_state(state_path)
        if state.get('last_success_sha256') == source_sha and not args.force:
            receipt['skipped'] = 'source sha256 unchanged since last successful reload'
            receipt['finished_at'] = now()
            save(run_dir / 'receipt.json', receipt)
            print(json.dumps({'skipped': True, 'source_sha256': source_sha,
                              'reason': receipt['skipped']}, ensure_ascii=False))
            return 0

        lark = Lark(run_dir / 'cli', timeout=300)
        grouped, report, build_warnings = build_snapshot(args.source_path)
        receipt['build'] = report
        receipt['source_alerts'] = build_warnings[:200]
        receipt['source_alert_count'] = len(build_warnings)

        inventory = lark.base('+table-list', '--base-token', args.base_token, '--format', 'json',
                              kind='inventory')['data']['tables']
        if args.table_plan:
            plan = json.loads(Path(args.table_plan).read_text(encoding='utf-8'))
        else:
            plan = discover_tables(inventory)
        receipt['base_tables'] = plan
        placement, blocked = plan_placement(grouped, plan, args.max_rows_per_table)
        receipt['capacity_blocked'] = blocked
        receipt['planned'] = {table_id: len(rows) for table_id, rows in placement.items()}
        receipt['planned_total'] = sum(len(rows) for rows in placement.values())
        for name, detail in blocked.items():
            receipt['alerts'].append({'kind': 'capacity_blocked', 'group': name, **detail})
        flush()
        print(json.dumps({'planned': receipt['planned'], 'capacity_blocked': blocked},
                         ensure_ascii=False), flush=True)

        if not args.apply:
            receipt['dry_run'] = True
            receipt['finished_at'] = now()
            flush()
            return 0

        with S.sync_lock():
            schemas = {}
            for table_id in placement:
                schemas[table_id] = field_options(lark, args.base_token, table_id)
            for table_id, rows in placement.items():
                schema_key = json.dumps({name: sorted(schema.get('options') or [])
                                         for name, schema in schemas[table_id].items()},
                                        ensure_ascii=False, sort_keys=True)
                receipt['tables'].setdefault(table_id, {})['schema_key'] = hashlib.sha256(
                    schema_key.encode()).hexdigest()[:16]
                alerts = sanitize(rows, schemas[table_id], table_id)
                receipt['alerts'].extend(alerts)
                receipt['tables'][table_id]['data_alerts'] = alerts
                flush()
                result = reload_table(lark, args.base_token, table_id, rows,
                                      schemas[table_id], run_dir, len(rows), args.workers)
                result['group'] = next((name for name, ids in plan.items() if table_id in ids), None)
                receipt['alerts'].extend(result.get('alerts') or [])
                receipt['tables'][table_id].update(result)
                flush()
                print(json.dumps({'table_id': table_id, 'status': result['status'],
                                  'records': result.get('records_after'),
                                  'sec': result['sec'], 'calls': result['calls']},
                                 ensure_ascii=False), flush=True)

        failed = [tid for tid, value in receipt['tables'].items() if value.get('status') != 'ok']
        receipt['failed_tables'] = failed
        receipt['success'] = not failed and not blocked
        if failed:
            receipt['alerts'].append({'kind': 'table_failed', 'tables': failed})
        if not failed:
            state['last_success_sha256'] = source_sha
            state['last_success_at'] = now()
            state['tables'] = {tid: {'records': value.get('records_after'),
                                     'backup_sha256': value.get('backup_sha256')}
                               for tid, value in receipt['tables'].items()}
            save(state_path, state)
        receipt['state_saved'] = not failed
    except Exception as error:
        receipt['error'] = type(error).__name__ + ': ' + str(error)[:1000]
        receipt['success'] = False
    finally:
        if lark is not None:
            receipt['calls_total'] = lark.count
            receipt['calls_by_kind'] = lark.by_kind()
            receipt['cli_seconds_total'] = lark.seconds
            receipt['rate_limited_retries'] = lark.rate_limited
            receipt['transient_retries'] = lark.transient
            flush()
        receipt['finished_at'] = now()
        receipt['wall_seconds'] = round((dt.datetime.now(dt.timezone.utc) - started).total_seconds(), 2)
        save(run_dir / 'receipt.json', receipt)

    print(json.dumps({key: receipt.get(key) for key in
                      ('success', 'skipped', 'planned_total', 'calls_total', 'cli_seconds_total',
                       'wall_seconds', 'failed_tables', 'capacity_blocked', 'error')},
                     ensure_ascii=False))
    return 0 if receipt.get('success') or receipt.get('skipped') else 1


if __name__ == '__main__':
    raise SystemExit(main())
