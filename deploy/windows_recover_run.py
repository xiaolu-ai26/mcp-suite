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
from deploy.windows_collector import (digest, guarded_publish_snapshot, prepare_candidate, pull,
                                      refuse_unsafe_writer, unconfirmed_alignment, working_baseline)
from deploy.windows_rebase import publish_with_rebase

# The old --sync branch drove the row-level lark_sync_daemon, which the Excel-import
# route replaces; recovery only (re)publishes to the server.
SYNC_RETIRED=('row-level Base sync is retired; deliver a server-accepted version through '
              'deploy/windows_excel_delivery.py instead')


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
    """Called only while holding the same global runner lock, after a terminal receipt.

    Uses exactly the publication gates of the daily runner: the unsafe-writer refusal,
    the run's working baseline (never the pre-segment original, which would turn the
    run's own published edits into conflicts), ``prepare_candidate`` on a frozen copy
    and the boundary lifecycle guard. The source run directory is never written.
    """
    if sync:raise ValueError(SYNC_RETIRED)
    run,workdir=Path(run),Path(workdir)
    if state.get('stage') not in {'completed','partial-or-failed'} or not state.get('completed_at'):
        raise ValueError('source run is not terminal')
    refuse_unsafe_writer(state)
    if state.get('steps',{}).get('normalize')!=0:
        raise ValueError('source run has no successful normalization; do not publish it')
    if not state.get('publication_ledger') and state.get('publication'):
        raise ValueError('source receipt predates the working-baseline ledger and has published '
                         'before; resume it with windows_collector --resume-run, which migrates it '
                         '(or refuses) before anything is published')
    if state.get('stage_advance') or state.get('publication_intent'):
        raise ValueError('source run has an unfinished publication step; resume it with '
                         'windows_collector --resume-run, which aligns it first')
    baseline=run/'jobs.before.json';candidate=run/'data/jobs.json'
    before_hash=digest(baseline)
    if before_hash!=state.get('before_sha256'):
        raise ValueError('real original baseline does not match run receipt')
    reference,reference_hash=working_baseline(state,run)
    candidate_hash=digest(candidate)
    attempts=workdir/'attempts';attempts.mkdir(exist_ok=True)
    result=None;publication_reused=False
    # A publication may have succeeded before the outer receipt was written. Reuse its
    # attested file, never replay the same delta just because the recovery receipt failed.
    for receipt in sorted(attempts.glob('*/publication/receipt.json'),key=lambda p:p.stat().st_mtime_ns,reverse=True):
        prior=json.loads(receipt.read_text(encoding='utf-8'))
        source=receipt.parent.parent/'source-binding.json'
        binding=json.loads(source.read_text(encoding='utf-8')) if source.exists() else {}
        if (binding.get('source_candidate_sha256')!=candidate_hash or binding.get('working_sha256')!=reference_hash
                or prior.get('publication',{}).get('published') is not True):
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
        shutil.copyfile(reference,frozen_base);shutil.copyfile(candidate,frozen_candidate)
        if digest(reference)!=reference_hash or digest(candidate)!=candidate_hash:
            raise ValueError('source data changed while freezing completed run')
        if digest(frozen_base)!=reference_hash or digest(frozen_candidate)!=candidate_hash:
            raise ValueError('frozen input hash mismatch')
        atomic_json(attempt/'source-run-receipt.json',state)
        frozen,preserved,total=prepare_candidate(frozen_base,frozen_candidate)
        atomic_json(attempt/'source-binding.json',{'source_run':str(run.resolve()),
            'source_candidate_sha256':candidate_hash,
            'working_sha256':reference_hash,'working_path':str(reference),
            'original_before_sha256':before_hash,'removed_frozen':frozen,
            'preserved_missing':preserved,'total_jobs':total,
            'prepared_candidate_sha256':digest(frozen_candidate)})
        result=publish_with_rebase(frozen_base,frozen_candidate,reference_hash,attempt/'publication',
                                   pull,guarded_publish_snapshot(frozen_base),force_rebase=True,
                                   aligned=unconfirmed_alignment(state))
    published_path=Path(result['published_path'])
    atomic_json(workdir/'PUBLICATION_HANDOFF.json',{'publication':result['publication'],
        'published_path':str(published_path),'source_candidate_sha256':candidate_hash,
        'working_sha256':reference_hash,'publication_reused':publication_reused})
    if digest(baseline)!=before_hash or digest(candidate)!=candidate_hash or digest(reference)!=reference_hash:
        raise ValueError('source run changed despite exclusive lock')
    return {'state':'recovered_and_published','source_run':str(run),
            'attempt_dir':str(attempt),
            'source_run_before_sha256':before_hash,'source_candidate_sha256':candidate_hash,
            'source_working_sha256':reference_hash,
            'source_run_data_untouched':True,'source_receipt_before_sha_not_rewritten':True,
            'publication_reused':publication_reused,'daily_restarted':False,
            'feishu':'not_requested; '+SYNC_RETIRED,'canonical_data_file_modified':False,
            'result':result,'completed_at':dt.datetime.now().astimezone().isoformat()}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--wait',action='store_true')
    parser.add_argument('--sync',action='store_true',help='retired: refused (use the Excel delivery)')
    # Accepted so existing scheduled command lines still parse; it gated the retired sync.
    parser.add_argument('--sync-ready-file',type=Path,help='accepted for compatibility; ignored')
    parser.add_argument('--max-wait-seconds',type=int,default=28800)
    a=parser.parse_args();run=a.run.resolve();workdir=a.work_dir.resolve()
    if a.sync:raise SystemExit(SYNC_RETIRED)
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
                    if acquired and not task_is_running():
                        state=json.loads((run/'receipt.json').read_text(encoding='utf-8'))
                        if state.get('stage') in {'completed','partial-or-failed'} and state.get('completed_at'):
                            atomic_json(statusfile,{'state':'recovering_completed_run','pid':os.getpid(),
                                                    'source_run':str(run),'source_before_sha256':state.get('before_sha256')})
                            try:
                                result=recover(run,workdir,state)
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
                     'source_run_untouched':True,
                     'checked_at':dt.datetime.now().astimezone().isoformat()}
            atomic_json(statusfile,waiting)
            if not a.wait or elapsed>=a.max_wait_seconds:
                return 75
            time.sleep(30)


if __name__=='__main__':raise SystemExit(main())
