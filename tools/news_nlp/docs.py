# -*- coding: utf-8 -*-
"""README.md·column_dictionary.csv 작성(수치는 manifest에서)."""
import os

import pandas as pd

COLUMNS = [
    # file, column, 설명
    ("articles", "news_id", "기사 기본키. N+게시일(YYYYMMDD)+_+URL 해시 6자리. 같은 URL이면 다시 만들어도 같다"),
    ("articles", "source_order", "원자료(크롤링 jsonl)에서의 순서(1부터)"),
    ("articles", "date / event_date_est", "게시일 / 본문 '지난 6일'·'11월 4일' 표기로 추정한 행사일(게시일 이전 가장 가까운 날). 근거는 event_date_basis"),
    ("articles", "title / title_masked", "정제 제목(머리말 [포토뉴스] 등 제거) / 사람 이름·연락처를 가린 제목"),
    ("articles", "body_masked", "정제 본문에서 이름([이름])·전화([전화])·이메일([이메일])을 가린 것. 공유·검색·모델 입력은 이것을 쓴다"),
    ("articles(jsonl만)", "body_clean", "가리기 전 정제 본문. 내부 분석 전용(외부 공유 금지)"),
    ("articles", "relevance", "A 공단 단지 현장 활동 / B 공단 협약·지사 사업 / C 다른 공공임대 / D 지역 복지 / E 관련 낮음(규칙)"),
    ("articles", "is_partnership", "업무협약·MOU 기사면 1"),
    ("articles", "dup_cluster / dup_size / is_representative", "같은 사건을 다룬 기사 묶음, 묶음 크기, 대표 기사(가장 긴 완전 본문)면 1. 집계는 대표 기사만 센다"),
    ("articles", "primary_std_id / primary_std_name / primary_std_confidence", "가장 확실한 표준 프로그램(커뮤니티 NLP와 같은 코드)과 확신도(high·medium)"),
    ("articles", "std_ids", "중간 이상 확신도로 연결된 표준 프로그램 전부"),
    ("articles", "complex_ids / complex_ids_review", "확정 연결된 단지(complex_id) / 이름이 부분 일치해 검토가 필요한 후보"),
    ("articles", "branches / sido / sigungu", "본문에 나온 공단 지사 / 시도 / 시군구"),
    ("articles", "actor_types", "등장 주체 유형: KOHOM, LH, LOCAL_GOV, PUBLIC_CORP, WELFARE_ORG, HEALTH, COMPANY, UNIVERSITY"),
    ("articles", "target_codes / target_labels", "원문에 적힌 수혜 대상(커뮤니티 NLP 대상 사전, 직원·봉사자 제외)"),
    ("articles", "org_type_codes / org_type_labels", "협력 기관 유형(커뮤니티 NLP 기관 사전 OG01~)"),
    ("articles", "purpose_codes / need_domain_codes", "목적(P01~, 프로그램 유형 기본+원문 단서)과 필요 영역(N1~N6)"),
    ("articles", "effect_codes", "원문에 드러난 기대효과 단서(EF01~)"),
    ("articles", "vuln_codes", "본문 문장에서 찾은 취약 신호 코드(signals/vulnerability_sentences.csv에 문장 근거)"),
    ("articles", "persons_max / households_max / money_max_krw", "본문에 적힌 최대 인원·가구 수·금액(없으면 빈 값, 0이 아님)"),
    ("articles", "keywords", "Kiwi 명사 TF-IDF 상위어"),
    ("articles", "is_snippet / cut_tail / truncated", "본문이 200자 미만·요약만 / 뒤쪽 본문 잘림 의심 / 마지막 문장이 끝나지 않음"),
    ("articles", "crawl_status / reuse_status_raw / reuse_policy", "수집 상태 / 원 표기 / 재사용 정책(internal_analysis_only, kogl_type1_attribution, kogl_type2_noncommercial)"),
    ("sentences", "news_id, sent_idx, role, text, text_masked", "Kiwi 문장 분리. role = lead(첫 문장)·quote(인용 발언)·bullet·body"),
    ("chunks.jsonl", "chunk_id, text, 메타데이터", "검색(RAG)용 450자 안팎 청크(문장 1개 겹침, 가린 본문). complex_ids·std_ids·need_domains·vuln_codes·similar_programs 포함"),
    ("links/article_program", "std_id, confidence, methods, n_signals, alias_sim_max, evidence, rank", "기사↔표준 프로그램. methods: title_rule, quoted_rule, alias_knn, sentence_rule"),
    ("links/article_complex", "complex_id, complex_name, mention, match_type, confidence, needs_review", "기사↔단지. exact·numbered_base는 확정, base_only는 검토 대상"),
    ("links/article_org", "org_name", "본문에 나온 기관 이름(규칙 추출)"),
    ("signals/quantities", "kind, value, unit, approx, what, context", "인원·가구·물품·금액·횟수 표기('여'가 붙으면 approx=1)"),
    ("signals/vulnerability_sentences", "code, label, need_domain, cue, sentence", "취약 신호 문장 근거. 기사 서술의 분류이지 개인·세대 판정이 아니다"),
    ("signals/new_program_candidates", "phrase, sentence, best_alias, best_sim", "표준 사전·별칭에 없는 행사명 후보(사전 확장 검토용)"),
    ("features/program_news_evidence", "n_articles, n_high, n_kohom, community_records_30m, community_adoption_rate, targets_in_news, example_titles", "표준 프로그램별 언론 근거(대표 기사 기준)와 커뮤니티 기록 규모 비교"),
    ("features/complex_news_features", "n_articles, std_ids, vuln_codes, news_ids", "단지별 기사 수와 다뤄진 프로그램·취약 신호"),
    ("features/branch_news_features", "n_articles, std_ids", "지사별 기사 수와 프로그램"),
    ("features/vulnerability_signal_summary", "n_articles, n_sentences", "취약 신호별 기사·문장 수"),
    ("index/*", "chunk_lsa64.npy, program_lsa64.npy, *_rows.csv, chunk_program_similarity_top3.csv",
     "글자 2~4그램 TF-IDF → LSA 64차원 벡터(L2 정규화). 행 순서는 *_rows.csv. 청크마다 비슷한 표준 프로그램 상위 3개(TF-IDF 코사인)"),
]


def write_docs(out, s):
    pd.DataFrame(COLUMNS, columns=["file", "column", "description"]).to_csv(os.path.join(out, "column_dictionary.csv"), index=False, encoding="utf-8-sig")
    rel = s["relevance"]
    pc = s["program_link_confidence"]
    md = f"""# 주거복지 뉴스·보도자료 구조화 데이터 ({s['version']})

크롤링한 뉴스·보도자료 {s['n_articles']}건을 정제하고, 기존 자료(단지 통합표, 커뮤니티 NLP의 표준 프로그램)와 같은 키로 연결한 데이터입니다.
나중에 **복지 프로그램 추천**(프로그램 근거·사례), **취약도 분석**(취약 신호 문장), **의미화**(검색·요약·설명 근거)에 쓰도록 만들었습니다.

- 원자료: `data/raw/news_crawl_20261117/` (크롤링 결과 그대로, 수정하지 않음)
- 코드: `project/tools/news_nlp/` · 다시 만들기: `python -m news_nlp.build --raw <원자료 articles.jsonl> --out <이 폴더>` (같은 입력이면 같은 결과)
- 만든 시각: {s['built_at']} · 자동 점검 {s['checks_pass']}/{s['checks_total']} 통과(`qa/quality_checks.csv`)

## 한눈에

| 항목 | 값 |
|---|---|
| 기사 | {s['n_articles']}건(같은 사건 중복을 묶으면 대표 기사 {s['n_representative']}건, 2건 이상 묶음 {s['n_dup_clusters_multi']}개) |
| 관련도 | 공단 단지 현장 활동 {rel.get('A_kohom_complex_activity', 0)}건, 공단 협약·지사 사업 {rel.get('B_kohom_partnership_or_branch', 0)}건 |
| 문장 / 검색 청크 | {s['n_sentences']}문장 / {s['n_chunks']}청크 |
| 표준 프로그램 연결 | {s['n_program_links']}건(high {pc.get('high', 0)}, medium {pc.get('medium', 0)}, low {pc.get('low', 0)}) |
| 단지 연결 | 확정 {s['n_complex_links']}건 + 검토 후보 {s['n_complex_link_candidates']}건 |
| 취약 신호 문장 | {s['n_vuln_sentences']}건 |
| 새 프로그램 후보 | {s['n_new_program_candidates']}건 |
| 재사용 정책 | {', '.join(f'{k} {v}건' for k, v in s['reuse_policy'].items())} |

## 처리 구조

```
raw/news_crawl_20261117/articles.jsonl
  │ 1 정제(clean)      줄 분류(버림·사진설명·부제·목록·본문) → 제목과 가장 겹치는 본문 줄을 기준으로 본문 덩어리 확장
  │                    → 기자·언론사 표기, 저작권·메뉴·댓글, 다른 기사 목록, 해시태그 제거 / 강제 줄바꿈 복원
  │ 2 중복(dedup)      글자 3그램 TF-IDF 코사인 + 같은 날·제목 겹침 → 같은 사건 묶음, 대표 기사 1건
  │ 3 연결(link)       단지명 사전 대조(정확 일치만 확정) · 지사 · 시도/시군구 · 주체 유형 · 기관명 · 관련도 분류
  │ 4 프로그램(programs) 제목 규칙 + 따옴표 행사명 규칙 + 별칭 사전 최근접(TF-IDF kNN) + 문장 규칙 → 표준 프로그램(std_id)·확신도
  │ 5 신호(signals)    대상·기관 유형·목적·필요 영역·기대효과(커뮤니티 NLP 사전) · 수량 · 행사일 · 취약 신호 · 이름·연락처 가리기
  │ 6 색인(index)      Kiwi 문장 분리 → 450자 청크 → 글자 TF-IDF → LSA 64차원, 청크↔프로그램 유사도
  ▼
processed/housing_welfare_news_v1/
```

- 커뮤니티 NLP와 **같은 규칙 엔진·사전**(표준 프로그램 109종, 대상·기관·목적·필요 영역)을 써서, 뉴스와 단지 활동 기록이 같은 코드로 만납니다.
- 이름으로 짐작한 단지 연결은 자동 확정하지 않습니다(`complex_ids_review`, `qa/review_queue.csv`).
- 사람이 검토해 정한 내용(단지 연결 확정·거절, 별칭 추가, '프로그램 아님' 문구)은 `project/tools/news_nlp/review_decisions.csv`에 적고, 다시 만들 때마다 반영됩니다(연결 방법에 `user_confirmed`·`user_alias`로 표시).
- 확신도: 서로 다른 신호 두 개 이상이 같은 프로그램을 가리키면 high, 제목·따옴표 행사명 규칙 하나 또는 별칭 근접도 0.6 이상이면 medium, 문장 규칙만이면 low. 기사 요약 열(`std_ids`)은 medium 이상만 씁니다.

## 폴더 구성

| 경로 | 내용 |
|---|---|
| `articles.csv` / `articles.jsonl` | 기사 1행: 메타·관련도·중복 묶음·프로그램·단지·지역·대상·필요 영역·취약 신호·수량·가린 본문. jsonl에는 가리기 전 정제 본문(`body_clean`)도 있음(내부 전용) |
| `sentences.csv` | 문장 1행(역할: 첫 문장·인용·목록·본문, 가린 문장) |
| `chunks.jsonl` | 검색(RAG)용 청크와 메타데이터 |
| `links/` | 기사↔표준 프로그램, 기사↔단지, 기사↔기관 |
| `signals/` | 수량, 취약 신호 문장, 새 프로그램 후보 |
| `features/` | 프로그램별 언론 근거, 단지별·지사별 기사 특성, 취약 신호 요약 |
| `index/` | LSA 64차원 벡터(청크·프로그램)와 행 순서표, 청크별 유사 프로그램 |
| `qa/` | 자동 점검, 정제 기록(줄·글자 보존 비율), 중복 쌍, 검토 대기열 |
| `column_dictionary.csv` | 열 설명 |
| `manifest.json` / `file_checksums.json` | 요약 수치 / 파일 체크섬 |

## 활용 방법

- **프로그램 추천**: `features/program_news_evidence.csv`로 프로그램별 언론 근거(기사 수, 대상, 사례 제목)를 후보 설명에 붙입니다. `links/article_program.csv`의 사례(협력 기관·대상·인원)는 '다른 단지는 이렇게 했다'는 근거 문장이 됩니다.
- **취약도 분석**: `signals/vulnerability_sentences.csv`는 필요 영역(N1~N6)별 서술 근거입니다. 단지 연결이 있는 기사는 `features/complex_news_features.csv`로 단지 특성에 붙일 수 있습니다. 기사 서술이지 세대 판정이 아니므로 가중치가 아니라 설명 근거로 씁니다.
- **의미화·검색**: `chunks.jsonl`(+`index/`)로 질의와 비슷한 청크를 찾고 메타데이터(단지·프로그램·필요 영역)로 거릅니다. 문장 임베딩 모델을 쓸 수 있게 되면 `text`만 다시 벡터화하면 됩니다.
- **사전 확장**: `signals/new_program_candidates.csv`와 `qa/review_queue.csv`를 검토해 별칭 사전에 더합니다.

## 주의

- 기사 {s['reuse_policy'].get('internal_analysis_only', 0)}건은 이용허락 표시가 없거나 확인하지 못했습니다(`reuse_policy=internal_analysis_only`). 본문을 외부에 다시 싣지 말고, 분석 결과·요약·링크만 씁니다. 공공누리 표시 기사는 조건을 지킵니다.
- 이름 가리기는 직함 앞뒤 규칙이라 일부 일반어가 함께 가려지거나(과잉), 드물게 빠질 수 있습니다. 외부 공유 전에는 한 번 더 확인합니다.
- 프로그램·대상·취약 신호는 규칙·사전 기반 자동 판정(silver label)입니다. 수집 대상 자체가 공단 관련 기사라 관련도는 A·B에 몰려 있습니다.
- 수집 단계에서 본문 일부만 받은 기사(`is_snippet`, `truncated`)가 있습니다.
"""
    open(os.path.join(out, "README.md"), "w", encoding="utf-8").write(md)
