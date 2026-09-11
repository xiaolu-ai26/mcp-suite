"""ASGI entrypoint: Streamable HTTP MCP plus a minimal redemption site.

One codebase, one product per process. MCP_PRODUCT selects which tool set, static
site and dataset this process serves; everything else (auth, metering, redemption)
is shared. Defaults keep the recruitment product byte-identical to its first release.
"""
from __future__ import annotations
import json
import os
import secrets
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware
from pydantic import Field
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
    job_category: Annotated[str | None, Field(description="岗位大类筛选，如技术/研发、产品、运营、设计、市场/营销、销售、职能/支持、金融、咨询、医疗/医药、制造/生产、科研、教育/培训、法律/合规、其他", max_length=50)] = None,
    graduation_year: Annotated[str | None, Field(description="毕业届别筛选，如2025届、2026届、2027届、未披露", max_length=20)] = None,
    major_category: Annotated[str | None, Field(description="专业大类筛选，如计算机类、电子信息类、金融经济类、机械制造类、医药生物类、管理类、文科类、理科类、设计艺术类、农业类、其他、未披露", max_length=20)] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 50,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    """按城市、专业、届别、关键词、企业、招聘类型、行业、地域、岗位大类、毕业届别、专业大类筛选官方岗位，含状态、截止日、原公告URL、数据截至时间。可用offset翻页。"""
    return jobs.search(city, major, cohort, keyword, limit, offset,
                       company=company, recruitment_type=recruitment_type,
                       industry=industry, region=region,
                       job_category=job_category, graduation_year=graduation_year,
                       major_category=major_category)


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
