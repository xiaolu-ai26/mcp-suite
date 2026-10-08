"""Platform-level Beisen (zhiye.com) campus/intern/social adapter.

One adapter covers every tenant: adding a company is one line in
``p1_platform_companies.json``. Contract matches the per-company
``p1_sources_*`` modules: ``COMPANIES`` + ``collect(company, scope, output_dir)``
returning ``{'jobs': [...], 'coverage': {...}}`` and writing the same evidence.

Request budget: ``QIUZHAO_PLATFORM_REQUEST_BUDGET`` (or the ``max_requests``
argument) caps network calls per tenant per run. Production defaults to no cap
(``DEFAULT_REQUEST_BUDGET = None``); the offline verification runs set 20 only to
stay polite in front of the Beisen WAF, which would truncate a large tenant.
"""
from __future__ import annotations
import json
import hashlib
from datetime import datetime, timezone
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urljoin, parse_qs

try:
    from . import p1_sources_01_10 as shared
except ImportError:  # direct module execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from qiuzhao.collector import p1_sources_01_10 as shared

CONFIG_PATH = Path(__file__).with_name('p1_platform_companies.json')
MODULE_PATH = 'qiuzhao.collector.p1_platform_beisen'
DEFAULT_CATEGORIES = {'1': 'social', '2': 'campus', '3': 'intern'}
IGNORE = '__ignore__'
FIELDS = ['LocId', 'Degree', 'Kind', 'OrgId', 'Category', 'PostDate', 'HeadCount',
          'EndTime', 'YearsOfWorking', 'Duty', 'Require']
# Details are fetched for verification (and as a fallback when the list omits
# role text), never above the remaining request budget.
DETAIL_VERIFY_LIMIT = 5
# Production default: no cap. Budgeting is an opt-in politeness guard; the offline
# verification runs pass 20 on purpose via QIUZHAO_PLATFORM_REQUEST_BUDGET /
# max_requests. A low default would truncate a healthy tenant: 安踏集团 alone has
# 158 published rows, which needs far more than 20 list/detail requests. A run is
# still bounded per scope by the pipeline's --scope-timeout / --max-run-seconds.
DEFAULT_REQUEST_BUDGET = None
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')


class BudgetExhausted(RuntimeError):
    pass


def _read_platform():
    data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    return data.get('beisen') or {}


def _entry_name(entry):
    return entry if isinstance(entry, str) else str((entry or {}).get('name') or '')


def _load_companies():
    companies = {}
    for key, entry in _read_platform().items():
        if isinstance(entry, dict) and entry.get('enabled') is False:
            continue  # parked survey line: kept on file, never registered
        name = _entry_name(entry)
        if name:
            companies[str(key)] = name
    return companies


COMPANIES = _load_companies()
NAME_TO_SLUG = {name: key for key, name in COMPANIES.items()}


def reload_config():
    """Re-read the shared JSON config (tests point CONFIG_PATH at a fixture)."""
    global COMPANIES, NAME_TO_SLUG
    COMPANIES = _load_companies()
    NAME_TO_SLUG = {name: key for key, name in COMPANIES.items()}
    return COMPANIES


def merged_registry():
    """Company name -> adapter module path for the pipeline REGISTRY."""
    from qiuzhao.collector import p1_platform_moka as moka
    registry = {name: MODULE_PATH for name in COMPANIES.values()}
    registry.update({name: moka.MODULE_PATH for name in moka.COMPANIES.values()})
    return registry


def resolve(company):
    if company in COMPANIES:
        return company
    if company in NAME_TO_SLUG:
        return NAME_TO_SLUG[company]
    raise ValueError('unknown beisen company: ' + str(company))


def _entry(key):
    entry = _read_platform().get(key) or {}
    return entry if isinstance(entry, dict) else {}


def host_for(key):
    return str(_entry(key).get('host') or f'https://{key}.zhiye.com')


def categories_for(key):
    mapping = dict(DEFAULT_CATEGORIES)
    for category in _entry(key).get('ignore_categories') or []:
        mapping[str(category)] = IGNORE
    for category, scope in (_entry(key).get('categories') or {}).items():
        mapping[str(category)] = scope
    return mapping


def _budget_limit(max_requests):
    if max_requests is not None:
        return int(max_requests)
    raw = os.environ.get('QIUZHAO_PLATFORM_REQUEST_BUDGET')
    return int(raw) if raw and raw.strip() else DEFAULT_REQUEST_BUDGET


def _make_session():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    session = requests.Session()
    session.headers['User-Agent'] = UA
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=0)))
    return session


def _has_budget(budget):
    return budget is None or budget['limit'] is None or budget['used'] < budget['limit']


def _spend(budget):
    if budget is None:
        return
    if budget['limit'] is not None and budget['used'] >= budget['limit']:
        raise BudgetExhausted('per-tenant request budget reached')
    budget['used'] += 1


def _send(budget, call, *args, **kwargs):
    """One polite retry (429/WAF/connection), then give up and let the caller block."""
    import requests
    _spend(budget)
    try:
        response = call(*args, **kwargs)
    except requests.RequestException:
        time.sleep(2.0)
        _spend(budget)
        response = call(*args, **kwargs)
    if getattr(response, 'status_code', 200) in (429, 403):
        time.sleep(2.0)
        _spend(budget)
        response = call(*args, **kwargs)
    response.raise_for_status()
    return response


def _get(session, url, budget, **kwargs):
    return _send(budget, session.get, url, **kwargs)


def _post(session, url, budget, **kwargs):
    return _send(budget, session.post, url, **kwargs)


def _date(value):
    text = str(value or '')
    if text.startswith('0001') or not text.strip():
        return ''
    match = re.match(r'(\d{4}-\d{2}-\d{2})', text)
    if not match:
        return text[:32]
    year = int(match.group(1)[:4])
    if year >= 2100:  # platform sentinel such as 2222-02-02 means "no deadline"
        return ''
    return match.group(1)


def _description(row):
    duty = shared.text((row or {}).get('Duty'))
    require = shared.text((row or {}).get('Require'))
    if not duty and not require:
        return ''
    return duty + '\n任职要求\n' + require


def _job_from(row, name, scope, host, key, detail_source):
    ident = row['Id']
    duty = shared.text(row.get('Duty'))
    require = shared.text(row.get('Require'))
    description = (duty + '\n任职要求\n' + require).strip()
    locations = row.get('LocNames') or []
    location = ' / '.join(str(x) for x in locations)
    job = shared.job(name, scope, ident, row.get('JobAdName') or '',
                     host + '/' + scope + '/detail?jobAdId=' + ident, description, location, row)
    job['recruitment_type_raw'] = {'CategoryId': row.get('CategoryId'), 'Category': row.get('Category')}
    job['scope_evidence'] = (f'Official Beisen CategoryId={row.get("CategoryId")}; '
                             f'Category={row.get("Category")}; tenant={key}')
    published = _date(row.get('PostDate'))
    job['published_at'] = published
    job['publication_date'] = published
    job['source_updated_at'] = _date(row.get('ChangeDate'))
    deadline = _date(row.get('EndTime'))
    job['deadline_raw'] = deadline
    if deadline:
        job['deadline'] = deadline
        job['deadline_type'] = 'explicit'
    job['detail_source'] = detail_source
    job['source_publication_field'] = 'PostDate' if published else ''
    return job


def _require_sentences(value):
    return [x.strip() for x in re.split(r'[\n。；;]', shared.text(value)) if x.strip()]


def _hard_education(value):
    """Only explicit requirements; preferences/equivalent experience are not gates."""
    hard = []
    ambiguous = False
    degree = r'(?:博士(?:研究生)?|硕士(?:研究生)?|本科|学士|大专|专科|中专|高中)'
    sentences = _require_sentences(value)
    for index, sentence in enumerate(sentences):
        if not re.search(degree + r'|bachelor|master|ph\.?d', sentence, re.I):
            continue
        # Commas do not end qualification semantics: an adjacent alternative
        # can replace the degree, so inspect the full sentence first.
        context = sentence
        if index + 1 < len(sentences) and re.match(r'^(?:或|同等|等同|具有同等|具备同等)', sentences[index + 1]):
            context += '；' + sentences[index + 1]
        qualification_parts = re.split(r'[，,；;]', context)
        alternative = re.search(r'(?:或|或者|亦可|也可).*?(?:同等|等同|equivalent)|经验替代', context, re.I)
        uncertain_equivalence = any(
            re.search(r'同等|等同|equivalent', part, re.I)
            and not re.search(r'优先|优选|preferred', part, re.I)
            for part in qualification_parts)
        if alternative or uncertain_equivalence or re.search(r'不限|不限制|不要求|无需', context):
            ambiguous = True
            continue
        for clause in re.split(r'[，,]', sentence):
            if not re.search(degree + r'|bachelor|master|ph\.?d', clause, re.I):
                continue
            # Preference belongs to this degree clause, not every degree in
            # the sentence. Alternatives above still bind across commas.
            if re.search(r'优先|优选|preferred', clause, re.I):
                ambiguous = True
                continue
            if (re.search(degree + r'(?:及以上|以上)?(?:学历|学位)', clause)
                    or re.search(r'学历(?:要求)?[：:为\s]*' + degree, clause)
                    or re.search(r'(?:不低于|至少(?:具有|具备)?|最低(?:为)?)\s*(?:大学)?' + degree, clause)
                    or re.search(degree + r'(?:及以上|以上)', clause)):
                hard.append(clause.strip())
            else:
                ambiguous = True
    return '；'.join(dict.fromkeys(hard)), ambiguous


def _education_levels(value):
    levels = set()
    for expression, level in ((r'高中|中专', 1), (r'大专|专科', 2),
                              (r'本科|学士', 3), (r'硕士', 4), (r'博士', 5)):
        if re.search(expression, str(value or '')):
            levels.add(level)
    if levels and re.search(r'及以上|以上|不低于|至少', str(value or '')):
        levels.update(range(min(levels), 6))
    return levels


def _annotate_fields(job, row, listed, detail, list_checked_at, detail_checked_at, list_file):
    """Expose per-field observation origins; never turn omitted keys into missing facts."""
    detail = detail or {}
    detail_file = 'detail-' + str(row['Id']) + '.json'
    provenance = {}
    def record(output, fields):
        origins = []
        for field in fields:
            incoming = field in detail
            value = row.get(field)
            origins.append({'field': field,
                            'source': 'official_detail' if incoming else 'official_list',
                            'checked_at': detail_checked_at if incoming else list_checked_at,
                            'evidence_file': detail_file if incoming else list_file,
                            'value_state': ('explicit_null' if value is None and field in row else
                                            'explicit_empty' if value == [] or (isinstance(value, str) and not value.strip()) else
                                            'provided' if field in row else 'not_disclosed')})
        sources = {x['source'] for x in origins}
        provenance[output] = {'source': next(iter(sources)) if len(sources) == 1 else 'official_list_and_detail',
                              'checked_at': min(x['checked_at'] for x in origins),
                              'components': origins}
        if len(origins) == 1:
            provenance[output]['value_state'] = origins[0]['value_state']
    mappings = {'job_title': ['JobAdName'], 'description_raw': ['Duty', 'Require'],
                'cities': ['LocNames'], 'education_raw': ['Degree'] if shared.text(row.get('Degree')) else ['Require'],
                'major_requirements_raw': ['Require'], 'published_at': ['PostDate'],
                'deadline_raw': ['EndTime'], 'source_updated_at': ['ChangeDate'],
                'experience_raw': ['YearsOfWorking'], 'recruitment_type_raw': ['CategoryId', 'Category']}
    for output, fields in mappings.items():
        record(output, fields)
    notes = []
    list_degree = shared.text(listed.get('Degree'))
    if 'Degree' in row:
        job['source_fields']['Degree'] = row['Degree']
    if 'Degree' in listed:
        job['source_fields']['beisen_list_Degree'] = listed['Degree']
    if 'Require' in detail:
        require = shared.text(detail.get('Require'))
        job['major_requirements_raw'] = '；'.join(x for x in _require_sentences(require)
            if re.search(r'专业|major|degree in', x, re.I))
        hard, ambiguous = _hard_education(require)
        if hard:
            job['education_raw'] = hard
            record('education_raw', ['Require'])
            if list_degree:
                prior_levels, required_levels = _education_levels(list_degree), _education_levels(hard)
                # A plain list label is a summary, not an exact exclusion set.
                # Disjoint labels alone cannot establish a true contradiction.
                list_scope_explicit = bool(re.search(r'仅限|只限|限于|及以上|以上|不低于', list_degree))
                relation = ('compatible' if prior_levels and required_levels and prior_levels & required_levels else
                            'conflicting' if prior_levels and required_levels and list_scope_explicit else 'unresolved')
                job['field_observation_differences'] = {'education_raw': {
                    'list_degree': list_degree, 'requirement_clause': hard, 'relation': relation,
                    'selection_basis': 'explicit_requirement_semantics_not_fetch_recency',
                    'list_checked_at': list_checked_at, 'detail_checked_at': detail_checked_at}}
                label = {'compatible': '兼容表述差异', 'conflicting': '官方表述冲突，待核验',
                         'unresolved': '表述关系未能确认，待核验'}[relation]
                notes.append(f'学历主展示按明确任职条款“{hard}”；列表摘要“{list_degree}”（{list_checked_at}），'
                             f'详情条款（{detail_checked_at}）：{label}。')
                if relation != 'compatible':
                    job['status_note'] = label + '；学历主展示按明确任职条款，原摘要与时点见来源说明。'
        elif ambiguous:
            # Structured disclosure is retained; a preference is not a mandatory degree.
            job['education_raw'] = shared.text(row.get('Degree'))
            record('education_raw', ['Degree'])
            job['status_note'] = '详情学历涉及偏好、资格替代或未能可靠解析；完整原文保留，未结构化为硬性学历门槛，待核验。'
            notes.append(f'保留官网学历摘要“{job["education_raw"]}”；详情表述“{require}”不作为硬性门槛。'
                         f'列表核验{list_checked_at}；详情核验{detail_checked_at}。')
    if 'Degree' in detail and list_degree and not _hard_education(detail.get('Require'))[0]:
        new_degree = shared.text(detail.get('Degree'))
        if new_degree != list_degree:
            disclosure = new_degree or '未披露'
            notes.append(f'列表学历摘要“{list_degree}”（{list_checked_at}）；详情学历字段“{disclosure}”'
                         f'（{detail_checked_at}），明确空值不以旧摘要回填。')
    if detail:
        labels = {'job_title': '标题', 'description_raw': '职责/要求', 'cities': '城市',
                  'education_raw': '学历', 'major_requirements_raw': '专业', 'published_at': '发布日期',
                  'deadline_raw': '截止日期', 'experience_raw': '经验', 'recruitment_type_raw': '招聘类别'}
        retained = [labels[k] for k, v in provenance.items() if k in labels
                    and job.get(k) not in (None, '', [])
                    and any(c['source'] == 'official_list' and c['value_state'] == 'provided' for c in v['components'])]
        if retained:
            notes.insert(0, '详情未重述的' + '、'.join(dict.fromkeys(retained))
                         + f'保留同一运行官网列表事实（核验{list_checked_at}）；详情核验{detail_checked_at}。')
    job['field_provenance'] = provenance
    if notes:
        job['detail_presentation'] = ' '.join(notes)
    used = [v for k, v in provenance.items() if job.get(k) not in (None, '', [], {})]
    checked = min(v['checked_at'] for v in used) if used else list_checked_at
    job['verified_at'] = checked
    job['reviewed_at'] = checked
    if detail and any(c['source'] == 'official_list' and c['value_state'] == 'provided'
                      for v in used for c in v['components']):
        job['detail_source'] = 'official_list_and_detail'


def _list_identity(key, entry_host, host, body):
    # Bind both the configured entry and its verified redirect origin. Scope is
    # deliberately absent: categories are interpreted separately by each call.
    return {'source': 'beisen', 'version': 1, 'tenant': key,
            'entry_origin': shared.moka_host_origin(entry_host),
            'origin': shared.moka_host_origin(host),
            'endpoint': '/api/Jobad/GetJobAdPageList', 'params': body,
            'config_sha256': hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()}


def _complete_pages(pages):
    """Validate the raw list, including the terminal page and every total."""
    if not isinstance(pages, list) or not pages:
        return False
    total = None
    seen = set()
    for index, page in enumerate(pages):
        if not isinstance(page, dict) or page.get('Code') != 200:
            return False
        rows, count = page.get('Data'), page.get('Count')
        if (not isinstance(rows, list) or isinstance(count, bool)
                or not isinstance(count, int) or count < 0):
            return False
        if total is not None and count != total:
            return False
        total = count
        if not rows:
            return index == len(pages) - 1 and len(seen) == total
        for row in rows:
            if not isinstance(row, dict):
                return False
            ident = row.get('Id')
            if not isinstance(ident, str) or not ident or ident in seen:
                return False
            seen.add(ident)
    return False


def _list_cache_path(output_dir, identity):
    run_id = shared.current_logical_run()
    if (not run_id or not os.environ.get('QIUZHAO_P1_DETAIL_CACHE_ROOT')
            or not identity['origin'] or not identity['entry_origin']):
        return None
    digest = hashlib.sha256(json.dumps([identity, run_id], sort_keys=True,
                                      ensure_ascii=False).encode()).hexdigest()
    return shared.moka_cache_root(output_dir) / 'beisen-lists' / (digest + '.json')


def _pages_digest(pages):
    return hashlib.sha256(json.dumps(pages, sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()


def _load_list_snapshot(path, identity):
    if path is None:
        return None
    payload = shared._read_json(path)
    if (not isinstance(payload, dict) or payload.get('identity') != identity
            or payload.get('run_id') != shared.current_logical_run()
            or payload.get('complete') is not True
            or payload.get('fetched_on') != shared.moka_today()):
        return None
    stamp = shared.parse_moka_time(payload.get('list_checked_at'))
    if (stamp is None or stamp.date().isoformat() != shared.moka_today()
            or stamp > datetime.now(timezone.utc) + shared.MOKA_TIME_FUTURE_SKEW
            or not _complete_pages(payload.get('pages'))
            or payload.get('pages_sha256') != _pages_digest(payload['pages'])):
        return None
    return payload


def _store_list_snapshot(path, identity, pages, checked_at):
    if path is None or not _complete_pages(pages):
        return
    stamp = shared.parse_moka_time(checked_at)
    if stamp is None or stamp.date().isoformat() != shared.moka_today():
        return
    try:
        shared._write_json(path, {'identity': identity,
                                 'run_id': shared.current_logical_run(),
                                 'fetched_on': stamp.date().isoformat(), 'complete': True,
                                 'list_checked_at': checked_at, 'pages': pages,
                                 'pages_sha256': _pages_digest(pages)})
    except OSError:
        pass  # An unavailable optimization must not invalidate a real list.


def validate_legacy_route(route, scope='social'):
    """One explicitly configured old Social HTML protocol; no inferred scopes."""
    required = {'adapter','method','host','list_path','tenant_title','recruitment_label'}
    if not isinstance(route,dict) or set(route)!=required or scope!='social':
        raise ValueError('Unknown Beisen legacy route parameters/scope')
    host=urlsplit(route['host']) if isinstance(route['host'],str) else None
    if (host is None or host.scheme!='https' or not re.fullmatch(r'[a-z0-9-]+\.zhiye\.com',host.netloc)
            or host.path or host.query or host.fragment or route['adapter']!='beisen_legacy'
            or route['method']!='GET' or route['list_path']!='/Social'
            or route['recruitment_label']!='社会招聘'
            or not isinstance(route['tenant_title'],str) or not route['tenant_title'].strip()):
        raise ValueError('Unverified Beisen legacy host/method/identity')
    return route


def _legacy_identity(soup,route):
    title=soup.title.get_text(strip=True) if soup.title else ''
    if not title.startswith(route['tenant_title']+'招聘系统--'):
        raise ValueError('Legacy Beisen tenant identity mismatch')


def _legacy_page(raw,url,route):
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(raw,'html.parser');_legacy_identity(soup,route)
    if not soup.title.get_text(strip=True).endswith('--'+route['recruitment_label']):
        raise ValueError('Legacy list recruitment scope not verified')
    tables=soup.select('.positionlist-newtemplate table.listtable')
    counts=soup.select('.positionlist-newtemplate .tablenote')
    footers=soup.select('.positionlist-newtemplate .tablefooter')
    if len(tables)!=1 or len(counts)!=1 or len(footers)!=1:
        raise ValueError('Legacy list envelope/pagination missing or ambiguous')
    count=re.fullmatch(r'共\s*(\d+)\s*条记录',counts[0].get_text(strip=True))
    paging=re.findall(r'当前第\s*(\d+)\s*/\s*(\d+)\s*页',footers[0].get_text(' ',strip=True))
    if count is None or len(paging)!=1:raise ValueError('Legacy list total/page unknown')
    total=int(count[1]);current,pages=map(int,paging[0])
    if not 1<=current<=pages<=10000:raise ValueError('Legacy page range invalid')
    rows=[];problems=[]
    for tr in tables[0].find_all('tr'):
        if tr.find('th'):continue
        cells=tr.find_all('td',recursive=False)
        if not cells:continue
        if total==0 and not tr.find('a',href=True):continue
        anchors=tr.select('a[href]')
        if len(cells)!=4 or len(anchors)!=1:
            problems.append('Legacy list row shape/ID unknown');continue
        anchor=anchors[0];link=urljoin(url,anchor['href']);parts=urlsplit(link)
        ident=re.fullmatch(r'/zpdetail/(\d+)',parts.path)
        title=(anchor.get('title') or anchor.get_text(' ',strip=True)).strip()
        if (parts.scheme+'://'+parts.netloc!=route['host'] or parts.query or parts.fragment
                or ident is None or anchor.get('jobadid')!=(ident[1] if ident else None)
                or not title or '...' in title or '…' in title):
            problems.append('Legacy list native ID/title/host not verified');continue
        rows.append({'Id':ident[1],'JobAdName':title,'detail_url':link,
                     'LocNames':[cells[2].get('title') or cells[2].get_text(' ',strip=True)],
                     'PostDate':cells[3].get_text(' ',strip=True)})
    next_links=[a for a in footers[0].find_all('a') if a.get_text(strip=True)=='下一页' and a.get('href')]
    next_url=None
    if current<pages:
        if len(next_links)!=1:problems.append('Legacy next page evidence missing/ambiguous')
        else:
            candidate=urljoin(url,next_links[0]['href']);parts=urlsplit(candidate);query=parse_qs(parts.query,keep_blank_values=True)
            if (parts.scheme+'://'+parts.netloc!=route['host'] or parts.path.rstrip('/').lower()!='/social'
                    or parts.fragment or query!={'PageIndex':[str(current+1)]}):
                problems.append('Legacy next page has unverified parameters/host')
            else:next_url=candidate
    elif next_links:problems.append('Legacy terminal page still links next')
    if total and not rows:problems.append('Legacy positive total has no valid rows')
    return total,current,pages,rows,next_url,problems


def _legacy_detail(raw,ident,route):
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(raw,'html.parser');_legacy_identity(soup,route)
    titles=soup.select('.xiangqingtitle');containers=soup.select('.xiangqingcontain')
    if len(titles)!=1 or len(containers)!=1:raise ValueError('Legacy detail envelope unknown')
    title=titles[0].get_text(' ',strip=True);body=containers[0];fields={}
    for label in body.select('li.ntitle'):
        value=label.find_next_sibling('li')
        key=label.get_text(strip=True).rstrip('：:')
        if key in fields or value is None or 'nvalue' not in value.get('class',[]):
            raise ValueError('Legacy detail field shape/ambiguity')
        fields[key]=value.get_text(' ',strip=True)
    apply=soup.select('#apply[url]')
    apply_parts=urlsplit(apply[0]['url']) if len(apply)==1 else None
    apply_query=parse_qs(apply_parts.query,keep_blank_values=True) if apply_parts else {}
    if (apply_parts is None or apply_parts.scheme or apply_parts.netloc or apply_parts.fragment
            or apply_parts.path!='/Portal/Resume/ResumeItem' or set(apply_query)-{'jid','r'}
            or apply_query.get('jid')!=[ident]
            or ('r' in apply_query and apply_query['r']!=['/zpdetail/'+ident])
            or fields.get('招聘类别')!=route['recruitment_label'] or not title):
        raise ValueError('Legacy detail native identity/scope mismatch')
    sections={};blocks=body.select('.xiangqingtext')
    if len(blocks)!=1:raise ValueError('Legacy detail role section missing/ambiguous')
    paragraphs=blocks[0].find_all('p');used_values=set()
    def paragraph_text(paragraph):
        # Old html.parser/bs4 can nest subsequent paragraphs under a void br.
        # Own paragraph text excludes descendant p sections so neither label nor
        # another section's body is borrowed into this paragraph.
        return '\n'.join(str(node).strip() for node in paragraph.strings
                         if node.find_parent('p') is paragraph and str(node).strip())
    names=('工作地点','工作职责','任职资格')
    for index,label in enumerate(paragraphs):
        key=paragraph_text(label).rstrip('：:')
        if key not in names:continue
        if key in sections:raise ValueError('Legacy detail repeated requirement section')
        value=paragraphs[index+1] if index+1<len(paragraphs) else None
        text=paragraph_text(value) if value is not None else ''
        if text.rstrip('：:') in names:text=''
        elif text:
            if id(value) in used_values:raise ValueError('Legacy detail body reused across sections')
            used_values.add(id(value))
        sections[key]=text
    return {'Id':ident,'JobAdName':title,'Category':fields['招聘类别'],
            'Kind':fields.get('工作性质',''),'HeadCount':fields.get('招聘人数',''),
            'PostDate':fields.get('发布时间',''),'EndTime':fields.get('截止时间',''),
            'LocNames':[sections['工作地点']] if sections.get('工作地点') else [],
            'Duty':sections.get('工作职责',''),'Require':sections.get('任职资格','')}


def collect_legacy(company,scope,output_dir,route,max_requests=None):
    """Legacy HTML branch reached only by a typed, explicit scope route."""
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    coverage=shared.coverage(str(route.get('host','')) if isinstance(route,dict) else '')
    jobs=[];budget={'limit':_budget_limit(max_requests),'used':0};saved=[];listed={}
    try:
        validate_legacy_route(route,scope)
        host=route['host'];url=host+route['list_path'];session=_make_session()
        coverage['source_url']=url
        coverage['scope_request']={'company':company,'scope':scope,'source_url':url,'params':dict(route)}
        coverage['scope_evidence']='Official tenant Social HTML label='+route['recruitment_label']
        expected=None;expected_pages=None;page_number=1
        def fetch(link):
            response=_get(session,link,budget,timeout=(10,30),allow_redirects=False)
            if response.status_code!=200 or response.url!=link:
                raise ValueError('Legacy response status/origin changed')
            response.encoding='utf-8'
            return response.text,datetime.now(timezone.utc).isoformat()
        while url:
            raw,checked=fetch(url);filename=f'legacy-list-{page_number}.html'
            (out/filename).write_text(raw,encoding='utf-8');saved.append(filename)
            coverage['pages_scanned']+=1
            total,current,pages,rows,next_url,problems=_legacy_page(raw,url,route)
            if expected is None:
                expected=total;expected_pages=pages;coverage['expected_total']=total
            if total!=expected or pages!=expected_pages or current!=page_number:
                raise ValueError('Legacy total/page identity drift')
            coverage['errors'].extend(problems)
            for row in rows:
                if row['Id'] in listed:raise ValueError('Legacy duplicate native ID across pages')
                listed[row['Id']]={**row,'list_checked_at':checked,'list_file':filename}
            coverage['list_checked_at']=checked
            coverage['last_page_evidence']=f'{filename}; page={current}/{pages}; total={total}; unique={len(listed)}'
            if current==pages:
                coverage['pagination_exhausted']=not problems and len(listed)==total
                break
            if next_url is None:break
            url=next_url;page_number+=1
        if expected is None or len(listed)!=expected or not coverage.get('pagination_exhausted'):
            coverage['errors'].append('Legacy listing not proven complete')
        for ident,row in listed.items():
            try:
                raw,checked=fetch(row['detail_url']);filename=f'legacy-detail-{ident}.html'
                (out/filename).write_text(raw,encoding='utf-8');saved.append(filename)
                detail=_legacy_detail(raw,ident,route)
                if not _description(detail):raise ValueError('Legacy detail has no role body')
                location_from_list=not detail['LocNames'] and bool(row['LocNames'])
                if location_from_list:detail['LocNames']=row['LocNames']
                publication_from_list=not detail['PostDate'] and bool(row['PostDate'])
                if publication_from_list:detail['PostDate']=row['PostDate']
                job=_job_from(detail,company,scope,host,urlsplit(host).hostname,'official_detail')
                for field in ('source_url','detail_url','application_url'):job[field]=row['detail_url']
                job.update(recruitment_type_raw={'Category':detail['Category']},
                    scope_evidence='Official legacy detail 招聘类别='+detail['Category'],
                    recruiting_unit_raw=route['tenant_title'],employment_type_raw=detail['Kind'],
                    headcount_raw=detail['HeadCount'],list_checked_at=row['list_checked_at'],
                    detail_checked_at=checked,detail_verified=True,evidence_path=filename,
                    description_source='official legacy detail 工作职责/任职资格',
                    field_provenance={'description_raw':{'source':'official_detail','checked_at':checked,'evidence_file':filename},
                                      'cities':{'source':'official_list' if location_from_list else 'official_detail',
                                                'checked_at':row['list_checked_at'] if location_from_list else checked,
                                                'evidence_file':row['list_file'] if location_from_list else filename},
                                      'published_at':{'source':'official_list' if publication_from_list else 'official_detail',
                                                      'checked_at':row['list_checked_at'] if publication_from_list else checked,
                                                      'evidence_file':row['list_file'] if publication_from_list else filename}})
                facts=[label+'：'+detail[field] for label,field in (('招聘类别','Category'),('工作性质','Kind'),('招聘人数','HeadCount'),('发布时间','PostDate')) if detail.get(field) and not (field=='PostDate' and publication_from_list)]
                job['description_raw']='\n'.join(facts)+'\n'+job['description_raw']
                retained=[label for used,label in ((location_from_list,'地点'),(publication_from_list,'发布日期')) if used]
                if retained:
                    job['detail_source']='official_list_and_detail'
                    job['detail_presentation']='官网详情本次未单独披露'+'、'.join(retained)+'，保留本次官网列表事实；来源时间 '+row['list_checked_at']
                job['verified_at']=job['reviewed_at']=row['list_checked_at'] if retained else checked
                missing=[k for k in ('Duty','Require') if not detail[k]]
                job['detail_missing_fields']=missing
                job['source_missing_fields']=[label for field,label in (('Duty','description'),('Require','requirement')) if field in missing]
                if missing:coverage['errors'].append(f'Legacy detail {ident} missing '+','.join(missing))
                jobs.append(job)
            except BudgetExhausted:
                coverage['request_budget_exhausted']=True;break
            except Exception as error:coverage['errors'].append(f'detail {ident}: {type(error).__name__}: {error}')
        coverage['detail_complete']=expected is not None and len(jobs)==expected and not coverage['errors']
    except BudgetExhausted:coverage['request_budget_exhausted']=True
    except Exception as error:coverage['errors'].append(f'{type(error).__name__}: {error}')
    coverage.update(list_observed_ids=sorted(listed),selected_job_ids=sorted(listed),
                    evidence=saved,evidence_files=saved,request_budget=budget)
    if coverage.get('request_budget_exhausted'):coverage['errors'].append('Legacy request budget exhausted')
    return shared.finish(jobs,coverage)


def collect(company, scope, output_dir, max_requests=None):
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if scope not in shared.TYPES:
        raise ValueError('invalid scope')
    key = resolve(company)
    name = COMPANIES[key]
    host = host_for(key)
    categories = categories_for(key)
    budget = {'limit': _budget_limit(max_requests), 'used': 0}
    coverage = shared.coverage(host)
    coverage['source_url'] = host
    jobs = []
    session = _make_session()
    unmapped = {}
    try:
        page = _get(session, host, budget, timeout=(10, 30))
        page.encoding = 'utf-8'
        (output_dir / 'official-entry.html').write_text(page.text)
        portal_ids = set(re.findall(r'"PortalId"\s*:\s*"([^"]+)"', page.text))
        if len(portal_ids) != 1:
            raise ValueError('Official Beisen PortalId missing or ambiguous (WAF challenge?)')
        portal = portal_ids.pop()
        host = urlsplit(page.url).scheme + '://' + urlsplit(page.url).netloc
        coverage['source_url'] = host
        body = {'PortalId': portal, 'PageIndex': 0, 'PageSize': 50, 'Category': [],
                'KeyWords': '', 'SpecialType': 0, 'DisplayFields': FIELDS}

        identity = _list_identity(key, host_for(key), host, body)
        cache_path = _list_cache_path(output_dir, identity)
        snapshot = _load_list_snapshot(cache_path, identity)
        raw_pages = []
        list_checked_at = snapshot['list_checked_at'] if snapshot else ''
        coverage['list_cache_reused'] = snapshot is not None

        def list_page(index):
            payload = dict(body, PageIndex=index)
            if snapshot is not None:
                payload_json = snapshot['pages'][index]
            else:
                response = _post(session, host + '/api/Jobad/GetJobAdPageList', budget,
                                 json=payload, timeout=(10, 45))
                payload_json = response.json()
            raw_pages.append(payload_json)
            (output_dir / f'list-{index}.json').write_text(json.dumps(payload_json, ensure_ascii=False))
            coverage['pages_scanned'] += 1
            if payload_json.get('Code') != 200:
                raise ValueError(str(payload_json)[:300])
            return payload_json

        selected = []
        list_files = {}
        seen = set()
        total = None
        index = 0
        while True:
            payload_json = list_page(index)
            rows = payload_json.get('Data') or []
            count = payload_json.get('Count')
            if (not isinstance(payload_json.get('Data'), list)
                    or isinstance(count, bool) or not isinstance(count, int) or count < 0):
                raise ValueError('Invalid Beisen list rows/count')
            if total is not None and count != total:
                raise ValueError('Official count changed during scan')
            total = count
            if not rows:
                coverage['pagination_exhausted'] = True
                coverage['last_page_evidence'] = (f'index={index};rows=0;'
                                                  + (f'prior_total={total};' if total is not None else '')
                                                  + f'total={count}')
                break
            for row in rows:
                ident = row.get('Id')
                if not ident or ident in seen:
                    raise ValueError('Repeated Beisen pagination GUID')
                seen.add(ident)
                list_files[ident] = f'list-{index}.json'
                actual = str(row.get('CategoryId'))
                if actual not in categories:
                    unmapped[actual] = row.get('Category')
                    continue
                if categories[actual] == IGNORE:
                    continue
                if categories[actual] == scope:
                    selected.append(row)
            index += 1
        if total is not None and len(seen) != total:
            raise ValueError(f'Incomplete list: {len(seen)} vs {total}')
        if not _complete_pages(raw_pages):
            raise ValueError('Incomplete Beisen list snapshot')
        if snapshot is None:
            list_checked_at = datetime.now(timezone.utc).isoformat()
            _store_list_snapshot(cache_path, identity, raw_pages, list_checked_at)
        coverage['list_checked_at'] = list_checked_at
        coverage['list_total'] = total
        coverage['expected_total'] = len(selected)
        coverage['unmapped_categories'] = {k: v for k, v in unmapped.items()}
        for category, label in sorted(unmapped.items()):
            coverage['errors'].append(f'Unknown official Beisen category {category}: {label}')

        for position, row in enumerate(selected):
            listed = row
            detail_for_fields = None
            description = _description(row)
            verified = False
            detail_checked_at = ''
            detail_missing_fields = []
            detail_unprovided_fields = []
            if _has_budget(budget) and (position < DETAIL_VERIFY_LIMIT or not description):
                try:
                    params = {'jobAdId': row['Id'], 'portalId': portal,
                              'category': str(row.get('CategoryId')),
                              'displayFields': json.dumps(FIELDS)}
                    response = _get(session, host + '/api/JobAd/GetJobAdInfo', budget,
                                    params=params, timeout=(10, 45))
                    detail_env = response.json()
                    (output_dir / f'detail-{row["Id"]}.json').write_text(
                        json.dumps(detail_env, ensure_ascii=False))
                    if detail_env.get('Code') != 200:
                        coverage.setdefault('detail_fetch_errors', []).append(
                            f'{row["Id"]}: {str(detail_env)[:200]}')
                    else:
                        detail = detail_env.get('Data') or {}
                        if (detail.get('Id') != row['Id']
                                or str(detail.get('CategoryId')) != str(row.get('CategoryId'))):
                            message = f'{row["Id"]}: detail identity/category mismatch'
                            coverage.setdefault('detail_fetch_errors', []).append(message)
                            coverage['errors'].append(message)
                            continue  # Conflicting official identity/scope is quarantined.
                        else:
                            required = {'JobAdName', 'Duty', 'Require', 'LocNames', 'Category'}
                            missing = sorted((required | set(row)) - set(detail))
                            # Usable new detail values win. A GET DTO omission
                            # or empty value is not proof that known facts were cleared.
                            row = dict(row)
                            detail_for_fields = {}
                            detail_unprovided_fields = []
                            for field, value in detail.items():
                                unprovided = (value is None or value == []
                                              or isinstance(value, str) and not value.strip())
                                known_list = (field in row and row[field] is not None and row[field] != []
                                              and not (isinstance(row[field], str) and not row[field].strip()))
                                # This GET DTO is not a PATCH: null/empty alone
                                # does not prove the employer cleared known facts.
                                if unprovided and known_list:
                                    detail_unprovided_fields.append(field)
                                    continue
                                row[field] = value
                                detail_for_fields[field] = value
                            description = _description(row)
                            verified = True
                            detail_checked_at = datetime.now(timezone.utc).isoformat()
                            detail_missing_fields = missing
                except BudgetExhausted:
                    coverage['request_budget_exhausted'] = True
                    break
                except Exception as error:  # official list remains authoritative
                    coverage.setdefault('detail_fetch_errors', []).append(
                        f'{row["Id"]}: {type(error).__name__}: {error}'[:300])
            if not description:
                coverage['errors'].append('No official description for ' + str(row.get('Id')))
                continue
            job = _job_from(row, name, scope, host, key,
                            'official_detail' if verified else 'official_list')
            job['list_checked_at'] = list_checked_at
            _annotate_fields(job, row, listed, detail_for_fields, list_checked_at,
                             detail_checked_at, list_files[row['Id']])
            if verified:
                job['detail_checked_at'] = detail_checked_at
                job['detail_verified'] = True
                job['detail_missing_fields'] = detail_missing_fields
                job['detail_unprovided_fields'] = detail_unprovided_fields
                labels = {'JobAdName': '标题', 'Duty': '职责', 'Require': '任职要求',
                          'LocNames': '城市', 'Degree': '学历', 'Category': '招聘类别',
                          'PostDate': '发布日期', 'EndTime': '截止日期', 'YearsOfWorking': '经验'}
                unprovided = [labels[field] for field in detail_unprovided_fields if field in labels]
                if unprovided:
                    prior_note = job.get('detail_presentation') or ''
                    job['detail_presentation'] = (prior_note + ' 官网详情本次未提供'
                        + '、'.join(unprovided)
                        + f'的新披露；这不能证明招聘方清空已有条件，保留本运行官网列表事实（{list_checked_at}），'
                        + f'详情观察{detail_checked_at}。').strip()
                # A missing detail key is not a source-wide missing field when
                # the verified list disclosed it; shared.job uses merged facts.
            jobs.append(job)
        coverage['detail_verified_count'] = sum(1 for j in jobs if j.get('detail_verified'))
        coverage['list_only_count'] = sum(1 for j in jobs if not j.get('detail_verified'))
        coverage['detail_complete'] = (not coverage['errors']
                                       and len(jobs) == len(selected))
        coverage['evidence'] = (['official-entry.html']
                                + sorted(p.name for p in output_dir.glob('list-*.json'))
                                + sorted(p.name for p in output_dir.glob('detail-*.json')))
        coverage['evidence_files'] = coverage['evidence']
        coverage['scope_evidence'] = (f'Official Beisen tenant={key}; verified category mapping={categories}; '
                                      f'requested={scope}')
        coverage['scope_request'] = {'company': name, 'scope': scope, 'source_url': host,
                                     'params': {'PortalId': portal, 'Category': [],
                                                'DisplayFields': FIELDS, 'tenant': key}}
    except BudgetExhausted:
        coverage['request_budget_exhausted'] = True
    except Exception as error:
        coverage['errors'].append(f'{type(error).__name__}: {error}')
    coverage['request_budget'] = budget
    result = shared.finish(jobs, coverage)
    if coverage.get('request_budget_exhausted'):
        result['coverage'].update(complete=False, detail_complete=False)
        if result['coverage']['status'] == 'success':
            result['coverage']['status'] = 'partial'
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('company')
    parser.add_argument('--scope', choices=list(shared.TYPES), default='campus')
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--max-requests', type=int)
    args = parser.parse_args()
    payload = collect(args.company, args.scope, args.output_dir, max_requests=args.max_requests)
    print(json.dumps({'company': args.company, 'scope': args.scope,
                      'coverage': payload['coverage']}, ensure_ascii=False))
