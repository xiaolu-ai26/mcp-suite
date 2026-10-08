"""Bounded-memory, fail-closed JSON-array normalization (no network or publication).

Only the I/O strategy changes. Field decisions remain in qiuzhao.normalize.
Memory is O(mapping assets + largest record), not O(dataset size). A malformed or
oversized record is an error, never silently skipped. The caller owns the runner
lock; content/stat checks detect drift but are not a substitute for that lock.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Callable, Iterator, TextIO

CHUNK_CHARS = 64 * 1024
MAX_RECORD_CHARS = 64 * 1024 * 1024


class NormalizationInputError(ValueError):
    """Invalid, over-limit, or concurrently modified input; source is not replaced."""


class NormalizationRecordError(ValueError):
    """Identifies a failing record without copying its possibly private payload."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _reject_constant(value: str):
    raise NormalizationInputError('non-JSON numeric constant: ' + value)


def iter_records(stream: TextIO, *, chunk_chars: int = CHUNK_CHARS,
                 max_record_chars: int = MAX_RECORD_CHARS) -> Iterator[dict]:
    """Read one strict top-level JSON array of objects with linear record scanning.

    Object boundaries are located incrementally while tracking JSON strings, escapes
    and nested delimiters. Each complete record is passed to the strict JSON decoder
    exactly once, avoiding repeated raw_decode from the object start for long records.
    Boundary scanning is not validation: complete candidates still use the strict
    JSONDecoder, and malformed/oversized/trailing input fails closed.
    """
    if chunk_chars <= 0 or max_record_chars <= 0:
        raise ValueError('chunk and record limits must be positive')
    decoder = json.JSONDecoder(parse_constant=_reject_constant)
    buffer, position, eof, index = '', 0, False, 0

    def refill() -> None:
        nonlocal buffer, position, eof
        block = stream.read(chunk_chars)
        buffer = buffer[position:] + block
        position = 0
        eof = not block

    def peek() -> str:
        nonlocal position
        while True:
            while position < len(buffer) and buffer[position] in ' \t\r\n':
                position += 1
            if position < len(buffer):
                return buffer[position]
            if eof:
                return ''
            refill()

    def read_object() -> dict:
        nonlocal buffer, position, eof
        parts = []
        record_chars = 0
        depth = 0
        in_string = False
        escaped = False
        while True:
            if position >= len(buffer):
                if eof:
                    raise NormalizationInputError(
                        f'record index {index}: invalid or truncated JSON (unterminated object)')
                refill()
                continue
            segment_start = position
            completed = False
            while position < len(buffer):
                ch = buffer[position]
                position += 1
                if in_string:
                    if escaped:
                        escaped = False
                    elif ch == '\\':
                        escaped = True
                    elif ch == '"':
                        in_string = False
                    continue
                if ch == '"':
                    in_string = True
                elif ch in '{[':
                    depth += 1
                elif ch in '}]':
                    depth -= 1
                    if depth < 0 or depth == 0:
                        completed = True
                        break
            piece = buffer[segment_start:position]
            record_chars += len(piece)
            if record_chars > max_record_chars:
                raise NormalizationInputError(
                    f'record index {index}: record exceeds limit={max_record_chars} chars')
            parts.append(piece)
            if completed:
                break
            if eof:
                raise NormalizationInputError(
                    f'record index {index}: invalid or truncated JSON (unterminated object)')
        candidate = ''.join(parts)
        try:
            record, end = decoder.raw_decode(candidate)
        except (json.JSONDecodeError, NormalizationInputError) as error:
            detail = error.msg if isinstance(error, json.JSONDecodeError) else str(error)
            raise NormalizationInputError(
                f'record index {index}: invalid JSON ({detail})') from error
        if end != len(candidate) or not isinstance(record, dict):
            raise NormalizationInputError(f'record index {index}: expected exactly one object')
        return record

    if peek() != '[':
        raise NormalizationInputError('expected a top-level JSON array')
    position += 1
    if peek() == ']':
        position += 1
    else:
        while True:
            if peek() != '{':
                raise NormalizationInputError(f'record index {index}: expected an object')
            yield read_object()
            index += 1
            delimiter = peek()
            if delimiter == ']':
                position += 1
                break
            if delimiter != ',':
                raise NormalizationInputError(f'after record index {index - 1}: expected comma or closing bracket')
            position += 1
            if peek() == ']':
                raise NormalizationInputError(f'after record index {index - 1}: trailing comma')
    if peek():
        raise NormalizationInputError('trailing content after JSON array')


def _identity(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def normalize_path(path, *, check: bool, normalize_one: Callable,
                   fields, is_empty: Callable, metadata: dict) -> dict:
    """Normalize an isolated/locked file; commit only after the entire input passes.

    --check creates no candidate. Normal execution fsyncs a same-directory temporary
    file and closes both handles before os.replace (required on Windows). The old
    file survives parsing, callback, serialization, fsync and pre-commit failures.
    This does not catch/convert errors into partial-success exit codes.
    """
    path = Path(path)
    initial = path.lstat()
    if not stat.S_ISREG(initial.st_mode):
        raise NormalizationInputError('input must be a regular file, not a symlink or directory')
    source_sha = file_sha256(path)
    if _identity(path.stat()) != _identity(initial):
        raise NormalizationInputError('input changed while computing its identity')
    counts = {field: 0 for field in fields}
    rows, changed_existing = 0, 0
    temporary = None
    output = None
    try:
        if not check:
            fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + '.', suffix='.tmp')
            try:
                output = os.fdopen(fd, 'w', encoding='utf-8', newline='')
            except BaseException:
                os.close(fd)
                raise
            output.write('[')
        with path.open('r', encoding='utf-8', newline='') as source:
            for row in iter_records(source):
                before = {field: deepcopy(row.get(field)) for field in fields
                          if not is_empty(row.get(field))}
                try:
                    normalize_one(row, counts)
                except Exception as error:
                    raise NormalizationRecordError(
                        f'record index {rows}: {type(error).__name__}; see chained traceback; source retained') from error
                changed_existing += sum(row.get(field) != old for field, old in before.items())
                if output is not None:
                    if rows:
                        output.write(', ')
                    json.dump(row, output, ensure_ascii=False, allow_nan=False)
                rows += 1
        if output is not None:
            output.write(']')
            output.flush()
            os.fsync(output.fileno())
            output.close()
            output = None
            os.chmod(temporary, stat.S_IMODE(initial.st_mode))
            if hasattr(os, 'chown'):
                try:
                    os.chown(temporary, initial.st_uid, initial.st_gid)
                except PermissionError:
                    pass
        if (_identity(path.stat()) != _identity(initial) or file_sha256(path) != source_sha):
            raise NormalizationInputError('input changed during normalization; candidate not committed')
        result = dict(metadata, path=str(path), check=bool(check), records=rows,
                      filled=counts, filled_total=sum(counts.values()),
                      would_change_existing=changed_existing, written=False,
                      input_sha256=source_sha, io_mode='streaming-atomic',
                      max_record_chars=MAX_RECORD_CHARS)
        if temporary is not None:
            result['output_sha256'] = file_sha256(Path(temporary))
            os.replace(temporary, path)
            temporary = None
            result['written'] = True
        return result
    finally:
        try:
            if output is not None:
                output.close()
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
