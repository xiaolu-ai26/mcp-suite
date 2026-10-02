"""Retry ONLY a failed normalize stage using the existing runner's lock and step.

No collector, publisher, Base importer, deadline adjustment or budget reset is
called here. Default is inspection. --apply requires exact source/receipt hashes
and a reviewed deployment manifest. Review authenticity is a human obligation;
this command validates byte binding, not the reviewer's identity.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys

CORE_FILES = (
    'qiuzhao/normalize.py', 'qiuzhao/normalization_io.py',
    'qiuzhao/company_names.py', 'qiuzhao/v4_fields.py',
    'qiuzhao/collector/portable_runtime.py',
    'deploy/windows_collector.py', 'deploy/windows_normalize_retry.py',
)
ASSET_FILES = ('qiuzhao/normalize_tables.json', 'qiuzhao/data/company_aliases.json',
               'qiuzhao/collector/p1_platform_companies.json')


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for part in iter(lambda: source.read(1024 * 1024), b''):
            result.update(part)
    return result.hexdigest()


def identities(root):
    """Missing assets are explicit nulls; never manufacture or download an asset."""
    root = Path(root)
    return {name: digest(root / name) if (root / name).is_file() else None
            for name in (*CORE_FILES, *ASSET_FILES)}


def read_object(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('expected JSON object: ' + str(path))
    return value


def validate_manifest(path, actual):
    manifest = read_object(path)
    if manifest.get('decision') != 'PASS' or not str(manifest.get('reviewer') or '').strip():
        raise ValueError('independent byte review is required; no PASS/reviewer in manifest')
    if manifest.get('files') != actual or any(actual.get(name) is None for name in CORE_FILES):
        raise ValueError('reviewed code/asset identity mismatch or required code missing')


def retry_normalization(runner, run, *, expected_source, expected_receipt,
                        apply=False, review_manifest=None, task_is_running=lambda: True):
    """runner is deploy.windows_collector; injected only to test orchestration.

    The existing run_stage_step owns snapshot, subprocess timeout, rollback and
    unsafe-writer handling. We do not implement a second publication/state machine.
    A retry remains stopped/pending even on exit 0: normalization != delivery.
    """
    root = Path(runner.ROOT).resolve()
    run = Path(run).resolve()
    if run == root / 'runs' or not run.is_relative_to(root / 'runs') or not run.is_dir():
        raise ValueError('run must be an existing child of the collector runs directory')
    state_path, stage = run / 'receipt.json', run / 'data'
    jobs = stage / 'jobs.json'
    if not (root / 'data').is_dir():
        raise ValueError('collector data directory missing')
    with (root / 'data/windows-runner.lock').open('a+') as lock:
        runner.fcntl.flock(lock, runner.fcntl.LOCK_EX | runner.fcntl.LOCK_NB)
        try:
            if task_is_running():
                raise ValueError('daily scheduler is unknown, queued, or running; retry refused')
            if digest(state_path) != expected_receipt or digest(jobs) != expected_source:
                raise ValueError('source or receipt changed; inspect again, do not reuse old hashes')
            state = read_object(state_path)
            if state.get('stage') != 'partial-or-failed' or not state.get('completed_at'):
                raise ValueError('source run is not a terminal partial-or-failed receipt')
            runner.refuse_unsafe_writer(state)
            if state.get('publication_intent') or state.get('stage_advance') or state.get('unconfirmed_publications'):
                raise ValueError('publication outcome/alignment unresolved; read-only reconciliation required')
            code = (state.get('steps') or {}).get('normalize')
            if type(code) is not int or code == 0 or not state.get('p1_segments'):
                raise ValueError('requires an explicitly failed normalize after an existing P1 segment; zero-segment guard unchanged')
            if (state.get('collection') or {}).get('state') != 'stopped':
                raise ValueError('only a stopped collection is eligible; no finished-state rewriting')
            if read_object(stage / 'p1-status.json').get('active_batch'):
                raise ValueError('P1 has an active local batch; resolve it before normalizing')
            if any(p.name != 'jobs.before.json' for p in run.glob('*.before.json')):
                raise ValueError('interrupted stage snapshot exists; inspect it before retrying')
            dependencies = identities(root)
            result = {'action': 'inspect-only', 'run': str(run),
                      'source_sha256': expected_source, 'receipt_sha256': expected_receipt,
                      'dependencies': dependencies, 'previous_normalize_exit': code,
                      'collection_attempted': False, 'publication_attempted': False,
                      'feishu_attempted': False}
            if not apply:
                return result
            if review_manifest is None:
                raise ValueError('--apply requires --review-manifest')
            validate_manifest(review_manifest, dependencies)
            # The unchanged capacity gate, unchanged timeout and same step implementation.
            runner.capacity_check([jobs])
            steps = {name: (args, limit) for name, args, limit in runner.steps_for(stage, False)}
            args, limit = steps['normalize']
            env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
                       QIUZHAO_DATA_DIR=str(stage), QIUZHAO_SKIP_SERVICE_RESTART='1')
            before_policy = json.dumps({key: state.get(key) for key in
                ('p1_budget_ledger', 'p1_budget', 'collection', 'p1_segments')}, sort_keys=True)
            retry_error = None
            # The existing step persists exit 0 before our identity checks. Keep the
            # existing global writer gate closed across that crash window. This is a
            # validation barrier, not a claim that a child process is still alive.
            guard = {'step': 'normalize', 'normalization_retry_validation': True,
                     'reason': 'normalize-only retry validation pending; inspect before any resume/publication'}
            state['unsafe_writer'] = guard
            result['action'] = 'retry-interrupted-validation-pending'
            runner.atomic_json(state_path, state)
            try:
                result['normalize_exit'] = runner.run_stage_step(
                    state, state_path, run, stage, 'normalize', args, limit, env, force=True)
                if identities(root) != dependencies:
                    state['steps']['normalize'] = 1
                    raise ValueError('code/assets changed during retry; output is NOT approved for publication')
                after_policy = json.dumps({key: state.get(key) for key in
                    ('p1_budget_ledger', 'p1_budget', 'collection', 'p1_segments')}, sort_keys=True)
                if after_policy != before_policy:
                    state['steps']['normalize'] = 1
                    raise ValueError('collection policy changed unexpectedly; refuse publication')
                result['action'] = ('normalized-not-published' if result['normalize_exit'] == 0
                                    else 'normalize-failed-not-published')
                result['output_sha256'] = digest(jobs)
                if result['normalize_exit'] == 2:
                    # normalize has no partial-success contract. Do not leave an
                    # exit the segment publisher could interpret as publishable.
                    state['steps']['normalize'] = 1
                    raise ValueError('unexpected partial normalize exit; inspect retained evidence')
                if state.get('unsafe_writer') != guard:
                    raise ValueError('writer safety state changed during retry')
                state.pop('unsafe_writer')
            except Exception as error:
                if state.get('steps', {}).get('normalize') == 0:
                    state['steps']['normalize'] = 1
                result['action'] = 'retry-failed-preserve-evidence'
                result['error_type'] = type(error).__name__
                retry_error = error
            finally:
                result['checked_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
                state.setdefault('normalization_retries', []).append(result)
                # Do not overwrite historical completion time, success, collection or delivery.
                state['stage'] = 'partial-or-failed'
                runner.atomic_json(state_path, state)
            if retry_error is not None:
                raise retry_error
            return result
        finally:
            runner.fcntl.flock(lock, runner.fcntl.LOCK_UN)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--expected-source-sha256', required=True)
    parser.add_argument('--expected-receipt-sha256', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--review-manifest', type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from deploy import windows_collector as runner
    from deploy.windows_recover_run import task_is_running
    result = retry_normalization(runner, args.run,
        expected_source=args.expected_source_sha256, expected_receipt=args.expected_receipt_sha256,
        apply=args.apply, review_manifest=args.review_manifest, task_is_running=task_is_running)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['action'] in ('inspect-only', 'normalized-not-published') else 1


if __name__ == '__main__':
    raise SystemExit(main())
