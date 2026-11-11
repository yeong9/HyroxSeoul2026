#!/usr/bin/env python3
"""results.hyrox.com 의 2026 Seoul 결과 목록을 읽어, index.html 의 출전 팀 중 결과가 올라온 팀 id 를 finished.json 으로 저장합니다.

사용법: python3 scripts/fetch_results.py index.html > finished.json
id 는 '요일번호-배번' (예: 0-92043). 실패해도 항상 유효한 JSON 을 출력합니다.
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = 'https://results.hyrox.com/season-9/'
SUFFIX = ['LR3MS4JI19A2', 'LR3MS4JI19A3', 'LR3MS4JI19A4']          # 금, 토, 일
EVENTS = [['HA', 'HD', 'H'], ['HA', 'HDP', 'H', 'HPRO', 'HD'], ['HD', 'H', 'HA', 'HMR']]
PER_PAGE = 100
MAX_PAGES = 40
UA = 'Mozilla/5.0 (compatible; HyroxSeoulSchedule/1.0; +https://yeong9.github.io/HyroxSeoul2026/)'


def prefix(wave):
    u = wave.upper()
    if 'RELAY' in u:
        return 'HMR'
    if 'ADAPTIVE' in u:
        return 'HA'
    if 'DOUBLES' in u:
        return 'HDP' if 'PRO' in u else 'HD'
    return 'HPRO' if 'PRO' in u else 'H'


def norm(name):
    """'Kim, Geonwoo (KOR)' / '원준 정' 처럼 순서와 표기가 달라도 같은 사람이면 같은 문자열"""
    s = re.sub(r'\([^)]*\)', ' ', name).lower().replace('-', ' ').replace(',', ' ')
    return ' '.join(sorted(s.split()))


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise last


def strip(s):
    return html.unescape(re.sub(r'<[^>]+>', '', s)).strip()


def parse_rows(page):
    """[(이름 목록, 연령대, 기록, 순위, 상세 id)] — 기록이 없는 줄은 건너뜀"""
    out = []
    for blk in re.findall(r'<li class="[^"]*list-group-item row[^"]*">(.*?)</li>', page, re.S):
        m = re.search(r'<h4[^>]*class="[^"]*list-field[^"]*"[^>]*>(.*?)</h4>', blk, re.S)
        if not m:
            continue
        single = 'type-fullname' in m.group(0)
        txt = strip(m.group(1))
        if single:
            txt = re.sub(r'\([^)]*\)\s*$', '', txt).strip()
            if ',' in txt:
                sur, given = [x.strip() for x in txt.split(',', 1)]
                names = [given + ' ' + sur]
            else:
                names = [txt]
        else:
            names = []
            for x in txt.split(','):
                x = x.strip()
                if x and norm(x) not in [norm(n) for n in names]:
                    names.append(x)
        a = re.search(r'type-age_class[^>]*>(?:<div[^>]*>.*?</div>)?\s*([^<]*)', blk, re.S)
        t = re.search(r'type-time[^>]*>(?:<div[^>]*>.*?</div>)?\s*(\d+:\d\d:\d\d)', blk, re.S)
        if not t:
            continue
        rk = re.search(r'type-place place-primary[^>]*>\s*(\d+)\s*<', blk)
        ip = re.search(r'idp=([A-Za-z0-9]+)', blk)
        out.append((names, strip(a.group(1)) if a else '', t.group(1), int(rk.group(1)) if rk else 0, ip.group(1) if ip else ''))
    return out


def fetch_event(ev):
    rows = []
    for page in range(1, MAX_PAGES + 1):
        q = {'pid': 'list', 'pidp': 'ranking_nav', 'event': ev, 'num_results': PER_PAGE, 'page': page}
        got = parse_rows(fetch(BASE + '?' + urllib.parse.urlencode(q)))
        rows += got
        if len(got) < PER_PAGE:
            break
    return rows


def load_data(path):
    s = open(path, encoding='utf-8').read()
    m = re.search(r'const DATA = (\{.*?\});\n', s, re.S)
    return json.loads(m.group(1))


def main():
    data = load_data(sys.argv[1] if len(sys.argv) > 1 else 'index.html')
    waves = data['waves']
    idx = {}   # (요일, 접두사) -> [(id, 연령대, 이름 집합)]
    for d, _t, bib, w, age, people in data['rows']:
        idx.setdefault((d, prefix(waves[w])), []).append((f'{d}-{bib}', age, {norm(p) for p in people}))

    done, recs, errors = set(), {}, 0
    for d in range(3):
        for pre in EVENTS[d]:
            cands = idx.get((d, pre))
            if not cands:
                continue
            try:
                rows = fetch_event(f'{pre}_{SUFFIX[d]}')
            except Exception as e:  # noqa: BLE001
                errors += 1
                print(f'warn: {pre} day{d}: {e}', file=sys.stderr)
                continue
            for names, age, total, rank, idp in rows:
                res = {norm(n) for n in names}
                for tid, a, ppl in cands:
                    if ppl and ppl <= res and (not a or not age or a == age):
                        done.add(tid)
                        recs[tid] = [total, rank, idp]
    json.dump({'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
               'errors': errors, 'done': sorted(done), 'res': recs}, sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
