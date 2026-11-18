# 자료 가공 스크립트

`project/data/`의 원자료를 읽어 `data/processed/`의 가공 자료를 만든다. `data/`는 용량과 내부 자료 때문에 저장소에 없으므로, 여기 스크립트는 자료가 있는 PC에서 돌린다. 경로는 모두 이 파일이 있는 폴더 기준 상대 경로다(`project/`를 옮겨도 된다).

`python -m 패키지.모듈` 형태는 이 `tools/` 폴더에서 실행한다.

## 폴더

| 폴더 | 하는 일 | 주요 입력 → 출력(`data/` 아래) |
|---|---|---|
| `complex_address/` | 단지 주소 → 좌표(VWorld), 도로명·지번 교차검증, LH 공식 자료 대조, 확정 주소를 반영한 최종 CSV | `raw/…임대단지 관리현황_20260901.csv` → `processed/complex_geocode_20261117_v1/` |
| `happycall/` | 해피콜 결과보고서 PDF에서 표·의견을 뽑아 구조화(추출 → 정제 → 점검 → 패키징) | `전문가 자료/주요사업 결과보고서.pdf`(project 밖) → `processed/happycall_2025_v1/`, 정제본은 `전문가 지식자료/주요사업_결과보고서_정제/`(project 밖) |
| `community_nlp/` | 커뮤니티 프로그램 기록을 표준 프로그램(std_id)으로 묶고, 단지 특성·후보·잠재요인과 품질 점검 | `raw/임대주택 주거복지 커뮤니티 현황(202606기준).xlsx` → `processed/community_nlp_2026_v1/` |
| `casebook_nlp/` | 주거복지사 활동 사례집을 사례·근거 카드·장애물과 해결로 구조화 | `raw/expert_casebook_2025/` → `processed/casebook_programs_v1/` |
| `news_nlp/` | 주거복지 뉴스·보도자료 구조화(제목·링크만 공개, 본문은 내부 전용) | `raw/news_crawl_20261117/` → `processed/housing_welfare_news_v1/` |
| `welfare_services/` | 한국사회보장정보원 중앙·지자체 복지서비스 목록 내려받기 | 공공데이터포털 API → `processed/welfare_services_v1/` |
| `eda/` | 단지 키 정합성, 단지×월 패널, 탐색 분석·문제정의 분석, 분석 웹 페이지 | `processed/*` → `processed/complex_keys_20261117_v1/`, `complex_month_panel_20261117_v1/`, EDA 출력 폴더 |

## 실행 순서(처음부터 다시 만들 때)

1. `complex_address/geocode_complexes.py` → `compare_lh_addresses.py` → `build_final_complex_csv.py`
2. `happycall/extract_happycall.py` → `finalize_happycall.py` (추가 정제는 `refine_happycall.py` → `audit_happycall_v2.py` → `package_happycall_v2.py`)
3. `community_nlp/run_pipeline.py`, `casebook_nlp/build.py`, `news_nlp/build.py`
4. `eda/build_crosswalk.py` → `confirm_happycall_map.py` → `build_month_panel.py`
5. `eda/run_eda.py` → `run_problem.py` → `redesign_analysis.py` → `korea_outline.py` → `build_web.py`
6. `welfare_services/fetch.py`
7. 그 위에서 `model/run_all.py`(알고리즘·실험)와 `platform/`(웹)이 돈다.

각 스크립트의 머리말(docstring)에 입력·출력·실행 방법이 있다. 대부분 같은 입력이면 같은 결과가 나온다.

## 인증키

저장소에 올리지 않는다.

| 키 | 쓰는 곳 | 넣는 곳 |
|---|---|---|
| 공공데이터포털(`data_go_kr`) | `welfare_services/fetch.py` | `project/.secrets/data_go_kr.key` 또는 환경 변수 `DATA_GO_KR_KEY` |
| VWorld | `complex_address/geocode_complexes.py` | 환경 변수 `VWORLD_KEY` |

`.secrets/`는 `.gitignore`에 들어 있다.

## 참고

- `eda/vendor/`는 Plotly 번들(분석 웹 페이지가 한 파일로 열리도록 넣는다), `eda/web_template*`는 그 페이지의 틀이다.
- `happycall/`의 `refine`·`audit`·`package` 스크립트는 일회성 정제 작업을 그대로 남긴 것이다. `audit_happycall_v2.py --render`는 poppler의 `pdftoppm`이 PATH에 있거나 환경 변수 `PDFTOPPM`에 경로가 있어야 한다.
