# -*- coding: utf-8 -*-
"""심화 분석 계산: 프로그램 공급 지형·시간 흐름·단지 간 격차·유형·참여·협력·프로그램 간 관계·단지 여건(통합표)과의 관계.

모든 함수는 표(DataFrame)와 요약 값(dict)을 돌려주며, 보고서의 숫자는 여기서 나온 값을 그대로 쓴다.
통계 기법은 학부 수준에서 설명 가능한 것(분위수·상관·비모수 검정·부트스트랩 신뢰구간·로그-로그 회귀·계층 군집)으로 제한했다.
"""
import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster.hierarchy import linkage, leaves_list
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

from . import taxonomy as TX
from . import typology as TY

# 단지 여건(통합표) 변수와 한글 라벨
CTX = [("인구_60세이상_비율", "60세 이상 인구 비율"), ("인구_70세이상_비율", "70세 이상 인구 비율"), ("인구_20세미만_비율", "20세 미만 인구 비율"),
       ("입주기준경과년수", "입주 후 경과 연수"), ("평형_전용면적가중평균_㎡", "평균 전용면적(㎡)"), ("승강기대수_100세대당", "승강기 수(100세대당)"),
       ("홈닥터_2025_100세대당월평균지원건수", "홈닥터 지원(100세대당 월평균, 2025)"), ("거버넌스_2025_회의건수", "거버넌스 회의 건수(2025)"),
       ("접근성_경로당_대표점_km", "경로당까지 거리(km)"), ("접근성_병원_대표점_km", "병원까지 거리(km)"), ("접근성_보건기관_대표점_km", "보건기관까지 거리(km)"),
       ("접근성_노인복지관_대표점_km", "노인복지관까지 거리(km)")]
OUTCOMES = [("resident_records_per_1000hh_year", "활동량(세대 1000당 연 기록 수)"), ("std_richness", "프로그램 다양성(표준 유형 수)"),
            ("participation_per_100hh_year", "참여 규모(세대 100당 연 참여인원)")]
# 단지 지표 간 상관표에 넣는 변수
CORR_VARS = [("resident_records_per_1000hh_year", "활동량(세대당)"), ("std_richness", "유형 수(다양성)"), ("std_evenness", "고른 정도"), ("std_top1_share", "최다 유형 쏠림"),
             ("ops_evt_Y_share", "행사형 비중"), ("ops_reg_YP_share", "정기 운영 비중"), ("single_day_share", "당일 기록 비중"), ("repeat_record_share", "반복 기록 비중"),
             ("participation_per_100hh_year", "참여 규모(세대당)"), ("share_mou", "업무협약 비중"), ("partner_org_type_richness", "협력기관 유형 수"),
             ("seasonality_cv", "계절 편중")]     # 모형 추정치(비용·부담)는 규칙으로 계산한 값이라 관측 지표와 섞지 않는다


# ───────────────────────── 통계 보조 ─────────────────────────
def gini(v):
    v = np.sort(np.asarray(v, float))
    v = v[~np.isnan(v)]
    n = len(v)
    return float((2 * np.sum(np.arange(1, n + 1) * v) / (n * v.sum())) - (n + 1) / n)


def lorenz(v):
    v = np.sort(np.asarray(v, float))
    v = v[~np.isnan(v)]
    c = np.insert(np.cumsum(v) / v.sum(), 0, 0.0)
    return np.linspace(0, 1, len(c)), c


def spearman_boot(x, y, n_boot=1000, seed=7):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = ~np.isnan(x) & ~np.isnan(y)
    x, y = x[ok], y[ok]
    r, p = stats.spearmanr(x, y)
    rng = np.random.default_rng(seed)
    bs = np.empty(n_boot)
    for i in range(n_boot):
        s = rng.integers(0, len(x), len(x))
        bs[i] = stats.spearmanr(x[s], y[s])[0]
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    return float(r), float(p), float(lo), float(hi), int(len(x))


def kruskal(groups):
    H, p = stats.kruskal(*groups)
    n, k = sum(len(g) for g in groups), len(groups)
    return float(H), float(p), float(max((H - k + 1) / (n - k), 0.0))


def holm(p):
    p = np.asarray(p, float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (len(p) - rank) * p[i])
        adj[i] = min(run, 1.0)
    return adj


def median_ci(x, n_boot=1000, seed=7):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    rng = np.random.default_rng(seed)
    bs = np.array([np.median(x[rng.integers(0, len(x), len(x))]) for _ in range(n_boot)])
    return float(np.median(x)), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def loglog_fit(x, y, n_boot=1000, seed=7):
    lx, ly = np.log(np.asarray(x, float)), np.log(np.asarray(y, float))
    sl = stats.linregress(lx, ly)
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(n_boot):
        s = rng.integers(0, len(lx), len(lx))
        bs.append(np.polyfit(lx[s], ly[s], 1)[0])
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return dict(slope=float(sl.slope), intercept=float(sl.intercept), r2=float(sl.rvalue ** 2), lo=float(lo), hi=float(hi), n=int(len(lx)))


# ───────────────────────── 자료 준비 ─────────────────────────
def prepare(res, integrated=None, update_table=None):
    rows = res["rows"].copy()
    rows["start_date"] = pd.to_datetime(rows["start_date"])
    rr = rows[rows["in_resident_scope"] == 1].copy()
    cf = res["cf"].copy()
    cx = cf
    if integrated is not None:
        want = ["complex_id", "지사명", "longitude", "latitude"] + [c for c, _ in CTX]
        cx = cf.merge(integrated[[c for c in want if c in integrated.columns]], on="complex_id", how="left")
    main = cx[cx["low_data_flag"] == 0].copy()
    return dict(rows=rows, rr=rr, cf=cf, cx=cx, main=main, dic=res["dic"], co=res["co"], tinfo=res["tinfo"], update=update_table, n_cx=int(cf["complex_id"].nunique()))


# ───────────────────────── 5.1 공급 지형 ─────────────────────────
def type_landscape(P):
    rr, n_cx = P["rr"], P["n_cx"]
    rr = rr[rr["std_id"] != "Z99"]
    g = (rr.groupby(["std_id", "std_name", "std_family_label"]).agg(n_records=("source_row", "size"), n_complexes=("complex_name", "nunique")).reset_index())
    per = rr.groupby(["std_id", "complex_name"]).size().groupby("std_id")
    g["records_per_adopter_median"] = g["std_id"].map(per.median())
    g["records_per_adopter_mean"] = g["std_id"].map(per.mean())
    g["adoption_rate"] = g["n_complexes"] / n_cx
    g = g.sort_values("n_records", ascending=False).reset_index(drop=True)
    g["rank"] = np.arange(1, len(g) + 1)
    g["share"] = g["n_records"] / g["n_records"].sum()
    g["cum_share"] = g["share"].cumsum()
    S = dict(n_types=int(len(g)), n_cx=int(n_cx), total=int(g["n_records"].sum()),
             k50=int((g["cum_share"] < 0.5).sum() + 1), k80=int((g["cum_share"] < 0.8).sum() + 1), k90=int((g["cum_share"] < 0.9).sum() + 1),
             top1_name=str(g.loc[0, "std_name"]), top1_share=float(g.loc[0, "share"]), top5_share=float(g["share"].head(5).sum()), top10_share=float(g["share"].head(10).sum()),
             n_universal=int((g["adoption_rate"] >= 0.5).sum()), n_niche=int((g["adoption_rate"] < 0.1).sum()), n_rare=int((g["n_records"] < 50).sum()),
             niche_records_share=float(g.loc[g["adoption_rate"] < 0.1, "n_records"].sum() / g["n_records"].sum()))
    return g, S


# ───────────────────────── 5.2 시간 흐름 ─────────────────────────
def time_profile(P):
    rows, rr, upd = P["rows"], P["rr"], P["update"]
    idx = pd.period_range("2024-01", "2026-06", freq="M")
    per = lambda df: df.groupby(df["start_date"].dt.to_period("M")).size().reindex(idx, fill_value=0)
    mon = pd.DataFrame({"month": idx.astype(str), "n_rows": per(rows).values, "n_resident": per(rr).values})
    if upd is not None and len(upd):
        a = upd[(upd["change_type"] == "added") & (upd["in_analysis"] == 1)].copy()
        a["m"] = pd.to_datetime(a["시작일자"]).dt.to_period("M")
        mon["n_added_in_update"] = a.groupby("m").size().reindex(idx, fill_value=0).values
    else:
        mon["n_added_in_update"] = 0
    mon["added_share"] = np.where(mon["n_rows"] > 0, mon["n_added_in_update"] / mon["n_rows"], 0.0)
    mon["year"] = idx.year
    mon["mth"] = idx.month
    # 달력월 계절 지수(2024·2025 두 해를 평균): 해당 월 건수 ÷ 그 해 월평균
    full = mon[mon["year"].isin([2024, 2025])].copy()
    full["idx"] = full["n_resident"] / full.groupby("year")["n_resident"].transform("mean")
    season = full.groupby("mth")["idx"].mean().rename("season_index").reset_index()
    # 상반기(1~6월) 구성 변화
    fam = rr[rr["std_family"] != "F99"].copy()
    fam["y"], fam["mth"] = fam["start_date"].dt.year, fam["start_date"].dt.month
    h1 = fam[fam["mth"] <= 6]
    cnt = h1.groupby(["std_family_label", "y"]).size().unstack(fill_value=0)
    shr = cnt / cnt.sum()
    fam_h1 = pd.DataFrame({"family": shr.index, "share_2024h1": shr[2024].values, "share_2025h1": shr[2025].values, "share_2026h1": shr[2026].values,
                           "n_2024h1": cnt[2024].values, "n_2025h1": cnt[2025].values, "n_2026h1": cnt[2026].values})
    fam_h1["diff_pp_25_26"] = (fam_h1["share_2026h1"] - fam_h1["share_2025h1"]) * 100
    fam_h1["diff_pp_24_25"] = (fam_h1["share_2025h1"] - fam_h1["share_2024h1"]) * 100
    fam_h1 = fam_h1.sort_values("diff_pp_25_26").reset_index(drop=True)
    h1n = {y: int(mon[(mon["year"] == y) & (mon["mth"] <= 6)]["n_resident"].sum()) for y in (2024, 2025, 2026)}
    last6 = mon.tail(6)
    pk = season.sort_values("season_index", ascending=False)
    S = dict(h1=h1n, ratio_25_24=h1n[2025] / h1n[2024], ratio_26_25=h1n[2026] / h1n[2025],
             peak_months=[int(m) for m in pk["mth"].head(2)], trough_months=[int(m) for m in pk["mth"].tail(2)], peak_index=float(pk["season_index"].iloc[0]),
             trough_index=float(pk["season_index"].iloc[-1]), added_total=int(mon["n_added_in_update"].sum()), added_last6=int(last6["n_added_in_update"].sum()),
             added_share_last6=float(last6["n_added_in_update"].sum() / max(last6["n_rows"].sum(), 1)),
             added_share_before=float(mon.head(24)["n_added_in_update"].sum() / max(mon.head(24)["n_rows"].sum(), 1)),
             worst_month=str(last6.loc[last6["added_share"].idxmax(), "month"]), worst_added_share=float(last6["added_share"].max()),
             rise=fam_h1.tail(3)[["family", "diff_pp_25_26"]].values.tolist()[::-1], fall=fam_h1.head(3)[["family", "diff_pp_25_26"]].values.tolist())
    return dict(monthly=mon, season=season, fam_h1=fam_h1), S


# ───────────────────────── 5.3 단지 간 격차·규모 ─────────────────────────
def disparity(P, seed=7):
    cx, main = P["cx"], P["main"]
    vol = cx["n_records_resident"].astype(float).values
    inten = cx["resident_records_per_1000hh_year"].fillna(0).astype(float).values
    ineq = pd.DataFrame([
        dict(metric="단지별 주민 대상 기록 수", gini=gini(vol), top10_share=float(np.sort(vol)[::-1][:max(int(len(vol) * 0.1), 1)].sum() / vol.sum()),
             bottom50_share=float(np.sort(vol)[:len(vol) // 2].sum() / vol.sum())),
        dict(metric="세대 1000당 연 기록 수(활동량)", gini=gini(inten), top10_share=float(np.sort(inten)[::-1][:max(int(len(inten) * 0.1), 1)].sum() / inten.sum()),
             bottom50_share=float(np.sort(inten)[:len(inten) // 2].sum() / inten.sum()))])
    # 규모 효과(로그-로그)
    rec = cx[(cx["n_records_resident"] > 0) & (cx["households"] > 0)]
    par = cx[(cx["participants_total_sum"].fillna(0) > 0) & (cx["households"] > 0)]
    sc = pd.DataFrame([dict(outcome="기록 수", **loglog_fit(rec["households"], rec["n_records_resident"], seed=seed)),
                       dict(outcome="참여인원 합", **loglog_fit(par["households"], par["participants_total_sum"], seed=seed))])
    # 집단 비교
    tests, summ = [], []
    factors = [("supply_group", "공급군"), ("size_tertile", "규모 3분위(S·M·L)")] + ([("지사명", "지사")] if "지사명" in main.columns else [])
    for col, lab in factors:
        d = main[[col, "resident_records_per_1000hh_year"]].dropna()
        order = list(d.groupby(col)["resident_records_per_1000hh_year"].median().sort_values().index)
        groups = [d.loc[d[col] == k, "resident_records_per_1000hh_year"].values for k in order]
        H, p, e2 = kruskal(groups)
        tests.append(dict(factor=lab, n_groups=len(order), n=int(len(d)), H=H, p=p, epsilon2=e2))
        for k, g in zip(order, groups):
            med, lo, hi = median_ci(g, seed=seed)
            summ.append(dict(factor=lab, group=k, n=int(len(g)), median=med, ci_lo=lo, ci_hi=hi, q1=float(np.percentile(g, 25)), q3=float(np.percentile(g, 75))))
    tests, summ = pd.DataFrame(tests), pd.DataFrame(summ)
    S = dict(gini_vol=float(ineq.loc[0, "gini"]), gini_int=float(ineq.loc[1, "gini"]), top10_vol=float(ineq.loc[0, "top10_share"]), bottom50_vol=float(ineq.loc[0, "bottom50_share"]),
             top10_int=float(ineq.loc[1, "top10_share"]), slope_rec=float(sc.loc[0, "slope"]), slope_rec_lo=float(sc.loc[0, "lo"]), slope_rec_hi=float(sc.loc[0, "hi"]), r2_rec=float(sc.loc[0, "r2"]),
             slope_par=float(sc.loc[1, "slope"]), slope_par_lo=float(sc.loc[1, "lo"]), slope_par_hi=float(sc.loc[1, "hi"]), r2_par=float(sc.loc[1, "r2"]),
             tests=tests.set_index("factor")[["H", "p", "epsilon2", "n_groups", "n"]].to_dict("index"),
             median_int=float(main["resident_records_per_1000hh_year"].median()), q1_int=float(main["resident_records_per_1000hh_year"].quantile(.25)),
             q3_int=float(main["resident_records_per_1000hh_year"].quantile(.75)), n_main=int(len(main)))
    if "지사" in tests["factor"].values:
        b = summ[summ["factor"] == "지사"].sort_values("median")
        S["branch_lo"] = (str(b.iloc[0]["group"]), float(b.iloc[0]["median"]))
        S["branch_hi"] = (str(b.iloc[-1]["group"]), float(b.iloc[-1]["median"]))
        S["branch_n"] = int(len(b))
    return dict(inequality=ineq, scaling=sc, group_tests=tests, group_summary=summ), S


# ───────────────────────── 5.4 단지 구성 유형 ─────────────────────────
def type_structure(P):
    cf, main = P["cf"], P["main"]
    mask = (cf["n_records_resident"] >= 15)
    X = TY._matrix(cf, mask)
    cols = list(X.columns)
    Z = StandardScaler().fit_transform(X.values)
    zdf = pd.DataFrame(Z, columns=cols, index=X.index)
    types = cf.loc[mask, "complex_type_id"].values
    prof = zdf.groupby(types).mean()
    prof.columns = [TY.LABEL.get(c, c) for c in prof.columns]
    pca = PCA(n_components=min(10, Z.shape[1]), random_state=7).fit(Z)
    scree = pd.DataFrame({"component": [f"PC{i + 1}" for i in range(len(pca.explained_variance_ratio_))], "explained": pca.explained_variance_ratio_,
                          "cumulative": np.cumsum(pca.explained_variance_ratio_)})
    # 가족 구성 군집(계층 군집; Ward)
    fcols = [c for c in cf.columns if c.startswith("share_family_F") and c != "share_family_F99"]
    F = cf.loc[mask, fcols].fillna(0)
    Fz = StandardScaler().fit_transform(F.values)
    row_order = leaves_list(linkage(Fz, method="ward"))
    col_order = leaves_list(linkage(Fz.T, method="ward"))
    fam_label = {f"share_family_{k}": v for k, v in TX.FAMILIES.items()}
    size = cf.loc[mask].groupby("complex_type_id").size()
    ordered = np.asarray(types)[row_order]
    adj_same = float((ordered[:-1] == ordered[1:]).mean())
    chance = float(((size / size.sum()) ** 2).sum())
    S = dict(adj_same=adj_same, adj_chance=chance, k=int(len(size)), sizes=size.to_dict(), var_pc1=float(scree.loc[0, "explained"]), var_pc2=float(scree.loc[1, "explained"]),
             var_pc3=float(scree.loc[2, "explained"]), cum3=float(scree.loc[2, "cumulative"]), n_feat=int(len(cols)),
             top=prof.apply(lambda r: [(c, float(r[c])) for c in r.sort_values(ascending=False).index[:2]], axis=1).to_dict())
    A = dict(prof=prof, scree=scree, F=F, fcols=fcols, row_order=row_order, col_order=col_order, fam_label=fam_label, types=types, Z=Z, cols=cols)
    return dict(profile_z=prof.reset_index().rename(columns={"index": "type"}), scree=scree), S, A


# ───────────────────────── 5.5 참여·비용 ─────────────────────────
def participation_cost(P):
    rr = P["rr"]
    d = rr[rr["std_family"] != "F99"].copy()
    pos = d[d["participants_total"] > 0]
    g = pos.groupby("std_family_label")["participants_total"].agg(n="size", median="median", q1=lambda s: s.quantile(.25), q3=lambda s: s.quantile(.75), p90=lambda s: s.quantile(.9), p10=lambda s: s.quantile(.1))
    g["zero_share"] = d.groupby("std_family_label")["participants_zero_flag"].mean()
    g = g.sort_values("median").reset_index()
    # 건수 비중 vs 추정 비용 비중
    c = d.groupby("std_family_label").agg(n_records=("source_row", "size"), cost=("est_cost_mid_krw", "sum"), burden=("est_burden_mid_krw", "sum"))
    c["records_share"] = c["n_records"] / c["n_records"].sum()
    c["cost_share"] = c["cost"] / c["cost"].sum()
    c["burden_share"] = c["burden"] / c["burden"].sum()
    c["ratio"] = c["cost_share"] / c["records_share"]
    c = c.sort_values("cost_share", ascending=False).reset_index()
    big = d[d["participants_total"] >= d["participants_total"].quantile(0.99)]
    S = dict(median_all=float(pos["participants_total"].median()), p90_all=float(pos["participants_total"].quantile(.9)), p99_all=float(pos["participants_total"].quantile(.99)),
             top_family=str(g.iloc[-1]["std_family_label"]), top_median=float(g.iloc[-1]["median"]), low_family=str(g.iloc[0]["std_family_label"]), low_median=float(g.iloc[0]["median"]),
             cost_top=str(c.iloc[0]["std_family_label"]), cost_top_share=float(c.iloc[0]["cost_share"]), cost_top_rec_share=float(c.iloc[0]["records_share"]),
             top3_cost_share=float(c["cost_share"].head(3).sum()), top3_cost_names=list(c["std_family_label"].head(3)),
             share_p99_participants=float(big["participants_total"].sum() / pos["participants_total"].sum()), n_p99=int(len(big)))
    return dict(participation_family=g, cost_share=c), S


# ───────────────────────── 5.6 협력·운영 ─────────────────────────
def cooperation_ops(P):
    rr = P["rr"]
    d = rr[rr["std_family"] != "F99"].copy()
    fams = list(d.groupby("std_family_label").size().sort_values(ascending=False).index)
    # 협력기관 유형 × 가족: 해당 유형이 원문에 언급된 기록의 비중
    org = {}
    for code in TX.ORGS:
        org[code] = d["partner_org_codes"].astype(str).str.split("|").map(lambda lst, c=code: c in lst)
    om = pd.DataFrame({TX.ORGS[c]: s.groupby(d["std_family_label"]).mean() for c, s in org.items()})
    tot = pd.Series({TX.ORGS[c]: s.mean() for c, s in org.items()})
    keep = list(tot[tot >= 0.01].sort_values(ascending=False).index)
    om = om.loc[fams, keep]
    # 운영 특성 × 가족: Y·P 비중
    cols = {"op_always": "상시형", "op_regular": "정기형", "op_event": "행사형", "op_adhoc": "수시형", "op_seasonal": "계절형"}
    ops = pd.DataFrame({lab: d[c].isin(["Y", "P"]).groupby(d["std_family_label"]).mean() for c, lab in cols.items()}).loc[fams]
    S = dict(org_top=[(k, float(v)) for k, v in tot.sort_values(ascending=False).head(4).items()],
             org_any=float((d["partner_org_codes"].astype(str) != "").mean()),
             evt_top=str(ops["행사형"].idxmax()), evt_top_v=float(ops["행사형"].max()), reg_top=str(ops["정기형"].idxmax()), reg_top_v=float(ops["정기형"].max()),
             alw_top=str(ops["상시형"].idxmax()), alw_top_v=float(ops["상시형"].max()), sea_top=str(ops["계절형"].idxmax()), sea_top_v=float(ops["계절형"].max()))
    # 가장 눈에 띄는 가족–기관 짝
    stack = om.stack()
    best = stack.sort_values(ascending=False).head(3)
    S["fam_org_best"] = [(a, b, float(v)) for (a, b), v in best.items()]
    return dict(org_by_family=om.reset_index().rename(columns={"std_family_label": "family"}), ops_by_family=ops.reset_index().rename(columns={"std_family_label": "family"})), S


# ───────────────────────── 5.7 프로그램 간 관계 ─────────────────────────
def relations(P, min_both=20, min_lift=1.6, max_edges=45):
    co, dic = P["co"], P["dic"]
    e = co[(co["n_both"] >= min_both) & (co["lift"] >= min_lift)].sort_values("lift", ascending=False).head(max_edges).copy()
    fam = dict(zip(dic["std_id"], dic["std_family"]))
    e["same_family"] = [int(fam.get(a) == fam.get(b)) for a, b in zip(e["std_a"], e["std_b"])]
    adopt = dict(zip(dic["std_id"], dic["adoption_rate"]))
    # 단지 지표 상관
    main = P["main"]
    cv = [(c, l) for c, l in CORR_VARS if c in main.columns]
    M = main[[c for c, _ in cv]].astype(float)
    R = M.corr(method="spearman")
    R.index = R.columns = [l for _, l in cv]
    pairs = []
    for i in range(len(R)):
        for j in range(i + 1, len(R)):
            pairs.append((R.index[i], R.columns[j], float(R.iloc[i, j])))
    pairs = sorted(pairs, key=lambda t: -abs(t[2]))
    S = dict(n_edges=int(len(e)), n_same=int(e["same_family"].sum()), top_edges=e.head(3)[["std_a_name", "std_b_name", "lift", "n_both"]].values.tolist(),
             top_pos=[p for p in pairs if p[2] > 0][:3], top_neg=[p for p in pairs if p[2] < 0][:3], n_vars=int(len(cv)))
    return dict(edges=e, corr=R.reset_index().rename(columns={"index": "var"})), S, dict(adopt=adopt, fam=fam, R=R)


# ───────────────────────── 5.8 단지 여건(통합표)과의 관계 ─────────────────────────
def context(P, seed=7):
    cx = P["cx"]
    if "인구_60세이상_비율" not in cx.columns:
        return None
    main = cx[cx["low_data_flag"] == 0].copy()
    rows = []
    for ocol, olab in OUTCOMES:
        for ccol, clab in CTX:
            if ccol not in main.columns:
                continue
            r, p, lo, hi, n = spearman_boot(main[ocol], main[ccol], seed=seed)
            rows.append(dict(outcome=olab, outcome_col=ocol, context=clab, context_col=ccol, rho=r, p=p, ci_lo=lo, ci_hi=hi, n=n))
    cor = pd.DataFrame(rows)
    cor["p_holm"] = holm(cor["p"].values)
    # 다중 회귀(OLS, 표준화 설명변수; 신뢰구간은 부트스트랩)
    preds = [("log_hh", "세대수(로그)"), ("입주기준경과년수", "입주 후 경과 연수"), ("인구_60세이상_비율", "60세 이상 인구 비율"), ("평형_전용면적가중평균_㎡", "평균 전용면적"),
             ("홈닥터_2025_100세대당월평균지원건수", "홈닥터 지원(2025)"), ("접근성_경로당_대표점_km", "경로당까지 거리")]
    d = main.copy()
    d["log_hh"] = np.log(d["households"])
    d["y"] = np.log(d["resident_records_per_1000hh_year"])
    d = d.dropna(subset=["y"] + [c for c, _ in preds if c in d.columns])
    d = d[np.isfinite(d["y"])]
    Xm = d[[c for c, _ in preds]].astype(float).values
    Xz = (Xm - Xm.mean(0)) / Xm.std(0)
    A = np.column_stack([np.ones(len(Xz)), Xz])
    y = d["y"].values
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    pred = A @ beta
    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    rng = np.random.default_rng(seed)
    bs = np.empty((1000, A.shape[1]))
    for i in range(1000):
        s = rng.integers(0, len(y), len(y))
        bs[i] = np.linalg.lstsq(A[s], y[s], rcond=None)[0]
    lo, hi = np.percentile(bs, [2.5, 97.5], axis=0)
    reg = pd.DataFrame({"term": ["절편"] + [l for _, l in preds], "coef": beta, "ci_lo": lo, "ci_hi": hi})
    reg["pct_change_per_sd"] = (np.exp(reg["coef"]) - 1) * 100
    reg.loc[0, "pct_change_per_sd"] = np.nan
    # 해석용 요약
    sig = cor[(cor["p_holm"] < 0.05)]
    S = dict(n=int(len(d)), r2=float(r2), n_tests=int(len(cor)), n_sig=int(len(sig)),
             strong=cor.reindex(cor["rho"].abs().sort_values(ascending=False).index).head(4)[["outcome", "context", "rho", "ci_lo", "ci_hi"]].values.tolist(),
             reg_top=reg.iloc[1:].reindex(reg.iloc[1:]["coef"].abs().sort_values(ascending=False).index).head(3)[["term", "coef", "ci_lo", "ci_hi", "pct_change_per_sd"]].values.tolist(),
             age60_vs_int=cor[(cor["outcome_col"] == "resident_records_per_1000hh_year") & (cor["context_col"] == "인구_60세이상_비율")][["rho", "ci_lo", "ci_hi", "p"]].values.tolist()[0])
    return dict(context_corr=cor, regression=reg), S, dict(d=d, preds=preds)


# ───────────────────────── 전체 실행 ─────────────────────────
def run(res, integrated=None, update_table=None, seed=7):
    """모든 심화 분석을 계산한다. 반환: dict(P=자료, T=표, S=요약, A=그림용 배열)."""
    P = prepare(res, integrated, update_table)
    T, S, A = {}, {}, {}
    T["type_landscape"], S["landscape"] = type_landscape(P)
    t, S["time"] = time_profile(P)
    T.update({f"time_{k}": v for k, v in t.items()})
    t, S["disp"] = disparity(P, seed)
    T.update({f"disp_{k}": v for k, v in t.items()})
    t, S["types"], A["types"] = type_structure(P)
    T.update({f"types_{k}": v for k, v in t.items()})
    t, S["part"] = participation_cost(P)
    T.update({f"part_{k}": v for k, v in t.items()})
    t, S["coop"] = cooperation_ops(P)
    T.update({f"coop_{k}": v for k, v in t.items()})
    t, S["rel"], A["rel"] = relations(P)
    T.update({f"rel_{k}": v for k, v in t.items()})
    out = context(P, seed)
    if out is not None:
        t, S["ctx"], A["ctx"] = out
        T.update({f"ctx_{k}": v for k, v in t.items()})
    return dict(P=P, T=T, S=S, A=A)
