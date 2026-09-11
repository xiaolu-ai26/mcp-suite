"""Full-library compliance scan. Exit code 0 only when every rule passes.

Scans the shipped data file, the product copy surfaces (static pages, tool
descriptions, README) and, with --url, the live MCP responses themselves.
Writes a receipt so the result is auditable later.

    .venv/bin/python -m bench.assert_clean
    BENCH_ASSERT_KEY=... .venv/bin/python -m bench.assert_clean --url https://savegems.top/bench
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Field names that could only ever carry a note body, a transcript or an exact metric.
BODY_FIELDS = re.compile(
    r"transcript|逐字|字幕|subtitle|ocr|raw_json|evidence|full_text|文字稿|note_text|"
    r"正文|文案|分镜|script|(^|_)(content|body|desc|description|text|caption)"
    r"(_(raw|text|html|md|full))?$",
    re.IGNORECASE)
METRIC_FIELDS = re.compile(
    r"like|collect|favou?rite|comment|share|view|play|read|fans|follower|engagement|ratio|"
    r"点赞|收藏|评论|分享|播放|粉丝|互动|赞粉",
    re.IGNORECASE)
# Bands and levels are the only permitted way to express reach.
METRIC_FIELD_ALLOW = {"follower_band", "breakout_level"}
MEDIA = re.compile(r"xhscdn|sns-(img|video|na)|\.(jpe?g|png|gif|webp|bmp|mp4|mov|m3u8|ts|avi)(\?|#|$)",
                   re.IGNORECASE)
# The field-name blacklist above cannot see a number that hides inside a sentence:
# 「收藏8615极高」「1.4w赞1.9w藏」「没爆(9赞)」all passed it. So any free text where an
# engagement word sits next to a number is a failure too. Deliberately wider than a
# 2-digit rule: 「4w赞」「收藏1.8w」「(29赞)」are exact numbers as well.
_METRIC_WORD = r"收藏|点赞|赞|评论|转发|播放|粉丝|涨粉|互动|藏|粉"
_NUM = r"\d+(?:[.,]\d+)?\s*(?:[wWkK万千百]|\+)?"
# Two directions, each allowing only the handful of connectors that show up in real
# sentences — 「收藏破1.4w」「收藏拉满(2152)」「3.8w高收藏」「1457赞2311藏」「没爆(9赞)」.
# Kept deliberately tight: a wider gap starts matching ordinary prose such as
# 「私藏的10个提示词」or「2026-06 低粉爆款研究」, which would train everyone to ignore it.
# This is a floor, not a proof — a number with no engagement word next to it
# (「2万+双高数据」) still needs a human to catch, so read new takeaways before shipping.
METRIC_NUMBER = re.compile(
    rf"(?:{_METRIC_WORD})\s*(?:量|数|率)?\s*[:：=]?\s*(?:破|近|超|达|约|仅|高达|拉满|只有)?\s*[（(\[]?\s*{_NUM}"
    rf"|{_NUM}\s*[)）\]]?\s*(?:超|极|巨|高)?(?:{_METRIC_WORD})"
    rf"|赞粉比\s*[\d.]+")
# Exceptions, one line each with the reason it is not an engagement number. A hit that is
# not listed here fails — no broad "titles are fine" rule, so a new one must be reviewed.
METRIC_NUMBER_ALLOW = [
    ("promised_result", "收藏10个最值得装的Codex插件",
     "「收藏10个」是原笔记承诺读者拿到的东西（收藏=动词），不是这条笔记的收藏数"),
    ("title", "用AI做儿童绘本🔥涨粉8W",
     "他人原标题原样引用，Max 已拍板原标题照出；同时记入 notes 作为待决定项"),
]
_METRIC_ALLOW_INDEX = {(field, value) for field, value, _ in METRIC_NUMBER_ALLOW}
_METRIC_ALLOW_REASON = {(field, value): reason for field, value, reason in METRIC_NUMBER_ALLOW}
BANNED_COPY = ("爬虫", "爬取", "抓取", "采集", "小红书数据")
SCORE_FIELDS = {"replicability_score", "remake_value_score", "fit_score"}
# Containers whose dict keys are data labels (a taxonomy value, a batch name), not field
# names; checking them as field names produces false positives like "low_follower_viral".
HISTOGRAM_KEYS = {"counts", "tagging_source", "filters"}
COUNTER_KEYS = {"total", "offset", "next_offset", "total_records"} | HISTOGRAM_KEYS
MAX_STRING = 300
MAX_URL = 500


class Scan:
    def __init__(self):
        self.failures: list[str] = []
        self.notes: list[str] = []
        self.stats: dict[str, int] = {}

    def fail(self, message: str):
        self.failures.append(message)

    def check_value(self, where: str, key: str, value):
        if isinstance(value, dict):
            histogram = key in HISTOGRAM_KEYS
            for k, v in value.items():
                if histogram:
                    self.check_value(where, key, k)
                    self.check_value(where, key, v)
                else:
                    self.check_value(where, k, v)
            return
        if isinstance(value, list):
            for v in value:
                self.check_value(where, key, v)
            return
        if isinstance(value, bool) or value is None:
            return
        if BODY_FIELDS.search(key or ""):
            self.fail(f"{where}: 出现正文/逐字稿类字段名 `{key}`")
        if METRIC_FIELDS.search(key or "") and key not in METRIC_FIELD_ALLOW:
            self.fail(f"{where}: 出现互动数据类字段名 `{key}`")
        if isinstance(value, (int, float)):
            if key in METRIC_FIELD_ALLOW:
                self.fail(f"{where}.{key}: 分级字段必须是文字分级，收到数字 {value}")
            elif key in SCORE_FIELDS:
                if not 0 <= value <= 10:
                    self.fail(f"{where}.{key}: 评分超出 0-10 范围（{value}）")
            elif key not in COUNTER_KEYS and not str(key).endswith("count"):
                if value > 999:
                    self.fail(f"{where}.{key}: 疑似精确数值 {value}，产品库不返回原始数字")
            return
        if not isinstance(value, str):
            return
        limit = MAX_URL if key in {"url"} else MAX_STRING
        if len(value) > limit:
            self.fail(f"{where}.{key}: 字符串长度 {len(value)} 超过 {limit}，疑似正文/逐字稿")
        if MEDIA.search(value):
            self.fail(f"{where}.{key}: 出现图片/视频直链 `{value[:80]}`")
        self.check_metric_numbers(where, key, value)
        for word in BANNED_COPY:
            if word in value:
                if key == "title":
                    self.notes.append(f"{where}.title 含「{word}」，属他人原标题原样引用，不改写")
                else:
                    self.fail(f"{where}.{key}: 出现禁用字样「{word}」 → {value[:60]}")

    def check_metric_numbers(self, where: str, key: str, value: str):
        """互动词 + 数字（任一方向）= 精确互动数泄漏，除非逐条白名单放行。"""
        hits = [m.group(0) for m in METRIC_NUMBER.finditer(value)]
        if not hits:
            return
        if (key, value) in _METRIC_ALLOW_INDEX:
            self.notes.append(f"{where}.{key} 命中互动数正则但已逐条豁免（{'/'.join(hits)}）："
                              f"{_METRIC_ALLOW_REASON[(key, value)]}")
            return
        self.fail(f"{where}.{key}: 自由文本内嵌精确互动数「{'/'.join(hits)}」 → {value[:80]}")

    def check_records(self, where: str, records: list):
        self.stats[where] = len(records)
        seen = set()
        for i, record in enumerate(records):
            tag = f"{where}[{i}:{record.get('id', '?')}]"
            url = record.get("url")
            if not isinstance(url, str) or not url.strip():
                self.fail(f"{tag}: url 为空，链接是必填项")
            elif not url.startswith(("http://", "https://")):
                self.fail(f"{tag}: url 不是 http(s) 链接 → {url[:60]}")
            rid = record.get("id")
            if not rid:
                self.fail(f"{tag}: 缺少 id")
            elif rid in seen:
                self.fail(f"{tag}: id 重复")
            else:
                seen.add(rid)
            for key, value in record.items():
                self.check_value(tag, key, value)


def copy_body(path: Path) -> tuple[str, int]:
    """Return the copy that belongs to this product, plus its starting line number.

    README.md documents several products; only the bench chapter is bench copy, and
    the recruitment product legitimately describes its own collector.
    """
    body = path.read_text(errors="replace")
    if path.name != "README.md":
        return body, 1
    lines = body.splitlines()
    # The chapter heading is 「## bench · AI 赛道爆款拆解库 MCP」. An earlier online run
    # scanned 0 chars here because the chapter did not exist yet, and the scan stayed
    # green while silently checking nothing — so a missing chapter is now a failure.
    start = next((i for i, line in enumerate(lines)
                  if re.match(r"^##\s", line) and "bench" in line.lower()), None)
    if start is None:
        return "", 1
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^##\s", lines[i])), len(lines))
    return "\n".join(lines[start:end]), start + 1


def rel(path: Path) -> str:
    """Never let a path outside the repo (a --copy override) crash the scan."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def scan_copy(scan: Scan, paths: list[Path]):
    """Product copy a buyer or their agent can read must never sound like harvesting."""
    for path in paths:
        if not path.is_file():
            scan.fail(f"文案文件不存在：{path}，本轮文案规则并未真正生效")
            scan.stats[f"copy:{path.name}"] = 0
            continue
        body, base_line = copy_body(path)
        if not body.strip():
            scan.fail(f"文案 {rel(path)}: 扫描到 0 字符"
                      f"（README 需含以 `## ` 开头且带 bench 的章节标题），本轮文案规则并未真正生效")
            scan.stats[f"copy:{path.name}"] = 0
            continue
        for word in BANNED_COPY:
            for match in re.finditer(word, body):
                line = body.count("\n", 0, match.start()) + base_line
                scan.fail(f"文案 {rel(path)}:{line} 出现禁用字样「{word}」")
        for match in METRIC_NUMBER.finditer(body):
            line = body.count("\n", 0, match.start()) + base_line
            scan.fail(f"文案 {rel(path)}:{line} 出现互动词+数字「{match.group(0)}」")
        scan.stats[f"copy:{path.name}"] = len(body)


async def scan_online(scan: Scan, base: str, key: str, page: int = 100):
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    transport = StreamableHttpTransport(base.rstrip("/") + "/mcp",
                                        headers={"Authorization": "Bearer " + key})
    collected = []
    async with Client(transport) as client:
        taxonomy = (await client.call_tool("bench_taxonomy", {})).data
        scan.check_value("online:bench_taxonomy", "bench_taxonomy", taxonomy)
        offset, total = 0, None
        while True:
            data = (await client.call_tool("bench_search", {"limit": page, "offset": offset})).data
            total = data.get("total")
            scan.check_records("online:bench_search", data.get("records", []))
            collected.extend(data.get("records", []))
            for key_name in ("scope_note", "link_note", "suggestion", "data_as_of"):
                scan.check_value("online:bench_search", key_name, data.get(key_name))
            if data.get("next_offset") is None:
                break
            offset = data["next_offset"]
        if collected:
            detail = (await client.call_tool("bench_detail", {"id": collected[0]["id"]})).data
            scan.check_records("online:bench_detail", detail.get("records", []))
    scan.stats["online_total_reported"] = total or 0
    scan.stats["online_records_scanned"] = len(collected)
    if total is not None and len(collected) != total:
        scan.fail(f"线上分页未覆盖全库：抓到 {len(collected)}，接口声称 {total}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "bench" / "data" / "bench.json")
    parser.add_argument("--copy", type=Path, nargs="*", default=None,
                        help="文案文件；默认扫 bench/static/*、bench/tools.py、core/server.py、README.md")
    parser.add_argument("--url", default=None, help="线上基址，如 https://savegems.top/bench")
    parser.add_argument("--receipt", type=Path, default=ROOT / "bench" / "receipts" / "assert-clean.json")
    args = parser.parse_args()

    scan = Scan()
    payload = json.loads(args.data.read_text())
    records = payload["records"] if isinstance(payload, dict) else payload
    scan.check_records("file:" + args.data.name, records)
    for key in ("data_as_of", "generated_at", "taxonomy", "batches"):
        scan.check_value("file:meta", key, payload.get(key) if isinstance(payload, dict) else None)

    copy_paths = args.copy if args.copy is not None else (
        sorted((ROOT / "bench" / "static").glob("*.*")) +
        [ROOT / "bench" / "tools.py", ROOT / "core" / "server.py", ROOT / "README.md"])
    scan_copy(scan, [Path(p) for p in copy_paths])

    if args.url:
        key = os.environ.get("BENCH_ASSERT_KEY", "")
        if not key:
            scan.fail("给了 --url 但环境变量 BENCH_ASSERT_KEY 为空，无法扫描线上返回")
        else:
            asyncio.run(scan_online(scan, args.url, key))

    receipt = {"checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
               "data_file": str(args.data), "online_base": args.url,
               "stats": scan.stats, "notes": scan.notes,
               "failures": scan.failures, "passed": not scan.failures,
               "rules": ["无正文/逐字稿字段名", "无正文级长字符串(>300)", "无互动数字段名与精确数字",
                         "每条必有 http(s) 链接且 id 唯一", "无图片/视频直链",
                         "文案面无「爬虫/爬取/抓取/采集/小红书数据」",
                         "自由文本无「互动词+数字」（含 万/w/括号/个位数），例外逐条白名单",
                         "每个文案面必须扫到 >0 字符，扫到 0 判失败"]}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))

    print(json.dumps({k: v for k, v in receipt.items() if k != "failures"}, ensure_ascii=False, indent=2))
    if scan.failures:
        print("\nFAILURES:")
        for failure in scan.failures[:60]:
            print("  -", failure)
        print(f"\n不合规：{len(scan.failures)} 条。收据：{args.receipt}")
        return 1
    print(f"\n全部通过。收据：{args.receipt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
