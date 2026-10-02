"""Orchestration tests with real files/locks; runner step and Scheduler are stubs.

This suite does NOT claim a Windows scheduler, SSH or production integration test.
The target runbook separately invokes the existing runner regression suites.
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from deploy import windows_normalize_retry as retry
from qiuzhao.normalization_io import normalize_path

try:
    import fcntl
except ImportError:
    from qiuzhao.collector.portable_runtime import fcntl


def save(path, value):
    path = Path(path)
    temp = path.with_suffix('.test.tmp')
    temp.write_text(json.dumps(value), encoding='utf-8')
    temp.replace(path)


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / 'collector'; (root/'data').mkdir(parents=True)
    run = root/'runs/20261002'; (run/'data').mkdir(parents=True)
    for rel in retry.CORE_FILES:
        p = root/rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('# synthetic reviewed fixture\n')
    # Assets are intentionally missing; no old production data is copied here.
    state = {'stage':'partial-or-failed', 'completed_at':'2026-10-02T05:42:11+08:00',
             'steps':{'basic':0,'tencent':0,'p1':2,'normalize':1},
             'collection':{'state':'stopped','reason':'normalize failed; later segments would repeat it'},
             'p1_segments':[{'segment':1,'exit':2,'normalize_exit':1}],
             'p1_budget_ledger':{'used_seconds':901.5,'deadline_epoch':1790938800,'budget_seconds':72000},
             'p1_budget':{'exhausted':False}, 'success':False, 'finished':False,
             'delivery':{'publication':'pending'}, 'unconfirmed_publications':[]}
    save(run/'receipt.json',state)
    save(run/'data/jobs.json',[{'id':'kept','detail_fetch_errors':['timeout']}])
    save(run/'data/p1-status.json',{'run_finished':False,'pending':['plan-key']})
    calls = []
    def refuse(s):
        if s.get('unsafe_writer'): raise RuntimeError('unsafe writer')
    def capacity(paths): calls.append('capacity')
    def stage_step(s, sp, r, st, name, args, limit, env, **kwargs):
        calls.append(name)
        assert name == 'normalize' and kwargs['force'] is True
        assert limit == 1800 and env['PYTHONUTF8'] == '1'
        def fill(row, counts): row['normalized']=True; counts['normalized']+=1
        normalize_path(st/'jobs.json',check=False,normalize_one=fill,fields=['normalized'],
                       is_empty=lambda x:x is None,metadata={})
        s['steps'][name]=0; save(sp,s); return 0
    runner=SimpleNamespace(ROOT=root,fcntl=fcntl,refuse_unsafe_writer=refuse,capacity_check=capacity,
        steps_for=lambda stage,smoke:[('normalize',['-m','qiuzhao.normalize','--path',str(stage/'jobs.json')],1800)],
        run_stage_step=stage_step,atomic_json=save)
    manifest=tmp_path/'review.json'
    save(manifest,{'decision':'PASS','reviewer':'SYNTHETIC TEST ONLY','files':retry.identities(root)})
    return SimpleNamespace(root=root,run=run,state=state,runner=runner,calls=calls,manifest=manifest)


def invoke(s, **kwargs):
    args=dict(expected_source=retry.digest(s.run/'data/jobs.json'),
              expected_receipt=retry.digest(s.run/'receipt.json'), task_is_running=lambda:False)
    args.update(kwargs)
    return retry.retry_normalization(s.runner,s.run,**args)


def test_inspection_changes_no_jobs_receipt_or_budget(setup):
    s=setup; jobs=(s.run/'data/jobs.json').read_bytes(); receipt=(s.run/'receipt.json').read_bytes()
    out=invoke(s)
    assert out['action']=='inspect-only' and out['dependencies']['qiuzhao/normalize_tables.json'] is None
    assert (s.run/'data/jobs.json').read_bytes()==jobs and (s.run/'receipt.json').read_bytes()==receipt
    assert s.calls==[]


def test_success_only_normalizes_and_keeps_plan_deadline_history(setup):
    s=setup; pending=(s.run/'data/p1-status.json').read_bytes()
    out=invoke(s,apply=True,review_manifest=s.manifest)
    current=json.loads((s.run/'receipt.json').read_text())
    assert out['action']=='normalized-not-published'
    assert s.calls==['capacity','normalize']
    for key in ['p1_budget','p1_budget_ledger','collection','p1_segments','completed_at','delivery','success','finished']:
        assert current[key]==s.state[key]
    assert current['steps']==dict(s.state['steps'],normalize=0)
    assert (s.run/'data/p1-status.json').read_bytes()==pending
    assert json.loads((s.run/'data/jobs.json').read_text())[0]['detail_fetch_errors']==['timeout']
    assert not out['publication_attempted'] and not out['collection_attempted']
    with pytest.raises(ValueError,match='failed normalize'):
        invoke(s,apply=True,review_manifest=s.manifest)
    assert s.calls==['capacity','normalize']


@pytest.mark.parametrize('field,value', [
    ('unsafe_writer',{'reason':'alive'}), ('publication_intent',{'candidate':'unknown'}),
    ('stage_advance',{'artifact':'unsettled'}), ('unconfirmed_publications',[{'sha':'unknown'}]),
    ('p1_segments',[]), ('collection',{'state':'complete'}), ('stage','running'), ('completed_at',None),
    ('steps',{'normalize':0}), ('steps',{'normalize':True}), ('steps',{}),
])
def test_unsafe_or_ineligible_receipts_refused_before_actions(setup,field,value):
    s=setup; current=copy.deepcopy(s.state); current[field]=value; save(s.run/'receipt.json',current)
    old=(s.run/'data/jobs.json').read_bytes(); before=(s.run/'receipt.json').read_bytes()
    with pytest.raises((ValueError,RuntimeError)):
        invoke(s,apply=True,review_manifest=s.manifest)
    assert s.calls==[] and (s.run/'data/jobs.json').read_bytes()==old
    assert (s.run/'receipt.json').read_bytes()==before


@pytest.mark.parametrize('kind',['source','receipt','review','scheduler','batch','snapshot'])
def test_boundaries(setup,kind):
    s=setup; args={'apply':True,'review_manifest':s.manifest}
    if kind=='source':args['expected_source']='0'*64
    if kind=='receipt':args['expected_receipt']='0'*64
    if kind=='review': (s.root/retry.CORE_FILES[0]).write_text('# drift')
    if kind=='scheduler':args['task_is_running']=lambda:True
    if kind=='batch':save(s.run/'data/p1-status.json',{'active_batch':{'id':'pending'}})
    if kind=='snapshot':(s.run/'normalize.before.json').write_text('[]')
    with pytest.raises(ValueError):invoke(s,**args)
    assert s.calls==[]


def test_runner_lock_blocks_second_invocation(setup):
    s=setup
    with (s.root/'data/windows-runner.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            with pytest.raises(OSError):invoke(s,apply=True,review_manifest=s.manifest)
        finally:fcntl.flock(lock,fcntl.LOCK_UN)
    assert s.calls==[]


def test_no_review_no_apply(setup):
    with pytest.raises(ValueError,match='review-manifest'):invoke(setup,apply=True)
    assert setup.calls==[]


def test_zero_segment_special_case_is_not_extended(setup):
    s=setup; state=copy.deepcopy(s.state); state['p1_segments']=[]
    save(s.run/'receipt.json',state)
    with pytest.raises(ValueError,match='zero-segment'):invoke(s,apply=True,review_manifest=s.manifest)
    assert s.calls==[]


def test_capacity_failure_does_not_reset_or_normalize(setup):
    s=setup
    def fail(paths):raise RuntimeError('capacity gate')
    s.runner.capacity_check=fail
    original=(s.run/'receipt.json').read_bytes()
    with pytest.raises(RuntimeError,match='capacity'):invoke(s,apply=True,review_manifest=s.manifest)
    assert s.calls==[] and (s.run/'receipt.json').read_bytes()==original


def test_step_failure_stays_failed_not_delivered(setup):
    s=setup; source=(s.run/'data/jobs.json').read_bytes()
    def failure(state,*a,**kw):state['steps']['normalize']=124;return 124
    s.runner.run_stage_step=failure
    out=invoke(s,apply=True,review_manifest=s.manifest)
    state=json.loads((s.run/'receipt.json').read_text())
    assert out['action']=='normalize-failed-not-published'
    assert state['steps']['normalize']==124 and state['collection']==s.state['collection']
    assert state['delivery']==s.state['delivery'] and (s.run/'data/jobs.json').read_bytes()==source


def test_unknown_child_termination_preserves_unsafe_writer(setup):
    s=setup
    def failure(state,*a,**kw):
        state['unsafe_writer']={'reason':'termination unconfirmed'}
        state['steps']['normalize']=125
        raise RuntimeError('unsafe')
    s.runner.run_stage_step=failure
    with pytest.raises(RuntimeError,match='unsafe'):invoke(s,apply=True,review_manifest=s.manifest)
    state=json.loads((s.run/'receipt.json').read_text())
    assert state['unsafe_writer'] and state['steps']['normalize']==125
    assert state['normalization_retries'][-1]['action']=='retry-failed-preserve-evidence'


def test_code_drift_after_success_blocks_publication(setup):
    s=setup; real=s.runner.run_stage_step
    def drift(*a,**kw):
        result=real(*a,**kw); (s.root/retry.CORE_FILES[0]).write_text('# changed during run');return result
    s.runner.run_stage_step=drift
    with pytest.raises(ValueError,match='changed during'):invoke(s,apply=True,review_manifest=s.manifest)
    state=json.loads((s.run/'receipt.json').read_text())
    assert state['steps']['normalize']==1 and state['stage']=='partial-or-failed'


def test_crash_after_step_success_leaves_publisher_gate_closed(setup):
    s=setup; real=s.runner.run_stage_step
    def interrupt(*a,**kw):
        real(*a,**kw)
        raise KeyboardInterrupt('synthetic crash after persisted exit 0')
    s.runner.run_stage_step=interrupt
    with pytest.raises(KeyboardInterrupt):invoke(s,apply=True,review_manifest=s.manifest)
    state=json.loads((s.run/'receipt.json').read_text())
    assert state['steps']['normalize']==0
    assert state['unsafe_writer']['normalization_retry_validation'] is True
    with pytest.raises(RuntimeError,match='unsafe'):s.runner.refuse_unsafe_writer(state)
    assert state['normalization_retries'][-1]['action']=='retry-interrupted-validation-pending'


def test_partial_normalize_exit_does_not_become_publishable(setup):
    s=setup
    def partial(state,*a,**kw):state['steps']['normalize']=2;return 2
    s.runner.run_stage_step=partial
    with pytest.raises(ValueError,match='partial normalize'):invoke(s,apply=True,review_manifest=s.manifest)
    state=json.loads((s.run/'receipt.json').read_text())
    assert state['steps']['normalize']==1 and state['unsafe_writer']


def test_success_commits_without_validation_barrier(setup):
    s=setup
    invoke(s,apply=True,review_manifest=s.manifest)
    assert 'unsafe_writer' not in json.loads((s.run/'receipt.json').read_text())
