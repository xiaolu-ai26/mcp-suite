"""ASGI entrypoint: Streamable HTTP MCP plus a minimal redemption site.

One codebase, one product per process. MCP_PRODUCT selects which tool set, static
site and dataset this process serves; everything else (auth, metering, redemption)
is shared. Defaults keep the recruitment product byte-identical to its first release.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware
from pydantic import Field
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from core.store import PLANS, AccessError, Store

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = os.environ.get("MCP_PRODUCT", "qiuzhao")
PRODUCTS = {
    "qiuzhao": {
        "static": ROOT / "core" / "static",
        "base": "https://savegems.top/qiuzhao",
        "title": "秋招国央企岗位库",
        "instructions": "仅提供公开官方公告中的岗位事实。必须保留原公告链接及数据截至时间。未披露条件为空，不推断录取资格；岗位状态以原公告为准。",
        "tools": {"jobs_search", "jobs_deadlines", "jobs_detail"},
    },
    "bench": {
        "static": ROOT / "bench" / "static",
        "base": "https://savegems.top/bench",
        "title": "AI 赛道爆款拆解库",
        "instructions": "只提供公开内容链接、原标题与原创拆解标签、原创拆解结论及观察日期。不提供笔记正文、逐字稿、图片或视频，不提供精确互动数据；粉丝量级只给区间，破圈程度只给分级词。未记录的字段为空，不推断、不补写。",
        "tools": {"bench_search", "bench_detail", "bench_taxonomy"},
    },
}
if PRODUCT not in PRODUCTS:
    raise SystemExit(f"未知产品 MCP_PRODUCT={PRODUCT}")
CONFIG = PRODUCTS[PRODUCT]
STATIC = CONFIG["static"]
TOOLS = CONFIG["tools"]
PUBLIC_BASE = os.environ.get("MCP_PUBLIC_BASE_URL", CONFIG["base"]).rstrip("/")
CODE_PREFIXES = tuple(sorted(p["code_prefix"] for p in PLANS.values() if p["product"] == PRODUCT))
store = Store(os.environ.get("MCP_DB_PATH", ROOT / "private" / "access.sqlite3"))
mcp = FastMCP(CONFIG["title"], instructions=CONFIG["instructions"])

jobs = bench = None
if PRODUCT == "qiuzhao":
    from qiuzhao.tools import Jobs
    jobs = Jobs(os.environ.get("MCP_JOBS_PATH", ROOT / "qiuzhao" / "data" / "jobs.json"))
else:
    from bench.tools import Bench
    bench = Bench(os.environ.get("MCP_BENCH_PATH", ROOT / "bench" / "data" / "bench.json"))


def bearer(headers):
    value = headers.get("authorization", "")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 200:
        raise AccessError("请在请求头配置 Authorization: Bearer 你的API key。")
    return token


class MeterTools(Middleware):
    async def on_call_tool(self, context, call_next):
        if context.message.name not in TOOLS:
            raise ToolError("未知工具，请刷新工具列表。")
        try:
            token = bearer(get_http_request().headers)
            quota = store.consume(token, PRODUCT, context.message.name)
        except AccessError as exc:
            raise ToolError(str(exc)) from None
        result = await call_next(context)
        # Keep protocol wrapping untouched. Account state is available through /usage.
        return result


mcp.add_middleware(MeterTools())


def jobs_search(
    city: Annotated[str | None, Field(description="城市，如北京；未披露城市不会猜测", max_length=100)] = None,
    major: Annotated[str | None, Field(description="专业关键词", max_length=100)] = None,
    cohort: Annotated[str | None, Field(description="公告中明确写出的届别，如2027", max_length=100)] = None,
    keyword: Annotated[str | None, Field(description="单位/签约主体/岗位关键词", max_length=200)] = None,
    company: Annotated[str | None, Field(description="企业/单位名称关键词，如中国邮政；在recruitment_unit等企业主体字段中做包含匹配", max_length=100)] = None,
    recruitment_type: Annotated[str | None, Field(description="招聘类型，如校园招聘；未披露类型不推断", max_length=50)] = None,
    industry: Annotated[str | None, Field(description="企业主体行业筛选（基于招聘单位所属行业）；当前数据集无企业行业字段，此筛选暂返回空结果，待数据管线补充后启用", max_length=100)] = None,
    region: Annotated[str | None, Field(description="地域/城市关键词，如北京；在岗位城市字段中做包含匹配", max_length=100)] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 50,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    """按城市、专业、届别、关键词、企业、招聘类型、行业、地域筛选官方岗位，含状态、截止日、原公告URL、数据截至时间。可用offset翻页。"""
    return jobs.search(city, major, cohort, keyword, limit, offset,
                       company=company, recruitment_type=recruitment_type,
                       industry=industry, region=region)


def jobs_deadlines(
    days: Annotated[int, Field(ge=1, le=366, description="未来N天（含今天）")] = 7,
    limit: Annotated[int, Field(ge=1, le=100)] = 100,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    """未来N天内明确截止且有效的岗位，按截止日期倒排；不混入招满即止/未披露截止日。"""
    return jobs.deadlines(days, limit, offset)


def jobs_detail(id: Annotated[str, Field(min_length=1, max_length=200, description="jobs_search返回的岗位id")]) -> dict:
    """返回岗位全部业务字段、原公告URL与数据截至时间；内部证据文件路径不暴露。"""
    return jobs.detail(id)


def bench_search(
    topic: Annotated[str | None, Field(description="选题分类或来源关键词，如 AI工具、AI变现、Codex", max_length=60)] = None,
    format: Annotated[str | None, Field(description="内容形式：图文 或 视频", max_length=20)] = None,
    tag: Annotated[str | None, Field(description="标签：标题公式 / 内容角度 / 封面版式 / 话题词；取值见 bench_taxonomy", max_length=60)] = None,
    platform: Annotated[str | None, Field(description="平台，如 小红书、抖音、视频号、TikTok", max_length=20)] = None,
    time_window: Annotated[str | None, Field(description="发布时间窗：90d 表示近90天，或 2026 / 2026-08。约一半记录未公开发布时间，带时间窗会被排除", max_length=20)] = None,
    keyword: Annotated[str | None, Field(description="在原标题与拆解结论中搜关键词", max_length=100)] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    """按选题、形式、标签、平台、时间窗筛选爆款记录，返回公开链接、原标题、原创标签与原创拆解结论、观察日期与数据截至时间。可用offset翻页。"""
    return bench.search(topic, format, tag, platform, time_window, keyword, limit, offset)


def bench_detail(id: Annotated[str, Field(min_length=1, max_length=200, description="bench_search返回的记录id")]) -> dict:
    """返回单条记录的全部业务字段与公开链接；不含正文、逐字稿、图片、视频与精确互动数据。"""
    return bench.detail(id)


def bench_taxonomy() -> dict:
    """返回选题分类、标题公式、封面版式、内容角度等标签体系及各类记录数量，并说明哪些维度本期未标注。"""
    return bench.taxonomy()


REGISTRY = {"jobs_search": jobs_search, "jobs_deadlines": jobs_deadlines, "jobs_detail": jobs_detail,
            "bench_search": bench_search, "bench_detail": bench_detail, "bench_taxonomy": bench_taxonomy}
for _name in sorted(TOOLS):
    mcp.tool()(REGISTRY[_name])


@mcp.custom_route("/", methods=["GET"])
async def index(request: Request):
    return FileResponse(STATIC / "index.html", media_type="text/html")


@mcp.custom_route("/guide", methods=["GET"])
async def guide(request: Request):
    return FileResponse(STATIC / "guide.html", media_type="text/html")


@mcp.custom_route("/site.css", methods=["GET"])
async def style(request: Request):
    return FileResponse(STATIC / "site.css", media_type="text/css")


@mcp.custom_route("/app.js", methods=["GET"])
async def script(request: Request):
    return FileResponse(STATIC / "app.js", media_type="text/javascript")


@mcp.custom_route("/config", methods=["GET"])
async def config(request: Request):
    return JSONResponse({"mcp_url": PUBLIC_BASE + "/mcp", "guide_url": PUBLIC_BASE + "/guide"})


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request):
    try:
        if PRODUCT == "qiuzhao":
            rows, cutoff = jobs.load()
            return JSONResponse({"status": "ok", "jobs": len(rows), "data_as_of": cutoff})
        rows, cutoff, _ = bench.load()
        return JSONResponse({"status": "ok", "records": len(rows), "data_as_of": cutoff})
    except (ValueError, OSError):
        return JSONResponse({"status": "data_unavailable"}, status_code=503)


@mcp.custom_route("/redeem", methods=["POST"])
async def redeem(request: Request):
    # Same-origin browser request; no CORS and no credential-bearing URLs.
    origin = request.headers.get("origin")
    expected = urlsplit(PUBLIC_BASE)
    allowed = {f"{expected.scheme}://{expected.netloc}", str(request.base_url).rstrip("/")}
    if origin and origin not in allowed:
        return JSONResponse({"error": "请在本服务兑换页提交。"}, status_code=403)
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        return JSONResponse({"error": "请求格式必须为JSON。"}, status_code=415)
    try:
        body = b""
        async for chunk in request.stream():
            body += chunk
            if len(body) > 1024:
                return JSONResponse({"error": "请求过大。"}, status_code=413)
        data = json.loads(body)
        if not isinstance(data, dict) or not isinstance(data.get("code"), str):
            raise ValueError
        # Reject another product's code before touching it, so it is never burned here.
        if not data["code"].strip().upper().startswith(CODE_PREFIXES):
            raise AccessError("兑换码无效，请检查输入。", 400)
        result = store.redeem(data["code"])
        result.update({"mcp_url": PUBLIC_BASE + "/mcp", "guide_url": PUBLIC_BASE + "/guide"})
        return JSONResponse(result)
    except (ValueError, json.JSONDecodeError):
        return JSONResponse({"error": "请输入有效兑换码。"}, status_code=400)
    except AccessError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status)


@mcp.custom_route("/usage", methods=["GET"])
async def usage(request: Request):
    try:
        result = store.authorize(bearer(request.headers), PRODUCT)
        result.pop("key_id")
        return JSONResponse(result)
    except AccessError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status)


class Guard:
    """Authenticate every MCP HTTP request; charge only actual tool invocation."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        async def secure_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([(b"cache-control", b"no-store"), (b"referrer-policy", b"no-referrer"),
                                (b"x-content-type-options", b"nosniff"),
                                (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")])
                message["headers"] = headers
            await send(message)
        if scope["path"].rstrip("/") == "/mcp":
            request = Request(scope)
            try:
                store.authorize(bearer(request.headers), PRODUCT)
            except AccessError as exc:
                response = JSONResponse({"error": str(exc)}, status_code=exc.status,
                                        headers={"WWW-Authenticate": "Bearer"} if exc.status == 401 else None)
                return await response(scope, receive, secure_send)
        return await self.app(scope, receive, secure_send)


app = Guard(mcp.http_app(path="/mcp", json_response=True, stateless_http=True))
