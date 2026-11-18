# -*- coding: utf-8 -*-
"""배경·문제정의 재설계용 보강 분석(기존 EDA에 없던 것).

r01 단지 간 격차(인구·주거·접근성 지표의 하위 10%·상위 10%)
r02 지역 환경(대도시 자치구 / 시 / 군)별 접근성·고령·공급
r03 외부 복지시설이 먼 단지에 단지 안 프로그램이 더 가는가(보완 여부)
r04 영구임대 vs 국민임대: 주민 구성은 다른데 프로그램 구성은 얼마나 같은가
r05 관성: 올해 프로그램은 작년 자기 단지와 닮았나, 주민 구성이 비슷한 단지와 닮았나
r06 주거복지사 배치 기준(500세대)과 필요
r07 주민이 원한다고 답한 것과 실제 공급(해피콜 × 프로그램 기록)
사용: python redesign_analysis.py <EDA 폴더>  → <EDA 폴더>/redesign/{figures,tables,summary.json}
모든 관계는 상관·기술 통계이며 원인을 증명하지 않는다.
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial.distance import braycurtis, cosine

import eda_data as ED
import problem_def as P
import web_extra as WX
from community_nlp import taxonomy as TX
from community_nlp.figures import SURFACE, INK1, INK2, INK3, GRID, AXIS, CAT, GRAY_N

OUT = os.path.join(sys.argv[1], "redesign")
FIG, TAB = os.path.join(OUT, "figures"), os.path.join(OUT, "tables")
os.makedirs(FIG, exist_ok=True); os.makedirs(TAB, exist_ok=True)
ROOT = r"C:/Users/user/Desktop/2026 DRIVE/project/data/"
rd = lambda p, **k: pd.read_csv(p, encoding="utf-8-sig", low_memory=False, **k)
f = lambda n: os.path.join(FIG, n)
HI = P.HI
S = {}

D = P.load()
b, r, master, sd = D["b"].copy(), D["r"], D["master"], D["sd"]
acc_cols = [c for c in master.columns if c.startswith("접근성_") and c.endswith("_대표점_km")]
add = [c for c in acc_cols + ["평형_40㎡미만세대비율", "입주기준경과년수"] if c not in b.columns]
b = b.merge(master[["complex_id"] + add], on="complex_id", how="left")
b["comm_per1000"] = b["n_res"] / 2.5 / b["세대수"] * 1000
b["pct60"] = b["인구_60세이상_비율"] * 100
A = lambda name: f"접근성_{name}_대표점_km"


def q(s, p):
    return float(np.nanpercentile(s.dropna(), p))


# ───────── r01 단지 간 격차 ─────────
vars_ = [("60세 이상 비율(%)", b["pct60"]), ("80세 이상 비율(%)", b["인구_80세이상_비율"] * 100), ("20세 미만 비율(%)", b["인구_20세미만_비율"] * 100),
         ("전용 40㎡ 미만 세대 비율(%)", b["평형_40㎡미만세대비율"] * (100 if b["평형_40㎡미만세대비율"].max() <= 1.01 else 1)), ("입주 후 경과 연수(년)", b["입주기준경과년수"]),
         ("세대수", b["세대수"]), ("홈닥터 지원(100세대당 월)", b["hd_per100"]), ("홈닥터 중 의료지원 비중(%)", b["hd25_의료지원_share"] * 100),
         ("노인복지관까지 거리(km)", b[A("노인복지관")]), ("종합사회복지관까지 거리(km)", b[A("종합사회복지관")]), ("병원까지 거리(km)", b[A("병원")]),
         ("보건기관까지 거리(km)", b[A("보건기관")]), ("프로그램 기록(1,000세대당 연)", b["comm_per1000"])]
rows = []
for lab, s in vars_:
    s = s.replace([np.inf, -np.inf], np.nan)
    rows.append(dict(variable=lab, n=int(s.notna().sum()), p10=q(s, 10), median=q(s, 50), p90=q(s, 90), min=float(s.min()), max=float(s.max()),
                     p90_over_p10=(q(s, 90) / q(s, 10) if q(s, 10) > 0 else np.nan)))
T1 = pd.DataFrame(rows)
T1.to_csv(os.path.join(TAB, "r01_between_complex_gaps.csv"), index=False, encoding="utf-8-sig")
S["gaps"] = {r_["variable"]: dict(p10=r_["p10"], median=r_["median"], p90=r_["p90"], ratio=r_["p90_over_p10"]) for _, r_ in T1.iterrows()}
fig, ax = P._fig(1, size=(11, 6.2))
ax.grid(axis="y", visible=False); ax.grid(axis="x", color=GRID)
t = T1[T1["p90_over_p10"].notna()].sort_values("p90_over_p10")
ax.barh(t["variable"], t["p90_over_p10"], color=[HI if "거리" in v else CAT[0] for v in t["variable"]], height=0.6)
for y, (v, a_, c_) in enumerate(zip(t["p90_over_p10"], t["p10"], t["p90"])):
    ax.text(v * 1.04, y, f"{v:.1f}배  ({a_:,.1f} → {c_:,.1f})", va="center", fontsize=10, color=INK1)
ax.set_xscale("log"); ax.set_xlim(1, t["p90_over_p10"].max() * 4)
ax.tick_params(axis="y", labelsize=10.5, colors=INK1)
ax.set_xlabel("상위 10% 단지 ÷ 하위 10% 단지 (배, 로그 눈금) — 괄호는 하위 10% → 상위 10% 값", fontsize=10, color=INK2)
far = T1.set_index("variable").loc["종합사회복지관까지 거리(km)"]
sen = T1.set_index("variable").loc["노인복지관까지 거리(km)"]
P._head(fig, "실증 1 · 단지마다 다르다", f"단지 간 격차는 복지시설 접근성에서 가장 크다: 종합사회복지관까지 {far['p10']:.1f}km인 단지와 {far['p90']:.1f}km인 단지",
        f"공단 관리 {len(b)}개 단지의 하위 10%와 상위 10% 비교. 빨간 막대는 시설까지의 거리(노인복지관은 {sen['p10']:.1f}km ↔ {sen['p90']:.1f}km로 {sen['p90_over_p10']:.0f}배)")
P._foot(fig, "자료: 단지 통합표(인구·주택·홈닥터), 국토정책지표 250m 격자 접근성(단지 대표점), 커뮤니티 NLP. 하위 10%가 0인 지표는 제외")
P._save(fig, f("r01_between_complex_gaps.png"))

# ───────── r02 지역 환경 ─────────
def region_type(addr):
    t_ = str(addr).split()
    if len(t_) < 2:
        return None
    if t_[1].endswith("군"):
        return "군 지역"
    if ("특별시" in t_[0] or "광역시" in t_[0]) and t_[1].endswith("구"):
        return "대도시 자치구"
    return "시 지역"
b["region_type"] = b["기본주소"].map(region_type)
RT = ["대도시 자치구", "시 지역", "군 지역"]
g = b.groupby("region_type").agg(n=("complex_id", "size"), pct60=("pct60", "median"), d_senior=(A("노인복지관"), "median"), d_welfare=(A("종합사회복지관"), "median"),
                                 d_hospital=(A("병원"), "median"), d_health=(A("보건기관"), "median"), comm=("comm_per1000", "median"), rich=("std_richness", "median"),
                                 hh=("세대수", "median"), hd=("hd_per100", "median")).reindex(RT)
g.to_csv(os.path.join(TAB, "r02_region_type.csv"), encoding="utf-8-sig")
S["region"] = {k: {c: (None if pd.isna(v) else float(v)) for c, v in row.items()} for k, row in g.iterrows()}
kw = stats.kruskal(*[b.loc[b["region_type"] == k, A("노인복지관")].dropna() for k in RT])
S["region_kw_p_senior"] = float(kw.pvalue)
fig, axes = P._fig(3, size=(13, 5.2))
for ax, (col, lab, fmt) in zip(axes, [("pct60", "60세 이상 비율(%, 중앙값)", "{:.0f}%"), ("d_welfare", "종합사회복지관까지 거리(km, 중앙값)", "{:.1f}km"), ("rich", "운영한 프로그램 종류(중앙값)", "{:.0f}종")]):
    ax.bar(range(3), g[col], color=[CAT[0], CAT[0], HI] if col == "d_welfare" else ([HI, CAT[0], CAT[0]] if col == "pct60" else GRAY_N), width=0.6)
    for i, v in enumerate(g[col]):
        ax.text(i, v * 1.02, fmt.format(v), ha="center", va="bottom", fontsize=11, color=INK1)
    ax.set_xticks(range(3)); ax.set_xticklabels([f"{k}\n({int(g.loc[k, 'n'])}곳)" for k in RT], fontsize=10)
    ax.set_title(lab, fontsize=11, color=INK1, loc="left"); ax.set_ylim(0, g[col].max() * 1.2)
P._head(fig, "실증 1 · 단지마다 다르다", f"대도시 단지는 고령 {g.loc['대도시 자치구', 'pct60']:.0f}%·복지관 {g.loc['대도시 자치구', 'd_welfare']:.1f}km, 군 지역 단지는 고령 {g.loc['군 지역', 'pct60']:.0f}%·복지관 {g.loc['군 지역', 'd_welfare']:.0f}km",
        f"지역 환경에 따라 주민 구성과 단지 밖 자원이 정반대인데, 운영한 프로그램 종류는 {g['rich'].min():.0f}~{g['rich'].max():.0f}종으로 비슷하다")
P._foot(fig, "지역 환경 = 단지 주소 기준(특별·광역시의 구 / 시 / 군). 값은 단지 중앙값. 군 지역은 소규모 국민임대가 많다(세대수 중앙값 "
        f"{g.loc['군 지역', 'hh']:.0f} vs 대도시 {g.loc['대도시 자치구', 'hh']:,.0f})")
P._save(fig, f("r02_region_environment.png"), top=0.78)

# ───────── r03 외부 시설이 먼 단지에 프로그램이 더 가는가 ─────────
x = b[(b["n_res"] >= 15)].copy()
x["far_idx"] = x[[A("노인복지관"), A("종합사회복지관")]].rank(pct=True).mean(axis=1)
x = x[x["far_idx"].notna()]
r_sup = P._rho(x["far_idx"], x["comm_per1000"])
r_rich = P._rho(x["far_idx"], x["std_richness"])
r_eld = P._rho(x["far_idx"], x["eld_share"])
xe = x[x["pct60"] >= 50]                                              # 고령 단지(60세 이상 50% 이상)만 따로 확인
re_sup, re_rich = P._rho(xe["far_idx"], xe["comm_per1000"]), P._rho(xe["far_idx"], xe["std_richness"])
x["far_t"] = pd.qcut(x["far_idx"], 3, labels=["가까운 1/3", "중간", "먼 1/3"])
gt = x.groupby("far_t", observed=True).agg(n=("complex_id", "size"), d_senior=(A("노인복지관"), "median"), d_welfare=(A("종합사회복지관"), "median"),
                                           comm=("comm_per1000", "median"), rich=("std_richness", "median"), pct60=("pct60", "median"))
gt.to_csv(os.path.join(TAB, "r03_access_vs_supply.csv"), encoding="utf-8-sig")
S["access_supply"] = dict(rho_supply=r_sup, rho_richness=r_rich, rho_elderly_share=r_eld, elderly_only=dict(n=int(len(xe)), rho_supply=re_sup, rho_richness=re_rich), tertiles={k: {c: float(v) for c, v in row.items()} for k, row in gt.iterrows()}, n=int(len(x)))
fig, axes = P._fig(2, size=(12.5, 5.6))
for ax, (col, lab, fmt) in zip(axes, [("comm", "프로그램 기록(1,000세대당 연, 중앙값)", "{:.0f}건"), ("rich", "운영한 프로그램 종류(중앙값)", "{:.0f}종")]):
    ax.bar(range(3), gt[col], color=[CAT[0], CAT[0], HI], width=0.6)
    for i, v in enumerate(gt[col]):
        ax.text(i, v * 1.02, fmt.format(v), ha="center", va="bottom", fontsize=11.5, color=INK1)
    ax.set_xticks(range(3)); ax.set_xticklabels([f"{k}\n노인복지관 {gt.loc[k, 'd_senior']:.1f}km" for k in gt.index], fontsize=10)
    ax.set_title(lab, fontsize=11, color=INK1, loc="left"); ax.set_ylim(0, gt[col].max() * 1.22)
P._head(fig, "실증 2 · 그런데 프로그램은 따라가지 않는다", f"복지시설이 먼 단지라고 단지 안 프로그램이 더 많지 않다: 가까운 단지 {gt['comm'].iloc[0]:.0f}건, 먼 단지 {gt['comm'].iloc[-1]:.0f}건",
        f"외부 복지시설 거리와 세대당 프로그램의 순위상관 {r_sup['rho']:+.2f}({r_sup['lo']:+.2f}~{r_sup['hi']:+.2f}). 프로그램 종류는 먼 단지가 더 적다({gt['rich'].iloc[0]:.0f}종 → {gt['rich'].iloc[-1]:.0f}종). 단지 밖 자원의 빈자리를 단지 안에서 메우는 모습은 보이지 않는다")
P._foot(fig, f"주민 대상 기록 15건 이상 {len(x)}개 단지를 노인복지관·종합사회복지관 거리 순으로 3등분. 먼 단지는 고령 비율이 낮은 편이다({gt['pct60'].iloc[-1]:.0f}% vs {gt['pct60'].iloc[0]:.0f}%). "
        f"고령 단지(60세 이상 50% 이상, {len(xe)}곳)만 봐도 세대당 프로그램 {re_sup['rho']:+.2f}, 종류 {re_rich['rho']:+.2f}")
P._save(fig, f("r03_access_not_compensated.png"), top=0.78)

# ───────── r04 영구임대 vs 국민임대 프로그램 구성 ─────────
fam = [c for c in b.columns if c.startswith("share_family_F") and c != "share_family_F99"]
y = b[b["n_res"] >= 15]
mix = y.groupby("supply_group")[fam].mean()
pv, nv = mix.loc["영구임대"].values, mix.loc["국민임대"].values
pv, nv = pv / pv.sum(), nv / nv.sum()
overlap = 1 - braycurtis(pv, nv)
cos = 1 - cosine(pv, nv)
age_p, age_n = y.loc[y["supply_group"] == "영구임대", "pct60"].median(), y.loc[y["supply_group"] == "국민임대", "pct60"].median()
lab = [TX.FAMILIES[c.replace("share_family_", "")] for c in fam]
T4 = pd.DataFrame(dict(family=lab, 영구임대=pv * 100, 국민임대=nv * 100)); T4["diff_pp"] = T4["영구임대"] - T4["국민임대"]
T4.sort_values("diff_pp").to_csv(os.path.join(TAB, "r04_mix_by_supply_type.csv"), index=False, encoding="utf-8-sig")
S["mix_supply"] = dict(overlap=float(overlap), cosine=float(cos), age_perm=float(age_p), age_nat=float(age_n), n_perm=int((y["supply_group"] == "영구임대").sum()),
                       n_nat=int((y["supply_group"] == "국민임대").sum()), max_diff=(T4.loc[T4["diff_pp"].abs().idxmax(), "family"], float(T4["diff_pp"].abs().max())))
fig, ax = P._fig(1, size=(11.5, 6.4))
ax.grid(axis="y", visible=False); ax.grid(axis="x", color=GRID)
t4 = T4.sort_values("영구임대")
yy = np.arange(len(t4))
ax.barh(yy + 0.2, t4["영구임대"], height=0.38, color=CAT[1], label=f"영구임대({S['mix_supply']['n_perm']}곳, 60세 이상 중앙값 {age_p:.0f}%)")
ax.barh(yy - 0.2, t4["국민임대"], height=0.38, color=CAT[0], label=f"국민임대({S['mix_supply']['n_nat']}곳, 60세 이상 중앙값 {age_n:.0f}%)")
ax.set_yticks(yy); ax.set_yticklabels(t4["family"], fontsize=10.5, color=INK1)
ax.set_xlabel("주민 대상 프로그램 기록 중 비중(%, 단지 평균)", fontsize=10.5, color=INK2)
ax.legend(loc="lower right", frameon=False, fontsize=10.5, labelcolor=INK2)
P._head(fig, "실증 2 · 그런데 프로그램은 따라가지 않는다", f"주민 구성이 전혀 다른 영구임대와 국민임대의 프로그램 구성이 {overlap * 100:.0f}% 겹친다",
        f"60세 이상 비율은 {age_p:.0f}% 대 {age_n:.0f}%로 {age_p - age_n:.0f}%p 차이인데, 15개 영역 비중의 차이는 가장 큰 영역도 {S['mix_supply']['max_diff'][1]:.1f}%p({S['mix_supply']['max_diff'][0]})")
P._foot(fig, "겹침 = 두 구성에서 영역별로 겹치는 몫의 합(1에서 Bray–Curtis 거리를 뺀 값). 주민 대상 기록 15건 이상 단지. 프로그램 영역은 NLP 자동 분류(silver label)")
P._save(fig, f("r04_same_mix_different_residents.png"))

# ───────── r05 관성: 작년 자기 단지 vs 비슷한 단지 ─────────
rr = r.copy()
rr["year"] = pd.to_datetime(rr["start_date"]).dt.year
s24 = rr[rr["year"] == 2024].groupby("complex_id")["std_id"].apply(set)
s25 = rr[rr["year"] == 2025].groupby("complex_id")["std_id"].apply(set)
n24 = rr[rr["year"] == 2024].groupby("complex_id").size(); n25 = rr[rr["year"] == 2025].groupby("complex_id").size()
ok = [c for c in s24.index if c in s25.index and n24[c] >= 8 and n25[c] >= 8]
nb = rd(os.path.join(sys.argv[1], "problem_definition", "tables", "context_neighbors_k10.csv")).groupby("complex_id")["neighbor_id"].apply(list).to_dict()
jac = lambda a, c: len(a & c) / len(a | c) if (a | c) else np.nan
rng = np.random.default_rng(7)
rows = []
for c in ok:
    own = jac(s24[c], s25[c])
    reuse = len(s25[c] & s24[c]) / len(s25[c])                         # 올해 종류 중 작년에도 한 것
    rec25 = rr[(rr["complex_id"] == c) & (rr["year"] == 2025)]
    reuse_rec = rec25["std_id"].isin(s24[c]).mean()                    # 올해 기록 중 작년에 하던 종류
    peers = [jac(s25[c], s25[n_]) for n_ in nb.get(c, []) if n_ in s25.index and n_ in ok]
    rnd = [jac(s25[c], s25[o]) for o in rng.choice([o for o in ok if o != c], 10, replace=False)]
    rows.append(dict(complex_id=c, own_prev_year=own, similar_complexes=np.nanmean(peers) if peers else np.nan, random_complexes=np.nanmean(rnd),
                     reuse_types=reuse, reuse_records=reuse_rec, n_types_2025=len(s25[c]), new_types_2025=len(s25[c] - s24[c])))
T5 = pd.DataFrame(rows)
T5.to_csv(os.path.join(TAB, "r05_inertia_by_complex.csv"), index=False, encoding="utf-8-sig")
w = stats.wilcoxon(T5.dropna(subset=["similar_complexes"])["own_prev_year"], T5.dropna(subset=["similar_complexes"])["similar_complexes"])
S["inertia"] = dict(n=int(len(T5)), own=float(T5["own_prev_year"].median()), similar=float(T5["similar_complexes"].median()), random=float(T5["random_complexes"].median()),
                    reuse_types=float(T5["reuse_types"].median()), reuse_records=float(T5["reuse_records"].median()), new_types=float(T5["new_types_2025"].median()),
                    n_types=float(T5["n_types_2025"].median()), wilcoxon_p=float(w.pvalue), ratio=float(T5["own_prev_year"].median() / T5["similar_complexes"].median()),
                    similar_minus_random=float(T5["similar_complexes"].median() - T5["random_complexes"].median()))
fig, ax = P._fig(1, size=(11, 5.8))
vals = [T5["own_prev_year"].dropna() * 100, T5["similar_complexes"].dropna() * 100, T5["random_complexes"].dropna() * 100]
bp = ax.boxplot(vals, vert=True, widths=0.5, patch_artist=True, showfliers=False, medianprops=dict(color=INK1, linewidth=2))
for patch, col in zip(bp["boxes"], [HI, CAT[0], GRAY_N]):
    patch.set_facecolor(col); patch.set_alpha(0.75); patch.set_edgecolor(SURFACE)
for i, v in enumerate(vals):
    ax.text(i + 1.32, v.median(), f"중앙값 {v.median():.0f}%", va="center", fontsize=11.5, color=INK1, fontweight="bold")
ax.set_xticks([1, 2, 3]); ax.set_xticklabels(["같은 단지의 작년(2024)", "주민 구성이 비슷한\n다른 단지 10곳(2025)", "임의의 다른 단지\n10곳(2025)"], fontsize=11)
ax.set_ylabel("2025년 프로그램 종류가 겹치는 정도(%)", fontsize=10.5, color=INK2); ax.set_xlim(0.5, 3.9)
i_ = S["inertia"]
P._head(fig, "기존 의사결정의 한계 · 관성", f"올해 프로그램은 '비슷한 단지'보다 '작년의 우리 단지'를 {i_['ratio']:.1f}배 더 닮았다",
        f"2025년에 운영한 프로그램 종류의 {i_['reuse_types'] * 100:.0f}%는 2024년에도 하던 것. 주민 구성이 비슷한 단지와의 겹침({i_['similar'] * 100:.0f}%)은 임의의 단지({i_['random'] * 100:.0f}%)와 {i_['similar_minus_random'] * 100:.0f}%p 차이")
P._foot(fig, f"겹침 = 표준 프로그램 종류의 Jaccard 지수. 2024·2025년 주민 대상 기록이 각각 8건 이상인 {i_['n']}개 단지. 명절·기념일처럼 해마다 하는 행사가 있어 일정한 반복은 자연스럽다")
P._save(fig, f("r05_inertia_last_year.png"))

# ───────── r06 주거복지사 배치 기준 ─────────
dep = rd(ROOT + "processed/casebook_programs_v1/features/welfare_worker_deployment_2025.csv")
dep_ids = set(dep.loc[dep["complex_id"].notna() & (dep["needs_review"] == 0), "complex_id"])
b["deployed"] = b["complex_id"].isin(dep_ids).astype(int)
perm = b[b["공급유형"].astype(str).str.contains("영구임대")].copy()
perm["size500"] = np.where(perm["세대수"] >= 500, "500세대 이상", "500세대 미만")
g6 = perm.groupby("size500").agg(n=("complex_id", "size"), deployed=("deployed", "sum"), pct60=("pct60", "median"), pct80=("인구_80세이상_비율", lambda s: s.median() * 100),
                                 hd=("hd_per100", "median"), comm=("comm_per1000", "median"), hh=("세대수", "median"), households=("세대수", "sum"))
g6.to_csv(os.path.join(TAB, "r06_deployment_threshold.csv"), encoding="utf-8-sig")
small = perm[perm["세대수"] < 500]
big = perm[perm["세대수"] >= 500]
S["deploy"] = dict(n_perm=int(len(perm)), n_small=int(len(small)), n_small_deployed=int(small["deployed"].sum()), n_big=int(len(big)), n_big_deployed=int(big["deployed"].sum()),
                   pct60_small=float(small["pct60"].median()), pct60_big=float(big["pct60"].median()), pct80_small=float(small["인구_80세이상_비율"].median() * 100),
                   pct80_big=float(big["인구_80세이상_비율"].median() * 100), households_small=float(small["세대수"].sum()), comm_small=float(small["comm_per1000"].median()),
                   comm_big=float(big["comm_per1000"].median()), n_small_older_than_big_median=int((small["pct60"] >= big["pct60"].median()).sum()),
                   n_deployed_matched=int(len(dep_ids)), n_deployed_book=int(len(dep)), mw_p=float(stats.mannwhitneyu(small["pct60"].dropna(), big["pct60"].dropna()).pvalue))
# 기준선 근처(350~700세대) 영구임대 단지: 배치 여부에 따른 프로그램 차이(규모가 비슷한 단지끼리, 상관)
near = perm[(perm["세대수"] >= 350) & (perm["세대수"] <= 700)].merge(D["cf"][["complex_id", "active_month_ratio"]].rename(columns={"active_month_ratio": "amr"}), on="complex_id", how="left")
gn = near.groupby("deployed").agg(n=("complex_id", "size"), hh=("세대수", "median"), pct60=("pct60", "median"), rich=("std_richness", "median"), comm=("comm_per1000", "median"), active_month_ratio=("amr", "median"))
gn.to_csv(os.path.join(TAB, "r06b_near_threshold_deployed_vs_not.csv"), encoding="utf-8-sig")
S["deploy_near"] = dict(range="350~700세대", n_dep=int(gn.loc[1, "n"]), n_not=int(gn.loc[0, "n"]), hh_dep=float(gn.loc[1, "hh"]), hh_not=float(gn.loc[0, "hh"]), rich_dep=float(gn.loc[1, "rich"]),
                        rich_not=float(gn.loc[0, "rich"]), comm_dep=float(gn.loc[1, "comm"]), comm_not=float(gn.loc[0, "comm"]), months_dep=float(gn.loc[1, "active_month_ratio"]),
                        months_not=float(gn.loc[0, "active_month_ratio"]), pct60_dep=float(gn.loc[1, "pct60"]), pct60_not=float(gn.loc[0, "pct60"]),
                        mw_p_rich=float(stats.mannwhitneyu(near.loc[near["deployed"] == 1, "std_richness"].dropna(), near.loc[near["deployed"] == 0, "std_richness"].dropna()).pvalue))
ex = perm[(perm["세대수"] < 500) & (perm["세대수"] >= 470)].sort_values("세대수", ascending=False)
S["deploy_examples"] = [dict(name=r_["단지명"], households=int(r_["세대수"]), pct60=float(r_["pct60"])) for _, r_ in ex.head(6).iterrows()]
perm[["complex_id", "단지명", "지사명", "공급유형", "세대수", "pct60", "deployed", "comm_per1000", "hd_per100"]].to_csv(os.path.join(TAB, "r06_permanent_rental_complexes.csv"), index=False, encoding="utf-8-sig")
fig, ax = P._fig(1, size=(11, 6.0))
for flag, col, lab_ in [(1, CAT[0], "주거복지사 배치(2025)"), (0, HI, "미배치")]:
    s_ = perm[perm["deployed"] == flag]
    ax.scatter(s_["세대수"], s_["pct60"], s=46, color=col, alpha=0.85, edgecolor="#ffffff", linewidth=0.6, label=f"{lab_} {len(s_)}곳")
ax.axvline(500, color=INK1, linestyle="--", linewidth=1.3)
ax.text(510, ax.get_ylim()[0] + 2, "배치 기준 500세대", fontsize=10.5, color=INK1)
ax.set_xscale("log"); ax.set_xlabel("세대수(로그 눈금)", fontsize=10.5, color=INK2); ax.set_ylabel("60세 이상 비율(%)", fontsize=10.5, color=INK2)
ax.legend(loc="lower right", frameon=False, fontsize=10.5, labelcolor=INK2)
d_ = S["deploy"]
P._head(fig, "기존 의사결정의 한계 · 기준", f"500세대 미만 영구임대 {d_['n_small']}곳은 고령 비율이 {d_['pct60_small']:.0f}%로 같은데 주거복지사가 한 곳도 없다",
        f"영구임대를 포함한 {d_['n_perm']}개 단지. 500세대 이상 {d_['n_big']}곳(60세 이상 중앙값 {d_['pct60_big']:.0f}%) 중 {d_['n_big_deployed']}곳 배치, 500세대 미만 {d_['n_small']}곳({d_['households_small']:,.0f}세대) 중 {d_['n_small_deployed']}곳 배치")
P._foot(fig, "배치 단지 = 주거복지사 활동 사례집(주택관리공단, 2025)의 배치 목록 111곳 중 통합표와 연결된 102곳. 배치 기준은 영구임대 500세대 이상(세대수는 통합표의 단지 전체 세대수라 일부 차이 가능)")
P._save(fig, f("r06_deployment_threshold.png"))

# ───────── r07 주민 수요 vs 공급 ─────────
DEM = WX.demand(D["pa"])
vs = pd.DataFrame(DEM["vs"]).sort_values("demand_share")
vs.drop(columns=["purposes"]).to_csv(os.path.join(TAB, "r07_demand_vs_supply.csv"), index=False, encoding="utf-8-sig")
vi = vs.set_index("k")
n_dem = DEM["pops"]["residential_life_support_service_users"]["n"]
S["demand"] = dict(n=int(n_dem), matched_record_share=float(DEM["matched_record_share"]), rows={k: dict(demand_pct=float(v["demand_pct"]), demand_share=float(v["demand_share"]), supply_share=float(v["supply_share"])) for k, v in vi.iterrows()})
fig, ax = P._fig(1, size=(11, 5.8))
ax.grid(axis="y", visible=False); ax.grid(axis="x", color=GRID)
yy = np.arange(len(vs))
ax.barh(yy + 0.2, vs["demand_share"] * 100, height=0.38, color=CAT[1], label=f"주민이 필요하다고 답한 비중(해피콜, {n_dem}명)")
ax.barh(yy - 0.2, vs["supply_share"] * 100, height=0.38, color=CAT[0], label=f"실제 프로그램 기록 비중(대응되는 기록 {DEM['matched_record_share'] * 100:.0f}% 안에서)")
for i, (a_, c_) in enumerate(zip(vs["demand_share"] * 100, vs["supply_share"] * 100)):
    ax.text(a_ + 0.4, i + 0.2, f"{a_:.0f}%", va="center", fontsize=10.5, color=INK1); ax.text(c_ + 0.4, i - 0.2, f"{c_:.0f}%", va="center", fontsize=10.5, color=INK1)
ax.set_yticks(yy); ax.set_yticklabels(vs["k"], fontsize=11, color=INK1); ax.set_xlabel("비중(%)", fontsize=10.5, color=INK2)
ax.legend(loc="lower right", frameon=False, fontsize=10.5, labelcolor=INK2)
P._head(fig, "실증 3 · 주민이 말한 필요와도 어긋난다", f"주민 수요의 {vi.loc['경제적 지원', 'demand_share'] * 100:.0f}%인 '경제적 지원'은 공급의 {vi.loc['경제적 지원', 'supply_share'] * 100:.0f}%, '일자리'는 {vi.loc['일자리', 'demand_share'] * 100:.0f}% 대 {vi.loc['일자리', 'supply_share'] * 100:.0f}%",
        "2025 해피콜 주거생활지원 서비스 이용자가 고른 '필요한 복지 서비스'(복수 응답을 합 100%로 환산)와 같은 분류로 묶은 프로그램 기록")
P._foot(fig, f"수요는 전국 응답(단지별 값 아님). 수요 항목과 프로그램 목적의 대응은 분석자가 정함. 양쪽 모두 대응되는 8개 항목의 합을 100%로 환산(주민 대상 기록 20,808건의 {DEM['matched_record_share'] * 100:.0f}%가 해당)")
P._save(fig, f("r07_demand_vs_supply.png"))

json.dump(S, open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
for k, v in S.items():
    print(k, json.dumps(v, ensure_ascii=False, default=float)[:900])
