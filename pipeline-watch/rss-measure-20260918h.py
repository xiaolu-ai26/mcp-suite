#!/usr/bin/env python3
"""Zero-network RSS probe for one/several pipeline unit subprocesses (20260918h).

Creates a throwaway stub adapter in a temp dir (no HTTP, only imports the real
adapter stack) and launches the real ``p1_pipeline --adapter`` subprocess path,
sampling each child's RSS with ``ps -o rss=``. Also measures the interpreter-only
baseline. Prints MB values; no network access.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
STUB = """\
import time
from qiuzhao.collector import p1_platform_moka, p1_platform_beisen, p1_platform_workday
from qiuzhao.collector import p1_sources_01_10


def collect(company, scope, output_dir):
    time.sleep(20)
    return {'jobs': [], 'coverage': {'status': 'blocked', 'complete': False,
            'detail_complete': False, 'expected_total': None, 'collected_jobs': 0,
            'pages_scanned': 0, 'errors': ['rss-probe'], 'checked_at': '2026-09-18T00:00:00+00:00'}}
"""


def rss_mb(pid):
    try:
        out = subprocess.check_output(['ps', '-o', 'rss=', '-p', str(pid)], text=True).strip()
        return int(out) / 1024.0
    except Exception:
        return None


def launch(adapter, tag, index, stub_dir, env):
    out = Path(tempfile.gettempdir()) / f'cn2-rss-{tag}-{index}'
    out.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [PY, '-m', 'qiuzhao.collector.p1_pipeline', '--adapter', adapter,
         '--company', '大疆', '--scope', 'campus', '--output-dir', str(out)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def sample(procs, seconds):
    peaks = {p.pid: 0.0 for p in procs}
    start = time.time()
    while time.time() - start < seconds:
        for p in procs:
            if p.poll() is None:
                value = rss_mb(p.pid)
                if value:
                    peaks[p.pid] = max(peaks[p.pid], value)
        time.sleep(0.4)
    return peaks


def main():
    with tempfile.TemporaryDirectory() as stub_dir:
        Path(stub_dir, 'rss_stub.py').write_text(STUB, encoding='utf-8')
        env = dict(os.environ, PYTHONPATH=stub_dir, PYTHONUTF8='1')
        single = launch('rss_stub', 'one', 1, stub_dir, env)
        single_peak = max(sample([single], 14).values())
        single.terminate(); single.wait()
        print(f'single unit peak RSS:        {single_peak:.1f} MB')

        pair = [launch('rss_stub', 'two', i, stub_dir, env) for i in (1, 2)]
        pair_peaks = sample(pair, 14)
        values = list(pair_peaks.values())
        for p in pair:
            p.terminate()
        for p in pair:
            p.wait()
        print(f'two concurrent unit peaks:   {[round(v, 1) for v in values]} MB')

        base = subprocess.Popen([PY, '-c',
                                 'import time; import qiuzhao.collector.p1_pipeline; time.sleep(6)'],
                                cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        base_peak = max(sample([base], 8).values())
        base.terminate(); base.wait()
        print(f'interpreter+import baseline:  {base_peak:.1f} MB')


if __name__ == '__main__':
    main()
