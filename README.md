# 온터

공공임대 단지 318곳에 대해, 아직 하지 않은 주거복지 프로그램 가운데 먼저 검토할 후보를 근거·사례·걸림돌·실행 점검표와 함께 보여 주는 시스템.

**공개 시연판: https://clustering-jun.github.io/onter/**

시연판은 서버 없이 도는 정적 사이트다. 추천과 실행 계획은 조절값의 격자로 미리 계산해 두었고, 문장과 점검표는 로컬 LLM(Ollama, exaone3.5:7.8b)으로 미리 만들어 검사를 통과한 것만 실었다. 제외·메모 같은 입력은 보는 사람의 브라우저에만 저장된다.

## 폴더

| 경로 | 내용 |
|---|---|
| `docs/` | 공개 시연판(GitHub Pages). `platform/tools/build_static.py`가 만든다. 직접 고치지 않는다 |
| `platform/` | 웹 플랫폼. 파이썬 서버(`server/`), 화면(`web/`), LLM 미리 만들기와 정적 판 빌드(`tools/`), 만들어 둔 LLM 결과(`data/`) |
| `model/` | 추천 알고리즘 네 모듈(`onter/`), 실험(`experiments/`), 결과(`results/`), 설계 문서(`docs/`) |
| `knowledge_graph/` | 단지·프로그램·기록·사례의 연결을 탐색하는 시제품(로컬 서버 필요) |
| `tools/` | 자료 가공 스크립트(해피콜, 커뮤니티 기록, 사례집, 뉴스) |

문서: [시스템 구조](model/docs/00_system_architecture.md) · [플랫폼 설계](platform/docs/01_설계.md) · [플랫폼 README](platform/README.md)

## 이 저장소에 없는 것

원자료와 가공 자료(`data/`), 모델 산출물 표(`model/outputs/`의 LLM 문장 외), 전문가 응답 원본, Knowledge Graph DB는 올리지 않았다. 그래서 저장소만 받아서는 서버 판을 돌릴 수 없고, 시연판(`docs/`)만 그대로 열 수 있다.

```bash
python -m http.server 8000 --directory docs
```

자료가 있는 PC에서 서버 판을 돌리고 시연판을 다시 만드는 방법은 [platform/README.md](platform/README.md)에 있다.

## 주의

- 시연판의 수치는 2026년 11월 기준 자료로 계산한 것이며, 후보는 '검토 후보'이지 확정된 계획이 아니다.
- LLM 문장은 숫자와 정해 둔 표현만 검사했다. 틀린 집계나 어색한 문장이 남아 있을 수 있다.
- 뉴스는 제목과 링크만 싣는다.
