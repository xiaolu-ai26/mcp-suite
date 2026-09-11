"""Build Midea (10 verified page-1 records) and Mindray (20 verified R&D records)
staging files from browser-rendered DOM text captured 2026-09-10.
Coverage is honest partial: Midea 146 total (10/page, interactive pagination);
Mindray 58 total (first-screen R&D family 20).
"""
import json
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TZ).isoformat(timespec='seconds')
OUT = '/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/job_mvp'

# ---- Midea: 10 records from rendered page 1 (careers.midea.com/schoolOut/post) ----
midea_jobs = [
    {"title": "电机控制软件工程师", "cat": "研发技术类", "loc": ["佛山市"],
     "desc": "1、永磁同步电机PMSM、感应电机IM的控制算法研究及产品化应用；2、全新电机的控制参数设计及量变化推进落地；3、以产品实际需求为目标，结合AI及仿真系统，维护及升级电机控制代码。"},
    {"title": "解决方案工程师-海外", "cat": "海外营销类", "loc": ["深圳市"],
     "desc": "负责储能、智能电网、光储充一体化项目的标书解读与客户需求澄清，开展现场调研与资源核查，结合电网接入、储能调峰等应用场景，联合各专业技术团队完成整体解决方案设计及方案书编制；项目推进与商务支撑。"},
    {"title": "算法工程师-运筹优化", "cat": "信息技术类", "loc": ["上海市", "佛山市", "无锡市"],
     "desc": "结合业务场景，完成相关算法项目的问题抽象、研究和开发，包括路径规划、仓网规划、选址、配送网络规划、库存优化、送装任务分配等。"},
    {"title": "研究员-阀体结构", "cat": "研发技术类", "loc": ["上海市", "佛山市"],
     "desc": "负责阀组系统集成设计相关技术研究；负责阀组相关问题分析及优化方案设计；跟踪阀等技术需求、趋势和行业动态。"},
    {"title": "研究员-系统PHM算法", "cat": "研发技术类", "loc": ["上海市", "佛山市"],
     "desc": "跟踪家用空调系统全生命周期健康管理技术动态，开展售前售中售后核心技术算法、工具、流程的开发、调试、参数优化及问题排查，如故障诊断算法等。"},
    {"title": "智能开发工程师-传感器", "cat": "研发技术类", "loc": ["佛山市"],
     "desc": "设计、开发和实现融合感知算法，包括雷达、视觉、红外等；辅助进行3D视觉重建；参与红外视觉热舒适项目；跟踪多模态融合感知算法和技术。"},
    {"title": "人力资源管理-SSC", "cat": "管理类", "loc": ["上海市", "佛山市"],
     "desc": "员工关系：负责员工入转调离、劳动合同、人事档案等；薪酬福利：负责薪酬核算、社保公积金、个税申报、福利落实等。"},
    {"title": "质量技术研究工程师", "cat": "制造技术类", "loc": ["佛山市", "合肥市"],
     "desc": "品质价值流开展，推进制造六大链路品质改进；负责制程检验设计和逆向改进；结合业务痛点开展质量技术研究，提升检出。"},
    {"title": "研究员-系统智能控制算法", "cat": "研发技术类", "loc": ["上海市", "合肥市"],
     "desc": "根据空调器特性及使用环境，开发和设计高效、智能的空调控制系统；优化空调控制算法；研究并引入智能化算法技术。"},
    {"title": "产品培训运营", "cat": "国内营销类", "loc": ["合肥市"],
     "desc": "负责产品培训，包括产品卖点、卖点话术及产品应用场景等内容提炼与萃取；独立制定培训计划，组织开展线下、线上培训；探索AI在培训中的应用。"},
]

midea_records = []
for i, j in enumerate(midea_jobs, 1):
    midea_records.append({
        "id": f"midea-{i:03d}",
        "recruitment_unit": "美的集团股份有限公司",
        "contracting_entity": "",
        "job_title": j["title"],
        "job_category": j["cat"],
        "cities": j["loc"],
        "major_requirements_raw": "",
        "major_tags": [],
        "education_raw": "",
        "cohort_raw": "2027届全球校园招聘（2026年1月1日-2027年12月31日毕业）",
        "deadline": None,
        "deadline_type": "undisclosed",
        "status": "open",
        "application_url": "https://careers.midea.com/schoolOut/post",
        "source_url": "https://careers.midea.com/schoolOut/post",
        "published_at": None,
        "reviewed_at": NOW,
        "source_name": "美的集团校园招聘官网",
        "description_raw": j["desc"],
        "recruiting_unit_raw": "美的集团",
        "hiring_department_raw": "",
        "campaign_cohort_raw": "应届生招聘",
        "source_record_id": f"page1-{i}",
        "recruitment_type_raw": "校招",
        "recruitment_scope_note": "campus_fulltime_page1",
        "region": "mainland",
        "overseas_flag": False,
        "record_kind": "official_position_id",
    })

# ---- Mindray: 20 records from rendered first screen (career.mindray.com/campus/jobs) ----
mindray_jobs = [
    ("PHD01 系统控制算法研究工程师（博士）", "J18899", "广东省·深圳市", "研发族"),
    ("PHD02 医学信号处理算法研究工程师（博士）", "J18900", "广东省·深圳市", "研发族"),
    ("PHD03 图像系统算法研究工程师（博士）", "J18901", "广东省·深圳市", "研发族"),
    ("PHD04 检测系统工程师（博士）", "J18902", "广东省·深圳市", "研发族"),
    ("PHD05 硬件开发工程师（博士）", "J18903", "广东省·深圳市", "研发族"),
    ("PHD06 传感器工程师（声学设计）（博士）", "J18904", "广东省·深圳市", "研发族"),
    ("PHD07 试剂研发工程师（博士）", "J18905", "广东省·深圳市,湖北省·武汉市,北京市", "研发族"),
    ("PHD08 临床工程师（临床医学与检验医学方向）（博士）", "J18906", "广东省·深圳市,北京市", "研发族"),
    ("PHD09 气路结构工程师（气动减震降噪）（博士）", "J18907", "广东省·深圳市", "研发族"),
    ("PHD10 学术专员（超声影像产品）（博士）", "J18922", "广东省·深圳市,湖北省·武汉市,陕西省·西安市,北京市,四川省·成都市", "研发族"),
    ("RD01 医学信号处理算法研究工程师", "J18975", "广东省·深圳市", "研发族"),
    ("RD02 系统控制算法研究工程师", "J18976", "广东省·深圳市,湖北省·武汉市", "研发族"),
    ("RD03 医学图像处理研究工程师", "J18977", "广东省·深圳市,湖北省·武汉市", "研发族"),
    ("RD04 图像系统算法研究工程师", "J18978", "广东省·深圳市", "研发族"),
    ("RD05 检测系统工程师", "J18979", "广东省·深圳市,湖北省·武汉市,北京市,陕西省·西安市,浙江省·杭州市", "研发族"),
    ("RD06 软件开发工程师", "J18980", "广东省·深圳市,湖北省·武汉市,北京市,陕西省·西安市,浙江省·杭州市", "研发族"),
    ("RD07 机械开发工程师", "J18981", "广东省·深圳市,湖北省·武汉市,江苏省·南京市", "研发族"),
    ("RD08 包装标贴设计工程师", "J18982", "湖北省·武汉市", "研发族"),
    ("RD09 工艺研究工程师", "J18983", "湖北省·武汉市", "研发族"),
    ("RD10 生物力学工程师", "J18984", "湖北省·武汉市", "研发族"),
]


def cn_city(raw):
    m = {"广东省": "", "湖北省": "", "陕西省": "", "四川省": "", "浙江省": "", "江苏省": "",
         "北京市": "北京", "上海市": "上海", "深圳市": "深圳", "武汉市": "武汉",
         "西安市": "西安", "成都市": "成都", "杭州市": "杭州", "南京市": "南京"}
    out = []
    for part in raw.split(","):
        part = part.strip()
        # strip province prefix
        for prov in ["广东省", "湖北省", "陕西省", "四川省", "浙江省", "江苏省", "北京市", "上海市", "天津市", "重庆市"]:
            if part.startswith(prov):
                part = part[len(prov):] or prov
                break
        if part and part not in out:
            out.append(part)
    return out


mindray_records = []
for title, code, loc, fam in mindray_jobs:
    cities = cn_city(loc)
    mindray_records.append({
        "id": f"mindray-{code}",
        "recruitment_unit": "深圳迈瑞生物医疗电子股份有限公司",
        "contracting_entity": "",
        "job_title": title,
        "job_category": fam,
        "cities": cities,
        "major_requirements_raw": "",
        "major_tags": [],
        "education_raw": "博士" if "博士" in title else "硕士/本科",
        "cohort_raw": "2027届全球校园招聘（国内本硕2026.8-2027.7毕业）",
        "deadline": None,
        "deadline_type": "undisclosed",
        "status": "open",
        "application_url": f"https://career.mindray.com/campus/jobs/{code}",
        "source_url": "https://career.mindray.com/campus/jobs",
        "published_at": None,
        "reviewed_at": NOW,
        "source_name": "迈瑞医疗校园招聘官网（北森）",
        "description_raw": f"职位编码{code}；{fam}；{loc}",
        "recruiting_unit_raw": "迈瑞医疗",
        "hiring_department_raw": fam,
        "campaign_cohort_raw": "2027届全球校园招聘",
        "source_record_id": code,
        "recruitment_type_raw": "校招",
        "recruitment_scope_note": "campus_rdfamily_firstscreen",
        "region": "mainland",
        "overseas_flag": False,
        "record_kind": "official_job_post_id",
    })

with open(f"{OUT}/midea_staging.json", "w") as f:
    json.dump({"accepted": midea_records, "rejected": [],
               "summary": {"company": "midea", "total_listed": 146, "collected": len(midea_records),
                           "coverage_note": "page-1 rich records; 10/page interactive pagination, 146 total",
                           "checked_at": NOW}}, f, ensure_ascii=False, indent=2)
with open(f"{OUT}/mindray_staging.json", "w") as f:
    json.dump({"accepted": mindray_records, "rejected": [],
               "summary": {"company": "mindray", "total_listed": 58, "collected": len(mindray_records),
                           "coverage_note": "R&D family first screen; other 4 categories (营销/技术支持/供应链/职能) need category filter",
                           "checked_at": NOW}}, f, ensure_ascii=False, indent=2)

print(f"midea: {len(midea_records)} records")
print(f"mindray: {len(mindray_records)} records")
