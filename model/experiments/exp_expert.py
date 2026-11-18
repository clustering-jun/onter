"""E8. 전문가 검토 응답 반영.  python experiments/exp_expert.py

x1 응답의 성격(분포, 프로그램 수준 대 단지 수준, 필요와 실행의 관계)
x2 순위 방법 비교(요청 당시 상위 5개의 등급) + 조절값(w, λ, 실행 가능성) 점검(판정된 후보만 줄 세우는 방식, 반반 나눠 고르고 확인)
x3 성분 점수와 전문가 등급의 관계(필요 적합·근거·채택률·실행 가능성)
x4 필요 지수 검증(D)과 지표 가중치 민감도(C)
x5 실행 요건(B): 초안과의 일치, 전문가 값으로 만든 실행 가능성의 도입 예측, 주거복지사 의존, 묶음 선택 재계산

주의: 평가자 1명. 평가자 간 일치도 없음. 순위 모델 학습에는 쓰지 않는다.
"""
from common import *
from scipy.stats import spearmanr
from onter import expert as X

K5 = 5
DISC = 1 / np.log2(np.arange(K5) + 2)


def setup():
    """요청 엑셀을 만들 때와 같은 조건(전체 기간, 아직 안 한 프로그램만 후보)."""
    s = type("S", (), {})()
    s.a, s.b, s.c = X.sheet_a(), X.sheet_b(), X.sheet_c()
    s.d, s.memo = X.sheet_d()
    s.Xb = F.interactions(C.FIRST_MONTH, C.LAST_MONTH)
    s.items, s.ids = list(s.Xb.columns), list(s.Xb.index)
    s.M, s.T, s.Q = F.need_membership(), F.target_membership(), M1.target_distribution()
    s.S_h = M2.sim_matrix("hybrid")
    s.cand = (s.Xb == 0).to_numpy()
    s.pop = R.pop(s.Xb)
    s.ev = R.fuse({"p": R.userknn(s.Xb, s.S_h), "e": R.ease(s.Xb), "o": s.pop}, cand=s.cand)
    s.nf = R.need_fit(s.Xb, s.M, T=s.T)
    s.req, s.cap = M4.requirements(), M4.capacity()
    s.feas_rule, s.comp_rule = M4.feasibility(s.req, s.cap)
    s.reqx = M4.apply_expert(s.req, s.b)
    s.feas_x, s.comp_x = M4.feasibility_expert(s.reqx, s.cap)
    s.cids = list(s.a["complex_id"].unique())
    # 판정 행렬(단지×프로그램, 판정 없는 칸은 NaN)
    s.G = {g: s.a.pivot(index="complex_id", columns="std_id", values=g).reindex(index=s.ids, columns=s.items) for g in ("need", "feas", "y")}
    s.G["both"] = np.minimum(s.G["need"], s.G["feas"])
    s.judged = s.G["need"].notna().to_numpy()
    return s


def fusion(s, w, wf=0.0, feas=None):
    comp, wt = {"e": s.ev, "n": s.nf}, {"e": 1 - w, "n": w}
    if wf > 0:
        comp["f"], wt["f"] = feas, wf
        wt["e"], wt["n"] = (1 - wf) * (1 - w), (1 - wf) * w
    return R.fuse(comp, wt, cand=s.cand)


def gains(s, top, g):
    """top: {단지: [프로그램 색인…]} → 단지별 (NDCG@5, 평균 등급). 이상적 순서는 그 단지의 판정된 후보 전체에서 구한다."""
    G = s.G[g].to_numpy()
    nd, mean = [], []
    for cid in s.cids:
        u = s.ids.index(cid)
        t = np.asarray(top[cid])[:K5]
        v = np.nan_to_num(G[u, t], nan=0.0)
        ideal = np.sort(G[u, s.judged[u]])[::-1][:K5]
        nd.append((v * DISC[:len(v)]).sum() / max((ideal * DISC[:len(ideal)]).sum(), 1e-9))
        mean.append(v.mean())
    return np.array(nd), np.array(mean)


def condensed(s, S=None, lam=0.0):
    """판정된 후보만 점수로 줄 세운 상위 5개(판정 없는 후보가 끼지 않게 하는 방식). lam>0이면 필요 보정 재순위."""
    if lam > 0:
        top = R.calibrated_topk(S, s.judged, s.M, s.Q, K5, lam)
        return {cid: top[s.ids.index(cid)] for cid in s.cids}
    A = np.asarray(S, float)
    rng = np.random.default_rng(C.SEED)
    out = {}
    for cid in s.cids:
        u = s.ids.index(cid)
        j = np.where(s.judged[u])[0]
        j = j[rng.permutation(len(j))]
        out[cid] = j[np.argsort(-A[u, j], kind="stable")][:K5]
    return out


def within(s, S, g, min_n=6):
    """단지 안에서 점수와 전문가 등급의 순위상관(단지별로 구해 평균)."""
    A, G = np.asarray(S, float), s.G[g].to_numpy()
    r = []
    for cid in s.cids:
        u = s.ids.index(cid)
        j = np.where(s.judged[u])[0]
        if len(j) >= min_n and np.std(G[u, j]) > 0 and np.std(A[u, j]) > 0:
            r.append(spearmanr(A[u, j], G[u, j])[0])
    return np.array(r)


# ───────── x1 응답의 성격 ─────────
def x1(s):
    a = s.a
    rows = [dict(item=f"{g} 등급 {v}", n=int(n), share=n / len(a)) for g in ("need", "feas") for v, n in a[g].value_counts().sort_index().items()]
    rows.append(dict(item="우선 추천 Y", n=int(a.y.sum()), share=a.y.mean()))
    per = a.groupby("complex_id")["y"].sum()
    rows.append(dict(item="단지별 Y 개수(최소~최대)", n=int(per.min()), share=float(per.max())))
    save(pd.DataFrame(rows).round(4), "e8_a_distribution")
    # 분산 분해: 등급이 프로그램에 따라 정해지는가, 단지에 따라 달라지는가
    dec = []
    for g in ("need", "feas", "y"):
        tot = ((a[g] - a[g].mean()) ** 2).sum()
        r2 = lambda key: 1 - ((a[g] - a.groupby(key)[g].transform("mean")) ** 2).sum() / tot
        multi = a[a.groupby("std_id")[g].transform("size") >= 2]
        dec.append(dict(grade=g, r2_program=r2("std_id"), r2_complex=r2("complex_id"), sd_total=a[g].std(), sd_within_program=multi.groupby("std_id")[g].std().mean()))
    save(pd.DataFrame(dec).round(4), "e8_a_variance")
    rho = spearmanr(a.need, a.feas)[0]
    src = []
    for m in ("pop", "evidence", "need_fit", "onter", "random"):
        k = a["sources"].str.split("|").apply(lambda x: m in x)
        src.append(dict(source=m, n=int(k.sum()), need=a.loc[k, "need"].mean(), feas=a.loc[k, "feas"].mean(), y_rate=a.loc[k, "y"].mean(),
                        need3=(a.loc[k, "need"] == 3).mean(), feas3=(a.loc[k, "feas"] == 3).mean()))
    save(pd.DataFrame(src).round(4), "e8_a_by_source")
    put_summary("expert_a", dict(n=len(a), complexes=a.complex_id.nunique(), programs=a.std_id.nunique(), raters=1, y_rate=float(a.y.mean()), need_feas_rho=float(rho),
                                 r2_program={d["grade"]: d["r2_program"] for d in dec}, y_per_complex=[int(per.min()), int(per.max())]))
    print("x1 done")


# ───────── x2 순위 방법 비교와 조절값 점검 ─────────
def x2(s):
    rk = pd.read_csv(X.RANKS).sort_values(["complex_id", "method", "rank"])
    col = {sid: j for j, sid in enumerate(s.items)}
    tops = {m: {cid: [col[x] for x in g["std_id"]] for cid, g in d.groupby("complex_id")} for m, d in rk.groupby("method")}
    rows, per = [], {}
    for m in ("pop", "evidence", "need_fit", "onter"):
        r = dict(method=m)
        for g in ("y", "need", "feas", "both"):
            nd, mean = gains(s, tops[m], g)
            per[(m, g)] = nd
            r[f"ndcg5_{g}"], r[f"mean_{g}"] = nd.mean(), mean.mean()
        rows.append(r)
    # 무작위 기준선: 판정된 무작위 후보의 평균 등급
    rnd = s.a[s.a["sources"] == "random"]
    rows.append(dict(method="random(후보 2개)", mean_y=rnd.y.mean(), mean_need=rnd.need.mean(), mean_feas=rnd.feas.mean(), mean_both=np.minimum(rnd.need, rnd.feas).mean()))
    save(pd.DataFrame(rows).round(4), "e8_methods_pooled")
    tests = []
    for g in ("y", "need", "feas", "both"):
        for a_, b_ in [("onter", "pop"), ("onter", "evidence"), ("onter", "need_fit"), ("evidence", "pop"), ("need_fit", "pop")]:
            t = E.paired_boot(per[(a_, g)], per[(b_, g)])
            tests.append(dict(gain=g, a=a_, b=b_, diff=t["diff"], lo=t["lo"], hi=t["hi"], p=t["p"]))
    tests = pd.DataFrame(tests)
    tests["p_holm"] = E.holm(tests["p"].to_numpy())
    save(tests.round(4), "e8_methods_tests")

    # 조절값 격자: 판정된 후보만 줄 세운다
    grid, cache = [], {}
    feas_opts = {"none": None, "rule": s.feas_rule, "expert": s.feas_x}
    for w in (0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0):
        for lam in (0, 0.25, 0.5):
            for fk, wf in [("none", 0.0), ("rule", 0.2), ("expert", 0.1), ("expert", 0.2), ("expert", 0.3)]:
                S = fusion(s, w, wf, feas_opts[fk])
                top = condensed(s, S, lam)
                r = dict(w=w, lam=lam, feas=fk, w_feas=wf)
                for g in ("y", "need", "feas", "both"):
                    nd, mean = gains(s, top, g)
                    r[f"ndcg5_{g}"], r[f"mean_{g}"] = nd.mean(), mean.mean()
                    cache[(w, lam, fk, wf, g)] = nd
                grid.append(r)
    grid = pd.DataFrame(grid)
    save(grid.round(4), "e8_grid_condensed")
    for name, S in [("random", R.random_scores(s.Xb)), ("pop", s.pop), ("evidence", s.ev), ("need_fit", s.nf), ("feas_rule", s.feas_rule), ("feas_expert", s.feas_x)]:
        top = condensed(s, S)
        for g in ("y", "need", "feas", "both"):
            cache[(name, g)] = gains(s, top, g)[0]
    base = pd.DataFrame([dict(model=n, **{f"ndcg5_{g}": cache[(n, g)].mean() for g in ("y", "need", "feas", "both")})
                         for n in ("random", "pop", "evidence", "need_fit", "feas_rule", "feas_expert")])
    save(base.round(4), "e8_base_condensed")

    # 반반 검증: 단지 12곳으로 고르고 나머지 12곳에서 기본값과 비교(500번)
    rng = np.random.default_rng(C.SEED)
    keys = [(r.w, r.lam, r.feas, r.w_feas) for r in grid.itertuples()]
    Y = np.stack([cache[k + ("y",)] for k in keys])                      # 구성×단지
    dflt = keys.index((R.DEFAULT["w_need"], R.DEFAULT["lam"], "none", 0.0))
    nofe = [i for i, k in enumerate(keys) if k[2] == "none"]
    res = {"전체 격자(실행 가능성 포함)": list(range(len(keys))), "w·λ만": nofe}
    half = []
    for label, pool in res.items():
        gain, pick = [], []
        for _ in range(500):
            p = rng.permutation(Y.shape[1])
            tr, te = p[:Y.shape[1] // 2], p[Y.shape[1] // 2:]
            best = pool[int(np.argmax(Y[pool][:, tr].mean(1)))]
            gain.append(Y[best, te].mean() - Y[dflt, te].mean())
            pick.append(best)
        top3 = pd.Series(pick).value_counts().head(3)
        half.append(dict(search=label, default_ndcg5_y=Y[dflt].mean(), best_full_ndcg5_y=Y[pool].mean(1).max(), best_full_config=str(keys[pool[int(np.argmax(Y[pool].mean(1)))]]),
                         holdout_gain_mean=float(np.mean(gain)), holdout_gain_lo=float(np.quantile(gain, 0.025)), holdout_gain_hi=float(np.quantile(gain, 0.975)),
                         share_gain_positive=float(np.mean(np.array(gain) > 0)), most_picked="; ".join(f"{keys[i]} {n / 500:.0%}" for i, n in top3.items())))
    save(pd.DataFrame(half).round(4), "e8_split_half")
    # 결정표: 필요 가중 w를 올릴 때 도입 예측(주 분할)과 전문가 판단이 어떻게 움직이는가
    f = Fold(C.MAIN_FOLD)
    ev_f = f.score("evidence")
    ref = f.row("evidence", f.top(ev_f))[0]["recall10"]
    dec = []
    for w in (0, 0.1, 0.2, 0.3, 0.4, 0.5):
        for lam in (0, 0.25):
            Sf = R.fuse({"e": ev_f, "n": f.NF}, {"e": 1 - w, "n": w}, cand=f.cand)
            top = R.calibrated_topk(Sf, f.cand, f.M, f.Q, K, lam) if lam else f.top(Sf)
            r = f.row("grid", top)[0]
            g = grid[(grid.w == w) & (grid.lam == lam) & (grid.feas == "none")].iloc[0]
            dec.append(dict(w=w, lam=lam, adoption_recall10=r["recall10"], recall_vs_evidence=r["recall10"] / ref, adoption_ndcg10=r["ndcg10"], need_gain=r["need_gain"],
                            need_align=r["need_align"], expert_ndcg5_y=g["ndcg5_y"], expert_mean_need=g["mean_need"], expert_mean_feas=g["mean_feas"]))
    save(pd.DataFrame(dec).round(4), "e8_decision_table")
    put_summary("expert_methods", dict(pooled={r["method"]: {k: r[k] for k in ("ndcg5_y", "mean_y", "mean_need", "mean_feas")} for r in rows[:4]},
                                       random_y=float(rnd.y.mean()), split_half=half))
    print("x2 done")


# ───────── x3 성분 점수와 전문가 등급 ─────────
def x3(s):
    scores = {"채택률": s.pop, "근거 융합": s.ev, "필요 적합": s.nf, "온터 융합(w=0.2)": fusion(s, 0.2), "실행 가능성(규칙)": s.feas_rule, "실행 가능성(전문가 요건)": s.feas_x,
              **{f"전문가 요건 성분: {k}": v for k, v in s.comp_x.items()}}
    rows = []
    for n, S in scores.items():
        r = dict(score=n)
        for g in ("need", "feas", "y"):
            v = within(s, S, g)
            mu, lo, hi = E.boot_mean(v)
            r[f"rho_{g}"], r[f"lo_{g}"], r[f"hi_{g}"] = mu, lo, hi
        rows.append(r)
    save(pd.DataFrame(rows).round(4), "e8_component_validity")
    # 단지에 따른 차이를 맞히는가: 프로그램 평균을 뺀 나머지끼리의 상관(같은 프로그램이 단지마다 다르게 평가된 부분)
    a = s.a.copy()
    u, j = [s.ids.index(c) for c in a.complex_id], [s.items.index(p) for p in a.std_id]
    need = M1.need_table("S")
    prim = D.programs()["need_primary"].reindex(a.std_id).to_numpy()
    a["nf"] = R.row_rank(s.nf, s.cand).to_numpy()[u, j]
    a["need_idx"] = [need.at[c, d] if d in need.columns else np.nan for c, d in zip(a.complex_id, prim)]
    a["feas_x"], a["feas_rule"], a["ev"] = s.feas_x.to_numpy()[u, j], s.feas_rule.to_numpy()[u, j], R.row_rank(s.ev, s.cand).to_numpy()[u, j]
    a = a[a.groupby("std_id")["need"].transform("size") >= 3]
    res = []
    dm = lambda c: a[c] - a.groupby("std_id")[c].transform("mean")
    for g, c in [("need", "nf"), ("need", "need_idx"), ("need", "ev"), ("feas", "feas_x"), ("feas", "feas_rule"), ("y", "nf"), ("y", "ev"), ("y", "feas_x")]:
        k = a[c].notna()
        rho, p = spearmanr(dm(g)[k], dm(c)[k])
        res.append(dict(grade=g, score=c, n=int(k.sum()), rho_within_program=rho, p=p))
    save(pd.DataFrame(res).round(4), "e8_within_program")
    print("x3 done")


# ───────── x4 필요 지수 검증(D)과 지표 가중치(C) ─────────
def expert_weights(c, floor=0.0):
    """적절성 등급(0~3)을 가중치로: 등급/3. 구조 지표(S)만."""
    return {(r.domain, r.col): max(r.rating / 3, floor) for r in c.itertuples() if r.variant == "S"}


def x4(s):
    d = s.d
    need = M1.need_table("S")
    raw = M1.need_raw("S")
    wx = expert_weights(s.c)
    need_x, raw_x = M1.need_table("S", weights=wx), M1.need_raw("S", weights=wx)
    # (1) 분야별: 전문가 배점과 필요 백분위의 단지 간 순위상관(24곳)
    rows = []
    for dom in C.NEED_IDS:
        r = dict(domain=C.NEED[dom])
        for lab, tb in [("current", need), ("expert_weight", need_x)]:
            t = E.spearman_ci(tb.loc[d.index, dom].to_numpy(), d[dom].to_numpy())
            r[f"rho_{lab}"], r[f"lo_{lab}"], r[f"hi_{lab}"] = t["rho"], t["lo"], t["hi"]
        rows.append(r)
    save(pd.DataFrame(rows).round(3), "e8_need_vs_expert_domain")
    # (2) 단지 안 분포: 전문가 배분과 가장 닮은 기준 분포는 무엇인가(1−JSD)
    _, _, share = M1.supply_table()
    nat = M1.demand_base("national")
    cands = {"균등": pd.DataFrame(1 / 6, index=d.index, columns=C.NEED_IDS), "현재 공급 비중": share.loc[d.index].fillna(1 / 6),
             "해피콜 전국 수요": pd.DataFrame(np.tile(nat.to_numpy(), (len(d), 1)), index=d.index, columns=C.NEED_IDS),
             "구조 필요(단지 안 비중)": raw.loc[d.index].div(raw.loc[d.index].sum(1), axis=0),
             "목표 분포 Q(해피콜+필요 기울기)": s.Q.loc[d.index],
             "목표 분포 Q(균등+필요 기울기)": M1.target_distribution(base="uniform").loc[d.index],
             "전문가 평균 배분(자기 제외)": pd.DataFrame([(d.drop(i).mean()).to_numpy() for i in d.index], index=d.index, columns=C.NEED_IDS)}
    al = []
    for n, P in cands.items():
        v = np.array([1 - E.jsd(P.loc[i].to_numpy(), d.loc[i].to_numpy()) for i in d.index])
        prof = np.array([spearmanr(P.loc[i], d.loc[i])[0] if P.loc[i].std() > 0 else np.nan for i in d.index])
        mu, lo, hi = E.boot_mean(v)
        al.append(dict(reference=n, align=mu, lo=lo, hi=hi, profile_rho=np.nanmean(prof)))
    save(pd.DataFrame(al).round(4), "e8_need_distribution_align")
    # (3) 전문가 배분이 '현재 공급의 빈 곳'을 따라가는가: 배점 ~ 필요 백분위 + 공급 백분위
    _, sp, _ = M1.supply_table()
    long = pd.DataFrame({"pts": d.stack(), "need": need.loc[d.index].stack(), "supply": sp.loc[d.index].stack()}).dropna()
    z = (long - long.mean()) / long.std()
    beta = np.linalg.lstsq(np.column_stack([np.ones(len(z)), z["need"], z["supply"]]), z["pts"], rcond=None)[0]
    # (4) 가중치 민감도: 전문가 가중치로 바꾸면 무엇이 달라지는가
    sens = [dict(domain=C.NEED[dom], rho_old_new=spearmanr(need[dom], need_x[dom])[0],
                 top_third_overlap=float(((need[dom] >= 2 / 3) & (need_x[dom] >= 2 / 3)).sum() / (need[dom] >= 2 / 3).sum())) for dom in C.NEED_IDS]
    Sx = R.fuse({"e": s.ev, "n": R.need_fit(s.Xb, s.M, need=need_x, T=s.T)}, {"e": 0.8, "n": 0.2}, cand=s.cand)
    S0 = fusion(s, 0.2)
    t0, tx = E.topk(S0.to_numpy(), s.cand, 10), E.topk(Sx.to_numpy(), s.cand, 10)
    ov = np.mean([len(set(a_) & set(b_)) / 10 for a_, b_ in zip(t0, tx)])
    save(pd.DataFrame(sens).round(4), "e8_weight_sensitivity")
    ck = s.c.assign(domain=s.c["domain"].map(C.NEED))
    save(ck[["domain", "label", "variant", "weight", "rating"]], "e8_indicator_ratings")
    put_summary("expert_need", dict(domain_rho={r["domain"]: r["rho_current"] for r in rows}, domain_rho_expert_weight={r["domain"]: r["rho_expert_weight"] for r in rows},
                                    align={r["reference"]: r["align"] for r in al}, beta_need=float(beta[1]), beta_supply=float(beta[2]),
                                    weight_rho_min=float(min(x["rho_old_new"] for x in sens)), top10_overlap_expert_weight=float(ov),
                                    usage_indicator_rating_mean=float(s.c.loc[s.c.variant == "E", "rating"].mean()), struct_indicator_rating_mean=float(s.c.loc[s.c.variant == "S", "rating"].mean())))
    print("x4 done")


# ───────── x5 실행 요건(B) ─────────
def x5(s):
    b, req = s.b, s.req
    sp = lambda x, y: float(spearmanr(x, y, nan_policy="omit")[0])
    draft_places = [set(k for k in M4.PLACES if q[f"place_{k}"] >= 0.25) for _, q in req.iterrows()]
    draft_og = [set(o for o in sorted(M4.OG_IDS, key=lambda o: -q[f"og_{o}"])[:2] if q[f"og_{o}"] >= 0.08) for _, q in req.iterrows()]
    xp, xo = [set(filter(None, v.split("|"))) for v in b["x_places"]], [set(filter(None, v.split("|"))) for v in b["x_partners"]]
    jac = lambda A, B_: np.mean([len(a_ & b_) / len(a_ | b_) for a_, b_ in zip(A, B_) if a_ | b_])
    hit = lambda A, B_: np.mean([len(a_ & b_) > 0 for a_, b_ in zip(A, B_) if a_ and b_])
    mh = pd.read_csv(C.TABLES / "e5_deployment_dependence.csv").set_index("std_id")
    dep_data = (mh["lo"] > 1).reindex(b.index)
    k = dep_data.notna()
    dd, xx = dep_data[k].astype(int).to_numpy(), b.loc[k, "x_needs_welfare_worker"].to_numpy()
    po = (dd == xx).mean()
    pe = dd.mean() * xx.mean() + (1 - dd.mean()) * (1 - xx.mean())
    agree = [dict(item="1회 비용: 초안(기록 추정 중앙값) 대 전문가", stat="순위상관", value=sp(req["cost_med"], b["x_cost_session"])),
             dict(item="1회 비용: 초안/전문가 비(중앙값)", stat="비", value=float((req["cost_med"] / b["x_cost_session"].replace(0, np.nan)).median())),
             dict(item="인력: 초안 부담 등급 대 전문가 명×시간", stat="순위상관", value=sp(req["staff_tier"], b["x_staff_hours"])),
             dict(item="인력: 초안 부담 등급 대 전문가 난이도", stat="순위상관", value=sp(req["staff_tier"], b["x_difficulty"])),
             dict(item="장소: 초안(25% 이상) 대 전문가 필수 공간", stat="자카드", value=float(jac(draft_places, xp))),
             dict(item="협력기관: 초안 상위 2곳 중 하나라도 전문가 필수 기관에 있음", stat="비율", value=float(hit(draft_og, xo))),
             dict(item=f"주거복지사 의존: 자료(MH 오즈비 유의, {int(dd.sum())}종) 대 전문가(N, {int(xx.sum())}종), 공통 {int((dd & xx).sum())}종", stat="카파", value=float((po - pe) / (1 - pe))),
             dict(item="전문가 '주거복지사 필요' 프로그램의 MH 오즈비 중앙값", stat="오즈비", value=float(mh["mh_or"].reindex(b.index)[b["x_needs_welfare_worker"] == 1].median())),
             dict(item="전문가 '없이 가능' 프로그램의 MH 오즈비 중앙값", stat="오즈비", value=float(mh["mh_or"].reindex(b.index)[b["x_needs_welfare_worker"] == 0].median()))]
    save(pd.DataFrame(agree).round(3), "e8_requirements_agreement")
    out = b.join(req[["name", "cost_med", "staff_tier", "cost_tier"]]).join(mh[["mh_or", "lo"]])
    save(out.reset_index().round(3), "e8_requirements_expert")

    # 전문가 요건으로 만든 실행 가능성이 새 도입을 맞히는가(주 분할, 여건은 학습 구간에서 계산)
    f = Fold(C.MAIN_FOLD)
    req_f, cap_f = M4.requirements(*f.tr), M4.capacity(*f.tr)
    reqx_f = M4.apply_expert(req_f, b)
    rule, _ = M4.feasibility(req_f, cap_f)
    tot, comp = M4.feasibility_expert(reqx_f, cap_f)
    ev = f.score("evidence")
    base = f.rank(ev)
    rows = []
    for n, S in [("규칙 기반(초안 요건)", rule), ("전문가 요건(종합)", tot)] + [(f"전문가 요건 성분: {k}", v) for k, v in comp.items()]:
        rk = f.rank(S)
        mu, lo, hi = E.boot_mean(rk["auc"])
        rows.append(dict(score=n, auc=mu, lo=lo, hi=hi))
    for w in (0.1, 0.2):
        rk = f.rank(R.fuse({"e": ev, "f": tot}, {"e": 1 - w, "f": w}, cand=f.cand))
        t = E.paired_boot(rk["ndcg@10"], base["ndcg@10"])
        rows.append(dict(score=f"근거 + 전문가 요건 실행 가능성(w={w}) NDCG@10 차", auc=rk["auc"].mean(), lo=t["lo"], hi=t["hi"], d_ndcg=t["diff"], p=t["p"]))
    # 조건별 새 도입률: 전문가가 '주거복지사 필요'라고 한 프로그램
    el, cand, new = f.el, f.cand, f.new
    nw = reqx_f["x_needs_welfare_worker"].to_numpy()[None, :] == 1
    dep = cap_f["deployed"].to_numpy()[:, None] == 1
    lift = []
    for lab, pm in [("전문가: 주거복지사 필요", nw), ("전문가: 없이 가능", ~nw)]:
        for lv, cm in [("배치", dep), ("미배치", ~dep)]:
            m = pm & cm & cand & el[:, None]
            kk, n = new[m].sum(), m.sum()
            lift.append(dict(condition=lab, level=lv, pairs=int(n), new_rate=kk / n, se=np.sqrt(kk / n * (1 - kk / n) / n)))
    for lab, lo_, hi_ in [("난이도 1~2", 1, 2), ("난이도 3", 3, 3), ("난이도 4~5", 4, 5)]:
        m = ((reqx_f["x_difficulty"].to_numpy()[None, :] >= lo_) & (reqx_f["x_difficulty"].to_numpy()[None, :] <= hi_)) & cand & el[:, None]
        kk, n = new[m].sum(), m.sum()
        lift.append(dict(condition="전문가 난이도", level=lab, pairs=int(n), new_rate=kk / n, se=np.sqrt(kk / n * (1 - kk / n) / n)))
    save(pd.DataFrame(rows).round(4), "e8_feasibility_validity")
    save(pd.DataFrame(lift).round(4), "e8_requirement_lift")

    # 묶음 선택: 초안 요건 대 전문가 요건(같은 점수, 같은 개수 제한)
    S = R.fuse({"e": ev, "n": f.NF}, {"e": 0.8, "n": 0.2}, cand=f.cand)
    prim, need = D.programs()["need_primary"], M1.need_table("S")
    port = []
    for budget in (5e5, 1e6, 3e6):
        v = []
        for cid in f.X.index[el]:
            sc = S.loc[cid].where(f.fd["cand_new"].loc[cid]).dropna()
            mind = {d_: 1 for d_ in need.loc[cid].nlargest(2).index}
            p0 = M4.plan(sc, req_f, prim, budget=budget * 3, load=6.0, n_max=6, min_per_domain=mind)
            p1 = M4.plan(sc, reqx_f, prim, budget=budget, load=M4.LOAD_HOURS, n_max=6, min_per_domain=mind)
            g1 = M4.plan(sc, reqx_f, prim, budget=budget, load=M4.LOAD_HOURS, n_max=6, min_per_domain=mind, method="greedy")
            ov = len(set(p0["items"]) & set(p1["items"])) / max(len(p1["items"]), 1) if p1["feasible"] else np.nan
            cost0_x = reqx_f["cost_year"].reindex(p0["items"]).sum()
            hrs0_x = reqx_f["staff_load"].reindex(p0["items"]).sum()
            v.append((p1["feasible"], len(p1["items"]), p1["cost"], p1["load"], ov, cost0_x > budget or hrs0_x > M4.LOAD_HOURS, g1["value"] / max(p1["value"], 1e-9),
                      g1["cost"] <= budget and g1["load"] <= M4.LOAD_HOURS))
        v = np.array(v, float)
        port.append(dict(budget=budget, load_hours=M4.LOAD_HOURS, feasible=v[:, 0].mean(), n_items=np.nanmean(v[:, 1]), cost=np.nanmean(v[:, 2]), hours=np.nanmean(v[:, 3]),
                         overlap_with_draft_plan=np.nanmean(v[:, 4]), draft_plan_violates_expert_limits=v[:, 5].mean(), greedy_ratio=v[:, 6].mean(), greedy_feasible=v[:, 7].mean()))
    save(pd.DataFrame(port).round(4), "e8_portfolio_expert")
    put_summary("expert_requirements", dict(agreement={r["item"]: r["value"] for r in agree}, feasibility_auc={r["score"]: r["auc"] for r in rows[:2]},
                                            n_needs_welfare_worker=int(b["x_needs_welfare_worker"].sum()), difficulty_mean=float(b["x_difficulty"].mean())))
    print("x5 done")


if __name__ == "__main__":
    if not X.available():
        print("전문가 응답 파일이 없어 건너뜀")
        sys.exit(0)
    s = setup()
    x1(s), x2(s), x3(s), x4(s), x5(s)
