"""Server-authority incremental Feishu Base mirror with a persistent success index.

The attested server-published jobs.json snapshot (sha256 receipt from the locked
receiver pull) is the only truth. A persistent index maps job_id to
table/record_id/synced_content_hash/last_applied_version so that:

* a second run over the same snapshot makes zero Base calls (no table-list,
  field-list, auth business read, or record IO) — the local attested hash check
  is independent of Base;
* observation timestamps (reviewed/checked/verified/list_checked/detail_checked)
  never change the business hash and never trigger a Base write;
* only real deltas (new published rows, business field changes, evidence-backed
  lifecycle states) produce point-checked, journaled, batch writes;
* unknown write results stay pending in a durable journal and are reconciled by
  exact job_id point checks, never by blind re-append.

Bootstrap from an existing snapshot backup marks located records as `unknown`
(identity only, no invented synced hash); one controlled point read upgrades
them to known. A projection version mismatch refuses to write (migration gate).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

from qiuzhao import v4_fields as V
from qiuzhao.collector import lark_sync_enrichment as E
from qiuzhao.collector import sync_lark_multivalue as S

INDEX_VERSION = 1
PROJECTION_VERSION = 'server-mirror-v1'
# Evidence 2026-09-14: 互联网科技岗 held 19998 records while 互联网科技岗·续表1 was
# rejected with code 800040832 quota_exceeded during a 50-record create at 19843+n.
TABLE_RECORD_LIMIT = 20000
MACHINE_STATES = {'open', 'expired', 'unverified'}
NOTE_FIELD = E.NOTE_FIELD
BUSINESS_FIELDS = ['岗位名称', '公司名称', '招聘单位', '原链接', '投递入口', '来源',
                   '投递截止', '岗位大类', '招聘性质', '岗位描述', NOTE_FIELD, '状态',
                   *S.TARGETS]
# 笔试要求 4 列默认不启用:生产 Base 还没有这些列,打开前写入会失败。
# 开关:环境变量 QIUSHAO_LARK_WRITTEN_TEST=1(须先在第 4.4 节确认 Base 已建列)。
WRITTEN_TEST_FIELDS = list(E.WRITTEN_TEST_COLUMNS)
WRITTEN_TEST_ENV = 'QIUSHAO_LARK_WRITTEN_TEST'


def written_test_enabled():
    return os.environ.get(WRITTEN_TEST_ENV, '') == '1'


def enabled_business_fields():
    """真正参与读写与内容哈希的字段列表(默认与历史完全一致)。"""
    return [*BUSINESS_FIELDS, *WRITTEN_TEST_FIELDS] if written_test_enabled() else list(BUSINESS_FIELDS)


def content_hash(projection):
    """Order-insensitive canonical hash over the machine-owned field projection.

    Only real Base machine fields are hashed (never the whole source row):
    multi-selects hash as sorted sets, and empty values (None/''/[]) are dropped
    so both sides of a comparison normalize identically.
    """
    normalized = {}
    for name, value in sorted(projection.items()):
        if value is None or value == '' or value == [] or value == {}:
            continue
        if isinstance(value, list):
            normalized[name] = sorted({str(item) for item in value})
        else:
            normalized[name] = str(value)
    payload = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def business_projection(raw):
    """Machine-owned Base field projection of one published row.

    This reuses the exact enrichment functions of the existing sync so the
    mirrored cells equal what the established writers produce; observation
    fields are never part of the projection.
    """
    identity = str(raw.get('id') or '').strip()
    if not identity:
        return None
    projection = {'job_id': identity}
    projection.update(E.business_fields(raw))
    projection.update(S.values_for(raw))
    if written_test_enabled():
        projection.update(E.written_test_fields(raw))
    projection[NOTE_FIELD] = E.qualification_note(raw)
    state = E.source_lifecycle_state(raw)
    if state:
        projection['状态'] = [state]
    return projection


def company_of(raw):
    return (raw.get('p1_company') or raw.get('canonical_company')
            or raw.get('recruitment_unit') or raw.get('company') or '')


def append_row(raw):
    """Full create payload for a row absent from the Base. `复核时间` is a create
    convenience only and is deliberately excluded from the synced content hash."""
    table, industry = E.route(company_of(raw))
    projection = business_projection(raw) or {'job_id': str(raw.get('id') or '').strip()}
    row = dict(projection)
    v, _ = V.convert(raw)
    row.update({'岗位名称': v['job_title'], '公司名称': company_of(raw),
                '招聘单位': raw.get('recruiting_unit_raw') or raw.get('recruitment_unit') or company_of(raw),
                '行业': [industry], '招聘性质': projection.get('招聘性质') or ['未注明'],
                '岗位大类': [v['job_category']],
                '状态': projection.get('状态') or ['unverified'],
                '原链接': raw.get('source_url') or raw.get('detail_url') or '',
                '投递入口': raw.get('application_url') or raw.get('detail_url') or '',
                '复核时间': str(raw.get('reviewed_at') or ''),
                '来源': raw.get('source_name') or (company_of(raw) + '官方招聘') if company_of(raw) else raw.get('source_name') or '',
                NOTE_FIELD: projection.get(NOTE_FIELD, '')})
    if raw.get('deadline'):
        row['投递截止'] = str(raw['deadline'])
    return table, row


def build_desired(rows):
    """{job_id: projection} following the online query's validity rules exactly:
    source/application links required, test records dropped, first occurrence
    wins on duplicate ids, removed rows absent from the published projection."""
    desired = {}
    report = Counter()
    for raw in rows:
        report['rows_total'] += 1
        if not (isinstance(raw, dict) and raw.get('source_url') and raw.get('application_url')):
            report['dropped_invalid'] += 1
            continue
        if V.test_rule(raw):
            report['dropped_test_record'] += 1
            continue
        identity = str(raw.get('id') or '').strip()
        if not identity:
            report['dropped_no_id'] += 1
            continue
        if identity in desired:
            report['duplicate_id_first_wins'] += 1
            continue
        if raw.get('status') == 'removed':
            report['dropped_removed'] += 1
            continue
        projection = business_projection(raw)
        if projection is None:
            report['dropped_no_identity'] += 1
            continue
        desired[identity] = projection
    report['desired'] = len(desired)
    return desired, dict(report)


def empty_index():
    return {'index_version': INDEX_VERSION, 'projection_version': PROJECTION_VERSION,
            'last_applied_version': None, 'records': {}}


def load_index(index_path, allow_projection_migration=False):
    index_path = Path(index_path)
    if not index_path.exists():
        return empty_index()
    index = json.loads(index_path.read_text(encoding='utf-8'))
    if index.get('index_version') != INDEX_VERSION:
        raise ValueError('sync index version migration required: ' + str(index.get('index_version')))
    if index.get('projection_version') != PROJECTION_VERSION and not allow_projection_migration:
        raise ValueError('projection version drift; migration gate closed: '
                         + str(index.get('projection_version')))
    if allow_projection_migration and index.get('projection_version') != PROJECTION_VERSION:
        fresh = empty_index()
        fresh['records'] = index.get('records', {})
        for entry in fresh['records'].values():
            entry['unknown'] = True
            entry.pop('synced_hash', None)
        fresh['last_applied_version'] = None
        return fresh
    index.setdefault('records', {})
    return index


def save_index(index_path, index):
    S.save(Path(index_path), index)


def load_journal(journal_path):
    journal_path = Path(journal_path)
    if not journal_path.exists():
        return {'entries': []}
    journal = json.loads(journal_path.read_text(encoding='utf-8'))
    journal.setdefault('entries', [])
    return journal


def save_journal(journal_path, journal):
    S.save(Path(journal_path), journal)


def pending_entries(journal):
    return [entry for entry in journal['entries'] if entry.get('state') == 'pending']


def add_intent(journal, journal_path, *, kind, table, job_ids, content_hashes, source_version):
    operation_id = hashlib.sha256(json.dumps([source_version, kind, table, sorted(job_ids)],
                                             sort_keys=True).encode()).hexdigest()[:24]
    entry = {'operation_id': operation_id, 'kind': kind, 'table': table,
             'job_ids': sorted(job_ids), 'content_hashes': content_hashes,
             'source_version': source_version, 'state': 'pending',
             'created_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}
    journal['entries'].append(entry)
    save_journal(journal_path, journal)
    return entry


def import_index_from_backup(backup_dir, index_path):
    """One-time bootstrap from an existing verified snapshot backup.

    Those backups carry job_id identity and record location only; the synced
    content hash is genuinely unknown and is marked as such — never filled with
    the desired hash. First mirror run upgrades each entry via one controlled
    point read.
    """
    backup_dir = Path(backup_dir)
    backup = json.loads((backup_dir / 'backup.json').read_text(encoding='utf-8'))
    if backup.get('base') != S.BASE or not S.valid_table_selection(list(backup.get('tables', {}))):
        raise ValueError('backup target mismatch')
    index = load_index(index_path, allow_projection_migration=True)
    imported = 0
    for table, meta in backup['tables'].items():
        records_path = Path(meta['records'])
        if S.digest(records_path) != meta['records_sha256']:
            raise ValueError('backup integrity mismatch: ' + table)
        for record in json.loads(records_path.read_text(encoding='utf-8')):
            identity = record.get('job_id')
            if not identity:
                continue  # anonymous legacy records never get invented identities
            index['records'][str(identity)] = {'table': table, 'record_id': record['record_id'],
                                               'unknown': True}
            imported += 1
    save_index(index_path, index)
    return {'imported_identities': imported, 'unknown': True,
            'projection_version': index['projection_version']}


def plan_delta(index, desired, scope):
    records = index['records']
    plan = {'append': [], 'update': [], 'recheck': [], 'takedown': [], 'noop': 0,
            'absent_partial': []}
    for identity, projection in desired.items():
        entry = records.get(identity)
        wanted = content_hash(projection)
        if entry is None:
            plan['append'].append((identity, projection, wanted))
        elif entry.get('unknown'):
            plan['recheck'].append((identity, projection, wanted))
        elif entry.get('tombstoned'):
            plan['update'].append((identity, projection, wanted))
        elif entry.get('synced_hash') != wanted:
            plan['update'].append((identity, projection, wanted))
        else:
            plan['noop'] += 1
    absent = set(records) - set(desired)
    for identity in sorted(absent):
        entry = records[identity]
        if entry.get('tombstoned'):
            continue  # already reconciled as expired; zero further calls
        if scope == 'complete':
            plan['takedown'].append(identity)
        else:
            plan['absent_partial'].append(identity)
    return plan


class LarkCliTransport:
    """Existing lark-cli protocols only; schema once per table per run, table-list
    at most once per run, and only when appends make capacity routing necessary."""

    def __init__(self, run_dir, cli=None):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.cli = cli or S.cli
        self._schema = {}
        self._counts = None
        self.calls = 0
        self.schema_reads = Counter()

    def _call(self, *args):
        self.calls += 1
        return self.cli(*args)

    def locate(self, job_ids, tag):
        """Exact job_id match across every approved table; ambiguity stays visible."""
        found = {}
        stamp = hashlib.sha256(json.dumps(sorted(job_ids)).encode()).hexdigest()[:10]
        for table in S.TABLES:
            matches = E.read_id_matches(table, list(job_ids),
                                        self.run_dir / f'locate-{tag}-{table}-{stamp}.ndjson')
            for identity, record_id in matches.items():
                found.setdefault(identity, []).append({'table': table, 'record_id': record_id})
        return found

    def read_business(self, table, record_id, identity, tag):
        path = self.run_dir / f'read-{tag}-{record_id}.ndjson'
        args = ['+record-get', '--base-token', S.BASE, '--table-id', table,
                '--record-id', record_id, '--format', 'ndjson', '--output', S.rel(path), '--overwrite']
        for name in ['job_id', *enabled_business_fields()]:
            args += ['--field-id', name]
        response = self._call(*args)
        if response.get('ignored_fields') or response.get('record_not_found'):
            raise ValueError('mirror read incomplete: ' + record_id)
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]
        if len(rows) != 1 or str(rows[0].get('job_id') or '').strip() != identity:
            raise ValueError('mirror identity drift: ' + record_id)
        return rows[0]

    def schema(self, table):
        if table not in self._schema:
            self.schema_reads[table] += 1
            self._schema[table] = {field['name']: field for field in S.full_fields(table)}
        return self._schema[table]

    def table_counts(self):
        if self._counts is None:
            tables = self._call('+table-list', '--base-token', S.BASE, '--format', 'json')['data']['tables']
            self._counts = {table['id']: table.get('records_count') for table in tables}
        return self._counts

    def update_records(self, table, updates, tag):
        body = self.run_dir / f'update-{tag}.json'
        S.save(body, {'update_records': updates})
        response = self._call('+record-batch-update', '--base-token', S.BASE, '--table-id', table,
                              '--json', '@' + S.rel(body))
        S.save(self.run_dir / f'update-response-{tag}.json', response)
        return response

    def create_records(self, table, rows, tag):
        body = self.run_dir / f'create-{tag}.json'
        S.save(body, {'create_records': rows})
        try:
            response = self._call('+record-batch-create', '--base-token', S.BASE, '--table-id', table,
                                  '--json', '@' + S.rel(body))
        except RuntimeError as error:
            if E.quota_rejection(error):
                return {'quota_rejected': True, 'error': str(error)[:500]}
            raise
        S.save(self.run_dir / f'create-response-{tag}.json', response)
        return response


def field_delta(current, desired, schema):
    """Machine-owned whitelist intersected with the live schema; select values
    outside existing options are dropped, never invented; human-only fields
    (备注, 复核时间, attachments...) are never in the whitelist."""
    delta = {}
    for name, value in desired.items():
        if name == 'job_id':
            continue
        definition = schema.get(name)
        if definition is None:
            continue
        if definition.get('type') == 'select':
            options = {option['name'] for option in definition.get('options', [])}
            if not set(value) <= options:
                continue
        if isinstance(value, list):
            if set(current.get(name) or []) != set(value):
                delta[name] = value
        elif str(current.get(name) or '') != str(value):
            delta[name] = value
    return delta


def status_delta(current, desired_state):
    old = current.get('状态') or []
    if any(value not in MACHINE_STATES for value in old):
        return None  # human lifecycle value retained, never overwritten
    return None if old == [desired_state] else {'状态': [desired_state]}


def _advance(index, identity, entry):
    index['records'][identity] = entry


def reconcile_pending(index, journal, journal_path, transport):
    """Confirm or preserve pending intents by exact job_id point checks only."""
    confirmed = 0
    for entry in pending_entries(journal):
        matches = transport.locate(entry['job_ids'], tag='reconcile-' + entry['operation_id'])
        conflicts = {}
        for identity in entry['job_ids']:
            locations = matches.get(identity, [])
            if len(locations) != 1:
                conflicts[identity] = locations
        if conflicts:
            entry['reconcile_conflict'] = conflicts
            continue  # preserved pending; reported, never blind-retried
        unresolved = []
        for identity in entry['job_ids']:
            location = matches[identity][0]
            current = transport.read_business(location['table'], location['record_id'],
                                              identity, tag='reconcile-' + entry['operation_id'])
            actual = content_hash({name: current.get(name) for name in ['job_id', *enabled_business_fields()]
                                   if name in current or name == 'job_id' or current.get(name) is not None})
            wanted = entry['content_hashes'][identity]
            if actual == wanted:
                _advance(index, identity, {'table': location['table'], 'record_id': location['record_id'],
                                           'synced_hash': wanted, 'unknown': False,
                                           'last_applied_version': entry['source_version']})
                entry['state'] = 'confirmed'
                confirmed += 1
            else:
                unresolved.append(identity)
        if unresolved:
            entry['reconcile_content_mismatch'] = unresolved
    save_journal(journal_path, journal)
    return confirmed


def _desired_hash_from_current(current, identity):
    present = {name: current.get(name) for name in ['job_id', *enabled_business_fields()]
               if current.get(name) not in (None, '', [])}
    present['job_id'] = identity
    return content_hash(present)


def run_mirror(source_path, source_sha256, *, index_path, journal_path, run_dir=None,
               scope='complete', transport=None, allow_projection_migration=False):
    """Mirror one attested server snapshot. Returns a receipt; the checkpoint
    (index last_applied_version) advances only when every planned item resolved
    with a confirmed success — prepared writes and unknown results never do."""
    source_path = Path(source_path)
    if S.digest(source_path) != source_sha256:
        raise ValueError('source snapshot does not match the attested sha256')
    index_path = Path(index_path)
    journal_path = Path(journal_path)
    if run_dir is None:
        run_dir = index_path.parent / 'mirror-runs' / dt.datetime.now().strftime('%Y%m%dT%H%M%S%f')
    if transport is None:
        transport = LarkCliTransport(run_dir)
    index = load_index(index_path, allow_projection_migration=allow_projection_migration)
    journal = load_journal(journal_path)

    receipt = {'source_sha256': source_sha256, 'scope': scope,
               'projection_version': index['projection_version'], 'base_calls': 0,
               'appended': 0, 'updated': 0, 'takedown': 0, 'noop': 0,
               'recheck_confirmed': 0, 'reconciled_confirmed': 0,
               'capacity_blocked': {}, 'conflicts': [], 'pending_preserved': 0,
               'checkpoint_advanced': False, 'schema_reads': {}}

    if index['last_applied_version'] == source_sha256 and not pending_entries(journal):
        receipt['status'] = 'unchanged'
        S.save(Path(run_dir) / 'mirror-receipt.json', receipt)
        return receipt

    reconcile_pending(index, journal, journal_path, transport)
    receipt['reconciled_confirmed'] = sum(1 for entry in journal['entries']
                                          if entry.get('state') == 'confirmed')

    rows = V.iter_json_file(source_path)
    desired, report = build_desired(rows)
    receipt['source_report'] = report
    plan = plan_delta(index, desired, scope)
    receipt['planned'] = {'append': len(plan['append']), 'update': len(plan['update']),
                          'recheck': len(plan['recheck']), 'takedown': len(plan['takedown']),
                          'noop': plan['noop'], 'absent_partial': len(plan['absent_partial'])}

    blocked = False
    if plan['absent_partial']:
        # A partial snapshot cannot certify what it does not cover; absence is
        # reported, never actioned, and the checkpoint stays put because this
        # version was not completely reconciled.
        receipt['absent_partial_ids'] = sorted(plan['absent_partial'])
        blocked = True

    # 1) Unknown entries from bootstrap: one controlled point read each.
    for identity, projection, wanted in plan['recheck']:
        entry = index['records'][identity]
        try:
            current = transport.read_business(entry['table'], entry['record_id'], identity,
                                              tag='recheck')
        except ValueError:
            index['records'][identity] = {**entry, 'unknown': True, 'locate_failed': True}
            blocked = True
            receipt['conflicts'].append({'job_id': identity, 'reason': 'index location unreadable'})
            continue
        actual = _desired_hash_from_current(current, identity)
        if actual == wanted:
            _advance(index, identity,
                     {'table': entry['table'], 'record_id': entry['record_id'],
                      'synced_hash': wanted, 'unknown': False,
                      'last_applied_version': source_sha256})
            receipt['recheck_confirmed'] += 1
            receipt['noop'] += 1
        else:
            plan['update'].append((identity, projection, wanted, current))

    # 2) Updates for known records: CAS point read, delta only, journal first.
    by_table = {}
    for item in plan['update']:
        identity, projection, wanted = item[0], item[1], item[2]
        current = item[3] if len(item) > 3 else None
        entry = index['records'][identity]
        if entry.get('tombstoned'):
            entry = {'table': entry['table'], 'record_id': entry['record_id']}
        by_table.setdefault(entry['table'], []).append((identity, projection, wanted, current, entry))
    for table, items in sorted(by_table.items()):
        schema = transport.schema(table)
        batch = []
        for identity, projection, wanted, current, entry in items:
            if current is None:
                current = transport.read_business(table, entry['record_id'], identity, tag='cas')
                actual = _desired_hash_from_current(current, identity)
                if actual == wanted:
                    _advance(index, identity, {'table': table, 'record_id': entry['record_id'],
                                               'synced_hash': wanted, 'unknown': False,
                                               'last_applied_version': source_sha256})
                    receipt['noop'] += 1
                    continue
                # Drift from the synced hash is not blind trust and not an error:
                # recompute the machine-owned delta from the live read. An empty
                # delta just re-baselines the hash; a real delta is written below
                # with the journal/CAS guarantees of any other update.
            delta = field_delta(current, projection, schema)
            human_state = any(value not in MACHINE_STATES
                              for value in (current.get('状态') or []))
            if '状态' in delta and human_state:
                delta.pop('状态')  # human lifecycle values are never overwritten
            if delta:
                batch.append((identity, entry['record_id'], delta, wanted))
            else:
                _advance(index, identity, {'table': table, 'record_id': entry['record_id'],
                                           'synced_hash': wanted, 'unknown': False,
                                           'last_applied_version': source_sha256})
                receipt['noop'] += 1
        for start in range(0, len(batch), 200):
            chunk = batch[start:start + 200]
            intent = add_intent(journal, journal_path, kind='update', table=table,
                                job_ids=[item[0] for item in chunk],
                                content_hashes={item[0]: item[3] for item in chunk},
                                source_version=source_sha256)
            updates = {record_id: delta for _, record_id, delta, _ in chunk}
            try:
                response = transport.update_records(table, updates, tag=intent['operation_id'])
            except Exception as error:
                intent['write_error'] = type(error).__name__ + ': ' + str(error)[:300]
                save_journal(journal_path, journal)
                blocked = True
                continue
            if response.get('data', {}).get('ignored_fields'):
                intent['state'] = 'ignored_fields'
                save_journal(journal_path, journal)
                blocked = True
                continue
            for identity, record_id, _, wanted in chunk:
                _advance(index, identity, {'table': table, 'record_id': record_id,
                                           'synced_hash': wanted, 'unknown': False,
                                           'last_applied_version': source_sha256})
                receipt['updated'] += 1
            intent['state'] = 'confirmed'
            save_journal(journal_path, journal)

    # 3) Evidence-backed takedowns; only a complete snapshot absence justifies
    #    them, and the write is a lifecycle state, never a record delete.
    takedown_by_table = {}
    for identity in plan['takedown']:
        entry = index['records'][identity]
        takedown_by_table.setdefault(entry['table'], []).append((identity, entry))
    for table, items in sorted(takedown_by_table.items()):
        schema = transport.schema(table)
        if '状态' not in schema or schema['状态'].get('type') != 'select':
            raise ValueError('lifecycle status schema drift: ' + table)
        if 'expired' not in {option['name'] for option in schema['状态'].get('options', [])}:
            raise ValueError('expired status option missing: ' + table)
        batch = []
        for identity, entry in items:
            current = transport.read_business(table, entry['record_id'], identity, tag='takedown')
            delta = status_delta(current, 'expired')
            if delta is None:
                if (current.get('状态') or []) == ['expired']:
                    _advance(index, identity, {**entry, 'tombstoned': True, 'synced_hash':
                        content_hash({'job_id': identity, '状态': ['expired']}),
                        'last_applied_version': source_sha256})
                    receipt['noop'] += 1
                else:
                    index['records'][identity] = {**entry, 'unknown': True}
                    blocked = True
                    receipt['conflicts'].append({'job_id': identity,
                                                 'reason': 'human lifecycle value blocks takedown'})
                continue
            batch.append((identity, entry['record_id'], delta))
        for start in range(0, len(batch), 200):
            chunk = batch[start:start + 200]
            intent = add_intent(journal, journal_path, kind='takedown', table=table,
                                job_ids=[item[0] for item in chunk],
                                content_hashes={item[0]: content_hash({'job_id': item[0], '状态': ['expired']})
                                                for item in chunk},
                                source_version=source_sha256)
            updates = {record_id: delta for _, record_id, delta in chunk}
            try:
                response = transport.update_records(table, updates, tag=intent['operation_id'])
            except Exception as error:
                intent['write_error'] = type(error).__name__ + ': ' + str(error)[:300]
                save_journal(journal_path, journal)
                blocked = True
                continue
            if response.get('data', {}).get('ignored_fields'):
                intent['state'] = 'ignored_fields'
                save_journal(journal_path, journal)
                blocked = True
                continue
            for identity, record_id, _ in chunk:
                _advance(index, identity, {'table': table, 'record_id': record_id,
                                           'synced_hash': content_hash({'job_id': identity, '状态': ['expired']}),
                                           'tombstoned': True, 'unknown': False,
                                           'last_applied_version': source_sha256})
                receipt['takedown'] += 1
            intent['state'] = 'confirmed'
            save_journal(journal_path, journal)

    # 4) New published rows: capacity-routed appends; full tables produce a
    #    concrete plan for the publisher instead of writes.
    appends_by_table = {}
    raw_by_identity = {}
    for raw in V.iter_json_file(source_path):
        identity = str(raw.get('id') or '').strip()
        if identity:
            raw_by_identity[identity] = raw
    for identity, projection, wanted in plan['append']:
        raw = raw_by_identity.get(identity)
        if raw is None:
            continue
        table, row = append_row(raw)
        appends_by_table.setdefault(table, []).append((identity, row, wanted))
    if appends_by_table:
        counts = transport.table_counts()
    for table, items in sorted(appends_by_table.items()):
        schema = transport.schema(table)
        available = TABLE_RECORD_LIMIT - (counts.get(table) or 0)
        eligible = items[:max(available, 0)]
        overflow = items[max(available, 0):]
        if overflow:
            receipt['capacity_blocked'][table] = {
                'records_count': counts.get(table), 'limit': TABLE_RECORD_LIMIT,
                'blocked_job_ids': [item[0] for item in overflow],
                'continuation_plan': 'publisher-approved compatible continuation table or '
                                     'approved capacity action required; existing record '
                                     'locations are never moved'}
            blocked = True
        if not eligible:
            continue
        for name in S.TARGETS:
            definition = schema.get(name)
            if not definition or definition.get('type') != 'select' or not definition.get('multiple'):
                raise ValueError('append select schema drift: ' + table + '/' + name)
        for start in range(0, len(eligible), 50):
            chunk = eligible[start:start + 50]
            rows_payload = [{key: value for key, value in row.items()
                             if key == 'job_id' or key in schema} for _, row, _ in chunk]
            # The synced hash is the hash of the exact machine-field payload sent
            # (schema-intersected), never of the whole source row: after a
            # confirmed create, a point read of the record must reproduce it.
            payload_hashes = {identity: content_hash({key: value for key, value in row.items()
                                                      if key == 'job_id' or key in enabled_business_fields()})
                              for (identity, _, _), row in zip(chunk, rows_payload)}
            for row in rows_payload:
                for name in S.TARGETS:
                    options = {option['name'] for option in schema[name].get('options', [])}
                    missing = set(row.get(name) or []) - options
                    if missing:
                        raise ValueError('select option missing for append: ' + table + '/' + name
                                         + ' ' + sorted(missing)[0])
            intent = add_intent(journal, journal_path, kind='append', table=table,
                                job_ids=[item[0] for item in chunk],
                                content_hashes=payload_hashes,
                                source_version=source_sha256)
            try:
                response = transport.create_records(table, rows_payload, tag=intent['operation_id'])
            except Exception as error:
                intent['write_error'] = type(error).__name__ + ': ' + str(error)[:300]
                save_journal(journal_path, journal)
                blocked = True
                continue
            if response.get('quota_rejected'):
                rest = eligible[start:]
                receipt['capacity_blocked'][table] = {
                    'records_count': counts.get(table), 'limit': TABLE_RECORD_LIMIT,
                    'api_error': response.get('error'),
                    'blocked_job_ids': [item[0] for item in rest],
                    'continuation_plan': 'publisher-approved compatible continuation table or '
                                         'approved capacity action required'}
                intent['state'] = 'rejected_capacity'
                save_journal(journal_path, journal)
                blocked = True
                break
            record_ids = response.get('data', {}).get('record_id_list', [])
            if len(record_ids) != len(chunk) or response.get('data', {}).get('ignored_fields'):
                intent['state'] = 'uncertain_result'
                save_journal(journal_path, journal)
                blocked = True
                continue
            for (identity, _, _), record_id in zip(chunk, record_ids):
                _advance(index, identity, {'table': table, 'record_id': record_id,
                                           'synced_hash': payload_hashes[identity], 'unknown': False,
                                           'last_applied_version': source_sha256})
                receipt['appended'] += 1
            intent['state'] = 'confirmed'
            save_journal(journal_path, journal)

    unresolved = len(pending_entries(journal))
    receipt['pending_preserved'] = unresolved
    if not blocked and unresolved == 0:
        index['last_applied_version'] = source_sha256
        receipt['checkpoint_advanced'] = True
        receipt['status'] = 'synced'
    else:
        receipt['status'] = 'partial_pending' if blocked else 'pending_reconciliation'
    save_index(index_path, index)
    receipt['base_calls'] = getattr(transport, 'calls', None)
    receipt['schema_reads'] = dict(getattr(transport, 'schema_reads', {}))
    S.save(Path(run_dir) / 'mirror-receipt.json', receipt)
    return receipt


def enqueue_intent(queue_dir, *, published_path, sha256, published_receipt=None):
    """Hand a successfully published server snapshot to the mirror queue without
    running the mirror; website publication already succeeded at this point."""
    queue_dir = Path(queue_dir)
    queue_dir.mkdir(parents=True, exist_ok=True)
    intent = {'published_path': str(published_path), 'sha256': sha256,
              'enqueued_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
              'publication': published_receipt}
    S.save(queue_dir / 'mirror-intent.json', intent)
    return intent


def expected_deleted_ids(checkpoint_dir):
    """Record IDs whose delete receipt the old writer DID persist in its
    checkpoint. Receipts that were never persisted back are deliberately NOT
    listed here — they are verified live, never replayed."""
    checkpoint_dir = Path(checkpoint_dir)
    deleted = set()
    for path in checkpoint_dir.glob('*.delete.json'):
        receipt = json.loads(path.read_text(encoding='utf-8'))
        if receipt.get('ok') is not True:
            continue
        deleted.update(receipt.get('data', {}).get('record_id_list', []))
    return deleted


def load_reconcile_manifest(checkpoint_dir):
    checkpoint_dir = Path(checkpoint_dir)
    manifest_path = checkpoint_dir / 'RECONCILE_IDS.json'
    by_job = {}
    if manifest_path.exists():
        for item in json.loads(manifest_path.read_text(encoding='utf-8')):
            by_job.setdefault(item['job_id'], set()).add(item['record_id'])
    return by_job


def reconcile_legacy_group(checkpoint_dir, transport):
    """Post-handoff targeted verification of the old writer's final duplicate
    group(s), by exact record IDs only (LEGACY_WRITE_RECONCILE_INPUT policy).

    Read-only: this never deletes, never creates, and never replays an
    un-persisted receipt. A job whose expected deletions all landed resolves to
    its surviving location with an UNKNOWN synced hash — the caller marks the
    index entry accordingly and the normal mirror run re-baselines it through
    one controlled point read. Any deviation is reported and left untouched.
    """
    checkpoint_dir = Path(checkpoint_dir)
    deleted = expected_deleted_ids(checkpoint_dir)
    receipt = {'verified': {}, 'duplicate_remaining': [], 'missing': [],
               'conflicts': [], 'writes': 0}
    for job_id, candidate_ids in sorted(load_reconcile_manifest(checkpoint_dir).items()):
        matches = transport.locate([job_id], tag='legacy-reconcile')
        locations = matches.get(job_id, [])
        remaining = {location['record_id'] for location in locations}
        stray = remaining & deleted
        if stray:
            receipt['duplicate_remaining'].append({'job_id': job_id, 'record_ids': sorted(stray)})
            continue
        if len(locations) > 1:
            receipt['conflicts'].append({'job_id': job_id,
                                         'record_ids': sorted(remaining)})
            continue
        if not locations:
            receipt['missing'].append({'job_id': job_id, 'candidate_ids': sorted(candidate_ids)})
            continue
        survivor = locations[0]
        if survivor['record_id'] in deleted:
            receipt['duplicate_remaining'].append({'job_id': job_id,
                                                   'record_ids': [survivor['record_id']]})
            continue
        receipt['verified'][job_id] = {'table': survivor['table'],
                                       'record_id': survivor['record_id'], 'unknown': True}
    return receipt


def apply_legacy_reconcile(index, checkpoint_dir, transport):
    """Fold verified survivor locations into the index (unknown hashes only)."""
    receipt = reconcile_legacy_group(checkpoint_dir, transport)
    for job_id, location in receipt['verified'].items():
        index['records'][job_id] = {'table': location['table'], 'record_id': location['record_id'],
                                    'unknown': True}
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='attested server snapshot')
    parser.add_argument('--sha256', required=True, help='attested snapshot sha256')
    parser.add_argument('--index', type=Path, required=True, help='persistent sync index')
    parser.add_argument('--journal', type=Path, required=True, help='pending-intent journal')
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--scope', choices=['complete', 'partial'], default='complete')
    parser.add_argument('--import-backup', type=Path, help='one-time index bootstrap from a verified backup')
    parser.add_argument('--allow-projection-migration', action='store_true')
    parser.add_argument('--enqueue-only', action='store_true',
                        help='only write the queue intent; do not contact Base')
    parser.add_argument('--reconcile-checkpoint', type=Path,
                        help='read-only exact-record-ID verification of an old-writer checkpoint')
    parser.add_argument('--queue-dir', type=Path)
    args = parser.parse_args(argv)
    if args.import_backup:
        print(json.dumps(import_index_from_backup(args.import_backup, args.index), ensure_ascii=False))
        return 0
    if args.reconcile_checkpoint:
        with S.sync_lock():
            transport = LarkCliTransport(Path(args.index).parent / 'mirror-runs' / 'legacy-reconcile')
            print(json.dumps(reconcile_legacy_group(args.reconcile_checkpoint, transport), ensure_ascii=False))
        return 0
    if args.enqueue_only:
        print(json.dumps(enqueue_intent(args.queue_dir or Path(args.index).parent / 'mirror-queue',
                                        published_path=args.source, sha256=args.sha256),
                         ensure_ascii=False))
        return 0
    with S.sync_lock():
        receipt = run_mirror(args.source, args.sha256, index_path=args.index, journal_path=args.journal,
                             run_dir=args.run_dir, scope=args.scope,
                             allow_projection_migration=args.allow_projection_migration)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt['status'] in {'synced', 'unchanged'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
