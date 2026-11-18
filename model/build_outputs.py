"""전체 기간(2024-01~2026-06)으로 네 모듈을 돌려 웹 구축 전 단계의 산출물을 만든다.

python build_outputs.py   →  outputs/*.csv, outputs/recommendations_detail.jsonl
"""
import sys, json, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from onter import config as C, data as D, features as F, m1_profile as M1, m2_cases as M2, m3_rank as R, m4_feasibility as M4, explain as X, expert as XP

sys.stdout.reconfigure(encoding="utf-8")
K, KP = 10, R.DEFAULT["k_peer"]
out = lambda df, name: df.to_csv(C.OUTPUTS / name, encoding="utf-8-sig")


def main():
    c, p = D.complexes(), D.programs()
    Xb, Xc = F.interactions(C.FIRST_MONTH, C.LAST_MONTH), F.interactions(C.FIRST_MONTH, C.LAST_MONTH, "count")
    X12 = F.interactions(str(pd.Period(C.LAST_MONTH, "M") - 11), C.LAST_MONTH)
    M, T = F.need_membership(), F.target_membership()
    # 모듈 1
    prof = M1.profile()
    out(prof, "m1_complex_profile.csv")
    need, Q = M1.need_table("S"), M1.target_distribution()
    out(Q.round(4), "m1_target_distribution.csv")
    # 모듈 2
    sims = {k: M2.sim_matrix(k) for k in ("hybrid", "struct", "geo", "behav")}
    act = F.active_complexes(C.FIRST_MONTH, C.LAST_MONTH)
    rows = []
    for cid in c.index:
        for kind in ("hybrid", "struct", "geo"):
            for r_, (pid, s) in enumerate(M2.peers(sims[kind], cid, 10, pool=act).items(), 1):
                rows.append(dict(complex_id=cid, kind=kind, rank=r_, peer_id=pid, peer=c.at[pid, "name"], similarity=round(float(s), 4),
                                 struct_sim=round(float(sims["struct"].at[cid, pid]), 3), behav_sim=round(float(sims["behav"].at[cid, pid]), 3),
                                 geo_sim=round(float(sims["geo"].at[cid, pid]), 3), same_branch=int(c.at[cid, "branch"] == c.at[pid, "branch"])))
    pd.DataFrame(rows).to_csv(C.OUTPUTS / "m2_complex_peers.csv", index=False, encoding="utf-8-sig")
    IS = M2.item_sim("hybrid")
    # 모듈 3
    cand = (Xb == 0).to_numpy()                                   # 전체 기간에 한 번도 안 한 프로그램
    parts = {}
    S = R.onter_scores(Xb, sims["hybrid"], M, T, cand=cand, parts_out=parts)
    top = R.calibrated_topk(S, cand, M, Q, K, R.DEFAULT["lam"])
    Sall = R.onter_scores(Xb, sims["hybrid"], M, T)               # 분야별 순위·재개 검토용(전체 프로그램)
    nf_rank, ev_rank = R.row_rank(parts["need"]).to_numpy(), R.row_rank(parts["evidence"], cand).to_numpy()
    # 모듈 4
    req, cap = M4.requirements(), M4.capacity()
    expert = XP.available()                                       # 전문가 검토값이 있으면 요건을 그 값으로 바꾼다(초안은 *_draft 열)
    if expert:
        req = M4.apply_expert(req, XP.sheet_b())
        feas, comp = M4.feasibility_expert(req, cap)
    else:
        feas, comp = M4.feasibility(req, cap)
    out(req.round(3), "m4_program_requirements.csv")
    out(cap.round(3), "m4_complex_capacity.csv")
    dep = pd.read_csv(C.TABLES / "e5_deployment_dependence.csv").set_index("std_id") if (C.TABLES / "e5_deployment_dependence.csv").exists() else None
    items = list(Xb.columns)
    recs, detail, dom_rows = [], [], []
    for u, cid in enumerate(c.index):
        nb = M2.peers(sims["hybrid"], cid, KP, pool=act).index
        for r_, j in enumerate(top[u], 1):
            sid = items[j]
            d = p.at[sid, "need_primary"] if isinstance(p.at[sid, "need_primary"], str) else None
            rec = dict(complex_id=cid, complex=c.at[cid, "name"], rank=r_, std_id=sid, name=p.at[sid, "name"], family=p.at[sid, "family_label"], domain=d,
                       score=float(S.iat[u, j]), evidence_pct=float(ev_rank[u, j]), need_fit_pct=float(nf_rank[u, j]),
                       need_pct=float(need.at[cid, d]) if d else float(need.loc[cid].mean()), peer_n=int(Xb.loc[nb, sid].sum()), peer_k=len(nb),
                       pop=float(Xb.loc[act, sid].mean()), feasibility=float(feas.iat[u, j]),
                       welfare_worker_dependent=bool(dep is not None and sid in dep.index and dep.at[sid, "lo"] > 1))
            rec["check"] = M4.checklist(sid, cid, req, cap, comp)
            rec["welfare_worker_needed_expert"] = bool(rec["check"].get("needs_welfare_worker", False))
            rec["welfare_gap"] = bool(rec["check"].get("welfare_gap", False))
            rec["evidence"] = M2.evidence_bundle(cid, sid, sims["hybrid"], IS, 3)
            rec["explanation"] = X.explain(rec)["text"]
            detail.append(rec)
            recs.append({k: v for k, v in rec.items() if k not in ("check", "evidence")} | {"n_peer_cases": len(rec["evidence"]["peer_records"]),
                        "n_casebook": len(rec["evidence"]["casebook"]), "n_news": len(rec["evidence"]["news"]), "cost_year_est": rec["check"]["cost_year_est"],
                        "staff_tier": rec["check"]["staff_tier"], "partner_needed": rec["check"]["partner_needed"], "requirement_basis": rec["check"]["basis"]})
        # 분야별 순위: 그 분야가 주 분야인 프로그램을 점수순으로 3개(이미 하는 것은 '유지', 12개월 넘게 쉰 것은 '재개 검토')
        for d in C.NEED_IDS:
            its = [i for i in items if p.at[i, "need_primary"] == d]
            for r_, sid in enumerate(Sall.loc[cid, its].nlargest(3).index, 1):
                st = "신규 검토" if Xb.at[cid, sid] == 0 else ("유지" if X12.at[cid, sid] > 0 else "재개 검토")
                dom_rows.append(dict(complex_id=cid, domain=d, domain_label=C.NEED[d], rank=r_, std_id=sid, name=p.at[sid, "name"], status=st,
                                     score=round(float(Sall.at[cid, sid]), 4), need_pct=round(float(need.at[cid, d]), 3)))
    pd.DataFrame(recs).round(4).to_csv(C.OUTPUTS / "m3_recommendations_top10.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(dom_rows).to_csv(C.OUTPUTS / "m3_ranking_by_domain.csv", index=False, encoding="utf-8-sig")
    with open(C.OUTPUTS / "recommendations_detail.jsonl", "w", encoding="utf-8") as f:
        for r_ in detail:
            f.write(json.dumps(r_, ensure_ascii=False, default=float) + "\n")
    # 기본 제약의 연간 묶음(6개 이내, 필요 상위 두 분야에서 1개 이상). 전문가 요건: 공단 쪽 예산 100만 원·인력 80명×시간. 초안 요건: 300만 원·부담 6점
    plans = []
    for u, cid in enumerate(c.index):
        s = S.loc[cid].where(Xb.loc[cid] == 0).dropna()
        pl = M4.plan(s, req, p["need_primary"], budget=1e6 if expert else 3e6, load=M4.LOAD_HOURS if expert else 6.0, n_max=6,
                     min_per_domain={d: 1 for d in need.loc[cid].nlargest(2).index})
        plans.append(dict(complex_id=cid, complex=c.at[cid, "name"], items="|".join(pl["items"]), names=" | ".join(p.loc[pl["items"], "name"]),
                          cost_year_est=round(pl["cost"]), staff_load=round(pl["load"], 2), feasible=pl["feasible"]))
    pd.DataFrame(plans).to_csv(C.OUTPUTS / "m4_default_plan.csv", index=False, encoding="utf-8-sig")
    chk = [X.check_grounded(r_["explanation"], r_)["ok"] for r_ in detail]
    cov = pd.DataFrame(recs)
    summary = dict(n_complexes=len(c), n_recs=len(recs), explanation_grounded_share=float(np.mean(chk)), with_peer_case=float((cov["n_peer_cases"] > 0).mean()),
                   with_casebook=float((cov["n_casebook"] > 0).mean()), with_news=float((cov["n_news"] > 0).mean()),
                   distinct_programs=int(cov["std_id"].nunique()), dependent_share=float(cov["welfare_worker_dependent"].mean()),
                   requirement_basis="expert" if expert else "draft", welfare_gap_share=float(cov["welfare_gap"].mean()),
                   plan_feasible_share=float(pd.DataFrame(plans)["feasible"].mean()))
    (C.OUTPUTS / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(summary)
    print(detail[0]["explanation"])


if __name__ == "__main__":
    main()
