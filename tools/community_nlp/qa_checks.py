# -*- coding: utf-8 -*-
"""전수 정합성·무결성·강건성 점검. 각 점검은 (id, 분류, 설명, 결과값, 기준, 판정, 상세)로 기록한다."""
import re
import random
import numpy as np
import pandas as pd

from . import taxonomy as TX
from .std_programs import BY_ID
from .classify import classify_row
from .text_utils import has_household_identifier

_VALID_STATES = {"Y", "P", "N", "U"}


def _split(s):
    return [x for x in str(s).split("|") if x]


def _chk(out, cid, cat, desc, value, expected, ok, detail=""):
    out.append(dict(check_id=cid, category=cat, description=desc, result=value, expected=expected,
                    status=("PASS" if ok else "FAIL"), detail=detail))


def run_checks(raw, rows, dictionary, cf, cand, long, std_ids, id_table=None):
    out = []
    n = len(rows)
    # ── 무결성 ──
    _chk(out, "C01", "무결성", "원본 행 수와 분석 행 수 일치", n, len(raw), n == len(raw))
    sr = rows["source_row"]
    _chk(out, "C02", "무결성", "source_row가 유일하고 원본 엑셀 행 번호(2행 이상)와 같은 집합", int(sr.nunique()), len(raw),
         sr.nunique() == len(raw) and sr.min() >= 2 and set(sr) == set(raw["source_row"]))
    _chk(out, "C03", "무결성", "record_id 유일", int(rows["record_id"].nunique()), n, rows["record_id"].nunique() == n)
    m = rows.merge(raw[["source_row", "커뮤니티명", "활동내용", "단지명", "활동횟수", "참여인원_계", "세대수", "커뮤니티장소명"]], on="source_row", how="left")
    ok_txt = int(((m["program_name_raw"] == m["커뮤니티명"]) & (m["activity_content_raw"] == m["활동내용"]) &
                  (m["complex_name"] == m["단지명"]) & (m["place_raw"] == m["커뮤니티장소명"])).sum())
    _chk(out, "C04", "무결성", "원문 텍스트·단지명·장소가 원본과 100% 동일(source_row 조인)", ok_txt, n, ok_txt == n)
    ok_num = int(((m["participants_total"] == m["참여인원_계"]) & (m["households"] == m["세대수"]) &
                  (m["activity_count"].fillna(-1) == m["활동횟수"].fillna(-1))).sum())
    _chk(out, "C05", "무결성", "참여인원_계·세대수·활동횟수가 원본과 100% 동일", ok_num, n, ok_num == n)
    _chk(out, "C06", "무결성", "참여인원_계 총합 보존", int(rows["participants_total"].sum()), int(raw["참여인원_계"].sum()),
         int(rows["participants_total"].sum()) == int(raw["참여인원_계"].sum()))
    if id_table is not None:
        idm = dict(zip(id_table["단지명"], id_table["complex_id"]))
        ok_id = int((rows["complex_id"] == rows["complex_name"].map(idm)).sum())
        _chk(out, "C07", "무결성", "모든 행의 complex_id가 단지통합 엑셀의 단지명 기준 ID와 일치", ok_id, n, ok_id == n)
        out_of_table = int((~rows["complex_name"].isin(idm)).sum())
        _chk(out, "C08", "무결성", "단지통합 엑셀에 없는 단지의 행 수(제외 대상이므로 0)", out_of_table, 0, out_of_table == 0)
        one2one = int(cf["complex_id"].is_unique and cf["complex_name"].is_unique and cand.groupby("complex_id")["complex_name"].nunique().max() == 1)
        _chk(out, "C09", "무결성", "단지 집계·후보 표에서 complex_id와 단지명이 1:1", one2one, 1, one2one == 1)
    # ── 코드 도메인 ──
    _chk(out, "C10", "도메인", "std_id가 사전(또는 Z99)에 존재", int((~rows["std_id"].isin(std_ids)).sum()), 0, (~rows["std_id"].isin(std_ids)).sum() == 0)
    _chk(out, "C11", "도메인", "scope 값 유효", int((~rows["scope"].isin(TX.SCOPES)).sum()), 0, (~rows["scope"].isin(TX.SCOPES)).sum() == 0)
    bad = 0
    for c in ["op_always", "op_regular", "op_event", "op_adhoc", "op_seasonal"]:
        bad += int((~rows[c].isin(_VALID_STATES)).sum())
    _chk(out, "C12", "도메인", "운영 특성 5종 값이 Y/P/N/U", bad, 0, bad == 0)
    def _bad_codes(col, valid):
        return sum(1 for v in rows[col] for x in _split(v) if x not in valid)
    for cid, col, valid, desc in [("C13", "purpose_primary", set(TX.PURPOSES) | {""}, "주 목적 코드 유효"),
                                  ("C14", "purpose_secondary", set(TX.PURPOSES), "부수 목적 코드 유효"),
                                  ("C15", "target_explicit", set(TX.TARGETS), "명시 대상 코드 유효"),
                                  ("C16", "mode_explicit", set(TX.MODES), "제공 방식 코드 유효"),
                                  ("C17", "partner_org_codes", set(TX.ORGS), "협력기관 코드 유효"),
                                  ("C18", "effect_explicit", set(TX.EFFECTS), "효과 코드 유효"),
                                  ("C19", "resource_explicit", set(TX.RESOURCES), "자원 코드 유효"),
                                  ("C20", "need_domains", set(TX.NEED_DOMAINS), "필요 분야 코드 유효")]:
        b = _bad_codes(col, valid)
        _chk(out, cid, "도메인", desc, b, 0, b == 0)
    nn = rows[["std_id", "scope", "op_always", "op_regular", "op_event", "op_adhoc", "op_seasonal", "start_date"]].isna().sum().sum()
    _chk(out, "C21", "도메인", "핵심 라벨·일자 결측 없음", int(nn), 0, nn == 0)
    ok_scope = int((rows["in_resident_scope"] == rows["scope"].isin(TX.RESIDENT_SCOPES).astype(int)).sum())
    _chk(out, "C22", "도메인", "in_resident_scope가 scope와 일치", ok_scope, n, ok_scope == n)
    # ── 논리 일관성(경고성) ──
    alw_single = int(((rows["op_always"] == "Y") & (rows["single_day_flag"] == 1)).sum())
    _chk(out, "C30", "논리", "상시형=Y이면서 당일 기록(원문 상시 명시 vs 일정 상충, 검토 대상)", alw_single, "참고(0이 이상적)", True, f"{alw_single}건은 op_flags에 표시")
    evt_alw = int(((rows["op_event"] == "Y") & (rows["op_always"] == "Y")).sum())
    _chk(out, "C31", "논리", "행사형=Y와 상시형=Y 동시(상충, 검토 대상)", evt_alw, "참고", True)
    reg_n_multi = int(((rows["op_regular"] == "N") & (rows["activity_count"] >= 3) & (rows["duration_days"] >= 14)).sum())
    _chk(out, "C32", "논리", "정기형=N인데 3회 이상·14일 이상 기록(상충)", reg_n_multi, 0, reg_n_multi == 0)
    sea_n_cue = int(((rows["op_seasonal"] == "N") & rows["op_calendar_tag"].isin(["명절", "여름", "겨울", "봄", "가을", "연말연시"])).sum())
    _chk(out, "C33", "논리", "계절형=N인데 계절·명절 태그 존재", sea_n_cue, 0, sea_n_cue == 0)
    unit_bad = int(((rows["scope"].isin(["ADMIN", "STAFF"])) & (rows["support_unit_household"] == 1)).sum())
    _chk(out, "C34", "논리", "행정·직원 범위 기록에 세대 직접 지원 단위가 부여되지 않음", unit_bad, 0, unit_bad == 0)
    mid_ok = int(((rows["est_cost_low_krw"] <= rows["est_cost_mid_krw"]) & (rows["est_cost_mid_krw"] <= rows["est_cost_high_krw"]) &
                  (rows["est_burden_mid_krw"] <= rows["est_cost_mid_krw"] + 1)).sum())
    _chk(out, "C35", "논리", "예산 추정 하한≤중앙≤상한, 부담≤중앙", mid_ok, n, mid_ok == n)
    # ── 일자·수치 이상 ──
    _chk(out, "C40", "원자료", "종료일 이상(2027 이후/시작보다 빠름) 기록 수(결측 처리됨)", int(rows["date_anomaly_flag"].sum()), "관측값 보고", True,
         "duration_days를 결측으로 둠")
    _chk(out, "C41", "원자료", "활동횟수 0 / 60 초과 기록 수", f"{int(rows['activity_count_zero_flag'].sum())} / {int(rows['activity_count_gt60_flag'].sum())}", "관측값 보고", True)
    from .build_rows import PART_COLS
    raw_mis = int((raw["참여인원_계"] != raw[PART_COLS].sum(axis=1)).sum())
    _chk(out, "C42", "원자료", "참여인원_계≠세부 합 기록 수(원자료 불일치, 삭제하지 않음)", int(rows["participants_total_mismatch_flag"].sum()), f"원본 재계산 {raw_mis}",
         int(rows["participants_total_mismatch_flag"].sum()) == raw_mis)
    _chk(out, "C43", "원자료", "참여인원_계=0 기록 수(미상과 구분 불가, 0으로 유지)", int(rows["participants_zero_flag"].sum()), "관측값 보고", True)
    dup_cnt = int(rows["dup_exact_flag"].sum() - rows["dup_exact_first_flag"].where(rows["dup_exact_flag"] == 1, 0).sum())
    raw_dup = int(raw.duplicated([c for c in raw.columns if c != "source_row"]).sum())
    _chk(out, "C44", "원자료", "완전 동일 추가 행 수(삭제하지 않고 플래그)", dup_cnt, f"원본 재계산 {raw_dup}", dup_cnt == raw_dup)
    # ── 개인정보 ──
    resid = sum(1 for a, b, c in zip(rows["program_name_masked"], rows["activity_content_masked"], rows["place_masked"]) if has_household_identifier(a, b, c))
    _chk(out, "C50", "개인정보", "마스킹 텍스트(활동명·활동내용·장소명)에 남은 동호수·이름 패턴 수(마스킹 규칙과 별도로 작성한 점검용 정규식)", resid, 0, resid == 0)
    _chk(out, "C51", "개인정보", "원문에 식별 패턴이 있어 마스킹이 원문을 바꾼 기록 수(sensitive_identifier_flag=1)", int(rows["sensitive_identifier_flag"].sum()), "관측값 보고", True)
    tok = (rows["program_name_masked"].str.contains(r"\[(?:동호|호|이름|전화)\]", regex=True) | rows["activity_content_masked"].str.contains(r"\[(?:동호|호|이름|전화)\]", regex=True)
           | rows["place_masked"].str.contains(r"\[(?:동호|호|이름|전화)\]", regex=True))
    tok_noflag = int((tok & (rows["sensitive_identifier_flag"] == 0)).sum())
    loose = re.compile(r"\d{2,4}\s*동\s*\d{2,4}(?![\d가-힣])|(?<![\d\-./])\d{3,4}\s*-\s*\d{3,4}(?![\d])|\d\*+")
    n_loose = int(sum(1 for a_, b_, c_ in zip(rows["program_name_masked"], rows["activity_content_masked"], rows["place_masked"]) if any(loose.search(t) for t in (a_, b_, c_))))
    _chk(out, "C53", "개인정보", "마스킹 텍스트에서 느슨한 정규식(동+번호, 번호-번호, 숫자+별표)에 걸리는 후보 행 수(건물 번호·단지명·산식도 포함되므로 참고용)", n_loose, "관측값 보고", True)
    _chk(out, "C52", "개인정보", "마스킹 토큰([동호]·[호]·[이름]·[전화])이 있는 행은 모두 sensitive_identifier_flag=1", tok_noflag, 0, tok_noflag == 0)
    # ── 집계 대사 ──
    _chk(out, "C60", "집계 대사", "단지 집계 n_records_all 합 = 전체 행 수", int(cf["n_records_all"].sum()), n, int(cf["n_records_all"].sum()) == n)
    res_n = int(rows["in_resident_scope"].sum())
    _chk(out, "C61", "집계 대사", "단지 집계 n_records_resident 합 = 주민 대상 기록 수", int(cf["n_records_resident"].sum()), res_n, int(cf["n_records_resident"].sum()) == res_n)
    res_part = int(rows.loc[rows["in_resident_scope"] == 1, "participants_total"].sum())
    _chk(out, "C62", "집계 대사", "단지 집계 참여인원 합 = 주민 대상 기록 합", int(cf["participants_total_sum"].fillna(0).sum()), res_part, int(cf["participants_total_sum"].fillna(0).sum()) == res_part)
    fcols = [c for c in cf.columns if c.startswith("share_family_")]
    fs = cf.loc[cf["n_records_resident"] > 0, fcols].sum(axis=1)
    _chk(out, "C63", "집계 대사", "가족 비율 합(미분류 F99 포함) = 1(±0.003, 소수 반올림 허용)", f"min={fs.min():.4f},max={fs.max():.4f}", "1", bool(((fs - 1).abs() < 0.003).all()))
    mcols = [f"month_share_{m:02d}" for m in range(1, 13)]
    ms = cf.loc[cf["n_records_resident"] > 0, mcols].sum(axis=1)
    _chk(out, "C64", "집계 대사", "월별 비율 합 = 1(±0.003, 소수 반올림 허용)", f"min={ms.min():.4f},max={ms.max():.4f}", "1", bool(((ms - 1).abs() < 0.003).all()))
    ent_ok = bool((cf.loc[cf["std_richness"] > 1, "std_entropy"] <= np.log(cf.loc[cf["std_richness"] > 1, "std_richness"]) + 1e-6).all())
    _chk(out, "C65", "집계 대사", "엔트로피 ≤ ln(종류 수)", "통과" if ent_ok else "위반", "통과", ent_ok)
    _chk(out, "C66", "집계 대사", "사전 n_records 합 = 전체 행 수", int(dictionary["n_records"].sum()), n, int(dictionary["n_records"].sum()) == n)
    dup_pairs = int(cand.duplicated(["complex_name", "std_id"]).sum())
    _chk(out, "C67", "집계 대사", "후보 표에 (단지, 유형) 중복 없음", dup_pairs, 0, dup_pairs == 0)
    adopted = int(cand["complex_adopted"].sum())
    long_ct = int(long[long["std_id"].isin(cand["std_id"].unique())].shape[0])
    _chk(out, "C68", "집계 대사", "후보 표 시행(1) 수 = 단지×유형 행렬의 비영 셀 수", adopted, long_ct, adopted == long_ct)
    # ── 결정성 ──
    g = rows[rows["label_source"] == "rule"].groupby(["title_norm", rows["activity_content_masked"]])["std_id"].nunique()
    conflict = int((g > 1).sum())
    _chk(out, "C70", "결정성", "동일 정규화 제목+내용인데 규칙 라벨이 서로 다른 그룹 수", conflict, "참고(0 이상적)", True,
         "문맥 규칙(override)·분야/유형 보조점수 차이로 발생 가능")
    pend = int(((rows["label_source"] == "rule") & (rows["std_id_llm"] == "") & ((rows["needs_llm_review"] == 1) | (rows["std_confidence"] == "medium"))).sum())
    _chk(out, "C71", "결정성", "규칙이 불확실하거나 중간 확신인데 LLM 판정이 없는 행 수(판정 누락)", pend, 0, pend == 0)
    llm_rows = rows[rows["label_source"] == "llm"]
    mism = int(((llm_rows["std_id"] != llm_rows["std_id_llm"]) & ~llm_rows["std_override"].astype(str).str.contains("harmonize")).sum())
    _chk(out, "C72", "결정성", "LLM 확정 행의 std_id가 LLM 판정과 일치(계절 돌봄 B05→B01 통일 제외)", mism, 0, mism == 0)
    return pd.DataFrame(out)


def robustness_test(raw, n=2500, seed=11):
    """표현 변이에 대한 라벨 안정성: 공백 제거, 문장부호 치환, 연·월·차수 제거, 접미 추가에도 표준 유형이 유지되는 비율."""
    rng = random.Random(seed)
    sub = raw.sample(n=min(n, len(raw)), random_state=seed)
    def base(r):
        return classify_row(r["커뮤니티명"], r["활동내용"], r["커뮤니티유형"], r["분야"], r["문화예술공연여부"])["primary"]["id"]
    def strip_dates(s):
        s = re.sub(r"(20)?\d{2}\s*년도?", "", str(s))
        s = re.sub(r"\d{1,2}\s*월", "", s)
        s = re.sub(r"(제\s*)?\d+\s*(차시|차수|회차|차|회)", "", s)
        return s
    def add_suffix(s):
        return rng.choice(["", "2025년 ", "3월 "]) + str(s) + rng.choice([" 실시", " 행사 실시 보고", "(1차)", " 시행"])
    def scramble_space(s):
        s = str(s).replace(" ", "")
        out = []
        for ch in s:
            out.append(ch)
            if rng.random() < 0.08:
                out.append(" ")
        return "".join(out)
    tests = {
        "공백 제거": lambda s: str(s).replace(" ", ""),
        "공백 임의 삽입": scramble_space,
        "문장부호→밑줄": lambda s: re.sub(r"[\s\(\)\[\]·,]+", "_", str(s)),
        "연·월·차수 표기 제거": strip_dates,
        "접미·연월 표기 추가": add_suffix,
    }
    base_ids = [base(r) for _, r in sub.iterrows()]
    rows_out = []
    for name, fn in tests.items():
        same = 0
        for (_, r), b in zip(sub.iterrows(), base_ids):
            nm = fn(r["커뮤니티명"])
            ct = fn(r["활동내용"]) if name != "접미·연월 표기 추가" else r["활동내용"]
            v = classify_row(nm, ct, r["커뮤니티유형"], r["분야"], r["문화예술공연여부"])["primary"]["id"]
            same += int(v == b)
        rows_out.append(dict(perturbation=name, n=len(sub), label_unchanged_rate=round(same / len(sub), 4)))
    return pd.DataFrame(rows_out)
