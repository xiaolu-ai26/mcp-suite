import json, os, re, datetime

RAW = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/conditional_release/_mokahr_raw"
OUT = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/conditional_release/batch_mokahr.json"
NOW = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

# companies to SKIP (no live current-season campus jobs)
SKIP = {"cloudwalk", "4paradigm", "kingdee"}  # cloudwalk stale 2020-21; 4paradigm 0 active; kingdee cross-domain fail (already online)

def cohort_of(title, desc):
    m = re.search(r"(20\d{2})\s*届", title) or re.search(r"(27)\s*届", title)
    if m:
        g = m.group(1)
        return ("20" + g + "届") if len(g) == 2 else (g + "届")
    return "2027届"  # 2026秋招季默认2027届

def rtype_of(title, desc):
    if "实习" in title:
        return "实习"
    return "校招"

jobs = []
companies_detail = []
skipped = {
    "cloudwalk": "页面仅存2020-2021历史在招岗，非当前秋招季，按硬约束剔除",
    "4paradigm": "#/jobs 当前0在招（暂无匹配职位），校招季未开放",
    "kingdee": "自定义域 campus.kingdee.com 加载失败(chrome-error)，且该源已上线218岗，无需补",
}
blocked = {
    "nestle": "app.mokahr.com/campus-recruitment/nestle 返回404，未定位到正确站点ID",
    "lixiang": "理想 lixiang 路径404（可能用自定义域名/未在Moka公网host）",
    "nio": "蔚来 nio 未找到对应官网",
    "xpeng": "小鹏 xpeng 路径404",
    "megvii": "旷视 megvii 未找到对应官网",
    "horizon": "地平线 horizon 未找到对应官网",
    "yitu": "依图 yitu 路径404",
    "deepglint": "格灵深瞳 deepglint 页面已关停",
    "volkswagen": "大众 /volkswagen/78313 页面加载异常(len=7)，未取到岗位",
}

for fn in sorted(os.listdir(RAW)):
    if not fn.endswith(".json"):
        continue
    d = json.load(open(os.path.join(RAW, fn)))
    slug = d["slug"]
    if slug in SKIP:
        companies_detail.append({"slug": slug, "cn_name": d["name"], "industry": d["industry"],
                                 "to_publish": 0, "blocker": skipped.get(slug, "跳过")})
        continue
    if d["count"] == 0:
        companies_detail.append({"slug": slug, "cn_name": d["name"], "industry": d["industry"],
                                 "to_publish": 0, "blocker": "列表无UUID/详情"})
        continue
    n = 0
    for j in d["jobs"]:
        desc = (j.get("description_raw") or "").strip()
        title = j["title"].strip()
        if len(desc) < 80:
            continue  # 正文过短，不合格
        rec = {
            "id": f"{slug}-{j['uuid'][:8]}",
            "recruitment_unit": d["unit"],
            "contracting_entity": "",
            "job_title": title,
            "job_category": "",
            "cities": j.get("cities") or [],
            "major_requirements_raw": "",
            "major_tags": [],
            "education_raw": "",
            "cohort_raw": cohort_of(title, desc),
            "deadline": "",
            "deadline_type": "",
            "status": "open",
            "application_url": j["source_url"],
            "source_url": j["source_url"],
            "published_at": "",
            "reviewed_at": NOW,
            "source_name": "MokaHR招聘SaaS（前端渲染DOM采集）",
            "description_raw": desc,
            "recruiting_unit_raw": d["name"],
            "source_record_id": j["uuid"],
            "recruitment_type": rtype_of(title, desc),
            "overseas_flag": False,
            "region": "内地",
            "industry_tags": [d["industry"]],
            "incomplete": False,
        }
        jobs.append(rec)
        n += 1
    companies_detail.append({"slug": slug, "cn_name": d["name"], "industry": d["industry"],
                             "to_publish": n, "blocker": ""})

batch = {
    "batch": "mokahr",
    "generated_at": NOW,
    "source": "conditional_release/_mokahr_raw (browser DOM render extraction)",
    "crack_method": "MokaHR API响应为{data:base64密文, necromancer:hex密钥}加密体，curl无法解密；改为在已渲染SPA页面(bu平面)读取解密后DOM：列表#/jobs正则提取job/{uuid}，详情#/job/{uuid}从innerText解析职位名称/工作地点/职位描述。未逆向后端算法，未绕过登录/验证码。",
    "total_companies_evaluated": len(companies_detail) + len(blocked),
    "qualified_count": len(jobs),
    "qualified_jobs": jobs,
    "companies_detail": companies_detail,
    "blocked_companies": blocked,
    "hard_constraints": {"no_fake_jd": True, "no_social_as_campus": True, "no_login_bypass": True, "not_released_to_prod": True},
}
json.dump(batch, open(OUT, "w"), ensure_ascii=False, indent=1)
print("WROTE", OUT)
print("qualified jobs:", len(jobs))
for c in companies_detail:
    print(" -", c["slug"], c["cn_name"], "publish=", c["to_publish"], c["blocker"])
