# 온터 추천 시스템: 알고리즘 설계·실험 (웹 구축 전 단계)

주택관리공단 318개 단지에 복지 프로그램 검토 후보를 내는 네 모듈의 알고리즘, 비교·절제 실험, 산출물.

## 실행

```bash
python run_all.py
```

약 3분. 실험 → 전문가 응답 반영 → 보고서 → 산출물 순서. 필요한 것: numpy, pandas, scipy, scikit-learn, matplotlib, openpyxl.

로컬 LLM으로 근거 문장을 다듬을 때(선택, Ollama 필요. 파이썬 SDK `ollama`가 없거나 깨져 있으면 HTTP로 직접 부른다):

```bash
powershell -ExecutionPolicy Bypass -File serve_ollama.ps1
```

```bash
python run_llm_explain.py
```

`--sample 300`으로 표본만 먼저 볼 수 있다. 결과는 `outputs/llm/explanations_llm.jsonl`에 한 줄씩 저장되고, 끊긴 뒤 다시 실행하면 남은 것만 한다. 자세한 내용은 `docs/06_llm_plan.md`.

## 폴더

| 경로 | 내용 |
|---|---|
| `onter/` | 패키지. `data` 로더, `features` 공통 특징, `m1_profile`, `m2_cases`, `m3_rank`, `m4_feasibility`, `explain`, `evalx` |
| `experiments/` | `exp_ranking.py`(E3·E4), `exp_modules.py`(E1·E2·E5·E6·E7), `exp_expert.py`(E8 전문가 응답), `make_report.py`, `common.py` |
| `results/` | `tables/*.csv`(실험 표 45개), `figures/`, `summary.json` |
| `outputs/` | 전체 기간으로 계산한 시스템 산출물(웹이 읽을 자료) |
| `expert_request/` | 전문가 검토 요청·응답 엑셀, 출처 키, 요청 당시 순위 |
| `docs/` | 설계·실험·웹 메모·데이터 지도·전문가 요청·LLM 계획 |

## 문서

0. `docs/00_system_architecture.md` 전체 구조: 자료 → 알고리즘 → 입력·출력
1. `docs/01_algorithm_design.md` 알고리즘 설계와 근거
2. `docs/02_experiments.md` 비교·절제 실험 결과(자동 생성)
3. `docs/03_web_design_notes.md` 웹 설계 메모(모델링과 분리)
4. `docs/04_data_usage_map.md` 전처리 데이터 활용 지도
5. `docs/05_expert_label_request.md` 전문가 검토 요청과 응답 반영 결과
6. `docs/06_llm_plan.md` 로컬 LLM 실행 결과

## 산출물(outputs)

| 파일 | 내용 |
|---|---|
| `m1_complex_profile.csv` | 단지 프로파일: 필요 백분위·구간, 공급, 어긋남, 우선 검토, 유형, 이력 |
| `m1_target_distribution.csv` | 단지별 목표 분야 분포 |
| `m2_complex_peers.csv` | 이웃 10곳 × 3종(혼합·구조·거리)과 성분 유사도 |
| `m3_recommendations_top10.csv` | 단지별 검토 후보 10개와 성분 점수 |
| `m3_ranking_by_domain.csv` | 분야별 상위 3개와 상태(신규·유지·재개) |
| `m4_program_requirements.csv` | 프로그램 96종 요건 프로파일 |
| `m4_complex_capacity.csv` | 단지 여건 |
| `m4_default_plan.csv` | 기본 제약의 연간 묶음 |
| `recommendations_detail.jsonl` | 추천 3,180건의 점검표·사례·근거 문장 |

## 핵심 결과

- 어떤 개인화 모델도 전국 채택률을 뚜렷이 넘지 못한다. 필요 적합만으로는 무작위와 같다.
- 온터 기본값(필요 가중 0.2, 보정 0.25)은 새 도입 재현율을 근거 모델의 95%로 지키면서 필요 적합을 0.52 → 0.68로 올린다.
- 해피콜을 쓰지 않은 구성의 추천도 현재 공급보다 주민 수요 분포에 가깝다.
- 규칙 기반 실행 가능성 점수는 도입을 예측하지 못해 순위에서 뺐다. 주거복지사 의존 프로그램 23종을 찾았다.
- 전문가 응답(1명)을 반영했다. 실행 요건을 전문가 값으로 바꿨고, '주거복지사 필요인데 미배치' 경고를 더했다. 순위 기본값은 바꾸지 않았다.
- 전문가 판단에서도 채택률은 '실행'과, 필요 적합은 '필요'와 맞았다. 온터 기본값은 필요 등급을 올리면서 실행 등급을 지킨다.
- 필요 지수의 독립 검증은 아직 없다. 전문가 응답이 단지 프로파일을 보고 작성된 흔적이 있어 두 번째 평가자가 필요하다.
