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


def parse_checkpoint(page):
    """상세 페이지 아래쪽 '통과 시각' 표에서 마지막으로 찍힌 지점을 보고 끝낸 구간 수(0~16)를 돌려줌 (표가 없으면 -1).
    요약 표(러닝·스테이션 시간)는 한 박자 늦게 채워지거나 비어 보일 때가 있어서, 통과 지점이 더 믿을 만해요.
    지점 순서: 스테이션 1~7 마다 [Rox In, 스테이션 In, 스테이션 Out, Rox Out] 4개, 이어서 월볼 In, Total (총 30개)"""
    vals = []
    for blk in re.split(r'<tr\b', page):
        m = re.search(r'<td[^>]*time_day[^>]*>\s*([^<]*?)\s*</td>', blk)
        if m:
            vals.append(m.group(1))
    if len(vals) != 30:
        return -1
    last = -1
    for i, v in enumerate(vals):
        if re.fullmatch(r'\d{1,2}:\d\d:\d\d', v):
            last = i
    if last < 0:
        return 0
    if last == 29:
        return 16
    if last == 28:
        return 15
    k, r = last // 4 + 1, last % 4
    return 2 * k - 1 if r < 3 else 2 * k


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


def fetch_live(tid, bib, event, idp=''):
    try:
        idp = idp or lookup_idp(bib, event)
        if not idp:
            return tid, None
        q = {'content': 'detail', 'fpid': 'search', 'pid': 'search', 'idp': idp, 'lang': 'EN_CAP', 'event': event}
        page = fetch(BASE + '?' + urllib.parse.urlencode(q), tries=2)
        n, cum = parse_splits(page)
        n = max(n, parse_checkpoint(page))
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


LIVE_END_PAD = 90  # 하루 흐름 시간표의 디비전 범위는 출발 시각 범위라, 마지막 출발 + 90분(완주·기록 반영)까지 확인


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
    """시간표상 출발(−5분) ~ 디비전 마지막 출발 시각+90분 사이, 이미 출발한 팀 중 배번이 있는 팀"""
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


SWEEP_AFTER = 5    # 출발 후 이 시간(분)이 지난 팀부터 진행 구간·완주 기록을 확인
SWEEP_N = 350      # 한 번에 확인하는 일반 팀 수 상한 (오래 안 확인한 팀부터. 처음 쌓인 팀은 몇 번에 나눠 처리)


def recheck_gap(n):
    """끝낸 구간 수에 따라 다시 확인할 때까지 쉬는 시간(분)"""
    return 3 if n >= 12 else 5


def sweep_candidates(data, done, now, flow, skip, chk, nowm=0):
    """조회 대상(소속·기본 목록) 밖 팀 중 완주했을 만한 팀. 순위가 늦게 나와서, 상세 페이지의 최종 기록을 직접 확인"""
    waves = data['waves']
    out = []
    for d, t, bib, w, _age, _ppl in data['rows']:
        tid = f'{d}-{bib}'
        if tid in done or tid in skip or not re.fullmatch(r'\d{1,2}:\d\d', t or '') or not re.fullmatch(r'\d+', str(bib)):
            continue
        hh, mm = (int(x) for x in t.split(':'))
        day0 = datetime(DAY0[0], DAY0[1], DAY0[2] + d, 0, 0, tzinfo=KST)
        start = day0 + timedelta(hours=hh, minutes=mm)
        end = start + timedelta(minutes=LIVE_AFTER)
        for names, _a, b in (flow or {}).get(d, []):
            if waves[w] in names:
                end = day0 + timedelta(minutes=b + LIVE_END_PAD)
                break
        c = chk.get(tid)
        last, n = (c if isinstance(c, list) else [c or 0, 0])
        if start + timedelta(minutes=SWEEP_AFTER) <= now <= end and nowm - last >= recheck_gap(n):
            out.append((last, tid, str(bib), f'{prefix(waves[w])}_{SUFFIX[d]}'))
    out.sort()
    return [(tid, bib, ev) for _c, tid, bib, ev in out[:SWEEP_N]]


def load_prev(path):
    try:
        j = json.load(open(path, encoding='utf-8'))
        return j if isinstance(j, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


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
    prev = load_prev(sys.argv[2]) if len(sys.argv) > 2 else {}
    fin = {k: v for k, v in (prev.get('fin') or {}).items() if k not in done}
    idps = dict(prev.get('idp') or {})
    chk = dict(prev.get('chk') or {})
    live = {k: v for k, v in (prev.get('live') or {}).items() if len(v) > 2 and k not in fin and k not in done and int(datetime.now(KST).timestamp() // 60) - v[2] <= 25}
    src = sys.argv[1] if len(sys.argv) > 1 else 'index.html'
    now = datetime.now(KST)
    nowm = int(now.timestamp() // 60)
    try:
        flow = load_flow(src)
        watch = load_watch(src)
        cands = [(t, b, e, idps.get(t, '')) for t, b, e in live_candidates(data, done, now, watch, flow)[:120]]
        wt = {c[0] for c in cands}
        sweep = [(t, b, e, idps.get(t, '')) for t, b, e in sweep_candidates(data, done, now, flow, set(fin) | wt, chk, nowm) if t not in watch]
        with ThreadPoolExecutor(max_workers=6) as ex:
            for (tid, *_r), (_t, v) in zip(cands + sweep, ex.map(lambda c: fetch_live(*c), cands + sweep)):
                if v is None:
                    continue
                chk[tid] = [nowm, v[0]]
                idps[tid] = v[3]   # 상세 페이지 id: 순위가 아직 없어도 기록 페이지로 바로 연결
                if tid not in fin and not v[2]:
                    before = live.get(tid)
                    n = max(v[0], before[0] if before else 0)   # 구간이 뒤로 가는 일(러닝↔스키 왔다갔다)이 없도록 이전보다 낮은 값은 무시
                    live[tid] = [n, v[1], nowm]   # 팀별 확인 시각(분)도 같이 남겨서 오래된 정보는 화면에서 숨김
                else:
                    live.pop(tid, None)
                if v[2]:
                    fin[tid] = v[2]   # 순위 목록에 아직 안 올라왔어도 상세 페이지에 최종 기록이 있으면 임시로 보여줌
    except Exception as e:  # noqa: BLE001
        print(f'warn: live: {e}', file=sys.stderr)
    json.dump({'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
               'errors': errors, 'done': sorted(done), 'res': recs, 'live': live, 'fin': fin, 'idp': idps, 'chk': chk}, sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
