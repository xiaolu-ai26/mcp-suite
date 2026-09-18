#!/usr/bin/env python3
"""Zero-network probe for foreign ATS batch A (20260919b).

Verifies the Eightfold / Phenom registration without any adapter call or HTTP
request:

* the default set is the 948 of 20260918k plus exactly the 13 new tenants,
* both new modules are platform-gated with their own host group and three scopes,
* every configured tenant resolves to its own module and no name is shared,
* the config sections carry a tenant entry for every registry name and the
  documentation keys are never mistaken for a company,
* neither module is in ROTATING_MODULES (every company runs every day).

Exit 0 = every invariant holds.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qiuzhao.collector import p1_pipeline as p  # noqa: E402
from qiuzhao.collector import p1_platform_eightfold as eightfold  # noqa: E402
from qiuzhao.collector import p1_platform_phenom as phenom  # noqa: E402

K_BASELINE = 948
EIGHTFOLD_MODULE = 'qiuzhao.collector.p1_platform_eightfold'
PHENOM_MODULE = 'qiuzhao.collector.p1_platform_phenom'
EIGHTFOLD = ('惠普', '微软', '高通', '应用材料', '泛林')
PHENOM = ('宝洁', '玛氏', '罗氏', '波士顿咨询', 'ABB', '飞利浦', '默沙东', '思科')


def main():
    result = {}
    extra = [name for name in p.DEFAULT_COMPANIES if name not in p.COMPANIES]
    result['default_total'] = len(p.DEFAULT_COMPANIES)
    result['registry_total'] = len(p.REGISTRY)
    result['unique_names'] = len(set(p.DEFAULT_COMPANIES)) == len(p.DEFAULT_COMPANIES)

    for name in (*EIGHTFOLD, *PHENOM):
        assert name in p.REGISTRY, name
        assert name not in p.COMPANIES, name
    assert all(p.REGISTRY[n] == EIGHTFOLD_MODULE for n in EIGHTFOLD)
    assert all(p.REGISTRY[n] == PHENOM_MODULE for n in PHENOM)
    assert len(p.DEFAULT_COMPANIES) == K_BASELINE + len(EIGHTFOLD) + len(PHENOM)
    assert result['registry_total'] == result['default_total'] == K_BASELINE + 13
    assert result['unique_names'] is True
    # The two new blocks are appended last, so no earlier block moved.
    assert extra[-len(EIGHTFOLD) - len(PHENOM):] == [*EIGHTFOLD, *PHENOM], extra[-15:]

    # Platform gating: one host group per platform family, three scopes each.
    assert p.platform_group('惠普') == p.platform_group('微软') == 'eightfold'
    assert p.platform_group('宝洁') == p.platform_group('思科') == 'phenom'
    for name in (*EIGHTFOLD, *PHENOM):
        assert p.company_scopes(name) == ['campus', 'intern', 'social'], name
        assert p.REGISTRY[name] in p.PLATFORM_MODULES, name
        assert p.REGISTRY[name] not in p.ROTATING_MODULES, name
    assert EIGHTFOLD_MODULE not in p.ROTATING_MODULES
    assert PHENOM_MODULE not in p.ROTATING_MODULES

    # Every platform module needs a host group, else same-host concurrency is
    # mistaken for independent companies.
    without_group = sorted({m for m in p.PLATFORM_MODULES if m not in p.PLATFORM_HOST_GROUPS})
    assert without_group == [], without_group
    assert 'eightfold' in set(p.PLATFORM_HOST_GROUPS.values())
    assert 'phenom' in set(p.PLATFORM_HOST_GROUPS.values())

    # Config sections: every declared tenant is registered, `_note` is not a company.
    config = json.loads(
        (Path(p.__file__).with_name('p1_platform_companies.json')).read_text(encoding='utf-8'))
    for section, module, expected in (('eightfold', EIGHTFOLD_MODULE, EIGHTFOLD),
                                      ('phenom', PHENOM_MODULE, PHENOM)):
        entries = config[section]
        declared = [v if isinstance(v, str) else str((v or {}).get('name') or '')
                    for k, v in entries.items() if not str(k).startswith('_')]
        assert sorted(declared) == sorted(expected), (section, declared)
        assert '_note' in entries
        for name in declared:
            assert p.REGISTRY[name] == module, (section, name)
    assert '_note' not in p.REGISTRY
    assert not any(str(n).startswith('_') for n in p.REGISTRY)

    # Registry names never collide across the whole default set.
    duplicates = [n for n, c in Counter(p.DEFAULT_COMPANIES).items() if c > 1]
    assert duplicates == [], duplicates
    result['probe_ok'] = True
    print('PROBE OK', json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
