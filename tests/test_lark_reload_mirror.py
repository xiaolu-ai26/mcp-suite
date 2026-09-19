"""Offline tests for the fixed-table full-reload mirror.

No network: a fake `Lark` implements exactly the lark-cli surface the module
uses and keeps a small in-memory Base, so the whole reload (backup, delete,
create, verify, rollback, sha256 gate) runs end to end in the test process.
"""
import json
from pathlib import Path

import pytest

from qiuzhao.collector import lark_reload_mirror as R

SELECT = {
    '行业': (False, ['互联网/科技', '国企/央企', '制造/工业', '能源/电力', '金融', '医药/医疗',
                     '教育', '物流/运输', '传媒/广告', '消费/零售', '农业', '房地产', '其他']),
    '岗位大类': (False, ['技术/研发', '产品', '运营', '设计', '市场/营销', '销售', '职能/支持',
                         '金融', '咨询', '其他']),
    '招聘性质': (False, ['校招', '实习', '社招', '未注明']),
    '状态': (False, ['open', 'expired', 'unverified', '未注明']),
    '截止类型': (False, ['明确', '未披露']),
    '专业': (True, ['计算机类', '机械制造类', '管理类', '其他']),
    '毕业届别': (True, ['2026届', '2027届', '社招不限届别']),
    # >50 unique options so the option-pagination path is exercised for real.
    '工作地点': (True, [f'合成城市{i:03d}' for i in range(250)] + ['北京', '上海']),
}
TEXT_FIELDS = ['job_id', '岗位名称', '公司名称', '招聘单位', '原链接', '投递入口', '来源', '投递截止',
               '复核时间', '届别条件说明', '备注']


URL_FIELDS = ('原链接', '投递入口')


def field_defs():
    fields = [{'id': 'fld_' + name, 'name': name, 'type': 'text',
               **({'style': {'type': 'url'}} if name in URL_FIELDS else {})}
              for name in TEXT_FIELDS if name != 'job_id']
    fields.insert(0, {'id': 'fld_job_id', 'name': 'job_id', 'type': 'text'})
    for name, (multiple, options) in SELECT.items():
        fields.append({'id': 'fld_' + name, 'name': name, 'type': 'select', 'multiple': multiple,
                       'options': [{'name': value} for value in options[:50]],
                       'remaining_options_count': max(0, len(options) - 50)})
    return fields


def _validate_raw_cells(fields):
    """Reproduce the raw endpoint's cell-format refusals.

    The `base +record-batch-create` shortcut normalises cells; the raw
    `records/batch_create` endpoint does not, and the module deliberately uses
    the raw one. Without this check the fake would happily accept a format the
    live Base rejects with 1254062 / 1254068.
    """
    specs = {field['name']: field for field in field_defs()}
    for name, value in fields.items():
        spec = specs.get(name)
        if spec is None:
            raise AssertionError('field not in table: ' + name)
        if spec['type'] == 'select' and not spec.get('multiple'):
            if not isinstance(value, str):
                raise RuntimeError('1254062 SingleSelectFieldConvFail: ' + name)
        elif spec['type'] == 'select':
            if not isinstance(value, list):
                raise RuntimeError('1254063 MultiSelectFieldConvFail: ' + name)
        elif (spec.get('style') or {}).get('type') == 'url':
            if not (isinstance(value, dict) and 'link' in value and 'text' in value):
                raise RuntimeError('1254068 URLFieldConvFail: ' + name)
        elif not isinstance(value, str):
            raise AssertionError('text field expects a string: ' + name)


class FakeLark:
    """Same surface as `R.Lark`, backed by an in-memory Base."""

    def __init__(self, workdir, timeout=300):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.records = []
        self.rate_limited = 0
        self.transient = 0
        self.tables = {}
        self.fail_create_at = None
        self.api_calls = []
        self._serial = 0

    # -- test helpers ------------------------------------------------------
    def add_table(self, table_id, name, rows=0):
        self.tables[table_id] = {'id': table_id, 'name': name, 'records': [
            {'record_id': f'rec{table_id}{i:05d}', 'fields': {'job_id': f'old-{i}'}}
            for i in range(rows)]}

    @property
    def count(self):
        return len(self.records)

    @property
    def seconds(self):
        return 0.0

    def by_kind(self):
        out = {}
        for record in self.records:
            bucket = out.setdefault(record['kind'], {'calls': 0, 'sec': 0.0})
            bucket['calls'] += 1
        return out

    def _next_id(self):
        self._serial += 1
        return f'new{self._serial:06d}'

    @staticmethod
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

    # -- lark-cli surface --------------------------------------------------
    def base(self, *args, cwd=None, kind=None):
        command, opts = self._parse(args)
        self.records.append({'kind': kind or command, 'sec': 0.0, 'ok': True})
        table = self.tables.get(opts.get('table-id'))
        if command == '+table-list':
            return {'ok': True, 'data': {'tables': [
                {'id': t['id'], 'name': t['name'], 'records_count': len(t['records'])}
                for t in self.tables.values()]}}
        if command == '+field-list':
            return {'ok': True, 'data': {'fields': field_defs()}}
        if command == '+field-search-options':
            name = opts['field-id'][4:]
            options = SELECT[name][1]
            offset = int(opts.get('offset') or 0)
            return {'ok': True, 'data': {'total': len(options),
                                         'options': [{'name': value} for value
                                                     in options[offset:offset + 200]]}}
        if command == '+record-list':
            offset, limit = int(opts.get('offset') or 0), int(opts.get('limit') or 2000)
            rows = table['records'][offset:offset + limit]
            payload = [{'record_id': row['record_id'], **row['fields']} for row in rows]
            target = Path(cwd or self.workdir)
            target.mkdir(parents=True, exist_ok=True)
            (target / opts['output']).write_text(
                '\n'.join(json.dumps(row, ensure_ascii=False) for row in payload) + '\n',
                encoding='utf-8')
            end = offset + len(rows)
            # lark-cli answers `+record-list --output` with a flat manifest.
            return {'rev': 1, 'records_count': len(rows),
                    'has_more': end < len(table['records']), 'next_offset': end}
        raise AssertionError('unexpected command ' + command)

    def api(self, method, path, body=None, cwd=None, kind=None):
        table_id = path.split('/tables/')[1].split('/')[0]
        table = self.tables[table_id]
        self.api_calls.append({'kind': kind, 'path': path, 'size': len(body and (
            body.get('records') or []))})
        self.records.append({'kind': kind, 'sec': 0.0, 'ok': True})
        if kind == 'create' and self.fail_create_at is not None \
                and len(self.api_calls) >= self.fail_create_at:
            raise RuntimeError('lark-cli rejected create: simulated failure')
        if path.endswith('batch_delete'):
            wanted = set(body['records'])
            table['records'] = [row for row in table['records'] if row['record_id'] not in wanted]
            return {'ok': True, 'data': {'records': [{'record_id': rid, 'deleted': True}
                                                     for rid in body['records']]}}
        if path.endswith('batch_create'):
            created = []
            for item in body['records']:
                _validate_raw_cells(item['fields'])
                record_id = self._next_id()
                table['records'].append({'record_id': record_id, 'fields': item['fields']})
                created.append({'record_id': record_id, 'fields': item['fields']})
            return {'ok': True, 'data': {'records': created}}
        raise AssertionError('unexpected api path ' + path)


# --------------------------------------------------------------------- routing

def test_industry_routes_to_the_live_table_group():
    assert R.mirror_industry({'industry': '互联网/科技'}) == ('互联网科技岗', '互联网/科技', None)
    assert R.mirror_industry({'industry': '国企/央企'}) == ('国企央企岗', '国企/央企', None)
    assert R.mirror_industry({'industry': '制造/工业'}) == ('制造工业岗', '制造/工业', None)
    # 没有单独分组的行业进「其他行业岗」,并保留自己的行业值。
    assert R.mirror_industry({'industry': '医药/医疗'}) == ('其他行业岗', '医药/医疗', None)
    assert R.mirror_industry({'industry': '能源/电力'}) == ('其他行业岗', '能源/电力', None)
    assert R.mirror_industry({'industry': ''}) == ('其他行业岗', '其他', 'missing_industry')
    assert R.mirror_industry({'industry': '不存在的行业'}) == ('其他行业岗', '其他',
                                                       'unknown_industry:不存在的行业')


def test_continuation_tables_are_discovered_in_numeric_order():
    plan = R.discover_tables([
        {'id': 'tbl4', 'name': '互联网科技岗·续表2'},
        {'id': 'tbl1', 'name': '互联网科技岗'},
        {'id': 'tbl2', 'name': '互联网科技岗·续表1'},
        {'id': 'tbl9', 'name': '制造工业岗'},
    ])
    assert plan['互联网科技岗'] == ['tbl1', 'tbl2', 'tbl4']
    assert plan['制造工业岗'] == ['tbl9']
    # 没有的表就是零容量,绝不自动建表。
    assert plan['国企央企岗'] == []
    assert plan['其他行业岗'] == []


def test_placement_fills_existing_tables_and_blocks_the_overflow():
    grouped = {name: [] for name in R.BASE_TABLE_NAMES}
    grouped['互联网科技岗'] = [{'job_id': f'j{i}'} for i in range(7)]
    grouped['国企央企岗'] = [{'job_id': 'g0'}]
    plan = {'互联网科技岗': ['tblA', 'tblB'], '国企央企岗': [], '制造工业岗': [],
            '其他行业岗': []}
    placement, blocked = R.plan_placement(grouped, plan, 4)
    assert [row['job_id'] for row in placement['tblA']] == ['j0', 'j1', 'j2', 'j3']
    assert [row['job_id'] for row in placement['tblB']] == ['j4', 'j5', 'j6']
    assert blocked == {'国企央企岗': {'rows': 1, 'capacity': 0, 'tables': [], 'overflow': 1}}


# -------------------------------------------------------------------- mapping

def schema_of():
    """The fully paged schema `field_options` would return."""
    return {field['name']: {'type': field['type'], 'multiple': field.get('multiple', False),
                            **({'options': set(SELECT[field['name']][1])}
                               if field['type'] == 'select' else {})}
            for field in field_defs()}


def test_sanitize_drops_undeclared_field_and_option_but_keeps_the_row():
    fields = schema_of()
    rows = [{'job_id': 'a', '岗位描述': '不在 19 列里', '工作地点': ['北京', '火星'],
             '行业': ['互联网/科技'], '状态': ['open', 'expired']}]
    alerts = R.sanitize(rows, fields, 'tblA')
    assert rows[0] == {'job_id': 'a', '工作地点': ['北京'], '行业': ['互联网/科技'],
                       '状态': ['open']}
    kinds = {(alert['kind'], alert.get('field')) for alert in alerts}
    assert ('field_not_in_table', '岗位描述') in kinds
    assert ('option_missing', '工作地点') in kinds
    assert ('single_select_truncated', '状态') in kinds
    assert {alert['kind']: alert.get('rows') for alert in alerts} == {
        'field_not_in_table': 1, 'option_missing': 1, 'single_select_truncated': 1}


def test_sanitize_reports_a_value_whose_option_the_table_lacks():
    fields = schema_of()
    fields['行业']['options'] = {'互联网/科技'}
    rows = [{'job_id': 'a', '行业': ['医药/医疗']}]
    alerts = R.sanitize(rows, fields, 'tblA')
    assert rows[0] == {'job_id': 'a'}
    assert alerts[0]['kind'] == 'option_missing' and alerts[0]['values'] == ['医药/医疗']


def test_restore_payload_reduces_markdown_links_and_drops_empty_cells():
    payload = R.restore_payload({'record_id': 'rec1', 'job_id': 'a', '备注': '',
                                 '原链接': '[https://x.invalid/a](https://x.invalid/a)',
                                 '工作地点': ['北京'], '来源': None})
    assert payload == {'fields': {'job_id': 'a', '原链接': 'https://x.invalid/a',
                                  '工作地点': ['北京']}}


def test_snapshot_keeps_the_established_membership_and_payload():
    import tempfile
    rows = [
        {'id': 'keep-1', 'industry': '国企/央企', 'job_title': '岗位一', 'recruitment_unit': '单位一',
         'source_url': 'https://x.invalid/1', 'application_url': 'https://x.invalid/a1',
         'status': 'open'},
        {'id': 'dup', 'industry': '互联网/科技', 'job_title': '第一次', 'source_url': 'https://x.invalid/2',
         'application_url': 'https://x.invalid/a2'},
        {'id': 'dup', 'industry': '互联网/科技', 'job_title': '第二次', 'source_url': 'https://x.invalid/3',
         'application_url': 'https://x.invalid/a3'},
        {'id': 'removed', 'industry': '互联网/科技', 'job_title': '下架', 'status': 'removed',
         'source_url': 'https://x.invalid/4', 'application_url': 'https://x.invalid/a4'},
        {'id': 'no-link', 'industry': '互联网/科技', 'job_title': '缺链接'},
    ]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'jobs.json'
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        grouped, report, warnings = R.build_snapshot(path)
    assert report['desired'] == 2 and report['duplicate_id_first_wins'] == 1
    assert report['dropped_removed'] == 1 and report['dropped_invalid'] == 1
    assert [row['job_id'] for row in grouped['互联网科技岗']] == ['dup']
    assert grouped['互联网科技岗'][0]['岗位名称'] == '第一次'
    assert [row['job_id'] for row in grouped['国企央企岗']] == ['keep-1']
    assert warnings == []


# ---------------------------------------------------------------- end to end

@pytest.fixture
def run_env(tmp_path, monkeypatch):
    monkeypatch.setattr(R, 'Lark', FakeLark)
    monkeypatch.setenv('QIUZHAO_LARK_SYNC_LOCK_PATH', str(tmp_path / 'sync.lock'))
    jobs = tmp_path / 'jobs.json'
    jobs.write_text(json.dumps([
        {'id': 'a1', 'industry': '互联网/科技', 'job_title': '岗位一', 'recruitment_unit': '单位一',
         'source_url': 'https://x.invalid/1', 'application_url': 'https://x.invalid/a1',
         'cities': ['北京'], 'cities_normalized': ['北京']},
        {'id': 'a2', 'industry': '互联网/科技', 'job_title': '岗位二', 'recruitment_unit': '单位二',
         'source_url': 'https://x.invalid/2', 'application_url': 'https://x.invalid/a2'},
        {'id': 'b1', 'industry': '国企/央企', 'job_title': '岗位三', 'recruitment_unit': '单位三',
         'source_url': 'https://x.invalid/3', 'application_url': 'https://x.invalid/a3'},
    ], ensure_ascii=False), encoding='utf-8')
    return {'jobs': jobs, 'state': tmp_path / 'state', 'runs': tmp_path / 'runs', 'tmp': tmp_path}


def _seed_plan(monkeypatch, run_env, tables):
    """Give `main` a fixed table inventory without standing up a real Base."""
    inventory = {'ok': True, 'data': {'tables': [
        {'id': table_id, 'name': name, 'records_count': 0} for table_id, name in tables]}}
    original = FakeLark.base

    def patched(self, *args, cwd=None, kind=None):
        if args and args[0] == '+table-list':
            return inventory
        return original(self, *args, cwd=cwd, kind=kind)

    monkeypatch.setattr(FakeLark, 'base', patched)
    return inventory


def test_end_to_end_reload_is_idempotent_and_never_touches_table_identity(run_env, monkeypatch):
    inventory = [('tblA', '互联网科技岗'), ('tblB', '互联网科技岗·续表1'), ('tblC', '国企央企岗')]
    _seed_plan(monkeypatch, run_env, inventory)
    seeded = {}
    original_init = FakeLark.__init__

    def patched_init(self, workdir, timeout=300):
        original_init(self, workdir, timeout)
        self.add_table('tblA', '互联网科技岗', rows=3)
        self.add_table('tblB', '互联网科技岗·续表1', rows=1)
        self.add_table('tblC', '国企央企岗', rows=2)
        seeded['lark'] = self

    monkeypatch.setattr(FakeLark, '__init__', patched_init)
    argv = ['--source-path', str(run_env['jobs']), '--state-dir', str(run_env['state']),
            '--runs-dir', str(run_env['runs']), '--apply', '--max-rows-per-table', '2',
            '--workers', '3']
    assert R.main(argv) == 0
    lark = seeded['lark']
    assert len(lark.tables['tblA']['records']) == 2
    # 续表不再需要时必须被清空,不能留着昨天的溢出数据。
    assert len(lark.tables['tblB']['records']) == 0
    assert len(lark.tables['tblC']['records']) == 1
    # 表身份从不改变:没有建表/删表/改名调用。
    assert not [call for call in lark.api_calls if 'table' in (call['path'] or '').split('/')[-1]]
    receipt = json.loads(sorted(run_env['runs'].glob('*/receipt.json'))[-1].read_text(encoding='utf-8'))
    assert receipt['success'] is True and receipt['planned_total'] == 3
    assert receipt['tables']['tblA']['records_before'] == 3
    assert receipt['tables']['tblA']['records_after'] == 2
    assert receipt['tables']['tblA']['backup_sha256']
    # 三张表各清空一次;续表1 计划 0 行,所以只有两次批量创建。
    assert receipt['calls_by_kind']['delete']['calls'] == 3
    assert receipt['calls_by_kind']['create']['calls'] == 2
    assert receipt['tables']['tblB']['emptied'] is True

    # 同一个 sha 再跑一次:跳过,零写入。
    before = [len(lark.tables[table_id]['records']) for table_id, _ in inventory]
    assert R.main(argv) == 0
    assert [len(lark.tables[table_id]['records']) for table_id, _ in inventory] == before
    skipped = json.loads(sorted(run_env['runs'].glob('*/receipt.json'))[-1].read_text(encoding='utf-8'))
    assert skipped.get('skipped') and 'skipped' not in (skipped.get('failed_tables') or [])


def test_a_failed_create_is_rolled_back_from_that_tables_own_backup(run_env, monkeypatch):
    inventory = [('tblA', '互联网科技岗'), ('tblB', '互联网科技岗·续表1'), ('tblC', '国企央企岗')]
    _seed_plan(monkeypatch, run_env, inventory)
    seeded = {}
    original_init = FakeLark.__init__

    def patched_init(self, workdir, timeout=300):
        original_init(self, workdir, timeout)
        self.add_table('tblA', '互联网科技岗', rows=4)
        self.add_table('tblB', '互联网科技岗·续表1', rows=0)
        self.add_table('tblC', '国企央企岗', rows=0)
        seeded['lark'] = self

    monkeypatch.setattr(FakeLark, '__init__', patched_init)
    argv = ['--source-path', str(run_env['jobs']), '--state-dir', str(run_env['state']),
            '--runs-dir', str(run_env['runs']), '--apply', '--max-rows-per-table', '2']

    original_api = FakeLark.api
    failures = []

    def failing(self, method, path, body=None, cwd=None, kind=None):
        # 只让第一次 create 失败,回滚时的那次必须成功,才测得到"用备份恢复"。
        if kind == 'create' and path.split('/tables/')[1].startswith('tblA') and not failures:
            failures.append(1)
            raise RuntimeError('lark-cli rejected create: simulated 500')
        return original_api(self, method, path, body=body, cwd=cwd, kind=kind)

    monkeypatch.setattr(FakeLark, 'api', failing)
    assert R.main(argv) == 1
    lark = seeded['lark']
    # 失败表恢复到备份状态,其余表照常完成。
    assert len(lark.tables['tblA']['records']) == 4
    assert len(lark.tables['tblB']['records']) == 0
    assert len(lark.tables['tblC']['records']) == 1
    receipt = json.loads(sorted(run_env['runs'].glob('*/receipt.json'))[-1].read_text(encoding='utf-8'))
    assert receipt['success'] is False and receipt['failed_tables'] == ['tblA']
    assert receipt['tables']['tblA']['restore']['exact'] is True
    assert receipt['tables']['tblA']['restore']['records'] == 4
    assert receipt['tables']['tblC']['status'] == 'ok'
    assert not (run_env['state'] / 'reload-state.json').exists()


def test_a_restore_that_also_fails_is_reported_as_partial_data(run_env, monkeypatch):
    inventory = [('tblA', '互联网科技岗'), ('tblC', '国企央企岗')]
    _seed_plan(monkeypatch, run_env, inventory)
    seeded = {}
    original_init = FakeLark.__init__

    def patched_init(self, workdir, timeout=300):
        original_init(self, workdir, timeout)
        self.add_table('tblA', '互联网科技岗', rows=4)
        self.add_table('tblC', '国企央企岗', rows=0)
        seeded['lark'] = self

    monkeypatch.setattr(FakeLark, '__init__', patched_init)

    def failing(self, method, path, body=None, cwd=None, kind=None):
        if path.split('/tables/')[1].startswith('tblA'):
            raise RuntimeError('lark-cli rejected: simulated outage')
        return original_api(self, method, path, body=body, cwd=cwd, kind=kind)

    original_api = FakeLark.api
    monkeypatch.setattr(FakeLark, 'api', failing)
    argv = ['--source-path', str(run_env['jobs']), '--state-dir', str(run_env['state']),
            '--runs-dir', str(run_env['runs']), '--apply', '--max-rows-per-table', '2']
    assert R.main(argv) == 1
    receipt = json.loads(sorted(run_env['runs'].glob('*/receipt.json'))[-1].read_text(encoding='utf-8'))
    assert receipt['tables']['tblA']['status'] == 'failed'
    assert 'error' in receipt['tables']['tblA']['restore']
    kinds = {(alert['kind'], alert.get('table_id')) for alert in receipt['alerts']}
    assert ('partial_data', 'tblA') in kinds


def test_module_has_no_undefined_globals():
    """A missing stdlib import must fail here, not mid-run against the live Base."""
    import ast
    import builtins

    tree = ast.parse(Path(R.__file__).read_text(encoding='utf-8'))
    defined = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                defined.add((alias.asname or alias.name).split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                defined.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
    used = {node.id for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    assert sorted(used - defined) == []


def test_write_payload_uses_the_raw_endpoint_cell_format():
    fields = schema_of()
    fields['原链接'] = {'type': 'text', 'multiple': False, 'style': 'url'}
    fields['投递入口'] = {'type': 'text', 'multiple': False, 'style': 'url'}
    row = {'job_id': 'a', '行业': ['互联网/科技'], '专业': ['计算机类', '其他'],
           '原链接': 'https://x.invalid/a', '备注': '保留'}
    assert R.write_payload(row, fields) == {
        'job_id': 'a',
        '行业': '互联网/科技',                       # 单选 -> 字符串
        '专业': ['计算机类', '其他'],                 # 多选 -> 保持列表
        '原链接': {'link': 'https://x.invalid/a', 'text': 'https://x.invalid/a'},
        '备注': '保留'}


def test_write_payload_drops_a_field_the_table_does_not_declare():
    fields = schema_of()
    assert R.write_payload({'job_id': 'a', '岗位描述': 'x'}, fields) == {'job_id': 'a'}


def test_run_batches_overlaps_but_keeps_order_and_propagates_failure():
    import time as clock

    active, peak = [], []

    def work(chunk):
        active.append(chunk)
        peak.append(len(active))
        clock.sleep(0.05)
        active.remove(chunk)
        return chunk

    assert R.run_batches(work, [1, 2, 3], 1) == [1, 2, 3]
    assert max(peak) == 1
    assert R.run_batches(work, [1, 2], 3) == [1, 2]
    assert max(peak) > 1, 'workers must actually overlap'

    def failing(chunk):
        work(chunk)
        if chunk == 3:
            raise RuntimeError('batch 3 failed')
        return chunk

    with pytest.raises(RuntimeError, match='batch 3 failed'):
        R.run_batches(failing, [1, 2, 3, 4, 5, 6], 3)
    assert active == [], 'no worker may still be running after a failure returns'


def test_transient_data_not_ready_is_retryable_but_capacity_is_not():
    """1254607 is a retry; 800040832 is an operator decision, never a retry."""
    assert R.Lark._transient({'code': 1254607, 'message': 'Data not ready, please try again later'})
    assert R.Lark._transient({'message': 'Data not ready, please try again later'})
    assert not R.Lark._transient({'code': 800040832, 'message': 'quota_exceeded'})
    assert not R.Lark._rate_limited({'code': 800040832, 'message': 'quota_exceeded'})
