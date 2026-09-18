#!/usr/bin/env python3
"""Zero-network probe for the collector-next-4 merge (20260919g).

Verifies the merged foreign ATS lines (A: Eightfold/Phenom, B: Avature/ORC/iCIMS,
C: tupu360), the foreign-discovery config and the company-name normalization
without any adapter call or HTTP request:

* default set size (20260918k's 948 + 13 + 17 + 82 - 4 duplicates - 5 parked
  tupu360 tenants = 1056) and the append-only block order,
* every new adapter module is platform-gated, declares a host group and exposes
  the collect contract,
* the same-company conflicts resolved by measurement: 惠普/应用材料 -> Eightfold,
  飞利浦 -> Phenom, 强生 -> Workday, 毕马威 -> the shipped moka tenant,
* iCIMS and tupu360 register no company (robots), the parked rows stay parked,
* company names in the merged config are normalization fixed points.

Exit 0 = every invariant holds.
"""
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qiuzhao.collector import p1_pipeline as p  # noqa: E402
from qiuzhao.collector import p1_platform_workday as workday  # noqa: E402
from qiuzhao.company_names import canonical_of, table_info  # noqa: E402

K_BASELINE = 948
CONFIG_PATH = ROOT / 'qiuzhao' / 'collector' / 'p1_platform_companies.json'
EIGHTFOLD = 'qiuzhao.collector.p1_platform_eightfold'
PHENOM = 'qiuzhao.collector.p1_platform_phenom'
AVATURE = 'qiuzhao.collector.p1_platform_avature'
ICIMS = 'qiuzhao.collector.p1_platform_icims'
ORC = 'qiuzhao.collector.p1_platform_orc'
TUPU360 = 'qiuzhao.collector.p1_platform_tupu360'
NEW_MODULES = (EIGHTFOLD, PHENOM, AVATURE, ICIMS, ORC, TUPU360)
NEW_HOST_GROUPS = ('eightfold', 'phenom', 'avature', 'icims', 'oraclecloud', 'tupu360.com')
SAME_NAME_OWNERS = {
    '惠普': EIGHTFOLD,
    '应用材料': EIGHTFOLD,
    '飞利浦': PHENOM,
    '强生': 'qiuzhao.collector.p1_platform_workday',
    '毕马威': 'qiuzhao.collector.p1_platform_moka',
}
PARKED = ('惠普', '应用材料', '飞利浦')          # parked workday rows
TUPU360_PARKED = ('IQVIA 艾昆纬', '礼来', '舍弗勒', '宝马', '茵梦达')
FOREIGN_LINES = ('微软', '宝洁', '西门子', '霍尼韦尔', '泛林', '贝恩', '万豪')


def main():
    extra = [name for name in p.DEFAULT_COMPANIES if name not in p.COMPANIES]
    blocks = []
    for name in extra:
        module = p.REGISTRY[name]
        if not blocks or blocks[-1][0] != module:
            blocks.append([module, 0])
        blocks[-1][1] += 1
    per_module = Counter(p.REGISTRY.values())
    platform_modules = sorted(m for m in set(p.REGISTRY.values()) if m in p.PLATFORM_MODULES)
    day = dt.date(2026, 9, 19)
    selected_default = p.companies_for_day(p.DEFAULT_COMPANIES, p.PLATFORM_ROTATION_DEFAULT, day=day)
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
            declared.setdefault(section, []).append((key, name, parked))
    tupu_rows = declared.get('tupu360', [])
    renamed = []
    for section, rows in declared.items():
        for key, name, _ in rows:
            canonical, basis = canonical_of(name)
            if canonical != name:
                renamed.append({'section': section, 'key': key, 'name': name,
                                'canonical': canonical, 'basis': basis})

    result = {
        'hardcoded': len(p.COMPANIES),
        'k_baseline': K_BASELINE,
        'default_total': len(p.DEFAULT_COMPANIES),
        'added_since_k': len(p.DEFAULT_COMPANIES) - K_BASELINE,
        'duplicates': len(p.DEFAULT_COMPANIES) - len(set(p.DEFAULT_COMPANIES)),
        'blocks': blocks,
        'per_module': dict(sorted(per_module.items(), key=lambda item: -item[1])),
        'same_name_owners': {name: p.REGISTRY.get(name) for name in SAME_NAME_OWNERS},
        'tupu360_rows': len(tupu_rows),
        'tupu360_registers': sum(1 for _, _, parked in tupu_rows if not parked),
        'tupu360_all_parked': all(parked for _, _, parked in tupu_rows),
        'icims_registers': sum(1 for name in p.DEFAULT_COMPANIES if p.REGISTRY[name] == ICIMS),
        'parked_workday_out': [name for name in PARKED if name not in workday.COMPANIES],
        'tupu360_parked_out': [name for name in TUPU360_PARKED if name not in p.DEFAULT_COMPANIES],
        'new_modules': {module: {'in_platform_modules': module in p.PLATFORM_MODULES,
                                 'host_group': p.PLATFORM_HOST_GROUPS.get(module),
                                 'registered': per_module.get(module, 0)}
                        for module in NEW_MODULES},
        'module_count': len(per_module),
        'platform_modules_without_group': sorted(
            m for m in platform_modules if m not in p.PLATFORM_HOST_GROUPS),
        'gate_groups': sorted(set(p.PLATFORM_HOST_GROUPS.values())),
        'new_host_groups': {group: group in set(p.PLATFORM_HOST_GROUPS.values())
                            for group in NEW_HOST_GROUPS},
        'rotation_default': p.PLATFORM_ROTATION_DEFAULT,
        'default_select_full': selected_default == p.DEFAULT_COMPANIES,
        'probe_day_total': len(selected_default),
        'config_sections': {section: len(rows) for section, rows in sorted(declared.items())},
        'config_rows': sum(len(rows) for rows in declared.values()),
        'names_normalization_would_rewrite': renamed,
        'normalization_table': table_info(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    assert result['hardcoded'] == 50
    assert result['k_baseline'] == 948
    assert result['default_total'] == 1056, result['default_total']
    assert result['duplicates'] == 0
    assert len(p.REGISTRY) == len(p.DEFAULT_COMPANIES)
    assert set(p.REGISTRY) == set(p.DEFAULT_COMPANIES)
    # Append-only order: the 20260919b/c blocks sit after 51job.
    block_modules = [module for module, _ in blocks]
    assert block_modules[-4:] == [EIGHTFOLD, PHENOM, AVATURE, ORC], block_modules[-4:]
    assert 'qiuzhao.collector.p1_platform_51job' in block_modules
    assert 'qiuzhao.collector.p1_bytedance_public' in block_modules
    # Every new adapter is platform-gated, has a host group and no rotation.
    for module in NEW_MODULES:
        info = result['new_modules'][module]
        assert info['in_platform_modules'] is True, module
        assert info['host_group'], module
        assert module not in p.ROTATING_MODULES, module
    assert result['platform_modules_without_group'] == []
    assert all(result['new_host_groups'].values()), result['new_host_groups']
    # Same-name conflicts: one owner each, three scopes, parked rows out.
    for name, module in SAME_NAME_OWNERS.items():
        assert p.REGISTRY[name] == module, (name, p.REGISTRY[name])
        assert p.company_scopes(name) == ['campus', 'intern', 'social'], name
    # The three workday rows are parked: gone from the adapter's own registry,
    # but the company names survive through the winning adapter.
    assert result['parked_workday_out'] == list(PARKED)
    for name in PARKED:
        assert name in p.DEFAULT_COMPANIES, name
    assert result['tupu360_parked_out'] == list(TUPU360_PARKED)
    assert result['tupu360_registers'] == 0
    assert result['tupu360_all_parked'] is True
    assert result['icims_registers'] == 0
    for module in (TUPU360, ICIMS):
        assert result['new_modules'][module]['registered'] == 0, module
    # Config rows are normalization fixed points (the brand set includes them).
    assert result['names_normalization_would_rewrite'] == [], result['names_normalization_would_rewrite']
    assert result['normalization_table']['platform_names'] >= result['config_rows']
    # All four foreign lines reach the daily set.
    missing = [name for name in FOREIGN_LINES if name not in p.DEFAULT_COMPANIES]
    assert not missing, missing
    # 不轮转：默认全选 1056 家。
    assert result['rotation_default'] == 1
    assert result['default_select_full'] is True
    assert result['probe_day_total'] == len(p.DEFAULT_COMPANIES)
    print('PROBE OK')


if __name__ == '__main__':
    main()
