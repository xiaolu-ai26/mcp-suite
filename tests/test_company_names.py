# -*- coding: utf-8 -*-
"""公司名规范化(qiuzhao/company_names.py + normalize 阶段)的单测。

覆盖:幂等、空值回填、别名、不确定保留原名、展示名不变量、统计口径、
别名表自检,以及 normalize_file 的"条数与 id 集合不变"。
"""
import json
from pathlib import Path

import pytest

from qiuzhao import company_names as CN
from qiuzhao.normalize import normalize_records, normalize_file, REPORTED_FIELDS


def row(rid, **fields):
    return {"id": rid, "job_title": "工程师", **fields}


# ---------------------------------------------------------------- 别名

@pytest.mark.parametrize("raw,expected", [
    ("腾讯科技（深圳）有限公司", "腾讯"),          # 任务点名样例
    ("北京小桔科技有限公司", "滴滴"),              # 任务点名样例
    ("大疆创新", "大疆"),                          # 任务点名样例
    ("达能（中国）", "达能"),
    ("中国邮政集团有限公司", "中国邮政"),
    ("国家能源投资集团有限责任公司", "国家能源集团"),
    ("北京石晶光电科技股份有限公司", "石晶光电"),
    ("招商局仁和人寿保险股份有限公司", "招商局仁和人寿"),
])
def test_alias_hits(raw, expected):
    assert CN.canonical_of(raw)[0] == expected


@pytest.mark.parametrize("raw,expected", [
    # 集团法人自己的法人后缀归一(精确别名)
    ("中国移动通信集团有限公司", "中国移动"),
    ("中国联合网络通信集团有限公司", "中国联通"),
])
def test_group_legal_entity_itself_is_normalized(raw, expected):
    assert CN.canonical_of(raw)[0] == expected


@pytest.mark.parametrize("raw", [
    # 站长 2026-09-19:子品牌/子公司/省分公司/事业部一律不并入母公司,保留原名
    "网易互娱",
    "网易互联网",
    "网易有道信息技术（北京）有限公司",
    "中国移动通信集团北京有限公司",
    "中国移动通信集团浙江有限公司",
    "中国移动通信有限公司在线营销服务中心",
    "中国移动通信集团设计院有限公司",
    "中国联合网络通信有限公司湖北省分公司",
    "中国联合网络通信有限公司软件研究院",
    "中国联合网络通信有限公司北京网络运营事业部",
    "中国邮政集团有限公司河北省分公司",
])
def test_group_and_subbrands_are_not_merged(raw):
    canonical, basis = CN.canonical_of(raw)
    assert canonical == raw, (raw, canonical)
    assert basis == "keep"


@pytest.mark.parametrize("raw,expected", [
    ("中国航天科工集团有限公司", "中国航天科工集团"),
    ("中国兵器装备集团有限公司", "中国兵器装备集团"),
    ("中国能源建设股份有限公司", "中国能源建设"),
    ("招商局集团有限公司", "招商局集团"),
    ("中国电信集团有限公司", "中国电信"),
    ("小米科技有限公司", "小米"),
    ("华为技术有限公司", "华为"),
])
def test_conservative_suffix_rules(raw, expected):
    assert CN.canonical_of(raw)[0] == expected


# ---------------------------------------------------------------- 不确定保留原名

@pytest.mark.parametrize("raw", [
    "塞浦路斯阿里斯托开发有限公司北京代表处",   # 名字里有"阿里"但不是阿里巴巴
    "三亚海洋实验室",                          # 没有法人后缀,也没有品牌依据
    "南昌凯迅光电股份有限公司",                 # 剥完是"南昌凯迅光电",不是已知品牌
    "北京银行股份有限公司",                     # 剥完是"北京银行",不在品牌集合里
    "TEG",                                    # 腾讯的部门码,不是公司
    "国机金刚石晶源创科（新疆）有限公司",
])
def test_unknown_names_are_kept_verbatim(raw):
    canonical, basis = CN.canonical_of(raw)
    assert canonical == raw
    assert basis == "keep"


def test_keep_is_the_default_when_tables_are_empty(monkeypatch):
    monkeypatch.setattr(CN, "_ALIASES", {})
    monkeypatch.setattr(CN, "_BRANDS", {})
    assert CN.canonical_of("腾讯科技（深圳）有限公司") == ("腾讯科技（深圳）有限公司", "keep")


def test_empty_input_is_not_invented():
    assert CN.canonical_of(None) == ("", "空值")
    assert CN.canonical_of("   ") == ("", "空值")
    assert CN.canonical_company_of({}) == ("", "empty")
    assert CN.canonical_company_of({"canonical_company": None, "company": ""}) == ("", "empty")


# ---------------------------------------------------------------- 展示名与用人单位层

def test_display_fields_all_equal_canonical():
    records = [row("a", recruitment_unit="腾讯科技（深圳）有限公司", recruiting_unit_raw="TEG"),
               row("b", canonical_company="美团", company="美团", recruitment_unit="美团"),
               row("c", recruitment_unit="塞浦路斯阿里斯托开发有限公司北京代表处")]
    normalize_records(records)
    for record in records:
        assert record["company"] == record["canonical_company"]
        assert record["company_name"] == record["canonical_company"]
        assert record["canonical_company"]
    assert records[0]["canonical_company"] == "腾讯"
    assert records[1]["canonical_company"] == "美团"
    assert records[2]["canonical_company"] == "塞浦路斯阿里斯托开发有限公司北京代表处"


def test_employer_unit_is_filled_but_never_overwritten():
    keep = row("a", recruitment_unit="中国移动通信集团有限公司", recruiting_unit_raw="中国移动通信集团北京有限公司")
    fill = row("b", recruitment_unit="中国移动通信集团有限公司")
    raw_only = row("c", recruiting_unit_raw="中国邮政集团有限公司总部")
    normalize_records([keep, fill, raw_only])
    assert keep["recruitment_unit"] == "中国移动通信集团有限公司"      # 已有值不动
    assert keep["recruiting_unit_raw"] == "中国移动通信集团北京有限公司"
    assert fill["recruiting_unit_raw"] == "中国移动通信集团有限公司"    # 单向补齐
    assert raw_only["recruitment_unit"] == "中国邮政集团有限公司总部"   # 反向补齐
    assert CN.employer_unit_of({}) == ""


# ---------------------------------------------------------------- 幂等

def test_normalize_records_is_idempotent():
    records = [row("a", recruitment_unit="腾讯科技（深圳）有限公司", recruiting_unit_raw="TEG"),
               row("b", recruitment_unit="字节跳动"),
               row("c", recruitment_unit="中国移动通信集团北京有限公司"),
               row("d", recruitment_unit="三亚海洋实验室"),
               row("e", company="上海艾为电子技术股份有限公司")]
    normalize_records(records)
    snapshot = [dict(record) for record in records]
    second = normalize_records(records)
    assert records == snapshot
    assert all(second[field] == 0 for field in REPORTED_FIELDS)


def test_canonical_of_is_idempotent():
    for raw in ["腾讯科技（深圳）有限公司", "网易互娱", "中国联合网络通信有限公司湖北省分公司",
                "中国航天科工集团有限公司", "小米科技有限公司", "三亚海洋实验室",
                "塞浦路斯阿里斯托开发有限公司北京代表处"]:
        once = CN.canonical_of(raw)[0]
        assert CN.canonical_of(once)[0] == once


# ---------------------------------------------------------------- 统计口径

# "现在按 recruitment_unit 计" 的等价口径:公司身份字段里确实属于该品牌的记录。
BASELINE_UNITS = {
    "腾讯": {"腾讯科技（深圳）有限公司", "腾讯"},
    "字节跳动": {"字节跳动"},
    "阿里巴巴": {"阿里巴巴"},
}


def baseline_count(records, brand):
    return sum(1 for r in records
               if r.get("recruitment_unit") in BASELINE_UNITS[brand]
               or r.get("canonical_company") == brand)


def test_brand_counts_match_recruitment_unit_baseline():
    records = [
        row("t1", recruitment_unit="腾讯科技（深圳）有限公司", recruiting_unit_raw="TEG"),
        row("t2", recruitment_unit="腾讯科技（深圳）有限公司", recruiting_unit_raw="IEG"),
        row("t3", canonical_company="腾讯", company="腾讯", company_name="腾讯", recruitment_unit="腾讯"),
        row("b1", recruitment_unit="字节跳动"),
        row("b2", recruitment_unit="字节跳动"),
        row("a1", recruitment_unit="阿里巴巴"),
        row("a2", recruitment_unit="塞浦路斯阿里斯托开发有限公司北京代表处"),   # 干扰项:含"阿里"子串
    ]
    before = {brand: baseline_count(records, brand) for brand in BASELINE_UNITS}
    assert before == {"腾讯": 3, "字节跳动": 2, "阿里巴巴": 1}
    normalize_records(records)
    after = {brand: sum(1 for r in records if r.get("canonical_company") == brand)
             for brand in BASELINE_UNITS}
    assert after == before
    # 干扰项没有被算进阿里巴巴
    assert records[-1]["canonical_company"] != "阿里巴巴"


# ---------------------------------------------------------------- 别名表自检

def test_alias_table_entries_all_carry_basis():
    payload = json.loads(CN.ALIASES_PATH.read_text(encoding="utf-8"))
    for section in ("aliases", "brands"):
        entries = payload.get(section) or {}
        assert entries, f"{section} 段为空"
        for key, spec in entries.items():
            basis = spec if isinstance(spec, str) else str(spec.get("basis") or "")
            assert basis.strip(), f"{section}.{key} 缺少 basis"


def test_alias_table_has_no_group_prefix_merges():
    """站长 2026-09-19:删除“集团化”前缀合并(原 prefixes 段),以后也不许再加回来。"""
    payload = json.loads(CN.ALIASES_PATH.read_text(encoding="utf-8"))
    assert not (payload.get("prefixes") or {}), payload.get("prefixes")
    assert not hasattr(CN, "_PREFIXES")
    assert not hasattr(CN, "_PREFIX_KEYS")


def test_every_canonical_target_is_stable():
    payload = json.loads(CN.ALIASES_PATH.read_text(encoding="utf-8"))
    targets = [spec["canonical"] for spec in payload["aliases"].values()]
    targets += [spec["canonical"] for spec in (payload.get("prefixes") or {}).values()]
    for canonical in targets:
        assert CN.canonical_of(canonical)[0] == canonical


def test_alias_table_actually_loaded():
    info = CN.table_info()
    assert info["aliases"] >= 17
    assert "prefixes" not in info
    assert info["brands"] >= 50
    assert info["platform_names"] > 0


def test_every_brand_entry_is_a_full_name_not_a_bare_string():
    """回归:平台配置并入 brands 时若存成裸字符串,取 entry[0] 会退化成首字符
    (干跑里真出现过 国信证券 -> 国)。这里锁死每个条目的形状。"""
    for key, entry in CN._BRANDS.items():
        assert isinstance(entry, tuple) and len(entry) == 2, f"{key} 不是 (规范名, 依据)"
        canonical, basis = entry
        assert len(canonical) > 1 and CN.norm_key(canonical) == key, f"{key} -> {canonical!r}"
        assert basis.strip(), f"{key} 缺少依据"


def test_platform_config_names_are_usable_as_canonical():
    """平台配置里的规范名必须原样返回,不能被截断或二次改写。"""
    for raw in ("国信证券", "中金公司", "基恩士", "迈瑞医疗", "中科创达"):
        assert CN.canonical_of(raw)[0] == raw


# ---------------------------------------------------------------- normalize_file 不丢记录

def test_normalize_file_keeps_record_count_and_ids(tmp_path):
    path = tmp_path / "jobs.json"
    records = [row("a", recruitment_unit="腾讯科技（深圳）有限公司"),
               row("b", recruitment_unit="字节跳动"),
               row("c", recruitment_unit="三亚海洋实验室"),
               row("d")]
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    result = normalize_file(path)
    written = json.loads(path.read_text(encoding="utf-8"))
    assert result["records"] == len(records)
    assert [r["id"] for r in written] == [r["id"] for r in records]
    assert result["filled"]["canonical_company"] == 3      # d 没有任何公司证据,不凭空造
    assert written[3].get("canonical_company") is None   # 没有证据就不写空字段
    # 第二次运行:补齐数为 0,且不改动上一轮产物
    again = normalize_file(path)
    assert all(count == 0 for count in again["filled"].values())
    assert json.loads(path.read_text(encoding="utf-8")) == written


def test_company_fields_are_reported_but_not_inherited_by_collector_merge():
    """公司名不进 NORMALIZED_FIELDS:collector/run.py 会继承那批字段的上一轮取值,
    公司名一旦继承,改别名表就会留下改不动的旧名。"""
    from qiuzhao.normalize import COMPANY_FIELDS, NORMALIZED_FIELDS
    assert set(COMPANY_FIELDS).isdisjoint(NORMALIZED_FIELDS)
    assert set(COMPANY_FIELDS) <= set(REPORTED_FIELDS)
