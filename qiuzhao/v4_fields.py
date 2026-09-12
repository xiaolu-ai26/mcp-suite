"""v4 fields for the recruitment dataset: pure functions, no I/O at import time.

Every v4 field in research/qiuzhao-v4-interface-20260911/SPEC.md is computed here from the raw
record; the old ``*_normalized`` fields (written by research/normalize-origin-20260911/*.py) are
only used as a reference where SPEC says so, with a raw-field fallback when they are absent.
The server calls :func:`build` once per jobs.json version (see ``qiuzhao/tools.py``); nothing in
this module reads the clock except :func:`status_on`, which takes ``today`` explicitly.

Run ``python -m qiuzhao.v4_fields check <jobs.json>`` before a deploy: it exits 1 when a schema
enum and the values present in the data differ (SPEC 9.15).
"""
from __future__ import annotations

import codecs
import datetime as dt
import json
import re
import sys
from collections import Counter

# ---------------------------------------------------------------- enums (schema values)

JOB_CATEGORIES = ["技术/研发", "产品", "运营", "设计", "市场/营销", "销售", "职能/支持", "金融", "咨询",
                  "医疗/医药", "制造/生产", "科研", "教育/培训", "法律/合规", "其他"]
RECRUITMENT_TYPES = ["校园招聘", "实习招聘", "社会招聘"]
INDUSTRIES = ["互联网/科技", "国企/央企", "制造/工业", "能源/电力", "金融", "医药/医疗", "教育", "物流/运输",
              "传媒/广告", "消费/零售", "农业", "房地产", "其他"]
EDUCATIONS = ["不限", "中专及以下", "大专", "本科", "硕士", "博士", "未注明"]
EDU_RANK = {"中专及以下": 1, "大专": 2, "本科": 3, "硕士": 4, "博士": 5}
MAJOR_CATEGORIES = ["计算机类", "电子信息类", "金融经济类", "机械制造类", "医药生物类", "管理类", "文科类",
                    "理科类", "设计艺术类", "农业类", "其他"]
# Schema enum = these + 未注明. 2028届/2024届 come from role descriptions ("2027届或2028届硕士在读",
# "2024—2027届高校毕业生优先"); `python -m qiuzhao.v4_fields check` fails when this drifts from data.
GRADUATION_YEARS = ["2028届", "2027届", "2026届", "2025届", "2024届"]
UNSPECIFIED = "未注明"

# ---------------------------------------------------------------- match bases and tiers

LEVELS = ["明确匹配", "推断匹配", "含未注明"]
# A row whose only 届 was inferred (按招聘季推断 / 来源专场注明 name a concrete 届) states no cohort
# itself, so a query for another 届 keeps it in the unspecified tier under this basis instead of
# dropping it (Max, 2026-09-12). A 届 the posting states still rules the row out.
INFERRED_OTHER = "推断为其他届别"
# basis -> tier (0 explicit, 1 inferred, 2 unspecified)
BASIS_TIER = {"岗位写明": 0, "活动标题写明": 0, "全国": 0, "专业不限": 0, "学历不限": 0,
              "按招聘季推断": 1, "来源专场注明": 1, "实习未写届别": 1, "社招不限届别": 1,
              UNSPECIFIED: 2, INFERRED_OTHER: 2}
# Order inside a tier (Max, 2026-09-12): per dimension the role's own words first, then the blanket
# forms (全国 / 专业不限 / 学历不限 / 活动标题写明), then inferred bases, then unspecified; dimensions
# are compared in RANK_DIMENSIONS order, so within a tier every 成都 row precedes every 全国 row.
RANK_DIMENSIONS = ("city", "major", "education", "graduation_year")
BASIS_RANK = {"岗位写明": 0, "全国": 1, "专业不限": 1, "学历不限": 1, "活动标题写明": 1,
              "按招聘季推断": 2, "来源专场注明": 2, "实习未写届别": 2, "社招不限届别": 2,
              UNSPECIFIED: 3, INFERRED_OTHER: 3}
NOTE_SOCIAL, NOTE_INTERN = "社招不限届别", "实习未写届别"

# ---------------------------------------------------------------- test / placeholder records

# Upstream test postings (e.g. 国聘 tenant tests). Each rule is listed with its hit count in the
# build report; only whole-record placeholders are matched, never real roles that mention testing.
TEST_RULES = [
    ("title_test_n", "job_title", re.compile(r"(?i)test\s*\d*")),            # 'test50'
    ("title_test_post", "job_title", re.compile(r"测试修改职位|测试职位\d{4,}")),  # 'zyx联调测试修改职位01'
    ("desc_placeholder_only", "description_raw", re.compile(r"(?:测试数据\s*)+")),
    ("desc_do_not_apply", "description_raw", re.compile(r"测试职位请勿投递")),
    ("desc_template_text", "description_raw", re.compile(r"这是工作职责.*这是任职要求", re.S)),
]
_FULLMATCH_RULES = {"title_test_n", "desc_placeholder_only"}


def test_rule(r):
    """Name of the first test-record rule that matches, else None."""
    for name, field, rx in TEST_RULES:
        text = str(r.get(field) or "").strip()
        if not text:
            continue
        hit = rx.fullmatch(text) if name in _FULLMATCH_RULES else rx.search(text)
        if hit:
            return name
    return None

# ---------------------------------------------------------------- 届别

_SEP = r"\s*(?:至|到|~|～|—|－|-)\s*"
DATE_WINDOW = re.compile(r"(20\d{2})[-./年](\d{1,2})(?:[-./月](\d{1,2})日?)?" + _SEP + r"(20\d{2})[-./年](\d{1,2})")
YEAR_RANGE = re.compile(r"(?<!\d)(20\d{2})" + _SEP + r"(20\d{2})\s*年")
YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
VALID_YEARS = range(2024, 2030)
_Y = r"(?<!\d)(20\d{2})(?!\d)"


def _window_years(sy, sm, ey, em):
    """Years whose June–August graduation season a window touches."""
    return {y for y in range(sy, ey + 1) if (y > sy or sm <= 8) and (y < ey or em >= 6)}


def years_in(text):
    """Cohort years in a field that is about cohorts (cohort_raw, campaign title, source scope).

    Graduation windows count the years whose 6–8 月 season they cover ("2026-11-01 至 2027-10-31"
    is 2027 only); "2026-2027年" counts both; every other standalone 20xx counts.
    """
    text = str(text or "")
    found = set()

    def window(m):
        found.update(_window_years(int(m[1]), int(m[2]), int(m[4]), int(m[5])))
        return " "

    def year_range(m):
        found.update(range(int(m[1]), int(m[2]) + 1))
        return " "

    text = DATE_WINDOW.sub(window, text)
    text = YEAR_RANGE.sub(year_range, text)
    found.update(int(y) for y in YEAR.findall(text))
    return sorted(y for y in found if y in VALID_YEARS)


# Job title: a year only counts next to a cohort word ("2027届", "2027校招", "- 2027 Start",
# "campus-2027"); bare years in titles are batch codes or dates.
TITLE_COHORT = re.compile(_Y + r"\s*(?:年度?)?\s*(?:届|应届|校招|校园招聘|秋招|春招|毕业|[Ss]tart\b|[Gg]rad)"
                          r"|(?i:campus|class of)[-\s]*" + _Y)
# Description: only years tied to graduation ("2027届", "2027年应届", "2027年7月毕业",
# "毕业时间为2027年…", "2025-2027届", "2026、2027届", "2026年1月至2027年8月毕业", "Class of 2027").
_GRAD = r"\s*(?:年度?)?\s*(?:\d{1,2}\s*月\s*(?:\d{1,2}\s*日)?\s*(?:前|之前|以前)?\s*)?(?:的)?\s*(?:届|应届|毕业)"
# Descriptions write windows as "2026年1月至2027年8月" too, which DATE_WINDOW (kept identical to the
# SPEC reference for cohort_raw) does not read; groups: 1 sy, 2 sm, 3 sd, 4 ey, 5 em, 6 毕业/届.
DESC_WINDOW = re.compile(r"(?:毕业(?:时间|日期)\s*(?:为|是|在|：|:)?\s*)?"
                         r"(20\d{2})[-./年](\d{1,2})月?(?:[-./]?(\d{1,2})日?)?" + _SEP + r"(20\d{2})[-./年](\d{1,2})"
                         r"\s*月?\s*(?:[-./]?\d{1,2}\s*日?)?\s*(?:期间|之间|间)?\s*(?:的)?\s*(毕业|届)?")
DESC_RANGE = re.compile(_Y + _SEP + _Y + r"\s*年?\s*(?:届|应届|毕业)")
DESC_LIST = re.compile(_Y + r"(?:\s*年?\s*(?:[、,，/]|和|及|或|与)\s*20\d{2}(?!\d))+" + r"\s*年?\s*(?:届|应届|毕业)")
DESC_SINGLE = [re.compile(_Y + _GRAD),
               re.compile(r"毕业(?:时间|日期)\s*(?:为|是|在|：|:)?\s*" + _Y),
               re.compile(r"(?i:class of|graduat\w*(?:\s+(?:in|between|from|by))?)\s+(?:[A-Za-z]+\s+)?" + _Y),
               re.compile(_Y + r"\s+(?i:graduates?|grads?)\b")]


def title_years(text):
    text = str(text or "")
    return sorted({int(a or b) for a, b in TITLE_COHORT.findall(text)} & set(VALID_YEARS))


def description_years(text):
    """Graduation years stated in a free-text description; ignores unrelated dates."""
    text = str(text or "")
    found = set()

    def window(m):
        # Only a window introduced by "毕业时间…" or followed by 毕业/届 is a graduation window.
        if m.group(0).startswith("毕业") or m[6]:
            found.update(_window_years(int(m[1]), int(m[2]), int(m[4]), int(m[5])))
            return " "
        return m.group(0)

    def year_range(m):
        found.update(range(int(m[1]), int(m[2]) + 1))
        return " "

    def year_list(m):
        found.update(int(y) for y in YEAR.findall(m.group(0)))
        return " "

    text = DESC_WINDOW.sub(window, text)
    text = DESC_RANGE.sub(year_range, text)
    text = DESC_LIST.sub(year_list, text)
    for rx in DESC_SINGLE:
        found.update(int(y) for y in rx.findall(text))
    return sorted(y for y in found if y in VALID_YEARS)


# A campus role with no cohort clue at all, published in this window, is inferred as this cohort.
SEASON_RULES = [(dt.date(2026, 7, 1), dt.date(2026, 12, 31), "2027届")]

# Recruiting scope of official sources, from research/qiuzhao-expansion-20260910/
# sources_registry.jsonl (scope_graduation_year, keyed by the detail-URL prefix). Regenerate with
# derive_source_scopes(); tests/test_v4_fields.py checks this copy against the registry file.
SOURCE_SCOPES = {
    "https://360campus.zhiye.com/job/": [2027],
    "https://app-tc.mokahr.com/campus-recruitment/vipshophr/10039": [2027],
    "https://app.mokahr.com/campus-recruitment/catlhr/148948#/job": [2026, 2027],
    "https://app.mokahr.com/campus-recruitment/glodon/91966#/job/": [2027],
    "https://app.mokahr.com/campus_apply/huya/4112#/job/": [2027],
    "https://app.mokahr.com/campus_apply/zhihu/68321#/job/": [2027],
    "https://campus-talent.alibaba.com/campus/position/": [2027],
    "https://campus.163.com/app/detail/index?id=": [2027],
    "https://campus.58.com/campus-recruitment/58/150953/#/job/": [2027],
    "https://campus.dewu.com/578078/position/": [2027],
    "https://campus.jd.com/#/details?id=": [2027],
    "https://campus.kingdee.com/campus-recruitment/kingdeehr/1665": [2027],
    "https://campus.kuaishou.cn/recruit/campus/e/#/campus/job/": [2027],
    "https://careers.ctrip.com/#/campus/jobDetail/": [2027],
    "https://careers.dji.com/zh-CN/campus/job/": [2027],
    "https://careers.iqiyi.com/campus/position/": [2027],
    "https://careers.midea.com/schoolOut/post/details?id=": [2026, 2027],
    "https://careers.oppo.com/university/oppo/campus/postDetail/": [2027],
    "https://careers.pddglobalhr.com/campus/grad/": [2027],
    "https://hr-campus.vivo.com/#/job/": [2027],
    "https://hr.g-bits.com/web/index.html#/post-web/post-detail/": [2027],
    "https://iflytek.zhiye.com/job/": [2027],
    "https://job.xiaohongshu.com/campus/position/": [2027],
    "https://jobs.bilibili.com/campus/position/": [2027],
    "https://jobs.bytedance.com/campus/position/": [2027],
    "https://jobs.mihoyo.com/#/campus/position/": [2027],
    "https://join.qq.com/post_detail.html?postid=": [2027],
    "https://ke.zhiye.com/job/": [2027],
    "https://lilithgames.jobs.feishu.cn/campus/job/": [2027],
    "https://papergames.jobs.feishu.cn/campus/job/": [2027],
    "https://recruit.inovance.com/#/job/": [2027],
    "https://sensetime.jobs.feishu.cn/campus/job/": [2027],
    "https://talent.baidu.com/jobs/detail/": [2027],
    "https://talent.didiglobal.com/campus/job/": [2027],
    "https://thundersoft.jobs.feishu.cn/campus/job/": [2027],
    "https://www.pgcareers.com/global/en/job/R": [2025, 2026, 2027],
    "https://xiaomi.jobs.f.mioffice.cn/campus/job/": [2027],
    "https://yiche.zhiye.com/job/": [2027],
    "https://zhaopin.meituan.com/web/position/detail?jobUnionId=": [2027],
}


def derive_source_scopes(registry_rows):
    """{detail-URL prefix: [years]} for registry rows whose scope names a cohort."""
    out = {}
    for row in registry_rows:
        pattern = str(row.get("detail_url_pattern") or "")
        years = years_in(row.get("scope_graduation_year"))
        if pattern.startswith("http") and "{" in pattern and years:
            out[pattern.split("{")[0][:60]] = years
    return dict(sorted(out.items()))


def source_scope_years(url):
    url = str(url or "")
    for prefix, years in SOURCE_SCOPES.items():
        if url.startswith(prefix):
            return years
    return []


def campaign_text(r):
    return r.get("campaign_cohort_raw") or r.get("batch_name") or ""


def graduation_of(r):
    """(years, basis, note, rule).

    years/basis: cohorts that apply and why; note: why there is no year (社招不限届别 /
    实习未写届别 / 未注明, empty when years is non-empty); rule: which step decided (for counts).
    Order (SPEC 6.3 + v4 decision 3): role text, campaign title, then — only when both are
    silent — social recruitment, job title, description, internship, publish season, source scope.
    """
    basis = {}
    for y in years_in(r.get("cohort_raw")):
        basis[f"{y}届"] = "岗位写明"
    rule = "cohort_raw" if basis else ""
    for y in years_in(campaign_text(r)):
        basis.setdefault(f"{y}届", "活动标题写明")
    if basis:
        return _sorted(basis), basis, "", rule or "campaign_title"
    rtype = r.get("recruitment_type")
    if rtype == "社会招聘":
        return [], {}, NOTE_SOCIAL, "social"
    for rule, years in (("job_title", title_years(r.get("job_title"))),
                        ("description", description_years(r.get("description_raw")))):
        if years:
            basis = {f"{y}届": "岗位写明" for y in years}
            return _sorted(basis), basis, "", rule
    if rtype == "实习招聘":
        return [], {}, NOTE_INTERN, "intern"
    if rtype == "校园招聘":
        if r.get("p1_company"):
            return [], {}, "未注明", "p1_no_explicit_cohort"
        published = parse_date(r.get("published_at"))
        if published:
            for start, end, cohort in SEASON_RULES:
                if start <= published <= end:
                    return [cohort], {cohort: "按招聘季推断"}, "", "season"
        else:
            years = source_scope_years(r.get("source_url"))
            if years:
                basis = {f"{y}届": "来源专场注明" for y in years}
                return _sorted(basis), basis, "", "source_scope"
            return [], {}, UNSPECIFIED, "campus_no_date_unmatched"
    return [], {}, UNSPECIFIED, "unspecified"


def _sorted(basis):
    return sorted(basis, reverse=True)

# ---------------------------------------------------------------- 学历

EDU_GARBAGE = re.compile(r"\d{2,3}[A-Za-z0-9]{4,6}")


def is_edu_garbage(raw):
    return bool(EDU_GARBAGE.fullmatch(str(raw or "").strip()))


def education_of(raw):
    """Lowest level a role accepts (7 tiers). '本科/硕士' takes the lower one."""
    s = str(raw or "").strip()
    if not s or s == "未披露" or is_edu_garbage(s):
        return UNSPECIFIED
    if "无学历" in s or s == "不限":
        return "不限"
    if any(k in s for k in ("初中", "高中", "中专", "中技")):
        return "中专及以下"
    if "大专" in s or "专科" in s:
        return "大专"
    if "本科" in s or "Bachelor" in s or s == "本硕":
        return "本科"
    if "硕士" in s or "Master" in s:
        return "硕士"
    if "博士" in s or "PhD" in s:
        return "博士"
    return UNSPECIFIED

# ---------------------------------------------------------------- 专业

MAJOR_PLACEHOLDER = {"", "未披露", "详见职位描述"}
MAJOR_UNLIMITED = re.compile(r"专业不限|不限专业|专业[：:]\s*不限|不限制专业")
# Fallback when major_normalized is absent: the classifier of normalize_major_fix.py (the last
# script that wrote major_normalized), same keyword order.
_MAJOR_FALLBACK = [
    ("计算机类", "计算机科学 计算机技术 计算机应用 软件工程 软件技术 人工智能 大数据 网络工程 信息安全 物联网工程 数据科学 机器学习 深度学习 算法 程序设计 网络空间安全 数字媒体技术 游戏设计 计算机类 软件类"),
    ("电子信息类", "电子信息 电子科学 通信工程 通信技术 自动化 电气工程 电气类 微电子 信息工程 集成电路 光电信息 电磁场 信号处理 电子类"),
    ("机械制造类", "机械工程 机械设计 机械制造 材料科学 材料工程 材料类 能源与动力 能源动力 动力工程 车辆工程 汽车服务 航空航天 船舶与海洋 兵器类 核工程 工程力学 机械类 热能与动力 能源类"),
    ("金融经济类", "金融学 金融工程 经济学 经济统计学 会计学 财务管理 审计学 投资学 保险学 财政学 税收学 统计学 国际经济 国际贸易 金融类 经济类 财会类"),
    ("医药生物类", "临床医学 基础医学 预防医学 口腔医学 中医学 中药学 药学 药物制剂 护理学 医学检验 医学影像 康复治疗 公共卫生 生物医学 生物技术 生物工程 制药工程 医学类 药学类 生物类"),
    ("管理类", "工商管理 人力资源 市场营销 行政管理 公共管理 旅游管理 酒店管理 物流管理 供应链管理 项目管理 企业管理 管理科学 工业工程 电子商务 管理类"),
    ("文科类", "汉语言文学 新闻学 传播学 广告学 法学 法律 英语 日语 翻译 教育学 社会学 心理学 哲学 历史学 政治学 国际关系 公共事业 中国语言文学 外国语言文学 文科类"),
    ("理科类", "数学与应用数学 信息与计算科学 物理学 应用物理学 化学 应用化学 地理科学 海洋科学 大气科学 环境科学 生态学 理科类"),
    ("设计艺术类", "视觉传达 环境设计 产品设计 服装与服饰 工业设计 美术学 绘画 雕塑 摄影 动画 音乐学 舞蹈学 戏剧影视 艺术设计 设计类 艺术类"),
    ("农业类", "农学 园艺 植物保护 动物科学 动物医学 林学 园林 水产养殖 食品科学 食品质量 粮食工程 农业资源 农业类 食品类"),
]


def _major_fallback(r):
    text = str(r.get("major_requirements_raw") or "") or " ".join(map(str, r.get("major_tags") or []))
    text = re.sub(r"办公软件|应用软件|办公应用|软件应用|熟练使用|掌握", "", text)
    for cat, words in _MAJOR_FALLBACK:
        if any(w in text for w in words.split()):
            return cat
    return "其他"


def major_state(r):
    raw = str(r.get("major_requirements_raw") or "").strip()
    if MAJOR_UNLIMITED.search(raw):
        return "不限"
    if raw in MAJOR_PLACEHOLDER and not r.get("major_tags"):
        return UNSPECIFIED
    return "写明"


def major_category_of(r):
    state = major_state(r)
    if state != "写明":
        return state
    if "major_normalized" not in r:
        return _major_fallback(r)
    mc = r.get("major_normalized")
    return mc if mc in MAJOR_CATEGORIES else "其他"

def major_categories_of(r):
    """All categories supported by the explicit major field, retaining legacy primary."""
    state = major_state(r)
    if state != '写明':
        return []
    text = str(r.get('major_requirements_raw') or '') or ' '.join(map(str, r.get('major_tags') or []))
    text = re.sub(r'办公软件|应用软件|办公应用|软件应用|熟练使用|掌握', '', text)
    found = [cat for cat, words in _MAJOR_FALLBACK if any(word in text for word in words.split())]
    primary = major_category_of(r)
    if not found and primary in MAJOR_CATEGORIES:
        found = [primary]
    return found


# ---------------------------------------------------------------- 城市 / 地区

AREA_CN = re.compile(r"'area_cn':\s*'([^']+)'")
CITY_UNKNOWN = {"", "未披露", "未知", "多地"}
NON_CITY = {"Hybrid", "智能制造", "销售"}
CITY_ALIASES = {"中国": ["全国"], "中国大陆": ["全国"], "中国香港": ["香港"], "香港特别行政区": ["香港"],
                "Hongkong": ["香港"], "Shanghai": ["上海"], "SanFrancisco": ["旧金山"], "SanJose": ["圣何塞"],
                "Seattle": ["西雅图"], "London": ["伦敦"], "Paris": ["巴黎"], "NewYork": ["纽约"],
                "NewYorkCity": ["纽约"], "Toronto": ["多伦多"], "Montreal": ["蒙特利尔"], "Clearwater": ["克利尔沃特"],
                "United States": ["美国"], "Remote": ["远程"], "RemoteIreland;Remote": ["远程"],
                "SanFranciscoBayAreaorNewYork": ["旧金山", "纽约"]}
# Every overseas value in the 2026-09-11 data (hand-curated, SPEC 6.8).
OVERSEAS_CITIES = {"圣何塞", "新加坡", "西雅图", "迪拜", "利雅得", "东京", "塔吉格", "科威特城", "圣地亚哥", "纽约",
                   "伦敦", "墨西哥", "墨西哥城", "首尔", "洛杉矶", "曼谷", "开罗", "英国", "圣保罗", "印尼", "埃及",
                   "胡志明", "吉隆坡", "古来", "古尔冈", "巴黎", "莫斯科", "约翰内斯堡", "阿拉木图", "海外", "旧金山",
                   "多伦多", "蒙特利尔", "克利尔沃特", "美国", "远程"}
HMT = ("香港", "澳门", "台湾", "台北")
REGION_ORDER = ["中国大陆", "港澳台", "海外"]


def _city_fallback(city):
    """normalize_fields_v2.normalize_city, used only when cities_normalized is absent."""
    city = str(city or "").strip()
    if city in ("未披露", "未知", "", "null", "None", "不限"):
        return ""
    if city in ("全国", "中国", "全国各地", "全国多地", "全国各省市"):
        return "全国"
    if city in ("海外", "国外", "境外", "海外及其他"):
        return "海外"
    if "-" in city:
        city = city.split("-")[0].strip()
    city = city[:-1] if city.endswith("市") else city
    city = city.replace(" ", "")
    for sep in (",", "，", "/", "、", ";", "；"):
        if sep in city:
            city = city.split(sep)[0].strip()
            break
    return re.sub(r"[（(].*?[）)]", "", city).strip()


def cities_of(r):
    out = []
    raw = r.get("cities") or []
    raw = [raw] if isinstance(raw, str) else raw
    for c in raw:
        m = AREA_CN.search(str(c))
        if m:
            out.append(m.group(1).split("-")[0])
    normalized = r.get("cities_normalized")
    if normalized is None:
        normalized = [_city_fallback(c) for c in raw if "area_code" not in str(c)]
    for c in normalized or []:
        s = str(c).strip()
        if "area_code" not in s:
            out.append(s)
    result = []
    for c in out:
        for v in CITY_ALIASES.get(c, [c]):
            if v not in CITY_UNKNOWN and v not in NON_CITY and v not in result:
                result.append(v)
    return result


def city_region(c):
    if c in OVERSEAS_CITIES:
        return "海外"
    if c.startswith(HMT):
        return "港澳台"
    return "中国大陆"


OVERSEAS_REGION = {"overseas", "海外"}


def region_of(r, cities):
    """From the cities; only without a city fall back to overseas_flag/region/country."""
    if cities:
        regs = {city_region(c) for c in cities}
        return "、".join(g for g in REGION_ORDER if g in regs)
    if r.get("overseas_flag") or (r.get("region") or "") in OVERSEAS_REGION or (r.get("country") or "中国") != "中国":
        return "海外"
    return "中国大陆"


def norm_city(q):
    q = q.strip()
    q = q[:-1] if q.endswith("市") and len(q) > 2 else q
    alias = CITY_ALIASES.get(q)
    return alias[0] if alias else q

# ---------------------------------------------------------------- 岗位大类

# Only where the normalizer said 技术/研发 but the source's own category says otherwise (SPEC 6.2).
RAW_CATEGORY_RULES = [
    ("产品", lambda s: "产品" in s and "研发" not in s),
    ("运营", lambda s: "运营" in s and "生产" not in s),
    ("销售", lambda s: "销售" in s),
    ("市场/营销", lambda s: "市场" in s),
    ("职能/支持", lambda s: "人力" in s or s.upper().startswith("HR")),
    ("设计", lambda s: s in {"设计", "设计类", "艺术/设计"} or any(k in s for k in ("视觉", "交互", "UI", "UX", "美术"))),
]
# Fallback when job_category_normalized is absent: normalize_fields_v2.normalize_job_category's
# keyword table, except that 技术/研发 is tried last (its keywords 技术/数据/AI/go swallowed
# product and operations roles) and the source category is matched before the title.
_JC_FALLBACK = [
    ("产品", "产品 PM 产品经理 产品助理"),
    ("运营", "运营"),
    ("市场/营销", "市场 营销 品牌 公关 推广 广告 策划 BD 商务"),
    ("设计", "设计 UI UX 视觉 交互 平面 美术 插画"),
    ("销售", "销售 客户经理 客户成功 售前 售后 渠道 大客户"),
    ("职能/支持", "人力 HR 行政 财务 会计 法务 审计 采购 供应链 物流 仓储 客服 助理 秘书 文员 管培生 管理培训生 人事"),
    ("金融", "金融 银行 证券 基金 保险 投资 风控 信贷 投行 分析师"),
    ("咨询", "咨询 顾问 战略"),
    ("医疗/医药", "医生 护士 医药 医疗 临床 药剂 检验 影像 护理"),
    ("制造/生产", "生产 制造 工艺 质量 质检 设备 机械 电气 自动化 工厂 车间"),
    ("科研", "科研 研究员 科学家 博士后 实验室"),
    ("教育/培训", "教师 老师 教育 培训 讲师 教授 助教"),
    ("法律/合规", "律师 法律 合规"),
    ("技术/研发", "工程师 开发 算法 前端 后端 全栈 测试 运维 数据库 安全 架构 数据 AI 人工智能 机器学习 深度学习 "
                  "嵌入式 硬件 芯片 通信 网络 软件 程序员 研发 技术 java python c++ go rust ios android 大数据 云计算 区块链"),
]


def _jc_fallback(raw, title):
    for text in (raw, f"{raw} {title}"):
        low = text.lower()
        for cat, words in _JC_FALLBACK:
            if any(w.lower() in low for w in words.split()):
                return cat
    return "其他"


def job_category_of(r):
    raw = str(r.get("job_category") or r.get("category") or "").strip()
    if "job_category_normalized" not in r:
        return _jc_fallback(raw, str(r.get("job_title") or ""))
    norm = r.get("job_category_normalized") or "其他"
    if norm != "技术/研发" or not raw:
        return norm
    for cat, hit in RAW_CATEGORY_RULES:
        if hit(raw):
            return cat
    return norm

# ---------------------------------------------------------------- 截止日 / 状态 / 日期

UNTIL_FILLED = {"招满即止", "until_filled", "rolling"}
DATE10 = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")


def parse_date(value):
    m = DATE10.match(str(value or ""))
    if not m:
        return None
    try:
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def deadline_of(r):
    """(date|None, kind). Any parseable date before 2099 is 明确日期 — including the 国聘 rows
    that say deadline_type=undisclosed but carry end_time (see RECEIPT: decision 5)."""
    d = parse_date(r.get("deadline"))
    if d and d.year >= 2099:
        return None, "招满即止或长期"
    if d:
        return d, "明确日期"
    if r.get("deadline_type") in UNTIL_FILLED:
        return None, "招满即止或长期"
    return None, UNSPECIFIED


def base_status(r):
    """Status before the date check: 已下线 / 已截止 / 未核验 / 招聘中."""
    s = r.get("status")
    if s == "removed":
        return "已下线"
    if s == "expired":
        return "已截止"
    if s == "unverified":
        return "未核验"
    return "招聘中"


def status_on(item, today):
    """Runtime status: a past explicit deadline turns any status into 已截止."""
    d = item["deadline"]
    return "已截止" if d and d < today.isoformat() else item["status"]


def date_of(value):
    d = parse_date(value)
    return d.isoformat() if d else None

# ---------------------------------------------------------------- one v4 job

# Always present (possibly empty); the others are dropped when empty (SPEC 3.1 "?").
CORE = ("id", "job_title", "company", "job_category", "recruitment_type", "industry", "cities", "region",
        "graduation_years", "graduation_year_basis", "education", "major_category", "deadline",
        "deadline_kind", "status", "published_at", "description_raw", "application_url", "source_url",
        "source_name", "reviewed_at")
KEYWORD_FIELDS = ("job_title", "job_category_raw", "description_raw", "company", "recruiting_unit_raw",
                  "parent_unit_raw", "hiring_department_raw", "contracting_entity")
COMPANY_FIELDS = ("company", "recruiting_unit_raw", "parent_unit_raw", "contracting_entity")


def _text(value):
    return "" if value is None else str(value)


def to_item(r):
    """The v4 public record (status = base status; apply status_on() at read time)."""
    return convert(r)[0]


def convert(r):
    """(v4 record, graduation rule name)."""
    d, kind = deadline_of(r)
    cities = cities_of(r)
    years, basis, note, grad_rule = graduation_of(r)
    edu_raw = _text(r.get("education_raw"))
    tags = r.get("major_tags") or []
    it = {
        "id": _text(r.get("id")),
        "job_title": _text(r.get("job_title") or r.get("title")),
        "company": _text(r.get("canonical_company") or r.get("recruitment_unit") or r.get("company")),
        "recruiting_unit_raw": _text(r.get("recruiting_unit_raw")),
        "hiring_department_raw": _text(r.get("hiring_department_raw")),
        "parent_unit_raw": _text(r.get("parent_unit_raw")),
        "contracting_entity": _text(r.get("contracting_entity")),
        "job_category": job_category_of(r),
        "job_category_raw": _text(r.get("job_category") or r.get("category")),
        "recruitment_type": _text(r.get("recruitment_type")),
        "industry": _text(r.get("industry")),
        "industry_tags": r.get("industry_tags") or [],
        "cities": cities,
        "region": region_of(r, cities),
        "country": _text(r.get("country")),
        "graduation_years": years,
        "graduation_year_basis": basis,
        "graduation_year_note": note,
        "cohort_raw": _text(r.get("cohort_raw")),
        "campaign_title": _text(campaign_text(r)),
        "education": education_of(edu_raw),
        "education_raw": "" if is_edu_garbage(edu_raw) else edu_raw,
        "major_category": major_category_of(r),
        "major_categories": major_categories_of(r),
        "major_requirements_raw": _text(r.get("major_requirements_raw")),
        "major_tags": [str(t) for t in tags] if isinstance(tags, list) else [str(tags)],
        "deadline": d.isoformat() if d else None,
        "deadline_kind": kind,
        "status": base_status(r),
        "status_note": _text(r.get("status_note")),
        "published_at": date_of(r.get("published_at")),
        "job_code": _text(r.get("job_code") or r.get("position_code")),
        "description_raw": _text(r.get("description_raw")),
        "application_url": _text(r.get("application_url")),
        "source_url": _text(r.get("source_url")),
        "announcement_url": _text(r.get("announcement_url")),
        "campaign_url": _text(r.get("campaign_url")),
        "job_listing_url": _text(r.get("job_listing_url")),
        "source_name": _text(r.get("source_name")),
        "reviewed_at": r.get("reviewed_at") or None,
    }
    return {k: v for k, v in it.items() if k in CORE or v not in ("", [], {}, None)}, grad_rule


def data_as_of(rows):
    return max((str(r.get("reviewed_at") or "") for r in rows), default="") or None


def build(rows):
    """Raw jobs.json rows (a list, or any iterable of dicts) -> (items, data_as_of, report).

    Same validity filter as v3 (source_url and application_url), then dedupe by id (first
    occurrence wins; SPEC 6.1 found every duplicate group identical), then drop test records and
    removed roles, then compute every v4 field. ``report`` holds the counts quoted in RECEIPT.md.
    Passing a generator (tools.iter_json_array) keeps only one raw row alive at a time.
    """
    if isinstance(rows, (dict, str, bytes)) or rows is None:
        raise ValueError("岗位库格式异常，请稍后重试")
    report = Counter()
    seen, items, as_of = set(), [], ""
    for r in rows:
        report["rows_total"] += 1
        if not (isinstance(r, dict) and r.get("source_url") and r.get("application_url")):
            continue
        report["rows_valid"] += 1
        rule = test_rule(r)
        if rule:
            report[f"test_rows_before_dedupe:{rule}"] += 1
        rid = _text(r.get("id")).strip()
        if not rid:
            report["dropped_no_id"] += 1
            continue
        if rid in seen:
            report["dropped_duplicate_id"] += 1
            continue
        seen.add(rid)
        report["rows_deduped"] += 1
        as_of = max(as_of, str(r.get("reviewed_at") or ""))
        if rule:
            report["dropped_test_record"] += 1
            report[f"test_rule:{rule}"] += 1
            continue
        if r.get("status") == "removed":
            report["dropped_removed"] += 1
            continue
        it, grad_rule = convert(r)
        items.append(it)
        _count(report, r, it, grad_rule)
    report["items"] = len(items)
    return items, as_of or None, dict(report)


def _count(report, r, it, rule):
    """Correction counts (after dedupe and test filtering)."""
    report[f"grad_rule:{rule}"] += 1
    if not it["graduation_years"]:
        report[f"grad_note:{it['graduation_year_note']}"] += 1
    if r.get("job_category_normalized") and it["job_category"] != r["job_category_normalized"]:
        report[f"job_category_fixed:{it['job_category']}"] += 1
    if any("area_code" in str(c) for c in r.get("cities") or []) and it["cities"]:
        report["city_area_code_fixed"] += 1
    if "全国" in it["cities"]:
        report["city_nationwide"] += 1
    if not it["cities"]:
        report["city_unspecified"] += 1
    if "海外" in it["region"] and not r.get("overseas_flag"):
        report["overseas_flag_was_false"] += 1
    if is_edu_garbage(r.get("education_raw")):
        report["education_garbage"] += 1
    report[f"education:{it['education']}"] += 1
    report[f"major:{'不限' if it['major_category'] == '不限' else it['major_category'] if it['major_category'] == UNSPECIFIED else '写明'}"] += 1
    report[f"deadline_kind:{it['deadline_kind']}"] += 1
    if r.get("deadline_type") == "undisclosed" and it["deadline_kind"] == "明确日期":
        report["deadline_undisclosed_with_date"] += 1
    report[f"rtype:{it['recruitment_type']}"] += 1

# ---------------------------------------------------------------- enum / data consistency

def enum_report(items):
    """Schema enums vs the values present in the data; empty 'problems' means consistent."""
    present = {
        "job_category": {it["job_category"] for it in items},
        "recruitment_type": {it["recruitment_type"] for it in items},
        "industry": {it["industry"] for it in items},
        "education": {it["education"] for it in items},
        "major_category": {it["major_category"] for it in items},
        "graduation_year": {y for it in items for y in it["graduation_years"]},
    }
    enums = {"job_category": set(JOB_CATEGORIES), "recruitment_type": set(RECRUITMENT_TYPES),
             "industry": set(INDUSTRIES), "education": set(EDUCATIONS),
             "major_category": set(MAJOR_CATEGORIES) | {"不限", UNSPECIFIED},
             "graduation_year": set(GRADUATION_YEARS)}
    problems = []
    for name, allowed in enums.items():
        extra = sorted(present[name] - allowed)
        unused = sorted(allowed - present[name])
        if extra:
            problems.append(f"{name}: 数据里有、枚举里没有 {extra}（这些岗位用该条件查不到）")
        if unused:
            problems.append(f"{name}: 枚举里有、数据里没有 {unused}（选了必然 0 条）")
    return {"present": {k: sorted(v) for k, v in present.items()}, "problems": problems}


_WS = re.compile(r"[\s,]*")
CHUNK_BYTES = 4 << 20


def iter_json_file(path, chunk_bytes=CHUNK_BYTES):
    """Yield the elements of a file holding one top-level JSON array, one element at a time.

    Same C scanner as json.loads, but the file is decoded in chunks and only one raw record is
    alive at a time: reading the 81 MB jobs.json whole costs ~570 MB of Python heap at the peak
    (bytes + a UCS-4 str + the decode buffer), this costs one chunk plus the converted records.
    """
    decoder = json.JSONDecoder()
    utf8 = codecs.getincrementaldecoder("utf-8")()
    with open(path, "rb") as fh:
        buf, pos, eof = "", 0, False

        def more():
            nonlocal buf, pos, eof
            if eof:
                return False
            data = fh.read(chunk_bytes)
            eof = not data
            buf = buf[pos:] + utf8.decode(data, final=eof)
            pos = 0
            return True

        def skip():
            nonlocal pos
            pos = _WS.match(buf, pos).end()
            while pos >= len(buf) and more():
                pos = _WS.match(buf, pos).end()

        skip()
        if buf[pos:pos + 1] != "[":
            raise ValueError("岗位库格式异常，请稍后重试")
        pos += 1
        while True:
            skip()
            if pos >= len(buf):
                raise ValueError("岗位库格式异常：文件不完整")
            if buf[pos] == "]":
                pos += 1
                while True:
                    if buf[pos:].strip():
                        raise ValueError("岗位库格式异常：数组后还有内容")
                    pos = len(buf)
                    if not more():
                        return
            try:
                obj, end = decoder.raw_decode(buf, pos)
            except json.JSONDecodeError:
                if more():  # the element runs past this chunk: read on and parse it again
                    continue
                raise
            if end >= len(buf) - 1 and not eof and more():
                continue  # a scalar cut at the chunk end (123 of 12345) must be parsed again
            yield obj
            pos = end


def main(argv=None):
    """``python qiuzhao/v4_fields.py check <jobs.json>`` also works as a standalone file (no imports
    from this code tree), which is how the deploy check runs it against the live jobs.json."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] != "check":
        print("usage: python -m qiuzhao.v4_fields check <jobs.json>", file=sys.stderr)
        return 2
    items, as_of, report = build(iter_json_file(argv[1]))
    result = enum_report(items)
    print(json.dumps({"items": len(items), "data_as_of": as_of, "problems": result["problems"]},
                     ensure_ascii=False, indent=1))
    print("RESULT", "FAIL" if result["problems"] else "OK")
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
