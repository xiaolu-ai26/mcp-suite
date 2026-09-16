import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from qiuzhao.collector import auto_collect as ac


class CollectorStatusTests(unittest.TestCase):
    def invoke(self, behavior):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ac, 'DATA_DIR', Path(tmp)), patch.object(ac, 'log'), patch.object(ac.subprocess, 'run', side_effect=behavior):
            return ac.run_tencent_collector()

    def output(self, state, jobs):
        def run(args, **kwargs):
            out = Path(args[-1])
            (out / 'source_state.json').write_text(json.dumps({'tencent': state}))
            (out / 'jobs.json').write_text(json.dumps(jobs))
            return subprocess.CompletedProcess(args, 0, '', '')
        return run

    def test_verified_zero_is_success(self):
        self.assertEqual(self.invoke(self.output({'status': 'success', 'complete': True, 'errors': [], 'collected_jobs': 0, 'expected_total': 0}, [])), [])

    def test_nonempty_success(self):
        jobs = [{"id": "tencent-1"}]
        self.assertEqual(self.invoke(self.output({"status": "success", "complete": True, "errors": [], "collected_jobs": 1, "expected_total": 1}, jobs)), jobs)

    def test_nonzero_is_failure(self):
        self.assertIsNone(self.invoke(lambda *a, **k: subprocess.CompletedProcess(a, 1, '', 'PermissionError')))

    def test_timeout_is_failure(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired('collector', 600)
        self.assertIsNone(self.invoke(timeout))

    def test_exit_zero_partial_is_failure(self):
        self.assertIsNone(self.invoke(self.output({'status': 'partial', 'complete': False, 'errors': ['API failure'], 'collected_jobs': 0, 'expected_total': 1}, [])))

    def test_missing_fresh_output_is_failure(self):
        self.assertIsNone(self.invoke(lambda *a, **k: subprocess.CompletedProcess(a, 0, '', '')))

    def test_count_mismatch_is_failure(self):
        self.assertIsNone(self.invoke(self.output({'status': 'success', 'complete': True, 'errors': [], 'collected_jobs': 1, 'expected_total': 1}, [])))

    def test_failed_collection_does_not_merge_publish_or_restart(self):
        with patch.object(ac.sys, 'argv', ['auto_collect', '--skip-basic-collectors']), patch.object(ac, 'log'), patch.object(ac, 'backup_jobs'), patch.object(ac, 'run_tencent_collector', return_value=None), patch.object(ac, 'merge_tencent_jobs') as merge, patch.object(ac, 'update_changelog') as changelog, patch.object(ac, 'restart_service') as restart:
            self.assertEqual(ac.main(), 1)
            merge.assert_not_called()
            changelog.assert_not_called()
            restart.assert_not_called()


class TencentMergeTests(unittest.TestCase):
    def merge(self, previous, incoming):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'jobs.json'
            path.write_text(json.dumps(previous))
            before = path.read_bytes()
            with patch.object(ac, 'JOBS_FILE', path), patch.object(ac, 'log'), patch.object(ac, 'normalize_records'):
                added = ac.merge_tencent_jobs(incoming)
            return added, json.loads(path.read_text()), before == path.read_bytes()

    def test_stable_id_updates_changed_url_and_preserves_idless_history(self):
        old = {'id': 'tencent-1', 'detail_url': 'https://x/old', 'job_title': 'Old'}
        history = {'job_title': 'Historical index without ID'}
        added, rows, unchanged = self.merge([old, history], [dict(old, detail_url='https://x/new', job_title='New')])
        self.assertEqual(added, 0)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['job_title'], 'New')
        self.assertEqual(rows[1], history)
        self.assertFalse(unchanged)

    def test_url_alias_survives_later_url_change(self):
        old = {'id': 'tencent-1', 'detail_url': 'https://x/job'}
        incoming = dict(old, id='tencent-2')
        added, rows, _ = self.merge([old], [incoming])
        self.assertEqual(added, 0)
        self.assertEqual(rows[0]['id'], 'tencent-1')
        added, rows, _ = self.merge(rows, [dict(incoming, detail_url='https://x/changed')])
        self.assertEqual(added, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['detail_url'], 'https://x/changed')

    def test_timestamp_only_and_empty_snapshot_leave_bytes_unchanged(self):
        old = {'id': 'tencent-1', 'reviewed_at': 'yesterday', 'evidence_path': 'old'}
        self.assertTrue(self.merge([old], [dict(old, reviewed_at='today', evidence_path='new')])[2])
        self.assertTrue(self.merge([old], [])[2])
        self.assertTrue(self.merge([old], None)[2])

    def test_explicit_closure_is_updated_and_retained_on_unverified_listing(self):
        old = {'id': 'tencent-1', 'status': 'unverified'}
        closed = dict(old, status='expired', source_is_active=False, source_status_raw='closed')
        _, rows, _ = self.merge([old], [closed])
        self.assertEqual(rows[0]['status'], 'expired')
        _, rows, _ = self.merge(rows, [old])
        self.assertEqual(rows[0]['status'], 'expired')

    def test_same_batch_alias_does_not_duplicate(self):
        first = {'id': 'tencent-1', 'detail_url': 'https://x/job'}
        added, rows, _ = self.merge([{'job_title': 'old'}], [first, dict(first, id='tencent-2')])
        self.assertEqual(added, 1)
        self.assertEqual(len(rows), 2)


if __name__ == '__main__':
    unittest.main()
