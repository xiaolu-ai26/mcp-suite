from pathlib import Path
from qiuzhao.collector import lark_sync_daemon as D


def test_unchanged_source_does_not_read_or_write_base(tmp_path,monkeypatch):
    D.S.save(tmp_path/'status.json',{'status':'success','last_source_sha256':'a'*64,'last_success_at':'before'})
    monkeypatch.setattr(D,'source_hash',lambda:'a'*64)
    monkeypatch.setattr(D,'capture_source',lambda out: (_ for _ in ()).throw(AssertionError('unexpected snapshot')))
    result=D.run(tmp_path)
    assert result['status']=='unchanged' and result['last_success_at']=='before'


def test_auth_or_network_failure_is_recorded_without_losing_last_success(tmp_path,monkeypatch):
    D.S.save(tmp_path/'status.json',{'status':'success','last_source_sha256':'a'*64,'last_success_at':'before'})
    def fail():raise RuntimeError('SSH unavailable')
    monkeypatch.setattr(D,'source_hash',fail)
    try:D.run(tmp_path)
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
    result=D.run(tmp_path)
    assert phases[-1]=='--explain'
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
