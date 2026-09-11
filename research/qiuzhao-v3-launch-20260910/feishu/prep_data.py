#!/usr/bin/env python3
"""秋招岗位库 v3 - 飞书镜像数据准备脚本
产出:
  import_data/jobs_selected.csv / .json   精选岗位镜像 (>=100)
  import_data/source_status.csv / .json  来源状态 (24 registry + 50 companies)
  table_schema.json                       表结构定义
不包含任何 key / 凭证 / 简历信息。
"""
import json, csv, os, collections, datetime

BASE = "/Users/maxzhl/Projects/mcp-suite"
OUT = os.path.join(BASE, "research/qiuzhao-v3-launch-20260910/feishu")
IMP = os.path.join(OUT, "import_data")
os.makedirs(IMP, exist_ok=True)

# ---------- 行业映射 (按招聘单位) ----------
INDUSTRY_MAP = [
    ("中国邮政", "邮政物流"),
    ("中国联合网络通信", "通信运营"),
    ("中国移动", "通信运营"),
    ("中国电信", "通信运营"),
    ("中国航天科工", "航天军工"),
    ("中国能源建设", "能源电力"),
    ("国家能源", "能源电力"),
    ("中国广核", "能源电力"),
    ("中国机械科学研究总院", "机械制造"),
    ("中国建设银行", "银行金融"),
    ("中国银行", "银行金融"),
    ("腾讯", "互联网"),
]
def industry_of(unit: str) -> str:
    for k, v in INDUSTRY_MAP:
        if k in (unit or ""):
            return v
    return "其他"

def nature_of(job) -> str:
    """招聘性质: 校招/社招/实习/未知。本数据集均为2027届校招专场。"""
    txt = (job.get("cohort_raw","") or "") + (job.get("campaign_cohort_raw","") or "") + (job.get("record_kind","") or "")
    if "实习" in txt and "应届" not in txt and "校招" not in txt:
        return "实习"
    # 数据集整体为2027届校园招聘专场 (国聘/官网校招), 无社招/实习主路径
    return "校招"

def cohort_of(job) -> str:
    txt = job.get("cohort_raw","") or ""
    if "2027" in txt:
        return "2027届"
    if "2026" in txt:
        return "2026届"
    if job.get("campaign_cohort_raw"):
        return job["campaign_cohort_raw"][:20]
    return "应届"

# ---------- 读取生产快照 ----------
jobs = json.load(open(os.path.join(BASE, "qiuzhao/data/jobs.json")))
tencent = json.load(open(os.path.join(BASE, "research/qiuzhao-expansion-20260910/staging/tencent_jobs.json")))

def normalize(job, source_tag):
    cities = job.get("cities") or []
    return {
        "job_id": job.get("id",""),
        "岗位名称": job.get("job_title","") or "(未命名岗位)",
        "公司名称": job.get("recruitment_unit","") or job.get("recruiting_unit_raw",""),
        "招聘单位": job.get("recruitment_unit",""),
        "行业": industry_of(job.get("recruitment_unit","")),
        "招聘性质": nature_of(job),
        "毕业届别": cohort_of(job),
        "工作地点": "、".join(cities) if cities else "",
        "岗位大类": job.get("job_category","") or "",
        "投递截止": job.get("deadline") or "",
        "截止类型": "明确" if job.get("deadline_type")=="explicit" else "未披露",
        "原链接": job.get("source_url","") or "",
        "投递入口": job.get("application_url","") or "",
        "来源": source_tag or job.get("source_name",""),
        "状态": job.get("status","unknown"),
        "复核时间": (job.get("reviewed_at") or "")[:19].replace("T"," "),
        "备注": (job.get("status_note") or "")[:200],
    }

# ---------- 精选岗位: 生产快照按公司分层抽样, 优先 explicit deadline ----------
prod_norm = [normalize(j, j.get("source_name","")) for j in jobs]
# 只保留 open 且有明确截止的作为主样本
prod_eligible = [j for j in prod_norm if j["状态"]=="open" and j["截止类型"]=="明确"]
by_unit = collections.defaultdict(list)
for j in prod_eligible:
    by_unit[j["招聘单位"]].append(j)

selected = []
# 每个公司取若干, 覆盖不同岗位大类, 总量控制
per_unit_quota = {
    "中国邮政集团有限公司": 12,
    "中国联合网络通信集团有限公司": 12,
    "中国移动通信集团有限公司": 12,
    "中国航天科工集团有限公司": 12,
    "中国能源建设股份有限公司": 10,
    "国家能源投资集团有限责任公司": 10,
    "中国机械科学研究总院集团有限公司": 6,
    "中国建设银行股份有限公司": 6,
    "中国银行股份有限公司": 4,
    "中国电信集团有限公司": 4,
    "中国广核集团有限公司": 4,
}
seen_cat = collections.defaultdict(set)
for unit, quota in per_unit_quota.items():
    pool = by_unit.get(unit, [])
    picked = 0
    # 先按岗位大类去重选取
    by_cat = collections.defaultdict(list)
    for j in pool:
        by_cat[j["岗位大类"] or "未分类"].append(j)
    for cat, items in by_cat.items():
        if picked >= quota: break
        # 每个大类取1条
        selected.append(items[0])
        picked += 1
    # 不足则补
    if picked < quota:
        have = {id(x) for x in selected}
        for j in pool:
            if picked >= quota: break
            if id(j) not in have:
                selected.append(j); picked += 1

# 腾讯互联网岗位: 取20条不同job_category
ten_norm = [normalize(j, "腾讯校园招聘官方网站(staging)") for j in tencent]
ten_by_cat = collections.defaultdict(list)
for j in ten_norm:
    ten_by_cat[j["岗位大类"] or "未分类"].append(j)
ten_picked = []
for cat, items in sorted(ten_by_cat.items(), key=lambda x:-len(x[1])):
    if len(ten_picked) >= 24: break
    ten_picked.append(items[0])
# 若不足24, 补
i=0
while len(ten_picked) < 24 and i < len(ten_norm):
    if ten_norm[i] not in ten_picked:
        ten_picked.append(ten_norm[i])
    i += 1
selected.extend(ten_picked)

# 去重 by job_id
seen=set(); jobs_final=[]
for j in selected:
    if j["job_id"] in seen: continue
    seen.add(j["job_id"]); jobs_final.append(j)

print(f"[jobs] 精选岗位数: {len(jobs_final)}")
ind_ct = collections.Counter(j["行业"] for j in jobs_final)
print(f"[jobs] 行业分布: {dict(ind_ct)}")
nat_ct = collections.Counter(j["招聘性质"] for j in jobs_final)
print(f"[jobs] 招聘性质: {dict(nat_ct)}")
dl_ct = collections.Counter(j["截止类型"] for j in jobs_final)
print(f"[jobs] 截止类型: {dict(dl_ct)}")

# ---------- 来源状态表 ----------
reg = [json.loads(l) for l in open(os.path.join(BASE,"research/qiuzhao-expansion-20260910/sources_registry.jsonl"))]
comp = [json.loads(l) for l in open(os.path.join(BASE,"research/qiuzhao-expansion-20260910/companies.jsonl"))]
comp_by_id = {c["company_id"]: c for c in comp}

RANK_LABEL = {
    "fortune_global_500_2026": "财富世界500强",
    "fortune_china_500_2026": "财富中国500强",
    "forbes_best_employers_2025": "Forbes最佳雇主",
    "gptw_best_workplaces_2025": "GPTW最佳雇主",
}
def rank_labels(cid):
    c = comp_by_id.get(cid)
    labs=[]
    if c:
        for m in c.get("ranking_memberships",[]):
            lab = RANK_LABEL.get(m.get("list_id"))
            if lab and lab not in labs: labs.append(lab)
    if not labs:
        labs.append("行业种子")
    return labs

def platform_norm(pf):
    pf = pf or ""
    if "moka" in pf.lower(): return "Moka"
    if "beisen" in pf.lower() or "北森" in pf: return "北森"
    if "workday" in pf.lower(): return "Workday"
    if "phenom" in pf.lower(): return "Phenom"
    if "talentbrew" in pf.lower(): return "TalentBrew"
    if "liepin" in pf.lower(): return "无门户"
    if "self_built" in pf: return "自建"
    return "未知"

def status_from_reg(r):
    stage = r.get("integration_stage","")
    health = r.get("run_health","")
    exp = r.get("expected_total") or 0
    obs = r.get("observed_unique_total") or 0
    blocker = r.get("blocker_reason")
    if health == "blocked":
        return "访问受阻"
    if "阻塞" in stage:
        return "访问受阻"
    if health == "degraded":
        return "访问受阻"
    if stage == "source_discovered":
        return "入口已证实"
    if stage.startswith("A阶段-探源完成") and "列表级" in stage:
        return "有可用岗位部分覆盖"
    if "partial" in stage or health == "partial":
        return "有可用岗位部分覆盖"
    if stage == "samples_confirmed":
        if exp and obs and obs >= exp:
            return "声明范围完整"
        return "有可用岗位部分覆盖"
    return "待核验"

def last_probe(r):
    sj = r.get("sample_jobs") or []
    if sj and sj[0].get("collected_at"):
        return sj[0]["collected_at"]
    return "2026-09-10"

sources_final = []
for r in reg:
    slug = r["company_slug"]
    sources_final.append({
        "company_slug": slug,
        "公司名称": r.get("company_name",""),
        "行业": "、".join(r.get("job_categories") or [])[:60],
        "榜单归属": rank_labels(slug),
        "官方招聘入口": r.get("official_entry_url","") or "",
        "平台类型": platform_norm(r.get("platform_family","")),
        "处理状态": status_from_reg(r),
        "预计岗位数": r.get("expected_total") or 0,
        "已采集岗位数": r.get("observed_unique_total") or 0,
        "阻塞原因": r.get("blocker_reason") or "",
        "最后探源时间": last_probe(r),
        "适配器规格": (r.get("api_endpoint") or r.get("detail_url_pattern") or "")[:200],
    })

# 从 companies.jsonl 选 50 家 pending (排除已在 registry 的 slug)
reg_slugs = {r["company_slug"] for r in reg}
pend = [c for c in comp if c.get("investigation_status")=="pending" and c["company_id"] not in reg_slugs]
# 优先有榜单归属的, 再取其余
pend_ranked = [c for c in pend if c.get("ranking_memberships")]
pend_plain = [c for c in pend if not c.get("ranking_memberships")]
pick = (pend_ranked + pend_plain)[:50]
for c in pick:
    sources_final.append({
        "company_slug": c["company_id"],
        "公司名称": c.get("canonical_name",""),
        "行业": "、".join(c.get("industry_tags") or [])[:60],
        "榜单归属": rank_labels(c["company_id"]),
        "官方招聘入口": c.get("homepage_url","") or "",
        "平台类型": "未知",
        "处理状态": "未开始",
        "预计岗位数": 0,
        "已采集岗位数": 0,
        "阻塞原因": c.get("notes","") or "",
        "最后探源时间": "2026-09-10",
        "适配器规格": "",
    })

print(f"\n[sources] 来源状态记录数: {len(sources_final)} (registry={len(reg)}, companies_picked={len(pick)})")
st_ct = collections.Counter(s["处理状态"] for s in sources_final)
print(f"[sources] 处理状态分布: {dict(st_ct)}")

# ---------- 写 CSV (脱敏) ----------
job_fields = ["job_id","岗位名称","公司名称","招聘单位","行业","招聘性质","毕业届别","工作地点",
              "岗位大类","投递截止","截止类型","原链接","投递入口","来源","状态","复核时间","备注"]
with open(os.path.join(IMP,"jobs_selected.csv"),"w",newline="",encoding="utf-8-sig") as f:
    w=csv.DictWriter(f, fieldnames=job_fields); w.writeheader()
    for j in jobs_final: w.writerow({k:j.get(k,"") for k in job_fields})

src_fields = ["company_slug","公司名称","行业","榜单归属","官方招聘入口","平台类型","处理状态",
              "预计岗位数","已采集岗位数","阻塞原因","最后探源时间","适配器规格"]
with open(os.path.join(IMP,"source_status.csv"),"w",newline="",encoding="utf-8-sig") as f:
    w=csv.DictWriter(f, fieldnames=src_fields); w.writeheader()
    for s in sources_final:
        row={}
        for k in src_fields:
            v=s.get(k,"")
            if isinstance(v,list): v="、".join(v)
            row[k]=v
        w.writerow(row)

# ---------- 写 JSON (供 lark-cli batch create) ----------
# 岗位总表记录: select 字段值需与字段选项一致
job_records=[]
for j in jobs_final:
    rec = {
        "job_id": j["job_id"],
        "岗位名称": j["岗位名称"],
        "公司名称": j["公司名称"],
        "招聘单位": j["招聘单位"],
        "行业": j["行业"],
        "招聘性质": j["招聘性质"],
        "毕业届别": j["毕业届别"],
        "工作地点": j["工作地点"],
        "岗位大类": j["岗位大类"],
        "投递截止": j["投递截止"] + " 00:00:00" if j["投递截止"] else None,
        "截止类型": j["截止类型"],
        "原链接": j["原链接"],
        "投递入口": j["投递入口"],
        "来源": j["来源"],
        "状态": j["状态"],
        "复核时间": j["复核时间"] if j["复核时间"] else None,
        "备注": j["备注"] or None,
    }
    # 去掉 None 键
    rec = {k:v for k,v in rec.items() if v is not None and v!=""}
    job_records.append(rec)

src_records=[]
for s in sources_final:
    rec = {
        "company_slug": s["company_slug"],
        "公司名称": s["公司名称"],
        "行业": s["行业"] or "未登记",
        "榜单归属": s["榜单归属"],
        "官方招聘入口": s["官方招聘入口"] or None,
        "平台类型": s["平台类型"],
        "处理状态": s["处理状态"],
        "预计岗位数": s["预计岗位数"],
        "已采集岗位数": s["已采集岗位数"],
        "阻塞原因": s["阻塞原因"] or None,
        "最后探源时间": s["最后探源时间"] + " 00:00:00" if s["最后探源时间"] else None,
        "适配器规格": s["适配器规格"] or None,
    }
    rec = {k:v for k,v in rec.items() if v is not None and v!=""}
    src_records.append(rec)

json.dump({"create_records": job_records}, open(os.path.join(IMP,"jobs_selected.json"),"w"), ensure_ascii=False, indent=2)
json.dump({"create_records": src_records}, open(os.path.join(IMP,"source_status.json"),"w"), ensure_ascii=False, indent=2)

# ---------- table_schema.json ----------
schema = {
  "base_name": "秋招岗位库 v3 - 20260910",
  "sync_scope": "精选镜像，非全量；查询真源为服务器岗位快照 (qiuzhao/data/jobs.json 9191条 + staging/tencent_jobs.json 814条)",
  "tables": [
    {
      "table_name": "岗位总表",
      "purpose": "精选岗位镜像 (>=100条, 优先2027届校招/明确截止/多行业覆盖)",
      "fields": [
        {"name":"job_id","type":"text","desc":"岗位唯一ID"},
        {"name":"岗位名称","type":"text"},
        {"name":"公司名称","type":"text"},
        {"name":"招聘单位","type":"text"},
        {"name":"行业","type":"select","options":["邮政物流","通信运营","航天军工","能源电力","机械制造","银行金融","互联网","其他"]},
        {"name":"招聘性质","type":"select","options":["校招","社招","实习","未知"]},
        {"name":"毕业届别","type":"text"},
        {"name":"工作地点","type":"text","desc":"多城市用、分隔"},
        {"name":"岗位大类","type":"text"},
        {"name":"投递截止","type":"datetime","format":"yyyy-MM-dd"},
        {"name":"截止类型","type":"select","options":["明确","未披露"]},
        {"name":"原链接","type":"text","style":"url"},
        {"name":"投递入口","type":"text","style":"url"},
        {"name":"来源","type":"text"},
        {"name":"状态","type":"select","options":["open","expired","removed","unverified"]},
        {"name":"复核时间","type":"datetime","format":"yyyy-MM-dd HH:mm"},
        {"name":"备注","type":"text"}
      ]
    },
    {
      "table_name": "来源状态表",
      "purpose": "企业处理状态 (24家已探源 + 50家登记)",
      "fields": [
        {"name":"company_slug","type":"text","desc":"企业唯一slug"},
        {"name":"公司名称","type":"text"},
        {"name":"行业","type":"text"},
        {"name":"榜单归属","type":"select","multiple":True,"options":["财富世界500强","财富中国500强","Forbes最佳雇主","GPTW最佳雇主","行业种子"]},
        {"name":"官方招聘入口","type":"text","style":"url"},
        {"name":"平台类型","type":"select","options":["自建","Moka","北森","Workday","Phenom","TalentBrew","无门户","未知"]},
        {"name":"处理状态","type":"select","options":["未开始","入口已证实","采集中","有可用岗位部分覆盖","声明范围完整","未发现适用岗位","尚未开放","访问受阻","待核验","维护逾期"]},
        {"name":"预计岗位数","type":"number","precision":0},
        {"name":"已采集岗位数","type":"number","precision":0},
        {"name":"阻塞原因","type":"text"},
        {"name":"最后探源时间","type":"datetime","format":"yyyy-MM-dd"},
        {"name":"适配器规格","type":"text"}
      ]
    }
  ]
}
json.dump(schema, open(os.path.join(OUT,"table_schema.json"),"w"), ensure_ascii=False, indent=2)

print("\n[done] CSV/JSON/schema written to:", IMP)
print(f"  jobs_selected.csv rows={len(jobs_final)}")
print(f"  source_status.csv rows={len(sources_final)}")
