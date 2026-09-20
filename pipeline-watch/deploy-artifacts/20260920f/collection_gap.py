"""Daily collection-gap report: the site's own total vs what we actually stored.

Why this module exists (2026-09-20): the p1 status file already carried both
``expected_total`` (the number the source reports) and ``collected_jobs`` (what we
kept) for every unit, but nothing ever compared them.  The 2026-09-20 morning run
finished with 18 units honestly marked ``partial`` -- 2631 missing postings, 2588 of
them 美团 alone -- and nobody saw it.  The problem was never a lying adapter; it was
that nobody read the gap behind ``partial``.

So every p1 run now writes ``runs/<date>/collection-gap.{json,md}`` with:

* one row per unit: company / scope / status / complete / expected_total /
  collected_jobs / gap;
* a summary: how many units match, the **complete-but-short** list (a unit that
  claims ``complete`` while holding fewer rows than the source reports -- the most
  serious class, highlighted separately), the partial-gap TOP 20, and every unit
  whose source never states a total;
* a comparison against the previous day's report: newly appeared gaps and gaps that
  grew.

Key numbers go into the p1 status (and from there into ``receipt.json`` under
``collection_gap``), and a threshold breach is pushed through ``qiuzhao.notify`` when
that module is present on the branch (it lands with ``feat/cc-bot-notifier``), with a
``collection-gap-alert.jsonl`` file as the always-available fallback.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPORT_JSON = 'collection-gap.json'
REPORT_MD = 'collection-gap.md'
ALERT_FILE = 'collection-gap-alert.jsonl'

# A unit that claims complete while missing rows is always an alert: the source said
# how many postings exist and we stored fewer, so the status is lying somewhere.
COMPLETE_BUT_SHORT_ALERT = 0
# A single company missing more than this many postings is worth a message even when
# every unit is honestly marked partial (美团's 2588 on 2026-09-20).
COMPANY_GAP_ALERT_THRESHOLD = 200
TOP_N = 20


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _split_key(key: str) -> Tuple[str, str]:
    company, _, scope = str(key).rpartition('/')
    return (company or str(key)), scope


def unit_records(status: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One report row per unit, in a stable order.

    ``expected_total`` may legitimately be absent (124 units on 2026-09-20): the
    source never states a total, so no gap can be computed and the unit is listed
    separately instead of being counted as a match or as a gap.
    """
    results = (status or {}).get('results') or {}
    rows: List[Dict[str, Any]] = []
    for key, entry in results.items():
        coverage = (entry or {}).get('coverage') or {}
        company, scope = _split_key(key)
        expected = _as_int(coverage.get('expected_total'))
        collected = _as_int(coverage.get('collected_jobs'))
        gap = max(0, expected - collected) if expected is not None and collected is not None else None
        errors = [str(item) for item in (coverage.get('errors') or [])]
        rows.append({
            'company': str(coverage.get('company') or company),
            'scope': str(coverage.get('scope') or scope),
            'status': coverage.get('status'),
            'complete': bool(coverage.get('complete')),
            'expected_total': expected,
            'collected_jobs': collected,
            'gap': gap,
            'pages_scanned': _as_int(coverage.get('pages_scanned')),
            'pagination_exhausted': coverage.get('pagination_exhausted'),
            'retries': _as_int(coverage.get('retries')),
            'error_count': len(errors),
            'error_preview': errors[:3],
            'published': bool((entry or {}).get('published')),
            'publish_error': (entry or {}).get('publish_error'),
        })
    rows.sort(key=lambda row: (-(row['gap'] or 0), row['company'], row['scope']))
    return rows


def _per_company(units: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for unit in units:
        if not unit['gap']:
            continue
        bucket = buckets.setdefault(unit['company'], {
            'company': unit['company'], 'gap': 0, 'gap_units': 0,
            'complete_but_short': 0, 'scopes': []})
        bucket['gap'] += unit['gap']
        bucket['gap_units'] += 1
        bucket['complete_but_short'] += 1 if (unit['complete'] and unit['gap']) else 0
        bucket['scopes'].append('%s:%d' % (unit['scope'], unit['gap']))
    return sorted(buckets.values(), key=lambda item: (-item['gap'], item['company']))


def _index(units: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    return {(unit['company'], unit['scope']): unit for unit in units}


def compare_to_previous(units: List[Dict[str, Any]],
                        previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """New gaps and grown gaps against the previous day's report (if any)."""
    current = _index(units)
    previous_units = (previous or {}).get('units') or []
    before = _index(previous_units)
    new_gaps, wider_gaps, narrowed, resolved = [], [], [], []
    for key, unit in sorted(current.items()):
        gap = unit['gap'] or 0
        old = before.get(key)
        old_gap = (old or {}).get('gap') or 0
        if gap > 0 and old_gap == 0:
            new_gaps.append({'company': key[0], 'scope': key[1], 'gap': gap,
                             'previous_gap': old_gap if old else None,
                             'first_seen': old is None})
        elif gap > old_gap:
            wider_gaps.append({'company': key[0], 'scope': key[1], 'gap': gap,
                               'previous_gap': old_gap, 'delta': gap - old_gap})
        elif gap < old_gap and gap > 0:
            narrowed.append({'company': key[0], 'scope': key[1], 'gap': gap,
                             'previous_gap': old_gap, 'delta': gap - old_gap})
        elif old_gap > 0 and gap == 0:
            resolved.append({'company': key[0], 'scope': key[1],
                             'previous_gap': old_gap})
    return {
        'previous_date': (previous or {}).get('date'),
        'previous_report': bool(previous),
        'new_gaps': new_gaps,
        'wider_gaps': sorted(wider_gaps, key=lambda item: -item['delta']),
        'narrowed_gaps': sorted(narrowed, key=lambda item: item['delta']),
        'resolved_gaps': resolved,
    }


def build_report(status: Dict[str, Any], *, date: Optional[str] = None,
                 previous: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    units = unit_records(status)
    with_total = [unit for unit in units if unit['expected_total'] is not None]
    without_total = [unit for unit in units if unit['expected_total'] is None]
    complete_but_short = [unit for unit in with_total if unit['complete'] and unit['gap']]
    partial_gaps = [unit for unit in with_total if not unit['complete'] and unit['gap']]
    matched = [unit for unit in with_total if not unit['gap']]
    per_company = _per_company(with_total)
    summary = {
        'units_total': len(units),
        'units_with_expected_total': len(with_total),
        'units_matched': len(matched),
        'units_with_gap': len(complete_but_short) + len(partial_gaps),
        'units_complete_but_short': len(complete_but_short),
        'units_partial_with_gap': len(partial_gaps),
        'units_without_expected_total': len(without_total),
        'total_gap': sum(unit['gap'] for unit in with_total if unit['gap']),
        'complete_but_short_gap': sum(unit['gap'] for unit in complete_but_short),
        'partial_gap': sum(unit['gap'] for unit in partial_gaps),
        'companies_with_gap': len(per_company),
        'top3_companies': [{'company': item['company'], 'gap': item['gap']}
                           for item in per_company[:3]],
    }
    return {
        'date': date or dt.datetime.now().strftime('%Y%m%d'),
        'generated_at': _now_iso(),
        'summary': summary,
        'units': units,
        'complete_but_short': complete_but_short,
        'partial_gap_top': partial_gaps[:TOP_N],
        'per_company': per_company,
        'units_without_expected_total': without_total,
        'comparison': compare_to_previous(units, previous),
    }


def _fmt_gap(value: Optional[int]) -> str:
    return '-' if value is None else str(value)


def render_markdown(report: Dict[str, Any]) -> str:
    summary = report['summary']
    comparison = report.get('comparison') or {}
    lines: List[str] = []
    lines.append('# 采集缺口报告 %s' % report['date'])
    lines.append('')
    lines.append('生成时间:%s (UTC+8)' % _local_display(report['generated_at']))
    lines.append('')
    lines.append('**总缺口 %d 条 / 声称完整却少采 %d 个单元(%d 条)/ 缺口最大公司:%s**'
                 % (summary['total_gap'], summary['units_complete_but_short'],
                    summary['complete_but_short_gap'],
                    '、'.join('%s %d' % (item['company'], item['gap'])
                              for item in summary['top3_companies']) or '无'))
    lines.append('')
    lines.append('## 汇总')
    lines.append('')
    lines.append('| 指标 | 值 |')
    lines.append('| --- | --- |')
    lines.append('| 单元总数 | %d |' % summary['units_total'])
    lines.append('| 站点自报总数可比对 | %d |' % summary['units_with_expected_total'])
    lines.append('| 完全吻合 | %d |' % summary['units_matched'])
    lines.append('| 有缺口单元 | %d |' % summary['units_with_gap'])
    lines.append('| 声称 complete 却少采 | **%d** |' % summary['units_complete_but_short'])
    lines.append('| partial 且有缺口 | %d |' % summary['units_partial_with_gap'])
    lines.append('| 站点不报总数 | %d |' % summary['units_without_expected_total'])
    lines.append('| 总缺口 | **%d** |' % summary['total_gap'])
    lines.append('')
    lines.append('## 最严重:声称 complete 却少采')
    lines.append('')
    if not report['complete_but_short']:
        lines.append('无。')
    else:
        lines.append('站点自报总数、我们却存得更少,却仍被标成 complete —— 这一类必须逐条核。')
        lines.append('')
        lines.append('| 公司 | scope | status | expected_total | collected_jobs | gap | 错误摘要 |')
        lines.append('| --- | --- | --- | --- | --- | --- | --- |')
        for unit in report['complete_but_short']:
            lines.append('| %s | %s | %s | %d | %d | **%d** | %s |'
                         % (unit['company'], unit['scope'], unit['status'],
                            unit['expected_total'], unit['collected_jobs'], unit['gap'],
                            _escape(' / '.join(unit['error_preview']) or '-')))
    lines.append('')
    lines.append('## partial 缺口 TOP %d' % TOP_N)
    lines.append('')
    if not report['partial_gap_top']:
        lines.append('无。')
    else:
        lines.append('| 公司 | scope | expected_total | collected_jobs | gap | 错误摘要 |')
        lines.append('| --- | --- | --- | --- | --- | --- |')
        for unit in report['partial_gap_top']:
            lines.append('| %s | %s | %d | %d | **%d** | %s |'
                         % (unit['company'], unit['scope'], unit['expected_total'],
                            unit['collected_jobs'], unit['gap'],
                            _escape(' / '.join(unit['error_preview']) or '-')))
    lines.append('')
    lines.append('## 公司维度(有缺口的公司)')
    lines.append('')
    if not report['per_company']:
        lines.append('无。')
    else:
        lines.append('| 公司 | 合计缺口 | 缺口单元 | 其中声称 complete | scopes |')
        lines.append('| --- | --- | --- | --- | --- |')
        for item in report['per_company']:
            lines.append('| %s | **%d** | %d | %d | %s |'
                         % (item['company'], item['gap'], item['gap_units'],
                            item['complete_but_short'], _escape(', '.join(item['scopes']))))
    lines.append('')
    lines.append('## 与前一天对比')
    lines.append('')
    if not comparison.get('previous_report'):
        lines.append('没有可比对的前一日报告(本报告首次生成,或前一日未产出)。')
    else:
        lines.append('基线:%s' % comparison.get('previous_date'))
        lines.append('')
        lines.append('- 新出现的缺口:%d 个' % len(comparison['new_gaps']))
        lines.append('- 缺口变大的单元:%d 个' % len(comparison['wider_gaps']))
        lines.append('- 缺口收窄:%d 个' % len(comparison['narrowed_gaps']))
        lines.append('- 已消除:%d 个' % len(comparison['resolved_gaps']))
        if comparison['new_gaps']:
            lines.append('')
            lines.append('| 新缺口公司 | scope | gap | 备注 |')
            lines.append('| --- | --- | --- | --- |')
            for item in comparison['new_gaps']:
                lines.append('| %s | %s | %d | %s |'
                             % (item['company'], item['scope'], item['gap'],
                                '首次出现(前日无此单元)' if item['first_seen']
                                else '前日无缺口(%s)' % item['previous_gap']))
        if comparison['wider_gaps']:
            lines.append('')
            lines.append('| 缺口变大公司 | scope | 前日 | 今日 | 增量 |')
            lines.append('| --- | --- | --- | --- | --- |')
            for item in comparison['wider_gaps'][:TOP_N]:
                lines.append('| %s | %s | %d | %d | **+%d** |'
                             % (item['company'], item['scope'], item['previous_gap'],
                                item['gap'], item['delta']))
    lines.append('')
    lines.append('## 站点不报总数的单元(%d 个)'
                 % summary['units_without_expected_total'])
    lines.append('')
    if not report['units_without_expected_total']:
        lines.append('无。')
    else:
        lines.append('这些单元无法比对,缺口不可知 —— 需要的是给适配器补上"站点自报总数"这条证据。')
        lines.append('')
        lines.append('| 公司 | scope | status | collected_jobs |')
        lines.append('| --- | --- | --- | --- |')
        for unit in report['units_without_expected_total']:
            lines.append('| %s | %s | %s | %s |'
                         % (unit['company'], unit['scope'], unit['status'],
                            _fmt_gap(unit['collected_jobs'])))
    lines.append('')
    lines.append('## 附:全部单元')
    lines.append('')
    lines.append('| 公司 | scope | status | complete | expected_total | collected_jobs | gap |')
    lines.append('| --- | --- | --- | --- | --- | --- | --- |')
    for unit in report['units']:
        lines.append('| %s | %s | %s | %s | %s | %s | %s |'
                     % (unit['company'], unit['scope'], unit['status'],
                        'yes' if unit['complete'] else 'no',
                        _fmt_gap(unit['expected_total']), _fmt_gap(unit['collected_jobs']),
                        _fmt_gap(unit['gap'])))
    lines.append('')
    return '\n'.join(lines)


def _escape(text: str) -> str:
    return str(text).replace('|', '\\|').replace('\n', ' ')[:160]


def _local_display(iso: str) -> str:
    """Report timestamps are UTC (machine-readable); show them in UTC+8."""
    moment = dt.datetime.fromisoformat(iso)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')


def default_run_root(data_dir, run_dir=None) -> Path:
    """Where ``runs/<date>/`` lives.

    The daily chain runs p1 with ``--data-dir runs/<date>/data``, so the report
    belongs one level up.  Any other layout falls back to the run directory itself.
    """
    data_path = Path(data_dir)
    if data_path.name == 'data' and data_path.parent.name.isdigit():
        return data_path.parent
    return Path(run_dir) if run_dir is not None else data_path


def find_previous_report(run_root: Path, date: str) -> Optional[Dict[str, Any]]:
    """The most recent earlier ``collection-gap.json`` under the same runs/ tree."""
    base = Path(run_root).parent
    if not base.is_dir():
        return None
    for candidate in sorted((p for p in base.iterdir()
                             if p.is_dir() and p.name.isdigit() and p.name < str(date)),
                            reverse=True):
        path = candidate / REPORT_JSON
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict):
                return payload
    return None


def evaluate_alerts(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    summary = report['summary']
    alerts: List[Dict[str, Any]] = []
    if summary['units_complete_but_short'] > COMPLETE_BUT_SHORT_ALERT:
        alerts.append({
            'event': 'collection_gap.complete_but_short',
            'severity': 'critical',
            'count': summary['units_complete_but_short'],
            'gap': summary['complete_but_short_gap'],
            'units': ['%s/%s %d/%d' % (unit['company'], unit['scope'],
                                       unit['collected_jobs'], unit['expected_total'])
                      for unit in report['complete_but_short'][:5]],
        })
    for item in report['per_company']:
        if item['gap'] > COMPANY_GAP_ALERT_THRESHOLD:
            alerts.append({
                'event': 'collection_gap.company_gap',
                'severity': 'warning',
                'company': item['company'],
                'gap': item['gap'],
                'threshold': COMPANY_GAP_ALERT_THRESHOLD,
                'scopes': item['scopes'],
            })
    return alerts


def _load_notify():
    """``qiuzhao.notify`` lands with feat/cc-bot-notifier; absent means file fallback."""
    try:
        from qiuzhao import notify as notify_module  # type: ignore
    except Exception:
        return None
    return notify_module


def emit_alerts(report: Dict[str, Any], run_root: Path,
                notify_module: Any = None) -> Dict[str, Any]:
    alerts = evaluate_alerts(report)
    run_root = Path(run_root)
    result: Dict[str, Any] = {'alerts': alerts, 'alert_file': None, 'notify': None}
    if not alerts:
        return result
    alert_path = run_root / ALERT_FILE
    run_root.mkdir(parents=True, exist_ok=True)
    with alert_path.open('a', encoding='utf-8') as handle:
        for alert in alerts:
            handle.write(json.dumps({'ts': _now_iso(), 'date': report['date'], **alert},
                                    ensure_ascii=False) + '\n')
    result['alert_file'] = str(alert_path)

    module = notify_module if notify_module is not None else _load_notify()
    if module is None:
        result['notify'] = {'channel': 'file', 'sent': False,
                            'reason': 'qiuzhao.notify is not on this branch '
                                      '(merge feat/cc-bot-notifier to enable push)'}
        return result
    delivered = []
    for alert in alerts:
        try:
            outcome = module.notify(alert['event'], fields=_notify_fields(alert))
            delivered.append({'event': alert['event'], 'sent': bool(outcome), 'result': outcome})
        except Exception as error:  # a notifier must never break the daily run
            delivered.append({'event': alert['event'], 'sent': False,
                              'error': type(error).__name__ + ': ' + str(error)[:200]})
    result['notify'] = {'channel': 'qiuzhao.notify', 'sent': any(d['sent'] for d in delivered),
                        'deliveries': delivered}
    return result


def _notify_fields(alert: Dict[str, Any]) -> Dict[str, Any]:
    fields = {key: value for key, value in alert.items() if key not in ('event', 'severity')}
    fields['severity'] = alert.get('severity')
    return fields


def run_date(run_root: Path, status: Optional[Dict[str, Any]] = None) -> str:
    """The report's date: the runs/<date> directory, else the run start in UTC+8.

    ``started_at`` is UTC (a 06:10 CST run starts at 22:10 the previous day), so the
    directory name must win whenever it looks like a date.
    """
    name = Path(run_root).name
    if len(name) == 8 and name.isdigit():
        return name
    started = str((status or {}).get('started_at') or '')
    try:
        moment = dt.datetime.fromisoformat(started)
    except ValueError:
        return dt.datetime.now().strftime('%Y%m%d')
    if moment.tzinfo is not None:
        moment = moment.astimezone(dt.timezone(dt.timedelta(hours=8)))
    return moment.strftime('%Y%m%d')


def publish(status: Dict[str, Any], run_root: Path, *, date: Optional[str] = None,
            previous: Any = 'auto', notify_module: Any = None) -> Dict[str, Any]:
    """Write the JSON + Markdown report, then fire the threshold alerts."""
    run_root = Path(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    if date is None:
        date = run_date(run_root, status)
    if previous == 'auto':
        previous = find_previous_report(run_root, date)
    report = build_report(status, date=date, previous=previous)
    json_path = run_root / REPORT_JSON
    md_path = run_root / REPORT_MD
    tmp = json_path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, json_path)
    tmp_md = md_path.with_suffix('.md.tmp')
    tmp_md.write_text(render_markdown(report), encoding='utf-8')
    os.replace(tmp_md, md_path)
    alerts = emit_alerts(report, run_root, notify_module=notify_module)
    return {'date': date, 'summary': report['summary'],
            'comparison': {key: (len(value) if isinstance(value, list) else value)
                           for key, value in report['comparison'].items()},
            'json_path': str(json_path), 'md_path': str(md_path),
            'alerts': alerts['alerts'], 'alert_file': alerts['alert_file'],
            'notify': alerts['notify']}
