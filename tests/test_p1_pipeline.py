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

    def test_empty_complete_requires_scope_evidence(self):
        payload = result(())
        payload['coverage'].pop('scope_evidence')
        with self.assertRaisesRegex(ValueError, 'scope evidence'):
            p.validate_result(payload, '大疆', 'campus')

    def test_complete_requires_real_bound_evidence_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / '01' / 'campus'
            root.mkdir(parents=True)
            payload = result(())
            payload['coverage'].update(
                evidence_files=['response.json'],
                scope_request={'company': '大疆', 'scope': 'campus',
                               'source_url': 'https://careers.dji.com/jobs', 'params': {'type': 'campus'}})
            with self.assertRaises(ValueError):
                p.validate_result(payload, '大疆', 'campus', root)
            (root / 'response.json').write_text('{"total":0}')
            p.validate_result(payload, '大疆', 'campus', root)
            payload['coverage']['scope_request']['scope'] = 'social'
            with self.assertRaises(ValueError):
                p.validate_result(payload, '大疆', 'campus', root)
            payload['coverage']['scope_request']['scope'] = 'campus'
            outside = Path(d) / 'another-company.json'
            outside.write_text('{}')
            payload['coverage']['evidence_files'] = [str(outside)]
            with self.assertRaises(ValueError):
                p.validate_result(payload, '大疆', 'campus', root)
            shared = root.parent / 'shared'
            shared.mkdir()
            (shared / 'list.json').write_text('{}')
            payload['coverage']['evidence_files'] = ['../shared/list.json']
            p.validate_result(payload, '大疆', 'campus', root)

    def test_shared_url_never_collapses_distinct_source_ids(self):
        payload = result(('one', 'two'))
        for row in payload['jobs']:
            row['detail_url'] = 'https://careers.dji.com/jobs/shared'
        validated = p.validate_result(payload, '大疆', 'campus')
        old = {'id': 'legacy', 'detail_url': payload['jobs'][0]['detail_url'],
               'recruitment_type': '校园招聘'}
        rows, _ = p.merge_records([old], [('大疆', 'campus', validated)])
        self.assertEqual({r.get('source_record_id') for r in rows if r.get('p1_company')}, {'one', 'two'})
        again, _ = p.merge_records(rows, [('大疆', 'campus', validated)])
        self.assertEqual(len(again), len(rows))

    def test_corrupted_existing_backup_blocks_next_publish(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'jobs.json').write_text('[]')
            receipt = p.publish(root, [('大疆', 'campus', self.validated())], root / 'batch')
            before = (root / 'jobs.json').read_bytes()
            with gzip.open(receipt['backup'], 'wb') as stream:
                stream.write(b'changed')
            with self.assertRaisesRegex(RuntimeError, 'backup hash mismatch'):
                p.publish(root, [('大疆', 'campus', self.validated(('2',)))], root / 'batch')
            self.assertEqual((root / 'jobs.json').read_bytes(), before)

    def test_interrupt_checkpoint_is_discoverable_and_cli_resumes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run = root / 'run'
            with patch.object(p, 'collect_process', side_effect=[self.validated(), KeyboardInterrupt]):
                with self.assertRaises(KeyboardInterrupt):
                    p.run(root, run, ['大疆'], ['campus', 'intern'])
            checkpoint = json.loads((root / 'p1-status.json').read_text())
            self.assertFalse(checkpoint['run_finished'])
            self.assertIn('大疆/campus', checkpoint['results'])
            with patch.object(p, 'collect_process', return_value=self.validated(scope='intern')) as collect:
                with patch('sys.argv', ['p1', '--data-dir', str(root), '--companies', '大疆',
                                        '--scopes', 'campus,intern', '--resume-latest']):
                    self.assertEqual(p.main(), 0)
                self.assertEqual(collect.call_count, 1)
                self.assertEqual(collect.call_args.args[1], 'intern')
            self.assertTrue(json.loads((root / 'p1-status.json').read_text())['run_finished'])

    def test_real_module_cli_dispatches_adapter(self):
        import sys
        import shutil
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            package = root / 'qiuzhao'; collector = package / 'collector'
            collector.mkdir(parents=True)
            (package / '__init__.py').write_text('')
            (collector / '__init__.py').write_text('')
            (package / 'normalize.py').write_text('def normalize_records(rows): return {}\n')
            shutil.copyfile(p.__file__, collector / 'p1_pipeline.py')
            shutil.copyfile(Path(p.__file__).parents[1] / 'v4_fields.py', package / 'v4_fields.py')
            fixture = p.blocked('offline fixture adapter dispatched')
            (collector / 'p1_sources_01_10.py').write_text(
                'def collect(company, scope, output_dir): return ' + repr(fixture) + '\n')
            proc = subprocess.run([sys.executable, '-m', 'qiuzhao.collector.p1_pipeline',
                '--data-dir', str(root / 'data'), '--run-dir', str(root / 'run'),
                '--companies', '拼多多', '--scopes', 'social'],
                cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 1)
            status = json.loads((root / 'data' / 'p1-status.json').read_text())
            errors = status['results']['拼多多/social']['coverage']['errors']
            self.assertIn('offline fixture adapter dispatched', errors)

    def test_legacy_uuid_adoption_requires_unique_same_company_and_scope(self):
        ident = '093114fd-38fa-497b-ac5a-8a8f47777708'
        incoming = self.validated((ident,))
        legacy = {'id': 'legacy', 'source_record_id': ident, 'recruitment_unit': '大疆',
                  'recruitment_type': '校园招聘', 'source_url': 'https://app.mokahr.com/jobs/' + ident}
        rows, _ = p.merge_records([legacy], [('大疆', 'campus', incoming)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], 'legacy')
        for mutation in ({'recruitment_unit': '另一家公司'}, {'recruitment_type': '社会招聘'}):
            old = dict(legacy, **mutation)
            rows, _ = p.merge_records([old], [('大疆', 'campus', incoming)])
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0], old)
        rows, _ = p.merge_records([legacy, dict(legacy, id='ambiguous')], [('大疆', 'campus', incoming)])
        self.assertEqual(len(rows), 3)

    def test_subset_run_does_not_replace_another_selection_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first = root / 'first'; second = root / 'second'
            p.run(root, first, ['大疆'], ['campus'], max_run_seconds=0)
            p.run(root, second, ['拼多多'], ['social'], max_run_seconds=0)
            self.assertEqual(json.loads((root / 'p1-status.json').read_text())['run_dir'], str(second))
            with patch.object(p, 'collect_process', return_value=self.validated()) as collect:
                with patch('sys.argv', ['p1', '--data-dir', str(root), '--companies', '大疆',
                                       '--scopes', 'campus', '--resume-latest']):
                    self.assertEqual(p.main(), 0)
                self.assertEqual(collect.call_args.args[2], first / '02' / 'campus')
            self.assertFalse(json.loads((second / 'status.json').read_text())['run_finished'])
            self.assertTrue(json.loads((first / 'status.json').read_text())['run_finished'])

    def test_legacy_latest_different_selection_is_not_resumed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p.run(root, root / 'subset', ['拼多多'], ['social'], max_run_seconds=0)
            with patch.object(p, 'collect_process', return_value=self.validated()):
                with patch('sys.argv', ['p1', '--data-dir', str(root), '--companies', '大疆',
                                       '--scopes', 'campus', '--resume-latest']):
                    self.assertEqual(p.main(), 0)
            self.assertFalse(json.loads((root / 'subset' / 'status.json').read_text())['run_finished'])

    def test_timeout_publishes_only_validated_partial_checkpoint(self):
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            process=MagicMock(pid=1234)
            process.wait.side_effect=[subprocess.TimeoutExpired('adapter',1),0]
            def start(*args,**kwargs):
                p.atomic_json(root/'result.json',result())
                return process
            with patch.object(p.subprocess,'Popen',side_effect=start), patch.object(p.os,'killpg'):
                collected=p.collect_process('大疆','campus',root,timeout=1)
            self.assertEqual(len(collected['jobs']),1)
            self.assertEqual(collected['coverage']['status'],'partial')
            self.assertFalse(collected['coverage']['complete'])
            self.assertTrue(collected['coverage']['errors'])

    def test_timeout_does_not_reuse_preexisting_result(self):
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p.atomic_json(root/'result.json',result())
            process=MagicMock(pid=1234)
            process.wait.side_effect=[subprocess.TimeoutExpired('adapter',1),0]
            with patch.object(p.subprocess,'Popen',return_value=process), patch.object(p.os,'killpg'):
                collected=p.collect_process('大疆','campus',root,timeout=1)
            self.assertEqual(collected['coverage']['status'],'blocked')
            self.assertEqual(collected['jobs'],[])

    def test_merge_retains_input_immutability_when_removing(self):
        previous,_=p.merge_records([], [('大疆','campus',self.validated())])
        saved=copy.deepcopy(previous)
        merged,_=p.merge_records(previous,[('大疆','campus',self.validated(()))])
        self.assertEqual(previous,saved)
        self.assertEqual(merged[0]['status'],'removed')


if __name__ == '__main__':
    unittest.main()
