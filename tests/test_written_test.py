"""笔试要求(written_test):标注表查表、岗位继承、岗位描述明文、MCP 筛选与分组。"""
import json
from datetime import date

import pytest

from qiuzhao import normalize as N
from qiuzhao import tools as T
from qiuzhao import v4_fields as V
from qiuzhao import written_test as WT


def row(**kw):
    base = dict(id="x", source_url="https://example.org/s", application_url="https://example.org/a")
    base.update(kw)
    return base


def tables(company=(), campaign=()):
    """(company_table, campaign_table) 的测试替身。"""
    return ({WT.normalize_company(k): v for k, v in company},
            {WT.normalize_company(k): v for k, v in campaign})


LABEL = {"written_test": "有笔试", "written_test_scope": "company", "written_test_basis": "公告原文",
         "written_test_evidence": "统一笔试", "written_test_source_url": "https://example.org/notice",
         "written_test_checked_at": "2026-09-19T02:40:00+08:00"}


# ---------------------------------------------------------------- 公司名归一化

@pytest.mark.parametrize("raw,expected", [
    ("科大讯飞股份有限公司", "科大讯飞"),
    ("中国邮政集团有限公司", "中国邮政"),
    ("中国银行股份有限公司", "中国银行"),
    ("广东省韶铸集团有限公司（韶关铸锻总厂）", "广东省韶铸"),
    (" 中国工商银行 ", "中国工商银行"),
    ("腾讯", "腾讯"),
    ("", ""),
    (None, ""),
])
def test_normalize_company(raw, expected):
    assert WT.normalize_company(raw) == expected


# ---------------------------------------------------------------- 查表

def test_lookup_exact_alias_and_prefix():
    table = tables([("科大讯飞", LABEL)])
    # 别名与去后缀写法都命中
    for name in ("科大讯飞", "科大讯飞股份有限公司"):
        assert WT.lookup(row(company=name), table) is LABEL
    # 库内带层级后缀的公司名按前缀命中(>=4 字)
    assert WT.lookup(row(company="中国邮政集团有限公司北京市分公司"), tables([("中国邮政", LABEL)])) is LABEL
    # 太短的 key 不做前缀匹配,避免误配
    assert WT.lookup(row(company="中国邮政集团"), tables([("中国", LABEL)])) is None
    assert WT.lookup(row(company="字节跳动"), table) is None


def test_lookup_campaign_beats_company():
    company = tables([("中国邮政", {**LABEL, "written_test": "有笔试"})])
    campaign = tables(campaign=[("中国邮政2027校招", {**LABEL, "written_test": "免笔试", "key_type": "campaign"})])
    merged = (company[0], campaign[1])
    hit = WT.lookup(row(company="中国邮政", source_name="中国邮政2027校招"), merged)
    assert hit["written_test"] == "免笔试"


def test_resolve_priority_job_over_company():
    table = tables([("科大讯飞", LABEL)])
    record = row(company="科大讯飞", description_raw="本岗位需要参加在线笔试，请留意通知")
    assert WT.resolve(record, table)["written_test"] == "有笔试"
    assert WT.resolve(record, table)["written_test_scope"] == "job"
    plain = row(company="科大讯飞", description_raw="负责日常研发工作")
    assert WT.resolve(plain, table)["written_test_scope"] == "company"


def test_resolve_returns_none_without_label():
    assert WT.resolve(row(company="某不在表里的公司"), tables([("科大讯飞", LABEL)])) is None


# ---------------------------------------------------------------- 岗位描述明文

@pytest.mark.parametrize("text,value,scope", [
    ("本岗位免笔试", "免笔试", "job"),
    ("该岗位无需笔试，直接进入面试", "免笔试", "job"),
    ("优秀者可免笔试直通面试", "部分免笔试", "job"),
    ("部分岗位免笔试", "部分免笔试", "job"),
    ("*本岗位需要参加在线笔试", "有笔试", "job"),
    ("该岗位需参加在线测评", "有笔试", "job"),
    ("负责组织笔试安排与面试通知", None, None),
    ("岗位职责：协助笔试通知的发放", None, None),
    ("Candidates who pass resume screening will be invited to participate in Our Company's technical online assessment.",
     "有笔试", "job"),
])
def test_job_level(text, value, scope):
    got = WT.job_level(row(description_raw=text))
    if value is None:
        assert got is None
    else:
        assert got["written_test"] == value and got["written_test_scope"] == scope
        assert got["written_test_evidence"] in text.replace("\n", "")


def test_job_level_keeps_limiting_clause():
    got = WT.job_level(row(description_raw="（可选）优秀者可免笔试直通面试！"))
    assert got["written_test"] == "部分免笔试"
    assert "优秀者可免笔试" in got["written_test_evidence"]


# ---------------------------------------------------------------- 写入记录

def test_apply_to_record_idempotent_and_no_table_noop():
    record = row(company="科大讯飞", written_test="有笔试", written_test_evidence="旧值")
    stats = {f: 0 for f in N.NORMALIZED_FIELDS}
    assert WT.apply_to_record(record, ({}, {}), stats) is False
    assert record["written_test"] == "有笔试" and record["written_test_evidence"] == "旧值"
    assert WT.apply_to_record(record, tables([("科大讯飞", LABEL)]), stats) is True
    assert record["written_test"] == "有笔试"
    assert record["written_test_evidence"] == "统一笔试"
    before = dict(record)
    WT.apply_to_record(record, tables([("科大讯飞", LABEL)]), stats)
    assert record == before


def test_apply_clears_stale_fields_for_unspecified():
    other = {**LABEL, "written_test": "免笔试", "written_test_evidence": "投递简历-初筛-面试-入职"}
    record = row(company="某公司", written_test="", written_test_evidence="旧证据")
    WT.apply_to_record(record, tables([("科大讯飞", other)]), {f: 0 for f in N.NORMALIZED_FIELDS})
    assert record["written_test"] == "未注明"
    assert "written_test_evidence" not in record


# ---------------------------------------------------------------- normalize 集成

def test_normalize_inherits_label(tmp_path, monkeypatch):
    labels = {"version": 1, "updated_at": "2026-09-19T02:40:00+08:00",
              "labels": [{**LABEL, "key": "中国邮政"}]}
    path = tmp_path / "written_test_labels.json"
    path.write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(WT, "LABELS_PATH", path)
    monkeypatch.setattr(N, "_WT_TABLES", None)
    monkeypatch.setattr(N, "_WT_CHECKED_AT", None)
    records = [row(id="a", company="中国邮政集团有限公司", job_title="柜员"),
               row(id="b", company="别的公司", job_title="工程师")]
    stats = N.normalize_records(records)
    assert records[0]["written_test"] == "有笔试"
    assert records[0]["written_test_source_url"] == "https://example.org/notice"
    assert records[0]["written_test_checked_at"] == "2026-09-19T02:40:00+08:00"
    assert records[1]["written_test"] == "未注明"
    assert stats["written_test"] == 2


def test_normalize_without_labels_does_not_touch_records(tmp_path, monkeypatch):
    monkeypatch.setattr(WT, "LABELS_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(N, "_WT_TABLES", None)
    monkeypatch.setattr(N, "_WT_CHECKED_AT", None)
    records = [row(id="a", company="中国邮政", written_test="有笔试")]
    N.normalize_records(records)
    assert records[0]["written_test"] == "有笔试"


# ---------------------------------------------------------------- v4 字段

def test_convert_written_test_defaults_to_unspecified():
    item = V.to_item(row(id="a", job_title="工程师", company="某公司"))
    assert item["written_test"] == "未注明"
    assert "written_test_evidence" not in item


def test_convert_passes_through_evidence():
    item = V.to_item(row(id="a", written_test="免笔试", written_test_scope="company",
                         written_test_basis="公告原文", written_test_evidence="网申→面试→offer",
                         written_test_source_url="https://example.org/n",
                         written_test_checked_at="2026-09-19T02:40:00+08:00"))
    assert item["written_test"] == "免笔试" and item["written_test_evidence"] == "网申→面试→offer"
    assert item["written_test_source_url"] == "https://example.org/n"


# ---------------------------------------------------------------- MCP 工具

def _jobs_file(tmp_path):
    rows = [
        row(id="a", job_title="算法工程师", company="科大讯飞", description_raw="负责算法研发",
            written_test="有笔试", written_test_scope="company", written_test_basis="岗位描述明文",
            written_test_evidence="人员通过简历筛选、笔试、初试、复试、终审等环节后录用",
            written_test_source_url="https://example.org/a", written_test_checked_at="2026-09-19T02:40:00+08:00"),
        row(id="b", job_title="销售", company="某小公司", description_raw="负责销售",
            written_test="免笔试", written_test_scope="company", written_test_basis="岗位描述明文",
            written_test_evidence="投递简历-初筛-面试-入职",
            written_test_source_url="https://example.org/b", written_test_checked_at="2026-09-19T02:40:00+08:00"),
        row(id="c", job_title="财务", company="另一家公司", description_raw="负责财务"),
    ]
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return path


def test_search_filters_by_written_test(tmp_path):
    jobs = T.Jobs(_jobs_file(tmp_path), today="2026-09-19")
    out = jobs.search(written_test="免笔试")
    assert out["total"] == 1 and out["jobs"][0]["id"] == "b"
    assert out["jobs"][0]["written_test_evidence"] == "投递简历-初筛-面试-入职"
    assert out["jobs"][0]["written_test_source_url"] == "https://example.org/b"
    assert out["written_test_as_of"] == "2026-09-19T02:40:00+08:00"
    assert out["applied_filters"]["written_test"] == "免笔试"


def test_search_unspecified_is_not_exempt(tmp_path):
    jobs = T.Jobs(_jobs_file(tmp_path), today="2026-09-19")
    out = jobs.search(written_test="未注明")
    assert [j["id"] for j in out["jobs"]] == ["c"]
    assert any("不等于免笔试" in n for n in out["notices"])


def test_search_rejects_unknown_value(tmp_path):
    jobs = T.Jobs(_jobs_file(tmp_path), today="2026-09-19")
    with pytest.raises(T.ParamError):
        jobs.search(written_test="不用笔试")


def test_stats_group_by_written_test(tmp_path):
    jobs = T.Jobs(_jobs_file(tmp_path), today="2026-09-19")
    out = jobs.stats(group_by="written_test")
    assert out["group_by"] == "written_test" and out["fill_param"] == "written_test"
    groups = {g["value"]: g["count"] for g in out["groups"]}
    assert groups == {"有笔试": 1, "免笔试": 1, "未注明": 1}
    assert out["written_test_as_of"] == "2026-09-19T02:40:00+08:00"
    assert [g["value"] for g in out["groups"] if g["value"] == "未注明"]


def test_detail_keeps_written_test_fields(tmp_path):
    jobs = T.Jobs(_jobs_file(tmp_path), today="2026-09-19")
    out = jobs.detail("a")
    job = out["jobs"][0]
    assert job["written_test"] == "有笔试"
    assert job["written_test_evidence"].startswith("人员通过简历筛选")
    assert out["written_test_as_of"] == "2026-09-19T02:40:00+08:00"
