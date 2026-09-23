from unittest.mock import patch
from qiuzhao.collector.p1_sources_21_30 import collect_yonyou

class Response:
 def __init__(self,value):self.value=value
 def raise_for_status(self):pass
 def json(self):return self.value

def test_dayee_honors_server_page_size_and_full_details(tmp_path):
 calls=[];suite='67ac41886202cc7916ae3029'
 def post(url,data,**kwargs):
  if 'listPositionDetail' in url:
   return Response({'state':200,'data':{'postId':data['postId'],'postName':'实习工程师','recruitType':12,'workContent':'开发真实功能','serviceCondition':'','workPlaceList':[{'name':'上海'}]}})
  page=data['currentPage'];calls.append(dict(data));r={'postId':str(page),'postName':'实习工程师','recruitType':12,'currentSuiteKey':suite}
  return Response({'state':200,'data':{'pageForm':{'pageData':[r],'dataCount':2,'pageSize':1}}})
 with patch('qiuzhao.collector.p1_sources_21_30.requests.post',post),patch('qiuzhao.collector.p1_sources_21_30.Fetcher.get',return_value=('<html>official</html>','official')):
  result=collect_yonyou('用友网络','intern',tmp_path)
 assert [p['pageSize'] for p in calls]==[50,1]
 assert result['coverage']['complete'] and len(result['jobs'])==2
 assert result['jobs'][0]['source_missing_fields']==['requirement']

def test_dayee_duplicate_page_cannot_succeed(tmp_path):
 def post(url,data,**kwargs):
  return Response({'state':200,'data':{'pageForm':{'pageData':[{'postId':'same','recruitType':12,'currentSuiteKey':'67ac41886202cc7916ae3029'}],'dataCount':2,'pageSize':1}}})
 with patch('qiuzhao.collector.p1_sources_21_30.requests.post',post),patch('qiuzhao.collector.p1_sources_21_30.Fetcher.get',return_value=('<html>official</html>','official')):
  result=collect_yonyou('用友网络','intern',tmp_path)
 assert not result['coverage']['complete']
 assert any('repeated ID' in e for e in result['coverage']['errors'])

def test_dayee_wrong_tenant_rejected(tmp_path):
 def post(url,data,**kwargs):
  return Response({'state':200,'data':{'pageForm':{'pageData':[{'postId':'1','recruitType':12,'currentSuiteKey':'another-company'}],'dataCount':1,'pageSize':1}}})
 with patch('qiuzhao.collector.p1_sources_21_30.requests.post',post),patch('qiuzhao.collector.p1_sources_21_30.Fetcher.get',return_value=('<html>official</html>','official')):
  result=collect_yonyou('用友网络','intern',tmp_path)
 assert result['jobs']==[] and not result['coverage']['complete']


# --- iflytek evidence paths (2026-09-24: 894 official rows rejected, evidence was nested) ---
import json
from pathlib import Path

import pytest

from qiuzhao.collector import p1_pipeline as P
from qiuzhao.collector import p1_sources_21_30 as S21
from qiuzhao.collector import p1_sources_31_40 as S31

PORTAL = '6e2235dc-4b88-4698-b96a-5a73c705d8db'
ROWS = [('a1', '2', '校园招聘'), ('a2', '4', '飞星计划'), ('b1', '6', '星火X顶尖AI人才计划'), ('c1', '1', '社会招聘')]


class Page:
    def __init__(self, value, url='https://iflytek.zhiye.com/'):
        self.value, self.url, self.encoding = value, url, None
        self.text = value if isinstance(value, str) else json.dumps(value)

    def raise_for_status(self):
        pass

    def json(self):
        return self.value


class Session:
    def get(self, url, **kwargs):
        return Page('<script>var c={"PortalId":"%s"}</script> iflytek.zhiye.com' % PORTAL)

    def post(self, url, json=None, **kwargs):
        data = [{'Id': i, 'CategoryId': c, 'Category': n} for i, c, n in ROWS] if json['PageIndex'] == 0 else []
        return Page({'Code': 200, 'Data': data, 'Count': len(ROWS)})


def detail(url, params=None, **kwargs):
    ident = params['jobAdId']
    _, category, name = next(r for r in ROWS if r[0] == ident)
    return Page({'Code': 200, 'Data': {'Id': ident, 'CategoryId': category, 'Category': name, 'JobAdName': '工程师' + ident,
                                       'Duty': '负责真实研发工作', 'Require': '本科及以上', 'LocNames': ['合肥'], 'Kind': '实习'}})


def collect(scope, output_dir, monkeypatch):
    monkeypatch.setattr(S31.shared, 'make_session', Session)
    monkeypatch.setattr(S31.shared, 'http_get', detail)
    return S21.collect('科大讯飞', scope, output_dir)


@pytest.mark.parametrize('scope, expected', [('campus', {'a1', 'a2'}), ('intern', {'b1'}), ('social', {'c1'})])
def test_iflytek_evidence_is_named_relative_to_the_scope_output_root(tmp_path, monkeypatch, scope, expected):
    result = collect(scope, tmp_path, monkeypatch)
    coverage = result['coverage']
    assert coverage['complete'] is True and {j['source_record_id'] for j in result['jobs']} == expected
    nested = f'iflytek/{scope}/'
    assert coverage['evidence_files'] == coverage['evidence']
    assert coverage['evidence_files'][0] == nested + 'official-entry.html'
    assert all(ref.startswith(nested) and (tmp_path / ref).stat().st_size for ref in coverage['evidence_files'])
    validated = P.validate_result(result, '科大讯飞', scope, tmp_path)
    assert validated['coverage']['complete'] is True and len(validated['jobs']) == len(expected)


def test_iflytek_relative_output_dir_is_resolved_like_the_pipeline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = collect('campus', Path('scope-out'), monkeypatch)
    assert result['coverage']['evidence_files'][0] == 'iflytek/campus/official-entry.html'
    assert P.validate_result(result, '科大讯飞', 'campus', Path('scope-out'))['coverage']['complete'] is True


def test_bare_names_are_what_the_validator_rejected(tmp_path, monkeypatch):
    result = collect('campus', tmp_path, monkeypatch)
    for key in ('evidence_files', 'evidence'):
        result['coverage'][key] = [Path(ref).name for ref in result['coverage'][key]]
    with pytest.raises(ValueError, match='nonempty current scope'):
        P.validate_result(result, '科大讯飞', 'campus', tmp_path)


@pytest.mark.parametrize('tamper', ['missing', 'empty', 'traversal', 'absolute_outside'])
def test_bad_iflytek_evidence_is_still_rejected(tmp_path, monkeypatch, tamper):
    root = tmp_path / 'scope'
    result = collect('campus', root, monkeypatch)
    refs = result['coverage']['evidence_files']
    outside = tmp_path / 'outside.json'
    outside.write_text('{"Code": 200}')
    if tamper == 'missing':
        (root / refs[-1]).unlink()
    elif tamper == 'empty':
        (root / refs[-1]).write_text('')
    elif tamper == 'traversal':
        refs.append('iflytek/campus/../../../outside.json')
    else:
        refs.append(str(outside))
    with pytest.raises(ValueError, match='nonempty current scope'):
        P.validate_result(result, '科大讯飞', 'campus', root)
