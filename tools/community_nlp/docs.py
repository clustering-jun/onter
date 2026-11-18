# -*- coding: utf-8 -*-
"""README·엑셀 요약본·manifest 작성."""
import datetime as dt
import os
import numpy as np
import pandas as pd

from . import taxonomy as TX
from . import package as PK
from .std_programs import TYPES

CX_CORE = ["complex_name", "supply_type", "households", "supply_group", "size_tertile", "complex_type_id", "n_records_all", "n_records_resident",
           "n_records_governance", "n_records_staff", "n_records_facility", "n_records_admin", "records_per_month", "resident_records_per_1000hh_year",
           "active_months", "active_month_ratio", "first_record_date", "last_record_date", "months_since_last_record", "n_2024", "n_2025", "n_2026h1",
           "n_recent12m", "std_richness", "std_entropy", "std_evenness", "std_effective_n", "std_top1_share", "std_top3_share", "std_top1_name", "std_top5",
           "ops_evt_Y_share", "ops_reg_YP_share", "ops_alw_YP_share", "ops_adh_YP_share", "ops_sea_YP_share", "single_day_share", "activity_count_median",
           "peak_month", "seasonality_cv", "repeat_record_share", "recurring_std_n", "hq_template_share", "participants_total_sum",
           "participation_per_100hh_year", "individual_per_100hh_year", "share_mou", "share_external_contest", "share_part_flag_welfare_org",
           "share_part_flag_local_gov", "share_part_flag_private_corp", "partner_org_type_richness", "share_partner_mentioned",
           "est_cost_mid_per_year_krw", "est_burden_mid_per_year_krw", "est_cost_mid_per_hh_year_krw", "gap_need_domain_n", "gap_need_domains",
           "peer_cf_neighbors", "summary_ko", "low_data_flag"]


def write_readme(res, out_dir, files_info):
    rows, cf, dic, cand = res["rows"], res["cf"], res["dic"], res["cand"]
    val = res.get("val_final", {})
    lines = []
    A = lines.append
    A("# 온터 커뮤니티 프로그램 NLP 구조화 데이터셋 v1 (`community_nlp_2026_v1`)")
    A("")
    meta = res.get("meta", {})
    src, upd = meta.get("src", {}), meta.get("update")
    A(f"`{src.get('name', '')}`({len(rows):,}행·{len(cf)}개 단지, 2024-01~2026-06)의 활동명·활동내용을 구조화하고, 프로그램 단위 분석 데이터·단지 집계 특성·표준 프로그램 사전·추천/LTR 후보 특성을 만들었다. "
      "원본 파일과 기존 processed 폴더는 변경하지 않았다.")
    if upd:
        A("")
        A(f"> **원본 갱신 반영**: 2026년 상반기 자료가 갱신된 최종본을 기준으로 다시 만들었다. 이전 스냅샷({upd['n_old']:,}행) 대비 값이 같은 행 {upd['identical']:,}, 수정 {upd['modified_new_rows']:,}, 추가 {upd['added']:,}, 빠짐 {upd['removed']:,}행. "
          "기존 LLM 판정은 같은 문구의 행으로 옮기고, 새로 생긴·바뀐 문구만 다시 판정했다(상세는 `분석보고서.md` §1.1).")
    A("")
    A("> **자동 구조화 초안(silver label)이다.** 규칙·사전 판정에 독립 LLM 라벨러의 판정을 결합했으며, 전문가가 독립 검토한 정답이 아니다. 참여인원은 기록 인원(고유 주민 수 아님), 예산은 모델 추정치(실제 집행액 아님), 공급 공백은 필요의 정답이 아니다.")
    A("")
    A("## 먼저 볼 파일")
    A("")
    A("| 파일 | 내용 | 단위·규모 | 사용 범위 |")
    A("|---|---|---|---|")
    A(f"| `분석보고서.md` | 방법·결과·심화 분석(5장)·품질 검증·한계 | - | 전체 개요 |")
    A(f"| `program_analysis.csv` / `.jsonl` | **프로그램(행) 단위 분석 데이터**: 표준 유형·범위·목적·대상·서비스·방식·운영 특성(5종 Y/P/N/U)·협력기관·효과·자원·참여·예산 추정·반복·중복·품질 플래그 | {len(rows):,}행 × {rows.shape[1]}열, `source_row`로 원본 연결 | 추천·분석의 기본 단위 |")
    A(f"| `complex_features.csv` / `.jsonl` | **단지별 집계 특성**: 구성·다양성·집중도·운영 패턴·월 분포·참여·협력·예산 추정·반복·공급 공백·피어 이웃·유형·잠재요인 | {len(cf)}개 단지 × {cf.shape[1]}열 | 사용자(단지) 특성, 유형화 |")
    A(f"| `standard_program_dictionary.csv` / `.jsonl` | **표준 프로그램 사전**: 정의·통상 속성·판정 규칙·채택률·계절성·참여·예산 분위·협력기관·별칭 예시·출처 행 | {len(dic[dic['std_id'] != 'Z99'])}종 + 미분류 | 아이템 특성, 후보 사전 |")
    A(f"| `complex_program_candidates.csv` | 단지×표준 프로그램 후보 특성(시행 이력·채택률·공백·계절·예산·중복·협력 적합 등) | {len(cand):,}쌍 × {cand.shape[1]}열 | LTR 입력 후보(정답 라벨 없음) |")
    A("| `complex_std_matrix_long/wide.csv` | 단지×표준 유형 시행 횟수·최근성 | 단지×유형 | 협업 필터링 |")
    A("| `complex_latent_factors.csv`, `std_latent_factors.csv`, `latent_components.csv` | NMF 잠재 요인(단지 적재·유형 구성·요인 설명) | k=8 | 밀집 특성 |")
    A("| `std_cooccurrence.csv` | 표준 유형 동시 시행(리프트·자카드) | 유형 쌍 | 보완성·묶음 |")
    A("| `alias_dictionary.csv` | 별칭 군집 → 대표 명칭·변이 예시 | 군집 | 명칭 표준화 |")
    A("| `complex_types.csv` | 단지 유형 프로파일(군집 평균·두드러진 특징) | 유형 | 단지 비교 |")
    A("| `codebook_taxonomy.csv`, `budget_assumptions.csv` | 코드북·예산 추정 가정 | - | 해석 |")
    A("| `feature_catalog.csv` | **특성 카탈로그**: 모든 열의 정의·분모·관측 기간·결측 처리·역할·버전 | 열 | 특성 사용 전 확인 |")
    A("| `validation/` | 무결성 점검·독립 LLM 일치도·혼동 쌍·강건성·유형 k 선택·원본 갱신 변경 목록(`source_update_changes.csv`) | - | 품질 근거 |")
    A("| `llm_annotations/` | 라벨러 원 응답(A·ADJ·ADJ2·ADJ3·B·C)·지침서·이전→현재 행 번호 대응(`previous_to_current_row_map.csv`) | 행 | 감사·재현 |")
    A("| `온터_커뮤니티_NLP분석_요약.xlsx` | 핵심 표 모음(사전·단지 집계·유형·코드북·검증) | 시트 | 엑셀 열람용 |")
    A("| `analysis/` | 심화 분석(5장) 계산 표: 유형 지형·월별·격차·유형 구조·참여·협력·관계·단지 여건 상관/회귀 | CSV | 분석 근거 |")
    A("| `figures/` | 보고서 그림(fig01~fig28) | PNG | - |")
    A("| `source_snapshot/` | 분석에 쓴 원본 엑셀의 사본(SHA256은 `manifest.json`과 일치) | 1파일 | 재현 |")
    A("| `manifest.json`, `file_checksums.json`, `record_schemas.json` | 출처 해시·버전·검증 집계·파일 SHA256·필드 계약 | - | 추적·검증 |")
    A("")
    A("CSV는 UTF-8 BOM이다. JSONL은 **빈 값(None·빈 문자열)을 생략**했다(없음 = 결측). 복합 필드는 `|` 구분 문자열이다. 빈 숫자 칸은 0이 아니다.")
    A("")
    A("## 핵심 키")
    A("")
    A(f"- `source_row`: 원본 엑셀 행 번호(헤더 1행, 데이터 {int(rows["source_row"].min())}~{int(rows["source_row"].max())}; 통합표에 없는 단지의 행은 빠져 번호가 이어지지 않는다). `record_id = comm_%05d`. 이전 스냅샷의 행 번호와는 다르다(대응표는 `llm_annotations/previous_to_current_row_map.csv`).")
    A(f"- `complex_id`: 단지통합표의 단지 고유 ID(예: KOH_1). `complex_name`: 단지명(통합표와 정확히 일치). {len(cf)}개. 통합표에 없는 단지는 분석에서 제외했다.")
    A("- `end_date`: 종료일이 2027년 이후이거나 시작보다 빠르면 결측(원문은 `end_date_raw`, `date_anomaly_flag=1`).")
    A("- `std_id`: 표준 프로그램 유형(`standard_program_dictionary.csv`), `alias_cluster_id`/`canonical_title`: 유형 안 별칭 군집과 대표 명칭.")
    A("- 운영 특성 열: `op_always`·`op_regular`·`op_event`·`op_adhoc`·`op_seasonal` ∈ {Y 확정, P 개연, N 반증, U 미확인} + `op_basis`(근거).")
    A("")
    A("## 빠른 사용")
    A("")
    A("```python")
    A("import pandas as pd")
    A("rows = pd.read_csv('program_analysis.csv', encoding='utf-8-sig')")
    A("resident = rows[rows['in_resident_scope'] == 1]                 # 추천 후보 범위(주민 프로그램·세대 지원)")
    A("sure = resident[resident['std_confidence'].isin(['high', 'llm-high', 'llm-medium'])]   # 확신 있는 라벨만")
    A("cx = pd.read_csv('complex_features.csv', encoding='utf-8-sig')")
    A("cand = pd.read_csv('complex_program_candidates.csv', encoding='utf-8-sig')   # LTR 후보(정답 없음)")
    A("```")
    A("")
    A("## 주의")
    A("")
    A("1. 학습·시험은 **단지 단위로 분리**하고, 채택률·피어·이웃 특성은 학습 단지에서만 산출한다(누수 방지). 관측 기간은 2024-01~2026-06이며 `n_recent12m` 등은 2025-07~2026-06 창이다.")
    A("2. `complex_adopted=0`·공급 공백(`gap_*`)은 **필요 없음·실패의 정답이 아니다**. 필요 정답은 현장 확인·전문가 등급 수집 후 별도 구축한다(연구방법론 v4·v5).")
    A("3. `target_explicit`(원문 명시)과 `target_type_default`(유형 사전의 통상 대상)을 구분해 쓴다. 효과·자원·제공 방식도 `*_explicit`과 `*_type_default`가 분리되어 있다.")
    A("4. `est_*` 열은 **모델 추정치**다(`budget_assumptions.csv`). '기타'로 기재된 소요비용분류·예산주체를 0원으로 해석하지 않는다.")
    A("5. 참여 규모는 기록 인원이다. 같은 주민의 반복 참여·관리소·기관 인원이 포함되고, 활동횟수가 복수일 때 합산인지 회당인지 알 수 없다.")
    A("6. 동·호수·이름 패턴이 있어 마스킹이 원문을 바꾼 기록은 `sensitive_identifier_flag=1`이며 `*_masked` 열(활동명·활동내용·장소명)을 쓴다. 마스킹은 규칙 기반이라 별표 없이 적힌 직함 붙은 실명 등은 남을 수 있으므로 외부 공유 전에 확인한다.")
    A("7. 기록 15건 미만 단지(`low_data_flag=1`)는 집계가 불안정해 유형화에서 제외했다. 후보 표(`complex_program_candidates.csv`)에는 `low_data_complex=1`로 표시해 남겼으므로 학습·추천에서 뺄지는 사용자가 정한다.")
    A("8. 지원 대상·효과·자원의 `*_explicit`과 협력기관 `partner_org_codes`는 원문 근거가 있는 행에만 값이 있다(없으면 빈 값). 빈 값을 0이나 '해당 없음'으로 읽지 않는다.")
    A("")
    if val:
        name, v = list(val.items())[0]
        A("## 품질 요약")
        A("")
        A(f"- 전수 자동 점검 {len(res['qa'])}건 중 PASS {int((res['qa']['status'] == 'PASS').sum())}건(상세 `validation/qa_checks.csv`).")
        A(f"- 독립 LLM 일치도(`{name}`, {v['n']}행): 범위 {v['scope_acc'] * 100:.0f}%, 표준 유형 {v['std_acc_valid'] * 100:.0f}%, 유형 가족 {v['family_acc_valid'] * 100:.0f}%, 주 목적 {v['purpose_primary_acc'] * 100:.0f}%.")
        vc = [(k, x) for k, x in val.items() if k.startswith("C(")]
        if vc:
            k2, x2 = vc[0]
            A(f"- 갱신분 점검(`{k2}`, {x2['n']}행; 규칙 high 확신 층): 범위 {x2['scope_acc'] * 100:.0f}%, 표준 유형 {x2['std_acc_valid'] * 100:.0f}%, 유형 가족 {x2['family_acc_valid'] * 100:.0f}% 일치. LLM 판정을 거치지 않은 층이라 B와 구성이 다르다(보고서 §6.2).")
        A("- 규칙 판정이 불확실하거나 중간 확신인 문구는 LLM 판정으로 확정했고(`label_source=llm`), high 확신 규칙 라벨은 유지했다. LLM이 Z99(내용 불명)로 답한 문구는 미분류(Z99)로 확정했고, NEW(맞는 유형 없음)로 답한 문구는 규칙 라벨이 high가 아니면 임시 라벨과 함께 `needs_llm_review=1`로 표시해 사람 검토 대상으로 남겼다.")
        A("")
    A("## 버전·재현")
    A("")
    A("- 코드: `project/tools/community_nlp/`. `project/tools`에서 `python -m community_nlp.build_final --raw <원본.xlsx> --ann <llm_annotations 폴더> --out <출력 폴더> --integrated <단지통합.xlsx>`로 다시 만든다(자세한 방법은 `분석보고서.md` §7). 원본 xlsx의 SHA256은 `manifest.json`.")
    A("- 버전: taxonomy_v1.0 · std_programs_v1.0(표준 유형 %d종) · budget_assumptions_v1.0 · 라벨러 지침 v1.0(A)/v1.1(ADJ·B)/v1.2(ADJ2·ADJ3·C)." % len(TYPES))
    A("- 라벨러는 규칙 결과를 보지 못했고(블라인드), 판정 원문은 `llm_annotations/`에 보존했다.")
    A("")
    A(f"생성일 {dt.date.today().isoformat()}")
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_excel(res, out_dir):
    rows, cf, dic = res["rows"], res["cf"], res["dic"]
    sheets = {}
    dcols = ["std_id", "std_name", "std_family_label", "scope_label", "recommendable", "purpose_primary_label", "purpose_all", "need_domains_def",
             "target_default", "service_default", "mode_default", "ops_typical", "season_tag", "definition_ko", "n_records", "n_complexes", "adoption_rate",
             "n_recent12m", "month_peak", "seasonality_cv", "op_evt_Y_share", "op_reg_YP_share", "op_sea_YP_share", "participants_total_median",
             "est_cost_mid_median_krw", "est_cost_mid_p10_krw", "est_cost_mid_p90_krw", "partner_org_top3", "target_explicit_top3", "alias_examples",
             "example_source_rows", "keyword_rule"]
    sheets["표준프로그램사전"] = dic[[c for c in dcols if c in dic.columns]]
    sheets["단지별집계_핵심"] = cf[[c for c in CX_CORE if c in cf.columns]]
    sheets["단지유형"] = res["tinfo"]["profile"].reset_index()
    sheets["잠재요인"] = res["comp"]
    sheets["공급공백_단지"] = cf[["complex_name", "households", "n_records_resident", "gap_need_domain_n", "gap_need_domains"] +
                              [f"need_N{i}_per_1000hh_year" for i in range(1, 7)] + [f"need_N{i}_peer_pctile" for i in range(1, 7)]]
    from .run_pipeline import codebook_frame
    sheets["코드북"] = codebook_frame()
    sheets["예산가정"] = pd.read_csv(os.path.join(out_dir, "budget_assumptions.csv"), encoding="utf-8-sig")
    vs = os.path.join(out_dir, "validation", "llm_validation_summary.csv")
    if os.path.exists(vs):
        sheets["검증요약"] = pd.read_csv(vs, encoding="utf-8-sig")
    sheets["품질점검"] = res["qa"]
    cat = res.get("catalog")
    if cat is not None:
        sheets["특성카탈로그"] = cat[["level", "feature", "role", "definition", "unit_denominator", "window", "missing_handling", "dtype", "non_null_rate"]]
    PK.write_xlsx(os.path.join(out_dir, "온터_커뮤니티_NLP분석_요약.xlsx"), sheets)
