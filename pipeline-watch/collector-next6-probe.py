#!/usr/bin/env python3
"""Zero-network probe for the collector-next-6 merge (部署件 20260920c).

Checks the three lines merged on top of ``feat/collector-next-5`` (精灵现役 20260920a):

  * ``feat/platform-adapters`` 95a88ad3 -> Moka bounded cache-resume passes,
  * ``feat/tupu360-fullsite``  c0d552f2 -> tupu360 pagination fix + the 60-tenant
    full-site *configuration* (every row parked, ``enabled:false``),
  * this branch's pagination-honesty audit fixes.

No adapter call, no HTTP request, no import of anything that opens a socket.
Exit 0 = every invariant holds.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qiuzhao.collector import p1_pipeline as p  # noqa: E402

DEFAULT_TOTAL = 1069
TUPU360 = 'qiuzhao.collector.p1_platform_tupu360'
ICIMS = 'qiuzhao.collector.p1_platform_icims'
MOKA = 'qiuzhao.collector.p1_platform_moka'
WORKDAY = 'qiuzhao.collector.p1_platform_workday'
DAYEE = 'qiuzhao.collector.p1_foreign_01'
CONFIG_PATH = ROOT / 'qiuzhao' / 'collector' / 'p1_platform_companies.json'
COLLECTOR = ROOT / 'qiuzhao' / 'collector'

# 95a88ad3: a detail already saved by an earlier bounded pass must not spend budget again.
MOKA_MARKERS = ('def _cached_detail(', 'reused = _cached_detail(output_dir, ident)',
                "if cached and budget['limit'] is not None:", "budget['used'] -= 1")
# c0d552f2: the page cap is a safety valve, never a target page count.
TUPU360_MARKERS = ('PAGE_CAP = 120', "page_cap_hit = False", 'coverage[\'page_cap_hit\'] = True',
                   'pagination_exhausted = False')
# audit 2026-09-20: every adapter that can stop at its own cap must say so.
SF_MARKERS = ('list_complete = False', "coverage['page_cap_hit'] = True",
              'truncated=true')
AVATURE_MARKERS = ("coverage['list_truncated'] = True", 'legend_total=',
                   "known is not None and len(seen) < int(known)")
NETEASE_MARKERS = ('if total == 0:', 'if total is None and not had_error:')
ALIBABA_MARKERS = ('totals_reported = False', 'if not totals_reported:',
                   'coverage[\'expected_total\'] = None')
PIPELINE_MARKERS = ('page_cap_hit', 'a scan that hit its page safety cap cannot claim complete')
POSITIVE_TOTAL = {
    'p1_platform_workday.py': 'if total and offset >= int(total):',
    'p1_platform_orc.py': "if coverage.get('site_total_china') and offset >=",
    'p1_platform_phenom.py': 'if total and offset >= int(total):',
    'p1_platform_eightfold.py': 'if total and start >= int(total):',
    'p1_foreign_01.py': 'if isinstance(total_page, int) and total_page > 0 and page >= total_page:',
}
# Adapters whose page loop is bounded by a site-reported page number only; the audit
# cleared them (evidence in RECEIPT-collector-next-6.md).
CLEARED = ('p1_meituan_public.py', 'p1_sources_01_10.py', 'p1_sources_11_20.py',
           'p1_sources_31_40.py', 'p1_sources_41_50.py', 'p1_banks_01.py',
           'p1_bytedance_public.py', 'p1_platform_51job.py', 'p1_platform_beisen.py',
           'p1_platform_icims.py', 'p1_platform_moka.py')


def read_config():
    config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    declared = {}
    for section, entries in config.items():
        if section == '_README' or not isinstance(entries, dict):
            continue
        for key, entry in entries.items():
            if str(key).startswith('_'):
                continue
            name = entry if isinstance(entry, str) else str((entry or {}).get('name') or '')
            parked = isinstance(entry, dict) and entry.get('enabled') is False
            declared.setdefault(section, []).append((key, name, entry, parked))
    return declared


def markers(path, needles):
    source = (COLLECTOR / path).read_text(encoding='utf-8') if path else ''
    return {needle: needle in source for needle in needles}


def main():
    declared = read_config()
    tupu = declared.get('tupu360', [])
    tupu_careersite = [row for row in tupu if 'careersite tenant' in str(
        (row[2] or {}).get('note') if isinstance(row[2], dict) else '')]
    extra = [name for name in p.DEFAULT_COMPANIES if name not in p.COMPANIES]
    blocks = []
    for name in extra:
        module = p.REGISTRY[name]
        if not blocks or blocks[-1][0] != module:
            blocks.append([module, 0])
        blocks[-1][1] += 1
    per_module = Counter(p.REGISTRY.values())
    pipeline_source = (COLLECTOR / 'p1_pipeline.py').read_text(encoding='utf-8')

    result = {
        'default_total': len(p.DEFAULT_COMPANIES),
        'duplicates': len(p.DEFAULT_COMPANIES) - len(set(p.DEFAULT_COMPANIES)),
        'registry_total': len(p.REGISTRY),
        'registry_covers_default': set(p.REGISTRY) == set(p.DEFAULT_COMPANIES),
        'module_count': len(per_module),
        'blocks_tail': [module for module, _ in blocks][-5:],
        'per_module_top': dict(sorted(per_module.items(), key=lambda item: -item[1])[:8]),
        'tupu360': {
            'declared_rows': len(tupu),
            'careersite_rows': len(tupu_careersite),
            'parked_rows': sum(1 for row in tupu if row[3]),
            'enabled_rows': [row[0] for row in tupu if not row[3]],
            'missing_blocked_reason': [row[0] for row in tupu
                                       if not (row[2] or {}).get('blocked_reason')],
            'readme_mentions_robots': 'Disallow: /' in str(
                json.loads(CONFIG_PATH.read_text(encoding='utf-8'))['tupu360']['_README']),
            'readme_mentions_enable_flip': 'enabled' in str(
                json.loads(CONFIG_PATH.read_text(encoding='utf-8'))['tupu360']['_README']),
            'registers_in_default': sum(1 for name in p.DEFAULT_COMPANIES
                                        if p.REGISTRY[name] == TUPU360),
        },
        'icims_registers': sum(1 for name in p.DEFAULT_COMPANIES if p.REGISTRY[name] == ICIMS),
        'moka_markers': markers('p1_platform_moka.py', MOKA_MARKERS),
        'tupu360_markers': markers('p1_platform_tupu360.py', TUPU360_MARKERS),
        'successfactors_markers': markers('p1_platform_successfactors.py', SF_MARKERS),
        'avature_markers': markers('p1_platform_avature.py', AVATURE_MARKERS),
        'netease_markers': markers('p1_netease_public.py', NETEASE_MARKERS),
        'alibaba_markers': markers('alibaba_headless.py', ALIBABA_MARKERS),
        'pipeline_markers': {needle: needle in pipeline_source for needle in PIPELINE_MARKERS},
        'positive_total_guards': {path: needle in (COLLECTOR / path).read_text(encoding='utf-8')
                                  for path, needle in POSITIVE_TOTAL.items()},
        'cleared_adapters_present': [name for name in CLEARED if (COLLECTOR / name).is_file()],
        'rotation_default': p.PLATFORM_ROTATION_DEFAULT,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    assert result['default_total'] == DEFAULT_TOTAL, result['default_total']
    assert result['duplicates'] == 0, result['duplicates']
    assert result['registry_total'] == DEFAULT_TOTAL
    assert result['registry_covers_default'] is True
    assert result['module_count'] == 21, result['module_count']
    # tupu360 ships the full-site configuration with every single row parked.
    assert result['tupu360']['declared_rows'] == 68, result['tupu360']['declared_rows']
    assert result['tupu360']['careersite_rows'] == 60, result['tupu360']['careersite_rows']
    assert result['tupu360']['enabled_rows'] == [], result['tupu360']['enabled_rows']
    assert result['tupu360']['parked_rows'] == 68
    assert result['tupu360']['missing_blocked_reason'] == []
    assert result['tupu360']['readme_mentions_robots'] is True
    assert result['tupu360']['readme_mentions_enable_flip'] is True
    assert result['tupu360']['registers_in_default'] == 0
    assert result['icims_registers'] == 0
    # every merged/audited marker must be present.
    for group in ('moka_markers', 'tupu360_markers', 'successfactors_markers',
                  'avature_markers', 'netease_markers', 'alibaba_markers',
                  'pipeline_markers'):
        missing = [name for name, present in result[group].items() if not present]
        assert not missing, (group, missing)
    missing = [path for path, present in result['positive_total_guards'].items() if not present]
    assert not missing, missing
    assert len(result['cleared_adapters_present']) == len(CLEARED)
    # no rotation: the whole 1069-company set runs every day.
    assert result['rotation_default'] == 1
    print('PROBE OK')


if __name__ == '__main__':
    main()
