#!/usr/bin/env python3
"""Zero-network probe for the collector-next-5 merge (20260920a).

Checks the merge of three lines on top of feat/collector-next-4:
  * feat/multi-entrance  -> 13 more companies via existing adapters (1056 -> 1069)
  * feat/normalize-adjust -> narrowed company-name normalization (i wins over g)
  * fix/p1-winlock       -> the shipped Windows publish-lock hotfix must survive

No adapter call, no HTTP request, no import of anything that touches the network.

Exit 0 = every invariant holds.
"""
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
G_TOTAL = 1056
CONFIG_PATH = ROOT / 'qiuzhao' / 'collector' / 'p1_platform_companies.json'
P1_PATH = ROOT / 'qiuzhao' / 'collector' / 'p1_pipeline.py'
EIGHTFOLD = 'qiuzhao.collector.p1_platform_eightfold'
PHENOM = 'qiuzhao.collector.p1_platform_phenom'
ORC = 'qiuzhao.collector.p1_platform_orc'
ICIMS = 'qiuzhao.collector.p1_platform_icims'
TUPU360 = 'qiuzhao.collector.p1_platform_tupu360'
MOKA = 'qiuzhao.collector.p1_platform_moka'
WORKDAY = 'qiuzhao.collector.p1_platform_workday'
NEW_MODULES = (EIGHTFOLD, PHENOM, 'qiuzhao.collector.p1_platform_avature',
               ICIMS, ORC, TUPU360)
SAME_NAME_OWNERS = {
    '惠普': EIGHTFOLD,
    '应用材料': EIGHTFOLD,
    '飞利浦': PHENOM,
    '强生': WORKDAY,
    '毕马威': MOKA,
}
PARKED_WORKDAY = ('惠普', '应用材料', '飞利浦')
TUPU360_PARKED = ('IQVIA 艾昆纬', '礼来', '舍弗勒', '宝马', '茵梦达')
MULTI_TENANT = {          # h: one company row merging several tenants
    '雀巢': ('moka', 'nestlezgc/91899', ['nestlezgc/91899', 'nestlezgc/91898',
                                         'nestlezgc/124026']),
    '安永': ('moka', 'ey/166374', ['ey/166374', 'ey/102474']),
}
# i narrowed normalization: these must NOT be rewritten any more.
NORMALIZATION_KEPT = ('网易互娱', '网易互联网', '中国移动通信',
                      '中国联合网络通信', '中国邮政')
# hotfix markers: in-process lock + per-unit convergence of publish() failures.
HOTFIX_MARKERS = ('_publish_thread_lock', 'with _publish_thread_lock',
                  'fcntl.LOCK_UN', "entry['publish_error']",
                  "return 'publish'", "status['success'] = all(")


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


def main():
    source = P1_PATH.read_text(encoding='utf-8')
    declared = read_config()
    extra = [name for name in p.DEFAULT_COMPANIES if name not in p.COMPANIES]
    blocks = []
    for name in extra:
        module = p.REGISTRY[name]
        if not blocks or blocks[-1][0] != module:
            blocks.append([module, 0])
        blocks[-1][1] += 1
    per_module = Counter(p.REGISTRY.values())
    selected_default = p.companies_for_day(p.DEFAULT_COMPANIES, p.PLATFORM_ROTATION_DEFAULT)

    rewritten = []
    for section, rows in declared.items():
        for key, name, entry, _ in rows:
            canonical, basis = canonical_of(name)
            if canonical != name:
                rewritten.append({'section': section, 'key': key, 'name': name,
                                  'canonical': canonical, 'basis': basis})

    multi_tenant = {}
    for name, (section, key, tenants) in MULTI_TENANT.items():
        row = next((item for item in declared.get(section, []) if item[0] == key), None)
        assert row is not None, (name, section, key)
        sites = row[2].get('sites') or []
        multi_tenant[name] = {
            'section': section, 'key': key,
            'tenants': [s.rstrip('/').split('/')[-2] + '/' + s.rstrip('/').split('/')[-1]
                        for s in sites],
            'site_count': len(sites),
            'enabled': row[2].get('enabled', True),
        }
        assert row[2].get('enabled', True) is not False, name

    result = {
        'default_total': len(p.DEFAULT_COMPANIES),
        'k_baseline': K_BASELINE,
        'g_total': G_TOTAL,
        'added_since_g': len(p.DEFAULT_COMPANIES) - G_TOTAL,
        'duplicates': len(p.DEFAULT_COMPANIES) - len(set(p.DEFAULT_COMPANIES)),
        'registry_total': len(p.REGISTRY),
        'registry_covers_default': set(p.REGISTRY) == set(p.DEFAULT_COMPANIES),
        'blocks': blocks,
        'per_module': dict(sorted(per_module.items(), key=lambda item: -item[1])),
        'module_count': len(per_module),
        'same_name_owners': {name: p.REGISTRY.get(name) for name in SAME_NAME_OWNERS},
        'multi_tenant': multi_tenant,
        'tupu360_registers': sum(1 for name in p.DEFAULT_COMPANIES if p.REGISTRY[name] == TUPU360),
        'icims_registers': sum(1 for name in p.DEFAULT_COMPANIES if p.REGISTRY[name] == ICIMS),
        'parked_workday_out': [name for name in PARKED_WORKDAY if name not in workday.COMPANIES],
        'tupu360_parked_out': [name for name in TUPU360_PARKED if name not in p.DEFAULT_COMPANIES],
        'normalization_table': table_info(),
        'normalization_kept': {name: canonical_of(name) for name in NORMALIZATION_KEPT},
        'contract_alias': canonical_of('腾讯科技（深圳）有限公司'),
        'config_names_rewritten': rewritten,
        'hotfix_markers': {marker: marker in source for marker in HOTFIX_MARKERS},
        'rotation_default': p.PLATFORM_ROTATION_DEFAULT,
        'default_select_full': selected_default == p.DEFAULT_COMPANIES,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    assert result['default_total'] == 1069, result['default_total']
    assert result['duplicates'] == 0, result['duplicates']
    assert result['registry_total'] == 1069
    assert result['registry_covers_default'] is True
    assert result['added_since_g'] == 13, result['added_since_g']
    assert result['module_count'] == 21, result['module_count']
    # merge order is append-only: the six g adapters keep their block positions.
    block_modules = [module for module, _ in blocks]
    assert block_modules[-4:] == [EIGHTFOLD, PHENOM, 'qiuzhao.collector.p1_platform_avature', ORC], block_modules[-4:]
    assert 'qiuzhao.collector.p1_platform_51job' in block_modules
    assert 'qiuzhao.collector.p1_bytedance_public' in block_modules
    # h: the multi-tenant rows survive with every tenant and stay enabled.
    for name, expected in multi_tenant.items():
        section, key, tenants = MULTI_TENANT[name]
        assert expected['site_count'] == len(tenants), (name, expected)
        assert sorted(expected['tenants']) == sorted(tenants), (name, expected['tenants'])
    # i wins over g: no brand/group folding is back.
    for name in NORMALIZATION_KEPT:
        canonical, basis = result['normalization_kept'][name]
        assert canonical == name, name
        assert basis in ('keep', 'brand'), (name, basis)
    assert result['contract_alias'] == ('腾讯', 'alias'), result['contract_alias']
    assert result['config_names_rewritten'] == [], result['config_names_rewritten']
    # same-name conflicts keep the measured owners.
    for name, module in SAME_NAME_OWNERS.items():
        assert p.REGISTRY[name] == module, (name, p.REGISTRY[name])
        assert p.company_scopes(name) == ['campus', 'intern', 'social'], name
    assert result['parked_workday_out'] == list(PARKED_WORKDAY)
    assert result['tupu360_parked_out'] == list(TUPU360_PARKED)
    assert result['tupu360_registers'] == 0 and result['icims_registers'] == 0
    # fix/p1-winlock: all hotfix markers present in the merged source.
    missing = [marker for marker, present in result['hotfix_markers'].items() if not present]
    assert not missing, missing
    # no rotation: the whole 1069-company set is selected every day.
    assert result['rotation_default'] == 1
    assert result['default_select_full'] is True
    print('PROBE OK')


if __name__ == '__main__':
    main()
