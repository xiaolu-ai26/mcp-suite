import importlib.util
from pathlib import Path
import pytest
p=Path(__file__).resolve().parents[1]/'deploy/feishu_r1/run_step3_schema_verify_r1.py';spec=importlib.util.spec_from_file_location('rate_candidate',p);R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
def clock(monkeypatch):
 t=[100.0];sleeps=[]
 monkeypatch.setattr(R.time,'monotonic',lambda:t[0])
 def sleep(n):sleeps.append(n);t[0]+=n
 monkeypatch.setattr(R.time,'sleep',sleep);monkeypatch.setattr(R,'_last_field_update',0);return sleeps

def limited():return {'exit_code':1,'body':{'ok':False,'error':{'code':800004135}},'stderr_tail':'method limited'}
def test_explicit_limit_retries_with_bound_then_success(monkeypatch):
 sleeps=clock(monkeypatch);calls=[];responses=[limited(),limited(),{'exit_code':0,'body':{'ok':True}}]
 def once(*args):calls.append(args);return responses.pop(0)
 monkeypatch.setattr(R,'_cli_once',once);out=R.cli(['base','+field-update','same-json'])
 assert len(calls)==3 and sleeps==[5,10] and out['rate_limit_retries']==2 and out['body']['ok']
 assert all(x[0]==calls[0][0] for x in calls)
def test_rate_limit_exhaustion_is_still_failure(monkeypatch):
 sleeps=clock(monkeypatch);calls=[]
 monkeypatch.setattr(R,'_cli_once',lambda *args:calls.append(args) or limited());out=R.cli(['base','+field-update'])
 assert len(calls)==4 and sleeps==[5,10,20] and out['body']['ok'] is False and out['stderr_tail']=='method limited'
def test_nonlimit_failure_is_never_retried(monkeypatch):
 clock(monkeypatch);calls=[]
 monkeypatch.setattr(R,'_cli_once',lambda *args:calls.append(args) or {'exit_code':1,'body':{'ok':False,'error':{'code':123}}});out=R.cli(['base','+field-update'])
 assert len(calls)==1 and out['body']['ok'] is False

def test_successful_field_calls_are_paced_other_calls_are_not(monkeypatch):
 sleeps=clock(monkeypatch);monkeypatch.setattr(R,'_cli_once',lambda *args:{'exit_code':0,'body':{'ok':True}})
 R.cli(['base','+field-update']);R.cli(['base','+field-update']);R.cli(['base','+field-list'])
 assert sleeps==[3]

def test_real_error_json_on_stderr_uses_bounded_retry(monkeypatch):
    import json
    from types import SimpleNamespace
    sleeps=clock(monkeypatch);calls=[]
    response=SimpleNamespace(stdout='',stderr=json.dumps({'ok':False,'error':{'code':800004135,'message':'OpenAPIUpdateField limited'}}),returncode=1)
    monkeypatch.setattr(R.subprocess,'run',lambda *a,**k:calls.append(a) or response)
    out=R.cli(['base','+field-update'])
    assert len(calls)==4 and sleeps==[5,10,20] and out['rate_limit_retries']==3
    assert out['body']['error']['code']==800004135 and 'limited' in out['stderr_tail']

@pytest.mark.parametrize('stderr',['unstructured message with 800004135','{"ok":true,"error":{"code":800004135}}'])
def test_unknown_or_success_stderr_never_causes_retry(monkeypatch,stderr):
    from types import SimpleNamespace
    clock(monkeypatch);calls=[]
    monkeypatch.setattr(R.subprocess,'run',lambda *a,**k:calls.append(a) or SimpleNamespace(stdout='',stderr=stderr,returncode=1))
    out=R.cli(['base','+field-update'])
    assert len(calls)==1 and out['body']['ok'] is False and out['exit_code']==1

def test_unknown_error_string_is_returned_once(monkeypatch):
    clock(monkeypatch);calls=[]
    monkeypatch.setattr(R,'_cli_once',lambda *a:calls.append(a) or {'exit_code':1,'body':{'ok':False,'error':'unknown supplier error'}})
    out=R.cli(['base','+field-update'])
    assert len(calls)==1 and out['body']['error']=='unknown supplier error'

def test_nonfield_timeout_remains_300(monkeypatch):
    calls=[];monkeypatch.setattr(R,'_cli_once',lambda *a:calls.append(a) or {'exit_code':0,'body':{'ok':True}})
    R.cli(['base','+record-list'])
    assert calls[0][2]==300
