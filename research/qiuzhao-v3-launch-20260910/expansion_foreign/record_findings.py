#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append per-company findings to foreign_companies.jsonl and write staging/{slug}/jobs.json.
Usage: python3 record_findings.py  (findings dict is embedded below)
"""
import json, os

BASE = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign"
REG = os.path.join(BASE, "foreign_companies.jsonl")

# findings: slug -> dict
F = {
# ---- batch 1 FMCG ----
"nestle": {
  "investigation_status":"有可用岗位部分覆盖",
  "china_campus_status":"2027校招在招(管培生项目)",
  "platform":"MokaHR",
  "entry_url":"https://app.mokahr.com/campus-recruitment/nestlegcr",
  "official_career_site":"https://www.nestlecareers.cn/  /  https://www.nestle.com.cn/jobs/students-graduates",
  "access_mode":"MokaHR SPA(列表经高校就业网证实活跃)；stg.nestlecareers.cn可渲染",
  "pagination":"MokaHR校招项目页",
  "scope":"中国内地 2027届校招管培生(市场/供应链/研发/财务/HR/IT/销售等职能)，每人限投2岗，截止2026-11-30",
  "job_count":None,
  "has_queryable_jobs":True,
  "sample_jobs":[
    {"title":"雀巢中国2027校园招聘管培生(市场/供应链/研发等职能)","location":"上海等","note":"MokaHR校招项目nestlegcr；暨南/郑大/西交等就业网2026-09转发证实","url":"https://app.mokahr.com/campus-recruitment/nestlegcr"},
  ],
  "blocker_reason":"",
},
"pepsico": {
  "investigation_status":"有可用岗位部分覆盖",
  "china_campus_status":"2027综合管理培训生在招",
  "platform":"Phenom + 51job",
  "entry_url":"https://www.pepsicojobs.com/china?lang=zh-CN",
  "official_career_site":"https://www.pepsicojobs.com/china ; 校招 http://campus.51job.com/pepsico",
  "access_mode":"Phenom中国区页面可web.fetch读取(已验证)",
  "pagination":"Phenom地点/职能筛选",
  "scope":"中国内地；社招(FULL TIME销售岗)+2027综合管理培训生(上海)",
  "job_count":None,
  "has_queryable_jobs":True,
  "sample_jobs":[
    {"title":"GTM 业务发展副经理(L07)","location":"Beijing, China","note":"PepsiCo China主要岗位，FULL TIME 销售","url":"https://www.pepsicojobs.com/china?lang=zh-CN"},
    {"title":"百事公司2027年度综合管理培训生","location":"上海","note":"2026-09-07发布，管培生(销售/市场/战略/财务轮岗)，51job来源","url":"http://campus.51job.com/pepsico"},
  ],
  "blocker_reason":"",
},
"cocacola": {
  "investigation_status":"入口已证实",
  "china_campus_status":"全球站当前0在招；中国区经装瓶厂(中粮可口可乐)招聘",
  "platform":"Workday(Taleo) + 智联",
  "entry_url":"https://careers.coca-colacompany.com/",
  "official_career_site":"https://www.coca-colacompany.com/careers ; 中粮可口可乐 https://cofcoko.zhaopin.com",
  "access_mode":"全球站可访问但当前0 Live Results；中国装瓶厂校招走智联",
  "pagination":"",
  "scope":"中国内地校招以装瓶公司(中粮可口可乐各区域)为主，非集团直管",
  "job_count":0,
  "has_queryable_jobs":False,
  "sample_jobs":[
    {"title":"中粮可口可乐华中饮料 2026校园招聘","location":"湖南","note":"装瓶厂校招，智联页面","url":"https://cofcoko.zhaopin.com/job/index.html"},
  ],
  "blocker_reason":"可口可乐集团全球careers当前0个live职位；中国校招分散在各装瓶厂(中粮/中萃等)，非集团统一入口",
},
"mars": {
  "investigation_status":"入口已证实",
  "china_campus_status":"2027校招在招(MLE/Functional LE)",
  "platform":"Workday + 51job",
  "entry_url":"https://careers.mars.com/cn/zh/students-graduates",
  "official_career_site":"https://careers.mars.com/cn/zh/students-graduates ; 中国 http://marscareer.51job.com",
  "access_mode":"全球Workday项目页可web.fetch读取(已验证)",
  "pagination":"",
  "scope":"中国内地2027校招，城市广州/上海/北京/嘉兴/天津；项目含General LE与Functional LE(Finance/R&D/Procurement/Engineering/Sales)",
  "job_count":None,
  "has_queryable_jobs":True,
  "sample_jobs":[
    {"title":"Mars Leadership Experience (MLE) 综合管培","location":"上海等","note":"三年轮岗(Sales/Marketing + Supply Chain/Manufacturing)","url":"https://careers.mars.com/cn/zh/students-graduates"},
  ],
  "blocker_reason":"",
},
"danone": {
  "investigation_status":"有可用岗位部分覆盖",
  "china_campus_status":"2027管培生在招(职能+医药)，截止2026-10-31",
  "platform":"MokaHR",
  "entry_url":"https://app.mokahr.com/campus-recruitment/danone/170511",
  "official_career_site":"https://careersite.danone.com.cn/zh_CN/careers/Campus/index.html",
  "access_mode":"careersite可web.fetch读取(已验证直出12个岗位)",
  "pagination":"",
  "scope":"中国内地2027校招，毕业时间2025-01至2027-07本科+；职能管培+医药管培两大项目",
  "job_count":12,
  "has_queryable_jobs":True,
  "sample_jobs":[
    {"title":"研发管培生","location":"上海(达能中国)","note":"2027达能管培，careersite直出","url":"https://careersite.danone.com.cn/zh_CN/careers/Campus/index.html"},
    {"title":"市场营销管培生","location":"上海/广州/香港","note":"无专业限制","url":"https://careersite.danone.com.cn/zh_CN/careers/Campus/index.html"},
    {"title":"医学市场管培生","location":"上海(达能生命早期营养-儿科)","note":"医药管培，限医学药学类","url":"https://careersite.danone.com.cn/zh_CN/careers/Campus/index.html"},
  ],
  "blocker_reason":"",
},
"mondelez": {
  "investigation_status":"入口已证实",
  "china_campus_status":"2027 Taste The Future管培在招",
  "platform":"51job + Avature",
  "entry_url":"https://campus.51job.com/2026mdlz",
  "official_career_site":"http://www.mondelezinternational.com/careers/index.html ; 中国 www.mdlz.cn",
  "access_mode":"51job校招专题页；全球Avature(betterteam)",
  "pagination":"",
  "scope":"中国内地2027 Taste The Future管理培训生，上海总部",
  "job_count":None,
  "has_queryable_jobs":True,
  "sample_jobs":[
    {"title":"亿滋中国2027 Taste The Future 管理培训生","location":"上海","note":"西交就业网2026-09-09发布","url":"https://campus.51job.com/2026mdlz"},
  ],
  "blocker_reason":"",
},
"colgate": {
  "investigation_status":"有可用岗位部分覆盖",
  "china_campus_status":"2027校招培训生在招",
  "platform":"Workday",
  "entry_url":"https://jobs.colgate.com/?locale=zh_CN",
  "official_career_site":"https://jobs.colgate.com/content/why-work-with-us/?locale=zh_CN",
  "access_mode":"Workday zh_CN；岗位经多高校就业网证实",
  "pagination":"",
  "scope":"中国内地2027校招，广州为主、上海、香港",
  "job_count":8,
  "has_queryable_jobs":True,
  "sample_jobs":[
    {"title":"市场培训生","location":"广州/上海","note":"2027高露洁校招，厦大/郑大/川大就业网","url":"https://jobs.colgate.com/?locale=zh_CN"},
    {"title":"全球技术研发中心培训生","location":"广州","note":"研发类","url":"https://jobs.colgate.com/?locale=zh_CN"},
  ],
  "blocker_reason":"",
},
"esteelauder": {
  "investigation_status":"有可用岗位部分覆盖",
  "china_campus_status":"时黛由你2027集团管培在招",
  "platform":"51job",
  "entry_url":"https://campus.51job.com/elccampus",
  "official_career_site":"http://campus.51job.com/elccampus",
  "access_mode":"51job校招专题页",
  "pagination":"",
  "scope":"上海，毕业2026-07至2027-06本硕博，招30人，薪资15-20k",
  "job_count":30,
  "has_queryable_jobs":True,
  "sample_jobs":[
    {"title":"“时黛由你”2027雅诗兰黛集团管培生","location":"上海","note":"先经2026暑期实习选拔再进2027管培；中央财大/北理工2026-09-01发布","url":"https://campus.51job.com/elccampus"},
  ],
  "blocker_reason":"",
},
"shiseido": {
  "investigation_status":"入口已证实",
  "china_campus_status":"全球站在招；中国区校招入口未单独定位",
  "platform":"自建(类Workday)",
  "entry_url":"https://careers.shiseido.com/",
  "official_career_site":"https://careers.shiseido.com/ ; 日本 https://recruit.shiseido.com/",
  "access_mode":"全球站多语种可访问",
  "pagination":"",
  "scope":"全球；中国区校招未在本轮定位到独立入口",
  "job_count":None,
  "has_queryable_jobs":False,
  "sample_jobs":[],
  "blocker_reason":"全球careers.shiseido.com可访问但本轮未筛出明确中国内地校招岗；日本recruit站面向日本新卒。中国区校招入口待后续定位",
},
"johnson": {
  "investigation_status":"入口已证实",
  "china_campus_status":"校招官网在招(含实习)",
  "platform":"自建",
  "entry_url":"https://chinacampus.jnj.com.cn/jnj/home/index/",
  "official_career_site":"https://careers.jnj.com.cn/jnj/home/index/",
  "access_mode":"自建SPA(哈希路由)，列表经高校就业网证实",
  "pagination":"",
  "scope":"中国内地；全职培训生+暑期实习(2027届)",
  "job_count":None,
  "has_queryable_jobs":True,
  "sample_jobs":[
    {"title":"医疗科技销售培训生","location":"中国","note":"chinacampus.jnj.com.cn；北化/太原理工就业网","url":"https://chinacampus.jnj.com.cn/jnj/home/index/"},
    {"title":"Technology Leadership Development Program 科技领导力发展项目","location":"中国","note":"TLDP","url":"https://chinacampus.jnj.com.cn/jnj/home/index/"},
  ],
  "blocker_reason":"",
},
}

# load registry
rows = [json.loads(l) for l in open(REG, encoding="utf-8")]
by = {r["slug"]: r for r in rows}

for slug, upd in F.items():
    if slug not in by:
        print("WARN missing slug", slug); continue
    r = by[slug]
    r["investigation_status"] = upd["investigation_status"]
    r["china_campus_status"] = upd["china_campus_status"]
    r["platform"] = upd["platform"]
    r["entry_url"] = upd["entry_url"]
    r["official_career_site"] = upd["official_career_site"]
    r["access_mode"] = upd["access_mode"]
    r["pagination"] = upd["pagination"]
    r["scope"] = upd["scope"]
    r["job_count"] = upd["job_count"]
    r["has_queryable_jobs"] = upd["has_queryable_jobs"]
    r["sample_jobs"] = upd["sample_jobs"]
    r["blocker_reason"] = upd["blocker_reason"]
    # staging jobs.json
    sdir = os.path.join(BASE, "staging", slug)
    os.makedirs(sdir, exist_ok=True)
    jobs_payload = {
        "company_slug": slug,
        "company_name": r["cn_name"],
        "country": r["country"],
        "platform": upd["platform"],
        "entry_url": upd["entry_url"],
        "access_mode": upd["access_mode"],
        "scope": upd["scope"],
        "has_queryable_jobs": upd["has_queryable_jobs"],
        "job_count_reported": upd["job_count"],
        "sample_jobs": upd["sample_jobs"],
        "blocker_reason": upd["blocker_reason"],
        "captured_at": "2026-09-10",
    }
    with open(os.path.join(sdir, "jobs.json"), "w", encoding="utf-8") as f:
        json.dump(jobs_payload, f, ensure_ascii=False, indent=2)

# rewrite registry
with open(REG, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

# stats
from collections import Counter
c = Counter(r["investigation_status"] for r in rows)
print("updated", len(F), "companies")
print("status counts so far:")
for k,v in c.items(): print(" ", k, v)
