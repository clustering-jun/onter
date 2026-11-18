"""모듈 1. 단지 현황 지표와 프로파일.

산출: 필요 지수(분야별 백분위와 불확실 구간), 공급 지수, 어긋남, 목표 분포, 대상 구성, 단지 유형, 운영 이력.

설계 원칙
- 필요 지수는 '구조 지표'(인구·주거·접근성)만으로 만든다(S). 이용 실적(홈닥터)은 공급이 있어야 생기므로
  기본값에서 빼고, 수렴 타당도 점검과 화면 표시(SE)에만 쓴다.
- 지표→분야 대응과 가중치는 지식 기반 가정이다. 그래서 가중치 흔들기·지표 하나 빼기로 순위 구간을 같이 낸다.
- 활동 기록(채택)은 필요 지수에 쓰지 않는다. 기록은 관성·규모·지사를 따르기 때문이다.
"""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, adjusted_rand_score
from . import config as C, data as D, features as F

# (열, 방향, 가중치, 설명). S=구조 지표, E=이용으로 드러난 필요(표시·점검용)
INDICATORS = {
    "N1": {"S": [("age80", +1, 1.0, "80세 이상 비율"), ("pph", -1, 1.0, "세대당 인구(적을수록 1인 가구)"),
                 ("small_unit", +1, 0.5, "전용 40㎡ 미만 세대 비율"), ("perm", +1, 0.5, "영구임대 포함")],
           "E": [("hd_life", +1, 1.0, "홈닥터 생활지원(100세대당 월)")]},
    "N2": {"S": [("perm", +1, 1.0, "영구임대 포함"), ("small_unit", +1, 1.0, "전용 40㎡ 미만 세대 비율"),
                 ("area_avg", -1, 0.5, "평균 전용면적(작을수록)")],
           "E": [("hd_econ", +1, 1.0, "홈닥터 경제지원(100세대당 월)")]},
    "N3": {"S": [("age70", +1, 1.0, "70세 이상 비율"), ("age80", +1, 1.0, "80세 이상 비율"),
                 ("acc_medical", +1, 1.0, "의원·병원·약국·보건기관까지 거리")],
           "E": [("hd_medical", +1, 1.0, "홈닥터 의료지원(100세대당 월)"), ("hd_chores", +1, 0.5, "홈닥터 가사지원(100세대당 월)")]},
    "N4": {"S": [("years", +1, 1.0, "입주 후 경과 연수"), ("cctv100", -1, 0.5, "CCTV(100세대당, 적을수록)"),
                 ("d_응급의료시설", +1, 0.5, "응급의료시설까지 거리"), ("age80", +1, 0.5, "80세 이상 비율(안전 취약)")],
           "E": [("hd_chores", +1, 1.0, "홈닥터 가사지원(100세대당 월)")]},
    "N5": {"S": [("acc_leisure", +1, 1.0, "노인여가복지시설·종합사회복지관까지 거리"), ("n_space", -1, 1.0, "단지 안 공용 공간 종류(적을수록)"),
                 ("age60", +1, 0.5, "60세 이상 비율(낮 시간 활동 수요)")],
           "E": []},
    "N6": {"S": [("age_work", +1, 1.0, "20~59세 비율"), ("age_u20", +1, 1.0, "20세 미만 비율")],
           "E": []},
}


def _base():
    c = F.complex_frame().copy()
    pr = lambda cols: pd.concat([F.pct_rank(c[x]) for x in cols], axis=1).mean(axis=1)
    c["acc_medical"] = pr(["d_의원", "d_병원", "d_약국", "d_보건기관"])
    c["acc_leisure"] = pr(["d_노인여가복지시설", "d_종합사회복지관"])
    return c


def need_raw(variant="S", weights=None, drop=None):
    """분야별 필요 점수(0~1, 지표 백분위의 가중 평균). weights: {(분야, 열): 가중치}로 덮어쓸 수 있다."""
    c = _base()
    out = pd.DataFrame(index=c.index, columns=C.NEED_IDS, dtype=float)
    for d in C.NEED_IDS:
        items = [x for v in variant for x in INDICATORS[d][v]]
        num, den = 0.0, 0.0
        for col, sign, w, _ in items:
            if drop == (d, col):
                continue
            w = (weights or {}).get((d, col), w)
            r = F.pct_rank(sign * c[col].astype(float))
            num = num + (r.fillna(0.5) * w)
            den += w
        out[d] = num / den
    return out


def need_table(variant="S", **kw):
    """분야별 필요 백분위(단지 간 순위, 0~1)."""
    return need_raw(variant, **kw).apply(F.pct_rank)


def need_uncertainty(variant="S", n_draw=300, seed=C.SEED):
    """가중치를 흔들고(로그정규 σ=0.5) 지표를 하나씩 빼서 필요 백분위의 5~95% 구간을 낸다."""
    rng = np.random.default_rng(seed)
    keys = [(d, col) for d in C.NEED_IDS for v in variant for col, _, _, _ in INDICATORS[d][v]]
    base_w = {(d, col): w for d in C.NEED_IDS for v in variant for col, _, w, _ in INDICATORS[d][v]}
    draws = [need_table(variant, weights={k: base_w[k] * rng.lognormal(0, 0.5) for k in keys}).to_numpy() for _ in range(n_draw)]
    draws += [need_table(variant, drop=k).to_numpy() for k in keys if sum(1 for kk in keys if kk[0] == k[0]) > 1]
    A = np.stack(draws)
    idx, cols = D.complexes().index, C.NEED_IDS
    return (pd.DataFrame(np.quantile(A, 0.05, axis=0), index=idx, columns=cols),
            pd.DataFrame(np.quantile(A, 0.95, axis=0), index=idx, columns=cols))


def supply_table(start=C.FIRST_MONTH, end=C.LAST_MONTH):
    """분야별 공급: 1,000세대당 연 기록 수(rate), 단지 간 백분위(pct), 단지 안 비중(share). 기록 없는 단지는 결측."""
    X = F.interactions(start, end, "count")
    M = F.need_membership(start, end)
    dom = pd.DataFrame(X.to_numpy() @ M.to_numpy(), index=X.index, columns=C.NEED_IDS)
    months = (pd.Period(end, "M") - pd.Period(start, "M")).n + 1
    hh = D.complexes()["hh"]
    act = F.active_complexes(start, end)
    rate = dom.div(hh, axis=0) * 1000 * 12 / months
    rate.loc[~rate.index.isin(act)] = np.nan
    share = dom.div(dom.sum(axis=1).replace(0, np.nan), axis=0)
    return rate, rate.apply(F.pct_rank), share


def gap_table(start=C.FIRST_MONTH, end=C.LAST_MONTH, variant="S", hi=2 / 3, lo=1 / 3):
    """어긋남 = 필요 백분위 − 공급 백분위. priority: 필요 상위 1/3이면서 공급 하위 1/3."""
    need = need_table(variant)
    _, sp, _ = supply_table(start, end)
    gap = need - sp
    pri = ((need >= hi) & (sp <= lo)).astype(float)
    pri.loc[sp.isna().all(axis=1)] = np.nan
    return gap, pri


# ───────── 주민이 말한 수요(해피콜) → 분야별 기준 분포 ─────────
AGE_GROUPS = {"40대 이하": ["20대", "30대", "40대"], "50대": ["50대"], "60대": ["60대"], "70대": ["70대", "80대", "90대", "100대"]}


def _demand_pop(population, mapping, shrink=30):
    """한 조사 집단의 (전체 분포, 연령대별 분포). 공단 관리 단지 응답을 기준으로 삼고 소표본은 전체 쪽으로 당긴다."""
    h = D.happycall_demand()
    h = h[(h["population"] == population) & h["metric"].isin(mapping)]
    base = h[(h["group"] == "관리소 소속") & (h["subgroup"] == "주택관리공단")].set_index("metric")["value"]
    if base.empty:
        base = h[h["scope"] == "overall"].set_index("metric")["value"]
    base = base.reindex(list(mapping)).fillna(0)
    age = {}
    for a in AGE_GROUPS:
        g = h[(h["group"] == "연령") & (h["subgroup"] == a)].set_index("metric")
        n = float(g["n"].max()) if len(g) else 0.0
        v = g["value"].reindex(list(mapping)).fillna(base) if len(g) else base
        age[a] = (n * v + shrink * base) / (n + shrink)
    to_dom = lambda s: s.groupby(mapping).sum().reindex(C.NEED_IDS).fillna(0)
    return to_dom(base), {a: to_dom(v) for a, v in age.items()}


def demand_base(by="complex"):
    """해피콜 수요 응답을 필요 분야 분포로 바꾼 '주민 목소리' 기준 분포.

    national: 두 조사 집단(주거생활지원 168명, 사회적 고립 243명)의 분야 분포 평균.
    complex : 단지의 성인 연령 구성으로 연령대별 응답을 가중한 합성 추정(단지별 응답이 아니다).
    """
    pops = [("residential_life_support_service_users", C.DEMAND_NEED), ("social_isolation_service_users", C.ISOLATION_NEED)]
    parts = [_demand_pop(p, m) for p, m in pops]
    norm = lambda s: s / s.sum()
    nat = sum(norm(b) for b, _ in parts) / len(parts)
    if by == "national":
        return nat
    c = D.complexes()
    w = pd.DataFrame({a: c[[f"n_{b}" for b in bands]].sum(axis=1) for a, bands in AGE_GROUPS.items()})
    w = w.div(w.sum(axis=1), axis=0).fillna(1 / len(AGE_GROUPS))
    out = 0
    for _, age in parts:
        A = pd.DataFrame({a: norm(v) for a, v in age.items()})          # 분야×연령대
        out = out + w.to_numpy() @ A[w.columns].to_numpy().T
    out = pd.DataFrame(out / len(parts), index=c.index, columns=C.NEED_IDS)
    return out.div(out.sum(axis=1), axis=0)


def supply_base(start=C.FIRST_MONTH, end=C.LAST_MONTH):
    """현재 공급의 전국 분야 분포(현상 유지 기준)."""
    X = F.interactions(start, end, "count")
    s = pd.Series(X.sum(axis=0).to_numpy() @ F.need_membership(start, end).to_numpy(), index=C.NEED_IDS)
    return s / s.sum()


def target_distribution(base="demand", beta=2.0, variant="S", start=C.FIRST_MONTH, end=C.LAST_MONTH):
    """단지별 목표 분야 분포 Q. q(d) ∝ base(d)·exp(β·(필요 백분위 − 단지 평균)).

    base: demand(해피콜 합성) / demand_national / supply(현 공급) / uniform. β=0이면 모든 단지가 base를 그대로 따른다.
    """
    need = need_table(variant)
    if base == "demand":
        b = demand_base("complex")
    elif base == "demand_national":
        b = pd.DataFrame([demand_base("national")] * len(need), index=need.index)
    elif base == "supply":
        b = pd.DataFrame([supply_base(start, end)] * len(need), index=need.index)
    else:
        b = pd.DataFrame(1 / len(C.NEED_IDS), index=need.index, columns=C.NEED_IDS)
    tilt = np.exp(beta * need.sub(need.mean(axis=1), axis=0))
    q = b[C.NEED_IDS] * tilt
    return q.div(q.sum(axis=1), axis=0)


def target_affinity():
    """단지×대상 구성(0~1 백분위). 프로그램의 통상 대상과 단지 주민 구성이 맞는 정도를 재는 데 쓴다."""
    c = _base()
    r = F.pct_rank
    a = pd.DataFrame(index=c.index)
    a["ELD"], a["ELD1"] = r(c["age60"]), (r(c["age80"]) + r(-c["pph"])) / 2
    a["VUL"] = (r(c["perm"]) + r(c["small_unit"])) / 2
    a["DIS"] = r(c["perm"])                                   # 단지별 장애 가구 자료가 없어 영구임대 여부로 대신한다
    a["CHD"], a["JOB"], a["WOM"] = r(c["age_u20"]), r(c["age_work"]), r(c["female"])
    a["MID"] = (r(c["age_work"]) + r(-c["pph"])) / 2
    a["CRI"] = need_table("S")["N1"]
    a["ALL"] = 0.5
    return a[F.TARGETS]


# ───────── 단지 유형(구조 특징 군집) ─────────
def typology(k=None, ks=range(3, 9), n_boot=30, seed=C.SEED):
    """구조 특징으로 단지를 묶는다. k를 주지 않으면 실루엣과 부트스트랩 안정도(ARI)를 함께 보고 고른다."""
    X = F.matrix(F.STRUCT)
    rows, rng = [], np.random.default_rng(seed)
    for kk in ([k] if k else ks):
        km = KMeans(kk, n_init=20, random_state=seed).fit(X)
        aris = []
        for _ in range(n_boot):
            idx = rng.choice(len(X), len(X), replace=True)
            lb = KMeans(kk, n_init=5, random_state=int(rng.integers(1e9))).fit(X.iloc[idx]).predict(X)
            aris.append(adjusted_rand_score(km.labels_, lb))
        rows.append(dict(k=kk, silhouette=silhouette_score(X, km.labels_), stability_ari=float(np.mean(aris)), labels=km.labels_))
    t = pd.DataFrame(rows)
    best = t.iloc[(t["silhouette"].rank() + t["stability_ari"].rank()).argmax()]
    lab = pd.Series(best["labels"], index=X.index).map(lambda i: f"S{i + 1}")
    return lab, t.drop(columns="labels"), int(best["k"])


def describe_types(lab, top=4):
    """유형별로 평균에서 가장 벗어난 특징(z)과 규모."""
    X = F.matrix(F.STRUCT)
    rows = []
    for t, g in X.groupby(lab):
        z = g.mean().sort_values(key=np.abs, ascending=False).head(top)
        rows.append(dict(type=t, n=len(g), traits=" / ".join(f"{k}({v:+.1f})" for k, v in z.items())))
    return pd.DataFrame(rows)


# ───────── 운영 이력 ─────────
def history(start=C.FIRST_MONTH, end=C.LAST_MONTH):
    r = F.window(start, end)
    r = r[r["std_id"].isin(D.programs().index)]
    months = (pd.Period(end, "M") - pd.Period(start, "M")).n + 1
    g = r.groupby("complex_id")
    h = pd.DataFrame({"n_records": g.size(), "active_month_ratio": g["ym"].nunique() / months, "richness": g["std_id"].nunique(),
                      "last_month": g["ym"].max()})
    cnt = r.groupby(["complex_id", "std_id"]).size()
    h["repeat_share"] = cnt[cnt > 1].groupby("complex_id").sum().reindex(h.index).fillna(0) / h["n_records"]
    yr = r.assign(y=r["ym"].str[:4])
    sets = yr.groupby(["complex_id", "y"])["std_id"].agg(set).unstack()
    if {"2024", "2025"} <= set(sets.columns):
        jac = lambda a, b: len(a & b) / len(a | b) if isinstance(a, set) and isinstance(b, set) and (a | b) else np.nan
        h["jaccard_24_25"] = [jac(a, b) for a, b in zip(sets["2024"].reindex(h.index), sets["2025"].reindex(h.index))]
    names = D.programs()["name"]
    top = cnt.reset_index(name="n").sort_values(["complex_id", "n"], ascending=[True, False]).groupby("complex_id").head(5)
    h["top_programs"] = top.assign(nm=top["std_id"].map(names)).groupby("complex_id")["nm"].agg(" | ".join)
    part = r[["complex_id", "partner_org_codes"]].dropna()
    part = part.assign(og=part["partner_org_codes"].str.split("|")).explode("og")
    h["partner_types"] = part.groupby("complex_id")["og"].agg(lambda s: "|".join(sorted(set(s))))
    h["n_partner_types"] = part.groupby("complex_id")["og"].nunique().reindex(h.index).fillna(0)
    return h.reindex(D.complexes().index)


def profile(start=C.FIRST_MONTH, end=C.LAST_MONTH):
    """단지 프로파일 표(시스템 산출물). 필요·공급·어긋남·유형·이력을 한 행에."""
    c = D.complexes()
    need, need_se = need_table("S"), need_table("SE")
    lo, hi = need_uncertainty("S", n_draw=200)
    rate, sp, share = supply_table(start, end)
    gap, pri = gap_table(start, end)
    lab, _, _ = typology()
    out = c[["name", "branch", "region", "supply", "hh", "pop", "age60", "age80", "age_u20", "pph", "years", "small_unit", "deployed", "n_space"]].copy()
    out["type"] = lab
    for d in C.NEED_IDS:
        out[f"need_{d}"], out[f"need_lo_{d}"], out[f"need_hi_{d}"] = need[d], lo[d], hi[d]
        out[f"need_se_{d}"] = need_se[d]
        out[f"supply_rate_{d}"], out[f"supply_pct_{d}"], out[f"supply_share_{d}"] = rate[d], sp[d], share[d]
        out[f"gap_{d}"], out[f"priority_{d}"] = gap[d], pri[d]
    out["n_priority"] = pri.sum(axis=1)
    return out.join(history(start, end))
