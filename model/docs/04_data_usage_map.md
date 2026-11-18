# 데이터 활용 지도

`project/data/processed`의 일곱 묶음을 어디에 썼는지. 역할: **입력**(점수 계산) / **검증**(실험의 기준) / **근거**(사례·설명) / **표시**(화면 전용, `03_web_design_notes.md` 3절).

| 묶음 | 파일 | 역할 | 쓰는 곳 |
|---|---|---|---|
| complex_integrated | complex_master.csv | 입력 | 인구·주거·공간·접근성·홈닥터 → `data.complexes()` → 모듈 1 필요 지수, 모듈 2 유사도, 모듈 4 여건 |
| | 〃 고독사 열 | 검증 | N1 필요 지수 점검 전용(E1) |
| | home_doctor_monthly, model_monthly_panel | 표시 | 추이선 |
| community_nlp | program_analysis.csv | 입력 | 단지×프로그램 행렬, 분야·대상 소속, 요건 프로파일, 사례 기록, 검색 색인 |
| | standard_program_dictionary.csv | 입력 | 추천 대상 96종의 정의 속성(기간 통계는 누수 방지로 안 씀) |
| | codebook_taxonomy.csv | 입력 | 코드 이름표 |
| | complex_program_candidates.csv, complex_features.csv, latent·cooccurrence | 미사용 | 전체 기간으로 만든 표라 시간 분할 평가에 쓰면 미래가 샌다. 같은 값을 기간별로 다시 계산했다 |
| | complex_types.csv, alias_dictionary.csv | 표시 | 운영 방식 유형, 자동 완성 |
| | budget_assumptions.csv | 입력(간접) | 기록의 비용 추정치가 이 가정에서 나왔다 |
| happycall | service_demand.csv | 입력+검증 | 목표 분포의 기준(공단 응답, 연령 보정), 수요 정렬 지표(E6) |
| | management_scores.csv | 검증 | 만족도와의 관계(E6, 관계 없음) |
| | voc, source_findings, evidence_chunks | 표시 | 주민 목소리 패널 |
| complex_keys | crosswalk, happycall_office_map_confirmed | 입력 | 기록 유무, 해피콜 관리소 연결(통합 관리소 제외) |
| complex_month_panel | complex_month_panel.csv | 표시 | 단지×월 추이 |
| housing_welfare_news | article_program, articles | 근거+검증 | 프로그램별 뉴스(제목·링크), 검색 평가(E7) |
| | signals, sentences, chunks | 표시(내부) | 취약 신호 문장은 내부 전용 |
| casebook_programs | evidence_cards, links | 근거+검증 | 사례 카드, 검색 평가(E7) |
| | obstacle_playbook, case_obstacles | 근거 | 점검표의 걸림돌·해결 |
| | welfare_worker_deployment_2025 | 입력 | 배치 여부(여건, 의존 프로그램 추정) |
| | case_elements, chunks | 표시 | 사례 상세 |

## 지켜야 할 것

- 조인은 `complex_id`, `std_id`로만 한다.
- 접근성 결측은 0km가 아니다. 중앙값으로 채운 것은 유사도 계산뿐이다.
- 참여 인원은 고유 주민 수가 아니다. 순위에 쓰지 않았다.
- 2026년 상반기 기록은 보고 지연으로 적게 잡혔을 수 있다(분할 C는 참고).
- 해피콜 수요는 전국·응답자 구분 집계다. 단지별 정답으로 복제하지 않았다.
