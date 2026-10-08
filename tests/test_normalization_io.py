"""Real filesystem/parser tests; the field callback is deliberately synthetic.

These tests validate I/O and the normalize_file delegation, not geography or
recruitment policy. Existing project field tests must also run on the full checkout.
"""
import ast
import errno
import io
import json
import os
from pathlib import Path
import stat

import pytest
from qiuzhao import normalization_io as nio


def fill(row, counts):
    if not row.get('normalized'):
        row['normalized'] = '确定值'
        counts['normalized'] += 1


def run(path, check=False, callback=fill):
    return nio.normalize_path(path, check=check, normalize_one=callback,
        fields=['normalized'], is_empty=lambda v: v in (None, '', []),
        metadata={'tables_loaded': False, 'company_tables': {}})


def write(path, rows):
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    return path.read_bytes()


@pytest.mark.parametrize('chunk', [1, 2, 3, 4, 7, 11, 31, 64, 1000])
def test_chunks_and_unicode(chunk):
    rows = [{'id': 'A', 'text': '引号" 反斜杠\\ 换行\n 中文😀', 'nested': [{'x': [1, None, True]}]},
            {'id': 'A'}, {}, {'anonymous': True}]
    payload = '\n ' + json.dumps(rows, ensure_ascii=False) + ' \t\r\n'
    assert list(nio.iter_records(io.StringIO(payload), chunk_chars=chunk)) == rows


@pytest.mark.parametrize('payload', ['[]', ' \n [ \t ] \r\n'])
def test_empty_array(payload):
    assert list(nio.iter_records(io.StringIO(payload), chunk_chars=1)) == []


@pytest.mark.parametrize('whitespace', [' ', '\t', '\r', '\n', ' \t\r\n'])
@pytest.mark.parametrize('chunk', [1, 7])
def test_actual_json_whitespace_accepted_at_array_boundaries(whitespace, chunk):
    payload = whitespace + '[' + whitespace + '{}' + whitespace + ',' + whitespace + '{}' + whitespace + ']' + whitespace
    assert list(nio.iter_records(io.StringIO(payload), chunk_chars=chunk)) == [{}, {}]


@pytest.mark.parametrize('suffix', ['n', 't', 'r', '\\', r'\t', r'\r', r'\n'])
def test_literal_escape_characters_are_not_trailing_json_whitespace(tmp_path, suffix):
    path = tmp_path / 'jobs.json'
    path.write_text('[{}]' + suffix, encoding='utf-8')
    original = path.read_bytes()
    with pytest.raises(nio.NormalizationInputError):
        run(path)
    assert path.read_bytes() == original
    assert list(tmp_path.glob('*.tmp')) == []


@pytest.mark.parametrize('payload', [
    '', '{}', 'null', '[1]', '[null]', '[[]]', '["s"]', '[true]',
    '[{},]', '[{}, 1]', '[{}', '[{"x":', '[{}]{}', '[{}]x',
    '[{bad}]', '[{"x":NaN}]', '[{"x":Infinity}]', '[{"x":-Infinity}]',
    '\ufeff[]', '[{}, {"x":"unterminated}]', '[{} {}]',
])
def test_invalid_json_never_replaces_input(tmp_path, payload):
    path = tmp_path / 'jobs.json'
    path.write_text(payload, encoding='utf-8')
    original = path.read_bytes()
    with pytest.raises((nio.NormalizationInputError, ValueError)):
        run(path)
    assert path.read_bytes() == original
    assert list(tmp_path.glob('*.tmp')) == []


def test_explicit_record_limit_does_not_salvage_prefix():
    payload = '[{}, {"long":"' + 'x' * 500 + '"}]'
    reader = nio.iter_records(io.StringIO(payload), chunk_chars=17, max_record_chars=100)
    assert next(reader) == {}
    with pytest.raises(nio.NormalizationInputError, match='limit'):
        list(reader)


def test_huge_closed_record_limit():
    with pytest.raises(nio.NormalizationInputError, match='exceeds'):
        list(nio.iter_records(io.StringIO('[{"x":"' + 'x' * 500 + '"}]'),
                              chunk_chars=2000, max_record_chars=100))


@pytest.mark.parametrize('chunk,limit', [(0,1), (1,0), (-1,1)])
def test_invalid_limits(chunk, limit):
    with pytest.raises(ValueError):
        list(nio.iter_records(io.StringIO('[]'), chunk_chars=chunk, max_record_chars=limit))


def test_callback_failure_rolls_back_entire_file(tmp_path):
    path = tmp_path / 'jobs.json'
    original = write(path, [{'id':'first'}, {'id':'bad'}, {'id':'last'}])
    def callback(row, counts):
        if row['id'] == 'bad':
            raise TypeError('synthetic bad field')
        fill(row, counts)
    with pytest.raises(nio.NormalizationRecordError, match='index 1') as caught:
        run(path, callback=callback)
    assert isinstance(caught.value.__cause__, TypeError)
    assert path.read_bytes() == original
    assert list(tmp_path.glob('*.tmp')) == []


def test_output_parity_order_duplicates_anonymous_and_idempotence(tmp_path):
    path = tmp_path / '岗位 空格.json'
    rows = [{'id':'same','status':'open','detail_fetch_errors':['timeout']},
            {'id':'same','normalized':'already','reviewed_at':'unchanged'}, {}]
    write(path, rows)
    expected = json.loads(json.dumps(rows))
    counts = {'normalized':0}
    for row in expected:
        fill(row, counts)
    first = run(path)
    assert path.read_bytes() == json.dumps(expected, ensure_ascii=False).encode()
    assert first['records'] == 3 and first['filled'] == counts
    assert first['input_sha256'] != first['output_sha256']
    assert first['output_sha256'] == nio.file_sha256(path)
    assert json.loads(path.read_text())[0]['detail_fetch_errors'] == ['timeout']
    bytes_after = path.read_bytes()
    second = run(path)
    assert second['filled_total'] == 0 and second['would_change_existing'] == 0
    assert path.read_bytes() == bytes_after


def test_check_creates_no_file_and_keeps_mtime(tmp_path, monkeypatch):
    path = tmp_path / 'jobs.json'
    original = write(path, [{}])
    before = path.stat()
    def refuse_temp(*a, **kw):
        raise AssertionError('check must not create a temporary file')
    monkeypatch.setattr(nio.tempfile, 'mkstemp', refuse_temp)
    result = run(path, check=True)
    assert result['written'] is False and result['check'] is True
    assert result['records'] == 1 and result['filled_total'] == 1
    assert path.read_bytes() == original and path.stat().st_mtime_ns == before.st_mtime_ns


def test_nested_existing_mutation_is_counted(tmp_path):
    path = tmp_path / 'jobs.json'
    write(path, [{'normalized':[1]}])
    def mutate(row, counts):
        row['normalized'].append(2)
        counts['normalized'] += 1
    result = run(path, callback=mutate)
    assert result['would_change_existing'] == 1


@pytest.mark.parametrize('operation', ['dump', 'fsync', 'replace', 'chmod'])
def test_os_failure_preserves_source_and_cleans_candidate(tmp_path, monkeypatch, operation):
    path = tmp_path / 'jobs.json'
    original = write(path, [{}, {}])
    def fail(*a, **kw):
        raise OSError(errno.ENOSPC if operation == 'dump' else errno.EACCES, 'injected')
    target = nio.json if operation == 'dump' else nio.os
    monkeypatch.setattr(target, operation, fail)
    with pytest.raises(OSError):
        run(path)
    assert path.read_bytes() == original
    assert list(tmp_path.glob('*.tmp')) == []


def test_non_serializable_normalized_value_keeps_source(tmp_path):
    path = tmp_path / 'jobs.json'
    original = write(path, [{}])
    def invalid(row, counts):
        row['normalized'] = {1, 2}
    with pytest.raises(TypeError):
        run(path, callback=invalid)
    assert path.read_bytes() == original
    assert list(tmp_path.glob('*.tmp')) == []


def test_detects_source_drift_without_overwriting_other_writer(tmp_path):
    path = tmp_path / 'jobs.json'
    write(path, [{'x': 1}])
    replacement = b'[{"x": 2}]'
    def other_writer(row, counts):
        path.write_bytes(replacement)
        fill(row, counts)
    with pytest.raises(nio.NormalizationInputError, match='changed'):
        run(path, callback=other_writer)
    assert path.read_bytes() == replacement
    assert list(tmp_path.glob('*.tmp')) == []


def test_regular_file_required(tmp_path):
    target = tmp_path / 'real.json'
    original = write(target, [{}])
    link = tmp_path / 'link.json'
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip('symlink creation requires platform privilege')
    with pytest.raises(nio.NormalizationInputError):
        run(link)
    assert target.read_bytes() == original


@pytest.mark.skipif(os.name == 'nt', reason='POSIX mode bits; Windows ACL test is separate')
def test_preserves_mode(tmp_path):
    path = tmp_path / 'jobs.json'
    write(path, [{}]); path.chmod(0o640)
    run(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_actual_normalize_file_entry_delegates_without_loading_whole_file(tmp_path, monkeypatch):
    # Compile the actual entry function, not a rewritten test version. Only field
    # callbacks and table-info are synthetic; the entry and all I/O are real code.
    source = Path(__file__).resolve().parents[1] / 'qiuzhao/normalize.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'normalize_file')
    class CN:
        @staticmethod
        def table_info(): return {'aliases':0}
    namespace = {'_normalize_one': fill, 'REPORTED_FIELDS':['normalized'],
                 '_is_empty':lambda v:v in (None,'',[]), '_TABLES':{}, 'CN':CN}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), 'exec'), namespace)
    path = tmp_path / 'jobs.json'; write(path, [{}, {}])
    monkeypatch.setattr(json, 'load', lambda *a,**k: (_ for _ in ()).throw(AssertionError('whole-file json.load')))
    result = namespace['normalize_file'](path)
    assert result['records'] == 2 and result['filled_total'] == 2 and result['written']


def test_long_record_is_decoded_once_after_incremental_boundary_scan(monkeypatch):
    text = ('前缀\\\\\"中文😀' * 200000) + ('\\\\\\\\尾部' * 100000)
    row = {'id': 'long', 'payload': text,
           'nested': {'items': [{'quoted': 'a}b]c\\\\\"d', 'n': [1, 2, {'x': True}]}]}}
    payload = '[' + json.dumps(row, ensure_ascii=False) + ']'
    calls = []
    original = json.JSONDecoder.raw_decode
    def counted(self, value, *args, **kwargs):
        calls.append(len(value))
        return original(self, value, *args, **kwargs)
    monkeypatch.setattr(json.JSONDecoder, 'raw_decode', counted)
    assert list(nio.iter_records(io.StringIO(payload), chunk_chars=4096,
                                 max_record_chars=len(payload) + 1)) == [row]
    assert calls == [len(payload) - 2]


def test_long_record_bad_tail_fails_after_complete_record_without_salvage(tmp_path):
    path = tmp_path / 'jobs.json'
    long_text = '合法内容} ] \\\\\" 😀' * 120000
    valid = json.dumps({'id': 'long', 'payload': long_text}, ensure_ascii=False)
    payload = '[' + valid + ', {"id":"broken","nested":[1,2,3}'
    path.write_text(payload, encoding='utf-8')
    original = path.read_bytes()
    with pytest.raises(nio.NormalizationInputError, match='record index 1'):
        run(path)
    assert path.read_bytes() == original
    assert list(tmp_path.glob('*.tmp')) == []
