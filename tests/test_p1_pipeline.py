import copy
import gzip
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from qiuzhao.collector import p1_pipeline as p
from qiuzhao.v4_fields import graduation_of, convert


def result(ids=('1',), complete=True, scope='campus'):
    jobs = [dict(source_record_id=i, job_title='软件工程师', description_raw='负责软件开发。',
                 recruitment_unit='深圳市大疆创新科技有限公司', recruitment_type=p.SCOPES[scope],
                 detail_url='https://careers.dji.com/jobs/' + i) for i in ids]
    return {'jobs': jobs, 'coverage': {'status': 'success' if complete else 'partial',
            'complete': complete, 'detail_complete': complete, 'expected_total': len(jobs),
            'collected_jobs': len(jobs), 'pages_scanned': 1, 'errors': [],
            'source_url': 'https://careers.dji.com/jobs', 'evidence': ['listing.json'],
            'scope_evidence': 'official employment type field'}}


class P1Tests(unittest.TestCase):
    def validated(self, ids=('1',), complete=True, scope='campus'):
        return p.validate_result(result(ids, complete, scope), '大疆', scope)

    def test_unknown_source_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.dict(p.REGISTRY, {'大疆': 'qiuzhao.collector.module_does_not_exist'}):
                actual = p.collect_process('大疆', 'campus', Path(d))
            self.assertEqual(actual['coverage']['status'], 'blocked')
            self.assertFalse(actual['coverage']['complete'])

    def test_empty_requires_successful_complete_proof(self):
        self.assertTrue(self.validated(())['coverage']['complete'])
        payload = result(())
        payload['coverage']['expected_total'] = None
        with self.assertRaises(ValueError):
            p.validate_result(payload, '大疆', 'campus')

    def test_exhausted_pagination_without_total(self):
        payload = result()
        payload['coverage'].update(expected_total=None, pagination_exhausted=True,
                                   unique_source_ids=1, last_page_evidence='last-page.json')
        self.assertTrue(p.validate_result(payload, '大疆', 'campus')['coverage']['complete'])

    def test_scope_and_detail_contract(self):
        for field in ('description_raw', 'source_record_id', 'recruitment_type'):
            payload = result()
            payload['jobs'][0].pop(field)
            with self.assertRaises(ValueError):
                p.validate_result(payload, '大疆', 'campus')

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            self.validated(('1', '1'))

    def test_partial_retains_missing_and_unrelated_records(self):
        previous, _ = p.merge_records([], [('大疆', 'campus', self.validated(('1', '2')))])
        unrelated = {'id': 'tencent-1', 'job_title': 'old', 'unusual': 'untouched'}
        previous.append(unrelated)
        current, stats = p.merge_records(previous, [('大疆', 'campus', self.validated(('1',), False))])
        self.assertEqual(stats['removed'], 0)
        self.assertEqual(current[-1], unrelated)
        self.assertEqual(len(current), 3)

    def test_complete_removes_only_same_scope(self):
        previous, _ = p.merge_records([], [('大疆', 'campus', self.validated()),
            ('大疆', 'intern', self.validated(scope='intern'))])
        current, stats = p.merge_records(previous, [('大疆', 'campus', self.validated(()))])
        self.assertEqual(stats['removed'], 1)
        self.assertEqual(current[0]['status'], 'removed')
        self.assertNotEqual(current[1]['status'], 'removed')

    def test_same_identity_refresh_and_legacy_id_stable(self):
        initial = self.validated()['jobs'][0]
        initial['id'] = 'legacy-id'
        initial['cohort_raw'] = '2026届'
        current, stats = p.merge_records([initial], [('大疆', 'campus', self.validated())])
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]['id'], 'legacy-id')
        self.assertNotIn('cohort_raw', current[0])
        self.assertEqual(stats['updated'], 1)

    def test_new_cohort_never_uses_stale_url_scope(self):
        row = self.validated()['jobs'][0]
        row.update(source_url='https://campus.163.com/app/detail/index?id=123', published_at='2026-09-12')
        self.assertEqual(graduation_of(row)[0], [])
        row['cohort_raw'] = '2026届、2027届毕业生'
        self.assertEqual(graduation_of(row)[0], ['2027届', '2026届'])
        self.assertEqual(convert(row)[0]['company'], '大疆')
        self.assertEqual(convert(row)[0]['recruiting_unit_raw'], '深圳市大疆创新科技有限公司')

    def test_prewrite_backup_and_untouched_failed_source(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            jobs = root/'jobs.json'
            before = b'[{"id":"other","custom":"keep"}]'
            jobs.write_bytes(before)
            receipt = p.publish(root, [('大疆', 'campus', self.validated())], root)
            with gzip.open(receipt['backup'], 'rb') as stream:
                self.assertEqual(stream.read(), before)
            self.assertEqual(json.loads(jobs.read_text())[0], {'id':'other','custom':'keep'})
            self.assertEqual(receipt['before_sha256'], p.hashlib.sha256(before).hexdigest())

    def test_budget_checkpoint_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); run=root/'run'
            with patch.object(p, 'collect_process') as collect:
                self.assertEqual(p.run(root, run, ['大疆'], ['campus'], max_run_seconds=0), 1)
                collect.assert_not_called()
            status=json.loads((run/'status.json').read_text())
            self.assertFalse(status['run_finished'])
            self.assertEqual(status['pending'], ['大疆/campus'])
            with patch.object(p, 'collect_process', return_value=self.validated()):
                self.assertEqual(p.run(root,run,['大疆'],['campus'],resume=True),0)

    def test_checkpoint_resume_does_not_repeat_completed_scope(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); run=root/'run'
            with patch.object(p,'collect_process',return_value=self.validated()):
                p.run(root,run,['大疆'],['campus'])
            with patch.object(p,'collect_process') as collect:
                p.run(root,run,['大疆'],['campus'],resume=True)
                collect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
