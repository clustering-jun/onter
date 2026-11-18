# -*- coding: utf-8 -*-
"""README.md·column_dictionary.csv 작성(수치는 manifest 요약에서)."""
import os

import pandas as pd

COLUMNS = [
    ("evidence_cards.csv/.jsonl", "card_id, case_id, std_id, std_name, std_confidence", "근거 카드 1장 = 사례×프로그램. std_id로 추천 후보(community_nlp의 complex_program_candidates 등)와 조인"),
    ("evidence_cards", "headline, need, target, partners, partner_org_labels, operation, how_it_runs, outcomes, outcome_numbers", "'비슷한 단지는 이렇게 했다' 근거: 필요·대상·협력기관(유형)·운영 방법·성과(수치)"),
    ("evidence_cards", "obstacles_and_solutions, lessons", "시작·운영 중 부딪힌 문제 → 해결, 주거복지사의 교훈"),
    ("evidence_cards", "card_text", "화면·LLM 프롬프트에 바로 넣는 한 덩어리 문장(이름 없음, 출처 포함)"),
    ("cases.csv", "case_id, part, domain, region, program_title, summary", "사례 18개. part P1~P4(책의 4부), domain 주거환경·문화·공동체·돌봄·건강·협업"),
    ("cases", "complex_ids, complexes_mentioned, branches", "확정 연결된 단지(complex_id), 원문 단지명, 지사"),
    ("cases", "text_masked", "사례 원문(인물 이름을 [이름]으로 가림)"),
    ("case_programs.csv", "program_id, program_name, program_summary, operation, target, start", "요약 상자 기준 프로그램(사례당 1~2개)"),
    ("case_programs", "std_id, std_confidence, std_methods, std_alternatives", "표준 프로그램 연결: 커뮤니티 NLP 규칙 엔진(rule) + 별칭 사전 근접(alias_knn) 합의. high=둘 다, medium=규칙 또는 근접 0.5 이상"),
    ("case_programs", "target_codes, need_domain_codes", "대상 코드(커뮤니티 NLP 사전), 표준 프로그램의 필요 영역(N1~N6)"),
    ("case_elements.csv", "element_id, type, type_ko, text, value, unit, speaker_role, evidence_masked, evidence_found", "레시피 요소. type: need·target·partner·resource·operation·outcome·lesson. evidence는 원문 그대로(이름 가림), evidence_found=원문 대조 결과"),
    ("case_elements", "partner_name, partner_role, partner_org_codes, partner_org_labels", "협력 기관 이름·역할·유형(OG 코드)"),
    ("case_obstacles.csv", "obstacle, obstacle_category, solution, solution_strategy, status", "사업을 하는 쪽이 부딪힌 장애와 해결. 범주 10종, 전략 9종, 상태(해결·일부 해결·진행 중·미해결)"),
    ("case_obstacles", "obstacle_evidence_masked, solution_evidence_masked", "원문 근거(이름 가림)"),
    ("features/obstacle_playbook.csv", "obstacle_category, solution_strategy, n, cases, examples", "장애물 범주 × 해결 전략 집계(어떤 문제에 어떤 방식이 통했나)"),
    ("features/welfare_worker_deployment_2025.csv", "region, name_in_book, complex_id, match_type, needs_review", "2025년 주거복지사 배치 단지 111곳. exact만 확정, candidate_similar_name은 검토 대상(OCR 오타 추정 포함), not_in_integrated_table은 통합표 밖(LH 직접 관리 등)"),
    ("features/casebook_facts.csv", "topic, item, value, unit, as_of, evidence", "영구임대 입주민 현황·사업 연혁 수치(원문 대조)"),
    ("links/case_complex.csv", "case_id, complex_id, mention, match_type, needs_review", "사례 ↔ 단지"),
    ("links/std_id_to_cards.csv", "std_id, n_cards, card_ids", "표준 프로그램 → 근거 카드 목록(추천 후보 조인용)"),
    ("chunks.jsonl / index/", "chunk_id, text, source_type=casebook, std_ids, complex_ids, similar_programs", "검색(RAG) 청크와 LSA 64차원 벡터. 뉴스(housing_welfare_news_v1)와 같은 방식이라 source_type으로 합쳐 쓸 수 있음"),
    ("casebook_programs_v1.xlsx", "시트: 근거카드·사례·프로그램·요소·장애물과해결·장애물플레이북·배치단지2025·개요수치", "코드 없이 보는 사람용 엑셀"),
]


def write_docs(out, s, pb, P, O):
    pd.DataFrame(COLUMNS, columns=["file", "column", "description"]).to_csv(os.path.join(out, "column_dictionary.csv"), index=False, encoding="utf-8-sig")
    et = s["element_types"]
    oc = s["obstacle_categories"]
    top_pb = pb.head(6)
    md = f"""# 주거복지사 활동 사례집 구조화 데이터 ({s['version']})

{s['source']}의 사례 {s['n_cases']}개를 **'복지 프로그램 실행 레시피'**로 구조화한 데이터입니다. 두 가지 쓰임을 염두에 두고 만들었습니다.

1. **추천 근거**: 추천 후보에 "비슷한 단지는 이렇게 했다"는 근거를 붙입니다(필요·대상·협력기관·운영 방법·성과). → `evidence_cards.*`, `links/std_id_to_cards.csv`
2. **시작할 때의 장애물과 해결법**: 사업을 열고 운영하며 부딪힌 문제와 푼 방법입니다(예: 지자체 자산 설치 불가, 노인일자리 파견 거부 → 설득). → `case_obstacles.csv`, `features/obstacle_playbook.csv`

- 원자료: `data/raw/expert_casebook_2025/`(OCR 통합본·PDF 사본, 수정하지 않음)
- 코드: `project/tools/casebook_nlp/` · 추출 결과(LLM, 사람 검토 가능): `project/tools/casebook_nlp/annotations/CBxx.json`
- 다시 만들기: `python -m casebook_nlp.build --raw <OCR 통합본> --ann <annotations 폴더> --out <이 폴더>`
- 만든 시각 {s['built_at']} · 자동 점검 {s['checks_pass']}/{s['checks_total']} 통과 · 근거 인용 원문 일치 {s['evidence_found']}

## 한눈에

| 항목 | 값 |
|---|---|
| 사례 | {s['n_cases']}개(주거환경·문화·공동체·돌봄·건강 각 3개, 협업 3개) |
| 프로그램(근거 카드) | {s['n_programs']}개 → 표준 프로그램 {s['n_std_with_cards']}종과 연결(확신도 {', '.join(f'{k} {v}' for k, v in s['std_confidence'].items())}) |
| 레시피 요소 | {s['n_elements']}개: {', '.join(f'{k} {v}' for k, v in et.items())} |
| 장애물과 해결 | {s['n_obstacles']}건: {', '.join(f'{k} {v}' for k, v in oc.items())} |
| 주거복지사 배치 단지(2025) | {s['n_deployment']}곳: {', '.join(f'{k} {v}' for k, v in s['deployment_match'].items())} |
| 검색 청크 | {s['n_chunks']}개 |

## 많이 나온 장애물 × 해결 전략

| 장애물 범주 | 해결 전략 | 건수 | 예 |
|---|---|---:|---|
""" + "\n".join(f"| {r['obstacle_category']} | {r['solution_strategy'] if isinstance(r['solution_strategy'], str) else '(해결 미기재)'} | {r['n']} | {str(r['examples'])[:80]} |" for _, r in top_pb.iterrows()) + f"""

## 만든 방법

```
사례집 OCR 통합본
 │ 1 분할     '[영역]'+'#지역' 표기로 사례 18개, 앞부분(입주민 현황·배치 단지 목록) 분리 — 목차로 지역·프로그램명 확인
 │ 2 추출     LLM 추출(정해진 틀: 프로그램·요소 7종·장애물/해결·요약). 모든 근거는 원문 그대로 인용하도록 지시
 │ 3 검증     근거 인용을 원문과 자동 대조(evidence_found), 범주 값 검사
 │ 4 연결     표준 프로그램(커뮤니티 NLP 규칙 엔진 + 별칭 사전 근접 합의) · 단지(정확 일치만 확정) · 대상·기관 유형(같은 사전)
 │ 5 가리기   인물 이름 → [이름](사례집은 공개 책자이나 데이터 재사용을 위해 가림)
 │ 6 산출     근거 카드 · 장애물 플레이북 · 검색 청크(LSA 64차원) · 엑셀
 ▼
processed/casebook_programs_v1/
```

## 쓰는 법

- **추천 화면**: 단지에 추천된 프로그램의 `std_id`로 `links/std_id_to_cards.csv`를 찾고, 카드의 `card_text`(또는 필요·대상·협력·운영·성과 칸)를 '비슷한 단지는 이렇게 했다'로 보여 줍니다.
- **실행 조건 검토(②연결)**: 같은 `std_id` 카드의 `obstacles_and_solutions`와 `features/obstacle_playbook.csv`로 '이 프로그램을 열 때 흔한 걸림돌과 푼 방법'을 미리 보여 줍니다.
- **협력기관 추천**: `case_elements.csv`의 partner 행(기관 유형 OG 코드)으로 '이 프로그램에 주로 함께한 기관 유형'을 제안합니다.
- **성과 지표 설계(④학습)**: outcome 행의 수치(이용 횟수·참여 인원·예산 절감 등)가 현장에서 실제로 남기는 성과 단위의 예시입니다.
- **배치 여부 특성**: `features/welfare_worker_deployment_2025.csv`로 단지별 주거복지사 배치 여부를 모델 특성에 붙일 수 있습니다(500세대 이상 영구임대 배치 기준 분석).
- **검색·LLM**: `chunks.jsonl`(+`index/`)은 뉴스 데이터와 같은 형식이라 `source_type`으로 합쳐 하나의 근거 검색에 씁니다.

## 주의

- 사례집은 우수 사례 모음이고 일부 각색이 섞여 있습니다(책 안내문). 수치는 '사례집이 기술한 값'으로 쓰고, 효과의 일반화 근거로 쓰지 않습니다.
- 장애물·요소는 LLM 추출(silver label)입니다. 모든 근거 인용은 원문과 자동 대조했고, 틀린 것은 `qa/review_queue.csv`에 남습니다. 고칠 때는 `annotations/CBxx.json`을 고치고 다시 빌드합니다.
- 배치 단지 목록의 이름이 통합표와 다르면(OCR 오타로 보이는 '마산증리1' 등) 자동으로 고치지 않고 검토 후보로 둡니다.
"""
    open(os.path.join(out, "README.md"), "w", encoding="utf-8").write(md)
