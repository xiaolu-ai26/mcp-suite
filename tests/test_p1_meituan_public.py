from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            with patch.object(m, '_post_json', side_effect=responses):
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
        self.assertEqual(scope_request['params']['page'].get('pageSize'), 20)
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
