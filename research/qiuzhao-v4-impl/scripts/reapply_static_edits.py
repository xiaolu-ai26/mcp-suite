"""Re-apply the six v4 text edits of guide.html and app.js (commit 4118fe8) to other copies.

For the deploy: if the live pages no longer equal main 1127cf7 (edited on the server after
2026-09-11 21:26), copy them into a directory, run this on it, review `diff`, and deploy the
result instead of the feat/v4 files. Each old sentence must occur exactly once in its file; if
any does not, nothing is written and the exit code is 1 (the live wording changed: stop).
Bytes other than the six sentences are left exactly as they are (line endings included).

usage: python3 reapply_static_edits.py <dir holding guide.html and app.js>
"""
import pathlib
import sys

EDITS = {
    "guide.html": [("<code>jobs_deadlines</code>", "<code>jobs_stats</code>"),
                   ("参数 <code>limit=1</code>", "参数 <code>page_size=1</code>"),
                   ("jobs_search，参数 limit=1。", "jobs_search，参数 page_size=1。")],
    "app.js": [("请调用秋招岗位库的 jobs_deadlines，查询未来7天内即将截止的岗位，按截止日期从近到远排序，",
                "请调用秋招岗位库的 jobs_search，参数 deadline_within_days=7、sort=deadline_asc，"
                "查询未来7天内即将截止的岗位（按截止日期从近到远），"),
               ("jobs_search、jobs_deadlines、jobs_detail", "jobs_search、jobs_stats、jobs_detail"),
               ("参数 limit=1，", "参数 page_size=1，")],
}


def main(argv):
    if len(argv) != 1:
        print("usage: python3 reapply_static_edits.py <dir holding guide.html and app.js>", file=sys.stderr)
        return 2
    root = pathlib.Path(argv[0])
    texts, bad = {}, []
    for name, pairs in EDITS.items():
        text = (root / name).read_bytes().decode("utf-8")
        for old, new in pairs:
            if text.count(old) != 1:
                bad.append(f"{name}: found {text.count(old)}x «{old[:40]}»")
            text = text.replace(old, new)
        texts[name] = text
    if bad:
        print("NOT WRITTEN", bad)
        return 1
    for name, text in texts.items():
        (root / name).write_bytes(text.encode("utf-8"))
    print("re-applied 6 edits to", ", ".join(sorted(texts)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
