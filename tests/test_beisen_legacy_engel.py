"""Offline ENGEL legacy protocol and configured routing; fixture is representative."""
import copy
import hashlib
import html
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from qiuzhao.collector import p1_platform_beisen as B
from qiuzhao.collector import p1_platform_51job as J
from qiuzhao.collector import p1_pipeline as P

FIELDS=json.loads((Path(__file__).parent/'fixtures/platform/engel_legacy_public_fields.json').read_text(encoding='utf-8'))
ROUTE=J.scope_route('ENGEL','social')


def listing(rows,total=None,current=1,pages=1,next_href=None,tenant=None):
    total=len(rows) if total is None else total
    cells=[]
    for row in rows:
        ident=row['Id'];title=html.escape(row['JobAdName'],quote=True)
        cells.append(f'<tr><td><a href="/zpdetail/{ident}" jobadid="{ident}" title="{title}">{title}</a></td><td></td><td title="广东省-东莞市">广东省-东莞市</td><td>2026-09-22</td></tr>')
    link=next_href if next_href is not None else f'/social/?PageIndex={current+1}'
    next_tag=f'<a href="{html.escape(link,quote=True)}">下一页</a>' if current<pages else ''
    return f'<title>{tenant or ROUTE["tenant_title"]}招聘系统--社会招聘</title><div class="positionlist-newtemplate"><table class="listtable"><tr><th>职位名称</th></tr>{"".join(cells)}</table><span class="tablenote">共{total}条记录</span><div class="tablefooter"><span>当前第{current}/{pages}页</span>{next_tag}</div></div>'


def detail(data):
    labels=(('招聘类别','Category'),('工作性质','Kind'),('招聘人数','HeadCount'),('发布时间','PostDate'),('截止时间','EndTime'))
    fields=''.join(f'<li class="ntitle">{label}：</li><li class="nvalue">{html.escape(data.get(key,""))}</li>' for label,key in labels)
    parts=''.join(f'<p>{label}：</p><p>{html.escape(value).replace(chr(10),"<br>")}</p>' for label,value in (
        ('工作地点',' / '.join(data.get('LocNames',[]))),('工作职责',data.get('Duty','')),('任职资格',data.get('Require',''))))
    return f'<title>{ROUTE["tenant_title"]}招聘系统--招聘详细</title><div class="xiangqingtitle"><span>{html.escape(data["JobAdName"])}</span></div><div class="xiangqingcontain"><ul>{fields}</ul><div class="xiangqingtext">{parts}</div><a id="apply" url="/Portal/Resume/ResumeItem?jid={data["Id"]}">现在申请</a></div>'


class Response:
    status_code=200
    def __init__(self,text,url):self.text=text;self.url=url
    def raise_for_status(self):pass


def collect(tmp_path,monkeypatch,pages=None,details=None,max_requests=None,scope='social'):
    pages=pages or [listing(FIELDS['rows'][:1])]
    details=details or {'311188671':detail(FIELDS['detail'])}
    calls=[]
    class Session:
        def get(self,url,**kwargs):
            calls.append(url)
            if '/zpdetail/' in url:
                value=details[url.rsplit('/',1)[-1]]
                if isinstance(value,Exception):raise value
                return Response(value,url)
            page=int(url.rsplit('=',1)[-1]) if 'PageIndex=' in url else 1
            return Response(pages[page-1],url)
    monkeypatch.setattr(B,'_make_session',Session)
    return J.collect('ENGEL',scope,tmp_path,max_requests=max_requests),calls


def test_recorded_public_fields_and_single_job_full_projection(tmp_path,monkeypatch):
    from datetime import date
    from qiuzhao.v4_fields import to_item
    from qiuzhao.tools import Jobs
    assert (FIELDS['total'],FIELDS['current'],FIELDS['pages'],len(FIELDS['rows']))==(39,1,3,15)
    result,calls=collect(tmp_path,monkeypatch)
    verified=P.validate_result(result,'ENGEL','social',tmp_path)
    assert verified['coverage']['complete'] and verified['coverage']['expected_total']==1
    job=verified['jobs'][0];public=Jobs.public(to_item(job),date(2026,10,9))
    assert job['source_record_id']=='311188671'
    assert public['recruitment_type']=='社会招聘' and public['cities']==['东莞']
    assert public['published_at']=='2026-09-22'
    assert '大专或以上学历' in public['description_raw'] and '工作性质：全职' in public['description_raw']
    assert calls==['https://engel.zhiye.com/Social','https://engel.zhiye.com/zpdetail/311188671']
    assert all('/Portal/' not in url for url in calls)


def test_three_page_39_offline_controlled_unique_native_ids(tmp_path,monkeypatch):
    rows=[{**FIELDS['rows'][0],'Id':str(500000000+i)} for i in range(39)]
    pages=[listing(rows[:15],39,1,3),listing(rows[15:30],39,2,3),listing(rows[30:],39,3,3)]
    details={r['Id']:detail({**FIELDS['detail'],'Id':r['Id']}) for r in rows}
    result,calls=collect(tmp_path,monkeypatch,pages,details)
    assert result['coverage']['complete'] and result['coverage']['expected_total']==39
    assert len(result['jobs'])==39 and len(result['coverage']['list_observed_ids'])==39
    assert calls[1:3]==['https://engel.zhiye.com/social/?PageIndex=2','https://engel.zhiye.com/social/?PageIndex=3']


@pytest.mark.parametrize('bad', ['total-drift','duplicate','early-empty','missing-id','offsite-next'])
def test_list_protocol_not_false_complete(tmp_path,monkeypatch,bad):
    first=listing(FIELDS['rows'][:1],2,1,2)
    second_row={**FIELDS['rows'][0],'Id':'311188672'}
    second=listing([second_row],2,2,2)
    if bad=='total-drift':second=listing([second_row],3,2,2)
    elif bad=='duplicate':second=listing(FIELDS['rows'][:1],2,2,2)
    elif bad=='early-empty':second=listing([],2,2,2)
    elif bad=='missing-id':first=first.replace('jobadid="311188671"','')
    else:first=listing(FIELDS['rows'][:1],2,1,2,next_href='https://other.zhiye.com/social/?PageIndex=2')
    result,calls=collect(tmp_path,monkeypatch,[first,second])
    assert not result['coverage']['complete'] and result['coverage']['expected_total']==2
    assert result['coverage']['errors'] and not any('other.zhiye' in url for url in calls)


@pytest.mark.parametrize('change',[{'Category':'校园招聘'},{'Id':'311188672'},{'Duty':'','Require':''},{'Require':''}])
def test_detail_identity_scope_or_body_gap_stays_partial(tmp_path,monkeypatch,change):
    result,_=collect(tmp_path,monkeypatch,details={'311188671':detail({**FIELDS['detail'],**change})})
    assert not result['coverage']['complete'] and result['coverage']['expected_total']==1
    assert result['coverage']['errors']


def test_budget_and_saved_evidence_not_complete_39(tmp_path,monkeypatch):
    first=listing(FIELDS['rows'],39,1,3)
    result,calls=collect(tmp_path,monkeypatch,[first],max_requests=1)
    assert calls==['https://engel.zhiye.com/Social']
    assert not result['coverage']['complete'] and result['coverage']['expected_total']==39
    assert result['coverage']['request_budget_exhausted']
    assert result['coverage']['evidence_files']==['legacy-list-1.html']


def test_intern_unknown_has_no_http_and_not_complete(tmp_path,monkeypatch):
    result,calls=collect(tmp_path,monkeypatch,scope='intern')
    assert calls==[] and result['coverage']['status']=='blocked'
    assert not result['coverage']['complete'] and result['coverage']['expected_total'] is None
    assert 'source_scope_not_verified' in result['coverage']['errors']


def test_campus_original_url_and_family_unchanged(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(J,'_get',lambda session,url,budget:calls.append(url) or '<title>ENGEL校园招聘</title>')
    J.collect('ENGEL','campus',tmp_path)
    assert calls==['https://campus.51job.com/engel2027/introduction.html']
    assert P.platform_group('ENGEL')==P.platform_group('ENGEL','campus')=='51job.com'
    assert P.platform_group('ENGEL','social')=='zhiye.com'


@pytest.mark.parametrize('change',[{'method':'POST'},{'host':'https://evil.example'},{'host':'http://engel.zhiye.com'},
                                  {'query':'China'},{'recruitment_label':'校园招聘'},{'adapter':'unknown'}])
def test_unknown_route_parameters_rejected_before_http(tmp_path,monkeypatch,change):
    entries=copy.deepcopy(J._read_platform());entries['engel2027']['scope_routes']['social'].update(change)
    monkeypatch.setattr(J,'_read_platform',lambda:entries)
    result,calls=collect(tmp_path,monkeypatch)
    assert calls==[] and not result['coverage']['complete'] and result['coverage']['errors']
    with pytest.raises(ValueError):P.platform_group('ENGEL','social')


def test_scope_route_joins_existing_zhiye_gate_without_cap_or_plan_change(tmp_path,monkeypatch):
    lock=threading.Lock();active=0;peak=0;starts=[]
    def fake(company,scope,out,timeout):
        nonlocal active,peak
        with lock:active+=1;peak=max(peak,active);starts.append(time.monotonic())
        time.sleep(.03)
        with lock:active-=1
        return {'jobs':[],'coverage':{'status':'partial','complete':False,'detail_complete':False,
            'available_job_count':1,'pending_count':0,'collected_jobs':0,'pages_scanned':1,'errors':[]}}
    monkeypatch.setattr(P,'collect_process',fake)
    P.run(tmp_path,tmp_path/'run',['ENGEL','中信建投'],['social'],workers=2,platform_workers=1,platform_min_interval=.05)
    assert peak==1 and starts[1]-starts[0]>=.045
    units=sorted((n,s) for n in P.DEFAULT_COMPANIES for s in P.SCOPES)
    assert len(P.DEFAULT_COMPANIES)==len(set(P.DEFAULT_COMPANIES))==1124 and len(units)==3372
    assert hashlib.sha256(json.dumps(units,ensure_ascii=False).encode()).hexdigest()=='81e6f011def97866350dcb3c221ceb9cf5a0d7b8d42b79a786960a5638ee0150'



def test_unknown_blank_next_parameter_is_not_adopted(tmp_path,monkeypatch):
    first=listing(FIELDS['rows'][:1],2,1,2,next_href='/social/?PageIndex=2&unknown=')
    result,calls=collect(tmp_path,monkeypatch,[first])
    assert result['coverage']['expected_total']==2 and not result['coverage']['complete']
    assert not any('PageIndex=2' in url for url in calls)


def test_detail_budget_partial_retains_previous_unfetched_role(tmp_path,monkeypatch):
    rows=[FIELDS['rows'][0],{**FIELDS['rows'][0],'Id':'311188672'}]
    pages=[listing(rows)]
    details={r['Id']:detail({**FIELDS['detail'],'Id':r['Id']}) for r in rows}
    old_dir=tmp_path/'old';current_dir=tmp_path/'current'
    old,_=collect(old_dir,monkeypatch,pages,details)
    previous,_=P.merge_records([], [('ENGEL','social',P.validate_result(old,'ENGEL','social',old_dir))])
    fresh,calls=collect(current_dir,monkeypatch,pages,details,max_requests=2)
    result=P.validate_result(fresh,'ENGEL','social',current_dir)
    assert result['coverage']['expected_total']==2 and len(result['jobs'])==1
    assert result['coverage']['status']=='partial' and not result['coverage']['complete']
    merged,_=P.merge_records(previous,[('ENGEL','social',result)])
    assert len(merged)==2 and all(row.get('status')!='removed' for row in merged)
    assert len(calls)==2 and result['coverage']['request_budget']['used']==2


def test_fresh_detail_mutation_and_omitted_city_keep_field_origins(tmp_path,monkeypatch):
    changed={**FIELDS['detail'],'JobAdName':'新服务岗位标题','Duty':'新职责：维修现场设备。','LocNames':[]}
    result,_=collect(tmp_path,monkeypatch,details={'311188671':detail(changed)})
    job=result['jobs'][0]
    assert job['job_title']=='新服务岗位标题' and '新职责' in job['description_raw']
    assert job['cities']==['东莞'] and job['verified_at']==job['list_checked_at']
    assert job['field_provenance']['cities']['source']=='official_list'
    assert job['field_provenance']['description_raw']['source']=='official_detail'
    assert '地点' in job['detail_presentation'] and '保留本次官网列表事实' in job['detail_presentation']


@pytest.mark.parametrize('missing',['工作职责','任职资格','both'])
def test_missing_value_paragraph_is_not_next_section_label(tmp_path,monkeypatch,missing):
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(detail(FIELDS['detail']),'html.parser')
    for label in soup.select('.xiangqingtext > p'):
        name=label.get_text(strip=True).rstrip('：:')
        if name==missing or (missing=='both' and name in ('工作职责','任职资格')):
            label.find_next_sibling('p').decompose()
    result,_=collect(tmp_path,monkeypatch,details={'311188671':str(soup)})
    validated=P.validate_result(result,'ENGEL','social',tmp_path)
    assert not validated['coverage']['complete'] and validated['coverage']['expected_total']==1
    if missing=='both':assert validated['jobs']==[]
    else:
        assert len(validated['jobs'])==1
        expected='description' if missing=='工作职责' else 'requirement'
        assert expected in validated['jobs'][0]['source_missing_fields']


def test_bad_route_is_one_blocked_unit_and_other_company_continues(tmp_path,monkeypatch):
    entries=copy.deepcopy(J._read_platform());entries['engel2027']['scope_routes']['social']['method']='POST'
    monkeypatch.setattr(J,'_read_platform',lambda:entries)
    calls=[]
    def good(company,scope,out,timeout):
        calls.append(company)
        return {'jobs':[],'coverage':{'status':'success','complete':True,'detail_complete':True,
            'expected_total':0,'collected_jobs':0,'pages_scanned':1,'errors':[],
            'scope_evidence':'offline controlled valid zero'}}
    monkeypatch.setattr(P,'collect_process',good)
    rc=P.run(tmp_path,tmp_path/'run',['ENGEL','中信建投'],['social'],workers=2,
             platform_workers=1,platform_min_interval=0)
    state=json.loads((tmp_path/'run'/'status.json').read_text(encoding='utf-8'))
    assert rc==2 and calls==['中信建投']
    rejected=state['results']['ENGEL/social']['coverage']
    assert rejected['status']=='blocked' and rejected['failure_phase']=='scope_route'
    assert state['results']['中信建投/social']['coverage']['complete']



def test_detail_missing_date_keeps_explicit_list_fact_and_time(tmp_path,monkeypatch):
    result,_=collect(tmp_path,monkeypatch,details={'311188671':detail({**FIELDS['detail'],'PostDate':''})})
    job=result['jobs'][0]
    assert job['published_at']=='2026-09-22'
    assert job['field_provenance']['published_at']['source']=='official_list'
    assert job['field_provenance']['published_at']['checked_at']==job['list_checked_at']
    assert job['verified_at']==job['list_checked_at']
    assert job['detail_source']=='official_list_and_detail' and '发布日期' in job['detail_presentation']
    assert '发布时间：2026-09-22' not in job['description_raw']



def original_markup_detail():
    marker='<div class="xiangqingtext">'
    baseline=detail(FIELDS['detail']);start=baseline.index(marker);end=baseline.index('</div><a id="apply"',start)
    return baseline[:start]+FIELDS['original_section_markup']+baseline[end+6:]


def test_original_voidbr_descendant_qualification_real_collect_chain(tmp_path,monkeypatch):
    import bs4
    from datetime import date
    from qiuzhao.v4_fields import to_item
    from qiuzhao.tools import Jobs
    original=bs4.BeautifulSoup
    class OldVoidBrTree(original):
        def __init__(self,raw,*args,**kwargs):
            super().__init__(raw,*args,**kwargs)
            section=self.select_one('.xiangqingtext')
            if section:
                label=next(p for p in section.find_all('p') if p.get_text(strip=True)=='任职资格：')
                value=label.find_next_sibling('p')
                wrapper=self.new_tag('br');wrapper.append(label.extract());wrapper.append(value.extract());section.append(wrapper)
                assert label.parent.name=='br'
    monkeypatch.setattr(bs4,'BeautifulSoup',OldVoidBrTree)
    raw=original_markup_detail()
    result,_=collect(tmp_path,monkeypatch,details={'311188671':raw})
    validated=P.validate_result(result,'ENGEL','social',tmp_path)
    assert validated['coverage']['complete'] and validated['coverage']['expected_total']==1
    job=validated['jobs'][0]
    assert job['source_missing_fields']==[]
    public=Jobs.public(to_item(job),date(2026,10,9))
    assert '大专或以上学历' in public['description_raw']
    assert '能够读懂电气原理图' in public['description_raw']
    assert 'Minimum of three years' in public['description_raw']


def test_actual_original_raw_detail_then_collect_validate_public(tmp_path,monkeypatch):
    from datetime import date
    from qiuzhao.v4_fields import to_item
    from qiuzhao.tools import Jobs
    raw_path=Path('/Users/maxzhl/Projects/qiuzhao-lzh-handoff-20261002/phase-20261008/engel-original-protocol/detail-311188671-original.html')
    if not raw_path.exists():pytest.skip('private original sample unavailable; original markup fixture remains tested')
    raw=raw_path.read_text(encoding='utf-8')
    assert hashlib.sha256(raw_path.read_bytes()).hexdigest()==FIELDS['detail_original_sha256']
    parsed=B._legacy_detail(raw,'311188671',ROUTE)
    assert parsed['Require']==FIELDS['detail']['Require'] and parsed['Duty']==FIELDS['detail']['Duty']
    result,_=collect(tmp_path,monkeypatch,details={'311188671':raw})
    checked=P.validate_result(result,'ENGEL','social',tmp_path)
    public=Jobs.public(to_item(checked['jobs'][0]),date(2026,10,9))
    assert checked['coverage']['complete'] and '大专或以上学历' in public['description_raw']


def test_present_null_route_rejected_by_adapter_preview_and_pipeline(tmp_path,monkeypatch):
    entries=copy.deepcopy(J._read_platform());entries['engel2027']['scope_routes']=None
    monkeypatch.setattr(J,'_read_platform',lambda:entries)
    result,calls=collect(tmp_path,monkeypatch)
    assert calls==[] and result['coverage']['status']=='blocked' and not result['coverage']['complete']
    with pytest.raises(ValueError):P.platform_group('ENGEL','social')
    calls=[]
    def good(company,scope,out,timeout):
        calls.append(company)
        return {'jobs':[],'coverage':{'status':'success','complete':True,'detail_complete':True,
            'expected_total':0,'collected_jobs':0,'pages_scanned':1,'errors':[],
            'scope_evidence':'offline controlled valid zero'}}
    monkeypatch.setattr(P,'collect_process',good)
    assert P.run(tmp_path,tmp_path/'run',['ENGEL','中信建投'],['social'],workers=2,platform_min_interval=0)==2
    assert calls==['中信建投']


def test_duplicate_descendant_section_label_still_rejected(tmp_path,monkeypatch):
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(original_markup_detail(),'html.parser')
    section=soup.select_one('.xiangqingtext');wrapper=soup.new_tag('br')
    label=soup.new_tag('p');label.string='任职资格：';value=soup.new_tag('p');value.string='重复但不可借用的资格段'
    wrapper.append(label);wrapper.append(value);section.append(wrapper)
    result,_=collect(tmp_path,monkeypatch,details={'311188671':str(soup)})
    assert not result['coverage']['complete'] and result['jobs']==[]
    assert any('repeated requirement section' in error for error in result['coverage']['errors'])


def test_absent_route_key_keeps_original_51job_semantics_only(tmp_path,monkeypatch):
    entries=copy.deepcopy(J._read_platform());del entries['engel2027']['scope_routes']
    monkeypatch.setattr(J,'_read_platform',lambda:entries)
    result,calls=collect(tmp_path,monkeypatch)
    assert calls==[] and result['coverage']['complete']
    assert J.scope_route('ENGEL','social') is None
