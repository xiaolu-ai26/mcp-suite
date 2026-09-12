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


if __name__ == '__main__':
    unittest.main()
