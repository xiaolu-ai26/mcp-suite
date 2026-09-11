"""End-to-end redemption + metering against an isolated local bench service.

Uses its own SQLite file and its own codes, so production stock is never touched.
Persists only sanitized receipts; no key or code is written to disk here.
"""
import asyncio
import json
import os
from pathlib import Path
import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from core.store import Store

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get('BENCH_E2E_BASE', 'http://127.0.0.1:8769')
DB = ROOT / 'private' / 'test-access.sqlite3'


async def run():
    store = Store(DB)
    code = store.generate_codes(1, 'bench-monthly')[0]
    receipt = {}
    async with httpx.AsyncClient(trust_env=False) as http:
        response = await http.post(BASE + '/redeem', json={'code': code})
        assert response.status_code == 200, response.text
        data = response.json()
        token = data['api_key']
        assert token.startswith('bm_') and data['product'] == 'bench'
        receipt['redemption'] = {'status': 200, 'product': data['product'],
                                 'valid_through': data['valid_through'],
                                 'daily_limit': data['daily_limit'],
                                 'note': '新建隔离测试码兑换成功，30天从兑换时刻起算'}
        assert (await http.post(BASE + '/redeem', json={'code': code})).status_code == 400
        receipt['single_use'] = 'second redemption HTTP 400'

        # A recruitment code must not mint a key on the bench site.
        other = store.generate_codes(1, 'qiuzhao-2026')[0]
        cross = await http.post(BASE + '/redeem', json={'code': other})
        assert cross.status_code == 400
        receipt['cross_product_code'] = {'status': 400, 'message': cross.json()['error']}
        with store.connect() as db:
            row = db.execute('SELECT redeemed_at FROM redemption_codes WHERE code_hash=?',
                             (__import__('core.store', fromlist=['digest']).digest(other),)).fetchone()
        assert row['redeemed_at'] is None
        receipt['cross_product_code']['code_not_burned'] = True

        headers = {'Authorization': 'Bearer ' + token}
        assert (await http.post(BASE + '/mcp')).status_code == 401
        receipt['no_key'] = 'HTTP 401'
        before = (await http.get(BASE + '/usage', headers=headers)).json()['remaining_today']
        assert before == 200

        transport = StreamableHttpTransport(BASE + '/mcp', headers=headers)
        async with Client(transport) as client:
            names = sorted(tool.name for tool in await client.list_tools())
            assert names == ['bench_detail', 'bench_search', 'bench_taxonomy']
            after_list = (await http.get(BASE + '/usage', headers=headers)).json()['remaining_today']
            assert after_list == 200, 'handshake and tool listing must stay free'
            search = (await client.call_tool('bench_search', {'topic': 'AI变现', 'limit': 3})).data
            assert search['total'] > 0 and search['records'][0]['url']
            record_id = search['records'][0]['id']
            detail = (await client.call_tool('bench_detail', {'id': record_id})).data
            assert detail['found'] and detail['records'][0]['id'] == record_id
            taxonomy = (await client.call_tool('bench_taxonomy', {})).data
            assert taxonomy['total_records'] > 400 and taxonomy['topic_category']['counts']
            empty = (await client.call_tool('bench_search', {'topic': '不存在的分类xyz'})).data
            assert empty['total'] == 0 and empty['suggestion']
            receipt['tools'] = {
                'names': names, 'search_total': search['total'],
                'search_sample_id': record_id, 'search_sample_url': search['records'][0]['url'],
                'search_sample_title': search['records'][0]['title'],
                'detail_found': detail['found'], 'taxonomy_total': taxonomy['total_records'],
                'taxonomy_topics': len(taxonomy['topic_category']['counts']),
                'taxonomy_formulas': len(taxonomy['title_formula']['counts']),
                'empty_result_suggestion': bool(empty['suggestion']),
                'data_as_of': search['data_as_of'],
            }
            # No body, no exact metrics, anywhere in a real response.
            blob = json.dumps(search, ensure_ascii=False)
            for banned in ('transcript', 'ocr_text', 'like_count', 'author_followers', 'xhscdn'):
                assert banned not in blob
            receipt['response_shape'] = '返回中无 transcript/ocr_text/like_count/author_followers/图片直链'

        after = (await http.get(BASE + '/usage', headers=headers)).json()['remaining_today']
        assert after == 196, after
        receipt['quota'] = {'before': before, 'after_initialize_and_list': after_list,
                            'after_four_tool_calls': after}

        with store.connect() as db:
            db.execute("UPDATE entitlements SET expires_at='2026-01-01T00:00:00+08:00' WHERE key_id=?",
                       (store.authorize(token, 'bench')['key_id'],))
        expired = await http.post(BASE + '/mcp', headers=headers)
        assert expired.status_code == 403 and '过期' in expired.json()['error']
        receipt['expired_key'] = {'status': expired.status_code, 'message': expired.json()['error']}

        # A key without the bench entitlement must be refused, not silently served.
        foreign = store.redeem(store.generate_codes(1, 'qiuzhao-2026')[0])['api_key']
        denied = await http.post(BASE + '/mcp', headers={'Authorization': 'Bearer ' + foreign})
        assert denied.status_code == 403 and '没有该产品权限' in denied.json()['error']
        receipt['wrong_product_key'] = {'status': denied.status_code, 'message': denied.json()['error']}

        health = (await http.get(BASE + '/health')).json()
        assert health['status'] == 'ok' and health['records'] > 400
        receipt['health'] = health

    path = ROOT / 'bench' / 'receipts' / 'local-e2e-receipt.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(run())
