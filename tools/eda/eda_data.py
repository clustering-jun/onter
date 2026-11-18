# -*- coding: utf-8 -*-
"""EDA 자료 적재·결합. 기준 단지 목록은 통합표(complex_master)의 complex_id 318개이며 모든 표를 complex_id로 결합한다."""
import os

import numpy as np
import pandas as pd

ROOT = r"C:/Users/user/Desktop/2026 DRIVE/project/data/processed/"
IG = ROOT + "complex_integrated_20261117_v1/data/"
KEYS = ROOT + "complex_keys_20261117_v1/"
COMMUNITY = os.environ.get("EDA_COMMUNITY") or (ROOT + "community_nlp_2026_v1/")
HAPPY = ROOT + "happycall_2025_v1/"
rd = lambda p, **k: pd.read_csv(p, encoding="utf-8-sig", **k)

HD_COLS = ["생활지원", "가사지원", "의료지원", "경제지원"]
SUPPLY_ORDER = ["국민임대", "영구임대", "공공임대(50년)", "복합 공급", "행복주택"]


def supply_group(s):
    s = str(s)
    if "," in s:
        return "복합 공급"
    return s if s in SUPPLY_ORDER else "복합 공급"


def load():
    d = {}
    d["cm"] = rd(IG + "complex_master.csv")
    d["cs"] = rd(IG + "model_cross_section.csv")
    d["mp"] = rd(IG + "model_monthly_panel.csv")
    d["hd"] = rd(IG + "home_doctor_monthly.csv")
    d["cd"] = rd(IG + "column_dictionary.csv")
    d["cf"] = rd(COMMUNITY + "complex_features.csv")
    d["hc"] = rd(HAPPY + "management_scores.csv")
    d["cx"] = rd(KEYS + "complex_key_crosswalk.csv")
    return d


def hd_year_table(hd, years=(2025,)):
    """홈닥터 월별 → 단지×연 집계(기록이 있는 달만; 달별 합계)."""
    h = hd[hd["년도"].isin(years)]
    g = h.groupby("complex_id").agg(n_months=("기간", "nunique"), support=("지원내용총건수", "sum"), households_mean=("세대수", "mean"),
                                    **{c: (c, "sum") for c in HD_COLS})
    for c in HD_COLS:
        g[f"{c}_share"] = g[c] / g["support"].where(g["support"] > 0)
    return g


def build_base(d):
    """단지 1행 분석표: 횡단면 + 커뮤니티 특성(일부) + 홈닥터 2025 구성 + 해피콜(정확 일치) + 파생."""
    cs, cf, hc, cx = d["cs"].copy(), d["cf"], d["hc"], d["cx"]
    b = cs.copy()
    b["supply_group"] = b["공급유형"].map(supply_group)
    b["log_households"] = np.log10(b["세대수"])
    cfk = ["complex_id", "n_records_resident", "resident_records_per_1000hh_year", "std_richness", "std_evenness", "std_entropy", "std_top1_share", "participation_per_100hh_year",
           "complex_type_id", "low_data_flag", "ops_reg_YP_share", "ops_evt_YP_share", "share_partner_mentioned", "peer_group", "est_cost_mid_per_hh_year_krw",
           "family_richness", "partner_org_type_richness", "repeat_record_share", "h1_2026_vs_h1_2025_ratio"] + [c for c in cf.columns if c.startswith("share_family_F") or c.startswith("share_need_N")]
    cfk = [c for c in cfk if c in cf.columns]
    b = b.merge(cf[cfk], on="complex_id", how="left")
    b["in_community"] = b["complex_id"].isin(set(cf["complex_id"])).astype(int)
    h25 = hd_year_table(d["hd"]).add_prefix("hd25_").reset_index()
    b = b.merge(h25, on="complex_id", how="left")
    for c in HD_COLS:
        b[f"hd25_{c}_per100"] = b[f"hd25_{c}"] / b["hd25_n_months"] / b["세대수"] * 100
    ex = cx[cx["happycall_status"].isin(["exact", "confirmed_name_variant"])][["complex_id", "happycall_source_name"]]
    hcm = hc.rename(columns={"source_name": "happycall_source_name"})[["happycall_source_name", "n_total", "small_sample", "overall_satisfaction", "welfare_satisfaction",
                                                                       "housing_management_satisfaction", "pcsi", "branch"]]
    b = b.merge(ex.merge(hcm, on="happycall_source_name"), on="complex_id", how="left")
    return b


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dl = p2 - p1, np.radians(lon2) - np.radians(lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))
