"""复现 SPEC.md 里的全部数量。

用法（在 qiuzhao-v4-interface-20260911/ 下）：python3 scripts/v4_numbers.py（不能叫 numbers.py，会遮住标准库 numbers）
输出：
  evidence/numbers.json        说明书引用的每个数字（键名即 SPEC 中的引用名）
  evidence/field_inventory.md  68 个字段逐个归类（业务 / 内部 / 改名合并）及覆盖率
  evidence/cohort_mapping.tsv  届别原文 → v4 届别与依据（供人工抽查）
只读 ../qiuzhao-doubao-fix-20260911/data/jobs.json，"今天"固定为 2026-09-11。
"""
import datetime as dt
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4lib as L  # noqa: E402

EV = L.ROOT / "evidence"
EV.mkdir(exist_ok=True)
N = {}


def put(key, value):
    N[key] = value
    return value


def pct(a, b):
    return round(a * 100 / b, 1) if b else None


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


def dist(xs):
    return {"mean": round(statistics.mean(xs)), "median": q(xs, .5), "p90": q(xs, .9), "p95": q(xs, .95),
            "p99": q(xs, .99), "max": max(xs)}


raw_all = L.load_all()
rows = L.valid_rows(raw_all)
fields = []
for r in rows:
    for k in r:
        if k not in fields:
            fields.append(k)
put("rows_raw", len(raw_all))
put("rows_valid", len(rows))
put("fields", len(fields))

# ------------------------------------------------------------------ 1. id 重复
by_id = defaultdict(list)
for r in rows:
    by_id[r["id"]].append(r)
dups = {k: v for k, v in by_id.items() if len(v) > 1}
put("dup_ids", len(dups))
put("dup_rows", sum(len(v) for v in dups.values()))
put("dup_extra_rows", sum(len(v) - 1 for v in dups.values()))
put("dup_groups_identical", sum(1 for v in dups.values()
                                if len({json.dumps(x, sort_keys=True, ensure_ascii=False) for x in v}) == 1))
put("dup_group_sizes", {str(k): v for k, v in sorted(Counter(len(v) for v in dups.values()).items())})
put("dup_by_source", Counter(v[0].get("source_name") for v in dups.values()).most_common(4))
put("dup_by_id_prefix", Counter(k.split("-")[0] for k in dups).most_common())
deduped = L.dedupe(rows)
put("rows_deduped", len(deduped))
# 同一岗位是否被拆成多条（不同 id、同单位同标题同描述）
same_post = defaultdict(set)
for r in deduped:
    same_post[(r.get("recruitment_unit"), r.get("job_title"), r.get("description_raw"))].add(r["id"])
multi = [k for k, v in same_post.items() if len(v) > 1]
put("same_post_multi_id_groups", len(multi))
put("same_post_multi_id_rows", sum(len(same_post[k]) for k in multi))
rows_by_id = {r["id"]: r for r in deduped}
kinds = Counter()
for k in multi:
    grp = [rows_by_id[i] for i in same_post[k]]
    cs = [tuple(sorted(map(str, r.get("cities_normalized") or []))) for r in grp]
    kinds["城市各不相同" if len(set(cs)) == len(cs) else "城市全相同" if len(set(cs)) == 1 else "部分相同"] += 1
put("same_post_multi_id_kinds", dict(kinds))
put("same_post_multi_id_cross_source_groups", sum(1 for k in multi if len({rows_by_id[i].get("source_name") for i in same_post[k]}) > 1))

# ------------------------------------------------------------------ 2. 岗位大类
bad = [r for r in rows if "产品" in (r.get("job_category") or "") and r.get("job_category_normalized") != "产品"]
put("jc_product_raw_not_norm", len(bad))
put("jc_product_raw_not_norm_by_norm", dict(Counter(r["job_category_normalized"] for r in bad)))
put("jc_product_raw_not_norm_bytedance", sum(r.get("source_name") == "字节跳动校园招聘官方网站" for r in bad))
clear = [r for r in bad if r["job_category"] in ("产品", "产品类", "产品运营") or "产品经理" in r["job_category"]]
put("jc_product_clear", len(clear))
put("jc_product_clear_bytedance", sum(r.get("source_name") == "字节跳动校园招聘官方网站" for r in clear))
put("jc_product_v3_substring", sum("产品" in json.dumps([r.get("job_category_normalized"), r.get("job_category")],
                                                        ensure_ascii=False) for r in rows))
put("jc_product_exact_now", sum(r.get("job_category_normalized") == "产品" for r in rows))
changes = Counter()
for r in rows:
    new = L.job_category_of(r)
    if new != r.get("job_category_normalized"):
        changes[new] += 1
put("jc_rule_changes_by_target", dict(changes.most_common()))
put("jc_rule_changes_total", sum(changes.values()))
put("jc_product_rule_only_changes", sum(L.job_category_of(r, only={"产品"}) != r.get("job_category_normalized")
                                        for r in rows))
put("jc_before", dict(Counter(r.get("job_category_normalized") for r in rows).most_common()))
put("jc_after_rows", dict(Counter(L.job_category_of(r) for r in rows).most_common()))
put("jc_after_deduped", dict(Counter(L.job_category_of(r) for r in deduped).most_common()))
put("company_bytedance_values", Counter(r.get("recruitment_unit") for r in rows
                                        if r.get("source_name") == "字节跳动校园招聘官方网站").most_common(3))

# ------------------------------------------------------------------ 3. 届别


def has2027(text):
    return "2027" in (text or "")


put("gy_now", dict(Counter(r.get("graduation_year_normalized") for r in rows).most_common()))
put("gy_brief_campaign_only_4266", sum(1 for r in rows if not (r.get("cohort_raw") or "").strip()
                                       and has2027(r.get("campaign_cohort_raw"))
                                       and r.get("graduation_year_normalized") == "未披露"))
put("gy_brief_squashed_319", sum(1 for r in rows if r.get("graduation_year_normalized") == "2026届"
                                 and has2027(r.get("cohort_raw"))))
put("gy_brief_v3_substring_18480", sum(1 for r in rows if has2027(r.get("cohort_raw") or r.get("campaign_cohort_raw"))))
put("gy_brief_no_year_8927", sum(1 for r in rows
                                 if not re.search(r"20\d\d", r.get("cohort_raw") or r.get("campaign_cohort_raw") or "")))
put("gy_role_mentions_2026_and_2027", sum(1 for r in rows if {"2026", "2027"} <= set(re.findall(r"20\d\d", r.get("cohort_raw") or ""))))
gy = [(r, *L.graduation_of(r)) for r in rows]
w27 = [(r, y, b) for r, y, b in gy if "2027届" in y]
put("gy_v4_2027", len(w27))
put("gy_v4_2027_by_basis", dict(Counter(b["2027届"] for _, _, b in w27)))
put("gy_v4_multi_year", sum(1 for _, y, _ in gy if len(y) > 1))
put("gy_v4_multi_year_combos", Counter("+".join(y) for _, y, _ in gy if len(y) > 1).most_common(6))
put("gy_v4_none", sum(1 for _, y, _ in gy if not y))
put("gy_v4_year_counts", dict(Counter(x for _, y, _ in gy for x in y).most_common()))
put("gy_v4_2026_only", sum(1 for _, y, _ in gy if y == ["2026届"]))
v3set = Counter(r["id"] for r in rows if has2027(r.get("cohort_raw") or r.get("campaign_cohort_raw")))
v4set = Counter(r["id"] for r, _, _ in w27)
only_v4 = [(r, y, b) for r, y, b in w27 if not has2027(r.get("cohort_raw") or r.get("campaign_cohort_raw"))]
only_v3 = [r for r, y, b in gy if has2027(r.get("cohort_raw") or r.get("campaign_cohort_raw")) and "2027届" not in y]
put("gy_v4_minus_v3", len(only_v4))
put("gy_v4_minus_v3_reason", Counter(f"cohort_raw有年份={bool(re.search(r'20\d\d', r.get('cohort_raw') or ''))}"
                                     f"|依据={b['2027届']}" for r, y, b in only_v4).most_common())
put("gy_v3_minus_v4", len(only_v3))
put("gy_v3_minus_v4_examples", Counter((r.get("cohort_raw") or "")[:40] for r in only_v3).most_common(5))
squashed = [(r, y, b) for r, y, b in gy if r.get("graduation_year_normalized") == "2026届" and has2027(r.get("cohort_raw"))]
put("gy_319_now_include_2027", sum(1 for _, y, _ in squashed if "2027届" in y))
camp = [(r, y, b) for r, y, b in gy if not (r.get("cohort_raw") or "").strip() and has2027(r.get("campaign_cohort_raw"))
        and r.get("graduation_year_normalized") == "未披露"]
put("gy_4266_now_campaign_basis", sum(1 for _, y, b in camp if b.get("2027届") == "活动标题写明"))
gyd = [L.graduation_of(r) for r in deduped]
put("gy_deduped_2027", sum(1 for y, _ in gyd if "2027届" in y))
put("gy_deduped_2027_by_basis", dict(Counter(b["2027届"] for y, b in gyd if "2027届" in y)))
put("gy_deduped_none", sum(1 for y, _ in gyd if not y))
put("gy_deduped_multi", sum(1 for y, _ in gyd if len(y) > 1))
put("gy_deduped_2026", sum(1 for y, _ in gyd if "2026届" in y))
mapping = Counter()
for r, y, b in gy:
    mapping[((r.get("cohort_raw") or "").replace("\t", " ").replace("\n", " ")[:120],
             (r.get("campaign_cohort_raw") or r.get("batch_name") or "")[:60],
             ",".join(f"{k}:{v}" for k, v in b.items()) or "未注明")] += 1
with open(EV / "cohort_mapping.tsv", "w") as fh:
    fh.write("rows\tcohort_raw(前120字)\tcampaign_title\tv4届别:依据\n")
    for (c, t, m), n in mapping.most_common():
        fh.write(f"{n}\t{c}\t{t}\t{m}\n")
put("gy_mapping_distinct", len(mapping))

# ------------------------------------------------------------------ 4. 学历
edu_raw = Counter((r.get("education_raw") or "").strip() for r in rows)
put("edu_raw_distinct_nonempty", len([k for k in edu_raw if k]))
put("edu_raw_empty", edu_raw.get("", 0))
garb = {k: v for k, v in edu_raw.items() if k and L.is_edu_garbage(k)}
put("edu_garbage_codes", garb)
put("edu_garbage_rows", sum(garb.values()))
put("edu_garbage_source", Counter(r.get("source_name") for r in rows if L.is_edu_garbage(r.get("education_raw"))).most_common(3))
put("edu_v4_rows", dict(Counter(L.education_of(r.get("education_raw")) for r in rows).most_common()))
put("edu_v4_deduped", dict(Counter(L.education_of(r.get("education_raw")) for r in deduped).most_common()))
put("edu_mapping", {lvl: dict(Counter((r.get("education_raw") or "").strip() for r in rows
                                     if L.education_of(r.get("education_raw")) == lvl).most_common())
                    for lvl in L.EDUCATIONS})
unk = [r for r in deduped if L.education_of(r.get("education_raw")) == "未注明"]
put("edu_unspecified_text_candidates", sum(1 for r in unk if L.EDU_IN_TEXT.search(
    (r.get("cohort_raw") or "") + " " + (r.get("description_raw") or ""))))

# ------------------------------------------------------------------ 5. 专业
put("major_unspecified_now", sum(r.get("major_normalized") == "未披露" for r in rows))
put("major_unspecified_now_pct", pct(N["major_unspecified_now"], len(rows)))
mr = Counter((r.get("major_requirements_raw") or "").strip() for r in rows)
put("major_placeholder_rows", {k or "(空)": mr.get(k, 0) for k in ("", "未披露", "详见职位描述")})
put("major_placeholder_norm_other", sum(1 for r in rows if (r.get("major_requirements_raw") or "").strip() in ("未披露", "详见职位描述")
                                        and not r.get("major_tags") and r.get("major_normalized") == "其他"))
put("major_unlimited_rows", sum(1 for r in rows if L.MAJOR_UNLIMITED.search(r.get("major_requirements_raw") or "")))
put("major_contains_buxian_substring", sum("不限" in (r.get("major_requirements_raw") or "") for r in rows))
put("major_v4_rows", dict(Counter(L.major_category_of(r) for r in rows).most_common()))
put("major_v4_deduped", dict(Counter(L.major_category_of(r) for r in deduped).most_common()))
put("major_v4_unspecified_pct_deduped", pct(N["major_v4_deduped"].get("未注明", 0), len(deduped)))

# ------------------------------------------------------------------ 6. 截止日
tbl = Counter()
for r in rows:
    d = L.parse_date(r.get("deadline"))
    tbl[(r.get("deadline_type") or "(空)", "有日期" if d else ("无" if not r.get("deadline") else "非日期文本"))] += 1
put("dl_type_x_date", {f"{a}|{b}": n for (a, b), n in tbl.most_common()})
put("dl_type_counts", dict(Counter(r.get("deadline_type") or "(空)" for r in rows).most_common()))


def v3_window(days):
    end = L.TODAY + dt.timedelta(days=days)
    n = 0
    for r in rows:
        if r.get("deadline_type") != "explicit" or r.get("status") in {"removed", "expired", "unverified"}:
            continue
        d = L.parse_date(r.get("deadline"))
        if d and L.TODAY <= d <= end:
            n += 1
    return n


def v4_window(rs, days):
    end = L.TODAY + dt.timedelta(days=days)
    by = Counter()
    for r in rs:
        d, kind = L.deadline_of(r)
        if d and L.TODAY <= d <= end and L.status_of(r, d) not in ("已截止", "已下线"):
            by[r.get("deadline_type") or "(空)"] += 1
    return by


for days in (7, 30):
    put(f"dl_v3_{days}d", v3_window(days))
    by = v4_window(rows, days)
    put(f"dl_v4_{days}d", sum(by.values()))
    put(f"dl_v4_{days}d_by_original_type", dict(by.most_common()))
    put(f"dl_v4_{days}d_deduped", sum(v4_window(deduped, days).values()))
put("dl_missed_30d_timestamp_fixed", N["dl_v4_30d_by_original_type"].get("timestamp", 0)
    + N["dl_v4_30d_by_original_type"].get("固定截止", 0))
ud = [r for r in rows if r.get("deadline_type") == "undisclosed" and L.parse_date(r.get("deadline"))]
put("dl_undisclosed_with_date", len(ud))
put("dl_undisclosed_with_date_source", Counter(r.get("source_name") for r in ud).most_common())
put("dl_undisclosed_with_date_format_len", dict(Counter(len(r["deadline"]) for r in ud)))
put("dl_undisclosed_with_date_scope", dict(Counter(str(r.get("deadline_scope")) for r in ud)))
put("dl_undisclosed_with_date_in_30d", N["dl_v4_30d_by_original_type"].get("undisclosed", 0))
put("dl_placeholder_2099", sum(1 for r in rows if (L.parse_date(r.get("deadline")) or dt.date(1, 1, 1)).year >= 2099))
put("dl_nondate_text", dict(Counter(r.get("deadline") for r in rows if r.get("deadline") and not L.parse_date(r.get("deadline")))))
put("dl_past_today", sum(1 for r in rows if (d := L.parse_date(r.get("deadline"))) and d < L.TODAY))
put("dl_v4_kind_rows", dict(Counter(L.deadline_of(r)[1] for r in rows).most_common()))
put("dl_v4_kind_deduped", dict(Counter(L.deadline_of(r)[1] for r in deduped).most_common()))
put("dl_status_unverified_explicit", sum(1 for r in rows if r.get("status") == "unverified" and r.get("deadline_type") == "explicit"))
fut = [r for r in rows if (d := L.parse_date(r.get("published_at"))) and d > L.TODAY]
put("published_at_future_rows", len(fut))
put("published_at_future_scope", Counter(str(r.get("published_at_scope")) for r in fut).most_common(3))
put("published_at_future_source", Counter(r.get("source_name") for r in fut).most_common(3))
put("published_at_missing_rows", sum(1 for r in rows if not L.parse_date(r.get("published_at"))))
put("major_raw_contains_duties", sum(1 for r in rows if "岗位职责" in (r.get("major_requirements_raw") or "")))

# ------------------------------------------------------------------ 7. 城市
put("city_norm_quanguo", sum(r.get("city_normalized") == "全国" for r in rows))
put("city_norm_undisclosed", sum(r.get("city_normalized") == "未披露" for r in rows))
put("city_norm_undisclosed_raw", dict(Counter(json.dumps(r.get("cities"), ensure_ascii=False) for r in rows
                                               if r.get("city_normalized") == "未披露")))
put("cities_norm_contains_quanguo", sum("全国" in (r.get("cities_normalized") or []) for r in rows))
put("cities_raw_quanguo_or_zhongguo", sum(any(c in ("全国", "中国") for c in (r.get("cities") or [])) for r in rows))
area = [r for r in rows if any("area_code" in str(c) for c in (r.get("cities") or []))]
put("city_area_code_rows", len(area))
put("city_area_code_source", Counter(r.get("source_name") for r in area).most_common(3))
put("city_multi_rows", sum(len(r.get("cities_normalized") or []) > 1 for r in rows))
v4c = [L.cities_of(r) for r in rows]
put("city_v4_quanguo_rows", sum("全国" in c for c in v4c))
put("city_v4_unspecified_rows", sum(not c for c in v4c))
odd = Counter(c for cs in v4c for c in cs if re.search(r"-|省|自治区|\{|'", c))
put("city_v4_odd_values", dict(odd.most_common(8)))
cmp = {}
for city in ("北京", "上海", "深圳", "杭州", "成都"):
    v3 = sum(city in json.dumps([r.get("city_normalized"), r.get("cities", [])], ensure_ascii=False) for r in rows)
    exp = sum(city in c for c in v4c)
    nat = sum("全国" in c and city not in c for c in v4c)
    cmp[city] = {"v3_substring": v3, "v4_explicit": exp, "v4_quanguo": nat, "v4_unspecified": N["city_v4_unspecified_rows"],
                 "v4_total": exp + nat + N["city_v4_unspecified_rows"]}
put("city_compare_rows", cmp)
v4cd = [L.cities_of(r) for r in deduped]
put("city_v4_deduped_quanguo", sum("全国" in c for c in v4cd))
put("city_v4_deduped_unspecified", sum(not c for c in v4cd))

# ------------------------------------------------------------------ 8. 地区 / 状态 / 招聘类型 / 行业
reg = Counter(r.get("region") or "" for r in rows)
put("region_raw_distinct", len(reg))
put("region_raw_mainland_variants", {k: reg[k] for k in ("mainland", "内地", "全国", "中国大陆", "中国")})
put("region_raw_overseas_variants", {k: reg[k] for k in ("overseas", "海外")})
put("region_raw_empty", reg[""])
other = {k: v for k, v in reg.items() if k and k not in L.MAINLAND | L.OVERSEAS}
put("region_raw_city_like_rows", sum(other.values()))
put("region_raw_city_like_distinct", len(other))
put("region_v4_rows", dict(Counter(L.region_of(r, c) for r, c in zip(rows, v4c)).most_common()))
put("region_v4_deduped", dict(Counter(L.region_of(r, L.cities_of(r)) for r in deduped).most_common()))
ov_bad = [r for r, c in zip(rows, v4c) if "海外" in L.region_of(r, c) and not r.get("overseas_flag")]
put("region_overseas_city_but_flag_false", len(ov_bad))
put("region_overseas_city_but_flag_false_source", Counter(r.get("source_name") for r in ov_bad).most_common(3))
put("region_flag_true_but_no_overseas_city", sum(1 for r, c in zip(rows, v4c)
                                                 if r.get("overseas_flag") and "海外" not in L.region_of(r, c)))
put("region_multi_rows", sum(1 for r, c in zip(rows, v4c) if "、" in L.region_of(r, c)))
put("overseas_cities_listed", len(L.OVERSEAS_CITIES))
put("city_alias_rows", sum(1 for r in rows if any(str(x) in L.CITY_ALIASES and str(x) not in ("中国",)
                                                   for x in (r.get("cities_normalized") or []))))
put("city_non_city_token_rows", sum(1 for r in rows if any(str(x) in L.NON_CITY for x in (r.get("cities_normalized") or []))))
PROV = re.compile(r"(省|自治区)$")
DIST = re.compile(r"[区县]$")
NOT_DIST = re.compile(r"新区|园区|特别行政区")
put("city_province_level_rows", sum(1 for cs in v4c if any(PROV.search(c) for c in cs)))
put("city_province_level_top", Counter(c for cs in v4c for c in cs if PROV.search(c)).most_common(5))
put("city_district_level_rows", sum(1 for cs in v4c if any(DIST.search(c) and not NOT_DIST.search(c) for c in cs)))
put("city_district_level_top", Counter(c for cs in v4c for c in cs if DIST.search(c) and not NOT_DIST.search(c)).most_common(5))
put("city_v4_distinct_deduped", len({c for r in deduped for c in L.cities_of(r)}))
put("status_raw", dict(Counter(r.get("status") for r in rows).most_common()))
put("status_raw_x_source", Counter(f"{r.get('status')}|{(r.get('source_name') or '')[:12]}" for r in rows
                                   if r.get("status") != "open").most_common(4))
put("status_unverified_is_apply_false", sum(1 for r in rows if r.get("status") == "unverified" and r.get("source_is_apply_raw") is False))
put("status_v4_rows", dict(Counter(L.status_of(r, L.deadline_of(r)[0]) for r in rows).most_common()))
put("rtype_rows", dict(Counter(r.get("recruitment_type") for r in rows).most_common()))
put("rtype_deduped", dict(Counter(r.get("recruitment_type") for r in deduped).most_common()))
put("industry_rows", dict(Counter(r.get("industry") for r in rows).most_common()))
put("industry_deduped", dict(Counter(r.get("industry") for r in deduped).most_common()))
put("companies_distinct_deduped", len({r.get("recruitment_unit") for r in deduped}))

# ------------------------------------------------------------------ 9. 返回大小
v3b = [L.nbytes(L.v3_public(r)) for r in rows]
put("size_v3_public_per_row", dist(v3b))
items, as_of = L.build()
put("data_as_of", as_of)
v4b = [L.nbytes(it) for it in items]
put("size_v4_item_per_row", dist(v4b))
put("size_description_share_v4", round(sum(L.nbytes(it.get("description_raw", "")) - 2 for it in items) / sum(v4b), 3))
# 复算 A 包默认调用（线上逻辑，limit=10），用来校准
v3sorted = sorted(rows, key=lambda r: (r.get("published_at") or "", r.get("id") or ""), reverse=True)
page = v3sorted[:10]
env_a = {"applied_filters": {}, "data_as_of": L.data_as_of(rows), "数据截至时间": L.data_as_of(rows),
         "source_urls": sorted({r["source_url"] for r in page}), "jobs": [L.v3_public(r) for r in page],
         "total": len(rows), "offset": 0, "next_offset": 10, "suggestion": None}
put("size_release_A_default_recomputed", L.nbytes(env_a))
put("size_release_A_default_measured", json.loads((L.ROOT.parent / "qiuzhao-doubao-fix-20260911" / "evidence" / "sizes_A.json")
                                                  .read_text())["default_call"])
# v4：默认排序（发布时间倒序）下逐页切分
order = sorted(items, key=lambda it: it["id"], reverse=True)
order.sort(key=lambda it: it["published_at"] or "", reverse=True)
envelope = L.nbytes({**L.jobs_search(items, as_of, keyword="__none__"), "jobs": []})
put("size_v4_envelope", envelope)
CJK = re.compile(r"[　-〿一-鿿＀-￯]")


def page_stats(n):
    sizes, over, toks = [], 0, []
    for i in range(0, len(order) - n + 1, n):
        chunk = order[i:i + n]
        text = json.dumps(chunk, ensure_ascii=False, separators=(",", ":"))
        b = len(text.encode()) + envelope
        sizes.append(b)
        over += len(text.encode()) > L.BUDGET_BYTES
        cjk = len(CJK.findall(text))
        toks.append(cjk + (len(text) - cjk) / 4)
    return {"pages": len(sizes), **dist(sizes), "pages_over_budget": over,
            "est_tokens_mean": round(statistics.mean(toks)), "est_tokens_p95": round(q(toks, .95)),
            "est_tokens_max": round(max(toks))}


put("size_v4_pages", {str(n): page_stats(n) for n in (5, 10, 20, 30, 50)})
default_payload = L.jobs_search(items, as_of)
text = json.dumps(default_payload, ensure_ascii=False, separators=(",", ":"))
put("size_v4_default_call", {"result_json": len(text.encode()),
                             "as_text_content_on_wire": len(json.dumps(text, ensure_ascii=False).encode()),
                             "double_estimate": len(text.encode()) + len(json.dumps(text, ensure_ascii=False).encode())})
big = sorted(items, key=L.nbytes, reverse=True)[:L.PAGE_SIZE_MAX]
put("size_v4_worst_page20", L.nbytes(big) + envelope)

# ------------------------------------------------------------------ 10. 字段归类
FIELD_CLASS = {
    # 业务字段：原样输出
    "id": ("业务", "id", "岗位唯一标识，jobs_detail 的入参来源；去重后唯一"),
    "job_title": ("业务", "job_title", "岗位名称"),
    "education_raw": ("业务", "education_raw", "学历原文，供核对；6 种乱码值输出为空"),
    "cohort_raw": ("业务", "cohort_raw", "届别/资格原文，是届别依据“岗位写明”的出处"),
    "application_url": ("业务", "application_url", "投递入口"),
    "source_url": ("业务", "source_url", "原公告或岗位页，回答必须附带"),
    "source_name": ("业务", "source_name", "来源名称"),
    "description_raw": ("业务", "description_raw", "岗位描述原文；约占 v4 每条字节的一半（size_description_share_v4），按决定 3 保留"),
    "recruitment_type": ("业务", "recruitment_type", "校园/实习/社会招聘，筛选与分组字段"),
    "industry": ("业务", "industry", "行业，筛选与分组字段"),
    "country": ("业务", "country", "国家"),
    "contracting_entity": ("业务", "contracting_entity", "签约主体，与招聘单位不同时学生需要知道"),
    "major_requirements_raw": ("业务", "major_requirements_raw", "专业要求原文"),
    "major_tags": ("业务", "major_tags", "专业标签"),
    "recruiting_unit_raw": ("业务", "recruiting_unit_raw", "具体用人单位（分公司、研究院）"),
    "hiring_department_raw": ("业务", "hiring_department_raw", "用人部门"),
    "parent_unit_raw": ("业务", "parent_unit_raw", "上级单位"),
    "announcement_url": ("业务", "announcement_url", "招聘公告链接"),
    "campaign_url": ("业务", "campaign_url", "招聘专场链接"),
    "job_listing_url": ("业务", "job_listing_url", "岗位列表页"),
    "status_note": ("业务", "status_note", "状态说明原文"),
    "industry_tags": ("业务", "industry_tags", "细分行业标签"),
    "reviewed_at": ("业务", "reviewed_at", "该条核验时间；data_as_of 取全库最大值"),
    # 改名 / 合并 / 修正：原字段不再单独出现，信息进入右侧输出字段
    "recruitment_unit": ("改名", "company", "与筛选参数 company、分组 company 同名，组值可直接填回"),
    "company": ("合并", "company", "444 条，值与 recruitment_unit 完全相同"),
    "title": ("合并", "job_title", "204 条，值与 job_title 完全相同"),
    "job_id": ("合并", "id", "65 条，值与 id 完全相同"),
    "detail_url": ("合并", "source_url", "30 条，值与 source_url 完全相同"),
    "category": ("合并", "job_category_raw", "204 条，值与 job_category 完全相同"),
    "job_category": ("改名", "job_category_raw", "原文类目；把 job_category 这个名字让给修正后的大类，与筛选参数取值一致"),
    "job_category_normalized": ("改名+修正", "job_category", "修正错分后输出，取值=筛选参数 job_category 的枚举"),
    "graduation_year_normalized": ("改名+改类型", "graduation_years + graduation_year_basis",
                                   "单值改多值并带依据；原字段把两届压成一届、把活动标题里的届别丢成未披露"),
    "campaign_cohort_raw": ("改名", "campaign_title", "内容是招聘活动标题，不是届别"),
    "batch_name": ("合并", "campaign_title", "477 条阿里巴巴批次名，性质同活动标题"),
    "major_normalized": ("改名+修正", "major_category", "与分组名一致；新增 不限、未注明 两个值"),
    "cities": ("合并", "cities", "原文城市；与 cities_normalized 合成一个修正后的列表（区县信息不再输出）"),
    "cities_normalized": ("合并+修正", "cities", "修复 area_code 字典串；中国→全国；未披露/未知→空列表"),
    "city_normalized": ("合并", "cities", "只存第一个城市，多城市岗位会漏；由 cities 取代"),
    "deadline": ("修正", "deadline", "统一为 YYYY-MM-DD 或 null；2099 占位日期置 null"),
    "deadline_type": ("改名+修正", "deadline_kind", "8 种写法收成 明确日期 / 招满即止或长期 / 未注明"),
    "status": ("修正", "status", "open/active/qualified→招聘中，unverified→未核验，截止日已过→已截止"),
    "published_at": ("修正", "published_at", "三种格式统一为 YYYY-MM-DD"),
    "region": ("合并+修正", "region", "五种大陆写法统一为 中国大陆；区县写进 region 的忽略"),
    "overseas_flag": ("合并", "region", "与 region=海外 重复"),
    "recruitment_type_raw": ("合并", "recruitment_type", "归一化来源，已体现在 recruitment_type"),
    "nature_raw": ("合并", "recruitment_type", "同上，只有“校招”一个值"),
    "job_code": ("合并", "job_code", "岗位编号，国企投递时常要填"),
    "position_code": ("合并", "job_code", "146 条，性质同 job_code"),
    # 仅内部：不输出
    "source_record_id": ("内部", "", "上游记录号，已拼进 id"),
    "evidence_path": ("内部", "", "服务器本地证据文件路径"),
    "announcement_evidence_path": ("内部", "", "服务器本地证据文件路径"),
    "directory_evidence_path": ("内部", "", "服务器本地证据文件路径"),
    "deadline_scope": ("内部", "", "采集流程标记：截止日取自岗位还是公告"),
    "published_at_scope": ("内部", "", "采集流程标记：发布日取自哪一层"),
    "cohort_scope": ("内部", "", "采集流程标记；信息已体现在 graduation_year_basis"),
    "requirements_scope": ("内部", "", "39 条的采集范围标记"),
    "education_scope": ("内部", "", "39 条的采集范围标记"),
    "job_title_scope": ("内部", "", "39 条的采集范围标记"),
    "recruitment_scope_note": ("内部", "", "8 条的采集范围标记"),
    "record_kind": ("内部", "", "上游记录类型"),
    "incomplete": ("内部", "", "采集完整性标记，出现的 13,000 条全为 false"),
    "source_status_raw": ("内部", "", "上游状态码，已折算进 status"),
    "source_is_apply_raw": ("内部", "", "上游可投递标记，已折算进 status（false→未核验）"),
    "source_group_key": ("内部", "", "上游分组键"),
    "company_id": ("内部", "", "上游企业 id"),
    "first_seen_at": ("内部", "", "采集时间戳"),
    "verified_at": ("内部", "", "采集时间戳，与 reviewed_at 不一致"),
    "fortune_rank": ("内部", "", "出现的 65 条全为 null"),
}
missing = [f for f in fields if f not in FIELD_CLASS]
extra = [f for f in FIELD_CLASS if f not in fields]
assert not missing and not extra, (missing, extra)
put("field_class_counts", dict(Counter(("业务" if c == "业务" else "内部" if c == "内部" else "改名/合并/修正")
                                       for c, _, _ in FIELD_CLASS.values())))
lines = ["| # | 原字段 | 出现行数 | 非空行数 | 归类 | v4 输出为 | 理由 |", "|---:|---|---:|---:|---|---|---|"]
order_cls = {"业务": 0}
for i, f in enumerate(sorted(fields, key=lambda f: (0 if FIELD_CLASS[f][0] == "业务" else 2 if FIELD_CLASS[f][0] == "内部" else 1,
                                                    -sum(f in r for r in rows))), 1):
    cls, target, why = FIELD_CLASS[f]
    present = sum(f in r for r in rows)
    nonempty = sum(r.get(f) not in (None, "", [], {}) for r in rows)
    lines.append(f"| {i} | `{f}` | {present:,} | {nonempty:,} | {cls} | {('`' + target + '`') if target else '—'} | {why} |")
(EV / "field_inventory.md").write_text("\n".join(lines) + "\n")

(EV / "numbers.json").write_text(json.dumps(N, ensure_ascii=False, indent=1) + "\n")
print(json.dumps(N, ensure_ascii=False, indent=1))
