# -*- coding: utf-8 -*-
"""분석 보고서(Markdown)와 README 작성. 모든 수치는 res(최종 산출 결과)에서 계산한다."""
import datetime as dt
import numpy as np
import pandas as pd

from . import taxonomy as TX
from . import budget as BG
from .std_programs import TYPES, BY_ID
from . import report_extra as RX
from .report import md_table, pct, validation_tables, conf_strata_table, ops_kappa_table, dictionary_summary

OPS_LABEL = {"op_always": "상시형", "op_regular": "정기형", "op_event": "행사형", "op_adhoc": "수시형", "op_seasonal": "계절형"}


def facts(res):
    rows, cf, dic = res["rows"], res["cf"], res["dic"]
    resid = rows[rows["in_resident_scope"] == 1]
    f = {}
    f["n_rows"] = len(rows)
    f["n_complex"] = rows["complex_name"].nunique()
    f["n_resid"] = len(resid)
    f["scope"] = rows["scope"].value_counts()
    f["label_source"] = rows["label_source"].value_counts()
    f["conf"] = rows["std_confidence"].value_counts()
    f["z99"] = int((rows["std_id"] == "Z99").sum())
    f["n_std_used"] = int((dic[(dic["std_id"] != "Z99")]["n_records"] > 0).sum())
    f["fam"] = (resid["std_family_label"].value_counts(normalize=True) * 100)
    f["top_std"] = dic[dic["std_id"] != "Z99"].sort_values("n_records", ascending=False).head(12)
    f["ops_state"] = {OPS_LABEL[c]: resid[c].value_counts(normalize=True).reindex(["Y", "P", "N", "U"], fill_value=0) * 100 for c in OPS_LABEL}
    f["single_day"] = float(rows["single_day_flag"].mean())
    f["part_sum"] = int(rows["participants_total"].sum())
    f["alias_clusters"] = int(rows["alias_cluster_id"].nunique())
    f["raw_titles"] = int(rows["program_name_raw"].nunique())
    f["title_norm"] = int(rows["title_norm"].nunique())
    return f


def fmt_series_pct(s, n=5):
    return ", ".join(f"{k} {v:.1f}%" for k, v in s.head(n).items())


def build_report(res, out_path, figs_rel=None, extra=None):
    rows, cf, dic, cand, qa, robust = res["rows"], res["cf"], res["dic"], res["cand"], res["qa"], res["robust"]
    tinfo, linfo, comp, co = res["tinfo"], res["linfo"], res["comp"], res["co"]
    val = res.get("val", {})
    final_val = res.get("val_final", {})
    F = facts(res)
    resid = rows[rows["in_resident_scope"] == 1]
    meta = res.get("meta", {})
    src, upd, li = meta.get("src", {}), meta.get("update"), meta.get("label_info", {})
    lab_n = li.get("n_labels_transferred") or li.get("n_labels_old") or {}
    nA, nB = int(lab_n.get("A", 0)), int(lab_n.get("B", 0))
    L = []
    A = L.append
    today = dt.date.today().isoformat()

    A("# 임대주택 주거복지 커뮤니티 활동 NLP 구조화·Feature Engineering 분석 보고서")
    A("")
    A(f"- 데이터셋 버전: `community_nlp_2026_v1` · 작성일 {today} · 분석 대상: `{src.get('name', '')}` 원본 {int(meta.get('scope', {}).get('n_source_rows', F['n_rows'])):,}행 중 단지통합표에 있는 단지의 {F['n_rows']:,}행({len(cf)}개 단지)")
    A("- 분석 성격: 규칙·사전 기반 구조화에 **독립 LLM 라벨러의 판정**을 결합한 **자동 구조화 초안(silver label)**. 전문가 검토 전에는 학습 정답이 아니다.")
    A("- 원본 파일·기존 processed 폴더는 변경하지 않았다. 모든 행은 `source_row`(엑셀 행 번호)로 원본과 연결된다.")
    A("")
    A("## 0. 한눈에 보기")
    A("")
    sc = F["scope"]
    ls = F["label_source"]
    shr = lambda col: float((rows[col].astype(str) != "").mean() * 100)
    A(f"- **전수 처리**: {F['n_rows']:,}행 전부에 표준 프로그램 유형·범위·목적·운영 특성(5종×Y/P/N/U)·예산 추정을 부여했다. 지원 대상·기대 효과·필요 자원·협력기관은 원문에 근거가 있을 때만 명시값을 두었다"
      f"(명시 대상 {shr('target_explicit'):.0f}%·명시 효과 {shr('effect_explicit'):.0f}%·명시 자원 {shr('resource_explicit'):.0f}%·협력기관 언급 {shr('partner_org_codes'):.0f}%의 행). "
      f"명시값이 없는 행은 유형 사전의 통상값(추정; 통상 대상 {shr('target_type_default'):.0f}%)을 따로 저장해 명시값과 섞지 않았다(위 비율은 전체 행 기준). 미분류(Z99)는 {F['z99']:,}행({F['z99'] / F['n_rows'] * 100:.1f}%)이며 이 중 주 목적이 빈 행이 {int((rows['purpose_primary'].astype(str) == '').sum())}행이다.")
    A(f"- **표준화**: 원본 프로그램명 {F['raw_titles']:,}종 → 연·월·차수·단지명을 제거한 정규화 제목 {F['title_norm']:,}종 → 별칭 군집 {F['alias_clusters']:,}개 → **표준 프로그램 유형 {F['n_std_used']}종(16개 가족)**.")
    A(f"- **기록의 성격**: 주민 대상 프로그램·세대 지원은 {int(sc.get('PROGRAM', 0) + sc.get('HOUSEHOLD_SUPPORT', 0)):,}행({(sc.get('PROGRAM', 0) + sc.get('HOUSEHOLD_SUPPORT', 0)) / F['n_rows'] * 100:.1f}%)이고, "
      f"회의·위원회 {int(sc.get('GOVERNANCE', 0)):,}행, 직원 대상 {int(sc.get('STAFF', 0)):,}행, 시설 관리 {int(sc.get('FACILITY_MGMT', 0)):,}행, 행정 {int(sc.get('ADMIN', 0)):,}행은 추천 후보에서 분리했다.")
    A(f"- **라벨 출처**: 규칙 확정 {int(ls.get('rule', 0)):,}행(이 중 LLM이 맞는 유형이 없다고 답해 임시 라벨로 두고 `needs_llm_review=1`로 표시한 행 {int((rows['needs_llm_review'] == 1).sum())}행 포함), 독립 LLM 판정 확정 {int(ls.get('llm', 0)):,}행(규칙이 불확실하거나 중간 확신인 문구와 같은 텍스트 행).")
    A(f"- **주민 대상 활동의 구성**: 가족별 비중은 {fmt_series_pct(F['fam'], 5)} 순이다(최대 가족 {F['fam'].iloc[0]:.0f}%).")
    es = F["ops_state"]
    top_op = max(es, key=lambda k: es[k]["Y"] + es[k]["P"])
    A(f"- **운영 특성**(주민 대상 {F['n_resid']:,}행 기준): " + ", ".join(f"{k} 확정(Y) {es[k]['Y']:.1f}%·개연(P) {es[k]['P']:.1f}%" for k in ["행사형", "정기형", "상시형", "수시형", "계절형"])
      + f"(Y·P 합이 가장 큰 특성은 {top_op}). 당일 기록이 {F['single_day'] * 100:.0f}%라 '기록 단위'와 '프로그램의 운영 방식'을 분리해 저장했다.")
    if final_val:
        fv = validation_tables(final_val)
        r0 = fv.iloc[0]
        A(f"- **독립 검증(B, 최종 라벨 vs 독립 LLM 라벨러 {int(r0['행 수'])}행)**: 범위 {pct(r0['범위(scope) 일치'], 0)}(추천 후보인 주민 대상 여부만 보면 {pct(r0['주민 대상 여부 일치'], 0)}), 표준 유형 {pct(r0['표준 유형 일치'], 0)}, 유형 가족 {pct(r0['유형 가족 일치'], 0)}, 주 목적 {pct(r0['주 목적 일치'], 0)} 일치.")
        rc = fv[fv["표본"].str.startswith("C(")]
        if len(rc):
            r1 = rc.iloc[0]
            A(f"- **갱신분 점검(C, 갱신 반영 시점의 새·변경 문구 중 규칙 high 확신 {int(r1['행 수'])}행)**: 범위 {pct(r1['범위(scope) 일치'], 0)}, 표준 유형 {pct(r1['표준 유형 일치'], 0)}, 유형 가족 {pct(r1['유형 가족 일치'], 0)} 일치(규칙이 high 확신으로 확정해 LLM 판정을 거치지 않은 층이라 B와 구성이 다르다. §6.2).")
    A(f"- **단지 집계**: 단지 {len(cf)}개 × 특성 {cf.shape[1]}개, 표준 프로그램 사전 {len(dic[dic['std_id'] != 'Z99'])}종 × {dic.shape[1]}개 속성, 단지×프로그램 후보 {len(cand):,}쌍 × {cand.shape[1]}개 특성(LTR 입력 후보).")
    A("- **주의**: 참여인원은 기록 인원이며 고유 주민 수가 아니다. 예산은 **모델 추정치**이며 실제 집행액이 아니다. 시행하지 않았다는 사실은 필요 없음의 근거가 아니다. 공급 공백은 필요의 정답이 아니라 공급 신호다.")
    A("")

    # ── 1. 자료 ──
    A("## 1. 자료와 분석 단위")
    A("")
    A("| 항목 | 내용 |")
    A("|---|---|")
    A(f"| 원본 | `{src.get('name', '')}`(시트 `{meta.get('sheet', '')}`) {int(meta.get('scope', {}).get('n_source_rows', F['n_rows'])):,}행 중 통합표에 있는 단지의 {F['n_rows']:,}행 × {meta.get('n_cols', 29)}열, SHA256 `{str(src.get('sha256', ''))[:16]}…`(전체 해시는 `manifest.json`) |")
    A(f"| 단지 | 단지명 {F['n_complex']}개(단지명이 공급유형·세대수와 1:1). 단지당 기록 중앙값 {int(cf['n_records_all'].median())}건(최소 {int(cf['n_records_all'].min())}~최대 {int(cf['n_records_all'].max())}) |")
    A(f"| 기간 | 시작일 {rows['start_date'].min()} ~ {rows['start_date'].max()}(2024-01~2026-06, 30개월). 당일 기록 {F['single_day'] * 100:.1f}% |")
    A(f"| 텍스트 | 활동명 평균 {rows['name_len'].mean():.1f}자, 활동내용 평균 {rows['content_len'].mean():.1f}자(짧은 행정 기록체) |")
    dup_extra = int(rows["dup_exact_flag"].sum() - rows["dup_exact_first_flag"].where(rows["dup_exact_flag"] == 1, 0).sum())
    A(f"| 이상치 | 종료일 이상 {int(rows['date_anomaly_flag'].sum())}건(2027년 이후이거나 시작일보다 빠른 값, 9999 등; `end_date`는 결측 처리하고 원문은 `end_date_raw`에 보존), 활동횟수 0회 {int(rows['activity_count_zero_flag'].sum())}건, "
      f"참여 계≠세부합 {int(rows['participants_total_mismatch_flag'].sum())}건, 완전 중복 추가 행 {dup_extra}건 — 행은 삭제하지 않고 플래그 |")
    A(f"| 개인정보 | 동·호수/이름 패턴이 포함된 {int(rows['sensitive_identifier_flag'].sum()):,}건은 마스킹본(`*_masked`)을 별도 제공 |")
    A("")
    if upd:
        ref = meta.get("ref", {})
        A("### 1.1 원본 갱신 내역과 라벨 이월")
        A("")
        A(f"2026년 상반기 자료가 갱신되어 이 데이터셋은 갱신본(`{src.get('name', '')}`)을 기준으로 다시 만들었다. 이전 스냅샷(`{ref.get('name', '')}`, {upd['n_old']:,}행)과 같은 열 구성에서 "
          f"`참여인원_공기업(한국주택토지공사제외)`의 열 이름 오타만 바로잡아(`한국토지주택공사제외`) 같은 이름으로 맞췄다.")
        A("")
        A("| 구분 | 행 수 | 비고 |")
        A("|---|---|---|")
        A(f"| 이전 스냅샷 | {upd['n_old']:,} | 시작연도별 {', '.join(f'{k} {v:,}' for k, v in upd['by_year_old'].items())} |")
        A(f"| 갱신본 | {upd['n_new']:,} | 시작연도별 {', '.join(f'{k} {v:,}' for k, v in upd['by_year_new'].items())} |")
        A(f"| 값이 완전히 같은 행 | {upd['identical']:,} | 두 파일의 모든 열이 같음(완전 중복 행은 공통 개수만큼만 계산) |")
        A(f"| 수정된 행 | 이전 {upd['modified_old_rows']:,} ↔ 갱신 {upd['modified_new_rows']:,} | 단지·활동명·시작일이 같고 다른 열이 바뀜(아래 열별 건수) |")
        A(f"| 추가된 행 | {upd['added']:,} | 시작연도별 {', '.join(f'{k} {v:,}' for k, v in upd['added_by_year'].items())} |")
        A(f"| 빠진 행 | {upd['removed']:,} | 시작연도별 {', '.join(f'{k} {v:,}' for k, v in upd['removed_by_year'].items())} |")
        A("")
        A(f"수정 행({upd['modified']:,}쌍; 단지·활동명·시작일로 짝지음)에서 값이 바뀐 열(건수): " + ", ".join(f"{k} {v:,}" for k, v in upd["changed_fields"].items()) + ". "
          "참여인원·기관 수 같은 숫자 열의 정정이 많고, 문구가 바뀐 행은 규칙 엔진을 다시 적용한 뒤 규칙이 불확실하거나 중간 확신이면 새 LLM 판정으로 확정했다. "
          "참여인원의 정정은 **새 활동이 늘었다는 뜻이 아니므로** 갱신 전후의 합을 시계열 증가로 읽지 않는다.")
        if upd.get("new_complexes") or upd.get("removed_complexes"):
            A(f"단지 구성 변화: 추가 {len(upd['new_complexes'])}개, 빠짐 {len(upd['removed_complexes'])}개.")
        else:
            A(f"단지(통합표에 없어 분석에서 뺀 단지 포함)는 이전과 같은 {upd['n_complex_new']}개이며 추가·삭제된 단지는 없다.")
        A("")
        tr = li.get("transfer") or {}
        old_n, new_n = li.get("n_labels_old", {}), li.get("n_labels_transferred", {})
        if tr:
            A(f"**LLM 라벨 이월**: 라벨러가 읽은 단위는 `정규화 제목 + 마스킹 활동내용`(텍스트 키)이다. 이전 스냅샷의 {tr['이전 원본 행']:,}행 중 {tr['갱신 원본에서 같은 문구로 찾은 행']:,}행이 갱신본에서 같은 문구로 확인되어 "
              f"기존 판정(A {old_n.get('A', 0):,}→{new_n.get('A', 0):,}, ADJ {old_n.get('ADJ', 0):,}→{new_n.get('ADJ', 0):,}, ADJ2 {old_n.get('ADJ2', 0):,}→{new_n.get('ADJ2', 0):,}, B {old_n.get('B', 0):,}→{new_n.get('B', 0):,}건)을 그대로 옮겼다. "
              "문구가 바뀌었거나 새로 생긴 행은 옮기지 않고 규칙 엔진과 새 LLM 판정(ADJ3)으로 다시 처리했다. 행 번호 대응은 `llm_annotations/previous_to_current_row_map.csv`.")
            A("")
            A("갱신본에는 제공 기관이 동·호수를 일부만 가린 표기(`5**동 2**호`, `3** 1***`)가 늘었다. 같은 활동이 표기만 달라 새 문구로 취급되는 일을 줄이려고, 이 표기도 `[동호]`로 통일하는 마스킹 규칙을 보강했다"
              "(이전·갱신 텍스트에 같은 규칙을 적용해 키를 만든다). 변경 목록은 `validation/source_update_changes.csv`.")
            A("")
    A("세 가지 단위를 구분한다(연구방법론 v5). **실행 레코드**는 특정 단지·시기의 기록 한 행, **표준 프로그램**은 목적·대상·제공 방식이 같은 지원의 유형, **실행안**은 유형에 기간·횟수·기관·비용을 붙인 구체 제안이다. 이 데이터셋은 앞의 둘을 다루며 실행안의 비용·인력은 추정치로만 제공한다.")
    A("")

    # ── 2. 방법 ──
    A("## 2. 분석 방법")
    A("")
    A("### 2.1 파이프라인")
    A("")
    A("```")
    A("원본 xlsx ─ ① 텍스트 정규화(compact, 우산 사업명 마스킹, 식별정보 마스킹)")
    A(f"          ─ ② 규칙·사전 판정(표준 유형 {len(TYPES)}종, 근거 문자열·점수·확신 기록)")
    A("          ─ ③ 독립 LLM 판정(규칙이 불확실하거나 중간 확신인 문구 → 블라인드 라벨러가 원문을 읽고 유형·범위·목적·대상 판정)")
    A("          ─ ④ 하위 속성 재계산(목적·대상·서비스·방식·운영특성·협력기관·효과·자원·예산)")
    A("          ─ ⑤ 별칭 군집·반복·중복 → 표준 프로그램 사전")
    A("          ─ ⑥ 단지 집계(구성·다양성·운영·참여·협력·반복·공백) → 유형화·잠재요인·후보 특성")
    A("          ─ ⑦ 품질 검증(무결성·도메인·논리·집계 대사·강건성·독립 LLM 일치도)")
    A("```")
    A("")
    A("### 2.2 분류체계(코드북 `codebook_taxonomy.csv`)")
    A("")
    A("| 차원 | 코드 수 | 설명 |")
    A("|---|---|---|")
    A(f"| 기록 범위(scope) | {len(TX.SCOPES)} | 주민 프로그램 / 세대 직접 지원 / 거버넌스 / 직원 / 시설 관리 / 행정. 앞의 둘만 추천 후보 |")
    A(f"| 표준 프로그램 | {len(TYPES)} + Z99 | 16개 가족. 유형 판정은 '무엇을 제공하는가(핵심 서비스)'를 기준으로 하고 고독사 예방·ESG·마을공동체 같은 주제·사업명은 목적/사업 계열로 둔다 |")
    A(f"| 복지 목적 | {len(TX.PURPOSES)} | 건강·정신건강·돌봄·식생활·경제·일자리·교육·여가·공동체·주거환경·안전·환경·갈등·정보연계·참여·행정. v4 필요 분야 6개(안부와 관계/생활과 경제/건강과 돌봄/주거환경과 생활안전/문화와 활동/일자리와 학습)로 매핑 |")
    A(f"| 지원 대상 | {len(TX.TARGETS)} | **원문 명시**와 **유형 사전의 통상 대상(추정)**을 분리 저장 |")
    A(f"| 제공 서비스·방식 | {len(TX.SERVICES)}·{len(TX.MODES)} | 정보 안내·기관 연계는 분야가 아니라 공통 제공 방식 태그(v4) |")
    A(f"| 지원 단위 | 3 | 단지 전체 활동 / 일부 가구 직접 지원 / 안부·관계 접촉(상호 배타적이지 않음) |")
    A(f"| 운영 특성 | 5×4상태 | 상시·정기·행사·수시·계절, 각각 Y 확정 / P 개연 / N 반증 / U 미확인 |")
    A(f"| 기대 효과·필요 자원·협력기관 | {len(TX.EFFECTS)}·{len(TX.RESOURCES)}·{len(TX.ORGS)} | 원문 단서와 유형 정의(추정)를 분리. 기관 이름을 만들어 내지 않고 원문에 언급된 유형만 기록 |")
    A("")
    A("### 2.3 규칙 엔진 + 독립 LLM 판정")
    A("")
    A("1. **규칙 엔진**: 유형별 정규식(명칭·내용·주제어·제외 패턴), 명확도(H/M/L)에 따른 가중(명칭 3/2/1, 내용 1/0.7/0.3), 우선순위로 점수를 매겨 1순위를 정하고 2순위와의 점수차로 확신(high/medium/low)을 둔다. "
      "근거 문자열과 필드(명칭/내용)를 남기고, 우산 사업명(공동체활성화·특화사업·외부자원 등)은 가려서 판정한다.")
    A("2. **독립 LLM 라벨러**: 규칙 결과를 보지 못한 별도 에이전트가 활동명+활동내용(+기간·횟수)을 읽고 같은 코드북으로 판정한다(스크립트·키워드 자동 분류 금지, 근거 25자 기재). "
      "라벨러 지침서(`guideline*.md`)는 버전별로 `llm_annotations/`에 보존했다(v1.0·v1.1은 표준 유형 104종, v1.2는 라벨러의 NEW 제안을 반영해 4종을 더한 108종).")
    A("3. **사용 정책**: 규칙이 불확실하거나(미매칭·낮은 확신·문맥 규칙 적용·경쟁 유형 근접) 중간 확신인 문구는 같은 텍스트의 모든 행에 대해 LLM 판정을 최종 라벨로 확정(`label_source=llm`)하고, "
      "high 확신 문구는 규칙 라벨을 유지하되 LLM 판정이 있으면 감사용 열로만 보존한다. LLM이 Z99(내용만으로 유형을 알 수 없음)라고 답한 문구는 미분류(Z99)로 확정한다. "
      "NEW(목록에 맞는 유형 없음)라고 답한 문구는 새 유형 코드가 없으므로 규칙 라벨이 high 확신이면 그대로 두고, "
      "아니면 규칙 라벨을 임시로 둔 채 `needs_llm_review=1`(`review_reason`에 llm_no_matching_type)로 사람 검토 대상으로 표시한다. "
      "운영 특성·협력기관·예산은 LLM이 아니라 규칙 기반으로 산출한다(근거가 투명하고 재현 가능).")
    A(f"4. **독립 검증**: ① A 표본(무작위 {nA}행)으로 규칙을 개발·보정하고, ② 규칙이 불확실하거나 중간 확신인 행을 LLM이 판정한 뒤, ③ A와 겹치지 않는 B 표본(무작위 {nB}행)을 다른 라벨러가 다시 판정해 최종 라벨과 비교했다. "
      "④ 갱신본 반영 시점에 새로 생기거나 바뀐 문구로 분류된 것 중 규칙이 high 확신으로 확정한 문구 전수(문구당 대표 1행, C 표본)를 독립 라벨러가 다시 판정해, 갱신분에도 같은 규칙이 유지되는지 점검했다"
      + (f"(이후 마스킹 규칙을 보강하면서 C {meta['c_info']['n']}행 중 {meta['c_info']['n_same_text_as_previous']}행은 이전 파일과 같은 문구로 확인되었다)" if meta.get("c_info", {}).get("n_same_text_as_previous") is not None else "")
      + "(§6).")
    partial = [b for lst in meta.get("batch_completion", {}).values() for b in lst if b["n_output"] < b["n_input"]]
    if partial:
        A("5. **중단된 배치**: " + ", ".join(f"{b['batch']}(입력 {b['n_input']}행 중 {b['n_output']}행 산출)" for b in partial)
          + ". 라벨러가 중간에 중단되어 산출된 행만 사용했고, 아직 판정이 없는 대표 문구는 갱신본 기준으로 다시 만든 배치(ADJ3)에서 판정했다.")
    A("")
    A("### 2.4 운영 특성 판정 규칙")
    A("")
    A("| 특성 | Y 확정 | P 개연 | N 반증 | U 미확인 |")
    A("|---|---|---|---|---|")
    A("| 상시형 | 상시·연중·상설·항시 등 원문 명시 | 상설 시설·수거함·공유냉장고 유형이면서 기간 14일 이상 또는 운영 단서 | 당일 기록, 기간 2일 이하, 기간 한정 행사 | 그 외 |")
    A("| 정기형 | 매주·매월·월 N회·격주·정기·분기별 등 주기 명시 | N차·회차·상/하반기 표기, 3회 이상이 14일 이상, 단지 내 같은 제목이 월 단위 간격(≤100일)으로 3회·3개월 이상 반복, 유형 관행+복수 회차 | 당일·1회 기록이고 주기 단서가 없음 | 그 외 |")
    A("| 행사형 | 행사·잔치·축제·대회·공연·캠페인·설명회·체험 등이고 기간 7일 이하 | 행사 단어이나 기간이 길거나, 행사 성격 유형의 단기 기록 | 회의·시설·행정 범위, 상시·정기 단서만 있고 행사 단어 없음, 행사 성격이 아닌 서비스 유형 | 그 외 |")
    A("| 수시형 | 수시·요청 시·신청 세대·민원 발생·긴급지원 등 | 성격상 수시인 유형(병원동행·사례관리·주거비 지원·집수리·갈등조정 등) | 당일·계획된 일정 활동 | 그 외 |")
    A("| 계절형 | 명절·폭염·한파·김장·복날·봄꽃·방학 등 원문 단서 | 기념일(어버이날·지구의 날 등), 유형 계절성+해당 월, 예초·모종·방역 등 계절 작업 | 계절 단서 없음(원문 10자 이상, 유형 계절성 없음) | 정보 부족 |")
    A("")
    A("- 날짜가 특정 월이라는 사실만으로 계절형으로 보지 않고, **기간이 길다는 이유만으로 상시형으로 보지 않으며, 기록 건수만으로 고정 주기를 확정하지 않는다.** 12-31 일괄 종료일은 행정 관행으로 보고 기간 근거에서 제외한다.")
    A("- 운영 특성은 **표준 유형의 통상 방식**(`op_type_prior`)과 **해당 기록의 실제 일정·원문 근거**(`op_basis`)를 분리해 저장한다.")
    A("")
    A("### 2.5 예산 추정(가상, 모델 가정)")
    A("")
    A(f"원자료에는 금액이 없고 '기타'가 소요비용분류 {(rows['cost_class_raw'] == '기타').mean() * 100:.0f}%·예산주체 {(rows['budget_subject_raw'] == '기타').mean() * 100:.0f}%(전체 {F['n_rows']:,}행 기준)이므로 **0원으로 바꾸지 않고**, 프로그램 내용과 운영 규모로 건당 직접 운영비 범위를 추정했다.")
    A("")
    A("> 건당 운영비(시장가) = (고정비 + 단가 × 유효 참여인원) × 회차계수. 유효 참여인원은 개인 참여 > 계−관리소 > 계 > 유형 기본값 순. 회차계수는 교실·식사·방문·상설 운영(월)만 적용(최대 60). "
      "단지 부담 추정 = 시장가 × 부담계수(소요비용 기재 1.0 / 불명 0.5 / 외부 제공 추정 0.15).")
    A("")
    A(md_table(BG_frame(), None))
    A("")

    # ── 3. 결과 ──
    A("## 3. 프로그램 분석 결과")
    A("")
    A("### 3.1 표준 프로그램 구성")
    A("")
    if figs_rel and "fig01" in figs_rel:
        A(f"![표준 프로그램 가족별 비중]({figs_rel['fig01']})")
        A("")
    top = F["top_std"][["std_id", "std_name", "n_records", "n_complexes", "adoption_rate"]].copy()
    top["adoption_rate"] = top["adoption_rate"].map(lambda x: f"{x * 100:.0f}%")
    top.columns = ["ID", "표준 프로그램", "기록 수", "시행 단지", f"채택률({len(cf)}개 단지 중)"]
    A("**기록 수 상위 12개 표준 프로그램**")
    A("")
    A(md_table(top))
    A("")
    A(f"전체 사전은 `standard_program_dictionary.csv`(정의·통상 속성·판정 규칙·통계·별칭 예시·출처 행)에 있다. 별칭 군집 `alias_dictionary.csv`는 같은 유형 안에서 표현만 다른 활동을 하나의 대표 명칭으로 묶었다.")
    A("")
    A("### 3.2 운영 특성")
    A("")
    A(f"이 절의 비율·근거 건수는 모두 **주민 대상 기록 {F['n_resid']:,}행** 기준이다(전체 행 기준 값은 `program_analysis.csv`로 다시 계산할 수 있다).")
    A("")
    if figs_rel and "fig02" in figs_rel:
        A(f"![운영 특성 상태 구성]({figs_rel['fig02']})")
        A("")
    st_tbl = pd.DataFrame({k: v for k, v in F["ops_state"].items()}).T
    st_tbl.columns = ["Y 확정(%)", "P 개연(%)", "N 반증(%)", "U 미확인(%)"]
    st_tbl = st_tbl.reset_index().rename(columns={"index": "운영 특성"})
    A(md_table(st_tbl, {c: "{:.1f}" for c in st_tbl.columns if c != "운영 특성"}))
    A("")
    prim = resid["op_primary"].replace("", "미확인").map({"REG": "정기형", "ALW": "상시형", "ADH": "수시형", "EVT": "행사형", "SEA": "계절형"}).fillna("미확인").value_counts(normalize=True) * 100
    A("주된 운영 유형(정기>상시>수시>행사>계절 순으로 Y를 우선, 없으면 P): " + ", ".join(f"{k} {v:.1f}%" for k, v in prim.items()) + ".")
    reg_basis = resid.loc[resid["op_regular"].isin(["Y", "P"]), "op_basis"].str.extract(r"REG:([a-z_]+)")[0].value_counts()
    A("정기형 Y·P의 근거: " + ", ".join(f"{k} {v:,}건" for k, v in reg_basis.items()) + " (repeat=같은 단지·제목의 월 단위 반복 기록, series=N차 표기, period_label=상·하반기·분기, date_count=일정·횟수, type_prior=유형 관행+복수 회차, text=주기 명시).")
    A("")
    if figs_rel and "fig03" in figs_rel:
        A(f"![가족별 시작월 분포]({figs_rel['fig03']})")
        A("")
    A("### 3.3 참여 규모·협력 구조·예산 추정")
    A("")
    p = resid
    A(f"- 참여인원 기록 합계(주민 대상) {int(p['participants_total'].sum()):,}명(중복 참여 포함, 고유 주민 수 아님). 기록당 중앙값 {p['participants_total'].median():.0f}명, 90분위 {p['participants_total'].quantile(0.9):.0f}명, 참여 0 기록 {p['participants_zero_flag'].mean() * 100:.1f}%.")
    A(f"- 세대 100당 참여(기록 단위, 주민 대상) 중앙값 {p['participation_per_100hh'].median():.1f}, 개인 51명 이상 대형 기록 {(p['participants_individual'] >= 51).mean() * 100:.1f}%, 참여가 세대수를 넘는 기록 {p['participants_over_households_flag'].mean() * 100:.2f}%.")
    A(f"- 협력(주민 대상 기록 기준): 업무협약 플래그 {p['flag_mou'].mean() * 100:.1f}%, 외부공모사업 {p['flag_external_contest'].mean() * 100:.1f}%, 문화예술공연 {p['flag_culture_performance'].mean() * 100:.1f}%, 원문에 협력기관 유형이 언급된 기록 {(p['partner_org_n_text'] > 0).mean() * 100:.1f}%, 평균 참여기관수 {p['org_count_raw'].mean():.2f}.")
    A(f"- 예산 구분(원본, 주민 대상 기록 기준): 예산주체{', '.join(f'{k} {v:.0f}%' for k, v in (p['budget_subject_raw'].value_counts(normalize=True) * 100).items())}; 소요비용분류 {', '.join(f'{k} {v:.0f}%' for k, v in (p['cost_class_raw'].value_counts(normalize=True) * 100).items())}.")
    est = p["est_cost_mid_krw"]
    A(f"- **가상 예산(모델 추정; 주민 대상 기록 기준)**: 건당 중앙 {est.median():,.0f}원(10분위 {est.quantile(0.1):,.0f}~90분위 {est.quantile(0.9):,.0f}원), 단지당 연간 추정 {cf['est_cost_mid_per_year_krw'].median():,.0f}원(중앙값; 최소 {cf['est_cost_mid_per_year_krw'].min():,.0f}~최대 {cf['est_cost_mid_per_year_krw'].max():,.0f}원), 단지 부담 추정 중앙 {cf['est_burden_mid_per_year_krw'].median():,.0f}원. "
      f"단지 부담 구분: " + ", ".join(f"{k.split('(')[0]} {v:.0f}%" for k, v in (p['est_burden_class'].value_counts(normalize=True) * 100).items()) + ".")
    ta = rows[(rows["text_amount_krw_max"].fillna(0) >= 10000)]
    if len(ta) >= 20:
        ratio = (ta["est_cost_mid_krw"] / ta["text_amount_krw_max"])
        rho = ta[["text_amount_krw_max", "est_cost_mid_krw"]].corr(method="spearman").iloc[0, 1]
        A(f"- **예산 추정 점검**: 전체 행 중 원문에 금액(1만원 이상)이 적힌 {len(ta)}건과 비교하면 추정 중앙값/원문 금액의 중앙값이 {ratio.median():.2f}, 0.2~5배 이내 {((ratio >= 0.2) & (ratio <= 5)).mean() * 100:.0f}%, 순위상관 ρ={rho:.2f}. 원문 금액은 단가·일부 품목인 경우가 많아 정밀 검증은 아니며, 추정치는 **자릿수 수준의 계획용 지표**로만 쓴다.")
    A("")
    if figs_rel and "fig07" in figs_rel:
        A(f"![가족별 건당 가상 예산]({figs_rel['fig07']})")
        A("")
    A("### 3.4 반복·중복·유사 프로그램")
    A("")
    dup_n = int(rows["dup_exact_flag"].sum() - rows["dup_exact_first_flag"].where(rows["dup_exact_flag"] == 1, 0).sum())
    A(f"- 원본 명칭 {F['raw_titles']:,}종은 표현 변이(연·월·차수·단지명·실시류)를 정규화하면 {F['title_norm']:,}종, 같은 유형 안 유사도 군집으로 {F['alias_clusters']:,}개 별칭 군집이 된다. 표준 유형은 {F['n_std_used']}종이다.")
    A(f"- 같은 단지에서 같은 정규화 제목이 3회 이상 반복되는 기록 {(rows['repeat_n_in_complex'] >= 3).mean() * 100:.1f}%, 10개 이상 단지에서 쓰인 본부·지사 공통 캠페인형 제목의 기록 {rows['hq_template_flag'].mean() * 100:.1f}%, 완전 중복 추가 행 {dup_n}건, 같은 단지·같은 날 같은 제목 중복 기록 {(rows['dup_same_day_title_n'] >= 2).sum():,}행.")
    A("")
    A("## 4. 단지 단위 종합")
    A("")
    A("### 4.1 구성·다양성·집중도")
    A("")
    cc = cf[cf["n_records_resident"] >= 15]
    A(f"- 주민 대상 기록 15건 이상 단지 {len(cc)}개 기준, 단지당 서로 다른 표준 유형 중앙 {cc['std_richness'].median():.0f}종(최소 {int(cc['std_richness'].min())}~최대 {int(cc['std_richness'].max())}), 균등도 중앙 {cc['std_evenness'].median():.2f}, 최다 유형 점유율 중앙 {cc['std_top1_share'].median() * 100:.0f}%, 상위 3개 점유율 중앙 {cc['std_top3_share'].median() * 100:.0f}%.")
    A(f"- 15건 미만 '자료 부족' 단지 {int((cf['n_records_resident'] < 15).sum())}개는 유형화에서 제외하고(T0), 단지×프로그램 후보 표에는 `low_data_complex=1`로 표시해 남겼다(학습·추천에서 뺄지는 사용자가 정한다). "
      f"단지 규모 대비 활동량(세대 1000당 연 기록)은 전체 {len(cf)}개 단지 기준 중앙 {cf['resident_records_per_1000hh_year'].median():.0f}건, 최대 {cf['resident_records_per_1000hh_year'].max():.0f}건.")
    A("")
    if figs_rel and "fig04" in figs_rel:
        A(f"![다양성과 집중도]({figs_rel['fig04']})")
        A("")
    A("### 4.2 단지 유형화")
    A("")
    cand_k = tinfo["candidates"]
    A(f"주민 대상 기록 15건 이상 {int((cf['complex_type_id'] != 'T0').sum())}개 단지를 대상으로 목적 구성(13)·운영 패턴·집중도·협력·활동량의 표준화 변수에 PCA(분산 {tinfo['var_explained'] * 100:.0f}% 보존) 후 K-means를 적용했다. "
      f"부분표본 안정성(ARI≥0.5)과 최소 군집 비중(≥8%)을 만족하는 가장 세분된 k={tinfo['k']}를 택했다. 평균 실루엣은 {tinfo['silhouette_mean']:.2f}로 **유형 경계가 뚜렷하지 않아**, 이 유형은 연속체 위의 기술적 구분이다.")
    A("")
    ck = cand_k.copy()
    ck["k"] = ck["k"].astype(int)
    A(md_table(ck.rename(columns={"k": "k", "silhouette": "실루엣", "ari_median": "부분표본 ARI 중앙", "min_cluster_share": "최소 군집 비중", "inertia": "관성"}), {"실루엣": "{:.3f}", "부분표본 ARI 중앙": "{:.3f}", "최소 군집 비중": "{:.3f}"}))
    A("")
    prof = tinfo["profile"].reset_index()
    A(md_table(prof[["cluster", "n_complexes", "top_features"]].rename(columns={"cluster": "유형", "n_complexes": "단지 수", "top_features": "평균 대비 두드러진 특징(z 점수)"})))
    A("")
    if figs_rel and "fig05" in figs_rel:
        A(f"![단지 유형]({figs_rel['fig05']})")
        A("")
    A("### 4.3 공급 공백")
    A("")
    gp = {TX.NEED_DOMAINS[k]: float(cc[f"gap_{k}_flag"].mean() * 100) for k in ["N1", "N2", "N3", "N4", "N5", "N6"]}
    A(f"필요 분야별 '최근 12개월 0건 또는 같은 피어 그룹(공급유형×규모) 하위 20%' 단지 비율(주민 대상 기록 15건 이상 단지 {len(cc)}개 기준): " + ", ".join(f"{k} {v:.0f}%" for k, v in sorted(gp.items(), key=lambda x: -x[1])) + ".")
    A("공백은 **공급 기록의 부족 신호**이지 주민 필요의 정답이 아니다. 시행 기록이 없다는 사실을 필요 없음이나 실패로 해석하지 않으며, 분야 분류가 주 목적 하나에 의존하므로 복수 목적 행의 분야 공급은 과소 계상될 수 있다.")
    A("")
    if figs_rel and "fig06" in figs_rel:
        A(f"![필요 분야별 공급 공백]({figs_rel['fig06']})")
        A("")
    A("### 4.4 잠재 요인과 동시 시행")
    A("")
    A(f"단지×표준 유형 기록 수(log1p)를 NMF(k={linfo['k']})로 분해했다(주민 대상 기록 15건 이상 {len(cc)}개 단지 기준이며, 나머지 {len(cf) - len(cc)}개 단지는 잠재요인 적재 열이 비어 있다; 상대 복원오차 {linfo['reconstruction_rel_error']:.2f}; 희소 행렬이라 높은 편). 요인은 '함께 운영되는 프로그램 묶음'이며 필요의 정답이 아니다.")
    A("")
    A(md_table(comp[["component", "top_std", "n_complexes_dominant"]].rename(columns={"component": "요인", "top_std": "비중이 큰 표준 프로그램", "n_complexes_dominant": "우세 단지 수"})))
    A("")
    co2 = co[co["n_both"] >= 20].head(8)
    if len(co2):
        A("동시 시행 연관(리프트, 두 유형 모두 20개 이상 단지에서 함께 시행): ")
        A("")
        A(md_table(co2[["std_a_name", "std_b_name", "n_both", "lift", "jaccard"]].rename(columns={"std_a_name": "유형 A", "std_b_name": "유형 B", "n_both": "동시 단지", "lift": "리프트", "jaccard": "자카드"})))
        A("")
    A("### 4.5 추천·Learning-to-Rank 특성")
    A("")
    A("특성 정의(분모·관측 기간·결측 처리·버전)는 `feature_catalog.csv`에 있다. 수준별 구성:")
    A("")
    A("| 수준 | 파일 | 단위 | 대표 특성 |")
    A("|---|---|---|---|")
    A(f"| 아이템(표준 프로그램) | `standard_program_dictionary.csv` | {len(dic[dic['std_id'] != 'Z99'])}종 | 목적·대상·방식·운영 통상 속성, 채택률·최근성, 월별 분포(계절성), 참여 규모, 건당 예산 분위, 협력기관, 지원 단위 비중, NMF 요인 구성 |")
    A(f"| 사용자(단지) | `complex_features.csv` | {len(cf)}개 | 활동량·다양성·집중도·운영 패턴·월 분포·참여·협력 구조·예산 추정·반복·공백·피어 이웃·유형·잠재요인 적재 |")
    A(f"| 쌍(단지×프로그램) | `complex_program_candidates.csv` | {len(cand):,}쌍 | 단지 내 시행 횟수·최근성, 전체·피어 그룹·유사 이웃 채택률, 공백 후보·공백 분야 충족, 다음 달 계절 적합, 예산 비율, 참여 규모 |")
    A(f"| 행렬 | `complex_std_matrix_long/wide.csv`, `std_cooccurrence.csv`, `complex_latent_factors.csv` | - | 협업 필터링·보완성·잠재요인 |")
    A("")
    A("사용 원칙: ① 학습·시험을 **단지 단위로 분리**하고 채택률·피어 특성은 학습 단지에서만 산출한다(누수 방지), ② `complex_adopted=0`을 비적합 라벨로 쓰지 않는다(정답은 전문가 등급 수집 후), ③ 예산·참여 특성은 추정/기록 인원임을 모형 해석에 반영, ④ 라벨 확신(`std_confidence`)·`label_source`로 불확실한 행을 가중·제외할 수 있다.")
    A("")

    # ── 5. 품질 검증 ──
    if extra is not None:
        L.extend(RX.build_extra(extra, figs_rel))
    A("## 6. 품질 검증")
    A("")
    A("### 6.1 무결성·정합성(전수 자동 점검)")
    A("")
    qs = qa.groupby(["category", "status"]).size().unstack(fill_value=0)
    n_obs = int(qa["expected"].astype(str).str.contains("관측|참고").sum())
    A(f"점검 {len(qa)}건 중 PASS {int((qa['status'] == 'PASS').sum())}건, FAIL {int((qa['status'] == 'FAIL').sum())}건. 이 중 {n_obs}건은 관측값을 보고하거나 참고로 남기는 점검(기준 열이 '관측값 보고'·'참고')이라 "
      f"항상 PASS로 기록되며, 실제 판정이 있는 점검은 {len(qa) - n_obs}건이다. 상세는 `validation/qa_checks.csv`.")
    A("")
    A(md_table(qa[["check_id", "category", "description", "result", "expected", "status"]].rename(columns={"check_id": "ID", "category": "분류", "description": "점검", "result": "결과", "expected": "기준", "status": "판정"})))
    A("")
    if len(robust):
        A("**표현 변이 점검**(무작위 2,500행에 변이를 가한 뒤 규칙 라벨이 유지되는 비율). 이 변이(공백·문장부호·연월·차수 표기)는 규칙이 찾는 키워드와 무관하거나(연·월·차수) 규칙이 텍스트를 만들 때 지우는 것(공백·문장부호)이라 이 표본에서는 라벨이 그대로 유지된다. "
          "전수에 적용하면 '1회용품'→'용품'처럼 일부 행은 바뀔 수 있으므로, 정규화가 의도대로 작동하는지 보는 점검일 뿐 동의어 치환 같은 의미 수준의 강건성을 보장하는 근거는 아니다:")
        A("")
        A(md_table(robust.rename(columns={"perturbation": "변이", "n": "행 수", "label_unchanged_rate": "라벨 유지율"}), {"라벨 유지율": "{:.3f}"}))
        A("")
    A("### 6.2 독립 LLM 라벨러와의 일치도")
    A("")
    if val:
        A("**규칙 엔진 단독**(최종 병합 전). A는 규칙을 개발·보정한 표본이라 낙관적이고, B가 독립 표본이다.")
        A("")
        vt = validation_tables(val)
        A(md_table(vt, {c: "{:.3f}" for c in vt.columns if c not in ("표본", "행 수")}))
        A("")
    if final_val:
        A("**최종 라벨(규칙 + LLM 판정 병합) vs 독립 LLM 라벨러**:")
        A("")
        vt = validation_tables(final_val)
        A(md_table(vt, {c: "{:.3f}" for c in vt.columns if c not in ("표본", "행 수")}))
        A("")
        for name, v in final_val.items():
            A(f"**{name} — 운영 특성 항목별 일치(레코드 수준; 반복 기록 근거는 라벨러가 볼 수 없어 제외)**")
            A("")
            A(md_table(ops_kappa_table(v), {c: "{:.3f}" for c in ops_kappa_table(v).columns if c != "운영 특성"}))
            A("")
            A(f"**{name} — 규칙 확신·라벨 출처별 표준 유형 일치**")
            A("")
            cs = v.get("by_label_source")
            if cs is not None:
                A(md_table(cs, {c: "{:.3f}" for c in cs.columns if c not in ("라벨 출처", "행 수")}))
                A("")
            conf = pd.DataFrame([{"규칙 확신": k, "행 수": d["n"], "유형 일치": d["std_acc"], "가족 일치": d["family_acc"]} for k, d in v["std_by_confidence"].items()])
            A(md_table(conf, {"유형 일치": "{:.3f}", "가족 일치": "{:.3f}"}))
            A("")
            conf_pairs = v["confusions"].head(12).copy()
            conf_pairs["규칙/최종"] = conf_pairs["std_id"].map(lambda x: f"{x} {BY_ID[x]['name']}" if x in BY_ID else x)
            conf_pairs["LLM"] = conf_pairs["llm_std"].map(lambda x: f"{x} {BY_ID[x]['name']}" if x in BY_ID else x)
            A(f"**{name} — 불일치가 많은 유형 쌍**")
            A("")
            A(md_table(conf_pairs[["규칙/최종", "LLM", "n"]].rename(columns={"n": "건수"})))
            A("")
            break
    A(f"해석 시 유의: 일치도는 *독립 LLM 한 명*과의 일치이며 사람 전문가 정답이 아니다. 유형 사전이 {len(TYPES)}종으로 세분되어 인접 유형(예: 명절 행사 vs 취약세대 돌봄 행사, 복지상담소 vs 개별 서비스, 후원물품 vs 식품 지원) 사이에서 라벨러 간에도 불일치가 크다. 가족 수준 일치가 유형 수준보다 높다. "
      + _c_vs_b(final_val) + _scope_note(final_val))
    A("")
    if figs_rel and "fig08" in figs_rel:
        A(f"![독립 LLM 일치도]({figs_rel['fig08']})")
        A("")
    A("### 6.3 알려진 한계")
    A("")
    A("- **정답이 아니다**: 자동 구조화 초안이다. 전문가가 독립 검토한 정답 구축(연구방법론 v5의 1단계) 전에는 모형 학습의 '정답'으로 쓰지 않는다. LLM 판정을 정답으로 삼아 같은 계열 모형을 평가하지 않는다.")
    A("- **참여인원**: 관리소·기관·단체를 포함한 기록 인원이며 고유 주민 수혜자 수가 아니다. 활동횟수가 여러 회차일 때 참여 계가 합산인지 회당인지 알 수 없다.")
    A("- **예산**: 모델 가정 기반 추정치다. 소요비용분류·예산주체의 '기타'는 금액이 아니며 0원이 아니다.")
    A("- **운영 특성**: 한 행은 한 번의 기록이라 프로그램 전체의 주기를 직접 보여주지 않는다. 정기형 P의 상당수는 같은 단지의 반복 기록(repeat) 근거이며 라벨러가 볼 수 없는 정보다.")
    A("- **분야·목적**: 유형당 주 목적 하나와 부수 목적을 두었으므로 복합 활동의 분야별 공급은 과소 계상될 수 있다.")
    nt = meta.get("new_type")
    if nt and nt["n_rows"]:
        hb = ", ".join(f"{k}×{v}" for k, v in nt.get("high_by_std", {}).items())
        A(f"- **사전에 없는 유형 후보**: LLM 라벨러가 '목록에 맞는 유형이 없다'(NEW)고 답한 문구가 {nt['n_new']}행, 내용만으로 유형을 알 수 없다(Z99)고 답한 문구가 {nt['n_z99']}행 있다. "
          f"NEW 가운데 규칙이 high 확신으로 사전 유형에 연결한 {nt['n_new_high']}행({hb})은 규칙 라벨을 유지했고, 그중 {nt.get('n_added_types', 0)}행은 초기 지침(104종; A·ADJ·B 표본)에 없다가 LLM의 NEW 제안을 반영해 "
          "사전에 추가한 4종(E06 웰다잉·인생기록, H06 세대 생활환경 측정, I10 차량 무상점검, M05 장애 인식개선)에 해당한다. "
          f"NEW 가운데 규칙 라벨이 high가 아닌 {nt['n_new_review']}행은 규칙 라벨을 임시로 둔 채 `needs_llm_review=1`(`review_reason`에 llm_no_matching_type)로 표시했다. "
          f"Z99 응답 {nt['n_z99']}행 중 {'모두' if nt['n_z99']==nt['n_z99_to_z99'] else str(nt['n_z99_to_z99'])+'행'}은 미분류(Z99)로 확정했다. "
          "LLM의 제안은 `std_id_llm`·`llm_new_name`에 남겼고 제안 명칭별 목록은 `validation/dictionary_gap_candidates.csv`.")
    A("- **유형화**: 단지 간 차이는 연속적이며 군집 경계는 약하다. 유형명은 해석을 돕는 기술적 이름이다.")
    if meta.get("id_source"):
        A(f"- **단지 식별**: 단지통합 엑셀(`{meta['id_source']['name']}`)의 `complex_id`를 기준으로 삼았다. 단지명이 정확히 일치하는 단지만 연결했고, 통합표에 없는 단지 {len(meta['scope']['excluded_complexes'])}개({int(meta['scope']['n_excluded_rows'])}행)는 분석에서 뺐다. "
          f"통합표 {meta['n_integrated']}개 단지 중 커뮤니티 기록이 없는 단지는 {meta['n_integrated_without_records']}개다(결측은 0이 아니라 '기록 없음').")
    else:
        A("- **단지 식별**: 단지명 문자열 키이며 승인된 단지 ID와의 연결이 아니다(연구방법론 v4 §9).")
    A("")
    A("## 7. 재현과 산출물")
    A("")
    import os as _os
    mods = sorted(f[:-3] for f in _os.listdir(_os.path.dirname(_os.path.abspath(__file__))) if f.endswith(".py") and f != "__init__.py")
    A("- 코드: `project/tools/community_nlp/`(" + "·".join(mods) + "). 작업 폴더를 `project/tools`로 두고 "
      "`python -m community_nlp.build_final --raw <원본.xlsx> --ann <라벨러 판정 폴더> --out <출력 폴더> [--label-ref <이전 원본.xlsx>] [--integrated <단지통합.xlsx>] [--guideline <지침서 ...>] [--seed 7]`로 다시 만든다. "
      "`--ann`에 산출물의 `llm_annotations/`를 주면 저장된 `previous_to_current_row_map.csv`로 이전 라벨을 옮기므로 이전 원본이 없어도 재현된다(이때 §1.1의 원본 비교 표는 생략된다).")
    A("- 버전: taxonomy_v1.0, std_programs_v1.0, budget_assumptions_v1.0, 라벨러 지침 v1.0(A)/v1.1(ADJ·B)/v1.2(ADJ2·ADJ3·C). 라벨러 원 응답은 `llm_annotations/`에 보존(A·ADJ·ADJ2·B는 이전 스냅샷 행 번호, ADJ3·C는 갱신본 행 번호).")
    A("- 분석에 쓴 원본 엑셀은 `source_snapshot/`에 사본을 두었다(SHA256은 `manifest.json`의 `source_sha256`과 같다).")
    A("- 파일 목록과 무결성 해시는 `README.md`, `manifest.json`, `file_checksums.json`.")
    A("")
    A("## 부록 A. 표준 프로그램 사전(요약)")
    A("")
    A(md_table(dictionary_summary(dic)))
    A("")
    if extra is not None:
        L.extend(RX.build_glossary())
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return out_path


def _c_vs_b(final_val):
    """C 표본과 B 표본의 표 값을 비교한 문장(어느 항목이 높고 낮은지는 값에서 계산한다)."""
    b = next((v for k, v in final_val.items() if k.startswith("B(")), None)
    c = next((v for k, v in final_val.items() if k.startswith("C(")), None)
    if b is None or c is None:
        return ""
    t = validation_tables({"B": b, "C": c}).set_index("표본")
    cols = [x for x in t.columns if x != "행 수"]
    hi = [x for x in cols if t.loc["C", x] > t.loc["B", x] + 0.005]
    lo = [x for x in cols if t.loc["C", x] < t.loc["B", x] - 0.005]
    return ("C 표본은 규칙이 high 확신으로 확정해 LLM 판정을 거치지 않은 층의 갱신분이라 B(무작위 표본)와 구성이 다르므로 B와 같은 기준의 성능 비교로 읽지 않는다. "
            f"참고로 표 값의 차이가 0.005를 넘는 항목만 보면 C가 B(최종 라벨 기준)보다 높은 항목은 {', '.join(hi) or '없음'}, 낮은 항목은 {', '.join(lo) or '없음'}이다(나머지는 비슷).")


def _scope_note(final_val):
    """범위(scope) 불일치 가운데 주민 프로그램↔세대 직접 지원 경계에서 갈린 건수를 표본별로 계산해 문장으로 만든다."""
    parts = []
    for nm, v in final_val.items():
        if nm.startswith(("B(", "C(")):
            m = v["merged"]
            x = m[m["scope"] != m["llm_scope"]]
            both = x["scope"].isin(TX.RESIDENT_SCOPES) & x["llm_scope"].isin(TX.RESIDENT_SCOPES)
            parts.append(f"{nm.split('(')[0]} 표본 {len(x)}건 중 {int(both.sum())}건")
    if not parts:
        return ""
    return (" 범위(scope) 불일치 가운데 '주민 프로그램'과 '세대 직접 지원' 사이의 경계에서 갈린 경우는 " + ", ".join(parts) + "이다. 두 범위 모두 추천 후보인 주민 대상 범위라 후보 집합에는 영향이 없고, "
            "표의 '주민 대상 여부 일치'가 후보 집합 기준의 일치율이다. 나머지는 거버넌스·시설 관리·직원·행정 범위로 갈린 경우다.")


def BG_frame():
    rows = []
    for k, (flo, fhi, ulo, uhi, scale, dn, desc) in BG.ARCH.items():
        rows.append(dict(아키타입=k, 고정비_하한=flo, 고정비_상한=fhi, 단가_하한=ulo, 단가_상한=uhi, 회차반영=scale, 설명=desc))
    return pd.DataFrame(rows)
