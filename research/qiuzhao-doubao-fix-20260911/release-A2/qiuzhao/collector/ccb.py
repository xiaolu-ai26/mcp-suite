"""Public CCB headquarters campus plan adapter; no login/personal endpoints.

Standalone writes only --output-dir (defaults to data/ccb_pending). Integration:
rows = collect_ccb(collector); rows and collector.states['ccb'] follow run.py's contract.
"""
from __future__ import annotations

import argparse
import gzip
import http.cookiejar
import json
import re
import ssl
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, HTTPSHandler, HTTPCookieProcessor, build_opener

from .run import Collector, base_job, clean, now, write_json

HOST = 'https://job1.ccb.com'
ANNOUNCEMENT_ID = '20260903163254718082'
ANNOUNCEMENT_URL = HOST + '/cn/job/announcement.html?annoId=' + ANNOUNCEMENT_ID
UA = 'Mozilla/5.0 QiuzhaoOfficialJobs/1.0 (public recruitment index; daily low-frequency review)'
BASE_PARAMS = {'CCB_IBSVersion': 'V5', 'isAjaxRequest': 'true', 'SERVLET_NAME': 'WCCMainPlatV5'}
LIST_FIELDS = ('planId', 'planPost', 'planPostName', 'planType', 'orgId', 'orgName',
               'secondOrgId', 'secondOName', 'workPlace', 'postDate', 'endDate', 'planStatus')


class PublicClient:
    def __init__(self, delay=1.25):
        context = ssl.create_default_context()
        # CCB's legacy TLS server needs renegotiation compatibility; certificate and
        # hostname verification stay enabled. This context is only used for CCB.
        context.options |= getattr(ssl, 'OP_LEGACY_SERVER_CONNECT', 4)
        self.opener = build_opener(HTTPSHandler(context=context),
                                  HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.delay = max(1.25, delay)
        self.last = 0.0

    def get(self, url, referer=None):
        if not url.startswith(HOST + '/'):
            raise ValueError('CCB adapter only permits its official recruitment host')
        time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
        headers = {'User-Agent': UA}
        if referer:
            headers.update({'X-Requested-With': 'XMLHttpRequest', 'Referer': referer})
        try:
            with self.opener.open(Request(url, headers=headers), timeout=35) as response:
                body = response.read()
                if response.headers.get('Content-Encoding') == 'gzip' or body[:2] == b'\x1f\x8b':
                    body = gzip.decompress(body)
                if not body.strip():
                    raise ValueError('CCB public endpoint returned an empty response; preserve previous snapshot')
                return body.decode('utf-8')
        finally:
            self.last = time.monotonic()

    def api(self, code, params, referer):
        if code not in {'NHR104', 'NHR106'}:
            raise ValueError('Only public recruitment announcement/list APIs are permitted')
        url = HOST + '/tran/WCCMainPlatV5?' + urlencode({**BASE_PARAMS, 'TXCODE': code, **params})
        result = json.loads(self.get(url, referer))
        if result.get('SUCCESS') != 'true' or result.get('busCode') != '000000000000':
            raise ValueError('CCB public API did not return success; no login retry')
        return result, url


def campaign_fields(content):
    text = clean(content)
    if '总部2027年度校园招聘' not in text or '部门经办岗' not in text:
        raise ValueError('CCB announcement no longer matches the supported campus plan')
    deadline = re.search(r'报名截止时间为\s*(\d{4})年(\d{1,2})月(\d{1,2})日24点', text)
    qualification = re.search(r'应聘者须为([^。]+)2027年应届毕业生', text)
    majors = re.search(r'专业需求以([^。]+专业为主)', text)
    if not deadline or not qualification:
        raise ValueError('CCB campaign deadline or qualification not found')
    deadline = f'{int(deadline[1]):04d}-{int(deadline[2]):02d}-{int(deadline[3]):02d}'
    return {
        'deadline': deadline,
        'education_raw': qualification[1],
        'cohort_raw': qualification[0],
        'major_requirements_raw': majors[0] if majors else '',
        'campaign_cohort_raw': '2027年度校园招聘',
        'requirements_scope': 'headquarters_campaign_announcement',
        'education_scope': 'headquarters_campaign_announcement',
        'cohort_scope': 'headquarters_campaign_announcement',
    }


def collect_ccb(collector):
    client = PublicClient(collector.delay)
    client.get(ANNOUNCEMENT_URL)
    announcement, _ = client.api('NHR106', {'annoId': ANNOUNCEMENT_ID}, ANNOUNCEMENT_URL)
    fields = campaign_fields(announcement['annoContent'])
    plan_id, parent_org = announcement['planId'], announcement['orgId']
    announcement_evidence = collector.evidence_file('ccb-announcement.json', json.dumps({
        k: announcement[k] for k in ('annoTitle', 'annoDate', 'annoOrgName', 'annoContent', 'planId', 'orgId')
    }, ensure_ascii=False, indent=2))
    list_url = HOST + '/cn/job/job_list.html?' + urlencode({'planId': plan_id, 'orgId': parent_org})
    client.get(list_url)
    jobs, seen, expected, total_pages = [], set(), None, None
    page = 1
    while True:
        data, api_url = client.api('NHR104', {'planType': 'XY', 'planId': plan_id,
             'orgId': parent_org, 'PAGE_JUMP': page, 'REC_IN_PAGE': 10}, list_url)
        total, pages = int(data['TOTAL_REC']), int(data['TOTAL_PAGE'])
        if expected is None:
            expected, total_pages = total, pages
        if total != expected or pages != total_pages or not 0 < pages <= 100:
            raise ValueError('CCB pagination changed during refresh')
        records = data.get('planPostList', [])
        safe = [{k: row.get(k, '') for k in LIST_FIELDS} for row in records]
        checked = now()
        evidence = collector.evidence_file(f'ccb-list-{page}.json', json.dumps({
            'source_url': api_url, 'reviewed_at': checked, 'total': total,
            'pages': pages, 'page': page, 'planPostList': safe,
        }, ensure_ascii=False, indent=2))
        for row in safe:
            if not row['planPost'] or not row['planPostName'] or row['planId'] != plan_id:
                raise ValueError('CCB public role schema changed')
            identity = '-'.join((row['planId'], row['planPost'], row['secondOrgId']))
            if identity in seen:
                raise ValueError('CCB repeated role during pagination')
            seen.add(identity)
            # The announcement supplies the shared role title; department stays separate.
            job = base_job('ccb-' + identity, '中国建设银行股份有限公司', '部门经办岗', ANNOUNCEMENT_URL, checked)
            application = HOST + '/cn/job/job_detail.html?' + urlencode({
                k: row[k] for k in ('planId', 'planPost', 'planType', 'orgId', 'secondOrgId')})
            deadline = row['endDate'] or fields['deadline']
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', deadline):
                raise ValueError('CCB role deadline malformed')
            status = 'expired' if deadline < checked[:10] or row['planStatus'] == '2' else (
                'open' if row['planStatus'] == '1' else 'unverified')
            job.update(fields)
            job.update(job_category='部门经办岗', job_title_scope='headquarters_campaign_announcement',
                recruiting_unit_raw=row['orgName'], hiring_department_raw=row['planPostName'],
                parent_unit_raw=announcement['annoOrgName'],
                cities=[row['workPlace']] if row['workPlace'] else [],
                deadline=deadline, deadline_type='explicit', deadline_scope='official_role_list' if row['endDate'] else 'headquarters_campaign_announcement',
                status=status, application_url=application, job_listing_url=list_url,
                announcement_url=ANNOUNCEMENT_URL, campaign_url=ANNOUNCEMENT_URL,
                published_at=row['postDate'][:10] or announcement['annoDate'][:10],
                evidence_path=evidence, announcement_evidence_path=announcement_evidence,
                source_name='中国建设银行官方2027总部校园招聘', source_record_id=row['planPost'],
                description_raw='官方公开列表岗位部门：' + row['planPostName'] + '；总部招聘公告统一岗位名：部门经办岗。具体部门职责未从需登录的接口采集。',
                record_kind='official_plan_post')
            jobs.append(job)
        if page >= total_pages:
            break
        page += 1
    if len(jobs) != expected:
        raise ValueError(f'CCB incomplete role listing: {len(jobs)}/{expected}')
    collector.states['ccb'] = {'status': 'success', 'checked_at': now(), 'collected_jobs': len(jobs),
        'expected_jobs': expected, 'complete': True, 'coverage': 'headquarters 2027 campus plan only',
        'announcement_url': ANNOUNCEMENT_URL, 'list_url': list_url}
    return jobs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'data' / 'ccb_pending')
    args = parser.parse_args()
    collector = Collector(args.output_dir)
    try:
        rows = collect_ccb(collector)
        write_json(args.output_dir / 'jobs.json', rows)
        write_json(args.output_dir / 'source_state.json', collector.states)
        write_json(args.output_dir / 'alerts.json', {'run_finished_at': now(), 'alerts': []})
        print(json.dumps(collector.states, ensure_ascii=False))
    except Exception as error:
        # Only the adapter error class/message; no cookie, headers or raw responses.
        write_json(args.output_dir / 'alerts.json', {'run_finished_at': now(),
            'alerts': [{'source': 'ccb', 'error': str(error)[:250]}]})
        raise SystemExit('CCB refresh failed; previous pending snapshot preserved. See alerts.json')


if __name__ == '__main__':
    main()
