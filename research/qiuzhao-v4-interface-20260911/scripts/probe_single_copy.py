"""FastMCP 单份返回实测。

进程内 Client（FastMCPTransport），不起 HTTP、不连服务器、不用 token、不 import 任何代码树，
只用 ~/Projects/mcp-suite/.venv 里已安装的 fastmcp（只读使用，不写 __pycache__）。

用法（在 qiuzhao-v4-interface-20260911/ 下）：
  PYTHONDONTWRITEBYTECODE=1 ~/Projects/mcp-suite/.venv/bin/python -W ignore scripts/probe_single_copy.py
输出：evidence/probe_single_copy.json

对比三种写法返回同一份 v4 默认 jobs_search 结果（10 条）时，CallToolResult 在线上传输的字节数：
  a_default_dict            现状：函数返回 dict → content 文本 + structuredContent 两份
  b_text_only               方案 A：output_schema=None + ToolResult(content=[TextContent(json)])
  c_structured_plus_summary 方案 B：output_schema=None + ToolResult(content=[一句摘要], structured_content=结果)
"""
import asyncio
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4lib as L  # noqa: E402

import fastmcp  # noqa: E402
from fastmcp import Client, FastMCP  # noqa: E402
from fastmcp.tools.tool import ToolResult  # noqa: E402
from mcp.types import TextContent  # noqa: E402

items, as_of = L.build()
payload = L.jobs_search(items, as_of)
text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
summary = (f"共 {payload['total']} 条，本页 {payload['returned']} 条，has_next={payload['has_next']}；"
           "完整结果在 structuredContent。")

mcp = FastMCP("probe")


@mcp.tool()
def a_default_dict() -> dict:
    """现状写法"""
    return payload


@mcp.tool(output_schema=None)
def b_text_only() -> ToolResult:
    """方案 A"""
    return ToolResult(content=[TextContent(type="text", text=text)])


@mcp.tool(output_schema=None)
def c_structured_plus_summary() -> ToolResult:
    """方案 B"""
    return ToolResult(content=[TextContent(type="text", text=summary)], structured_content=payload)


async def main():
    out = {"fastmcp_version": fastmcp.__version__, "payload_json_bytes": len(text.encode()), "tools": {}}
    async with Client(mcp) as client:
        listed = await client.list_tools()
        for t in listed:
            out["tools"][t.name] = {"tools_list_outputSchema": t.outputSchema}
        for name in ("a_default_dict", "b_text_only", "c_structured_plus_summary"):
            r = await client.call_tool_mcp(name, {})
            wire = r.model_dump_json(by_alias=True, exclude_none=True)
            texts = [b.text for b in r.content if getattr(b, "type", "") == "text"]
            out["tools"][name].update({
                "isError": r.isError,
                "result_bytes_on_wire": len(wire.encode()),
                "content_blocks": len(r.content),
                "content_text_bytes": sum(len(t.encode()) for t in texts),
                "content_text_is_full_result": any(t == text or (t.startswith("{") and json.loads(t) == payload) for t in texts),
                "has_structuredContent": r.structuredContent is not None,
                "structuredContent_bytes": L.nbytes(r.structuredContent) if r.structuredContent is not None else 0,
            })
    (L.ROOT / "evidence" / "probe_single_copy.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))


asyncio.run(main())
