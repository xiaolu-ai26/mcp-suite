#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch 7: Finance."""
import json, os
BASE = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign"
REG = os.path.join(BASE, "foreign_companies.jsonl")
F = {
"jpmorgan": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"2027中国实习/early careers在招(上海/北京)","platform":"自建",
  "entry_url":"https://www.jpmorganchase.com/careers",
  "official_career_site":"https://www.jpmorgan.com/apcareers",
  "access_mode":"全球early careers站可按China筛选","pagination":"","scope":"中国内地2027；IB/Markets/AM/Payments/CB实习(上海北京)","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Investment Banking Summer Analyst Program","location":"Shanghai","note":"JPM 2027 China Internship","url":"https://www.jpmorganchase.com/careers"},
                 {"title":"Markets Summer Analyst - Sales/Research","location":"Shanghai","note":"2027实习季","url":"https://www.jpmorganchase.com/careers"}],
  "blocker_reason":""},
"hsbc": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"2027中国管培在招(截止2026-10-31)","platform":"51job + 自建",
  "entry_url":"https://campus.51job.com/hsbc/",
  "official_career_site":"https://www.hsbc.com/careers/students-and-graduates/find-a-programme?location=mainland-china",
  "access_mode":"51job校招专题+hsbc.com项目筛选(可读取)","pagination":"","scope":"中国内地2027管培；CIB/财富/私人银行/科技Cyber","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"汇丰中国2027管理培训生(CIB/财富/科技)","location":"上海/广州/全国","note":"campus.51job.com/hsbc，截止2026-10-31","url":"https://campus.51job.com/hsbc/"},
                 {"title":"Cyber - Graduate","location":"Guangzhou","note":"hsbc.com Mainland China","url":"https://www.hsbc.com/careers/students-and-graduates"}],
  "blocker_reason":""},
"citi": {
  "investigation_status":"入口已证实","china_campus_status":"全球early careers可查中国岗(上海)","platform":"自建",
  "entry_url":"https://www.citigroup.com/global/careers","official_career_site":"https://jobs.citi.com/",
  "access_mode":"Citi jobs站","pagination":"","scope":"中国内地(上海)；early careers/analyst","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Citi China Analyst/Aspiring Leaders","location":"上海","note":"jobs.citi.com","url":"https://jobs.citi.com/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"goldmansachs": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗(北京/上海)","platform":"自建",
  "entry_url":"https://www.goldmansachs.com/careers/","official_career_site":"https://am-goldmansachs.icims.com/",
  "access_mode":"Goldman Sachs careers","pagination":"","scope":"中国内地(北京/上海)；analyst/暑期实习","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Goldman Sachs China Analyst/Summer","location":"北京/上海","note":"goldmansachs.com/careers","url":"https://www.goldmansachs.com/careers/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"morganstanley": {
  "investigation_status":"入口已证实","china_campus_status":"中国学生招聘页在招","platform":"自建",
  "entry_url":"https://www.morganstanleychina.com/people/students-and-graduates",
  "official_career_site":"https://careers.morganstanley.com.cn/",
  "access_mode":"大摩中国学生招聘页","pagination":"","scope":"中国内地(上海/北京)；校招/early talent","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Morgan Stanley China Students & Graduates","location":"上海/北京","note":"morganstanleychina.com","url":"https://www.morganstanleychina.com/people/students-and-graduates"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"ubs": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"2027中国内地校招全面启动(GTP 8/17开放)","platform":"自建",
  "entry_url":"https://jobs.ubs.com/","official_career_site":"https://www.ubs.com/global/en/careers.html",
  "access_mode":"jobs.ubs.com按China筛选","pagination":"","scope":"中国内地2027；GTP管培+暑期实习(Research/AM/GWM/GTO)","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"UBS China Graduate Programme (GTP)","location":"上海/北京","note":"2026-08-17开放，截止10月","url":"https://jobs.ubs.com/"},
                 {"title":"Summer Internship Program","location":"上海/北京/香港","note":"研究部/资管","url":"https://jobs.ubs.com/"}],
  "blocker_reason":""},
"allianz": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗(上海)","platform":"自建",
  "entry_url":"https://www.allianz.com/en/careers/","official_career_site":"https://careers.allianz.com/",
  "access_mode":"Allianz careers","pagination":"","scope":"中国内地(上海)；校招/early talent","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Allianz China 校招/early talent","location":"上海","note":"careers.allianz.com","url":"https://www.allianz.com/en/careers/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"aig": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗(上海/香港)","platform":"自建",
  "entry_url":"https://www.aig.com/careers","official_career_site":"https://www.aig.com/about-us/careers",
  "access_mode":"AIG careers","pagination":"","scope":"中国内地(上海)；校招/early talent","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"AIG China 校招","location":"上海","note":"aig.com/careers","url":"https://www.aig.com/careers"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"bnp": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗(上海)","platform":"自建",
  "entry_url":"https://careers.bnpparibas.com/","official_career_site":"https://careers.bnpparibas.com/en",
  "access_mode":"BNP Paribas careers","pagination":"","scope":"中国内地(上海)；VIE/校招","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"BNP Paribas China VIE/校招","location":"上海","note":"careers.bnpparibas.com","url":"https://careers.bnpparibas.com/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"db": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗(北京/上海)","platform":"自建",
  "entry_url":"https://www.db.com/careers","official_career_site":"https://careers.db.com/",
  "access_mode":"Deutsche Bank careers","pagination":"","scope":"中国内地(北京/上海)；校招/early talent","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Deutsche Bank China 校招","location":"北京/上海","note":"careers.db.com","url":"https://www.db.com/careers"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"sc": {
  "investigation_status":"入口已证实","china_campus_status":"全球graduate项目可查中国岗","platform":"自建",
  "entry_url":"https://www.sc.com/cn/careers/","official_career_site":"https://www.sc.com/graduates/",
  "access_mode":"Standard Chartered graduates站","pagination":"","scope":"中国内地；International Graduate Programme","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Standard Chartered International Graduate","location":"中国","note":"sc.com/graduates location=China","url":"https://www.sc.com/graduates/"}],
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
