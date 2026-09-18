#!/usr/bin/env python3
"""Zero-network probe for the collector-next-3 merge (20260918k).

Verifies the merged 20260918i (字节跳动/美的集团) + 20260918j (foreign batch 2)
scheduling without any adapter call or HTTP request:

* default set size (20260918h's 924 + the 24 new names) and block order,
* every adapter module declares a host group iff it is platform-gated,
* Dayee (hotjob.cn) and 51job join the platform gate, 字节跳动/美的集团 stay
  daily dedicated adapters (own gate group, three scopes),
* the Big Four and the new foreign companies are inside the default set.

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

H_BASELINE = 924
DAYEE_MODULE = 'qiuzhao.collector.p1_foreign_01'
JOB51_MODULE = 'qiuzhao.collector.p1_platform_51job'
BYTEDANCE_MODULE = 'qiuzhao.collector.p1_bytedance_public'
MIDEA_MODULE = 'qiuzhao.collector.p1_midea_public'
NEW_FOREIGN = ('基恩士', '安永', '普华永道', '高露洁棕榄', '德州仪器', '拜耳', '特斯拉',
               '大众汽车集团(CARIAD)', '达能', '达美乐中国', '伊顿', '阿特拉斯科普柯',
               '神龙汽车', '英特尔', '德勤', '康师傅', 'ZARA', '广汽集团', '益海嘉里',
               '迪卡侬', 'ZURU', '百事')
BIG_FOUR = ('德勤', '安永', '普华永道', '毕马威')


def main():
    extra = [name for name in p.DEFAULT_COMPANIES if name not in p.COMPANIES]
    blocks = []
    for name in extra:
        module = p.REGISTRY[name]
        if not blocks or blocks[-1][0] != module:
            blocks.append([module, 0])
        blocks[-1][1] += 1
    per_module = Counter(p.REGISTRY.values())
    dayee = [name for name in p.DEFAULT_COMPANIES if p.REGISTRY[name] == DAYEE_MODULE]
    job51 = [name for name in p.DEFAULT_COMPANIES if p.REGISTRY[name] == JOB51_MODULE]
    platform_modules = sorted(m for m in set(p.REGISTRY.values()) if m in p.PLATFORM_MODULES)
    daily_other = [name for name in p.DEFAULT_COMPANIES
                   if name not in p.COMPANIES and p.REGISTRY[name] not in p.ROTATING_MODULES]
    day = dt.date(2026, 9, 18)
    selected_default = p.companies_for_day(p.DEFAULT_COMPANIES, p.PLATFORM_ROTATION_DEFAULT, day=day)

    result = {
        'hardcoded': len(p.COMPANIES),
        'h_baseline': H_BASELINE,
        'default_total': len(p.DEFAULT_COMPANIES),
        'added_since_h': len(p.DEFAULT_COMPANIES) - H_BASELINE,
        'extra': len(extra),
        'duplicates': len(p.DEFAULT_COMPANIES) - len(set(p.DEFAULT_COMPANIES)),
        'blocks': blocks,
        'per_module': dict(sorted(per_module.items(), key=lambda item: -item[1])),
        'bytedance': {'module': p.REGISTRY.get('字节跳动'),
                      'in_default': '字节跳动' in p.DEFAULT_COMPANIES,
                      'scopes': p.company_scopes('字节跳动'),
                      'gate_group': p.platform_group('字节跳动'),
                      'platform_gated': p.REGISTRY.get('字节跳动') in p.PLATFORM_MODULES},
        'midea': {'module': p.REGISTRY.get('美的集团'),
                  'in_default': '美的集团' in p.DEFAULT_COMPANIES,
                  'scopes': p.company_scopes('美的集团'),
                  'gate_group': p.platform_group('美的集团'),
                  'platform_gated': p.REGISTRY.get('美的集团') in p.PLATFORM_MODULES},
        'big_four': {name: p.REGISTRY.get(name) for name in BIG_FOUR},
        'new_foreign_in_default': {name: name in p.DEFAULT_COMPANIES for name in NEW_FOREIGN},
        'dayee_total': len(dayee),
        'dayee_groups': sorted({p.platform_group(name) for name in dayee}),
        'job51_total': len(job51),
        'job51_groups': sorted({p.platform_group(name) for name in job51}),
        'platform_modules_without_group': sorted(
            m for m in platform_modules if m not in p.PLATFORM_HOST_GROUPS),
        'gate_groups': sorted(set(p.PLATFORM_HOST_GROUPS.values())),
        'rotation_default': p.PLATFORM_ROTATION_DEFAULT,
        'default_select_full': selected_default == p.DEFAULT_COMPANIES,
        'probe_day_total': len(selected_default),
        'probe_day_other_daily': sum(1 for name in selected_default if name in daily_other),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    assert result['hardcoded'] == 50
    assert result['h_baseline'] == 924
    assert result['default_total'] == 948, result['default_total']
    assert result['added_since_h'] == 24
    assert result['duplicates'] == 0
    assert len(p.REGISTRY) == len(p.DEFAULT_COMPANIES)
    # 20260918i block stays contiguous and is followed by the 20260918j blocks.
    block_modules = [module for module, _ in blocks]
    assert block_modules[-5] == 'qiuzhao.collector.p1_feishu_public', block_modules[-5]
    assert block_modules[-4:] == [BYTEDANCE_MODULE, MIDEA_MODULE, DAYEE_MODULE,
                                  JOB51_MODULE], block_modules[-4:]
    # 字节跳动 / 美的集团: daily dedicated adapters, three scopes, own gate group.
    assert result['bytedance']['module'] == BYTEDANCE_MODULE
    assert result['midea']['module'] == MIDEA_MODULE
    for key in ('bytedance', 'midea'):
        assert result[key]['in_default'] is True, key
        assert result[key]['scopes'] == ['campus', 'intern', 'social'], key
        assert result[key]['platform_gated'] is False, key
    assert result['bytedance']['gate_group'] == 'company:字节跳动'
    assert result['midea']['gate_group'] == 'company:美的集团'
    # 四大 + 外企第二批新增全部在默认集合内。
    assert result['big_four'] == {'德勤': DAYEE_MODULE, '安永': 'qiuzhao.collector.p1_platform_moka',
                                  '普华永道': 'qiuzhao.collector.p1_platform_moka',
                                  '毕马威': 'qiuzhao.collector.p1_platform_moka'}
    missing = [name for name, present in result['new_foreign_in_default'].items() if not present]
    assert not missing, missing
    # 大易/51job 归平台模块，同 host 一个 gate 组，三 scope。
    assert result['dayee_total'] == 7
    assert result['dayee_groups'] == ['hotjob.cn']
    assert result['job51_total'] == 1
    assert result['job51_groups'] == ['51job.com']
    for name in dayee + job51:
        assert p.company_scopes(name) == ['campus', 'intern', 'social'], name
    assert DAYEE_MODULE not in p.ROTATING_MODULES and JOB51_MODULE not in p.ROTATING_MODULES
    # 每个平台模块都必须有 host 组，否则同平台并发会被误当成独立公司。
    assert result['platform_modules_without_group'] == []
    assert 'hotjob.cn' in result['gate_groups'] and '51job.com' in result['gate_groups']
    # 不轮转：默认全选 948 家。
    assert result['rotation_default'] == 1
    assert result['default_select_full'] is True
    assert result['probe_day_total'] == len(p.DEFAULT_COMPANIES)
    assert result['probe_day_other_daily'] == len(daily_other)
    print('PROBE OK')


if __name__ == '__main__':
    main()
