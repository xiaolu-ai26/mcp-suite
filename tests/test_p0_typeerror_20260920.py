"""P0 2026-09-20: "TypeError: 'NoneType' object is not subscriptable" killed the day.

Chain of events (receipt: pipeline-watch/RECEIPT-p0-typeerror.md):

* p1 ran 06:41:51 -> its own ``--max-run-seconds 18000`` deadline expired 11:41:51;
* the daily chain's p1 step timeout was 18100s, so at 11:43:31 it ran
  ``portable_runtime.stop_tree`` -> ``taskkill`` while p1 was still finalising;
* taskkill answers in the console codepage (GBK) while python runs ``-X utf8``, so the
  strict decode raised inside ``subprocess._readerthread``; CPython's Windows
  ``_communicate`` then returns ``None`` for that stream
  (``stderr = stderr[0] if stderr else None``) and ``result.stderr[-1000:]`` raised;
* the TypeError escaped ``step()``, so ``steps['p1']`` was never written, the outer
  handler rolled the staging file back, ``reset_p1`` deleted p1-status.json and the run
  ended ``partial-or-failed`` -- basic (634 new / 62491 refreshed) and 958 p1 units
  (19619 added / 13310 updated, 95120 -> 114739 rows) never reached publication.

These tests pin every link: undecodable child output, None pipe output, the strict
safety contract that must survive the fix, per-unit failure accounting, and the
deadline-capped run that must still publish what it collected.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from qiuzhao.collector import lark_sync_daemon as D
from qiuzhao.collector import p1_pipeline as P
from qiuzhao.collector import portable_runtime as RT

GBK_CHILD = (
    "import sys, time\n"
    "time.sleep(0.2)\n"
    "sys.stdout.buffer.write('成功: 已终止 PID 12345 的进程。'.encode('gbk'))\n"
    "sys.stderr.buffer.write('错误: 没有找到进程 \"999999\"。'.encode('gbk'))\n"
    "sys.stdout.buffer.flush(); sys.stderr.buffer.flush()\n"
)


def gbk_child(tmp_path):
    script = tmp_path / 'gbk_child.py'
    script.write_text(GBK_CHILD, encoding='utf-8')
    return [sys.executable, str(script)]


def test_child_output_replaces_undecodable_bytes(tmp_path):
    """A GBK adapter/taskkill message must degrade to U+FFFD, not kill the reader."""
    output = RT.child_output(gbk_child(tmp_path))
    assert output['exit_code'] == 0
    assert isinstance(output['stdout'], str) and isinstance(output['stderr'], str)
    assert '\ufffd' in output['stdout'] and '\ufffd' in output['stderr']
    assert 'error' not in output


def test_child_output_never_returns_none_streams(monkeypatch):
    """CPython returns None for a pipe whose reader thread died; '' must replace it."""
    monkeypatch.setattr(RT.subprocess, 'run',
                        lambda *a, **k: subprocess.CompletedProcess(['fake'], 0, None, None))
    output = RT.child_output(['fake'])
    assert output == {'exit_code': 0, 'stdout': '', 'stderr': ''}


def test_child_output_reports_an_unrunnable_command(monkeypatch):
    """A missing/broken diagnostic binary is reported, never raised."""
    output = RT.child_output(['definitely-not-a-real-binary-20260920'])
    assert output['exit_code'] is None
    assert output['stdout'] == '' and output['stderr'] == ''
    assert 'error' in output


def test_stop_tree_windows_branch_survives_gbk_taskkill_output(tmp_path, monkeypatch):
    """The exact fatal line: Windows branch + taskkill that answers in GBK."""
    monkeypatch.setattr(RT, 'WINDOWS', True)
    monkeypatch.setattr(RT, 'taskkill_command', lambda pid: gbk_child(tmp_path))
    child = subprocess.Popen(gbk_child(tmp_path), start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    report = RT.stop_tree(child)  # strict: used by windows_collector.step()
    assert report['tree_termination_confirmed'] is True
    assert report['process_terminated'] is True
    assert '\ufffd' in report['taskkill_stderr']
    assert child.poll() is not None


def test_stop_tree_windows_branch_survives_none_taskkill_output(monkeypatch):
    """Windows semantics when the reader thread died: stdout/stderr both None."""
    class FakeChild:
        pid = 424242

        def __init__(self):
            self.reaped = False

        def poll(self):
            return 0 if self.reaped else None

        def wait(self, timeout=None):
            self.reaped = True
            return 0

        def kill(self):
            self.reaped = True

    monkeypatch.setattr(RT, 'WINDOWS', True)
    monkeypatch.setattr(RT.subprocess, 'run',
                        lambda *a, **k: subprocess.CompletedProcess(['taskkill'], 0, None, None))
    report = RT.stop_tree(FakeChild())
    assert report['tree_termination_confirmed'] is True
    assert report['taskkill_stdout'] == '' and report['taskkill_stderr'] == ''
    assert report['process_terminated'] is True


def test_stop_tree_still_refuses_unconfirmed_tree_termination(monkeypatch):
    """The fix must not weaken the contract: an unconfirmed tree still raises."""
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                             start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    monkeypatch.setattr(RT, 'WINDOWS', True)
    monkeypatch.setattr(RT, 'taskkill_command',
                        lambda pid: [sys.executable, '-c', 'import sys; sys.exit(3)'])
    with pytest.raises(RuntimeError, match='process cleanup incomplete'):
        RT.stop_tree(child)
    assert child.poll() is not None  # only our own test child was killed


class FakeProcess:
    def __init__(self, returncode):
        self.pid = 31337
        self.returncode = returncode

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode


def test_p1_collect_process_records_why_a_partial_checkpoint_was_rejected(tmp_path, monkeypatch):
    """A checkpoint without coverage metadata fails one unit and says why (no raise)."""
    company, scope = '测试公司', 'campus'
    monkeypatch.setitem(P.REGISTRY, company, 'qiuzhao.collector.p1_sources_11_20')
    output = tmp_path / 'unit'

    def fake_popen(command, **kwargs):
        output.mkdir(parents=True, exist_ok=True)
        (output / 'result.json').write_text(
            json.dumps({'jobs': [{'id': 'partial-1'}], 'pending_index': []}), encoding='utf-8')
        return FakeProcess(1)

    monkeypatch.setattr(P.subprocess, 'Popen', fake_popen)
    result = P.collect_process(company, scope, output)
    assert result['coverage']['status'] == 'blocked'
    assert result['jobs'] == []
    reason = result['coverage']['errors'][0]
    assert 'adapter exit=1' in reason
    assert 'partial checkpoint rejected' in reason
    assert 'NoneType' in reason


class _Clock:
    """Deterministic stand-in for p1_pipeline.time (deadline arithmetic only)."""

    def __init__(self, start=1000.0):
        self.value = start

    def monotonic(self):
        return self.value

    def time(self):
        return self.value

    def time_ns(self):
        return int(self.value * 1e9)


def p1_unit(company, scope):
    payload = {'jobs': [dict(source_record_id=f'{company}-{scope}', job_title='软件工程师',
                             description_raw='负责软件开发。', recruitment_unit=company,
                             recruitment_type=P.SCOPES[scope],
                             detail_url=f'https://official.example.com/{company}/{scope}')],
               'coverage': {'status': 'success', 'complete': True, 'detail_complete': True,
                            'expected_total': 1, 'collected_jobs': 1, 'pages_scanned': 1,
                            'errors': [], 'source_url': 'https://official.example.com/jobs',
                            'evidence': ['listing.json'],
                            'scope_evidence': 'official employment type field'}}
    return P.validate_result(payload, company, scope)


def test_p1_deadline_run_exits_2_and_publishes_what_it_collected(tmp_path, monkeypatch):
    """Deadline reached + already-validated units -> exit 2, output kept and published.

    This is the 2026-09-20 shape one layer down: p1 stops starting new units, drains the
    one in flight and still writes its status, gap report and merged rows. Only the
    caller's watchdog stopped that from happening.
    """
    clock = _Clock()
    monkeypatch.setattr(P, 'time', clock)

    def fake_collect(company, scope, output, timeout):
        clock.value += 3.0  # each real unit costs 3s of the 2s budget
        return p1_unit(company, scope)

    monkeypatch.setattr(P, 'collect_process', fake_collect)
    (tmp_path / 'jobs.json').write_text(json.dumps([{'id': 'seed', 'job_title': 't'}],
                                                   ensure_ascii=False), encoding='utf-8')
    code = P.run(tmp_path, tmp_path / 'run', ['A', 'B'], ['campus', 'intern'],
                 apply=True, workers=1, max_run_seconds=2)
    assert code == 2  # partial: not a failure, and never an exception
    status = json.loads((tmp_path / 'run' / 'status.json').read_text(encoding='utf-8'))
    assert status['success'] is False and status['run_finished'] is False
    assert sorted(status['results']) == ['A/campus']
    assert 'A/intern' in status['pending'] and 'B/campus' in status['pending']
    # Finalisation ran to the end: status checkpoint, gap report, merged staging file.
    assert (tmp_path / 'p1-status.json').exists()
    assert 'collection_gap' in status
    published = json.loads((tmp_path / 'jobs.json').read_text(encoding='utf-8'))
    assert len(published) == 2  # the seed row plus the one validated unit that ran
    assert {row['id'] for row in published} >= {'seed'}
    assert [row['source_record_id'] for row in published if row.get('source_record_id')] == ['A-campus']


def test_auto_collect_missing_stderr_still_reports_the_exit_code(tmp_path, monkeypatch):
    """A None stderr must not mask the real adapter failure behind a TypeError."""
    from qiuzhao.collector import auto_collect as A

    logged = []
    monkeypatch.setattr(A, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(A, 'log', lambda message, *a, **k: logged.append(str(message)))
    monkeypatch.setattr(A.subprocess, 'run',
                        lambda *a, **k: subprocess.CompletedProcess(['tencent'], 1, '', None))
    assert A.run_tencent_collector() is None  # None means failure, [] means verified empty
    assert any('exit=1' in message for message in logged), logged


def test_source_hash_rejects_a_missing_hash_line(monkeypatch):
    """lark_sync_daemon: stdout=None becomes a validation error, not an AttributeError."""
    monkeypatch.setattr(D.subprocess, 'run',
                        lambda *a, **k: subprocess.CompletedProcess(['ssh'], 0, None, ''))
    with pytest.raises(ValueError, match='invalid source hash response'):
        D.source_hash()
