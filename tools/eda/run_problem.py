# -*- coding: utf-8 -*-
"""문제정의 분석 실행: 그림(p01~p12)·표·요약 수치를 <EDA 폴더>/problem_definition 아래에 저장한다.
사용: python run_problem.py <EDA 출력 폴더>"""
import os
import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd

import problem_def as P

OUT = os.path.join(sys.argv[1], "problem_definition")
FIG, TAB = os.path.join(OUT, "figures"), os.path.join(OUT, "tables")
os.makedirs(FIG, exist_ok=True); os.makedirs(TAB, exist_ok=True)
f = lambda n: os.path.join(FIG, n)
D = P.load()
S = {}
S["bg"] = P.p01_background(D, f("p01_background_age_mix.png"))
S["eld"] = P.p02_elderly(D, f("p02_elderly_vs_program.png"))
S["hdp"] = P.p03_hd_vs_program(D, f("p03_need_vs_program_domain.png"))
S["exp"] = P.p04_what_explains(D, f("p04_what_explains_program_mix.png"))
S["size"] = P.p05_size(D, f("p05_size_vs_supply.png"))
S["ns"] = P.p06_need_supply(D, f("p06_need_supply_quadrant.png"))
S["unit"] = P.p07_reach_unit(D, f("p07_reach_record_unit.png"))
S["mon"] = P.p08_reach_months(D, f("p08_reach_active_months.png"))
S["names"] = P.p09_names(D, f("p09_one_program_many_names.png"))
S["fields"] = P.p10_record_fields(D, f("p10_what_records_miss.png"))
S["sat"] = P.p11_volume_vs_satisfaction(D, f("p11_volume_vs_satisfaction.png"))
S["gap"] = P.p12_peer_gap(D, f("p12_peer_gap_opportunity.png"))
S["conc"] = P.concentration(D)

S["exp"]["table"].to_csv(os.path.join(TAB, "program_mix_explained_r2.csv"), index=False, encoding="utf-8-sig")
S["exp"]["curve"].to_csv(os.path.join(TAB, "program_mix_vs_context_distance.csv"), index=False, encoding="utf-8-sig")
S["size"]["table"].to_csv(os.path.join(TAB, "supply_by_size_bin.csv"), index=False, encoding="utf-8-sig")
S["ns"]["mis_table"].to_csv(os.path.join(TAB, "high_need_low_supply_complexes.csv"), index=False, encoding="utf-8-sig")
S["ns"]["all_table"].to_csv(os.path.join(TAB, "need_supply_index.csv"), index=False, encoding="utf-8-sig")
S["gap"]["table"].to_csv(os.path.join(TAB, "peer_gap_by_complex.csv"), index=False, encoding="utf-8-sig")
pd.DataFrame([(k, v) for k, vs in S["gap"]["neighbors"].items() for v in vs], columns=["complex_id", "neighbor_id"]).to_csv(os.path.join(TAB, "context_neighbors_k10.csv"), index=False, encoding="utf-8-sig")
keep = {k: {a: c for a, c in v.items() if not isinstance(c, (pd.DataFrame, pd.Series)) and a != "neighbors"} for k, v in S.items()}
pickle.dump(keep, open(os.path.join(TAB, "problem_summary.pkl"), "wb"))
for k, v in keep.items():
    print(k, {a: (round(c, 3) if isinstance(c, float) else c) for a, c in v.items() if not isinstance(c, (dict, list))})
print({k: keep[k].get("rho") for k in ("eld", "ns")})
