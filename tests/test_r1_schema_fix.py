"""Focused offline checks for the Excel-import field repair gate."""

import json
from types import SimpleNamespace

import pytest

from deploy.feishu_r1 import run_step3_schema_verify_r1 as R


def select(name, fid, options, *, multiple=False, remaining=0):
    return {'id': fid, 'name': name, 'type': 'select', 'multiple': multiple,
            'default_value': None, 'options': options,
            'remaining_options_count': remaining}


def test_pipe_alias_is_fix_only_and_ambiguous_names_fail_closed():
    pipe = select('国家|地区', 'fld-country', [{'name': '中国', 'hue': 'Blue'}], multiple=True)
    raw = {'国家|地区': pipe}
    resolved = R.resolve_imported_fields(raw, 'tbl-new')
    assert raw == {'国家|地区': pipe}
    assert resolved['国家/地区'] is pipe
    with pytest.raises(SystemExit, match='ambiguous imported field'):
        R.resolve_imported_fields(dict(raw, **{'国家/地区': select('国家/地区', 'fld-other', [])}),
                                  'tbl-new')


def test_full_select_rename_preserves_all_options_and_default(monkeypatch):
    first = [{'name': '中国', 'hue': 'Blue', 'lightness': 'Lighter'},
             {'name': '美国', 'hue': 'Gray', 'lightness': 'Lighter'}]
    current = select('国家|地区', 'fld-country', first[:1], multiple=True, remaining=1)
    current['default_value'] = ['中国']

    def fake_cli(args, **_):
        assert '+field-search-options' in args
        return {'exit_code': 0, 'body': {'ok': True, 'data': {'options': first}},
                'stderr_tail': ''}

    monkeypatch.setattr(R, 'cli', fake_cli)
    body = R.field_body('国家/地区', {'type': 'select', 'multiple': True,
                                  'options': ['中国', '美国']}, current, 'tbl-new')
    assert body == {'name': '国家/地区', 'type': 'select', 'multiple': True,
                    'default_value': ['中国'], 'options': first}


def test_rename_keeps_existing_option_order_when_target_order_differs():
    existing = [{'name': '美国', 'hue': 'Gray'}, {'name': '中国', 'hue': 'Blue'}]
    current = select('国家|地区', 'fld-country', existing, multiple=True)
    body = R.field_body('国家/地区', {'type': 'select', 'multiple': True,
                                  'options': ['中国', '美国']}, current, 'tbl-new')
    assert body['options'] == existing


def test_incomplete_or_extra_select_options_are_not_silently_removed(monkeypatch):
    current = select('国家|地区', 'fld-country', [{'name': '中国'}], multiple=True, remaining=1)
    monkeypatch.setattr(R, 'cli', lambda *_args, **_kwargs: {
        'exit_code': 0, 'body': {'ok': True, 'data': {'options': [{'name': '中国'}]}},
        'stderr_tail': ''})
    with pytest.raises(SystemExit, match='incomplete options'):
        R.field_body('国家/地区', {'type': 'select', 'multiple': True,
                                'options': ['中国', '美国']}, current, 'tbl-new')
    current['remaining_options_count'] = 0
    current['options'].append({'name': '美国', 'hue': 'Gray'})
    with pytest.raises(SystemExit, match='refusing to remove existing options'):
        R.field_body('国家/地区', {'type': 'select', 'multiple': True,
                                'options': ['中国']}, current, 'tbl-new')


def test_paginated_options_without_existing_colors_fail_closed(monkeypatch):
    current = select('国家|地区', 'fld-country',
                     [{'name': '中国', 'hue': 'Blue'}], multiple=True, remaining=1)
    monkeypatch.setattr(R, 'cli', lambda *_args, **_kwargs: {
        'exit_code': 0, 'body': {'ok': True, 'data': {
            'options': [{'name': '中国'}, {'name': '美国'}]}}, 'stderr_tail': ''})
    with pytest.raises(SystemExit, match='option metadata changed'):
        R.field_body('国家/地区', {'type': 'select', 'multiple': True,
                                'options': ['中国', '美国']}, current, 'tbl-new')


def test_schema_fix_renames_imported_field_and_adds_option_then_resumes_idempotently(
        monkeypatch, tmp_path):
    monkeypatch.setattr(R, 'WORK', tmp_path)
    monkeypatch.setattr(R, 'LIVE_ORDER', ['国家/地区', '状态'])
    target = {'国家/地区': {'type': 'select', 'multiple': True, 'options': ['中国']},
              '状态': {'type': 'select', 'multiple': False, 'options': ['open', 'removed']}}
    monkeypatch.setattr(R, 'build_target', lambda: target)
    fields = {'国家|地区': select('国家|地区', 'fld-country',
                               [{'name': '中国', 'hue': 'Blue'}], multiple=True),
              '状态': select('状态', 'fld-status', [{'name': 'open', 'hue': 'Orange'}])}
    monkeypatch.setattr(R, 'field_list', lambda _tid: fields.copy())
    updates = []

    def fake_cli(args, cwd=None, **_):
        assert '+field-update' in args and cwd == str(tmp_path)
        body = json.loads((tmp_path / args[args.index('--json') + 1][1:]).read_text())
        fid = args[args.index('--field-id') + 1]
        updates.append((fid, body))
        fields.pop('国家|地区', None) if fid == 'fld-country' else None
        fields[body['name']] = dict(body, id=fid)
        return {'exit_code': 0, 'body': {'ok': True}, 'seconds': 0.01,
                'stderr_tail': ''}

    monkeypatch.setattr(R, 'cli', fake_cli)
    run = tmp_path / 'run'
    run.mkdir()
    assert R.phase_fix([('tbl-new', '待切换-测试')], run) == 0
    assert [fid for fid, _ in updates] == ['fld-country', 'fld-status']
    assert updates[0][1]['options'] == [{'name': '中国', 'hue': 'Blue'}]
    assert updates[1][1]['options'] == [{'name': 'open', 'hue': 'Orange'}, {'name': 'removed'}]
    assert R.phase_fix([('tbl-new', '待切换-测试')], run) == 0
    assert len(updates) == 2


def test_cli_keeps_stderr_when_stdout_is_valid_error_json(monkeypatch):
    monkeypatch.setattr(R.subprocess, 'run', lambda *_args, **_kwargs: SimpleNamespace(
        stdout='{"ok": false}', stderr='supplier field error', returncode=1))
    out = R.cli(['base', '+field-update'])
    assert out['body'] == {'ok': False}
    assert out['stderr_tail'] == 'supplier field error'


def test_field_list_rejects_duplicate_names(monkeypatch):
    monkeypatch.setattr(R, 'cli', lambda *_args, **_kwargs: {
        'body': {'ok': True, 'data': {'fields': [
            {'id': 'fld-1', 'name': '国家|地区'}, {'id': 'fld-2', 'name': '国家|地区'}]}},
        'exit_code': 0})
    with pytest.raises(SystemExit, match='duplicate field name or id'):
        R.field_list('tbl-new')

@pytest.mark.parametrize('kind', ['text', 'select'])
def test_field_description_survives_rename(kind):
    current = {'id': 'f', 'name': '州|省', 'type': kind, 'description': '保留说明'}
    want = {'type': kind}
    if kind == 'select':
        current.update(options=[{'name': 'NC', 'hue': 'Blue'}], multiple=False)
        want.update(options=['NC'], multiple=False)
    else:
        current['style'] = {'type': 'plain'}
        want['style'] = 'plain'
    assert R.field_body('州/省', want, current, 'tbl-new')['description'] == '保留说明'


def staging_fixture(monkeypatch, tmp_path):
    name = '待切换-abc-岗位库'
    run = tmp_path / 'runs' / 'batch'
    run.mkdir(parents=True)
    identity = {'source_projection_sha256_gz': 'p', 'xlsx': {name: 'x'}}
    manifest = {'source_projection_sha256_gz': 'p', 'files': [{'table_name': name, 'sha256': 'x'}]}
    state = {'base_token': R.BASE, 'batch_identity': identity, 'run_dir_name': 'batch',
             'batch_pre_ids': ['tbl-official'],
             'targets': {name: {'status': 'completed', 'table_id': 'tbl-new'}}}
    receipt = {'base_token': R.BASE, 'batch_identity': identity, 'outcome': 'completed',
               'expected_target_names': [name], 'targets_bound': {name: 'tbl-new'},
               'results': [{'table_name': name, 'table_name_actual': name,
                            'status': 'imported', 'table_id': 'tbl-new'}]}
    monkeypatch.setattr(R, 'WORK', tmp_path)
    monkeypatch.setattr(R, 'RUNS', tmp_path / 'runs')
    def write():
        (tmp_path / 'xlsx-manifest.json').write_text(json.dumps(manifest))
        (tmp_path / 'import-state.json').write_text(json.dumps(state))
        (run / 'import-receipt.json').write_text(json.dumps(receipt))
    write()
    return name, run, manifest, state, receipt, write


def test_staging_allowlist_matches_batch_and_exact_binding(monkeypatch, tmp_path):
    name, run, _, _, _, _ = staging_fixture(monkeypatch, tmp_path)
    assert R.load_new_tables() == ([('tbl-new', name)], run)


@pytest.mark.parametrize('mutation', ['official', 'identity', 'binding', 'duplicate', 'missing'])
def test_staging_allowlist_rejects_unsafe_receipts(monkeypatch, tmp_path, mutation):
    name, _, manifest, state, receipt, write = staging_fixture(monkeypatch, tmp_path)
    if mutation == 'official':
        receipt['results'][0]['table_id'] = 'tbl-official'
    elif mutation == 'identity':
        receipt['batch_identity'] = {}
    elif mutation == 'binding':
        state['targets'][name]['table_id'] = 'tbl-other'
    elif mutation == 'duplicate':
        receipt['results'].append(dict(receipt['results'][0]))
    else:
        receipt['results'] = []
    write()
    with pytest.raises(SystemExit, match='staging allowlist'):
        R.load_new_tables()
