"""모듈 4. 실행 검토.

(1) 프로그램 요건 프로파일: 기록에서 뽑은 자원·협력기관·장소·인력 부담·비용(추정)·시기.
(2) 단지 여건: 주거복지사 배치, 단지 안 공간, 협력 이력과 가까운 시설, 지금까지의 운영 규모.
(3) 실행 가능성 점수: 요건과 여건의 맞음(협력·공간·인력·예산). 규칙 기반이고 가중치를 학습하지 않는다.
(4) 제약을 넣은 연간 묶음 선택: 예산·인력 부담·개수·분야별 최소 개수를 사용자가 정하면 정수계획으로 고른다.

주의: 비용은 유형별 가정으로 만든 추정치이고 집행액이 아니다. 인력 부담은 상대 점수다. 둘 다 전문가 확인 대상이다.
"""
import re
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds
from . import config as C, data as D, features as F

PLACE_RULES = [("home", r"세대|가정|가구|자택|댁|방문"), ("senior", r"경로당|노인정|노인회|경노당"), ("welfare", r"복지관|복지센터|복지회관"),
               ("hall", r"관리동|관리사무소|관리소|회의실|집회|커뮤니티|주민공동|공동시설|상담실|센터|사무실|강당|교육실|다목적|북카페|도서관"),
               ("offsite", r"공원|극장|영화|체험장|박물관|수목원|체육관|시청|구청|군청|학교|대학|병원|보건소|외부|견학|여행|시장|마트")]
PLACES = ["home", "senior", "welfare", "hall", "offsite", "onsite"]
PLACE_KO = {"home": "세대 방문", "senior": "경로당", "welfare": "복지관", "hall": "관리동·회의실·커뮤니티실", "offsite": "단지 밖", "onsite": "단지 안 야외·공용부"}
OG_NEAR = {"OG02": [("d_보건기관", 2.0)], "OG03": [("d_종합사회복지관", 2.0)], "OG15": [("d_경로당", 0.5)], "OG12": [("d_의원", 1.0), ("d_병원", 2.0)],
           "OG09": [("d_초등학교", 1.0)]}
OG_IDS = [f"OG{i:02d}" for i in range(1, 17)]
RS_IDS = [f"RS{i:02d}" for i in range(1, 11)]


def place_type(s):
    if pd.isna(s) or not str(s).strip():
        return "onsite"
    for k, pat in PLACE_RULES:
        if re.search(pat, str(s)):
            return k
    return "onsite"                                        # 단지 이름·동 앞·광장 등은 단지 안으로 본다


def _share(r, col, codes, extra=None):
    x = r[col] if extra is None else r[col].fillna("") + "|" + r[extra].fillna("")
    x = pd.DataFrame({"rec": np.arange(len(r)), "std_id": r["std_id"].to_numpy(), "code": x.str.split("|").to_numpy()}).explode("code")
    x = x[x["code"].isin(codes)].drop_duplicates(["rec", "code"])          # 한 기록에서 같은 코드는 한 번만 센다
    t = pd.crosstab(x["std_id"], x["code"]).reindex(columns=codes, fill_value=0)
    n = r.groupby("std_id").size()
    return t.reindex(n.index, fill_value=0).div(n, axis=0)


def requirements(start=C.FIRST_MONTH, end=C.LAST_MONTH):
    """프로그램별 요건 프로파일(기간 내 기록 기준)."""
    p = D.programs()
    r = F.window(start, end)
    r = r[r["std_id"].isin(p.index)].reset_index(drop=True)
    years = ((pd.Period(end, "M") - pd.Period(start, "M")).n + 1) / 12
    g = r.groupby("std_id")
    q = pd.DataFrame(index=p.index)
    q["name"], q["n_records"], q["n_complexes"] = p["name"], g.size(), g["complex_id"].nunique()
    q[["n_records", "n_complexes"]] = q[["n_records", "n_complexes"]].fillna(0)
    q = q.join(_share(r, "resource_type_default", RS_IDS, "resource_explicit").add_prefix("res_"))
    q["partner_rate"] = g["partner_org_codes"].apply(lambda s: s.notna().mean())
    q = q.join(_share(r, "partner_org_codes", OG_IDS).add_prefix("og_"))
    mode = r["mode_explicit"].fillna(r["mode_type_default"]).fillna("")
    q["ext_delivery"] = mode.str.contains(r"M2|M6").groupby(r["std_id"]).mean()
    q["household_visit"] = g["support_unit_household"].mean()
    q["regular"] = r["op_primary"].isin(["REG", "ALW"]).groupby(r["std_id"]).mean()
    q["sessions_med"] = g["activity_count"].median().clip(1, 12)
    q["recs_per_complex_year"] = (q["n_records"] / q["n_complexes"].replace(0, np.nan) / years)
    pt = pd.crosstab(r["std_id"], r["place_masked"].map(place_type), normalize="index").reindex(columns=PLACES, fill_value=0)
    q = q.join(pt.add_prefix("place_"))
    q["cost_med"], q["cost_p90"] = g["est_cost_mid_krw"].median(), g["est_cost_mid_krw"].quantile(0.9)
    q["ext_burden"] = r["est_burden_class"].str.startswith("외부").groupby(r["std_id"]).mean()
    q["lh_fund"] = (r["cost_class_raw"] == "LH커뮤니티활동비").groupby(r["std_id"]).mean()
    q["participants_med"] = g["participants_total"].median()
    mon = pd.crosstab(r["std_id"], r["ym"].str[5:].astype(int), normalize="index")
    q["peak_months"] = mon.apply(lambda s: "|".join(str(m) for m in s.nlargest(3).index), axis=1)
    q["peak_share"] = mon.max(axis=1)
    # 연간 값: 단지가 이 프로그램을 한 해 운영할 때의 비용(추정)과 인력 부담(상대 점수)
    q["cost_year"] = q["cost_med"] * q["recs_per_complex_year"] * (1 - 0.7 * q["ext_burden"].fillna(0))
    load = q["recs_per_complex_year"] * q["sessions_med"] * (1 + q["household_visit"] + 0.5 * q["regular"]) * (1 - 0.5 * q["ext_delivery"])
    q["staff_load"] = load
    q["staff_tier"] = pd.qcut(load.rank(method="first"), 5, labels=False) + 1
    q["cost_tier"] = pd.cut(q["cost_year"], [-1, 1e5, 5e5, 2e6, 1e7, np.inf], labels=False) + 1
    num = q.select_dtypes("number").columns
    q[num] = q[num].fillna(q[num].median())
    return q


def capacity(start=C.FIRST_MONTH, end=C.LAST_MONTH):
    """단지 여건: 인력·공간·협력·운영 규모."""
    c = D.complexes()
    r = F.window(start, end)
    years = ((pd.Period(end, "M") - pd.Period(start, "M")).n + 1) / 12
    cap = c[["deployed", "sp_senior", "sp_gym", "sp_hall", "sp_daycare", "sp_library", "sp_welfare", "n_space", "mou25"]].copy()
    x = r[["complex_id", "partner_org_codes"]].dropna()
    x = x.assign(og=x["partner_org_codes"].str.split("|")).explode("og")
    hist = pd.crosstab(x["complex_id"], x["og"]).reindex(index=c.index, columns=OG_IDS, fill_value=0)
    for og in OG_IDS:
        near = np.zeros(len(c), bool)
        for col, km in OG_NEAR.get(og, []):
            near |= (c[col] <= km).fillna(False).to_numpy()
        if og == "OG03":
            near |= c["sp_welfare"].to_numpy() == 1
        if og == "OG15":
            near |= c["sp_senior"].to_numpy() == 1
        cap[f"a_{og}"] = np.where(hist[og].to_numpy() > 0, 1.0, np.where(near, 0.7, 0.3))      # 이력 있음 1 / 가까운 시설 0.7 / 둘 다 없음 0.3
        cap[f"h_{og}"] = hist[og].to_numpy()
    g = r.groupby("complex_id")
    cap["records_year"] = (g.size() / years).reindex(c.index)
    cap["cost_year_hist"] = (g["est_cost_mid_krw"].sum() / years).reindex(c.index)
    cap["cost_typical"] = g["est_cost_mid_krw"].quantile(0.75).reindex(c.index)
    cap["cost_typical"] = cap["cost_typical"].fillna(cap["cost_typical"].median())
    return cap


def feasibility(req, cap):
    """실행 가능성(0~1)과 네 성분. 행=단지, 열=프로그램."""
    ids, items = cap.index, req.index
    og = req[[f"og_{o}" for o in OG_IDS]].fillna(0).to_numpy()
    av = cap[[f"a_{o}" for o in OG_IDS]].to_numpy()
    avail = av @ og.T / np.maximum(og.sum(1)[None, :], 1e-9)
    avail = np.where(og.sum(1)[None, :] > 0, avail, 1.0)
    partner = 1 - req["partner_rate"].to_numpy()[None, :] * (1 - avail)
    pl = req[[f"place_{k}" for k in PLACES]].to_numpy()
    has = np.column_stack([np.ones(len(cap)), cap["sp_senior"], np.maximum(cap["sp_welfare"], 0.5 * (cap["a_OG03"] >= 0.7)),
                           np.maximum(cap["sp_hall"], 0.7), np.ones(len(cap)), np.ones(len(cap))]).astype(float)
    space = has @ pl.T
    dep = cap["deployed"].to_numpy()[:, None]
    staff = 1 - (1 - dep) * (0.5 * req["household_visit"].to_numpy()[None, :] + 0.1 * (req["staff_tier"].to_numpy()[None, :] - 1) / 4)
    cost1 = (req["cost_med"] * (1 - 0.7 * req["ext_burden"])).to_numpy()[None, :]
    budget = np.clip(cap["cost_typical"].to_numpy()[:, None] / np.maximum(cost1, 1.0), 0.3, 1.0)
    comp = {k: pd.DataFrame(v, index=ids, columns=items) for k, v in dict(partner=partner, space=space, staff=staff, budget=budget).items()}
    total = pd.DataFrame((partner * space * staff * budget) ** 0.25, index=ids, columns=items)
    return total, comp


def mh_odds_ratio(y, g, strata):
    """층화(Mantel-Haenszel) 오즈비와 95% 구간. y: 채택 여부, g: 집단(1/0), strata: 층."""
    num = den = 0.0
    P = Q = Rr = Ss = PR = PSQR = QS = 0.0
    for s in np.unique(strata):
        m = strata == s
        a, b = ((y == 1) & (g == 1) & m).sum(), ((y == 0) & (g == 1) & m).sum()
        c, d = ((y == 1) & (g == 0) & m).sum(), ((y == 0) & (g == 0) & m).sum()
        n = a + b + c + d
        if n == 0:
            continue
        R_, S_ = a * d / n, b * c / n
        num, den = num + R_, den + S_
        p_, q_ = (a + d) / n, (b + c) / n
        PR, PSQR, QS = PR + p_ * R_, PSQR + p_ * S_ + q_ * R_, QS + q_ * S_
    if num == 0 or den == 0:
        return np.nan, np.nan, np.nan
    orr = num / den
    se = np.sqrt(PR / (2 * num ** 2) + PSQR / (2 * num * den) + QS / (2 * den ** 2))
    return orr, orr * np.exp(-1.96 * se), orr * np.exp(1.96 * se)


def plan(scores, req, need_primary, budget=None, load=None, n_max=8, min_per_domain=None, allowed=None, method="milp"):
    """제약을 넣은 묶음 선택. scores: 한 단지의 프로그램 점수(Series). 비용·부담은 연간 값.

    method=milp: 정수계획(최적), greedy: 점수/자원 비율 순으로 담기(비교용).
    """
    items = [i for i in scores.index if allowed is None or i in allowed]
    s = scores.reindex(items).fillna(0).to_numpy()
    cost, ld = req["cost_year"].reindex(items).to_numpy(), req["staff_load"].reindex(items).to_numpy()
    dom = need_primary.reindex(items)
    if method == "greedy":
        dens = s / (1e-9 + (cost / budget if budget else 0) + (ld / load if load else 0) + 1 / n_max)
        pick, cb, lb = [], 0.0, 0.0
        for d, m in (min_per_domain or {}).items():                         # 분야 최소 개수를 먼저 채운다
            for j in [j for j in np.argsort(-s) if dom.iloc[j] == d][:m]:
                if j not in pick:
                    pick.append(j); cb += cost[j]; lb += ld[j]
        for j in np.argsort(-dens):
            if len(pick) >= n_max:
                break
            if j in pick or (budget and cb + cost[j] > budget) or (load and lb + ld[j] > load):
                continue
            pick.append(j); cb += cost[j]; lb += ld[j]
        x = np.zeros(len(items)); x[pick] = 1
    else:
        A, lo, hi = [np.ones(len(items))], [0], [n_max]
        if budget:
            A.append(cost); lo.append(0); hi.append(budget)
        if load:
            A.append(ld); lo.append(0); hi.append(load)
        for d, m in (min_per_domain or {}).items():
            A.append((dom == d).to_numpy().astype(float)); lo.append(min(m, int((dom == d).sum()))); hi.append(len(items))
        res = milp(-s, constraints=LinearConstraint(np.vstack(A), lo, hi), integrality=np.ones(len(items)), bounds=Bounds(0, 1))
        if res.x is None:
            return dict(items=[], value=0.0, cost=0.0, load=0.0, feasible=False)
        x = np.round(res.x)
    sel = [items[j] for j in np.where(x > 0.5)[0]]
    return dict(items=sel, value=float(s @ x), cost=float(cost @ x), load=float(ld @ x), feasible=True)


OBSTACLE_RULES = [("기관 협조", lambda q: q["partner_rate"] >= 0.4), ("예산", lambda q: q["cost_tier"] >= 4), ("운영 부담", lambda q: q["staff_tier"] >= 4),
                  ("공간", lambda q: q["place_senior"] + q["place_welfare"] + q["place_hall"] >= 0.5), ("대상자 특성", lambda q: q["household_visit"] >= 0.3)]


def checklist(std_id, cid, req, cap, comp):
    """한 단지·한 프로그램의 실행 점검표(화면·설명용 사전)."""
    q, k = req.loc[std_id], cap.loc[cid]
    og, rs = D.codebook()["partner_org"], D.codebook()["resource"]
    partners = [(o, float(q[f"og_{o}"])) for o in OG_IDS if q[f"og_{o}"] >= 0.08]
    partners.sort(key=lambda t: -t[1])
    status = {1.0: "협력 이력 있음", 0.7: "가까운 시설 있음", 0.3: "이력·가까운 시설 없음"}
    cats = ["주민 참여·신뢰"] + [name for name, rule in OBSTACLE_RULES if rule(q)]
    pb = D.casebook()["playbook"]
    tips = [dict(obstacle=r_["obstacle_category"], strategy=r_["solution_strategy"], cases=r_["cases"], n=int(r_["n"]))
            for _, r_ in pb[pb["obstacle_category"].isin(cats)].sort_values("n", ascending=False).groupby("obstacle_category").head(1).iterrows()]
    out = dict(
        resources=[rs[x] for x in RS_IDS if q[f"res_{x}"] >= 0.3],
        partners=[dict(type=og[o], share=round(s, 2), status=status[float(k[f"a_{o}"])]) for o, s in partners[:4]],
        partner_needed=bool(q["partner_rate"] >= 0.4), place=[PLACE_KO[p] for p in PLACES if q[f"place_{p}"] >= 0.2],
        staff_tier=int(q["staff_tier"]), cost_tier=int(q["cost_tier"]), cost_year_est=int(round(q["cost_year"], -4)),
        external_share=round(float(q["ext_burden"]), 2), participants_med=int(q["participants_med"]), peak_months=q["peak_months"],
        fit={n: round(float(v.at[cid, std_id]), 2) for n, v in comp.items()}, obstacles=tips, basis="draft")
    if "x_difficulty" in q.index and pd.notna(q["x_difficulty"]):          # 전문가 검토값이 있으면 같이 싣는다
        ess = [o for o in str(q["x_partners"]).split("|") if o in og]
        out.update(basis="expert", difficulty=int(q["x_difficulty"]), cost_session=int(q["x_cost_session"]), staff_hours_session=float(q["x_staff_hours"]),
                   cost_year_total=int(round(q["cost_year_total"], -4)), payers=str(q["x_payers"]).split("|"), internal_share=round(float(q["x_internal_share"]), 2),
                   essential_places=[PLACE_KO[p] for p in str(q["x_places"]).split("|") if p in PLACE_KO],
                   essential_partners=[dict(type=og[o], status=status[float(k[f"a_{o}"])]) for o in ess], self_run=bool(q["x_self_run"]),
                   needs_welfare_worker=bool(q["x_needs_welfare_worker"]), deployed=bool(k["deployed"]),
                   welfare_gap=bool(q["x_needs_welfare_worker"] and not k["deployed"]))
    return out


# ───────── 전문가 요건 반영(시트 B) ─────────
LOAD_HOURS = 80.0            # 새로 더하는 묶음의 연간 인력 한도(명×시간) 기본값. 단지가 지금 하는 프로그램의 추정 합계(중앙값 약 300시간)의 4분의 1 수준


def apply_expert(req, xb):
    """기록에서 추정한 요건에 전문가 값을 덮어쓴다. 초안은 *_draft 열로 남긴다.

    cost_year  = 1회 실제 비용 × 단지당 연간 기록 수 × 공단 쪽(단지·공단·LH) 부담 비중
    staff_load = 1회 필요 인력(명×시간) × 단지당 연간 기록 수   → 단위가 '연간 명×시간'으로 바뀐다
    부담 비중은 전문가가 적은 순서(먼저 적은 주체가 더 많이 부담)로 나눈 가정값이다.
    """
    q = req.copy()
    xb = xb.reindex(q.index)
    q["cost_year_draft"], q["staff_load_draft"], q["staff_tier_draft"], q["cost_tier_draft"] = q["cost_year"], q["staff_load"], q["staff_tier"], q["cost_tier"]
    for c in xb.columns:
        q[c] = xb[c]
    n = q["recs_per_complex_year"]
    q["cost_year_total"] = q["x_cost_session"] * n
    q["cost_year"] = (q["cost_year_total"] * q["x_internal_share"]).fillna(q["cost_year_draft"])
    q["staff_load"] = (q["x_staff_hours"] * n).fillna(q["staff_load_draft"])
    q["staff_tier"] = q["x_difficulty"].fillna(q["staff_tier_draft"]).astype(int)                      # 화면의 '부담 5단계'는 전문가 난이도로 바꾼다
    q["cost_tier"] = pd.cut(q["cost_year_total"], [-1, 1e5, 5e5, 2e6, 1e7, np.inf], labels=False) + 1
    return q


def feasibility_expert(reqx, cap):
    """전문가 요건으로 만든 실행 가능성(0~1)과 성분. 규칙은 그대로 두고 요건만 전문가 값으로 바꾼다. 가중치를 학습하지 않는다.

    welfare: 주거복지사가 필요한 프로그램인데 미배치면 0.4
    space  : 전문가가 적은 필수 공간 가운데 하나라도 쓸 수 있으면 1(세대 방문·야외·단지 밖은 늘 가능)
    partner: 필수 협력기관의 평균 협력 여건(이력 1 / 가까운 시설 0.7 / 없음 0.3). 자체 운영 가능하면 1
    ease   : 난이도 1→1.0 … 5→0.4
    """
    ids, items = cap.index, reqx.index
    dep = cap["deployed"].to_numpy()[:, None]
    welfare = np.where((reqx["x_needs_welfare_worker"].to_numpy()[None, :] == 1) & (dep == 0), 0.4, 1.0)
    has = dict(home=np.ones(len(cap)), onsite=np.ones(len(cap)), offsite=np.ones(len(cap)), senior=cap["sp_senior"].to_numpy().astype(float),
               welfare=np.maximum(cap["sp_welfare"], 0.5 * (cap["a_OG03"] >= 0.7)).to_numpy().astype(float), hall=np.maximum(cap["sp_hall"], 0.7).to_numpy().astype(float))
    space = np.ones((len(cap), len(items)))
    partner = np.ones((len(cap), len(items)))
    for j, (pl, og, self_run) in enumerate(zip(reqx["x_places"].fillna(""), reqx["x_partners"].fillna(""), reqx["x_self_run"].fillna(0))):
        pl, og = [p for p in pl.split("|") if p], [o for o in og.split("|") if o]
        if pl:
            space[:, j] = np.max([has[p] for p in pl], axis=0)
        if og and not self_run:
            partner[:, j] = cap[[f"a_{o}" for o in og]].to_numpy().mean(1)
    ease = np.tile(1 - 0.15 * (reqx["x_difficulty"].fillna(3).to_numpy() - 1), (len(cap), 1))
    comp = {k: pd.DataFrame(v, index=ids, columns=items) for k, v in dict(welfare=welfare, space=space, partner=partner, ease=ease).items()}
    total = pd.DataFrame((welfare * space * partner * ease) ** 0.25, index=ids, columns=items)
    return total, comp
