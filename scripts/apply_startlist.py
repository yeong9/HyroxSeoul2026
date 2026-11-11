#!/usr/bin/env python3
"""index.html 안의 DATA 를 startlist.json 내용으로 바꿔 줍니다.
사용법: python3 scripts/apply_startlist.py index.html startlist.json   (index.html 을 덮어씁니다)"""
import json, re, sys

page, sl = sys.argv[1], sys.argv[2]
s = open(page, encoding='utf-8').read()
d = json.load(open(sl, encoding='utf-8'))
assert d.get('rows') and d.get('waves') and d.get('scraped'), 'startlist.json 형식 오류'
new, n = re.subn(r'const DATA = \{.*?\};\n', lambda m: 'const DATA = ' + json.dumps(d, ensure_ascii=False, separators=(',', ':')) + ';\n', s, count=1, flags=re.S)
assert n == 1, 'DATA 를 찾지 못했어요'
open(page, 'w', encoding='utf-8').write(new)
print(f"applied {len(d['rows'])} rows, scraped {d['scraped']}")
