"""Clear the way for `git merge --ff-only feat/v4` in the main worktree (KIMI-DEPLOY.md step 12).

On 2026-09-12 the main worktree (~/Projects/mcp-suite) holds untracked copies of
research/qiuzhao-v4-interface-20260911/ (the SPEC inputs as received, committed to feat/v4 by
62c36fe) and an uncommitted edit of scripts/v4lib.py that feat/v4 also carries. Git refuses a
fast-forward over untracked or modified files at paths the merge writes, even byte-identical ones.
This lists every such path and, with --apply, moves it to a backup directory next to the worktree
(tracked files: copied there, then restored to HEAD) — but only when its bytes equal a committed
blob (feat/v4 or 62c36fe), so nothing is lost. Any other blocker: nothing is moved, exit code 1.

usage: python3 prepare_main_ff.py <main worktree> [--apply]      (default: dry run, read-only)
"""
import datetime
import os
import pathlib
import shutil
import subprocess
import sys

ENV = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}  # dry run must not even refresh the index


def git(wt, *args):
    return subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True, env=ENV,
                          check=True).stdout


def blob(wt, rev, path):
    out = subprocess.run(["git", "-C", str(wt), "rev-parse", "--verify", "-q", f"{rev}:{path}"],
                         capture_output=True, text=True, env=ENV)
    return out.stdout.strip() or None


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    wt, apply = pathlib.Path(argv[0]).expanduser(), "--apply" in argv[1:]
    branch = git(wt, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch != "main":
        print("STOP: worktree is on", branch, "not main")
        return 1
    touched = set(git(wt, "diff", "--name-only", "-z", "main", "feat/v4").split("\0")) - {""}
    dirty, entries = {}, git(wt, "status", "--porcelain", "-z", "--untracked-files=all").split("\0")
    skip = False
    for entry in entries:
        if skip or not entry:
            skip = False
            continue
        code, path = entry[:2], entry[3:]
        dirty[path] = code
        skip = code[0] in "RC"  # a rename/copy entry is followed by its source path
    blockers = sorted(p for p in dirty if p in touched)
    safe, unsafe = [], []
    for path in blockers:
        exists = (wt / path).is_file()
        digest = git(wt, "hash-object", "--", path).strip() if exists else None
        known = {blob(wt, "feat/v4", path), blob(wt, "62c36fe", path)} - {None}
        (safe if digest in known else unsafe).append((path, dirty[path], digest))
    for path, code, digest in safe:
        print(f"identical-to-commit  {code}  {path}")
    for path, code, digest in unsafe:
        print(f"DIFFERENT            {code}  {path}")
    print(f"blockers={len(blockers)} safe={len(safe)} different={len(unsafe)}")
    if unsafe:
        print("STOP: some blocking files differ from every committed version; move nothing, ask Max")
        return 1
    if not apply:
        print("dry run: nothing moved")
        return 0
    backup = wt.parent / f"mcp-suite-preff-backup-{datetime.datetime.now():%Y%m%d-%H%M%S}"
    for path, code, _ in safe:
        target = backup / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if code == "??":
            shutil.move(str(wt / path), str(target))
        else:
            shutil.copy2(wt / path, target)
            git(wt, "checkout", "--", path)
    print("moved", len(safe), "file(s) to", backup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
