#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch 8: Consulting / Big4."""
import json, os
BASE = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign"
REG = os.path.join(BASE, "foreign_companies.jsonl")
F = {
"mckinsey": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"中国区2027校招正式启动","platform":"自建",
  "entry_url":"https://www.mckinsey.com/careers/search-jobs",
  "official_career_site":"https://www.mckinsey.com/careers/",
  "access_mode":"麦肯锡全球job search可按Greater China筛选","pagination":"","scope":"中国内地2027；商业分析师/Associate/暑期实习，北京上海深圳香港台北","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Business Analyst / Associate (Greater China)","location":"北京/上海/深圳/香港","note":"麦肯锡中国区2027校招2026-07-17启动","url":"https://www.mckinsey.com/careers/search-jobs"}],
  "blocker_reason":""},
"bcg": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"中国区2027校招在招(全职)","platform":"自建",
  "entry_url":"https://careers.bcg.com/global/en/locations/greater-china",
  "official_career_site":"https://careers.bcg.com/",
  "access_mode":"careers.bcg.com Greater China页","pagination":"","scope":"中国内地2027；Consulting Full-time GC Campus，上海北京深圳香港台北","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Consulting Full-time (GC Campus)","location":"上海/北京/深圳/香港","note":"BCG中国区2027校招","url":"https://careers.bcg.com/global/en/locations/greater-china"}],
  "blocker_reason":""},
"bain": {
  "investigation_status":"入口已证实","china_campus_status":"2027秋季校招正式启动","platform":"自建",
  "entry_url":"https://www.bain.com/careers/","official_career_site":"https://www.bain.com/careers/find-a-role/",
  "access_mode":"Bain careers","pagination":"","scope":"中国内地(北京/上海)；Associate/Consultant校招","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Bain Greater China Associate/Consultant","location":"北京/上海","note":"贝恩2027秋季校招","url":"https://www.bain.com/careers/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"deloitte": {
  "investigation_status":"入口已证实","china_campus_status":"中国校招在招(审计/咨询/税务)","platform":"自建/MokaHR",
  "entry_url":"https://www2.deloitte.com/cn/zh/careers.html","official_career_site":"https://www2.deloitte.com/cn/zh/careers/campus.html",
  "access_mode":"德勤中国校招页","pagination":"","scope":"中国内地2027；审计/税务/咨询/风控校招","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"德勤中国校招(审计/咨询)","location":"全国","note":"deloitte.com/cn校招","url":"https://www2.deloitte.com/cn/zh/careers.html"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"pwc": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"2027校招在招(审计/税务/咨询/交易)","platform":"MokaHR",
  "entry_url":"https://app.mokahr.com/campus-recruitment/pwc/148260",
  "official_career_site":"https://www.pwccn.com/zh/careers/students.html",
  "access_mode":"MokaHR pwc/148260(经浙大就业网证实)","pagination":"","scope":"中国内地2025-2027届；审计/税务/咨询/交易","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"普华永道2027校招 咨询服务部","location":"上海","note":"MokaHR pwc/148260，招100人","url":"https://app.mokahr.com/campus-recruitment/pwc/148260"},
                 {"title":"Cyber/审计校招岗","location":"全国","note":"pwccn.com students","url":"https://www.pwccn.com/zh/careers/students.html"}],
  "blocker_reason":""},
"ey": {
  "investigation_status":"入口已证实","china_campus_status":"中国校招在招","platform":"自建/MokaHR",
  "entry_url":"https://careers.ey.com/ey/","official_career_site":"https://careers.ey.com/ey/students/",
  "access_mode":"EY careers","pagination":"","scope":"中国内地2027；审计/税务/咨询校招","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"EY China 校招(审计/咨询)","location":"全国","note":"careers.ey.com","url":"https://careers.ey.com/ey/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"kpmg": {
  "investigation_status":"入口已证实","china_campus_status":"中国校招在招","platform":"自建/MokaHR",
  "entry_url":"https://home.kpmg/cn/zh/home/careers.html","official_career_site":"https://kpmg.wd3.myworkdayjobs.com/",
  "access_mode":"KPMG中国校招页","pagination":"","scope":"中国内地2027；审计/税务/咨询校招","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"KPMG China 校招(审计/咨询)","location":"全国","note":"home.kpmg/cn careers","url":"https://home.kpmg/cn/zh/home/careers.html"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
}
rows=[json.loads(l) for l in open(REG,encoding="utf-8")]
by={r["slug"]:r for r in rows}
for slug,upd in F.items():
    if slug not in by: print("WARN",slug); continue
    r=by[slug]
    for k in ["investigation_status","china_campus_status","platform","entry_url","official_career_site","access_mode","pagination","scope","job_count","has_queryable_jobs","sample_jobs","blocker_reason"]:
        r[k]=upd[k]
    sdir=os.path.join(BASE,"staging",slug); os.makedirs(sdir,exist_ok=True)
    json.dump({**upd,"company_slug":slug,"company_name":r["cn_name"],"country":r["country"],"captured_at":"2026-09-10"},
              open(os.path.join(sdir,"jobs.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2)
with open(REG,"w",encoding="utf-8") as f:
    for r in rows: f.write(json.dumps(r,ensure_ascii=False)+"\n")
from collections import Counter
print("updated",len(F))
print(Counter(r["investigation_status"] for r in rows))
