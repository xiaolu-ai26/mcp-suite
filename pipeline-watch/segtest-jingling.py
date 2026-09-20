"""精灵实测:分段发布 + 断点续跑 + taskkill 路径(只写临时目录)。

设计约束(与任务书一致)
--------------------
* **对正式目录只读**:`C:\\mcp-suite-collector` 只被读(复制 `qiuzhao`/`deploy`、
  读 `runs\\20260920\\jobs.before.json`)。所有写入都在 `--root`(默认
  `C:\\mcp-suite-seg-test`)下;第二个并行验证用 `C:\\mcp-suite-seg-test2`。
* **不推真实服务器**:`pull` / `publish_snapshot` 被换成 `deploy\\windows_receiver.py` 的
  **同语义本地替身**(同样的 CAS 前提校验、`already_published` 短路、上传 hash 校验),
  目标是 `<root>\\fake-server\\<run-name>.jobs.json`。真实 SSH 一次都不会发。
* **不调飞书**:传 `--no-sync`。
* **不碰计划任务、不碰正式 data/runs、不终止任何进程**。
* 只跑少量已知稳定公司(取自 `runs\\20260920` 的 p1 status:9-20 当天 success+complete 的单元);
  段长/并发按验证目标临时调小,都写在收据里。

已跑过并在收据中记录的形态(通过 ssh stdin 运行 `python -X utf8 - <args>`):

    unpack   --bundle <root>\\segtest-bundle.tar.gz     # 复制正式树 + 覆盖部署件
    run --run-name segfinal-multi --companies A,B,C --scopes campus \\
        --workers 1 --segment-seconds 20 --fresh --fresh-server --skip-pre-stages
    run --run-name segfinal-16 --segment-seconds 300 --fresh --fresh-server --skip-pre-stages
    run --run-name segfinal-timeout --companies X --step-limit 25 --fresh --fresh-server
    taskkill                                          # 真实 taskkill + 真实子进程
"""
import argparse
import datetime as dt
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import traceback

PROD = Path(r'C:\mcp-suite-collector')
TEST = Path(r'C:\mcp-suite-seg-test')
VENV_PYTHON = PROD/'.venv'/'Scripts'/'python.exe'
BASELINE_SRC = PROD/'runs'/'20260920'/'jobs.before.json'
def fake_server(run_name):
    """One local stand-in receiver per run, so parallel verification runs never share CAS."""
    return TEST/'fake-server'/f'{run_name}.jobs.json'
BUNDLE_FILES = [
    r'deploy/windows_collector.py',
    r'qiuzhao/collector/alibaba_headless.py',
    r'qiuzhao/collector/auto_collect.py',
    r'qiuzhao/collector/collection_gap.py',
    r'qiuzhao/collector/lark_sync_daemon.py',
    r'qiuzhao/collector/p1_foreign_01.py',
    r'qiuzhao/collector/p1_meituan_public.py',
    r'qiuzhao/collector/p1_netease_public.py',
    r'qiuzhao/collector/p1_pipeline.py',
    r'qiuzhao/collector/p1_platform_avature.py',
    r'qiuzhao/collector/p1_platform_companies.json',
    r'qiuzhao/collector/p1_platform_eightfold.py',
    r'qiuzhao/collector/p1_platform_moka.py',
    r'qiuzhao/collector/p1_platform_orc.py',
    r'qiuzhao/collector/p1_platform_phenom.py',
    r'qiuzhao/collector/p1_platform_successfactors.py',
    r'qiuzhao/collector/p1_platform_tupu360.py',
    r'qiuzhao/collector/p1_platform_workday.py',
    r'qiuzhao/collector/p1_sources_11_20.py',
    r'qiuzhao/collector/portable_runtime.py',
    r'qiuzhao/collector/sync_lark_multivalue.py',
]


def log(message):
    print(f'[{time.strftime("%H:%M:%S")}] {message}', flush=True)


def load_collector():
    """Import the temp-tree copy of deploy/windows_collector.py (never the live one)."""
    sys.path.insert(0, str(TEST))
    os.environ['PYTHONPATH'] = str(TEST)
    spec = importlib.util.spec_from_file_location('seg_windows_collector',
                                                  TEST/'deploy'/'windows_collector.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert Path(module.__file__).resolve().is_relative_to(TEST), module.__file__
    assert Path(module.ROOT).resolve() == TEST.resolve(), module.ROOT
    module.PYTHON = VENV_PYTHON
    return module


def cmd_unpack(args):
    TEST.mkdir(parents=True, exist_ok=True)
    for name in ('qiuzhao', 'deploy'):
        if not (TEST/name).is_dir():
            shutil.copytree(PROD/name, TEST/name)
    with tarfile.open(args.bundle, 'r:gz') as archive:
        try:
            archive.extractall(TEST, filter='data')
        except TypeError:  # Python < 3.12 has no filter=
            archive.extractall(TEST)
    for relative in BUNDLE_FILES:
        target = TEST/relative
        assert target.is_file(), f'bundle did not deliver {relative}'
    # Python bytecode cached from the production tree must never shadow the bundle.
    for cache in TEST.rglob('__pycache__'):
        shutil.rmtree(cache, ignore_errors=True)
    child = subprocess.run([str(VENV_PYTHON), '-X', 'utf8', '-c',
                            'import qiuzhao,sys;print(qiuzhao.__file__)'],
                           cwd=str(TEST), env=dict(os.environ, PYTHONPATH=str(TEST)),
                           capture_output=True, text=True)
    print(json.dumps({'unpacked': len(BUNDLE_FILES), 'tree': str(TEST),
                      'child_qiuzhao': child.stdout.strip(), 'child_rc': child.returncode},
                     ensure_ascii=False))


class LocalReceiver:
    """Same semantics as deploy/windows_receiver.py, minus SSH (see module docstring)."""

    def __init__(self, digest, conflict, server):
        self.digest, self.conflict, self.server = digest, conflict, server
        self.pulls, self.publications = [], []

    def pull(self, target):
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.server, target)
        before = self.digest(target)
        self.pulls.append({'count': len(self.pulls) + 1, 'sha256': before,
                           'at': time.strftime('%H:%M:%S')})
        return before

    def publish(self, candidate, expected_base, workdir):
        candidate, workdir = Path(candidate), Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        after = self.digest(candidate)
        current = self.digest(self.server)
        if current == after:
            return {'published': True, 'already_published': True, 'after_sha256': after}
        if current != expected_base:
            raise self.conflict('production changed: pull and recollect')
        backup = self.server.with_name(f'{self.server.stem}.bak.'
                                       + dt.datetime.now().strftime('%Y%m%dT%H%M%S%f'))
        shutil.copyfile(self.server, backup)
        shutil.copyfile(candidate, self.server)
        if self.digest(self.server) != after:
            raise ValueError('fake receiver upload hash mismatch')
        record = {'published': True, 'before_sha256': expected_base, 'after_sha256': after,
                  'backup': str(backup), 'at': time.strftime('%H:%M:%S')}
        (workdir/'receiver.stdout').write_text(json.dumps(record), encoding='utf-8')
        self.publications.append(record)
        return record


def fake_steps_for(module, companies, scopes, step_limit, skip_pre_stages=False, workers=None):
    """Inject --companies/--scopes into the p1 segment argv (the chain has no such flag).

    ``skip_pre_stages`` drops basic/tencent: this verification is about the p1 segment
    loop, and basic alone is ~30 minutes of real collection in the daily chain.
    """
    base = module.steps_for

    def steps_for(stage, smoke):
        steps = []
        for name, argv, limit in base(stage, smoke):
            if skip_pre_stages and name in ('basic', 'tencent'):
                continue
            if name == 'p1':
                argv = [*argv, '--companies', ','.join(companies)]
                if scopes:
                    argv = [*argv, '--scopes', ','.join(scopes)]
                if workers:
                    argv[argv.index('--workers') + 1] = str(workers)
                if step_limit:
                    limit = step_limit
            steps.append((name, argv, limit))
        return steps
    return steps_for


def cmd_run(args):
    module = load_collector()
    run_dir = TEST/'runs'/args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.fresh:
        shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True)
    server = fake_server(args.run_name)
    server.parent.mkdir(parents=True, exist_ok=True)
    if not server.exists() or args.fresh_server:
        shutil.copyfile(BASELINE_SRC, server)
    module.P1_SEGMENT_SECONDS = args.segment_seconds
    module.P1_TOTAL_BUDGET_SECONDS = args.budget
    receiver = LocalReceiver(module.digest, module.CASConflict, server)
    module.pull = receiver.pull
    module.publish_snapshot = receiver.publish
    module.steps_for = fake_steps_for(module, args.companies, args.scopes, args.step_limit,
                                      skip_pre_stages=args.skip_pre_stages, workers=args.workers)
    sys.argv = ['windows_collector', '--no-sync', '--resume-run', str(run_dir)]
    started = time.time()
    result = {'run_name': args.run_name,
              # Self-certifying: the sha256 of the exact module file this process loaded.
              'windows_collector_sha256': hashlib.sha256(
                  Path(module.__file__).read_bytes()).hexdigest(),
              'bundle_sha256': hashlib.sha256((TEST/'segtest-bundle.tar.gz').read_bytes()).hexdigest()
              if (TEST/'segtest-bundle.tar.gz').exists() else None,
              'segment_seconds': args.segment_seconds,
              'budget_seconds': args.budget, 'step_limit': args.step_limit,
              'companies': args.companies, 'scopes': args.scopes or 'default(3)',
              'workers_override': args.workers,
              'fake_server': str(server), 'skipped_pre_stages': args.skip_pre_stages,
              'fake_server_rows': sum(1 for _ in module.iter_json_file(server, strict=True))
              if server.exists() else None}
    log(f'run {args.run_name}: calling windows_collector.main()')
    result['exit_code'] = module.main()
    result['wall_seconds'] = round(time.time() - started, 1)
    if not (run_dir/'receipt.json').exists():
        # Exit 75 (another run holds data/windows-runner.lock) never creates a receipt.
        alerts = TEST/'data'/'runner-skipped.jsonl'
        result['receipt'] = 'absent'
        result['runner_skipped_alerts'] = [json.loads(line) for line in
                                           alerts.read_text(encoding='utf-8').splitlines() if line.strip()] \
            if alerts.exists() else []
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    receipt = json.loads((run_dir/'receipt.json').read_text(encoding='utf-8'))
    stage = run_dir/'data'
    result['steps'] = receipt.get('steps')
    result['step_changes'] = receipt.get('step_changes')
    result['p1_finished'] = receipt.get('p1_finished')
    result['p1_pending_count'] = len(receipt.get('p1_pending') or [])
    result['p1_stopped'] = (receipt.get('p1_stopped') or {}).get('reason')
    result['p1_budget'] = receipt.get('p1_budget')
    result['p1_concurrency'] = receipt.get('p1_concurrency')
    result['cleanup_errors'] = receipt.get('cleanup_errors')
    result['error'] = receipt.get('error')
    result['error_step'] = receipt.get('error_step')
    result['typeerror_in_receipt'] = 'TypeError' in json.dumps(receipt)
    result['local_mirror_rows'] = sum(1 for _ in module.iter_json_file(
        TEST/'data'/'jobs.json', strict=True)) if (TEST/'data'/'jobs.json').exists() else None
    result['fake_server_rows_after'] = sum(1 for _ in module.iter_json_file(server, strict=True))
    result['receiver_pulls'] = len(receiver.pulls)
    result['receiver_publications'] = len(receiver.publications)
    result['segments'] = [{'segment': s['segment'], 'attempts': s.get('attempts'),
                           'exit': s.get('exit'), 'p1_seconds': s.get('p1_seconds'),
                           'elapsed_seconds': s.get('elapsed_seconds'),
                           'normalize_exit': s.get('normalize_exit'),
                           'run_finished': s.get('run_finished'),
                           'pending_count': s.get('pending_count'),
                           'publication': {k: v for k, v in (s.get('publication') or {}).items()
                                           if k != 'publication'},
                           'cleanup_errors': s.get('cleanup_errors'),
                           'step_changes': s.get('step_changes'), 'note': s.get('note')}
                          for s in receipt.get('p1_segments') or []]
    status = module.p1_status(stage)
    result['p1_status'] = {'run_finished': status.get('run_finished'),
                           'pending_count': len(status.get('pending') or []),
                           'results': len(status.get('results') or {}),
                           'run_dir': status.get('run_dir'),
                           'attempted_units': sum(1 for entry in (status.get('results') or {}).values()
                                                  if isinstance(entry, dict) and entry.get('attempted')),
                           'publish_errors': [key for key, entry in (status.get('results') or {}).items()
                                              if isinstance(entry, dict) and entry.get('publish_error')]}
    runs = sorted((stage/'p1-runs').glob('*')) if (stage/'p1-runs').exists() else []
    result['p1_run_directories'] = [path.name for path in runs]
    result['validated_json_files'] = len(list((stage/'p1-runs').rglob('validated.json'))) \
        if (stage/'p1-runs').exists() else 0
    result['p1_checkpoint_exists'] = (stage/'p1-checkpoints').exists()
    result['p1_status_file_exists'] = (stage/'p1-status.json').exists()
    if (run_dir/'p1.log').exists():
        text = (run_dir/'p1.log').read_text(encoding='utf-8', errors='replace')
        result['p1_log'] = {'lines': len(text.splitlines()),
                            'errno36': text.count('Errno 36'),
                            'unicode_error': text.count('UnicodeDecodeError'),
                            'traceback': text.count('Traceback (most recent call last)'),
                            'tail': text.splitlines()[-3:]}
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_taskkill(args):
    """The exact P0 shape on the real box: a live child + the real taskkill (GBK output)."""
    module = load_collector()
    import qiuzhao.collector.portable_runtime as runtime
    child = subprocess.Popen([str(VENV_PYTHON), '-X', 'utf8', '-c', 'import time;time.sleep(120)'],
                             start_new_session=True, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    time.sleep(1)
    result = {'pid': child.pid, 'taskkill': str(runtime.taskkill_command(child.pid))}
    try:
        report = runtime.stop_tree(child)
    except Exception as failure:
        result['raised'] = f'{type(failure).__name__}: {failure}'
        result['traceback'] = traceback.format_exc()
    else:
        result['raised'] = None
        result['report'] = report
    result['child_exited'] = child.poll() is not None
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    global TEST
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=r'C:\mcp-suite-seg-test',
                        help='temp tree to work in; the production tree is never written')
    sub = parser.add_subparsers(dest='command', required=True)
    unpack = sub.add_parser('unpack')
    unpack.add_argument('--bundle', type=Path, default=TEST/'segtest-bundle.tar.gz')
    unpack.set_defaults(func=cmd_unpack)
    run = sub.add_parser('run')
    run.add_argument('--run-name', default='segtest')
    run.add_argument('--segment-seconds', type=int, default=300)
    run.add_argument('--budget', type=int, default=1800)
    run.add_argument('--step-limit', type=int, default=None)
    run.add_argument('--companies', default='科沃斯,基恩士,安徽康明斯,新奥集团,易盛信息,英维克')
    run.add_argument('--scopes', default='')
    run.add_argument('--fresh', action='store_true')
    run.add_argument('--fresh-server', action='store_true')
    run.add_argument('--skip-pre-stages', action='store_true',
                     help='skip basic/tencent: verify the p1 segment loop only')
    run.add_argument('--workers', type=int, default=None,
                     help='override --workers in the p1 segment argv; keeps the segment '
                          'boundary meaningful when the company count is below the default')
    run.set_defaults(func=cmd_run)
    taskkill = sub.add_parser('taskkill')
    taskkill.set_defaults(func=cmd_taskkill)
    args = parser.parse_args()
    TEST = Path(args.root)
    if hasattr(args, 'companies'):
        args.companies = [name for name in args.companies.split(',') if name]
        args.scopes = [name for name in args.scopes.split(',') if name]
    args.func(args)


if __name__ == '__main__':
    main()
