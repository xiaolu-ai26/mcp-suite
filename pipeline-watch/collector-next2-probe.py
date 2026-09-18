#!/usr/bin/env python3
"""Zero-network probe for the collector-next-2 scheduling changes (20260918h).

Imports the pipeline (no adapter call, no HTTP) and prints the default set size,
per-block composition, scope policy, rotation default and the next-day fairness
ordering, then asserts the invariants the daily chain relies on. Exit 0 = all
invariants hold.
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
    selected_default = p.companies_for_day(p.DEFAULT_COMPANIES, groups, day=day)
    selected_2 = p.companies_for_day(p.DEFAULT_COMPANIES, 2, day=day)

    # Fairness: 大疆 attempted most recently, 拼多多 long ago, 小米 never reached.
    fairness_last = {'大疆/campus': 2000.0, '拼多多/campus': 1000.0}
    fairness_order = [chain['company'] for chain in p.plan_chains(
        ['大疆', '拼多多', '小米'], ['campus'], {}, last_attempt=fairness_last)]
    failed_queue = {'拼多多/campus': {'company': '拼多多', 'scope': 'campus',
                                      'consecutive_days': 1, 'reason': 'timeout'}}
    failed_order = [chain['company'] for chain in p.plan_chains(
        ['大疆', '拼多多'], ['campus'], failed_queue,
        last_attempt={'大疆/campus': 1000.0, '拼多多/campus': 2000.0})]

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
        'default_select_full': selected_default == p.DEFAULT_COMPANIES,
        'rotation2_total': len(selected_2),
        'rotating_total': len(rotating),
        'rotation2_buckets': dict(sorted(Counter(
            p.platform_rotation_group(name, 2) for name in rotating).items())),
        'probe_day': day.isoformat(),
        'probe_day_total': len(selected_default),
        'probe_day_hardcoded': sum(1 for name in selected_default if name in p.COMPANIES),
        'probe_day_other_daily': sum(1 for name in selected_default if name in daily_other),
        'probe_day_rotating': len(selected_default) - sum(1 for name in selected_default if name in p.COMPANIES)
                              - sum(1 for name in selected_default if name in daily_other),
        'fairness_order': fairness_order,
        'failed_order': failed_order,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert result['duplicates'] == 0
    assert result['hardcoded'] == 50
    assert result['default_total'] == 924
    assert result['hardcoded_scopes'] == ['campus', 'intern', 'social']
    for name, scopes in result['platform_scopes'].items():
        assert scopes == ['campus', 'intern', 'social'], name
    assert result['ali_scopes'] == ['campus', 'intern', 'social']
    assert result['tencent_music_scopes'] == ['campus', 'intern', 'social']
    # 站长口径：不轮转，默认全选 924 家。
    assert result['rotation_default'] == 1
    assert result['default_select_full'] is True
    assert result['probe_day_total'] == len(p.DEFAULT_COMPANIES)
    assert result['probe_day_hardcoded'] == 50
    assert result['probe_day_other_daily'] == len(daily_other)
    assert result['probe_day_rotating'] == len(rotating)
    # 轮转参数保留：N=2 时仍是真子集，硬编码与每天跑组恒在。
    assert result['rotation2_total'] < len(p.DEFAULT_COMPANIES)
    assert sum(result['rotation2_buckets'].values()) == len(rotating)
    assert len(result['rotation2_buckets']) == 2
    # 公平排序：未尝试的 小米 最前，其次较早尝试的 拼多多，最近尝试的 大疆 最后。
    assert result['fairness_order'] == ['小米', '拼多多', '大疆']
    # 失败单元优先：拼多多虽尝试更晚，但在重试队列里，排在 大疆 前。
    assert result['failed_order'] == ['拼多多', '大疆']
    print('PROBE OK')


if __name__ == '__main__':
    main()
