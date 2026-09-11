#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch 2 findings recorder."""
import json, os
BASE = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign"
REG = os.path.join(BASE, "foreign_companies.jsonl")

F = {
"kraftheinz": {
  "investigation_status":"入口已证实","china_campus_status":"校招在招(hotjob)","platform":"hotjob(前程无忧) + Workday",
  "entry_url":"https://kraftheinz.hotjob.cn","official_career_site":"https://careers.kraftheinzcompany.com/",
  "access_mode":"hotjob中国校招站；全球Workday","pagination":"",
  "scope":"中国内地校招，销售培训生(广州)等；上海R&D","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"销售培训生(Sales Trainee)","location":"广州越秀区","note":"kraftheinz.hotjob.cn；东莞理工宣讲会","url":"https://kraftheinz.hotjob.cn"}],
  "blocker_reason":""},
"abinbev": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"GMT/商务管培2027在招","platform":"MokaHR",
  "entry_url":"https://app.mokahr.com/campus-recruitment/budweiser/148097",
  "official_career_site":"https://www.budweiserapac.com/careers/","access_mode":"MokaHR校招项目(列表经高校就业网证实)",
  "pagination":"","scope":"中国内地2027 GMT(毕业2026.8-2027.7)；商务管理培训生东南事业部等","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Global Management Trainee (GMT)","location":"中国(区域内调动)","note":"百威中国MokaHR校招项目148097","url":"https://app.mokahr.com/campus-recruitment/budweiser/148097"},
                 {"title":"百威中国东南事业部 商务管理培训生","location":"福建/江西/湖南","note":"2026-09-03发布","url":"https://app.mokahr.com/campus-recruitment/budweiser/148097"}],
  "blocker_reason":""},
"diageo": {
  "investigation_status":"入口已证实","china_campus_status":"全球站China筛选可用；early careers","platform":"自建(类Workday)",
  "entry_url":"https://www.diageo.com/en/careers/search-and-apply?country=China",
  "official_career_site":"https://www.diageo.com/en/careers/search-and-apply","access_mode":"全球站country=China筛选可访问",
  "pagination":"","scope":"中国内地岗位(全球站China筛选)；early careers项目","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Diageo China Open Roles (early careers)","location":"China","note":"diageo.com careers country=China","url":"https://www.diageo.com/en/careers/search-and-apply?country=China"}],
  "blocker_reason":""},
"pernod": {
  "investigation_status":"入口已证实","china_campus_status":"Asia Regional MT项目(中国区入口经51job)","platform":"自建 + 51job",
  "entry_url":"https://www.pernod-ricard-china.com/joblist.html",
  "official_career_site":"https://www.pernod-ricard-china.com/ ; 亚洲MT pernodricard-asiantalent.com",
  "access_mode":"中国官网社招页；校招经51job/亚洲talent站","pagination":"",
  "scope":"中国内地；亚洲Regional Management Trainee(18个月)","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Pernod Ricard Asia Regional Management Trainee Programme","location":"中国/亚太","note":"18个月区域管培","url":"https://www.pernod-ricard-china.com/joblist.html"}],
  "blocker_reason":"中国官网joblist为社招；校招MT走51job/亚洲talent站，本轮未直接抓到2027在招JD列表"},
"lvmh": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"中国零售管培+Beauty MT在招","platform":"自建 + 51job",
  "entry_url":"https://www.lvmh.cn/cn/work-at-lvmh",
  "official_career_site":"https://www.lvmh.com/en/join-us/lvmh-graduate-programs/lvmh-china-retail-management-trainee-program",
  "access_mode":"lvmh.cn中国站+全球graduate program页","pagination":"",
  "scope":"中国内地2027；LVMH China Retail MT(2022启动)+LVMH Beauty香水化妆品MT","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"LVMH China Retail Management Trainee Program","location":"中国","note":"2022启动，75+ Maisons零售领导力","url":"https://www.lvmh.com/en/join-us/lvmh-graduate-programs/lvmh-china-retail-management-trainee-program"},
                 {"title":"LVMH Beauty 管理培训生","location":"上海","note":"路威酩轩香水化妆品MT","url":"https://www.lvmh.cn/cn/work-at-lvmh"}],
  "blocker_reason":""},
"nike": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"中国区在招(社招为主)+实习","platform":"Workday",
  "entry_url":"https://careers.nike.com/zh-cn/jobs",
  "official_career_site":"https://careers.nike.com/zh-cn/","access_mode":"Workday全球站可web.fetch读取中国岗位",
  "pagination":"","scope":"中国内地(上海/北京/广州)Marketing/零售/供应链；校招经nike.51job.com","job_count":1094,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Manager, City Marketing, Sportswear, Shanghai","location":"Shanghai, China","note":"careers.nike.com中国岗位R-90349","url":"https://careers.nike.com/zh-cn/jobs"},
                 {"title":"Senior Supervisor, Retail Marketing, EKIN, East GC","location":"Beijing, China","note":"中国区Marketing","url":"https://careers.nike.com/zh-cn/jobs"}],
  "blocker_reason":""},
"adidas": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"Greater China Trainee在招(Brands Trainee/APAC)","platform":"Workday",
  "entry_url":"https://careers.adidas-group.com/jobs?location=%5B%7B%22country%22%3A%22Greater+China%22%7D%5D&brand=adidas",
  "official_career_site":"https://careers.adidas-group.com/teams/students/apac-trainee-program","access_mode":"Workday Greater China筛选可读取",
  "pagination":"","scope":"大中华区(上海为主)；APAC Trainee/Brands Trainee/Sourcing 24-month Trainee","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"Sourcing Associate (24-month Trainee Program)","location":"Shanghai, Greater China","note":"careers.adidas-group.com","url":"https://careers.adidas-group.com/jobs"},
                 {"title":"品牌管培生 Brands Trainee","location":"上海","note":"2026-08-31发布，Product/Marketing/Creation","url":"https://careers.adidas-group.com/teams/students/apac-trainee-program"}],
  "blocker_reason":""},
"ikea": {
  "investigation_status":"入口已证实","china_campus_status":"未来领袖/校招项目在招(51job)","platform":"自建 + 51job",
  "entry_url":"https://www.ikea.cn/cn/zh/this-is-ikea/work-with-us/",
  "official_career_site":"https://jobs.ikea.com/ ; 校招 https://campus.51job.com/m/IKEA2024/","access_mode":"ikea.cn招聘流程页；校招走51job",
  "pagination":"","scope":"中国内地2027(毕业30个月内)；未来领袖项目(餐饮/顾客关系/销售部)","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"宜家零售校招未来领袖项目","location":"全国门店(上海/北京/广州/深圳等)","note":"51job IKEA校招专题","url":"https://campus.51job.com/m/IKEA2024/index.html"}],
  "blocker_reason":"当前51job专题页仍为IKEA2024，2027最新校招批次入口待更新确认"},
"walmart": {
  "investigation_status":"有可用岗位部分覆盖","china_campus_status":"2027人才菁英管培在招","platform":"智联",
  "entry_url":"https://walmart.zhaopin.com/",
  "official_career_site":"https://www.walmart.cn/joinus/","access_mode":"智联校招站walmart.zhaopin.com",
  "pagination":"","scope":"中国内地2027(毕业2026.1-2027.6)；总部管培(深圳)/门店管培(沃尔玛/山姆)/供应链管培","job_count":None,"has_queryable_jobs":True,
  "sample_jobs":[{"title":"沃尔玛营运管培生-供应链区域配送中心","location":"深圳/全国","note":"2027届人才菁英计划","url":"https://walmart.zhaopin.com/"},
                 {"title":"沃尔玛门店管培生","location":"全国门店/山姆","note":"27-30个月成门店副总经理","url":"https://walmart.zhaopin.com/"}],
  "blocker_reason":""},
"costco": {
  "investigation_status":"入口已证实","china_campus_status":"中国区以零售社招为主，校招信号弱","platform":"自建",
  "entry_url":"https://www.costco.com.cn/",
  "official_career_site":"https://www.costco.com.cn/ 加入我们","access_mode":"中国官网",
  "pagination":"","scope":"中国内地；开市客零售岗位为主","job_count":None,"has_queryable_jobs":False,
  "sample_jobs":[],"blocker_reason":"开市客中国以门店零售招聘为主，本轮未发现明确中国校招/管培生项目入口"},
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
