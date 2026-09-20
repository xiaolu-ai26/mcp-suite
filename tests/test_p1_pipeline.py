import copy
import datetime as dt
import errno
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
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

    def test_page_cap_hit_can_never_validate_as_complete(self):
        """An adapter that records its own page cap being reached must not claim complete.

        Defence in depth for the 2026-09-20 pagination audit: whatever an adapter puts in
        ``complete``/``expected_total``, a recorded cap hit is a self-declared truncation.
        """
        payload = result()
        payload['coverage']['page_cap_hit'] = True
        with self.assertRaises(ValueError) as caught:
            p.validate_result(payload, '大疆', 'campus')
        self.assertIn('page safety cap', str(caught.exception))
        # The same payload without the flag still validates, so the guard is the only change.
        payload['coverage'].pop('page_cap_hit')
        self.assertTrue(p.validate_result(payload, '大疆', 'campus')['coverage']['complete'])
        # A partial scan may carry the flag; only the complete claim is refused.
        partial = result(complete=False)
        partial['coverage']['page_cap_hit'] = True
        checked = p.validate_result(partial, '大疆', 'campus')
        self.assertFalse(checked['coverage']['complete'])

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
        previous, _ = p.merge_records([], [('大疆', 'campus', self.validated(('1','2'))),
            ('大疆', 'intern', self.validated(scope='intern'))])
        current, stats = p.merge_records(previous, [('大疆', 'campus', self.validated(('2',)))])
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
            shutil.copyfile(Path(p.__file__).parent / 'portable_runtime.py', collector / 'portable_runtime.py')
            shutil.copyfile(Path(p.__file__).parent / 'p1_pending_index.py', collector / 'p1_pending_index.py')
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
                self.assertEqual(collect.call_args.args[2], first / '01' / 'campus')
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
        previous,_=p.merge_records([], [('大疆','campus',self.validated(('1','2')))])
        saved=copy.deepcopy(previous)
        merged,_=p.merge_records(previous,[('大疆','campus',self.validated(('2',)))])
        self.assertEqual(previous,saved)
        self.assertEqual(merged[0]['status'],'removed')


if __name__ == '__main__':
    unittest.main()


def pending_result(root,reason='source_empty_body',complete=True):
    (root/'listing.json').write_text('{"id":"1","title":"软件工程师"}')
    payload=result((),complete=complete)
    payload['pending_index']=[{'source_record_id':'1','job_title':'软件工程师','detail_url':'https://careers.dji.com/jobs/1',
        'listing_evidence_path':'listing.json','pending_reason':reason,'detail_request_status':'success' if reason=='source_empty_body' else 'failed',
        'source_missing_fields':['responsibilities','requirements'] if reason=='source_empty_body' else [],'last_attempt_at':'2026-09-13T01:00:00+08:00'}]
    payload['coverage'].update(expected_total=1,evidence_files=['listing.json'],
        scope_request={'company':'大疆','scope':'campus','source_url':'https://careers.dji.com/jobs','params':{}})
    return p.validate_result(payload,'大疆','campus',root)


def test_pending_visible_with_empty_body_then_same_id_upgrades(tmp_path):
    from datetime import date
    from qiuzhao.tools import Jobs
    pending=pending_result(tmp_path)
    data=tmp_path/'data';data.mkdir();(data/'jobs.json').write_text('[]')
    p.publish(data,[('大疆','campus',pending)],tmp_path/'publication')
    found=Jobs(data/'jobs.json',today=date(2026,9,13)).search(company='大疆')['jobs']
    assert len(found)==1 and found[0]['index_only'] and found[0]['description_raw']==''
    assert found[0]['pending_reason']=='source_empty_body'
    previous=json.loads((data/'jobs.json').read_text());full=p.validate_result(result(),'大疆','campus')
    merged,changes=p.merge_records(previous,[('大疆','campus',full)])
    assert len(merged)==1 and merged[0]['id']==previous[0]['id'] and merged[0]['description_raw']
    assert not merged[0].get('index_only')


def test_failed_details_retain_prior_prose_and_verification_time(tmp_path):
    full=p.validate_result(result(),'大疆','campus');old=full['jobs'][0];old['reviewed_at']='2026-09-12T01:00:00+08:00'
    pending=pending_result(tmp_path,'fetch_failed',False)
    merged,_=p.merge_records([old],[('大疆','campus',pending)])
    assert merged[0]['description_raw']==old['description_raw']
    assert merged[0]['reviewed_at']==old['reviewed_at']
    assert merged[0]['last_attempt_at']=='2026-09-13T01:00:00+08:00'
    assert merged[0]['pending_reason']=='fetch_failed' and not merged[0].get('index_only')
    import pytest
    with pytest.raises(ValueError,match='failed detail'):
        pending_result(tmp_path,'fetch_failed',True)


def test_pending_inactive_keeps_full_proof_and_adopts_legacy_identity(tmp_path):
    from qiuzhao.collector.lark_sync_enrichment import source_lifecycle_state
    full=p.validate_result(result(),'大疆','campus');old=full['jobs'][0]
    for key in ('p1_identity','p1_company','p1_scope'):old.pop(key)
    old.update(id='legacy-real-id',source_is_active=True,source_status_raw='open',source_list_status_raw='open',source_status_evidence={'list_status':'open'})
    pending=pending_result(tmp_path)
    pending['pending_index'][0].update(status='expired',source_is_active=False,source_status_raw='pause',
        source_list_status_raw='pause',source_detail_status_raw=None,source_status_evidence={'list_status':'pause','detail_status':None})
    merged,_=p.merge_records([old],[('大疆','campus',pending)])
    assert len(merged)==1 and merged[0]['id']=='legacy-real-id'
    assert merged[0]['p1_company']=='大疆' and merged[0]['p1_scope']=='campus' and merged[0]['p1_identity']
    assert merged[0]['description_raw']==old['description_raw']
    assert source_lifecycle_state(merged[0])=='expired'


def test_pending_unknown_availability_stays_visible_but_explicit_pause_does_not(tmp_path):
    from datetime import date
    from qiuzhao.tools import Jobs
    pending=pending_result(tmp_path)
    row=pending['pending_index'][0];row.update(source_is_active=False,source_status_raw='unrecognized')
    data=tmp_path/'jobs.json';data.write_text(json.dumps([row]))
    assert Jobs(data,today=date(2026,9,13)).search()['total']==1
    row.update(status='expired',source_status_raw='pause')
    data.write_text(json.dumps([row]))
    assert Jobs(data,today=date(2026,9,13)).search()['total']==0


def validated_for(company, scope, complete=True):
    """A validated complete/partial result for any company/scope, no I/O."""
    return p.validate_result(result(('1',), complete, scope), company, scope)


class P1ConcurrencyTests(unittest.TestCase):
    def test_concurrent_run_is_bounded_by_longest_unit(self):
        companies = ['大疆', '拼多多', '小米', '京东']
        delay = 0.25

        def fake(company, scope, output, timeout):
            time.sleep(delay)
            return validated_for(company, scope)

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.object(p, 'collect_process', side_effect=fake):
                started = time.monotonic()
                self.assertEqual(p.run(root, root / 'run', companies, ['campus'], workers=4), 0)
                elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, delay)
        # Four serial units would need 4x delay; four workers finish near one delay.
        self.assertLess(elapsed, delay * len(companies) * 0.75)

    def test_same_company_scopes_serialize_while_companies_overlap(self):
        lock = threading.Lock()
        per_company, global_active = {}, {'value': 0}
        observed = {'same': 0, 'global': 0}

        def fake(company, scope, output, timeout):
            with lock:
                per_company[company] = per_company.get(company, 0) + 1
                observed['same'] = max(observed['same'], per_company[company])
                global_active['value'] += 1
                observed['global'] = max(observed['global'], global_active['value'])
            time.sleep(0.3)
            with lock:
                per_company[company] -= 1
                global_active['value'] -= 1
            return validated_for(company, scope)

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.object(p, 'collect_process', side_effect=fake):
                self.assertEqual(p.run(root, root / 'run', ['大疆', '拼多多'],
                                       ['campus', 'intern'], workers=4), 0)
        self.assertEqual(observed['same'], 1, 'same company scopes must never overlap')
        self.assertGreaterEqual(observed['global'], 2, 'different companies should overlap')

    def test_concurrent_checkpoints_keep_one_entry_per_unit(self):
        companies, scopes = ['大疆', '拼多多', '小米'], ['campus', 'intern']

        def fake(company, scope, output, timeout):
            time.sleep(0.05)
            return validated_for(company, scope)

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run = root / 'run'
            with patch.object(p, 'collect_process', side_effect=fake):
                self.assertEqual(p.run(root, run, companies, scopes, workers=3), 0)
            expected = {f'{c}/{s}' for c in companies for s in scopes}
            status = json.loads((run / 'status.json').read_text(encoding='utf-8'))
            checkpoint = json.loads(p.checkpoint_path(root, companies, scopes).read_text(encoding='utf-8'))
            self.assertEqual(set(status['results']), expected)
            self.assertEqual(set(checkpoint['results']), expected)
            self.assertTrue(status['run_finished'])
            for key, entry in status['results'].items():
                self.assertTrue(Path(entry['result_path']).is_file(), key)

    def test_failed_unit_enters_retry_queue_and_runs_first_next_time(self):
        def first_run(company, scope, output, timeout):
            if company == '大疆':
                return p.blocked('SSLError: certificate verify failed')
            return validated_for(company, scope)

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.object(p, 'collect_process', side_effect=first_run):
                self.assertEqual(p.run(root, root / 'run1', ['大疆', '拼多多'], ['campus'], workers=1), 2)
            entries = json.loads(p.retry_queue_path(root).read_text(encoding='utf-8'))['entries']
            entry = entries['大疆/campus']
            self.assertEqual(entry['reason'], 'ssl')
            self.assertEqual(entry['count'], 1)
            self.assertEqual(entry['consecutive_days'], 1)
            self.assertNotIn('拼多多/campus', entries)

            order = []

            def second_run(company, scope, output, timeout):
                order.append((company, scope))
                return validated_for(company, scope)

            with patch.object(p, 'collect_process', side_effect=second_run):
                # 拼多多 is listed first, but the queued 大疆/campus unit must lead.
                self.assertEqual(p.run(root, root / 'run2', ['拼多多', '大疆'], ['campus'], workers=1), 0)
            self.assertEqual(order[0], ('大疆', 'campus'))
            self.assertNotIn('大疆/campus',
                             json.loads(p.retry_queue_path(root).read_text(encoding='utf-8'))['entries'])

    def test_three_day_failure_is_demoted_to_last(self):
        yesterday = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p.atomic_json(p.retry_queue_path(root), {'entries': {'大疆/campus': {
                'company': '大疆', 'scope': 'campus', 'reason': 'timeout', 'count': 3,
                'consecutive_days': 3, 'last_failed_date': yesterday}}})
            order = []

            def fake(company, scope, output, timeout):
                order.append((company, scope))
                if company == '大疆':
                    return p.blocked('adapter exit=timeout')
                return validated_for(company, scope)

            with patch.object(p, 'collect_process', side_effect=fake):
                p.run(root, root / 'run', ['大疆', '拼多多'], ['campus'], workers=1)
            self.assertEqual(order[-1], ('大疆', 'campus'))
            status = json.loads((root / 'run' / 'status.json').read_text(encoding='utf-8'))
            self.assertIn('大疆/campus', status['retry']['demoted'])
            entries = json.loads(p.retry_queue_path(root).read_text(encoding='utf-8'))['entries']
            self.assertEqual(entries['大疆/campus']['consecutive_days'], 4)

    def test_resume_latest_reuses_concurrent_checkpoint_without_repeating(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run = root / 'run'

            def interrupted(company, scope, output, timeout):
                # 拼多多 finishes first and checkpoints; 大疆 interrupts the run.
                time.sleep(0.4 if company == '大疆' else 0.1)
                if company == '大疆':
                    raise KeyboardInterrupt
                return validated_for(company, scope)

            with patch.object(p, 'collect_process', side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    p.run(root, run, ['大疆', '拼多多'], ['campus'], workers=2)
            mid = json.loads((run / 'status.json').read_text(encoding='utf-8'))
            self.assertFalse(mid['run_finished'])
            self.assertEqual(set(mid['results']), {'拼多多/campus'})

            with patch.object(p, 'collect_process',
                              side_effect=lambda company, scope, output, timeout: validated_for(company, scope)) as collect:
                with patch('sys.argv', ['p1', '--data-dir', str(root), '--companies', '大疆,拼多多',
                                       '--scopes', 'campus', '--resume-latest', '--workers', '2']):
                    self.assertEqual(p.main(), 0)
            self.assertEqual(collect.call_count, 1)
            self.assertEqual(collect.call_args.args[0], '大疆')
            self.assertTrue(json.loads((run / 'status.json').read_text(encoding='utf-8'))['run_finished'])

    def test_resume_latest_resumes_unfinished_concurrent_run(self):
        companies = ['大疆', '拼多多', '小米']
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run = root / 'run'
            # Nothing runs, but the checkpoint is written for a concurrent configuration.
            self.assertEqual(p.run(root, run, companies, ['campus'], max_run_seconds=0, workers=3), 1)
            calls = []

            def fake(company, scope, output, timeout):
                calls.append((company, scope))
                return validated_for(company, scope)

            with patch.object(p, 'collect_process', side_effect=fake):
                with patch('sys.argv', ['p1', '--data-dir', str(root), '--companies', ','.join(companies),
                                       '--scopes', 'campus', '--resume-latest', '--workers', '3']):
                    self.assertEqual(p.main(), 0)
            self.assertEqual(sorted(calls), sorted((c, 'campus') for c in companies))

    def test_retry_reason_classification(self):
        queue = {}
        p.record_retry_failure(queue, '大疆', 'campus',
                               {'status': 'blocked', 'errors': ['adapter exit=timeout'],
                                'timeout_cleanup': {'pid': 1}})
        p.record_retry_failure(queue, '大疆', 'intern',
                               {'status': 'blocked', 'errors': ['SSLError: bad handshake']})
        p.record_retry_failure(queue, '大疆', 'social',
                               {'status': 'blocked', 'errors': ['adapter result missing']})
        self.assertEqual(queue['大疆/campus']['reason'], 'timeout')
        self.assertEqual(queue['大疆/intern']['reason'], 'ssl')
        self.assertEqual(queue['大疆/social']['reason'], 'blocked')

    def test_scope_timeout_flag_precedence_and_workers_passed(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(p, 'run', return_value=0) as run_mock:
                with patch('sys.argv', ['p1', '--data-dir', d, '--companies', '大疆', '--scopes', 'campus',
                                       '--timeout', '1200', '--scope-timeout', '600', '--workers', '2']):
                    p.main()
            self.assertEqual(run_mock.call_args.args[4], 600)
            self.assertEqual(run_mock.call_args.args[8], 2)
            with patch.object(p, 'run', return_value=0) as legacy:
                # The elf chain still passes --timeout 1200 without --scope-timeout.
                with patch('sys.argv', ['p1', '--data-dir', d, '--companies', '大疆', '--scopes', 'campus',
                                       '--timeout', '1200']):
                    p.main()
            self.assertEqual(legacy.call_args.args[4], 1200)
            self.assertEqual(legacy.call_args.args[8], 4)

    def test_concurrent_apply_publishes_every_unit_and_keeps_publish_lock(self):
        companies = ['大疆', '拼多多', '小米']

        def fake(company, scope, output, timeout):
            time.sleep(0.05)
            return validated_for(company, scope)

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'jobs.json').write_text('[]', encoding='utf-8')
            with patch.object(p, 'collect_process', side_effect=fake):
                self.assertEqual(p.run(root, root / 'run', companies, ['campus'],
                                       apply=True, workers=3), 0)
            rows = json.loads((root / 'jobs.json').read_text(encoding='utf-8'))
            self.assertEqual({row['p1_company'] for row in rows}, set(companies))
            status = json.loads((root / 'run' / 'status.json').read_text(encoding='utf-8'))
            self.assertEqual(len(status['publications']), len(companies))
            self.assertTrue(all(entry['published'] for entry in status['results'].values()))
            backup = Path(status['publications'][0]['backup'])
            self.assertTrue(backup.is_file())


class _WindowsStyleFcntl:
    """Fake portable ``fcntl`` that reproduces ``msvcrt.locking`` re-entrancy.

    On Windows ``portable_runtime.flock`` calls ``msvcrt.locking``; locking a
    region the same process already holds raises
    ``OSError [Errno 36] Resource deadlock avoided`` instead of blocking like
    POSIX ``flock``. This fake keys the held region by file path and raises the
    same error, so a missing in-process lock is observable on macOS. An explicit
    ``LOCK_UN`` (which the real code now performs) releases the region.
    """

    LOCK_EX = 2
    LOCK_NB = 4
    LOCK_UN = 8

    def __init__(self, hold_seconds=0.02):
        self._held = set()
        self._guard = threading.Lock()
        self._hold_seconds = hold_seconds
        self.active = 0
        self.max_active = 0
        self.lock_calls = 0

    def flock(self, handle, flags):
        name = os.fspath(getattr(handle, 'name', handle))
        with self._guard:
            if flags & self.LOCK_UN:
                if name in self._held:
                    self._held.discard(name)
                    self.active -= 1
                return
            if name in self._held:
                raise OSError(errno.EDEADLK, 'Resource deadlock avoided')
            self._held.add(name)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.lock_calls += 1
        # Widen the hold window outside the guard so overlapping publishers would
        # reliably collide if the in-process lock were removed.
        if self._hold_seconds:
            time.sleep(self._hold_seconds)


class P1WindowsPublishLockTests(unittest.TestCase):
    def test_fake_lock_reproduces_windows_same_process_reentry(self):
        fake = _WindowsStyleFcntl(hold_seconds=0)
        with tempfile.TemporaryDirectory() as d:
            lock = Path(d) / 'p1-publish.lock'
            with lock.open('a') as first, lock.open('a') as second:
                fake.flock(first, fake.LOCK_EX)
                with self.assertRaises(OSError) as raised:
                    fake.flock(second, fake.LOCK_EX)
                self.assertEqual(raised.exception.errno, errno.EDEADLK)
                # Releasing the first holder lets the second acquire: the fake is
                # only simulating same-process re-entry, not permanent failure.
                fake.flock(first, fake.LOCK_UN)
                fake.flock(second, fake.LOCK_EX)
                fake.flock(second, fake.LOCK_UN)

    def test_eight_threads_publish_all_succeed_and_serialize(self):
        companies = ['大疆', '拼多多', '小米', '京东', '华为', '快手', 'OPPO', 'vivo']
        fake = _WindowsStyleFcntl()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'jobs.json').write_text('[]', encoding='utf-8')
            errors = []

            def worker(company):
                try:
                    p.publish(root, [(company, 'campus', validated_for(company, 'campus'))],
                              root / 'publication')
                except Exception as error:  # noqa: BLE001 - report, do not hide
                    errors.append(f'{company}: {type(error).__name__}: {error}')

            with patch.object(p, 'fcntl', fake):
                with ThreadPoolExecutor(max_workers=8) as executor:
                    list(executor.map(worker, companies))
            self.assertEqual(errors, [], 'no publisher may hit the msvcrt re-entry error')
            self.assertEqual(fake.max_active, 1, 'publishers must be serialized in-process')
            self.assertEqual(fake.lock_calls, len(companies))
            rows = json.loads((root / 'jobs.json').read_text(encoding='utf-8'))
            self.assertEqual({row['p1_company'] for row in rows}, set(companies))

    def test_concurrent_run_with_windows_style_lock_publishes_every_unit(self):
        companies = ['大疆', '拼多多', '小米', '京东', '华为', '快手', 'OPPO', 'vivo']
        fake = _WindowsStyleFcntl()

        def fake_collect(company, scope, output, timeout):
            return validated_for(company, scope)

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'jobs.json').write_text('[]', encoding='utf-8')
            with patch.object(p, 'collect_process', side_effect=fake_collect), \
                    patch.object(p, 'fcntl', fake):
                self.assertEqual(p.run(root, root / 'run', companies, ['campus'],
                                       apply=True, workers=8), 0)
            self.assertEqual(fake.max_active, 1)
            status = json.loads((root / 'run' / 'status.json').read_text(encoding='utf-8'))
            self.assertEqual(len(status['publications']), len(companies))
            self.assertTrue(all(entry['published'] for entry in status['results'].values()))
            rows = json.loads((root / 'jobs.json').read_text(encoding='utf-8'))
            self.assertEqual({row['p1_company'] for row in rows}, set(companies))

    def test_single_publish_failure_keeps_other_units_and_returns_partial(self):
        companies = ['大疆', '拼多多', '小米', '京东']
        real_publish = p.publish

        def flaky(data_dir, results, run_dir):
            if results[0][0] == '小米':
                raise OSError(errno.EDEADLK, 'Resource deadlock avoided')
            return real_publish(data_dir, results, run_dir)

        def fake_collect(company, scope, output, timeout):
            return validated_for(company, scope)

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'jobs.json').write_text('[]', encoding='utf-8')
            with patch.object(p, 'collect_process', side_effect=fake_collect), \
                    patch.object(p, 'publish', side_effect=flaky):
                self.assertEqual(p.run(root, root / 'run', companies, ['campus'],
                                       apply=True, workers=2), 2)
            status = json.loads((root / 'run' / 'status.json').read_text(encoding='utf-8'))
            failed = status['results']['小米/campus']
            self.assertIn('publish_error', failed)
            self.assertIn('deadlock avoided', failed['publish_error'])
            self.assertFalse(failed['published'])
            for company in ('大疆', '拼多多', '京东'):
                self.assertTrue(status['results'][f'{company}/campus']['published'], company)
            self.assertEqual(len(status['publications']), 3)
            self.assertEqual([row['p1_company'] for row in
                              json.loads((root / 'jobs.json').read_text(encoding='utf-8'))].count('小米'), 0)
            entries = json.loads(p.retry_queue_path(root).read_text(encoding='utf-8'))['entries']
            self.assertEqual(entries['小米/campus']['reason'], 'publish')

    def test_all_publish_failures_return_fatal_without_aborting(self):
        companies = ['大疆', '拼多多']

        def boom(data_dir, results, run_dir):
            raise OSError(errno.EDEADLK, 'Resource deadlock avoided')

        def fake_collect(company, scope, output, timeout):
            return validated_for(company, scope)

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'jobs.json').write_text('[]', encoding='utf-8')
            with patch.object(p, 'collect_process', side_effect=fake_collect), \
                    patch.object(p, 'publish', side_effect=boom):
                self.assertEqual(p.run(root, root / 'run', companies, ['campus'],
                                       apply=True, workers=2), 1)
            status = json.loads((root / 'run' / 'status.json').read_text(encoding='utf-8'))
            self.assertEqual(set(status['results']),
                             {f'{company}/campus' for company in companies})
            self.assertTrue(all(entry.get('publish_error') for entry in status['results'].values()))
            self.assertFalse(p.any_validated(status))

    def test_publish_still_waits_for_another_process_file_lock(self):
        """The in-process lock must not replace cross-process mutual exclusion."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'jobs.json').write_text('[]', encoding='utf-8')
            lock_path = root / 'p1-publish.lock'
            child_code = (
                "import fcntl, sys, time\n"
                "handle = open(sys.argv[1], 'a')\n"
                "fcntl.flock(handle, fcntl.LOCK_EX)\n"
                "print('locked', flush=True)\n"
                "time.sleep(2.5)\n"
                "fcntl.flock(handle, fcntl.LOCK_UN)\n"
            )
            child = subprocess.Popen([sys.executable, '-c', child_code, str(lock_path)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            outcome = {}

            def do_publish():
                outcome['receipt'] = p.publish(
                    root, [('大疆', 'campus', validated_for('大疆', 'campus'))], root / 'publication')

            thread = None
            try:
                self.assertEqual(child.stdout.readline().strip(), 'locked')
                thread = threading.Thread(target=do_publish)
                thread.start()
                thread.join(timeout=0.6)
                self.assertTrue(thread.is_alive(),
                                'publish must block while another process holds the lock')
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
                self.assertEqual(outcome['receipt']['after_sha256'], p.sha(root / 'jobs.json'))
            finally:
                if thread is not None and thread.is_alive():
                    thread.join(timeout=10)
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:  # pragma: no cover - safety only
                    child.kill()
                    child.wait(timeout=5)

