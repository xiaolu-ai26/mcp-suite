#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, datetime
NOW = datetime.datetime.now().astimezone().isoformat()
LIST = "https://careersite.tupu360.com/pfizercampus/position/index"
DESC = """【你将收获】
1、全面了解辉瑞公司历史、文化及核心价值观，三观一致才能走得长久。
2、接受专业医学知识培训、软性技能提升课程，增强综合实力。
3、跟随专属导师学习产品知识、业务流程、合规的工作方式以及推广模式，提前锻炼职场人的专业素质。
4、收集市场信息反馈，学习学术推广活动的筹备、组织，磨练市场敏锐度、洞察力和执行能力。
5、对业务数据进行有效分析和处理，学会用可信的数据支撑工作。
6、制作业务方案，并用优秀的表达能力和清晰的思路呈现有影响力的演讲。
7、在储备期表现出色者将晋级"快速面试环节"，受到认可的储备专员将直接拿到辉瑞生物制药正式Offer。

【你需要具备】
1、2026年全日制大学毕业生；
2、专业不限，药学、临床医学、化学化工、生物及生命科学等相关专业优先；
3、爱沟通、拥有敏感的人际交往能力；
4、喜欢拼搏、热爱学习、有良好的自我驱动力；
5、心怀美好相信自己能创造未来，内心强大能坚持理想；
6、享受团队合作，善于发现伙伴闪光点；
7、熟练使用Windows办公系统：Word、Excel、Power Point。"""

def rec(idx, title, cities, pid, note):
    return {
        "id": f"pfizer-{idx:03d}",
        "recruitment_unit": "辉瑞投资有限公司",
        "contracting_entity": "辉瑞投资有限公司",
        "job_title": title,
        "job_category": "医学信息沟通储备专员",
        "cities": cities,
        "major_requirements_raw": "专业不限，药学/临床医学/化学化工/生物及生命科学相关专业优先",
        "major_tags": [],
        "education_raw": "本科及以上",
        "cohort_raw": "2026届",
        "deadline": "",
        "deadline_type": "招满即止",
        "status": "open",
        "application_url": f"https://careersite.tupu360.com/pfizercampus/position/detail/{pid}",
        "source_url": f"https://careersite.tupu360.com/pfizercampus/position/detail/{pid}",
        "published_at": "2026-09-10",
        "reviewed_at": NOW,
        "source_name": "辉瑞中国校园招聘官网",
        "evidence_path": "",
        "description_raw": DESC,
        "recruiting_unit_raw": "辉瑞",
        "hiring_department_raw": "",
        "campaign_cohort_raw": "2026届",
        "source_record_id": f"pfizer-campus-2026-{idx}",
        "job_listing_url": f"https://careersite.tupu360.com/pfizercampus/position/detail/{pid}",
        "campaign_url": LIST,
        "record_kind": "official_position_id",
        "status_note": note,
        "recruitment_type": "校招",
        "overseas_flag": False,
        "region": "mainland",
        "industry": "医药"
    }
rows = [
 rec(1,"医学信息沟通储备专员（26应届-北京）",["北京"],"68dbaa4a24357135f82fa432","辉瑞医学信息沟通储备专员项目，表现优异直通正式Offer"),
 rec(2,"医学信息沟通储备专员（26应届-广东）",["深圳","广州"],"68dbaa4924357135f82fa430","广东区域"),
 rec(3,"医学信息沟通储备专员（26应届-上海）",["上海"],"68dbaa824357135f82fa42b","上海"),
 rec(4,"医学信息沟通储备专员（26应届-江苏省）",["南京","苏州","扬州"],"68dbaa4924357135f82fa42d","江苏区域"),
]
json.dump(rows, open("/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign/mcp_round1/pfizer.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote", len(rows))
