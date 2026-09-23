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
from deploy.windows_rebase import CASConflict, publish_with_rebase, rebase_files
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
# 2026-09-24: the server-side dataset activation (deploy/activate_qiuzhao_dataset.py) holds the
# receiver's collector.lock for at most ~220 s (sample, stop, start, one <=120 s warm, re-sample).
# The receiver's publish takes that lock non-blocking and dies with BlockingIOError; that is a
# busy lock, not a rejection. Wait it out (390 s in total) and then defer the segment -- never
# end the day for it.
RECEIVER_BUSY_DELAYS=(30,60,120,180)

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
# workers/company-budget/--batch-publish below are exactly what the 2026-09-21/22
# 796-company recovery ran through all 1069 companies to completion (proven in
# mcp-suite-recovery-20260921/segment18-receipt.json: workers=16, platform_workers=1),
# only never wired into this daily entry point before. p1_pipeline.py itself already
# supports all three unmodified -- see the 2026-09-23 baseline-capture commit.
P1_WORKERS=16
P1_PLATFORM_WORKERS=1
# --platform-interval is left at p1_pipeline's default (PLATFORM_MIN_INTERVAL = 1.0s).
P1_COMPANY_BUDGET=40          # QIUZHAO_P1_COMPANY_BUDGET; p1_pipeline.py default is 20
P1_MEMORY_NOTE=('16 workers; same-platform concurrency 1; max 40 companies or 1800s per '
                'segment; --batch-publish (segment writes stage/jobs.json once, not once '
                'per scope)')

def p1_segment_args(stage,seconds):
    """p1 argv for one segment; ``--resume-latest`` continues the previous checkpoint."""
    return ['-m','qiuzhao.collector.p1_pipeline','--data-dir',str(stage),'--apply','--resume-latest',
            '--batch-publish','--scope-timeout',str(P1_SCOPE_TIMEOUT),'--workers',str(P1_WORKERS),
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
    """Row-level deltas of one stage, so 'ran but nothing landed' is visible in the receipt.

    ``updated`` counts business changes only, with the same rule p1's own publish uses
    (``qiuzhao.normalize.business_value`` drops reviewed_at, list/detail check times and
    evidence paths). A row whose only change is a fresh observation is ``observed_only``;
    it is not a content update.
    """
    from qiuzhao.normalize import business_value

    def fingerprint(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def snapshot(path):
        rows = {}
        for row in iter_json_file(path, strict=True):
            if not row.get('id'):
                continue
            rows[str(row['id'])] = (fingerprint(row), fingerprint(business_value(row)), row.get('status'))
        return rows
    old, new = snapshot(before), snapshot(after)
    changes = {'added': 0, 'updated': 0, 'observed_only': 0, 'marked_removed': 0, 'disappeared': 0}
    for key, (whole, business, status) in new.items():
        if key not in old:
            changes['added'] += 1
            continue
        old_whole, old_business, old_status = old[key]
        if whole == old_whole:
            continue
        if status == 'removed' and old_status != 'removed':
            changes['marked_removed'] += 1
        elif business == old_business:
            changes['observed_only'] += 1
        else:
            changes['updated'] += 1
    changes['disappeared'] = sum(1 for key in old if key not in new)
    return changes

def receiver_busy(completed):
    """The receiver could not take collector.lock (LOCK_NB): someone else holds it right now."""
    return completed.returncode not in (0,255) and b'BlockingIOError' in (completed.stderr or b'')

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
    for busy in range(len(RECEIVER_BUSY_DELAYS)+1):
        result=_retry_transient('publish_snapshot',attempt,receipt=receipt)
        if not receiver_busy(result):break
        if receipt is not None:
            receipt.setdefault('receiver_busy',[]).append({'attempt':busy+1,'at':dt.datetime.now().astimezone().isoformat()})
        if busy==len(RECEIVER_BUSY_DELAYS):
            raise PublishUnavailable('receiver lock stayed busy (dataset activation) through %d waits; '
                                     'segment deferred' % len(RECEIVER_BUSY_DELAYS))
        time.sleep(RECEIVER_BUSY_DELAYS[busy])
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

def prepare_candidate(reference,candidate):
    """The lifecycle + completeness pair every publication runs on its candidate.

    ``freeze_new_removed`` puts back rows this candidate would newly mark ``removed``
    (retirement stays conservative), ``preserve`` restores reference rows the
    candidate lost. The normal segment path and ``windows_recover_run`` both call
    this; recovery must not get a weaker version of it.
    """
    frozen=freeze_new_removed(reference,candidate)
    preserved,total=preserve(reference,candidate)
    return frozen,preserved,total

def guarded_publish_snapshot(baseline,*,receipt=None):
    """``publish_snapshot`` behind the publication-boundary lifecycle guard.

    The reference is the snapshot the receiver is expected to hold: the pulled
    ``latest.jobs.json`` of a rebase attempt, otherwise ``baseline``. A candidate that
    newly retires a row relative to it is refused, whichever path is publishing.
    """
    baseline=Path(baseline)
    def publish(candidate,expected,folder):
        folder=Path(folder)
        latest=folder.parent/'latest.jobs.json'
        reference=latest if latest.exists() else baseline
        if digest(reference)!=expected:raise ValueError('publication lifecycle reference hash mismatch')
        freeze_new_removed(reference,candidate,write=False)
        return publish_snapshot(candidate,expected,folder,receipt=receipt)
    return publish

def refuse_unsafe_writer(state):
    """Same gate for resume, publication and recovery: an unconfirmed writer blocks all of them."""
    if state.get('unsafe_writer'):
        raise RuntimeError('unsafe writer requires confirmed termination before resume or publication: '
                           +str(state['unsafe_writer'].get('reason') if isinstance(state['unsafe_writer'],dict)
                                else state['unsafe_writer']))

# Publication bookkeeping (2026-09-23 fix). ``jobs.before.json`` + ``before_sha256`` stay
# the untouched pull of the run's start -- recovery evidence only. ``working_baseline``
# is the frozen artifact the receiver last *accepted* (the direct candidate or the
# rebased merge), and staging is advanced to exactly that artifact. Publishing every
# segment against the original base made a job this run edited A->B (published) ->C
# look like a conflict with its own earlier publication, and "keep online" silently
# dropped C.
def working_baseline(state,run):
    """(path, sha256) of the last accepted artifact, verified; the original pull before any."""
    current=state.get('working_baseline')
    if current:
        path,sha=Path(current['path']),current['sha256']
    else:
        path,sha=Path(run)/'jobs.before.json',state['before_sha256']
    if not path.is_file() or digest(path)!=sha:
        raise ValueError('working baseline missing or its hash changed: '+str(path))
    return path,sha

def unconfirmed_alignment(state):
    """sha256 -> local candidate for every artifact sent without a confirmed receipt.

    Each unconfirmed attempt contributes its frozen candidate (a direct publication
    sends it byte for byte) and every rebased merge found in its work directory whose
    own receipt names that candidate. ``publish_with_rebase`` uses this map only when
    the server is found holding one of those exact hashes.
    """
    aligned={}
    for intent in state.get('unconfirmed_publications') or []:
        candidate=Path(intent['candidate'])
        if not candidate.is_file() or digest(candidate)!=intent['candidate_sha256']:continue
        aligned[intent['candidate_sha256']]=str(candidate)
        for receipt in sorted(Path(intent['workdir']).glob('rebase-*/merged.jobs.receipt.json')):
            try:
                report=json.loads(receipt.read_text(encoding='utf-8'))
            except (OSError,ValueError):
                continue
            merged=receipt.parent/'merged.jobs.json'
            if (report.get('collected_sha256')==intent['candidate_sha256'] and merged.is_file()
                    and digest(merged)==report.get('merged_sha256')):
                aligned[report['merged_sha256']]=str(candidate)
    return aligned

def unconfirmed_parents(state):
    """sha256 -> server sha256 it was sent against, for the unconfirmed artifacts above.

    A direct attempt was sent with ``expected`` = the working baseline of its intent; a
    rebased merge was sent against the ``latest`` its own receipt names. Used only to
    keep the accepted-version lineage unbroken when one of them turns out accepted.
    """
    parents={}
    for intent in state.get('unconfirmed_publications') or []:
        parents.setdefault(intent['candidate_sha256'],intent.get('working_sha256'))
        for receipt in sorted(Path(intent['workdir']).glob('rebase-*/merged.jobs.receipt.json')):
            try:
                report=json.loads(receipt.read_text(encoding='utf-8'))
            except (OSError,ValueError):
                continue
            if report.get('collected_sha256')==intent['candidate_sha256'] and report.get('merged_sha256'):
                parents.setdefault(report['merged_sha256'],report.get('latest_sha256'))
    return parents

def finish_stage_advance(state,statepath,stage):
    """Move staging onto the accepted artifact; safe to re-run after any interruption.

    The expected staging hash is persisted before the atomic replace, so a crash on
    either side of it is recognised on the next call. Staging in any third state
    means something wrote to it between acceptance and here, which is refused.
    """
    advance=state.get('stage_advance')
    if not advance:return
    jobs=Path(stage)/'jobs.json';current=digest(jobs)
    if advance.get('stage_sha256') and current==advance['stage_sha256']:
        pass
    elif current==advance['from_sha256']:
        if advance['from_sha256']==advance['to_sha256']:
            advance['stage_sha256']=current
        else:
            artifact=Path(advance['artifact'])
            if digest(artifact)!=advance['to_sha256']:
                raise ValueError('accepted artifact changed before staging could follow it')
            temporary=jobs.with_name('jobs.accepted.tmp')
            atomic_json(temporary,list(iter_json_file(artifact,strict=True)))
            advance['stage_sha256']=digest(temporary)
            atomic_json(statepath,state)
            os.replace(temporary,jobs)
    else:
        raise ValueError('staging changed between server acceptance and stage advance; cannot align safely')
    # A legacy migration moves staging onto a merge that still holds unpublished local
    # rows; only an advance onto an accepted artifact means "nothing left to publish".
    if advance.get('accepted',True):
        state['publication_source_sha256']=advance['stage_sha256']
    state.pop('stage_advance',None)
    atomic_json(statepath,state)

def accepted_versions_root():
    return ROOT/'data'/'accepted-versions'

ACCEPTED_LINEAGE_LIMIT=2000

def record_accepted_version(state,run,record):
    """Publish-side manifest of one server-accepted version for the Feishu delivery.

    ``data/accepted-versions/<sha>.json`` + ``latest.json`` name the frozen artifact
    (absolute and relative to the collector root) and carry the accumulated
    child->parent lineage of accepted versions, so the delivery side can refuse to
    import something older than what Feishu already shows. Best effort: a failure is
    recorded and never undoes or blocks the publication itself.
    """
    try:
        folder=accepted_versions_root();folder.mkdir(parents=True,exist_ok=True)
        lineage=(json.loads((folder/'lineage.json').read_text(encoding='utf-8'))
                 if (folder/'lineage.json').exists() else {'edges':{}})
        for child,parent in record.get('lineage_edges') or []:
            if child and parent and child!=parent:lineage['edges'][child]=parent
        if len(lineage['edges'])>ACCEPTED_LINEAGE_LIMIT:
            lineage['edges']=dict(list(lineage['edges'].items())[-ACCEPTED_LINEAGE_LIMIT:])
        atomic_json(folder/'lineage.json',lineage)
        artifact=Path(record['artifact'])
        try:
            relative=str(artifact.resolve().relative_to(ROOT.resolve()).as_posix())
        except ValueError:
            relative=None
        manifest={'sha256':record['sha256'],'artifact':str(artifact),'artifact_relpath':relative,
                  'artifact_bytes':artifact.stat().st_size,'run':str(run),'accepted_at':record['accepted_at'],
                  'parent_sha256':dict(record.get('lineage_edges') or []).get(record['sha256']),
                  'lineage':lineage['edges'],'source':record.get('source','collector')}
        atomic_json(folder/(record['sha256']+'.json'),manifest)
        atomic_json(folder/'latest.json',manifest)
        return str(folder/(record['sha256']+'.json'))
    except Exception as failure:
        state.setdefault('accepted_manifest_errors',[]).append(type(failure).__name__+': '+str(failure)[:200])
        return None

def accept_publication(state,statepath,stage,intent,result,*,stage_from=None,source='collector',
                       with_state=None):
    """Record what the receiver took, then advance working baseline and staging to it.

    ``stage_from`` is the staging hash the accepted content was frozen from (defaults to
    the intent's candidate; recovery prepares a copy, so it passes the raw staging hash).
    ``with_state`` holds receipt fields to set only once the artifact has been verified,
    in the same first save that moves the working baseline -- never before, never after.
    """
    published=Path(result['published_path']);publication=result['publication']
    accepted=publication.get('after_sha256')
    if publication.get('published') is not True or not published.is_file() or digest(published)!=accepted:
        raise ValueError('accepted artifact does not match the receiver receipt')
    report=result.get('rebase_report') or {}
    parents=unconfirmed_parents(state)
    edges=[]
    aligned=result.get('aligned_unconfirmed_publication')
    if aligned:
        edges.append([aligned['server_sha256'],parents.get(aligned['server_sha256'])])
    parent=publication.get('before_sha256')
    if not parent and publication.get('already_published'):
        parent=parents.get(accepted)
    edges.append([accepted,parent])
    record={'artifact':str(published),'sha256':accepted,'candidate':intent['candidate'],
            'candidate_sha256':intent['candidate_sha256'],'workdir':intent['workdir'],
            'expected_server_sha256':intent['working_sha256'],'rebased':bool(report),
            'already_published':publication.get('already_published') is True,
            'lineage_edges':edges,'source':source,
            'accepted_at':dt.datetime.now().astimezone().isoformat()}
    if aligned:
        record['aligned_unconfirmed_publication']=aligned
    history=state.setdefault('accepted_publications',[])
    history.append(record)
    state['working_baseline']={'path':str(published),'sha256':accepted,'accepted_index':len(history)}
    state['publication']=publication;state['publication_file']=str(published)
    # The server now provably holds ``accepted``; nothing sent before it can still be pending.
    state['unconfirmed_publications']=[]
    state['stage_advance']={'from_sha256':stage_from or intent['candidate_sha256'],'to_sha256':accepted,
                            'artifact':str(published)}
    state.pop('publication_intent',None)
    state.update(with_state or {})
    atomic_json(statepath,state)
    finish_stage_advance(state,statepath,stage)
    record['manifest']=record_accepted_version(state,Path(stage).parent,record)
    atomic_json(statepath,state)
    return record

# --- receipts written before the working-baseline ledger ---------------------------
PUBLICATION_LEDGER_VERSION=1

def gunzip_verified(source,target,sha):
    """Decompress one old ``jobs.upload.gz`` and prove it is the expected snapshot."""
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_file() and digest(target)==sha:return target
    temporary=target.with_suffix('.tmp')
    with gzip.open(source,'rb') as compressed,temporary.open('wb') as out:shutil.copyfileobj(compressed,out,1048576)
    if digest(temporary)!=sha:
        temporary.unlink(missing_ok=True)
        raise ValueError('legacy upload does not decompress to the recorded hash: '+str(source))
    os.replace(temporary,target)
    return target

def _upload_sha(folder):
    """sha256 of what an old attempt uploaded, from its receiver receipt or by decompressing."""
    receipt=folder/'receiver-receipt.json'
    if receipt.is_file():
        try:
            return json.loads(receipt.read_text(encoding='utf-8')).get('after_sha256')
        except (OSError,ValueError):
            pass
    h=hashlib.sha256()
    with gzip.open(folder/'jobs.upload.gz','rb') as source:
        for chunk in iter(lambda:source.read(1048576),b''):h.update(chunk)
    return h.hexdigest()

def migrate_legacy_publication(state,statepath,run,stage):
    """Carry a receipt from the old runner onto the working-baseline ledger, or refuse.

    The old runner published every segment against the original pull and recorded only
    ``publication`` (the last receiver receipt). Resuming such a run against the
    original base would drop this run's own later edits of already-published IDs. The
    last accepted snapshot is rebuilt from the old run's own frozen evidence -- the
    gzip it uploaded (``direct/jobs.upload.gz``) or the merge it published -- and
    verified against the receiver's ``after_sha256``. When it was a rebased merge,
    staging is three-way merged onto it from the candidate that merge was built from.
    Uploads without a receiver receipt become unconfirmed publications. Anything that
    cannot be proven raises: resuming must not silently fall back to the original.
    """
    if state.get('publication_ledger'):return None
    run=Path(run);work_root=run/'rebase';report={'from':'receipt without publication_ledger'}
    folders=sorted(path for path in work_root.glob('*') if path.is_dir()) if work_root.is_dir() else []
    last=(state.get('publication') or {}).get('after_sha256')
    accepted_folder=None
    if last:
        for folder in reversed(folders):
            result=load_json_file(folder/'receipt.json')
            if (result or {}).get('publication',{}).get('after_sha256')==last:
                accepted_folder=folder;break
        if accepted_folder is None:
            raise ValueError('legacy receipt names accepted publication %s but its frozen artifact cannot '
                             'be found under %s; recover this run manually, the original baseline must '
                             'not be used' % (last,work_root))
        result=load_json_file(accepted_folder/'receipt.json')
        rebase=result.get('rebase_report')
        target=run/'legacy-accepted'
        if not rebase:
            upload=accepted_folder/'direct'/'jobs.upload.gz'
            if not upload.is_file():
                raise ValueError('legacy direct publication has no upload to rebuild it from: '+str(upload))
            artifact=gunzip_verified(upload,target/(last+'.jobs.json'),last)
            if digest(stage/'jobs.json')==last:state['publication_source_sha256']=last
        else:
            merged=Path(result['published_path'])
            if not merged.is_file() or digest(merged)!=last:
                raise ValueError('legacy rebased publication artifact missing or changed: '+str(merged))
            upload=accepted_folder/'direct'/'jobs.upload.gz'
            if not upload.is_file():
                raise ValueError('legacy rebase has no frozen copy of the candidate it merged; '
                                 'cannot replay staging onto it safely')
            origin=gunzip_verified(upload,target/(rebase['collected_sha256']+'.candidate.json'),
                                   rebase['collected_sha256'])
            artifact=target/(last+'.jobs.json')
            if not (artifact.is_file() and digest(artifact)==last):shutil.copyfile(merged,artifact)
            staged=target/'stage-onto-accepted.json'
            merge=rebase_files(origin,stage/'jobs.json',artifact,staged)
            report['stage_merge']={'conflicts':len(merge['conflicts']),'receipt':str(staged.with_suffix('.receipt.json'))}
            state['stage_advance']={'from_sha256':digest(stage/'jobs.json'),'to_sha256':merge['merged_sha256'],
                                    'artifact':str(staged),'accepted':False}
        state['working_baseline']={'path':str(artifact),'sha256':last,'accepted_index':0,'legacy':True}
        report['accepted_sha256']=last;report['rebuilt_from']=str(accepted_folder)
    # Later attempts whose outcome the old runner never learnt: treat as unconfirmed.
    unconfirmed=[]
    for folder in folders:
        if accepted_folder is not None and folder.name<=accepted_folder.name:continue
        upload=folder/'direct'/'jobs.upload.gz'
        if not upload.is_file():continue
        sha=_upload_sha(folder/'direct')
        candidate=gunzip_verified(upload,run/'legacy-accepted'/(sha+'.unconfirmed.json'),sha)
        unconfirmed.append({'workdir':str(folder),'candidate':str(candidate),'candidate_sha256':sha,
                            'working_sha256':None,'legacy':True})
    if unconfirmed:
        state.setdefault('unconfirmed_publications',[]).extend(unconfirmed)
        report['unconfirmed']=len(unconfirmed)
    state['publication_ledger']=PUBLICATION_LEDGER_VERSION
    state['legacy_migration']=report
    atomic_json(statepath,state)
    finish_stage_advance(state,statepath,stage)
    return report

def load_json_file(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):
        return None

# --- publications made by windows_recover_run -------------------------------------
def recovery_bindings(run):
    """Every recovery attempt made for this run: (attempt dir, binding) newest first."""
    found=[]
    for binding_path in (ROOT/'recovery').glob('*/attempts/*/source-binding.json'):
        binding=load_json_file(binding_path)
        if isinstance(binding,dict) and binding.get('source_run')==str(Path(run).resolve()):
            found.append((binding_path.parent,binding))
    return sorted(found,key=lambda item:item[0].stat().st_mtime_ns,reverse=True)

def consume_recovery_publications(state,statepath,run,stage):
    """Adopt a verified recovery publication of this run before collecting again.

    ``windows_recover_run`` never writes the source run. Its accepted publication is
    adopted here like any other acceptance: working baseline and staging move to the
    artifact the receiver took. Remaining p1 checkpoints stay untouched. A recovery
    attempt without a receipt is filed as unconfirmed; one that no longer matches this
    run's working baseline and staging refuses the resume.
    """
    done=set(state.get('consumed_recoveries') or [])
    # A receipt written by a runner that adopted before this marker became transactional:
    # the acceptance record itself names the recovery attempt, which is proof enough.
    done|={str(Path(record['workdir']).parent) for record in state.get('accepted_publications') or []
           if record.get('source')=='recovery' and record.get('workdir')}
    fresh=[(attempt,binding) for attempt,binding in recovery_bindings(run) if str(attempt) not in done]
    if not fresh:return None
    adopted=None;report=[];unconfirmed=[]
    for attempt,binding in fresh:
        receipt=load_json_file(attempt/'publication'/'receipt.json')
        if not (receipt or {}).get('publication',{}).get('published'):
            unconfirmed.append(
                {'workdir':str(attempt/'publication'),'candidate':str(attempt/'collected.jobs.json'),
                 'candidate_sha256':binding.get('prepared_candidate_sha256'),
                 'working_sha256':binding.get('working_sha256'),'recovery':True})
            report.append({'attempt':str(attempt),'result':'unconfirmed'})
        elif adopted is None:
            adopted=(attempt,binding,receipt)
        else:
            report.append({'attempt':str(attempt),'result':'superseded by a newer recovery publication'})
        done.add(str(attempt))
    # Nothing above touched ``state``: a refusal below must leave every attempt fresh.
    marker={'consumed_recoveries':sorted(done),
            'recovery_adoptions':list(state.get('recovery_adoptions') or [])+report}
    if adopted is not None:
        attempt,binding,receipt=adopted
        current=working_baseline(state,run)[1]
        staged=digest(stage/'jobs.json')
        if binding.get('working_sha256')!=current or binding.get('source_candidate_sha256')!=staged:
            raise ValueError('recovery publication %s was made from another state of this run; '
                             'align it manually before resuming' % attempt)
        if p1_status(stage).get('active_batch'):
            raise ValueError('p1 batch unresolved; cannot move staging onto the recovery publication')
        intent={'workdir':str(attempt/'publication'),'candidate':str(attempt/'collected.jobs.json'),
                'candidate_sha256':binding.get('prepared_candidate_sha256'),'working_sha256':current}
        marker['recovery_adoptions'].append({'attempt':str(attempt),'result':'adopted',
                                             'sha256':receipt['publication']['after_sha256']})
        # The server provably holds the adopted artifact, so older unconfirmed attempts are
        # moot (accept clears them); the consumed marker lands in accept's first save, after
        # the artifact and receipt checks, so a refusal there leaves the attempt fresh.
        accept_publication(state,statepath,stage,intent,receipt,stage_from=staged,source='recovery',
                           with_state=marker)
        return report+marker['recovery_adoptions'][-1:]
    state.setdefault('unconfirmed_publications',[]).extend(unconfirmed)
    state.update(marker)
    atomic_json(statepath,state)
    return report

def publication_pending(state,stage):
    """True while staging holds anything the server has not accepted."""
    if state.get('stage_advance') or state.get('publication_intent'):return True
    jobs=Path(stage)/'jobs.json'
    if not jobs.is_file():return False
    return digest(jobs)!=state.get('publication_source_sha256')

def publish_stage(state,statepath,run,stage,baseline,*,smoke):
    """Freeze staging, publish it against the working baseline, then advance to what was accepted.

    Returns a receipt fragment with ``action`` ``published``, ``unchanged`` or
    ``deferred``. ``baseline`` (the original pull) is only evidence here; the reference
    is ``working_baseline``. Transport exhaustion raises ``PublishUnavailable`` after the
    attempt has been filed as unconfirmed.
    """
    state['stage']='validate-and-publish';atomic_json(statepath,state)
    refuse_unsafe_writer(state)
    finish_stage_advance(state,statepath,stage)
    if state.get('publication_intent'):
        # Interrupted between upload and receipt: never assume either outcome.
        state.setdefault('unconfirmed_publications',[]).append(state.pop('publication_intent'))
        atomic_json(statepath,state)
    before_rows=state.get('server_rows')
    active=p1_status(stage).get('active_batch')
    if active:
        # p1 binds its unfinished batch to the current staging hash; advancing staging to
        # a rebased artifact now would make that batch unrecoverable. Publish after p1
        # has resolved it.
        return {'action':'deferred','server_rows_before':before_rows,'server_rows_after':before_rows,
                'reason':'p1 batch publication unresolved (active_batch); staging not frozen'}
    reference,reference_sha=working_baseline(state,run)
    frozen,preserved,total=prepare_candidate(reference,stage/'jobs.json')
    state['removed_frozen']=frozen;state['preserved_missing'],state['total_jobs']=preserved,total
    after=digest(stage/'jobs.json')
    if after==state.get('publication_source_sha256') or after==reference_sha:
        state['publication_source_sha256']=after
        shutil.copyfile(reference,ROOT/'data/jobs.json')
        atomic_json(statepath,state)
        return {'action':'unchanged','source_sha256':after,'server_rows_before':before_rows,
                'server_rows_after':before_rows,'server_sha256':reference_sha,
                'reason':'staging equals the last accepted publication'}
    work=run/'rebase'/dt.datetime.now().strftime('%Y%m%dT%H%M%S%f');work.mkdir(parents=True)
    candidate=work/'candidate.jobs.json'
    shutil.copyfile(stage/'jobs.json',candidate)
    if digest(candidate)!=after or digest(stage/'jobs.json')!=after:
        raise ValueError('staging changed while freezing the publication candidate')
    intent={'workdir':str(work),'candidate':str(candidate),'candidate_sha256':after,
            'working_sha256':reference_sha,'started_at':dt.datetime.now().astimezone().isoformat()}
    aligned=unconfirmed_alignment(state)
    state['publication_intent']=intent;atomic_json(statepath,state)
    try:
        result=publish_with_rebase(reference,candidate,reference_sha,work,
                                   lambda path:pull(path,receipt=state),
                                   guarded_publish_snapshot(reference,receipt=state),aligned=aligned)
    except Exception:
        # Whatever happened, the receiver may or may not hold this candidate.
        state.setdefault('unconfirmed_publications',[]).append(state.pop('publication_intent'))
        atomic_json(statepath,state)
        raise
    record=accept_publication(state,statepath,stage,intent,result)
    state['rebase_receipt']=str(work/'receipt.json')
    state['collection_scope']='single-source-boc-smoke' if smoke else 'daily-pipeline'
    report=result.get('rebase_report') or {}
    after_rows=report.get('merged_rows') if report else state.get('total_jobs')
    state['server_rows']=after_rows
    shutil.copyfile(record['artifact'],ROOT/'data/jobs.json')
    atomic_json(statepath,state)
    return {'action':'published','direct':not report,'source_sha256':after,
            'server_sha256':record['sha256'],'server_rows_before':before_rows,
            'server_rows_after':after_rows,'added_rows':report.get('added_rows'),
            'conflicts':len(report.get('conflicts') or []),
            'rebase_attempts':len(result.get('attempts') or []),
            'aligned_unconfirmed_publication':result.get('aligned_unconfirmed_publication'),
            'publication':result['publication']}

# Cross-day p1 state (2026-09-23). p1_pipeline keeps its retry queue and last-attempt
# times in ``--data-dir``, which for this runner is the per-day stage directory: every
# new day started from an empty queue and yesterday's failures were invisible. p1's own
# layout is left alone; the runner seeds the stage copy from one persistent root before
# each segment and writes it back after, so the state belongs to no single run.
# The Moka detail cache is pointed at a stable root through p1's own
# ``QIUZHAO_P1_DETAIL_CACHE_ROOT`` for the same reason.
P1_STATE_FILES=('p1-retry-queue.json','p1-last-attempt.json')

def p1_state_root():
    return ROOT/'data'/'p1-state'

def p1_detail_cache_root():
    return ROOT/'data'/'p1-detail-cache'

def _state_payload(path):
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):
        return None
    return value if isinstance(value,dict) and isinstance(value.get('entries'),dict) else None

def import_p1_state(stage):
    """Seed staging from the persistent root: newer retry queue wins, attempt times merge by max."""
    report={}
    for name in P1_STATE_FILES:
        persistent=_state_payload(p1_state_root()/name);local=_state_payload(Path(stage)/name)
        if persistent is None:
            report[name]='no persistent state';continue
        if name=='p1-last-attempt.json' and local is not None:
            merged=dict(local['entries'])
            for key,value in persistent['entries'].items():
                try:
                    if key not in merged or float(value)>float(merged[key]):merged[key]=value
                except (TypeError,ValueError):
                    continue
            atomic_json(Path(stage)/name,{'updated_at':max(str(local.get('updated_at') or ''),
                                                            str(persistent.get('updated_at') or '')),
                                           'entries':merged})
            report[name]='merged'
        elif local is None or str(persistent.get('updated_at') or '')>str(local.get('updated_at') or ''):
            atomic_json(Path(stage)/name,persistent);report[name]='seeded'
        else:
            report[name]='kept run copy'
    return report

def export_p1_state(stage):
    """Write the stage copy back to the persistent root; a failure is reported, never raised."""
    report={}
    for name in P1_STATE_FILES:
        local=_state_payload(Path(stage)/name)
        if local is None:
            report[name]='no run state';continue
        try:
            atomic_json(p1_state_root()/name,local);report[name]='exported'
        except OSError as error:
            report[name]='export failed: '+type(error).__name__+': '+str(error)[:200]
    return report

def p1_budget(state):
    """The logical run's p1 budget, created once and persisted in receipt.json.

    ``used_seconds`` accumulates across processes and ``deadline_epoch`` is wall-clock,
    so ``--resume-run`` continues the same 20h budget instead of receiving a new one.
    """
    ledger=state.get('p1_budget_ledger')
    if not ledger:
        ledger=state['p1_budget_ledger']=legacy_budget(state) or new_budget()
    return ledger

def new_budget():
    now=time.time()
    return {'budget_seconds':P1_TOTAL_BUDGET_SECONDS,'used_seconds':0.0,
            'started_epoch':now,'deadline_epoch':now+P1_TOTAL_BUDGET_SECONDS}

def _epoch(value):
    try:
        return dt.datetime.fromisoformat(value).timestamp()
    except (TypeError,ValueError):
        return None

def legacy_budget(state):
    """The budget an older receipt already spent; None when p1 never ran in this run.

    An old ``p1_budget.exhausted`` stays exhausted (publication only). Otherwise the
    spend is rebuilt from the segment records (loop-relative ``budget_elapsed_seconds``
    plus the last segment's duration, or the sum of durations) and the deadline from the
    earliest segment start. Records too incomplete to prove anything are treated as
    exhausted rather than as a fresh 20h.
    """
    budget=P1_TOTAL_BUDGET_SECONDS
    segments=[s for s in state.get('p1_segments') or [] if isinstance(s,dict)]
    old=state.get('p1_budget') or {}
    if not segments and not old and 'p1' not in (state.get('steps') or {}):return None
    if old.get('exhausted'):
        start=_epoch(state.get('started_at')) or time.time()
        return {'budget_seconds':budget,'used_seconds':float(budget),'started_epoch':start,
                'deadline_epoch':start+budget,'migrated_from':'legacy p1_budget.exhausted'}
    durations=[float(s.get('elapsed_seconds') or s.get('p1_seconds') or 0) for s in segments]
    loop=0.0
    for s in segments:
        if s.get('budget_elapsed_seconds') is not None:
            loop=max(loop,float(s['budget_elapsed_seconds'])+float(s.get('elapsed_seconds') or 0))
    used=max(sum(durations),loop)
    starts=[value for value in (_epoch(s.get('started_at')) for s in segments) if value]
    start=min(starts) if starts else _epoch(state.get('started_at'))
    if start is None or (segments and not any(durations) and not starts):
        start=start or time.time()
        return {'budget_seconds':budget,'used_seconds':float(budget),'started_epoch':start,
                'deadline_epoch':start,'migrated_from':'legacy receipt without provable p1 spend; treated as exhausted'}
    return {'budget_seconds':budget,'used_seconds':round(used,1),'started_epoch':start,
            'deadline_epoch':start+budget,'migrated_from':'legacy p1 segment records'}

def run_p1_segments(state,statepath,run,stage,baseline,env,steps,*,smoke):
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
                             'company_budget':P1_COMPANY_BUDGET,'batch_publish':True,
                             'segment_seconds':P1_SEGMENT_SECONDS,'segment_step_limit':limit,
                             'total_budget_seconds':P1_TOTAL_BUDGET_SECONDS,
                             'detail_cache_root':env.get('QIUZHAO_P1_DETAIL_CACHE_ROOT'),
                             'persistent_state_root':str(p1_state_root())}
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
                                                        smoke=smoke)
                except PublishUnavailable as error:
                    record['publication']={'action':'deferred','reason':str(error)[:800]}
                if record['publication'].get('action')=='deferred':
                    state.setdefault('publish_deferrals',[]).append(
                        {'segment':record['segment'],'reason':record['publication']['reason'],
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
        state['collection']={'state':'complete','reason':'p1 finished'}
        atomic_json(statepath,state)
        return
    ledger=p1_budget(state);atomic_json(statepath,state)
    mark=time.monotonic();stalled=0;previous_pending=None;stop=None
    def charge():
        nonlocal mark
        current=time.monotonic();ledger['used_seconds']=round(ledger['used_seconds']+current-mark,1);mark=current
    while stop is None:
        charge()
        elapsed=ledger['used_seconds']
        if elapsed>=ledger['budget_seconds'] or time.time()>=ledger['deadline_epoch']:
            state['p1_budget']={'exhausted':True,'budget_seconds':ledger['budget_seconds'],
                                'elapsed_seconds':round(elapsed,1),'stopped_at':'segment-boundary',
                                'deadline_epoch':ledger['deadline_epoch'],
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
            record['p1_state_import']=import_p1_state(stage)
            try:
                code=run_stage_step(state,statepath,run,stage,'p1',args,limit,env,force=True,
                                    keep_exit_codes=(124,))
            finally:
                record['p1_state_export']=export_p1_state(stage)
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
        charge();atomic_json(statepath,state)
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
    # Collection is over for this logical run once p1 finished or its budget is spent;
    # a resume then only publishes. Any other stop leaves collection resumable within
    # the remaining persisted budget.
    if state['p1_finished'] or state.get('p1_budget',{}).get('exhausted'):
        state['collection']={'state':'complete','reason':'p1 finished' if state['p1_finished'] else 'p1 budget exhausted'}
    else:
        state['collection']={'state':'stopped','reason':stop or 'p1 loop ended'}
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

def delivery_summary(state,stage,*,requested_feishu=False):
    """Four separate states; none of them is inferred from another.

    collection: complete / stopped / failed / unknown. publication: accepted (server
    holds exactly the current staging) / pending (collected rows not yet accepted,
    including unconfirmed attempts) / not_applicable (nothing to publish).
    feishu: this runner never writes Feishu; delivery is the Excel import route run
    separately from a server-accepted version (deploy/windows_excel_delivery.py).
    """
    collection=(state.get('collection') or {}).get('state') or 'unknown'
    if not Path(stage,'jobs.json').is_file() or 'before_sha256' not in state:
        publication='not_applicable'
    else:
        publication='pending' if publication_pending(state,stage) else 'accepted'
    accepted=(state.get('working_baseline') or {}).get('sha256')
    return {'collection':collection,'publication':publication,
            'server_accepted_sha256':accepted,
            'unconfirmed_publications':len(state.get('unconfirmed_publications') or []),
            'feishu':'requested_separately' if requested_feishu else 'not_requested',
            'feishu_route':'excel-import (deploy/windows_excel_delivery.py); the old row-level '
                           'lark_sync_daemon is retired from this runner'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke',action='store_true')
    # --no-sync is accepted for the existing scheduled-task command line only. The old
    # --no-sync default=True made the Base-sync branch unreachable, and that branch drove
    # the retired row-level lark_sync_daemon; Feishu delivery is a separate Excel import.
    parser.add_argument('--no-sync',action='store_true');parser.add_argument('--preflight',action='store_true');parser.add_argument('--resume-run',type=Path);a=parser.parse_args()
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
        statepath=run/'receipt.json';state=json.loads(statepath.read_text(encoding='utf-8')) if statepath.exists() else {'started_at':dt.datetime.now().astimezone().isoformat(),'steps':{},'publication_ledger':PUBLICATION_LEDGER_VERSION}
        if state.get('mode', 'smoke' if run.name.endswith('-smoke') else 'daily')!=('smoke' if a.smoke else 'daily'):raise ValueError('persisted collection scope mismatch')
        state['mode']='smoke' if a.smoke else 'daily'
        refuse_unsafe_writer(state)
        if state.get('error'):
            state.setdefault('previous_errors',[]).append(state.pop('error'))
            atomic_json(statepath,state)
        # ``finished`` is only ever written together with an accepted publication (see
        # below). A receipt from the older runner could say finished while its last
        # publication was deferred; that one falls through and publishes.
        if state.get('finished') and not (state.get('publish_deferrals') and 'delivery' not in state):
            return 0 if state.get('success') else 1
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
            # Older receipts are moved onto the ledger (or refused), an acceptance recorded
            # just before an interruption is finished, and a recovery publication of this
            # run is adopted -- all before anything (p1 included) writes to staging again.
            migrate_legacy_publication(state,statepath,run,stage)
            finish_stage_advance(state,statepath,stage)
            consume_recovery_publications(state,statepath,run,stage)
            env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8',QIUZHAO_DATA_DIR=str(stage),QIUZHAO_SKIP_SERVICE_RESTART='1',QIUZHAO_P1_COMPANY_BUDGET=str(P1_COMPANY_BUDGET),
                     QIUZHAO_P1_DETAIL_CACHE_ROOT=str(p1_detail_cache_root()))
            steps=steps_for(stage,a.smoke);by_name={name:(args,limit) for name,args,limit in steps}
            for stale in run.glob('*.before.json'):
                if stale.name=='jobs.before.json':continue
                shutil.copyfile(stale,stage/'jobs.json');stale.unlink()
                if stale.name=='p1.before.json':reset_p1(stage)
                state['steps'].pop(stale.name.removesuffix('.before.json'),None)
                state['steps'].pop('normalize',None)
            if (state.get('collection') or {}).get('state')=='complete':
                # Collection for this logical run is over; only its publication is owed.
                state['resume_mode']='publication-only'
                if state['steps'].get('normalize')!=0:raise ValueError('normalization failed; production retained')
                try:
                    state['publication_retry']=publish_stage(state,statepath,run,stage,baseline,smoke=a.smoke)
                except PublishUnavailable as error:
                    state['publication_retry']={'action':'deferred','reason':str(error)[:800]}
            else:
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
                    run_p1_segments(state,statepath,run,stage,baseline,env,by_name,smoke=False)
                    # Rows that are still not on the server when collection stops (a
                    # deferred last segment, or a budget already spent on entry) get one
                    # more bounded publication attempt now instead of waiting for a resume.
                    if publication_pending(state,stage) and state['steps'].get('normalize')==0:
                        try:
                            state['final_publication']=publish_stage(state,statepath,run,stage,baseline,smoke=False)
                        except PublishUnavailable as error:
                            state['final_publication']={'action':'deferred','reason':str(error)[:800]}
                # Daily collection-gap report: the p1 stage writes runs/<date>/collection-gap.json
                # (expected_total vs collected_jobs for every unit). Surface its key numbers in
                # the receipt; a missing/broken report must never fail the run.
                state['collection_gap']=collection_gap_summary(run,stage)
                if state['steps']['normalize']!=0:raise ValueError('normalization failed; production retained')
                if all(state['steps'][name] not in (0,2) for name in state['steps'] if name!='normalize'):raise ValueError('all collection stages failed; production retained')
                if a.smoke:
                    state['collection']={'state':'complete','reason':'smoke collection finished'}
                    atomic_json(statepath,state)
                    publish_stage(state,statepath,run,stage,baseline,smoke=True)
            state['delivery']=delivery_summary(state,stage)
            clean=all(v==0 for v in state['steps'].values())
            accepted=state['delivery']['publication']=='accepted'
            # A run whose rows are still waiting for the server is neither finished nor a
            # success, whatever its steps returned, so --resume-run comes back to publish.
            state['finished']=state['success']=clean and accepted
        except Exception as e:
            # Keep the full traceback, not just the message: on 2026-09-20 the receipt
            # stored only "TypeError: 'NoneType' object is not subscriptable", so the
            # raising line had to be reconstructed from logs a second time.
            state['error']=type(e).__name__+': '+str(e)[:500]
            state['error_step']=state.get('stage')
            state['error_traceback']=traceback.format_exc()
            state['success']=False;state['finished']=False
            try:
                state['delivery']=delivery_summary(state,stage)
            except Exception as summary_failure:
                state['delivery']={'error':type(summary_failure).__name__+': '+str(summary_failure)[:200]}
        state['stage']='completed' if state.get('success') else 'partial-or-failed'
        state['completed_at']=dt.datetime.now().astimezone().isoformat();atomic_json(statepath,state);atomic_json(ROOT/'data/windows-status.json',state)
        print(json.dumps(state,ensure_ascii=False));return 0 if state.get('success') else 1
if __name__=='__main__':raise SystemExit(main())
