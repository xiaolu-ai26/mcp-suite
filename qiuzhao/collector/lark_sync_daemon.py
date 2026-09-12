"""One local user-session sync attempt; launchd supplies hourly/wake scheduling."""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
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

HOST='root@114.215.188.109'
SOURCE='/var/lib/mcp-suite/jobs.json'


def now():return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


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


def run(state_dir):
    state_dir=state_dir.resolve();state_dir.mkdir(parents=True,exist_ok=True)
    with (state_dir/'sync.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'status':'already_running'}
        status_path=state_dir/'status.json'
        previous=json.loads(status_path.read_text()) if status_path.exists() else {}
        state={**previous,'last_attempt_at':now(),'status':'checking','error':None}
        S.save(status_path,state)
        try:
            observed=source_hash();state['observed_source_sha256']=observed
            if observed==previous.get('last_source_sha256') and previous.get('last_success_at'):
                state.update(status='unchanged',finished_at=now());S.save(status_path,state);return state
            out=state_dir/'runs'/dt.datetime.now().strftime('%Y%m%dT%H%M%S');out.mkdir(parents=True)
            state.update(status='running',run_dir=str(out),phase='capture');S.save(status_path,state)
            jobs,source_sha=capture_source(out)
            # Explicit separate steps keep failures and partially completed writes
            # inspectable. lark-cli remains local under the logged-in user.
            steps=[('snapshot',['--snapshot']),('update',['--jobs',str(jobs),'--plan','--apply']),
                   ('append',['--jobs',str(jobs),'--append-p1']),('conditions',['--jobs',str(jobs),'--explain'])]
            child_env=dict(os.environ, QIUZHAO_LARK_SYNC_LOCK_PATH=str(state_dir/'sync.lock'),
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
            state.update(status='success',phase='complete',last_success_at=now(),last_source_sha256=source_sha,
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
            raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir',type=Path,default=Path('research/qiuzhao-p1-sync-runtime'))
    args=p.parse_args();print(json.dumps(run(args.state_dir),ensure_ascii=False))


if __name__=='__main__':main()
