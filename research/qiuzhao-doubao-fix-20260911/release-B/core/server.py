"""ASGI entrypoint: Streamable HTTP MCP plus a minimal redemption site.

One codebase, one product per process. MCP_PRODUCT selects which tool set, static
site and dataset this process serves; everything else (auth, metering, redemption)
is shared. Defaults keep the recruitment product byte-identical to its first release.
"""
from __future__ import annotations
import json
import logging
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware
from pydantic import BeforeValidator, Field
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse

from core.store import PLANS, AccessError, Store
from core.distribution import DistributionStore

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = os.environ.get("MCP_PRODUCT", "qiuzhao")
PRODUCTS = {
    "qiuzhao": {
        "static": ROOT / "core" / "static",
        "base": "https://savegems.top/qiuzhao",
        "title": "秋招国央企岗位库",
        "instructions": "仅提供公开官方公告中的岗位事实。必须保留原公告链接及数据截至时间。未披露条件为空，不推断录取资格；岗位状态以原公告为准。返回里的 applied_filters 若与你传入的条件不一致，说明客户端没有传递参数，应告知用户，不要重复同样的调用。",
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
# 独立的分销账本（绝不写 access.sqlite3）；首次调用时才建库建表。
dist = DistributionStore(os.environ.get("MCP_DIST_DB_PATH", "/var/lib/mcp-suite/distribution.db"))
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


# One stderr line per tool call (journald under systemd): tool name, sorted argument names
# and a truncated User-Agent. Never the Authorization header, the key, or any argument value.
call_log = logging.getLogger("mcp_suite.tool_calls")
if not call_log.handlers:
    _call_handler = logging.StreamHandler(sys.stderr)
    _call_handler.setFormatter(logging.Formatter("%(message)s"))
    call_log.addHandler(_call_handler)
    call_log.setLevel(logging.INFO)
    call_log.propagate = False


def log_tool_call(name, arguments):
    try:
        try:
            agent = get_http_request().headers.get("user-agent", "")
        except RuntimeError:
            agent = ""
        names = sorted(str(key)[:64] for key in (arguments or {}))[:40]
        call_log.info("mcp_tool_call %s", json.dumps(
            {"tool": str(name)[:64], "args": names, "ua": agent[:100]}, ensure_ascii=False))
    except Exception:
        pass  # Observability must never break a paid call.


class MeterTools(Middleware):
    async def on_call_tool(self, context, call_next):
        log_tool_call(context.message.name, context.message.arguments)
        if context.message.name not in TOOLS:
            raise ToolError("未知工具，请刷新工具列表。")
        try:
            token = bearer(get_http_request().headers)
            quota = store.consume(token, PRODUCT, context.message.name)
        except AccessError as exc:
            raise ToolError(str(exc)) from None
        if context.message.name == "jobs_search" and LEGACY_JOBS_ARGS.keys() & set(context.message.arguments or {}):
            arguments, mapped, ignored = map_legacy_jobs_args(context.message.arguments)
            call_log.info("mcp_legacy_args %s", json.dumps(
                {"tool": "jobs_search", "mapped": mapped, "ignored": ignored}, ensure_ascii=False))
            context = context.copy(message=context.message.model_copy(update={"arguments": arguments}))
        result = await call_next(context)
        # Keep protocol wrapping untouched. Account state is available through /usage.
        return result


mcp.add_middleware(MeterTools())


# Strict-schema clients (e.g. 豆包) drop any parameter whose schema has no top-level "type",
# which is what `str | None` renders as (anyOf string/null). Optional text parameters are
# therefore plain strings defaulting to "", and an explicit null still validates as "".
NoneToEmpty = BeforeValidator(lambda v: "" if v is None else v)


def _choice(value):
    return "" if value is None else (value.strip() if isinstance(value, str) else value)


def _graduation_year(value):
    """None -> ""; 2027 / "2027" / "2027届" / "2027年" -> "2027届"; anything else is left as is."""
    value = _choice(value)
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if isinstance(value, str):
        match = re.fullmatch(r"(20\d{2})\s*(?:届|年)?", value)
        if match:
            return f"{match.group(1)}届"
    return value


ChoiceInput = BeforeValidator(_choice)
GraduationYearInput = BeforeValidator(_graduation_year)
# Exactly the values of job_category_normalized / graduation_year_normalized in the dataset.
JobCategory = Literal["", "技术/研发", "产品", "运营", "设计", "市场/营销", "销售", "职能/支持", "金融",
                      "咨询", "医疗/医药", "制造/生产", "科研", "教育/培训", "法律/合规", "其他"]
GraduationYear = Literal["", "2027届", "2026届", "2025届", "未披露"]

# jobs_search names removed from the MCP schema in release B. FastMCP 2.14.7 rejects unknown
# arguments ("Unexpected keyword argument") instead of ignoring them, so MeterTools maps old
# callers here: old -> new, only when the new one was not given. Names are logged, never values.
LEGACY_JOBS_ARGS = {"cohort": "graduation_year", "region": "city", "major_category": "major"}


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def map_legacy_jobs_args(arguments):
    args = dict(arguments or {})
    mapped, ignored = {}, []
    for old, new in LEGACY_JOBS_ARGS.items():
        if old not in args:
            continue
        value = args.pop(old)
        if not _blank(value) and _blank(args.get(new)):
            # cohort goes through the same normalization as graduation_year (2027 -> 2027届).
            args[new] = _graduation_year(value) if new == "graduation_year" else value
            mapped[old] = new
        else:
            ignored.append(old)
    return args, mapped, sorted(ignored)


def jobs_search(
    city: Annotated[str, NoneToEmpty, Field(description="城市，如北京；未披露城市不会猜测", max_length=100)] = "",
    major: Annotated[str, NoneToEmpty, Field(description="专业关键词或专业大类，如计算机、会计，或计算机类、电子信息类、金融经济类、机械制造类、管理类、文科类、医药生物类、理科类、农业类、设计艺术类；同时匹配专业要求原文、专业标签和归一化专业大类", max_length=100)] = "",
    keyword: Annotated[str, NoneToEmpty, Field(description="单位/签约主体/岗位关键词", max_length=200)] = "",
    company: Annotated[str, NoneToEmpty, Field(description="企业/单位名称关键词，如中国邮政；在recruitment_unit等企业主体字段中做包含匹配", max_length=100)] = "",
    recruitment_type: Annotated[str, NoneToEmpty, Field(description="招聘类型，如校园招聘；未披露类型不推断", max_length=50)] = "",
    industry: Annotated[str, NoneToEmpty, Field(description="企业主体行业筛选，在招聘单位所属行业字段（industry、industry_tags）中做包含匹配；常见取值：互联网/科技、国企/央企、制造/工业、能源/电力、金融、医药/医疗", max_length=100)] = "",
    job_category: Annotated[JobCategory, ChoiceInput, Field(description="岗位大类，按归一化岗位大类精确匹配，取值：技术/研发、产品、运营、设计、市场/营销、销售、职能/支持、金融、咨询、医疗/医药、制造/生产、科研、教育/培训、法律/合规、其他；不筛选时不传")] = "",
    graduation_year: Annotated[GraduationYear, GraduationYearInput, Field(description="毕业届别，按归一化届别精确匹配，取值：2027届、2026届、2025届、未披露；写2027会按2027届处理；不筛选时不传")] = "",
    limit: Annotated[int, Field(ge=1, le=100, description="每页条数，默认10，最大100")] = 10,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    """按城市、专业、关键词、企业、招聘类型、行业、岗位大类、毕业届别筛选官方岗位，含状态、截止日、原公告URL、数据截至时间。找某类岗位用 job_category，找具体岗位名或单位用 keyword，找公司用 company。默认每次返回10条，可用offset翻页。返回的applied_filters是服务端实际使用的筛选条件。"""
    # Empty string means "not given"; the data layer keeps receiving None exactly as before.
    return jobs.search(city or None, major or None, None, keyword or None, limit, offset,
                       company=company or None, recruitment_type=recruitment_type or None,
                       industry=industry or None, job_category=job_category or None,
                       graduation_year=graduation_year or None)


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
    topic: Annotated[str, NoneToEmpty, Field(description="选题分类或来源关键词，如 AI工具、AI变现、Codex", max_length=60)] = "",
    format: Annotated[str, NoneToEmpty, Field(description="内容形式：图文 或 视频", max_length=20)] = "",
    tag: Annotated[str, NoneToEmpty, Field(description="标签：标题公式 / 内容角度 / 封面版式 / 话题词；取值见 bench_taxonomy", max_length=60)] = "",
    platform: Annotated[str, NoneToEmpty, Field(description="平台，如 小红书、抖音、视频号、TikTok", max_length=20)] = "",
    time_window: Annotated[str, NoneToEmpty, Field(description="发布时间窗：90d 表示近90天，或 2026 / 2026-08。约一半记录未公开发布时间，带时间窗会被排除", max_length=20)] = "",
    keyword: Annotated[str, NoneToEmpty, Field(description="在原标题与拆解结论中搜关键词", max_length=100)] = "",
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    """按选题、形式、标签、平台、时间窗筛选爆款记录，返回公开链接、原标题、原创标签与原创拆解结论、观察日期与数据截至时间。可用offset翻页。"""
    # Type change only: "" means "not given" and the data layer keeps receiving None as before.
    return bench.search(topic or None, format or None, tag or None, platform or None,
                        time_window or None, keyword or None, limit, offset)


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
        ref = data.get("ref")
        if isinstance(ref, str) and ref.strip():
            try:
                plan_name = next((n for n, p in PLANS.items()
                                  if data["code"].strip().upper().startswith(p["code_prefix"])), None)
                if plan_name:
                    dist.record_referral(ref, plan_name, PLANS[plan_name]["price_cny"])
            except Exception:
                pass  # 分销记账失败不影响兑换主流程；ref 绝不透传回前端
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


@mcp.custom_route("/wechat-qr.png", methods=["GET"])
async def wechat_qr(request: Request):
    return FileResponse(STATIC / "wechat-qr.png")


@mcp.custom_route("/api/changelog", methods=["GET"])
async def changelog(request: Request):
    return FileResponse(STATIC / "changelog.json", media_type="application/json")


def _dist_admin_ok(request: Request) -> bool | JSONResponse:
    token = os.environ.get("MCP_DIST_ADMIN_TOKEN", "")
    if not token:
        return JSONResponse({"error": "分销统计接口未配置管理员令牌。"}, status_code=503)
    presented = request.headers.get("authorization", "")
    if presented.lower().startswith("bearer "):
        candidate = presented.partition(" ")[2].strip()
    else:
        candidate = request.query_params.get("token", "").strip()
    if not candidate or not secrets.compare_digest(candidate, token):
        return JSONResponse({"error": "未授权。"}, status_code=401)
    return True


@mcp.custom_route("/api/distribution/list", methods=["GET"])
async def distribution_list(request: Request):
    auth = _dist_admin_ok(request)
    if auth is not True:
        return auth
    # 只返回业务字段；账本本身从不存兑换码或 api key。
    return JSONResponse(dist.list_records())


@mcp.custom_route("/api/distribution/stats", methods=["GET"])
async def distribution_stats(request: Request):
    auth = _dist_admin_ok(request)
    if auth is not True:
        return auth
    return JSONResponse(dist.stats())


@mcp.custom_route("/admin", methods=["GET"])
async def admin_page(request: Request):
    html = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>管理后台 · 秋招岗位库</title>
  <link rel="stylesheet" href="./admin.css">
</head>
<body>
  <!-- 登录视图 -->
  <div id="login-view" class="login-wrap" hidden>
    <div class="login-card">
      <div class="brand">
        <span class="brand-mark">秋</span>
        <span class="brand-text"><b>秋招岗位库</b><small>管理后台</small></span>
      </div>
      <h1 class="serif">管理员登录</h1>
      <p class="sub">输入管理员令牌以进入后台。</p>
      <div class="field">
        <label for="token-input">管理员令牌</label>
        <input id="token-input" class="input mono" type="password" autocomplete="off" spellcheck="false" placeholder="Bearer Token">
      </div>
      <button id="login-btn" class="btn btn-primary btn-full" type="button">登录</button>
      <p id="login-msg" class="msg" role="status" aria-live="polite"></p>
      <div class="login-foot">
        <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 8 0v4"></path></svg>
        <span>令牌只保存在本标签页会话中，关闭即清除；仅用于接口鉴权，不写入网址或日志。</span>
      </div>
    </div>
  </div>

  <!-- 管理视图 -->
  <div id="app-view" hidden>
    <header class="topbar">
      <div class="topbar-inner">
        <div class="brand">
          <span class="brand-mark">秋</span>
          <span class="brand-text"><b>秋招岗位库</b><small>管理后台</small></span>
        </div>
        <div class="topbar-actions">
          <span class="tag-live"><i></i>已登录</span>
          <button id="refresh-btn" class="btn btn-ghost btn-sm" type="button">
            <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36"></path><path d="M21 4v5h-5"></path></svg>刷新
          </button>
          <button id="logout-btn" class="btn btn-ghost btn-sm" type="button">退出登录</button>
        </div>
      </div>
    </header>

    <main>
      <!-- 概览 -->
      <section class="section">
        <div class="sec-head">
          <div><p class="sec-index">§ 01 · 概览</p><h2 class="serif">兑换码与分销一览</h2></div>
          <p class="sec-note">数据实时读取，北京时间。</p>
        </div>
        <div class="stat-grid">
          <div class="card stat-card"><div class="label">总兑换码</div><div class="num" id="stat-total">—</div><div class="usage-bar"><span id="usage-fill"></span></div><div class="sub" id="usage-label">兑换率 —</div></div>
          <div class="card stat-card"><div class="label">已兑换</div><div class="num accent" id="stat-redeemed">—</div></div>
          <div class="card stat-card"><div class="label">未兑换</div><div class="num" id="stat-pending">—</div></div>
          <div class="card stat-card"><div class="label">今日新增</div><div class="num" id="stat-today-new">—</div><div class="sub">按创建时间计</div></div>
          <div class="card stat-card"><div class="label">今日兑换</div><div class="num" id="stat-today-redeemed">—</div><div class="sub">按兑换时间计</div></div>
        </div>
        <p class="subhead">分销</p>
        <div class="stat-grid">
          <div class="card stat-card"><div class="label">总推荐数</div><div class="num" id="dist-referrals">—</div></div>
          <div class="card stat-card"><div class="label">总佣金</div><div class="num money accent" id="dist-total">—</div></div>
          <div class="card stat-card"><div class="label">待结算佣金</div><div class="num money" id="dist-pending">—</div></div>
        </div>
      </section>

      <!-- 兑换码 -->
      <section class="section">
        <div class="sec-head">
          <div><p class="sec-index">§ 02 · 兑换码</p><h2 class="serif">生成与管理</h2></div>
          <p class="sec-note">系统只存哈希；明文兑换码仅在生成时显示一次。</p>
        </div>
        <div class="toolbar">
          <div class="field"><label for="gen-plan">套餐</label><select id="gen-plan" class="select"></select></div>
          <div class="field"><label for="gen-count">生成数量</label><input id="gen-count" class="input mono" type="number" value="1" min="1" max="100"></div>
          <button id="gen-btn" class="btn btn-primary" type="button">
            <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14"></path><path d="M5 12h14"></path></svg>生成兑换码
          </button>
        </div>
        <p id="gen-msg" class="msg" role="status" aria-live="polite"></p>
        <div id="gen-out" class="gen-out" hidden>
          <div class="gen-head"><b>本次生成的兑换码</b><button id="gen-copy-all" class="icon-btn" type="button" data-codes="">复制全部</button></div>
          <div id="gen-list" class="code-list"></div>
        </div>

        <div class="filter-row">
          <button class="chip-btn on" type="button" data-filter="all">全部</button>
          <button class="chip-btn" type="button" data-filter="pending">未兑换</button>
          <button class="chip-btn" type="button" data-filter="redeemed">已兑换</button>
          <span class="spacer"></span>
          <button id="codes-refresh" class="btn btn-ghost btn-sm" type="button">刷新列表</button>
        </div>
        <div class="table-wrap"><div class="table-scroll"><table>
          <thead><tr><th class="mono">兑换码</th><th>套餐</th><th>创建时间</th><th>状态</th><th>兑换时间</th><th>操作</th></tr></thead>
          <tbody id="codes-body"><tr><td colspan="6" class="state-row">加载中…</td></tr></tbody>
        </table></div></div>
      </section>

      <!-- 分销 -->
      <section class="section">
        <div class="sec-head">
          <div><p class="sec-index">§ 03 · 分销</p><h2 class="serif">推荐记录</h2></div>
          <button id="dist-refresh" class="btn btn-ghost btn-sm" type="button">刷新分销数据</button>
        </div>
        <div class="table-wrap"><div class="table-scroll"><table>
          <thead><tr><th>推荐人微信号</th><th>推荐时间</th><th>兑换状态</th><th>佣金</th></tr></thead>
          <tbody id="dist-body"><tr><td colspan="4" class="state-row">点击右上「刷新分销数据」加载</td></tr></tbody>
        </table></div></div>
      </section>
    </main>
  </div>

  <div id="toast" class="toast" role="status" aria-live="polite"></div>
  <script src="./admin.js"></script>
</body>
</html>
"""
    return HTMLResponse(html)

@mcp.custom_route("/admin.css", methods=["GET"])
async def admin_css(request: Request):
    return FileResponse(STATIC / "admin.css", media_type="text/css")


@mcp.custom_route("/admin.js", methods=["GET"])
async def admin_js(request: Request):
    return FileResponse(STATIC / "admin.js", media_type="text/javascript")


# 接入指南图片
@mcp.custom_route("/img/guide/doubao-1.png", methods=["GET"])
async def img_doubao_1(request: Request):
    return FileResponse(STATIC / "img/guide/doubao-1.png")


@mcp.custom_route("/img/guide/doubao-2.png", methods=["GET"])
async def img_doubao_2(request: Request):
    return FileResponse(STATIC / "img/guide/doubao-2.png")


@mcp.custom_route("/img/guide/workbuddy-1.png", methods=["GET"])
async def img_workbuddy_1(request: Request):
    return FileResponse(STATIC / "img/guide/workbuddy-1.png")


@mcp.custom_route("/img/guide/workbuddy-2.png", methods=["GET"])
async def img_workbuddy_2(request: Request):
    return FileResponse(STATIC / "img/guide/workbuddy-2.png")


@mcp.custom_route("/img/guide/qianwen-1.jpeg", methods=["GET"])
async def img_qianwen_1(request: Request):
    return FileResponse(STATIC / "img/guide/qianwen-1.jpeg")


@mcp.custom_route("/img/guide/qianwen-2.jpeg", methods=["GET"])
async def img_qianwen_2(request: Request):
    return FileResponse(STATIC / "img/guide/qianwen-2.jpeg")


@mcp.custom_route("/api/admin/stats", methods=["GET"])
async def admin_stats(request: Request):
    auth = _dist_admin_ok(request)
    if auth is not True:
        return auth
    with store.connect() as db:
        total = db.execute("SELECT COUNT(*) as c FROM redemption_codes").fetchone()["c"]
        redeemed = db.execute("SELECT COUNT(*) as c FROM redemption_codes WHERE redeemed_at IS NOT NULL").fetchone()["c"]
        pending = total - redeemed
    return JSONResponse({"total": total, "redeemed": redeemed, "pending": pending})


@mcp.custom_route("/api/admin/codes", methods=["GET"])
async def admin_codes(request: Request):
    auth = _dist_admin_ok(request)
    if auth is not True:
        return auth
    limit = int(request.query_params.get("limit", "100"))
    with store.connect() as db:
        rows = db.execute("SELECT code_hash, code_plain, plan, created_at, redeemed_at FROM redemption_codes ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        codes = [dict(r) for r in rows]
    return JSONResponse({"codes": codes})


@mcp.custom_route("/api/admin/delete_code", methods=["POST", "DELETE"])
async def admin_delete_code(request: Request):
    auth = _dist_admin_ok(request)
    if auth is not True:
        return auth
    body = await request.json()
    code_hash = body.get("code_hash", "")
    if not code_hash:
        return JSONResponse({"error": "缺少code_hash参数"}, status_code=400)
    success = store.delete_code(code_hash)
    if success:
        return JSONResponse({"success": True})
    else:
        return JSONResponse({"error": "删除失败：码不存在或已被兑换"}, status_code=400)


@mcp.custom_route("/api/admin/generate", methods=["GET", "POST"])
async def admin_generate(request: Request):
    auth = _dist_admin_ok(request)
    if auth is not True:
        return auth
    count = int(request.query_params.get("count", "1"))
    plan = request.query_params.get("plan", "qiuzhao-2026")
    codes = store.generate_codes(count, plan)
    return JSONResponse({"codes": codes})


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
