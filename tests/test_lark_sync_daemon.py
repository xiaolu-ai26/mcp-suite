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
