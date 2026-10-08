"""ChinaHR public campaign JSONP directory; no login or JavaScript execution."""
import datetime as dt
import json
import re
from urllib.parse import urlencode

CALLBACK = 'qiuzhao_public_directory'
API = 'https://ats.chinahr.com/api/'


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('ChinaHR invalid native identity')
    return value


def jsonp(raw):
    text = raw.strip()
    if text.startswith('/**/'):
        text = text[4:]
    prefix = CALLBACK + '('
    if not text.startswith(prefix) or not text.endswith(');'):
        raise ValueError('ChinaHR invalid fixed JSONP envelope')
    data = json.loads(text[len(prefix):-2])
    if not isinstance(data, dict) or type(data.get('code')) is not int or data.get('code') != 1:
        raise ValueError('ChinaHR unsuccessful response envelope')
    return data


def bootstrap(raw, campaign, conditions_title):
    marker = 'window.chinahr_cmp_json_data'
    match = re.search(re.escape(marker) + r'\s*=\s*', raw)
    if not match:
        raise ValueError('ChinaHR campaign bootstrap missing')
    config, _ = json.JSONDecoder().raw_decode(raw[match.end():])
    if not isinstance(config, dict) or not isinstance(config.get('jobs'), dict):
        raise ValueError('ChinaHR invalid campaign bootstrap')
    jobs = config['jobs']
    token = jobs.get('token')
    if not isinstance(token, str) or not token.strip() or jobs.get('show') is not True:
        raise ValueError('ChinaHR public campaign selector unavailable')
    root = identity(jobs.get('firstId'))
    # Exact disclosed campaign and shared title; asset folder/year is not proof.
    if campaign not in raw:
        raise ValueError('ChinaHR campaign identity changed')
    matches = []
    for group in config.get('gonggao', []):
        if not isinstance(group, dict):
            continue
        for tab in group.get('tabs', []):
            if isinstance(tab, dict) and tab.get('title') == conditions_title:
                content = tab.get('content')
                if isinstance(content, list) and all(isinstance(x, str) for x in content):
                    matches.append(content)
    if len(matches) != 1:
        raise ValueError('ChinaHR shared conditions not uniquely disclosed')
    return token, root, matches[0]


def conditions_for(lines, unit, title):
    """Exact disclosed institution/role heading, with no HQ fallback to branches."""
    sections = []
    active = None
    basic, notes = [], []
    region = ''
    for line in lines:
        if line.startswith('&'):
            region = line
            active = None
        elif region.startswith('&一'):
            basic.append(line)
        elif region.startswith('&三'):
            notes.append(line)
        elif region.startswith('&二'):
            if re.match(r'^（[一二三四五六七八九十]+）', line):
                heading = re.sub(r'^（[^）]+）', '', line).rstrip('。')
                active = []
                # Keep occurrences: repeated headings cannot silently overwrite.
                sections.append((heading, active))
            elif active is not None:
                active.append(line)
    candidates = [(heading, content) for heading, content in sections
                  if heading.removesuffix('岗位') == unit]
    if len(candidates) != 1:
        return '', '适用通用招聘条件未能与所属单位唯一匹配；保留岗位正文及官网条件引用，需核验完整门槛。'
    heading, content = candidates[0]
    specialized = [line for line in content if '主要招收' in line]
    matched = []
    for line in specialized:
        label = line.split('主要招收', 1)[0].strip().removesuffix('岗位')
        if label == title:
            matched.append(line)
    # A generic title prefix or an unknown specialization does not identify one
    # of several role clauses. Preserve the original job and disclosed reference.
    if specialized and len(matched) != 1:
        return '', '所属单位的专门岗位条件未能与岗位名称精确唯一匹配；保留岗位正文及官网条件引用，需核验完整门槛。'
    selected = [line for line in content if line not in specialized or line in matched]
    if not selected:
        return '', '所属单位条件段未提供可唯一匹配的岗位条件，需核验完整门槛。'
    return '\n'.join(basic + [heading] + selected + notes), ''


def collect_campaign(collector, *, page_url, campaign, conditions_title, group):
    from .run import base_job, clean, now, failure_details
    rows, errors, scopes = [], [], []
    checked = now()
    state = {'status': 'partial', 'complete': False, 'checked_at': checked,
             'scopes': scopes, 'errors': errors, 'collected_jobs': 0}

    token = ''
    def diagnostic(error, phase):
        details = failure_details(error, phase)
        return {key: value.replace(token, '[public-project-selector]')
                if token and isinstance(value, str) else value for key, value in details.items()}

    def request(kind, params, name):
        # Public project selector never persisted in request/evidence URLs.
        url = API + kind + '?' + urlencode({**params, 'callback': CALLBACK})
        response = jsonp(collector.fetch(url))
        observed = now()
        safe = {'code': response['code'], 'totalCount': response.get('totalCount'),
                'retMsg': [{k: v for k, v in row.items() if k in {'id', 'name', 'parentId', 'companyId', 'companyName', 'jobNo', 'jobDesc', 'education', 'experience', 'workPlaceList', 'applyEndTime', 'recruitNumber'}}
                           if isinstance(row, dict) else row for row in response.get('retMsg', [])]
                if isinstance(response.get('retMsg'), list) else response.get('retMsg'),
                'checked_at': observed, 'endpoint': API + kind,
                'page': params.get('page'), 'pageSize': params.get('pageSize')}
        path = collector.evidence_file(name, json.dumps(safe, ensure_ascii=False))
        return response, path, observed

    def pages(kind, params, prefix, accept, progress=None):
        total, seen = None, set()
        # Existing UI pageSize10000, bounded finite safeguard; cap is partial.
        for page in range(1, 101):
            data, path, observed = request(kind, {**params, 'page': page, 'pageSize': 10000}, f'{prefix}-{page}.json')
            values = data.get('retMsg')
            count = data.get('totalCount')
            if not isinstance(values, list) or type(count) is not int or count < 0:
                raise ValueError('ChinaHR invalid list/totalCount')
            if total is None:
                total = count
                if progress is not None:
                    progress['expected_total'] = total
            elif total != count:
                raise ValueError('ChinaHR totalCount drift')
            for value in values:
                if not isinstance(value, dict):
                    raise ValueError('ChinaHR row is not an object')
                key = identity(value.get('id'))
                if key in seen:
                    raise ValueError('ChinaHR duplicate native identity within listing')
                seen.add(key)
                if progress is not None:
                    progress['observed_unique_ids'] = len(seen)
                accept(value, path, observed)
            if len(seen) > total:
                raise ValueError('ChinaHR rows exceed totalCount')
            if len(seen) == total:
                return total
            if not values:
                raise ValueError('ChinaHR positive total ended before all native identities')
        raise ValueError('ChinaHR page cap reached')

    try:
        raw = collector.fetch(page_url)
        token, root, conditions = bootstrap(raw, campaign, conditions_title)
        # Store only relevant public conditions; raw bootstrap contains selector.
        conditions_path = collector.evidence_file('boc-ats-conditions.json', json.dumps(
            {'title': conditions_title, 'content': conditions, 'source_url': page_url, 'checked_at': checked}, ensure_ascii=False))
        nodes = {}
        def node(value, *_):
            if not isinstance(value.get('name'), str) or not value['name'].strip() or not isinstance(value.get('parentId'), str):
                raise ValueError('ChinaHR invalid company tree node')
            nodes[value['id']] = value
        state['metadata_total'] = pages('company/list', {'token': token}, 'boc-ats-company', node)
        if root not in nodes or nodes[root]['name'] != campaign:
            raise ValueError('ChinaHR selected campaign root mismatch')
        children = {}
        for key, value in nodes.items():
            parent = value['parentId']
            if parent and parent not in nodes:
                raise ValueError('ChinaHR orphan metadata node')
            children.setdefault(parent, []).append(key)
        leaves = []
        reachable = {root}
        for first in children.get(root, []):
            reachable.add(first)
            for second in children.get(first, []):
                reachable.add(second)
                for third in children.get(second, []):
                    reachable.add(third)
                    if children.get(third):
                        raise ValueError('ChinaHR unexpected deeper company hierarchy')
                    leaves.append((first, second, third))
        if reachable != set(nodes):
            raise ValueError('ChinaHR metadata outside verified campaign hierarchy')
        if not leaves:
            raise ValueError('ChinaHR no valid third-level role selectors')
        native = {}
        for first, second, third in leaves:
            scope = {'selector_id': third, 'unit': nodes[second]['name'], 'complete': False}
            scopes.append(scope)
            def job(value, path, observed):
                key = identity(value['id'])
                if value.get('companyId') != third or not isinstance(value.get('name'), str) or not value['name'].strip():
                    raise ValueError('ChinaHR job identity/selector mismatch')
                signature = {k: v for k, v in value.items() if k not in {'applyCount', 'companyId', 'companyName'}}
                if key in native:
                    if native[key] != (signature, second):
                        raise ValueError('ChinaHR conflicting native job across selectors')
                    return
                if not isinstance(value.get('jobDesc'), str):
                    raise ValueError('ChinaHR invalid embedded job introduction')
                intro = clean(value.get('jobDesc'))
                shared, gap = conditions_for(conditions, nodes[second]['name'], value['name'])
                if not intro:
                    raise ValueError('ChinaHR job introduction missing')
                if conditions_title not in intro:
                    shared, gap = '', '岗位未明确引用该通用条件；保留其官网正文，适用条件需核验。'
                jobrow = base_job('boc-ats-' + key, group, value['name'], page_url, observed)
                for field in ('education', 'experience', 'jobNo'):
                    if value.get(field) is not None and not isinstance(value[field], str):
                        raise ValueError('ChinaHR invalid job field type: ' + field)
                places = value.get('workPlaceList')
                if not isinstance(places, list) or any(not isinstance(x, dict) for x in places):
                    raise ValueError('ChinaHR invalid workPlaceList')
                if any(x.get(field) is not None and not isinstance(x[field], str) for x in places for field in ('city', 'province')):
                    raise ValueError('ChinaHR invalid disclosed city')
                cities = list(dict.fromkeys(x.get('city') or x.get('province') for x in places if x.get('city') or x.get('province')))
                end = value.get('applyEndTime')
                deadline = None
                if end is not None and (type(end) is not int or end < 0):
                    raise ValueError('ChinaHR invalid deadline timestamp')
                if type(end) is int and end > 0:
                    moment = dt.datetime.fromtimestamp(end / 1000, dt.timezone(dt.timedelta(hours=8)))
                    if moment.hour == moment.minute == moment.second == 0:
                        moment -= dt.timedelta(seconds=1)
                    deadline = moment.date().isoformat()
                majors = '\n'.join(line for line in shared.splitlines() if '主要招收' in line)
                degree_clauses = [line for line in shared.splitlines()
                                  if re.match(r'^\d+[．.]大学本科及以上学历', line)]
                education = degree_clauses[0] if len(degree_clauses) == 1 else value.get('education') or ''
                jobrow.update(source_record_id=key, job_no=value.get('jobNo'), record_kind='ats_native_job',
                    recruiting_unit_raw=nodes[second]['name'], job_category=nodes[third]['name'],
                    source_group_key=third, campaign_cohort_raw=campaign, cities=cities,
                    education_raw=education, education_summary_raw=value.get('education') or '',
                    major_requirements_raw=majors, cohort_raw=value.get('experience') or '',
                    description_raw=intro + ('\n适用官网通用条件：\n' + clean(shared) if shared else ''),
                    application_url='https://applyjob.chinahr.com/apply/job/wish/' + key,
                    source_name='中国银行官网授权ChinaHR公开招聘目录', evidence_path=path,
                    shared_conditions_evidence_path=conditions_path, requirements_scope='embedded_official_job_and_matched_shared_conditions' if shared else 'embedded_official_job_with_unresolved_shared_conditions',
                    detail_presentation=gap, status_note=gap, detail_complete=not bool(gap),
                    deadline=deadline, deadline_type='explicit' if deadline else 'undisclosed',
                    status='expired' if deadline and deadline < observed[:10] else 'unverified')
                if gap:
                    scope.setdefault('condition_gaps', []).append(key)
                native[key] = (signature, second)
                rows.append(jobrow)
            try:
                scope['expected_total'] = pages('job/list', {'token': token, 'companyId': third}, 'boc-ats-job-' + third, job, scope)
                scope['complete'] = True
            except Exception as error:
                scope.update(error_type=type(error).__name__, error=diagnostic(error, 'native_listing').get('error', ''))
                errors.append({'scope': third, **diagnostic(error, 'native_listing')})
        complete = all(s['complete'] for s in scopes) and not errors
        gaps = any(s.get('condition_gaps') for s in scopes)
        state.update(complete=complete and not gaps, listing_complete=complete,
                     status='success' if complete and not gaps else 'partial')
    except Exception as error:
        errors.append(diagnostic(error, 'campaign_metadata'))
    state['collected_jobs'] = len(rows)
    return rows, state
