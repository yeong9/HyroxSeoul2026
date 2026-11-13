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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

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


KST = timezone(timedelta(hours=9))
DAY0 = (2026, 11, 13)
SEQ = ['01', '11', '02', '12', '03', '13', '04', '14', '05', '15', '06', '16', '07', '17', '08', '18']   # 러닝1, 스키에르그, 러닝2 … 러닝8, 월볼
LIVE_BEFORE = 5       # 출발 몇 분 전부터
LIVE_AFTER = 135      # 출발 몇 분 뒤까지 (결과가 안 올라와도 이 시간까지만 확인)


def to_sec(t):
    h, m, s = (int(x) for x in t.split(':'))
    return h * 3600 + m * 60 + s


def parse_splits(page):
    """상세 페이지(워크아웃 써머리)에서 끝낸 구간 수와 누적 초를 돌려줌: (끝낸 구간 수 0~16, 누적 초)
    구간 순서: 러닝1 → 스키에르그 → 러닝2 → … → 러닝8 → 월볼 (줄 class 'f-time_01', 'f-time_11' …)"""
    times = {}
    for blk in re.split(r'<tr\b', page):
        m = re.search(r'<td[^>]*f-time_(\d\d)[^>]*>\s*(\d+:\d\d:\d\d)\s*</td>', blk)
        if m:
            times[m.group(1)] = to_sec(m.group(2))
    n, cum = 0, 0
    for code in SEQ:
        if code not in times:
            break
        n += 1
        cum += times[code]
    return n, cum


def parse_finish(page):
    """상세 페이지의 '최종 기록(Overall Time)'. 아직 안 들어왔으면 ''"""
    m = re.search(r'<td[^>]*f-time_finish_netto[^>]*>\s*(\d+:\d\d:\d\d)\s*</td>', page)
    return m.group(1) if m else ''


def lookup_idp(bib, event):
    """배번 → 상세 id (대회 리더보드 검색 JSON). 못 찾으면 ''"""
    q = {'content': 'ajax2', 'onpage': 'leaderboard', 'func': 'getSearchResult',
         'options[string]': bib, 'options[lang]': 'EN_CAP', 'options[event]': event}
    data = json.loads(fetch(BASE + 'index.php?' + urllib.parse.urlencode(q), tries=2))
    for r in data:
        if str(r.get('start_no')) == str(bib) and r.get('id'):
            return r['id']
    return ''


def fetch_live(tid, bib, event):
    try:
        idp = lookup_idp(bib, event)
        if not idp:
            return tid, None
        q = {'content': 'detail', 'fpid': 'search', 'pid': 'search', 'idp': idp, 'lang': 'EN_CAP', 'event': event}
        page = fetch(BASE + '?' + urllib.parse.urlencode(q), tries=2)
        n, cum = parse_splits(page)
        return tid, [n, cum, parse_finish(page), idp]
    except Exception as e:  # noqa: BLE001
        print(f'warn: live {tid}: {e}', file=sys.stderr)
        return tid, None


def load_watch(path):
    """구간 기록을 확인할 팀 id: 소속(XON·F45범계) 출전 명단 + 기본 목록. (모든 팀을 5분마다 조회하면 결과 사이트에 부담이라 범위를 제한)"""
    s = open(path, encoding='utf-8').read()
    ids = set()
    m = re.search(r'const XON_H = (\{.*?\});', s, re.S)
    if m:
        ids |= set(json.loads(m.group(1)).keys())
    m = re.search(r'const F45_IDS = new Set\(\[(.*?)\]\)', s, re.S)
    if m:
        ids |= set(re.findall(r"'(\d-\d+)'", m.group(1)))
    m = re.search(r'const DEFAULTS = \[(.*?)\n\];', s, re.S)
    if m:
        ids |= {f'{d}-{b}' for d, b in re.findall(r"\{d:(\d),b:'(\d+)'", m.group(1))}
    return ids


LIVE_END_PAD = 90  # 구분 종료 시각 + 90분까지


def load_flow(path):
    """index.html 의 FLOW(하루 흐름 시간표)에서 {요일: [(웨이브 이름 집합, 시작분, 종료분)]}"""
    s = open(path, encoding='utf-8').read()
    m = re.search(r'const FLOW = \{(.*?)\n\};', s, re.S)
    flow = {}
    if not m:
        return flow
    for dm in re.finditer(r'(?m)^\s*(\d):\[(.*?)\](?=,\n\s*\d:\[|\s*$)', m.group(1) + '\n', re.S):
        d = int(dm.group(1))
        for rm in re.finditer(r"w:\[(.*?)\],r:\['(\d\d):(\d\d)','(\d\d):(\d\d)'\]", dm.group(2)):
            names = set(re.findall(r'"([^"]+)"|\'([^\']+)\'', rm.group(1)))
            names = {a or b for a, b in names}
            flow.setdefault(d, []).append((names, int(rm.group(2)) * 60 + int(rm.group(3)), int(rm.group(4)) * 60 + int(rm.group(5))))
    return flow


def live_candidates(data, done, now, watch=None, flow=None):
    """시간표상 구분 시작(−5분) ~ 구분 종료+90분 사이, 이미 출발한 팀 중 배번이 있는 팀"""
    waves = data['waves']
    out = []
    for d, t, bib, w, _age, _ppl in data['rows']:
        tid = f'{d}-{bib}'
        if tid in done or (watch is not None and tid not in watch) or not re.fullmatch(r'\d{1,2}:\d\d', t or '') or not re.fullmatch(r'\d+', str(bib)):
            continue
        hh, mm = (int(x) for x in t.split(':'))
        day0 = datetime(DAY0[0], DAY0[1], DAY0[2] + d, 0, 0, tzinfo=KST)
        start = day0 + timedelta(hours=hh, minutes=mm)
        end = start + timedelta(minutes=LIVE_AFTER)
        for names, _a, b in (flow or {}).get(d, []):
            if waves[w] in names:
                end = day0 + timedelta(minutes=b + LIVE_END_PAD)
                break
        if start - timedelta(minutes=LIVE_BEFORE) <= now <= end:
            out.append((tid, str(bib), f'{prefix(waves[w])}_{SUFFIX[d]}'))
    return out


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
    live, fin, idps = {}, {}, {}
    try:
        cands = live_candidates(data, done, datetime.now(KST), load_watch(sys.argv[1] if len(sys.argv) > 1 else 'index.html'), load_flow(sys.argv[1] if len(sys.argv) > 1 else 'index.html'))[:120]
        with ThreadPoolExecutor(max_workers=6) as ex:
            for tid, v in ex.map(lambda c: fetch_live(*c), cands):
                if v is not None:
                    live[tid] = v[:2]
                    idps[tid] = v[3]   # 상세 페이지 id: 순위가 아직 없어도 기록 페이지로 바로 연결
                    if v[2]:
                        fin[tid] = v[2]   # 순위 목록에 아직 안 올라왔어도 상세 페이지에 최종 기록이 있으면 임시로 보여줌
    except Exception as e:  # noqa: BLE001
        print(f'warn: live: {e}', file=sys.stderr)
    json.dump({'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
               'errors': errors, 'done': sorted(done), 'res': recs, 'live': live, 'fin': fin, 'idp': idps}, sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
