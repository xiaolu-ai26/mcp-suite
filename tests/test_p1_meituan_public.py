from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from qiuzhao.collector import p1_meituan_public as m


def page_response(page_no, rows, total_count, total_page, status=1):
    return {
        'status': status,
        'message': '成功',
        'data': {
            'page': {
                'pageNo': page_no,
                'pageSize': 20,
                'totalCount': total_count,
                'totalPage': total_page,
            },
            'list': rows,
        },
    }


def mk_job(*, job_id='111', title='测试岗位', job_type='1', duty='', req='', project=''):
    return {
        'jobUnionId': job_id,
        'name': title,
        'jobType': job_type,
        'cityList': [{'name': '北京市'}],
        'jobDuty': duty,
        'jobRequirement': req,
        'projectName': project,
        'refreshTime': 0,
        'expiredTime': 0,
    }


class MeituanPublicAdapterTests(unittest.TestCase):

    def run_collect(self, scope, responses):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            # The adapter paces real list pages (>=1s apart); tests must not wait.
            with patch.object(m, '_post_json', side_effect=responses), \
                 patch.object(m.time, 'sleep'):
                result = m.collect('美团', scope, out)
            return result, out, (out / 'candidate.json').exists(), (out / 'coverage.json').exists()

    def test_pagination_duplicate_job_id_no_full_complete(self):
        rows = [mk_job(job_id='a', job_type='1', duty='岗位职责：测试职责', req='岗位要求：测试要求'),
                mk_job(job_id='a', job_type='1', duty='岗位职责：重复', req='岗位要求：重复')]
        result, _, candidate_exists, _ = self.run_collect('campus', [page_response(1, rows, 1, 1)])
        self.assertEqual(result['coverage']['complete'], False)
        self.assertEqual(result['coverage']['status'], 'partial')
        self.assertEqual(result['coverage']['collected_jobs'], 1)
        self.assertIn('duplicate source_record_id', '\n'.join(result['coverage']['errors']))
        self.assertTrue(candidate_exists)

    def test_pagination_missing_page_not_complete(self):
        rows1 = [mk_job(job_id='a', job_type='1', duty='岗位职责：测试', req='岗位要求：测试')]
        rows2 = []
        result, *_ = self.run_collect('campus', [page_response(1, rows1, 2, 2), page_response(2, rows2, 2, 2)])
        self.assertFalse(result['coverage']['complete'])
        self.assertEqual(result['coverage']['expected_total'], 2)
        self.assertEqual(result['coverage']['unique_source_ids'], 1)
        self.assertEqual(result['coverage']['collected_jobs'], 1)

    def test_wrong_job_type_is_rejected_as_non_complete(self):
        rows = [mk_job(job_id='b', job_type='1', duty='岗位职责：A', req='岗位要求：B')]
        result, *_ = self.run_collect('intern', [page_response(1, rows, 1, 1)])
        self.assertIn('jobType mismatch', '\n'.join(result['coverage']['errors']))
        self.assertFalse(result['coverage']['complete'])
        self.assertEqual(result['coverage']['collected_jobs'], 0)

    def test_wrong_job_type_is_skipped_and_kept_including_other_jobs(self):
        rows = [
            mk_job(job_id='x', job_type='1', duty='岗位职责：A', req='岗位要求：B'),
            mk_job(job_id='y', job_type='2', duty='岗位职责：C', req='岗位要求：D'),
        ]
        result, *_ = self.run_collect('intern', [page_response(1, rows, 2, 1)])
        self.assertIn('jobType mismatch for x', '\n'.join(result['coverage']['errors']))
        self.assertEqual(result['coverage']['collected_jobs'], 1)
        self.assertEqual(result['jobs'][0]['source_record_id'], 'y')
        self.assertFalse(result['coverage']['complete'])

    def test_one_field_missing_is_retained(self):
        rows = [mk_job(job_id='c', job_type='2', duty='岗位职责：1）真实职责内容', req='')]
        result, *_ = self.run_collect('intern', [page_response(1, rows, 1, 1)])
        self.assertEqual(result['coverage']['complete'], True)
        self.assertEqual(result['coverage']['status'], 'success')
        self.assertEqual(result['jobs'][0]['source_missing_fields'], ['jobRequirement'])

    def test_both_fields_empty_stays_pending(self):
        rows = [mk_job(job_id='d', job_type='3', duty='   ', req='\n\n')]
        result, *_ = self.run_collect('social', [page_response(1, rows, 1, 1)])
        self.assertEqual(result['coverage']['complete'], False)
        self.assertEqual(result['coverage']['detail_missing_count'], 1)
        self.assertEqual(result['coverage']['status'], 'partial')
        self.assertEqual(result['coverage']['jobs_with_missing_fields'], [])
        self.assertEqual(result['coverage']['collected_jobs'], 0)
        self.assertEqual(result['coverage']['pending_source_ids'], ['d'])

    def test_both_fields_empty_does_not_count_for_detail_complete(self):
        rows = [mk_job(job_id='e2', job_type='2', duty='   ', req='\n\n')]
        result, *_ = self.run_collect('intern', [page_response(1, rows, 1, 1)])
        self.assertFalse(result['coverage']['detail_complete'])
        self.assertFalse(result['coverage']['complete'])
        self.assertEqual(result['coverage']['status'], 'partial')

    def test_long_raw_description_is_not_truncated(self):
        duty = '岗位职责：' + ('A' * 5200)
        rows = [mk_job(job_id='e', job_type='1', duty=duty, req='要求：')]
        result, *_ = self.run_collect('campus', [page_response(1, rows, 1, 1)])
        self.assertGreaterEqual(len(result['jobs'][0]['description_raw']), 5200)

    def test_scope_request_and_evidence_files_are_real_paths(self):
        rows = [mk_job(job_id='f', job_type='1', duty='岗位职责：A', req='岗位要求：B')]
        result, out, _, coverage_exists = self.run_collect('campus', [page_response(1, rows, 1, 1)])
        scope_request = result['coverage']['scope_request']
        self.assertEqual(scope_request['company'], '美团')
        self.assertEqual(scope_request['scope'], 'campus')
        self.assertEqual(scope_request['source_url'], m.API_URL)
        self.assertIn('page', scope_request['params'])
        self.assertIsInstance(scope_request['params']['page'], dict)
        self.assertEqual(scope_request['params']['page'].get('pageNo'), 1)
        self.assertEqual(scope_request['params']['page'].get('pageSize'), m.PAGE_SIZE)
        self.assertEqual(m.PAGE_SIZE, 100)
        self.assertGreaterEqual(result['coverage']['request_interval'], 1.0)
        self.assertIn('jobType', scope_request['params'])
        self.assertTrue(all(Path(path).is_absolute() for path in result['coverage']['evidence_files']))
        self.assertTrue(coverage_exists)

    def test_proof_path_record_is_on_job_and_no_source_texts(self):
        rows = [mk_job(job_id='g', job_type='1', duty='岗位职责：A', req='岗位要求：B')]
        result, out, _, _ = self.run_collect('campus', [page_response(1, rows, 1, 1)])
        self.assertTrue(Path(result['jobs'][0]['evidence_path']).is_absolute())
        self.assertTrue(result['jobs'][0]['evidence_path'].endswith('/list-1.json'))
        self.assertNotIn('source_texts', result['jobs'][0])

    def test_status_only_1_is_accepted(self):
        rows = [mk_job(job_id='h', job_type='1', duty='岗位职责：A', req='岗位要求：B')]
        result, *_ = self.run_collect('campus', [page_response(1, rows, 1, 1, status=200)])
        self.assertFalse(result['coverage']['complete'])
        self.assertTrue(any("API status=200" in e for e in result['coverage']['errors']))

    def test_education_major_from_requirement_only(self):
        req = '岗位要求：1）2027届本科及以上学历，专业不限；2）优先计算机科学与技术、通信工程及相关专业'
        rows = [mk_job(job_id='i', job_type='1', duty='职位职责：负责AI平台产品落地', req=req)]
        result, *_ = self.run_collect('campus', [page_response(1, rows, 1, 1)])
        job = result['jobs'][0]
        self.assertIn('本科及以上', job['education_raw'])
        self.assertIn('专业不限', job['major_requirements_raw'])
        self.assertIn('计算机科学与技术', job['major_requirements_raw'])

    def test_wrong_company_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                m.collect('非美团', 'campus', Path(d))


if __name__ == '__main__':
    unittest.main()


def test_requirement_extraction_keeps_constraints_without_inventing_majors():
    from qiuzhao.collector import p1_meituan_public as M
    assert M._major_values('优先有Java经验')==''
    assert M._major_values('专业不限')=='专业不限'
    assert M._education_values('本科及以上学历，优秀者可放宽')=='本科及以上学历，优秀者可放宽'
    assert M._is_boilerplate('隐私政策：本网站收集个人信息')


def test_professional_skills_are_not_academic_majors():
    from qiuzhao.collector import p1_meituan_public as M
    assert M._major_values('具备专业的数据分析能力和专业精神')==''
    assert M._major_values('计算机相关专业优先')=='计算机相关专业优先'


# --------------------------------------------------------------------------- #
# pagination honesty + transport retry (2026-09-20 "320/2500" regression)
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode('utf-8')
        self.headers = {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _rows(prefix, count, job_type='3'):
    return [mk_job(job_id='%s-%03d' % (prefix, i), job_type=job_type,
                   duty='岗位职责：职责 %d' % i, req='岗位要求：要求 %d' % i)
            for i in range(count)]


def _collect(monkeypatch, scope, pages, tmp_path):
    """Run collect against faked transports, never sleeping."""
    import ssl
    from urllib.error import HTTPError, URLError

    calls = {'n': 0, 'slots': []}

    def fake_urlopen(request, timeout=None):
        idx = calls['n']
        calls['n'] += 1
        item = pages[min(idx, len(pages) - 1)]
        if isinstance(item, Exception):
            raise item
        return _FakeResponse(item)

    monkeypatch.setattr(m, 'urlopen', fake_urlopen)
    monkeypatch.setattr(m.time, 'sleep', lambda seconds=0: calls['slots'].append(seconds))
    result = m.collect('美团', scope, tmp_path)
    return result, calls


def test_a_transient_ssl_eof_is_retried_and_the_scope_still_completes(monkeypatch, tmp_path):
    # 2026-09-20 的真实形态：page 16 一次 `SSL: UNEXPECTED_EOF_WHILE_READING` 把整个
    # social 采集中断在 320/2500。修法是重试瞬时传输错误，而不是砍页数。
    import ssl
    from urllib.error import URLError
    pages = [page_response(1, _rows('a', 3), 5, 2),
             URLError(ssl.SSLEOFError(8, 'EOF occurred in violation of protocol')),
             page_response(2, _rows('b', 2), 5, 2)]
    result, calls = _collect(monkeypatch, 'social', pages, tmp_path)
    coverage = result['coverage']
    assert coverage['complete'] is True
    assert coverage['status'] == 'success'
    assert coverage['expected_total'] == 5
    assert coverage['collected_jobs'] == 5
    assert coverage['retries'] == 1
    assert calls['n'] == 3
    assert coverage['errors'] == []


def test_retry_is_bounded_and_an_exhausted_retry_stays_partial(monkeypatch, tmp_path):
    from urllib.error import URLError
    boom = URLError(OSError('connection reset'))
    pages = [page_response(1, _rows('a', 3), 5, 2), boom]
    result, calls = _collect(monkeypatch, 'social', pages, tmp_path)
    coverage = result['coverage']
    assert coverage['complete'] is False
    assert coverage['status'] == 'partial'
    assert coverage['collected_jobs'] == 3
    assert coverage['pagination_exhausted'] is False
    assert coverage['retries'] == m.MAX_ATTEMPTS - 1
    assert any('Network failure' in e for e in coverage['errors'])
    # 1 initial try + (MAX_ATTEMPTS-1) retries of page 2, never more.
    assert calls['n'] == 1 + m.MAX_ATTEMPTS


def test_http_404_is_not_retried_but_http_500_is(monkeypatch, tmp_path):
    from io import BytesIO
    from urllib.error import HTTPError
    missing = HTTPError(m.API_URL, 404, 'Not Found', None, BytesIO(b'{"status":0}'))
    result, calls = _collect(monkeypatch, 'social', [missing], tmp_path)
    assert calls['n'] == 1, 'a 4xx answer is final, never retried'
    assert any('HTTP 404' in e for e in result['coverage']['errors'])

    pages = [HTTPError(m.API_URL, 503, 'Busy', None, BytesIO(b'{"status":0}')),
             page_response(1, _rows('a', 2), 2, 1)]
    result, calls = _collect(monkeypatch, 'social', pages, tmp_path)
    assert calls['n'] == 2, 'a 5xx answer is worth another attempt'
    assert result['coverage']['complete'] is True
    assert result['coverage']['retries'] == 1


def test_retry_backoff_is_exponential_and_capped(monkeypatch):
    from urllib.error import URLError
    slept = []
    monkeypatch.setattr(m, 'urlopen',
                        lambda request, timeout=None: (_ for _ in ()).throw(URLError(OSError('x'))))
    monkeypatch.setattr(m.time, 'sleep', lambda seconds=0: slept.append(seconds))
    with pytest.raises(RuntimeError) as excinfo:
        m._post_json({'page': {'pageNo': 1}}, attempts=5)
    assert 'Network failure' in str(excinfo.value)
    assert slept == [1.0, 2.0, 4.0, 8.0]


def test_pages_are_spaced_by_at_least_one_second(monkeypatch, tmp_path):
    pages = [page_response(1, _rows('a', 3), 5, 2), page_response(2, _rows('b', 2), 5, 2)]
    result, calls = _collect(monkeypatch, 'social', pages, tmp_path)
    assert result['coverage']['complete'] is True
    assert calls['slots'], 'the adapter must pace its list pages'
    assert min(calls['slots']) >= m.REQUEST_INTERVAL_FLOOR >= 1.0
    assert result['coverage']['request_interval'] >= 1.0


def test_request_interval_env_hook_can_only_slow_the_adapter(monkeypatch):
    monkeypatch.setenv('QIUZHAO_PLATFORM_REQUEST_INTERVAL', '2.5')
    assert m._page_interval() == 2.5
    monkeypatch.setenv('QIUZHAO_PLATFORM_REQUEST_INTERVAL', '0.05')
    assert m._page_interval() == 1.0
    monkeypatch.setenv('QIUZHAO_PLATFORM_REQUEST_INTERVAL', 'nonsense')
    assert m._page_interval() == 1.0
    monkeypatch.delenv('QIUZHAO_PLATFORM_REQUEST_INTERVAL', raising=False)
    assert m._page_interval() == 1.0


def test_a_reported_page_count_short_of_total_count_keeps_paging(monkeypatch, tmp_path):
    # 站点自报 totalPage 小于 totalCount 时，按 totalPage 收手就会静默少采；
    # 必须继续翻到补齐（有界），并把补的页数留成证据。
    pages = [page_response(1, _rows('a', 100), 150, 1),
             page_response(2, _rows('b', 50), 150, 1)]
    result, calls = _collect(monkeypatch, 'social', pages, tmp_path)
    coverage = result['coverage']
    assert coverage['expected_total'] == 150
    assert coverage['collected_jobs'] == 150
    assert coverage['unique_source_ids'] == 150
    assert coverage['complete'] is True
    assert coverage['pagination_exhausted'] is True
    assert coverage['pages_beyond_reported_total'] == 1
    assert calls['n'] == 2


def test_an_empty_page_before_total_count_is_partial_with_an_error(monkeypatch, tmp_path):
    pages = [page_response(1, _rows('a', 2), 5, 2), page_response(2, [], 5, 2)]
    result, _ = _collect(monkeypatch, 'social', pages, tmp_path)
    coverage = result['coverage']
    assert coverage['complete'] is False
    assert coverage['status'] == 'partial'
    assert coverage['collected_jobs'] == 2
    assert coverage['pagination_exhausted'] is False
    assert any('list exhausted at page 2' in e for e in coverage['errors'])


def test_total_page_overrun_is_bounded_and_reported(monkeypatch, tmp_path):
    # totalPage 永远说 1、totalCount 说 999：补页有上限，超限后如实报错。
    pages = [page_response(1, _rows('a', 100), 999, 1),
             page_response(2, _rows('b', 100), 999, 1)]
    result, calls = _collect(monkeypatch, 'social', pages, tmp_path)
    coverage = result['coverage']
    assert coverage['complete'] is False
    assert any('reported totalPage=1 exhausted' in e for e in coverage['errors'])
    assert calls['n'] == 1 + m.PAGE_OVERRUN_LIMIT
