"""ASGI entrypoint: Streamable HTTP MCP plus a minimal redemption site."""
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

from core.store import AccessError, Store
from qiuzhao.tools import Jobs

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "core" / "static"
PUBLIC_BASE = os.environ.get("MCP_PUBLIC_BASE_URL", "https://savegems.top/qiuzhao").rstrip("/")
store = Store(os.environ.get("MCP_DB_PATH", ROOT / "private" / "access.sqlite3"))
jobs = Jobs(os.environ.get("MCP_JOBS_PATH", ROOT / "qiuzhao" / "data" / "jobs.json"))
TOOLS = {"jobs_search", "jobs_deadlines", "jobs_detail"}
mcp = FastMCP("秋招国央企岗位库", instructions="仅提供公开官方公告中的岗位事实。必须保留原公告链接及数据截至时间。未披露条件为空，不推断录取资格；岗位状态以原公告为准。")


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
            quota = store.consume(token, "qiuzhao", context.message.name)
        except AccessError as exc:
            raise ToolError(str(exc)) from None
        result = await call_next(context)
        # Keep protocol wrapping untouched. Account state is available through /usage.
        return result


mcp.add_middleware(MeterTools())


@mcp.tool()
def jobs_search(
    city: Annotated[str | None, Field(description="城市，如北京；未披露城市不会猜测", max_length=100)] = None,
    major: Annotated[str | None, Field(description="专业关键词", max_length=100)] = None,
    cohort: Annotated[str | None, Field(description="公告中明确写出的届别，如2027", max_length=100)] = None,
    keyword: Annotated[str | None, Field(description="单位/签约主体/岗位关键词", max_length=200)] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 50,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    """按城市、专业、届别、关键词筛选官方岗位，含状态、截止日、原公告URL、数据截至时间。可用offset翻页。"""
    return jobs.search(city, major, cohort, keyword, limit, offset)


@mcp.tool()
def jobs_deadlines(
    days: Annotated[int, Field(ge=1, le=366, description="未来N天（含今天）")] = 7,
    limit: Annotated[int, Field(ge=1, le=100)] = 100,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    """未来N天内明确截止且有效的岗位，按截止日期倒排；不混入招满即止/未披露截止日。"""
    return jobs.deadlines(days, limit, offset)


@mcp.tool()
def jobs_detail(id: Annotated[str, Field(min_length=1, max_length=200, description="jobs_search返回的岗位id")]) -> dict:
    """返回岗位全部业务字段、原公告URL与数据截至时间；内部证据文件路径不暴露。"""
    return jobs.detail(id)


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
        rows, cutoff = jobs.load()
        return JSONResponse({"status": "ok", "jobs": len(rows), "data_as_of": cutoff})
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
        result = store.authorize(bearer(request.headers))
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
                store.authorize(bearer(request.headers))
            except AccessError as exc:
                response = JSONResponse({"error": str(exc)}, status_code=exc.status,
                                        headers={"WWW-Authenticate": "Bearer"} if exc.status == 401 else None)
                return await response(scope, receive, secure_send)
        return await self.app(scope, receive, secure_send)


app = Guard(mcp.http_app(path="/mcp", json_response=True, stateless_http=True))
