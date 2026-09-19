"""Read-only Moka list-phase probe: count site postings by hireMode/scope.
Usage: python probe_moka_list.py <org/site> [--site-url URL] [--out DIR]
"""
import argparse, html, json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from qiuzhao.collector import p1_sources_01_10 as shared

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('key', help='org/site')
    ap.add_argument('--site-url', default=None)
    ap.add_argument('--out', default='research/multi-entrance/moka-probe')
    args = ap.parse_args()
    org, site = args.key.split('/', 1)
    site_url = args.site_url or f'https://app.mokahr.com/social-recruitment/{org}/{site}'
    out = Path(args.out) / f'{org}-{site}'
    out.mkdir(parents=True, exist_ok=True)
    session = shared.make_session()
    session.headers['User-Agent'] = UA
    ledger = []

    def rec(url, **kw):
        t0 = time.time()
        r = session.get(url, timeout=(10, 45), **kw)
        ledger.append({'url': url, 'status': r.status_code, 'bytes': len(r.content),
                       'secs': round(time.time() - t0, 2)})
        return r

    report = {'key': args.key, 'site_url': site_url, 'list_endpoint': None}
    r = rec(site_url)
    report['portal_status'] = r.status_code
    page = html.unescape(r.text)
    ivm = re.search(r'"aesIv"\s*:\s*"([^"]+)"', page)
    report['aesIv_found'] = bool(ivm)
    (out / 'portal.html').write_text(r.text, encoding='utf-8')
    if r.status_code != 200 or not ivm:
        report['error'] = 'portal not readable'
        print(json.dumps(report, ensure_ascii=False))
        return
    iv = ivm.group(1)
    host = 'https://' + site_url.split('/')[2]
    endpoint = host + '/api/outer/ats-apply/website/jobs/v2'
    report['list_endpoint'] = endpoint
    offset, rows_all, total = 0, [], None
    while True:
        time.sleep(2.0)
        t0 = time.time()
        payload = shared.request_json(session, endpoint,
                                      {'orgId': org, 'siteId': int(site), 'limit': 50,
                                       'offset': offset, 'needStat': True, 'locale': 'zh-CN'}, iv)
        ledger.append({'url': endpoint, 'offset': offset, 'status': 200, 'secs': round(time.time() - t0, 2)})
        (out / f'list-{offset}.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        rows = payload.get('jobs') or []
        n = (payload.get('jobStats') or {}).get('total')
        if not rows:
            report['terminal_offset'] = offset
            report['terminal_total'] = n
            break
        total = n
        rows_all.extend(rows)
        offset += 50
        if offset > 5000:
            report['truncated'] = True
            break
    from collections import Counter
    report['total'] = total
    report['listed'] = len(rows_all)
    report['by_hireMode'] = dict(Counter(str(r.get('hireMode')) for r in rows_all))
    report['by_status'] = dict(Counter(str(r.get('status')) for r in rows_all))
    report['by_commitment'] = dict(Counter(str(r.get('commitment')) for r in rows_all))
    def scope_of(row):
        if shared.is_internship(row.get('commitment'), row.get('title', '')):
            return 'intern'
        return 'campus' if row.get('hireMode') == 2 else 'social' if row.get('hireMode') == 1 else 'unknown'
    report['by_scope'] = dict(Counter(scope_of(r) for r in rows_all))
    report['sample_titles'] = [r.get('title') for r in rows_all[:20]]
    report['ledger'] = ledger
    report['request_count'] = len(ledger)
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('sample_titles',)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
