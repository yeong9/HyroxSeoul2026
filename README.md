# HYROX Seoul 2026 시간표 (오늘 누구 응원하지?)

HYROX Seoul 2026(2026.11.13–15) 출발 시간과 시상 스케줄을 이름으로 찾아 한눈에 보는 개인 제작 웹페이지입니다.
페이지: https://yeong9.github.io/HyroxSeoul2026/

## 기능

- 이름이나 배번으로 검색해 내 목록에 추가하면 날짜별, 디비전별로 정리됩니다. 한글 이름으로 영문 등록 이름을 찾는 후보 검색, XON·F45범계 필터, 샘플 목록 불러오기를 지원합니다.
- 디비전별 출발 시간대(하루 흐름)와 시상식 일정을 함께 보여줍니다.
- 한국 시간 기준으로 1분마다 상태를 갱신합니다. 출발 후 1시간까지 진행 중, 1시간부터 1시간 30분까지 N분 경과, 이후 종료로 표시합니다.
- 결과 사이트에 결과가 올라온 팀은 바로 종료로 바뀌고, 완주 기록과 전체 순위, 상세 결과 링크가 붙습니다.
- 스타트리스트에 아직 없는 팀은 "시간 미확인"으로 두고 가능한 시간 범위를 보여주며, 등록되면 자동으로 실제 팀에 연결됩니다.
- 경기장 지도(`img/hyroxseoulmap.webp`), 진행 중 경기로 이동하는 버튼, 대회 전(11/13 08:00 이전) 안내를 제공합니다.
- 목록은 각자 브라우저(localStorage)에만 저장됩니다.

## 구성

| 경로 | 설명 |
| --- | --- |
| `index.html` | 화면과 선수 데이터가 모두 들어 있는 정적 페이지 (빌드 과정 없음) |
| `img/hyroxseoulmap.webp` | 경기장 지도 (원본 PNG를 3000px로 줄인 것) |
| `scripts/fetch_startlist.py` | startlist.hyrox.com 스타트리스트를 받아 데이터(JSON)로 만듦 |
| `scripts/apply_startlist.py` | 받은 데이터를 `index.html` 안의 `DATA`에 반영 |
| `scripts/fetch_results.py` | results.hyrox.com 결과 목록에서 결과가 올라온 팀과 기록·순위를 `finished.json`으로 만듦 |
| `.github/workflows/pages.yml` | 위 스크립트를 돌려 GitHub Pages에 배포 |

## 자동 갱신 (GitHub Actions)

저장소 Settings → Pages 의 Source 는 **GitHub Actions** 여야 합니다.

- `main` 에 푸시하면 스타트리스트를 새로 받아 사이트를 배포합니다.
- 매일 10:05, 18:05(KST)에 스타트리스트를 다시 받아 반영합니다. 마지막 날(11/15)까지 동작합니다.
- 대회 기간(11/13~11/15) 09:00~22:00(KST)에는 5분마다 결과를 확인해 `finished.json`을 만들어 배포합니다. 그 밖의 시간에는 건너뜁니다.
- 스타트리스트나 결과 사이트에 접속하지 못하면 직전 데이터로 유지됩니다.
- 푸시할 때 워크플로우 파일을 포함하려면 토큰에 `workflow` 권한이 필요합니다.

## 데이터

- 출처: [startlist.hyrox.com](https://startlist.hyrox.com/) 2026 Seoul 스타트리스트, [results.hyrox.com](https://results.hyrox.com/season-9/) 2026 Seoul 결과
- 시상 스케줄과 출발 시간대: 대회 공식 타임테이블
- XON·F45범계 소속 표기와 시간 미확인 팀은 `index.html` 안의 목록에서 관리합니다.
- 결과 반영과 스타트리스트 갱신은 몇 분 정도 시간차가 있을 수 있고, 출발 시간은 대회 직전까지 바뀔 수 있습니다.

HYROX 공식 페이지가 아닙니다.

## 만든 사람

by yeong9 · [instagram.com/yeong9_](https://www.instagram.com/yeong9_/)
