# 온터

공공임대 단지 318곳에 대해, 아직 하지 않은 주거복지 프로그램 가운데 먼저 검토할 후보를 근거·사례·걸림돌·실행 점검표와 함께 보여 주는 시스템.

**공개 시연판: https://clustering-jun.github.io/onter/**

시연판은 서버 없이 도는 정적 사이트다. 추천과 실행 계획은 조절값의 격자로 미리 계산해 두었고, 문장과 점검표는 로컬 LLM(Ollama, exaone3.5:7.8b)으로 미리 만들어 검사를 통과한 것만 실었다. 제외·메모 같은 입력은 보는 사람의 브라우저에만 저장된다.

## 프로젝트 구조

주요 경로만 표시했습니다. `data/`, `model/expert_request/`, `knowledge_graph/data/`는 로컬 실행에 사용하는 경로이며 저장소에는 포함되지 않습니다.

```text
├── model/                           # 추천 알고리즘 및 비교·절제 실험
│   ├── onter/                       # 추천 시스템 패키지
│   │   ├── config.py                # 경로 및 공통 설정
│   │   ├── data.py                  # 전처리 데이터 로더
│   │   ├── features.py              # 단지 특징·프로그램 운영 행렬
│   │   ├── m1_profile.py            # 단지별 필요·공급·격차 및 유형 분석
│   │   ├── m2_cases.py              # 유사 단지·운영 사례 탐색 및 프로그램 검색
│   │   ├── m3_rank.py               # 프로그램 추천 점수 및 필요 보정 재순위
│   │   ├── m4_feasibility.py        # 실행 요건 검토 및 제약 기반 연간 계획
│   │   ├── expert.py                # 전문가 응답 로딩 및 실행 요건 반영
│   │   ├── explain.py               # 템플릿 기반 추천 근거 생성
│   │   ├── llm.py                   # Ollama 연결 및 설명 문장 생성
│   │   └── evalx.py                 # 평가 지표 및 통계 검정
│   ├── experiments/                # 모듈·순위·전문가 평가 실험
│   ├── results/                    # 실험 결과 표·그림
│   ├── outputs/                    # 모델 산출물(LLM 문장 외 파일은 gitignore)
│   ├── expert_request/             # 전문가 요청·응답 원본(gitignore)
│   ├── docs/                       # 시스템 구조·설계·실험 문서
│   ├── build_outputs.py            # 추천·프로파일·실행 계획 산출물 생성
│   ├── run_all.py                  # 실험 → 보고서 → 산출물 일괄 실행
│   ├── run_llm_explain.py           # 로컬 LLM 설명 문장 일괄 생성
│   └── serve_ollama.ps1             # Windows용 Ollama 서버 실행
├── platform/                        # 로컬 웹 플랫폼 및 정적 시연판 빌드
│   ├── server/                     # HTTP 서버 및 플랫폼 API
│   │   ├── app.py                  # 서버 실행 및 라우팅
│   │   ├── engine.py               # 추천·연간 계획 계산 엔진
│   │   ├── catalog.py              # 프로그램·사례·주민 수요 자료 조회
│   │   ├── llm_service.py          # LLM 설명·점검표 생성 및 검사·캐시
│   │   └── store.py                # 제외·보류·메모 등 사용자 입력 저장
│   ├── web/                        # 웹 화면 원본(HTML·CSS·JavaScript·이미지)
│   ├── tools/
│   │   ├── prefill_llm.py          # LLM 결과 사전 생성
│   │   └── build_static.py         # GitHub Pages용 docs/ 생성
│   ├── data/                       # LLM 결과 캐시(사용자 입력은 gitignore)
│   ├── tests/                      # API 점검 스크립트
│   ├── docs/                       # 플랫폼 설계 및 변경 기록
│   └── start.cmd                   # Windows용 플랫폼 실행
├── tools/                           # 원천 자료 수집·전처리 및 탐색 분석
│   ├── complex_address/            # 단지 주소 정제·좌표 변환·공식 자료 대조
│   ├── community_nlp/              # 커뮤니티 활동 기록 정제 및 표준 프로그램 분류
│   ├── happycall/                  # 해피콜 보고서 추출·정제·구조화
│   ├── casebook_nlp/               # 사례집의 사례·걸림돌·해결 전략 구조화
│   ├── news_nlp/                   # 주거복지 뉴스 구조화
│   ├── welfare_services/           # 중앙·지자체 복지서비스 목록 수집
│   └── eda/                        # 데이터 정합성 점검·탐색 분석·분석 웹 생성
├── knowledge_graph/                 # 단지·프로그램·기록·사례 연결 탐색 시제품
│   ├── build_graph.py              # 지식 그래프 DB 생성
│   ├── server.py                   # 그래프 탐색 서버
│   ├── web/                        # 그래프 탐색 화면
│   ├── data/                       # 로컬 그래프 DB(gitignore)
│   └── docs/                       # 그래프 구조 및 검증 문서
├── docs/                            # GitHub Pages 공개 시연판(자동 생성)
├── data/                            # 원자료·가공 자료(gitignore)
├── .gitignore
└── README.md
```

자료 가공 순서와 입출력은 [tools/README.md](tools/README.md)를 참고합니다. `docs/`는 `platform/tools/build_static.py`가 생성하므로 화면 수정은 `platform/web/`에서 합니다.

문서: [시스템 구조](model/docs/00_system_architecture.md) · [플랫폼 설계](platform/docs/01_설계.md) · [플랫폼 README](platform/README.md)

## 설치

Python 3.10 이상을 권장합니다. 아래 명령은 저장소 최상위 폴더에서 실행합니다.

### 공개 시연판 실행

저장소를 내려받은 뒤 다음 명령으로 정적 시연판을 열 수 있습니다. 별도 데이터나 추가 Python 패키지는 필요하지 않습니다.

```bash
git clone https://github.com/clustering-jun/onter.git
cd onter
python -m http.server 8000 --directory docs
```

브라우저에서 http://localhost:8000 에 접속합니다.

### 로컬 서버 및 모델 실행

모델·플랫폼 실행에 필요한 Python 패키지를 설치합니다. 정수계획 계산에 사용하는 `scipy.optimize.milp`를 위해 SciPy 1.9 이상이 필요합니다.

```bash
python -m pip install numpy pandas "scipy>=1.9" scikit-learn matplotlib openpyxl
```

원자료·가공 자료와 필요한 전문가 응답 파일을 별도로 준비한 환경에서 실행합니다.

```bash
# 로컬 웹 플랫폼 실행
python platform/server/app.py --port 8770
```

브라우저에서 http://localhost:8770 에 접속합니다. 모델 실험과 산출물을 다시 만들 때는 다음 명령을 사용합니다.

```bash
python model/run_all.py
```

### 로컬 LLM 사용(선택)

설명 문장과 실행 점검표 생성에는 Ollama의 `exaone3.5:7.8b` 모델을 사용합니다. Ollama를 설치하고 서버를 실행한 뒤 모델을 내려받습니다.

```bash
ollama pull exaone3.5:7.8b
```

LLM을 사용할 수 없으면 규칙 기반 문장과 점검표를 사용합니다. 추천 순위와 연간 계획 계산에는 LLM이 필요하지 않습니다. 자세한 실행·정적 시연판 빌드 방법은 [platform/README.md](platform/README.md)를 참고합니다.

## 이 저장소에 없는 것

원자료와 가공 자료(`data/`), 모델 산출물 표(`model/outputs/`의 LLM 문장 외), 전문가 응답 원본, Knowledge Graph DB는 올리지 않았다. 그래서 저장소만 받아서는 서버 판을 돌릴 수 없고, 시연판(`docs/`)만 그대로 열 수 있다.

## 주의

- 시연판의 수치는 2026년 11월 기준 자료로 계산한 것이며, 후보는 '검토 후보'이지 확정된 계획이 아니다.
- LLM 문장은 숫자와 정해 둔 표현만 검사했다. 틀린 집계나 어색한 문장이 남아 있을 수 있다.
- 뉴스는 제목과 링크만 싣는다.
