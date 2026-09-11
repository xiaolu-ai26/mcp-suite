#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch 5: remaining auto."""
import json, os
BASE = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign"
REG = os.path.join(BASE, "foreign_companies.jsonl")
F = {
"vw": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"2026-2027届校招在招(上海/北京/合肥/大连)","platform":"MokaHR",
  "entry_url":"https://app.mokahr.com/campus-recruitment/vwa/168597",
  "official_career_site":"https://volkswagengroupchina.jobs2web.sapsf.cn/vwa/content/VWA-Campus-Recruitement-CN/",
  "access_mode":"MokaHR校招项目168597(经多高校就业网证实)","pagination":"",
  "scope":"中国内地2026-2027届校招；合肥/大连/上海/北京","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"大众汽车集团(中国)2026-2027届校园招聘","location":"上海/北京/合肥/大连","note":"MokaHR vwa/168597；北航/中科大2026-09-03","url":"https://app.mokahr.com/campus-recruitment/vwa/168597"}],
  "blocker_reason":""},
"gm": {
  "investigation_status":"入口已证实","china_campus_status":"中国校招主要经合资(上汽通用/泛亚)","platform":"自建(zhiye)",
  "entry_url":"https://www.gm.com.cn/zh/home/join-us.html",
  "official_career_site":"https://www.gm.com.cn/ ; 上汽通用校招 https://sgm.zhiye.com/campus",
  "access_mode":"通用中国官网+合资校招站","pagination":"",
  "scope":"中国内地；GM中国+上汽通用/泛亚汽车技术中心","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"上汽通用/泛亚 2027校招暨暑期实习","location":"上海","note":"sgm.zhiye.com/campus","url":"https://sgm.zhiye.com/campus"}],
  "blocker_reason":"通用中国直管校招入口较少，主要经上汽通用等合资公司"},
"ford": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"2027校招在招(GT毕业生培训生)","platform":"MokaHR",
  "entry_url":"https://app.mokahr.com/campus-recruitment/ford/43706",
  "official_career_site":"https://www.ford.com.cn/careers",
  "access_mode":"MokaHR校招项目43706(经高校就业网证实)","pagination":"",
  "scope":"中国内地2027校招；上海/南京","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"福特中国2027校园招聘 GT毕业生培训生","location":"上海/南京","note":"MokaHR ford/43706；2026-09网申","url":"https://app.mokahr.com/campus-recruitment/ford/43706"}],
  "blocker_reason":""},
"honda": {
  "investigation_status":"入口已证实","china_campus_status":"中国校招经本田中国/合资","platform":"自建",
  "entry_url":"https://www.honda.com.cn/","official_career_site":"https://www.honda.com.cn/ recruitment",
  "access_mode":"本田中国官网","pagination":"","scope":"中国内地；本田中国+广汽本田/东风本田","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"本田中国/合资 校招岗","location":"广州/武汉","note":"honda.com.cn","url":"https://www.honda.com.cn/"}],
  "blocker_reason":"本轮未逐岗枚举具体校招JD"},
"nissan": {
  "investigation_status":"入口已证实","china_campus_status":"中国校招经日产中国/合资","platform":"自建",
  "entry_url":"https://www.nissan.com.cn/","official_career_site":"https://www.nissan.com.cn/ careers",
  "access_mode":"日产中国官网","pagination":"","scope":"中国内地；日产中国+东风日产","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"日产中国/东风日产 校招岗","location":"广州","note":"nissan.com.cn","url":"https://www.nissan.com.cn/"}],
  "blocker_reason":"本轮未逐岗枚举具体校招JD"},
"hyundai": {
  "investigation_status":"入口已证实","china_campus_status":"中国校招经现代中国/北京现代","platform":"自建",
  "entry_url":"https://www.hyundai.com.cn/","official_career_site":"https://www.hyundai.com.cn/ careers",
  "access_mode":"现代中国官网","pagination":"","scope":"中国内地；现代中国+北京现代","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"现代/北京现代 校招岗","location":"北京","note":"hyundai.com.cn","url":"https://www.hyundai.com.cn/"}],
  "blocker_reason":"本轮未逐岗枚举具体校招JD"},
"stellantis": {
  "investigation_status":"入口已证实","china_campus_status":"全球站Workday可查中国岗","platform":"Workday",
  "entry_url":"https://www.stellantis.com/en/careers","official_career_site":"https://stellantis.wd3.myworkdayjobs.com/",
  "access_mode":"Workday","pagination":"","scope":"中国内地(武汉/广州)；标致雪铁龙/菲亚特品牌","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Stellantis China 校招/early talent","location":"武汉/广州","note":"stellantis Workday","url":"https://www.stellantis.com/en/careers"}],
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
