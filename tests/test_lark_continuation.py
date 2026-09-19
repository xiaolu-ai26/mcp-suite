"""Offline tests for automatic continuation-table provisioning.

A fake Base implements exactly the lark-cli commands ``lark_continuation`` uses
and keeps an in-memory table inventory, so discovery, creation, field-by-field
validation, idempotency and thread concurrency all run without a network call.
"""
import json
import threading
from pathlib import Path

import pytest

from qiuzhao.collector import lark_continuation as C
from qiuzhao.collector import lark_sync_index as L

TEMPLATE_NAMES = ('互联网科技岗', '国企央企岗', '制造工业岗', '其他行业岗')


def template_fields():
    """A 19-field shape with a >50-option select and two url text fields."""
    fields = [
        {'id': 'fld_job_id', 'name': 'job_id', 'type': 'text', 'style': {'type': 'plain'}},
        {'id': 'fld_title', 'name': '岗位名称', 'type': 'text', 'style': {'type': 'plain'}},
        {'id': 'fld_company', 'name': '公司名称', 'type': 'text', 'style': {'type': 'plain'}},
        {'id': 'fld_unit', 'name': '招聘单位', 'type': 'text', 'style': {'type': 'plain'}},
        {'id': 'fld_industry', 'name': '行业', 'type': 'select', 'multiple': False,
         'options': [{'name': n, 'hue': 'Blue', 'lightness': 'Lighter'}
                     for n in ('互联网/科技', '国企/央企', '制造/工业', '其他')]},
        {'id': 'fld_jobcat', 'name': '岗位大类', 'type': 'select', 'multiple': False,
         'options': [{'name': n, 'hue': 'Gray', 'lightness': 'Lighter'}
                     for n in ('技术/研发', '产品', '运营', '其他')]},
        {'id': 'fld_nature', 'name': '招聘性质', 'type': 'select', 'multiple': False,
         'options': [{'name': n, 'hue': 'Yellow', 'lightness': 'Lighter'}
                     for n in ('校招', '实习', '社招', '未注明')]},
        {'id': 'fld_status', 'name': '状态', 'type': 'select', 'multiple': False,
         'options': [{'name': n, 'hue': 'Gray', 'lightness': 'Lighter'}
                     for n in ('open', 'expired', 'unverified')]},
        {'id': 'fld_deadline', 'name': '投递截止', 'type': 'text', 'style': {'type': 'plain'}},
        {'id': 'fld_grad', 'name': '毕业届别', 'type': 'select', 'multiple': True,
         'options': [{'name': n, 'hue': 'Green', 'lightness': 'Lighter'}
                     for n in ('2026届', '2027届', '未注明')]},
        {'id': 'fld_major', 'name': '专业', 'type': 'select', 'multiple': True,
         'options': [{'name': n, 'hue': 'Blue', 'lightness': 'Lighter'}
                     for n in ('计算机类', '机械制造类', '其他', '未注明')]},
        # 120 options > the 50-option +field-list truncation: paging is required.
        {'id': 'fld_city', 'name': '工作地点', 'type': 'select', 'multiple': True,
         'options': [{'name': f'城市{i:03d}', 'hue': 'Wathet', 'lightness': 'Lighter'}
                     for i in range(117)] + [{'name': '北京'}, {'name': '上海'},
                                             {'name': '未注明'}]},
        {'id': 'fld_source', 'name': '来源', 'type': 'text', 'style': {'type': 'plain'}},
        {'id': 'fld_srcurl', 'name': '原链接', 'type': 'text', 'style': {'type': 'url'}},
        {'id': 'fld_applyurl', 'name': '投递入口', 'type': 'text', 'style': {'type': 'url'}},
        {'id': 'fld_note', 'name': '届别条件说明', 'type': 'text', 'style': {'type': 'plain'},
         'description': '保留毕业日期范围等资格限制。'},
        {'id': 'fld_remark', 'name': '备注', 'type': 'text', 'style': {'type': 'plain'}},
        {'id': 'fld_reviewed', 'name': '复核时间', 'type': 'text', 'style': {'type': 'plain'}},
        {'id': 'fld_deadline_type', 'name': '截止类型', 'type': 'select', 'multiple': False,
         'options': [{'name': n, 'hue': 'Green', 'lightness': 'Lighter'}
                     for n in ('明确', '未披露')]},
    ]
    return fields


def _parse(args):
    command, opts = args[0], {}
    index = 1
    while index < len(args):
        key = args[index].lstrip('-')
        if index + 1 < len(args) and not args[index + 1].startswith('--'):
            opts[key] = args[index + 1]
            index += 2
        else:
            opts[key] = True
            index += 1
    return command, opts


class FakeBase:
    """In-memory lark-cli Base covering the provisioning command surface."""

    def __init__(self, names=TEMPLATE_NAMES, counts=None, fields=None):
        self.calls = 0
        self.serial = 0
        self.tables = {}
        self.fields = {}
        self.views = {}
        self.records = {}
        self.mutate_created = None
        self.fail_create = None
        template = fields if fields is not None else template_fields()
        for name in names:
            count = (counts or {}).get(name, 0)
            self._add_table(name, template=template, records=count)
        # The remaining groups still need a base table for ensure_total_capacity.
        if names == TEMPLATE_NAMES[:1]:
            for name in TEMPLATE_NAMES[1:]:
                self._add_table(name, template=template, records=0)

    def _add_table(self, name, template, records=0, fields=None):
        self.serial += 1
        table_id = f'tbl{self.serial:04d}{name[:3]}'
        self.tables[table_id] = {'id': table_id, 'name': name, 'records_count': records}
        self.fields[table_id] = json.loads(json.dumps(fields if fields is not None else template))
        self.views[table_id] = {'id': f'vew{self.serial:04d}',
                                'order': [f['name'] for f in self.fields[table_id]]}
        self.records[table_id] = records
        return table_id

    def table_id(self, name):
        return next(t['id'] for t in self.tables.values() if t['name'] == name)

    def names(self):
        return sorted(t['name'] for t in self.tables.values())

    def __call__(self, *args):
        self.calls += 1
        command, opts = _parse(args)
        table_id = opts.get('table-id')
        if command == '+table-list':
            return {'data': {'tables': [dict(t) for t in self.tables.values()]}}
        if command == '+field-list':
            fields = json.loads(json.dumps(self.fields[table_id]))
            for field in fields:
                if field.get('type') == 'select' and len(field.get('options') or []) > 50:
                    field['remaining_options_count'] = len(field['options']) - 50
                    field['options'] = field['options'][:50]
            return {'data': {'fields': fields}}
        if command == '+field-search-options':
            field = next(f for f in self.fields[table_id] if f['id'] == opts['field-id'])
            options = field.get('options') or []
            offset = int(opts.get('offset') or 0)
            return {'data': {'total': len(options),
                             'options': json.loads(json.dumps(options[offset:offset + 200]))}}
        if command == '+view-list':
            view = self.views[table_id]
            return {'data': {'views': [{'id': view['id'], 'name': '表格', 'type': 'grid'}]}}
        if command == '+view-get-visible-fields':
            return {'data': {'visible_fields': list(self.views[table_id]['order'])}}
        if command == '+view-set-visible-fields':
            body = json.loads(opts['json'])
            self.views[table_id]['order'] = list(body['visible_fields'])
            return {'data': {}}
        if command == '+table-create':
            if self.fail_create:
                raise RuntimeError(self.fail_create)
            self.serial += 1
            table_id = f'tbl{self.serial:04d}new'
            self.tables[table_id] = {'id': table_id, 'name': opts['name'], 'records_count': 0}
            self.fields[table_id] = json.loads(opts['fields'])
            for field in self.fields[table_id]:
                field.setdefault('id', f'fld{self.serial:04d}{field["name"][:2]}')
            self.views[table_id] = {'id': f'vew{self.serial:04d}',
                                    'order': [f['name'] for f in self.fields[table_id]]}
            self.records[table_id] = 0
            return {'data': {'table': {'id': table_id, 'name': opts['name'],
                                       'views': [{'id': self.views[table_id]['id']}]}}}
        if command == '+field-create':
            created = []
            for field in json.loads(opts['json']):
                field = dict(field)
                self.serial += 1
                field.setdefault('id', f'fld{self.serial:04d}{field["name"][:2]}')
                self.fields[table_id].append(field)
                created.append(field)
            if self.mutate_created:
                self.mutate_created(self, table_id)
            return {'data': {'created': len(created)}}
        if command == '+table-delete':
            self.tables.pop(table_id, None)
            self.fields.pop(table_id, None)
            self.views.pop(table_id, None)
            self.records.pop(table_id, None)
            return {'data': {}}
        if command == '+record-batch-create':
            rows = json.loads(opts['json'])['create_records']
            self.records[table_id] = self.records.get(table_id, 0) + len(rows)
            self.tables[table_id]['records_count'] = self.records[table_id]
            return {'data': {'record_id_list': [f'rec{self.serial}{i}' for i in range(len(rows))]}}
        raise AssertionError('unexpected command ' + command)


def run(cli, base='fake-base', group='互联网科技岗', needed=5, state=None, alerts=None,
        **kwargs):
    return C.ensure_capacity(cli, base, group, needed, state_path=state,
                             alert_path=alerts, **kwargs)


def test_discovery_sorts_by_n_and_skips_unrelated_names():
    tables = [{'id': 'tblBase', 'name': '互联网科技岗', 'records_count': 100},
              {'id': 'tblTwo', 'name': '互联网科技岗·续表2', 'records_count': 20},
              {'id': 'tblOne', 'name': '互联网科技岗·续表1', 'records_count': 200},
              {'id': 'tblOther', 'name': '重灌原型-互联网科技岗', 'records_count': 9},
              {'id': 'tblZero', 'name': '互联网科技岗·续表0', 'records_count': 9},
              {'id': 'tblLead', 'name': '互联网科技岗·续表01', 'records_count': 9},
              {'id': 'tblSuffix', 'name': '互联网科技岗2', 'records_count': 9},
              {'id': 'tblNoun', 'name': '互联网科技岗·续表X', 'records_count': 9},
              {'id': 'tblManu', 'name': '制造工业岗', 'records_count': 5}]
    plan, problems = C.discover(tables)
    assert problems == []
    assert [slot['index'] for slot in plan['互联网科技岗']] == [0, 1, 2]
    assert [slot['table_id'] for slot in plan['互联网科技岗']] == ['tblBase', 'tblOne', 'tblTwo']
    assert plan['制造工业岗'][0]['table_id'] == 'tblManu'
    assert plan['国企央企岗'] == []


def test_capacity_below_threshold_creates_and_validates_one_table(tmp_path):
    cli = FakeBase(counts={'互联网科技岗': C.TABLE_RECORD_LIMIT - 10})
    state, alerts = tmp_path / 'state.json', tmp_path / 'alerts.jsonl'
    result = run(cli, state=state, alerts=alerts)
    created = result['created']
    assert len(created) == 1 and created[0]['name'] == '互联网科技岗·续表1'
    assert created[0]['validated'] is True
    assert not created[0].get('fatal')
    assert cli.names().count('互联网科技岗·续表1') == 1
    # The new blank table is now the append target with a full budget.
    assert result['table_id'] == cli.table_id('互联网科技岗·续表1')
    assert result['free'] == C.TABLE_RECORD_LIMIT
    # The created table's fields match the template exactly (19 names, view order).
    template = cli.fields[cli.table_id('互联网科技岗')]
    target = cli.fields[result['table_id']]
    assert len(template) == len(target) == 19
    assert {f['name'] for f in template} == {f['name'] for f in target}
    events = [json.loads(line) for line in alerts.read_text().splitlines()]
    assert events[0]['kind'] == 'continuation_created'
    saved = json.loads(state.read_text())
    assert saved['creations'][0]['validated'] is True


def test_no_creation_when_last_table_has_enough_room(tmp_path):
    cli = FakeBase(counts={'互联网科技岗': 100})
    result = run(cli, state=tmp_path / 'state.json', alerts=tmp_path / 'alerts.jsonl')
    assert result['created'] == []
    assert cli.names() == sorted(TEMPLATE_NAMES)
    assert result['table_id'] == cli.table_id('互联网科技岗')


def test_highest_n_continuation_is_the_append_target(tmp_path):
    cli = FakeBase(counts={'互联网科技岗': 100})
    cli._add_table('互联网科技岗·续表1', template=template_fields(), records=50)
    result = run(cli, state=tmp_path / 'state.json', alerts=tmp_path / 'alerts.jsonl')
    assert result['created'] == []
    assert result['table_id'] == cli.table_id('互联网科技岗·续表1')


def test_field_mismatch_deletes_the_new_table_and_never_validates_it(tmp_path):
    cli = FakeBase(counts={'互联网科技岗': C.TABLE_RECORD_LIMIT - 1})
    def drop_option(fake, table_id):
        if fake.tables[table_id]['name'] == '互联网科技岗·续表1':
            for field in fake.fields[table_id]:
                if field['name'] == '工作地点':
                    field['options'] = field['options'][:-1]  # 工作地点 shrinks by one
    cli.mutate_created = drop_option
    with pytest.raises(C.ContinuationValidationError):
        run(cli, state=tmp_path / 'state.json', alerts=tmp_path / 'alerts.jsonl')
    # The unvalidated table is deleted and never written into.
    assert '互联网科技岗·续表1' not in cli.names()
    events = [json.loads(line) for line in (tmp_path / 'alerts.jsonl').read_text().splitlines()]
    assert events[-1]['kind'] == 'continuation_validation_failed'
    assert events[-1]['deleted'] is True
    assert events[-1]['fatal'][0]['kind'] == 'options_set'


def test_field_type_mismatch_is_rejected(tmp_path):
    cli = FakeBase(counts={'互联网科技岗': C.TABLE_RECORD_LIMIT - 1})
    def break_type(fake, table_id):
        if fake.tables[table_id]['name'] == '互联网科技岗·续表1':
            next(f for f in fake.fields[table_id] if f['name'] == '原链接')['style'] = {'type': 'plain'}
    cli.mutate_created = break_type
    with pytest.raises(C.ContinuationValidationError):
        run(cli, state=tmp_path / 'state.json', alerts=tmp_path / 'alerts.jsonl')
    assert '互联网科技岗·续表1' not in cli.names()


def test_idempotent_two_runs_create_one_table(tmp_path):
    cli = FakeBase(counts={'互联网科技岗': C.TABLE_RECORD_LIMIT - 1})
    state, alerts = tmp_path / 'state.json', tmp_path / 'alerts.jsonl'
    first = run(cli, state=state, alerts=alerts)
    second = run(cli, state=state, alerts=alerts)
    assert len(first['created']) == 1
    assert second['created'] == []
    assert cli.names().count('互联网科技岗·续表1') == 1
    saved = json.loads(state.read_text())
    assert len([c for c in saved['creations'] if c.get('validated')]) == 1


def test_two_threads_create_only_one_table(tmp_path):
    cli = FakeBase(counts={'互联网科技岗': C.TABLE_RECORD_LIMIT - 1})
    state, alerts = tmp_path / 'state.json', tmp_path / 'alerts.jsonl'
    barrier = threading.Barrier(2)
    results = []

    def worker():
        barrier.wait()
        results.append(run(cli, state=state, alerts=alerts))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert cli.names().count('互联网科技岗·续表1') == 1
    assert sum(len(result['created']) for result in results) == 1


def test_ensure_total_capacity_grows_until_the_group_fits(tmp_path):
    cli = FakeBase(counts={'互联网科技岗': 0})
    state, alerts = tmp_path / 'state.json', tmp_path / 'alerts.jsonl'
    limit = 100
    threshold = min(C.CAPACITY_THRESHOLD, max(1, limit // 20))
    first = C.ensure_total_capacity(cli, 'fake-base', '互联网科技岗', 150,
                                    state_path=state, alert_path=alerts, limit=limit,
                                    threshold=threshold)
    assert first['created'] and first['created'][0]['name'] == '互联网科技岗·续表1'
    second = C.ensure_total_capacity(cli, 'fake-base', '互联网科技岗',
                                    limit * len(first['table_ids']),
                                    state_path=state, alert_path=alerts, limit=limit,
                                    threshold=threshold)
    assert second['created'] == []


def test_creation_failure_is_alerted_and_leaves_no_new_table(tmp_path):
    cli = FakeBase(counts={'互联网科技岗': C.TABLE_RECORD_LIMIT - 1})
    cli.fail_create = '模拟建表失败'
    with pytest.raises(C.ContinuationError):
        run(cli, state=tmp_path / 'state.json', alerts=tmp_path / 'alerts.jsonl')
    assert '互联网科技岗·续表1' not in cli.names()
    events = [json.loads(line) for line in (tmp_path / 'alerts.jsonl').read_text().splitlines()]
    assert events[-1]['kind'] == 'continuation_create_failed'


def test_reload_plan_grows_through_the_shared_provisioner(tmp_path):
    """The full reload's overflow path uses the same discovery/create/validate."""
    from qiuzhao.collector import lark_reload_mirror as R
    cli = FakeBase(counts={'互联网科技岗': 100})
    limit, threshold = 100, 5
    grouped = {'互联网科技岗': [{'row': i} for i in range(250)],
               '国企央企岗': [], '制造工业岗': [], '其他行业岗': []}
    plan = R.discover_tables([dict(t) for t in cli.tables.values()])
    _, blocked = R.plan_placement(grouped, plan, limit)
    assert blocked['互联网科技岗']['overflow'] == 150  # one table of 100 cannot hold 250
    ensured = C.ensure_total_capacity(cli, 'fake-base', '互联网科技岗', 250,
                                      state_path=tmp_path / 'state.json',
                                      alert_path=tmp_path / 'alerts.jsonl',
                                      limit=limit, threshold=threshold)
    assert [record['name'] for record in ensured['created']] == \
        ['互联网科技岗·续表1', '互联网科技岗·续表2']
    plan = R.discover_tables([dict(t) for t in cli.tables.values()])
    placement, blocked = R.plan_placement(grouped, plan, limit)
    assert blocked == {}
    assert sum(len(rows) for rows in placement.values()) == 250


# ---------------------------------------------------------------- run_mirror

class FakeTransport:
    """Minimal lark_sync_index transport backed by the same FakeBase."""

    def __init__(self, base, run_dir):
        self.base = base
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.calls = 0

    def continuation_cli(self, *args):
        self.calls += 1
        return self.base(*args)

    def table_counts(self):
        return {t['id']: t['records_count'] for t in self.base.tables.values()}

    def schema(self, table):
        return {f['name']: dict(f, options=f.get('options') or [])
                for f in self.base.fields[table]}

    def create_records(self, table, rows, tag):
        self.calls += 1
        self.base.records[table] = self.base.records.get(table, 0) + len(rows)
        self.base.tables[table]['records_count'] = self.base.records[table]
        return {'data': {'record_id_list': [f'new{self.calls}{i}' for i in range(len(rows))]}}


def _jobs_file(tmp_path, count):
    rows = []
    for i in range(count):
        rows.append({'id': f'mirror-{i}', 'p1_company': '测试公司', 'job_title': f'岗位{i}',
                     'recruitment_type': '校园招聘', 'source_url': f'https://x/{i}',
                     'application_url': f'https://x/apply/{i}', 'detail_url': f'https://x/{i}',
                     'description_raw': '面向2026届毕业生', 'reviewed_at': '2026-09-19'})
    path = tmp_path / 'jobs.json'
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    return path


def test_run_mirror_creates_continuation_before_appending(tmp_path):
    cli = FakeBase(counts={'互联网科技岗': C.TABLE_RECORD_LIMIT - 1})
    source = _jobs_file(tmp_path, 2)
    transport = FakeTransport(cli, tmp_path / 'run')
    receipt = L.run_mirror(source, L.S.digest(source), index_path=tmp_path / 'index.json',
                           journal_path=tmp_path / 'journal.json', run_dir=tmp_path / 'run',
                           transport=transport)
    assert cli.names().count('互联网科技岗·续表1') == 1
    assert receipt['continuations']['互联网科技岗'][0]['validated'] is True
    assert receipt['appended'] == 2
    assert cli.records[cli.table_id('互联网科技岗·续表1')] == 2
    assert receipt['status'] == 'synced'


def test_run_mirror_never_writes_when_validation_fails(tmp_path):
    cli = FakeBase(counts={'互联网科技岗': C.TABLE_RECORD_LIMIT - 1})
    def break_field(fake, table_id):
        if fake.tables[table_id]['name'] == '互联网科技岗·续表1':
            for field in fake.fields[table_id]:
                if field['name'] == '招聘性质':
                    field['options'] = field['options'][:1]
    cli.mutate_created = break_field
    source = _jobs_file(tmp_path, 2)
    transport = FakeTransport(cli, tmp_path / 'run')
    receipt = L.run_mirror(source, L.S.digest(source), index_path=tmp_path / 'index.json',
                           journal_path=tmp_path / 'journal.json', run_dir=tmp_path / 'run',
                           transport=transport)
    assert receipt['appended'] == 0
    assert receipt['capacity_blocked']
    assert '互联网科技岗·续表1' not in cli.names()
    assert receipt['status'] != 'synced'
