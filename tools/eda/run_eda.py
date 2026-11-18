# -*- coding: utf-8 -*-
"""통합 데이터 EDA 실행: 그림·표 저장 후 요약 수치를 pickle로 남긴다(보고서 생성은 eda_report.py).
사용: python run_eda.py 출력폴더"""
import os
import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd

import eda_data as ED
import eda_figs as F

OUT = sys.argv[1]
FIG = os.path.join(OUT, "figures")
TAB = os.path.join(OUT, "tables")
os.makedirs(FIG, exist_ok=True)
os.makedirs(TAB, exist_ok=True)
f = lambda n: os.path.join(FIG, n)

d = ED.load()
b = F.add_derived(ED.build_base(d))
S = {}
S["inv"] = F.fig_inventory(d, f("e01_inventory.png"))
S["miss"] = F.fig_missing(d, f("e02_missingness.png"))
S["bs"] = F.fig_branch_supply(b, f("e03_branch_supply.png"))
S["size"] = F.fig_size(b, f("e04_size_distribution.png"))
S["map"] = F.fig_map(b, f("e05_map_intensity.png"))
S["age"] = F.fig_age(b, f("e06_age_structure.png"))
S["corr"] = F.fig_corr(b, f("e07_correlation_matrix.png"))
S["hdt"] = F.fig_hd_time(d, f("e08_home_doctor_time.png"))
S["hdc"] = F.fig_hd_comp(d, b, f("e09_home_doctor_composition.png"))
S["hdd"] = F.fig_hd_dist(d, f("e10_home_doctor_distribution.png"))
S["base"] = F.fig_baseline(d, f("e11_forecast_baselines.png"))
S["rec"] = F.fig_recon(d, f("e12_reconciliation.png"))
S["acc"] = F.fig_access(b, f("e13_accessibility.png"))
S["acch"] = F.fig_access_hd(b, f("e14_access_vs_medical_support.png"))
S["ch"] = F.fig_comm_hd(b, f("e15_community_vs_home_doctor.png"))
S["ts"] = F.fig_type_supply(b, f("e16_community_type_by_supply.png"))
S["td"] = F.fig_type_demo(b, f("e17_community_type_context.png"))
S["hc"] = F.fig_happy(d, f("e18_happycall_satisfaction.png"))
S["ha"] = F.fig_happy_assoc(b, f("e19_happycall_association.png"))
S["pca"] = F.fig_pca(b, f("e20_pca.png"))
S["km"] = F.fig_kmeans(b, S["pca"]["scores"], f("e21_kmeans_profiles.png"))
S["sp"] = F.fig_spatial(b, f("e22_spatial_autocorrelation.png"))
S["tr"] = F.fig_trend(b, f("e23_trend_2026h1.png"))
S["pr"] = F.fig_presence(b, f("e24_record_presence.png"))
S["out"] = F.fig_outliers(b, f("e25_outliers.png"))

S["ex"] = F.extra_stats(b, d)
# 표 저장
S["hdt"]["monthly"].to_csv(os.path.join(TAB, "home_doctor_monthly_totals.csv"), index=False, encoding="utf-8-sig")
S["base"]["table"].to_csv(os.path.join(TAB, "forecast_baselines.csv"), index=False, encoding="utf-8-sig")
S["corr"]["R"].to_csv(os.path.join(TAB, "spearman_matrix.csv"), encoding="utf-8-sig")
S["ch"]["R"].to_csv(os.path.join(TAB, "community_family_vs_home_doctor_rho.csv"), encoding="utf-8-sig")
S["out"]["table"].to_csv(os.path.join(TAB, "outlier_complexes.csv"), index=False, encoding="utf-8-sig")
S["km"]["labels"].rename("env_cluster").to_csv(os.path.join(TAB, "context_clusters.csv"), encoding="utf-8-sig")
pd.DataFrame(S["sp"]["rows"], columns=["variable", "morans_I", "p_perm", "null_lo", "null_hi"]).to_csv(os.path.join(TAB, "morans_i.csv"), index=False, encoding="utf-8-sig")
pd.DataFrame(S["ha"]["rows"], columns=["variable", "rho", "p", "lo", "hi", "n", "p_holm"]).to_csv(os.path.join(TAB, "happycall_association.csv"), index=False, encoding="utf-8-sig")
S["ts"]["table"].to_csv(os.path.join(TAB, "community_type_by_supply.csv"), encoding="utf-8-sig")
b.to_csv(os.path.join(TAB, "analysis_base_table.csv"), index=False, encoding="utf-8-sig")
pickle.dump({k: {a: c for a, c in v.items() if not isinstance(c, (pd.DataFrame, pd.Series)) and a not in ("scores",)} for k, v in S.items()}, open(os.path.join(TAB, "summary_values.pkl"), "wb"))
print("figures", len(os.listdir(FIG)), "tables", len(os.listdir(TAB)))
