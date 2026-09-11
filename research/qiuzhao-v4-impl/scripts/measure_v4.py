"""tools/list, HTTP response sizes, latency and memory of the v4 tree (local uvicorn, throwaway DB).

usage (from the code root):
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python research/qiuzhao-v4-impl/scripts/measure_v4.py
Starts `uvicorn core.server:app` for qiuzhao (qiuzhao/data/jobs.json, MCP_TODAY=2026-09-11) and bench
(2-record fixture) through tests/_mcp_harness.py and speaks JSON-RPC over HTTP like a remote client.
Writes, under research/qiuzhao-v4-impl/:
  tools_list_v4.json / tools_list_v4.bench.json   the tools/list results
  evidence/sizes_v4.json                          body/text/jobs bytes, rough tokens, latency per call
  evidence/perf_v4.json                           build time, cached-call latency, memory
"""
import gc
import json
import os
import re
import statistics
import subprocess
import sys
import time
import tracemalloc
from datetime import date
from pathlib import Path

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT)]

import _mcp_harness as H  # noqa: E402
from conftest import BENCH_FIXTURE  # noqa: E402

W = ROOT / "research" / "qiuzhao-v4-impl"
WIDE = re.compile(r"[⺀-鿿가-힯豈-﫿＀-￯　-〿]")


def rss_mb(pid):
    return int(subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)]).strip()) / 1024


def rough_tokens(text):
    wide = len(WIDE.findall(text))
    return wide + (len(text) - wide) // 4


def write(name, obj):
    path = W / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def measure(server, tool, args, runs=7):
    times, body, result = [], None, None
    for _ in range(runs):
        started = time.perf_counter()
        result, body = server.call(tool, args, raw=True)
        times.append(round((time.perf_counter() - started) * 1000, 1))
    text = result["content"][0]["text"]
    data = json.loads(text)
    jobs = data.get("jobs")
    return {"tool": tool, "arguments": args, "http_body_bytes": len(body), "text_bytes": len(text.encode()),
            "has_structuredContent": result.get("structuredContent") is not None,
            "jobs_bytes": len(json.dumps(jobs, ensure_ascii=False, separators=(",", ":")).encode()) if jobs is not None else None,
            "returned": data.get("returned", len(jobs) if jobs is not None else data.get("returned_groups")),
            "total": data.get("total", data.get("found")), "truncated": data.get("truncated"),
            "rough_tokens": rough_tokens(text), "latency_ms_median": statistics.median(times), "latency_ms": times}


def http_part():
    qz = H.Server("qiuzhao", label="measure-qiuzhao").start()
    try:
        rss = {"after_start_mb": round(rss_mb(qz.proc.pid))}
        initialize = qz.initialize()
        tools = qz.rpc("tools/list")
        write("tools_list_v4.json", tools)
        started = time.perf_counter()
        qz.call("jobs_search", {"page_size": 1})
        first_call_ms = round((time.perf_counter() - started) * 1000)
        rss["after_first_call_mb"] = round(rss_mb(qz.proc.pid))
        from qiuzhao.tools import Jobs
        jobs = Jobs(H.JOBS_PATH, today=date.fromisoformat(H.TODAY))
        offset = next(k for k in range(0, 25_000, 20) if jobs.search(page_size=20, offset=k)["truncated"])
        ids = ",".join(j["id"] for j in jobs.search(page_size=10)["jobs"])
        cases = [("jobs_search", {}), ("jobs_search", {"page_size": 20}),
                 ("jobs_search", {"page_size": 20, "offset": offset}),
                 ("jobs_search", {"city": "杭州", "graduation_year": "2027届", "major": "计算机类", "education": "硕士"}),
                 ("jobs_search", {"city": "上海", "job_category": "技术/研发", "deadline_within_days": 14,
                                  "sort": "deadline_asc", "page_size": 20}),
                 ("jobs_stats", {"group_by": "city"}), ("jobs_stats", {"group_by": "company", "top": 100}),
                 ("jobs_detail", {"ids": ids})]
        sizes = [measure(qz, tool, args) for tool, args in cases]
        rss["after_measure_mb"] = round(rss_mb(qz.proc.pid))
        tools_text = json.dumps(tools, ensure_ascii=False)
        meta = {"tools": [t["name"] for t in tools["tools"]], "tools_list_bytes": len(tools_text.encode()),
                "tools_list_rough_tokens": rough_tokens(tools_text),
                "anyOf_oneOf_allOf": sum(tools_text.count(k) for k in ('"anyOf"', '"oneOf"', '"allOf"')),
                "outputSchema_present": any("outputSchema" in t for t in tools["tools"]),
                "instructions": initialize.get("instructions"), "first_call_ms_including_build": first_call_ms,
                "truncated_page_offset": offset, "uvicorn_rss": rss}
    finally:
        qz.stop()
    H.TMP.mkdir(parents=True, exist_ok=True)
    bench_path = H.TMP / "bench-fixture-measure.json"
    bench_path.write_text(json.dumps(BENCH_FIXTURE, ensure_ascii=False))
    bench = H.Server("bench", bench_path=bench_path, label="measure-bench").start()
    try:
        bench_tools = bench.rpc("tools/list")
        write("tools_list_v4.bench.json", bench_tools)
        text = json.dumps(bench_tools)
        meta["bench_tools"] = [t["name"] for t in bench_tools["tools"]]
        meta["bench_anyOf_oneOf_allOf"] = sum(text.count(k) for k in ('"anyOf"', '"oneOf"', '"allOf"'))
        meta["bench_search_ok"] = bench.out("bench_search", {})["total"] == 2
    finally:
        bench.stop()
        bench_path.unlink(missing_ok=True)
    return meta, sizes


def inprocess_part():
    from qiuzhao.tools import Jobs
    builds = []
    for _ in range(3):
        jobs = Jobs(H.JOBS_PATH, today=date.fromisoformat(H.TODAY))
        started = time.perf_counter()
        jobs.dataset()
        builds.append(round(time.perf_counter() - started, 2))
    started = time.perf_counter()
    for _ in range(1000):
        jobs.dataset()
    cached_lookup_us = round((time.perf_counter() - started) * 1000, 3)  # 1000 calls in ms == µs per call
    queries = {"search_default": ("search", {}), "search_page_size_20": ("search", {"page_size": 20}),
               "search_city_year": ("search", {"city": "北京", "graduation_year": "2027届"}),
               "search_keyword": ("search", {"keyword": "算法"}),
               "search_q01": ("search", {"city": "杭州", "graduation_year": "2027届", "major": "计算机类", "education": "硕士"}),
               "search_deadline": ("search", {"recruitment_type": "校园招聘", "deadline_within_days": 7, "sort": "deadline_asc"}),
               "stats_total": ("stats", {}), "stats_city": ("stats", {"group_by": "city"}),
               "stats_company": ("stats", {"group_by": "company"}),
               "detail_10": ("detail", {"ids": ",".join(it["id"] for it in jobs.dataset().items[:10])})}
    latency = {}
    for name, (op, args) in queries.items():
        times = []
        for _ in range(9):
            started = time.perf_counter()
            getattr(jobs, op)(**args)
            times.append((time.perf_counter() - started) * 1000)
        latency[name] = round(statistics.median(times), 1)
    del jobs
    gc.collect()
    tracemalloc.start()
    jobs = Jobs(H.JOBS_PATH, today=date.fromisoformat(H.TODAY))
    jobs.dataset()
    gc.collect()
    retained, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"build_seconds_runs": builds, "cached_dataset_lookup_us": cached_lookup_us,
            "query_latency_ms_median": latency, "python_heap_retained_mb": round(retained / 1e6),
            "python_heap_peak_during_build_mb": round(peak / 1e6),
            "jobs_json_bytes": H.JOBS_PATH.stat().st_size, "items": len(jobs.dataset().items)}


def main():
    meta, sizes = http_part()
    perf = inprocess_part()
    perf["uvicorn_rss"] = meta.pop("uvicorn_rss")
    perf["first_call_ms_including_build"] = meta.pop("first_call_ms_including_build")
    write("evidence/sizes_v4.json", {"meta": meta, "calls": sizes})
    write("evidence/perf_v4.json", perf)
    for s in sizes:
        print(f"{s['tool']:12} {json.dumps(s['arguments'], ensure_ascii=False)[:70]:72} body={s['http_body_bytes']:>7} "
              f"text={s['text_bytes']:>7} jobs={s['jobs_bytes']} returned={s['returned']} truncated={s['truncated']} "
              f"tokens~{s['rough_tokens']} {s['latency_ms_median']}ms")
    print(json.dumps(meta, ensure_ascii=False, indent=1)[:1500])
    print(json.dumps(perf, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
