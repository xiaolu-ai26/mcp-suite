#!/usr/bin/env python3
"""Summarise MCP tool-call logs (tool_calls-YYYYMMDD.jsonl written by core/server.py, release A2+).

Usage:  analyze_call_logs.py LOG_DIR [--window 60] [--top 20] [--json]

Reports calls per day, per tool, per client (User-Agent), how often each parameter name is
sent, the top values of each parameter, the zero-result ratio, and how many times the same
user_ref repeated an identical call (same tool, same arguments) within --window seconds of
the previous one; that last number is what exposes a client stuck in a retry loop.
Standard library only; reads the files, never modifies them.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def load(target: Path):
    files = [target] if target.is_file() else sorted(target.glob("tool_calls-*.jsonl"))
    entries, bad = [], 0
    for path in files:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    entry["_t"] = datetime.fromisoformat(entry["ts"])
                    if not isinstance(entry.get("args"), dict):
                        raise ValueError
                except (ValueError, KeyError, TypeError):
                    bad += 1
                    continue
                entries.append(entry)
    entries.sort(key=lambda e: e["_t"])
    return files, entries, bad


def tool_key(entry) -> str:
    return f"{entry.get('product')}/{entry.get('tool')}"


def show(value) -> str:
    if value is None:
        return "(null)"
    if value == "":
        return "(空字符串)"
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)[:80]


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def analyze(entries, window: float, top: int) -> dict:
    by_day = defaultdict(Counter)
    by_tool = defaultdict(lambda: {"calls": 0, "ok": 0, "error": 0, "error_types": Counter(), "ms": []})
    by_ua = Counter()
    names = defaultdict(Counter)
    values = defaultdict(lambda: defaultdict(Counter))
    zero = defaultdict(Counter)
    groups = defaultdict(list)
    no_ref = 0
    for e in entries:
        key, ok = tool_key(e), e.get("outcome") == "ok"
        day = e["_t"].date().isoformat()
        by_day[day]["calls"] += 1
        by_day[day]["ok" if ok else "error"] += 1
        t = by_tool[key]
        t["calls"] += 1
        t["ok" if ok else "error"] += 1
        if not ok:
            t["error_types"][e.get("error_type") or "unknown"] += 1
        if isinstance(e.get("duration_ms"), (int, float)):
            t["ms"].append(e["duration_ms"])
        by_ua[e.get("ua") or "(空)"] += 1
        for name, value in e["args"].items():
            names[key][name] += 1
            values[key][name][show(value)] += 1
        count = e.get("result_total") if e.get("result_total") is not None else e.get("returned")
        if ok and isinstance(count, int):
            for bucket in ("_all", key):
                zero[bucket]["known"] += 1
                zero[bucket]["zero"] += count == 0
        if e.get("user_ref"):
            args = json.dumps(e["args"], ensure_ascii=False, sort_keys=True)
            groups[(e["user_ref"], e.get("product"), e.get("tool"), args)].append(e)
        else:
            no_ref += 1

    repeat_groups, total_repeats = [], 0
    for (ref, product, tool, args), calls in groups.items():
        repeats, burst, longest = 0, 1, 1
        for prev, cur in zip(calls, calls[1:]):
            if (cur["_t"] - prev["_t"]).total_seconds() <= window:
                repeats, burst = repeats + 1, burst + 1
                longest = max(longest, burst)
            else:
                burst = 1
        if repeats:
            total_repeats += repeats
            repeat_groups.append({"user_ref": ref, "product": product, "tool": tool, "args": json.loads(args),
                                  "calls": len(calls), "repeats": repeats, "longest_burst": longest,
                                  "ua": Counter(c.get("ua") or "(空)" for c in calls).most_common(1)[0][0],
                                  "first_ts": calls[0]["ts"], "last_ts": calls[-1]["ts"]})
    repeat_groups.sort(key=lambda g: (-g["repeats"], g["first_ts"]))

    def ratio(c):
        return {"known": c["known"], "zero": c["zero"],
                "ratio": round(c["zero"] / c["known"], 4) if c["known"] else None}

    ua_top = dict(by_ua.most_common(top))
    if len(by_ua) > top:
        ua_top["(其他)"] = sum(by_ua.values()) - sum(ua_top.values())
    return {
        "lines": len(entries),
        "first_ts": entries[0]["ts"] if entries else None,
        "last_ts": entries[-1]["ts"] if entries else None,
        "users": len({e["user_ref"] for e in entries if e.get("user_ref")}),
        "outcome": dict(Counter(e.get("outcome") for e in entries)),
        "by_day": {d: dict(c) for d, c in sorted(by_day.items())},
        "by_tool": {k: {"calls": t["calls"], "ok": t["ok"], "error": t["error"],
                        "error_types": dict(t["error_types"].most_common()),
                        "p50_ms": percentile(t["ms"], 0.5), "p95_ms": percentile(t["ms"], 0.95)}
                    for k, t in sorted(by_tool.items(), key=lambda kv: -kv[1]["calls"])},
        "by_ua": ua_top,
        "param_names": {k: {n: {"count": c, "share": round(c / by_tool[k]["calls"], 4)}
                            for n, c in counter.most_common()} for k, counter in names.items()},
        "top_values": {k: {n: [[v, c] for v, c in counter.most_common(top)]
                           for n, counter in sorted(params.items(), key=lambda kv: -sum(kv[1].values()))}
                       for k, params in values.items()},
        "zero_results": {"overall": ratio(zero["_all"]),
                         "by_tool": {k: ratio(c) for k, c in sorted(zero.items()) if k != "_all"}},
        "repeats": {"window_s": window, "total_repeats": total_repeats, "groups_with_repeats": len(repeat_groups),
                    "calls_without_user_ref": no_ref, "groups": repeat_groups[:top]},
    }


def render(target, files, bad, r) -> str:
    out = [f"调用日志分析：{target}（文件 {len(files)} 个，有效行 {r['lines']}，坏行 {bad}）",
           f"时间范围：{r['first_ts']} — {r['last_ts']}；不同 user_ref {r['users']} 个；结果 {r['outcome']}", ""]
    out.append("== 按天调用量 ==")
    out.append(f"{'日期':<12}{'调用':>6}{'成功':>6}{'失败':>6}")
    for day, c in r["by_day"].items():
        out.append(f"{day:<12}{c.get('calls', 0):>6}{c.get('ok', 0):>6}{c.get('error', 0):>6}")
    out += ["", "== 按工具 ==", f"{'产品/工具':<26}{'调用':>6}{'成功':>6}{'失败':>6}{'p50ms':>8}{'p95ms':>8}  错误类型"]
    for key, t in r["by_tool"].items():
        errors = "，".join(f"{k}×{v}" for k, v in t["error_types"].items()) or "-"
        out.append(f"{key:<26}{t['calls']:>6}{t['ok']:>6}{t['error']:>6}"
                   f"{str(t['p50_ms']):>8}{str(t['p95_ms']):>8}  {errors}")
    out += ["", "== 按客户端（UA）=="]
    out += [f"{c:>6}  {ua}" for ua, c in r["by_ua"].items()]
    out += ["", "== 参数名出现频率（占该工具调用次数的比例）=="]
    for key, params in r["param_names"].items():
        out.append(f"{key}（{r['by_tool'][key]['calls']} 次调用）")
        out += [f"  {name:<20}{p['count']:>6}  {p['share']:>7.1%}" for name, p in params.items()]
    out += ["", "== 热门参数值（每个参数取前 N 个，N 见 --top）=="]
    for key, params in r["top_values"].items():
        for name, pairs in params.items():
            out.append(f"{key} · {name}")
            out += [f"  {c:>6}  {v if len(v) <= 60 else v[:60] + '…'}" for v, c in pairs]
    out += ["", "== 零结果比例（成功且能取到条数的调用）=="]
    z = r["zero_results"]
    rows = [("全部", z["overall"])] + list(z["by_tool"].items())
    for name, c in rows:
        share = f"{c['ratio']:.1%}" if c["ratio"] is not None else "-"
        out.append(f"{name:<26}{c['zero']:>6}/{c['known']:<6}{share:>8}")
    rp = r["repeats"]
    out += ["", f"== 同一 user_ref 在 {rp['window_s']:g} 秒内用相同参数重复调用 ==",
            f"重复次数合计：{rp['total_repeats']}（涉及 {rp['groups_with_repeats']} 组；"
            f"无 user_ref 的调用 {rp['calls_without_user_ref']} 次，未计入）"]
    if rp["groups"]:
        out.append(f"{'user_ref':<14}{'产品/工具':<24}{'调用':>5}{'重复':>5}{'最长连发':>9}  UA | 参数")
        for g in rp["groups"]:
            args = json.dumps(g["args"], ensure_ascii=False)
            out.append(f"{g['user_ref']:<14}{g['product'] + '/' + g['tool']:<24}{g['calls']:>5}{g['repeats']:>5}"
                       f"{g['longest_burst']:>9}  {g['ua'][:40]} | {args[:120]}")
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("log_dir", type=Path, help="目录（读取其中 tool_calls-*.jsonl）或单个 .jsonl 文件")
    parser.add_argument("--window", type=float, default=60, help="重复调用判定窗口，秒（默认 60）")
    parser.add_argument("--top", type=int, default=20, help="每个排行取前 N（默认 20）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)
    if not args.log_dir.exists():
        parser.error(f"不存在：{args.log_dir}")
    files, entries, bad = load(args.log_dir)
    report = analyze(entries, args.window, args.top)
    if args.json:
        print(json.dumps({"files": [str(f) for f in files], "bad_lines": bad, **report}, ensure_ascii=False, indent=1))
    else:
        print(render(args.log_dir, files, bad, report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
