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
