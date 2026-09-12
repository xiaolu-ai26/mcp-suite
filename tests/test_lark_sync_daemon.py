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
