"""Process Tencent staging 814 jobs -> production schema, dedup, classify, merge."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path('/Users/maxzhl/Projects/mcp-suite')
STAGING = BASE / 'research/qiuzhao-expansion-20260910/staging/tencent_jobs.json'
EXISTING = BASE / 'qiuzhao/data/jobs.json'
OUT_DIR = BASE / 'research/qiuzhao-v3-launch-20260910/job_mvp'
MERGED = OUT_DIR / 'staging_merged/jobs.json'
LOG = OUT_DIR / 'tencent_review_log.jsonl'

TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TZ).isoformat(timespec='seconds')

HK_CITIES = {'中国香港', '香港', '中国澳门', '澳门', '中国台湾', '台湾'}
OVERSEAS_HINT = {'新加坡', '首尔', '东京', '悉尼', '洛杉矶', '纽约', '伦敦', '巴黎'}


def classify(rec):
    """Return (recruitment_type, scope_note). Campus portal feed has no 社招."""
    proj = rec.get('campaign_cohort_raw') or rec.get('description_raw') or ''
    title = rec.get('job_title') or ''
    text = proj + ' ' + title
    if any(k in text for k in ['实习生', '实习']):
        return '实习', 'campus_portal_intern'
    if any(k in text for k in ['应届', '青云计划']):
        return '校招', 'campus_portal_fulltime'
    return '校招', 'campus_portal_undisclosed_type'


def main():
    staging = json.loads(STAGING.read_text())
    existing = json.loads(EXISTING.read_text())

    # Build existing dedup key set: source_url + title + company
    existing_keys = set()
    for r in existing:
        key = (r.get('source_url', '').strip(),
               (r.get('job_title') or '').strip(),
               (r.get('recruitment_unit') or '').strip())
        existing_keys.add(key)

    log_lines = []
    accepted = []
    seen_post = set()
    n_dup_existing = 0
    n_dup_internal = 0
    n_rejected = 0

    for rec in staging:
        post_id = str(rec.get('source_record_id') or '')
        title = (rec.get('job_title') or '').strip()
        src = (rec.get('source_url') or '').strip()
        unit = rec.get('recruitment_unit') or ''

        # Internal dedup by postId
        if post_id in seen_post:
            n_dup_internal += 1
            log_lines.append(json.dumps({'post_id': post_id, 'title': title,
                                         'decision': 'reject', 'reason': 'internal_duplicate_postid'}, ensure_ascii=False))
            continue
        seen_post.add(post_id)

        # Cross dedup against existing 9191
        key = (src, title, unit)
        if key in existing_keys:
            n_dup_existing += 1
            log_lines.append(json.dumps({'post_id': post_id, 'title': title,
                                         'decision': 'reject', 'reason': 'duplicate_vs_production'}, ensure_ascii=False))
            continue

        # Field presence checks
        problems = []
        if not title:
            problems.append('missing_title')
        if not src.startswith('https://join.qq.com/post_detail.html?postid='):
            problems.append('unexpected_source_url')
        cities = rec.get('cities') or []
        if not cities:
            problems.append('no_cities')

        rtype, scope = classify(rec)
        cities_list = list(cities)
        is_hk = any(c in HK_CITIES for c in cities_list)
        is_overseas = any(c in OVERSEAS_HINT for c in cities_list)
        region = 'overseas' if (is_hk or is_overseas) else 'mainland'

        # Build production-schema record
        out = {
            'id': rec.get('id') or f'tencent-{post_id}',
            'recruitment_unit': '腾讯科技（深圳）有限公司',
            'contracting_entity': '',
            'job_title': title,
            'job_category': rec.get('job_category') or '',
            'cities': cities_list,
            'major_requirements_raw': '',
            'major_tags': [],
            'education_raw': '',
            'cohort_raw': rec.get('cohort_raw') or '',
            'deadline': None,
            'deadline_type': 'undisclosed',
            'status': 'open' if not problems else 'unverified',
            'application_url': src,
            'source_url': src,
            'published_at': None,
            'reviewed_at': NOW,
            'source_name': '腾讯校园招聘官方网站',
            'evidence_path': rec.get('evidence_path', ''),
            'description_raw': rec.get('description_raw', ''),
            'recruiting_unit_raw': rec.get('recruiting_unit_raw', ''),
            'hiring_department_raw': rec.get('hiring_department_raw', ''),
            'campaign_cohort_raw': rec.get('campaign_cohort_raw', ''),
            'source_record_id': post_id,
            'recruitment_type_raw': rtype,
            'recruitment_scope_note': scope,
            'region': region,
            'overseas_flag': is_hk or is_overseas,
            'record_kind': 'official_position_id',
        }
        # prune empty evidence_path to avoid breaking public()
        if not out['evidence_path']:
            out.pop('evidence_path', None)

        if problems:
            n_rejected += 1
            log_lines.append(json.dumps({'post_id': post_id, 'title': title,
                                         'decision': 'reject', 'reason': ';'.join(problems),
                                         'cities': cities_list}, ensure_ascii=False))
            continue

        accepted.append(out)
        log_lines.append(json.dumps({'post_id': post_id, 'title': title,
                                     'decision': 'accept', 'recruitment_type': rtype,
                                     'region': region, 'cities': cities_list[:6]}, ensure_ascii=False))

    # Merge: existing + accepted (existing unchanged, appended after)
    merged = existing + accepted
    MERGED.parent.mkdir(parents=True, exist_ok=True)
    MERGED.write_text(json.dumps(merged, ensure_ascii=False, indent=2))
    LOG.write_text('\n'.join(log_lines) + '\n')

    # Summary
    from collections import Counter
    rt = Counter(a['recruitment_type_raw'] for a in accepted)
    rg = Counter(a['region'] for a in accepted)
    print('=== Tencent processing summary ===')
    print(f'staging input: {len(staging)}')
    print(f'accepted: {len(accepted)}')
    print(f'dup_internal: {n_dup_internal}, dup_existing: {n_dup_existing}, rejected: {n_rejected}')
    print(f'recruitment_type: {dict(rt)}')
    print(f'region: {dict(rg)}')
    print(f'existing kept: {len(existing)}')
    print(f'merged total: {len(merged)}')
    print(f'written: {MERGED}')
    print(f'log: {LOG}')


if __name__ == '__main__':
    main()
