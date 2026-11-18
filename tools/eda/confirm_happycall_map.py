# -*- coding: utf-8 -*-
"""해피콜 관리소 ↔ 단지 연결 확정(사용자 확인 2026-11-17 반영). build_crosswalk.py 실행 뒤에 돌린다.

확인 내용(사용자 답변)
- A(이름 사실상 동일)·B(접미 단어 차이) 후보 36건: 모두 확정
- C(통합 관리소) 4건: 아래 MERGED 대응대로 확정(1 관리소 → 여러 단지)
- D 11건: 연결하지 않음
산출
- happycall_office_map_confirmed.csv : 관리소 1행 × 단지 1행(통합 관리소는 여러 행), match_type 기록
- happycall_office_candidates.csv    : decision 열을 확정/연결안함으로 갱신
- complex_key_crosswalk.csv          : happycall_status = exact | confirmed_name_variant | confirmed_shared_office | none
- key_integrity_checks.csv           : K33~K36 추가
"""
import os
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "processed")).replace("\\", "/") + "/"
K = ROOT + "complex_keys_20261117_v1/"
rd = lambda p, **kw: pd.read_csv(p, encoding="utf-8-sig", **kw)
DATE = "2026-11-17"

MERGED = {
    "옹진백령(실버) 통합": ["KOH_114", "KOH_115"],
    "제주삼도이동2, 제주 일도이동 통합": ["KOH_317", "KOH_E45DCE9EBE"],
    "진도동외, 진도쌍정 통합": ["KOH_236", "KOH_237"],
    "울릉(저동, 남서, 천부, 동도) 통합": ["KOH_278", "KOH_279", "KOH_280", "KOH_281"],
}
NO_LINK = ["광주역다사로움", "서림마을다사로움", "JDC제주첨단리슈빌", "JDC제주첨단행복주택", "부안봉덕공공실버주택", "종갓집공공실버주택",
           "강변늘푸른타운", "구암다가온청년주택", "신탄진다가온청년주택", "나라키움영등포복합청사", "나라키움남양주복합청사"]


def main():
    ids = rd(ROOT + "complex_integrated_20261117_v1/data/complex_master.csv", usecols=["complex_id", "단지명", "지사명"])
    name_of = dict(zip(ids["complex_id"], ids["단지명"]))
    hc = rd(ROOT + "happycall_2025_v1/management_scores.csv")
    cand = rd(K + "happycall_office_candidates.csv")
    rows = []
    # 정확 일치
    id_of = dict(zip(ids["단지명"], ids["complex_id"]))
    ex = hc[hc["source_name"].isin(id_of)]
    for _, r in ex.iterrows():
        rows.append(dict(source_name=r["source_name"], branch=r["branch"], n_total=r["n_total"], complex_id=id_of[r["source_name"]], match_type="exact"))
    # 이름 차이 단일 확정(A+B)
    single = cand[(cand["office_kind"] == "single") & (~cand["source_name"].isin(NO_LINK))]
    assert len(single) == 36, len(single)
    for _, r in single.iterrows():
        rows.append(dict(source_name=r["source_name"], branch=r["branch"], n_total=r["n_total"], complex_id=r["best_candidate_id"], match_type="confirmed_name_variant"))
    # 통합 관리소
    mg = cand[cand["office_kind"] == "merged_offices"]
    assert set(mg["source_name"]) == set(MERGED), set(mg["source_name"]) ^ set(MERGED)
    for _, r in mg.iterrows():
        for cid in MERGED[r["source_name"]]:
            rows.append(dict(source_name=r["source_name"], branch=r["branch"], n_total=r["n_total"], complex_id=cid, match_type="confirmed_shared_office"))
    # 연결 안 함
    nl = cand[cand["source_name"].isin(NO_LINK)]
    assert len(nl) == 11, len(nl)
    for _, r in nl.iterrows():
        rows.append(dict(source_name=r["source_name"], branch=r["branch"], n_total=r["n_total"], complex_id=None, match_type="no_link"))
    m = pd.DataFrame(rows)
    m["complex_name"] = m["complex_id"].map(name_of)
    m["complex_branch"] = m["complex_id"].map(dict(zip(ids["complex_id"], ids["지사명"])))
    m["offices_for_complex"] = m.groupby("complex_id")["source_name"].transform("nunique")
    m["complexes_for_office"] = m.groupby("source_name")["complex_id"].transform("nunique")
    m["confirmed_by"] = "user_2026-11-17"
    m.loc[m["match_type"] == "exact", "confirmed_by"] = "rule_exact_name"
    m.to_csv(K + "happycall_office_map_confirmed.csv", index=False, encoding="utf-8-sig")

    # candidates 결정 갱신
    cand["decision"] = cand["source_name"].map(lambda s: "no_link_confirmed" if s in NO_LINK else ("merged_confirmed" if s in MERGED else "confirmed_name_variant"))
    cand.to_csv(K + "happycall_office_candidates.csv", index=False, encoding="utf-8-sig")

    # crosswalk 갱신
    cx = rd(K + "complex_key_crosswalk.csv")
    lk = m[m["complex_id"].notna()]
    cx["happycall_status"] = cx["complex_id"].map(dict(zip(lk["complex_id"], lk["match_type"]))).fillna("none")
    cx["happycall_source_name"] = cx["complex_id"].map(dict(zip(lk["complex_id"], lk["source_name"])))
    cx["happycall_n_total"] = cx["complex_id"].map(dict(zip(lk["complex_id"], lk["n_total"])))
    cx["happycall_exact_match"] = (cx["happycall_status"] == "exact").astype(int)
    cx = cx.drop(columns=[c for c in ["happycall_candidate_name"] if c in cx.columns])
    cx.to_csv(K + "complex_key_crosswalk.csv", index=False, encoding="utf-8-sig")

    # 점검
    ck = rd(K + "key_integrity_checks.csv")
    ck = ck[~ck.iloc[:, 0].astype(str).str.match(r"K3[3-6]")]
    single_ok = m[m["match_type"].isin(["exact", "confirmed_name_variant"])]
    n_dup = int(single_ok["complex_id"].duplicated().sum())
    n_dup_off = int(single_ok["source_name"].duplicated().sum())
    shared_overlap = int(set(lk[lk["match_type"] == "confirmed_shared_office"]["complex_id"]) & set(single_ok["complex_id"]) != set())
    br = lk.copy()
    br_mis = int((br["branch"].str.replace(" ", "") != br["complex_branch"].str.replace(" ", "")).sum())
    cols = ck.columns.tolist()
    new = [
        ["K33", "해피콜 확정 연결(1:1)에서 한 단지에 관리소가 둘 이상 / 한 관리소가 단지 둘 이상 연결된 건수", f"{n_dup} / {n_dup_off}", "0 / 0", "PASS" if n_dup == 0 and n_dup_off == 0 else "FAIL"],
        ["K34", "통합 관리소 대응 단지가 1:1 연결 단지와 겹치지 않음", f"겹침 {shared_overlap}", "0", "PASS" if shared_overlap == 0 else "FAIL"],
        ["K35", "확정 연결 전체에서 해피콜 지사 = 통합표 지사", f"{br_mis}건 불일치", "0건", "PASS" if br_mis == 0 else "FAIL"],
        ["K36", "해피콜 관리소 전수(319곳)가 확정표에 수록(연결/통합/연결안함 중 하나)", f"{m['source_name'].nunique()}/{len(hc)}", "전수", "PASS" if m["source_name"].nunique() == len(hc) else "FAIL"],
    ]
    ck = pd.concat([ck, pd.DataFrame(new, columns=cols)], ignore_index=True)
    ck.to_csv(K + "key_integrity_checks.csv", index=False, encoding="utf-8-sig")
    print(ck.tail(6).to_string())
    print(m["match_type"].value_counts().to_dict(), "complexes linked", lk["complex_id"].nunique())
    print(cx["happycall_status"].value_counts().to_dict())


if __name__ == "__main__":
    main()
