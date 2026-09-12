"""Screenshots and UI checks for research/codes-kind-20260912 (local only, nothing remote).

Starts core.server (MCP_PRODUCT=qiuzhao) under uvicorn on 127.0.0.1 with every path in a fresh temp
directory (MCP_DB_PATH, distribution DB, call logs, admin log), seeds it through core.store, then
drives the redemption page and the admin page with Playwright (headless Chromium).

The admin token comes from $CODES_KIND_ADMIN_TOKEN or is generated in memory. It reaches the server
only through the child's environment and the page only by typing into the login field; it is never
written to a file or printed. Codes and keys live only in the temp DB, which is deleted at the end.

Output in research/codes-kind-20260912/evidence/: PNG screenshots and ui-checks.json (visible texts,
dialog texts, HTTP statuses, /api/pricing bodies; codes masked).
Run from the repo root:  <venv>/bin/python research/codes-kind-20260912/scripts/shots.py
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from core.store import Store  # noqa: E402

OUT = ROOT / "research" / "codes-kind-20260912" / "evidence"
PLAN = "qiuzhao-2026"
CODE_RE = re.compile(r"QZ-[0-9A-F]{4,}…?")


def masked(value):
    if isinstance(value, str):
        return CODE_RE.sub("QZ-…", value)
    if isinstance(value, list):
        return [masked(v) for v in value]
    if isinstance(value, dict):
        return {k: masked(v) for k, v in value.items()}
    return value


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(tmp: Path, token: str):
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("MCP_") and k != "CODES_KIND_ADMIN_TOKEN"}
    env.update(MCP_PRODUCT="qiuzhao", MCP_DB_PATH=str(tmp / "access.sqlite3"), MCP_DIST_DB_PATH=str(tmp / "dist.db"),
               MCP_JOBS_PATH=str(tmp / "jobs-not-needed.json"), MCP_CALL_LOG_DIR=str(tmp / "call_logs"),
               MCP_ADMIN_LOG_PATH=str(tmp / "admin_actions.jsonl"), MCP_DIST_ADMIN_TOKEN=token,
               PYTHONDONTWRITEBYTECODE="1", PYTHONWARNINGS="ignore")
    log = open(tmp / "uvicorn.log", "wb")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "core.server:app", "--host", "127.0.0.1",
                             "--port", str(port), "--no-access-log"],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(300):
        if proc.poll() is not None:
            raise RuntimeError((tmp / "uvicorn.log").read_text()[-2000:])
        try:
            if httpx.get(base + "/config", trust_env=False).status_code == 200:
                return proc, log, base
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError("server did not start")


def sell_until(store: Store, sold: int) -> None:
    """Redeem fresh formal codes until `sold` formal codes have been redeemed."""
    need = sold - store.early_bird(PLAN)["sold"]
    if need > 0:
        for code in store.generate_codes(need, PLAN, "formal"):
            store.redeem(code)


def main() -> None:
    token = os.environ.get("CODES_KIND_ADMIN_TOKEN") or secrets.token_urlsafe(24)
    tmp = Path(tempfile.mkdtemp(prefix="codes-kind-shots-"))
    OUT.mkdir(parents=True, exist_ok=True)
    checks: dict = {"note": "Throwaway local DB; codes masked. Token never recorded.", "steps": []}
    proc = log = None

    def step(name, **data):
        checks["steps"].append({"step": name, **masked(data)})
        print("step", name)

    try:
        store = Store(tmp / "access.sqlite3")
        formal = store.generate_codes(5, PLAN, "formal")
        tests = store.generate_codes(4, PLAN, "test")
        for code in formal[:3]:
            store.redeem(code)
        test_keys = {code: store.redeem(code)["api_key"] for code in tests[:2]}
        proc, log, base = start_server(tmp, token)

        def pricing():
            return httpx.get(base + "/api/pricing", trust_env=False).json()

        def usage(key):
            return httpx.get(base + "/usage", headers={"Authorization": f"Bearer {key}"}, trust_env=False).status_code

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            console_errors: list[str] = []
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: console_errors.append(str(e)))
            dialogs: list[str] = []

            def answer(accept):
                def handler(dialog):
                    dialogs.append(dialog.message)
                    dialog.accept() if accept else dialog.dismiss()
                page.once("dialog", handler)

            def redeem_page(name):
                page.goto(base + "/")
                page.wait_for_function("() => !document.getElementById('tier-list').textContent.includes('正在读取')")
                visible = page.evaluate("""() => {
                  const t = id => { const e = document.getElementById(id); return e && !e.closest('[hidden]') ? e.textContent.trim() : null; };
                  return {chip: t('price-chip'), price: t('price-current'), standard: t('price-standard'),
                          status: t('price-status'),
                          tiers: [...document.querySelectorAll('#tier-list li')].map(li => ({
                            text: li.textContent.replace(/\\s+/g, ' ').trim(), class: li.className}))};
                }""")
                page.locator("#pricing").screenshot(path=str(OUT / f"{name}.png"))
                return visible

            def codes_table():
                return page.evaluate("""() => [...document.querySelectorAll('#codes-body tr')].map(tr => {
                  const td = [...tr.querySelectorAll('td')];
                  return td.length < 7 ? {state: tr.textContent.trim()} : {
                    kind: td[1].textContent.trim(), status: td[4].textContent.trim(),
                    delete_button: !!td[6].querySelector('button'), action: td[6].textContent.trim()};
                })""")

            def pick(filter_value=None, kind_value=None):
                if filter_value:
                    page.click(f".chip-btn[data-filter='{filter_value}']")
                if kind_value:
                    page.click(f".chip-btn[data-kind='{kind_value}']")

            codes_section = page.locator("main > section").nth(1)

            # 1. Redemption page after 3 redeemed formal codes.
            step("redeem page, 3 sold", pricing=pricing(), visible=redeem_page("01-redeem-sold3"))

            # 2. Admin login and overview.
            page.goto(base + "/admin")
            page.fill("#token-input", token)
            page.click("#login-btn")
            page.wait_for_function("() => document.getElementById('stat-early-sold').textContent.startsWith('已售')")
            page.wait_for_selector("#codes-body tr td .badge")
            overview = page.evaluate("""() => Object.fromEntries(['stat-total','stat-redeemed','stat-pending',
              'stat-formal-total','stat-formal-sub','stat-test-total','stat-test-sub','stat-early-sold','stat-early-sub']
              .map(id => [id, document.getElementById(id).textContent.trim()]))""")
            page.locator("main > section").nth(0).screenshot(path=str(OUT / "02-admin-overview.png"))
            step("admin overview", visible=overview)

            # 3-5. Filters: formal only, test only, test + redeemed (the two filters combine).
            pick(kind_value="formal")
            codes_section.screenshot(path=str(OUT / "03-admin-filter-formal.png"))
            step("filter formal", rows=codes_table())
            pick(kind_value="test")
            codes_section.screenshot(path=str(OUT / "04-admin-filter-test.png"))
            step("filter test", rows=codes_table())
            pick(filter_value="redeemed")
            codes_section.screenshot(path=str(OUT / "05-admin-filter-test-redeemed.png"))
            step("filter test + redeemed", rows=codes_table())

            # 6. Delete a redeemed test code in the UI: the dialog names the key; the key stops working.
            victim = tests[0]
            before = usage(test_keys[victim])
            answer(True)
            page.locator("#codes-body tr", has_text=victim).locator("button", has_text="删除").click()
            page.locator("#codes-body tr", has_text=victim).wait_for(state="detached")
            step("delete redeemed test code", dialog=dialogs[-1], usage_before=before,
                 usage_after=usage(test_keys[victim]), other_test_key_usage=usage(test_keys[tests[1]]))

            # 7. Delete an unredeemed test code: plain confirmation, no key involved.
            pick(filter_value="pending")
            victim = tests[2]
            answer(True)
            page.locator("#codes-body tr", has_text=victim).locator("button", has_text="删除").click()
            page.locator("#codes-body tr", has_text=victim).wait_for(state="detached")
            step("delete unredeemed test code", dialog=dialogs[-1])

            # 8. Generate formal codes: cancel once (nothing made), then confirm.
            pick(filter_value="all", kind_value="all")
            formal_before = store.code_stats()["formal"]["total"]
            page.select_option("#gen-kind", "formal")
            page.fill("#gen-count", "2")
            answer(False)
            page.click("#gen-btn")
            page.wait_for_function("() => document.getElementById('gen-msg').textContent.includes('已取消')")
            cancelled = {"dialog": dialogs[-1], "message": page.text_content("#gen-msg"),
                         "formal_total_after_cancel": store.code_stats()["formal"]["total"]}
            page.select_option("#gen-kind", "formal")
            answer(True)
            page.click("#gen-btn")
            page.wait_for_function("() => document.getElementById('gen-msg').textContent.includes('成功生成')")
            page.wait_for_selector("#codes-body tr td .badge")
            codes_section.screenshot(path=str(OUT / "06-admin-generated-formal.png"))
            step("generate formal", formal_total_before=formal_before, cancel=cancelled,
                 confirm_dialog=dialogs[-1], message=page.text_content("#gen-msg"),
                 formal_total_after=store.code_stats()["formal"]["total"],
                 kind_select_after=page.input_value("#gen-kind"))

            # 9. Generate test codes: no dialog at all.
            seen = len(dialogs)
            page.fill("#gen-count", "1")
            page.click("#gen-btn")
            page.wait_for_function("() => document.getElementById('gen-msg').textContent.includes('测试兑换码')")
            step("generate test", dialog_shown=len(dialogs) > seen, message=page.text_content("#gen-msg"))

            # 10-11. Redemption page at the tier boundaries.
            sell_until(store, 10)
            step("redeem page, 10 sold", pricing=pricing(), visible=redeem_page("07-redeem-sold10"))
            sell_until(store, 100)
            step("redeem page, 100 sold", pricing=pricing(), visible=redeem_page("08-redeem-sold100"))
            page.goto(base + "/admin")
            page.wait_for_function("() => document.getElementById('stat-early-sold').textContent.startsWith('已售')")
            page.locator("main > section").nth(0).screenshot(path=str(OUT / "09-admin-overview-sold100.png"))
            step("admin overview, 100 sold", early_bird=page.text_content("#stat-early-sold") + " / "
                 + page.text_content("#stat-early-sub"))

            # 12. /api/pricing unreachable: no price and no remaining count on the page.
            page.route("**/api/pricing", lambda route: route.abort())
            step("redeem page, pricing request fails", visible=redeem_page("10-redeem-pricing-unavailable"))
            page.unroute("**/api/pricing")

            checks["console_errors"] = console_errors
            browser.close()
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=15)
        if log:
            log.close()
        (OUT / "ui-checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n")
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
