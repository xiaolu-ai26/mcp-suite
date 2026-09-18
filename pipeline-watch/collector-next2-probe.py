#!/usr/bin/env python3
"""Zero-network probe for the collector-next-2 scheduling changes.

Imports the pipeline (no adapter call, no HTTP) and prints the default set size,
per-block composition, scope policy and rotation buckets, then asserts the
invariants the daily chain relies on. Exit 0 = all invariants hold.
"""
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qiuzhao.collector import p1_pipeline as p  # noqa: E402


def main():
    extra = [name for name in p.DEFAULT_COMPANIES if name not in p.COMPANIES]
    blocks = []
    for name in extra:
        module = p.REGISTRY[name]
        if not blocks or blocks[-1][0] != module:
            blocks.append([module, 0])
        blocks[-1][1] += 1
    groups = p.PLATFORM_ROTATION_DEFAULT
    rotating = [name for name in p.DEFAULT_COMPANIES
                if name not in p.COMPANIES and p.REGISTRY[name] in p.ROTATING_MODULES]
    daily_other = [name for name in p.DEFAULT_COMPANIES
                   if name not in p.COMPANIES and p.REGISTRY[name] not in p.ROTATING_MODULES]
    day = dt.date(2026, 9, 18)
    selected = p.companies_for_day(p.DEFAULT_COMPANIES, groups, day=day)
    result = {
        'hardcoded': len(p.COMPANIES),
        'default_total': len(p.DEFAULT_COMPANIES),
        'extra': len(extra),
        'duplicates': len(p.DEFAULT_COMPANIES) - len(set(p.DEFAULT_COMPANIES)),
        'blocks': blocks,
        'hardcoded_scopes': p.company_scopes('大疆'),
        'platform_scopes': {name: p.company_scopes(name)
                            for name in ('中信建投', '小天才', '英伟达', '交通银行')},
        'ali_scopes': p.company_scopes('阿里巴巴'),
        'tencent_music_scopes': p.company_scopes('腾讯音乐'),
        'rotation_default': groups,
        'rotating_total': len(rotating),
        'rotation_buckets': dict(sorted(Counter(
            p.platform_rotation_group(name, groups) for name in rotating).items())),
        'probe_day': day.isoformat(),
        'probe_day_total': len(selected),
        'probe_day_hardcoded': sum(1 for name in selected if name in p.COMPANIES),
        'probe_day_other_daily': sum(1 for name in selected if name in daily_other),
        'probe_day_rotating': len(selected) - sum(1 for name in selected if name in p.COMPANIES)
                              - sum(1 for name in selected if name in daily_other),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert result['duplicates'] == 0
    assert result['hardcoded'] == 50
    assert result['default_total'] > 900
    assert result['hardcoded_scopes'] == ['campus', 'intern', 'social']
    for name, scopes in result['platform_scopes'].items():
        assert scopes == ['campus', 'intern'], name
    assert result['ali_scopes'] == ['campus', 'intern', 'social']
    assert result['tencent_music_scopes'] == ['campus', 'intern', 'social']
    assert sum(result['rotation_buckets'].values()) == len(rotating)
    assert len(result['rotation_buckets']) == groups
    assert result['probe_day_hardcoded'] == 50
    assert result['probe_day_other_daily'] == len(daily_other)
    assert set(p.COMPANIES) <= set(selected)
    assert set(daily_other) <= set(selected)
    print('PROBE OK')


if __name__ == '__main__':
    main()
