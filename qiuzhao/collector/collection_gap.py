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


def _unit_key(item: Any) -> Optional[Tuple[str, str]]:
    if isinstance(item, str):
        company, scope = _split_key(item)
    elif isinstance(item, (list, tuple)) and len(item) == 2:
        company, scope = str(item[0]), str(item[1])
    else:
        return None
    return (company, scope) if company and scope else None


def _unit_list(items: Iterable[Any]) -> List[Tuple[str, str]]:
    keys: List[Tuple[str, str]] = []
    for item in items:
        key = _unit_key(item)
        if key is not None and key not in keys:
            keys.append(key)
    return keys


def plan_scope(status: Dict[str, Any], plan: Any = None) -> Dict[str, Any]:
    """Which units this round planned, and whether that list is a full denominator.

    Only real plan fields are used: an explicit ``plan`` argument, p1's
    ``batch_plan``, or p1's ``pending`` list together with the results. Scopes a
    company does not use never appear in those fields, so they are never counted
    as missing, and no target is ever invented from ``companies`` x ``scopes``.

    ``complete`` is True only with a trustworthy full plan:

    * ``argument``: the caller's plan, as given;
    * ``batch_plan``: every company in ``status['companies']`` (when present) has a
      planned unit -- a resume that added companies and died before the plan was
      extended would otherwise pass for a full denominator;
    * ``pending``: only after ``run_finished`` is True *and* ``status['companies']``
      is exactly the set of companies seen in pending + results. A stale pending
      from an earlier segment, or a bare ``run_finished`` flag, proves nothing.

    Any result outside a known plan is listed in ``out_of_plan`` and the plan is
    not complete either. Without a plan field the report covers results only.
    """
    status = status or {}
    results = status.get('results') or {}
    result_keys = _unit_list(results)
    targets = status.get('companies')
    target_set = ({str(item) for item in targets}
                  if isinstance(targets, list) else None)
    if plan is not None:
        source, keys = 'argument', _unit_list(plan)
    elif isinstance(status.get('batch_plan'), list):
        source, keys = 'batch_plan', _unit_list(status['batch_plan'])
    elif isinstance(status.get('pending'), list):
        source, keys = 'pending', _unit_list(status['pending'])
    else:
        return {'keys': None, 'source': None, 'complete': False, 'issue': None,
                'out_of_plan': [], 'targets_missing': []}
    issue = None
    targets_missing: List[str] = []
    if source == 'pending':
        keys = keys + [key for key in result_keys if key not in keys]
        seen_companies = {company for company, _ in keys}
        if target_set is None:
            issue = 'no_target_list'
        else:
            targets_missing = sorted(target_set - seen_companies)
            if targets_missing:
                issue = 'targets_missing_from_plan'
            elif seen_companies - target_set:
                issue = 'units_outside_targets'
            elif status.get('run_finished') is not True:
                issue = 'run_not_finished'
    elif source == 'batch_plan' and target_set is not None:
        targets_missing = sorted(target_set - {company for company, _ in keys})
        if targets_missing:
            issue = 'targets_missing_from_plan'
    if source == 'pending':
        # Pending already absorbs every result; what falls outside is a result for
        # a company that is not a target of this run.
        out_of_plan = [key for key in result_keys
                       if target_set is not None and key[0] not in target_set]
    else:
        out_of_plan = [key for key in result_keys if key not in keys]
    if out_of_plan and issue is None:
        issue = 'results_outside_plan'
    return {'keys': keys, 'source': source, 'complete': issue is None, 'issue': issue,
            'out_of_plan': out_of_plan, 'targets_missing': targets_missing}


def planned_units(status: Dict[str, Any], plan: Any = None
                  ) -> Tuple[Optional[List[Tuple[str, str]]], Optional[str]]:
    """The known planned units and their source (see ``plan_scope`` for trust)."""
    scope = plan_scope(status, plan)
    return scope['keys'], scope['source']


def _not_started_row(company: str, scope: str) -> Dict[str, Any]:
    return {
        'company': company, 'scope': scope, 'status': 'not_started', 'complete': False,
        'expected_total': None, 'collected_jobs': None, 'gap': None,
        'pages_scanned': None, 'pagination_exhausted': None, 'retries': None,
        'error_count': 0, 'error_preview': [], 'published': False, 'publish_error': None,
        'not_started': True,
    }


def unit_records(status: Dict[str, Any], plan: Any = None) -> List[Dict[str, Any]]:
    """One report row per unit, in a stable order.

    ``expected_total`` may legitimately be absent (124 units on 2026-09-20): the
    source never states a total, so no gap can be computed and the unit is listed
    separately instead of being counted as a match or as a gap. Planned units with
    no result are added as ``not_started`` rows whose gap stays unknown.
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
    keys, _ = planned_units(status, plan)
    seen = {_split_key(key) for key in results} | {(row['company'], row['scope']) for row in rows}
    for company, scope in keys or []:
        if (company, scope) not in seen:
            rows.append(_not_started_row(company, scope))
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


def _known_gap(unit: Optional[Dict[str, Any]]) -> Optional[int]:
    """A real integer gap. None stays unknown and is never coerced to 0."""
    if not isinstance(unit, dict):
        return None
    gap = unit.get('gap')
    if isinstance(gap, bool) or not isinstance(gap, int):
        return None
    return gap


def _reliable_complete_zero(unit: Dict[str, Any]) -> bool:
    """True only when this round finished cleanly and the source total was met."""
    if unit.get('not_started') or unit.get('started') is False:
        return False
    if unit.get('publish_error'):
        return False
    if unit.get('status') != 'success' or unit.get('complete') is not True:
        return False
    if _known_gap(unit) != 0:
        return False
    return unit.get('expected_total') is not None and unit.get('collected_jobs') is not None


def _unknown_reason(unit: Dict[str, Any]) -> str:
    if unit.get('not_started'):
        return 'not_started'
    if unit.get('expected_total') is None:
        return 'no_expected_total'
    if unit.get('collected_jobs') is None:
        return 'no_collected_jobs'
    return 'not_reliable_complete'


def compare_to_previous(units: List[Dict[str, Any]],
                        previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """New, grown, narrowed and resolved gaps against the previous report.

    An unknown gap stays unknown. A previous positive gap is resolved only when
    this round has a reliable complete result whose gap is really 0; a failed,
    unknown, not-started or missing unit goes to ``unknown_gaps`` instead.
    """
    current = _index(units)
    previous_units = (previous or {}).get('units') or []
    before = _index(previous_units)
    new_gaps, wider_gaps, narrowed, resolved, unknown = [], [], [], [], []
    for key, unit in sorted(current.items()):
        gap = _known_gap(unit)
        old = before.get(key)
        old_gap = _known_gap(old)
        if gap is None:
            # Only a real previous gap can be lost from view; an old 0 or unknown
            # that is still unknown is already in units_gap_unknown / the units table.
            if old_gap:
                unknown.append({'company': key[0], 'scope': key[1], 'gap': None,
                                'previous_gap': old_gap, 'reason': _unknown_reason(unit)})
            continue
        if gap > 0 and (old_gap is None or old_gap == 0):
            new_gaps.append({'company': key[0], 'scope': key[1], 'gap': gap,
                             'previous_gap': old_gap, 'first_seen': old is None})
        elif old_gap is None:
            continue
        elif gap > old_gap:
            wider_gaps.append({'company': key[0], 'scope': key[1], 'gap': gap,
                               'previous_gap': old_gap, 'delta': gap - old_gap})
        elif 0 < gap < old_gap:
            narrowed.append({'company': key[0], 'scope': key[1], 'gap': gap,
                             'previous_gap': old_gap, 'delta': gap - old_gap})
        elif old_gap > 0 and gap == 0:
            if _reliable_complete_zero(unit):
                resolved.append({'company': key[0], 'scope': key[1],
                                 'previous_gap': old_gap})
            else:
                unknown.append({'company': key[0], 'scope': key[1], 'gap': gap,
                                'previous_gap': old_gap, 'reason': _unknown_reason(unit)})
    for key, old in sorted(before.items()):
        old_gap = _known_gap(old)
        if key not in current and old_gap:
            unknown.append({'company': key[0], 'scope': key[1], 'gap': None,
                            'previous_gap': old_gap, 'reason': 'not_in_this_round'})
    return {
        'previous_date': (previous or {}).get('date'),
        'previous_report': bool(previous),
        'new_gaps': new_gaps,
        'wider_gaps': sorted(wider_gaps, key=lambda item: -item['delta']),
        'narrowed_gaps': sorted(narrowed, key=lambda item: item['delta']),
        'resolved_gaps': resolved,
        'unknown_gaps': unknown,
    }


def build_report(status: Dict[str, Any], *, date: Optional[str] = None,
                 previous: Optional[Dict[str, Any]] = None, plan: Any = None) -> Dict[str, Any]:
    units = unit_records(status, plan)
    scope = plan_scope(status, plan)
    plan_keys, plan_source = scope['keys'], scope['source']
    if plan_keys is None:
        report_scope = 'results_only'
    elif scope['complete']:
        report_scope = 'planned'
    elif scope['out_of_plan']:
        report_scope = 'out_of_plan'
    else:
        report_scope = 'incomplete'
    out_of_plan = [{'company': company, 'scope': unit_scope}
                   for company, unit_scope in scope['out_of_plan']]
    not_started = [unit for unit in units if unit.get('not_started')]
    started = [unit for unit in units if not unit.get('not_started')]
    with_total = [unit for unit in started if unit['expected_total'] is not None]
    without_total = [unit for unit in started if unit['expected_total'] is None]
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
        # The plan's size only when the plan itself is trustworthy; an explicit plan
        # keeps its size even when results fall outside it (see units_out_of_plan).
        'units_planned': (len(plan_keys) if plan_keys is not None and (
            scope['complete'] or scope['issue'] == 'results_outside_plan') else None),
        'units_known_planned': len(plan_keys) if plan_keys is not None else None,
        'units_out_of_plan': len(out_of_plan),
        'plan_complete': bool(scope['complete']),
        'plan_issue': scope['issue'],
        'targets_missing_from_plan': list(scope['targets_missing']),
        'units_not_started': len(not_started),
        'units_gap_unknown': sum(1 for unit in units if unit['gap'] is None),
        'report_scope': report_scope,
        'plan_source': plan_source,
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
        'units_not_started': not_started,
        'units_out_of_plan': out_of_plan,
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
    lines.append('| 计划内未启动 | %d |' % summary.get('units_not_started', 0))
    lines.append('| 缺口未知 | %d |' % summary.get('units_gap_unknown', 0))
    lines.append('| 统计范围 | %s |' % _scope_text(summary))
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
        lines.append('- 状态未知(不算消除):%d 个' % len(comparison.get('unknown_gaps') or []))
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
    if report.get('units_not_started'):
        lines.append('## 计划内未启动的单元(%d 个)' % len(report['units_not_started']))
        lines.append('')
        lines.append('本轮计划内但没有结果,缺口未知,不计为 0。')
        lines.append('')
        lines.append('| 公司 | scope |')
        lines.append('| --- | --- |')
        for unit in report['units_not_started']:
            lines.append('| %s | %s |' % (unit['company'], unit['scope']))
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


def _scope_text(summary: Dict[str, Any]) -> str:
    scope = summary.get('report_scope')
    if scope == 'planned':
        return '本轮计划 %d 个单元(来源 %s)' % (summary['units_planned'], summary['plan_source'])
    if scope in ('incomplete', 'out_of_plan'):
        text = '计划不完整(来源 %s,原因 %s),已知计划 %s 个单元,分母未知' % (
            summary.get('plan_source'), summary.get('plan_issue'),
            _fmt_gap(summary.get('units_known_planned')))
        if summary.get('units_out_of_plan'):
            text += ';计划外结果 %d 个' % summary['units_out_of_plan']
        if summary.get('targets_missing_from_plan'):
            text += ';目标公司未进计划:%s' % '、'.join(summary['targets_missing_from_plan'])
        return text.replace('|', '\\|')
    return '仅已产出结果的单元(上游未给计划,未启动单元不在分母内)'


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
            previous: Any = 'auto', notify_module: Any = None,
            plan: Any = None) -> Dict[str, Any]:
    """Write the JSON + Markdown report, then fire the threshold alerts."""
    run_root = Path(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    if date is None:
        date = run_date(run_root, status)
    if previous == 'auto':
        previous = find_previous_report(run_root, date)
    report = build_report(status, date=date, previous=previous, plan=plan)
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
