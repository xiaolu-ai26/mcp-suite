import pytest

@pytest.fixture(autouse=True)
def isolate_daemon_lock(tmp_path, monkeypatch):
    monkeypatch.setenv('QIUZHAO_LARK_SYNC_LOCK_PATH', str(tmp_path/'isolated-sync.lock'))
    monkeypatch.delenv('QIUZHAO_LARK_SYNC_LOCK_FD', raising=False)

from pathlib import Path
from qiuzhao.collector import lark_sync_daemon as D


def local_run(path,monkeypatch):
    monkeypatch.setattr(D,'external_runs_ready',lambda state,runs:state/'runs')
    return D.run(path)


def test_unchanged_source_does_not_read_or_write_base(tmp_path,monkeypatch):
    D.S.save(tmp_path/'status.json',{'status':'success','last_source_sha256':'a'*64,'last_success_at':'before','sync_rule_version':D.SYNC_RULE_VERSION})
    monkeypatch.setattr(D,'source_hash',lambda:'a'*64)
    monkeypatch.setattr(D,'capture_source',lambda out: (_ for _ in ()).throw(AssertionError('unexpected snapshot')))
    result=local_run(tmp_path,monkeypatch)
    assert result['status']=='unchanged' and result['last_success_at']=='before'


def test_auth_or_network_failure_is_recorded_without_losing_last_success(tmp_path,monkeypatch):
    D.S.save(tmp_path/'status.json',{'status':'success','last_source_sha256':'a'*64,'last_success_at':'before'})
    def fail():raise RuntimeError('SSH unavailable')
    monkeypatch.setattr(D,'source_hash',fail)
    try:local_run(tmp_path,monkeypatch)
    except RuntimeError:pass
    result=__import__('json').loads((tmp_path/'status.json').read_text())
    assert result['status']=='failed' and result['last_success_at']=='before'
    assert result['error']=='SSH unavailable'


def test_manual_sync_reuses_runner_lock_without_unlocking_parent(tmp_path,monkeypatch):
    import fcntl,os,subprocess,sys
    from qiuzhao.collector import sync_lark_multivalue as S
    path=tmp_path/'sync.lock'
    with path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        env=dict(os.environ,QIUZHAO_LARK_SYNC_LOCK_PATH=str(path),QIUZHAO_LARK_SYNC_LOCK_FD=str(lock.fileno()))
        child=subprocess.run([sys.executable,'-c','from qiuzhao.collector.sync_lark_multivalue import sync_lock;\nwith sync_lock(): print("inherited")'],env=env,pass_fds=(lock.fileno(),),capture_output=True,text=True)
        assert child.returncode==0 and 'inherited' in child.stdout
        other=path.open('a')
        try:
            try:fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:pass
            else:raise AssertionError('child released parent lock')
        finally:other.close()


def test_capacity_pending_runs_conditions_but_never_commits_source_hash(tmp_path,monkeypatch):
    import json
    phases=[]
    monkeypatch.setattr(D,'source_hash',lambda:'new')
    def capture(out):
        path=out/'source.jobs.json';path.write_text('[]')
        return path,'new'
    monkeypatch.setattr(D,'capture_source',capture)
    class Child:
        def __init__(self,args,**kwargs):
            phase=args[-1];phases.append(phase)
            out=Path(args[args.index('--output-dir')+1])
            if phase=='--append-p1':
                D.S.save(out/'append-status.json',{'finished':False,'capacity_blocked':{'table':{'job_ids':['missing']}}})
        def wait(self,timeout):return 0
    monkeypatch.setattr(D.subprocess,'Popen',Child)
    result=local_run(tmp_path,monkeypatch)
    assert '--explain' in phases and phases[-1]=='--deduplicate-exact'
    assert result['status']=='partial' and 'last_source_sha256' not in result
    assert Path(result['run_dir'],'source.jobs.json').exists()


def test_unmounted_external_disk_refuses_local_fallback(tmp_path,monkeypatch):
    import pytest
    mount=tmp_path/'pretend-volume';mount.mkdir()
    monkeypatch.setattr(D,'EXTERNAL_MOUNT',mount)
    monkeypatch.setattr(D,'source_hash',lambda: (_ for _ in ()).throw(AssertionError('must fail before capture')))
    with pytest.raises(RuntimeError,match='not mounted'):
        D.run(tmp_path,runs_dir=mount/'runs')
    assert not (mount/'runs').exists()
    import json
    assert json.loads((tmp_path/'status.json').read_text())['status']=='failed'


def test_old_rule_version_cannot_skip_first_new_rule_pass(tmp_path,monkeypatch):
    import pytest
    D.S.save(tmp_path/'status.json',{'last_source_sha256':'a'*64,'last_success_at':'before'})
    monkeypatch.setattr(D,'source_hash',lambda:'a'*64)
    monkeypatch.setattr(D,'capture_source',lambda out: (_ for _ in ()).throw(RuntimeError('first new-rule capture reached')))
    with pytest.raises(RuntimeError,match='first new-rule capture reached'):
        local_run(tmp_path,monkeypatch)


def test_run_local_clears_stale_error_and_finished_at_but_keeps_success_index(tmp_path,monkeypatch):
    import json
    source=tmp_path/'jobs.json';source.write_text('[]')
    state_dir=tmp_path/'state';runs_dir=tmp_path/'runs'
    # Old run residue: WinError 206 + old finished_at must not describe this attempt.
    D.S.save(state_dir/'status.json',{'status':'failed','error':'[WinError 206] 文件名或扩展名太长。',
        'finished_at':'2026-09-14T08:53:28+00:00','last_success_at':'keep-me',
        'last_source_sha256':'b'*64,'last_business_sha256':'c'*64})
    def fake_cli(*args):
        if args and args[0]=='+table-list':
            return {'data':{'tables':[{'id':table} for table in D.S.TABLES]}}
        raise AssertionError('unexpected Base call: '+str(args[:1]))
    monkeypatch.setattr(D.S,'cli',fake_cli)
    monkeypatch.setattr('os.getcwd',lambda: str(tmp_path))  # run_local keeps evidence under cwd
    monkeypatch.setattr(D.S,'snapshot',lambda out: None)   # planned run: snapshot body out of scope
    monkeypatch.setattr(D.S,'make_plan',lambda out, jobs: None)
    state=D.run_local(source,state_dir,runs_dir,apply=False)
    assert state['status']=='planned'
    assert state['error'] is None and state['finished_at'] is not None
    assert state['last_success_at']=='keep-me'
    saved=json.loads((state_dir/'status.json').read_text())
    assert saved['error'] is None and saved['last_success_at']=='keep-me'
