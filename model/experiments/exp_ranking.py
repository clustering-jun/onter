"""E3 순위 모델 비교 · E4 절제와 교환 관계(새 도입 예측 ↔ 필요 정렬).

python experiments/exp_ranking.py
"""
from common import *
from sklearn.ensemble import HistGradientBoostingClassifier

BASE = ["random", "pop", "pop_recent", "diffusion", "branch_pop", "type_pop", "knn_demo", "knn_struct", "knn_need", "knn_behav", "knn_geo",
        "knn_branch", "knn_hybrid", "itemknn", "ease", "svd", "als", "ridge", "need_fit", "evidence", "evidence+"]


def fusion(f, w, ev="evidence"):
    return R.fuse({"evidence": f.score(ev), "need": f.NF}, {"evidence": 1 - w, "need": w}, cand=f.cand)


def two_stage(f, n, ev="evidence"):
    """1단계: 근거 점수 상위 n개를 후보로. 2단계: 후보 안에서 필요 적합 순."""
    r_ev = R.row_rank(f.score(ev), f.cand).fillna(0).to_numpy()
    order = np.argsort(-r_ev, axis=1)
    pool = np.zeros_like(r_ev, bool)
    np.put_along_axis(pool, order[:, :n], True, axis=1)
    return pd.DataFrame(np.where(pool, 2 + np.nan_to_num(f.NFr), r_ev), index=f.X.index, columns=f.X.columns)


def calib(f, lam, S=None, Q=None):
    return R.calibrated_topk(f.score("evidence") if S is None else S, f.cand, f.M, f.Q if Q is None else Q, K, lam)


def ltr_features(f):
    names = ["pop", "pop_recent", "diffusion", "branch_pop", "type_pop", "knn_struct", "knn_behav", "knn_geo", "ease", "itemknn", "ridge", "need_fit"]
    cols = [f.score(n).to_numpy().ravel() for n in names]
    n, m = f.X.shape
    cols += [np.repeat(f.c["log_hh"].to_numpy(), m), np.repeat(f.c["deployed"].to_numpy(), m), np.repeat(f.X.sum(1).to_numpy(), m)]
    return np.column_stack(cols), names + ["log_hh", "deployed", "n_items_train"]


def select(f, keep=0.9, min_align=0.95):
    """기본값 고르기(검증 분할에서): 새 도입 재현율이 근거 모델의 90% 이상, 필요 정렬 0.95 이상인 구성 중 필요 적합이 가장 큰 것."""
    ref = f.row("evidence", f.top(f.score("evidence")))[0]["recall10"]
    rows = []
    for w in [0, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4]:
        for lam in [0, 0.25, 0.5, 0.75]:
            r = f.row("grid", calib(f, lam, fusion(f, w)) if lam else f.top(fusion(f, w)), w=w, lam=lam)[0]
            r["ok"] = int(r["recall10"] >= keep * ref and r["need_align"] >= min_align)
            rows.append(r)
    g = pd.DataFrame(rows)
    best = g[g.ok == 1].sort_values("need_gain", ascending=False).iloc[0]
    return g, float(best["w"]), float(best["lam"]), ref


def run():
    global W, LAM
    folds = {k: Fold(k) for k in C.FOLDS}
    grid, W, LAM, ref = select(folds["A"])
    save(grid.round(4), "e4_select_grid_foldA")
    put_summary("onter_default", dict(w_need=W, lam=LAM, rule="검증 분할 A에서 재현율≥근거의 90%·필요 정렬≥0.95 중 필요 적합 최대", evidence_recall_A=ref))
    print("selected", W, LAM)
    rows, per = [], {}
    for fn, f in folds.items():
        for m in BASE:
            row, lm = f.row(m, f.top(f.score(m)))
            rk = f.rank(f.score(m))
            row.update(auc=rk["auc"].mean(), mrr=rk["mrr"].mean(), hit10=rk["hit@10"].mean(), n=int(lm["ndcg"].notna().sum()))
            rows.append(row)
            per[(fn, m)] = lm
        # 온터 기본(융합 + 필요 보정)과 그 사이 전략들
        for label, top in [("onter_fusion(w=0.4)", f.top(fusion(f, 0.4))), ("onter_two_stage(n=20)", f.top(two_stage(f, 20))),
                           ("onter_calib(λ=0.5)", calib(f, 0.5)), ("onter", calib(f, LAM, fusion(f, W)))]:
            row, lm = f.row(label, top)
            row["n"] = int(lm["ndcg"].notna().sum())
            rows.append(row)
            per[(fn, label)] = lm
    # 행동 지도학습(LTR): A 구간의 (특징→새 도입)으로 학습해 C 구간에 적용. B는 평가 기간이 A의 정답과 겹쳐 쓰지 않는다
    fa, fc = folds["A"], folds["C"]
    Xa, names = ltr_features(fa)
    mask_a = (fa.cand & fa.el[:, None]).ravel()
    for tag, keep in [("ltr_gbdt", list(range(len(names)))), ("ltr_gbdt(-need_fit)", [i for i, n in enumerate(names) if n != "need_fit"])]:
        gb = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_depth=3, random_state=C.SEED).fit(Xa[mask_a][:, keep], fa.new.ravel()[mask_a])
        Xcf, _ = ltr_features(fc)
        s = gb.predict_proba(Xcf[:, keep])[:, 1].reshape(fc.X.shape)
        row, lm = fc.row(tag, fc.top(s))
        rk = fc.rank(s)
        row.update(auc=rk["auc"].mean(), mrr=rk["mrr"].mean(), hit10=rk["hit@10"].mean(), n=int(lm["ndcg"].notna().sum()))
        rows.append(row)
        per[("C", tag)] = lm
    res = save(pd.DataFrame(rows).round(4), "e3_ranking_models")

    # 주 분할(B)에서 채택률 기준선 대비 짝지은 부트스트랩 검정
    tests = []
    for (fn, m), lm in per.items():
        if fn != C.MAIN_FOLD or m == "pop":
            continue
        for met in ("ndcg", "need_align", "need_gain"):
            t = E.paired_boot(lm[met], per[(fn, "pop")][met])
            tests.append(dict(model=m, metric=met, **t))
    tests = pd.DataFrame(tests)
    tests["p_holm"] = tests.groupby("metric")["p"].transform(lambda p: E.holm(p.to_numpy()))
    save(tests.round(4), "e3_tests_vs_pop")

    # E4-1 교환 관계: 세 전략의 조절 손잡이를 돌린다
    f = folds[C.MAIN_FOLD]
    tr = []
    for w in [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0]:
        tr.append(dict(f.row("fusion", f.top(fusion(f, w)), knob=w)[0]))
    for n in [10, 12, 15, 20, 25, 30, 40, 60, 96]:
        tr.append(dict(f.row("two_stage", f.top(two_stage(f, n)), knob=n)[0]))
    for lam in [0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.97]:
        tr.append(dict(f.row("calib", calib(f, lam), knob=lam)[0]))
    for n in [15, 20, 30]:
        for lam in [0.25, 0.5, 0.75]:
            tr.append(dict(f.row("two_stage+calib", calib(f, lam, two_stage(f, n)), knob=n + lam)[0]))
    save(pd.DataFrame(tr).round(4), "e4_tradeoff")

    # E4-2 절제: 기본 구성에서 하나씩 빼거나 바꾼다
    ab = []
    def add(label, top):
        row, lm = f.row(label, top)
        d = E.paired_boot(lm["ndcg"], base_lm["ndcg"]); a = E.paired_boot(lm["need_align"], base_lm["need_align"])
        ab.append(dict(row, d_ndcg=d["diff"], p_ndcg=d["p"], d_align=a["diff"], p_align=a["p"]))
    base_top = calib(f, LAM, fusion(f, W))
    _, base_lm = f.row("base", base_top)
    add(f"기본(온터): 융합 w={W} + 보정 λ={LAM}", base_top)
    add("− 필요 보정(λ=0)", f.top(fusion(f, W)))
    add("− 필요 점수(근거만 + 보정)", calib(f, LAM))
    add("− 필요 전부(근거만)", f.top(f.score("evidence")))
    for drop in ("knn_hybrid", "ease", "pop"):
        keep = [k for k in ("knn_hybrid", "ease", "pop") if k != drop]
        f._sc["evidence_tmp"] = R.fuse({k: f.score(k) for k in keep}, cand=f.cand)
        add(f"− 근거 성분 {drop}", calib(f, LAM, fusion(f, W, "evidence_tmp")))
    add("+ 근거에 지사 채택률·확산 속도", calib(f, LAM, fusion(f, W, "evidence+")))
    for kind in ("struct", "behav", "geo", "need", "branch"):
        f._sc["evidence_tmp"] = R.fuse({"p": R.userknn(f.X, f.sim(kind)), "e": f.score("ease"), "o": f.score("pop")}, cand=f.cand)
        add(f"이웃 정의 = {kind}", calib(f, LAM, fusion(f, W, "evidence_tmp")))
    for kk in (5, 10, 40):
        f._sc["evidence_tmp"] = R.fuse({"p": R.userknn(f.X, f.sim("hybrid"), kk), "e": f.score("ease"), "o": f.score("pop")}, cand=f.cand)
        add(f"이웃 수 k={kk}", calib(f, LAM, fusion(f, W, "evidence_tmp")))
    nf0, nfr0 = f.NF, f.NFr
    for label, nf in [("필요 지수에 이용 실적 포함(SE)", R.need_fit(f.X, f.M, need=M1.need_table("SE"), T=f.T)),
                      ("대상 적합 빼기", R.need_fit(f.X, f.M, T=None))]:
        f.NF, f.NFr = nf, R.row_rank(nf, f.cand).to_numpy()
        top = calib(f, LAM, fusion(f, W))
        f.NF, f.NFr = nf0, nfr0                                             # 지표는 기준 필요 점수로 잰다
        add(label, top)
    for base, beta in [("uniform", 2.0), ("supply", 2.0), ("demand_national", 2.0), ("demand", 0.0), ("demand", 1.0), ("demand", 4.0)]:
        Q = M1.target_distribution(base=base, beta=beta, start=f.tr[0], end=f.tr[1])
        add(f"목표 분포: base={base}, β={beta}", calib(f, LAM, fusion(f, W), Q=Q))
    save(pd.DataFrame(ab).round(4), "e4_ablation")

    # 현재 공급의 수요 정렬(현상 유지 기준값)과 분야별 순위 품질
    sup = F.interactions(*f.tr, "count")
    put_summary("demand_align_status_quo_supply", demand_align(None, sup.columns, weights=sup.sum(0).to_numpy()))
    dom = []
    prim = D.programs()["need_primary"].reindex(f.X.columns)
    for d in C.NEED_IDS:
        cm = f.cand & (prim == d).to_numpy()[None, :]
        for m, S in [("pop", f.score("pop")), ("evidence", f.score("evidence")), ("need_fit", f.NF), ("onter_score", fusion(f, W))]:
            rk = E.rank_metrics(np.asarray(S)[f.el], f.new[f.el], cm[f.el], ks=(3,))
            dom.append(dict(domain=d, label=C.NEED[d], model=m, ndcg3=rk["ndcg@3"].mean(), hit3=rk["hit@3"].mean(), n=int(rk["ndcg@3"].notna().sum())))
    save(pd.DataFrame(dom).round(4), "e3_per_domain")

    # 기록 없는 단지(콜드 스타트) 모의: 단지 1/5의 학습 이력을 가리고 평가 구간 전체 운영을 맞힌다
    rng = np.random.default_rng(C.SEED)
    idx = np.where(f.el)[0]
    perm = rng.permutation(idx)
    cs = {m: [] for m in ("pop", "branch_pop", "type_pop", "knn_struct", "knn_geo", "knn_hybrid", "ridge", "need_fit")}
    test_all = f.fd["test"].to_numpy()
    for k in range(5):
        hide = perm[k::5]
        Xm = f.X.copy()
        Xm.iloc[hide] = 0
        S_h = M2.sim_matrix("hybrid", *f.tr, weights={"struct": 0.7, "geo": 0.3})
        sc = {"pop": R.pop(Xm), "branch_pop": R.group_pop(Xm, f.c["branch"]), "type_pop": R.group_pop(Xm, M1.typology(k=3)[0]),
              "knn_struct": R.userknn(Xm, f.sim("struct")), "knn_geo": R.userknn(Xm, f.sim("geo")), "knn_hybrid": R.userknn(Xm, S_h),
              "ridge": R.feature_ridge(Xm), "need_fit": f.NF}
        for m, s in sc.items():
            cs[m].append(E.rank_metrics(s.to_numpy()[hide], test_all[hide], np.ones((len(hide), f.X.shape[1]), bool)))
    cold = []
    for m, parts in cs.items():
        d = pd.concat(parts)
        mu, lo, hi = E.boot_mean(d["ndcg@10"])
        cold.append(dict(model=m, ndcg10=mu, lo=lo, hi=hi, recall10=d["recall@10"].mean(), auc=d["auc"].mean(), n=len(d)))
    save(pd.DataFrame(cold).round(4), "e3_cold_start")

    # 집단별 성능(작은 단지·미배치 단지에서 더 나쁜가)
    fair = []
    lm_o, lm_p = per[(C.MAIN_FOLD, "onter")], per[(C.MAIN_FOLD, "pop")]
    cc = f.c[f.el]
    grp = {"규모": pd.qcut(cc["hh"], 3, labels=["소", "중", "대"]).astype(str), "주거복지사": cc["deployed"].map({1: "배치", 0: "미배치"}), "지역": cc["region"],
           "유형": M1.typology(k=3)[0].reindex(cc.index)}
    for gname, g in grp.items():
        for lv in pd.unique(g):
            mk = (g == lv).to_numpy()
            fair.append(dict(group=gname, level=lv, n=int(mk.sum()), onter_ndcg=lm_o["ndcg"][mk].mean(), pop_ndcg=lm_p["ndcg"][mk].mean(),
                             onter_align=lm_o["need_align"][mk].mean(), pop_align=lm_p["need_align"][mk].mean()))
    save(pd.DataFrame(fair).round(4), "e3_fairness")
    print(res[res.fold == C.MAIN_FOLD][["model", "ndcg10", "recall10", "auc", "need_align", "need_gain", "demand_align", "pop_pct", "coverage"]].to_string())
    return res


if __name__ == "__main__":
    run()
