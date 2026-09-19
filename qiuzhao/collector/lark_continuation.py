"""Automatic continuation-table provisioning for the Qiuzhao Feishu Base.

The industry tables hold one group's jobs and each Base table caps at
``TABLE_RECORD_LIMIT`` records (evidence: ``lark_sync_index.py`` returns
``800040832 quota_exceeded`` at 19843+n). Until now a full table was only
reported as ``capacity_blocked`` and a human had to create
``<base>·续表N+1`` by hand and register its id in code (commit 3112763 did
exactly that for 互联网科技岗·续表2).

This module makes that automatic and shared by every writer — the incremental
sync (``lark_sync_enrichment.append_p1`` / ``lark_sync_index.run_mirror``) and
the fixed-table full reload (``lark_reload_mirror``):

* :func:`discover` finds every ``<base>`` / ``<base>·续表N`` table from the
  live Base inventory and sorts by N. The old hardcoded ids in
  ``sync_lark_multivalue`` are only a compatibility reference; a name that
  resolves to a different live id produces a ``legacy_id_drift`` alert instead
  of a silent wrong-table write.
* :func:`ensure_capacity` creates the next continuation when the last table's
  free space drops below ``CAPACITY_THRESHOLD``, then validates it field by
  field against the group's *base* table (count/name/type/multiple/style and
  the full select option set; order is the default grid view order the user
  actually sees). A table that fails validation is deleted again and an alert
  is recorded — no row is ever written into an unvalidated table.
* Creation is idempotent and concurrency safe: a durable state file records
  every created table, and an in-process lock plus a file lock serialise the
  discover → decide → create critical section, so a retry or a concurrent run
  cannot create two tables with the same name.

The module never reads, stores or prints a token; every Base call goes through
the injected ``cli`` callable (``lark-cli`` keeps credentials in the keychain).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from qiuzhao.collector.portable_runtime import fcntl

# Single-table record cap. Evidence 2026-09-14: a table holding 19998 records
# and a continuation rejected a 50-record create at 19843+n with
# `800040832 quota_exceeded` (lark_sync_index.py:36-38, TABLE_RECORD_LIMIT).
TABLE_RECORD_LIMIT = 20000
# Create the next table once the last one is this close to the cap:
# min(1000, 5% of 20000) = 1000. One day's publication is ~1000-2000 new rows,
# so 1000 headroom covers a day's writers and absorbs a stale records_count.
CAPACITY_THRESHOLD = min(1000, TABLE_RECORD_LIMIT // 20)

# Industry base tables, in the order they appear in the Base.
BASE_TABLE_NAMES = ('互联网科技岗', '国企央企岗', '制造工业岗', '其他行业岗')

# Hardcoded ids kept only as compatibility reference for drift alerts. Live
# discovery always wins; the constants are never used as a write target.
LEGACY_TABLE_IDS = {
    '互联网科技岗': 'tblX7rOpjWaRArng',
    '互联网科技岗·续表1': 'tblu0nsYjntEOCGY',
    '互联网科技岗·续表2': 'tblZOCFHBraQThw9',
    '国企央企岗': 'tbl0xkmJUMmLqZ1W',
    '制造工业岗': 'tbl0gDcxEaIOYERw',
    '制造工业岗·续表1': 'tbllqb2R9itUKXdH',
    '制造工业岗·续表2': 'tblffIc9CoTXcRUH',
    '其他行业岗': 'tblcrBAi0ld7uej8',
}

STATE_VERSION = 1
# Sentinel used by ensure_capacity when the caller does not want a state file.
CREATE_ATTEMPTS = 3


class ContinuationError(RuntimeError):
    """Raised when a continuation table cannot be provisioned safely."""


class ContinuationValidationError(ContinuationError):
    """A freshly created table failed field-by-field validation (and was deleted)."""


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_state(path):
    path = Path(path)
    if not path.exists():
        return {'state_version': STATE_VERSION, 'creations': []}
    state = json.loads(path.read_text(encoding='utf-8'))
    if state.get('state_version') != STATE_VERSION:
        raise ContinuationError('continuation state version migration required: '
                                + str(state.get('state_version')))
    state.setdefault('creations', [])
    return state


# ----------------------------------------------------------------- names / plan

def continuation_name(base, index):
    return f'{base}·续表{index}'


def parse_table_name(name, base_names=BASE_TABLE_NAMES):
    """(base, index) for a recognized table name, else None.

    ``index`` is 0 for the base table and N for ``<base>·续表N``. Only exact
    matches count: ``续表0``, ``续表01``, ``<base>2`` or an unrelated name such
    as ``重灌原型-互联网科技岗`` are deliberately skipped.
    """
    if not isinstance(name, str):
        return None
    for base in base_names:
        if name == base:
            return base, 0
        prefix = base + '·续表'
        if name.startswith(prefix):
            suffix = name[len(prefix):]
            if suffix.isdigit() and suffix == str(int(suffix)) and int(suffix) >= 1:
                return base, int(suffix)
    return None


def discover(tables, base_names=BASE_TABLE_NAMES):
    """{base: [slot, ...]} from a live ``+table-list`` inventory, sorted by N.

    Each slot is ``{'index','name','table_id','records_count','rev'}``.
    Returns ``(plan, problems)``; a duplicate name or duplicate N is a problem
    the caller must surface rather than silently picking one table.
    """
    plan = {base: [] for base in base_names}
    seen_names, seen_indices, problems = {}, {}, []
    for table in tables or []:
        name = table.get('name')
        parsed = parse_table_name(name, base_names)
        if parsed is None:
            continue
        base, index = parsed
        if name in seen_names:
            problems.append({'kind': 'duplicate_table_name', 'name': name,
                             'table_ids': [seen_names[name], table.get('id')]})
        seen_names[name] = table.get('id')
        key = (base, index)
        if key in seen_indices:
            problems.append({'kind': 'duplicate_continuation_index', 'base': base,
                             'index': index,
                             'table_ids': [seen_indices[key], table.get('id')]})
        seen_indices[key] = table.get('id')
        plan[base].append({'index': index, 'name': name, 'table_id': table.get('id'),
                           'records_count': table.get('records_count'),
                           'rev': table.get('rev')})
    for base in plan:
        plan[base].sort(key=lambda slot: slot['index'])
    return plan, problems


def legacy_drift(plan):
    """Names whose live id differs from the hardcoded compatibility constant."""
    drift = []
    for slots in plan.values():
        for slot in slots:
            expected = LEGACY_TABLE_IDS.get(slot['name'])
            if expected is not None and expected != slot['table_id']:
                drift.append({'kind': 'legacy_id_drift', 'name': slot['name'],
                              'expected_id': expected, 'live_id': slot['table_id']})
    return drift


# ---------------------------------------------------------------------- schema

def read_fields(cli, base, table_id, pagination_bound=100):
    """Field definitions with the *complete* option list.

    ``+field-list`` truncates select options at 50 and reports the remainder in
    ``remaining_options_count``; such a field is paged to completion with
    ``+field-search-options`` so a legal city (工作地点 has 600+) is never
    mistaken for a missing option. The returned shape matches
    ``sync_lark_multivalue.full_fields`` (``id``/``name``/``type``/``options``
    and no ``remaining_options_count``).
    """
    fields = cli('+field-list', '--base-token', base, '--table-id', table_id,
                 '--format', 'json')['data']['fields']
    for field in fields:
        if field.get('type') != 'select' or not field.get('remaining_options_count'):
            field.pop('remaining_options_count', None)
            continue
        options, offset, total = [], 0, None
        for _ in range(pagination_bound):
            data = cli('+field-search-options', '--base-token', base, '--table-id', table_id,
                       '--field-id', field['id'], '--limit', '200', '--offset', str(offset),
                       '--format', 'json')['data']
            if total is None:
                total = data['total']
            if data['total'] != total or not data['options']:
                raise ContinuationError('select options changed or pagination stalled')
            options.extend(data['options'])
            if len(options) == total:
                break
            if len(options) > total:
                raise ContinuationError('select option pagination count mismatch')
            offset = len(options)
        else:
            raise ContinuationError('select option pagination exceeded bound')
        if len({option['name'] for option in options}) != total:
            raise ContinuationError('duplicate select options across pages')
        field['options'] = options
        field.pop('remaining_options_count', None)
    return fields


def field_options_map(fields):
    out = {}
    for field in fields:
        options = field.get('options') or []
        out[field['name']] = {
            'field_id': field.get('id'),
            'name': field['name'],
            'type': field.get('type'),
            'multiple': bool(field.get('multiple')),
            'style': field.get('style'),
            'description': field.get('description') or '',
            'default_value': field.get('default_value'),
            'options': {option['name']: (option.get('hue'), option.get('lightness'))
                        for option in options},
            'options_order': [option['name'] for option in options],
        }
    return out


def field_write_spec(field):
    """One field in the ``+field-create`` / ``+table-create --fields`` shape."""
    spec = {'name': field['name'], 'type': field['type']}
    if field.get('style') is not None:
        spec['style'] = field['style']
    if field.get('description'):
        spec['description'] = field['description']
    if field.get('type') == 'select':
        spec['multiple'] = bool(field.get('multiple'))
        options = []
        for option in field.get('options') or []:
            item = {'name': option['name']}
            if option.get('hue') is not None:
                item['hue'] = option['hue']
            if option.get('lightness') is not None:
                item['lightness'] = option['lightness']
            options.append(item)
        spec['options'] = options
    if field.get('default_value') is not None:
        spec['default_value'] = field['default_value']
    return spec


def order_fields(fields, order):
    """Template fields in the template's view order, extras appended in read order."""
    by_name = {field['name']: field for field in fields}
    ordered = []
    for name in order or []:
        if name in by_name:
            ordered.append(by_name.pop(name))
    for field in fields:
        if field['name'] in by_name:
            ordered.append(by_name.pop(field['name']))
    return ordered


def schema_diff(template_fields, target_fields, template_order=None, target_order=None):
    """Field-by-field differences between the group base table and a target.

    Fatal kinds (``severity='error'``): field_count, field_missing,
    field_extra, field_type, field_multiple, field_style, options_set,
    field_order. Everything else (description, default_value, option colours,
    option order) is reported as a warning, because the Bitable field-list API
    does not reliably preserve those and the manual 2026-09-17 build recorded
    the same caveat.
    """
    diffs = []
    template, target = field_options_map(template_fields), field_options_map(target_fields)
    if len(template) != len(target):
        diffs.append({'kind': 'field_count', 'severity': 'error',
                      'template': len(template), 'target': len(target)})
    for name in sorted(set(template) - set(target)):
        diffs.append({'kind': 'field_missing', 'severity': 'error', 'field': name})
    for name in sorted(set(target) - set(template)):
        diffs.append({'kind': 'field_extra', 'severity': 'error', 'field': name})
    for name in sorted(set(template) & set(target)):
        left, right = template[name], target[name]
        for key, kind in (('type', 'field_type'), ('multiple', 'field_multiple'),
                          ('style', 'field_style')):
            if left[key] != right[key]:
                diffs.append({'kind': kind, 'severity': 'error', 'field': name,
                              'template': left[key], 'target': right[key]})
        for key, kind in (('description', 'field_description'),
                          ('default_value', 'field_default_value')):
            if left[key] != right[key]:
                diffs.append({'kind': kind, 'severity': 'warning', 'field': name,
                              'template': left[key], 'target': right[key]})
        if left['type'] == 'select':
            missing = sorted(set(left['options']) - set(right['options']))
            extra = sorted(set(right['options']) - set(left['options']))
            if missing or extra:
                diffs.append({'kind': 'options_set', 'severity': 'error', 'field': name,
                              'missing': missing[:20], 'extra': extra[:20],
                              'missing_count': len(missing), 'extra_count': len(extra)})
            else:
                coloured = sorted(name for name in left['options']
                                  if left['options'][name] != right['options'][name])
                if coloured:
                    diffs.append({'kind': 'options_style', 'severity': 'warning',
                                  'field': name, 'options': coloured[:20],
                                  'count': len(coloured)})
                if left['options_order'] != right['options_order']:
                    diffs.append({'kind': 'options_order', 'severity': 'warning', 'field': name})
    if template_order is not None and target_order is not None:
        if list(template_order) != list(target_order):
            diffs.append({'kind': 'field_order', 'severity': 'error',
                          'template': list(template_order), 'target': list(target_order)})
    return diffs


def fatal_diffs(diffs):
    return [diff for diff in diffs if diff.get('severity') == 'error']


def default_view(cli, base, table_id):
    data = cli('+view-list', '--base-token', base, '--table-id', table_id,
               '--format', 'json').get('data') or {}
    views = data.get('views') or []
    return next((view for view in views if view.get('type') == 'grid'),
                views[0] if views else None)


def view_order(cli, base, table_id, view_id=None):
    if view_id is None:
        view = default_view(cli, base, table_id)
        view_id = view.get('id') if view else None
    if view_id is None:
        return None
    data = cli('+view-get-visible-fields', '--base-token', base, '--table-id', table_id,
               '--view-id', view_id, '--format', 'json').get('data') or {}
    return list(data.get('visible_fields') or [])


def wait_fields(cli, base, table_id, expected_names, timeout=60, interval=2):
    """Poll until every expected field is visible; field creation is async."""
    expected = set(expected_names)
    deadline = time.monotonic() + timeout
    while True:
        present = {field['name'] for field in
                   cli('+field-list', '--base-token', base, '--table-id', table_id,
                       '--format', 'json')['data']['fields']}
        if expected <= present:
            return True
        if time.monotonic() >= deadline:
            raise ContinuationError('field creation did not settle for ' + table_id
                                    + '; missing ' + ','.join(sorted(expected - present)))
        time.sleep(interval)


def validate_continuation(cli, base, template_table_id, target_table_id):
    """Compare a continuation against its group base table.

    Returns ``{'diff','fatal','template_order','target_order','field_count'}``.
    """
    template_fields = read_fields(cli, base, template_table_id)
    target_fields = read_fields(cli, base, target_table_id)
    template_view = default_view(cli, base, template_table_id)
    target_view = default_view(cli, base, target_table_id)
    template_order = view_order(cli, base, template_table_id,
                                template_view.get('id') if template_view else None)
    target_order = view_order(cli, base, target_table_id,
                              target_view.get('id') if target_view else None)
    diffs = schema_diff(template_fields, target_fields, template_order, target_order)
    return {'diff': diffs, 'fatal': fatal_diffs(diffs),
            'template_order': template_order, 'target_order': target_order,
            'field_count': {'template': len(template_fields), 'target': len(target_fields)}}


# ------------------------------------------------------------------- alerts

def record_alert(alert_path, event, notifier=None):
    """Append a structured alert to the run's alert file.

    A Feishu-message channel does not exist in this codebase yet, so the
    project-wide convention cannot be satisfied here; the alert is written to
    ``alert_path`` (JSONL) and an optional ``notifier`` callback is invoked if a
    caller ever supplies one. This gap is recorded in the receipt rather than
    inventing a new channel.
    """
    event = {'at': now(), 'channel': 'file' if notifier is None else 'notifier', **event}
    if alert_path is not None:
        path = Path(alert_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')
    if notifier is not None:
        try:
            notifier(event)
        except Exception as error:  # a broken notifier must never block a sync
            event['notifier_error'] = type(error).__name__ + ': ' + str(error)[:200]
    return event


# ---------------------------------------------------------------------- locks

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def _thread_lock(key):
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock
        return lock


@contextmanager
def provision_lock(state_path):
    """In-process + cross-process lock around discover → decide → create.

    The in-process RLock is what makes two threads in one worker safe (Windows
    ``msvcrt.locking`` re-entry raises instead of blocking); the file lock keeps
    two independent workers from racing on the same state file.
    """
    key = str(state_path) if state_path is not None else '__memory__'
    lock = _thread_lock(key)
    lock.acquire()
    handle = None
    try:
        if state_path is not None:
            path = Path(str(state_path) + '.lock')
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.open('a')
            fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        if handle is not None:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            except Exception:
                pass
            handle.close()
        lock.release()


# ---------------------------------------------------------------- inventory

class Inventory:
    """Live view of the industry tables, refreshed before every decision."""

    def __init__(self, cli, base, base_names=BASE_TABLE_NAMES):
        self.cli = cli
        self.base = base
        self.base_names = tuple(base_names)
        self.by_name = {}
        self.plan = {name: [] for name in self.base_names}
        self.alerts = []

    def refresh(self):
        data = self.cli('+table-list', '--base-token', self.base,
                        '--format', 'json')['data']
        tables = data.get('tables') or []
        self.by_name = {table['name']: table for table in tables}
        plan, problems = discover(tables, self.base_names)
        self.plan = plan
        self.alerts = problems + legacy_drift(plan)
        return self.plan

    def last(self, base_name):
        slots = self.plan.get(base_name) or []
        return slots[-1] if slots else None


# -------------------------------------------------------------- create/validate

def create_continuation(cli, base, base_name, index, template_table_id, *,
                        alert_path=None, notifier=None, poll_timeout=60):
    """Create, pin the view order and validate ``<base>·续表index``.

    The 2026-09-17 manual build is replicated here: ``+table-create`` with a
    primary field then one ``+field-create`` array (the CLI creates the array
    sequentially), then ``+view-set-visible-fields`` pins the grid view to the
    template order — the Bitable field-list API does not reliably return fields
    in creation order, so the view is the order a user actually sees and the
    one this module validates.

    On any validation error the freshly created table is deleted and
    :class:`ContinuationValidationError` is raised; nothing is ever written into
    a table that failed validation.
    """
    name = continuation_name(base_name, index)
    template_fields = read_fields(cli, base, template_table_id)
    template_view = default_view(cli, base, template_table_id)
    template_order = view_order(cli, base, template_table_id,
                                template_view.get('id') if template_view else None)
    ordered = order_fields(template_fields, template_order)
    if not ordered:
        raise ContinuationError('template table has no fields: ' + template_table_id)
    payload = [field_write_spec(field) for field in ordered]
    record = {'base_name': base_name, 'index': index, 'name': name,
              'template_table_id': template_table_id, 'created_at': now(),
              'field_count': len(payload), 'validated': False, 'status': 'creating'}
    try:
        response = cli('+table-create', '--base-token', base, '--name', name,
                       '--fields', json.dumps(payload[:1], ensure_ascii=False))
        table = response['data']['table']
        table_id = table['id']
        record['table_id'] = table_id
        views = table.get('views') or []
        view_id = views[0].get('id') if views else None
        if view_id is None:
            view = default_view(cli, base, table_id)
            view_id = view.get('id') if view else None
        record['view_id'] = view_id
        if len(payload) > 1:
            cli('+field-create', '--base-token', base, '--table-id', table_id,
                '--json', json.dumps(payload[1:], ensure_ascii=False))
        wait_fields(cli, base, table_id, [field['name'] for field in ordered],
                    timeout=poll_timeout)
        if template_order:
            if view_id is None:
                raise ContinuationError('created table has no grid view: ' + table_id)
            cli('+view-set-visible-fields', '--base-token', base, '--table-id', table_id,
                '--view-id', view_id, '--json',
                json.dumps({'visible_fields': list(template_order)}, ensure_ascii=False))
        result = validate_continuation(cli, base, template_table_id, table_id)
        record['diff'] = result['diff']
        record['field_count'] = result['field_count']
        record['view_order'] = result['target_order']
        if result['fatal']:
            record['status'] = 'invalid_removed'
            record['fatal'] = result['fatal']
            try:
                cli('+table-delete', '--base-token', base, '--table-id', table_id, '--yes')
                record['deleted'] = True
            except Exception as error:
                record['deleted'] = False
                record['delete_error'] = type(error).__name__ + ': ' + str(error)[:300]
            record_alert(alert_path, {'kind': 'continuation_validation_failed', **record},
                         notifier)
            raise ContinuationValidationError(
                'continuation validation failed for ' + name + ': '
                + json.dumps(result['fatal'], ensure_ascii=False)[:800])
        record['validated'] = True
        record['status'] = 'active'
        record_alert(alert_path, {'kind': 'continuation_created', **record}, notifier)
        return record
    except ContinuationValidationError:
        raise
    except Exception as error:
        record['status'] = 'failed'
        record['error'] = type(error).__name__ + ': ' + str(error)[:500]
        record_alert(alert_path, {'kind': 'continuation_create_failed', **record}, notifier)
        # Best effort: never leave a half-built table behind if it is identifiable.
        if record.get('table_id'):
            try:
                cli('+table-delete', '--base-token', base, '--table-id',
                    record['table_id'], '--yes')
                record['deleted'] = True
            except Exception:
                record['deleted'] = False
        raise ContinuationError('continuation creation failed for ' + name + ': '
                                + str(error)[:500]) from error


def _provision(cli, base, base_name, satisfied, *, template_table_id=None,
               state_path=None, alert_path=None, notifier=None,
               threshold=CAPACITY_THRESHOLD, limit=TABLE_RECORD_LIMIT,
               max_creations=CREATE_ATTEMPTS, poll_timeout=60):
    """Shared discover → decide → create → validate → record loop.

    ``satisfied(inventory, slots, limit)`` decides whether the group needs one
    more table. Both writers call it with their own predicate but share every
    creation, validation, lock, state and alert path below.
    """
    inventory = Inventory(cli, base)
    state = None
    created = []
    alerts = []
    with provision_lock(state_path):
        if state_path is not None:
            state = load_state(state_path)
        inventory.refresh()
        alerts.extend(inventory.alerts)
        slots = inventory.plan.get(base_name) or []
        if not slots:
            raise ContinuationError('no base table exists for ' + base_name)
        if template_table_id is None:
            template_table_id = slots[0]['table_id']
        for _ in range(max_creations + 1):
            slots = inventory.plan.get(base_name) or []
            if satisfied(inventory, slots, limit):
                break
            last = slots[-1]
            next_index = last['index'] + 1
            name = continuation_name(base_name, next_index)
            live = inventory.by_name.get(name)
            if live is not None:
                # A previous attempt already made the table: validate and adopt
                # it, never create a second table with the same name.
                result = validate_continuation(cli, base, template_table_id, live['id'])
                record = {'base_name': base_name, 'index': next_index, 'name': name,
                          'table_id': live['id'], 'created_at': now(), 'adopted': True,
                          'diff': result['diff'], 'field_count': result['field_count'],
                          'view_order': result['target_order']}
                if result['fatal']:
                    record['status'] = 'invalid_live'
                    record['fatal'] = result['fatal']
                    record_alert(alert_path, {'kind': 'continuation_live_invalid', **record},
                                 notifier)
                    raise ContinuationValidationError(
                        'existing continuation failed validation: ' + name)
                record['validated'] = True
                record['status'] = 'active'
                if state is not None:
                    state['creations'].append(record)
                    save(state_path, state)
                created.append(record)
                alerts.extend(result['diff'])
                inventory.refresh()
                continue
            if len(created) >= max_creations + 1:
                raise ContinuationError('continuation creation limit reached for ' + base_name)
            record = create_continuation(cli, base, base_name, next_index,
                                         template_table_id, alert_path=alert_path,
                                         notifier=notifier, poll_timeout=poll_timeout)
            if state is not None:
                state['creations'].append(record)
                save(state_path, state)
            created.append(record)
            inventory.refresh()
        slots = inventory.plan.get(base_name) or []
        last = slots[-1]
        return {'table_id': last['table_id'],
                'table_ids': [slot['table_id'] for slot in slots],
                'created': created, 'alerts': alerts,
                'free': limit - (last['records_count'] or 0),
                'records_count': last['records_count'], 'name': last['name'],
                'state_path': str(state_path) if state_path is not None else None}


def _append_satisfied(needed, threshold):
    def satisfied(inventory, slots, limit):
        free = limit - (slots[-1]['records_count'] or 0)
        return free >= threshold and free >= needed
    return satisfied


def ensure_capacity(cli, base, base_name, needed, *, template_table_id=None,
                    state_path=None, alert_path=None, notifier=None,
                    threshold=CAPACITY_THRESHOLD, limit=TABLE_RECORD_LIMIT,
                    max_creations=CREATE_ATTEMPTS, poll_timeout=60):
    """Guarantee room for ``needed`` appended rows in ``base_name``'s group.

    Creates ``<base>·续表N+1`` whenever the last table's free space is below
    ``threshold`` or below ``needed``. Returns the last (highest-N) table to
    append into. A live table with the target name is validated and adopted, so
    a retry or a concurrent worker never creates a duplicate.
    """
    return _provision(cli, base, base_name, _append_satisfied(max(int(needed), 0), threshold),
                      template_table_id=template_table_id, state_path=state_path,
                      alert_path=alert_path, notifier=notifier, threshold=threshold,
                      limit=limit, max_creations=max_creations, poll_timeout=poll_timeout)


def ensure_total_capacity(cli, base, base_name, needed, *, template_table_id=None,
                          state_path=None, alert_path=None, notifier=None,
                          threshold=CAPACITY_THRESHOLD, limit=TABLE_RECORD_LIMIT,
                          max_creations=CREATE_ATTEMPTS, poll_timeout=60):
    """Guarantee the group's *total* capacity covers ``needed`` rows.

    Used by the fixed-table full reload, whose placement spreads one group's
    rows across every table in index order. A new continuation is created when
    total capacity is short, and also when the current last table would be left
    within ``threshold`` of the cap (so a table never sits nearly full).
    """
    needed = max(int(needed), 0)

    def satisfied(inventory, slots, limit):
        total = limit * len(slots)
        last_free = limit - (slots[-1]['records_count'] or 0)
        return total >= needed and last_free >= threshold

    return _provision(cli, base, base_name, satisfied, template_table_id=template_table_id,
                      state_path=state_path, alert_path=alert_path, notifier=notifier,
                      threshold=threshold, limit=limit, max_creations=max_creations,
                      poll_timeout=poll_timeout)
