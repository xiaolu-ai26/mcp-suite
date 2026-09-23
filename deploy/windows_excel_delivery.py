"""Feishu delivery of one server-accepted jobs.json version by Excel import (plan 4.2).

This is not a new import system. The steps are the 2026-09-23 R1 scripts in
``mcp-suite-recovery-20260921/feishu-20260923/scripts`` (projection -> xlsx -> schema
snapshot -> ``drive +import`` into temporary tables of the one fixed Base -> schema fix /
clean-blank / verify -> gated switch), loaded unmodified. What this module adds is only
what a daily run needs around them:

* the source is a version the server accepted: the collector's accepted-version
  manifest (``data/accepted-versions/*.json``) or a run receipt's working baseline,
  re-hashed here; the projection is fixed to that hash;
* versions only move forward: the manifests carry the child->parent lineage of accepted
  versions, and a version that cannot be shown to descend from the last delivered one
  is refused -- a different hash is not a newer one;
* one state file per source version records every stage, so an interruption resumes at
  the recorded stage and the scripts' own state files (``import-state.json`` with its
  tickets, ``switch-state.json``) keep them idempotent; a version already delivered is
  not imported again and only one version is in progress at a time;
* a failure stops here. The server is never touched, tables created for the failed
  version are listed for cleanup -- not deleted -- and a version whose switch has
  started can only be finished, never abandoned.

The batch-specific constants of the R1 scripts come from a policy approved once
(``draft-policy`` proposes it from the last switch receipt) plus the ledger: the tables
the previous delivery made official become the outgoing ones. Archive naming and the
protected tables are only ever taken from that policy. External stages also require
``--apply``; a fetch of the frozen snapshot runs only when a fetch command is
configured. The old row-level ``lark_sync_daemon`` is not used anywhere.

Configuration the Mac side needs (nothing here is guessed; the defaults perform no
remote action): ``--root`` (delivery state), ``--policy`` (approved policy JSON, whose
``bootstrap`` binds the version the Base already shows -- see ``verify_bootstrap``),
``--manifest`` (a copy of the collector's accepted-version manifest), and either the
artifact at the manifest's path, ``--artifact-root`` (a mount of the collector root) or
``--fetch-command`` (e.g. ``["scp", "collector:{remote}", "{local}"]``).
"""
import argparse
import ast
import datetime as dt
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qiuzhao.collector.p1_pipeline import atomic_json
from qiuzhao.collector.portable_runtime import fcntl

BASE_TOKEN = 'KaJIbYuIPacWersWD4jcO1AjnGh'  # the one Base total link; never another
DEFAULT_SCRIPTS = Path('/Users/maxzhl/Projects/mcp-suite-recovery-20260921/feishu-20260923/scripts')
SCRIPT = {'projection': 'sprite_build_projection_r1.py', 'xlsx': 'build_xlsx_r1.py',
          'schema_snapshot': 'build_prod_schema_snapshot.py', 'import': 'run_step2_import_r1.py',
          'schema_fix': 'run_step3_schema_verify_r1.py', 'clean_blank': 'run_step3_schema_verify_r1.py',
          'verify': 'run_step3_schema_verify_r1.py', 'switch': 'run_step4_switch_r1.py'}
SCRIPT_ARGS = {'schema_fix': ['--phase', 'fix'], 'clean_blank': ['--phase', 'clean-blank'],
               'verify': ['--phase', 'verify'], 'switch': ['--apply']}
LOCAL_STAGES = ('projection', 'xlsx', 'samples')
EXTERNAL_STAGES = ('schema_snapshot', 'import', 'schema_fix', 'clean_blank', 'verify', 'switch')
STAGES = LOCAL_STAGES + EXTERNAL_STAGES
SAMPLE_COUNT = 24  # run_step3 verify gate: semantic_sample_total == 24
SAMPLE_RULE = 'sha256-rank-round-robin-v1'
EXCEL_CELL_LIMIT = 32767
LINEAGE_WALK_LIMIT = 10000
GENERIC_WHITELIST = '__generic_excel_text_whitelist__'


class DeliveryError(RuntimeError):
    pass


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def now():
    return dt.datetime.now().astimezone().isoformat()


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


# --- source ------------------------------------------------------------------------

def verified_source(path, sha, *, origin, lineage=None):
    path = Path(path)
    if not path.is_file() or digest(path) != sha:
        raise DeliveryError('server-accepted snapshot missing or hash mismatch: ' + str(path))
    return {'path': str(path), 'sha256': sha, 'origin': origin, 'bytes': path.stat().st_size,
            'lineage': dict(lineage or {})}


def source_from_run_receipt(receipt_path):
    """The version a collector run's receiver accepted, re-hashed; never staging bytes."""
    state = load_json(receipt_path)
    if not isinstance(state, dict):
        raise DeliveryError('run receipt unreadable: ' + str(receipt_path))
    working = state.get('working_baseline') or {}
    path, sha = working.get('path'), working.get('sha256')
    if not path or not sha:
        raise DeliveryError('run receipt has no server-accepted publication (working_baseline)')
    lineage = {}
    for record in state.get('accepted_publications') or []:
        for child, parent in record.get('lineage_edges') or []:
            if child and parent:
                lineage[child] = parent
    return verified_source(path, sha, origin=str(receipt_path), lineage=lineage)


def fetch(remote, local, command):
    """Copy one file with the configured command; the caller verifies what arrived."""
    local = Path(local)
    local.parent.mkdir(parents=True, exist_ok=True)
    partial = local.with_suffix(local.suffix + '.partial')
    partial.unlink(missing_ok=True)
    argv = [part.format(remote=remote, local=str(partial)) for part in command]
    completed = subprocess.run(argv, capture_output=True, timeout=6 * 3600)
    if completed.returncode or not partial.is_file():
        raise DeliveryError('fetch failed (%s): %s' % (completed.returncode,
                            completed.stderr.decode('utf-8', 'replace')[-500:]))
    return partial


def source_from_manifest(manifest_path, *, cache_dir, artifact_root=None, fetch_command=None):
    """Resolve the frozen artifact an accepted-version manifest names, and prove it.

    Order: the manifest's own path, then ``artifact_root/artifact_relpath`` (a mount of
    the collector root), then -- only if configured -- ``fetch_command`` into
    ``cache_dir``. Every route ends in the same sha256 check.
    """
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict) or not manifest.get('sha256'):
        raise DeliveryError('accepted-version manifest unreadable: ' + str(manifest_path))
    sha = manifest['sha256']
    lineage = manifest.get('lineage') or {}
    origin = 'manifest ' + str(manifest_path)
    options = [Path(manifest['artifact'])] if manifest.get('artifact') else []
    if artifact_root and manifest.get('artifact_relpath'):
        options.append(Path(artifact_root) / manifest['artifact_relpath'])
    cached = Path(cache_dir) / (sha + '.jobs.json')
    options.append(cached)
    for option in options:
        if option.is_file() and digest(option) == sha:
            return verified_source(option, sha, origin=origin, lineage=lineage)
    if not fetch_command:
        raise DeliveryError('accepted artifact %s not reachable locally and no fetch command is '
                            'configured (set --artifact-root or --fetch-command)' % sha)
    partial = fetch(manifest['artifact'], cached, fetch_command)
    if digest(partial) != sha:
        partial.unlink(missing_ok=True)
        raise DeliveryError('fetched artifact does not match the accepted sha256')
    os.replace(partial, cached)
    return verified_source(cached, sha, origin=origin + ' (fetched)', lineage=lineage)


# --- version order -----------------------------------------------------------------

def descends(child, ancestor, edges):
    """True when ``ancestor`` is reachable from ``child`` through accepted-version parents."""
    seen = set()
    current = child
    while current and current not in seen and len(seen) < LINEAGE_WALK_LIMIT:
        if current == ancestor:
            return True
        seen.add(current)
        current = edges.get(current)
    return False


def check_forward(ledger, sha):
    last = ledger.get('last_delivered')
    if not last or last == sha:
        return
    edges = ledger.get('lineage') or {}
    if descends(sha, last, edges):
        return
    if descends(last, sha, edges):
        raise DeliveryError('version %s is older than the delivered %s; refusing to move Feishu back'
                            % (sha, last))
    raise DeliveryError('cannot prove version %s descends from the delivered %s; a different '
                        'hash is not a newer version' % (sha, last))


# --- bootstrap: what Feishu shows before this ledger existed ----------------------
# An empty local ledger says nothing about the Base. The first delivery must know which
# accepted version the current official tables hold, or an older accepted snapshot could
# replace them. That version is proven from the R1 batch's own receipt chain -- switch ->
# verify -> import + projection manifest, linked by the paths each receipt records --
# and every evidence file's sha256 is pinned in the approved policy. A Base that truly
# has no official tables is declared explicitly (mode ``empty_base``); nothing defaults
# to it.

def _evidence(path):
    path = Path(path)
    return {'path': str(path), 'sha256': digest(path)}


def bootstrap_from_switch(switch_receipt_path):
    """Collect and pin the R1 receipt chain behind the tables a switch made official."""
    switch = load_json(switch_receipt_path) or {}
    verify_path = switch.get('verify_receipt')
    verify = load_json(verify_path) if verify_path else None
    if not verify:
        raise DeliveryError('switch receipt does not lead to a readable verify receipt')
    missing = [key for key in ('projection_manifest', 'import_receipt') if not verify.get(key)]
    if missing:
        raise DeliveryError('verify receipt lacks ' + ', '.join(missing))
    projection = load_json(verify['projection_manifest']) or {}
    return {'mode': 'existing_base', 'official_sha256': projection.get('source_sha256'),
            'evidence': {'switch_receipt': _evidence(switch_receipt_path),
                         'verify_receipt': _evidence(verify_path),
                         'import_receipt': _evidence(verify['import_receipt']),
                         'projection_manifest': _evidence(verify['projection_manifest'])}}


def verify_bootstrap(bootstrap, official_tables):
    """Prove the bootstrap claim; returns the summary the ledger keeps. Fails closed."""
    if not isinstance(bootstrap, dict):
        raise DeliveryError('bootstrap missing')
    if bootstrap.get('mode') == 'empty_base':
        if not bootstrap.get('declared_by') or not bootstrap.get('declared_at'):
            raise DeliveryError('empty_base bootstrap must name declared_by and declared_at')
        if official_tables:
            raise DeliveryError('empty_base bootstrap cannot list official tables')
        return {'mode': 'empty_base', 'declared_by': bootstrap['declared_by'],
                'declared_at': bootstrap['declared_at'], 'verified_at': now()}
    if bootstrap.get('mode') != 'existing_base':
        raise DeliveryError('bootstrap.mode must be existing_base or empty_base')
    evidence = bootstrap.get('evidence') or {}
    docs = {}
    for key in ('switch_receipt', 'verify_receipt', 'import_receipt', 'projection_manifest'):
        pinned = evidence.get(key) or {}
        path = pinned.get('path')
        if not path or not Path(path).is_file():
            raise DeliveryError('bootstrap evidence missing: ' + key)
        if digest(path) != pinned.get('sha256'):
            raise DeliveryError('bootstrap evidence changed since approval: ' + key)
        docs[key] = load_json(path) or {}
    switch, verify, imported, projection = (docs[k] for k in ('switch_receipt', 'verify_receipt',
                                                              'import_receipt', 'projection_manifest'))
    same = lambda a, b: Path(str(a)).resolve() == Path(str(b)).resolve()
    problems = []
    if switch.get('outcome') != 'completed' or switch.get('base_token') != BASE_TOKEN:
        problems.append('switch receipt is not a completed switch of this Base')
    if not same(switch.get('verify_receipt'), evidence['verify_receipt']['path']):
        problems.append('switch receipt names another verify receipt')
    if (verify.get('outcome') != 'completed' or verify.get('gate_passed') is not True
            or verify.get('base_token') != BASE_TOKEN):
        problems.append('verify receipt did not pass its gate for this Base')
    projection_gz = verify.get('source_projection_sha256_gz')
    if not projection_gz or verify.get('projection_sha256_on_disk') != projection_gz:
        problems.append('verify receipt does not pin one projection')
    if not same(verify.get('projection_manifest'), evidence['projection_manifest']['path']):
        problems.append('verify receipt names another projection manifest')
    if not same(verify.get('import_receipt'), evidence['import_receipt']['path']):
        problems.append('verify receipt names another import receipt')
    if (imported.get('outcome') != 'completed' or imported.get('base_token') != BASE_TOKEN
            or (imported.get('batch_identity') or {}).get('source_projection_sha256_gz') != projection_gz):
        problems.append('import receipt is not the completed import of that projection')
    if (projection.get('projection_ndjson_gz') or {}).get('sha256_gz') != projection_gz:
        problems.append('projection manifest is not the verified projection')
    official = bootstrap.get('official_sha256')
    if not official or projection.get('source_sha256') != official:
        problems.append('official_sha256 is not the source of the verified projection')
    try:
        tables = official_tables_from(switch)
    except DeliveryError as error:
        problems.append(str(error))
        tables = None
    if tables != [list(x) for x in official_tables]:
        problems.append('switch receipt made other tables official than the policy names')
    if set((imported.get('targets_bound') or {}).values()) != {tid for tid, _ in tables or []}:
        problems.append('import receipt bound other tables than the switch made official')
    if problems:
        raise DeliveryError('bootstrap evidence rejected: ' + '; '.join(problems))
    return {'mode': 'existing_base', 'official_sha256': official, 'projection_sha256_gz': projection_gz,
            'evidence': evidence, 'verified_at': now()}


def bootstrap_ledger(ledger, bootstrap, official_tables, since_date):
    """Seed an empty ledger from a verified bootstrap; the Base's version becomes the floor."""
    summary = verify_bootstrap(bootstrap, official_tables)
    ledger['bootstrap'] = summary
    if summary['mode'] == 'existing_base':
        sha = summary['official_sha256']
        ledger['last_delivered'] = sha
        ledger['delivered'][sha] = {'delivered_at': 'before this ledger (bootstrap)', 'bootstrap': True}
        ledger['official_tables'] = [list(x) for x in official_tables]
        ledger['official_since_date'] = since_date
    return summary


BOOTSTRAP_NEEDED = ('this delivery ledger was never bootstrapped, and a missing local ledger is not '
                    'an empty Base. Approve a policy whose "bootstrap" binds the current official '
                    'version (mode existing_base: official_sha256 plus pinned switch/verify/import/'
                    'projection-manifest receipts, as draft-policy proposes from the last R1 switch '
                    'receipt), or declare {"mode": "empty_base", "declared_by", "declared_at"} for a '
                    'Base that has no official tables')


# --- layout ------------------------------------------------------------------------

def draft_policy(switch_receipt_path):
    """A policy proposal from the last completed switch; ``approved`` stays false.

    The tables that switch made official are the starting official set. Archive naming,
    the folder, the protected tables and the sample rule are for the reviewer.
    """
    receipt = load_json(switch_receipt_path)
    if not isinstance(receipt, dict) or receipt.get('outcome') != 'completed':
        raise DeliveryError('switch receipt missing or not completed: ' + str(switch_receipt_path))
    if receipt.get('base_token') != BASE_TOKEN:
        raise DeliveryError('switch receipt belongs to another Base')
    return {'approved': False, 'base_token': BASE_TOKEN, 'derived_from': str(switch_receipt_path),
            'bootstrap': bootstrap_from_switch(switch_receipt_path),
            'initial_official_tables': official_tables_from(receipt),
            'initial_official_date': None, 'legacy_suffix_template': None, 'folder_name': None,
            'protected_table_ids': None, 'sample_rule': None,
            'review_required': ['initial_official_date', 'legacy_suffix_template (with {version_date})',
                                'folder_name', 'protected_table_ids', 'sample_rule']}


def official_tables_from(receipt):
    mapping = receipt.get('temp_to_official') or {}
    tables = []
    for tid, temp in receipt.get('new_tables') or []:
        if temp not in mapping:
            raise DeliveryError('switch receipt has no official name for ' + temp)
        tables.append([tid, mapping[temp]])
    return tables


def checked_policy(policy):
    if not isinstance(policy, dict) or policy.get('approved') is not True:
        raise DeliveryError('policy is not approved; the first delivery needs a reviewed policy')
    if policy.get('base_token') != BASE_TOKEN:
        raise DeliveryError('policy names another Base')
    for key in ('bootstrap', 'initial_official_tables', 'initial_official_date', 'legacy_suffix_template',
                'folder_name', 'protected_table_ids'):
        if policy.get(key) is None:
            raise DeliveryError('policy field missing: ' + key)
    if '{version_date}' not in policy['legacy_suffix_template']:
        raise DeliveryError('legacy_suffix_template must contain {version_date}')
    if policy.get('sample_rule') != SAMPLE_RULE:
        raise DeliveryError('policy sample_rule must be ' + SAMPLE_RULE)
    return policy


def archive_suffix(template, since, outgoing_sha):
    """Archive name for the tables being replaced, unique per outgoing version.

    The date alone collides as soon as two versions become official on the same day
    (2026-09-24: d516 and 1244 both did, and the 1244 -> bd4f switch was refused with
    "table name already exists"). The outgoing accepted hash prefix makes the name
    identify the version it archives, so a retry of the same batch reuses the same name.
    """
    if not outgoing_sha:
        return template.format(version_date=since)
    return template.format(version_date=f'{since}-{outgoing_sha[:8]}')


def layout_from_policy(policy, ledger):
    """This version's R1 inputs: approved policy + the tables the ledger knows are official."""
    policy = checked_policy(policy)
    official = ledger.get('official_tables') or policy['initial_official_tables']
    since = ledger.get('official_since_date') or policy['initial_official_date']
    outgoing = ledger.get('last_delivered') or (policy.get('bootstrap') or {}).get('official_sha256')
    return {'approved': True, 'base_token': BASE_TOKEN, 'legacy_tables': official,
            'schema_source_tables': official, 'pre_archived': [],
            'legacy_suffix': archive_suffix(policy['legacy_suffix_template'], since, outgoing),
            'outgoing_sha256': outgoing,
            'folder_name': policy['folder_name'],
            'existing_table_ids': sorted(set(policy['protected_table_ids'])
                                         | set(ledger.get('archived_table_ids') or [])),
            'sample_rule': SAMPLE_RULE, 'derived_from_policy': True}


def checked_layout(layout):
    """Refuse anything but a complete, approved layout for the fixed Base."""
    if not isinstance(layout, dict) or layout.get('approved') is not True:
        raise DeliveryError('layout is not approved; external stages need a reviewed layout')
    if layout.get('base_token') != BASE_TOKEN:
        raise DeliveryError('layout names another Base')
    for key in ('legacy_tables', 'schema_source_tables', 'pre_archived', 'legacy_suffix',
                'folder_name', 'existing_table_ids'):
        if layout.get(key) is None:
            raise DeliveryError('layout field missing: ' + key)
    if not layout.get('samples') and layout.get('sample_rule') != SAMPLE_RULE:
        raise DeliveryError('layout needs explicit samples or sample_rule=' + SAMPLE_RULE)
    return layout


def protected_ids(layout):
    """Every table that existed before this version: never a target of fix/clean/rename."""
    ids = {tid for tid, _ in layout['legacy_tables']} | {tid for tid, _ in layout['pre_archived']}
    return ids | set(layout['existing_table_ids'])


def temp_prefix(sha):
    return '待切换-' + sha[:12] + '-'


def overrides_for(stage, layout, work, sha, xlsx_manifest=None):
    """Module constants each R1 script receives; paths go through their env variables."""
    if stage == 'schema_snapshot':
        return {'TABLES': [list(x) for x in layout['schema_source_tables']],
                'OUT': str(work / 'prod-schema-snapshot.json')}
    legacy = sorted(protected_ids(layout))
    if stage == 'import':
        return {'LEGACY_IDS': legacy}
    if stage in ('schema_fix', 'clean_blank', 'verify'):
        return {'LEGACY_IDS': legacy,
                'SOURCE_TABLE_ORDER': [tid for tid, _ in layout['schema_source_tables']],
                GENERIC_WHITELIST: True}
    if stage == 'switch':
        prefix = temp_prefix(sha)
        official = [item['table_name'][len(prefix):] for item in xlsx_manifest['files']]
        return {'LEGACY_IDS': legacy, 'LEGACY_TABLES': [list(x) for x in layout['legacy_tables']],
                'PRE_ARCHIVED': [list(x) for x in layout['pre_archived']],
                'LEGACY_SUFFIX': layout['legacy_suffix'], 'FOLDER_NAME': layout['folder_name'],
                'OFFICIAL_ORDER': official,
                'OFFICIAL_BY_TEMP': {prefix + name: name for name in official}}
    return {}


# Constants the scripts derive as sets/dicts; JSON carries lists, restore the type.
SET_CONSTANTS = {'LEGACY_IDS'}
TUPLE_LIST_CONSTANTS = {'TABLES', 'LEGACY_TABLES', 'PRE_ARCHIVED'}


def load_script(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply_overrides(module, overrides):
    if getattr(module, 'BASE', BASE_TOKEN) != BASE_TOKEN:
        raise DeliveryError('script targets another Base: ' + str(getattr(module, 'BASE', None)))
    for key, value in overrides.items():
        if key == GENERIC_WHITELIST:
            if not hasattr(module, 'apply_excel_text_whitelist'):
                raise DeliveryError(f'{module.__name__} has no apply_excel_text_whitelist; script changed?')
            module.apply_excel_text_whitelist = generic_excel_text_whitelist(module)
            continue
        if not hasattr(module, key):
            raise DeliveryError(f'{module.__name__} has no constant {key}; script changed?')
        if key in SET_CONSTANTS:
            value = set(value)
        elif key in TUPLE_LIST_CONSTANTS:
            value = [tuple(x) for x in value]
        elif key in ('OUT', 'OUT_DIR', 'WORK', 'SOURCE', 'ROOT'):
            value = Path(value)
        setattr(module, key, value)


# --- Excel illegal characters ------------------------------------------------------
# openpyxl strips control characters while build_xlsx writes each cell, so the imported
# table differs from the projection in exactly those cells. The R1 verify accepted one
# hard-coded cell (the 2026-09-23 batch had exactly one). This keeps the same rule for
# any number of cells, zero included: every cell the xlsx builder sanitised is listed
# from the projection itself, the count must equal the builder's own counter, and a
# value Excel would truncate is refused rather than compared loosely.

def build_illegal_character_report(work):
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    work = Path(work)
    projection = load_json(work / 'projection-manifest.json')
    xlsx = load_json(work / 'xlsx-manifest.json')
    columns = projection['columns']
    fields = xlsx.get('live_column_order') or columns
    index = {name: columns.index(name) for name in fields}
    job_index = columns.index('job_id')
    report = {'cells_scanned': 0, 'cells_with_illegal_chars': 0, 'cells_truncated': 0,
              'hits': [], 'truncated': [], 'source_projection_sha256_gz': digest(work / 'projection.ndjson.gz')}
    with gzip.open(work / 'projection.ndjson.gz', 'rt', encoding='utf-8') as fh:
        for line in fh:
            if not line.strip():
                continue
            record = json.loads(line)
            for name, position in index.items():
                value = record['c'][position]
                report['cells_scanned'] += 1
                cleaned = ILLEGAL_CHARACTERS_RE.sub('', value)
                if cleaned != value:
                    report['cells_with_illegal_chars'] += 1
                    report['hits'].append({'group': record['g'], 'job_id': record['c'][job_index],
                                           'field': name, 'before_repr': repr(value),
                                           'after_repr': repr(cleaned),
                                           'removed_codepoints': sorted({hex(ord(ch)) for ch in value
                                                                         if ch not in cleaned})})
                if len(cleaned) > EXCEL_CELL_LIMIT:
                    report['cells_truncated'] += 1
                    report['truncated'].append({'job_id': record['c'][job_index], 'field': name,
                                                'length': len(cleaned)})
    sanitized = xlsx.get('sanitized_cells')
    if 'live_column_order' in xlsx:
        counted = (sanitized or {}).get('cells', 0)
        if counted != report['cells_with_illegal_chars']:
            raise DeliveryError('xlsx builder sanitised %s cells but the projection has %s'
                                % (counted, report['cells_with_illegal_chars']))
    if report['cells_truncated'] or (sanitized or {}).get('truncated_cells'):
        raise DeliveryError('%s cell(s) exceed the Excel limit and would be truncated; refusing '
                            'to import a lossy copy' % max(report['cells_truncated'],
                                                           (sanitized or {}).get('truncated_cells', 0)))
    atomic_json(work / 'illegal-character-report.json', report)
    return report


def generic_excel_text_whitelist(module):
    """Replacement for R1 ``apply_excel_text_whitelist``: every reported hit, exactly once."""
    def apply(per_group):
        work = Path(module.WORK)
        report = json.loads((work / 'illegal-character-report.json').read_text(encoding='utf-8'))
        xlsx = json.loads((work / 'xlsx-manifest.json').read_text(encoding='utf-8'))
        hits = report.get('hits') or []
        if report.get('cells_truncated') or report.get('truncated'):
            raise SystemExit('illegal-character report lists truncated cells; refusing')
        if len(hits) != report.get('cells_with_illegal_chars'):
            raise SystemExit('illegal-character report is internally inconsistent')
        if len(hits) != (xlsx.get('sanitized_cells') or {}).get('cells', 0):
            raise SystemExit('illegal-character report does not match the xlsx sanitised-cell count')
        applied = []
        for hit in hits:
            before = ast.literal_eval(hit['before_repr'])
            after = ast.literal_eval(hit['after_repr'])
            count = 0
            for row in per_group.get(hit['group'], []):
                if row['job_id'] == hit['job_id'] and row[hit['field']] == before:
                    row[hit['field']] = after
                    count += 1
            if count != 1:
                raise SystemExit(f"excel text whitelist hit {count} times for "
                                 f"{hit['job_id']}/{hit['field']}, expected exactly 1")
            applied.append({'group': hit['group'], 'job_id': hit['job_id'], 'field': hit['field'],
                            'removed_codepoints': hit['removed_codepoints']})
        return {'hits': len(applied), 'applied': applied}
    return apply


# --- stage runner ------------------------------------------------------------------

class ScriptRunner:
    """Runs the R1 scripts. Local stages in-process, external ones in a child process."""

    def __init__(self, scripts_dir=DEFAULT_SCRIPTS, *, apply=False, python=sys.executable):
        self.scripts = Path(scripts_dir)
        self.apply = apply
        self.python = python

    def local(self, stage, work, source):
        if stage == 'projection':
            module = load_script(self.scripts / SCRIPT['projection'], 'r1_projection')
            apply_overrides(module, {'SOURCE': source['path'], 'OUT_DIR': str(work),
                                     'EXPECTED_SOURCE_SHA': source['sha256'], 'ROOT': str(ROOT)})
            module.main()
        elif stage == 'xlsx':
            module = load_script(self.scripts / SCRIPT['xlsx'], 'r1_xlsx')
            apply_overrides(module, {'WORK': str(work), 'PREFIX': temp_prefix(source['sha256'])})
            module.main()
            build_illegal_character_report(work)
        else:
            raise DeliveryError('not a local stage: ' + stage)

    def live_blocks(self):
        """Read-only listing of the Base's tables and folders (lark-cli base +base-block-list)."""
        if not self.apply:
            raise DeliveryError('reading the live Base requires --apply')
        completed = subprocess.run(['lark-cli', 'base', '+base-block-list', '--base-token', BASE_TOKEN,
                                    '--as', 'user'], capture_output=True, text=True, timeout=180)
        body = {}
        for stream in (completed.stdout, completed.stderr):
            try:
                body = json.loads(stream)
                break
            except ValueError:
                continue
        if completed.returncode or not body.get('ok'):
            raise DeliveryError('cannot read the live Base blocks: ' + (completed.stdout or completed.stderr)[-300:])
        return body['data']['blocks']

    def external(self, stage, work, overrides, log):
        if not self.apply:
            raise DeliveryError('external stage requires --apply')
        spec = work / f'.exec-{stage}.json'
        atomic_json(spec, {'script': str(self.scripts / SCRIPT[stage]), 'overrides': overrides,
                           'argv': SCRIPT_ARGS.get(stage, [])})
        env = dict(os.environ, EXCEL_IMPORT_WORK=str(work), EXCEL_IMPORT_OUT=str(work / 'receipts'),
                   PYTHONUTF8='1')
        with Path(log).open('ab') as out:
            completed = subprocess.run([self.python, '-X', 'utf8', str(Path(__file__).resolve()),
                                        'exec-script', str(spec)], cwd=str(work), env=env,
                                       stdout=out, stderr=subprocess.STDOUT, timeout=6 * 3600)
        return completed.returncode


def exec_script(spec_path):
    """Child side of ``ScriptRunner.external``: load, override, run ``main()``."""
    spec = load_json(spec_path)
    module = load_script(spec['script'], 'r1_' + Path(spec['script']).stem)
    apply_overrides(module, spec['overrides'])
    sys.argv = [spec['script'], *spec['argv']]
    result = module.main()
    return int(result or 0)


# --- samples -----------------------------------------------------------------------

def choose_samples(work, layout, sha):
    """The 24 semantic sample IDs the verify gate reads from ``samples24.json``."""
    manifest = load_json(work / 'xlsx-manifest.json')
    if layout.get('samples'):
        ids = [str(x) for x in layout['samples']]
    else:
        tables = [item['table_name'] for item in manifest['files']]
        ranked = {name: [] for name in tables}
        projection = load_json(work / 'projection-manifest.json')
        job_index = projection['columns'].index('job_id')
        by_group = {}
        with gzip.open(work / 'projection.ndjson.gz', 'rt', encoding='utf-8') as fh:
            for line in fh:
                if line.strip():
                    rec = json.loads(line)
                    by_group.setdefault(rec['g'], []).append(rec['c'][job_index])
        for item in manifest['files']:
            chunk = by_group.get(item['group'], [])[item['chunk_index'] * manifest['chunk_limit']:]
            chunk = chunk[:item['rows']]
            ranked[item['table_name']] = sorted(
                chunk, key=lambda ident: hashlib.sha256((sha + ident).encode()).hexdigest())
        ids, position = [], 0
        while len(ids) < SAMPLE_COUNT and any(len(v) > position for v in ranked.values()):
            for name in tables:
                if len(ids) < SAMPLE_COUNT and len(ranked[name]) > position:
                    ids.append(ranked[name][position])
            position += 1
    if len(ids) != SAMPLE_COUNT or len(set(ids)) != SAMPLE_COUNT:
        raise DeliveryError(f'need exactly {SAMPLE_COUNT} distinct samples, got {len(set(ids))}')
    atomic_json(work / 'samples24.json', [{'id': ident} for ident in ids])
    return ids


# --- orchestration -----------------------------------------------------------------

def version_dir(root, sha):
    return Path(root) / 'versions' / sha


def load_state(root, source):
    path = version_dir(root, source['sha256']) / 'state.json'
    state = load_json(path)
    if state is None:
        state = {'source': source, 'base_token': BASE_TOKEN, 'created_at': now(),
                 'stages': {name: {'status': 'pending', 'attempts': 0} for name in STAGES},
                 'outcome': 'in_progress'}
    elif state['source']['sha256'] != source['sha256']:
        raise DeliveryError('version state belongs to another source')
    elif state.get('outcome') == 'abandoned':
        raise DeliveryError('version %s was abandoned; its state is kept as evidence and it is '
                            'not resumed' % source['sha256'])
    return path, state


def save(path, state):
    state['updated_at'] = now()
    atomic_json(path, state)


def local_outputs(work):
    """Hashes that pin everything imported to the projection of this exact version."""
    projection = load_json(work / 'projection-manifest.json') or {}
    xlsx = load_json(work / 'xlsx-manifest.json') or {}
    return {'projection_manifest_source_sha256': projection.get('source_sha256'),
            'projection_gz_sha256': digest(work / 'projection.ndjson.gz')
            if (work / 'projection.ndjson.gz').exists() else None,
            'xlsx': {item['table_name']: item['sha256'] for item in xlsx.get('files', [])}}


def cleanup_manifest(work):
    """Tables this version created in the Base, from the import script's own state."""
    state = load_json(work / 'import-state.json') or {}
    return [{'table_name': name, 'table_id': entry.get('table_id'), 'status': entry.get('status')}
            for name, entry in sorted((state.get('targets') or {}).items()) if entry.get('table_id')]


def switch_result(work):
    """The official tables the completed R1 switch produced (its own receipt)."""
    receipts = sorted(Path(work).glob('runs/*/switch-receipt.json'))
    receipt = load_json(receipts[-1]) if receipts else None
    if not receipt or receipt.get('outcome') != 'completed':
        raise DeliveryError('switch reported success but no completed switch receipt was found')
    return official_tables_from(receipt)


def migrate_switch_layout(state, frozen, wanted, work, ledger, sha, runner):
    """Allow a switch that failed under an older archive name to resume under the new one.

    Only the archive suffix may differ, and only if the Base provably still looks exactly
    as it did before the switch: the R1 switch recorded no successful action and no
    folder, every outgoing official table carries its original name at the Base root
    (none has the old suffix), every imported temporary table still has its import-time
    id and temporary name, and source, verify gate and ledger all name this version and
    these outgoing tables. Anything else means a partial switch; this refuses, and the
    batch must be resumed with its original layout.
    """
    problems = []
    if [list(x) for x in frozen.get('legacy_tables') or []] != wanted['legacy_tables']:
        problems.append('outgoing tables differ from the frozen layout')
    if frozen.get('folder_name') != wanted['folder_name']:
        problems.append('archive folder differs from the frozen layout')
    if state['source']['sha256'] != sha:
        problems.append('state belongs to another source version')
    if state['stages']['verify']['status'] != 'completed':
        problems.append('verify gate has not passed for this version')
    if ledger.get('active') != sha:
        problems.append('ledger does not hold this version as the active delivery')
    if (ledger.get('official_tables') or []) != wanted['legacy_tables']:
        problems.append('ledger official tables are not the frozen outgoing tables')
    switch_state = load_json(Path(work) / 'switch-state.json', {}) or {}
    done = [key for key, value in (switch_state.get('actions') or {}).items() if (value or {}).get('ok')]
    if done:
        problems.append('switch already applied actions: ' + ', '.join(sorted(done)[:5]))
    if switch_state.get('folder_id'):
        problems.append('switch already created or chose an archive folder')
    batch = switch_state.get('batch') or {}
    if batch and [list(x) for x in batch.get('legacy') or []] != wanted['legacy_tables']:
        problems.append('switch state names other outgoing tables')
    imported = (load_json(Path(work) / 'import-state.json', {}) or {}).get('targets') or {}
    temporary = sorted([entry.get('table_id'), name] for name, entry in imported.items())
    if not temporary:
        problems.append('no import state to identify the temporary tables')
    if batch and sorted(list(x) for x in batch.get('new_tables') or []) != temporary:
        problems.append('switch state names other temporary tables than the import')
    blocks = runner.live_blocks()
    live = {block.get('id'): block for block in blocks}
    for tid, name in wanted['legacy_tables'] + temporary:
        block = live.get(tid)
        if not block or block.get('name') != name or block.get('parent_id'):
            problems.append(f'table {tid} is not at the Base root as {name!r} '
                            f'(live: {block and block.get("name")!r})')
    if problems:
        raise DeliveryError('refusing archive-name migration; resume with the original layout: '
                            + '; '.join(problems[:6]))
    return {'at': now(), 'from_suffix': frozen.get('legacy_suffix'), 'to_suffix': wanted['legacy_suffix'],
            'source_sha256': sha, 'ledger_active': ledger.get('active'),
            'ledger_last_delivered': ledger.get('last_delivered'),
            'state_sha256_before': digest(Path(work).parent / 'state.json'),
            'switch_state_sha256': (digest(Path(work) / 'switch-state.json')
                                    if (Path(work) / 'switch-state.json').exists() else None),
            'import_state_sha256': digest(Path(work) / 'import-state.json'),
            'live_blocks_sha256': hashlib.sha256(json.dumps(
                sorted([b.get('id'), b.get('name'), b.get('parent_id')] for b in blocks),
                ensure_ascii=False).encode()).hexdigest(),
            'checked_outgoing_tables': len(wanted['legacy_tables']),
            'checked_temporary_tables': len(temporary)}


def resolve_layout(layout, policy, ledger):
    if layout is not None:
        return layout
    if policy is not None:
        return layout_from_policy(policy, ledger)
    return None


def deliver(root, source, runner, *, layout=None, policy=None):
    """Advance this version's delivery as far as allowed; returns the version state."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'delivery.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise DeliveryError('another delivery holds the lock')
        ledger_path = root / 'ledger.json'
        ledger = load_json(ledger_path, {'delivered': {}, 'active': None})
        sha = source['sha256']
        if 'bootstrap' not in ledger:
            if policy is not None:
                checked = checked_policy(policy)
                bootstrap_ledger(ledger, checked['bootstrap'], checked['initial_official_tables'],
                                 checked['initial_official_date'])
            elif isinstance(layout, dict) and layout.get('bootstrap'):
                checked = checked_layout(layout)
                bootstrap_ledger(ledger, checked['bootstrap'], checked['legacy_tables'], None)
            else:
                raise DeliveryError(BOOTSTRAP_NEEDED)
            atomic_json(ledger_path, ledger)
        if sha in ledger['delivered']:
            return {'outcome': 'already_delivered', 'source': source, **ledger['delivered'][sha]}
        if ledger.get('active') and ledger['active'] != sha:
            raise DeliveryError('version %s is still in progress; finish it (abandon only before its '
                                'switch started)' % ledger['active'])
        ledger.setdefault('lineage', {}).update(source.get('lineage') or {})
        check_forward(ledger, sha)
        path, state = load_state(root, source)
        work = path.parent / 'work'
        work.mkdir(parents=True, exist_ok=True)
        ledger['active'] = sha
        atomic_json(ledger_path, ledger)
        save(path, state)
        verified_source(source['path'], sha, origin=source.get('origin', 'recheck'))
        try:
            layout = resolve_layout(layout, policy, ledger)
        except DeliveryError as error:
            layout = {'approved': False, 'error': str(error)}
        for stage in STAGES:
            entry = state['stages'][stage]
            if entry['status'] == 'completed':
                continue
            if stage in EXTERNAL_STAGES or stage == 'samples':
                try:
                    checked = checked_layout(layout)
                    if (ledger.get('official_tables')
                            and [list(x) for x in checked['legacy_tables']] != ledger['official_tables']):
                        raise DeliveryError('layout outgoing tables differ from the tables the last '
                                            'delivery made official')
                except DeliveryError as error:
                    state['outcome'] = 'awaiting_layout'
                    state['blocked'] = {'stage': stage, 'reason': (layout or {}).get('error') or str(error)}
                    save(path, state)
                    return state
            if stage in EXTERNAL_STAGES:
                if not runner.apply:
                    state['outcome'] = 'awaiting_apply'
                    state['blocked'] = {'stage': stage, 'reason': 'external stage requires --apply'}
                    save(path, state)
                    return state
                if local_outputs(work) != state['local_outputs']:
                    raise DeliveryError('projection/xlsx changed on disk after they were recorded')
            if stage == 'switch':
                # Re-read under the lock right before anything becomes official.
                check_forward(ledger, sha)
                wanted = {'legacy_tables': [list(x) for x in checked['legacy_tables']],
                          'legacy_suffix': checked['legacy_suffix'],
                          'folder_name': checked['folder_name']}
                frozen = state.get('switch_layout')
                if frozen is not None and frozen != wanted:
                    state.setdefault('switch_layout_migrations', []).append(
                        migrate_switch_layout(state, frozen, wanted, work, ledger, sha, runner))
                state['switch_layout'] = wanted
            state.pop('blocked', None)
            entry.update(status='running', attempts=entry['attempts'] + 1, started_at=now())
            entry.pop('error', None)
            save(path, state)
            try:
                if stage in ('projection', 'xlsx'):
                    runner.local(stage, work, source)
                    manifest = load_json(work / 'projection-manifest.json') or {}
                    if manifest.get('source_sha256') != sha:
                        raise DeliveryError('projection is not of the accepted version')
                    if stage == 'xlsx':
                        state['local_outputs'] = local_outputs(work)
                elif stage == 'samples':
                    entry['sample_ids'] = choose_samples(work, checked, sha)
                    entry['rule'] = 'layout.samples' if checked.get('samples') else SAMPLE_RULE
                else:
                    xlsx = load_json(work / 'xlsx-manifest.json')
                    code = runner.external(stage, work, overrides_for(stage, checked, work, sha, xlsx),
                                           path.parent / f'{stage}.log')
                    entry['exit_code'] = code
                    if code != 0:
                        raise DeliveryError(f'{stage} exited {code}; see {stage}.log and its receipt')
                    if stage == 'switch':
                        state['official_tables_after'] = switch_result(work)
            except Exception as error:
                entry.update(status='failed', error=type(error).__name__ + ': ' + str(error)[:800],
                             finished_at=now())
                state['outcome'] = 'failed'
                state['failed_stage'] = stage
                state['cleanup_manifest'] = cleanup_manifest(work)
                state['server'] = 'untouched: delivery never writes the server'
                state['official_tables'] = ('unchanged' if stage != 'switch'
                                            else 'switch may be partly applied; resume this version')
                save(path, state)
                return state
            entry.update(status='completed', finished_at=now())
            save(path, state)
        state['outcome'] = 'delivered'
        state['delivered_at'] = now()
        state['feishu_accepted_sha256'] = sha
        save(path, state)
        previous = ledger.get('official_tables') or (layout or {}).get('legacy_tables') or []
        ledger['archived_table_ids'] = sorted(set(ledger.get('archived_table_ids') or [])
                                              | {tid for tid, _ in previous})
        ledger['official_tables'] = state['official_tables_after']
        ledger['official_since_date'] = dt.datetime.now().strftime('%Y%m%d')
        ledger['delivered'][sha] = {'delivered_at': state['delivered_at'], 'state': str(path)}
        ledger['active'] = None
        ledger['last_delivered'] = sha
        atomic_json(ledger_path, ledger)
        return state


def abandon(root, sha, reason):
    """Release the ledger from an unfinished version whose switch never started.

    The R1 switch renames and moves tables step by step; once it has started (running,
    failed, or even just a ``switch-state.json`` on disk) the Base may be half switched,
    and only finishing this same version is safe.
    """
    root = Path(root)
    with (root / 'delivery.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise DeliveryError('another delivery holds the lock')
        ledger = load_json(root / 'ledger.json', {'delivered': {}, 'active': None})
        if ledger.get('active') != sha:
            raise DeliveryError('not the active version')
        path = version_dir(root, sha) / 'state.json'
        state = load_json(path)
        work = path.parent / 'work'
        switch = state['stages']['switch']
        if switch['status'] != 'pending' or switch.get('attempts') or (work / 'switch-state.json').exists():
            raise DeliveryError('switch already started for %s; it may be partly applied, so resume '
                                'this version instead of abandoning it' % sha)
        state.update(outcome='abandoned', abandoned_at=now(), abandon_reason=reason,
                     cleanup_manifest=cleanup_manifest(work))
        save(path, state)
        ledger['active'] = None
        ledger.setdefault('abandoned', {})[sha] = {'at': state['abandoned_at'], 'reason': reason}
        atomic_json(root / 'ledger.json', ledger)
        return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('deliver')
    run.add_argument('--root', type=Path, required=True)
    group = run.add_mutually_exclusive_group(required=True)
    group.add_argument('--manifest', type=Path, help="copy of the collector's accepted-version manifest")
    group.add_argument('--run-receipt', type=Path)
    group.add_argument('--snapshot', type=Path)
    run.add_argument('--sha256')
    run.add_argument('--artifact-root', type=Path, help='mount of the collector root')
    run.add_argument('--fetch-command', type=json.loads,
                     help='JSON argv with {remote} and {local}; nothing is fetched without it')
    rules = run.add_mutually_exclusive_group()
    rules.add_argument('--policy', type=Path, help='approved policy; layouts derive from it and the ledger')
    rules.add_argument('--layout', type=Path, help='explicit approved layout for this one version')
    run.add_argument('--scripts-dir', type=Path, default=DEFAULT_SCRIPTS)
    run.add_argument('--apply', action='store_true', help='allow the lark-cli stages')
    draft = sub.add_parser('draft-policy')
    draft.add_argument('--switch-receipt', type=Path, required=True)
    draft.add_argument('--out', type=Path, required=True)
    drop = sub.add_parser('abandon')
    drop.add_argument('--root', type=Path, required=True)
    drop.add_argument('--sha256', required=True)
    drop.add_argument('--reason', required=True)
    child = sub.add_parser('exec-script')
    child.add_argument('spec', type=Path)
    a = parser.parse_args(argv)
    if a.command == 'exec-script':
        return exec_script(a.spec)
    if a.command == 'draft-policy':
        if a.out.exists():
            raise SystemExit('refusing to overwrite an existing policy: ' + str(a.out))
        atomic_json(a.out, draft_policy(a.switch_receipt))
        return 0
    if a.command == 'abandon':
        print(json.dumps(abandon(a.root, a.sha256, a.reason), ensure_ascii=False))
        return 0
    if a.manifest:
        source = source_from_manifest(a.manifest, cache_dir=a.root / 'artifacts',
                                      artifact_root=a.artifact_root, fetch_command=a.fetch_command)
    elif a.run_receipt:
        source = source_from_run_receipt(a.run_receipt)
    else:
        if not a.sha256:
            raise SystemExit('--snapshot needs --sha256 (the hash the receiver acknowledged)')
        source = verified_source(a.snapshot, a.sha256, origin='explicit snapshot')
    state = deliver(a.root, source, ScriptRunner(a.scripts_dir, apply=a.apply),
                    layout=load_json(a.layout) if a.layout else None,
                    policy=load_json(a.policy) if a.policy else None)
    print(json.dumps({k: state.get(k) for k in ('outcome', 'blocked', 'failed_stage',
                                                'feishu_accepted_sha256', 'cleanup_manifest')},
                     ensure_ascii=False))
    return 0 if state.get('outcome') in ('delivered', 'already_delivered') else 1


if __name__ == '__main__':
    raise SystemExit(main())
