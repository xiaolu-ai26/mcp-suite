"""Read owned breakdown records: public link, original title, original tags, conclusion.

Hard rule enforced here as well as in the build step: the response projection is an
allowlist. Note bodies, transcripts, cover/video files and exact engagement numbers
have no field to travel in, even if a future data file grew one.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from core.store import TZ

PUBLIC_FIELDS = ("id", "url", "platform", "note_type", "title", "published_at",
                 "topic_category", "content_angle", "title_formula", "title_hook",
                 "cover_hook", "opening_hook", "pain_point", "promised_result",
                 "target_audience", "monetization_hint", "follower_band", "breakout_level",
                 "replicability_score", "remake_value_score", "fit_score", "takeaway",
                 "keyword_source", "hashtags", "observed_at", "source_batch", "tagging")

TAG_FIELDS = ("title_formula", "content_angle", "cover_hook", "keyword_source",
              "title_hook", "topic_category")

SCOPE_NOTE = ("本库为存量拆解资产：只提供公开链接、原标题与原创拆解标签，"
              "不含笔记正文、图片、视频与精确互动数据；粉丝只给区间，破圈只给分级词。")
# Verified 2026-09-10 by opening records in a logged-in browser: xiaohongshu note links
# carry a time-bound xsec_token, and the ones recorded at observation time no longer
# render on the web. Say so in every response instead of letting the buyer discover it.
LINK_NOTE = ("链接为观察当时记录的公开地址。小红书的 explore/discovery 链接带有时效性参数，"
             "2026-09-10 实测多数已无法在网页端直接打开（提示需在小红书 App 内查看）；"
             "此时可用返回的原标题在小红书 App 内搜索原文。抖音、TikTok 等平台链接实测可直接打开。"
             "作者删除或平台调整都会导致链接失效，本服务不保存内容副本，也不承诺链接长期可访问。")


class Bench:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.is_file():
            raise FileNotFoundError("拆解库数据尚未就绪")
        payload = json.loads(self.path.read_text())
        if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
            raise ValueError("拆解库格式异常，请稍后重试")
        # A malformed dataset must never silently turn into records without a source link.
        rows = [row for row in payload["records"] if isinstance(row, dict) and row.get("url")]
        cutoff = payload.get("data_as_of") or max((r.get("observed_at") or "" for r in rows), default="") or None
        return rows, cutoff, payload

    @staticmethod
    def public(row):
        return {field: row.get(field, "") for field in PUBLIC_FIELDS}

    def envelope(self, rows, cutoff, **extra):
        return {"data_as_of": cutoff, "数据截至时间": cutoff, "scope_note": SCOPE_NOTE,
                "link_note": LINK_NOTE,
                "records": [self.public(r) for r in rows], **extra}

    @staticmethod
    def _window(row, window):
        """Filter on the publish date only when it is actually recorded; never guess."""
        if not window:
            return True
        published = (row.get("published_at") or "")[:10]
        if not published:
            return False
        text = str(window).strip().lower()
        days = re.fullmatch(r"(\d{1,5})\s*(d|天|days?)?", text)
        if days and text != "":
            try:
                limit = int(days.group(1))
            except ValueError:
                return False
            edge = (datetime.now(TZ).date() - timedelta(days=limit)).isoformat()
            return published >= edge
        if re.fullmatch(r"\d{4}(-\d{2}){0,2}", text):
            return published.startswith(text)
        return False

    def search(self, topic=None, format=None, tag=None, platform=None, time_window=None,
               keyword=None, limit=20, offset=0):
        rows, cutoff, _ = self.load()

        def contains(query, values):
            return query.strip().casefold() in json.dumps(values, ensure_ascii=False).casefold()

        def matches(row):
            if topic and not contains(topic, [row.get("topic_category"), row.get("keyword_source")]):
                return False
            if format and not contains(format, [row.get("note_type")]):
                return False
            if platform and not contains(platform, [row.get("platform")]):
                return False
            if tag and not contains(tag, [row.get(f) for f in TAG_FIELDS] + [row.get("hashtags")]):
                return False
            if keyword and not contains(keyword, [row.get("title"), row.get("takeaway"),
                                                  row.get("pain_point"), row.get("promised_result"),
                                                  row.get("target_audience")]):
                return False
            return self._window(row, time_window)

        selected = [r for r in rows if matches(r)]
        selected.sort(key=lambda r: (r.get("published_at") or "", r.get("observed_at") or "",
                                     r.get("id") or ""), reverse=True)
        total = len(selected)
        page = selected[offset:offset + limit]
        suggestion = None
        if not selected:
            suggestion = ("没有命中记录。可放宽条件：去掉 time_window（约一半记录未公开发布时间，"
                          "带时间窗会被排除）、换用 bench_taxonomy() 里列出的分类或标签名、"
                          "或只用 keyword 搜标题。未记录的字段不会被推断。")
        return self.envelope(page, cutoff, total=total, offset=offset,
                             next_offset=offset + limit if offset + limit < total else None,
                             filters={"topic": topic, "format": format, "tag": tag,
                                      "platform": platform, "time_window": time_window,
                                      "keyword": keyword},
                             suggestion=suggestion)

    def detail(self, record_id):
        rows, cutoff, _ = self.load()
        found = [r for r in rows if r.get("id") == record_id]
        return self.envelope(found, cutoff, found=bool(found),
                             suggestion=None if found else "未找到该记录，请先用 bench_search 获取当前 id。")

    def taxonomy(self):
        rows, cutoff, payload = self.load()
        declared = payload.get("taxonomy", {})

        def tally(field, vocabulary=None):
            counts = {}
            for row in rows:
                value = row.get(field) or ""
                counts[value or "未标注"] = counts.get(value or "未标注", 0) + 1
            ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            return {"vocabulary": vocabulary or sorted(k for k in counts if k != "未标注"),
                    "counts": dict(ordered)}

        tagging = {"human": 0, "ai_filled": 0, "url_only": 0, "other": 0}
        for row in rows:
            mode = (row.get("tagging") or {}).get("mode", "other")
            tagging[mode if mode in tagging else "other"] += 1
        return {
            "data_as_of": cutoff, "数据截至时间": cutoff, "scope_note": SCOPE_NOTE,
            "link_note": LINK_NOTE, "total_records": len(rows),
            "topic_category": tally("topic_category", declared.get("topic_category")),
            "title_formula": tally("title_formula", declared.get("title_formula")),
            "cover_hook": tally("cover_hook", declared.get("cover_hook")),
            "content_angle": tally("content_angle", declared.get("content_angle")),
            "note_type": tally("note_type", declared.get("note_type")),
            "platform": tally("platform"),
            "follower_band": tally("follower_band", declared.get("follower_band")),
            "breakout_level": tally("breakout_level", declared.get("breakout_level")),
            "source_batch": tally("source_batch"),
            "tagging_source": tagging,
            "coverage_notes": {
                "cover_hook": "封面版式需要看封面图才能判定；本产品不保存也不返回封面图，本期全部留空，标签体系先给出，后续人工补。",
                "opening_hook": "开头钩子需要看正文或视频，本期不标注。",
                "published_at": "约一半记录的发布时间原始资料未记录，留空而不是推断。",
                "tagging": "human=2026-06 低粉爆款研究的人工/原研究标签；ai_filled=依据标题与公开元数据由 AI 补打；url_only=只有链接，未补标签。",
            },
        }
