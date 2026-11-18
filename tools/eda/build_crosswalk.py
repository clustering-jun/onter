# -*- coding: utf-8 -*-
"""단지 기본키(complex_id) 정합성 점검과 교차 연결표 생성.

기준: processed/complex_integrated_20261117_v1/data/complex_master.csv 의 complex_id(318개).
산출: processed/complex_keys_20261117_v1/
  - complex_key_crosswalk.csv       단지 1행: 각 자료에 기록이 있는지·해피콜 관리소 연결 상태
  - happycall_office_candidates.csv 해피콜 관리소 중 단지명이 정확히 같지 않은 곳의 연결 후보(자동 확정 아님)
  - key_integrity_checks.csv        표 간 ID 정합성 점검 결과
"""
import difflib
import os
import re
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"C:/Users/user/Desktop/2026 DRIVE/project/data/processed/"
OUT = ROOT + "complex_keys_20261117_v1/"
IG = ROOT + "complex_integrated_20261117_v1/data/"
COMM = os.environ.get("EDA_COMMUNITY") or (ROOT + "community_nlp_2026_v1/")
rd = lambda p, **k: pd.read_csv(p, encoding="utf-8-sig", **k)


def norm(s):
    s = re.sub(r"\(.*?\)", "", str(s))
    return re.sub(r"[\s·,\-_/]", "", s)


def main():
    os.makedirs(OUT, exist_ok=True)
    cm = rd(IG + "complex_master.csv")
    cs = rd(IG + "model_cross_section.csv")
    mp = rd(IG + "model_monthly_panel.csv")
    hd = rd(IG + "home_doctor_monthly.csv")
    cn = rd(COMM + "complex_features.csv")
    hc = rd(ROOT + "happycall_2025_v1/management_scores.csv")
    ids = cm[["complex_id", "단지명", "지사명"]].copy()
    id_of = dict(zip(ids["단지명"], ids["complex_id"]))
    name_of = dict(zip(ids["complex_id"], ids["단지명"]))

    chk = []

    def add(cid, desc, result, expected, ok):
        chk.append(dict(check_id=cid, description=desc, result=result, expected=expected, status="PASS" if ok else "FAIL"))

    add("K01", "통합표 complex_id 유일·비결측", f"{cm['complex_id'].nunique()}/{len(cm)}", "행 수와 같음", cm["complex_id"].is_unique and cm["complex_id"].notna().all())
    add("K02", "통합표 단지명 유일·비결측", f"{cm['단지명'].nunique()}/{len(cm)}", "행 수와 같음", cm["단지명"].is_unique and cm["단지명"].notna().all())
    add("K03", "단지명 앞뒤 공백·연속 공백 없음", int((cm["단지명"] != cm["단지명"].str.strip()).sum() + cm["단지명"].str.contains("  ").sum()), 0, True if ((cm["단지명"] != cm["단지명"].str.strip()).sum() + cm["단지명"].str.contains("  ").sum()) == 0 else False)
    odd = cm.loc[~cm["complex_id"].str.match(r"^[A-Z]+_\d+$"), ["complex_id", "단지명"]]
    add("K04", "complex_id 형식(KOH_정수)", f"{len(odd)}건 예외: " + ", ".join(f"{a}({b})" for a, b in odd.values), "0건(예외는 사용자가 확인·결정; 임의로 바꾸지 않음)", len(odd) == 0)
    if len(odd):
        chk[-1]["status"] = "WARN"
    for nm, df in [("model_cross_section", cs), ("model_monthly_panel", mp), ("home_doctor_monthly", hd)]:
        ok_id = df["complex_id"].isin(set(ids["complex_id"])).all()
        mism = int((df["complex_id"].map(name_of) != df["단지명"]).sum())
        add(f"K10-{nm}", f"{nm}: complex_id가 통합표에 모두 존재", f"{int((~df['complex_id'].isin(set(ids['complex_id']))).sum())}행 불일치", "0행", ok_id)
        add(f"K11-{nm}", f"{nm}: complex_id↔단지명이 통합표와 일치", f"{mism}행 불일치", "0행", mism == 0)
    add("K12", "model_cross_section 단지 수가 통합표와 같음", f"{cs['complex_id'].nunique()}/{len(cm)}", "같음", cs["complex_id"].nunique() == len(cm))
    add("K13", "model_monthly_panel (complex_id, target_month) 유일", int(mp.duplicated(["complex_id", "target_month"]).sum()), "0행 중복", not mp.duplicated(["complex_id", "target_month"]).any())
    add("K14", "home_doctor_monthly (complex_id, 기간) 유일", int(hd.duplicated(["complex_id", "기간"]).sum()), "0행 중복", not hd.duplicated(["complex_id", "기간"]).any())
    # 커뮤니티 NLP
    cn_ok = cn["complex_id"].isin(set(ids["complex_id"])).all() if "complex_id" in cn.columns else False
    cn_mm = int((cn["complex_id"].map(name_of) != cn["complex_name"]).sum()) if "complex_id" in cn.columns else -1
    add("K20", "community_nlp complex_features: complex_id가 통합표에 존재", f"{cn['complex_id'].nunique() if 'complex_id' in cn.columns else 0}개 단지", "모두 존재", cn_ok)
    add("K21", "community_nlp: complex_id↔단지명 일치", f"{cn_mm}행 불일치", "0행", cn_mm == 0)
    for fn in ["program_analysis.csv", "complex_program_candidates.csv", "complex_std_matrix_long.csv"]:
        d = rd(COMM + fn, usecols=lambda c: c in ("complex_id",), low_memory=False)
        add(f"K22-{fn}", f"community_nlp {fn}: complex_id 비결측·통합표 존재", f"결측 {int(d['complex_id'].isna().sum())}, 미존재 {int((~d['complex_id'].isin(set(ids['complex_id']))).sum())}", "0, 0",
            d["complex_id"].notna().all() and d["complex_id"].isin(set(ids["complex_id"])).all())
    # 해피콜
    hc_exact = hc["source_name"].isin(set(ids["단지명"]))
    add("K30", "해피콜 management_scores 관리소명의 단지명 정확 일치", f"{int(hc_exact.sum())}/{len(hc)}", "참고(자동 확정은 정확 일치만)", True)
    hc_dup = int(hc.loc[hc_exact, "source_name"].duplicated().sum())
    add("K31", "해피콜 정확 일치 관리소가 한 단지에만 연결", f"중복 {hc_dup}", "0", hc_dup == 0)
    # 지사 일치 확인
    hcm = hc[hc_exact].copy()
    hcm["complex_id"] = hcm["source_name"].map(id_of)
    br_of = dict(zip(ids["complex_id"], ids["지사명"]))
    hcm["branch_master"] = hcm["complex_id"].map(br_of)
    br_mis = int((hcm["branch"].map(lambda s: str(s).replace(" ", "")) != hcm["branch_master"].map(lambda s: str(s).replace(" ", ""))).sum())
    add("K32", "정확 일치 관리소의 지사명이 통합표 지사명과 일치", f"{br_mis}건 불일치", "0건(표기 차이는 참고)", br_mis == 0)

    # 연결 후보(정확 일치가 아닌 관리소)
    cand_rows = []
    used = set(hcm["complex_id"])
    free = ids[~ids["complex_id"].isin(used)].copy()
    free["n"] = free["단지명"].map(norm)
    for _, r in hc[~hc_exact].iterrows():
        nm = norm(r["source_name"])
        pool = free[free["지사명"].str.replace(" ", "") == str(r["branch"]).replace(" ", "")]
        scored = sorted(((difflib.SequenceMatcher(None, nm, x).ratio(), cid, n0) for x, cid, n0 in zip(pool["n"], pool["complex_id"], pool["단지명"])), reverse=True)[:3]
        best = scored[0] if scored else (0, None, None)
        kind = "merged_offices" if "통합" in str(r["source_name"]) or "," in str(r["source_name"]) else "single"
        starts = [n0 for x, cid, n0 in zip(pool["n"], pool["complex_id"], pool["단지명"]) if x.startswith(nm) or nm.startswith(x)]
        cand_rows.append(dict(source_name=r["source_name"], branch=r["branch"], n_total=r["n_total"], office_kind=kind,
                              best_candidate_id=best[1], best_candidate_name=best[2], similarity=round(best[0], 3),
                              prefix_candidates=" | ".join(starts), second_candidate=("" if len(scored) < 2 else f"{scored[1][2]}({scored[1][0]:.2f})"),
                              decision="unconfirmed_needs_user_confirmation"))
    cand = pd.DataFrame(cand_rows).sort_values(["office_kind", "similarity"], ascending=[True, False])
    cand.to_csv(OUT + "happycall_office_candidates.csv", index=False, encoding="utf-8-sig")

    # 교차 연결표
    cx = ids.copy()
    cx["n_community_rows"] = cx["complex_id"].map(rd(COMM + "program_analysis.csv", usecols=["complex_id"], low_memory=False)["complex_id"].value_counts()).fillna(0).astype(int)
    cx["in_community_nlp"] = (cx["n_community_rows"] > 0).astype(int)
    cx["community_low_data"] = cx["complex_id"].map(dict(zip(cn["complex_id"], cn["low_data_flag"]))).astype("Int64")
    cx["n_home_doctor_months"] = cx["complex_id"].map(hd["complex_id"].value_counts()).fillna(0).astype(int)
    cx["n_panel_rows"] = cx["complex_id"].map(mp["complex_id"].value_counts()).fillna(0).astype(int)
    cx["happycall_exact_match"] = cx["complex_id"].isin(used).astype(int)
    cx["happycall_source_name"] = cx["complex_id"].map(dict(zip(hcm["complex_id"], hcm["source_name"])))
    cx["happycall_n_total"] = cx["complex_id"].map(dict(zip(hcm["complex_id"], hcm["n_total"])))
    sure = cand[(cand["office_kind"] == "single") & (cand["similarity"] >= 0.85)]
    cx["happycall_candidate_name"] = cx["complex_id"].map(dict(zip(sure["best_candidate_id"], sure["source_name"])))
    cx["happycall_status"] = cx.apply(lambda r: "exact" if r["happycall_exact_match"] else ("candidate_unconfirmed" if pd.notna(r["happycall_candidate_name"]) else "none"), axis=1)
    cx.to_csv(OUT + "complex_key_crosswalk.csv", index=False, encoding="utf-8-sig")
    # 통합표에 없는 단지(커뮤니티 제외 3개)
    chk_df = pd.DataFrame(chk)
    chk_df.to_csv(OUT + "key_integrity_checks.csv", index=False, encoding="utf-8-sig")
    print(chk_df.to_string())
    print(cx["happycall_status"].value_counts().to_dict(), "community", cx["in_community_nlp"].sum(), "hd months>0", (cx["n_home_doctor_months"] > 0).sum())
    print(cand.head(25).to_string())


if __name__ == "__main__":
    main()
