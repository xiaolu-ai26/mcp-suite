"""One local user-session sync attempt; launchd supplies hourly/wake scheduling."""
from __future__ import annotations
import argparse
import datetime as dt
import gzip
import hashlib
import os
import signal
import threading
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from qiuzhao.collector import sync_lark_multivalue as S
SYNC_RULE_VERSION = 2

HOST='root@114.215.188.109'
SOURCE='/var/lib/mcp-suite/jobs.json'
EXTERNAL_MOUNT=S.EXTERNAL_MOUNT
DEFAULT_RUNS=S.EXTERNAL_RUNS


def now():return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def alert_sync_failed(state, status_path):
    """Tell 站长 a Feishu sync attempt failed; best effort, never raises.

    The channel (``qiuzhao.notify``) is imported lazily and degrades to an alert
    file when credentials/target are missing, so the sync failure path keeps its
    original behaviour on a host where the notifier is not deployed.
    """
    try:
        from qiuzhao.notify import notify
        notify('lark_sync_failed',
               fields={'status':state.get('status'),'phase':state.get('phase'),
                       'run_dir':state.get('run_dir'),'state_dir':str(Path(status_path).parent),
                       'error':(state.get('error') or '')[:300]},
               action='看精灵 data\\lark-sync\\status.json 与 sync.log,处理后重跑同步')
    except Exception:
        pass


def source_hash():
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',HOST,
                           'sha256sum '+shlex.quote(SOURCE)],capture_output=True,text=True,timeout=45,check=True)
    value=result.stdout.split()[0]
    if len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise ValueError('invalid source hash response')
    return value


def capture_source(out):
    # Both hash and gzip use the same open inode, so concurrent atomic publishes
    # cannot mix one version's hash with another version's content.
    code="""import sys,json,hashlib,gzip,shutil,os
with open('/var/lib/mcp-suite/jobs.json','rb') as f:
 h=hashlib.sha256()
 for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 f.seek(0);sys.stdout.buffer.write((json.dumps({'sha256':h.hexdigest(),'size':os.fstat(f.fileno()).st_size})+'\\n').encode());sys.stdout.buffer.flush()
 with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',compresslevel=1,mtime=0) as g:shutil.copyfileobj(f,g,1048576)
"""
    command=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',HOST,
             '/opt/mcp-suite/.venv/bin/python -c '+shlex.quote(code)]
    error_log=out/'snapshot-ssh.stderr.log'
    with error_log.open('wb') as errors:
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=errors)
        watchdog=threading.Timer(300,lambda: process.kill() if process.poll() is None else None)
        watchdog.start()
        try:
            header=json.loads(process.stdout.readline())
            archive=out/'source.jobs.json.gz'
            with archive.open('wb') as target:shutil.copyfileobj(process.stdout,target,1<<20)
            if process.wait(timeout=300):raise RuntimeError('source snapshot SSH failed')
        except BaseException:
            if process.poll() is None:process.kill()
            process.wait();raise
        finally:watchdog.cancel()
    jobs=out/'source.jobs.json';digest=hashlib.sha256()
    with gzip.open(archive,'rb') as source,jobs.open('wb') as target:
        for chunk in iter(lambda:source.read(1<<20),b''):digest.update(chunk);target.write(chunk)
    if digest.hexdigest()!=header['sha256'] or jobs.stat().st_size!=header['size']:
        raise ValueError('source snapshot hash/size mismatch')
    S.save(out/'source-receipt.json',{**header,'captured_at':now(),'host':HOST,'source':SOURCE})
    return jobs,header['sha256']


def external_runs_ready(state_dir,runs_dir):
    mount=EXTERNAL_MOUNT
    if not mount.is_dir() or not mount.is_mount() or mount.stat().st_dev==state_dir.stat().st_dev:
        raise RuntimeError('external evidence disk is not mounted; local capture refused')
    if runs_dir.resolve()!=DEFAULT_RUNS.resolve():raise ValueError('unapproved external runs directory')
    alias=state_dir/'runs'
    if not alias.is_symlink() or alias.resolve()!=runs_dir.resolve():
        raise RuntimeError('external runs alias is not configured; no local fallback')
    if not runs_dir.is_dir():raise RuntimeError('external runs directory is unavailable')
    if not runs_dir.resolve().is_relative_to(mount.resolve()) or runs_dir.stat().st_dev!=mount.stat().st_dev:
        raise RuntimeError('runs directory is not physically on the approved external mount')
    return alias


def run(state_dir,runs_dir=None):
    state_dir=state_dir.resolve();state_dir.mkdir(parents=True,exist_ok=True)
    with S.sync_lock() as lock:
        status_path=state_dir/'status.json'
        previous=json.loads(status_path.read_text()) if status_path.exists() else {}
        state={**previous,'last_attempt_at':now(),'status':'checking','error':None,'finished_at':None}
        S.save(status_path,state)
        try:
            runs_root=external_runs_ready(state_dir,Path(runs_dir) if runs_dir is not None else DEFAULT_RUNS)
            observed=source_hash();state['observed_source_sha256']=observed
            if observed==previous.get('last_source_sha256') and previous.get('last_success_at') and previous.get('sync_rule_version') == SYNC_RULE_VERSION:
                state.update(status='unchanged',finished_at=now());S.save(status_path,state);return state
            out=runs_root/dt.datetime.now().strftime('%Y%m%dT%H%M%S');out.mkdir(parents=True)
            state.update(status='running',run_dir=str(out),phase='capture');S.save(status_path,state)
            jobs,source_sha=capture_source(out)
            semantic_hash=S.business_source_hash(jobs)
            if previous.get('last_business_sha256') == semantic_hash and previous.get('last_success_at') and previous.get('sync_rule_version') == SYNC_RULE_VERSION:
                state.update(status='unchanged',last_source_sha256=source_sha,finished_at=now())
                S.save(status_path,state);jobs.unlink();(out/'source.jobs.json.gz').unlink();return state
            # Explicit separate steps keep failures and partially completed writes
            # inspectable. lark-cli remains local under the logged-in user.
            steps=[('snapshot',['--snapshot']),('update',['--jobs',str(jobs),'--plan','--apply']),
                   ('business',['--jobs',str(jobs),'--sync-business']),('source_status',['--jobs',str(jobs),'--sync-status']),('append',['--jobs',str(jobs),'--append-p1']),('conditions',['--jobs',str(jobs),'--explain']),('deduplicate',['--jobs',str(jobs),'--deduplicate-exact'])]
            child_env=dict(os.environ, QIUZHAO_LARK_SYNC_LOCK_PATH=str(Path(lock.name).resolve()),
                           QIUZHAO_LARK_SYNC_LOCK_FD=str(lock.fileno()))
            for phase,flags in steps:
                state['phase']=phase;S.save(status_path,state)
                with (out/(phase+'.log')).open('wb') as log:
                    child=subprocess.Popen([sys.executable,'-m','qiuzhao.collector.sync_lark_multivalue',
                        '--output-dir',str(out),*flags],stdout=log,stderr=subprocess.STDOUT,env=child_env,
                        pass_fds=(lock.fileno(),),start_new_session=True)
                    try:exit_code=child.wait(timeout=5400)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGKILL);child.wait();raise
                if exit_code:raise RuntimeError(f'{phase} failed, exit={exit_code}; see {out/(phase+".log")}')
            append_state=json.loads((out/'append-status.json').read_text())
            if append_state.get('capacity_blocked'):
                state.update(status='partial',phase='complete_with_capacity_pending',finished_at=now(),
                             error='Base table capacity reached; other tables and conditions processed',
                             capacity_blocked=append_state['capacity_blocked'])
                S.save(status_path,state)
                return state
            if append_state.get('finished') is not True or append_state.get('pending'):
                raise RuntimeError('append has not reconciled all eligible source IDs')
            state.pop('capacity_blocked',None)
            state.update(status='success',phase='complete',last_success_at=now(),last_source_sha256=source_sha,last_business_sha256=semantic_hash,sync_rule_version=SYNC_RULE_VERSION,
                         finished_at=now(),source_receipt=str(out/'source-receipt.json'))
            S.save(status_path,state)
            # Keep restoration records/schema; only discard this run's redundant
            # decompressed public-source copy after a successful sync.
            jobs.unlink()
            (out/'source.jobs.json.gz').unlink()
            return state
        except Exception as error:
            state.update(status='failed',error=str(error)[:1000],finished_at=now())
            S.save(status_path,state)
            alert_sync_failed(state,status_path)
            raise


def run_local(source_path, state_dir, runs_dir, apply=False):
    """Sync a local collected snapshot using this machine's own user login."""
    source_path = source_path.resolve()
    state_dir = state_dir.resolve()
    runs_dir = runs_dir.resolve()
    # CLI paths stay inside the project; Windows needs no external-disk alias.
    if not runs_dir.is_relative_to(Path.cwd().resolve()):
        raise ValueError('local sync evidence must be inside project working directory')
    state_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    with S.sync_lock() as lock:
        status_path = state_dir/'status.json'
        previous = json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {}
        # Old runs' error/finished_at are run-state residue, never evidence about
        # this attempt (mirrors run() above); the success index fields survive via
        # the previous-state merge below.
        state = {**previous, 'status': 'checking', 'last_attempt_at': now(), 'source': str(source_path),
                 'error': None, 'finished_at': None}
        try:
            # An authenticated business read is required even for unchanged data.
            live = S.cli('+table-list', '--base-token', S.BASE, '--format', 'json')['data']['tables']
            if not set(S.ORIGINAL_TABLES) <= {table['id'] for table in live}:
                raise ValueError('target table identity drift')
            observed = S.digest(source_path)
            state['observed_source_sha256'] = observed
            if apply and previous.get('last_source_sha256') == observed and previous.get('last_success_at') and previous.get('sync_rule_version') == SYNC_RULE_VERSION:
                state = {**previous, **state, 'status': 'unchanged', 'finished_at': now(), 'auth_verified': True}
                S.save(status_path, state)
                return state
            out = runs_dir/dt.datetime.now().strftime('%Y%m%dT%H%M%S%f')
            out.mkdir()
            jobs = out/'source.jobs.json'
            # Copy from one open handle, then hash the actual immutable sync input.
            with source_path.open('rb') as source, jobs.open('wb') as target:
                shutil.copyfileobj(source, target, 1 << 20)
            source_sha = S.digest(jobs)
            semantic_hash = S.business_source_hash(jobs)
            if apply and previous.get('last_business_sha256') == semantic_hash and previous.get('last_success_at') and previous.get('sync_rule_version') == SYNC_RULE_VERSION:
                state.update(status='unchanged',last_source_sha256=source_sha,finished_at=now(),auth_verified=True)
                S.save(status_path,state);jobs.unlink();return state
            S.save(out/'source-receipt.json', {'sha256': source_sha, 'size': jobs.stat().st_size,
                                             'source': str(source_path), 'captured_at': now()})
            state.update(run_dir=str(out), phase='snapshot', status='running')
            S.save(status_path, state)
            S.snapshot(out)
            S.make_plan(out, jobs)
            if not apply:
                state.update(status='planned', finished_at=now())
                S.save(status_path, state)
                return state
            from qiuzhao.collector.lark_sync_enrichment import status_sync, append_p1, note_sync, business_sync, deduplicate_exact
            for phase, operation in [('update', lambda: S.apply_plan(out)),
                    ('business', lambda: business_sync(out, jobs)),
                    ('source_status', lambda: status_sync(out, jobs)),
                    ('append', lambda: append_p1(out, jobs)),
                    ('conditions', lambda: note_sync(out, jobs)),
                    ('deduplicate', lambda: deduplicate_exact(out,jobs))]:
                state['phase'] = phase
                S.save(status_path, state)
                operation()
            append_state = json.loads((out/'append-status.json').read_text(encoding='utf-8'))
            if append_state.get('capacity_blocked') or append_state.get('pending') or append_state.get('finished') is not True:
                raise RuntimeError('append reconciliation incomplete; inspect append-status.json')
            state.update(status='success', phase='complete', last_source_sha256=source_sha,last_business_sha256=semantic_hash,sync_rule_version=SYNC_RULE_VERSION,
                         last_success_at=now(), finished_at=now(), auth_verified=True)
            S.save(status_path, state)
            jobs.unlink()
            return state
        except Exception as error:
            state.update(status='failed', error=str(error)[:1000], finished_at=now())
            S.save(status_path, state)
            alert_sync_failed(state, status_path)
            raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir',type=Path,default=Path('research/qiuzhao-p1-sync-runtime'))
    p.add_argument('--runs-dir',type=Path,default=DEFAULT_RUNS)
    p.add_argument('--source-path',type=Path)
    p.add_argument('--apply',action='store_true')
    args=p.parse_args()
    result = (run_local(args.source_path,args.state_dir,args.runs_dir,args.apply)
              if args.source_path else run(args.state_dir,args.runs_dir))
    print(json.dumps(result,ensure_ascii=False))
    if result.get('status') not in {'success', 'unchanged', 'planned'}:
        raise SystemExit(1)


if __name__=='__main__':main()
