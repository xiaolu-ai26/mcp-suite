"""Core: HTTP client, schema mapping, state store."""
import json, re, time, random
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx

WORK = Path('/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-500-mvp')
CAND_DIR = WORK / 'candidate_batches'
STATE = WORK / 'state'
CAND_DIR.mkdir(parents=True, exist_ok=True)
STATE.mkdir(parents=True, exist_ok=True)

TZ = timezone(timedelta(hours=8))
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

HTML_TAG = re.compile(r'<[^>]+>')
WS = re.compile(r'\n{3,}')


def now_iso():
    return datetime.now(TZ).isoformat(timespec='seconds')


def today():
    return datetime.now(TZ).date().isoformat()


def strip_html(text):
    if not text:
        return ''
    t = re.sub(r'<(br|/p|/li|/div|/h\d)[^>]*>', '\n', text, flags=re.I)
    t = re.sub(r'<li[^>]*>', '• ', t, flags=re.I)
    t = HTML_TAG.sub('', t)
    t = (t.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<')
          .replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'")
          .replace('&rsquo;', "'").replace('&ndash;', '-').replace('&mdash;', '—')
          .replace('&bull;', '•').replace('&#x27;', "'"))
    t = re.sub(r'[ \t]+', ' ', t)
    t = WS.sub('\n\n', t)
    return t.strip()


class Blocked(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


class Client:
    def __init__(self):
        self.c = httpx.Client(timeout=25, follow_redirects=True,
                              headers={'User-Agent': UA,
                                       'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'})

    def get(self, url, **kw):
        return self._req('GET', url, **kw)

    def post(self, url, **kw):
        return self._req('POST', url, **kw)

    def _req(self, method, url, retries=2, **kw):
        last = None
        for i in range(retries + 1):
            try:
                r = self.c.request(method, url, **kw)
                if r.status_code in (429, 503):
                    time.sleep(2 + 2 * i + random.random())
                    continue
                return r
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = e
                time.sleep(1.5 + i)
        raise Blocked(f'网络错误: {type(last).__name__}')


def clean_city(city):
    if not city:
        return None
    city = str(city).strip().strip(',').strip()
    return city or None


def classify_type(title, text=''):
    t = f'{title} {text[:300]}'.lower()
    if any(k in t for k in ['intern', '实习', 'co-op', 'coop', 'trainee', 'apprenti']):
        return '实习'
    if any(k in t for k in ['university grad', 'early career', 'campus', '校招',
                            'graduate program', 'graduate engineer', 'new grad',
                            '校园招聘', '应届', ' MANAGEMENT TRAINEE', 'management trainee',
                            'graduate scheme', 'associates program', 'campagne']):
        return '校招'
    return '社招'


def guess_category(title):
    t = title.lower()
    for cat, kws in [
        ('技术', ['engineer', 'developer', 'software', 'algorithm', 'data', 'it ', 'architect',
                  '技术', '算法', '研发', '开发', '测试', '运维', '安全', 'ai ', '机器学习']),
        ('产品', ['product manager', '产品']),
        ('设计', ['design', '设计', 'ux', 'ui ']),
        ('市场', ['marketing', 'brand', '市场', '品牌', '推广']),
        ('销售', ['sales', 'account', '销售', '客户']),
        ('职能', ['hr', 'human resources', 'finance', 'accounting', 'legal', '人事', '财务', '法务', '行政']),
        ('供应链', ['supply', 'logistic', 'procure', '采购', '物流', '供应链']),
        ('制造', ['manufactur', 'production', 'quality', '生产', '工艺', '质量']),
        ('医疗', ['nurse', 'medical', 'clinic', 'medical', '医药', '医师', '临床']),
    ]:
        if any(k in t for k in kws):
            return cat
    return '其他'


def build_record(co, raw, idx):
    """co: company meta dict; raw: adapter-normalized job dict."""
    desc = (raw.get('description') or '').strip()
    if len(desc) < 50:
        raise Blocked(f'正文过短({len(desc)}字符)')
    title = (raw.get('title') or '').strip()
    if not title:
        raise Blocked('缺少岗位名称')
    cities = [clean_city(c) for c in raw.get('cities', [])]
    cities = [c for c in cities if c]
    rtype = raw.get('recruitment_type') or classify_type(title, desc)
    rec = {
        'id': raw.get('id') or f"{co['slug']}-{idx}",
        'recruitment_unit': co['cn_name'],
        'contracting_entity': '',
        'job_title': title,
        'job_category': raw.get('category') or guess_category(title),
        'cities': cities or ['未披露'],
        'education_raw': raw.get('education') or '未披露',
        'major_requirements_raw': raw.get('major') or '未披露',
        'cohort_raw': raw.get('cohort') or '未披露',
        'deadline': raw.get('deadline') or None,
        'deadline_type': 'explicit' if raw.get('deadline') else 'undisclosed',
        'status': 'open',
        'application_url': raw.get('apply_url') or raw['detail_url'],
        'source_url': raw['detail_url'],
        'source_name': f"{co['cn_name']}招聘官网",
        'published_at': raw.get('published_at') or today(),
        'reviewed_at': now_iso(),
        'description_raw': desc[:6000],
        'recruitment_type': rtype,
        'industry': co.get('industry') or '未披露',
        'industry_tags': [co['industry']] if co.get('industry') else [],
        'country': co.get('country') or '未披露',
        'status_note': '首版快照（官网公开信息采集，未接入定时更新）',
    }
    if co.get('fortune_rank'):
        rec['fortune_rank'] = co['fortune_rank']
    return rec


class State:
    """Queue + done + blocked state, json-file backed."""

    def __init__(self):
        self.path = STATE / 'state.json'
        if self.path.exists():
            self.d = json.loads(self.path.read_text())
            for k in ('done', 'blocked', 'candidates'):
                self.d.setdefault(k, {} if k != 'candidates' else [])
        else:
            self.d = {'done': {}, 'blocked': {}, 'candidates': []}

    def save(self):
        self.path.write_text(json.dumps(self.d, ensure_ascii=False, indent=1))

    def add_done(self, slug, info):
        self.d['done'][slug] = info
        self.save()

    def add_blocked(self, slug, reason):
        self.d['blocked'][slug] = reason
        with open(WORK / 'blocked_companies.jsonl', 'a') as f:
            f.write(json.dumps({'slug': slug, 'reason': reason,
                                'at': now_iso()}, ensure_ascii=False) + '\n')

    def add_candidates(self, records):
        self.d['candidates'].extend(records)
        self.save()
