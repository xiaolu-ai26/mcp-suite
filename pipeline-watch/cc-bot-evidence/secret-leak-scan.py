#!/usr/bin/env python3
"""扫描工作区里有没有把 cc 机器人的凭据值写进任何文件(只报数量,不回显值)。

凭据只从 ``~/.config/qiuzhao-cc-bot.env``(或 QIUZHAO_CC_BOT_ENV_FILE)读,扫描范围
是 git 跟踪的文件 + 未跟踪的新文件(排除 .git/、__pycache__、.venv、外接盘影子文件)。

用法: /path/to/python pipeline-watch/cc-bot-evidence/secret-leak-scan.py [目录]
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {'.git', '__pycache__', '.venv', 'node_modules', '.pytest_cache'}
SKIP_SUFFIX = {'.pyc', '.png', '.jpg', '.jpeg', '.gif', '.zip', '.gz', '.pdf', '.woff', '.woff2'}


def credentials():
    env_file = Path(os.environ.get('QIUZHAO_CC_BOT_ENV_FILE', '~/.config/qiuzhao-cc-bot.env')).expanduser()
    values = []
    for line in env_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            value = line.partition('=')[2].strip().strip('"').strip("'")
            if len(value) >= 8:
                values.append(value)
    return values


def tracked_files(root):
    listed = subprocess.run(['git', '-C', str(root), 'ls-files'], capture_output=True, text=True)
    names = [Path(line) for line in listed.stdout.splitlines() if line]
    status = subprocess.run(['git', '-C', str(root), 'ls-files', '--others', '--exclude-standard'],
                            capture_output=True, text=True)
    names += [Path(line) for line in status.stdout.splitlines() if line]
    return names


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    secrets = credentials()
    if not secrets:
        print(json.dumps({'ok': False, 'error': 'no credential values found to scan for'}))
        return 1
    scanned = hits = 0
    for name in tracked_files(root):
        if any(part in SKIP_DIRS for part in name.parts) or name.suffix.lower() in SKIP_SUFFIX:
            continue
        path = root / name
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        scanned += 1
        if any(secret in text for secret in secrets):
            hits += 1
            print('LEAK: %s' % name)
    print(json.dumps({'ok': hits == 0, 'files_scanned': scanned, 'files_with_credentials': hits,
                      'credential_values_checked': len(secrets)}, ensure_ascii=False))
    return 0 if hits == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
