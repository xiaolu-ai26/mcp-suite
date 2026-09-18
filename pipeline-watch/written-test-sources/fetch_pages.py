# -*- coding: utf-8 -*-
"""L2/L3 官方页面只读抓取 + 逐字证据抽取。

预算:每站(域名)最多 2 个 URL、全局最多 150 个、每次请求间隔 >= 2 秒。
只用普通浏览器 UA 裸 GET,不登录、不带 cookie、不绕验证码/签名。
"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
MAX_PER_SITE = 2
MAX_TOTAL = 150
DELAY = 2.2

TEST_WORD = re.compile(
    r"笔试|机考|上机考试|在线考试|统一考试|在线测试|线上测试|能力测试|性格测试|心理测试|职业测试|"
    r"认知能力|游戏化测评|(?:在线|线上|职业|性格|心理|能力|综合|人才|认知|游戏化|专业|招聘|应聘|录用|笔试|面试|素质)\s*测评|"
    r"\bOT\b|online\s*test|assessment", re.I)
FLOW_CHAIN = re.compile(r"网申|网上申请|在线申请|简历投递|投递简历|简历筛选|简历初筛|初筛|资格审查|"
                        r"笔试|测评|面试|初面|复试|终面|offer|录用|体检|背景调查|签约|入职")
EXEMPT = re.compile(r"免笔试|无需笔试|无笔试|不设笔试|不用笔试|不需要笔试|免去笔试|跳过笔试|免除笔试")
CONDITIONAL = re.compile(r"优秀|优先|部分岗位|视情况|酌情|可免|免予|豁免|绿色通道|直通")


def site_of(url):
    return urlsplit(url).netloc.lower().replace("www.", "")


def fetch(url, session):
    return session.get(url, headers=HEADERS, timeout=20, allow_redirects=True)


def text_of(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def sentences(text):
    for raw in re.split(r"[。；;\n\r]+", text):
        s = re.sub(r"\s+", "", raw)
        if 6 <= len(s) <= 260:
            yield s


def analyze(text):
    hits = {"test": [], "flow": [], "exempt": [], "conditional": []}
    for s in sentences(text):
        if TEST_WORD.search(s):
            hits["test"].append(s)
        if len({m.group(0) for m in FLOW_CHAIN.finditer(s)}) >= 3:
            hits["flow"].append(s)
        if EXEMPT.search(s):
            hits["exempt"].append(s)
        if CONDITIONAL.search(s) and TEST_WORD.search(s):
            hits["conditional"].append(s)
    for k in hits:
        hits[k] = hits[k][:12]
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True, help="JSON 清单 [{company,url,kind}]")
    ap.add_argument("--out", required=True, help="结果 JSON 输出路径")
    ap.add_argument("--evidence", required=True, help="证据文本目录")
    ap.add_argument("--max-total", type=int, default=MAX_TOTAL)
    args = ap.parse_args()

    targets = json.loads(Path(args.list).read_text(encoding="utf-8"))
    out_path = Path(args.out)
    ev_dir = Path(args.evidence)
    ev_dir.mkdir(parents=True, exist_ok=True)

    results = []
    if out_path.exists():
        try:
            results = json.loads(out_path.read_text(encoding="utf-8"))
        except ValueError:
            results = []
    done = {r["url"] for r in results}
    per_site = {}
    for r in results:
        per_site[site_of(r["url"])] = per_site.get(site_of(r["url"]), 0) + 1

    session = requests.Session()
    used = 0
    for item in targets:
        url = item["url"]
        site = site_of(url)
        if url in done:
            continue
        if per_site.get(site, 0) >= MAX_PER_SITE:
            print("SKIP site budget %s %s" % (site, url), file=sys.stderr)
            continue
        if used >= args.max_total:
            print("STOP global budget", file=sys.stderr)
            break
        rec = {"company": item.get("company", ""), "url": url, "kind": item.get("kind", ""),
               "expected": item.get("expected", ""), "site": site}
        try:
            resp = fetch(url, session)
            rec["http"] = resp.status_code
            rec["final_url"] = resp.url
            raw = resp.content
            me = re.search(rb"charset=[\"']?([\w-]+)", raw[:6000], re.I)
            enc = me.group(1).decode("ascii", "ignore") if me else ""
            if not enc or enc.lower() in ("iso-8859-1", "us-ascii"):
                enc = resp.apparent_encoding or "utf-8"
            try:
                html = raw.decode(enc, errors="replace")
            except LookupError:
                enc, html = "utf-8", raw.decode("utf-8", errors="replace")
            rec["encoding"] = enc
            rec["bytes"] = len(html)
            text = text_of(html)
            rec["text_len"] = len(text)
            m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
            rec["title"] = re.sub(r"\s+", " ", m.group(1)).strip()[:200] if m else ""
            rec["hits"] = analyze(text)
            digest = hashlib.sha256(url.encode()).hexdigest()[:12]
            ev = ev_dir / ("%s__%s.txt" % (re.sub(r"[^\w\-]+", "_", item.get("company", "x"))[:40], digest))
            ev.write_text("URL: %s\nHTTP: %s\nENCODING: %s\nTITLE: %s\n\n%s" % (
                url, resp.status_code, enc, rec["title"], text[:400000]), encoding="utf-8")
            rec["evidence_file"] = str(ev)
        except Exception as exc:  # noqa: BLE001 - record and continue
            rec["error"] = "%s: %s" % (type(exc).__name__, exc)
            try:
                direct = requests.Session()
                direct.trust_env = False
                resp = fetch(url, direct)
                rec.pop("error", None)
                rec["http"] = resp.status_code
                rec["final_url"] = resp.url
                rec["direct_retry"] = True
                raw = resp.content
                me = re.search(rb"charset=[\"']?([\w-]+)", raw[:6000], re.I)
                enc = me.group(1).decode("ascii", "ignore") if me else ""
                if not enc or enc.lower() in ("iso-8859-1", "us-ascii"):
                    enc = resp.apparent_encoding or "utf-8"
                try:
                    html = raw.decode(enc, errors="replace")
                except LookupError:
                    enc, html = "utf-8", raw.decode("utf-8", errors="replace")
                rec["encoding"] = enc
                rec["bytes"] = len(html)
                text = text_of(html)
                rec["text_len"] = len(text)
                m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
                rec["title"] = re.sub(r"\s+", " ", m.group(1)).strip()[:200] if m else ""
                rec["hits"] = analyze(text)
                digest = hashlib.sha256(url.encode()).hexdigest()[:12]
                ev = ev_dir / ("%s__%s.txt" % (re.sub(r"[^\w\-]+", "_", item.get("company", "x"))[:40], digest))
                ev.write_text("URL: %s\nHTTP: %s\nENCODING: %s\nTITLE: %s\n\n%s" % (
                    url, resp.status_code, enc, rec["title"], text[:400000]), encoding="utf-8")
                rec["evidence_file"] = str(ev)
            except Exception as exc2:  # noqa: BLE001
                rec["error"] = "%s | direct: %s: %s" % (rec["error"], type(exc2).__name__, exc2)
        results.append(rec)
        done.add(url)
        per_site[site] = per_site.get(site, 0) + 1
        used += 1
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print("[%d] %s %s http=%s hits=%s" % (
            used, item.get("company", ""), url,
            rec.get("http") or rec.get("error"),
            {k: len(v) for k, v in (rec.get("hits") or {}).items()}), file=sys.stderr)
        time.sleep(DELAY)
    print("done used=%d total=%d" % (used, len(results)), file=sys.stderr)


if __name__ == "__main__":
    main()
