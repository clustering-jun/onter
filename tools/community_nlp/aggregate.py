# -*- coding: utf-8 -*-
"""단지 단위 집계·표준 프로그램 사전·단지×프로그램 후보 특성 생성.

관측 기간: 2024-01-01 ~ 2026-06-30(30개월). 분모·관측 기간을 각 특성에 명시한다.
- '주민 대상' 집계는 in_resident_scope==1(PROGRAM·HOUSEHOLD_SUPPORT)만 사용하고, 거버넌스·직원·시설·행정 기록은 별도 부하 지표로 둔다.
- 참여인원은 기록 인원이며 고유 주민 수혜자가 아니다. 예산은 모델 추정치다. 미시행은 '필요 없음'의 근거로 쓰지 않는다.
"""
import math
import numpy as np
import pandas as pd

from . import taxonomy as TX
from .std_programs import TYPES, BY_ID
from . import budget as BG

OBS_START = pd.Timestamp("2024-01-01")
OBS_END = pd.Timestamp("2026-06-30")
OBS_MONTHS = 30
OBS_YEARS = OBS_MONTHS / 12.0
RECENT_START = pd.Timestamp("2025-07-01")   # 최근 12개월 창
ASOF = "2026-06-30"

NEED_CODES = ["N1", "N2", "N3", "N4", "N5", "N6"]
FAM_CODES = [f"F{i:02d}" for i in range(1, 16)] + ["F99"]
PUR_CODES = [f"P{i:02d}" for i in range(1, 17)]
TGT_CODES = list(TX.TARGETS.keys())
ORG_CODES = list(TX.ORGS.keys())
OPS_COLS = {"ALW": "op_always", "REG": "op_regular", "EVT": "op_event", "ADH": "op_adhoc", "SEA": "op_seasonal"}
MODE_CODES = list(TX.MODES.keys())


def _entropy(counts):
    c = np.array([x for x in counts if x > 0], dtype=float)
    if c.sum() == 0:
        return dict(H=np.nan, even=np.nan, eff=np.nan, simpson=np.nan, hhi=np.nan, top1=np.nan, top3=np.nan, k=0)
    p = c / c.sum()
    H = float(-(p * np.log(p)).sum())
    k = len(p)
    ps = np.sort(p)[::-1]
    return dict(H=H, even=(H / math.log(k) if k > 1 else 0.0), eff=math.exp(H), simpson=float(1 - (p ** 2).sum()),
                hhi=float((p ** 2).sum()), top1=float(ps[0]), top3=float(ps[:3].sum()), k=k)


def _explode_counts(series, sep="|"):
    c = {}
    for v in series:
        if isinstance(v, str) and v:
            for x in v.split(sep):
                c[x] = c.get(x, 0) + 1
    return c


def supply_group(s):
    s = str(s)
    for key, g in (("영구임대", "영구임대계"), ("국민임대", "국민임대계"), ("공공임대(50년)", "공공임대50계"), ("행복주택", "행복주택계")):
        if key in s:
            return g
    return "기타"



def _top_keywords(series, k=5):
    c = {}
    for v in series:
        if isinstance(v, str) and v:
            for x in v.split("|"):
                c[x] = c.get(x, 0) + 1
    return [x for x, _ in sorted(c.items(), key=lambda kv: -kv[1])[:k]]


def _definition_ko(t):
    pur = [TX.PURPOSES.get(p, p) for p in t["pur"].split("+") if p]
    svc = [TX.SERVICES.get(x, x) for x in t["svc"].split("+") if x]
    mode = [TX.MODES.get(x, x) for x in t["mode"].split("+") if x]
    tgt = [TX.TARGETS.get(x, x) for x in t["tgt"].split("+") if x]
    ops = [TX.OPS.get(x, x) for x in t["ops"].split("+") if x]
    scope = TX.SCOPES.get(t["scope"], t["scope"])
    parts = [f"{t['name']}: {scope}."]
    if pur:
        parts.append("주 목적 " + pur[0] + (f"(부수: {', '.join(pur[1:])})" if len(pur) > 1 else "") + ".")
    if svc:
        parts.append("제공 서비스 " + ", ".join(svc) + ".")
    if mode:
        parts.append("통상 제공 방식 " + ", ".join(mode) + ".")
    if tgt:
        parts.append("통상 대상 " + ", ".join(tgt) + "(원문 명시가 아닌 유형 정의).")
    if ops:
        parts.append("통상 운영 " + "·".join(ops) + (f", 계절 연동 {t['season']}" if t.get("season") else "") + ".")
    return " ".join(parts)

# ────────────────────────────────────────────────────────────────────────
def build_dictionary(rows):
    """표준 프로그램 사전: 유형 정의 + 자료에서 관측한 통계(분모=전체 단지, 기간=관측 30개월)."""
    res = rows[rows["in_resident_scope"] == 1] if False else rows
    n_complex_total = rows["complex_name"].nunique()
    recs = []
    for t in TYPES + [BY_ID["Z99"]]:
        sub = rows[rows["std_id"] == t["id"]]
        n = len(sub)
        if n == 0 and t["id"] != "Z99":
            recs.append(dict(std_id=t["id"], std_name=t["name"], std_family=t["fam"], std_family_label=TX.FAMILIES[t["fam"]],
                             scope=t["scope"], n_records=0))
            continue
        dates = pd.to_datetime(sub["start_date"])
        mon = dates.dt.month.value_counts().reindex(range(1, 13), fill_value=0)
        mshare = (mon / max(1, mon.sum())).round(4)
        ops_share = {k: round(float((sub[c] == "Y").mean()), 4) for k, c in OPS_COLS.items()}
        ops_yp = {k: round(float(sub[c].isin(["Y", "P"]).mean()), 4) for k, c in OPS_COLS.items()}
        tg = _explode_counts(sub["target_explicit"])
        tg_top = "|".join(k for k, _ in sorted(tg.items(), key=lambda x: -x[1])[:3])
        og = _explode_counts(sub["partner_org_codes"])
        og_top = "|".join(k for k, _ in sorted(og.items(), key=lambda x: -x[1])[:3])
        tn = sub["program_name_raw"].value_counts()
        alias_n = int(sub["title_norm"].nunique())
        d = dict(
            std_id=t["id"], std_name=t["name"], std_family=t["fam"], std_family_label=TX.FAMILIES[t["fam"]],
            scope=t["scope"], scope_label=TX.SCOPES[t["scope"]], recommendable=int(t["scope"] in TX.RESIDENT_SCOPES and t["id"] != "Z99"),
            purpose_primary=(t["pur"].split("+")[0] if t["pur"] else ""),
            purpose_primary_label=TX.PURPOSES.get(t["pur"].split("+")[0], "") if t["pur"] else "",
            purpose_all="|".join(TX.PURPOSES.get(p, p) for p in t["pur"].split("+") if p),
            need_domains_def="|".join(TX.NEED_DOMAINS[x] for x in dict.fromkeys(TX.PURPOSE_TO_NEED.get(p, "") for p in t["pur"].split("+") if p) if x and x != "N0"),
            target_default="|".join(TX.TARGETS.get(x, x) for x in t["tgt"].split("+") if x),
            service_default="|".join(TX.SERVICES.get(x, x) for x in t["svc"].split("+") if x),
            mode_default="|".join(TX.MODES.get(x, x) for x in t["mode"].split("+") if x),
            ops_typical="|".join(TX.OPS.get(x, x) for x in t["ops"].split("+") if x),
            season_tag=t.get("season", ""),
            effect_default="|".join(TX.EFFECTS.get(x, x) for x in t["eff"].split("+") if x),
            resource_default="|".join(TX.RESOURCES.get(x, x) for x in t["res"].split("+") if x),
            budget_archetype=t.get("cost", "NONE"),
            budget_assumption=BG.ARCH.get(t.get("cost", "NONE"), BG.ARCH["NONE"])[6],
            keyword_rule=t["pat"], name_only_rule=t["n"], theme_rule=t.get("th", ""), exclude_rule=t["x"], rule_specificity=t["spec"], rule_priority=t["prio"],
            n_records=int(n), n_complexes=int(sub["complex_name"].nunique()),
            adoption_rate=round(sub["complex_name"].nunique() / n_complex_total, 4),
            records_per_adopting_complex_median=float(sub.groupby("complex_name").size().median()),
            first_start_date=dates.min().date().isoformat(), last_start_date=dates.max().date().isoformat(),
            n_2024=int((dates.dt.year == 2024).sum()), n_2025=int((dates.dt.year == 2025).sum()), n_2026h1=int((dates.dt.year == 2026).sum()),
            n_recent12m=int((dates >= RECENT_START).sum()),
            n_complexes_recent12m=int(sub.loc[dates >= RECENT_START, "complex_name"].nunique()),
            month_peak=int(mon.idxmax()), month_peak_share=float(mshare.max()),
            seasonality_cv=round(float(mon.std(ddof=0) / mon.mean()) if mon.mean() else 0, 3),
            **{f"month_share_{m:02d}": float(mshare[m]) for m in range(1, 13)},
            **{f"op_{k.lower()}_Y_share": v for k, v in ops_share.items()},
            **{f"op_{k.lower()}_YP_share": v for k, v in ops_yp.items()},
            single_day_share=round(float(sub["single_day_flag"].mean()), 4),
            activity_count_median=float(sub["activity_count"].median()),
            duration_days_median=float(sub["duration_days"].median()) if sub["duration_days"].notna().any() else np.nan,
            participants_total_median=float(sub["participants_total"].median()), participants_total_p90=float(sub["participants_total"].quantile(0.9)),
            participants_individual_median=float(sub["participants_individual"].median()),
            participation_per_100hh_median=float(sub["participation_per_100hh"].median()),
            est_cost_mid_median_krw=float(sub["est_cost_mid_krw"].median()), est_cost_mid_p10_krw=float(sub["est_cost_mid_krw"].quantile(0.1)),
            est_cost_mid_p90_krw=float(sub["est_cost_mid_krw"].quantile(0.9)),
            est_burden_mid_median_krw=float(sub["est_burden_mid_krw"].median()),
            share_cost_self=round(float((sub["cost_class_raw"] == "자체비용").mean()), 4),
            share_cost_lh=round(float((sub["cost_class_raw"] == "LH커뮤니티활동비").mean()), 4),
            share_cost_other=round(float((sub["cost_class_raw"] == "기타").mean()), 4),
            share_subject_mgmt=round(float((sub["budget_subject_raw"] == "주택관리공단").mean()), 4),
            share_subject_lh=round(float((sub["budget_subject_raw"] == "LH").mean()), 4),
            share_subject_self=round(float((sub["budget_subject_raw"] == "자체").mean()), 4),
            share_subject_other=round(float((sub["budget_subject_raw"] == "기타").mean()), 4),
            share_mou=round(float(sub["flag_mou"].mean()), 4), share_external_contest=round(float(sub["flag_external_contest"].mean()), 4),
            mean_org_count_raw=round(float(sub["org_count_raw"].mean()), 3),
            partner_org_top3="|".join(TX.ORGS.get(x, x) for x in og_top.split("|") if x), partner_mention_rate=round(float((sub["partner_org_n_text"] > 0).mean()), 4),
            target_explicit_top3="|".join(TX.TARGETS.get(x, x) for x in tg_top.split("|") if x),
            llm_or_rule_confidence_high_share=round(float((sub["std_confidence"] == "high").mean()), 4),
            alias_distinct_titles=alias_n,
            alias_examples=" / ".join(f"{k}({v})" for k, v in tn.head(5).items()),
            definition_ko=_definition_ko(t),
            example_source_rows="|".join(str(x) for x in sub.drop_duplicates("title_norm").sort_values("source_row")["source_row"].head(8).tolist()),
            example_contents=" // ".join(sub["activity_content_masked"].astype(str).str.replace(r"\s+", " ", regex=True).str.slice(0, 60).value_counts().head(3).index),
            partner_keywords_top5="|".join(_top_keywords(sub["partner_org_keywords"], 5)),
            share_support_unit_complex_wide=round(float(sub["support_unit_complex_wide"].mean()), 4),
            share_support_unit_household=round(float(sub["support_unit_household"].mean()), 4),
            share_support_unit_contact=round(float(sub["support_unit_contact"].mean()), 4),
            hq_template_share=round(float(sub["hq_template_flag"].mean()), 4),
        )
        recs.append(d)
    return pd.DataFrame(recs)


# ────────────────────────────────────────────────────────────────────────
def build_complex_std_long(rows):
    r = rows[rows["in_resident_scope"] == 1].copy()
    r["start_dt"] = pd.to_datetime(r["start_date"])
    g = r.groupby(["complex_name", "std_id"])
    out = g.agg(n_records=("source_row", "size"), n_months_active=("start_dt", lambda s: s.dt.to_period("M").nunique()),
                first_date=("start_dt", "min"), last_date=("start_dt", "max"),
                activity_count_sum=("activity_count", "sum"), participants_total_sum=("participants_total", "sum"),
                participants_individual_sum=("participants_individual", "sum"),
                est_cost_mid_sum_krw=("est_cost_mid_krw", "sum")).reset_index()
    out["months_since_last"] = ((OBS_END - out["last_date"]).dt.days / 30.44).round(1)
    out["recent12m_n"] = r[r["start_dt"] >= RECENT_START].groupby(["complex_name", "std_id"]).size().reindex(
        pd.MultiIndex.from_frame(out[["complex_name", "std_id"]])).fillna(0).astype(int).values
    out["first_date"] = out["first_date"].dt.date.astype(str)
    out["last_date"] = out["last_date"].dt.date.astype(str)
    out["std_name"] = out["std_id"].map(lambda x: BY_ID[x]["name"])
    return out


# ────────────────────────────────────────────────────────────────────────
def build_complex_features(rows, dictionary):
    allr = rows.copy()
    allr["start_dt"] = pd.to_datetime(allr["start_date"])
    res = allr[allr["in_resident_scope"] == 1]
    hh_map = allr.groupby("complex_name")["households"].first()
    sup_map = allr.groupby("complex_name")["supply_type"].first()
    cx = []
    for name, sub_all in allr.groupby("complex_name"):
        sub = sub_all[sub_all["in_resident_scope"] == 1]
        hh = int(hh_map[name])
        d = dict(complex_name=name, supply_type=sup_map[name], households=hh, supply_group=supply_group(sup_map[name]))
        for key, col in (("영구임대", "has_perm_rental"), ("국민임대", "has_national_rental"), ("공공임대(50년)", "has_public50"),
                         ("행복주택", "has_happy_housing"), ("임대상가", "has_rental_shop"), ("분양", "has_sale_unit"), ("장기전세", "has_longterm_jeonse")):
            d[col] = int(key in str(sup_map[name]))
        n_all = len(sub_all)
        n = len(sub)
        d.update(n_records_all=n_all, n_records_resident=n, n_records_governance=int((sub_all["scope"] == "GOVERNANCE").sum()),
                 n_records_staff=int((sub_all["scope"] == "STAFF").sum()), n_records_facility=int((sub_all["scope"] == "FACILITY_MGMT").sum()),
                 n_records_admin=int((sub_all["scope"] == "ADMIN").sum()), n_records_household_support=int((sub_all["scope"] == "HOUSEHOLD_SUPPORT").sum()),
                 share_resident_records=round(n / n_all, 4) if n_all else np.nan)
        d["records_per_month"] = round(n / OBS_MONTHS, 3)
        d["resident_records_per_1000hh_year"] = round(n / hh * 1000 / OBS_YEARS, 2) if hh else np.nan
        if n == 0:
            cx.append(d)
            continue
        dt = sub["start_dt"]
        am = dt.dt.to_period("M").nunique()
        d.update(first_record_date=dt.min().date().isoformat(), last_record_date=dt.max().date().isoformat(),
                 months_since_last_record=round((OBS_END - dt.max()).days / 30.44, 1), active_months=int(am), active_month_ratio=round(am / OBS_MONTHS, 3),
                 n_2024=int((dt.dt.year == 2024).sum()), n_2025=int((dt.dt.year == 2025).sum()), n_2026h1=int((dt.dt.year == 2026).sum()),
                 n_recent12m=int((dt >= RECENT_START).sum()),
                 active_months_recent12m=int(dt[dt >= RECENT_START].dt.to_period("M").nunique()))
        h1_25 = int(((dt >= "2025-01-01") & (dt <= "2025-06-30")).sum())
        h1_26 = int((dt.dt.year == 2026).sum())
        d["h1_2026_vs_h1_2025_ratio"] = round(h1_26 / h1_25, 3) if h1_25 else np.nan
        d["y2025_vs_y2024_ratio"] = round(d["n_2025"] / d["n_2024"], 3) if d["n_2024"] else np.nan
        # 구성: 가족·목적·필요분야
        fam = sub["std_family"].value_counts()
        for f in FAM_CODES:
            d[f"share_family_{f}"] = round(float(fam.get(f, 0)) / n, 4)
        pc = sub["purpose_primary"].value_counts()
        for p in PUR_CODES:
            d[f"share_purpose_{p}"] = round(float(pc.get(p, 0)) / n, 4)
        nc_ = sub["need_domain_primary"].value_counts()
        for k in NEED_CODES + ["N0"]:
            d[f"share_need_{k}"] = round(float(nc_.get(k, 0)) / n, 4)
        # 다양성
        sc = sub["std_id"].value_counts()
        e = _entropy(sc.values)
        d.update(std_richness=int(e["k"]), std_entropy=round(e["H"], 4), std_evenness=round(e["even"], 4), std_effective_n=round(e["eff"], 3),
                 std_simpson=round(e["simpson"], 4), std_hhi=round(e["hhi"], 4), std_top1_share=round(e["top1"], 4), std_top3_share=round(e["top3"], 4),
                 std_top1_id=sc.index[0], std_top1_name=BY_ID[sc.index[0]]["name"],
                 std_top5="; ".join(f"{BY_ID[k]['name']}({v})" for k, v in sc.head(5).items()))
        fe = _entropy(fam.values)
        d.update(family_richness=int(fe["k"]), family_entropy=round(fe["H"], 4), family_evenness=round(fe["even"], 4))
        pe = _entropy(pc.values)
        d.update(purpose_richness=int(pe["k"]), purpose_entropy=round(pe["H"], 4), purpose_evenness=round(pe["even"], 4))
        ne = _entropy(nc_.drop("N0", errors="ignore").values)
        d.update(need_domain_richness=int(ne["k"]), need_domain_entropy=round(ne["H"], 4))
        d["records_per_distinct_std"] = round(n / e["k"], 3)
        # 운영 패턴
        for k, c in OPS_COLS.items():
            d[f"ops_{k.lower()}_Y_share"] = round(float((sub[c] == "Y").mean()), 4)
            d[f"ops_{k.lower()}_YP_share"] = round(float(sub[c].isin(["Y", "P"]).mean()), 4)
            d[f"ops_{k.lower()}_U_share"] = round(float((sub[c] == "U").mean()), 4)
        d["ops_primary_unknown_share"] = round(float((sub["op_primary"] == "").mean()), 4)
        d["single_day_share"] = round(float(sub["single_day_flag"].mean()), 4)
        d["activity_count_mean"] = round(float(sub["activity_count"].mean()), 3)
        d["activity_count_median"] = float(sub["activity_count"].median())
        d["share_activity_count_ge3"] = round(float((sub["activity_count"] >= 3).mean()), 4)
        d["duration_days_median"] = float(sub["duration_days"].median()) if sub["duration_days"].notna().any() else np.nan
        d["year_end_end_date_share"] = round(float(sub["year_end_end_date_flag"].mean()), 4)
        mon = sub["start_month"].value_counts().reindex(range(1, 13), fill_value=0)
        for m in range(1, 13):
            d[f"month_share_{m:02d}"] = round(float(mon[m]) / n, 4)
        d["peak_month"] = int(mon.idxmax())
        d["seasonality_cv"] = round(float(mon.std(ddof=0) / mon.mean()), 3)
        d["season_winter_share"] = round(float(mon[[12, 1, 2]].sum()) / n, 4)
        d["season_summer_share"] = round(float(mon[[6, 7, 8]].sum()) / n, 4)
        # 정기 반복: 단지×정규화제목 그룹에서 3회 이상 반복
        gsz = sub.groupby("title_norm")["source_row"].transform("size")
        d["repeat_record_share"] = round(float((gsz >= 3).mean()), 4)
        d["max_repeat_n"] = int(gsz.max())
        rec_std = sub.groupby("std_id")["start_dt"].agg(lambda s: s.dt.to_period("M").nunique())
        d["recurring_std_n"] = int((rec_std >= 6).sum())
        d["recurring_std_share"] = round(float((rec_std >= 6).sum() / len(rec_std)), 4)
        d["same_month_same_std_dup_cells"] = int((sub.groupby(["std_id", sub["start_dt"].dt.to_period("M")]).size() >= 2).sum())
        d["dup_exact_n"] = int(sub["dup_exact_flag"].sum() - sub["dup_exact_first_flag"].where(sub["dup_exact_flag"] == 1, 0).sum())
        d["hq_template_share"] = round(float(sub["hq_template_flag"].mean()), 4)
        d["unique_program_share"] = round(1 - d["hq_template_share"], 4)
        # 참여
        d["participants_total_sum"] = int(sub["participants_total"].sum())
        d["participants_individual_sum"] = int(sub["participants_individual"].sum())
        d["participants_total_median"] = float(sub["participants_total"].median())
        d["participants_total_p90"] = float(sub["participants_total"].quantile(0.9))
        d["participants_individual_median"] = float(sub["participants_individual"].median())
        d["participation_per_100hh_year"] = round(d["participants_total_sum"] / hh * 100 / OBS_YEARS, 2) if hh else np.nan
        d["individual_per_100hh_year"] = round(d["participants_individual_sum"] / hh * 100 / OBS_YEARS, 2) if hh else np.nan
        d["median_participation_per_100hh"] = float(sub["participation_per_100hh"].median())
        d["share_large_events_indiv51plus"] = round(float((sub["participants_individual"] >= 51).mean()), 4)
        d["share_zero_participants"] = round(float((sub["participants_total"] == 0).mean()), 4)
        d["share_participants_mismatch"] = round(float(sub["participants_total_mismatch_flag"].mean()), 4)
        # 협력 구조
        d["org_count_raw_mean"] = round(float(sub["org_count_raw"].mean()), 3)
        d["share_mou"] = round(float(sub["flag_mou"].mean()), 4)
        d["share_external_contest"] = round(float(sub["flag_external_contest"].mean()), 4)
        d["share_culture_performance"] = round(float(sub["flag_culture_performance"].mean()), 4)
        for c in [c for c in sub.columns if c.startswith("part_flag_")]:
            d["share_" + c] = round(float(sub[c].mean()), 4)
        d["institution_types_nonzero_mean"] = round(float(sub["institution_types_nonzero"].mean()), 3)
        oc = _explode_counts(sub["partner_org_codes"])
        for k in ORG_CODES:
            d[f"share_org_{k}"] = round(oc.get(k, 0) / n, 4)
        oe = _entropy(list(oc.values()))
        d.update(partner_org_type_richness=int(oe["k"]), partner_org_entropy=(round(oe["H"], 4) if oe["k"] else 0.0),
                 share_partner_mentioned=round(float((sub["partner_org_n_text"] > 0).mean()), 4))
        for k, v in (("주택관리공단", "mgmt"), ("LH", "lh"), ("자체", "self"), ("기타", "other")):
            d[f"share_subject_{v}"] = round(float((sub["budget_subject_raw"] == k).mean()), 4)
        for k, v in (("자체비용", "self"), ("LH커뮤니티활동비", "lh"), ("기타", "other")):
            d[f"share_costclass_{v}"] = round(float((sub["cost_class_raw"] == k).mean()), 4)
        # 제공 방식·지원 단위·대상
        mc = _explode_counts(sub["mode_explicit"])
        for k in MODE_CODES:
            d[f"share_mode_{k}"] = round(mc.get(k, 0) / n, 4)
        d["share_support_unit_complex_wide"] = round(float(sub["support_unit_complex_wide"].mean()), 4)
        d["share_support_unit_household"] = round(float(sub["support_unit_household"].mean()), 4)
        d["share_support_unit_contact"] = round(float(sub["support_unit_contact"].mean()), 4)
        tc = _explode_counts(sub["target_explicit"])
        for k in TGT_CODES:
            d[f"share_target_{k}"] = round(tc.get(k, 0) / n, 4)
        d["share_target_any_explicit"] = round(float((sub["target_explicit"] != "").mean()), 4)
        # 원자료 유형·분야
        rc = sub["raw_community_type"].value_counts()
        for k in ["주민화합", "여가/취미/교양/교육", "건강/운동", "주거환경개선", "기타", "자살/고독사 예방", "친환경/재활용/에너지절약", "사회봉사활동", "층간소음 등 이웃갈등해결"]:
            d[f"share_rawtype_{k}"] = round(float(rc.get(k, 0)) / n, 4)
        d["share_field_safety"] = round(float((sub["field"] == "주거안전").mean()), 4)
        # 예산(모델 추정)
        d["est_cost_mid_sum_krw"] = float(sub["est_cost_mid_krw"].sum())
        d["est_cost_mid_per_year_krw"] = round(d["est_cost_mid_sum_krw"] / OBS_YEARS, -3)
        d["est_burden_mid_per_year_krw"] = round(float(sub["est_burden_mid_krw"].sum()) / OBS_YEARS, -3)
        d["est_cost_mid_per_hh_year_krw"] = round(d["est_cost_mid_per_year_krw"] / hh, 1) if hh else np.nan
        d["est_cost_mid_median_krw"] = float(sub["est_cost_mid_krw"].median())
        for k, lab in (("단지·LH·공단 부담(소요비용 기재, 금액 미상)", "own"), ("외부 제공·후원 추정(단지 부담 낮음)", "ext"), ("부담 주체 불명(기타·미기재)", "unk")):
            d[f"share_burden_{lab}"] = round(float((sub["est_burden_class"] == k).mean()), 4)
        # 품질
        d["share_label_low_confidence"] = round(float((sub["std_confidence"] == "low").mean()), 4)
        d["share_sensitive_identifier"] = round(float(sub["sensitive_identifier_flag"].mean()), 4)
        d["low_data_flag"] = int(n < 15)
        cx.append(d)
    cf = pd.DataFrame(cx)
    # 규모 구간·피어 그룹
    q = cf["households"].quantile([1 / 3, 2 / 3]).values
    cf["size_tertile"] = np.where(cf["households"] <= q[0], "S", np.where(cf["households"] <= q[1], "M", "L"))
    cf["peer_group"] = cf["supply_group"] + "|" + cf["size_tertile"]
    return cf


# ────────────────────────────────────────────────────────────────────────
def add_gap_features(cf, rows):
    """공급 공백: 같은 피어 그룹(공급유형×규모) 대비 필요 분야별 공급 수준. 공백은 필요의 정답이 아니다."""
    res = rows[rows["in_resident_scope"] == 1].copy()
    res["start_dt"] = pd.to_datetime(res["start_date"])
    hh = cf.set_index("complex_name")["households"]
    rec = res[res["start_dt"] >= RECENT_START]
    out = cf.copy()
    for k in NEED_CODES:
        tot = res[res["need_domain_primary"] == k].groupby("complex_name").size().reindex(cf["complex_name"]).fillna(0).values
        r12 = rec[rec["need_domain_primary"] == k].groupby("complex_name").size().reindex(cf["complex_name"]).fillna(0).values
        out[f"need_{k}_records_30m"] = tot.astype(int)
        out[f"need_{k}_records_12m"] = r12.astype(int)
        out[f"need_{k}_per_1000hh_year"] = np.round(tot / out["households"].values * 1000 / OBS_YEARS, 2)
        # 피어 그룹 내 백분위(낮을수록 상대적 공급 부족)
        pr = out.groupby("peer_group")[f"need_{k}_per_1000hh_year"].rank(pct=True, method="average")
        out[f"need_{k}_peer_pctile"] = np.round(pr.values, 3)
        out[f"gap_{k}_flag"] = ((r12 == 0) | (pr.values <= 0.2)).astype(int)
        out[f"gap_{k}_zero_12m"] = (r12 == 0).astype(int)
    gcols = [f"gap_{k}_flag" for k in NEED_CODES]
    out["gap_need_domain_n"] = out[gcols].sum(axis=1)
    out["gap_need_domains"] = out.apply(lambda r: "|".join(TX.NEED_DOMAINS[k] for k in NEED_CODES if r[f"gap_{k}_flag"] == 1), axis=1)
    out.loc[out["n_records_resident"] == 0, "gap_need_domains"] = "전체 미기록"
    return out


def add_peers(cf, rows, k=8):
    """프로그램 구성 유사도 기반 이웃 단지(협업 필터링용). 가족 점유율+운영·규모 로그 변수의 코사인 유사도."""
    feat = [c for c in cf.columns if c.startswith("share_family_")] + [c for c in cf.columns if c.startswith("share_purpose_")]
    X = cf[feat].fillna(0).values.astype(float)
    nrm = np.linalg.norm(X, axis=1, keepdims=True)
    nrm[nrm == 0] = 1
    Xn = X / nrm
    S = Xn @ Xn.T
    np.fill_diagonal(S, -1)
    names = cf["complex_name"].values
    ok = (cf["n_records_resident"].values >= 15)
    S[:, ~ok] = -1
    peers, sims = [], []
    for i in range(len(cf)):
        idx = np.argsort(-S[i])[:k]
        peers.append("|".join(names[j] for j in idx if S[i, j] > 0))
        sims.append(round(float(np.mean([S[i, j] for j in idx if S[i, j] > 0])) if (S[i, idx] > 0).any() else np.nan, 3))
    out = cf.copy()
    out["peer_cf_neighbors"] = peers
    out["peer_cf_mean_similarity"] = sims
    return out, S



def _item_attr_matrix(ids):
    """표준 유형 속성(목적·서비스·방식·통상 대상·통상 운영·가족)의 원-핫 코사인 유사도 — 중복·보완 특성용."""
    vocab = ([f"P{i:02d}" for i in range(1, 17)] + [f"S{i:02d}" for i in range(1, 21)] + [f"M{i}" for i in range(1, 11)] +
             list(TX.TARGETS.keys()) + list(TX.OPS.keys()) + [f"F{i:02d}" for i in range(1, 17)])
    pos = {v: i for i, v in enumerate(vocab)}
    X = np.zeros((len(ids), len(vocab)))
    for r, sid in enumerate(ids):
        t = BY_ID[sid]
        w = {}
        for k, wt in (("pur", 1.0), ("svc", 1.0), ("mode", 0.7), ("tgt", 0.6), ("ops", 0.5)):
            for j, c in enumerate([x for x in str(t[k]).split("+") if x]):
                if c in pos:
                    X[r, pos[c]] = max(X[r, pos[c]], wt * (1.0 if j == 0 else 0.6))
        X[r, pos[t["fam"]]] = 1.0
    nrm = np.linalg.norm(X, axis=1, keepdims=True)
    nrm[nrm == 0] = 1
    Xn = X / nrm
    return Xn @ Xn.T



def build_candidates(cf, rows, dictionary, S):
    """단지×표준프로그램 후보 특성(LTR 입력 후보). 전체 추천 가능 유형 × 전체 단지. 정답 라벨은 없다."""
    res = rows[rows["in_resident_scope"] == 1].copy()
    res["start_dt"] = pd.to_datetime(res["start_date"])
    cand_types = dictionary[(dictionary["recommendable"] == 1) & (dictionary["n_records"] > 0)]["std_id"].tolist()
    names = cf["complex_name"].tolist()
    idx_of = {n: i for i, n in enumerate(names)}
    cnt = res.groupby(["complex_name", "std_id"]).size().unstack(fill_value=0).reindex(index=names, columns=cand_types, fill_value=0)
    rec = res[res["start_dt"] >= RECENT_START].groupby(["complex_name", "std_id"]).size().unstack(fill_value=0).reindex(index=names, columns=cand_types, fill_value=0)
    last = res.groupby(["complex_name", "std_id"])["start_dt"].max().unstack().reindex(index=names, columns=cand_types)
    nmon = res.groupby(["complex_name", "std_id"])["start_dt"].agg(lambda s: s.dt.to_period("M").nunique()).unstack(fill_value=0).reindex(index=names, columns=cand_types, fill_value=0)
    adopt = (cnt.values > 0).astype(float)
    adopt_rec = (rec.values > 0).astype(float)
    ok = (cf["n_records_resident"].values >= 15)
    glob_rate = adopt[ok].mean(axis=0)
    glob_rate_rec = adopt_rec[ok].mean(axis=0)
    pg = cf["peer_group"].values
    dmap = dictionary.set_index("std_id")
    # 피어 그룹 채택률
    peer_rate = np.zeros_like(adopt)
    for g in np.unique(pg):
        m = (pg == g) & ok
        if m.sum() >= 3:
            peer_rate[pg == g] = adopt[m].mean(axis=0)
        else:
            peer_rate[pg == g] = glob_rate
    # 유사 단지(CF) 채택률: 상위 k 이웃의 평균
    k = 8
    cf_rate = np.zeros_like(adopt)
    for i in range(len(names)):
        j = np.argsort(-S[i])[:k]
        j = [x for x in j if S[i, x] > 0]
        cf_rate[i] = adopt[j].mean(axis=0) if j else glob_rate
    # 필요 분야 공백 상태
    gapcols = {k_: cf[f"gap_{k_}_flag"].values for k_ in NEED_CODES}
    # 중복·보완: 표준 유형 속성 유사도, 협력기관 적합, 운영 패턴·규모 적합
    sim = _item_attr_matrix(cand_types)
    adopted12 = [np.where(rec.values[ci] > 0)[0] for ci in range(len(names))]
    org_cols = [o for o in ORG_CODES if o != "OG13"]
    org_by_std = np.zeros((len(cand_types), len(org_cols)))
    for si, sid in enumerate(cand_types):
        sub_ = res[res["std_id"] == sid]
        if len(sub_):
            for oi, o in enumerate(org_cols):
                org_by_std[si, oi] = sub_["partner_org_codes"].astype(str).str.contains(o).mean()
    org_used = np.zeros((len(names), len(org_cols)))
    for ci, cn in enumerate(names):
        sub_ = res[res["complex_name"] == cn]
        for oi, o in enumerate(org_cols):
            org_used[ci, oi] = float(sub_["partner_org_codes"].astype(str).str.contains(o).sum() >= 3) if len(sub_) else 0.0
    std_evt = dictionary.set_index("std_id")["op_evt_YP_share"]
    std_reg = dictionary.set_index("std_id")["op_reg_YP_share"]
    # 월별 계절성 적합: 다음 달(2026-07) 기준
    next_month = 7
    rows_out = []
    cf_i = cf.set_index("complex_name")
    est_med = cf_i["est_cost_mid_median_krw"]
    for ci, cn in enumerate(names):
        c = cf_i.loc[cn]
        for si, sid in enumerate(cand_types):
            drow = dmap.loc[sid]
            primary_need = TX.PURPOSE_TO_NEED.get(drow["purpose_primary"], "N0")
            n_prog = int(cnt.iat[ci, si])
            rows_out.append(dict(
                complex_name=cn, std_id=sid, std_name=drow["std_name"], std_family=drow["std_family"],
                need_domain_primary=primary_need,
                complex_n_records=n_prog, complex_n_records_12m=int(rec.iat[ci, si]), complex_months_active=int(nmon.iat[ci, si]),
                complex_adopted=int(n_prog > 0),
                complex_months_since_last=(None if pd.isna(last.iat[ci, si]) else round((OBS_END - last.iat[ci, si]).days / 30.44, 1)),
                global_adoption_rate=round(float(glob_rate[si]), 4), global_adoption_rate_12m=round(float(glob_rate_rec[si]), 4),
                peer_group_adoption_rate=round(float(peer_rate[ci, si]), 4), cf_neighbor_adoption_rate=round(float(cf_rate[ci, si]), 4),
                gap_supply_candidate=int(n_prog == 0 and glob_rate[si] >= 0.10),
                fills_gap_domain=int(primary_need in NEED_CODES and gapcols[primary_need][ci] == 1),
                domain_share_in_complex=(float(c.get(f"share_need_{primary_need}", np.nan)) if primary_need != "N0" else np.nan),
                family_share_in_complex=float(c.get(f"share_family_{drow['std_family']}", np.nan)),
                peer_minus_complex_gap=round(float(peer_rate[ci, si]) - float(n_prog > 0), 4),
                season_share_next_month=float(drow.get(f"month_share_{next_month:02d}", np.nan)),
                std_seasonality_cv=float(drow["seasonality_cv"]),
                std_est_cost_mid_median_krw=float(drow["est_cost_mid_median_krw"]),
                cost_ratio_to_complex_median=(round(float(drow["est_cost_mid_median_krw"]) / float(est_med[cn]), 3) if est_med[cn] and est_med[cn] > 0 else np.nan),
                std_participants_total_median=float(drow["participants_total_median"]),
                std_participation_per_100hh_median=float(drow["participation_per_100hh_median"]),
                households=int(c["households"]),
                low_data_complex=int(c["low_data_flag"]),
                redundancy_max_sim_12m=(round(float(sim[si, [j for j in adopted12[ci] if j != si]].max()), 3) if len([j for j in adopted12[ci] if j != si]) else 0.0),
                redundancy_top3_mean_sim_12m=(round(float(np.sort(sim[si, [j for j in adopted12[ci] if j != si]])[::-1][:3].mean()), 3) if len([j for j in adopted12[ci] if j != si]) else 0.0),
                partner_fit=(round(float((org_by_std[si] * org_used[ci]).sum() / org_by_std[si].sum()), 3) if org_by_std[si].sum() > 0 else np.nan),
                ops_event_gap=round(float(std_evt.get(sid, np.nan)) - float(c.get("ops_evt_YP_share", np.nan)), 3),
                ops_regular_gap=round(float(std_reg.get(sid, np.nan)) - float(c.get("ops_reg_YP_share", np.nan)), 3),
                participants_ratio_to_complex_median=(round(float(drow["participants_total_median"]) / float(c.get("participants_total_median")), 3) if c.get("participants_total_median") and c.get("participants_total_median") > 0 else np.nan),
            ))
    out = pd.DataFrame(rows_out)
    return out


# ────────────────────────────────────────────────────────────────────────
def latent_factors(rows, dictionary, cf, k=8, seed=7, min_item_records=10, min_complex_records=15):
    """단지×표준 유형 기록 수(log1p)의 비음수 행렬분해. 단지 적재(구성 점유율)와 유형 요인을 반환.
    협업 필터링·LTR의 밀집 특성 후보이며 '필요'의 정답이 아니라 '공급 구성의 잠재 패턴'이다."""
    from sklearn.decomposition import NMF
    res = rows[rows["in_resident_scope"] == 1]
    cnt = res.groupby(["complex_name", "std_id"]).size().unstack(fill_value=0)
    items = [c for c in cnt.columns if cnt[c].sum() >= min_item_records and c != "Z99"]
    cx_ok = cf.loc[cf["n_records_resident"] >= min_complex_records, "complex_name"].tolist()
    M = np.log1p(cnt.reindex(index=cx_ok, columns=items, fill_value=0).values.astype(float))
    model = NMF(n_components=k, init="nndsvda", random_state=seed, max_iter=1000)
    W = model.fit_transform(M)
    H = model.components_
    err = float(np.linalg.norm(M - W @ H) / np.linalg.norm(M))
    Wn = W / np.maximum(W.sum(axis=1, keepdims=True), 1e-12)
    wdf = pd.DataFrame(Wn, index=cx_ok, columns=[f"latent_c{i + 1:02d}" for i in range(k)]).round(4)
    wdf["latent_dominant"] = ["c%02d" % (int(np.argmax(r)) + 1) for r in Wn]
    hdf = pd.DataFrame(H.T, index=items, columns=[f"latent_c{i + 1:02d}" for i in range(k)])
    hn = hdf / np.maximum(hdf.sum(axis=1).values[:, None], 1e-12)
    comp = []
    for i in range(k):
        col = f"latent_c{i + 1:02d}"
        top = hdf[col].sort_values(ascending=False).head(6)
        comp.append(dict(component=f"c{i + 1:02d}", top_std="; ".join(f"{BY_ID[x]['name']}" for x in top.index),
                         top_std_ids="|".join(top.index), mean_loading=round(float(wdf[col].mean()), 4),
                         n_complexes_dominant=int((wdf["latent_dominant"] == f"c{i + 1:02d}").sum())))
    return wdf, hn.round(4), pd.DataFrame(comp), dict(reconstruction_rel_error=round(err, 4), k=k, n_items=len(items), n_complexes=len(cx_ok))


def cooccurrence(rows, dictionary, min_both=8, min_complex_records=15, cf=None):
    """표준 유형 간 단지 수준 동시 시행(보완·묶음 후보). lift = P(a,b)/(P(a)P(b)), Jaccard."""
    res = rows[rows["in_resident_scope"] == 1]
    cnt = res.groupby(["complex_name", "std_id"]).size().unstack(fill_value=0)
    if cf is not None:
        ok = cf.loc[cf["n_records_resident"] >= min_complex_records, "complex_name"]
        cnt = cnt.loc[cnt.index.isin(ok)]
    B = (cnt.values > 0).astype(int)
    ids = list(cnt.columns)
    N = B.shape[0]
    co = B.T @ B
    pa = B.sum(axis=0) / N
    out = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            nb = int(co[i, j])
            if nb < min_both:
                continue
            lift = (nb / N) / (pa[i] * pa[j]) if pa[i] * pa[j] > 0 else np.nan
            jac = nb / (B[:, i].sum() + B[:, j].sum() - nb)
            out.append(dict(std_a=ids[i], std_a_name=BY_ID[ids[i]]["name"], std_b=ids[j], std_b_name=BY_ID[ids[j]]["name"], n_both=nb,
                            n_a=int(B[:, i].sum()), n_b=int(B[:, j].sum()), lift=round(float(lift), 3), jaccard=round(float(jac), 3)))
    return pd.DataFrame(out).sort_values("lift", ascending=False)


def complex_summary_ko(cf):
    """단지별 한 줄 요약(발표·검토용). 수치는 모두 집계 특성에서 가져오며 서술에 새 사실을 더하지 않는다."""
    FAM = {"F01": "명절·기념 행사", "F02": "돌봄·안부", "F03": "식생활·생필품 지원", "F04": "건강증진", "F05": "정신건강", "F06": "상담·정보 연계",
           "F07": "주거환경", "F08": "생활편의 서비스", "F09": "안전", "F10": "문화·여가", "F11": "운동·체육", "F12": "교육", "F13": "환경·에너지",
           "F14": "공동체·참여", "F15": "갈등·질서"}
    out = []
    for _, r in cf.iterrows():
        if r.get("n_records_resident", 0) == 0:
            out.append("주민 대상 기록 없음")
            continue
        fam = sorted(((f, r.get(f"share_family_{f}", 0)) for f in FAM), key=lambda x: -x[1])[:2]
        gap = r.get("gap_need_domains", "")
        s = (f"주민 대상 {int(r['n_records_resident'])}건(세대 1000당 연 {r['resident_records_per_1000hh_year']:.0f}건), "
             f"{FAM[fam[0][0]]} {fam[0][1] * 100:.0f}%·{FAM[fam[1][0]]} {fam[1][1] * 100:.0f}% 중심, "
             f"표준 유형 {int(r['std_richness'])}종(균등도 {r['std_evenness']:.2f}), 행사형 {r['ops_evt_Y_share'] * 100:.0f}%·정기 {r['ops_reg_YP_share'] * 100:.0f}%")
        if r.get("low_data_flag", 0) == 1:
            s += " [기록 15건 미만: 자료 부족]"
        elif gap:
            s += f", 최근 공급 공백 분야: {gap}"
        out.append(s)
    return out
