#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch 9: Industrial/Energy/Logistics."""
import json, os
BASE = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign"
REG = os.path.join(BASE, "foreign_companies.jsonl")
F = {
"siemens": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"SGP/智先锋校招在招(148岗)","platform":"自建",
  "entry_url":"https://jobs.siemens.com.cn/siemens/position/index",
  "official_career_site":"https://www.siemens.com/zh-cn/company/campus-recruiting/",
  "access_mode":"jobs.siemens.com.cn可web.fetch读取职位列表(已验证148结果)","pagination":"页码分页",
  "scope":"中国内地2027；SGP管理培训生(硕士+)/智先锋销售培训生/校招实习","job_count":148,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"西门子中国研究院 大模型强化学习研究员","location":"上海/北京/苏州","note":"jobs.siemens.com.cn R&D","url":"https://jobs.siemens.com.cn/siemens/position/index"},
                 {"title":"西门子管理培训生项目(SGP)","location":"上海/全国","note":"硕士及以上","url":"https://www.siemens.com/zh-cn/company/campus-recruiting/"}],
  "blocker_reason":""},
"abb": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗","platform":"SuccessFactors",
  "entry_url":"https://careers.abb.com/","official_career_site":"https://abb.wd3.myworkdayjobs.com/",
  "access_mode":"ABB careers","pagination":"","scope":"中国内地(北京/上海)；校招/early talent","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"ABB China 校招","location":"北京/上海","note":"careers.abb.com","url":"https://careers.abb.com/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"honeywell": {
  "investigation_status":"入口已证实","china_campus_status":"全球Workday可查中国岗","platform":"Workday",
  "entry_url":"https://careers.honeywell.com/","official_career_site":"https://honeywell.wd3.myworkdayjobs.com/",
  "access_mode":"Workday","pagination":"","scope":"中国内地(上海/上海紫竹)；校招/early talent","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Honeywell China 校招","location":"上海","note":"careers.honeywell.com","url":"https://careers.honeywell.com/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"mmm": {
  "investigation_status":"入口已证实","china_campus_status":"全球Workday可查中国岗","platform":"Workday",
  "entry_url":"https://3m.wd1.myworkdayjobs.com/","official_career_site":"https://www.3m.com/3M/en_US/careers-us/",
  "access_mode":"Workday","pagination":"","scope":"中国内地(上海/广州)；校招/early talent","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"3M China 校招","location":"上海/广州","note":"3M Workday","url":"https://www.3m.com/3M/en_US/careers-us/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"ge": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗","platform":"Workday",
  "entry_url":"https://jobs.ge/","official_career_site":"https://ge.wd5.myworkdayjobs.com/",
  "access_mode":"GE Workday","pagination":"","scope":"中国内地(上海/北京/无锡)；校招/Leadership Program","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"GE China 校招/Leadership Program","location":"上海/北京","note":"jobs.ge","url":"https://jobs.ge/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"shell": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"毕业生英才计划2027在招","platform":"Workday",
  "entry_url":"https://shell.wd3.myworkdayjobs.com/shellcareers?q=Graduate",
  "official_career_site":"https://www.shell.com.cn/careers/students-and-graduates.html",
  "access_mode":"shell.com.cn中国站+shell Workday","pagination":"","scope":"中国内地2027；Shell Graduate Programme(毕业生英才计划)/实习","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Shell Graduate Programme 毕业生英才计划","location":"中国","note":"2026.9-2027.8毕业，本科+","url":"https://www.shell.com.cn/careers/students-and-graduates/shell-graduate-programme/"},
                 {"title":"Assessed Internship 实习","location":"中国","note":"shell.com.cn在校生与毕业生","url":"https://www.shell.com.cn/careers/students-and-graduates.html"}],
  "blocker_reason":""},
"bp": {
  "investigation_status":"入口已证实","china_campus_status":"全球毕业生项目可查中国岗","platform":"自建",
  "entry_url":"https://www.bp.com/en/global/careers.html","official_career_site":"https://www.bp.com/en/global/careers/students-and-graduates.html",
  "access_mode":"BP careers","pagination":"","scope":"中国内地(北京/上海)；Early Careers/Graduate","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"BP China Early Careers/Graduate","location":"北京/上海","note":"bp.com careers","url":"https://www.bp.com/en/global/careers.html"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"total": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗","platform":"自建",
  "entry_url":"https://jobs.totalenergies.com/","official_career_site":"https://www.totalenergies.com/en/careers",
  "access_mode":"TotalEnergies jobs","pagination":"","scope":"中国内地(上海)；校招/graduate program","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"TotalEnergies China 校招","location":"上海","note":"jobs.totalenergies.com","url":"https://jobs.totalenergies.com/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"caterpillar": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗","platform":"自建",
  "entry_url":"https://jobs.caterpillar.com/","official_career_site":"https://www.caterpillar.com/en/careers.html",
  "access_mode":"Caterpillar jobs","pagination":"","scope":"中国内地(无锡/徐州)；校招","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Caterpillar China 校招","location":"无锡/徐州","note":"jobs.caterpillar.com","url":"https://jobs.caterpillar.com/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"airliquide": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗","platform":"自建",
  "entry_url":"https://careers.airliquide.com/","official_career_site":"https://airliquide.wd3.myworkdayjobs.com/",
  "access_mode":"Air Liquide careers","pagination":"","scope":"中国内地(上海)；校招","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Air Liquide China 校招","location":"上海","note":"careers.airliquide.com","url":"https://careers.airliquide.com/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"basf": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗(上海/南京/湛江)","platform":"自建",
  "entry_url":"https://www.basf.com/cn/zh/careers.html","official_career_site":"https://basf.wd3.myworkdayjobs.com/",
  "access_mode":"巴斯夫中国招聘","pagination":"","scope":"中国内地(上海/南京/湛江)；校招/intern","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"BASF China 校招/实习","location":"上海/南京","note":"basf.com/cn careers","url":"https://www.basf.com/cn/zh/careers.html"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"dhl": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"2027管培/实习在招","platform":"自建(smartdeer)",
  "entry_url":"https://careers.dhl.com/apac/zh/working-with-dhl",
  "official_career_site":"https://dhl-campus.smartdeer.co/",
  "access_mode":"careers.dhl.com APAC + smartdeer校招站","pagination":"","scope":"中国内地2027；DHL全球货运中国管理培训生(3年)/实习","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"DHL全球货运中国 管理培训生项目","location":"上海/厦门/深圳/广州","note":"3年金牌导师，2027秋招","url":"https://careers.dhl.com/global/en/students-graduates"},
                 {"title":"DHL 单证员实习生(2027届)","location":"成都","note":"BOSS直聘在招","url":"https://dhl-campus.smartdeer.co/"}],
  "blocker_reason":""},
"fedex": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗(上海/广州)","platform":"自建",
  "entry_url":"https://careers.fedex.com/","official_career_site":"https://fedex.wd5.myworkdayjobs.com/",
  "access_mode":"FedEx careers","pagination":"","scope":"中国内地(上海/广州)；校招/实习","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"FedEx China 校招/实习","location":"上海/广州","note":"careers.fedex.com","url":"https://careers.fedex.com/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"ups": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗(上海/深圳)","platform":"自建",
  "entry_url":"https://www.ups.com/careers","official_career_site":"https://ups.wd1.myworkdayjobs.com/",
  "access_mode":"UPS careers","pagination":"","scope":"中国内地(上海/深圳)；校招/实习","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"UPS China 校招/实习","location":"上海/深圳","note":"ups.com/careers","url":"https://www.ups.com/careers"}],
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
print("未开始:", [r["slug"] for r in rows if r["investigation_status"]=="未开始"])
