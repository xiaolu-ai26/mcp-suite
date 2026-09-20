#!/usr/bin/env python3
"""Zero-network probe for feat/gap-report (部署件 20260920d).

Supersedes the tupu360/enablement assertions of ``collector-next6-probe.py``: that probe
records collector-next-6 as it shipped (68 rows, all parked, DEFAULT_COMPANIES 1069) and
those assertions are *meant* to fail now that 站长 enabled the 60 careersite tenants.  This
probe is the current source of truth for:

  * tupu360: 60 careersite rows enabled with the 2026-09-20 站长 decision on every row,
    8 anonymously-unreachable rows still parked with a reason, 1069 -> 1124 companies;
  * the Meituan fix: retry + >=1s pacing + pageSize 100 + the totalPage/totalCount overrun
    guard that keeps a truncated scan honest;
  * the daily collection-gap report: module present, wired into p1_pipeline, and its summary
    surfaced in receipt.json by the Windows chain.

No adapter call, no HTTP request, no socket. Exit 0 = every invariant holds.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qiuzhao.collector import p1_pipeline as p  # noqa: E402
from qiuzhao.collector import p1_platform_tupu360 as tupu  # noqa: E402
from qiuzhao.collector import collection_gap as gap  # noqa: E402

DEFAULT_TOTAL = 1124
TUPU360 = 'qiuzhao.collector.p1_platform_tupu360'
MEITUAN_SLOT = 'qiuzhao.collector.p1_sources_41_50'
MEITUAN = 'qiuzhao.collector.p1_meituan_public'
CONFIG = ROOT / 'qiuzhao' / 'collector' / 'p1_platform_companies.json'
COLLECTOR = ROOT / 'qiuzhao' / 'collector'
KEEP_OFF = {'nestle', 'taitaile', 'autoliv', 'louisvuitton', 'jntl', 'google',
            'boschhuayu-steering', 'johnsonelectric'}
SETDEFAULT_OWNERS = {
    'ABB': 'qiuzhao.collector.p1_platform_phenom',
    '康明斯': 'qiuzhao.collector.p1_platform_orc',
    '强生': 'qiuzhao.collector.p1_platform_workday',
    '斯堪尼亚': 'qiuzhao.collector.p1_platform_moka',
    '药明康德': 'qiuzhao.collector.p1_sources_41_50',
}
MEITUAN_MARKERS = (
    'PAGE_SIZE = 100',
    'REQUEST_INTERVAL_FLOOR = 1.0',
    'MAX_ATTEMPTS = 4',
    'RETRY_BACKOFF_BASE = 1.0',
    'PAGE_OVERRUN_LIMIT = 20',
    'def _page_interval()',
    'on_retry=_note_retry',
    "coverage['retries'] = retries",
    "coverage['pages_beyond_reported_total']",
    "coverage['pages_beyond_reported_total'] = page_no + 1 - observed_total_pages",
    'list exhausted at page',
    'reported totalPage=',
)
GAP_MARKERS = (
    'def unit_records(', 'def build_report(', 'def render_markdown(', 'def publish(',
    'def evaluate_alerts(', 'def compare_to_previous(', 'def find_previous_report(',
    'COMPANY_GAP_ALERT_THRESHOLD = 200', 'COMPLETE_BUT_SHORT_ALERT = 0',
)


def source(name, folder=COLLECTOR):
    return (folder / name).read_text(encoding='utf-8')


def main():
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    section = {key: value for key, value in config['tupu360'].items()
               if not str(key).startswith('_')}
    enabled = sorted(key for key, value in section.items() if value.get('enabled') is True)
    disabled = sorted(key for key, value in section.items() if value.get('enabled') is False)
    readme = str(config['tupu360']['_README'])
    pipeline_source = source('p1_pipeline.py')
    collector_chain = source('windows_collector.py', ROOT / 'deploy')
    result = {
        'default_total': len(p.DEFAULT_COMPANIES),
        'registry_total': len(p.REGISTRY),
        'registry_covers_default': set(p.REGISTRY) == set(p.DEFAULT_COMPANIES),
        'duplicates': len(p.DEFAULT_COMPANIES) - len(set(p.DEFAULT_COMPANIES)),
        'modules': len(set(p.REGISTRY.values())),
        'tupu360': {
            'declared_rows': len(section),
            'enabled_rows': len(enabled),
            'disabled_rows': disabled,
            'registers_in_default': sum(1 for name in p.DEFAULT_COMPANIES
                                        if p.REGISTRY[name] == TUPU360),
            'companies_dict': len(tupu.COMPANIES),
            'missing_enabled_reason': [key for key in enabled
                                       if not section[key].get('enabled_reason')],
            'decision_recorded': all('站长 2026-09-20' in str(section[key].get('enabled_reason'))
                                     and '接回来的60家都开' in str(section[key].get('enabled_reason'))
                                     and 'Disallow' in str(section[key].get('enabled_reason'))
                                     for key in enabled),
            'missing_blocked_reason': [key for key in disabled
                                       if not section[key].get('blocked_reason')],
            'readme_decision': '接回来的60家都开' in readme and '2026-09-20' in readme,
            'readme_robots': 'Disallow: /' in readme,
        },
        'setdefault_owners_hold': all(p.REGISTRY[name] == module
                                      for name, module in SETDEFAULT_OWNERS.items()),
        'meituan_module_owner': p.REGISTRY.get('美团'),
        'meituan_delegates_to_public_adapter': 'from qiuzhao.collector.p1_meituan_public import collect'
                                               in source('p1_sources_41_50.py'),
        'meituan_markers': {needle: needle in source('p1_meituan_public.py')
                            for needle in MEITUAN_MARKERS},
        'gap_markers': {needle: needle in source('collection_gap.py')
                        for needle in GAP_MARKERS},
        'pipeline_calls_gap_report': 'collection_gap.publish(' in pipeline_source
                                     and 'default_run_root(data_dir, run_dir)' in pipeline_source,
        'receipt_gets_gap_summary': "run/'collection-gap.json'" in collector_chain
                                    and "state['collection_gap']" in collector_chain,
        'gap_failure_is_not_fatal': 'status[\'collection_gap\'] = {\'available\': False' in pipeline_source,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    assert result['default_total'] == DEFAULT_TOTAL, result['default_total']
    assert result['registry_total'] == DEFAULT_TOTAL
    assert result['registry_covers_default'] is True
    assert result['duplicates'] == 0
    # 21 modules before the enablement + the tupu360 adapter, which registered nothing
    # while all 68 rows were parked and now owns 55 companies.
    assert result['modules'] == 22, result['modules']
    t = result['tupu360']
    assert t['declared_rows'] == 68
    assert t['enabled_rows'] == 60, t['enabled_rows']
    assert t['disabled_rows'] == sorted(KEEP_OFF), t['disabled_rows']
    assert t['missing_enabled_reason'] == []
    assert t['missing_blocked_reason'] == []
    assert t['decision_recorded'] is True
    assert t['readme_decision'] is True and t['readme_robots'] is True
    assert t['companies_dict'] == 60
    # 5 names keep an earlier adapter; the other 55 are net-new.
    assert t['registers_in_default'] == 55, t['registers_in_default']
    assert result['setdefault_owners_hold'] is True
    # 美团 is dispatched through the hardcoded p1_sources_41_50 slot, which delegates
    # to p1_meituan_public.collect -- the fixed module must stay on that path.
    assert result['meituan_module_owner'] == MEITUAN_SLOT, result['meituan_module_owner']
    assert result['meituan_delegates_to_public_adapter'] is True
    for group in ('meituan_markers', 'gap_markers'):
        missing = [name for name, present in result[group].items() if not present]
        assert not missing, (group, missing)
    assert result['pipeline_calls_gap_report'] is True
    assert result['receipt_gets_gap_summary'] is True
    assert result['gap_failure_is_not_fatal'] is True
    # The reporting thresholds must stay at the agreed values.
    assert gap.COMPANY_GAP_ALERT_THRESHOLD == 200
    assert gap.COMPLETE_BUT_SHORT_ALERT == 0
    print('PROBE OK')


if __name__ == '__main__':
    main()
