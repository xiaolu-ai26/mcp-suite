"""qiuzhao/v4_fields.py and the in-process parts of qiuzhao/tools.py (no HTTP)."""
import json
import os
import sys
from datetime import date, timedelta

import pytest

from _mcp_harness import RELEASE, TODAY
from acceptance_cases import CASES
from qiuzhao import tools as T
from qiuzhao import v4_fields as V

SPEC_SCRIPTS = RELEASE / "research" / "qiuzhao-v4-interface-20260911" / "scripts"
REGISTRY = RELEASE / "research" / "qiuzhao-expansion-20260910" / "sources_registry.jsonl"
TEST_IDS = {"gp-208198996248757008", "gp_开开心心有限公司2-213282367253512230", "gp_梧桐科技-150370747208958449",
            "gp_洛阳前钱有限企业-109204351230152857", "guopin-109204351230152857"}


def row(**kw):
    base = dict(id="x", source_url="https://example.org/s", application_url="https://example.org/a")
    base.update(kw)
    return base

# ---------------------------------------------------------------- 届别 extraction


@pytest.mark.parametrize("text,years", [
    ("1、相关要求：2027年应届高校毕业生，本科及以上", [2027]),
    ("毕业时间：2027年10月前", [2027]),
    ("招聘对象为毕业时间为2027年7月的在校应届毕业生", [2027]),
    ("学历要求：2026届未就业、2027届普通高校毕业生", [2026, 2027]),
    ("1.2025-2027届本科及以上学历毕业生", [2025, 2026, 2027]),
    ("2、2026、 2027届普通高等院校国家统招本科", [2026, 2027]),
    ("国（境）外学生：2026年1月至2027年8月毕业", [2026, 2027]),
    ("毕业时间为2026年7月1日至2027年6月30日", [2026, 2027]),
    ("1、2027届或2028届硕士研究生在读", [2027, 2028]),
    ("1.2026年度应届硕士研究生及以上", [2026]),
    ("Candidates in the Class of 2027", [2027]),
    ("年龄计算的截止时间为2027年7月31日；", []),
    ("自2024年起，实习留用是获得腾讯正式 offer 的主要方式", []),
    ("需2027年9月1日前取得相应毕业证", []),
    ("统一模型在2025年已经取得了巨大进步", []),
    ("2026年7月1日至2027年6月30日期间入职", []),
    ("2024/2025/2026以及应届毕业生", []),
])
def test_description_years(text, years):
    assert V.description_years(text) == years


@pytest.mark.parametrize("text,years", [
    ("之家-琴园-全科医生【2027届】(J85495)", [2027]), ("君乐宝2027校招-电商管培生", [2027]),
    ("Software Engineer Graduate - 2027 Start", [2027]), ("电池及能源系统类-campus-2027(博士招聘）", [2027]),
    ("2026应届生-销售", [2026]), ("QDG20260031-助理工程师", []), ("2026-氢能与燃料电池【博士后】", []),
    ("（2026）实验员", []),
])
def test_title_years_need_a_cohort_word(text, years):
    assert V.title_years(text) == years


def test_years_in_keeps_the_spec_window_rule():
    assert V.years_in("2026-11-01 至 2027-10-31") == [2027]
    assert V.years_in("2026-2027年8月毕业") == [2026, 2027]
    assert V.years_in("国聘行动2027校园招聘") == [2027] and V.years_in("") == []


@pytest.mark.parametrize("r,years,basis,note,rule", [
    (row(cohort_raw="2026届应届毕业生", campaign_cohort_raw="2027届校园招聘", recruitment_type="校园招聘"),
     ["2026届"], {"2026届": "岗位写明"}, "", "cohort_raw"),
    (row(campaign_cohort_raw="国聘行动2027校园招聘", recruitment_type="校园招聘"),
     ["2027届"], {"2027届": "活动标题写明"}, "", "campaign_title"),
    (row(recruitment_type="社会招聘", job_title="2027届管培生"), ["2027届"], {"2027届":"岗位写明"}, "", "job_title"),
    (row(recruitment_type="校园招聘", job_title="2027届校招-财务培训生", description_raw="2026届也可"),
     ["2027届", "2026届"], {"2027届": "岗位写明", "2026届": "岗位写明"}, "", "description"),
    (row(recruitment_type="实习招聘", description_raw="1、2027届或2028届硕士研究生在读"),
     ["2028届", "2027届"], {"2028届": "岗位写明", "2027届": "岗位写明"}, "", "description"),
    (row(recruitment_type="实习招聘", published_at="2026-08-01"), [], {}, "实习未写届别", "intern"),
    (row(recruitment_type="校园招聘", published_at="2026-08-15"), ["2027届"], {"2027届": "按招聘季推断"}, "", "season"),
    (row(recruitment_type="校园招聘", published_at="2026-06-30"), [], {}, "未注明", "unspecified"),
    (row(recruitment_type="校园招聘", source_url="https://join.qq.com/post_detail.html?postid=1"),
     ["2027届"], {"2027届": "来源专场注明"}, "", "source_scope"),
    (row(recruitment_type="校园招聘"), [], {}, "未注明", "campus_no_date_unmatched"),
    (row(recruitment_type=""), [], {}, "未注明", "unspecified"),
])
def test_graduation_order(r, years, basis, note, rule):
    assert V.graduation_of(r) == (years, basis, note, rule)
    item = V.to_item(r)
    assert item["graduation_years"] == years and item["graduation_year_basis"] == basis
    assert item.get("graduation_year_note", "") == note


def test_source_scopes_match_the_registry():
    rows = [json.loads(line) for line in REGISTRY.read_text().splitlines() if line.strip()]
    assert V.derive_source_scopes(rows) == V.SOURCE_SCOPES

# ---------------------------------------------------------------- test records


@pytest.mark.parametrize("r,rule", [
    (row(job_title="test50"), "title_test_n"), (row(job_title="zyx联调测试修改职位01"), "title_test_post"),
    (row(job_title="亲属关系优化测试职位26070701"), "title_test_post"),
    (row(job_title="参与单位数据统计1", description_raw="测试数据 测试数据测试数据"), "desc_placeholder_only"),
    (row(job_title="x", description_raw="工作职责： 测试职位请勿投递！测试职位请勿投递！"), "desc_do_not_apply"),
    (row(job_title="x", description_raw="工作职责： 这是工作职责 任职要求： 这是任职要求"), "desc_template_text"),
    (row(job_title="软件测试工程师"), None), (row(job_title="测试开发工程师（联调方向）"), None),
    (row(job_title="Test Engineer"), None), (row(job_title="数据分析", description_raw="负责测试数据的采集与分析"), None),
    (row(job_title="培训生（市场营销）【仅限2027应届，往届勿投递】"), None),
])
def test_test_rules(r, rule):
    assert V.test_rule(r) == rule


def test_test_rules_hit_only_the_known_records(raw_rows):
    hits = {r["id"] for r in raw_rows if r.get("source_url") and r.get("application_url") and V.test_rule(r)}
    assert hits == TEST_IDS

# ---------------------------------------------------------------- parity with the SPEC reference


def test_shared_rules_match_the_spec_reference(raw_rows):
    """Every non-届别 field equals scripts/v4lib.py (the SPEC's reference) on all 27,506 rows, and
    届别 equals it wherever the role text or campaign title names a year."""
    sys.path.insert(0, str(SPEC_SCRIPTS))
    try:
        import v4lib as L
    finally:
        sys.path.remove(str(SPEC_SCRIPTS))
    valid = [r for r in raw_rows if r.get("source_url") and r.get("application_url")]
    assert len(valid) == 27506
    grad = {"graduation_years", "graduation_year_basis", "graduation_year_note"}
    for r in valid:
        a, b = L.to_item(r), V.to_item(r)
        assert {k: v for k, v in a.items() if k not in grad} == {k: v for k, v in b.items() if k not in grad}, r["id"]
        if a["graduation_years"]:
            assert (a["graduation_years"], a["graduation_year_basis"]) == (b["graduation_years"], b["graduation_year_basis"])
    fixed = {}
    for r in valid:
        jc = V.job_category_of(r)
        if jc != r["job_category_normalized"]:
            fixed[jc] = fixed.get(jc, 0) + 1
    assert fixed == {"产品": 370, "运营": 244, "设计": 80, "销售": 72, "市场/营销": 21, "职能/支持": 14}  # SPEC 6.2: 801
    assert sum(1 for r in valid if any("area_code" in str(c) for c in r["cities"]) and V.cities_of(r)) == 539
    assert sum(1 for r in valid if "海外" in V.region_of(r, V.cities_of(r)) and not r.get("overseas_flag")) == 373
    assert sum(1 for r in valid if r.get("deadline_type") == "undisclosed" and V.deadline_of(r)[1] == "明确日期") == 1087


def test_build_report_numbers(jobs_inproc):
    rep = jobs_inproc.dataset().report
    expected = {"rows_total": 28616, "rows_valid": 27506, "dropped_duplicate_id": 2043, "rows_deduped": 25463,
                "dropped_test_record": 5, "items": 25458,
                "grad_rule:cohort_raw": 13997, "grad_rule:campaign_title": 4280, "grad_rule:social": 3016,
                "grad_rule:job_title": 190, "grad_rule:description": 329, "grad_rule:intern": 509,
                "grad_rule:season": 2437, "grad_rule:source_scope": 381, "grad_rule:campus_no_date_unmatched": 155,
                "grad_rule:unspecified": 164, "city_area_code_fixed": 519, "overseas_flag_was_false": 364,
                "deadline_undisclosed_with_date": 912, "education_garbage": 89,
                "test_rule:title_test_n": 2, "test_rule:title_test_post": 2, "test_rule:desc_placeholder_only": 1}
    assert {k: rep.get(k) for k in expected} == expected
    assert sum(v for k, v in rep.items() if k.startswith("job_category_fixed:")) == 770
    assert sum(v for k, v in rep.items() if k.startswith("grad_rule:")) == rep["items"]

# ---------------------------------------------------------------- fallbacks and small pieces


def test_fallbacks_when_normalized_fields_are_absent():
    assert V.job_category_of(row(job_category="产品经理", job_title="AI 产品经理")) == "产品"
    assert V.job_category_of(row(job_category="后端开发", job_title="Go 后端工程师")) == "技术/研发"
    # The original classifier tried 技术/研发 first, so '数据运营' became 技术/研发.
    assert V.job_category_of(row(job_category="", job_title="数据运营专员")) == "运营"
    assert V.major_category_of(row(major_requirements_raw="计算机科学与技术、软件工程")) == "计算机类"
    assert V.cities_of(row(cities=["北京市", "全国各地", "未知"])) == ["北京", "全国"]


def test_status_is_computed_at_read_time():
    today = date(2026, 9, 11)
    item = V.to_item(row(deadline="2026-09-10", status="open"))
    assert item["status"] == "招聘中" and V.status_on(item, today) == "已截止"
    assert V.status_on(V.to_item(row(deadline="2026-09-11", status="unverified")), today) == "未核验"
    assert V.to_item(row(deadline="2099-01-01"))["deadline_kind"] == "招满即止或长期"
    assert V.to_item(row(deadline="2026-11-24 23:59:59", deadline_type="undisclosed"))["deadline"] == "2026-11-24"


@pytest.mark.parametrize("chunk", [1, 2, 3, 7, 64, 1 << 20])
def test_iter_json_file_across_chunk_boundaries(tmp_path, chunk):
    sample = [{"a": 1, "s": "北京，上海🙂"}, {"b": [1, 2, {"c": "\\\"]}"}]}, 12345, -0.5e3, "x", None, True, []]
    for indent in (None, 2):
        path = tmp_path / "a.json"
        path.write_text(json.dumps(sample, ensure_ascii=False, indent=indent), encoding="utf-8")
        assert list(T.iter_json_file(path, chunk)) == sample
    (tmp_path / "e.json").write_text(" [ ] \n")
    assert list(T.iter_json_file(tmp_path / "e.json", chunk)) == []
    for bad in ('{"a": 1}', '[{"a": 1}, {"b"', '[1, 2] trailing', "", "[1, 2"):
        (tmp_path / "b.json").write_text(bad)
        with pytest.raises(ValueError):
            list(T.iter_json_file(tmp_path / "b.json", chunk))


def test_iter_json_file_equals_json_load(raw_rows, jobs_inproc):
    rows = list(T.iter_json_file(jobs_inproc.path))
    assert len(rows) == len(raw_rows) == 28616 and rows[0] == raw_rows[0] and rows[-1] == raw_rows[-1]
    assert rows == raw_rows


def _write(path, rows, bump=0):
    path.write_text(json.dumps(rows, ensure_ascii=False))
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + bump))


def test_cache_rebuilds_only_when_the_file_changes(tmp_path):
    path = tmp_path / "jobs.json"
    rows = [row(id=str(i), job_title=f"岗位{i}", recruitment_type="校园招聘") for i in range(3)]
    _write(path, rows[:2])
    jobs = T.Jobs(path, today=date(2026, 9, 11))
    first = jobs.dataset()
    assert jobs.dataset() is first and len(first.items) == 2
    _write(path, rows, bump=10**9)
    second = jobs.dataset()
    assert second is not first and len(second.items) == 3 and jobs.health()["jobs"] == 3
    path.write_text('[{"id": "broken"')  # caught mid-write: keep serving the last good version
    os.utime(path, ns=(path.stat().st_atime_ns, second.key[0] + 2 * 10**9))
    assert jobs.dataset() is second and jobs.search()["total"] == 3
    _write(path, rows[:1], bump=3 * 10**9)
    assert len(jobs.dataset().items) == 1
    with pytest.raises(FileNotFoundError, match="岗位数据尚未就绪"):
        T.Jobs(tmp_path / "missing.json").dataset()
    (tmp_path / "bad.json").write_text("{}")
    with pytest.raises(ValueError):
        T.Jobs(tmp_path / "bad.json").dataset()


def test_budget_keeps_at_least_one_whole_job(tmp_path, monkeypatch):
    path = tmp_path / "jobs.json"
    _write(path, [row(id=str(i), job_title="x" * 50) for i in range(3)])
    monkeypatch.setattr(T, "BUDGET_BYTES", 10)
    out = T.Jobs(path, today=date(2026, 9, 11)).search(page_size=5)
    assert (out["returned"], out["truncated"], out["next_offset"], out["has_next"]) == (1, True, 1, True)


def test_order_inside_a_tier_follows_specificity(tmp_path):
    """Max, 2026-09-12: inside a tier the more specific basis comes first — city 岗位写明 > 全国, major
    岗位写明 > 专业不限, education 岗位写明 > 学历不限, 届别 岗位写明 > 活动标题写明 — compared in that
    dimension order, then the requested sort. Publish dates run against that order on purpose."""
    base = dict(recruitment_type="校园招聘", cities_normalized=["成都"], major_requirements_raw="计算机科学与技术",
                major_normalized="计算机类", education_raw="本科", cohort_raw="2027届")
    rows = [row(id="specific-old", **base, published_at="2026-09-01", deadline="2026-09-20"),
            row(id="specific-new", **base, published_at="2026-09-05", deadline="2026-09-30"),
            row(id="specific-undated", **base, published_at="2026-09-04"),
            row(id="campaign-title", **{**base, "cohort_raw": "", "campaign_cohort_raw": "2027校园招聘"},
                published_at="2026-09-07"),
            row(id="edu-unlimited", **{**base, "education_raw": "不限"}, published_at="2026-09-08"),
            row(id="major-unlimited", **{**base, "major_requirements_raw": "专业不限"}, published_at="2026-09-09"),
            row(id="nationwide", **{**base, "cities_normalized": ["全国"]}, published_at="2026-09-10"),
            row(id="nationwide-campaign", **{**base, "cities_normalized": ["全国"], "cohort_raw": "",
                                             "campaign_cohort_raw": "2027届校园招聘"}, published_at="2026-09-11"),
            row(id="inferred-season", **{**base, "cohort_raw": ""}, published_at="2026-09-11"),
            row(id="city-unspecified", **{**base, "cities_normalized": []}, published_at="2026-09-11")]
    path = tmp_path / "jobs.json"
    _write(path, rows)
    jobs = T.Jobs(path, today=date(2026, 9, 11))
    q = dict(city="成都", major="计算机类", education="本科", graduation_year="2027届", page_size=20)
    tail = ["campaign-title", "edu-unlimited", "major-unlimited", "nationwide", "nationwide-campaign",
            "inferred-season", "city-unspecified"]
    out = jobs.search(**q)
    assert [j["id"] for j in out["jobs"]] == ["specific-new", "specific-undated", "specific-old"] + tail
    assert [j["id"] for j in jobs.search(**q, sort="deadline_asc")["jobs"]] == [
        "specific-old", "specific-new", "specific-undated"] + tail
    by_id = {j["id"]: j["match"] for j in out["jobs"]}
    assert by_id["nationwide"] == {"level": "明确匹配", "graduation_year": "岗位写明", "city": "全国",
                                   "major": "岗位写明", "education": "岗位写明"}
    assert by_id["campaign-title"]["graduation_year"] == "活动标题写明"
    assert (by_id["inferred-season"]["level"], by_id["city-unspecified"]["level"]) == ("推断匹配", "含未注明")
    # No 届别/城市/专业/学历 condition: plain published-desc order, as before.
    assert [j["id"] for j in jobs.search(page_size=3)["jobs"]] == ["nationwide-campaign", "inferred-season",
                                                                  "city-unspecified"]


def test_inferred_year_is_unspecified_for_other_years(tmp_path):
    """Decision 2 (2026-09-12): an inferred-only 届 does not rule a row out for another 届 query; it
    comes back as 含未注明 with basis 推断为其他届别. A stated 届 still rules it out."""
    rows = [row(id="season", recruitment_type="校园招聘", published_at="2026-09-01"),
            row(id="scope-26-27", recruitment_type="校园招聘",
                source_url="https://careers.midea.com/schoolOut/post/details?id=1"),
            row(id="stated-2027", recruitment_type="校园招聘", cohort_raw="2027届"),
            row(id="no-clue", recruitment_type="校园招聘")]
    path = tmp_path / "jobs.json"
    _write(path, rows)
    jobs = T.Jobs(path, today=date(2026, 9, 11))

    def bases(**q):
        return {j["id"]: (j["match"]["level"], j["match"]["graduation_year"])
                for j in jobs.search(page_size=20, **q)["jobs"]}

    assert bases(graduation_year="2026届") == {"scope-26-27": ("推断匹配", "来源专场注明"),
                                              "season": ("含未注明", "推断为其他届别"), "no-clue": ("含未注明", "未注明")}
    assert bases(graduation_year="2025届") == {"scope-26-27": ("含未注明", "推断为其他届别"),
                                              "season": ("含未注明", "推断为其他届别"), "no-clue": ("含未注明", "未注明")}
    assert bases(graduation_year="2027届") == {"season": ("推断匹配", "按招聘季推断"),
                                              "scope-26-27": ("推断匹配", "来源专场注明"),
                                              "stated-2027": ("明确匹配", "岗位写明"), "no-clue": ("含未注明", "未注明")}
    assert jobs.search(graduation_year="2026届", explicit_only=True)["total"] == 0
    assert set(bases(graduation_year="未注明")) == {"no-clue"}

# ---------------------------------------------------------------- an independent reading of SPEC 3.0

KW = ("job_title", "job_category_raw", "description_raw", "company", "recruiting_unit_raw", "parent_unit_raw",
      "hiring_department_raw", "contracting_entity")
CO = ("company", "recruiting_unit_raw", "parent_unit_raw", "contracting_entity")
INFERRED = {"按招聘季推断", "来源专场注明", "实习未写届别", "社招不限届别"}
RANK = {"中专及以下": 1, "大专": 2, "本科": 3, "硕士": 4, "博士": 5}


def reference(items, today, **q):
    """Counts per tier written straight from the SPEC 3.0 table and the v4 decisions."""
    end = (date.fromisoformat(today) + timedelta(days=q.get("deadline_within_days", 0))).isoformat()
    cities = [c for c in q.get("city", "").split(",") if c]
    comps = [c.lower() for c in q.get("company", "").split(",") if c]
    counts, excluded = {"e": 0, "i": 0, "u": 0}, 0
    for it in items:
        dl = it["deadline"]
        if (not q.get("include_expired") and dl and dl < today) or \
                (q.get("deadline_within_days") and not (dl and today <= dl <= end)):
            continue
        if any(q.get(k) and it[k] != q[k] for k in ("job_category", "recruitment_type", "industry")):
            continue
        if q.get("keyword") and q["keyword"].lower() not in "\n".join(str(it.get(f, "")) for f in KW).lower():
            continue
        if comps and not any(c in "\n".join(str(it.get(f, "")) for f in CO).lower() for c in comps):
            continue
        bases = []
        if cities:
            cs = it["cities"]
            if cities == ["未注明"]:
                b = "未注明" if not cs else None
            elif set(cities) & set(cs):
                b = "岗位写明"
            elif "全国" in cs and any(c not in ("全国", "未注明") and V.city_region(c) == "中国大陆" for c in cities):
                b = "全国"
            else:
                b = None if cs else "未注明"
            bases.append(b)
        if q.get("major"):
            m, mc = q["major"], it["major_category"]
            text = (it.get("major_requirements_raw", "") + " " + " ".join(it.get("major_tags", []))).lower()
            if m in ("未注明", "不限"):
                b = {"未注明": "未注明", "不限": "专业不限"}[m] if mc == m else None
            elif mc in ("不限", "未注明"):
                b = "专业不限" if mc == "不限" else "未注明"
            else:
                b = "岗位写明" if mc == m or (m[:-1] if m.endswith("类") else m).lower() in text else None
            bases.append(b)
        if q.get("education"):
            e, ed = q["education"], it["education"]
            if e in ("未注明", "不限"):
                b = {"未注明": "未注明", "不限": "学历不限"}[e] if ed == e else None
            elif ed in ("不限", "未注明"):
                b = "学历不限" if ed == "不限" else "未注明"
            else:
                b = "岗位写明" if RANK[ed] <= RANK[e] else None
            bases.append(b)
        if q.get("graduation_year"):
            g, years, note = q["graduation_year"], it["graduation_years"], it.get("graduation_year_note")
            if g == "未注明":
                b = "未注明" if note == "未注明" else None
            elif years:
                b = it["graduation_year_basis"].get(g)
                # Decision 2 (2026-09-12): a row whose only 届 was inferred is not ruled out.
                if b is None and set(it["graduation_year_basis"].values()) <= {"按招聘季推断", "来源专场注明"}:
                    b = "推断为其他届别"
            elif note == "社招不限届别" and q.get("recruitment_type") != "社会招聘":
                if None not in bases:
                    excluded += not q.get("explicit_only")
                continue
            else:
                b = note
            bases.append(b)
        if None in bases:
            continue
        tier = "u" if {"未注明", "推断为其他届别"} & set(bases) else "i" if INFERRED & set(bases) else "e"
        if q.get("explicit_only") and tier != "e":
            continue
        counts[tier] += 1
    return counts, excluded


QUERIES = [args for _, steps in CASES.values() for tool, args in steps if tool != "jobs_detail"] + [
    {}, {"city": "新加坡"}, {"city": "全国"}, {"city": "未注明"}, {"city": "香港,北京"},
    {"graduation_year": "未注明"}, {"graduation_year": "2025届"}, {"graduation_year": "2028届", "explicit_only": True},
    {"education": "不限"}, {"education": "未注明"}, {"education": "大专", "city": "上海"}, {"major": "未注明"},
    {"major": "统计"}, {"graduation_year": "2027届", "recruitment_type": "社会招聘"},
    {"graduation_year": "2026届", "explicit_only": True}, {"company": "腾讯,阿里巴巴"}, {"keyword": "Python"},
    {"include_expired": True}, {"deadline_within_days": 30, "graduation_year": "2027届", "city": "深圳"},
    {"graduation_year": "2026届"}, {"graduation_year": "2028届"},
    {"graduation_year": "2025届", "recruitment_type": "校园招聘"},
    {"graduation_year": "2026届", "city": "北京", "education": "硕士"},
]


def test_counts_match_an_independent_reading_of_the_spec(jobs_inproc):
    items = jobs_inproc.dataset().items
    for q in QUERIES:
        filters = {k: v for k, v in q.items() if k in T.FILTER_DEFAULTS}
        got = jobs_inproc.stats(**filters)
        counts, excluded = reference(items, TODAY, **filters)
        assert (got["explicit_total"], got["inferred_total"], got["unspecified_total"]) == (
            counts["e"], counts["i"], counts["u"]), q
        assert got.get("excluded_social_total", 0) == excluded, q
