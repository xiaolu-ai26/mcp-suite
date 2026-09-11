"""Generate tools/list and default-call byte sizes from a real uvicorn process.

usage: python scripts/dump_tools_list.py <release-dir> <label>
  e.g. python scripts/dump_tools_list.py release-A A

Starts `uvicorn core.server:app` from <release-dir> for both products (qiuzhao on
data/jobs.json, bench on a 2-record fixture), with a throwaway access DB under tmp/,
and talks JSON-RPC over HTTP exactly like a remote client. Writes:
  tools_list_<label>.json        tools/list result, qiuzhao product
  tools_list_<label>.bench.json  tools/list result, bench product
  evidence/sizes_<label>.json    byte sizes of jobs_search responses
"""
import json
import os
import sys
from pathlib import Path

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"  # never drop __pycache__ into live-baseline
sys.dont_write_bytecode = True
WORKDIR = Path(__file__).resolve().parents[1]
release = (WORKDIR / sys.argv[1]).resolve()
label = sys.argv[2]
sys.path.insert(0, str(WORKDIR / "release-A" / "tests"))
sys.path.insert(0, str(release))

import _mcp_harness as harness  # noqa: E402
from conftest import BENCH_FIXTURE  # noqa: E402

harness.RELEASE = release


def write(name: str, obj) -> None:
    path = WORKDIR / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def measure(server, arguments):
    result, body = server.call("jobs_search", arguments, raw=True)
    content = result["structuredContent"]
    return {"arguments": arguments, "http_body_bytes": len(body),
            "structured_content_bytes": len(json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode()),
            "text_content_bytes": len(result["content"][0]["text"].encode()),
            "jobs_returned": len(content["jobs"]), "total": content["total"],
            "fields_per_job": sorted({len(job) for job in content["jobs"]}),
            "applied_filters": content.get("applied_filters", "(absent)")}


qz = harness.Server("qiuzhao").start()
try:
    instructions = qz.initialize().get("instructions")
    tools = qz.rpc("tools/list")
    write(f"tools_list_{label}.json", tools)
    search = next(t for t in tools["tools"] if t["name"] == "jobs_search")
    sizes = {"label": label, "release": release.name, "instructions": instructions,
             "anyOf_count_in_tools_list": json.dumps(tools).count('"anyOf"'),
             "jobs_search_params": list(search["inputSchema"]["properties"]),
             "default_call": measure(qz, {}),
             "limit_10_call": measure(qz, {"limit": 10}),
             "limit_50_call": measure(qz, {"limit": 50})}
finally:
    qz.stop()

harness.TMP.mkdir(exist_ok=True)
bench_path = harness.TMP / f"bench-fixture-{label}.json"
bench_path.write_text(json.dumps(BENCH_FIXTURE, ensure_ascii=False))
bench = harness.Server("bench", bench_path=bench_path).start()
try:
    bench_tools = bench.rpc("tools/list")
    write(f"tools_list_{label}.bench.json", bench_tools)
    sizes["bench_anyOf_count_in_tools_list"] = json.dumps(bench_tools).count('"anyOf"')
finally:
    bench.stop()
    bench_path.unlink(missing_ok=True)

write(f"evidence/sizes_{label}.json", sizes)
print(json.dumps({k: v for k, v in sizes.items() if k != "instructions"}, ensure_ascii=False, indent=2))
