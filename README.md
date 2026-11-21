<div align="center">
<h6>2026 CO-SHOW</h6>

<h1>AI 기반 맞춤형 주거복지 지원 플랫폼</h1>

<div>    
    <a>박정준</a>&nbsp&nbsp&nbsp&nbsp;
    <a>김서현</a>&nbsp&nbsp&nbsp&nbsp;
    <a>구은정</a>
</div>
<br>
<div>
    경상국립대학교 AI정보공학과, 컴퓨터공학부
</div>

<div>
    <h4 align="center">
        <a href="https://clustering-jun.github.io/onter/#/map" target="_blank">
            <img src="https://img.shields.io/badge/Web%20Demo-4285F4.svg?logo=googlechrome&logoColor=white" alt="Web Demo">
    </h4>
</div>
</div>

---

## 뉴스
- **2026년 10월 10일:** 빅데이터 컨소시엄 대표단 선발
- **2026년 10월 ~ 11월:** 현장실증 및 인큐베이팅 시스템 고도화
- **2026년 11월 20일:** 2026 CO-SHOW 최종 발표
  
  - 🏆 전남광주통합특별시장상 수상

---

## 프로젝트 구조

```text
├── model/                           # 추천 알고리즘 및 분석·실험
│   ├── onter/                       # 추천 시스템 패키지
│   ├── experiments/                # 비교·절제 실험 및 전문가 평가
│   ├── results/                    # 실험 결과 표·그림
│   ├── outputs/                    # 모델 산출물(LLM 문장 외 파일은 gitignore)
│   ├── docs/                       # 시스템 구조·알고리즘·실험 문서
│   ├── build_outputs.py            # 추천·프로파일·운영계획 산출물 생성
│   ├── run_all.py                  # 실험·보고서·산출물 일괄 생성
│   ├── run_llm_explain.py           # LLM 설명 문장 일괄 생성
│   └── serve_ollama.ps1             # Windows용 Ollama 서버 실행
├── platform/                        # 웹 플랫폼 및 정적 시연판 빌드
│   ├── server/
│   ├── web/                        # 웹 화면 원본(HTML·CSS·JavaScript·이미지)
│   ├── tools/
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
│   └── eda/                        # 데이터 정합성 점검 및 탐색 분석
├── knowledge_graph/                 # 단지·프로그램·기록·사례 연결 탐색 시제품
│   ├── build_graph.py              # 지식 그래프 DB 생성
│   ├── server.py                   # 그래프 탐색 서버
│   ├── web/                        # 그래프 탐색 화면
│   └── docs/                       # 그래프 구조 및 검증 문서
├── docs/                            # GitHub Pages 공개 시연판(자동 생성)
├── .gitignore
└── README.md
```

원자료·가공 자료(`data/`), 전문가 응답 원본(`model/expert_request/`), 지식 그래프 DB(`knowledge_graph/data/`)는 저장소에 포함되지 않습니다.

## 설치

Python 3.10 이상을 권장합니다.

### 공개 시연판 실행

추가 Python 패키지나 별도 데이터 없이 실행할 수 있습니다.

```bash
git clone https://github.com/clustering-jun/onter.git
cd onter
python -m http.server 8000 --directory docs
```

브라우저에서 http://localhost:8000 에 접속합니다.

### 로컬 서버 및 모델 실행

저장소 최상위 폴더에서 필요한 패키지를 설치합니다.

```bash
python -m pip install numpy pandas "scipy>=1.9" scikit-learn matplotlib openpyxl
```

가공 자료와 필요한 전문가 응답 파일을 별도로 준비한 뒤 웹 플랫폼을 실행합니다.

```bash
python platform/server/app.py --port 8770
```

브라우저에서 http://localhost:8770 에 접속합니다.

모델 실험과 산출물을 다시 생성하려면 다음 명령을 실행합니다.

```bash
python model/run_all.py
```

설명 문장과 실행 점검표 생성에는 선택적으로 로컬 LLM(Ollama, `exaone3.5:7.8b`)을 사용합니다. LLM을 사용할 수 없으면 규칙 기반 문장과 점검표로 동작하며, 추천 순위와 운영계획 계산에는 LLM이 필요하지 않습니다.

자세한 실행 및 정적 시연판 빌드 방법은 `platform/README.md`를 참고합니다.

---
## 인용
본 연구(또는 코드)를 인용하실 경우, 아래와 같이 표기해 주시기 바랍니다.
```
박정준, 김서현, 구은정, "AI 기반 맞춤형 주거복지 지원 플랫폼," 2026 CO-SHOW, 2026.
```

## 감사의 글
함께 고민하고 노력해 준 팀원 김서현, 구은정에게 감사의 마음을 전합니다.

프로젝트 수행 과정에서 귀중한 현장 경험과 전문적인 의견을 나누어 주신 주택관리공단 교육정보실 및 주거복지실 관계자 여러분, 현장의 주거복지사님들과 입주민 여러분께 진심으로 감사드립니다. 아울러 연구와 프로젝트 발전에 도움을 주신 한국전자통신연구원(ETRI)과 한국토지주택공사(LH)에도 감사의 말씀을 전합니다.

대표 박정준은 현대차 정몽구 재단 장학생으로, 재단의 지원을 받아 본 프로젝트를 수행하였습니다.

## 연락처
관련하여 궁금한 사항이 있으신 경우 아래로 연락해 주시기 바랍니다.
    
- 책임자: 박정준 ([LinkedIn](https://www.linkedin.com/in/jeong-jun-park/))
- 전자우편: [cluster@gnu.ac.kr](mailto:cluster@gnu.ac.kr)  
