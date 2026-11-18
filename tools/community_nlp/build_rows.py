# -*- coding: utf-8 -*-
"""프로그램(행) 단위 분석 테이블 생성 — 원본 전 행(전수). 모든 행은 source_row(엑셀 행 번호)로 원본과 연결된다."""
import re
import numpy as np
import pandas as pd

from . import taxonomy as TX
from .std_programs import BY_ID
from .classify import classify_row
from .text_utils import compact, title_norm, mask_sensitive, was_masked, umbrella_tags
from .attrs import (extract_targets, extract_orgs, extract_purposes, need_domains, extract_effects, extract_resources,
                    extract_modes, FUNDING_CUES, extract_numeric_mentions)
from .ops import derive_ops, primary_op
from . import budget as BG

PART_COLS = ["참여인원_국가", "참여인원_지자체", "참여인원_의회의원", "참여인원_관리소", "참여인원_임차인대표회의", "참여인원_복지시설단체",
             "참여인원_한국토지주택공사", "참여인원_공기업(한국토지주택공사제외)", "참여인원_민간기업", "참여인원_기타단체", "참여인원_개인"]
INST_COLS = [c for c in PART_COLS if c != "참여인원_개인"]
OBS_END = pd.Timestamp("2026-06-30")
OBS_START = pd.Timestamp("2024-01-01")


# 최종본(202401~202606) 열 이름 오타 보정: '한국주택토지공사제외' → '한국토지주택공사제외'(이전 파일과 동일한 이름으로 통일)
COL_RENAME = {"참여인원_공기업(한국주택토지공사제외)": "참여인원_공기업(한국토지주택공사제외)"}


def load_raw(path, sheet=None):
    xl = pd.ExcelFile(path)
    if sheet is None:
        sheet = "Sheet1" if "Sheet1" in xl.sheet_names else xl.sheet_names[0]   # 이전 파일은 Sheet1, 최종본은 단일 시트(이름이 다름)
    df = xl.parse(sheet, dtype=object).rename(columns=COL_RENAME)
    df.insert(0, "source_row", np.arange(2, len(df) + 2))   # 엑셀 행 번호(헤더=1행)
    for c in ["세대수", "활동횟수", "참여인원_계", "참여기관수"] + PART_COLS:
        df[c] = pd.to_numeric(df[c])
    df["커뮤니티시작일자"] = pd.to_datetime(df["커뮤니티시작일자"])
    df["커뮤니티종료일자"] = pd.to_datetime(df["커뮤니티종료일자"], errors="coerce")  # pandas 3: 9999-12-31 유지
    df.attrs["sheet"] = sheet
    return df


def _lab(code_map, codes, sep="|"):
    return sep.join(code_map.get(c, c) for c in codes)


def _season_of(m):
    return {12: "겨울", 1: "겨울", 2: "겨울", 3: "봄", 4: "봄", 5: "봄", 6: "여름", 7: "여름", 8: "여름", 9: "가을", 10: "가을", 11: "가을"}.get(m, "")


_SEASONAL_CARE = re.compile(r"(명절|설맞이|추석|새해|연말|폭염|무더위|한파|겨울나기|혹서|혹한|여름나기)")


def _confidence(res):
    t = res["primary"]
    if t["id"] == "Z99":
        return "low"
    s, mg = res["score"], res["margin"]
    if res["fallback"] == "umbrella_default":
        return "low"
    if res["evidence_field"] == "content":      # 내용에서만 근거를 찾은 경우 high 불가
        return "medium" if (s >= 1.5 and mg >= 0.8) else "low"
    if t["spec"] == "L":
        return "low" if s < 1.6 else "medium"
    if s >= 3.0 and mg >= 1.0:
        return "high"
    if s >= 1.5 and mg >= 0.5:
        return "medium"
    return "low"


def build_row_table(raw, llm=None, ops_from_llm=False):
    """llm: 독립 LLM 라벨러 결과(DataFrame: source_row, llm_scope, llm_std, llm_p1, llm_p2, llm_tg, llm_conf, llm_op_*).
    llm 행은 표준 유형·범위·목적·대상을 LLM 판정으로 확정(label_source=llm)하고 하위 속성은 새 유형으로 다시 계산한다."""
    n = len(raw)
    rows = []
    res_list = []
    for _, r in raw.iterrows():
        res_list.append(classify_row(mask_sensitive(r["커뮤니티명"]), mask_sensitive(r["활동내용"]), r["커뮤니티유형"], r["분야"], r["문화예술공연여부"]))

    tn = [title_norm(mask_sensitive(r["커뮤니티명"]), r["단지명"]) for _, r in raw.iterrows()]     # 이름 조각이 제목 키에 남지 않도록 마스킹한 명칭으로 만든다
    df = raw[["source_row", "단지명", "공급유형", "세대수", "분야", "커뮤니티유형", "문화예술공연여부", "외부공모사업여부", "업무협약여부",
              "커뮤니티명", "활동내용", "커뮤니티장소명", "소요비용분류", "예산주체", "참여기관수", "활동횟수", "참여인원_계"] + PART_COLS].copy()
    df["start_date"] = raw["커뮤니티시작일자"]
    df["end_date"] = raw["커뮤니티종료일자"]
    df["title_norm"] = tn

    # ── 반복 정보(단지 × 정규화 제목) ──
    df = df.sort_values(["단지명", "title_norm", "start_date", "source_row"]).reset_index(drop=True)
    grp = df.groupby(["단지명", "title_norm"], sort=False)
    df["repeat_n"] = grp["source_row"].transform("size")
    df["repeat_index"] = grp.cumcount() + 1
    df["repeat_months"] = grp["start_date"].transform(lambda s: s.dt.to_period("M").nunique())
    df["gap_prev_days"] = grp["start_date"].diff().dt.days
    df["repeat_gap_med"] = grp["gap_prev_days"].transform("median")
    df = df.sort_values("source_row").reset_index(drop=True)
    res_by_row = dict(zip(raw["source_row"], res_list))
    llm_map = {} if llm is None or len(llm) == 0 else llm.drop_duplicates("source_row").set_index("source_row").to_dict("index")

    out = []
    for _, r in df.iterrows():
        sr = int(r["source_row"])
        res = res_by_row[sr]
        t = res["primary"]
        lr = llm_map.get(sr)
        use_llm = False
        rule_std_id = t["id"]
        rule_conf = _confidence(res)
        rule_reasons = []
        if t["id"] == "Z99":
            rule_reasons.append("unmatched")
        if res["fallback"] == "umbrella_default":
            rule_reasons.append("umbrella_only")
        if rule_conf == "low" and t["id"] != "Z99":
            rule_reasons.append("low_confidence")
        if res["override"]:
            rule_reasons.append("override")
        if res["secondary"] and res["margin"] < 0.6:
            rule_reasons.append("close_competitor")
        # 정책: 규칙이 불확실(검토 사유 있음)하거나 force 지정된 행만 LLM 판정을 최종 라벨로 확정한다.
        # 그 밖의 행은 LLM 결과를 감사(llm_*) 열로만 보존하고 규칙 라벨을 유지한다.
        harmonized = ""
        if lr is not None and str(lr.get("llm_std", "")) in BY_ID and (rule_reasons or bool(lr.get("force", False))):
            t = BY_ID[lr["llm_std"]]
            use_llm = True
            # 사전 설계 정합: 명절·폭염·한파 등 계절 돌봄 물품 전달은 B01로 통일(지침 v1.1의 '관리홈닥터 세대→B05' 문구와 규칙 엔진 설계의 불일치 보정)
            if t["id"] == "B05" and _SEASONAL_CARE.search(compact(r["커뮤니티명"]) + compact(r["활동내용"])):
                t = BY_ID["B01"]
                harmonized = "harmonize:B05->B01"
        if lr is not None and not use_llm and str(lr.get("llm_std", "")) in ("NEW", "Z99") and rule_conf != "high":
            rule_reasons.append("llm_no_matching_type")   # LLM이 맞는 유형이 없다(NEW)·내용 불명(Z99)이라 했고 규칙 라벨도 확신이 높지 않음 → 사람 검토 대상
        nc = compact(r["커뮤니티명"])
        cc = compact(r["활동내용"])
        scope_for_ops = lr.get("llm_scope") if (use_llm and lr.get("llm_scope") in TX.SCOPES) else t["scope"]
        rep = dict(n=int(r["repeat_n"]), months=int(r["repeat_months"]),
                   gap_med=(None if pd.isna(r["repeat_gap_med"]) else float(r["repeat_gap_med"])))
        o = derive_ops(nc, cc, r["start_date"] if pd.notna(r["start_date"]) else None,
                       r["end_date"] if pd.notna(r["end_date"]) else pd.Timestamp("2099-12-31"),
                       r["활동횟수"], t.get("ops", ""), t.get("season", ""), rep, scope_for_ops)
        st = o["state"]
        st_rule = dict(st)
        if use_llm and ops_from_llm:
            for k in ("ALW", "REG", "EVT", "ADH", "SEA"):
                v = lr.get("llm_op_" + k, "")
                if v in ("Y", "P", "N", "U"):
                    st[k] = v
        # 목적
        tp = extract_purposes(nc, cc, t.get("pur", ""))
        if use_llm and lr.get("llm_p1") in TX.PURPOSES:
            sec_l = [x for x in str(lr.get("llm_p2", "")).split("|") if x in TX.PURPOSES and x != lr["llm_p1"]]
            tp = dict(primary=lr["llm_p1"], secondary=sec_l[:2], secondary_text=[])
        prim = tp["primary"]
        pur_all = ([prim] if prim else []) + tp["secondary"] + tp["secondary_text"]
        needs = need_domains(pur_all)
        # 대상
        type_tgt = [x for x in (t.get("tgt", "") or "").split("+") if x]
        tg = extract_targets(nc, cc, type_tgt, scope_for_ops)
        if use_llm:
            extra = [x for x in str(lr.get("llm_tg", "")).split("|") if x in TX.TARGETS and x not in tg["explicit"]]
            if extra:
                tg["explicit"] = tg["explicit"] + extra
                tg["inferred"] = [x for x in tg["inferred"] if x not in extra]
                tg["basis"] = "mixed" if tg["inferred"] else "text"
        # 협력기관·방식·효과·자원
        orgs = extract_orgs(nc, cc)
        md = extract_modes(nc, cc, [x for x in (t.get("mode", "") or "").split("+") if x], orgs, r["업무협약여부"], r["외부공모사업여부"])
        ef = extract_effects(nc, cc, [x for x in (t.get("eff", "") or "").split("+") if x])
        rs = extract_resources(nc, cc, [x for x in (t.get("res", "") or "").split("+") if x])
        svc = [x for x in (t.get("svc", "") or "").split("+") if x]
        scope = t["scope"]
        if use_llm and lr.get("llm_scope") in TX.SCOPES:
            scope = lr["llm_scope"]
        # 지원 단위(v4)
        modes_all = md["explicit"] + md["inferred"]
        tgt_all = tg["explicit"] + tg["inferred"]
        u3 = ("S10" in svc) or prim == "P03" or bool(re.search(r"안부|말벗|살피|방문확인", nc + cc))
        u2 = scope == "HOUSEHOLD_SUPPORT" or (("M1" in modes_all or "M9" in modes_all) and any(x in tgt_all for x in ("VUL", "ELD1", "DIS", "CRI"))
                                              and "M3" not in md["explicit"])
        if scope in ("ADMIN", "STAFF", "GOVERNANCE", "FACILITY_MGMT"):
            u2 = False
            u3 = u3 and scope != "ADMIN"
        u1 = scope in ("PROGRAM", "GOVERNANCE") and (any(m in modes_all for m in ("M3", "M4", "M5", "M2", "M10")) or "ALL" in tg["explicit"])
        # 신뢰도·검토 필요
        conf = rule_conf
        if use_llm:
            conf = "llm-" + {"H": "high", "M": "medium", "L": "low"}.get(str(lr.get("llm_conf", "")), "medium")
        reasons = list(rule_reasons)
        review_reason_rule = "|".join(rule_reasons)
        if use_llm:
            reasons = []
        # 예산 추정
        sec_orgs = {k: v for k, v in orgs.items() if k != "OG13"}
        b = BG.estimate(t.get("cost", "NONE"), r["활동횟수"], o["days"], r["참여인원_계"], r["참여인원_개인"], r["참여인원_관리소"],
                        r["소요비용분류"], r["예산주체"], bool(sec_orgs), r["업무협약여부"] == "Y", scope)
        # 참여
        inst_sum = int(sum(r[c] for c in INST_COLS))
        parts_sum = inst_sum + int(r["참여인원_개인"])
        total = int(r["참여인원_계"])
        hh = int(r["세대수"])
        cnt = r["활동횟수"]
        indiv = int(r["참여인원_개인"])
        end_year = None if pd.isna(r["end_date"]) else int(r["end_date"].year)
        sd = r["start_date"]
        place_masked = mask_sensitive(r["커뮤니티장소명"]) if pd.notna(r["커뮤니티장소명"]) else ""
        has_sens = was_masked(r["커뮤니티명"], r["활동내용"], r["커뮤니티장소명"] if pd.notna(r["커뮤니티장소명"]) else "")
        name_masked = mask_sensitive(r["커뮤니티명"])
        content_masked = mask_sensitive(r["활동내용"])
        nm_ = extract_numeric_mentions(name_masked, content_masked)
        same_nc = (compact(r["커뮤니티명"]) == compact(r["활동내용"]))
        sec_items = [x for x in res["secondary"] if x["id"] != t["id"]]
        ev_text, ev_field = res["evidence"], res["evidence_field"]
        if use_llm:
            ev_text, ev_field = str(lr.get("llm_why", "")), "llm"
        out.append(dict(
            source_row=sr,
            record_id="comm_%05d" % sr,
            complex_name=r["단지명"],
            supply_type=r["공급유형"],
            households=hh,
            field=r["분야"],
            raw_community_type=r["커뮤니티유형"],
            flag_culture_performance=int(r["문화예술공연여부"] == "Y"),
            flag_external_contest=int(r["외부공모사업여부"] == "Y"),
            flag_mou=int(r["업무협약여부"] == "Y"),
            program_name_raw=r["커뮤니티명"],
            activity_content_raw=r["활동내용"],
            place_raw=r["커뮤니티장소명"],
            program_name_masked=name_masked,
            activity_content_masked=content_masked,
            place_masked=place_masked,
            sensitive_identifier_flag=int(has_sens),
            title_norm=r["title_norm"],
            umbrella_tags="|".join(res["umbrella"]),
            # ── 표준화 ──
            scope=scope, scope_label=TX.SCOPES[scope], in_resident_scope=int(scope in TX.RESIDENT_SCOPES),
            std_family=t["fam"], std_family_label=TX.FAMILIES[t["fam"]],
            std_id=t["id"], std_name=t["name"],
            std_secondary_ids="|".join(x["id"] for x in sec_items),
            std_secondary_names="|".join(BY_ID[x["id"]]["name"] for x in sec_items),
            std_evidence=ev_text, std_evidence_field=ev_field,
            std_score=round(res["score"], 2), std_margin=round(res["margin"], 2), std_confidence=conf,
            std_override=("|".join(x for x in (res["override"], harmonized) if x)), std_fallback=res["fallback"],
            label_source=("llm" if use_llm else "rule"), review_reason=review_reason_rule, needs_llm_review=int(bool(reasons)),
            std_id_rule=rule_std_id, std_id_llm=(lr["llm_std"] if lr is not None else ""), llm_scope=(lr.get("llm_scope", "") if lr is not None else ""),
            llm_p1=(lr.get("llm_p1", "") if lr is not None else ""), llm_p2=(lr.get("llm_p2", "") if lr is not None else ""),
            llm_targets=(lr.get("llm_tg", "") if lr is not None else ""), llm_conf=(lr.get("llm_conf", "") if lr is not None else ""),
            llm_why=(lr.get("llm_why", "") if lr is not None else ""), llm_batch=(lr.get("batch", "") if lr is not None else ""), llm_new_name=(lr.get("llm_new_name", "") if lr is not None else ""),
            llm_ops=("" if lr is None else ",".join("%s=%s" % (k, lr.get("llm_op_" + k, "")) for k in ("ALW", "REG", "EVT", "ADH", "SEA"))),
            op_rule_states=",".join("%s=%s" % (k, st_rule[k]) for k in ("ALW", "REG", "EVT", "ADH", "SEA")),
            # ── 목적·필요분야 ──
            purpose_primary=prim, purpose_primary_label=TX.PURPOSES.get(prim, ""),
            purpose_secondary="|".join(tp["secondary"]), purpose_secondary_text_cue="|".join(tp["secondary_text"]),
            purpose_labels="|".join(TX.PURPOSES.get(p, p) for p in pur_all),
            need_domain_primary=(needs[0] if needs else ""), need_domains="|".join(needs),
            need_domain_labels="|".join(TX.NEED_DOMAINS.get(x, x) for x in needs),
            # ── 대상 ──
            target_explicit="|".join(tg["explicit"]), target_explicit_labels=_lab(TX.TARGETS, tg["explicit"]),
            target_type_default="|".join(tg["inferred"]), target_type_default_labels=_lab(TX.TARGETS, tg["inferred"]),
            target_basis=tg["basis"], target_age_text=tg["age"],
            # ── 서비스·방식 ──
            service_codes="|".join(svc), service_labels=_lab(TX.SERVICES, svc),
            mode_explicit="|".join(md["explicit"]), mode_explicit_labels=_lab(TX.MODES, md["explicit"]),
            mode_type_default="|".join(md["inferred"]), mode_type_default_labels=_lab(TX.MODES, md["inferred"]),
            support_unit_complex_wide=int(bool(u1)), support_unit_household=int(bool(u2)), support_unit_contact=int(bool(u3)),
            # ── 운영 특성 ──
            op_always=st["ALW"], op_regular=st["REG"], op_event=st["EVT"], op_adhoc=st["ADH"], op_seasonal=st["SEA"],
            op_primary=primary_op(st, o["basis"]),
            op_labels="|".join(TX.OPS[k] for k in ("ALW", "REG", "EVT", "ADH", "SEA") if st[k] in ("Y", "P")),
            op_labels_confirmed="|".join(TX.OPS[k] for k in ("ALW", "REG", "EVT", "ADH", "SEA") if st[k] == "Y"),
            op_basis=";".join("%s:%s" % (k, "/".join(v)) for k, v in o["basis"].items() if v),
            op_interval_days_est=o["interval_days"], op_interval_label=o["interval_label"], op_interval_basis=o["interval_basis"],
            op_series_no=o["series_no"], op_period_label=o["period_label"], op_calendar_tag=o["calendar_tag"],
            op_flags="|".join(o["flags"]),
            op_type_prior="|".join(TX.OPS[k] for k in [x for x in (t.get("ops", "") or "").split("+") if x]),
            # ── 협력·효과·자원 ──
            partner_org_codes="|".join(sorted(orgs)), partner_org_labels="|".join(TX.ORGS[k] for k in sorted(orgs)),
            partner_org_keywords="|".join(orgs[k] for k in sorted(orgs)), partner_org_n_text=len(orgs),
            effect_explicit="|".join(ef["explicit"]), effect_explicit_labels=_lab(TX.EFFECTS, ef["explicit"]),
            effect_type_default="|".join(ef["inferred"]), effect_type_default_labels=_lab(TX.EFFECTS, ef["inferred"]),
            resource_explicit="|".join(rs["explicit"]), resource_explicit_labels=_lab(TX.RESOURCES, rs["explicit"]),
            resource_type_default="|".join(rs["inferred"]), resource_type_default_labels=_lab(TX.RESOURCES, rs["inferred"]),
            funding_cue=int(bool(FUNDING_CUES.search(nc + cc))),
            text_households_n=nm_["households"], text_persons_n=nm_["persons"], text_amount_krw_max=nm_["won"], text_kg_max=nm_["kg"],
            text_item_count_max=nm_["items"], text_dates_n=nm_["dates"], text_sessions_n=nm_["sessions"],
            # ── 일정·횟수 ──
            start_date=sd.date().isoformat() if pd.notna(sd) else "",
            end_date_raw=("" if pd.isna(r["end_date"]) else r["end_date"].date().isoformat()),
            end_date=("" if (pd.isna(r["end_date"]) or "date_anomaly" in o["flags"]) else r["end_date"].date().isoformat()),   # 이상 종료일은 결측 처리(원문은 end_date_raw에 보존)
            start_year=int(sd.year), start_month=int(sd.month), start_quarter=int(sd.quarter), start_season=_season_of(int(sd.month)),
            duration_days=o["days"], single_day_flag=int(bool(o["single"])),
            year_end_end_date_flag=int(bool(o["year_end"])), date_anomaly_flag=int("date_anomaly" in o["flags"]),
            activity_count=(None if pd.isna(cnt) else int(cnt)),
            activity_count_zero_flag=int(not pd.isna(cnt) and cnt == 0),
            activity_count_gt60_flag=int(not pd.isna(cnt) and cnt > 60),
            # ── 참여 ──
            participants_total=total, participants_individual=indiv, participants_institutional=inst_sum,
            participants_staff_mgmt=int(r["참여인원_관리소"]), participants_tenant_council=int(r["참여인원_임차인대표회의"]),
            participants_total_mismatch_flag=int(total != parts_sum), participants_zero_flag=int(total == 0),
            institution_types_nonzero=int(sum(r[c] > 0 for c in INST_COLS)), org_count_raw=int(r["참여기관수"]),
            part_flag_national=int(r["참여인원_국가"] > 0), part_flag_local_gov=int(r["참여인원_지자체"] > 0),
            part_flag_council_member=int(r["참여인원_의회의원"] > 0), part_flag_welfare_org=int(r["참여인원_복지시설단체"] > 0),
            part_flag_lh=int(r["참여인원_한국토지주택공사"] > 0), part_flag_public_corp=int(r["참여인원_공기업(한국토지주택공사제외)"] > 0),
            part_flag_private_corp=int(r["참여인원_민간기업"] > 0), part_flag_other_org=int(r["참여인원_기타단체"] > 0),
            part_flag_tenant_council=int(r["참여인원_임차인대표회의"] > 0), part_flag_mgmt_office=int(r["참여인원_관리소"] > 0),
            participation_per_100hh=(round(total / hh * 100, 3) if hh else None),
            individual_per_100hh=(round(indiv / hh * 100, 3) if hh else None),
            participants_per_session=(round(total / cnt, 2) if (not pd.isna(cnt) and cnt > 0) else None),
            participants_over_households_flag=int(total > hh),
            scale_class=("none" if indiv == 0 else "xs(1-5)" if indiv <= 5 else "s(6-20)" if indiv <= 20 else "m(21-50)" if indiv <= 50
                         else "l(51-150)" if indiv <= 150 else "xl(151+)"),
            # ── 비용 구분 ──
            cost_class_raw=r["소요비용분류"], budget_subject_raw=r["예산주체"],
            budget_archetype=t.get("cost", "NONE"),
            est_cost_low_krw=b["low"], est_cost_mid_krw=b["mid"], est_cost_high_krw=b["high"],
            est_burden_class=b["burden"], est_burden_factor=b["factor"], est_burden_mid_krw=b["burden_mid"],
            est_n_effective=b["n_eff"], est_n_basis=b["n_basis"], est_sessions_used=b["sessions_used"],
            est_cost_band=BG.band(b["mid"]), est_flag="모델 추정치(관측 사실 아님)",
            # ── 반복·중복 ──
            repeat_n_in_complex=int(r["repeat_n"]), repeat_index=int(r["repeat_index"]), repeat_months_active=int(r["repeat_months"]),
            repeat_gap_prev_days=(None if pd.isna(r["gap_prev_days"]) else int(r["gap_prev_days"])),
            repeat_gap_median_days=(None if pd.isna(r["repeat_gap_med"]) else float(r["repeat_gap_med"])),
            # ── 텍스트 품질 ──
            name_len=len(str(r["커뮤니티명"])), content_len=len(str(r["활동내용"])), content_equals_name_flag=int(same_nc),
            low_info_text_flag=int(len(nc) + len(cc) < 14 or same_nc and len(nc) < 8),
        ))
    out = pd.DataFrame(out)

    # ── 중복·템플릿 ──
    # 완전 동일 행: 원본의 모든 열이 같은 행(source_row 제외)
    rawcols = [c for c in raw.columns if c not in ("source_row",)]
    dup_all = raw.duplicated(rawcols, keep=False).values
    dup_first = (~raw.duplicated(rawcols, keep="first")).values
    out["dup_exact_flag"] = out["source_row"].map(dict(zip(raw["source_row"].values, dup_all.astype(int))))
    out["dup_exact_first_flag"] = out["source_row"].map(dict(zip(raw["source_row"].values, dup_first.astype(int))))
    k2 = ["complex_name", "title_norm", "start_date"]
    out["dup_same_day_title_n"] = out.groupby(k2)["source_row"].transform("size")
    out["dup_same_day_std_n"] = out.groupby(["complex_name", "std_id", "start_date"])["source_row"].transform("size")
    gt = out.groupby("title_norm")["complex_name"].transform("nunique")
    out["title_n_complexes"] = gt
    out["hq_template_flag"] = (gt >= 10).astype(int)
    gc = out.groupby("activity_content_raw")["complex_name"].transform("nunique")
    out["content_n_complexes"] = gc
    return out
