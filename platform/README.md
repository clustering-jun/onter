# 온터 웹 플랫폼

단지를 지도에서 고르고, 현황을 보고, 검토할 복지 프로그램 후보와 근거·사례·걸림돌·실행 점검표를 확인하고, 예산·인력 한도 안에서 한 해 묶음을 고르는 로컬 웹 플랫폼. 알고리즘은 `project/model`, 자료는 `project/data/processed`, 그래프는 `project/knowledge_graph`를 그대로 쓴다.

## 실행

```bash
python server/app.py --port 8770
```

엔진을 올리는 데 5초쯤 걸린다. 그 뒤 http://localhost:8770 을 연다. Windows에서는 `start.cmd`를 더블클릭해도 된다. 추가로 설치할 패키지는 없다(`project/model`이 쓰는 numpy·pandas·scipy·scikit-learn과 파이썬 표준 라이브러리만 쓴다).

- 지도 타일(OpenStreetMap), Leaflet, 글꼴(Pretendard)은 인터넷에서 받는다. 인터넷이 없으면 지도 탭이 비고 글꼴이 맑은 고딕으로 바뀐다.
- LLM 기능은 Ollama가 떠 있어야 한다(`project/model/serve_ollama.ps1`). 없으면 규칙으로 만든 문장과 점검표가 나온다.
- Knowledge Graph 탭은 `project/knowledge_graph/data/knowledge.sqlite`가 있어야 한다.

## 폴더

```
platform/
├─ server/
│  ├─ app.py           HTTP 서버와 라우터. /api/* 플랫폼 API, /kg/* Knowledge Graph, 나머지는 web/
│  ├─ engine.py        project/model의 네 모듈을 메모리에 올리고 단지 한 곳 단위로 다시 계산
│  ├─ catalog.py       조회용 자료(프로그램 사전, 검색, 사례집·뉴스, 해피콜, 분석용 표)
│  ├─ llm_service.py   로컬 LLM: 추천 근거 문장, 실행 점검표, 묶음 설명. 검사와 캐시
│  └─ store.py         사용자 입력 저장(확인된 필요, 제외·보류, 메모)
├─ web/
│  ├─ index.html
│  ├─ css/app.css      플랫폼 스타일
│  ├─ css/kg_embed.css Knowledge Graph 화면을 플랫폼 디자인에 맞추는 덮어쓰기
│  ├─ js/core.js       공통(API, 상태, 표시 도우미, 차트, 단지 카드, 목차)
│  ├─ js/main.js       시작, 탭 전환, 단지 선택
│  ├─ js/tabs/*.js     탭 10개(map, complex, recommend, plan, programs, cases, happycall, analysis, kg, about)
│  └─ img/complex/     단지 사진(단지ID.jpg). 없으면 default.jpg(예시 사진)
├─ data/               llm_cache.json(LLM 결과 캐시), llm_generated/(읽기 좋은 사본), user_state.json(사용자 입력, 저장소에는 없음)
├─ tools/
│  ├─ prefill_llm.py   LLM 결과를 미리 만들어 캐시에 채운다
│  └─ build_static.py  서버 없이 도는 정적 판을 project/docs에 만든다(GitHub Pages)
├─ tests/test_api.py   API 점검
├─ docs/               01 설계, 02 변경 기록
└─ start.cmd
```

## 화면

| 탭 | 하는 일 |
|---|---|
| 지도 | 단지 318곳을 원으로 표시. 색 기준 20가지, 지사·유형으로 거르기, 누르면 단지 카드 |
| 단지 현황 | 단지 카드와 사진, 분야별 필요·공급, 확인된 필요 입력, 기본 정보, 지표 원값, 연령, 고독사 기록, 운영 이력, 프로그램 상태표, 거리, 해피콜, 홈닥터, 협력 기록, 비슷한 단지. 위쪽에 목차 |
| 프로그램 추천 | 한 화면 세 칸(조절 / 후보 목록 / 고른 후보 상세). 목록은 순위·분야별로 전환. 상세는 추천 근거, 운영 사례, 걸림돌·해결, 실행 점검표, 실행 요건 |
| 실행 계획 | 예산·인력·개수·분야 조건을 바꾸면 정수계획으로 묶음을 다시 고름. 달력, 묶음 설명 |
| 프로그램 사전 | 카드 목록(검색·분야·정렬) → 프로그램 상세 화면 |
| 사례·소식 | 사례 카드(목록 + 상세, 필터), 걸림돌·해결 표, 뉴스 제목과 링크 |
| 해피콜 | 주민이 말한 수요, 수요·공급·추천 분포, 관리소별 만족도, 주민 의견(분류 순위 + 대표 의견) |
| 분석 | 변수 탐색기(산점도), 전국 수요와 공급, 필요와 공급이 어긋난 단지 |
| Knowledge Graph | 단지·프로그램·기록·사례·소식의 연결 탐색 |
| 안내 | 계산 방법, 상태 표시의 뜻, LLM 사용 범위 |

## 점검

```bash
python tests/test_api.py --llm
```

GET 경로의 JSON 출력, 기본 순위와 오프라인 산출물의 일치(318/318), 속도, 한도 준수, 상태 구분, 제외 정책, 확인된 필요, 손잡이, 결측 표시, LLM 3종을 본다.

## LLM 결과 미리 만들기와 공개 시연판

```bash
python tools/prefill_llm.py
```

서버와 Ollama가 떠 있어야 한다. 묶음 설명(단지 × 조건 12가지), 분야별 보기의 근거 문장, 실행 점검표를 순위가 높은 것부터 만들어 `data/llm_cache.json`에 쌓고, 읽기 좋은 사본을 `data/llm_generated/*.jsonl`에 남긴다. 끊겨도 다시 실행하면 남은 것만 한다. 점검표 전체는 몇 시간 걸린다(`--top 3 --no-extra`로 줄일 수 있다).

```bash
python tools/build_static.py
```

`project/docs`에 정적 판을 만든다(약 15분, 300MB 남짓). 추천은 필요 반영 정도 4단계 × 분야 고르게 3단계, 실행 계획은 예산 4단계 × 프로그램 수 3단계로 미리 계산한다. LLM 문장은 새로 만들지 않고 캐시에 있는 것만 싣는다. 커밋해서 올리면 GitHub Pages에 반영된다. 정적 판에는 Knowledge Graph 탭이 없고, 인력·분야별 최소 개수 조절과 확인된 필요의 추천 반영이 빠진다.

## 단지 사진 넣기

318곳 모두 들어 있다(원본은 `project/data/raw/complex_photos_20261118/`, 여기에는 긴 변 1200px로 줄인 사본). 바꾸려면 `web/img/complex/`에 `단지ID.jpg`로 넣는다(예: `KOH_1.jpg`). 단지 ID는 단지 현황을 열었을 때 주소창의 `#/complex/` 뒤에 붙는 값이다. 가운데 기준 정사각형으로 잘라 보여 준다. 넣은 뒤에는 브라우저를 새로고침하면 된다.

## 자료를 바꿨을 때

1. `project/model`에서 `python run_all.py`. 필요하면 `python run_llm_explain.py --fresh`.
2. 이 서버를 다시 시작한다(엔진은 시작할 때 한 번 읽는다).
3. Knowledge Graph까지 맞추려면 `project/knowledge_graph`에서 그쪽 서버를 끄고 `python build_graph.py`를 돌린 뒤 이 서버를 다시 시작한다.

## 주의

- 로컬 도구다. 인증이 없고 `127.0.0.1`과 `::1`에만 붙는다. 그대로 공개 서버에 올리지 않는다.
- 단지별 수치를 밖에 공개할 범위는 아직 정하지 않았다.
- 뉴스는 제목과 링크만 보여 준다. 본문과 주민 식별 정보는 싣지 않는다.
- 고독사 기록은 참고로만 보여 주고 추천 계산과 필요 지수에 넣지 않는다.
