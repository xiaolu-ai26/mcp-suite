"""Execute against isolated local HTTP service; persist only sanitized receipts."""
import asyncio
import json
import os
from pathlib import Path
import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from core.store import Store

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8768'


async def run():
    store = Store(ROOT/'private/test-access.sqlite3')
    code = store.generate_codes(1)[0]
    receipt = {}
    async with httpx.AsyncClient(trust_env=False) as http:
        response = await http.post(BASE+'/redeem', json={'code':code})
        assert response.status_code == 200
        data = response.json()
        token = data['api_key']
        receipt['redemption'] = 'HTTP POST 200; new isolated test code redeemed'
        assert (await http.post(BASE+'/redeem', json={'code':code})).status_code == 400
        receipt['single_use'] = 'second redemption HTTP 400'
        headers={'Authorization':'Bearer '+token}
        assert (await http.post(BASE+'/mcp')).status_code == 401
        receipt['no_key'] = 'HTTP 401'
        before=(await http.get(BASE+'/usage',headers=headers)).json()['remaining_today']
        assert before==200
        transport=StreamableHttpTransport(BASE+'/mcp', headers=headers)
        async with Client(transport) as client:
            names=[tool.name for tool in await client.list_tools()]
            assert set(names)=={'jobs_search','jobs_detail','jobs_deadlines'}
            after_list=(await http.get(BASE+'/usage',headers=headers)).json()['remaining_today']
            assert after_list==200
            search=await client.call_tool('jobs_search',{'limit':3})
            search_data=search.data
            assert search_data['total']>=300
            job_id=search_data['jobs'][0]['id']
            deadlines=(await client.call_tool('jobs_deadlines',{'days':90,'limit':3})).data
            detail=(await client.call_tool('jobs_detail',{'id':job_id})).data
            assert detail['found'] and detail['source_urls'] and detail['data_as_of']
            assert deadlines['jobs'] and deadlines['source_urls']
            receipt['tools']={'names':names,'jobs_search_total':search_data['total'],
                              'jobs_deadlines_total':deadlines['total'], 'detail_id':job_id,
                              'data_as_of':search_data['data_as_of'], 'detail_source_urls':detail['source_urls']}
        after=(await http.get(BASE+'/usage',headers=headers)).json()['remaining_today']
        assert after==197
        receipt['quota']={'before':before,'after_initialize_and_list':after_list,'after_three_tools':after}
        with store.connect() as db:
            db.execute("UPDATE entitlements SET expires_at='2026-01-01T00:00:00+08:00' WHERE key_id=?",(store.authorize(token)['key_id'],))
        expired=await http.post(BASE+'/mcp',headers=headers)
        assert expired.status_code==403 and '过期' in expired.json()['error']
        receipt['expired_key']={'status':expired.status_code,'message':expired.json()['error']}
        # Distinct fresh test key for Claude Code; placeholder JSON never contains its secret.
        claude_key=store.redeem(store.generate_codes(1)[0])['api_key']
        private=ROOT/'private'
        fd=os.open(private/'claude-test-key.txt',os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as handle:handle.write(claude_key)
        (private/'claude-test.mcp.json').write_text(json.dumps({'mcpServers':{'qiuzhao':{
            'type':'http','url':BASE+'/mcp','headers':{'Authorization':'Bearer ${QIUZHAO_API_KEY}'}}}}))
    path=ROOT/'docs/local-e2e-receipt.json'
    path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    print(json.dumps(receipt,ensure_ascii=False,indent=2))


if __name__=='__main__':asyncio.run(run())
