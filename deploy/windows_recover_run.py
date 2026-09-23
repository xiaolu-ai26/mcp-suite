"""Wait for the existing daily runner to finish, then recover in an isolated directory."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qiuzhao.collector.portable_runtime import fcntl
from qiuzhao.collector.p1_pipeline import atomic_json
from deploy.windows_collector import digest, pull, publish_snapshot, sync_owner_ready
from deploy.windows_rebase import publish_with_rebase


def task_is_running():
    if os.name!='nt':
        return False
    # The ScheduledTasks PowerShell module can exhaust memory during a heavy P1 run.
    # Scheduler COM exposes the same numeric state without loading that module.
    command=("$s=New-Object -ComObject 'Schedule.Service';$s.Connect();"
             "[int]$s.GetFolder('\\').GetTask('Qiuzhao-Collector-Daily').State")
    result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],
                          capture_output=True,text=True,timeout=30)
    if result.returncode:
        raise RuntimeError('cannot verify daily scheduled-task state')
    state=int(result.stdout.strip())
    if state not in {0,1,2,3,4}:raise RuntimeError('unknown scheduled-task state')
    return state in {0,2,4}  # Unknown/queued/running are not safe handoff states.


def recover(run,workdir,state, sync=False):
    """Called only while holding the same global runner lock, after a terminal receipt."""
    run,workdir=Path(run),Path(workdir)
    if state.get('stage') not in {'completed','partial-or-failed'} or not state.get('completed_at'):
        raise ValueError('source run is not terminal')
    if state.get('steps',{}).get('normalize')!=0:
        raise ValueError('source run has no successful normalization; do not publish it')
    baseline=run/'jobs.before.json';candidate=run/'data/jobs.json'
    before_hash=digest(baseline)
    if before_hash!=state.get('before_sha256'):
        raise ValueError('real original baseline does not match run receipt')
    candidate_hash=digest(candidate)
    attempts=workdir/'attempts';attempts.mkdir(exist_ok=True)
    result=None;publication_reused=False
    # A publication may have succeeded before sync raised. Reuse its attested file,
    # never replay the same delta just because the outer recovery receipt failed.
    for receipt in sorted(attempts.glob('*/publication/receipt.json'),key=lambda p:p.stat().st_mtime_ns,reverse=True):
        prior=json.loads(receipt.read_text(encoding='utf-8'))
        if prior.get('source_candidate_sha256')!=candidate_hash or prior.get('publication',{}).get('published') is not True:
            continue
        published=Path(prior['published_path'])
        if not published.resolve().is_relative_to(workdir.resolve()):
            raise ValueError('prior published file escapes recovery directory')
        if digest(published)!=prior['publication']['after_sha256']:
            raise ValueError('prior published file hash mismatch; do not republish blindly')
        result=prior;attempt=receipt.parent.parent;publication_reused=True;break
    if result is None:
        # A failed pre-publication attempt retains its frozen evidence on retry.
        attempt=Path(tempfile.mkdtemp(prefix='attempt-',dir=attempts))
        frozen_base=attempt/'baseline.jobs.json';frozen_candidate=attempt/'collected.jobs.json'
        shutil.copyfile(baseline,frozen_base);shutil.copyfile(candidate,frozen_candidate)
        if digest(baseline)!=before_hash or digest(candidate)!=candidate_hash:
            raise ValueError('source data changed while freezing completed run')
        if digest(frozen_base)!=before_hash or digest(frozen_candidate)!=candidate_hash:
            raise ValueError('frozen input hash mismatch')
        atomic_json(attempt/'source-run-receipt.json',state)
        result=publish_with_rebase(frozen_base,frozen_candidate,before_hash,attempt/'publication',
                                   pull,publish_snapshot,force_rebase=True)
    published_path=Path(result['published_path'])
    atomic_json(workdir/'PUBLICATION_HANDOFF.json',{'publication':result['publication'],
        'published_path':str(published_path),'source_candidate_sha256':candidate_hash,
        'publication_reused':publication_reused,'sync_requested':sync})
    if digest(baseline)!=before_hash or digest(candidate)!=candidate_hash:
        raise ValueError('source run changed despite exclusive lock')
    sync_result=None
    if sync:
        if digest(published_path) != result['publication']['after_sha256']:
            raise ValueError('published sync input hash mismatch')
        # Publication and Base sync are separate. Even a reused successful publication
        # must not roll Base back when another publisher has since advanced production.
        sync_attempt=Path(tempfile.mkdtemp(prefix='sync-',dir=attempt))
        current_online=sync_attempt/'latest-online.jobs.json'
        online_sha=pull(current_online)
        if digest(current_online)!=online_sha:
            raise ValueError('latest online sync snapshot hash mismatch')
        atomic_json(sync_attempt/'snapshot-receipt.json',{'sha256':online_sha,
            'source':'locked receiver snapshot immediately before sync',
            'publication_reused':publication_reused,'snapshot':str(current_online)})
        canonical=ROOT/'data/jobs.json'
        temporary=canonical.with_suffix('.lifecycle.tmp')
        shutil.copyfile(current_online,temporary)
        os.replace(temporary,canonical)
        command=[str(ROOT/'.venv/Scripts/python.exe'),'-X','utf8','-m','qiuzhao.collector.lark_sync_daemon',
                 '--source-path',str(canonical),'--state-dir',str(ROOT/'data/lark-sync'),
                 '--runs-dir',str(ROOT/'data/lark-sync/runs'),'--apply']
        with (sync_attempt/'lark-sync.log').open('ab') as log:
            completed=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=21600)
        sync_result={'exit_code':completed.returncode,'log':str(sync_attempt/'lark-sync.log'),
                     'source_sha256':online_sha,'source_snapshot':str(current_online)}
        atomic_json(sync_attempt/'lark-sync-receipt.json',sync_result)
        if completed.returncode:raise RuntimeError('rebase published but Base sync failed; see '+str(sync_attempt/'lark-sync-receipt.json'))
    return {'state':'recovered_and_published','source_run':str(run),
            'attempt_dir':str(attempt),
            'source_run_before_sha256':before_hash,'source_candidate_sha256':candidate_hash,
            'source_run_data_untouched':True,'source_receipt_before_sha_not_rewritten':True,
            'publication_reused':publication_reused,
            'daily_restarted':False,'lark_sync_run':sync,'lark_sync_result':sync_result,'canonical_data_file_modified':sync,
            'result':result,'completed_at':dt.datetime.now().astimezone().isoformat()}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--wait',action='store_true')
    parser.add_argument('--sync-ready-file',type=Path,help='explicit cross-machine ownership handoff gate')
    parser.add_argument('--sync',action='store_true',help='sync the recovered publication through the existing local-user daemon')
    parser.add_argument('--max-wait-seconds',type=int,default=28800)
    a=parser.parse_args();run=a.run.resolve();workdir=a.work_dir.resolve()
    recovery_root=ROOT/'recovery'
    if not run.is_relative_to((ROOT/'runs').resolve()) or not run.is_dir():
        raise ValueError('invalid source run')
    if not workdir.is_relative_to(recovery_root.resolve()) or workdir==recovery_root.resolve():
        raise ValueError('work directory must be an independent recovery subdirectory')
    recovery_root.mkdir(exist_ok=True);workdir.mkdir(parents=True,exist_ok=True)
    statusfile=workdir/'RECOVERY_RECEIPT.json'
    prior=None
    if statusfile.exists():
        prior=json.loads(statusfile.read_text())
        if prior.get('state')=='recovered_and_published':
            if not a.sync or (prior.get('lark_sync_run') and prior.get('lark_sync_result',{}).get('exit_code')==0):
                return 0
    # One recovery watcher, even while it waits; the daily runner keeps its own lock.
    with (recovery_root/'pending-run-recovery.lock').open('a+') as singleton:
        try:fcntl.flock(singleton,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:return 75
        if prior:
            with (workdir/'recovery-status-history.jsonl').open('a',encoding='utf-8') as history:
                history.write(json.dumps(prior,ensure_ascii=False)+'\n')
        started=time.monotonic()
        while True:
            with (ROOT/'data/windows-runner.lock').open('a+') as runner_lock:
                acquired=False
                try:
                    try:
                        fcntl.flock(runner_lock,fcntl.LOCK_EX|fcntl.LOCK_NB);acquired=True
                    except OSError:
                        pass
                    handoff_ready = not a.sync or sync_owner_ready(a.sync_ready_file)
                    if acquired and not task_is_running() and handoff_ready:
                        state=json.loads((run/'receipt.json').read_text(encoding='utf-8'))
                        if state.get('stage') in {'completed','partial-or-failed'} and state.get('completed_at'):
                            atomic_json(statusfile,{'state':'recovering_completed_run','pid':os.getpid(),
                                                    'source_run':str(run),'source_before_sha256':state.get('before_sha256')})
                            try:
                                result=recover(run,workdir,state,sync=a.sync)
                            except Exception as error:
                                failure={'state':'recovery_failed_preserve_evidence',
                                         'error':type(error).__name__+': '+str(error)[-1500:],
                                         'source_run_untouched':True}
                                handoff=workdir/'PUBLICATION_HANDOFF.json'
                                if handoff.exists():
                                    failure['publication_handoff']=json.loads(handoff.read_text(encoding='utf-8'))
                                atomic_json(statusfile,failure)
                                raise
                            atomic_json(statusfile,result);print(json.dumps(result,ensure_ascii=False));return 0
                finally:
                    if acquired:fcntl.flock(runner_lock,fcntl.LOCK_UN)
            elapsed=time.monotonic()-started
            waiting={'state':'waiting_for_daily_terminal_and_runner_lock','pid':os.getpid(),
                     'source_run':str(run),'elapsed_seconds':round(elapsed),
                     'source_run_untouched':True,'sync_handoff_ready':not a.sync or sync_owner_ready(a.sync_ready_file),
                     'checked_at':dt.datetime.now().astimezone().isoformat()}
            atomic_json(statusfile,waiting)
            if not a.wait or elapsed>=a.max_wait_seconds:
                return 75
            time.sleep(30)


if __name__=='__main__':raise SystemExit(main())
