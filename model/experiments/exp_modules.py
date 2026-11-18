"""E1 필요 지수 타당도 · E2 유사 단지 정의 비교 · E5 실행 검토 검증 · E6 해피콜 유사 정답 · E7 사례·프로그램 검색.

python experiments/exp_modules.py
"""
import time, itertools
from common import *
from exp_ranking import fusion, calib


def e1():
    need = M1.need_table("S")
    c = D.complexes()
    ev = np.linalg.eigvalsh(np.corrcoef(need.to_numpy().T))[::-1]
    put_summary("need_pca_share", list((ev / ev.sum()).round(3)))
    save(need.corr(method="spearman").round(3).reset_index(), "e1_need_domain_corr")
    lo, hi = M1.need_uncertainty("S", n_draw=300)
    top = need >= 2 / 3
    stab = [dict(domain=d, label=C.NEED[d], width_median=(hi[d] - lo[d]).median(), width_p90=(hi[d] - lo[d]).quantile(0.9),
                 top_third_robust=float((lo[d][top[d]] >= 0.5).mean()), n_indicators=len(M1.INDICATORS[d]["S"])) for d in C.NEED_IDS]
    save(pd.DataFrame(stab).round(3), "e1_need_stability")
    # 수렴 타당도: 구조 지표만으로 만든 필요 ↔ 지수에 넣지 않은 이용 실적(홈닥터). 규모 통제 편상관도 본다
    rows = []
    for d, col, lab in [("N1", "hd_life", "홈닥터 생활지원"), ("N2", "hd_econ", "홈닥터 경제지원"), ("N3", "hd_medical", "홈닥터 의료지원"),
                        ("N4", "hd_chores", "홈닥터 가사지원"), ("N1", "hd", "홈닥터 전체")]:
        r = E.spearman_ci(need[d], c[col])
        pr, n = E.partial_spearman(need[d], c[col], c[["log_hh"]])
        rows.append(dict(domain=d, criterion=lab, **r, partial_rho_size=pr))
    ld = (c["ld_total"] > 0).astype(float)
    r = E.spearman_ci(need["N1"], ld)
    pr, _ = E.partial_spearman(need["N1"], ld, c[["log_hh"]])
    rows.append(dict(domain="N1", criterion="과거 고독사 기록 유무(점검 전용)", **r, partial_rho_size=pr))
    save(pd.DataFrame(rows).round(3), "e1_need_convergent")
    # 필요와 공급이 따로 노는 정도(문제 정의의 수치화)
    _, sp, _ = M1.supply_table()
    rows = [dict(domain=d, label=C.NEED[d], **E.spearman_ci(need[d], sp[d])) for d in C.NEED_IDS]
    save(pd.DataFrame(rows).round(3), "e1_need_vs_supply")
    gap, pri = M1.gap_table()
    put_summary("priority", dict(per_domain=pri.sum().to_dict(), complexes_any=int((pri.sum(axis=1) > 0).sum()), n=int(pri.notna().all(axis=1).sum())))
    lab, tt, k = M1.typology()
    save(tt.round(3), "e1_typology_k")
    save(M1.describe_types(lab), "e1_typology_types")
    db = M1.demand_base("complex")
    put_summary("happycall_synthetic_sd_pp", (db.std() * 100).round(2).to_dict())
    put_summary("demand_vs_supply_base", dict(demand=M1.demand_base("national").round(3).to_dict(), supply=M1.supply_base().round(3).to_dict()))
    print("e1 done")


def e2():
    rows, hom = [], []
    kinds = ["demo", "struct", "need", "behav", "geo", "branch", "hybrid"]
    Xs, Nd = F.matrix(F.STRUCT).to_numpy(), M1.need_table("S").to_numpy()
    c = D.complexes()
    km = F.haversine(c["lat"], c["lon"])
    for fn in ("A", "B"):
        f = Fold(fn)
        base = f.rank(f.score("pop"))
        act = np.isin(f.X.index, F.active_complexes(*f.tr))
        Bv = F.cosine(M2.behavior_vectors(*f.tr))
        for kind in kinds + ["random"]:
            S = f.sim(kind) if kind != "random" else pd.DataFrame(np.random.default_rng(C.SEED).random((len(f.X),) * 2), index=f.X.index, columns=f.X.index)
            rk = f.rank(R.userknn(f.X, S))
            t = E.paired_boot(rk["ndcg@10"], base["ndcg@10"])
            rows.append(dict(fold=fn, sim=kind, ndcg10=rk["ndcg@10"].mean(), recall10=rk["recall@10"].mean(), auc=rk["auc"].mean(), d_vs_pop=t["diff"], p_vs_pop=t["p"]))
            Sm = S.to_numpy().copy()
            Sm[:, ~act] = -1
            np.fill_diagonal(Sm, -1)
            nb = np.argsort(-Sm, axis=1)[:, :10]
            i = np.arange(len(Sm))[:, None]
            hom.append(dict(fold=fn, sim=kind, struct_dist=np.linalg.norm(Xs[i] - Xs[nb], axis=2).mean(), need_absdiff=np.abs(Nd[i] - Nd[nb]).mean(),
                            behav_cos=Bv[i, nb][act].mean(), same_branch=(c["branch"].to_numpy()[i] == c["branch"].to_numpy()[nb]).mean(), km_median=float(np.median(km[i, nb]))))
        if fn == "A":                                           # 혼합 가중치는 A에서 고르고 B에서 확인한다
            grid = []
            for ws, wb in itertools.product([0, 0.25, 0.5, 0.75, 1], repeat=2):
                if ws + wb <= 1:
                    w = {k: v for k, v in dict(struct=ws, behav=wb, geo=round(1 - ws - wb, 2)).items() if v > 0}
                    rk = f.rank(R.userknn(f.X, M2.sim_matrix("hybrid", *f.tr, weights=w)))
                    grid.append(dict(struct=ws, behav=wb, geo=round(1 - ws - wb, 2), ndcg10=rk["ndcg@10"].mean(), auc=rk["auc"].mean()))
            save(pd.DataFrame(grid).round(4), "e2_hybrid_weight_grid_foldA")
    save(pd.DataFrame(rows).round(4), "e2_similarity_predictive")
    save(pd.DataFrame(hom).round(3), "e2_similarity_homogeneity")
    print("e2 done")


def e5():
    f = Fold(C.MAIN_FOLD)
    req, cap = M4.requirements(*f.tr), M4.capacity(*f.tr)
    tot, comp = M4.feasibility(req, cap)
    rows = []
    for n, S in [("실행 가능성(종합)", tot)] + [(f"성분: {k}", v) for k, v in comp.items()]:
        rk = f.rank(S)
        mu, lo, hi = E.boot_mean(rk["auc"])
        rows.append(dict(score=n, auc=mu, lo=lo, hi=hi))
    ev = f.score("evidence")
    b = f.rank(ev)
    for w in (0.1, 0.2, 0.3):
        rk = f.rank(R.fuse({"e": ev, "f": tot}, {"e": 1 - w, "f": w}, cand=f.cand))
        t = E.paired_boot(rk["ndcg@10"], b["ndcg@10"])
        rows.append(dict(score=f"근거 + 실행 가능성(w={w}) NDCG@10 차", auc=rk["auc"].mean(), lo=t["lo"], hi=t["hi"], d_ndcg=t["diff"], p=t["p"]))
    save(pd.DataFrame(rows).round(4), "e5_feasibility_validity")
    # 요건이 실제로 도입을 가르는가: 후보(아직 안 한 프로그램) 쌍에서 조건별 새 도입률
    el, cand, new = f.el, f.cand, f.new
    pr = req["partner_rate"].to_numpy()[None, :] >= 0.4
    og = req[[f"og_{o}" for o in M4.OG_IDS]].fillna(0).to_numpy()
    avail = cap[[f"a_{o}" for o in M4.OG_IDS]].to_numpy() @ og.T / np.maximum(og.sum(1)[None, :], 1e-9)
    lift = []

    def rate(mask, label, level):
        m = mask & cand & el[:, None]
        k, n = new[m].sum(), m.sum()
        se = np.sqrt(k / n * (1 - k / n) / n) if n else np.nan
        lift.append(dict(condition=label, level=level, pairs=int(n), new_rate=k / n if n else np.nan, lo=k / n - 1.96 * se, hi=k / n + 1.96 * se))

    for lv, mk in [("협력 여건 높음(0.85 이상)", avail >= 0.85), ("중간", (avail >= 0.55) & (avail < 0.85)), ("낮음(0.55 미만)", avail < 0.55)]:
        rate(pr & mk, "협력기관이 필요한 프로그램(협력 표기율 40% 이상)", lv)
    hv = req["household_visit"].to_numpy()[None, :] >= 0.3
    dep = cap["deployed"].to_numpy()[:, None] == 1
    for lv, mk in [("주거복지사 배치", dep), ("미배치", ~dep)]:
        rate(hv & mk, "세대 방문형 프로그램(방문 비중 30% 이상)", lv)
        rate(~hv & mk, "그 밖의 프로그램", lv)
    sp = (req["place_senior"].to_numpy()[None, :] >= 0.3)
    for lv, mk in [("경로당 있음", cap["sp_senior"].to_numpy()[:, None] == 1), ("경로당 없음", cap["sp_senior"].to_numpy()[:, None] == 0)]:
        rate(sp & mk, "경로당에서 주로 하는 프로그램", lv)
    save(pd.DataFrame(lift).round(4), "e5_requirement_lift")
    # 주거복지사 의존도: 영구임대 포함 단지에서 규모 3분위로 층화한 MH 오즈비(전체 기간)
    c = D.complexes()
    Xf = F.interactions(C.FIRST_MONTH, C.LAST_MONTH)
    mk = (c["perm"] == 1) & c.index.isin(F.active_complexes(C.FIRST_MONTH, C.LAST_MONTH))
    strata = pd.qcut(c.loc[mk, "hh"], 3, labels=False).to_numpy()
    g = c.loc[mk, "deployed"].to_numpy()
    mh = []
    for it in Xf.columns:
        y = Xf.loc[mk, it].to_numpy()
        if 10 <= y.sum() <= len(y) - 10:
            o, lo, hi = M4.mh_odds_ratio(y, g, strata)
            mh.append(dict(std_id=it, name=D.programs().at[it, "name"], adopt_deployed=y[g == 1].mean(), adopt_not=y[g == 0].mean(), mh_or=o, lo=lo, hi=hi))
    mh = pd.DataFrame(mh).sort_values("mh_or", ascending=False)
    save(mh.round(3), "e5_deployment_dependence")
    put_summary("deployment_dependence", dict(n_programs=len(mh), n_or_gt1_sig=int((mh["lo"] > 1).sum()), n_or_lt1_sig=int((mh["hi"] < 1).sum()), median_or=float(mh["mh_or"].median())))
    # 제약 묶음 선택: 탐욕 vs 정수계획
    S = fusion(f, 0.2)
    prim = D.programs()["need_primary"]
    need = M1.need_table("S")
    out = []
    for budget in (1e6, 3e6, 1e7):
        t0, vals = time.time(), []
        for cid in f.X.index[el]:
            s = S.loc[cid].where(f.fd["cand_new"].loc[cid]).dropna()
            mind = {d: 1 for d in need.loc[cid].nlargest(2).index}
            a = M4.plan(s, req, prim, budget=budget, load=6.0, n_max=6, min_per_domain=mind, method="milp")
            b_ = M4.plan(s, req, prim, budget=budget, load=6.0, n_max=6, min_per_domain=mind, method="greedy")
            vals.append((a["value"], b_["value"], len(a["items"]), a["cost"], a["load"], b_["cost"] <= budget and b_["load"] <= 6.0))
        v = np.array(vals, float)
        out.append(dict(budget=budget, milp_value=v[:, 0].mean(), greedy_value=v[:, 1].mean(), greedy_ratio=(v[:, 1] / np.maximum(v[:, 0], 1e-9)).mean(),
                        greedy_feasible=v[:, 5].mean(), n_items=v[:, 2].mean(), cost=v[:, 3].mean(), load=v[:, 4].mean(), sec_per_complex=(time.time() - t0) / len(v) / 2))
    save(pd.DataFrame(out).round(4), "e5_portfolio")
    print("e5 done")


def e6():
    c, h = D.complexes(), D.happycall_scores()
    Q = M1.target_distribution()
    rate, sp, share = M1.supply_table()
    gap, pri = M1.gap_table()
    d = pd.DataFrame({"align_status_quo": 1 - E.jsd(share.fillna(0).to_numpy(), Q.to_numpy()), "supply_rate": rate.sum(axis=1), "n_priority": pri.sum(axis=1),
                      "richness": M1.history()["richness"]}, index=c.index)
    d.loc[share.isna().all(axis=1)] = np.nan
    d = d.join(h[["welfare_satisfaction", "overall_satisfaction", "small_sample", "n_total"]]).join(c[["log_hh", "age60", "perm"]])
    rows = []
    for sub, mk in [("전체", d["welfare_satisfaction"].notna()), ("표본 30명 이상", d["welfare_satisfaction"].notna() & (d["small_sample"] == False))]:
        for x in ("align_status_quo", "supply_rate", "n_priority", "richness"):
            for y in ("welfare_satisfaction", "overall_satisfaction"):
                r = E.spearman_ci(d.loc[mk, x], d.loc[mk, y])
                pr, _ = E.partial_spearman(d.loc[mk, x], d.loc[mk, y], d.loc[mk, ["log_hh", "age60", "perm"]])
                rows.append(dict(subset=sub, x=x, y=y, **r, partial_rho=pr))
    save(pd.DataFrame(rows).round(3), "e6_happycall_outcome")
    # 전국 합계 수준: 추천이 공급을 주민 수요 쪽으로 옮기는가. 해피콜을 기준 분포에 쓰지 않은 구성(base=uniform)으로 본다
    f = Fold(C.MAIN_FOLD)
    Qu = M1.target_distribution(base="uniform", beta=2.0, start=f.tr[0], end=f.tr[1])
    tops = {"채택률": f.top(f.score("pop")), "근거": f.top(f.score("evidence")), "온터(해피콜 미사용: base=uniform)": calib(f, 0.25, fusion(f, 0.2), Q=Qu),
            "온터(기본)": calib(f, 0.25, fusion(f, 0.2))}
    sup = F.interactions(*f.tr, "count").to_numpy()
    idx = np.where(f.el)[0]
    rng = np.random.default_rng(C.SEED)
    bs = {k: [] for k in list(tops) + ["현재 공급"]}
    for _ in range(1000):
        b = rng.choice(idx, len(idx))
        for k, t in tops.items():
            bs[k].append(demand_align(t[b], f.X.columns))
        bs["현재 공급"].append(demand_align(None, f.X.columns, weights=sup[b].sum(0)))
    rows = []
    for k, v in bs.items():
        v, ref = np.array(v), np.array(bs["현재 공급"])
        point = demand_align(tops[k][idx], f.X.columns) if k in tops else demand_align(None, f.X.columns, weights=sup[idx].sum(0))
        rows.append(dict(source=k, demand_align=point, lo=np.quantile(v, 0.025), hi=np.quantile(v, 0.975), diff_vs_supply=(v - ref).mean(),
                         diff_lo=np.quantile(v - ref, 0.025), diff_hi=np.quantile(v - ref, 0.975)))
    save(pd.DataFrame(rows).round(4), "e6_demand_alignment")
    cat = purpose_category().reindex(f.X.columns).to_numpy()
    dist = lambda t: pd.Series(cat[t[idx].ravel()]).dropna().value_counts(normalize=True)
    tab = pd.DataFrame({"해피콜 수요": demand_dist(), "현재 공급": pd.Series(sup[idx].sum(0), index=cat).groupby(level=0).sum().pipe(lambda s: s / s.sum()),
                        "근거 추천": dist(tops["근거"]), "온터 추천(base=uniform)": dist(tops["온터(해피콜 미사용: base=uniform)"]), "온터 추천(기본)": dist(tops["온터(기본)"])})
    save(tab.round(3).reset_index(names="수요 항목"), "e6_demand_distribution")
    print("e6 done")


def e7():
    f = Fold(C.MAIN_FOLD)
    items = list(D.programs().index)
    tr, te = F.window(*f.tr), F.window(*f.fd["te"])
    te = te[te["std_id"].isin(items) & ~te["title_norm"].isin(set(tr["title_norm"]))].drop_duplicates("title_norm")
    te = te.sample(min(3000, len(te)), random_state=C.SEED)
    q_rec = (te["program_name_masked"].fillna("") + " " + te["activity_content_masked"].fillna("")).str.slice(0, 200)
    ar = D.news()["articles"]
    ar = ar[(ar["is_representative"] == 1) & ar["primary_std_id"].isin(items)]
    cards = D.casebook()["cards"]
    cards = cards[cards["std_id"].isin(items)]
    sets = {"처음 보는 활동 제목(평가 구간 기록)": (q_rec, te["std_id"]), "뉴스 제목": (ar["title_masked"].fillna(ar["title"]), ar["primary_std_id"]),
            "사례집 카드 본문": (cards["card_text"].str.slice(0, 600), cards["std_id"])}
    idxs = {"사전 정의만": M2.ProgramSearch(M2.program_docs()), "사전 + 학습 구간 제목": M2.ProgramSearch(M2.train_title_docs(*f.tr))}
    rows = []
    for iname, ps in idxs.items():
        for sname, (q, y) in sets.items():
            yi = np.array([items.index(v) for v in y])
            for m in ("tfidf", "lsa", "bm25", "rrf"):
                rank = (-ps.scores(q.tolist(), m)).argsort(1).argsort(1)[np.arange(len(yi)), yi] + 1
                rows.append(dict(index=iname, queries=sname, n=len(yi), method=m, hit1=(rank == 1).mean(), hit3=(rank <= 3).mean(), mrr=(1 / rank).mean()))
    save(pd.DataFrame(rows).round(3), "e7_retrieval")
    print("e7 done")


if __name__ == "__main__":
    for fn in (e1, e2, e5, e6, e7):
        fn()
