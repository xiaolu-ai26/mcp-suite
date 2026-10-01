import importlib.util
from pathlib import Path
import pytest
p=Path(__file__).resolve().parents[1]/'deploy/feishu_r1/run_step2_import_r1.py';spec=importlib.util.spec_from_file_location('candidate_import',p);R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
def rows(n):return [{'id':f'tbl{i}', 'name':f'table{i}'} for i in range(n)]
def test_all_tables_after_default_page_boundary(monkeypatch):
    all_rows=rows(151);calls=[]
    def cli(args):
        offset=int(args[args.index('--offset')+1]);calls.append(offset)
        return {'exit_code':0,'body':{'ok':True,'data':{'tables':all_rows[offset:offset+100],'total':151}}}
    monkeypatch.setattr(R,'cli',cli);by_name,tables=R.table_map()
    assert calls==[0,100] and len(tables)==151 and by_name['table150']['id']=='tbl150'
@pytest.mark.parametrize('problem',['short','duplicate','changed_total'])
def test_incomplete_or_drifting_pages_fail_closed(monkeypatch,problem):
    all_rows=rows(151)
    def cli(args):
        offset=int(args[args.index('--offset')+1]);page=all_rows[offset:offset+100];total=151
        if problem=='short' and offset==0:page=page[:50]
        if problem=='duplicate' and offset:page[0]=all_rows[0]
        if problem=='changed_total' and offset:total=150
        return {'exit_code':0,'body':{'ok':True,'data':{'tables':page,'total':total}}}
    monkeypatch.setattr(R,'cli',cli)
    with pytest.raises(SystemExit,match='table-list pagination'):R.table_map()
