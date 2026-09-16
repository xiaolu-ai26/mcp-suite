"""Serial Windows daily collector, isolated staging and CAS publication."""
import argparse
from collections import Counter
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qiuzhao.collector.portable_runtime import fcntl,stop_tree
from qiuzhao.collector.p1_pipeline import atomic_json
from qiuzhao.v4_fields import iter_json_file
from deploy.windows_rebase import CASConflict, publish_with_rebase
PYTHON=ROOT/'.venv/Scripts/python.exe'
SSH=['C:/Program Files/Git/usr/bin/ssh.exe','-i',str(ROOT/'keys/ecs_collector'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(ROOT/'keys/known_hosts'),'-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','root@114.215.188.109']

def sync_owner_ready(path=None):
    try:
        value=json.loads(Path(path or ROOT/'data/sync-owner-ready.json').read_text(encoding='utf-8'))
        return value.get('owner') == 'LZH' and value.get('old_mac_sync_drained') is True
    except (OSError,ValueError,AttributeError):
        return False


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def pull(path):
    with path.with_suffix('.transfer').open('wb') as out:
        subprocess.run(SSH+['snapshot'],stdout=out,check=True,timeout=600)
    with path.with_suffix('.transfer').open('rb') as source:
        before=source.readline().decode().strip()
        with gzip.GzipFile(fileobj=source,mode='rb') as compressed,path.open('wb') as out:shutil.copyfileobj(compressed,out,1048576)
    path.with_suffix('.transfer').unlink()
    if digest(path)!=before:raise ValueError('snapshot download hash mismatch')
    return before

def step(args,log,env,timeout):
    with log.open('ab') as out:
        child=subprocess.Popen([str(PYTHON),'-X','utf8',*args],cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        try:return child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_tree(child)
            return 124

def reset_p1(stage):
    shutil.rmtree(stage/'p1-checkpoints',ignore_errors=True)
    (stage/'p1-status.json').unlink(missing_ok=True)

def preserve(baseline,candidate):
    # A source's filtering must never erase unrelated existing records.
    rows={};candidate_counts=Counter();baseline_counts=Counter()
    for row in iter_json_file(candidate,strict=True):
        if not row.get('id'):continue  # Legacy anonymous rows are restored unchanged below.
        key=str(row['id'])
        candidate_counts[key]+=1
        if key in rows and rows[key]!=row:raise ValueError('conflicting candidate duplicate identity')
        rows[key]=row
    preserved=0
    baseline_seen={}
    anonymous=[]
    for row in iter_json_file(baseline,strict=True):
        if not row.get('id'):
            anonymous.append(row);continue
        key=str(row['id']);fingerprint=hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        baseline_counts[key]+=1
        if key in baseline_seen and baseline_seen[key]!=fingerprint:raise ValueError('conflicting baseline duplicate identity')
        baseline_seen[key]=fingerprint
        if str(row['id']) not in rows:rows[str(row['id'])]=row;preserved+=1
    identified=[row for key,row in rows.items() for _ in range(max(candidate_counts[key],baseline_counts[key]))]
    atomic_json(candidate,[*identified,*anonymous])
    return preserved,len(identified)+len(anonymous)

def publish_snapshot(candidate,expected_base,workdir):
    """Invoke the existing receiver; only version conflicts permit a rebase retry."""
    workdir=Path(workdir);workdir.mkdir(parents=True,exist_ok=True)
    after=digest(candidate);upload=workdir/'jobs.upload.gz'
    with gzip.open(upload,'wb',compresslevel=3) as out,Path(candidate).open('rb') as source:
        shutil.copyfileobj(source,out,1048576)
    with upload.open('rb') as source:
        result=subprocess.run(SSH+['publish '+expected_base+' '+after],stdin=source,capture_output=True,timeout=600)
    (workdir/'receiver.stdout').write_bytes(result.stdout)
    (workdir/'receiver.stderr').write_bytes(result.stderr)
    if result.returncode:
        error=result.stderr.decode('utf-8',errors='replace')
        if 'production changed: pull and recollect' in error or 'CAS mismatch' in error:
            raise CASConflict(error[-1200:])
        raise RuntimeError('receiver rejected publication: '+error[-1200:])
    publication=json.loads(result.stdout)
    if publication.get('published') is not True or publication.get('after_sha256')!=after:
        raise ValueError('receiver publication receipt mismatch')
    atomic_json(workdir/'receiver-receipt.json',publication)
    return publication

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke',action='store_true');parser.add_argument('--no-sync',action='store_true');parser.add_argument('--preflight',action='store_true');parser.add_argument('--resume-run',type=Path);a=parser.parse_args()
    if a.preflight:
        import getpass
        result=subprocess.run(SSH+['status'],capture_output=True,check=True,timeout=60)
        receipt=dict(identity=getpass.getuser(),utf8=sys.flags.utf8_mode,remote=json.loads(result.stdout),checked_at=dt.datetime.now().astimezone().isoformat())
        atomic_json(ROOT/'data/task-preflight.json',receipt);print(json.dumps(receipt));return 0
    ROOT.joinpath('data').mkdir(exist_ok=True)
    with open(ROOT/'data/windows-runner.lock','a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:return 75
        run=a.resume_run or ROOT/'runs'/((dt.datetime.now().strftime('%Y%m%dT%H%M%S') if a.smoke else dt.datetime.now().strftime('%Y%m%d'))+('-smoke' if a.smoke else ''))
        if a.resume_run:
            if not run.is_dir() or not run.resolve().is_relative_to((ROOT/'runs').resolve()):raise ValueError('invalid resume directory')
            if run.name.endswith('-smoke')!=a.smoke:raise ValueError('resume collection scope mismatch')
        run.mkdir(parents=True,exist_ok=True);stage=run/'data';stage.mkdir(exist_ok=True)
        statepath=run/'receipt.json';state=json.loads(statepath.read_text(encoding='utf-8')) if statepath.exists() else {'started_at':dt.datetime.now().astimezone().isoformat(),'steps':{}}
        if state.get('mode', 'smoke' if run.name.endswith('-smoke') else 'daily')!=('smoke' if a.smoke else 'daily'):raise ValueError('persisted collection scope mismatch')
        state['mode']='smoke' if a.smoke else 'daily'
        if state.get('error'):
            state.setdefault('previous_errors',[]).append(state.pop('error'))
            atomic_json(statepath,state)
        if state.get('finished'):return 0 if state.get('success') else 1
        try:
            baseline=run/'jobs.before.json'
            state['stage']='snapshot';atomic_json(statepath,state)
            if not baseline.exists() or not state.get('before_sha256'):
                state['before_sha256']=pull(baseline);atomic_json(statepath,state)
            if digest(baseline)!=state['before_sha256']:raise ValueError('baseline hash changed')
            if not (stage/'jobs.json').exists():shutil.copyfile(baseline,stage/'jobs.json')
            env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8',QIUZHAO_DATA_DIR=str(stage),QIUZHAO_SKIP_SERVICE_RESTART='1')
            steps=[('basic',['-m','qiuzhao.collector.run','--output-dir',str(stage),'--source','boc' if a.smoke else 'all','--delay','2'],180 if a.smoke else 7200)]
            if not a.smoke:
                steps += [('tencent',['-m','qiuzhao.collector.auto_collect','--skip-basic-collectors'],1800),('p1',['-m','qiuzhao.collector.p1_pipeline','--data-dir',str(stage),'--apply','--resume-latest','--timeout','1200','--max-run-seconds','18000'],18100)]
            steps += [('normalize',['-m','qiuzhao.normalize','--path',str(stage/'jobs.json')],1800)]
            for stale in run.glob('*.before.json'):
                if stale.name=='jobs.before.json':continue
                shutil.copyfile(stale,stage/'jobs.json');stale.unlink()
                if stale.name=='p1.before.json':reset_p1(stage)
                state['steps'].pop(stale.name.removesuffix('.before.json'),None)
                state['steps'].pop('normalize',None)
            for name,args,limit in steps:
                if state['steps'].get(name)!=0:
                    state['stage']=name;atomic_json(statepath,state)
                    pre_step=run/(name+'.before.json');temporary=pre_step.with_suffix('.tmp');shutil.copyfile(stage/'jobs.json',temporary);os.replace(temporary,pre_step)
                    try:
                        state['steps'][name]=step(args,run/(name+'.log'),env,limit)
                    except Exception:
                        shutil.copyfile(pre_step,stage/'jobs.json')
                        if name=='p1':reset_p1(stage)
                        raise
                    if name!='normalize':state['steps'].pop('normalize',None)
                    if state['steps'][name]!=0:
                        shutil.copyfile(pre_step,stage/'jobs.json')
                        if name=='p1':
                            reset_p1(stage)
                    pre_step.unlink();atomic_json(statepath,state)
            if state['steps']['normalize']!=0:raise ValueError('normalization failed; production retained')
            if all(state['steps'][name]!=0 for name in state['steps'] if name!='normalize'):raise ValueError('all collection stages failed; production retained')
            state['stage']='validate-and-publish';atomic_json(statepath,state)
            state['preserved_missing'],state['total_jobs']=preserve(baseline,stage/'jobs.json')
            after=digest(stage/'jobs.json')
            published=Path(state.get('publication_file') or stage/'jobs.json')
            same_publication=(state.get('publication_source_sha256')==after and published.is_file()
                              and digest(published)==state.get('publication',{}).get('after_sha256'))
            if not same_publication:
                work=run/'rebase'/dt.datetime.now().strftime('%Y%m%dT%H%M%S%f')
                result=publish_with_rebase(baseline,stage/'jobs.json',state['before_sha256'],work,pull,publish_snapshot)
                state['publication']=result['publication'];published=Path(result['published_path'])
                state['publication_file']=str(published);state['publication_source_sha256']=after
                state['rebase_receipt']=str(work/'receipt.json')
                state['collection_scope']='single-source-boc-smoke' if a.smoke else 'daily-pipeline';state['sync_requested']=not a.no_sync;atomic_json(statepath,state)
            shutil.copyfile(published,ROOT/'data/jobs.json')
            if not a.no_sync:
                if not sync_owner_ready():
                    raise ValueError('Base sync ownership handoff pending; old Mac writer must drain first')
                # Website publication already succeeded above. The Base mirror is
                # only an eventually-consistent consumer: hand the attested
                # published snapshot to the mirror queue, then run the bounded
                # incremental mirror under its own sync lock. A mirror failure is
                # recorded with its phase but never rolls back publication or
                # blocks the next collection; the persistent index/journal resume it.
                state['stage']='base-mirror';atomic_json(statepath,state)
                published_sha=digest(Path(published))
                from qiuzhao.collector import lark_sync_index as mirror_index
                state['mirror_intent']=mirror_index.enqueue_intent(ROOT/'data/mirror-queue',
                    published_path=ROOT/'data/jobs.json',sha256=published_sha,
                    published_receipt=state.get('publication'))
                atomic_json(statepath,state)
                mirror_state_path=ROOT/'data/lark-sync'
                try:
                    mirror_exit=step(['-m','qiuzhao.collector.lark_sync_index','--source',str(ROOT/'data/jobs.json'),
                        '--sha256',published_sha,'--index',str(mirror_state_path/'mirror-index.json'),
                        '--journal',str(mirror_state_path/'mirror-journal.json'),
                        '--run-dir',str(run/'mirror'),'--scope','complete'],run/'mirror.log',env,7200)
                except Exception as mirror_error:
                    mirror_exit=None
                    state['mirror_error']=type(mirror_error).__name__+': '+str(mirror_error)[:500]
                receipt_path=run/'mirror'/'mirror-receipt.json'
                state['mirror_receipt']=(json.loads(receipt_path.read_text(encoding='utf-8'))
                                         if receipt_path.exists() else {'status':'mirror_failed_no_receipt','exit_code':mirror_exit})
                state['mirror_receipt']['exit_code']=mirror_exit
                state['sync_exit']=0 if mirror_exit==0 else None
                atomic_json(statepath,state)
            state['finished']=all(v==0 for v in state['steps'].values());state['success']=all(v==0 for v in state['steps'].values())
        except Exception as e:
            state['error']=type(e).__name__+': '+str(e)[:500];state['success']=False
        state['stage']='completed' if state.get('success') else 'partial-or-failed'
        state['completed_at']=dt.datetime.now().astimezone().isoformat();atomic_json(statepath,state);atomic_json(ROOT/'data/windows-status.json',state)
        print(json.dumps(state,ensure_ascii=False));return 0 if state.get('success') else 1
if __name__=='__main__':raise SystemExit(main())
