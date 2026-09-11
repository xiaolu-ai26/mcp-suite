#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch 3: Tech."""
import json, os
BASE = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign"
REG = os.path.join(BASE, "foreign_companies.jsonl")
F = {
"microsoft": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"2027校招在招(北京/上海/苏州)","platform":"自建",
  "entry_url":"https://careers.microsoft.com/students/us/en","official_career_site":"https://careers.microsoft.com/v2/global/en/home.html",
  "access_mode":"全球学生招聘站可筛选中国","pagination":"","scope":"中国内地2027校招/SDE/PM/Technical Sales，北京上海苏州","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Software Engineer (新校招)","location":"北京/上海/苏州","note":"careers.microsoft.com students","url":"https://careers.microsoft.com/students/us/en"}],
  "blocker_reason":""},
"google": {
  "investigation_status":"入口已证实","china_campus_status":"中国站可查(北京/上海)，岗位有限","platform":"自建",
  "entry_url":"https://careers.google.cn/","official_career_site":"https://careers.google.com/students/",
  "access_mode":"careers.google.cn中文版可筛选中国","pagination":"","scope":"中国内地(北京/上海)工程与业务；校招/实习","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Google中国 工程/业务岗位","location":"北京/上海","note":"careers.google.cn官方唯一渠道","url":"https://careers.google.cn/"}],
  "blocker_reason":"谷歌在华校招岗位相对有限，本轮未逐岗枚举"},
"amazon": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"2027校招正式启动","platform":"自建(amazon.jobs)",
  "entry_url":"https://www.amazon.jobs/","official_career_site":"https://www.amazon.jobs/en/teams/china",
  "access_mode":"amazon.jobs可按China筛选","pagination":"","scope":"中国内地2027校招；SDE/应用科学家/解决方案架构师/TPM/Sales Ops Analyst","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"软件开发工程师 (SDE)","location":"中国","note":"2027亚马逊校招2026-09-02交大就业","url":"https://www.amazon.jobs/"},
                 {"title":"应用科学家 / 解决方案架构师","location":"中国","note":"2027校招岗位列表","url":"https://www.amazon.jobs/"}],
  "blocker_reason":""},
"apple": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"2027校招在招(上海/北京/深圳/苏州)","platform":"自建",
  "entry_url":"https://jobs.apple.com/zh-cn/search?location=china-CHNC","official_career_site":"https://jobs.apple.com/zh-cn/",
  "access_mode":"jobs.apple.com可按location=china-CHNC筛选(已验证600+结果/18实习)","pagination":"页码分页","scope":"中国内地2027校招/实习，corporate+retail","job_count":600,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Noise & Vibration Internship (Oct2026-Sep2027)","location":"Shanghai","note":"jobs.apple.com China students intern","url":"https://jobs.apple.com/en-us/search?location=china-CHNC&team=internships-STDNT-INTRN"},
                 {"title":"Mac Product ... Intern","location":"Shanghai","note":"China intern","url":"https://jobs.apple.com/en-us/search?location=china-CHNC"}],
  "blocker_reason":""},
"meta": {
  "investigation_status":"未发现适用岗位","china_campus_status":"中国大陆无显著校招(以美/亚太为主)","platform":"自建(Greenhouse)",
  "entry_url":"https://www.metacareers.com/","official_career_site":"https://www.metacareers.com/",
  "access_mode":"全球站","pagination":"","scope":"全球；中国大陆校招岗位极少/无","job_count":0,"has_queryable_jobs":False,
  "sample_jobs":[],"blocker_reason":"Meta在中国大陆无显著校园招聘业务，岗位以美国/新加坡/亚太为主；本轮未发现内地可投校招岗"},
"nvidia": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"2027校招正式启动(北京/上海/深圳)","platform":"MokaHR",
  "entry_url":"https://app.mokahr.com/campus-recruitment/nvidia/47111","official_career_site":"https://jobs.nvidia.com/careers",
  "access_mode":"MokaHR校招项目47111 + jobs.nvidia.com China筛选可读取","pagination":"","scope":"中国内地2027校招；AI/HPC/芯片设计/软件/机器人","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Physical Design Intern, VLSI - 2027","location":"Beijing, China","note":"jobs.nvidia.com China","url":"https://jobs.nvidia.com/careers"},
                 {"title":"Circuit Validation Engineer Intern - 2027","location":"Shanghai, China","note":"2027校招","url":"https://app.mokahr.com/campus-recruitment/nvidia/47111"}],
  "blocker_reason":""},
"intel": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"2027中国校招正式启动(上海/北京/深圳)","platform":"自建",
  "entry_url":"https://chinacampus.jobs.intel.cn/","official_career_site":"https://jobs.intel.com/",
  "access_mode":"chinacampus.jobs.intel.cn应届生通道","pagination":"","scope":"中国内地2026/2027届；AI编译器/AI框架/数据中心软件","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"AI编译器/AI框架 校招岗","location":"上海/北京/深圳","note":"英特尔2027中国校招2026-08启动","url":"https://chinacampus.jobs.intel.cn/"}],
  "blocker_reason":""},
"amd": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗(上海/北京设计中心)","platform":"Greenhouse",
  "entry_url":"https://www.amd.com/en/careers","official_career_site":"https://careers-amd.icims.com/ (Greenhouse系)",
  "access_mode":"全球站可按China筛选","pagination":"","scope":"中国内地(上海/北京)设计/软件岗；校招随全球","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"AMD China 设计/软件岗","location":"上海/北京","note":"amd.com careers","url":"https://www.amd.com/en/careers"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"cisco": {
  "investigation_status":"入口已证实","china_campus_status":"全球站Workday可查中国岗","platform":"Workday",
  "entry_url":"https://jobs.cisco.com/","official_career_site":"https://jobs.cisco.com/jobs",
  "access_mode":"Workday可按China筛选","pagination":"","scope":"中国内地(上海/北京/苏州)；校招/early talent","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Cisco China Early Talent","location":"上海/北京","note":"jobs.cisco.com","url":"https://jobs.cisco.com/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"ibm": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗","platform":"Workday",
  "entry_url":"https://www.ibm.com/cn-zh/employment","official_career_site":"https://www.ibm.com/cn-zh/employment",
  "access_mode":"IBM中国招聘页","pagination":"","scope":"中国内地(上海/北京/广州)；校招/early professionals","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"IBM China Early Professional","location":"上海/北京","note":"ibm.com/cn-zh/employment","url":"https://www.ibm.com/cn-zh/employment"}],
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
