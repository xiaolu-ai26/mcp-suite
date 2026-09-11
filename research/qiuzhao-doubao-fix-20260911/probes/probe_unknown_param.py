from __future__ import annotations
import asyncio, json, re
from typing import Annotated, Literal
from fastmcp import FastMCP, Client
from pydantic import BeforeValidator, Field

NoneToEmpty = BeforeValidator(lambda v: "" if v is None else v)
def norm_year(v):
    if v is None: return ""
    if isinstance(v, int) and not isinstance(v, bool): v = str(v)
    if isinstance(v, str):
        s = v.strip()
        m = re.fullmatch(r"(20\d{2})\s*(届|年)?", s)
        if m: return f"{m.group(1)}届"
        return s
    return v
YearNorm = BeforeValidator(norm_year)

mcp = FastMCP("probe")
@mcp.tool()
def t(keyword: Annotated[str, NoneToEmpty, Field(description="kw", max_length=200)] = "",
      cat: Annotated[Literal["", "产品", "技术/研发"], NoneToEmpty, Field(description="c")] = "",
      year: Annotated[Literal["", "2027届", "未披露"], YearNorm, Field(description="y")] = "",
      limit: Annotated[int, Field(ge=1, le=100)] = 10) -> dict:
    return {"keyword": keyword, "cat": cat, "year": year, "limit": limit}

async def main():
    async with Client(mcp) as c:
        tools = await c.list_tools()
        print(json.dumps(tools[0].inputSchema, ensure_ascii=False))
        for args in [{}, {"keyword": None, "cat": None, "year": None}, {"keyword": "x", "cat": "产品", "year": 2027},
                     {"year": "2027"}, {"year": " 2027届 "}, {"keyword": "x", "unknown_param": "zzz"}, {"cat": "产品经理"}]:
            try:
                r = await c.call_tool("t", args, raise_on_error=False)
                print("ARGS", args, "->", "isError" if r.is_error else "", r.structured_content if not r.is_error else r.content[0].text[:300])
            except Exception as e:
                print("ARGS", args, "-> EXC", type(e).__name__, str(e)[:300])
asyncio.run(main())
