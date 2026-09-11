import sys, json
sys.path.insert(0, '/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-500-mvp')
from collector import discover
from collector.core import WORK

q = json.load(open(WORK / 'state' / 'queue.json'))
slugs = sys.argv[1].split(',') if len(sys.argv) > 1 else []
for co in [c for c in q if c['slug'] in slugs]:
    name = co.get('en_name') or co['cn_name']
    print('===', co['slug'], co['cn_name'], '|', name, '| tokens:', discover.name_tokens(co))
    for query in [f'site:myworkdayjobs.com {name}',
                  f'site:careers.smartrecruiters.com OR site:jobs.smartrecruiters.com {name}',
                  f'{name} careers official jobs apply']:
        urls = discover.search(query)
        print(' Q:', query, '->', len(urls), 'results')
        for u in urls[:6]:
            cfg = discover.route_url(u)
            print('   ', 'ATS' if cfg else 'gen', cfg or '', u[:100])
        print()
