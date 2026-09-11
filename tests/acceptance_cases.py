"""SPEC section 8 acceptance questions as tool calls, plus four that cover the inferred tier.

Shared by tests/test_v4_tools.py (HTTP result == in-process result) and
research/qiuzhao-v4-impl/scripts/acceptance_v4.py (reference numbers for the receipt).
An ids value of ("Q01", [1]) means: the ids of jobs[1] in Q01's first result.
"""

CASES = {
    "Q01": ("我是27届计算机专业硕士，想留杭州，有哪些岗位能投？",
            [("jobs_search", {"city": "杭州", "graduation_year": "2027届", "major": "计算机类", "education": "硕士"})]),
    "Q02": ("字节现在有哪些产品经理岗位？主要在哪些城市？",
            [("jobs_search", {"company": "字节跳动", "job_category": "产品"}),
             ("jobs_stats", {"company": "字节跳动", "job_category": "产品", "group_by": "city", "top": 5})]),
    "Q03": ("接下来一周要截止的校招有哪些？按截止时间排",
            [("jobs_search", {"recruitment_type": "校园招聘", "deadline_within_days": 7, "sort": "deadline_asc"})]),
    "Q04": ("北京有没有不限专业的国企岗位？",
            [("jobs_search", {"city": "北京", "industry": "国企/央企", "major": "不限"})]),
    "Q05": ("第 2 个岗位的具体要求是什么？投递链接给我", [("jobs_detail", {"ids": ("Q01", [1])})]),
    "Q06": ("上海有能转正的实习吗？",
            [("jobs_search", {"recruitment_type": "实习招聘", "city": "上海", "keyword": "转正"})]),
    "Q07": ("我 2026 年毕业还没找到工作，还能投哪些央企？",
            [("jobs_search", {"graduation_year": "2026届", "industry": "国企/央企"})]),
    "Q08": ("国庆前截止的产品岗有哪些？",
            [("jobs_search", {"job_category": "产品", "deadline_within_days": 19, "sort": "deadline_asc"})]),
    "Q09": ("腾讯和阿里在深圳招算法吗？",
            [("jobs_search", {"company": "腾讯,阿里巴巴", "city": "深圳", "keyword": "算法"})]),
    "Q10": ("北京和上海，哪边的 27 届产品岗更多？",
            [("jobs_stats", {"job_category": "产品", "graduation_year": "2027届", "group_by": "city", "top": 10})]),
    "Q11": ("今年校招哪些行业招得最多？给我前五",
            [("jobs_stats", {"recruitment_type": "校园招聘", "group_by": "industry", "top": 5})]),
    "Q12": ("哪几家国企招计算机专业最多？",
            [("jobs_stats", {"industry": "国企/央企", "major": "计算机类", "group_by": "company", "top": 5})]),
    "Q13": ("本科和硕士能投的岗位差多少？",
            [("jobs_stats", {"education": "本科"}), ("jobs_stats", {"education": "硕士"}),
             ("jobs_stats", {"group_by": "education"})]),
    "Q14": ("为什么很多岗位没写专业要求？这些我能投吗？",
            [("jobs_stats", {"major": "计算机类"}), ("jobs_stats", {"group_by": "major_category", "top": 13})]),
    "Q15": ("帮我排一下未来两周上海技术岗的投递计划",
            [("jobs_search", {"city": "上海", "job_category": "技术/研发", "deadline_within_days": 14,
                              "sort": "deadline_asc", "page_size": 20})]),
    "Q16": ("对比一下这两个岗位，哪个更适合学统计的我？", [("jobs_detail", {"ids": ("Q01", [0, 1])})]),
    "Q17": ("你们的数据是什么时候的？一共有多少家公司？", [("jobs_stats", {"group_by": "company", "top": 1})]),
    "Q18": ("字节的岗位主要在哪些城市？技术和非技术各多少？",
            [("jobs_stats", {"company": "字节跳动", "group_by": "city", "top": 5}),
             ("jobs_stats", {"company": "字节跳动", "group_by": "job_category"})]),
    "Q19": ("有新加坡或者海外的岗位吗？",
            [("jobs_search", {"city": "新加坡"}), ("jobs_stats", {"group_by": "city", "top": 100})]),
    "Q20": ("我只想看明确写了招 27 届的，没写届别的不要",
            [("jobs_search", {"graduation_year": "2027届", "explicit_only": True})]),
    # v4 additions: the inferred tier (按招聘季推断 / 来源专场注明 / 实习未写届别) and 社招不限届别.
    "Q21": ("我是 27 届，腾讯现在有哪些岗位？",
            [("jobs_search", {"company": "腾讯", "graduation_year": "2027届"})]),
    "Q22": ("有哪些 27 届能投的实习？",
            [("jobs_search", {"recruitment_type": "实习招聘", "graduation_year": "2027届"})]),
    "Q23": ("社招里有 27 届也能投的吗？",
            [("jobs_search", {"recruitment_type": "社会招聘", "graduation_year": "2027届"})]),
    "Q24": ("27 届和 26 届各有多少岗位？没写届别的有多少？",
            [("jobs_stats", {"group_by": "graduation_year"}),
             ("jobs_stats", {"graduation_year": "2027届"}), ("jobs_stats", {"graduation_year": "2026届"})]),
}


def resolve(args, first_results):
    """Replace ("Q01", [i, ...]) placeholders with ids from an earlier search result."""
    out = dict(args)
    for key, value in args.items():
        if isinstance(value, tuple):
            qid, idx = value
            out[key] = ",".join(first_results[qid]["jobs"][i]["id"] for i in idx)
    return out
