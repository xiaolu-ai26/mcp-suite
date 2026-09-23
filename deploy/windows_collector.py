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
import time
import traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qiuzhao.collector.portable_runtime import fcntl,stop_tree
from qiuzhao.collector.p1_pipeline import atomic_json
from qiuzhao.v4_fields import iter_json_file
from deploy.windows_rebase import CASConflict, publish_with_rebase
PYTHON=ROOT/'.venv/Scripts/python.exe'
SSH=['C:/Program Files/Git/usr/bin/ssh.exe','-i',str(ROOT/'keys/ecs_collector'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(ROOT/'keys/known_hosts'),'-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','root@114.215.188.109']

# 2026-09-23: segment 2's publish called pull_snapshot -> ssh ... snapshot, which returned
# exit 255 (ssh's own "could not establish/keep the connection" code, never the remote
# command's exit status -- the receiver always forwards 0/1) with no retry, and that
# CalledProcessError climbed all the way out of run_p1_segments into main()'s catch-all.
# The day stopped there: 3,256 already-collected scopes stayed pending and no further
# segment ever ran, even though 67,700+ budget seconds were left. ssh's own transport
# failures (exit 255), a timeout, or a plain OSError are the only things retried here --
# a CAS conflict or a receiver-side rejection is not transient (retrying cannot change the
# answer and would blur what actually happened), so it is raised straight through and CAS
# semantics are exactly what they were.
SSH_RETRY_ATTEMPTS=3
SSH_RETRY_DELAYS=(10,30,90)

class PublishUnavailable(RuntimeError):
    """A publish-related ssh call stayed unreachable through every bounded retry.

    The caller must fail *this segment* closed: keep whatever was already verified
    locally (nothing rolled back), skip the publish, and let a later segment retry --
    never let one transient network drop abort the rest of the day's segments.
    """

class _Transient(Exception):
    """Internal signal: this attempt failed in a way retrying might fix."""

def _retry_transient(op_name,attempt_fn,*,receipt=None):
    errors=[]
    for attempt in range(1,SSH_RETRY_ATTEMPTS+1):
        try:
            return attempt_fn()
        except _Transient as error:
            errors.append(str(error))
        except (subprocess.TimeoutExpired,OSError) as error:
            errors.append(f'{type(error).__name__}: {error}')
        if receipt is not None:
            receipt.setdefault('ssh_retries',[]).append(
                {'op':op_name,'attempt':attempt,'error':errors[-1],
                 'at':dt.datetime.now().astimezone().isoformat()})
        if attempt==SSH_RETRY_ATTEMPTS:
            raise PublishUnavailable(
                f'{op_name} unreachable after {SSH_RETRY_ATTEMPTS} attempts: {errors[-1]}')
        time.sleep(SSH_RETRY_DELAYS[min(attempt-1,len(SSH_RETRY_DELAYS)-1)])

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

def pull(path,*,receipt=None):
    def attempt():
        try:
            with path.with_suffix('.transfer').open('wb') as out:
                subprocess.run(SSH+['snapshot'],stdout=out,check=True,timeout=600)
        except subprocess.CalledProcessError as error:
            if error.returncode==255:raise _Transient(str(error)) from error
            raise  # the remote side ran and failed; not a transport problem, do not retry
        with path.with_suffix('.transfer').open('rb') as source:
            before=source.readline().decode().strip()
            with gzip.GzipFile(fileobj=source,mode='rb') as compressed,path.open('wb') as out:shutil.copyfileobj(compressed,out,1048576)
        path.with_suffix('.transfer').unlink()
        if digest(path)!=before:raise ValueError('snapshot download hash mismatch')
        return before
    return _retry_transient('pull_snapshot',attempt,receipt=receipt)


# 2026-09-23's "basic" step: the collector VM's C: drive fell to ~0.6GB free mid-run. One
# source hit ENOSPC and logged it, then qiuzhao/collector/run.py's own write_json() hit a
# bare MemoryError serialising jobs.json -- Windows could not grow the page file with the
# disk that full, and no step-level try/except can make that safe after the fact. The
# only reliable fix is to never start a step or a segment without headroom it is likely to
# need, and fail closed with a clear reason before anything is written. This deliberately
# does not touch qiuzhao/collector/run.py (the "basic" collector) or attempt to reclaim
# space itself -- it only refuses to proceed when there plainly is not enough.
CAPACITY_MIN_FREE_BYTES=5*1024**3    # flat floor; today's crash happened under 1GB free
CAPACITY_SIZE_MULTIPLE=4             # candidate + gzip upload + pulled snapshot + merge

def capacity_check(paths,*,free_override=None):
    """``shutil.disk_usage(ROOT.anchor).free`` against a size-scaled reserve.

    ``paths`` are references for "how big is the current working set"; a missing path
    just contributes 0. Raises ``RuntimeError`` (the fail-closed signal) when free space
    is short of the reserve; otherwise returns the numbers for the receipt. Never raises
    for its own I/O reasons -- ``Path.stat()`` failures on a missing file are exactly what
    ``if p.exists()`` already screens out.
    """
    reference=max((Path(p).stat().st_size for p in paths if Path(p).exists()),default=0)
    required=max(CAPACITY_MIN_FREE_BYTES,CAPACITY_SIZE_MULTIPLE*reference)
    free=shutil.disk_usage(ROOT.anchor).free if free_override is None else free_override
    result={'free_bytes':free,'required_bytes':required,'reference_bytes':reference,
            'drive':ROOT.anchor,'passed':free>=required}
    if not result['passed']:
        raise RuntimeError('capacity gate: {} bytes free on {}, need >= {} (reference {} '
                           'bytes); blocked before collecting or publishing anything'.format(
                               free,ROOT.anchor,required,reference))
    return result

def record_cleanup(receipt,name,child):
    """Kill a timed-out child tree; never raise, always leave evidence in the receipt.

    Second line of defence behind the 2026-09-20 P0 fix (``portable_runtime.child_output``
    no longer raises on GBK/None taskkill output). On that day ``stop_tree(child)`` ran
    bare inside ``step()``'s ``except``, its TypeError escaped, ``steps['p1']`` was never
    written and a whole collected day was rolled back. Cleanup failing must stay a
    recorded 124 -- a process that would not die is a diagnostic, not the day's fate.
    """
    try:
        report=dict(stop_tree(child))
    except Exception as failure:
        report={'cleanup_error':type(failure).__name__+': '+str(failure)[:300],
                'cleanup_traceback':traceback.format_exc()}
    if receipt is not None:
        receipt.setdefault('cleanup_errors',[]).append({'step':name,'pid':child.pid,**report})
    return report

def step(args,log,env,timeout,receipt=None,name=None):
    with log.open('ab') as out:
        child=subprocess.Popen([str(PYTHON),'-X','utf8',*args],cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        try:return child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            report=record_cleanup(receipt,name,child)
            return 124 if report.get('tree_termination_confirmed') is True else 125

def reset_p1(stage):
    shutil.rmtree(stage/'p1-checkpoints',ignore_errors=True)
    (stage/'p1-status.json').unlink(missing_ok=True)

# The chain used to run p1 exactly once and publish exactly once, after every stage had
# finished. 2026-09-20 showed why that cannot survive 1124 companies: p1 was killed while
# finalising, so 958 collected units (19,619 new rows) were rolled back and the day
# published nothing at all. p1 is now run as a series of segments, and every segment is
# normalized and published on its own, so the loss window is one segment.
#
# No new publication logic is involved. One segment = ``p1 --resume-latest`` with a short
# ``--max-run-seconds`` (p1's own deadline is already an orderly stop: it stops starting
# units, drains the unit in flight, writes ``pending`` and exits 2), followed by the same
# ``normalize`` + ``preserve`` + ``publish_with_rebase`` pair the chain always ran at the
# end, with ``same_publication`` suppressing the upload when staging did not change.
P1_SEGMENT_SECONDS=1800      # 90 min of collection per segment
P1_SCOPE_TIMEOUT=600         # unchanged per-scope subprocess timeout
# p1 only checks its deadline between units, so one unit in flight may still be draining
# (up to --scope-timeout) and the run then has to merge, publish locally, write its
# status/checkpoint and emit the daily gap report. The parent watchdog must outlast all of
# that: on 2026-09-20 it was deadline+100s and it killed p1 inside exactly that window.
P1_SEGMENT_FINALIZE_BUDGET=600
P1_SEGMENT_STEP_LIMIT=P1_SEGMENT_SECONDS+P1_SCOPE_TIMEOUT+P1_SEGMENT_FINALIZE_BUDGET
# Backstop against a runaway segment loop, checked at segment boundaries only. Reaching it
# stops the *next* segment from starting: the checkpoint stays, every finished segment is
# already published, and no running p1 is ever killed for it.
P1_TOTAL_BUDGET_SECONDS=72000
P1_SEGMENT_RETRY_LIMIT=1     # extra attempt after exit 1 (no scope produced usable output)
P1_MAX_STALLED_SEGMENTS=2    # stop once ``pending`` has not shrunk for this many segments
P1_WORKERS=8
P1_PLATFORM_WORKERS=1
# --platform-interval is left at p1_pipeline's default (PLATFORM_MIN_INTERVAL = 1.0s).
P1_MEMORY_NOTE='8 workers initially; same-platform concurrency 1; max 20 companies or 1800s per segment'

def p1_segment_args(stage,seconds):
    """p1 argv for one segment; ``--resume-latest`` continues the previous checkpoint."""
    return ['-m','qiuzhao.collector.p1_pipeline','--data-dir',str(stage),'--apply','--resume-latest',
            '--scope-timeout',str(P1_SCOPE_TIMEOUT),'--workers',str(P1_WORKERS),
            '--platform-workers',str(P1_PLATFORM_WORKERS),'--max-run-seconds',str(seconds)]

def steps_for(stage,smoke):
    """Single-run stages plus the p1 segment template and its per-segment normalize.

    ``main`` runs ``basic``/``tencent`` once and then drives ``p1`` as a segment loop
    (``run_p1_segments``), where ``normalize`` runs once per segment. Smoke mode runs the
    returned list as-is and publishes the single result. ``P1_SEGMENT_STEP_LIMIT`` is the
    watchdog for ONE segment, never for the whole day.
    """
    steps=[('basic',['-m','qiuzhao.collector.run','--output-dir',str(stage),'--source','boc' if smoke else 'all','--delay','2'],180 if smoke else 7200)]
    if not smoke:
        steps += [('tencent',['-m','qiuzhao.collector.auto_collect','--skip-basic-collectors'],1800),
                  ('p1',p1_segment_args(stage,P1_SEGMENT_SECONDS),P1_SEGMENT_STEP_LIMIT)]
    steps += [('normalize',['-m','qiuzhao.normalize','--path',str(stage/'jobs.json')],1800)]
    return steps

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

def collection_gap_summary(run, stage):
    """Key numbers of the daily collection-gap report, for receipt.json.

    The p1 stage writes ``runs/<date>/collection-gap.json`` in its own finalisation
    step.  On 2026-09-20 p1 hit its 18000s deadline and was killed by this chain's
    18100s step timeout *before* that step could run, so the report must be
    rebuildable from the p1 run status -- otherwise the daily numbers vanish exactly
    on the days they matter most.  Never raises: a missing report must not fail a run.
    """
    gap_path=run/'collection-gap.json'
    try:
        if not gap_path.is_file():
            import importlib
            status_paths=sorted((stage/'p1-runs').glob('*/status.json'),
                                key=lambda item:item.stat().st_mtime)
            if status_paths:
                report=importlib.import_module('qiuzhao.collector.collection_gap')
                status=json.loads(status_paths[-1].read_text(encoding='utf-8'))
                report.publish(status,run)
        if gap_path.is_file():
            gap=json.loads(gap_path.read_text(encoding='utf-8'))
            return {**(gap.get('summary') or {}),'available':True,'date':gap.get('date'),'report':str(gap_path)}
        return {'available':False,'reason':'collection-gap.json missing and no p1 run status to rebuild it from'}
    except Exception as gap_failure:
        return {'available':False,'error':type(gap_failure).__name__+': '+str(gap_failure)[:200]}


def diff_counts(before, after):
    """Row-level deltas of one stage, so 'ran but nothing landed' is visible in the receipt."""
    def snapshot(path):
        rows = {}
        for row in iter_json_file(path, strict=True):
            if not row.get('id'):
                continue
            fingerprint = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            rows[str(row['id'])] = (fingerprint, row.get('status'))
        return rows
    old, new = snapshot(before), snapshot(after)
    changes = {'added': 0, 'updated': 0, 'marked_removed': 0, 'disappeared': 0}
    for key, (fingerprint, status) in new.items():
        if key not in old:
            changes['added'] += 1
            continue
        old_fingerprint, old_status = old[key]
        if fingerprint == old_fingerprint:
            continue
        if status == 'removed' and old_status != 'removed':
            changes['marked_removed'] += 1
        else:
            changes['updated'] += 1
    changes['disappeared'] = sum(1 for key in old if key not in new)
    return changes

def publish_snapshot(candidate,expected_base,workdir,*,receipt=None):
    """Invoke the existing receiver; only version conflicts permit a rebase retry."""
    workdir=Path(workdir);workdir.mkdir(parents=True,exist_ok=True)
    after=digest(candidate);upload=workdir/'jobs.upload.gz'
    with gzip.open(upload,'wb',compresslevel=3) as out,Path(candidate).open('rb') as source:
        shutil.copyfileobj(source,out,1048576)
    def attempt():
        with upload.open('rb') as source:
            completed=subprocess.run(SSH+['publish '+expected_base+' '+after],stdin=source,capture_output=True,timeout=600)
        if completed.returncode==255:
            raise _Transient('ssh transport failure (exit 255): '
                             +completed.stderr.decode('utf-8',errors='replace')[-500:])
        return completed
    result=_retry_transient('publish_snapshot',attempt,receipt=receipt)
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

def row_count(path):
    """Records in a snapshot, legacy anonymous rows included. Reporting only."""
    return sum(1 for _ in iter_json_file(path,strict=True))

def p1_status(stage):
    """``<stage>/p1-status.json`` as a dict; {} when missing, unreadable or not an object."""
    try:
        value=json.loads((Path(stage)/'p1-status.json').read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):
        return {}

def run_stage_step(state,statepath,run,stage,name,args,limit,env,*,force=False,keep_exit_codes=()):
    """One stage process with the 2026-09-18 partial-keep contract.

    Exit 2 = partial success: the stage's validated output is kept (no rollback, no p1
    reset). Any other non-zero exit rolls the staging file back to the pre-step snapshot,
    except for exits listed in ``keep_exit_codes`` -- a p1 watchdog timeout (124) keeps its
    staging and its checkpoint, because p1 publishes per unit through atomic replaces and
    throwing a segment away is exactly what this change exists to stop. ``force`` runs the
    stage even when a previous invocation recorded 0, which is how p1 segments re-enter.
    """
    if not force and state['steps'].get(name)==0:return 0
    state['stage']=name;atomic_json(statepath,state)
    pre_step=run/(name+'.before.json');temporary=pre_step.with_suffix('.tmp')
    shutil.copyfile(stage/'jobs.json',temporary);os.replace(temporary,pre_step)
    try:
        state['steps'][name]=step(args,run/(name+'.log'),env,limit,state,name)
    except Exception:
        shutil.copyfile(pre_step,stage/'jobs.json')
        if name=='p1':reset_p1(stage)
        raise
    # cleanup_errors (a child tree that would not die) must be durable immediately: the
    # 2026-09-20 receipt had no p1 entry at all because the write happened too late.
    atomic_json(statepath,state)
    if state['steps'][name]==125:
        state['unsafe_writer']={'step':name,'reason':'process tree termination unconfirmed; no rollback, normalize, publish or next segment'}
        atomic_json(statepath,state)
        raise RuntimeError(state['unsafe_writer']['reason'])
    if name!='normalize':state['steps'].pop('normalize',None)
    entries=state.setdefault('step_changes',{})
    if state['steps'][name] not in (0,2):
        if state['steps'][name] in keep_exit_codes:
            entries[name]={'exit':state['steps'][name],'result':'kept'}
        else:
            shutil.copyfile(pre_step,stage/'jobs.json')
            if name=='p1':reset_p1(stage)
            entries[name]={'exit':state['steps'][name],'result':'rolled_back'}
    else:
        # diff_counts is reporting-only: its failure must never abort the run.
        try:
            changes=diff_counts(pre_step,stage/'jobs.json')
        except Exception as diff_failure:
            changes={'diff_error':type(diff_failure).__name__+': '+str(diff_failure)[:200]}
        entries[name]=dict({'exit':state['steps'][name],
                            'result':'ok' if state['steps'][name]==0 else 'partial'},**changes)
    pre_step.unlink();atomic_json(statepath,state)
    return state['steps'][name]

def freeze_new_removed(baseline,candidate,*,write=True):
    old={str(row['id']):row for row in iter_json_file(baseline,strict=True) if row.get('id')}
    rows=list(iter_json_file(candidate,strict=True));changed=[]
    for i,row in enumerate(rows):
        prior=old.get(str(row.get('id') or ''))
        if prior is not None and prior.get('status')!='removed' and row.get('status')=='removed':
            changed.append(str(row['id']))
            if write:rows[i]=prior
    if write and changed:atomic_json(candidate,rows)
    if not write and changed:raise ValueError('new removed lifecycle change rejected at publication boundary')
    return changed

def publish_stage(state,statepath,run,stage,baseline,*,smoke,no_sync):
    """``preserve()`` + ``publish_with_rebase()`` for the rows currently in staging.

    Returns a receipt fragment. ``same_publication`` (staging unchanged since the last
    publication and the published bytes still match) skips the upload, so a segment that
    collected nothing new never re-transfers the ~358MB library.
    """
    state['stage']='validate-and-publish';atomic_json(statepath,state)
    state['removed_frozen']=freeze_new_removed(baseline,stage/'jobs.json')
    state['preserved_missing'],state['total_jobs']=preserve(baseline,stage/'jobs.json')
    after=digest(stage/'jobs.json')
    published=Path(state.get('publication_file') or stage/'jobs.json')
    same_publication=(state.get('publication_source_sha256')==after and published.is_file()
                      and digest(published)==state.get('publication',{}).get('after_sha256'))
    before_rows=state.get('server_rows')
    outcome={'action':'unchanged','source_sha256':after,'server_rows_before':before_rows,
             'server_rows_after':before_rows,
             'reason':'staging and published bytes are identical (same_publication)'}
    if not same_publication:
        work=run/'rebase'/dt.datetime.now().strftime('%Y%m%dT%H%M%S%f')
        def guarded_publish(candidate,expected,folder):
            reference=folder.parent/'latest.jobs.json' if (folder.parent/'latest.jobs.json').exists() else baseline
            if digest(reference)!=expected:raise ValueError('publication lifecycle reference hash mismatch')
            freeze_new_removed(reference,candidate,write=False)
            return publish_snapshot(candidate,expected,folder,receipt=state)
        result=publish_with_rebase(baseline,stage/'jobs.json',state['before_sha256'],work,
                                   lambda path:pull(path,receipt=state),guarded_publish)
        state['publication']=result['publication'];published=Path(result['published_path'])
        state['publication_file']=str(published);state['publication_source_sha256']=after
        state['rebase_receipt']=str(work/'receipt.json')
        state['collection_scope']='single-source-boc-smoke' if smoke else 'daily-pipeline'
        state['sync_requested']=not no_sync
        report=result.get('rebase_report') or {}
        after_rows=report.get('merged_rows') if report else state.get('total_jobs')
        outcome={'action':'published','direct':not report,'source_sha256':after,
                 'server_rows_before':before_rows,'server_rows_after':after_rows,
                 'added_rows':report.get('added_rows'),'conflicts':len(report.get('conflicts') or []),
                 'rebase_attempts':len(result.get('attempts') or []),
                 'publication':result['publication']}
        state['server_rows']=after_rows
    # The local mirror must follow every publication, deduped or not.
    shutil.copyfile(published,ROOT/'data/jobs.json')
    atomic_json(statepath,state)
    return outcome

def run_p1_segments(state,statepath,run,stage,baseline,env,steps,*,smoke,no_sync):
    """Drive p1 as segments; each segment is normalized and published before the next one.

    Returns when p1 reports ``run_finished`` with an empty ``pending`` list, or when a
    guard fires (total budget, a stalled ``pending`` count, a watchdog timeout, exit 1, a
    failed normalize). Every finished segment is already published by then, and the
    checkpoint stays on disk so ``--resume-run``/the next day continue where this stopped.
    """
    segments=state.setdefault('p1_segments',[])
    args,limit=steps['p1'];normalize_args,normalize_limit=steps['normalize']
    state['p1_concurrency']={'workers':P1_WORKERS,'platform_workers':P1_PLATFORM_WORKERS,
                             'platform_min_interval':1.0,'memory':P1_MEMORY_NOTE,
                             'segment_seconds':P1_SEGMENT_SECONDS,'segment_step_limit':limit,
                             'total_budget_seconds':P1_TOTAL_BUDGET_SECONDS}
    def close_segment(record):
        """normalize + publish one segment, persisting the receipt before and after the upload.

        The record is appended to ``state['p1_segments']`` *before* publication, so a failing
        upload still leaves that segment's exit code, ``step_changes`` and ``pending`` count in
        receipt.json -- the 2026-09-20 lesson was that evidence written last is evidence lost.

        A publish-related ssh call that stays unreachable through every bounded retry
        (``PublishUnavailable``, see ``_retry_transient``) fails *this segment* closed
        instead of the day: staging keeps exactly what was normalized (nothing rolled
        back, CAS semantics untouched -- the next successful publish carries this
        segment's changes forward too), and the loop below keeps starting further
        segments. 2026-09-23 lost 3,256 pending scopes to one such call aborting the
        whole remaining day; this is what stops that from happening again.
        """
        record['normalize_exit']=run_stage_step(state,statepath,run,stage,'normalize',
                                                normalize_args,normalize_limit,env)
        status=p1_status(stage)
        record['run_finished']=status.get('run_finished') is True
        record['pending_count']=len(status.get('pending') or [])
        entries=state.get('step_changes') or {}
        record['step_changes']={name:entries[name] for name in ('p1','normalize') if name in entries}
        segments.append(record);atomic_json(statepath,state)
        try:
            if record['normalize_exit'] in (0,2):
                # Publishing un-normalized rows would be worse than publishing nothing.
                try:
                    record['publication']=publish_stage(state,statepath,run,stage,baseline,
                                                        smoke=smoke,no_sync=no_sync)
                except PublishUnavailable as error:
                    record['publication']={'action':'deferred','reason':str(error)[:800]}
                    state.setdefault('publish_deferrals',[]).append(
                        {'segment':record['segment'],'reason':str(error)[:800],
                         'at':dt.datetime.now().astimezone().isoformat()})
            else:
                record['publication']={'action':'blocked','reason':'normalize failed; staging kept but not published'}
        finally:
            record['finished_at']=dt.datetime.now().astimezone().isoformat()
            record['elapsed_seconds']=round(time.monotonic()-record.pop('_started'),1)
            atomic_json(statepath,state)
        return status
    status=p1_status(stage)
    if status.get('run_finished') is True:
        # ``--resume-run`` after a finished p1: never re-run a finished segment. The
        # normalize+publish pair still runs, and same_publication suppresses the upload.
        record={'_started':time.monotonic(),'segment':len(segments)+1,
                'started_at':dt.datetime.now().astimezone().isoformat(),
                'note':'p1 already reported run_finished; no segment re-run'}
        close_segment(record)
        state['steps'].setdefault('p1',0)
        state['p1_finished']=True
        return
    started=time.monotonic();stalled=0;previous_pending=None;stop=None
    while stop is None:
        elapsed=time.monotonic()-started
        if elapsed>=P1_TOTAL_BUDGET_SECONDS:
            state['p1_budget']={'exhausted':True,'budget_seconds':P1_TOTAL_BUDGET_SECONDS,
                                'elapsed_seconds':round(elapsed,1),'stopped_at':'segment-boundary',
                                'detail':'no new segment started; finished segments are published'}
            stop='total budget reached at a segment boundary'
            break
        try:
            state['capacity']=capacity_check([stage/'jobs.json'])
        except RuntimeError as error:
            state['capacity']={'passed':False,'error':str(error)}
            stop=str(error)
            break
        record={'_started':time.monotonic(),'segment':len(segments)+1,
                'started_at':dt.datetime.now().astimezone().isoformat(),
                'budget_elapsed_seconds':round(elapsed,1),
                'segment_seconds':P1_SEGMENT_SECONDS,'step_limit':limit,'attempts':[]}
        cleanup_before=len(state.get('cleanup_errors') or [])
        attempt_started=time.monotonic()
        for attempt in range(P1_SEGMENT_RETRY_LIMIT+1):
            code=run_stage_step(state,statepath,run,stage,'p1',args,limit,env,force=True,
                                keep_exit_codes=(124,))
            record['attempts'].append(code)
            if code in (0,2):break
            if code==1 and attempt<P1_SEGMENT_RETRY_LIMIT:
                record['retry_reason']='exit 1: no scope produced trustworthy output; checkpoint reset then retried once'
                continue
            break
        code=record['exit']=record['attempts'][-1]
        record['p1_seconds']=round(time.monotonic()-attempt_started,1)
        record['cleanup_errors']=(state.get('cleanup_errors') or [])[cleanup_before:]
        status=close_segment(record)
        if status.get('run_finished') is True and not status.get('pending'):
            state['p1_finished']=True;break
        if code==1:
            stop='p1 exited 1 (no trustworthy output) on every attempt';break
        if code==124:
            stop='p1 watchdog fired; staging and checkpoint kept for the next segment or resume';break
        if record['normalize_exit'] not in (0,2):
            stop='normalize failed; later segments would repeat it';break
        if not status:
            stop='p1-status.json missing or unreadable after the segment; cannot prove progress';break
        pending=record['pending_count']
        stalled=stalled+1 if (previous_pending is not None and pending>=previous_pending) else 0
        previous_pending=pending
        if stalled>=P1_MAX_STALLED_SEGMENTS:
            stop=f'pending stopped shrinking for {stalled} consecutive segments';break
    state['p1_finished']=bool(state.get('p1_finished'))
    current=p1_status(stage)
    if not state['p1_finished']:
        # The loop stopped with work left. Exit 0 from a segment would claim the day is
        # complete; downgrade it to 2 (partial) so the receipt and the exit code agree.
        if state['steps'].get('p1')==0:state['steps']['p1']=2
        state['p1_pending']=list(current.get('pending') or [])
    if stop:
        state['p1_stopped']={'reason':stop,'stopped_at':'segment-boundary','segments':len(segments),
                             'pending_count':len(current.get('pending') or []),
                             'pending':list(current.get('pending') or [])[:200]}
    atomic_json(statepath,state)

def runner_skipped_alert(smoke):
    """Record that a second daily run was skipped because the runner lock is held (exit 75).

    ``data/windows-runner.lock`` is a non-blocking flock, so a 06:10 run that overlaps a
    long collection exits cleanly -- and silently, which is how "the pipeline only ran once
    for days" stays invisible. This always appends a structured record to
    ``data/runner-skipped.jsonl`` and additionally sends a Feishu alert when this branch
    carries the cc-bot notifier (``qiuzhao/notify.py``, branch ``feat/cc-bot-notifier``;
    without it the JSONL record says so). Both paths are best effort: an alert must never
    be the reason the runner fails.
    """
    record={'ts':dt.datetime.now().astimezone().isoformat(),'event':'runner_skipped','exit_code':75,
            'mode':'smoke' if smoke else 'daily','previous':{}}
    try:
        previous=json.loads((ROOT/'data/windows-status.json').read_text(encoding='utf-8'))
        record['previous']={key:previous.get(key) for key in
                            ('started_at','stage','finished','success','completed_at','total_jobs','sync_exit')}
    except (OSError,ValueError):
        record['previous']={'status_file':'missing or unreadable'}
    record['reason']=('another windows_collector run still holds data/windows-runner.lock; '
                      'this invocation exited 75 without collecting, publishing or syncing')
    record['message']=('上一轮采集仍在运行，本次跳过（exit 75）。\n'
                       f"mode={record['mode']}\n"
                       f"previous.started_at={record['previous'].get('started_at')}\n"
                       f"previous.stage={record['previous'].get('stage')}\n"
                       'no second collector was started, nothing was collected or published.')
    try:
        from qiuzhao import notify as notifier
    except ImportError:
        record['notified']=('unavailable: qiuzhao.notify is not in this branch; merge '
                            'feat/cc-bot-notifier to deliver this over Feishu')
    else:
        try:
            record['notified']=notifier.notify('runner_skipped',text=record['message'])
        except Exception as failure:
            record['notified']='failed: '+type(failure).__name__+': '+str(failure)[:200]
    try:
        with (ROOT/'data/runner-skipped.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(record,ensure_ascii=False)+'\n')
    except OSError as failure:
        record['record_error']=type(failure).__name__+': '+str(failure)[:200]
    return record

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke',action='store_true');parser.add_argument('--no-sync',action='store_true',default=True);parser.add_argument('--preflight',action='store_true');parser.add_argument('--resume-run',type=Path);a=parser.parse_args()
    if a.preflight:
        import getpass
        result=subprocess.run(SSH+['status'],capture_output=True,check=True,timeout=60)
        receipt=dict(identity=getpass.getuser(),utf8=sys.flags.utf8_mode,remote=json.loads(result.stdout),checked_at=dt.datetime.now().astimezone().isoformat())
        atomic_json(ROOT/'data/task-preflight.json',receipt);print(json.dumps(receipt));return 0
    ROOT.joinpath('data').mkdir(exist_ok=True)
    with open(ROOT/'data/windows-runner.lock','a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            runner_skipped_alert(a.smoke)
            return 75
        run=a.resume_run or ROOT/'runs'/((dt.datetime.now().strftime('%Y%m%dT%H%M%S') if a.smoke else dt.datetime.now().strftime('%Y%m%d'))+('-smoke' if a.smoke else ''))
        if a.resume_run:
            if not run.is_dir() or not run.resolve().is_relative_to((ROOT/'runs').resolve()):raise ValueError('invalid resume directory')
            if run.name.endswith('-smoke')!=a.smoke:raise ValueError('resume collection scope mismatch')
        run.mkdir(parents=True,exist_ok=True);stage=run/'data';stage.mkdir(exist_ok=True)
        statepath=run/'receipt.json';state=json.loads(statepath.read_text(encoding='utf-8')) if statepath.exists() else {'started_at':dt.datetime.now().astimezone().isoformat(),'steps':{}}
        if state.get('mode', 'smoke' if run.name.endswith('-smoke') else 'daily')!=('smoke' if a.smoke else 'daily'):raise ValueError('persisted collection scope mismatch')
        state['mode']='smoke' if a.smoke else 'daily'
        if state.get('unsafe_writer'):raise RuntimeError('unsafe writer requires confirmed termination before resume')
        if state.get('error'):
            state.setdefault('previous_errors',[]).append(state.pop('error'))
            atomic_json(statepath,state)
        if state.get('finished'):return 0 if state.get('success') else 1
        try:
            baseline=run/'jobs.before.json'
            state['capacity']=capacity_check([ROOT/'data/jobs.json',baseline])
            state['stage']='snapshot';atomic_json(statepath,state)
            if not baseline.exists() or not state.get('before_sha256'):
                state['before_sha256']=pull(baseline,receipt=state)
                atomic_json(statepath,state)
            # Server row count at run start, so every segment can report before/after. A
            # receipt persisted by an older bundle has no such field; fill it in on resume.
            if 'server_rows' not in state:
                state['server_rows']=row_count(baseline);atomic_json(statepath,state)
            if digest(baseline)!=state['before_sha256']:raise ValueError('baseline hash changed')
            if not (stage/'jobs.json').exists():shutil.copyfile(baseline,stage/'jobs.json')
            env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8',QIUZHAO_DATA_DIR=str(stage),QIUZHAO_SKIP_SERVICE_RESTART='1')
            steps=steps_for(stage,a.smoke);by_name={name:(args,limit) for name,args,limit in steps}
            for stale in run.glob('*.before.json'):
                if stale.name=='jobs.before.json':continue
                shutil.copyfile(stale,stage/'jobs.json');stale.unlink()
                if stale.name=='p1.before.json':reset_p1(stage)
                state['steps'].pop(stale.name.removesuffix('.before.json'),None)
                state['steps'].pop('normalize',None)
            # basic/tencent run once; p1 runs as a loop of segments, each of which
            # normalizes and publishes on its own (run_p1_segments). Smoke mode is the
            # single-shot shape and keeps the original contract.
            for name,args,limit in steps:
                if a.smoke or name in ('basic','tencent'):
                    run_stage_step(state,statepath,run,stage,name,args,limit,env)
            # Daily mode publishes inside every segment, so a segment lands before the next
            # one starts. Smoke mode keeps the original ordering: publish only after the
            # guards below, so a failed smoke run still leaves production untouched.
            if not a.smoke:
                run_p1_segments(state,statepath,run,stage,baseline,env,by_name,
                                smoke=False,no_sync=a.no_sync)
            # Daily collection-gap report: the p1 stage writes runs/<date>/collection-gap.json
            # (expected_total vs collected_jobs for every unit). Surface its key numbers in
            # the receipt; a missing/broken report must never fail the run.
            state['collection_gap']=collection_gap_summary(run,stage)
            if state['steps']['normalize']!=0:raise ValueError('normalization failed; production retained')
            if all(state['steps'][name] not in (0,2) for name in state['steps'] if name!='normalize'):raise ValueError('all collection stages failed; production retained')
            if a.smoke:
                publish_stage(state,statepath,run,stage,baseline,smoke=True,no_sync=a.no_sync)
            if not a.no_sync:
                if not sync_owner_ready():
                    raise ValueError('Base sync ownership handoff pending; old Mac writer must drain first')
                state['stage']='base-sync';atomic_json(statepath,state)
                state['sync_exit']=step(['-m','qiuzhao.collector.lark_sync_daemon','--source-path',str(ROOT/'data/jobs.json'),'--state-dir',str(ROOT/'data/lark-sync'),'--runs-dir',str(ROOT/'data/lark-sync/runs'),'--apply'],run/'sync.log',env,21600,state,'base-sync')
            state['finished']=all(v==0 for v in state['steps'].values()) and (a.no_sync or state.get('sync_exit')==0);state['success']=all(v==0 for v in state['steps'].values()) and (a.no_sync or state.get('sync_exit')==0)
        except Exception as e:
            # Keep the full traceback, not just the message: on 2026-09-20 the receipt
            # stored only "TypeError: 'NoneType' object is not subscriptable", so the
            # raising line had to be reconstructed from logs a second time.
            state['error']=type(e).__name__+': '+str(e)[:500]
            state['error_step']=state.get('stage')
            state['error_traceback']=traceback.format_exc()
            state['success']=False
        state['stage']='completed' if state.get('success') else 'partial-or-failed'
        state['completed_at']=dt.datetime.now().astimezone().isoformat();atomic_json(statepath,state);atomic_json(ROOT/'data/windows-status.json',state)
        print(json.dumps(state,ensure_ascii=False));return 0 if state.get('success') else 1
if __name__=='__main__':raise SystemExit(main())
