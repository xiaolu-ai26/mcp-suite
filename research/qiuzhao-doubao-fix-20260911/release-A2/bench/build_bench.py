"""Merge three owned research batches into one product dataset.

Runs offline only: reads local files plus previously exported Feishu records.
Never fetches remote content. Output is an explicit allowlist of fields, so a new
column in a source file can never leak note bodies, transcripts or exact metrics.

Usage (needs openpyxl; the project venv does not have it):
    python3 bench/build_bench.py [--out bench/data/bench.json]
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "bench" / "sources"
CLEAN_XLSX = Path.home() / "Projects/AI自媒体/04_对标参考/低粉爆款研究_2026-06/xhs_ai_low_follower_viral_clean.xlsx"
CST = timezone(timedelta(hours=8))

# ---------------------------------------------------------------- taxonomies
TOPIC_CATEGORIES = ["AI工具", "AI绘画", "AI视频", "AI写作", "AI教程", "AI变现",
                    "AI自媒体起号", "AI自动化", "AI办公", "AI资料", "AI副业", "其他"]
CONTENT_ANGLES = ["教程型", "资源型", "清单型", "结果展示型", "案例型", "赚钱型",
                  "对比型", "挑战型", "工具测评型", "踩坑型"]
# Seven formulas distilled in 爆款标题模式库.md plus four patterns that recur in the
# 319-record free-text column; everything is normalised into this closed set.
TITLE_FORMULAS = ["提问求助式", "数字清单+必备感", "去AI味/反识别", "反焦虑真诚搞钱",
                  "身份代入从0打卡", "官方权威+极简", "资源白给+紧迫", "对比选型",
                  "保姆级教程承诺", "反差结果展示", "悬念猎奇/情绪吐槽", "反共识劝阻式",
                  "工具组合搭配", "系列连载/日更", "热点借势+榜单", "未归类"]
# Judging a cover layout needs the cover image, which this product neither stores
# nor fetches. The vocabulary is published; coverage is honestly reported as 0.
COVER_HOOKS = ["标题大字型", "对比前后型", "清单卡片型", "真人出镜型",
               "界面截图型", "手写笔记型", "未标注"]
FOLLOWER_BANDS = ["0-1k", "1k-5k", "5k-1w", "1w-3w", "3w-5w", "5w-10w", "10w+", "unknown"]
BREAKOUT_LEVELS = ["现象级", "强", "中", "观察", "未分级"]
NOTE_TYPES = ["图文", "视频"]

FIELDS = ["id", "url", "platform", "note_type", "title", "published_at", "topic_category",
          "content_angle", "title_formula", "title_hook", "cover_hook", "opening_hook",
          "pain_point", "promised_result", "target_audience", "monetization_hint",
          "follower_band", "breakout_level", "replicability_score", "remake_value_score",
          "fit_score", "takeaway", "keyword_source", "hashtags", "observed_at",
          "source_batch", "tagging"]

# Keyword -> title formula. First match wins, so order encodes precedence.
# Applied to the study's own free-text formula description first, then to the title.
FORMULA_RULES = [
    ("去AI味/反识别", r"ai\s*味|一眼假|反识别|去味|降ai|识别不出|像人写|反ai"),
    ("反共识劝阻式", r"别再|别在|别搞|不要再|伪需求|反装懂|反共识|打脸|劝阻|大胆抄|自我感动"),
    ("对比选型", r"vs|对比|横评|怎么选|哪个好|区别|pk|谁更|选型|收敛筛选|只剩|只留下|排行|盘点"),
    ("工具组合搭配", r"工具组合|组合等式|全家桶|工具搭配|配置展示|setup|矩阵.*玩法"),
    ("系列连载/日更", r"第\s*\d+\s*[集期]|日更|一天一个|每天一个|连载|依旧是|系列|进阶版|更新版|上下篇|（上）|\(上\)"),
    ("热点借势+榜单", r"本周爆火|爆火项目|排行榜|榜单|新规|封杀|政策|节日|安康|端午|风口|上线了|新功能|发布会|时效"),
    ("提问求助式", r"[?？]|求推荐|求助|求指点|求大神|求教|请教|有没有|到底怎么|怎么办|吗$|征集|提问|求分享|钓评论|互动"),
    ("反焦虑真诚搞钱", r"赚钱|变现|搞钱|挣钱|收入|智商税|副业|月入|割韭菜|多少钱|高薪|接单|焦虑|危机|被替代|抵.*员工|暴利|单月|年赚|商单|机会"),
    ("资源白给+紧迫", r"免费|白给|附.|领取|吐血整理|无偿|限时|资料|合集|打包|开源|白嫖|提示词|指令|模板|skill|私藏|干货|指南|宝库|速进|手册"),
    ("数字清单+必备感", r"\d+\s*[个种张条款类招]|必装|必备|清单|最该|神器.*\d|\d+\s*大"),
    ("身份代入从0打卡", r"零基础|0基础|从0|从零|小白|day\s*\d|第\d+天|新手|文科生|普通人|身份代入|职业身份|养成系|一人公司|人人都是|挑战|逼自己|精通"),
    ("保姆级教程承诺", r"保姆级|手把手|教程|入门|上手|速通|分钟|步走|三步|完整流程|全流程|如何|怎么做|方法论|讲透|搞定|分步|隐藏功能|教你|学习法|实操"),
    ("官方权威+极简", r"官方|大厂|吴恩达|大神|一图|一张图|一条|极简|底层逻辑|原理|核心概念|通俗易懂|大白话|黑话|权威|背书|一文|建议"),
    ("反差结果展示", r"我用|我把|我发现|当我|第一次|终于|居然|竟然|没想到|真实感想|实测|亲测|翻车|不行|太强|惊艳|以假乱真|夯爆|惊呆|封神|震撼|最强|绝了|悟了|才知道|醒悟|反差|效果|成果|干掉|做出|生成|短片|大片|成片|复盘|自研|宣告|4k|太.{0,3}啦"),
    ("悬念猎奇/情绪吐槽", r"到底|好玩|有意思|社死|吐槽|🤣|😂|猫|狗|萌宠|拟人|壁纸|角色|整活|出圈|猎奇|情绪|梗|悬念|be like|苦.*久已|抽象|意境|诗意|留白"),
]
ANGLE_RULES = [
    ("对比型", r"vs|对比|横评|怎么选|哪个好|区别|pk"),
    ("赚钱型", r"赚钱|变现|搞钱|挣钱|收入|月入|副业|多少钱"),
    ("踩坑型", r"翻车|不行|踩坑|避坑|别再|失败|问题|报错|吐槽"),
    ("清单型", r"^\d+\s*[个种张条款]|\d+\s*[个种张条款]|清单|必装|必备|排行"),
    ("资源型", r"免费|附|领取|资料|合集|打包|白给|开源|模板|提示词"),
    ("工具测评型", r"实测|体验|测评|试了|用了.*天"),
    ("案例型", r"我用|我把|记录|day\s*\d|第\d+天|复盘|经历"),
    ("教程型", r"教程|入门|上手|怎么|如何|步|指南|方法|技巧|速通|搭建"),
    ("结果展示型", r"效果|成品|做了|生成|出图|作品"),
]
TOPIC_BY_KEYWORD = {
    "Codex": "AI工具", "Claude Code": "AI工具", "Agent": "AI工具", "AI工具": "AI工具",
    "AI办公": "AI办公", "AI自动化": "AI自动化", "AI写作": "AI写作",
    "AI提示词": "AI资料", "AI赚钱": "AI变现", "AI副业": "AI副业",
    "AI小红书": "AI自媒体起号", "AI自媒体": "AI自媒体起号", "AI起号": "AI自媒体起号",
    "AI做账号": "AI自媒体起号", "AI矩阵": "AI自媒体起号", "AI图文": "AI自媒体起号",
    "AI资料号": "AI资料", "AI变现": "AI变现", "AI视频": "AI视频",
    "AI短视频": "AI视频", "AI数字人": "AI视频", "AI绘画": "AI绘画", "AI教程": "AI教程",
}
TOPIC_TITLE_RULES = [
    ("AI绘画", r"绘画|出图|midjourney|画图|图片|摄影|头像|风格图"),
    ("AI视频", r"视频|剪辑|漫剧|数字人|口播|短片|运镜"),
    ("AI变现", r"赚钱|变现|搞钱|挣钱|月入|收入|接单|卖"),
    ("AI自媒体起号", r"小红书|起号|涨粉|账号|笔记|爆款|流量"),
    ("AI办公", r"办公|excel|ppt|表格|公文|材料|汇报|周报|会议"),
    ("AI写作", r"写作|写稿|文案|论文|小说|文章|润色"),
    ("AI自动化", r"自动化|工作流|定时|批量|流水线|自动"),
    ("AI资料", r"提示词|prompt|资料|合集|模板|清单|指令"),
    ("AI教程", r"教程|入门|上手|零基础|保姆级|速通|指南"),
]
MONETIZATION = {"none": "none", "引流": "引流社群", "引流社群": "引流社群", "卖资料": "卖资料",
                "卖课": "卖课", "接单": "接单", "卖工具": "卖工具", "咨询": "咨询",
                "带货": "带货", "社群": "引流社群"}


def blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or str(value).strip().lower() in {"nan", "none", "null"}


# Product-facing copy must not read as a data-harvesting service. Quoted original
# titles are data and stay verbatim; every derived string goes through this.
BANNED_COPY = [("小红书数据", "小红书运营"), ("数据抓取", "数据归集"), ("爬虫", "自动化脚本"),
               ("爬取", "汇总"), ("抓取", "读取"), ("采集", "归集")]


# The red line is "links + our own labels and conclusions, never a body text and never
# an exact engagement number". Field-level that was already true, but the free-text
# `takeaway` column inherited exact counts from the 2026-06 study notes and from the AI
# tagging pass. Each rewrite below keeps the judgement and drops only the number, so the
# conclusion a buyer pays for survives. Curated one by one on purpose: a generic regex
# would either mangle the sentence or quietly swallow a real violation.
# Numbers that describe the *content* of someone's note (「100条指令」「50页报告」,
# a claimed income like 「单月广告商单10万」) are not platform engagement and stay.
METRIC_SCRUB = [
    # ---- 收藏 counts
    ("收藏8615极高", "收藏量极高"),
    ("收藏7189爆表", "收藏爆表"),
    ("6334收藏证明", "高收藏证明"),
    ("收藏4114远超点赞", "收藏远超点赞"),
    ("收藏3848高", "收藏高"),
    ("收藏2504高", "收藏高"),
    ("收藏2161证明诱饵强", "高收藏证明诱饵强"),
    ("2302收藏", "高收藏"),
    ("收藏1732适合保存", "高收藏适合保存"),
    ("收藏1570求方案心智强", "高收藏求方案心智强"),
    ("1567收藏>856赞", "收藏远超点赞"),
    ("收藏1224说明刚需", "高收藏说明刚需"),
    ("收藏1127高", "收藏高"),
    ("1471收藏说明强保存欲", "高收藏说明强保存欲"),
    ("376收藏", "收藏可观"),
    ("656收藏", "收藏可观"),
    ("超高收藏(16112)", "超高收藏"),
    ("超高收藏(2104)", "超高收藏"),
    ("高收藏(2798)", "高收藏"),
    ("高收藏(1446)", "高收藏"),
    ("收藏拉满(2152)", "收藏拉满"),
    ("收藏近6000即抄即用刚需", "收藏极高即抄即用刚需"),
    ("收藏破5700属可白嫖资源", "收藏极高属可白嫖资源"),
    # ---- 收藏 counts written in 万/w
    ("12万收藏", "超高收藏"),
    ("4.4万收藏", "超高收藏"),
    ("3.3万收藏", "超高收藏"),
    ("3.8w高收藏", "超高收藏"),
    ("1.6万高收藏", "超高收藏"),
    ("超2万收藏证明", "超高收藏证明"),
    ("高收藏(2w收藏)", "高收藏"),
    ("超高收藏(28w)", "超高收藏"),
    ("收藏破1.6万", "收藏极高"),
    ("收藏破1.4w炸裂", "收藏炸裂"),
    ("收藏近2w", "收藏极高"),
    ("收藏1.8w", "收藏极高"),
    # ---- 点赞 counts
    ("8074赞远超293粉", "赞数远超粉丝量"),
    ("低粉破1500赞", "低粉高赞破圈"),
    ("2929赞", "高赞"),
    ("563赞稳健", "赞数稳健"),
    ("天然收藏属性(3415赞)", "天然收藏属性(高赞)"),
    ("1457赞2311藏", "高赞高藏"),
    ("争议性引互动, 139赞", "争议性引互动, 互动量一般"),
    ("情绪共鸣, 505赞", "情绪共鸣, 互动中等"),
    ("222赞中等", "互动中等"),
    ("但233赞偏弱", "但互动偏弱"),
    ("互动低(29赞)", "互动低"),
    ("仅57赞非爆款", "互动低非爆款"),
    ("仅51赞非真爆款", "互动低非真爆款"),
    ("59赞非爆款", "互动低非爆款"),
    ("56赞非爆款", "互动低非爆款"),
    ("实际仅26赞未真爆", "实际互动低未真爆"),
    ("没爆(12赞)", "没爆(互动低)"),
    ("没爆(11赞)", "没爆(互动低)"),
    ("没爆(9赞)", "没爆(互动低)"),
    ("没爆(7赞)", "没爆(互动低)"),
    ("没爆(6赞)", "没爆(互动低)"),
    ("没爆(5赞)", "没爆(互动低)"),
    # ---- 点赞 counts written in 万/w
    ("40w赞核弹级", "点赞核弹级"),
    ("3.5万赞靠的是娱乐爆点", "高赞靠的是娱乐爆点"),
    ("1.4万赞神帖", "高赞神帖"),
    ("易上手高赞(2.4万)", "易上手高赞"),
    ("巨量互动(11.8万赞)", "巨量互动"),
    ("带来4w赞", "带来高赞"),
    ("4.4w赞", "高赞"),
    ("2.4w赞爆款", "高赞爆款"),
    ("点赞破1.7w纯流量爆款", "点赞极高纯流量爆款"),
    ("前作10w验证", "前作爆款验证"),
    ("2万+双高数据", "双高数据"),
    # ---- 赞 + 藏 in one breath
    ("1.9w赞3.9w藏是本批最强爆款", "高赞高藏是本批最强爆款"),
    ("1.4w赞1.9w藏说明", "高赞高藏说明"),
    ("2w赞2.4w收藏", "高赞高收藏"),
    # ---- 粉丝 counts
    ("涨粉8W结果背书", "涨粉结果背书"),
    # title_hook is our own one-line label for the hook, not the quoted original title,
    # so the follower count in it is ours to drop. The原标题 itself stays verbatim.
    ("涨粉8W", "涨粉成果背书"),
]


def sanitize(value: str) -> str:
    for bad, good in BANNED_COPY:
        value = value.replace(bad, good)
    for exact, qualitative in METRIC_SCRUB:
        value = value.replace(exact, qualitative)
    return value


def text(value, cap: int = 300) -> str:
    if blank(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()[:cap]


def iso_date(value) -> str:
    """Only convert timestamps we can actually verify; never guess a publish date."""
    if blank(value):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    raw = str(value).strip()
    if re.fullmatch(r"\d{12,14}", raw):
        return datetime.fromtimestamp(int(raw) / 1000, CST).date().isoformat()
    if re.fullmatch(r"\d{9,11}", raw):
        return datetime.fromtimestamp(int(raw), CST).date().isoformat()
    match = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", raw)
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else ""


def first_match(rules, haystack, default=""):
    low = haystack.lower()
    for label, pattern in rules:
        if re.search(pattern, low):
            return label
    return default


def formula_of(description: str, title: str) -> str:
    """The study's own formula wording is the better signal; the title is the fallback."""
    return first_match(FORMULA_RULES, description) or first_match(FORMULA_RULES, title, "未归类")


def follower_band(count) -> str:
    if count is None or not isinstance(count, (int, float)):
        return ""
    n = int(count)
    for edge, label in ((1000, "0-1k"), (5000, "1k-5k"), (10000, "5k-1w"), (30000, "1w-3w"),
                        (50000, "3w-5w"), (100000, "5w-10w")):
        if n < edge:
            return label
    return "10w+"


def breakout_from_ratio(likes, followers) -> str:
    """Bucket only. The ratio and both operands stay out of the product file."""
    if not isinstance(likes, (int, float)) or not isinstance(followers, (int, float)) or not followers:
        return "未分级"
    ratio = likes / followers
    return "现象级" if ratio >= 50 else "强" if ratio >= 10 else "中" if ratio >= 2 else "观察"


def canonical(url: str) -> str:
    """Identity key for dedup: strip session tokens and tracking, keep the note path."""
    base = re.sub(r"[?#].*$", "", url.strip()).rstrip("/")
    note = re.search(r"/(?:explore|discovery/item|item)/([0-9a-f]{16,32})", base)
    return f"xhs:{note.group(1)}" if note else base.lower()


def make_id(prefix: str, key: str) -> str:
    note = re.search(r"([0-9a-f]{20,32})", key)
    if note:
        return f"xhs-{note.group(1)}"
    return f"{prefix}-{hashlib.sha1(key.encode()).hexdigest()[:12]}"


def monetization(raw: str) -> str:
    if blank(raw):
        return ""
    parts = [p.strip() for p in re.split(r"[/+、,，]", str(raw)) if p.strip()]
    seen = []
    for part in parts:
        label = MONETIZATION.get(part, part if len(part) <= 6 else "")
        if label and label not in seen:
            seen.append(label)
    return "/".join(seen[:3])


def empty_record() -> dict:
    record = {field: "" for field in FIELDS}
    record["hashtags"] = []
    record["tagging"] = {"mode": "", "ai_filled_fields": [], "human_fields": []}
    for score in ("replicability_score", "remake_value_score", "fit_score"):
        record[score] = None
    return record


# ------------------------------------------------------------------ batch A
def load_main() -> list[dict]:
    import openpyxl
    sheet = openpyxl.load_workbook(CLEAN_XLSX, read_only=True, data_only=True)["low_follower_viral"]
    rows = list(sheet.iter_rows(values_only=True))
    header = list(rows[0])
    out = []
    for raw in rows[1:]:
        row = dict(zip(header, raw))
        url = text(row.get("note_url"), 600)
        if not url:
            continue
        record = empty_record()
        human = ["topic_category", "content_angle", "title_hook", "pain_point", "promised_result",
                 "target_audience", "monetization_hint", "takeaway", "replicability_score",
                 "remake_value_score", "fit_score"]
        notes = text(row.get("notes"))
        why = re.search(r"why_viral=(.*?)(?:\s*\|\s*remake=|$)", notes)
        remake = re.search(r"remake=(.*?)(?:\s*\|\s*fit=|$)", notes)
        takeaway = []
        if why:
            takeaway.append("爆点：" + why.group(1).strip())
        if remake:
            takeaway.append("可复刻：" + remake.group(1).strip())
        formula_raw = text(row.get("title_formula"))
        title = text(row.get("title"), 200)
        record.update(
            id=make_id("xhs", url),
            url=url,
            platform="小红书" if row.get("source_platform") == "xiaohongshu" else text(row.get("source_platform")),
            note_type="图文" if row.get("note_type") == "image_text" else "视频" if row.get("note_type") == "video" else "",
            title=title,
            published_at=iso_date(row.get("publish_time")),
            topic_category=text(row.get("topic_category")) or "其他",
            content_angle=text(row.get("content_angle")),
            title_formula=formula_of(formula_raw, title),
            title_hook=text(row.get("title_hook"), 120),
            cover_hook="",
            opening_hook="",
            pain_point=text(row.get("pain_point"), 200),
            promised_result=text(row.get("promised_result"), 200),
            target_audience=text(row.get("target_audience"), 120),
            monetization_hint=monetization(row.get("monetization_hint")),
            follower_band=text(row.get("follower_bucket")) or "unknown",
            breakout_level={"strong": "强", "standard": "中", "watchlist": "观察"}.get(
                text(row.get("viral_level")), "未分级"),
            replicability_score=row.get("replicability_score") if isinstance(row.get("replicability_score"), int) else None,
            remake_value_score=row.get("remake_value_score") if isinstance(row.get("remake_value_score"), int) else None,
            fit_score=row.get("xiaolu_fit_score") if isinstance(row.get("xiaolu_fit_score"), int) else None,
            takeaway=" ｜ ".join(takeaway)[:300],
            keyword_source=text(row.get("keyword_source"), 60),
            hashtags=[h for h in re.split(r"[\s,，#]+", text(row.get("hashtags"), 200)) if h][:12],
            observed_at=iso_date(row.get("collected_at")),
            source_batch="low_follower_viral_2026-06",
        )
        record["tagging"] = {"mode": "human", "human_fields": human,
                             "ai_filled_fields": ["title_formula"],
                             "note": "标签与拆解结论出自 2026-06 低粉爆款研究（人工/原研究）；title_formula 由原自由文本归一到固定枚举。"}
        out.append(record)
    return out


# ------------------------------------------------------------------ batch B
def load_radar() -> list[dict]:
    rows = json.loads((SOURCES / "radar_records.json").read_text())
    out = []
    for row in rows:
        if row.get("来源") not in {"雷达", "自己刷到的"}:
            continue
        url = text(row.get("链接"), 600)
        if not url:
            continue
        title = text(row.get("标题"), 200)
        keyword = text(row.get("来源关键词"), 60)
        record = empty_record()
        topic = TOPIC_BY_KEYWORD.get(keyword) or first_match(TOPIC_TITLE_RULES, title, "其他")
        record.update(
            id=make_id("xhs", text(row.get("笔记ID"), 64) or url),
            url=url,
            platform="小红书",
            note_type=text(row.get("类型"), 10) if text(row.get("类型")) in NOTE_TYPES else "",
            title=title,
            published_at=iso_date(row.get("发布日期")),
            topic_category=topic,
            content_angle=first_match(ANGLE_RULES, title, "教程型"),
            title_formula=first_match(FORMULA_RULES, title, "未归类"),
            follower_band=follower_band(row.get("作者粉丝")) or "unknown",
            breakout_level=breakout_from_ratio(row.get("点赞"), row.get("作者粉丝")) if row.get("点赞") else "强",
            keyword_source=keyword,
            observed_at=iso_date(row.get("采集日期")),
            source_batch="viral_radar",
        )
        record["tagging"] = {"mode": "ai_filled", "human_fields": ["keyword_source", "note_type"],
                             "ai_filled_fields": ["topic_category", "content_angle", "title_formula"],
                             "note": "本批只有链接与标题等公开元数据，分类/公式/拆解结论由 AI 依据标题判断，未读取原文正文。"}
        out.append(record)
    return out


# ------------------------------------------------------------------ batch C
def load_library() -> list[dict]:
    rows = json.loads((SOURCES / "benchmark_lib_records.json").read_text())
    out = []
    for row in rows:
        if row.get("exclude"):
            continue
        if row.get("source") not in {"对标参考", "学习素材"}:
            continue
        url = text(row.get("url"), 600)
        if not url:
            continue
        title = text(row.get("title"), 200)
        record = empty_record()
        record.update(
            id=make_id("ref", row.get("note_id") or url),
            url=url,
            platform=text(row.get("platform"), 20),
            note_type="视频" if row.get("duration_s") else "",
            title=title,
            published_at=iso_date(row.get("published_ms")),
            topic_category=first_match(TOPIC_TITLE_RULES, title, "") if title else "",
            content_angle=first_match(ANGLE_RULES, title, "") if title else "",
            title_formula=first_match(FORMULA_RULES, title, "未归类") if title else "",
            hashtags=[h for h in re.split(r"[\s,，#]+", text(row.get("hashtags"), 200)) if h][:12],
            observed_at=iso_date(row.get("observed_ms")),
            follower_band="",
            breakout_level="未分级",
            source_batch="benchmark_library",
        )
        record["tagging"] = {
            "mode": "ai_filled" if title else "url_only",
            "human_fields": ["platform", "url"],
            "ai_filled_fields": [f for f in ("topic_category", "content_angle", "title_formula") if record[f]],
            "note": "Max 人工收藏的对标链接。" + ("标签由 AI 依据标题判断。" if title
                    else "原表未记录标题，且本任务不抓取原内容，标题与标签留空，不推断。"),
        }
        out.append(record)
    return out


# ------------------------------------------------------------------ assembly
def apply_ai_tags(records: list[dict]) -> int:
    path = SOURCES / "ai_tags.json"
    if not path.is_file():
        return 0
    tags = json.loads(path.read_text())
    index = {r["id"]: r for r in records}
    touched = 0
    allowed = {"topic_category", "content_angle", "title_formula", "title_hook", "pain_point",
               "promised_result", "target_audience", "monetization_hint", "takeaway", "note_type"}
    for entry in tags:
        record = index.get(entry.get("id"))
        if not record:
            continue
        filled = set(record["tagging"].get("ai_filled_fields") or [])
        for field, value in entry.items():
            if field == "id" or field not in allowed or blank(value):
                continue
            record[field] = text(value, 300)
            filled.add(field)
        record["tagging"]["ai_filled_fields"] = sorted(filled)
        record["tagging"]["mode"] = "ai_filled"
        touched += 1
    return touched


def dedupe(batches: list[list[dict]]) -> tuple[list[dict], int]:
    """Earlier batches win: the 2026-06 study carries the richest human tagging."""
    seen: dict[str, dict] = {}
    dropped = 0
    for batch in batches:
        for record in batch:
            key = canonical(record["url"])
            if key in seen:
                dropped += 1
                kept = seen[key]
                if not kept["title"] and record["title"]:
                    kept["title"] = record["title"]
                if not kept["published_at"] and record["published_at"]:
                    kept["published_at"] = record["published_at"]
                continue
            seen[key] = record
    return list(seen.values()), dropped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "bench" / "data" / "bench.json")
    args = parser.parse_args()

    main_rows, radar_rows, library_rows = load_main(), load_radar(), load_library()
    records, dropped = dedupe([main_rows, radar_rows, library_rows])
    tagged = apply_ai_tags(records)
    records.sort(key=lambda r: (r["published_at"] or "0000-00-00", r["id"]), reverse=True)

    # Allowlist projection: only declared fields ever reach the product file.
    # Titles are third-party originals and stay verbatim; derived copy is sanitised.
    verbatim = {"title", "url", "id", "hashtags"}
    records = [{field: (record[field] if field in verbatim or not isinstance(record[field], str)
                        else sanitize(record[field])) for field in FIELDS} for record in records]
    for record in records:
        note = record["tagging"].get("note")
        if note:
            record["tagging"]["note"] = sanitize(note)
    counts = collections.Counter(r["topic_category"] or "未标注" for r in records)
    payload = {
        "data_as_of": max((r["observed_at"] for r in records if r["observed_at"]), default=""),
        "generated_at": datetime.now(CST).date().isoformat(),
        "taxonomy": {"topic_category": TOPIC_CATEGORIES, "content_angle": CONTENT_ANGLES,
                     "title_formula": TITLE_FORMULAS, "cover_hook": COVER_HOOKS,
                     "follower_band": FOLLOWER_BANDS, "breakout_level": BREAKOUT_LEVELS,
                     "note_type": NOTE_TYPES},
        "batches": [{"batch": "low_follower_viral_2026-06", "input_rows": len(main_rows)},
                    {"batch": "viral_radar", "input_rows": len(radar_rows)},
                    {"batch": "benchmark_library", "input_rows": len(library_rows)},
                    {"batch": "deduped_by_link", "input_rows": dropped}],
        "records": records,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"records={len(records)} A={len(main_rows)} B={len(radar_rows)} C={len(library_rows)} "
          f"deduped={dropped} ai_tag_rows_applied={tagged}")
    print("topic_category:", dict(counts.most_common()))
    print("out:", args.out)


if __name__ == "__main__":
    main()
