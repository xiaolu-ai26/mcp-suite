"""The deployment manifest names real repo files and frozen hashes stay honest (batch 1)."""
import json

from deploy import deploy_manifest as M


def load():
    return json.loads(M.MANIFEST.read_text(encoding='utf-8'))


def test_every_listed_file_exists_and_recorded_hashes_match():
    rows, failures = M.check(load())
    assert failures == [], failures
    assert {r['repo'] for r in rows} >= {'deploy/windows_collector.py', 'deploy/windows_receiver.py',
                                        'deploy/windows_receiver_rotation.py', 'qiuzhao/normalize_tables.json'}


def test_pending_entries_block_a_deployment_check():
    _, failures = M.check(load(), require_frozen=True)
    assert any('normalize_tables.json: not frozen' in f for f in failures)


def test_a_changed_frozen_file_fails(tmp_path):
    manifest = {'environments': {'x': {'files': [{'repo': 'f.py', 'sha256': '0' * 64, 'status': 'frozen'}]}}}
    (tmp_path / 'f.py').write_text('print(1)\n')
    _, failures = M.check(manifest, repo=tmp_path)
    assert failures == ['f.py: differs from the recorded sha256']


def test_the_manifest_carries_no_host_or_personal_path():
    text = M.MANIFEST.read_text(encoding='utf-8')
    for forbidden in ('/Users/', '114.', '192.168.', 'C:\\\\'):
        assert forbidden not in text


# --- delivery_mac is complete and enforced before any Base action (2026-09-28) --------

import plistlib
import shutil

import pytest

from deploy import windows_excel_delivery as X


def test_delivery_mac_lists_every_runtime_dependency_and_is_frozen():
    listed = {entry['repo'] for env, entry in M.entries(load()) if env == 'delivery_mac'}
    assert set(X.DELIVERY_RUNTIME_FILES) <= listed
    assert {'qiuzhao/v4_fields.py', 'qiuzhao/collector/lark_sync_enrichment.py',
            'qiuzhao/collector/sync_lark_multivalue.py'} <= listed
    # Frozen 2026-09-28 after both batch reviews passed: any later edit of a runtime file fails here.
    assert X.frozen_failures() == []


def frozen_copy(tmp_path):
    """A repo copy of the runtime files and a manifest that freezes exactly those bytes."""
    repo = tmp_path / 'repo'
    for name in X.DELIVERY_RUNTIME_FILES:
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(M.REPO / name, repo / name)
    files = [{'repo': name, 'sha256': X.digest(repo / name), 'status': 'frozen (test)'}
             for name in X.DELIVERY_RUNTIME_FILES]
    return repo, {'environments': {'delivery_mac': {'files': files}}}


def test_a_fully_frozen_copy_passes(tmp_path):
    repo, manifest = frozen_copy(tmp_path)
    assert X.frozen_failures(repo / 'deploy' / 'feishu_r1', manifest=manifest, repo=repo) == []


@pytest.mark.parametrize('case', ['pending', 'missing_dependency', 'drift', 'other_scripts_dir'])
def test_pending_missing_or_drifted_code_is_refused(tmp_path, case):
    repo, manifest = frozen_copy(tmp_path)
    scripts = repo / 'deploy' / 'feishu_r1'
    files = manifest['environments']['delivery_mac']['files']
    if case == 'pending':
        files[0]['status'] = 'pending: in review'
        expected = files[0]['repo'] + ': not frozen'
    elif case == 'missing_dependency':
        files[:] = [f for f in files if f['repo'] != 'qiuzhao/v4_fields.py']
        expected = 'qiuzhao/v4_fields.py: runtime dependency not in delivery_mac'
    elif case == 'drift':
        (repo / 'qiuzhao' / 'v4_fields.py').write_text('# edited after freezing\n')
        expected = 'qiuzhao/v4_fields.py: differs from the recorded sha256'
    else:
        other = tmp_path / 'external-r1'
        shutil.copytree(scripts, other)
        (other / X.SCRIPT['switch']).write_text('# an older external copy\n')
        scripts = other
        expected = 'is not the frozen deploy/feishu_r1/' + X.SCRIPT['switch']
    failures = X.frozen_failures(scripts, manifest=manifest, repo=repo)
    assert any(expected in f for f in failures), failures


def test_script_runner_checks_the_freeze_before_every_base_action(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / X.SCRIPT['import']).write_text('raise SystemExit("must not run")\n')
    runner = X.ScriptRunner(scripts, apply=True, frozen_check=lambda: ['qiuzhao/normalize.py: not frozen'])
    with pytest.raises(X.DeliveryError, match='not the frozen deploy manifest'):
        runner.external('import', tmp_path, {}, tmp_path / 'import.log')
    with pytest.raises(X.DeliveryError, match='not the frozen deploy manifest'):
        runner.live_blocks()
    assert not (tmp_path / 'import.log').exists() and not list(tmp_path.glob('.exec-*'))


def test_manual_apply_is_refused_while_the_manifest_is_pending(tmp_path, monkeypatch):
    # The real manifest is frozen, so a pending one is simulated; this never reaches the Base.
    monkeypatch.setattr(X, 'frozen_failures', lambda *a, **k: ['qiuzhao/v4_fields.py: not frozen'])
    snapshot = tmp_path / 'jobs.json'
    snapshot.write_text('[]')
    with pytest.raises(SystemExit, match='refusing --apply'):
        X.main(['deliver', '--root', str(tmp_path / 'root'), '--snapshot', str(snapshot),
                '--sha256', X.digest(snapshot), '--apply'])
    assert not (tmp_path / 'root').exists()


def test_launchd_template_sets_path_and_an_explicit_interpreter_without_private_paths():
    path = M.REPO / 'deploy' / 'launchd' / 'qiuzhao-feishu-deliver-latest.plist.template'
    text = path.read_text(encoding='utf-8')
    assert '/Users/' not in text and '192.168.' not in text
    job = plistlib.loads(text.encode())
    assert job['ProgramArguments'][0] == '@PYTHON@'
    assert job['EnvironmentVariables'] == {'PATH': '@PATH@', 'HOME': '@HOME@'}
    assert job['ProgramArguments'][-1] == '--apply' and '@CONFIG@' in job['ProgramArguments']
