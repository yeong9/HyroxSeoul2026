#!/usr/bin/env python3
"""startlist.hyrox.com 의 2026 Seoul 스타트리스트를 받아 index.html 에 들어가는 DATA(JSON)로 만듭니다.

사용법:
  python3 scripts/fetch_startlist.py [기존 DATA가 든 index.html] > startlist.json
  python3 scripts/fetch_startlist.py --from-raw raw.json [index.html] > startlist.json   # 이미 받아 둔 원본 줄로 변환만

- 기존 index.html 의 waves 순서를 유지해서 색상·디비전 번호가 바뀌지 않게 합니다.
- 배번이 아직 없는 팀은 'n' + 해시로 된 임시 번호를 붙입니다(같은 팀이면 항상 같은 번호).
- 실패하거나 기존보다 팀이 크게 줄었으면 종료 코드 1 로 끝나고 아무것도 출력하지 않습니다.
"""
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = 'https://startlist.hyrox.com/'
SUFFIX = ['LR3MS4JI19A2', 'LR3MS4JI19A3', 'LR3MS4JI19A4']          # 금, 토, 일
EVENTS = [['HA', 'HD', 'H'], ['HA', 'HDP', 'H', 'HPRO', 'HD'], ['HD', 'H', 'HA', 'HMR']]
DAYS = {'friday': 0, 'saturday': 1, 'sunday': 2}
PER_PAGE = 100
MAX_PAGES = 60
UA = 'Mozilla/5.0 (compatible; HyroxSeoulSchedule/1.0; +https://yeong9.github.io/HyroxSeoul2026/)'


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en'})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise last


def strip(s):
    return html.unescape(re.sub(r'<[^>]+>', '', s)).strip()


def parse_page(page):
    """페이지 하나에서 원본 줄 [이름문자열, 개인전여부, 배번, 연령대, 요일, 시작웨이브]를 뽑습니다."""
    out = []
    for blk in re.findall(r'<li class="[^"]*list-group-item row[^"]*">(.*?)</li>', page, re.S):
        m = re.search(r'<h4[^>]*class="[^"]*list-field[^"]*"[^>]*>(.*?)</h4>', blk, re.S)
        if not m:
            continue
        single = 'type-fullname' in m.group(0)
        f = {}
        for label, val in re.findall(r'<div class="[^"]*list-label">([^<]*)</div>(.*?)</div>', blk, re.S):
            f[label.strip()] = strip(val)
        out.append([strip(m.group(1)), single, f.get('Bib no.', ''), f.get('Age Group', ''),
                    f.get('Day', ''), f.get('Startwave', '')])
    return out


def fetch_all():
    raw, errors = [], 0
    for d in range(3):
        for pre in EVENTS[d]:
            ev = f'{pre}_{SUFFIX[d]}'
            for page in range(1, MAX_PAGES + 1):
                q = {'page': page, 'event': ev, 'num_results': PER_PAGE, 'pid': 'startlist_list',
                     'pidp': 'upcoming_nav', 'search[name]': '%', 'search_sort': 'start_no',
                     'search_sort_order': 'ASC'}
                try:
                    got = parse_page(fetch(BASE + '?' + urllib.parse.urlencode(q)))
                except Exception as e:  # noqa: BLE001
                    errors += 1
                    print(f'warn: {ev} page {page}: {e}', file=sys.stderr)
                    break
                for g in got:
                    g.append(d)
                raw += got
                if len(got) < PER_PAGE:
                    break
    return raw, errors


def people(name, single):
    if single:
        n = re.sub(r'\([^)]*\)\s*$', '', name).strip()
        if ',' in n:
            sur, given = [x.strip() for x in n.split(',', 1)]
            return [(given + ' ' + sur).strip()]
        return [n]
    return [x.strip() for x in name.split(',') if x.strip()]


def build(raw, base_waves):
    waves = list(base_waves)
    rows, seen = [], set()
    for name, single, bib, age, day, sw, d_hint in raw:
        m = re.match(r'^(\d{1,2}:\d{2})\s+(.+)$', sw or '')
        if not m or bib == '999999':
            continue                                   # 시간이 없는 줄, 테스트 줄
        t, wave = m.group(1).zfill(5), m.group(2).strip()
        d = DAYS.get(day.strip().lower(), d_hint)
        ppl = people(name, single)
        if not ppl:
            continue
        if wave not in waves:
            waves.append(wave)
        w = waves.index(wave)
        if not re.fullmatch(r'\d+', bib or ''):
            h = hashlib.sha1(f'{d}|{t}|{wave}|{"/".join(ppl)}'.encode()).hexdigest()[:5]
            bib = 'n' + h
        if (d, bib) in seen:
            continue
        seen.add((d, bib))
        rows.append([d, t, bib, w, age, ppl])
    return waves, rows


def load_base(path):
    try:
        s = open(path, encoding='utf-8').read()
        m = re.search(r'const DATA = (\{.*?\});\n', s, re.S)
        return json.loads(m.group(1))
    except Exception:  # noqa: BLE001
        return {'waves': [], 'rows': []}


def main():
    args = sys.argv[1:]
    raw_file = None
    if args and args[0] == '--from-raw':
        raw_file, args = args[1], args[2:]
    base = load_base(args[0] if args else 'index.html')
    if raw_file:
        raw, errors = json.load(open(raw_file, encoding='utf-8')), 0
    else:
        raw, errors = fetch_all()
    waves, rows = build(raw, base['waves'])
    old_n = len(base['rows'])
    if errors or len(rows) < max(1000, old_n * 0.9):
        print(f'error: 스타트리스트가 이상해요 (오류 {errors}건, {len(rows)}행, 기존 {old_n}행). 기존 데이터를 유지합니다.', file=sys.stderr)
        sys.exit(1)
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    json.dump({'event': base.get('event', 'HYROX Seoul 2026'),
               'scraped': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'),
               'waves': waves, 'rows': rows}, sys.stdout, ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    main()
