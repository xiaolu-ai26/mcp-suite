# Post-deploy check of the structured call log (release A2+). Read-only.
# Run on the server via stdin, e.g.  ssh $H '/opt/mcp-suite/.venv/bin/python -' < verify_call_log_snippet.py
# Checks today's (Beijing) tool_calls-YYYYMMDD.jsonl: directory/file owner and mode, every line
# is one JSON object with exactly the expected fields, and the whole file has no credential
# pattern (Bearer, API key, redemption code). Prints the last line so the fields can be eyeballed.
import json, os, pwd, re, stat, sys
from datetime import datetime
from zoneinfo import ZoneInfo

DIR = os.environ.get("MCP_CALL_LOG_DIR", "/var/lib/mcp-suite/call_logs")
FIELDS = {"ts", "product", "tool", "args", "ua", "user_ref", "outcome", "error_type",
          "result_total", "returned", "duration_ms"}
SECRETS = {"Bearer": re.compile(r"bearer\s+\S+", re.I),
           "api_key": re.compile(r"\b(?:qz|bm)_[A-Za-z0-9_\-]{16,}", re.I),
           "redemption_code": re.compile(r"\b(?:QZ|BM)-[0-9A-F]{16,}", re.I)}
problems = []


def owner_mode(path):
    st = os.stat(path)
    return f"{pwd.getpwuid(st.st_uid).pw_name}:{stat.S_IMODE(st.st_mode):o}"


path = os.path.join(DIR, f"tool_calls-{datetime.now(ZoneInfo('Asia/Shanghai')):%Y%m%d}.jsonl")
if not os.path.isfile(path):
    print("RESULT FAIL", ["no log file for today", path])
    sys.exit(1)
print("dir ", DIR, owner_mode(DIR))
print("file", path, owner_mode(path))
if owner_mode(DIR) != "mcp-suite:700" or owner_mode(path) != "mcp-suite:600":
    problems.append("owner/mode")
text = open(path, encoding="utf-8").read()
lines = text.splitlines()
last = None
for number, line in enumerate(lines, 1):
    try:
        entry = json.loads(line)
    except ValueError:
        problems.append(f"line {number}: not JSON")
        continue
    if set(entry) != FIELDS:
        problems.append(f"line {number}: fields {sorted(set(entry) ^ FIELDS)}")
    if not re.fullmatch(r"[0-9a-f]{12}", entry.get("user_ref") or "0" * 12):
        problems.append(f"line {number}: user_ref format")
    last = entry
for name, pattern in SECRETS.items():
    hits = len(pattern.findall(text))
    print(f"{name:<16} hits={hits}")
    if hits:
        problems.append(f"{name} x{hits}")
print("lines", len(lines))
print("last ", json.dumps(last, ensure_ascii=False))
print("RESULT", "FAIL" if problems else "OK", problems[:20])
