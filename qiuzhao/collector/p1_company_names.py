"""Company-name cleanup for ``p1_platform_companies.json``.

Platform tenant titles leak the recruiting-site chrome into the config
(``海大官网招聘门户``, ``AIVA汽车校园招聘门户网``, ``招聘门户``...). The daily chain
must show a company's short/common name, not a web-page title.

Two rules, in order:

1. Clean names are left untouched. A curated short name such as ``安踏集团`` must
   never be replaced by an unrelated Xianyu-table row: the table's first name for
   that tenant is ``FILA`` because the artifact sorts names alphabetically.
2. A dirty name (contains a site token such as 招聘/门户/网申/官网, a tagline
   separator, an English "campus recruitment", a trailing numeric code or a slogan
   prefix) is replaced by the Xianyu table's ``公司名称`` for the same platform
   slug when one exists; otherwise the site-title suffix is stripped.

The Xianyu artifact (``pipeline-watch/xianyu-ats-slugs.json``) is the preferred
source because it carries the name column of the user's own company table.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

SECTIONS = ('beisen', 'moka', 'feishu', 'workday', 'successfactors')

# Longest first so "校园招聘门户网" is removed before the bare "招聘".
SITE_SUFFIXES = (
    '官方网申渠道', '官网招聘门户', '校园招聘门户网', '校园招聘门户', '招聘门户网站',
    '校园招聘', '社会招聘', '招聘官网', '官网招聘', '招聘门户', '招聘网申',
    '招聘网', '人才招聘', '招聘系统', '招聘公众号', '招聘专场', '网申渠道',
    '网申', '招聘', '门户',
)
SITE_TOKENS = ('招聘', '门户', '网申', '官网', '校招', '校园')
SEPARATORS = ('||', '--', '—', '–', '|')
BRACKET_TAG = re.compile(r'[（(【\[“‘"](?:新|最新|热招|急招|校招|社招|官方)?[）)】\]”’"]\s*$')
BRACKET_SITE = re.compile(r'[（(【\[]\s*(?:校园招聘|社会招聘|校招|社招|招聘)\s*[）)】\]]\s*$')
ENGLISH_SITE = re.compile(r'(?i)campus\s*recruitment|recruitment|career[s]?\b')
TRAILING_CODE = re.compile(r'[\u4e00-\u9fff]\d{3,}$')
SLOGAN_PREFIX = re.compile(r'^\s*[“"「][^”"」]*[”"」]\s*')


def normalize(name):
    """Case/space-insensitive key for matching names."""
    return re.sub(r'\s+', '', str(name or '')).lower()


def is_site_title(name):
    """Whether a config name looks like a recruiting-site title rather than a name."""
    text = str(name or '').strip()
    if not text:
        return False
    if any(token in text for token in SITE_TOKENS):
        return True
    if any(sep in text for sep in SEPARATORS):
        return True
    if ENGLISH_SITE.search(text):
        return True
    if SLOGAN_PREFIX.match(text):
        return True
    if TRAILING_CODE.search(text):
        return True
    return False


def strip_site_title(name):
    """Remove tags/slogans/site suffixes from a dirty name without a table match."""
    text = re.sub(r'\s+', ' ', str(name or '')).strip()
    text = SLOGAN_PREFIX.sub('', text).strip()
    while True:
        updated = BRACKET_TAG.sub('', text).strip()
        updated = BRACKET_SITE.sub('', updated).strip()
        if updated == text:
            break
        text = updated
    for sep in ('||', '|'):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
            break
    for sep in ('--', '—', '–', '-'):
        if sep in text:
            head, tail = text.split(sep, 1)
            if any(token in head for token in SITE_TOKENS):
                text = head.strip()
            break
    text = re.sub(r'[-—–\s]+\d{3,}\s*(?:届.*)?$', '', text).strip()
    text = re.sub(r'\d{4}\s*(?:届|校招|校园|秋招|春招).*$', '', text).strip()
    changed = True
    while changed:
        changed = False
        for suffix in SITE_SUFFIXES:
            if text.endswith(suffix) and len(text) > len(suffix):
                text = text[:-len(suffix)].strip()
                changed = True
                break
    text = re.sub(r'[\s\-—–|]+$', '', text).strip()
    return text


def _common_prefix(left, right):
    count = 0
    for a, b in zip(left, right):
        if a != b:
            break
        count += 1
    return count


def pick_table_name(original, stripped, table_names):
    """Choose the Xianyu-table name that best matches the stripped config name."""
    table_names = [str(name).strip() for name in table_names or [] if str(name).strip()]
    if not table_names:
        return None
    norm_stripped = normalize(stripped)
    norm_original = normalize(original)
    for table in table_names:
        if normalize(table) == norm_stripped and norm_stripped:
            return table
    scored = sorted(((_common_prefix(norm_stripped, normalize(table)), -len(table), table)
                     for table in table_names), reverse=True)
    best_score, _, best = scored[0]
    if best_score >= 2:
        return best
    if norm_original and any(normalize(table) == norm_original for table in table_names):
        return next(table for table in table_names if normalize(table) == norm_original)
    return table_names[0]


def clean_company_name(name, table_names=()):
    """Return the company's short/common name for the given config entry name."""
    original = re.sub(r'\s+', ' ', str(name or '')).strip()
    if not original or not is_site_title(original):
        return original
    stripped = strip_site_title(original)
    table = pick_table_name(original, stripped, table_names)
    if table:
        return table
    return stripped or original


def load_table_names(artifact_path):
    """``{(section, slug): [table names]}`` from the Xianyu ATS extraction."""
    try:
        data = json.loads(Path(artifact_path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    mapping = {}
    for section in ('beisen', 'moka', 'feishu'):
        for entry in data.get(section) or []:
            slug = entry.get('slug')
            if not slug:
                continue
            names = list(entry.get('company_names') or [])
            if entry.get('company') and entry['company'] not in names:
                names.insert(0, entry['company'])
            mapping[(section, str(slug))] = names
    return mapping


def _entry_name(entry):
    return entry if isinstance(entry, str) else str((entry or {}).get('name') or '')


def resolve_cleanup(config, table_names):
    """Resolve every entry to one unique name per config section.

    Two tenants may legitimately map to the same table company (科大国创云网 and
    科大国创股份 both list 科大国创). The pipeline keys ``NAME_TO_SLUG`` by name,
    so a duplicate would silently drop a tenant. Colliding entries fall back to
    their stripped title (e.g. 科大国创云网 / 科大国创股份有限公司) or, failing
    that, their original name.
    """
    resolved = {}
    for section in SECTIONS:
        entries = config.get(section) or {}
        if not isinstance(entries, dict):
            continue
        section_rows = {}
        for slug, entry in entries.items():
            original = _entry_name(entry)
            names = table_names.get((section, str(slug))) or []
            cleaned = clean_company_name(original, names)
            stripped = strip_site_title(original) if is_site_title(original) else ''
            section_rows[str(slug)] = {'original': original, 'cleaned': cleaned,
                                       'stripped': stripped, 'table_names': names}
        counts = Counter(row['cleaned'] for row in section_rows.values() if row['cleaned'])
        for slug, row in section_rows.items():
            if row['cleaned'] and counts[row['cleaned']] > 1 and row['original'] != row['cleaned']:
                candidate = row['stripped']
                unique = candidate and candidate != row['cleaned'] and all(
                    other is row or other['cleaned'] != candidate
                    for other in section_rows.values())
                row['cleaned'] = candidate if unique else row['original']
        for slug, row in section_rows.items():
            resolved[(section, slug)] = row
    return resolved


def plan_cleanup(config, table_names):
    """Return one plan row per config entry (section/slug/original/cleaned/source)."""
    resolved = resolve_cleanup(config, table_names)
    rows = []
    for section in SECTIONS:
        entries = config.get(section) or {}
        if not isinstance(entries, dict):
            continue
        for slug in entries:
            row = resolved[(section, str(slug))]
            cleaned = row['cleaned']
            if cleaned == row['original']:
                source = 'unchanged'
            elif cleaned in row['table_names']:
                source = 'table'
            else:
                source = 'strip'
            rows.append({'section': section, 'slug': str(slug),
                         'original_name': row['original'], 'cleaned_name': cleaned,
                         'source': source})
    return rows


def apply_cleanup(config, table_names):
    """Return a deep copy of the config with every entry name replaced."""
    resolved = resolve_cleanup(config, table_names)
    cleaned = json.loads(json.dumps(config, ensure_ascii=False))
    for section in SECTIONS:
        entries = cleaned.get(section)
        if not isinstance(entries, dict):
            continue
        for slug, entry in entries.items():
            name = resolved[(section, str(slug))]['cleaned']
            if isinstance(entry, str):
                entries[slug] = name
            elif isinstance(entry, dict) and entry.get('name'):
                entry['name'] = name
    return cleaned


def write_csv(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=('section', 'slug', 'original_name',
                                                    'cleaned_name', 'source'))
        writer.writeheader()
        writer.writerows(rows)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path,
                        default=Path(__file__).with_name('p1_platform_companies.json'))
    parser.add_argument('--artifact', type=Path,
                        default=Path('pipeline-watch/xianyu-ats-slugs.json'))
    parser.add_argument('--csv', type=Path,
                        default=Path('pipeline-watch/company-name-cleanup.csv'))
    parser.add_argument('--write', action='store_true',
                        help='rewrite the config file in place (default: dry run)')
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding='utf-8'))
    table_names = load_table_names(args.artifact)
    rows = plan_cleanup(config, table_names)
    changed = [row for row in rows if row['source'] != 'unchanged']
    write_csv(rows, args.csv)
    print(json.dumps({'entries': len(rows), 'changed': len(changed),
                      'by_source': {source: sum(1 for row in rows if row['source'] == source)
                                    for source in ('unchanged', 'table', 'strip')},
                      'csv': str(args.csv)}, ensure_ascii=False))
    if args.write:
        args.config.write_text(json.dumps(apply_cleanup(config, table_names),
                                          ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
        print('wrote ' + str(args.config))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
