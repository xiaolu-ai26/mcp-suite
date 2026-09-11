#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Final 3: aldi, carrefour, disney."""
import json, os
BASE = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign"
REG = os.path.join(BASE, "foreign_companies.jsonl")
F = {
"aldi": {
  "investigation_status":"入口已证实","china_campus_status":"奥乐齐中国以门店零售为主，校招信号弱","platform":"自建",
  "entry_url":"https://www.aldi.cn/","official_career_site":"https://www.aldi.cn/ 加入我们",
  "access_mode":"奥乐齐中国官网","pagination":"","scope":"中国内地(上海)；零售/采购岗位为主","job_count":None,"has_queryable_jobs":False,
  "sample_jobs":[],"blocker_reason":"奥乐齐中国以门店零售招聘为主，本轮未发现明确校招/管培生项目入口"},
"carrefour": {
  "investigation_status":"未发现适用岗位","china_campus_status":"家乐福中国业务收缩，校招信号弱","platform":"自建",
  "entry_url":"https://www.carrefour.com.cn/","official_career_site":"https://www.carrefour.com.cn/",
  "access_mode":"家乐福中国官网","pagination":"","scope":"中国内地；零售岗位为主","job_count":0,"has_queryable_jobs":False,
  "sample_jobs":[],"blocker_reason":"家乐福中国(苏宁系)校招项目不显著，本轮未发现明确校招入口"},
"disney": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"上海迪士尼College Program在招(FY27)","platform":"自建(Taleo)",
  "entry_url":"https://chinajobs.disneycareers.cn/zh-hans",
  "official_career_site":"http://www.shdrcareers.com",
  "access_mode":"chinajobs.disneycareers.cn可web.fetch读取(已验证)","pagination":"","scope":"中国内地(上海)；运营类实习生项目(酒店/烹饪FY27)","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Shanghai Disney Resort College Program (Hotel FY27)","location":"上海","note":"酒店运营方向，2026-08-26发布","url":"https://chinajobs.disneycareers.cn/zh-hans"},
                 {"title":"Shanghai Disney Resort College Program (Culinary)","location":"上海","note":"烹饪方向，2026-07-13发布","url":"https://shdr.disneycareers.cn/"}],
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
print("total rows", len(rows))
print(Counter(r["investigation_status"] for r in rows))
print("has_queryable=True:", sum(1 for r in rows if r["has_queryable_jobs"]))
