"""Excel-import delivery orchestration (plan 4.2). No lark-cli call is ever made here."""
import gzip
import json
from pathlib import Path
import types

import pytest

from deploy import windows_excel_delivery as X


class Crash(BaseException):
    pass


def snapshot(tmp_path, rows=None, name='accepted.jobs.json'):
    path = tmp_path / name
    path.write_text(json.dumps(rows or [{'id': 'a', 'job_title': 't'}]), encoding='utf-8')
    return X.verified_source(path, X.digest(path), origin='test')


EMPTY_BASE = {'mode': 'empty_base', 'declared_by': 'test fixture', 'declared_at': '2026-09-23T00:00:00+08:00'}


def layout(**extra):
    # The fixture Base is declared empty; only the tests about switch overrides use tables.
    value = {'approved': True, 'base_token': X.BASE_TOKEN, 'bootstrap': EMPTY_BASE,
             'legacy_tables': [],
             'schema_source_tables': [['tblOLD1', '互联网科技岗']],
             'pre_archived': [], 'legacy_suffix': '（旧版）', 'folder_name': '待删除（旧版本）',
             'existing_table_ids': ['tblARCH'],
             'samples': [f'id-{i}' for i in range(24)]}
    value.update(extra)
    return value


class FakeRunner:
    """Stands in for the R1 scripts: local stages write manifests, external ones log calls."""

    def __init__(self, *, apply=True, fail=None, crash=None, switch_state=None, blocks=None):
        self.apply = apply
        self.calls = []
        self.fail = dict(fail or {})
        self.crash = set(crash or ())
        self.switch_state = switch_state
        self.blocks = blocks
        self.block_reads = 0

    def live_blocks(self):
        self.block_reads += 1
        if self.blocks is None:
            raise AssertionError('the live Base was read although no migration was expected')
        return self.blocks

    def local(self, stage, work, source):
        self.calls.append(stage)
        if stage == 'projection':
            with gzip.open(work / 'projection.ndjson.gz', 'wt', encoding='utf-8') as fh:
                for i in range(24):
                    fh.write(json.dumps({'g': '互联网科技岗', 'c': [f'id-{i}']}) + '\n')
            (work / 'projection-manifest.json').write_text(json.dumps(
                {'source_sha256': source['sha256'], 'columns': ['job_id'],
                 'projection_ndjson_gz': {}}))
        else:
            prefix = X.temp_prefix(source['sha256'])
            (work / 'xlsx-manifest.json').write_text(json.dumps(
                {'chunk_limit': 19500, 'files': [{'table_name': prefix + '互联网科技岗', 'group': '互联网科技岗',
                                                  'rows': 24, 'chunk_index': 0, 'sha256': 'x' * 64}]},
                ensure_ascii=False))

    def external(self, stage, work, overrides, log):
        self.calls.append(stage)
        self.last_overrides = overrides
        if stage in self.crash:
            self.crash.discard(stage)
            raise Crash(stage)
        if stage == 'import':
            (work / 'import-state.json').write_text(json.dumps(
                {'targets': {'t1': {'status': 'completed', 'table_id': 'tblNEW1'}}}))
        if stage == 'switch':
            (work / 'switch-state.json').write_text(json.dumps(self.switch_state or {'actions': {}},
                                                               ensure_ascii=False))
        code = self.fail.pop(stage, 0)
        if stage == 'switch' and code == 0:
            # What run_step4_switch_r1.py writes next to its verify receipt.
            (work / 'runs' / 'r').mkdir(parents=True, exist_ok=True)
            temps = list(overrides['OFFICIAL_BY_TEMP'])
            (work / 'runs' / 'r' / 'switch-receipt.json').write_text(json.dumps(
                {'outcome': 'completed', 'base_token': X.BASE_TOKEN,
                 'new_tables': [['tblNEW%d-%s' % (i, work.parent.name[:6]), temp] for i, temp in enumerate(temps)],
                 'temp_to_official': overrides['OFFICIAL_BY_TEMP']}, ensure_ascii=False))
        return code


def test_full_delivery_then_same_version_is_not_imported_again(tmp_path):
    source = snapshot(tmp_path)
    runner = FakeRunner()
    state = X.deliver(tmp_path / 'root', source, runner, layout=layout())
    assert state['outcome'] == 'delivered' and state['feishu_accepted_sha256'] == source['sha256']
    assert runner.calls == ['projection', 'xlsx', *X.EXTERNAL_STAGES]
    again = FakeRunner()
    result = X.deliver(tmp_path / 'root', source, again, layout=layout())
    assert result['outcome'] == 'already_delivered' and again.calls == []


def test_interruption_resumes_at_the_recorded_stage(tmp_path):
    source = snapshot(tmp_path)
    runner = FakeRunner(crash={'verify'})
    with pytest.raises(Crash):
        X.deliver(tmp_path / 'root', source, runner, layout=layout())
    state = json.loads((X.version_dir(tmp_path / 'root', source['sha256']) / 'state.json').read_text())
    assert state['stages']['verify']['status'] == 'running'
    assert state['stages']['clean_blank']['status'] == 'completed'
    resumed = FakeRunner()
    state = X.deliver(tmp_path / 'root', source, resumed, layout=layout())
    assert resumed.calls == ['verify', 'switch'], 'completed stages were repeated'
    assert state['outcome'] == 'delivered' and state['stages']['verify']['attempts'] == 2


def test_import_failure_keeps_server_and_official_tables_and_blocks_other_versions(tmp_path):
    source = snapshot(tmp_path)
    before = X.digest(source['path'])
    runner = FakeRunner(fail={'import': 1})
    state = X.deliver(tmp_path / 'root', source, runner, layout=layout())
    assert state['outcome'] == 'failed' and state['failed_stage'] == 'import'
    assert state['official_tables'] == 'unchanged' and 'switch' not in runner.calls
    assert state['cleanup_manifest'] == [{'table_name': 't1', 'table_id': 'tblNEW1', 'status': 'completed'}]
    assert X.digest(source['path']) == before
    newer = snapshot(tmp_path, [{'id': 'b', 'job_title': 't'}], name='newer.json')
    with pytest.raises(X.DeliveryError, match='still in progress'):
        X.deliver(tmp_path / 'root', newer, FakeRunner(), layout=layout())
    # Retrying the same version re-enters the failed stage only.
    retry = FakeRunner()
    assert X.deliver(tmp_path / 'root', source, retry, layout=layout())['outcome'] == 'delivered'
    assert retry.calls == list(X.EXTERNAL_STAGES[1:])


def test_abandon_releases_the_ledger_without_touching_the_base(tmp_path):
    source = snapshot(tmp_path)
    X.deliver(tmp_path / 'root', source, FakeRunner(fail={'verify': 1}), layout=layout())
    state = X.abandon(tmp_path / 'root', source['sha256'], 'superseded by a newer version')
    assert state['outcome'] == 'abandoned' and state['cleanup_manifest'][0]['table_id'] == 'tblNEW1'
    newer = snapshot(tmp_path, [{'id': 'b', 'job_title': 't'}], name='newer.json')
    assert X.deliver(tmp_path / 'root', newer, FakeRunner(), layout=layout())['outcome'] == 'delivered'


def bootstrap_empty(root):
    root.mkdir(parents=True, exist_ok=True)
    ledger = {'delivered': {}, 'active': None}
    X.bootstrap_ledger(ledger, EMPTY_BASE, [], None)
    (root / 'ledger.json').write_text(json.dumps(ledger))


def test_nothing_external_runs_without_an_approved_layout_or_apply(tmp_path):
    source = snapshot(tmp_path)
    bootstrap_empty(tmp_path / 'root')
    runner = FakeRunner()
    state = X.deliver(tmp_path / 'root', source, runner, layout=dict(layout(), approved=False))
    assert state['outcome'] == 'awaiting_layout' and runner.calls == ['projection', 'xlsx']
    runner = FakeRunner(apply=False)
    state = X.deliver(tmp_path / 'root', source, runner, layout=layout())
    assert state['outcome'] == 'awaiting_apply' and runner.calls == []
    assert state['stages']['samples']['status'] == 'completed'


def test_source_must_be_the_accepted_working_baseline(tmp_path):
    source = snapshot(tmp_path)
    receipt = tmp_path / 'receipt.json'
    receipt.write_text(json.dumps({'working_baseline': {'path': source['path'], 'sha256': 'f' * 64}}))
    with pytest.raises(X.DeliveryError, match='hash mismatch'):
        X.source_from_run_receipt(receipt)
    receipt.write_text(json.dumps({'before_sha256': source['sha256']}))
    with pytest.raises(X.DeliveryError, match='no server-accepted publication'):
        X.source_from_run_receipt(receipt)
    receipt.write_text(json.dumps({'working_baseline': {'path': source['path'], 'sha256': source['sha256']}}))
    assert X.source_from_run_receipt(receipt)['sha256'] == source['sha256']


def test_projection_of_another_version_is_refused(tmp_path):
    source = snapshot(tmp_path)

    class WrongProjection(FakeRunner):
        def local(self, stage, work, source_):
            super().local(stage, work, dict(source_, sha256='0' * 64))

    state = X.deliver(tmp_path / 'root', source, WrongProjection(), layout=layout())
    assert state['outcome'] == 'failed' and state['failed_stage'] == 'projection'


def test_switch_overrides_follow_this_version_and_the_layout():
    work = Path('/w')
    sha = 'ab' * 32
    prefix = X.temp_prefix(sha)
    manifest = {'files': [{'table_name': prefix + '互联网科技岗'}, {'table_name': prefix + '互联网科技岗·续表1'}]}
    value = X.overrides_for('switch', layout(legacy_tables=[['tblOLD1', '互联网科技岗']]), work, sha, manifest)
    assert value['OFFICIAL_ORDER'] == ['互联网科技岗', '互联网科技岗·续表1']
    assert value['OFFICIAL_BY_TEMP'][prefix + '互联网科技岗·续表1'] == '互联网科技岗·续表1'
    assert set(value['LEGACY_IDS']) == {'tblOLD1', 'tblARCH'}
    assert X.overrides_for('schema_snapshot', layout(), work, sha)['OUT'] == '/w/prod-schema-snapshot.json'


def test_overrides_refuse_another_base_and_unknown_constants():
    module = types.SimpleNamespace(__name__='m', BASE='other', LEGACY_IDS=set())
    with pytest.raises(X.DeliveryError, match='another Base'):
        X.apply_overrides(module, {'LEGACY_IDS': []})
    module.BASE = X.BASE_TOKEN
    with pytest.raises(X.DeliveryError, match='no constant'):
        X.apply_overrides(module, {'NOT_THERE': 1})
    X.apply_overrides(module, {'LEGACY_IDS': ['a']})
    assert module.LEGACY_IDS == {'a'}


def test_draft_policy_is_never_approved(tmp_path):
    draft = X.draft_policy(r1_evidence(tmp_path, 'c' * 64))
    assert draft['approved'] is False and draft['initial_official_tables'] == [['tblR1', '互联网科技岗']]
    assert draft['bootstrap']['official_sha256'] == 'c' * 64
    with pytest.raises(X.DeliveryError, match='not approved'):
        X.checked_policy(draft)


@pytest.mark.skipif(not X.DEFAULT_SCRIPTS.is_dir(), reason='R1 scripts not on this machine')
def test_real_r1_projection_and_xlsx_run_unmodified_on_a_fixture(tmp_path):
    pytest.importorskip('openpyxl')
    rows = [{'id': f'job-{i}', 'job_title': f'岗位{i}', 'company': '测试公司',
             'industry': '互联网/科技' if i % 2 else '制造/工业', 'status': 'open',
             'source_url': f'https://example.com/{i}', 'application_url': f'https://example.com/{i}/apply',
             'reviewed_at': '2026-09-23T08:00:00+08:00'} for i in range(30)]
    source = snapshot(tmp_path, rows)
    runner = X.ScriptRunner(X.DEFAULT_SCRIPTS, apply=False)
    state = X.deliver(tmp_path / 'root', source, runner,
                      layout=layout(samples=None, sample_rule=X.SAMPLE_RULE))
    assert state['outcome'] == 'awaiting_apply', state
    work = X.version_dir(tmp_path / 'root', source['sha256']) / 'work'
    projection = json.loads((work / 'projection-manifest.json').read_text(encoding='utf-8'))
    assert projection['source_sha256'] == source['sha256'] and projection['rows_written'] == 30
    xlsx = json.loads((work / 'xlsx-manifest.json').read_text(encoding='utf-8'))
    assert sum(item['rows'] for item in xlsx['files']) == 30
    assert all(item['table_name'].startswith(X.temp_prefix(source['sha256'])) for item in xlsx['files'])
    samples = json.loads((work / 'samples24.json').read_text(encoding='utf-8'))
    assert len({s['id'] for s in samples}) == 24
    # Deterministic: the same version always proposes the same samples.
    assert state['stages']['samples']['sample_ids'] == X.choose_samples(
        work, layout(samples=None, sample_rule=X.SAMPLE_RULE), source['sha256'])


def test_external_stage_runs_the_script_in_a_child_with_overrides_and_work_env(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / X.SCRIPT['import']).write_text(
        'import json, os, sys\n'
        f'BASE = {X.BASE_TOKEN!r}\n'
        'LEGACY_IDS = set()\n'
        'def main():\n'
        '    out = {"legacy": sorted(LEGACY_IDS), "work": os.environ["EXCEL_IMPORT_WORK"], "argv": sys.argv[1:]}\n'
        '    open(os.path.join(os.environ["EXCEL_IMPORT_WORK"], "seen.json"), "w").write(json.dumps(out))\n'
        '    return 0\n', encoding='utf-8')
    work = tmp_path / 'work'
    work.mkdir()
    runner = X.ScriptRunner(scripts, apply=True)
    assert runner.external('import', work, {'LEGACY_IDS': ['tblA', 'tblB']}, tmp_path / 'import.log') == 0
    seen = json.loads((work / 'seen.json').read_text())
    assert seen == {'legacy': ['tblA', 'tblB'], 'work': str(work), 'argv': []}
    with pytest.raises(X.DeliveryError, match='requires --apply'):
        X.ScriptRunner(scripts, apply=False).external('import', work, {}, tmp_path / 'import.log')


# --- review round 2 ----------------------------------------------------------------

def lineage_source(tmp_path, name, rows, parent=None, lineage=None):
    path = tmp_path / name
    path.write_text(json.dumps(rows), encoding='utf-8')
    sha = X.digest(path)
    edges = dict(lineage or {})
    if parent:
        edges[sha] = parent
    return X.verified_source(path, sha, origin='test', lineage=edges)


def test_an_older_accepted_version_never_replaces_a_newer_delivery(tmp_path):
    a = lineage_source(tmp_path, 'a.json', [{'id': 'a'}])
    b = lineage_source(tmp_path, 'b.json', [{'id': 'b'}], parent=a['sha256'])
    assert X.deliver(tmp_path / 'root', b, FakeRunner(), layout=layout())['outcome'] == 'delivered'
    runner = FakeRunner()
    with pytest.raises(X.DeliveryError, match='older than the delivered'):
        X.deliver(tmp_path / 'root', a, runner, layout=layout(legacy_tables=None))
    assert runner.calls == []
    unrelated = lineage_source(tmp_path, 'u.json', [{'id': 'u'}])
    with pytest.raises(X.DeliveryError, match='cannot prove'):
        X.deliver(tmp_path / 'root', unrelated, FakeRunner(), layout=layout())
    ledger = json.loads((tmp_path / 'root' / 'ledger.json').read_text())
    assert ledger['last_delivered'] == b['sha256'] and ledger['active'] is None


def test_abandon_a_then_deliver_b_then_a_is_refused(tmp_path):
    a = lineage_source(tmp_path, 'a.json', [{'id': 'a'}])
    b = lineage_source(tmp_path, 'b.json', [{'id': 'b'}], parent=a['sha256'])
    X.deliver(tmp_path / 'root', a, FakeRunner(fail={'verify': 1}), layout=layout())
    X.abandon(tmp_path / 'root', a['sha256'], 'newer version available')
    assert X.deliver(tmp_path / 'root', b, FakeRunner(), layout=layout())['outcome'] == 'delivered'
    with pytest.raises(X.DeliveryError, match='older than the delivered'):
        X.deliver(tmp_path / 'root', a, FakeRunner(), layout=layout())


def test_descendant_version_is_delivered_against_the_tables_the_last_switch_made_official(tmp_path):
    a = lineage_source(tmp_path, 'a.json', [{'id': 'a'}])
    b = lineage_source(tmp_path, 'b.json', [{'id': 'b'}], parent=a['sha256'])
    c = lineage_source(tmp_path, 'c.json', [{'id': 'c'}], parent=b['sha256'],
                       lineage={b['sha256']: a['sha256']})
    policy = approved_policy(tmp_path, a['sha256'])
    first = FakeRunner()
    assert X.deliver(tmp_path / 'root', b, first, policy=policy)['outcome'] == 'delivered'
    assert first.last_overrides['LEGACY_TABLES'] == [['tblR1', '互联网科技岗']]
    assert first.last_overrides['LEGACY_SUFFIX'] == '（20260923-%s版）' % a['sha256'][:8]
    ledger = json.loads((tmp_path / 'root' / 'ledger.json').read_text())
    second = FakeRunner()
    assert X.deliver(tmp_path / 'root', c, second, policy=policy)['outcome'] == 'delivered'
    assert second.last_overrides['LEGACY_TABLES'] == ledger['official_tables']
    assert second.last_overrides['LEGACY_SUFFIX'] == '（%s-%s版）' % (ledger['official_since_date'], b['sha256'][:8])
    assert {'tblR1', 'tblARCH'} <= set(second.last_overrides['LEGACY_IDS'])
    # An explicit layout that disagrees with what is actually official is refused.
    d = lineage_source(tmp_path, 'd.json', [{'id': 'd'}], parent=c['sha256'])
    state = X.deliver(tmp_path / 'root', d, FakeRunner(), layout=layout())
    assert state['outcome'] == 'awaiting_layout' and 'last delivery made official' in state['blocked']['reason']


def test_unapproved_policy_is_refused_before_anything_runs(tmp_path):
    source = snapshot(tmp_path)
    runner = FakeRunner()
    with pytest.raises(X.DeliveryError, match='policy is not approved'):
        X.deliver(tmp_path / 'root', source, runner, policy={'approved': False, 'base_token': X.BASE_TOKEN})
    assert runner.calls == []


def test_unapproved_policy_after_bootstrap_blocks_external_stages_only(tmp_path):
    source = snapshot(tmp_path)
    bootstrap_empty(tmp_path / 'root')
    runner = FakeRunner()
    state = X.deliver(tmp_path / 'root', source, runner, policy={'approved': False, 'base_token': X.BASE_TOKEN})
    assert state['outcome'] == 'awaiting_layout' and 'policy is not approved' in state['blocked']['reason']
    assert runner.calls == ['projection', 'xlsx']


def test_a_started_switch_cannot_be_abandoned_only_resumed(tmp_path):
    source = snapshot(tmp_path)
    state = X.deliver(tmp_path / 'root', source, FakeRunner(fail={'switch': 1}), layout=layout())
    assert state['outcome'] == 'failed' and state['failed_stage'] == 'switch'
    assert 'partly applied' in state['official_tables']
    with pytest.raises(X.DeliveryError, match='switch already started'):
        X.abandon(tmp_path / 'root', source['sha256'], 'try something else')
    retry = FakeRunner()
    assert X.deliver(tmp_path / 'root', source, retry, layout=layout())['outcome'] == 'delivered'
    assert retry.calls == ['switch']


def test_a_crashed_switch_cannot_be_abandoned(tmp_path):
    source = snapshot(tmp_path)
    with pytest.raises(Crash):
        X.deliver(tmp_path / 'root', source, FakeRunner(crash={'switch'}), layout=layout())
    with pytest.raises(X.DeliveryError, match='switch already started'):
        X.abandon(tmp_path / 'root', source['sha256'], 'crash')


def test_manifest_source_resolves_via_mount_or_configured_fetch_and_checks_the_hash(tmp_path, monkeypatch):
    from deploy import windows_collector as W
    collector = tmp_path / 'collector'
    artifact = collector / 'runs' / 'day' / 'rebase' / 'x' / 'candidate.jobs.json'
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps([{'id': 'a', 'job_title': 't'}]))
    sha = X.digest(artifact)
    monkeypatch.setattr(W, 'ROOT', collector)
    record = {'artifact': str(artifact), 'sha256': sha, 'accepted_at': 'now',
              'lineage_edges': [[sha, 'p' * 64]]}
    W.record_accepted_version({}, collector / 'runs' / 'day', record)
    manifest = json.loads((collector / 'data' / 'accepted-versions' / 'latest.json').read_text())
    # The Mac sees the manifest with Windows paths: move the tree to simulate that.
    moved = tmp_path / 'mount'
    collector.rename(moved)
    copy = tmp_path / 'latest.json'
    copy.write_text(json.dumps(manifest))
    with pytest.raises(X.DeliveryError, match='no fetch command'):
        X.source_from_manifest(copy, cache_dir=tmp_path / 'cache')
    mounted = X.source_from_manifest(copy, cache_dir=tmp_path / 'cache', artifact_root=moved)
    assert mounted['sha256'] == sha and mounted['lineage'] == {sha: 'p' * 64}
    remote = moved / manifest['artifact_relpath']
    fetch = [sys_executable(), '-c', 'import shutil,sys; shutil.copyfile(sys.argv[1], sys.argv[2])',
             str(remote), '{local}']
    fetched = X.source_from_manifest(copy, cache_dir=tmp_path / 'cache', fetch_command=fetch)
    assert fetched['sha256'] == sha and 'fetched' in fetched['origin']
    bad = tmp_path / 'bad.json'
    bad.write_text('[]')
    (tmp_path / 'cache' / (sha + '.jobs.json')).unlink()
    wrong = [sys_executable(), '-c', 'import shutil,sys; shutil.copyfile(sys.argv[1], sys.argv[2])',
             str(bad), '{local}']
    with pytest.raises(X.DeliveryError, match='does not match'):
        X.source_from_manifest(copy, cache_dir=tmp_path / 'cache', fetch_command=wrong)


def sys_executable():
    import sys
    return sys.executable


def real_r1_work(tmp_path, titles, name='work'):
    pytest.importorskip('openpyxl')
    rows = [{'id': f'job-{i}', 'job_title': title, 'company': '测试公司', 'industry': '互联网/科技',
             'status': 'open', 'source_url': f'https://example.com/{i}',
             'application_url': f'https://example.com/{i}/apply', 'reviewed_at': '2026-09-23T08:00:00+08:00'}
            for i, title in enumerate(titles)]
    source = snapshot(tmp_path, rows, name=name + '.json')
    work = tmp_path / name
    work.mkdir()
    runner = X.ScriptRunner(X.DEFAULT_SCRIPTS)
    runner.local('projection', work, source)
    runner.local('xlsx', work, source)
    return work


def real_verify_module(work, monkeypatch, *, generic=True):
    monkeypatch.setenv('EXCEL_IMPORT_WORK', str(work))
    module = X.load_script(X.DEFAULT_SCRIPTS / X.SCRIPT['verify'], 'r1_verify_' + work.name)
    if generic:
        X.apply_overrides(module, {X.GENERIC_WHITELIST: True})
    return module


@pytest.mark.skipif(not X.DEFAULT_SCRIPTS.is_dir(), reason='R1 scripts not on this machine')
@pytest.mark.parametrize('dirty', [0, 1, 2])
def test_real_r1_verify_accepts_any_number_of_sanitised_cells(tmp_path, monkeypatch, dirty):
    titles = [f'岗位{i}' for i in range(30)]
    for i in range(dirty):
        titles[i * 7] = f'英语翻译\x08/岗位{i}'
    work = real_r1_work(tmp_path, titles)
    report = json.loads((work / 'illegal-character-report.json').read_text())
    assert report['cells_with_illegal_chars'] == dirty and len(report['hits']) == dirty
    proj, xml, per_group, whitelist = real_verify_module(work, monkeypatch).load_expected()
    assert whitelist['hits'] == dirty
    cleaned = [row['岗位名称'] for rows in per_group.values() for row in rows]
    assert not any('\x08' in title for title in cleaned)
    # The unmodified R1 function is what the review found: it only accepts exactly one.
    original = real_verify_module(work, monkeypatch, generic=False)
    if dirty == 1:
        original.load_expected()
    else:
        with pytest.raises(SystemExit):
            original.load_expected()


@pytest.mark.skipif(not X.DEFAULT_SCRIPTS.is_dir(), reason='R1 scripts not on this machine')
def test_real_r1_verify_refuses_a_report_that_does_not_match_the_xlsx_build(tmp_path, monkeypatch):
    titles = [f'岗位{i}' for i in range(30)]
    titles[3] = 'a\x08b'
    titles[9] = 'c\x0bd'
    work = real_r1_work(tmp_path, titles)
    report = json.loads((work / 'illegal-character-report.json').read_text())
    report['hits'] = report['hits'][:1]
    report['cells_with_illegal_chars'] = 1
    (work / 'illegal-character-report.json').write_text(json.dumps(report))
    with pytest.raises(SystemExit, match='sanitised-cell count'):
        real_verify_module(work, monkeypatch).load_expected()


@pytest.mark.skipif(not X.DEFAULT_SCRIPTS.is_dir(), reason='R1 scripts not on this machine')
def test_a_cell_excel_would_truncate_is_refused_before_import(tmp_path):
    titles = [f'岗位{i}' for i in range(30)]
    titles[0] = '长' * (X.EXCEL_CELL_LIMIT + 10)
    with pytest.raises(X.DeliveryError, match='truncated'):
        real_r1_work(tmp_path, titles)


# --- first use against an existing Base -------------------------------------------

def r1_evidence(tmp_path, official_sha, tables=(('tblR1', '互联网科技岗'),), **tamper):
    """The R1 receipt chain as the real scripts write it (switch -> verify -> import + projection)."""
    work = tmp_path / 'r1' / 'work'
    run = work / 'runs' / '20260923T105111'
    run.mkdir(parents=True, exist_ok=True)
    projection_gz = 'e' * 64
    temps = {'待切换-20260923-' + name: name for _, name in tables}
    files = {
        'projection': (work / 'projection-manifest.json',
                       {'source_sha256': official_sha, 'projection_ndjson_gz': {'sha256_gz': projection_gz}}),
        'import': (run / 'import-receipt.json',
                   {'step': 'import', 'base_token': X.BASE_TOKEN, 'outcome': 'completed',
                    'batch_identity': {'source_projection_sha256_gz': projection_gz},
                    'targets_bound': {'待切换-20260923-' + name: tid for tid, name in tables}}),
        'verify': (run / 'verify-receipt.json',
                   {'step': 'verify', 'base_token': X.BASE_TOKEN, 'outcome': 'completed', 'gate_passed': True,
                    'source_projection_sha256_gz': projection_gz, 'projection_sha256_on_disk': projection_gz,
                    'projection_manifest': str(work / 'projection-manifest.json'),
                    'import_receipt': str(run / 'import-receipt.json')}),
        'switch': (run / 'switch-receipt.json',
                   {'step': 'switch', 'base_token': X.BASE_TOKEN, 'outcome': 'completed',
                    'verify_receipt': str(run / 'verify-receipt.json'),
                    'import_receipt': str(run / 'import-receipt.json'),
                    'new_tables': [[tid, '待切换-20260923-' + name] for tid, name in tables],
                    'temp_to_official': temps}),
    }
    for key, (path, body) in files.items():
        body.update(tamper.get(key, {}))
        path.write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
    return run / 'switch-receipt.json'


def approved_policy(tmp_path, official_sha, **tamper):
    policy = X.draft_policy(r1_evidence(tmp_path, official_sha, **tamper))
    policy.update(approved=True, initial_official_date='20260923', legacy_suffix_template='（{version_date}版）',
                  folder_name='待删除（旧版本）', protected_table_ids=['tblARCH'], sample_rule=X.SAMPLE_RULE)
    return policy


def test_empty_local_ledger_is_not_an_empty_base(tmp_path):
    runner = FakeRunner()
    with pytest.raises(X.DeliveryError, match='never bootstrapped'):
        X.deliver(tmp_path / 'root', snapshot(tmp_path), runner, layout=dict(layout(), bootstrap=None))
    assert runner.calls == [] and not (tmp_path / 'root' / 'ledger.json').exists()


def test_existing_base_first_delivery_refuses_an_older_accepted_version(tmp_path):
    older = lineage_source(tmp_path, 'older.json', [{'id': 'old'}])
    official = lineage_source(tmp_path, 'official.json', [{'id': 'r1'}], parent=older['sha256'])
    runner = FakeRunner()
    # Without lineage reaching the official version the older snapshot cannot be placed: refused.
    with pytest.raises(X.DeliveryError, match='cannot prove'):
        X.deliver(tmp_path / 'root', older, runner, policy=approved_policy(tmp_path, official['sha256']))
    assert runner.calls == []
    # With the collector's cumulative lineage it is recognised as older: refused as such.
    known = dict(older, lineage={official['sha256']: older['sha256']})
    with pytest.raises(X.DeliveryError, match='older than the delivered'):
        X.deliver(tmp_path / 'root', known, runner, policy=approved_policy(tmp_path, official['sha256']))
    assert runner.calls == []
    ledger = json.loads((tmp_path / 'root' / 'ledger.json').read_text())
    assert ledger['last_delivered'] == official['sha256'] and ledger['bootstrap']['mode'] == 'existing_base'
    assert ledger['official_tables'] == [['tblR1', '互联网科技岗']]
    unrelated = lineage_source(tmp_path, 'unrelated.json', [{'id': 'u'}])
    with pytest.raises(X.DeliveryError, match='cannot prove'):
        X.deliver(tmp_path / 'root', unrelated, FakeRunner(), policy=approved_policy(tmp_path, official['sha256']))
    # The version already in the Base is not imported again.
    same = X.deliver(tmp_path / 'root', official, FakeRunner(), policy=approved_policy(tmp_path, official['sha256']))
    assert same['outcome'] == 'already_delivered'


def test_existing_base_first_delivery_allows_a_reachable_successor(tmp_path):
    official = lineage_source(tmp_path, 'official.json', [{'id': 'r1'}])
    newer = lineage_source(tmp_path, 'newer.json', [{'id': 'n'}], parent=official['sha256'])
    runner = FakeRunner()
    state = X.deliver(tmp_path / 'root', newer, runner, policy=approved_policy(tmp_path, official['sha256']))
    assert state['outcome'] == 'delivered'
    assert runner.last_overrides['LEGACY_TABLES'] == [['tblR1', '互联网科技岗']]


def test_true_empty_base_must_be_declared(tmp_path):
    with pytest.raises(X.DeliveryError, match='declared_by'):
        X.deliver(tmp_path / 'root', snapshot(tmp_path), FakeRunner(),
                  layout=layout(bootstrap={'mode': 'empty_base'}))
    with pytest.raises(X.DeliveryError, match='cannot list official tables'):
        X.deliver(tmp_path / 'root', snapshot(tmp_path), FakeRunner(),
                  layout=layout(legacy_tables=[['tblR1', '互联网科技岗']]))
    state = X.deliver(tmp_path / 'root', snapshot(tmp_path), FakeRunner(), layout=layout())
    assert state['outcome'] == 'delivered'
    ledger = json.loads((tmp_path / 'root' / 'ledger.json').read_text())
    assert ledger['bootstrap']['declared_by'] == 'test fixture'


@pytest.mark.parametrize('tamper, message', [
    ({'verify': {'gate_passed': False}}, 'did not pass its gate'),
    ({'switch': {'base_token': 'another'}}, 'another Base|not a completed switch of this Base'),
    ({'projection': {'projection_ndjson_gz': {'sha256_gz': 'f' * 64}}}, 'not the verified projection'),
    ({'import': {'targets_bound': {'x': 'tblOTHER'}}}, 'bound other tables'),
    ({'import': {'batch_identity': {'source_projection_sha256_gz': 'f' * 64}}}, 'completed import of that projection'),
])
def test_bootstrap_evidence_that_does_not_hold_together_is_refused(tmp_path, tamper, message):
    official = lineage_source(tmp_path, 'official.json', [{'id': 'r1'}])
    with pytest.raises(X.DeliveryError, match=message):
        X.deliver(tmp_path / 'root', official, FakeRunner(), policy=approved_policy(tmp_path, official['sha256'], **tamper))
    assert not (tmp_path / 'root' / 'ledger.json').exists()


def test_bootstrap_rejects_a_claimed_sha_the_evidence_does_not_support_or_swapped_files(tmp_path):
    official = lineage_source(tmp_path, 'official.json', [{'id': 'r1'}])
    policy = approved_policy(tmp_path, official['sha256'])
    forged = dict(policy, bootstrap=dict(policy['bootstrap'], official_sha256='a' * 64))
    with pytest.raises(X.DeliveryError, match='official_sha256 is not the source'):
        X.deliver(tmp_path / 'root', official, FakeRunner(), policy=forged)
    swapped = tmp_path / 'r1' / 'work' / 'projection-manifest.json'
    swapped.write_text(json.dumps({'source_sha256': 'a' * 64}))
    with pytest.raises(X.DeliveryError, match='changed since approval'):
        X.deliver(tmp_path / 'root', official, FakeRunner(), policy=policy)
    Path(policy['bootstrap']['evidence']['verify_receipt']['path']).unlink()
    with pytest.raises(X.DeliveryError, match='evidence missing'):
        X.deliver(tmp_path / 'root', official, FakeRunner(), policy=policy)
    no_bootstrap = {k: v for k, v in policy.items() if k != 'bootstrap'}
    with pytest.raises(X.DeliveryError, match='policy field missing: bootstrap'):
        X.deliver(tmp_path / 'root', official, FakeRunner(), policy=no_bootstrap)


REAL_SWITCH = Path('/Users/maxzhl/Projects/mcp-suite-recovery-20260921/feishu-20260923/work/runs/'
                   '20260923T105111/switch-receipt.json')


@pytest.mark.skipif(not REAL_SWITCH.is_file(), reason='R1 receipts not on this machine')
def test_real_r1_receipts_bind_the_current_official_version(tmp_path):
    """Read-only: the 2026-09-23 receipt chain proves c963aeff... is what the Base shows."""
    draft = X.draft_policy(REAL_SWITCH)
    assert draft['approved'] is False
    assert draft['bootstrap']['official_sha256'] == \
        'c963aeffe542a8ca751092d35af66075e015650ddb86105808920c4433e398ee'
    summary = X.verify_bootstrap(draft['bootstrap'], draft['initial_official_tables'])
    assert summary['projection_sha256_gz'] == '0ce5a88954dec7876951c4cc3eb48c1d42781dd0dbc495eb75155bf499ab041e'
    assert len(draft['initial_official_tables']) == 10


def test_bootstrap_verification_itself_rejects_a_switch_of_another_base(tmp_path):
    official = 'c' * 64
    good = X.draft_policy(r1_evidence(tmp_path, official))
    switch = Path(good['bootstrap']['evidence']['switch_receipt']['path'])
    body = json.loads(switch.read_text())
    body['base_token'] = 'another'
    switch.write_text(json.dumps(body, ensure_ascii=False))
    bootstrap = dict(good['bootstrap'], evidence=dict(good['bootstrap']['evidence'],
                     switch_receipt={'path': str(switch), 'sha256': X.digest(switch)}))
    with pytest.raises(X.DeliveryError, match='not a completed switch of this Base'):
        X.verify_bootstrap(bootstrap, good['initial_official_tables'])


# --- archive names unique per outgoing version (2026-09-24 bd4f switch collision) ----------

def chain(tmp_path, count):
    sources, lineage = [], {}
    for i in range(count):
        parent = sources[-1]['sha256'] if sources else None
        sources.append(lineage_source(tmp_path, f'v{i}.json', [{'id': f'v{i}'}], parent=parent, lineage=lineage))
        if parent:
            lineage[sources[-1]['sha256']] = parent
    return sources


def test_same_day_deliveries_archive_under_distinct_stable_names(tmp_path):
    a, b, c, d = chain(tmp_path, 4)
    policy = approved_policy(tmp_path, a['sha256'])
    suffixes = []
    for source in (b, c, d):
        runner = FakeRunner()
        assert X.deliver(tmp_path / 'root', source, runner, policy=policy)['outcome'] == 'delivered'
        suffixes.append(runner.last_overrides['LEGACY_SUFFIX'])
    # c and d both replace tables that became official today; the old date-only name collided.
    today = json.loads((tmp_path / 'root' / 'ledger.json').read_text())['official_since_date']
    assert suffixes == ['（20260923-%s版）' % a['sha256'][:8], '（%s-%s版）' % (today, b['sha256'][:8]),
                        '（%s-%s版）' % (today, c['sha256'][:8])]
    assert len(set(suffixes)) == 3


def test_a_retried_switch_keeps_its_archive_name_without_reading_the_base(tmp_path):
    a, b = chain(tmp_path, 2)
    policy = approved_policy(tmp_path, a['sha256'])
    first = FakeRunner(fail={'switch': 1})
    assert X.deliver(tmp_path / 'root', b, first, policy=policy)['outcome'] == 'failed'
    retry = FakeRunner()
    assert X.deliver(tmp_path / 'root', b, retry, policy=policy)['outcome'] == 'delivered'
    assert retry.last_overrides['LEGACY_SUFFIX'] == first.last_overrides['LEGACY_SUFFIX']
    assert retry.calls == ['switch'] and retry.block_reads == 0
    state = json.loads((X.version_dir(tmp_path / 'root', b['sha256']) / 'state.json').read_text())
    assert 'switch_layout_migrations' not in state


OLD_SUFFIX = '（20260923版）'


def failed_under_old_layout(tmp_path, monkeypatch, actions=None, folder_id=None):
    """b's switch failed on its first legacy rename while the date-only name was in use."""
    a, b = chain(tmp_path, 2)
    policy = approved_policy(tmp_path, a['sha256'])
    with monkeypatch.context() as patched:
        patched.setattr(X, 'archive_suffix', lambda template, since, outgoing: template.format(version_date=since))
        switch_state = {'actions': actions or {'rename_legacy:tblR1': {'ok': False}}, 'folder_id': folder_id,
                        'critical_failure': 'legacy rename failed for tblR1',
                        'batch': {'legacy': [['tblR1', '互联网科技岗']], 'pre_archived': [],
                                  'new_tables': [['tblNEW1', 't1']]}}
        runner = FakeRunner(fail={'switch': 1}, switch_state=switch_state)
        state = X.deliver(tmp_path / 'root', b, runner, policy=policy)
    assert state['outcome'] == 'failed' and state['switch_layout']['legacy_suffix'] == OLD_SUFFIX
    assert runner.last_overrides['LEGACY_SUFFIX'] == OLD_SUFFIX
    return a, b, policy, switch_state


UNTOUCHED_BASE = [{'id': 'tblR1', 'name': '互联网科技岗', 'parent_id': None},
                  {'id': 'tblNEW1', 'name': 't1', 'parent_id': None},
                  {'id': 'tblD516', 'name': '互联网科技岗' + OLD_SUFFIX, 'parent_id': 'fldOLD'}]


def state_of(tmp_path, source):
    return json.loads((X.version_dir(tmp_path / 'root', source['sha256']) / 'state.json').read_text())


def test_switch_that_failed_before_any_rename_resumes_under_the_new_name_without_reimport(tmp_path, monkeypatch):
    a, b, policy, switch_state = failed_under_old_layout(tmp_path, monkeypatch)
    retry = FakeRunner(switch_state=switch_state, blocks=UNTOUCHED_BASE)
    state = X.deliver(tmp_path / 'root', b, retry, policy=policy)
    assert state['outcome'] == 'delivered' and state['feishu_accepted_sha256'] == b['sha256']
    assert retry.calls == ['switch'], 'nothing before the switch may run again'
    new = '（20260923-%s版）' % a['sha256'][:8]
    assert retry.last_overrides['LEGACY_SUFFIX'] == new and state['switch_layout']['legacy_suffix'] == new
    [migration] = state['switch_layout_migrations']
    assert (migration['from_suffix'], migration['to_suffix']) == (OLD_SUFFIX, new)
    assert migration['source_sha256'] == migration['ledger_active'] == b['sha256']
    assert migration['ledger_last_delivered'] == a['sha256']
    assert migration['checked_outgoing_tables'] == migration['checked_temporary_tables'] == 1
    assert all(len(migration[k]) == 64 for k in ('state_sha256_before', 'switch_state_sha256',
                                                 'import_state_sha256', 'live_blocks_sha256'))
    # Anti-regression still holds once delivered.
    older = lineage_source(tmp_path, 'older.json', [{'id': 'older'}])
    known = dict(older, lineage={a['sha256']: older['sha256']})
    with pytest.raises(X.DeliveryError, match='older than the delivered'):
        X.deliver(tmp_path / 'root', known, FakeRunner(), policy=policy)


@pytest.mark.parametrize('actions, folder_id, blocks, message', [
    ({'rename_legacy:tblR1': {'ok': True}}, None,
     [{'id': 'tblR1', 'name': '互联网科技岗' + OLD_SUFFIX, 'parent_id': None},
      {'id': 'tblNEW1', 'name': 't1', 'parent_id': None}], 'switch already applied actions'),
    (None, 'fldNEW', UNTOUCHED_BASE, 'archive folder'),
    # Nothing recorded, but the Base shows a rename or a move happened anyway.
    (None, None, [{'id': 'tblR1', 'name': '互联网科技岗' + OLD_SUFFIX, 'parent_id': None},
                  {'id': 'tblNEW1', 'name': 't1', 'parent_id': None}], 'table tblR1 is not at the Base root'),
    (None, None, [{'id': 'tblR1', 'name': '互联网科技岗', 'parent_id': 'fldX'},
                  {'id': 'tblNEW1', 'name': 't1', 'parent_id': None}], 'table tblR1 is not at the Base root'),
    (None, None, [{'id': 'tblR1', 'name': '互联网科技岗', 'parent_id': None},
                  {'id': 'tblNEW1', 'name': '互联网科技岗', 'parent_id': None}], 'table tblNEW1 is not'),
    (None, None, [{'id': 'tblR1', 'name': '互联网科技岗', 'parent_id': None}], 'table tblNEW1 is not'),
])
def test_any_partial_switch_refuses_the_migration(tmp_path, monkeypatch, actions, folder_id, blocks, message):
    a, b, policy, _ = failed_under_old_layout(tmp_path, monkeypatch, actions=actions, folder_id=folder_id)
    before = state_of(tmp_path, b)
    retry = FakeRunner(blocks=blocks)
    with pytest.raises(X.DeliveryError, match='resume with the original layout') as refused:
        X.deliver(tmp_path / 'root', b, retry, policy=policy)
    assert message in str(refused.value)
    assert retry.calls == [], 'no switch may run under a migrated layout'
    after = state_of(tmp_path, b)
    assert after['switch_layout'] == before['switch_layout'] and after['stages'] == before['stages']
    assert after['switch_layout']['legacy_suffix'] == OLD_SUFFIX and 'switch_layout_migrations' not in after
    # The started switch still cannot be abandoned; the old layout remains resumable.
    with pytest.raises(X.DeliveryError, match='switch already started'):
        X.abandon(tmp_path / 'root', b['sha256'], 'give up')


def test_identity_mismatches_refuse_the_migration(tmp_path, monkeypatch):
    a, b, policy, switch_state = failed_under_old_layout(tmp_path, monkeypatch)
    path = X.version_dir(tmp_path / 'root', b['sha256']) / 'state.json'
    work = path.parent / 'work'
    state = json.loads(path.read_text())
    ledger = json.loads((tmp_path / 'root' / 'ledger.json').read_text())
    frozen = state['switch_layout']
    wanted = dict(frozen, legacy_suffix='（20260923-%s版）' % a['sha256'][:8])
    runner = FakeRunner(blocks=UNTOUCHED_BASE)
    assert X.migrate_switch_layout(state, frozen, wanted, work, ledger, b['sha256'], runner)['to_suffix'] == \
        wanted['legacy_suffix']
    cases = {
        'another source version': dict(sha=a['sha256']),
        'active delivery': dict(ledger=dict(ledger, active=a['sha256'])),
        'ledger official tables': dict(ledger=dict(ledger, official_tables=[['tblOTHER', '互联网科技岗']])),
        'outgoing tables differ': dict(wanted=dict(wanted, legacy_tables=[['tblOTHER', '互联网科技岗']])),
        'archive folder differs': dict(wanted=dict(wanted, folder_name='别的文件夹')),
        'verify gate': dict(state=dict(state, stages=dict(state['stages'], verify={'status': 'failed'}))),
    }
    for message, change in cases.items():
        with pytest.raises(X.DeliveryError, match=message):
            X.migrate_switch_layout(change.get('state', state), frozen, change.get('wanted', wanted), work,
                                    change.get('ledger', ledger), change.get('sha', b['sha256']), runner)
    for key, value, message in [('new_tables', [['tblNEW9', 't1']], 'other temporary tables'),
                                ('legacy', [['tblOTHER', '互联网科技岗']], 'other outgoing tables')]:
        tampered = dict(switch_state, batch=dict(switch_state['batch'], **{key: value}))
        (work / 'switch-state.json').write_text(json.dumps(tampered, ensure_ascii=False))
        with pytest.raises(X.DeliveryError, match=message):
            X.migrate_switch_layout(state, frozen, wanted, work, ledger, b['sha256'], runner)
    # Through deliver: a ledger naming another outgoing version is refused before any switch.
    (work / 'switch-state.json').write_text(json.dumps(switch_state, ensure_ascii=False))
    ledger_path = tmp_path / 'root' / 'ledger.json'
    ledger_path.write_text(json.dumps(dict(ledger, last_delivered='f' * 64), ensure_ascii=False))
    retry = FakeRunner(blocks=UNTOUCHED_BASE)
    with pytest.raises(X.DeliveryError):
        X.deliver(tmp_path / 'root', b, retry, policy=policy)
    assert retry.calls == [] and state_of(tmp_path, b)['switch_layout']['legacy_suffix'] == OLD_SUFFIX
