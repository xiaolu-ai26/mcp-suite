#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch 6: Pharma."""
import json, os
BASE = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign"
REG = os.path.join(BASE, "foreign_companies.jsonl")
F = {
"pfizer": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"管培生计划/储备计划在招","platform":"自建(avature/tupu360)",
  "entry_url":"https://careersite.tupu360.com/pfizercampus/position/index",
  "official_career_site":"https://www.pfizer.com.cn/en/about-en/careers-en/careers-campus-en ; https://pfizer.avature.cn/zh_CN/campus",
  "access_mode":"tupu360校招站+avature中国站","pagination":"","scope":"中国内地；管培生(36个月轮岗)/储备计划/研发生产商贸","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"辉瑞管培生计划(36个月轮岗)","location":"上海/全国","note":"pfizer.com.cn校招项目","url":"https://www.pfizer.com.cn/en/about-en/careers-en/careers-campus-en"},
                 {"title":"医学信息沟通储备专员","location":"全国","note":"tupu360 pfizercampus","url":"https://careersite.tupu360.com/pfizercampus/position/index"}],
  "blocker_reason":""},
"roche": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"StartUp罗氏中国管培(2027将于9月启动)","platform":"自建",
  "entry_url":"https://careers.roche.com/cn/zh/startup-china-pharma",
  "official_career_site":"https://careers.roche.com/cn/zh/home",
  "access_mode":"careers.roche.com/cn/zh可web.fetch读取(已验证)","pagination":"","scope":"中国内地；StartUp制药中国管培(36个月4轮岗)，24-27届可投","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"StartUp 罗氏制药中国人才发展项目","location":"上海","note":"36个月轮岗(市场/准入/医学)","url":"https://careers.roche.com/cn/zh/startup-china-pharma"},
                 {"title":"罗氏中国创新中心实习生","location":"上海","note":"careers.roche.com students","url":"https://careers.roche.com/cn/zh/students-programmes"}],
  "blocker_reason":""},
"novartis": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"扬帆MR实习/研发培训生在招(2027届)","platform":"自建",
  "entry_url":"https://www.novartis.com.cn/careers/career-search",
  "official_career_site":"https://www.novartis.com.cn/careers",
  "access_mode":"novartis.com.cn职位搜索可web.fetch读取(1121结果,含China)","pagination":"页码分页","scope":"中国内地；扬帆医药代表MR Intern/研发培训生","job_count":1121,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"扬帆医药代表(MR Intern)","location":"北京/全国","note":"2027届本科+医学药学，转正一线推广","url":"https://www.novartis.com/careers/career-search/job/details/req-10077431"},
                 {"title":"(高级)地区经理 正式","location":"Hangzhou","note":"novartis.com.cn China岗位","url":"https://www.novartis.com.cn/careers/career-search"}],
  "blocker_reason":""},
"merck": {
  "investigation_status":"入口已证实","china_campus_status":"中国校招在招(MSD)","platform":"自建",
  "entry_url":"https://www.merck.com.cn/","official_career_site":"https://www.msdchina.com.cn/ careers",
  "access_mode":"默沙东中国官网","pagination":"","scope":"中国内地；校招/医学信息","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"默沙东中国校招岗","location":"上海/全国","note":"msdchina.com.cn","url":"https://www.msdchina.com.cn/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"gsk": {
  "investigation_status":"入口已证实","china_campus_status":"全球Workday可查中国岗","platform":"Workday",
  "entry_url":"https://www.gsk.com/en-gb/careers/","official_career_site":"https://gsk.wd3.myworkdayjobs.com/",
  "access_mode":"Workday","pagination":"","scope":"中国内地(上海/苏州)；校招/early talent","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"GSK China 校招/early talent","location":"上海","note":"GSK Workday","url":"https://www.gsk.com/en-gb/careers/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"sanofi": {
  "investigation_status":"入口已证实","china_campus_status":"全球Workday可查中国岗","platform":"Workday",
  "entry_url":"https://www.sanofi.com/en/careers","official_career_site":"https://sanofi.wd3.myworkdayjobs.com/",
  "access_mode":"Workday","pagination":"","scope":"中国内地(上海/北京)；校招/early talent","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Sanofi China 校招/early talent","location":"上海","note":"Sanofi Workday","url":"https://www.sanofi.com/en/careers"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"bayer": {
  "investigation_status":"入口已证实","china_campus_status":"全球Workday可查中国岗","platform":"Workday",
  "entry_url":"https://www.bayer.com.cn/","official_career_site":"https://career.bayer.com.cn/ (中国站)",
  "access_mode":"拜耳中国招聘站","pagination":"","scope":"中国内地(上海/北京/广州)；医药/作物科学/消费者健康校招","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"拜耳中国校招岗","location":"上海/北京","note":"bayer中国招聘","url":"https://www.bayer.com.cn/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"takeda": {
  "investigation_status":"入口已证实","china_campus_status":"全球Workday可查中国岗","platform":"Workday",
  "entry_url":"https://www.takeda.com/careers/","official_career_site":"https://takeda.wd3.myworkdayjobs.com/",
  "access_mode":"Workday","pagination":"","scope":"中国内地(上海/北京)；校招","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Takeda China 校招","location":"上海","note":"Takeda Workday","url":"https://www.takeda.com/careers/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"boehringer": {
  "investigation_status":"入口已证实","china_campus_status":"中国校招在招(BI)","platform":"自建",
  "entry_url":"https://www.boehringer-ingelheim.cn/","official_career_site":"https://www.boehringer-ingelheim.com/careers",
  "access_mode":"勃林格中国官网","pagination":"","scope":"中国内地(上海)；校招/兽医药/人用药","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"勃林格殷格翰中国校招","location":"上海","note":"boehringer-ingelheim.cn","url":"https://www.boehringer-ingelheim.cn/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"lilly": {
  "investigation_status":"入口已证实","china_campus_status":"全球站可查中国岗(上海)","platform":"自建",
  "entry_url":"https://careers.lilly.com/","official_career_site":"https://www.lilly.com/careers",
  "access_mode":"Lilly careers","pagination":"","scope":"中国内地(上海)；校招/early talent","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Eli Lilly China 校招","location":"上海","note":"careers.lilly.com","url":"https://careers.lilly.com/"}],
  "blocker_reason":"本轮未逐岗枚举中国校招JD"},
"abbvie": {
  "investigation_status":"入口已证实","china_campus_status":"全球Workday可查中国岗","platform":"Workday",
  "entry_url":"https://www.abbvie.com/careers.html","official_career_site":"https://abbvie.wd3.myworkdayjobs.com/",
  "access_mode":"Workday","pagination":"","scope":"中国内地(上海)；校招","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"AbbVie China 校招","location":"上海","note":"AbbVie Workday","url":"https://www.abbvie.com/careers.html"}],
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
