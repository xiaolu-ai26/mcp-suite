#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, datetime
NOW = datetime.datetime.now().astimezone().isoformat()
d = json.load(open("/tmp/sie_desc.json"))
sgp = d["sgp"]; xf = d["xf"]
# trim trailing boilerplate
for marker in ["Siemens AG, 1996"]:
    sgp = sgp.split(marker)[0].strip()
    xf = xf.split(marker)[0].strip()
LIST = "https://jobs.siemens.com.cn/siemens/position/index?recruitmentType=CAMPUSRECRUITMENT"
def rec(idx, title, city, desc, pid, note):
    return {
        "id": f"siemens-{idx:03d}",
        "recruitment_unit": "西门子（中国）",
        "contracting_entity": "西门子（中国）有限公司",
        "job_title": title,
        "job_category": "管理培训生",
        "cities": [city] if city else [],
        "major_requirements_raw": "",
        "major_tags": [],
        "education_raw": "硕士及以上" if "SGP" in title else "本科及以上",
        "cohort_raw": "2027届",
        "deadline": "",
        "deadline_type": "招满即止",
        "status": "open",
        "application_url": f"https://jobs.siemens.com.cn/siemens/position/detail/{pid}",
        "source_url": f"https://jobs.siemens.com.cn/siemens/position/detail/{pid}",
        "published_at": "2026-09-10",
        "reviewed_at": NOW,
        "source_name": "西门子中国招聘官网",
        "evidence_path": "",
        "description_raw": desc,
        "recruiting_unit_raw": "西门子（中国）",
        "hiring_department_raw": "",
        "campaign_cohort_raw": "2027届",
        "source_record_id": f"siemens-campus-2027-{idx}",
        "job_listing_url": f"https://jobs.siemens.com.cn/siemens/position/detail/{pid}",
        "campaign_url": LIST,
        "record_kind": "official_position_id",
        "status_note": note,
        "recruitment_type": "校招",
        "overseas_flag": False,
        "region": "mainland",
        "industry": "工业"
    }
rows = [
 rec(1,"Siemens Graduate Program 西门子管理培训生-产品专家方向","北京",sgp,"6aa0db127280da28da079799","SGP两年国际管培，3-4个assignment含至少1个海外，面向硕士"),
 rec(2,"“智·先锋”销售培训生（Smart Pioneer）","广州",xf,"6aa281357280da28da079917","智能基础设施集团SI销售培训生，轮岗+系统培训"),
 rec(3,"“智·先锋”销售培训生（Smart Pioneer）","深圳",xf,"6aa281347280da28da079915","智能基础设施集团SI销售培训生"),
 rec(4,"“智·先锋”销售培训生（Smart Pioneer）","济南",xf,"6aa265147280da28da0798eb","智能基础设施集团SI销售培训生（工作地天津/济南）"),
]
json.dump(rows, open("/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign/mcp_round1/siemens.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote", len(rows))
