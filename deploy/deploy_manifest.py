"""Compare deploy/qiuzhao-deploy-manifest.json with the repo files it names.

``python3 deploy/deploy_manifest.py`` prints every entry with its current sha256; an entry
whose recorded ``sha256`` differs from the file, or whose file is missing, fails (exit 1).
``pending`` entries are only reported (exit 0) unless ``--require-frozen`` is given (use that
right before a deployment); ``--environment`` limits the check to one environment.
windows_excel_delivery.py runs the same check for ``delivery_mac`` before every --apply action.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / 'deploy' / 'qiuzhao-deploy-manifest.json'


def entries(manifest):
    for env, spec in manifest['environments'].items():
        for kind in ('files', 'resources'):
            for entry in spec.get(kind, []):
                yield env, entry


def check(manifest, repo=REPO, require_frozen=False, environments=None):
    rows, failures = [], []
    if environments is not None:
        unknown = set(environments) - set(manifest["environments"])
        failures.extend("unknown environment: " + name for name in sorted(unknown))
    for env, entry in entries(manifest):
        if environments is not None and env not in environments:
            continue
        path = Path(repo) / entry['repo']
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        pending = str(entry.get('status', '')).startswith('pending')
        row = {'environment': env, 'repo': entry['repo'], 'owner': entry.get('owner'), 'actual_sha256': actual,
               'recorded_sha256': entry.get('sha256'), 'status': entry.get('status')}
        if actual is None:
            failures.append(entry['repo'] + ': missing in the repo')
        elif entry.get('sha256') and entry['sha256'] != actual:
            failures.append(entry['repo'] + ': differs from the recorded sha256')
        elif require_frozen and (pending or not entry.get('sha256')):
            failures.append(entry['repo'] + ': not frozen')
        rows.append(row)
    if require_frozen and not rows:
        failures.append("no deploy entries selected")
    return rows, failures


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--manifest', type=Path, default=MANIFEST)
    ap.add_argument('--require-frozen', action='store_true')
    ap.add_argument('--environment', action='append', help='only this environment (repeatable)')
    a = ap.parse_args(argv)
    rows, failures = check(json.loads(a.manifest.read_text(encoding='utf-8')), require_frozen=a.require_frozen,
                           environments=a.environment)
    print(json.dumps({'entries': rows, 'failures': failures}, ensure_ascii=False, indent=1))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
