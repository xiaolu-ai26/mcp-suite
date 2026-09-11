#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch 4: remaining tech + auto."""
import json, os
BASE = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign"
REG = os.path.join(BASE, "foreign_companies.jsonl")
F = {
"oracle": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗(上海)","platform":"Taleo",
  "entry_url":"https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/","official_career_site":"https://www.oracle.com/corporate/careers/",
  "access_mode":"Oracle Taleo云招聘","pagination":"","scope":"中国内地(上海)；校招/early talent","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Oracle China 校园/early talent","location":"上海","note":"oracle Taleo","url":"https://www.oracle.com/corporate/careers/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"sap": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗","platform":"SuccessFactors",
  "entry_url":"https://jobs.sap.com/","official_career_site":"https://jobs.sap.com/search/",
  "access_mode":"SuccessFactors可按China筛选","pagination":"","scope":"中国内地(上海/北京/大连)；校招/early talent","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"SAP China Early Talent","location":"上海/北京","note":"jobs.sap.com","url":"https://jobs.sap.com/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"salesforce": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗(香港/上海)","platform":"Workday",
  "entry_url":"https://careers.salesforce.com/","official_career_site":"https://careers.salesforce.com/en/jobs/",
  "access_mode":"Workday","pagination":"","scope":"中国内地岗位较少(香港为主)；校招随全球","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Salesforce China/HK Early Talent","location":"香港/上海","note":"careers.salesforce.com","url":"https://careers.salesforce.com/"}],
  "blocker_reason":"中国大陆校招岗位有限"},
"adobe": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗","platform":"Workday",
  "entry_url":"https://www.adobe.com/careers.html","official_career_site":"https://careers.adobe.com/",
  "access_mode":"Workday","pagination":"","scope":"中国内地(上海/北京)；校招/实习","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Adobe China 校招/实习","location":"上海/北京","note":"careers.adobe.com","url":"https://www.adobe.com/careers.html"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"qualcomm": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"中国研发中心校招在招(上海/北京)","platform":"自建",
  "entry_url":"https://qualcomm.wd5.myworkdayjobs.com/","official_career_site":"https://www.qualcomm.com/company/careers",
  "access_mode":"Workday可按China筛选","pagination":"","scope":"中国内地(上海/北京/深圳)；研发/软件/芯片校招","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Qualcomm China 研发校招岗","location":"上海/北京","note":"qualcomm careers","url":"https://www.qualcomm.com/company/careers"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"ti": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗(上海/无锡/北京)","platform":"自建",
  "entry_url":"https://careers.ti.com/","official_career_site":"https://careers.ti.com/search-jobs",
  "access_mode":"自建招聘站","pagination":"","scope":"中国内地(上海/无锡/北京/深圳)；校招/实习","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"TI China 校招/实习","location":"上海/无锡","note":"careers.ti.com","url":"https://careers.ti.com/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"toyota": {
  "investigation_status":"入口已证实","china_campus_status":"中国区校招经一汽丰田/广汽丰田等","platform":"自建",
  "entry_url":"https://www.toyota.com.cn/","official_career_site":"https://www.toyota.com.cn/ recruitment",
  "access_mode":"中国官网","pagination":"","scope":"中国内地；校招经合资(一汽丰田/广汽丰田)及丰田中国","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"丰田中国/合资 校招岗","location":"天津/广州/北京","note":"toyota.com.cn招聘","url":"https://www.toyota.com.cn/"}],
  "blocker_reason":"本轮未逐岗枚举具体校招JD列表"},
"bmw": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"AcceleratiON管培在招(北京/上海)","platform":"自建",
  "entry_url":"https://www.bmwgroup.jobs/cn/en/opportunities/graduate.html",
  "official_career_site":"http://www.bmw-brilliance.cn/cn/zh/career/future-talent-program/index.html",
  "access_mode":"宝马集团jobs站+华晨宝马英才计划","pagination":"","scope":"中国内地2027 AcceleratiON管培(18个月4轮岗)；北京上海","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"BMW AcceleratiON Trainee Programme","location":"北京/上海","note":"含慕尼黑/海外轮岗","url":"https://www.bmwgroup.jobs/cn/en/opportunities/graduate.html"},
                 {"title":"华晨宝马英才发展计划","location":"沈阳/北京","note":"18个月4次轮岗","url":"http://www.bmw-brilliance.cn/cn/zh/career/future-talent-program/index.html"}],
  "blocker_reason":""},
"mercedes": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"中国ATS直出岗位(北京/上海)","platform":"自建(tupu360)",
  "entry_url":"https://career.mercedes-benz.com.cn/recruiting/company/13746/job-list",
  "official_career_site":"https://jobs.mercedes-benz.com/en",
  "access_mode":"中国career站可web.fetch读取职位列表(已验证)","pagination":"","scope":"中国内地(北京/上海/大兴/亦庄)；实习+校招","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Intern_AI App Product Owner/AI应用产品经理","location":"北京","note":"career.mercedes-benz.com.cn职位列表","url":"https://career.mercedes-benz.com.cn/recruiting/company/13746/job-list"},
                 {"title":"Display and System Engineer_座舱屏幕研发工程师","location":"Beijing","note":"Mercedes-Benz Group China Ltd.","url":"https://jobs.mercedes-benz.com/"}],
  "blocker_reason":""},
"tesla": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"2027秋招在招(T-STAR实习+校招)","platform":"MokaHR",
  "entry_url":"https://app.mokahr.com/campus-recruitment/tesla/41460",
  "official_career_site":"https://intr.tesla.cn/SDCampus/home ; https://careers.tesla.cn/",
  "access_mode":"MokaHR校招项目41460 + intr.tesla.cn","pagination":"","scope":"中国内地2027校招/实习；技术职能上海北京，销售全国","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"特斯拉2027届秋季校园招聘","location":"上海/北京/全国","note":"杭电/哈工大威海2026-09发布","url":"https://app.mokahr.com/campus-recruitment/tesla/41460"},
                 {"title":"特斯拉顾问实习生-上海","location":"上海","note":"intr.tesla.cn销售交付","url":"https://intr.tesla.cn/SDCampus/home"}],
  "blocker_reason":""},
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
