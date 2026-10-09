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
RECRUITMENT_TYPES = ["校园招聘", "实习招聘", "社会招聘", "未注明"]
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
              "按招聘季推断": 1, "来源专场注明": 1, "实习未写届别": 1, "社招不限届别": 1, "旧数据记录": 1,
              UNSPECIFIED: 2, INFERRED_OTHER: 2}
# Order inside a tier (Max, 2026-09-12): per dimension the role's own words first, then the blanket
# forms (全国 / 专业不限 / 学历不限 / 活动标题写明), then inferred bases, then unspecified; dimensions
# are compared in RANK_DIMENSIONS order, so within a tier every 成都 row precedes every 全国 row.
RANK_DIMENSIONS = ("city", "major", "education", "graduation_year")
BASIS_RANK = {"岗位写明": 0, "全国": 1, "专业不限": 1, "学历不限": 1, "活动标题写明": 1,
              "按招聘季推断": 2, "来源专场注明": 2, "实习未写届别": 2, "社招不限届别": 2, "旧数据记录": 2,
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
YEAR_RANGE = re.compile(r"(?<!\d)(20\d{2})" + _SEP + r"(20\d{2})\s*(?:年|届)")
YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
VALID_YEARS = range(2000, 2100)
_Y = r"(?<!\d)(20\d{2})(?!\d)"


_SHORT_COHORT_CHAIN = re.compile(r'(?<![\d第])(?:20\d{2}|[23]\d)(?:\s*(?:/|、|,|，|及|或|-|至)\s*(?:20\d{2}|[23]\d)){0,99}\s*(?:届|校招|应届)')


def expand_short_cohorts(text):
    """Expand 20-39 only when tied to cohort words; never salary, age or identifiers."""
    text = str(text or '')
    return _SHORT_COHORT_CHAIN.sub(
        lambda match: re.sub(r'(?<!\d)([23]\d)(?!\d)', lambda year: '20'+year[1], match[0]), text)


def _window_years(sy, sm, ey, em):
    """Years whose June–August graduation season a window touches."""
    return {y for y in range(sy, ey + 1) if (y > sy or sm <= 8) and (y < ey or em >= 6)}


def years_in(text):
    """Cohort years in a field that is about cohorts (cohort_raw, campaign title, source scope).

    Graduation windows count the years whose 6–8 月 season they cover ("2026-11-01 至 2027-10-31"
    is 2027 only); "2026-2027年" counts both; every other standalone 20xx counts.
    """
    text = expand_short_cohorts(text)
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
    text = expand_short_cohorts(text)
    found = {int(a or b) for a, b in TITLE_COHORT.findall(text)}
    for match in _SHORT_COHORT_CHAIN.finditer(text):
        found.update(years_in(match[0]))
    return sorted(found & set(VALID_YEARS))


def description_years(text):
    """Graduation years stated in a free-text description; ignores unrelated dates."""
    text = expand_short_cohorts(text)
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
    scoped = r.get('cohort_raw') if r.get('cohort_scope') in {
        'campaign_announcement', 'headquarters_campaign_announcement'} else ''
    return r.get("campaign_cohort_raw") or r.get("batch_name") or scoped or ""


def positive_cohort_text(text):
    """Keep positive eligibility clauses, never promote a negated range to a lower bound."""
    eligible = []
    for clause in re.split(r'[,，；;。\n]', str(text or '')):
        exclusion = re.search(r'不接受|不招收|不面向|不含|除外|不适用', clause)
        if exclusion:
            prefix = clause[:exclusion.start()]
            if (exclusion.group() in {'除外','不适用'}
                    or not re.search(r'20\d{2}|[23]\d\s*届', clause[exclusion.end():])
                    or not re.search(r'仅|只限|面向|接受|招收', prefix)):
                continue
            clause = prefix
        eligible.append(clause)
    return '；'.join(eligible)


def positive_cohort_years(text):
    return years_in(positive_cohort_text(text))


def role_description_years(text):
    """Ignore explicitly wider campaign clauses when extracting role eligibility."""
    sentences = []
    for sentence in re.split(r'[。\n]', str(text or '')):
        if re.search(r'其中部分|部分.{0,12}岗位|部分境外|其他岗位', sentence):
            continue
        sentences.append(re.split(r'不接受|不招收|不面向', sentence, maxsplit=1)[0])
    return description_years('\n'.join(sentences))


def job_bound_campaign(r):
    ids = r.get('campaign_job_ids')
    return isinstance(ids, list) and str(r.get('source_record_id') or '') in ids


def graduation_conflicts_of(r, resolved=None):
    years, _, _, rule = resolved or graduation_of(r)
    if rule not in ('cohort_raw', 'description', 'job_title') or job_bound_campaign(r):
        return []
    extra = set(years_in(campaign_text(r))) - {int(y[:4]) for y in years}
    bounds = graduation_constraints_of(r, resolved or graduation_of(r))
    if bounds:
        extra = {y for y in extra if y < bounds['min_year'] or (bounds.get('max_year') is not None and y > bounds['max_year']) or y in bounds.get('excluded_years', [])}
    return [{'source': 'campaign', 'years': [f'{y}届' for y in sorted(extra)],
             'note': '一般活动条件与岗位明确条件冲突；按岗位条件展示'}] if extra else []


def graduation_of(r):
    """(years, basis, note, rule).

    years/basis: cohorts that apply and why; note: why there is no year (社招不限届别 /
    实习未写届别 / 未注明, empty when years is non-empty); rule: which step decided (for counts).
    Explicit role conditions precede generic campaigns. Only a campaign bound to
    this official source record may expand an explicit role cohort.
    """
    scoped_campaign = r.get('cohort_scope') in {'campaign_announcement', 'headquarters_campaign_announcement'}
    role_years = [] if scoped_campaign else positive_cohort_years(r.get('cohort_raw'))
    campaign_years = positive_cohort_years(campaign_text(r))
    basis = {f'{y}届': '岗位写明' for y in role_years}
    if basis:
        if job_bound_campaign(r):
            for year in campaign_years:
                basis.setdefault(f'{year}届', '活动标题写明')
        return _sorted(basis), basis, '', 'cohort_raw'
    rtype = r.get('recruitment_type')
    description = role_description_years(r.get('description_raw'))
    title = title_years(r.get('job_title'))
    if rtype == '社会招聘' and not description and not title and not job_bound_campaign(r):
        return [], {}, NOTE_SOCIAL, 'social'
    if description:
        description_text = str(r.get('description_raw') or '')
        if (re.search(r'20\d{2}\s*届(?:毕业生)?\s*(?:也可|亦可|也欢迎)', description_text)
                and not re.search(r'仅限|仅面向|只接受|只招', description_text)):
            description = sorted(set(description) | set(title))
        basis = {f'{y}届': '岗位写明' for y in description}
        rule = 'description'
    elif title:
        basis = {f'{y}届': '岗位写明' for y in title}
        rule = 'job_title'
    else:
        basis = {f'{y}届': '活动标题写明' for y in campaign_years}
        rule = 'campaign_title'
    if basis:
        if job_bound_campaign(r):
            for year in campaign_years:
                basis.setdefault(f'{year}届', '活动标题写明')
        return _sorted(basis), basis, '', rule
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


def graduation_constraints_of(r, resolved=None):
    """Open-ended eligibility is a bound, never an invented list of future cohorts."""
    resolved = resolved or graduation_of(r)
    rule = resolved[3]
    if rule == 'cohort_raw':text = r.get('cohort_raw') or ''
    elif rule == 'description':text = r.get('description_raw') or ''
    elif rule == 'job_title':text = r.get('job_title') or ''
    elif rule == 'campaign_title':text = campaign_text(r)
    else:return {}
    if job_bound_campaign(r):text += '\n'+campaign_text(r)
    text = expand_short_cohorts(text)
    selected = [x for x in re.split(r'[。\n]', text) if not re.search(r'其中部分|部分.{0,12}岗位|部分境外|其他岗位',x)]
    text = '\n'.join(selected)
    lower = re.findall(r'(20\d{2})\s*届\s*(?:及以后|及之后)',positive_cohort_text(text))
    if not lower:return {}
    excluded = set(); excluded_lower=[]
    for clause in re.findall(r'(?:不接受|不招收|不面向|不含)[^，,；;。\n]*',text):
        excluded.update(years_in(clause))
        excluded_lower.extend(map(int,re.findall(r'(20\d{2})\s*届\s*(?:及以后|及之后)',clause)))
    return {'min_year':min(map(int,lower)), 'max_year':min(excluded_lower)-1 if excluded_lower else None, 'excluded_years':sorted(excluded),
            'basis':'岗位写明' if rule!='campaign_title' else '活动标题写明'}


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
    if "本科" in s or "Bachelor" in s or s in {"本硕", "本硕博"} or re.search(r"本硕(?:博)?[^。；\n]{0,12}(?:毕业|学历|学位|在读)", s):
        return "本科"
    if "硕士" in s or "Master" in s or s == "研究生" or re.search(r"研究生(?:及?以上)?学历", s) or s == "硕博" or re.search(r"硕博[^。；\n]{0,12}(?:毕业|学历|学位|在读)", s):
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


# ---------------------------------------------------------------- 地点：国家 / 州省 / 城市 / 办公方式
#
# One source of truth for every location field (normalize.py persists what location_of returns;
# convert() serves it). Only what the posting states counts: the raw cities/country/state the
# collector saved, curated place knowledge below (Chinese script alone
# is not China), then a trustworthy existing country (see _legacy_country). A remote,
# Global, HQ, customer or travel mention never yields a country, and an unknown place stays
# unknown ("" / 未注明) instead of defaulting to 中国; the old normalizer's known defaults (unknown
# city -> 中国/mainland, 海外) are recognised and not kept.

AREA_CN = re.compile(r"'area_cn':\s*'([^']+)'")
CITY_UNKNOWN = {"", "未披露", "未知", "多地", "不限", "null", "None", "none", "-", "—", "N/A", "n/a", "TBD", "待定"}
NON_CITY = {"Hybrid", "智能制造", "销售"}
CITY_ALIASES = {"中国": ["全国"], "中国大陆": ["全国"], "中国香港": ["香港"], "香港特别行政区": ["香港"],
                "Hongkong": ["香港"], "Shanghai": ["上海"], "SanFrancisco": ["旧金山"], "SanJose": ["圣何塞"],
                "Seattle": ["西雅图"], "London": ["伦敦"], "Paris": ["巴黎"], "NewYork": ["纽约"],
                "NewYorkCity": ["纽约"], "Toronto": ["多伦多"], "Montreal": ["蒙特利尔"], "Clearwater": ["克利尔沃特"],
                "SanFranciscoBayAreaorNewYork": ["旧金山", "纽约"]}
# Every overseas value in the 2026-09-11 data (hand-curated, SPEC 6.8). 远程 is a work mode, not a
# place, and 美国/英国/印尼/埃及/墨西哥 are countries (see _COUNTRY_WORDS), so they are not here.
OVERSEAS_CITIES = {"圣何塞", "新加坡", "西雅图", "迪拜", "利雅得", "东京", "塔吉格", "科威特城", "圣地亚哥", "纽约",
                   "伦敦", "墨西哥城", "首尔", "洛杉矶", "曼谷", "开罗", "圣保罗", "胡志明", "吉隆坡", "古来",
                   "古尔冈", "巴黎", "莫斯科", "约翰内斯堡", "阿拉木图", "海外", "旧金山", "多伦多", "蒙特利尔",
                   "克利尔沃特"}
HMT = ("香港", "澳门", "台湾", "台北", "高雄", "台中", "新竹")
HMT_COUNTRIES = {"香港": "中国香港", "澳门": "中国澳门", "台湾": "中国台湾", "台北": "中国台湾", "高雄": "中国台湾",
                 "台中": "中国台湾", "新竹": "中国台湾"}
REGION_ORDER = ["中国大陆", "港澳台", "海外"]
WORK_MODES = ["远程", "混合", "现场"]

# Country spellings -> one Chinese name. Keys are _ckey() forms (lower case, no spaces/dots/dashes).
_COUNTRY_WORDS = {}
for _name, _spellings in {
    "中国": "china 中国 中国大陆 大陆 中华人民共和国 peoplesrepublicofchina chinasmainland mainlandchina chinamainland",
    "中国香港": "hongkong hongkongsar 中国香港 香港特别行政区",
    "中国澳门": "macau macao 中国澳门",
    "中国台湾": "taiwan 中国台湾 台湾地区",
    "美国": "unitedstatesofamerica unitedstates 美国",
    "英国": "unitedkingdom greatbritain england scotland wales 英国",
    "爱尔兰": "ireland 爱尔兰", "德国": "germany deutschland 德国", "法国": "france 法国",
    "西班牙": "spain 西班牙", "意大利": "italy 意大利", "荷兰": "netherlands thenetherlands 荷兰",
    "比利时": "belgium 比利时", "瑞士": "switzerland 瑞士", "奥地利": "austria 奥地利",
    "捷克": "czechrepublic czechia 捷克", "波兰": "poland 波兰", "罗马尼亚": "romania 罗马尼亚",
    "斯洛伐克": "slovakia 斯洛伐克", "匈牙利": "hungary 匈牙利", "保加利亚": "bulgaria 保加利亚",
    "瑞典": "sweden 瑞典", "丹麦": "denmark 丹麦", "挪威": "norway 挪威", "芬兰": "finland 芬兰",
    "葡萄牙": "portugal 葡萄牙", "希腊": "greece 希腊", "塞浦路斯": "cyprus 塞浦路斯",
    "北马其顿": "northmacedonia 北马其顿", "冰岛": "iceland 冰岛", "俄罗斯": "russia russianfederation 俄罗斯",
    "土耳其": "turkey türkiye turkiye 土耳其", "以色列": "israel 以色列",
    "日本": "japan 日本", "韩国": "southkorea korea republicofkorea 韩国", "新加坡": "singapore 新加坡",
    "马来西亚": "malaysia 马来西亚", "印度": "india 印度", "印度尼西亚": "indonesia 印度尼西亚 印尼",
    "泰国": "thailand 泰国", "越南": "vietnam vietnam 越南", "菲律宾": "philippines 菲律宾",
    "巴基斯坦": "pakistan 巴基斯坦", "孟加拉国": "bangladesh 孟加拉国", "哈萨克斯坦": "kazakhstan 哈萨克斯坦",
    "乌兹别克斯坦": "uzbekistan 乌兹别克斯坦", "澳大利亚": "australia 澳大利亚", "新西兰": "newzealand 新西兰",
    "加拿大": "canada 加拿大", "墨西哥": "mexico 墨西哥", "巴西": "brazil 巴西", "阿根廷": "argentina 阿根廷",
    "智利": "chile 智利", "哥伦比亚": "colombia 哥伦比亚", "秘鲁": "peru 秘鲁",
    "沙特阿拉伯": "saudiarabia ksa 沙特阿拉伯 沙特", "阿联酋": "unitedarabemirates uae 阿联酋",
    "卡塔尔": "qatar 卡塔尔", "科威特": "kuwait 科威特", "埃及": "egypt 埃及", "南非": "southafrica 南非",
    "尼日利亚": "nigeria 尼日利亚", "肯尼亚": "kenya 肯尼亚", "摩洛哥": "morocco 摩洛哥",
}.items():
    for _s in _spellings.split():
        _COUNTRY_WORDS[_s] = _name
# City-states: the one token is both the city and the country.
_CITY_STATES = {"新加坡": ("新加坡", "新加坡"), "singapore": ("Singapore", "新加坡"),
                "香港": ("香港", "中国香港"), "hongkong": ("香港", "中国香港"), "hongkongsar": ("香港", "中国香港"),
                "中国香港": ("香港", "中国香港"), "香港特别行政区": ("香港", "中国香港"),
                "澳门": ("澳门", "中国澳门"), "macau": ("澳门", "中国澳门"), "macao": ("澳门", "中国澳门"),
                "中国澳门": ("澳门", "中国澳门"), "澳门特别行政区": ("澳门", "中国澳门")}
# Mainland city spellings in Latin letters -> the Chinese name (country 中国).
_CN_CITY_EN = {k: v for v, ks in {
    "北京": "beijing peking", "上海": "shanghai", "深圳": "shenzhen", "广州": "guangzhou canton",
    "杭州": "hangzhou", "成都": "chengdu", "武汉": "wuhan", "天津": "tianjin", "南京": "nanjing",
    "西安": "xian xi'an", "苏州": "suzhou", "合肥": "hefei", "重庆": "chongqing", "厦门": "xiamen",
    "大连": "dalian", "青岛": "qingdao", "长沙": "changsha", "郑州": "zhengzhou", "沈阳": "shenyang",
    "济南": "jinan", "宁波": "ningbo", "无锡": "wuxi", "珠海": "zhuhai", "东莞": "dongguan",
    "佛山": "foshan", "惠州": "huizhou", "中山": "zhongshan", "昆山": "kunshan", "常州": "changzhou",
    "福州": "fuzhou", "昆明": "kunming", "哈尔滨": "harbin", "长春": "changchun", "南昌": "nanchang",
    "贵阳": "guiyang", "南宁": "nanning", "太原": "taiyuan", "石家庄": "shijiazhuang", "兰州": "lanzhou",
    "乌鲁木齐": "urumqi", "海口": "haikou", "三亚": "sanya", "榆林": "yulin",
}.items() for k in ks.split()}
_HMT_EN = {"taipei": "台北", "kaohsiung": "高雄", "hsinchu": "新竹", "taichung": "台中"}
# Latin-script Chinese province names: a state, never a city.
_CN_PROVINCES_EN = {"fujian": "福建", "jiangsu": "江苏", "zhejiang": "浙江", "guangdong": "广东", "sichuan": "四川",
                    "hubei": "湖北", "hunan": "湖南", "shandong": "山东", "henan": "河南", "hebei": "河北",
                    "anhui": "安徽", "jiangxi": "江西", "shaanxi": "陕西", "shanxi": "山西", "liaoning": "辽宁",
                    "jilin": "吉林", "heilongjiang": "黑龙江", "yunnan": "云南", "guizhou": "贵州",
                    "guangxi": "广西", "hainan": "海南", "gansu": "甘肃"}
# Chinese-script names of places outside China (country known).
_OVERSEAS_CJK_COUNTRY = {
    "圣何塞": "美国", "西雅图": "美国", "纽约": "美国", "洛杉矶": "美国", "旧金山": "美国", "克利尔沃特": "美国",
    "波士顿": "美国", "芝加哥": "美国", "休斯顿": "美国", "达拉斯": "美国", "奥斯汀": "美国", "硅谷": "美国",
    "圣克拉拉": "美国", "山景城": "美国", "帕洛阿尔托": "美国", "雷德蒙德": "美国", "迈阿密": "美国",
    "新加坡": "新加坡", "迪拜": "阿联酋", "阿布扎比": "阿联酋", "利雅得": "沙特阿拉伯", "吉达": "沙特阿拉伯", "东京": "日本",
    "大阪": "日本", "名古屋": "日本", "横滨": "日本", "塔吉格": "菲律宾", "马尼拉": "菲律宾", "科威特城": "科威特",
    "伦敦": "英国", "曼彻斯特": "英国", "爱丁堡": "英国", "墨西哥城": "墨西哥", "蒙特雷": "墨西哥",
    "瓜达拉哈拉": "墨西哥", "首尔": "韩国", "釜山": "韩国", "曼谷": "泰国", "开罗": "埃及", "圣保罗": "巴西",
    "里约热内卢": "巴西", "胡志明": "越南", "河内": "越南", "吉隆坡": "马来西亚", "古来": "马来西亚",
    "槟城": "马来西亚", "新山": "马来西亚", "古尔冈": "印度", "孟买": "印度", "班加罗尔": "印度",
    "巴黎": "法国", "莫斯科": "俄罗斯", "约翰内斯堡": "南非", "阿拉木图": "哈萨克斯坦", "多伦多": "加拿大",
    "蒙特利尔": "加拿大", "温哥华": "加拿大", "悉尼": "澳大利亚", "墨尔本": "澳大利亚", "慕尼黑": "德国",
    "柏林": "德国", "法兰克福": "德国", "斯图加特": "德国", "阿姆斯特丹": "荷兰", "米兰": "意大利",
    "马德里": "西班牙", "巴塞罗那": "西班牙", "雅加达": "印度尼西亚", "布拉格": "捷克", "华沙": "波兰",
    "布达佩斯": "匈牙利", "苏黎世": "瑞士", "日内瓦": "瑞士", "都柏林": "爱尔兰", "伊斯坦布尔": "土耳其",
    "多哈": "卡塔尔", "塔什干": "乌兹别克斯坦", "布宜诺斯艾利斯": "阿根廷", "比尼亚德尔马": "智利",
}
# No place at all: a scope word, a head-office mention or a region bigger than one country.
_NO_GEO = {"global", "worldwide", "anywhere", "international", "multiplelocations", "variouslocations",
           "various", "hq", "headquarters", "总部", "集团总部", "emea", "apac", "asiapacific", "americas",
           "latam", "europe", "northamerica", "全球", "不限地点", "多个地点"}
_REMOTE_TOKEN = re.compile(r"(?i)remote|远程|居家办公|在家办公|work\s*from\s*home|\bwfh\b")
_HYBRID_TOKEN = re.compile(r"(?i)hybrid|混合办公")
_ONSITE_TOKEN = re.compile(r"(?i)\bon-?site\b|\bin-?office\b|现场办公|坐班")
# Work mode stated in the posting text. Deliberately narrow: "remote sensing", "travel to customer
# sites" or "work with remote teams" are not a work mode.
_MODE_TEXT = [
    ("远程", re.compile(r"(?i)\bthis\s+(?:is\s+an?|role\s+is|position\s+is|job\s+is)\s+(?:fully\s+|100%\s+)?remote\b"
                      r"|\b(?:fully|100%)\s+remote\b|\bremote\s*[-–]\s*first\b|远程办公|远程工作|居家办公")),
    ("混合", re.compile(r"(?i)\bthis\s+(?:is\s+an?|role\s+is|position\s+is|job\s+is)\s+hybrid\b"
                      r"|\bhybrid\s+(?:role|position|work(?:ing)?\s+(?:model|arrangement|schedule))\b|混合办公")),
    ("现场", re.compile(r"(?i)\bthis\s+(?:is\s+an?|role\s+is|position\s+is|job\s+is)\s+(?:fully\s+|100%\s+)?"
                      r"(?:on-?site|in-?office)\b|\bon-?site\s+(?:role|position)\b")),
]
# Domestic place names (mainland provinces, prefecture-level cities, municipalities and a few
# well-known county-level cities). Chinese script alone never means China; only these do.
_CN_PROVINCES = {"北京", "天津", "上海", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽",
                 "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "海南", "四川", "贵州", "云南", "陕西",
                 "甘肃", "青海", "内蒙古", "广西", "西藏", "宁夏", "新疆"}
_CN_PLACES = set("""
北京 天津 上海 重庆 雄安新区 浦东新区
石家庄 唐山 秦皇岛 邯郸 邢台 保定 张家口 承德 沧州 廊坊 衡水
太原 大同 阳泉 长治 晋城 朔州 晋中 运城 忻州 临汾 吕梁
呼和浩特 包头 乌海 赤峰 通辽 鄂尔多斯 呼伦贝尔 巴彦淖尔 乌兰察布 兴安 锡林郭勒 阿拉善
沈阳 大连 鞍山 抚顺 本溪 丹东 锦州 营口 阜新 辽阳 盘锦 铁岭 朝阳 葫芦岛
长春 吉林 四平 辽源 通化 白山 松原 白城 延边
哈尔滨 齐齐哈尔 鸡西 鹤岗 双鸭山 大庆 伊春 佳木斯 七台河 牡丹江 黑河 绥化 大兴安岭
南京 无锡 徐州 常州 苏州 南通 连云港 淮安 盐城 扬州 镇江 泰州 宿迁 昆山 江阴 张家港 常熟 溧阳 宜兴
杭州 宁波 温州 嘉兴 湖州 绍兴 金华 衢州 舟山 台州 丽水 义乌 慈溪 余姚 桐庐 海宁
合肥 芜湖 蚌埠 淮南 马鞍山 淮北 铜陵 安庆 黄山 滁州 阜阳 宿州 六安 亳州 池州 宣城
福州 厦门 莆田 三明 泉州 漳州 南平 龙岩 宁德 晋江 南安 福清
南昌 景德镇 萍乡 九江 新余 鹰潭 赣州 吉安 宜春 抚州 上饶
济南 青岛 淄博 枣庄 东营 烟台 潍坊 济宁 泰安 威海 日照 临沂 德州 聊城 滨州 菏泽
郑州 开封 洛阳 平顶山 安阳 鹤壁 新乡 焦作 濮阳 许昌 漯河 三门峡 南阳 商丘 信阳 周口 驻马店 济源
武汉 黄石 十堰 宜昌 襄阳 鄂州 荆门 孝感 荆州 黄冈 咸宁 随州 恩施 仙桃 潜江 天门
长沙 株洲 湘潭 衡阳 邵阳 岳阳 常德 张家界 益阳 郴州 永州 怀化 娄底 湘西
广州 韶关 深圳 珠海 汕头 佛山 江门 湛江 茂名 肇庆 惠州 梅州 汕尾 河源 阳江 清远 东莞 中山 潮州 揭阳 云浮
南宁 柳州 桂林 梧州 北海 防城港 钦州 贵港 玉林 百色 贺州 河池 来宾 崇左
海口 三亚 三沙 儋州 万宁 五指山 琼海 文昌 东方 乐东 保亭
成都 自贡 攀枝花 泸州 德阳 绵阳 广元 遂宁 内江 乐山 南充 眉山 宜宾 广安 达州 雅安 巴中 资阳 阿坝 甘孜 凉山
贵阳 六盘水 遵义 安顺 毕节 铜仁 黔西南 黔东南 黔南
昆明 曲靖 玉溪 保山 昭通 丽江 普洱 临沧 楚雄 红河 文山 西双版纳 大理 德宏 怒江 迪庆
拉萨 日喀则 昌都 林芝 山南 那曲 阿里
西安 铜川 宝鸡 咸阳 渭南 延安 汉中 榆林 安康 商洛
兰州 嘉峪关 金昌 白银 天水 武威 张掖 平凉 酒泉 庆阳 定西 陇南 临夏 甘南
西宁 海东 海北 黄南 海南州 果洛 玉树 海西
银川 石嘴山 吴忠 固原 中卫
乌鲁木齐 克拉玛依 吐鲁番 哈密 昌吉 博尔塔拉 巴音郭楞 阿克苏 克孜勒苏 喀什 和田 伊犁 塔城 阿勒泰 石河子
""".split()) | _CN_PROVINCES
# Latin-script city names outside China whose country is unambiguous (ambiguous ones such as
# Dublin, Morrisville, Clermont or Middletown are deliberately absent).
_EN_OVERSEAS_CITY = {k: v for v, ks in {
    "美国": "sanfrancisco sanmateo chicago newyork newyorkcity seattle austin dallas denver atlanta losangeles "
            "sanjose mountainview fostercity anchorage boston houston miami sunnyvale santaclara paloalto redmond",
    "英国": "london edinburgh cardiff manchester farnborough maidenhead glasgow",
    "法国": "paris rueilmalmaison lyon", "德国": "berlin munich stuttgart frankfurt essen hamburg",
    "西班牙": "madrid barcelona", "捷克": "prague", "波兰": "warsaw krakow", "罗马尼亚": "bucharest",
    "斯洛伐克": "bratislava", "匈牙利": "budapest", "荷兰": "amsterdam rotterdam", "瑞典": "stockholm",
    "葡萄牙": "lisbon", "北马其顿": "skopje", "意大利": "milan rome", "瑞士": "zurich geneva",
    "日本": "tokyo yokohama yokohamashi chiyodaku osaka nagoya", "韩国": "seoul busan",
    "印度": "bangalore bengaluru mumbai pune hyderabad gurgaon gurugram chennai", "沙特阿拉伯": "riyadh jeddah",
    "阿联酋": "dubai abudhabi", "马来西亚": "kualalumpur petalingjaya penang", "巴西": "saopaulo riodejaneiro indaiatuba",
    "墨西哥": "mexicocity monterrey guadalajara", "加拿大": "toronto markham montreal vancouver",
    "澳大利亚": "sydney", "菲律宾": "manila taguig", "泰国": "bangkok", "印度尼西亚": "jakarta",
    "越南": "hochiminhcity hanoi", "埃及": "cairo", "阿根廷": "buenosaires", "土耳其": "istanbul",
}.items() for k in ks.split()}
# Exact upper-case codes only ("IN"/"CA" as words are never read as India/Canada; CA is ambiguous).
_COUNTRY_CODES = {"US": "美国", "USA": "美国", "UK": "英国", "GB": "英国", "CN": "中国", "PRC": "中国", "JP": "日本",
                  "KR": "韩国", "SG": "新加坡", "FR": "法国", "ES": "西班牙", "IT": "意大利",
                  "NL": "荷兰", "IE": "爱尔兰", "MY": "马来西亚", "TH": "泰国", "VN": "越南",
                  "PH": "菲律宾", "AU": "澳大利亚", "BR": "巴西", "MX": "墨西哥", "AE": "阿联酋", "SA": "沙特阿拉伯",
                  "HK": "中国香港", "TW": "中国台湾", "CH": "瑞士", "CZ": "捷克", "PL": "波兰"}
# DE / IN / MO (and every other US state code) are never read as countries: "Kansas City, MO" is Missouri.
_US_STATES = dict(zip(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH "
    "OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split(),
    ["Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", "Florida",
     "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
     "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska",
     "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
     "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas",
     "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming", "District of Columbia"]))
_US_STATE_NAMES = {_n.replace(" ", "").lower(): _n for _n in _US_STATES.values()}
_CA_PROVINCES = {"ON": "Ontario", "QC": "Quebec", "BC": "British Columbia", "AB": "Alberta", "MB": "Manitoba",
                 "NS": "Nova Scotia", "NB": "New Brunswick", "SK": "Saskatchewan", "NL": "Newfoundland and Labrador"}
# Tokens a generic "state" field may hold that are recruitment statuses, not provinces/states.
_STATE_STATUS = {"open", "opened", "closed", "close", "active", "inactive", "draft", "published", "online",
                 "offline", "true", "false", "yes", "no", "null", "none", "enabled", "disabled", "pending",
                 "招聘中", "已关闭", "已下线", "已发布", "在招", "停招", "有效", "无效", "正常"}
# Negated work-mode statements are removed before the positive patterns run.
_CN_PLACES_LONGEST_FIRST = sorted((p for p in _CN_PLACES if len(p) >= 2), key=len, reverse=True)
_MODE_NEGATION = re.compile(
    r"(?i)\b(?:not|isn['’]t|is\s+not|no|non)[\s-]+(?:an?\s+|a\s+fully\s+|fully\s+|100%\s+)?"
    r"(?:remote|hybrid)(?:\s+(?:position|role|job|work(?:ing)?|opportunity|option|eligible))?\b"
    r"|\bremote\s+work\s+is\s+not\s+(?:available|possible|permitted|offered)\b"
    r"|不(?:支持|接受|提供|可以?|能)\s*(?:远程|居家|混合)(?:办公|工作)?|非远程(?:办公|岗位|工作)?|无法远程(?:办公|工作)?")
_CJK = re.compile(r"[一-鿿]")
_PROVINCE_PREFIX = re.compile(r"^[一-鿿]{2,3}?(?:省|自治区)")


def _ckey(s):
    return re.sub(r"[\s.\-_'’,()（）]", "", str(s or "").replace("﻿", "")).lower()


def country_name(text):
    """A country the text names, as one Chinese name; None when it names no known country.

    Codes count only as exact upper-case tokens (US, CN, UK); "in"/"ca" as words never do.
    """
    t = re.sub(r"[.\s]", "", str(text or ""))
    if t in _COUNTRY_CODES:
        return _COUNTRY_CODES[t]
    return _COUNTRY_WORDS.get(_ckey(text))


def _alias(city):
    key = str(city).replace(" ", "")
    return CITY_ALIASES.get(key, [city])


def clean_city(raw):
    """One raw city token -> the display city, or None when it is no city (placeholder etc.).

    Keeps any real place the source wrote (Morrisville, 翠屏区) instead of discarding what a lookup
    table does not know; only trims the administrative wrapping around it.
    """
    s = re.sub(r"\s+", " ", str(raw or "").replace("﻿", "")).strip().strip(",;，；")
    m = AREA_CN.search(s)
    if m:
        s = m.group(1)
    if not s or s in CITY_UNKNOWN or s in NON_CITY or s.startswith("-") or "area_code" in s:
        return None
    if s in ("全国", "中国", "中国大陆", "全国多地", "全国各省市", "全国各地"):
        return "全国"
    if s in ("海外", "国外", "境外", "海外及其他"):
        return "海外"
    if _CJK.search(s):
        s = re.sub(r"[（(][^）)]*[）)]", "", s).strip()          # 北京（Beijing） -> 北京
        parts = [p for p in re.split(r"[·\-－]", s) if p.strip()]
        if len(parts) > 1 and re.search(r"(?:省|自治区)$", parts[0]):
            parts = parts[1:]                                     # 广东省·深圳市 -> 深圳市
        s = parts[0].strip() if parts else s
        s = _PROVINCE_PREFIX.sub("", s) or s                      # 浙江省杭州市 -> 杭州市
        m = re.match(r"^(.{2,}?)市.+[区县镇]$", s)                  # 杭州市桐庐县 -> 杭州
        if m:
            s = m.group(1)
        if s.endswith("市") and len(s) > 2:
            s = s[:-1]
        for p in _CN_PLACES_LONGEST_FIRST:                        # 北京顺义区 -> 北京
            if len(p) >= 2 and s.startswith(p) and re.fullmatch(r".{0,6}(?:区|县|旗|镇|新区|开发区)", s[len(p):]) \
                    and len(s) > len(p):
                return p
        return s or None
    if s.isupper() and len(s) > 4:
        s = s.title()                                             # SINGAPORE -> Singapore
    return s


_NATIONWIDE = {"全国", "中国", "中国大陆", "全国多地", "全国各省市", "全国各地"}


def _split_one(s, mode):
    """One place text (work-mode words already removed) -> [(country, state, city)]."""
    s = re.sub(r"[（(]\s*[)）]", " ", s).strip(" :|;,/-–")
    if not s or s in CITY_UNKNOWN or _ckey(s) in _NO_GEO:
        return []
    if s in _NATIONWIDE:
        return [("中国", "", "全国")]
    if _ckey(s) in _CITY_STATES:
        city, country = _CITY_STATES[_ckey(s)]
        return [(country, "", city)]
    if country_name(s):
        return [(country_name(s), "", "")]
    if mode:
        # "Remote US", "Remote: India", "Germany (Remote) ; Ireland (Remote)" bound the country;
        # anything else in a remote token (EMEA, "San Mateo area", "CA") names no place we can use.
        parts = [p for p in re.split(r"[:|;,/()（）\-]|\s+", s) if p]
        cities = [_CN_CITY_EN[_ckey(p)] for p in parts if _ckey(p) in _CN_CITY_EN]   # CN-Wuhan-Remote
        bound = [(country_name(p), "", "") for p in parts if country_name(p)]
        if cities:
            return [("中国", "", c) for c in cities]
        if bound:
            return bound
        # "San Francisco Bay Area or New York (Remote)": keep only places we can name for sure.
        key = s.replace(" ", "")
        if key in CITY_ALIASES:
            return [("", "", c) for c in CITY_ALIASES[key]]
        if _ckey(s) in _CN_CITY_EN:
            return [("中国", "", _CN_CITY_EN[_ckey(s)])]
        return []
    # "Sao Paulo - Brazil", "Hong Kong, China", "United States of America - North Carolina - Morrisville"
    parts = [p.strip() for p in re.split(r"\s+[-–]\s+|,\s*", s) if p.strip()]
    us = _us_city_state(parts)
    if us:
        return [us]
    if len(parts) > 1:
        head = _ckey(parts[0])
        if head in _CITY_STATES:
            city, country = _CITY_STATES[head]
            return [(country, "", city)]
        if country_name(parts[0]):
            rest = parts[1:]
            state = rest[0] if len(rest) > 1 else ""
            city = clean_city(" - ".join(rest[1:] if len(rest) > 1 else rest)) or ""
            return [(country_name(parts[0]), state, "" if country_name(city) else city)]
        if country_name(parts[-1]):
            return [(country_name(parts[-1]), " ".join(parts[1:-1]), clean_city(parts[0]) or "")]
    if _ckey(s) in _CN_PROVINCES_EN:
        return [("中国", _CN_PROVINCES_EN[_ckey(s)], "")]
    if len(parts) > 1 and not _CJK.search(s):
        # "Foo, Bar" with no country we know: the first part is the city, the rest may be a state;
        # a comma never stays inside a city (it would split a Feishu multi-select cell).
        city = clean_city(parts[0])
        return [("", _state_value(" ".join(parts[1:])), city)] if city else []
    province = _province_prefix(s)
    city = clean_city(s)
    if not city:
        return [("中国", province, "")] if province else []
    if province:
        return [("中国", province, city)]              # 广东省·深圳市: the stated province is kept
    if _ckey(city) in _CN_CITY_EN:
        return [("中国", "", _CN_CITY_EN[_ckey(city)])]
    if _ckey(city) in _HMT_EN:
        return [("中国台湾", "", _HMT_EN[_ckey(city)])]
    return [("", "", city)]


def _us_city_state(parts):
    """(country, state, city) for "City, ST" only when the country is explicit or already known.

    The country must come from an explicit third part (Austin, TX, USA) or from a city the curated
    tables already place in that country (San Francisco, CA; Toronto, ON). A state code or name
    alone never decides the country: "Kansas City, MO" and "Tbilisi, Georgia" keep their city and
    state, country unknown (see the "Foo, Bar" branch of _split_one).
    """
    if len(parts) not in (2, 3):
        return None
    city = clean_city(parts[0]) or ""
    if len(parts) == 3:
        country = country_name(parts[2])
    else:
        country = _city_country(city) or _city_country(_alias(city)[0])
    code = parts[1].strip()
    if country == "美国":
        state = _US_STATES.get(code) if code.isupper() else _US_STATE_NAMES.get(code.replace(" ", "").lower())
        return ("美国", state, city) if state else None
    if country == "加拿大" and code in _CA_PROVINCES:
        return ("加拿大", _CA_PROVINCES[code], city)
    return None


def state_in_country(state, country):
    """A US state / Canadian province code read in its own country's context (NC -> North Carolina
    only when the country is 美国); anything else unchanged. Never a country: MO here is Missouri."""
    code = str(state or "").strip()
    if country == "美国" and code.upper() in _US_STATES and len(code) == 2:
        return _US_STATES[code.upper()]
    if country == "加拿大" and code.upper() in _CA_PROVINCES and len(code) == 2:
        return _CA_PROVINCES[code.upper()]
    return state


def _province_prefix(s):
    """The province an explicit '…省/自治区' prefix names (广东省·深圳市 -> 广东); '' otherwise."""
    m = re.match(r"^([\u4e00-\u9fff]{2,3}?)(?:省|壮族自治区|回族自治区|维吾尔自治区|自治区)", s.strip())
    return m.group(1) if m and m.group(1) in _CN_PROVINCES and len(s.strip()) > m.end() else ""


def _state_value(raw):
    """A geographic state/province the source named, or '' (status words, numbers, placeholders)."""
    s = re.sub(r"\s+", " ", str(raw or "").replace("﻿", "")).strip(" ,;，；")
    if (not s or s in CITY_UNKNOWN or _ckey(s) in _STATE_STATUS or s.lower() in _STATE_STATUS
            or re.fullmatch(r"[\d\s.\-_/:]+", s) or len(s) > 40):
        return ""
    if _CJK.search(s):
        short = re.sub(r"(?:省|市|壮族自治区|回族自治区|维吾尔自治区|自治区|特别行政区)$", "", s)
        return short or s
    key = _ckey(re.sub(r"(?i)\s*province$", "", s))
    if key in _CN_PROVINCES_EN:
        return _CN_PROVINCES_EN[key]                   # Guangdong / Guangdong Province -> 广东
    return s


def _split_raw(token):
    """One raw location token -> [(country, state, city, work_mode)]; parts may be ''."""
    text = re.sub(r"\s+", " ", str(token or "").replace("﻿", "")).strip()
    out = []
    if text in CITY_UNKNOWN:
        return []
    pieces = [text] if AREA_CN.search(text) else re.split(r"[;；|、/]", text)
    for piece in pieces:
        mode = ""
        piece = _MODE_NEGATION.sub(" ", piece)
        for name, pat in (("远程", _REMOTE_TOKEN), ("混合", _HYBRID_TOKEN), ("现场", _ONSITE_TOKEN)):
            if pat.search(piece):
                mode, piece = name, pat.sub(" ", piece)
                break
        places = _split_one(piece, mode)
        out += [(*p, mode) for p in places] or ([("", "", "", mode)] if mode else [])
    return out


def _domestic(city):
    if city in _CN_PLACES:
        return True
    return any(city.startswith(p) and re.fullmatch(r".{0,6}(?:区|县|旗|镇|新区|开发区)", city[len(p):])
               for p in _CN_PLACES_LONGEST_FIRST if len(city) > len(p))


def _city_country(city):
    """The country a place name alone determines, from curated knowledge only; '' otherwise.

    Chinese script is not evidence of China: 翠屏区 or an unlisted 悉尼-like name stays unknown.
    """
    if not city or city == "海外":
        return ""
    if city == "全国":
        return "中国"
    if city in _OVERSEAS_CJK_COUNTRY:
        return _OVERSEAS_CJK_COUNTRY[city]
    for prefix, country in HMT_COUNTRIES.items():
        if city.startswith(prefix):
            return country
    if _domestic(city):
        return "中国"
    return _EN_OVERSEAS_CITY.get(_ckey(city), "")


def _region(country, city):
    if country == "中国":
        return "港澳台" if city.startswith(HMT) else "中国大陆"
    if country in ("中国香港", "中国澳门", "中国台湾"):
        return "港澳台"
    if country:
        return "海外"
    if city in OVERSEAS_CITIES:
        return "海外"
    return ""


def _raw_tokens(r):
    raw = r.get("cities")
    raw = [raw] if isinstance(raw, str) else (raw or [])
    tokens = [t for t in raw if isinstance(t, str) and t.strip()]
    if not tokens:
        for field in ("location", "city"):
            if isinstance(r.get(field), str) and r[field].strip():
                tokens = [r[field]]
                break
    return tokens


def _triples(r):
    """Structured (country, state, city) triples the collector saved from the source page."""
    return [x for x in r.get("locations_raw") or [] if isinstance(x, dict)], "source"


def _legacy_country(r):
    """An existing country value worth keeping, or ''.

    Values this module wrote carry country_basis and are recomputed, except ones kept as legacy.
    Older values have no provenance and are kept as legacy (uncertain; served with that basis)
    unless source fields or place knowledge say otherwise. Not kept: 海外 (a region, not a country)
    and the old normalizer's demonstrable default -- 中国 when its own city_normalized/
    cities_normalized was ""/未披露/未知 (callers only reach this without raw source country). Correcting a wrong old value needs actual source fields (a new collection or a
    scoped migration that saves them), never a special case here.
    """
    v = str(r.get("country") or "").strip()
    if not v or "、" in v:
        return ""
    if "country_basis" in r:
        return country_name(v) or "" if r.get("country_basis") == ["legacy"] else ""
    if v in ("海外", "overseas") or not country_name(v):
        return ""
    names = r.get("cities_normalized")
    names = [*(names if isinstance(names, list) else [names]), r.get("city_normalized")]
    if country_name(v) == "中国" and not any(str(n or "").strip() not in ("", "未披露", "未知") for n in names):
        # The old normalizer's own default (city ""/未披露/未知 -> 中国), not something a source said.
        return ""
    return country_name(v)


def has_raw_location(r):
    """Whether the record carries any source-stated place (placeholders/status words do not count)."""
    triples, _ = _triples(r)
    if any(str(x.get("country") or "").strip() or _state_value(x.get("state")) or str(x.get("city") or "").strip()
           for x in triples):
        return True
    if str(r.get("location_country_raw") or r.get("country_raw") or "").strip():
        return True
    if _state_value(r.get("location_state_raw") or r.get("province_raw")):
        return True
    return any(any(x[:3]) for t in _raw_tokens(r) for x in _split_raw(t))


def location_of(r):
    """Every location field of one record.

    Evidence order: structured source fields (locations_raw, location/country/state raw, tokens that
    name a country) > curated place knowledge > a trustworthy existing
    country (see _legacy_country) > unknown. A country is attached to a city only when it belongs to
    that city (the city's own triple, or the job's single city); one country is never spread over
    several cities. Returns {"locations": [{"country", "state", "city"}], "country_basis": [...]
    aligned with "countries", "cities", "countries", "states", "region", "work_modes"}.
    """
    locs, modes = [], []

    def add(country, state, city, basis):
        country = country or ""
        state = _state_value(state)
        for c in (_alias(city) if city else [""]):
            if c in CITY_UNKNOWN - {""} or c in NON_CITY:
                c = ""
            b = basis if country else ""
            if not country:
                country = _city_country(c) or (_city_country(state) if not c else "")
                b = "place" if country else ""
            state = state_in_country(state, country)         # source-typed "NC" + 美国 -> North Carolina
            if not (country or state or c):
                continue
            item = {"country": country, "state": state, "city": c, "basis": b}
            if not any(l["country"] == country and l["state"] == state and l["city"] == c for l in locs):
                locs.append(item)

    triples, tbasis = _triples(r)
    for x in triples:
        cc = str(x.get("country") or "").strip()
        country = country_name(cc) or cc
        parsed = _split_raw(x.get("city") or "") or [("", "", "", "")]
        for country_t, _, city, mode in parsed:
            if mode:
                modes.append(mode)
            add(country or country_t, x.get("state"), city, tbasis)

    tokens = _raw_tokens(r)
    if not tokens and not locs:
        tokens = [c for c in (r.get("cities_normalized") or []) if isinstance(c, str)]
    parsed = [x for t in tokens for x in _split_raw(t)]
    modes += [p[3] for p in parsed if p[3]]
    if locs:
        parsed = []                             # the triples already tie each city to its place
    bare, city_rows = [], []                    # bare: country-only tokens such as ["Shanghai", "China"]
    for country, state, city, _ in parsed:
        if city or (state and not country):
            city_rows.append([country, state, city])
        elif country and (country, state) not in bare:
            bare.append((country, state))
    src_country = str(r.get("location_country_raw") or r.get("country_raw") or "").strip()
    src_country = country_name(src_country) or src_country
    src_state = _state_value(r.get("location_state_raw") or r.get("province_raw") or r.get("state"))
    if not src_country and len(bare) == 1 and len(city_rows) == 1:
        src_country, src_state = bare[0][0], src_state or bare[0][1]
        bare = []
    one = len(city_rows) == 1
    for row in city_rows:
        country = row[0] or (src_country if one and not (row[2] and _city_country(row[2])
                                                          and _city_country(row[2]) != src_country) else "")
        state = row[1] or (src_state if one else "")
        known = _city_country(row[2]) or ("中国" if _ckey(row[2]) in _CN_CITY_EN else "")
        from_field = not row[0] and bool(country)            # the record-level country field
        add(country, state, row[2], "place" if country == known and not from_field else "source")
    if not triples:                             # structured triples replace record-level fields
        for country, state in ([(src_country, src_state if not city_rows else "")] if src_country else []) + bare:
            if not any(l["country"] == country for l in locs):
                add(country, state, "", "source")   # stated, but not tied to one of several cities
        if not locs and src_state:
            add("", src_state, "", "source")        # state-only record
    legacy = _legacy_country(r)
    if legacy and not any(l["country"] for l in locs):
        if len(locs) == 1:
            locs[0]["country"], locs[0]["basis"] = legacy, "legacy"
        else:
            add(legacy, "", "", "legacy")           # kept, but never assigned to one of several cities

    text = _MODE_NEGATION.sub(" ", str(r.get("work_mode_raw") or ""))
    for mode, pat in (("远程", _REMOTE_TOKEN), ("混合", _HYBRID_TOKEN), ("现场", _ONSITE_TOKEN)):
        if text.strip() and pat.search(text):
            modes.append(mode)
    desc = _MODE_NEGATION.sub(" ", str(r.get("description_raw") or ""))
    for mode, pat in _MODE_TEXT:
        if pat.search(desc):
            modes.append(mode)

    def uniq(values):
        return [v for i, v in enumerate(values) if v and v not in values[:i]]

    countries = uniq([l["country"] for l in locs])
    regions = {_region(l["country"], l["city"]) for l in locs}
    return {
        "locations": [{k: l[k] for k in ("country", "state", "city")} for l in locs],
        "location_basis": [l["basis"] for l in locs],
        "country_basis": [next(l["basis"] for l in locs if l["country"] == c) for c in countries],
        "cities": uniq([l["city"] for l in locs]),
        "countries": countries,
        "states": uniq([l["state"] for l in locs]),
        "region": "、".join(g for g in REGION_ORDER if g in regions),
        "work_modes": [m for m in WORK_MODES if m in modes],
    }


def cities_of(r):
    return location_of(r)["cities"]


def is_country_only(q):
    """A query word that names a country rather than a city (美国, USA); 新加坡/香港 are both."""
    return bool(country_name(q)) and _ckey(q) not in _CITY_STATES and q not in ("中国", "中国大陆", "全国")


def city_region(c):
    """Region of a city name alone (used for query cities); '' when the name does not tell."""
    if c in OVERSEAS_CITIES or c in _OVERSEAS_CJK_COUNTRY:
        return "海外"
    if c.startswith(HMT):
        return "港澳台"
    country = "中国" if _ckey(c) in _CN_CITY_EN else _city_country(c)
    return _region(country, c) if country else ""


OVERSEAS_REGION = {"overseas", "海外"}


def region_of(r, cities=None):
    """中国大陆/港澳台/海外 joined in that order; '' when nothing states where the job is."""
    return location_of(r)["region"]


def norm_city(q):
    q = q.strip()
    q = q[:-1] if q.endswith("市") and len(q) > 2 else q
    alias = CITY_ALIASES.get(q.replace(" ", ""))
    if alias:
        return alias[0]
    return _CN_CITY_EN.get(_ckey(q), q)

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
    loc = location_of(r)
    cities = loc["cities"]
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
        "region": loc["region"],
        "country": "、".join(loc["countries"]),
        "country_basis": loc["country_basis"] if "legacy" in loc["country_basis"] else [],
        "state": "、".join(loc["states"]),
        "work_mode": "、".join(loc["work_modes"]),
        # Which city belongs to which country/state; only worth sending when there are several.
        "locations": loc["locations"] if len(loc["locations"]) > 1 else [],
        # Every (country, state, city) triple for paired filtering; tools.public() never sends it.
        "_locs": [dict(l, basis=b) for l, b in zip(loc["locations"], loc["location_basis"])],
        "graduation_years": years,
        "graduation_year_basis": basis,
        "graduation_year_note": note,
        "graduation_year_conflicts": graduation_conflicts_of(r, (years, basis, note, grad_rule)),
        "graduation_year_constraints": graduation_constraints_of(r, (years, basis, note, grad_rule)),
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
        "source_is_active": r.get("source_is_active"),
        "source_status_raw": r.get("source_status_raw"),
        "published_at": date_of(r.get("published_at")),
        "job_code": _text(r.get("job_code") or r.get("position_code")),
        "description_raw": _text(r.get("description_raw")),
        "index_only": r.get("index_only"),
        "pending_reason": r.get("pending_reason"),
        "pending_note": r.get("pending_note"),
        "detail_request_status": r.get("detail_request_status"),
        "last_attempt_at": r.get("last_attempt_at"),
        "application_url": _text(r.get("application_url")),
        "application_link_type": _text(r.get("application_link_type")),
        "application_instructions": _text(r.get("application_instructions")),
        "detail_presentation": _text(r.get("detail_presentation")),
        "source_missing_fields": r.get("source_missing_fields") or [],
        "field_completeness": r.get("field_completeness") or {},
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
    if not it["region"]:
        report["region_unknown"] += 1
    if not it.get("country"):
        report["country_unknown"] += 1
    if it.get("work_mode"):
        report[f"work_mode:{it['work_mode']}"] += 1
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
             "graduation_year": {f"{year}届" for year in VALID_YEARS}}
    problems = []
    for name, allowed in enums.items():
        extra = sorted(present[name] - allowed)
        unused = sorted(allowed - present[name])
        if extra:
            problems.append(f"{name}: 数据里有、枚举里没有 {extra}（这些岗位用该条件查不到）")
        if unused and name != "graduation_year":
            problems.append(f"{name}: 枚举里有、数据里没有 {unused}（选了必然 0 条）")
    return {"present": {k: sorted(v) for k, v in present.items()}, "problems": problems}


_WS = re.compile(r"[\s,]*")
CHUNK_BYTES = 4 << 20


def iter_json_file(path, chunk_bytes=CHUNK_BYTES, strict=False):
    """Yield the elements of a file holding one top-level JSON array, one element at a time.

    Same C scanner as json.loads, but the file is decoded in chunks and only one raw record is
    alive at a time: reading the 81 MB jobs.json whole costs ~570 MB of Python heap at the peak
    (bytes + a UCS-4 str + the decode buffer), this costs one chunk plus the converted records.
    """
    decoder = json.JSONDecoder()
    whitespace = re.compile(r"[ \t\n\r]*") if strict else _WS
    expect_separator = False
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
            pos = whitespace.match(buf, pos).end()
            while pos >= len(buf) and more():
                pos = whitespace.match(buf, pos).end()

        skip()
        if buf[pos:pos + 1] != "[":
            raise ValueError("岗位库格式异常，请稍后重试")
        pos += 1
        while True:
            skip()
            if pos >= len(buf):
                raise ValueError("岗位库格式异常：文件不完整")
            if strict and expect_separator and buf[pos] != "]":
                if buf[pos] != ",":raise ValueError("岗位库格式异常：元素之间缺少逗号")
                pos += 1
                skip()
                if pos >= len(buf) or buf[pos] == "]":raise ValueError("岗位库格式异常：尾随逗号")
                expect_separator = False
            if buf[pos] == "]":
                pos += 1
                while True:
                    if (whitespace.match(buf, pos).end() != len(buf)) if strict else bool(buf[pos:].strip()):
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
            expect_separator = True
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
