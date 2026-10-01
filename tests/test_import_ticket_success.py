import importlib.util
from pathlib import Path
import pytest
p=Path(__file__).resolve().parents[1]/'deploy/feishu_r1/run_step2_import_r1.py';spec=importlib.util.spec_from_file_location('candidate_ticket',p);R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
def response():
 return {'exit_code':0,'body':{'ok':True,'data':{'ready':True,'failed':False,'job_status':0,'job_status_label':'success','job_error_msg':'success','type':'bitable','token':R.BASE}}}
def test_supplier_success_message_is_not_an_error_and_ticket_only_polled(monkeypatch):
 out=response();assert R.import_succeeded(out);calls=[];record={}
 monkeypatch.setattr(R,'POLL_SLEEP',0)
 def cli(args):calls.append(args);return out
 monkeypatch.setattr(R,'cli',cli)
 assert R.poll_ticket('accepted-ticket',record,{},None,{})=='ready'
 assert record['import_ok'] is True and len(calls)==1 and '+task_result' in calls[0] and '+import' not in calls[0]
@pytest.mark.parametrize('field,value',[('failed',True),('job_status',1),('job_status_label','failed'),('job_error_msg','failed'),('token','other-base'),('type','sheet'),('ready',False)])
def test_success_validator_rejects_supplier_failures_or_wrong_target(field,value):
 out=response();out['body']['data'][field]=value;assert not R.import_succeeded(out)
def test_success_validator_rejects_nonzero_cli_exit():
 out=response();out['exit_code']=1;assert not R.import_succeeded(out)
