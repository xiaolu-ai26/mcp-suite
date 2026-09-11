"""Local-only batch stock generation; outputs paths and counts, never credentials."""
import argparse
import os
from pathlib import Path
from core.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("generate-codes", nargs="?")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--plan", default="qiuzhao-2026")
    args = parser.parse_args()
    # Exclusive file creation prevents accidental stock overwrite.
    args.out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        codes = Store(args.db).generate_codes(args.count, args.plan)
        with os.fdopen(fd, "w") as handle:
            handle.write("\n".join(codes) + "\n")
        print(f"已生成 {len(codes)} 个兑换码；文件：{args.out.resolve()}；权限：0600")
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        args.out.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()
