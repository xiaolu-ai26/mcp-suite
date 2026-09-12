"""Pure helper utilities for pending-index reconciliation in p1 collection runs.

The module is intentionally side-effect free and does not perform any I/O.
"""
from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
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
    if not isinstance(value, list):
        raise ValueError('source_missing_fields must be a list')
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
        row['detail_url'] = detail_url
        row['job_title'] = job_title
        pending_reason = _as_text(row.get('pending_reason'))
        if pending_reason not in {'source_empty_body', 'fetch_failed'}:
            raise ValueError('pending_reason must be source_empty_body or fetch_failed')
        request_status = _as_text(row.get('detail_request_status'))
        missing = row.get('source_missing_fields', [])
        if not isinstance(missing, list):
            raise ValueError('source_missing_fields must be a list')
        if pending_reason == 'fetch_failed':
            if request_status not in {'failed', 'blocked'}:
                raise ValueError('fetch_failed requires detail_request_status failed or blocked')
            row['listing_evidence_path'] = _require_evidence_path(row.get('listing_evidence_path'))
            if missing:
                raise ValueError('fetch_failed cannot claim source_missing_fields; use unretrieved_fields')
            row['source_missing_fields'] = []
            row.setdefault('unretrieved_fields', ['responsibilities', 'requirements'])
        else:
            if request_status != 'success':
                raise ValueError('source_empty_body requires detail_request_status=success')
            _required_missing_fields(missing)
            evidence = row.get('listing_evidence_path') or row.get('detail_evidence_path')
            _require_evidence_path(evidence)
            if row.get('status') in {'failed', 'blocked'}:
                raise ValueError('source_empty_body cannot have failed/blocked status')
        row['pending_reason'] = pending_reason
        row['detail_request_status'] = request_status

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


def merge_pending_index(previous: Sequence[Dict[str, Any]],
                       updates: Sequence[Tuple[str, str, Dict[str, Any]]],
                       id_aliases: Optional[Dict[str, str]] = None):
    """Reconcile only pending records, keeping complete jobs outside this index.

    Dict buckets avoid per-job scans over the entire index. A complete scope can
    prune its own bucket; partial scopes preserve unseen entries.
    """
    buckets = {}
    stats = {'added': 0, 'updated': 0, 'removed': 0, 'upgraded': 0}
    for row in previous:
        if not _is_pending(row):
            raise ValueError('previous registry must contain only pending entries')
        group = (row.get('p1_company'), row.get('p1_scope'))
        identity = _row_identity(row)
        bucket = buckets.setdefault(group, {})
        if not identity or identity in bucket:
            raise ValueError('previous registry duplicate or missing identity')
        bucket[identity] = _apply_alias(row, id_aliases)
    for company, scope, result in updates:
        bucket = buckets.setdefault((company, scope), {})
        seen = set()
        upgraded = set()
        def identity_of(row):
            if row.get('p1_company', company) != company or row.get('p1_scope', scope) != scope:
                raise ValueError('update row company/scope mismatch')
            identity = row.get('p1_identity')
            if not identity:
                raise ValueError('normalized update requires p1_identity')
            return str(identity)
        for row in result.get('jobs', []) or []:
            identity = identity_of(row)
            seen.add(identity)
            if _as_text(row.get('description_raw')):
                upgraded.add(identity)
                if identity in bucket:
                    del bucket[identity]
                    stats['upgraded'] += 1
        pending_seen = set()
        for row in result.get('pending_index', []) or []:
            identity = identity_of(row)
            if identity in pending_seen:
                raise ValueError('duplicate incoming pending identity')
            pending_seen.add(identity)
            seen.add(identity)
            if identity in upgraded:
                continue
            if not _is_pending(row):
                raise ValueError('pending_index contains a non-pending row')
            incoming = _apply_alias(row, id_aliases)
            if identity in bucket:
                if incoming != bucket[identity]:
                    stats['updated'] += 1
                # Keep the legacy public ID if caller did not supply a new alias.
                if not id_aliases or identity not in id_aliases:
                    incoming['id'] = bucket[identity].get('id', incoming.get('id'))
            else:
                stats['added'] += 1
            bucket[identity] = incoming
        if result.get('coverage', {}).get('complete') is True:
            for identity in set(bucket) - seen:
                del bucket[identity]
                stats['removed'] += 1
    return [row for bucket in buckets.values() for row in bucket.values()], stats
