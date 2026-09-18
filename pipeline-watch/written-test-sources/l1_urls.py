# -*- coding: utf-8 -*-
"""从库内提取官方公告/专场 URL 线索(只读,精灵上经 stdin 运行)。"""
import json
import re
import sys
from collections import Counter, defaultdict

PATH = sys.argv[1] if len(sys.argv) > 1 else r"C:\mcp-suite-collector\data\jobs.json"
COMPANY_KEYS = ("p1_company", "canonical_company", "recruitment_unit", "company",
                "recruitment_unit_raw", "parent_unit_raw")


def iter_rows(path):
    decoder = json.JSONDecoder()
    with open(path, "r", encoding="utf-8") as fh:
        buf = fh.read(1 << 22)
        idx = buf.find("[")
        if idx < 0:
            return
        pos = idx + 1
        while True:
            n = len(buf)
            while pos < n and buf[pos] in " \t\r\n,":
                pos += 1
            if pos >= n:
                more = fh.read(1 << 22)
                if not more:
                    return
                buf = buf[pos:] + more
                pos = 0
                continue
            if buf[pos] == "]":
                return
            try:
                obj, end = decoder.raw_decode(buf, pos)
            except ValueError:
                more = fh.read(1 << 22)
                if not more:
                    return
                buf = buf[pos:] + more
                pos = 0
                continue
            yield obj
            pos = end
            if pos > (1 << 21):
                buf = buf[pos:]
                pos = 0
                more = fh.read(1 << 22)
                if not more and not buf:
                    return
                buf += more


def company_of(row):
    for key in COMPANY_KEYS:
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def main():
    out = defaultdict(lambda: {"jobs": 0, "campaign": Counter(), "announce": Counter(),
                               "listing": Counter(), "sources": Counter()})
    for row in iter_rows(PATH):
        c = company_of(row)
        if not c:
            continue
        e = out[c]
        e["jobs"] += 1
        for field, key in (("campaign_url", "campaign"), ("announcement_url", "announce"),
                           ("job_listing_url", "listing")):
            v = row.get(field)
            if isinstance(v, str) and v.startswith("http"):
                e[key][v] += 1
        sn = row.get("source_name")
        if isinstance(sn, str) and sn:
            e["sources"][sn] += 1
    rows = []
    for c, e in out.items():
        if not (e["campaign"] or e["announce"] or e["listing"]):
            continue
        rows.append({"company": c, "jobs": e["jobs"],
                     "campaign_urls": [u for u, _ in e["campaign"].most_common(4)],
                     "announcement_urls": [u for u, _ in e["announce"].most_common(4)],
                     "listing_urls": [u for u, _ in e["listing"].most_common(4)],
                     "sources": [s for s, _ in e["sources"].most_common(4)]})
    rows.sort(key=lambda r: -r["jobs"])
    json.dump(rows, sys.stdout, ensure_ascii=False, indent=1)
    print("", file=sys.stdout)


if __name__ == "__main__":
    main()
