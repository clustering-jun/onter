# -*- coding: utf-8 -*-
"""특성 카탈로그: 각 특성의 정의·분모·관측 기간·결측 처리·생성 버전을 남긴다(v5 §4)."""
import re
import numpy as np
import pandas as pd

from .std_programs import TYPES

GEN_VERSION = "community_nlp_2026_v1"
W30 = "2024-01~2026-06(30개월)"
W12 = "2025-07~2026-06(최근 12개월)"

# (패턴, 정의, 분모/단위, 기간, 결측 처리, 역할)
ROW_RULES = [
    (r"^source_row$", "원본 엑셀(데이터 시트)의 행 번호(헤더=1행, 데이터는 2행부터). 원본과 연결하는 기본 키", "행", "-", "없음", "id"),
    (r"^record_id$", "comm_ + source_row(5자리). 원본 행의 고정 식별자", "행", "-", "없음", "id"),
    (r"^complex_id$", "단지 고유 ID. 단지통합_20261117.xlsx의 complex_id(예: KOH_1)이며 complex_name과 1:1. 다른 단지 자료와 합칠 때 쓰는 키", "단지", "-", "없음", "id"),
    (r"^complex_name$", "단지명(원본). complex_id와 1:1이고 단지통합 엑셀의 단지명과 같다", "단지", "-", "없음", "id"),
    (r"^(supply_type|households)$", "원본 공급유형·세대수(단지당 단일 값)", "단지", "-", "없음", "raw"),
    (r"^(field|raw_community_type)$", "원본 분야(주거복지/주거안전)·커뮤니티유형(9종, 작성자 선택값; 의미 판정에는 보조로만 사용)", "행", "-", "없음", "raw"),
    (r"^flag_", "원본 Y/N 플래그(문화예술공연·외부공모사업·업무협약)를 1/0으로 변환", "행", "-", "없음", "raw"),
    (r"^(program_name_raw|activity_content_raw|place_raw)$", "원본 텍스트(커뮤니티명·활동내용·장소명) 그대로", "행", "-", "없음", "raw"),
    (r"^(program_name_masked|activity_content_masked|place_masked)$", "동·호수·부분 가림 이름·수료자 이름·전화번호 패턴을 가린 텍스트(분석·공유용). 규칙 기반이라 별표 없이 적힌 직함 붙은 실명(○○○ 회장 등)은 가리지 못할 수 있어 외부 공유 전 확인이 필요하다", "행", "-", "없음", "text"),
    (r"^sensitive_identifier_flag$", "활동명·활동내용·장소명 중 하나라도 마스킹 규칙이 원문을 실제로 바꾼 행이면 1(동·호수·부분 가림 이름·전화 같은 식별 패턴이 있어 가려짐; 마스킹본 사용 권장)", "행", "-", "없음", "qa"),
    (r"^title_norm$", "연·월·차수·단지명·실시류 접미를 제거한 정규화 제목(반복·별칭 묶기 키). 마스킹한 명칭에서 만들어 부분 가림 이름 조각이 남지 않는다", "행", "-", "빈 값 없음", "text"),
    (r"^umbrella_tags$", "사업 포장어(공동체활성화·특화사업·마을만들기·외부자원유치·1사1단지 등) 태그. 유형 판정에서는 제외", "행", "-", "없으면 빈 값", "label"),
    (r"^(scope|scope_label|in_resident_scope)$", "기록 범위: 주민 프로그램/세대 지원/거버넌스/직원/시설관리/행정. in_resident_scope=1이면 추천 후보 범위", "행", "-", "없음", "label"),
    (r"^std_(family|family_label|id|name)$", "표준 프로그램 유형 사전(%d종 + 미분류 Z99)의 가족·ID·명칭" % len(TYPES), "행", "-", "미분류는 Z99", "label"),
    (r"^std_secondary_(ids|names)$", "합성형 활동에서 함께 포착된 부수 표준 유형(최대 3개)", "행", "-", "없으면 빈 값", "label"),
    (r"^std_(evidence|evidence_field)$", "표준 유형 판정의 근거 문자열과 출처 필드(name/content/theme)", "행", "-", "근거 없으면 빈 값", "evidence"),
    (r"^std_(score|margin)$", "규칙 점수와 2위와의 점수차(명칭 적중 3/2/1, 내용 1/0.7/0.3 등). 문맥 규칙(override)으로 1순위를 바꾼 행은 음수일 수 있음. 규칙 엔진 값이며 LLM이 확정한 행에서도 규칙 값을 그대로 둔다", "점수", "-", "없음", "qa"),
    (r"^std_confidence$", "규칙 확신: high/medium/low. LLM 판정 행은 llm-H/M/L", "행", "-", "없음", "qa"),
    (r"^(std_override|std_fallback)$", "문맥 규칙으로 유형을 바꾼 경우·우산 기본값/미매칭 사유", "행", "-", "없으면 빈 값", "qa"),
    (r"^label_source$", "최종 라벨의 출처: rule(사전·규칙) / llm(독립 LLM 라벨러가 검토·확정)", "행", "-", "없음", "qa"),
    (r"^(review_reason|needs_llm_review)$", "LLM 검토 대상 사유(unmatched·low_confidence·close_competitor 등). LLM이 NEW·Z99로 답했는데 규칙 라벨이 high가 아니어서 규칙 라벨이 임시로 남은 행은 llm_no_matching_type으로 1을 유지(사람 검토 대상)", "행", "-", "없음", "qa"),
    (r"^llm_", "독립 LLM 라벨러의 원 응답 필드(감사용). 라벨러는 규칙 결과를 보지 않았다", "행", "-", "라벨러가 보지 않은 행은 빈 값", "evidence"),
    (r"^purpose_(primary|primary_label)$", "주 복지 목적(P01~P16). 표준 유형의 정의 또는 LLM 판정", "행", "-", "미분류는 빈 값", "label"),
    (r"^purpose_secondary$", "부수 목적(유형 정의 + LLM)", "행", "-", "빈 값", "label"),
    (r"^purpose_secondary_text_cue$", "원문 단서(명칭 적중 또는 내용 2회 이상)로 추가된 부수 목적", "행", "-", "빈 값", "label"),
    (r"^purpose_labels$", "주·부수 목적의 한글 라벨", "행", "-", "빈 값", "label"),
    (r"^need_domain_(primary|labels|primary_label)$|^need_domains$", "v4 필요 분야 6개(N1~N6)로의 대응. 정보·연계(P14)와 운영(P15·P16)은 분야가 아니라 N0", "행", "-", "N0는 별도", "label"),
    (r"^target_explicit(_labels)?$", "원문에 명시된 지원 대상 코드(키워드 단서 또는 LLM이 원문에서 확인). 추정 아님", "행", "-", "명시 없으면 빈 값(0 아님)", "label"),
    (r"^target_type_default(_labels)?$", "표준 유형의 통상 대상(원문에 없는 추정). 원문 명시와 구분해 저장", "행", "-", "빈 값", "label"),
    (r"^target_basis$", "대상 근거: text(원문 명시) / mixed / type_default(유형 추정만) / unknown", "행", "-", "unknown", "qa"),
    (r"^target_age_text$", "원문에 적힌 연령 표현(예: 만65세 이상)", "행", "-", "빈 값", "text"),
    (r"^service_(codes|labels)$", "제공 서비스(S01~S20): 표준 유형의 정의 속성", "행", "-", "빈 값", "label"),
    (r"^mode_explicit(_labels)?$", "원문 단서로 확인된 제공 방식(M1~M10)", "행", "-", "빈 값", "label"),
    (r"^mode_type_default(_labels)?$", "표준 유형의 통상 제공 방식(원문에 없는 추정)", "행", "-", "빈 값", "label"),
    (r"^support_unit_", "v4 지원 단위(단지 전체/일부 가구 직접 지원/안부·관계 접촉). 상호 배타적이지 않음", "행", "-", "0/1", "label"),
    (r"^op_(always|regular|event|adhoc|seasonal)$", "운영 특성 5종 각각의 상태: Y 확정 / P 개연 / N 반증 / U 미확인", "행", "-", "U", "label"),
    (r"^op_(primary|labels|labels_confirmed)$", "주된 운영 유형, Y·P 라벨 전체, Y(확정)만의 라벨", "행", "-", "근거 없으면 빈 값", "label"),
    (r"^op_basis$", "운영 특성 상태의 근거(text/date_count/series/period_label/repeat/type_prior 등)", "행", "-", "빈 값", "evidence"),
    (r"^op_interval_", "반복 간격 추정(일). 원문 주기 단서 우선, 없으면 (기간−1)/(횟수−1). 연말 일괄 종료는 제외", "일", "-", "근거 없으면 빈 값", "feature"),
    (r"^op_(series_no|period_label|calendar_tag)$", "원문의 차수 표기·상/하반기·분기 표기, 달력 연동 태그(명절/연말연시/여름/겨울/봄/가을/기념일)", "행", "-", "빈 값", "feature"),
    (r"^op_flags$", "운영 특성 판정 중 일정·원문 상충(예: alw_text_vs_single_day) 및 날짜 이상 표시", "행", "-", "빈 값", "qa"),
    (r"^op_type_prior$", "표준 유형의 통상 운영 방식(사전 정의). 실제 일정과 분리", "행", "-", "빈 값", "label"),
    (r"^partner_org_", "원문에 언급된 협력기관 유형(OG01~OG16)과 키워드. 기관 이름을 만들어 내지 않음", "행", "-", "미언급은 빈 값", "feature"),
    (r"^effect_explicit(_labels)?$", "원문에 명시된 기대 효과 키워드", "행", "-", "빈 값", "label"),
    (r"^effect_type_default(_labels)?$", "표준 유형의 통상 기대 효과(추정)", "행", "-", "빈 값", "label"),
    (r"^resource_explicit(_labels)?$", "원문 단서로 확인된 필요 자원", "행", "-", "빈 값", "label"),
    (r"^resource_type_default(_labels)?$", "표준 유형의 통상 필요 자원(추정)", "행", "-", "빈 값", "label"),
    (r"^text_(households_n|persons_n|amount_krw_max|kg_max|item_count_max|dates_n|sessions_n)$", "활동명·내용 자유 서술에서 추출한 수치(수혜 세대 수·인원·금액(원)·물량(kg)·개수·날짜 표기 수·회차). 검증되지 않은 관측이며 없으면 빈 값(0 아님). 금액은 예산 추정의 보정·점검용", "-", "-", "없으면 빈 값", "feature"),
    (r"^funding_cue$", "공모·지원사업·기금 등 재원 단서가 원문에 있으면 1", "행", "-", "0", "feature"),
    (r"^(start_date|end_date)$", "원본 시작·종료일자(ISO). 종료일이 2027년 이후이거나 시작보다 빠르면 date_anomaly_flag=1이고 end_date는 빈 값(결측)", "일", W30, "종료일 이상치는 빈 값(원문은 end_date_raw)", "raw"),
    (r"^end_date_raw$", "원본 종료일자 원문(ISO). 9999-12-31·2204·2042 등 이상 값도 그대로 보존하는 감사용 열. 분석에는 end_date·duration_days를 쓴다", "일", W30, "없음", "raw"),
    (r"^start_(year|month|quarter|season)$", "시작일 기준 연·월·분기·계절(봄3-5·여름6-8·가을9-11·겨울12-2)", "행", W30, "없음", "feature"),
    (r"^duration_days$", "종료−시작+1(일). 종료일 이상치는 결측", "일", W30, "이상치=결측(0 아님)", "feature"),
    (r"^(single_day_flag|year_end_end_date_flag|date_anomaly_flag)$", "당일 기록 / 12-31 일괄 종료 관행 추정(시작≠1/1, 31일 초과) / 종료일 이상(2027 이후 또는 시작보다 빠름)", "행", W30, "0", "qa"),
    (r"^activity_count(_zero_flag|_gt60_flag)?$", "원본 활동횟수. 0회·60회 초과 표시(입력 이상 가능성)", "회", W30, "결측 없음", "feature"),
    (r"^participants_(total|individual|institutional|staff_mgmt|tenant_council)$", "참여인원 기록(계/개인/기관 합/관리소/임차인대표회의). 고유 주민 수혜자 수가 아님", "명", W30, "0은 기록값(미상 아님)", "feature"),
    (r"^(participants_total_mismatch_flag|participants_zero_flag|participants_over_households_flag)$", "계≠세부 합 / 계=0 / 참여 계>세대수", "행", W30, "0", "qa"),
    (r"^(institution_types_nonzero|org_count_raw)$", "인원이 있는 기관 유형 수 / 원본 참여기관수", "개", W30, "0", "feature"),
    (r"^part_flag_", "해당 참여 주체 인원이 1명 이상이면 1", "행", W30, "0", "feature"),
    (r"^(participation_per_100hh|individual_per_100hh)$", "참여인원(계/개인) ÷ 단지 세대수 × 100. 기록 인원 기준이며 중복 참여 포함", "세대 100당", W30, "세대수 0이면 빈 값", "feature"),
    (r"^participants_per_session$", "참여인원_계 ÷ 활동횟수(횟수 0이면 빈 값). 합계가 회차 합산인지 불명이므로 참고용", "명/회", W30, "빈 값", "feature"),
    (r"^scale_class$", "개인 참여인원 구간(xs 1-5, s 6-20, m 21-50, l 51-150, xl 151+, none=0)", "행", W30, "none", "feature"),
    (r"^(cost_class_raw|budget_subject_raw)$", "원본 소요비용분류·예산주체. 금액이 아니며 '기타'를 0원으로 바꾸지 않음", "행", "-", "없음", "raw"),
    (r"^budget_archetype$", "예산 추정에 쓰는 비용 구조 유형(FREE_EXT·EVENT_FEAST·CLASS 등)", "행", "-", "NONE", "feature"),
    (r"^est_cost_(low|mid|high)_krw$", "[모델 추정] 1건의 직접 운영비(시장가) 하한·중앙·상한. (고정비+단가×유효 참여인원)×회차계수. 실제 집행액·견적 아님", "원", "건당", "추정 불가 시 0(비용 없음 유형)", "estimate"),
    (r"^est_burden_(class|factor|mid_krw)$", "[모델 추정] 단지 부담 구분(소요비용분류·예산주체·외부기관 언급 기반)과 계수(1.0/0.5/0.15), 부담 추정액=중앙×계수", "원", "건당", "-", "estimate"),
    (r"^est_(n_effective|n_basis|sessions_used|cost_band|flag)$", "[모델 추정] 유효 참여인원과 산정 근거, 회차 반영, 금액 구간, 추정 표시", "-", "-", "-", "estimate"),
    (r"^repeat_(n_in_complex|index|months_active)$", "같은 단지·같은 정규화 제목의 기록 수 / 시간순 번호 / 활동 월 수", "건", W30, "1", "feature"),
    (r"^repeat_gap_", "같은 단지·제목의 직전 기록과의 간격(일)과 그 중앙값. 기록 건수만으로 정기 주기를 확정하지 않음", "일", W30, "첫 기록은 빈 값", "feature"),
    (r"^(name_len|content_len)$", "활동명·활동내용 글자 수", "자", "-", "없음", "qa"),
    (r"^(content_equals_name_flag|low_info_text_flag)$", "활동내용이 활동명과 같음 / 정보량이 매우 적은 텍스트", "행", "-", "0", "qa"),
    (r"^dup_exact_(flag|first_flag)$", "완전 동일 레코드(단지·명칭·내용·일자·횟수·인원 동일) 여부와 대표 행", "행", "-", "0", "qa"),
    (r"^dup_same_day_(title_n|std_n)$", "같은 단지·같은 날짜의 같은 제목/같은 표준 유형 기록 수. 정상 반복 삭제 근거로 쓰지 않음", "건", W30, "1", "qa"),
    (r"^(title_n_complexes|content_n_complexes)$", "같은 정규화 제목/같은 활동내용을 쓴 단지 수", "단지", W30, "1", "feature"),
    (r"^hq_template_flag$", "정규화 제목이 10개 이상 단지에서 쓰인 본부·지사 공통 캠페인형 활동", "행", W30, "0", "feature"),
    (r"^alias_cluster_id$", "같은 표준 유형 안에서 제목이 유사한 활동의 별칭 군집 ID", "행", "-", "없음", "label"),
    (r"^canonical_title$", "별칭 군집의 대표 표준 명칭(연·월·차수·단지명 제거)", "행", "-", "없음", "label"),
    (r"^(std_id_rule|std_id_llm)$", "규칙 엔진이 낸 표준 유형 ID / 독립 LLM 라벨러가 낸 표준 유형 ID(라벨러가 본 행만)", "행", "-", "빈 값", "evidence"),
    (r"^op_rule_states$", "규칙 엔진 단독 운영 특성 상태(ALW=..,REG=..) — LLM 확정 행도 운영 특성은 규칙 기준으로 산출", "행", "-", "없음", "evidence"),
    (r"^llm_batch$", "LLM 판정이 속한 배치(A 표본/ADJ 검토/+propagated=동일 텍스트 전파)", "행", "-", "빈 값", "evidence"),
]


def _match(rules, col):
    for pat, d, den, win, miss, role in rules:
        if re.match(pat, col):
            return d, den, win, miss, role
    return None


def _summ(s):
    s2 = s.dropna()
    if s2.empty:
        return "", 0, ""
    if pd.api.types.is_numeric_dtype(s2):
        fmt = lambda v: f"{v:.0f}" if float(v).is_integer() and abs(v) < 1e12 else f"{v:.4g}" if abs(v) < 1e5 else f"{v:,.0f}"
        return "num", int(s2.nunique()), f"{fmt(s2.min())}~{fmt(s2.max())}"
    vc = s2.astype(str).value_counts()
    return "cat", int(s2.astype(str).nunique()), " / ".join(f"{k[:14]}({v})" for k, v in vc.head(3).items())


def build_row_catalog(df, extra_rules=None):
    rules = (extra_rules or []) + ROW_RULES
    out = []
    for c in df.columns:
        m = _match(rules, c)
        kind, nuniq, rng = _summ(df[c])
        if m is None:
            m = ("(설명 미작성)", "", "", "", "")
        out.append(dict(level="row(프로그램 기록)", feature=c, role=m[4], definition=m[0], unit_denominator=m[1], window=m[2],
                        missing_handling=m[3], dtype=str(df[c].dtype), non_null_rate=round(float(df[c].notna().mean()), 4),
                        n_unique=nuniq, value_summary=rng, version=GEN_VERSION))
    return pd.DataFrame(out)


# ── 단지·사전·후보 수준 규칙 ───────────────────────────────────────────────
CX_RULES = [
    (r"^complex_id$", "단지 고유 ID(단지통합_20261117.xlsx의 complex_id). complex_name과 1:1", "단지", "-", "없음", "id"),
    (r"^(complex_name|supply_type|households)$", "단지명(통합표와 같은 문자열 키)과 원본 공급유형·세대수", "단지", "-", "없음", "id"),
    (r"^(supply_group|size_tertile|peer_group)$", "공급유형 대표 그룹(영구>국민>50년>행복>기타) / 세대수 3분위(S/M/L) / 두 값의 결합 피어 그룹", "단지", "-", "없음", "feature"),
    (r"^has_", "공급유형 문자열에 해당 유형이 포함되면 1", "단지", "-", "0", "feature"),
    (r"^n_records_(all|resident|governance|staff|facility|admin|household_support)$", "기록 수(전체/주민 대상/거버넌스/직원/시설/행정/세대지원)", "건", W30, "0", "feature"),
    (r"^share_resident_records$", "전체 기록 중 주민 대상(프로그램+세대지원) 기록 비율", "전체 기록", W30, "-", "feature"),
    (r"^records_per_month$", "주민 대상 기록 수 ÷ 30개월", "건/월", W30, "-", "feature"),
    (r"^resident_records_per_1000hh_year$", "주민 대상 기록 수 ÷ 세대수 × 1000 ÷ 2.5년", "세대 1000당·연", W30, "-", "feature"),
    (r"^(first_record_date|last_record_date|months_since_last_record)$", "첫·마지막 기록 시작일과 2026-06-30 기준 마지막 기록 후 개월 수", "일/월", W30, "기록 없으면 빈 값", "feature"),
    (r"^(active_months|active_month_ratio|active_months_recent12m)$", "기록이 있는 달 수 / ÷30 / 최근 12개월 중 기록이 있는 달 수", "월", "각 창", "0", "feature"),
    (r"^n_(2024|2025|2026h1|recent12m)$", "연도별·최근 12개월 주민 대상 기록 수(2026은 상반기만)", "건", "각 창", "0", "feature"),
    (r"^(h1_2026_vs_h1_2025_ratio|y2025_vs_y2024_ratio)$", "공통 기간(상반기) 및 연간 기록 수 비율. 분모 0이면 결측", "배", "각 창", "분모 0이면 빈 값", "feature"),
    (r"^share_family_", "표준 유형 가족(F01~F15)별 기록 비율(주민 대상 기록 기준)", "주민 대상 기록", W30, "0", "feature"),
    (r"^share_purpose_", "주 목적(P01~P16)별 기록 비율", "주민 대상 기록", W30, "0", "feature"),
    (r"^share_need_", "v4 필요 분야(N1~N6, N0)별 주 분야 비율", "주민 대상 기록", W30, "0", "feature"),
    (r"^std_(richness|entropy|evenness|effective_n|simpson|hhi|top1_share|top3_share)$", "표준 유형 다양성: 종류 수 / 섀넌 엔트로피 / 균등도(H/lnK) / 유효 종류 수(e^H) / 심프슨 / HHI / 상위 1·3개 점유율(활동 집중도)", "유형", W30, "기록 없으면 빈 값", "feature"),
    (r"^std_top1_(id|name)$|^std_top5$", "가장 많은 표준 유형과 상위 5개(건수)", "-", W30, "빈 값", "feature"),
    (r"^(family|purpose|need_domain)_(richness|entropy|evenness)$", "가족·목적·필요분야 다양성(종류 수·엔트로피·균등도)", "-", W30, "빈 값", "feature"),
    (r"^records_per_distinct_std$", "기록 수 ÷ 서로 다른 표준 유형 수(반복 정도)", "건/유형", W30, "-", "feature"),
    (r"^ops_(alw|reg|evt|adh|sea)_(Y|YP|U)_share$", "운영 특성 5종별 확정(Y)/확정+개연(YP)/미확인(U) 비율", "주민 대상 기록", W30, "-", "feature"),
    (r"^ops_primary_unknown_share$", "주된 운영 유형을 정하지 못한 기록 비율", "주민 대상 기록", W30, "-", "qa"),
    (r"^(single_day_share|activity_count_mean|activity_count_median|share_activity_count_ge3|duration_days_median|year_end_end_date_share)$", "당일 비율 / 활동횟수 평균·중앙값 / 3회 이상 비율 / 기간 중앙값 / 12-31 일괄 종료 추정 비율", "-", W30, "-", "feature"),
    (r"^month_share_\d\d$", "시작월별 기록 비율(계절성). 합=1", "주민 대상 기록", W30, "-", "feature"),
    (r"^(peak_month|seasonality_cv|season_winter_share|season_summer_share)$", "최다 기록 월 / 월별 변동계수 / 겨울(12-2)·여름(6-8) 비율", "-", W30, "-", "feature"),
    (r"^(repeat_record_share|max_repeat_n|recurring_std_n|recurring_std_share|same_month_same_std_dup_cells|dup_exact_n|hq_template_share|unique_program_share)$", "반복·중복: 단지 내 제목 3회 이상 반복 기록 비율 / 최대 반복 수 / 6개월 이상 활동한 표준 유형 수·비율 / 같은 달 같은 유형 중복 셀 수 / 완전 중복 수 / 본부 공통 캠페인 비율·독자 비율", "-", W30, "-", "feature"),
    (r"^participants_(total|individual)_(sum|median|p90)$|^participants_total_(sum|median|p90)$|^participants_individual_(sum|median)$", "참여인원 기록 합·중앙값·90분위(고유 주민 수 아님)", "명", W30, "-", "feature"),
    (r"^(participation_per_100hh_year|individual_per_100hh_year|median_participation_per_100hh)$", "참여인원 합 ÷ 세대수 ×100 ÷ 2.5년 / 기록별 세대 100당 참여 중앙값", "세대 100당", W30, "-", "feature"),
    (r"^(share_large_events_indiv51plus|share_zero_participants|share_participants_mismatch)$", "개인 51명 이상 대형 기록 / 참여 0 기록 / 계≠세부합 기록 비율", "주민 대상 기록", W30, "-", "qa"),
    (r"^(org_count_raw_mean|institution_types_nonzero_mean)$", "원본 참여기관수 평균 / 인원이 있는 기관 유형 수 평균", "개", W30, "-", "feature"),
    (r"^share_(mou|external_contest|culture_performance)$", "업무협약·외부공모사업·문화예술공연 플래그 비율", "주민 대상 기록", W30, "-", "feature"),
    (r"^share_part_flag_", "해당 참여 주체(국가·지자체·의회·복지시설단체·LH·공기업·민간기업·기타단체·임차인대표회의·관리소)가 참여한 기록 비율", "주민 대상 기록", W30, "-", "feature"),
    (r"^share_org_OG", "원문에 협력기관 유형이 언급된 기록 비율(협력 구조)", "주민 대상 기록", W30, "-", "feature"),
    (r"^(partner_org_type_richness|partner_org_entropy|share_partner_mentioned)$", "협력기관 유형 수·엔트로피·협력기관 언급 기록 비율", "-", W30, "-", "feature"),
    (r"^share_subject_|^share_costclass_", "원본 예산주체·소요비용분류 구성 비율('기타'는 금액 아님)", "주민 대상 기록", W30, "-", "feature"),
    (r"^share_mode_M\d+$", "원문 단서로 확인된 제공 방식 비율", "주민 대상 기록", W30, "-", "feature"),
    (r"^share_support_unit_", "v4 지원 단위(단지 전체/일부 가구/안부·관계) 해당 비율(중복 가능)", "주민 대상 기록", W30, "-", "feature"),
    (r"^share_target_", "원문에 명시된 지원 대상 코드별 비율(대상 미명시는 포함되지 않음)", "주민 대상 기록", W30, "-", "feature"),
    (r"^share_rawtype_|^share_field_safety$", "원자료 커뮤니티유형·분야(주거안전) 구성 비율", "주민 대상 기록", W30, "-", "feature"),
    (r"^est_(cost_mid_sum_krw|cost_mid_per_year_krw|burden_mid_per_year_krw|cost_mid_per_hh_year_krw|cost_mid_median_krw)$", "[모델 추정] 단지의 연간 직접 운영비(시장가)·단지 부담 추정·세대당·건당 중앙값. 실제 금액 아님", "원", "연간/건당", "-", "estimate"),
    (r"^share_burden_", "[모델 추정] 단지 부담 구분 비율(소요비용 기재/외부 제공 추정/불명)", "주민 대상 기록", W30, "-", "estimate"),
    (r"^(share_label_low_confidence|share_sensitive_identifier|low_data_flag)$", "낮은 확신 라벨 비율 / 식별 패턴 포함 비율 / 주민 대상 기록 15건 미만이면 1(자료 부족)", "-", W30, "-", "qa"),
    (r"^need_N\d_records_(30m|12m)$", "필요 분야별 주민 대상 기록 수(30개월/12개월)", "건", "각 창", "0", "feature"),
    (r"^need_N\d_per_1000hh_year$", "필요 분야별 기록 ÷ 세대수 ×1000 ÷ 2.5년", "세대 1000당·연", W30, "-", "feature"),
    (r"^need_N\d_peer_pctile$", "같은 피어 그룹(공급유형×규모) 안 백분위(낮을수록 상대적 공급 적음)", "백분위", W30, "-", "feature"),
    (r"^gap_N\d_(flag|zero_12m)$", "[공급 공백] 최근 12개월 0건 또는 피어 하위 20% → 1 / 최근 12개월 0건 → 1. 필요의 정답이 아님", "-", W12, "-", "feature"),
    (r"^gap_need_domain_n$|^gap_need_domains$", "공급 공백으로 표시된 필요 분야 수·이름", "분야", W12, "-", "feature"),
    (r"^peer_cf_", "프로그램 구성 코사인 유사도 상위 8개 이웃 단지(기록 15건 이상)와 평균 유사도", "단지", W30, "이웃 없으면 빈 값", "feature"),
    (r"^complex_type_", "단지 유형(T1~Tk, T0=자료 부족) 및 실루엣·군집 중심까지 거리", "단지", W30, "T0", "label"),
    (r"^(first_|last_)?(complex_n|complex_months)", "단지×표준 유형 기록 수·활동 월 수", "건/월", W30, "0", "feature"),
    (r"^latent_c\d\d$", "단지×표준 유형 기록 수(log1p)의 NMF(k=8) 적재 비율(합=1). 공급 구성의 잠재 패턴이며 필요의 정답이 아님. 기록 15건 미만 단지는 빈 값", "점유율", W30, "자료 부족 단지는 빈 값", "feature"),
    (r"^latent_dominant$", "적재가 가장 큰 잠재 요인 번호", "-", W30, "빈 값", "label"),
    (r"^summary_ko$", "집계 특성에서 자동 생성한 단지 한 줄 요약(서술에 새 사실을 더하지 않음)", "-", W30, "-", "text"),
]

CAND_RULES = [
    (r"^(complex_id|complex_name|std_id|std_name|std_family)$", "후보 쌍의 키: 단지 ID·단지명·표준 프로그램", "-", "-", "없음", "id"),
    (r"^need_domain_primary$", "해당 표준 프로그램의 주 필요 분야(N1~N6)", "-", "-", "N0", "feature"),
    (r"^complex_n_records$|^complex_n_records_12m$|^complex_months_active$|^complex_adopted$", "이 단지의 해당 유형 기록 수(30·12개월)·활동 월 수·시행 여부(1/0). 주민 대상 범위(in_resident_scope=1) 기록만 센다(LLM이 직원·시설 범위로 본 기록은 제외). 미시행은 필요 없음의 정답이 아님", "건", "각 창", "0", "feature"),
    (r"^complex_months_since_last$", "해당 유형의 마지막 기록 이후 개월 수(2026-06-30 기준). 기록 없으면 결측", "월", W30, "빈 값", "feature"),
    (r"^global_adoption_rate(_12m)?$", "기록 15건 이상 단지 중 해당 유형을 1건 이상 시행한 비율(전체/최근 12개월)", "단지", "각 창", "-", "feature"),
    (r"^peer_group_adoption_rate$", "같은 피어 그룹(공급유형×규모) 안 채택률", "단지", W30, "그룹 3개 미만이면 전체 채택률", "feature"),
    (r"^cf_neighbor_adoption_rate$", "프로그램 구성 유사 이웃 8개 단지의 채택률(협업 필터링 신호)", "단지", W30, "이웃 없으면 전체 채택률", "feature"),
    (r"^gap_supply_candidate$", "이 단지에 0건이고 전체 채택률 10% 이상이면 1(공급 공백 후보; 필요 정답 아님)", "-", W30, "-", "feature"),
    (r"^fills_gap_domain$", "해당 유형의 주 필요 분야가 이 단지의 공급 공백 분야이면 1", "-", W12, "-", "feature"),
    (r"^domain_share_in_complex$|^family_share_in_complex$", "이 단지의 해당 필요 분야·가족 기록 비율", "주민 대상 기록", W30, "N0이면 빈 값", "feature"),
    (r"^peer_minus_complex_gap$", "피어 채택률 − 이 단지 시행 여부(1/0). 양수면 피어는 하는데 이 단지는 안 하는 정도", "-", W30, "-", "feature"),
    (r"^season_share_next_month$|^std_seasonality_cv$", "해당 유형 기록 중 다음 달(7월) 시작 비율 / 월별 변동계수(계절성)", "-", W30, "-", "feature"),
    (r"^std_est_cost_mid_median_krw$|^cost_ratio_to_complex_median$", "[모델 추정] 유형 건당 예산 중앙값 / 이 단지 건당 예산 중앙값 대비 비율", "원/배", "건당", "분모 0이면 빈 값", "estimate"),
    (r"^std_participants_total_median$|^std_participation_per_100hh_median$", "해당 유형의 참여인원 기록 중앙값과 세대 100당 참여 중앙값", "명", W30, "-", "feature"),
    (r"^redundancy_(max|top3_mean)_sim_12m$", "후보 유형과 이 단지가 최근 12개월에 시행한 다른 유형 간 속성(목적·서비스·방식·대상·운영) 코사인 유사도의 최대/상위3 평균. 높을수록 기존 활동과 중복 가능(보완 판단은 별도)", "0~1", W12, "시행 없으면 0", "feature"),
    (r"^partner_fit$", "후보 유형이 통상 연계하는 협력기관 유형(원문 언급 비율 가중) 중 이 단지가 3건 이상 연계해 본 유형의 비중. 현재 기관 가용성의 확인이 아님", "0~1", W30, "협력기관 언급이 없는 유형은 빈 값", "feature"),
    (r"^ops_(event|regular)_gap$", "후보 유형의 행사형/정기형(Y·P) 비율 − 이 단지의 같은 비율. 양수면 후보가 단지의 기존 운영 방식보다 더 행사형/정기형", "비율 차", W30, "-", "feature"),
    (r"^participants_ratio_to_complex_median$", "후보 유형의 참여인원 기록 중앙값 ÷ 이 단지 기록의 중앙값(규모 적합)", "배", W30, "분모 0이면 빈 값", "feature"),
    (r"^households$|^low_data_complex$", "단지 세대수 / 주민 대상 기록 15건 미만이면 1", "-", W30, "-", "feature"),
]


def build_catalog(df, level, rules):
    out = []
    for c in df.columns:
        m = _match(rules, c)
        kind, nuniq, rng = _summ(df[c])
        if m is None:
            m = ("(설명 미작성)", "", "", "", "")
        out.append(dict(level=level, feature=c, role=m[4], definition=m[0], unit_denominator=m[1], window=m[2], missing_handling=m[3],
                        dtype=str(df[c].dtype), non_null_rate=round(float(df[c].notna().mean()), 4), n_unique=nuniq, value_summary=rng,
                        version=GEN_VERSION))
    return pd.DataFrame(out)


DICT_RULES = [
    (r"^(std_id|std_name|std_family|std_family_label)$", "표준 프로그램 유형 ID·명칭·가족(목적·대상·제공 방식이 같은 활동의 묶음)", "-", "-", "없음", "id"),
    (r"^(scope|scope_label|recommendable)$", "기록 범위 / 추천 후보 여부(주민 프로그램·세대 지원 범위이고 미분류가 아니면 1)", "-", "-", "없음", "label"),
    (r"^(purpose_primary|purpose_primary_label|purpose_all|need_domains_def)$", "유형 정의의 주·부수 복지 목적과 v4 필요 분야 대응", "-", "-", "빈 값", "label"),
    (r"^(target_default|service_default|mode_default|ops_typical|season_tag|effect_default|resource_default)$", "유형 정의의 통상 대상·서비스·제공 방식·운영 방식·계절 연동·효과·자원(사전 정의이며 원문 사실이 아님)", "-", "-", "빈 값", "label"),
    (r"^(budget_archetype|budget_assumption)$", "예산 추정에 쓰는 비용 구조 아키타입과 가정 설명(budget_assumptions.csv 참조)", "-", "-", "-", "estimate"),
    (r"^(keyword_rule|name_only_rule|theme_rule|exclude_rule|rule_specificity|rule_priority)$", "유형 판정 규칙(정규식, compact 텍스트 적용), 명확도(H/M/L)·우선순위", "-", "-", "-", "evidence"),
    (r"^n_records$|^n_complexes$|^adoption_rate$|^records_per_adopting_complex_median$", "해당 유형 기록 수 / 시행 단지 수 / 전체 단지 대비 채택률 / 시행 단지당 기록 중앙값", "건·단지", W30, "0", "feature"),
    (r"^(first_start_date|last_start_date)$", "해당 유형 첫·마지막 기록 시작일", "일", W30, "기록 없으면 빈 값", "feature"),
    (r"^n_(2024|2025|2026h1|recent12m|complexes_recent12m)$", "연도별·최근 12개월 기록 수 / 최근 12개월 시행 단지 수(2026은 상반기만)", "건", "각 창", "0", "feature"),
    (r"^(month_peak|month_peak_share|seasonality_cv)$", "최다 기록 월·그 비중·월별 변동계수(계절성)", "-", W30, "-", "feature"),
    (r"^month_share_\d\d$", "시작월별 기록 비율(합=1)", "기록", W30, "-", "feature"),
    (r"^op_(alw|reg|evt|adh|sea)_(Y|YP)_share$", "운영 특성 5종 확정(Y)·확정+개연(YP) 기록 비율", "기록", W30, "-", "feature"),
    (r"^(single_day_share|activity_count_median|duration_days_median)$", "당일 비율 / 활동횟수·기간 중앙값", "-", W30, "-", "feature"),
    (r"^participants_(total|individual)_(median|p90)$|^participation_per_100hh_median$", "참여인원 기록 중앙값·90분위 / 세대 100당 참여 중앙값(고유 주민 수 아님)", "명", W30, "-", "feature"),
    (r"^est_(cost_mid_median_krw|cost_mid_p10_krw|cost_mid_p90_krw|burden_mid_median_krw)$", "[모델 추정] 건당 직접 운영비(시장가) 중앙·10·90분위 / 단지 부담 추정 중앙값. 실제 금액 아님", "원", "건당", "-", "estimate"),
    (r"^share_(cost_|subject_)", "원본 소요비용분류·예산주체 구성 비율('기타'는 금액 아님)", "기록", W30, "-", "feature"),
    (r"^(share_mou|share_external_contest|mean_org_count_raw|partner_org_top3|partner_mention_rate|target_explicit_top3)$", "업무협약·외부공모 비율 / 원본 참여기관수 평균 / 원문 언급 협력기관 상위 3 / 협력기관 언급 비율 / 원문 명시 대상 상위 3", "-", W30, "-", "feature"),
    (r"^definition_ko$", "유형의 속성(목적·서비스·방식·대상·운영)을 풀어 쓴 사전 정의 문장", "-", "-", "-", "label"),
    (r"^(example_source_rows|example_contents|partner_keywords_top5)$", "원본 출처 행 번호(서로 다른 제목 8건)·내용 예시 3건·원문에 언급된 협력기관 키워드 상위 5", "-", "-", "빈 값", "evidence"),
    (r"^share_support_unit_", "v4 지원 단위(단지 전체/일부 가구/안부·관계) 해당 기록 비율(중복 가능)", "기록", W30, "-", "feature"),
    (r"^(llm_or_rule_confidence_high_share|alias_distinct_titles|alias_examples|hq_template_share)$", "라벨 high 확신 비율 / 서로 다른 정규화 제목 수 / 대표 별칭 예시(건수) / 본부 공통 캠페인형 비율", "-", W30, "-", "qa"),
    (r"^latent_c\d\d$", "표준 유형의 NMF 요인 구성(요인별 비중, 합=1). 단지 적재와 짝을 이룸", "점유율", W30, "자료 부족 유형은 빈 값", "feature"),
]
