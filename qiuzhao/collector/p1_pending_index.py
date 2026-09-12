"""Pure helper utilities for pending-index reconciliation in p1 collection runs.

The module is intentionally side-effect free and does not perform any I/O.
"""
from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlsplit


def source_identity(company: str, scope: str, source_id: str) -> str:
    """Return the canonical p1 identity for a source record."""
    return 'p1-' + hashlib.sha256(f'{company}|{scope}|{source_id}'.encode()).hexdigest()[:24]


def _as_text(value: Any) -> str:
    return str(value).strip() if value is not None else ''


def _require_field(payload: Dict[str, Any], field: str) -> str:
    text = _as_text(payload.get(field))
    if not text:
        raise ValueError(f'{field} is required')
    return text


def _require_http_url(value: Any) -> str:
    url = _as_text(value)
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError('detail_url must be a valid http(s) URL')
    return url


def _require_evidence_path(value: Any) -> str:
    path = value if isinstance(value, str) else None
    if not _as_text(path):
        raise ValueError('listing_evidence_path must be a non-empty string')
    return path


def _required_missing_fields(value: Any) -> Set[str]:
    if not isinstance(value, Iterable):
        raise ValueError('source_missing_fields must be an iterable')
    normalized = {str(item).strip().lower() for item in value if _as_text(item)}
    if 'responsibilities' not in normalized or 'requirements' not in normalized:
        raise ValueError('source_empty_body requires responsibilities and requirements in source_missing_fields')
    return normalized


def normalize_pending_index(entries: Sequence[Any], company: str, scope: str,
                           recruitment_type: str) -> List[Dict[str, Any]]:
    """Normalize source pending records into pending-index rows.

    Requirements:
        - source_record_id and job_title must be concrete.
        - detail_url must be an http(s) URL.
        - listing_evidence_path must be a string.
        - pending_reason constraints are validated according to contract.
        - source ids are canonicalized with :func:`source_identity`.
    """
    if not isinstance(entries, Sequence):
        raise ValueError('entries must be a list-like object')

    normalized: List[Dict[str, Any]] = []
    identities: Set[str] = set()

    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('pending-index row must be a mapping')

        row = copy.deepcopy(entry)
        source_record_id = _require_field(row, 'source_record_id')
        job_title = _require_field(row, 'job_title')
        detail_url = _require_http_url(row.get('detail_url'))
        row['listing_evidence_path'] = _require_evidence_path(row.get('listing_evidence_path'))
        row['detail_url'] = detail_url
        row['job_title'] = job_title

        pending_reason = _as_text(row.get('pending_reason'))

        # detail fetch failed should be explicit.
        if pending_reason == 'fetch_failed':
            status = _as_text(row.get('status'))
            if status not in {'failed', 'blocked'}:
                raise ValueError('pending_reason=fetch_failed requires status failed or blocked')

        # listing content empty should keep a successful detail fetch and explicit missing fields.
        if pending_reason == 'source_empty_body':
            if _as_text(row.get('detail_request_status')) != 'success':
                raise ValueError('pending_reason=source_empty_body requires detail_request_status=success')
            _required_missing_fields(row.get('source_missing_fields'))

        if pending_reason and pending_reason not in {'source_empty_body', 'fetch_failed'}:
            raise ValueError('pending_reason must be source_empty_body or fetch_failed when present')

        identity = source_identity(company, scope, source_record_id)
        if identity in identities:
            raise ValueError(f'duplicate pending source_record_id: {source_record_id}')
        identities.add(identity)

        row['source_record_id'] = source_record_id
        row['id'] = identity
        row['p1_identity'] = identity
        row['p1_company'] = company
        row['p1_scope'] = scope
        row['recruitment_type'] = recruitment_type
        row['description_raw'] = ''
        row['index_only'] = True
        row['status'] = 'unverified'

        normalized.append(row)

    return copy.deepcopy(normalized)


def presence_keys(result: Dict[str, Any]) -> Set[str]:
    """Return all pending/job identities present in a normalized result payload."""
    identities: Set[str] = set()
    for key in ('jobs', 'pending_index'):
        for row in result.get(key, ()) or ():
            if not isinstance(row, dict):
                continue
            identity = row.get('p1_identity')
            if identity:
                identities.add(str(identity))
    return identities


def _row_identity(row: Dict[str, Any]) -> str:
    return str(row.get('p1_identity') or row.get('id') or '')


def _is_pending(row: Dict[str, Any]) -> bool:
    return row.get('pending_reason') is not None and row.get('pending_reason') != ''


def _belongs(row: Dict[str, Any], company: str, scope: str) -> bool:
    return row.get('p1_company') == company and row.get('p1_scope') == scope


def _apply_alias(row: Dict[str, Any], aliases: Optional[Dict[str, str]]) -> Dict[str, Any]:
    row = copy.deepcopy(row)
    if aliases:
        alias = aliases.get(row.get('p1_identity'))
        if alias is not None:
            row['id'] = alias
    return row


def _find_index_by_identity(rows: Sequence[Dict[str, Any]], identity: str,
                           company: str, scope: str) -> Optional[int]:
    for index, row in enumerate(rows):
        if row.get('p1_company') == company and row.get('p1_scope') == scope and _row_identity(row) == identity:
            return index
    return None


def merge_pending_index(previous: Sequence[Dict[str, Any]],
                       updates: Sequence[Tuple[str, str, Dict[str, Any]]],
                       id_aliases: Optional[Dict[str, str]] = None):
    """Merge normalised pending-index updates into previous rows.

    Returns ``(rows, stats)`` where stats include counts for:
    ``added``, ``updated``, ``removed`` and ``upgraded``.
    """
    merged: List[Dict[str, Any]] = copy.deepcopy(list(previous))
    stats = {'added': 0, 'updated': 0, 'removed': 0, 'upgraded': 0}

    for company, scope, result in updates:
        coverage = result.get('coverage', {}) if isinstance(result, dict) else {}
        jobs = result.get('jobs', []) if isinstance(result, dict) else []
        pending_rows = result.get('pending_index', []) if isinstance(result, dict) else []

        seen: Set[str] = set()

        # Real jobs replace pending rows first.
        for incoming in jobs:
            if not isinstance(incoming, dict):
                continue
            normalized = _apply_alias(incoming, id_aliases)
            identity = _row_identity(normalized)
            if not identity:
                continue
            index = _find_index_by_identity(merged, identity, company, scope)
            if index is None:
                merged.append(copy.deepcopy(normalized))
                stats['added'] += 1
            else:
                old = merged[index]
                was_pending = _is_pending(old)
                merged[index] = copy.deepcopy(normalized)
                if was_pending:
                    stats['upgraded'] += 1
                else:
                    stats['updated'] += 1
            seen.add(identity)

        # Add or refresh pending rows.
        for incoming in pending_rows:
            if not isinstance(incoming, dict):
                continue
            normalized = _apply_alias(incoming, id_aliases)
            identity = _row_identity(normalized)
            if not identity:
                continue
            index = _find_index_by_identity(merged, identity, company, scope)
            if index is None:
                merged.append(copy.deepcopy(normalized))
                stats['added'] += 1
            else:
                # Do not downgrade existing real jobs to pending.
                if _is_pending(merged[index]):
                    merged[index] = copy.deepcopy(normalized)
                    stats['updated'] += 1
            seen.add(identity)

        # Only successful complete coverage may remove unseen pending entries.
        if coverage.get('complete') is True:
            removed: List[int] = []
            for idx in range(len(merged) - 1, -1, -1):
                row = merged[idx]
                if not isinstance(row, dict) or not _belongs(row, company, scope):
                    continue
                if not _is_pending(row):
                    continue
                if _row_identity(row) in seen:
                    continue
                removed.append(idx)

            for idx in removed:
                merged.pop(idx)
                stats['removed'] += 1

    return merged, stats
