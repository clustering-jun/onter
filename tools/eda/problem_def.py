# -*- coding: utf-8 -*-
"""문제정의 분석: '복지 프로그램 추천(선정·배분)의 네 가지 문제'(근거·기준·도달·학습)를 단지 자료로 확인한다.

발표·대중용이라 그림은 16:9, 큰 글씨, 그림 하나에 메시지 하나. 제목 문장은 계산값에서 만든다.
각 함수는 그림을 저장하고 요약 수치(dict)를 돌려준다. 실행: run_problem.py
주의: 모든 관계는 상관(탐색)이며 원인을 증명하지 않는다. 프로그램 기록은 '공급의 기록'이지 필요의 정답이 아니다.
"""
import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from scipy.spatial.distance import pdist, squareform, cdist
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import KFold, cross_val_score

sys.path.insert(0, r"C:/Users/user/Desktop/2026 DRIVE/project/tools")
from community_nlp.figures import SURFACE, INK1, INK2, INK3, GRID, AXIS, CAT, GRAY_N, GRAY_U
from community_nlp.analysis_extra import spearman_boot
from community_nlp import taxonomy as TX
import eda_data as ED

ROOT = r"C:/Users/user/Desktop/2026 DRIVE/project/data/"
COMM = ROOT + "processed/community_nlp_2026_v1/"
HI = "#e34948"          # 강조(문제 지점) — 범주 팔레트 8번
SUPPLY_COLOR = dict(zip(ED.SUPPLY_ORDER, CAT[:5]))
rd = lambda p, **k: pd.read_csv(p, encoding="utf-8-sig", low_memory=False, **k)


# ───────── 공통 그림 틀(16:9, 큰 글씨) ─────────
def _fig(n=1, size=(11.0, 6.2), **kw):
    fig, axes = plt.subplots(1, n, figsize=size, dpi=170, **kw)
    fig.patch.set_facecolor(SURFACE)
    for ax in np.atleast_1d(axes):
        ax.set_facecolor(SURFACE)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=10, length=0)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
    return fig, axes


def _head(fig, tag, title, sub=None):
    fig.text(0.012, 0.995, tag, ha="left", va="top", fontsize=10.5, color=CAT[0], fontweight="bold")
    fig.text(0.012, 0.955, title, ha="left", va="top", fontsize=16, color=INK1, fontweight="bold")
    if sub:
        fig.text(0.012, 0.885, sub, ha="left", va="top", fontsize=10.5, color=INK2)


def _foot(fig, text):
    fig.text(0.012, -0.01, text, ha="left", va="top", fontsize=8.6, color=INK3)


def _save(fig, out, top=0.80):
    fig.subplots_adjust(top=top)
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)


def _pc(x, d=0):
    return f"{x * 100:.{d}f}%"


def _rho(x, y):
    r, p, lo, hi, n = spearman_boot(np.asarray(x, float), np.asarray(y, float), n_boot=1000)
    return dict(rho=r, p=p, lo=lo, hi=hi, n=n)


def fmt_rho(d):
    return f"ρ={d['rho']:+.2f} (95% 구간 {d['lo']:+.2f}~{d['hi']:+.2f}, n={d['n']})"


# ───────── 자료 ─────────
def load():
    d = ED.load()
    b = ED.build_base(d)
    m = rd(ROOT + "processed/complex_integrated_20261117_v1/data/complex_master.csv")
    add = [c for c in ["인구_60세이상_비율", "인구_80세이상_비율", "인구_20세미만_비율", "인구_60세이상_수"] if c not in b.columns]
    b = b.merge(m[["complex_id"] + add], on="complex_id", how="left")
    b["hd_per100"] = b["hd25_support"] / b["hd25_n_months"] / b["세대수"] * 100
    pa = rd(COMM + "program_analysis.csv")
    cf = rd(COMM + "complex_features.csv")
    sd = rd(COMM + "standard_program_dictionary.csv")
    ml = rd(COMM + "complex_std_matrix_long.csv")
    cand = rd(COMM + "complex_program_candidates.csv", usecols=["complex_id", "std_id", "complex_adopted", "peer_group_adoption_rate"])
    r = pa[pa["in_resident_scope"] == 1].copy()
    tgt = r["target_explicit"].fillna("") + "|" + r["target_type_default"].fillna("")
    r["t_eld"] = tgt.str.contains("ELD").astype(int)
    r["t_eld_explicit"] = r["target_explicit"].fillna("").str.contains("ELD").astype(int)
    r["t_any_explicit"] = r["target_explicit"].notna().astype(int)
    agg = r.groupby("complex_id").agg(n_res=("record_id", "size"), eld_share=("t_eld", "mean"), eld_explicit_share=("t_eld_explicit", "mean"))
    b = b.merge(agg, on="complex_id", how="left")
    b = b.merge(cf[["complex_id", "active_month_ratio", "active_months", "share_need_N2", "share_need_N3"]].rename(columns={"share_need_N2": "cf_N2", "share_need_N3": "cf_N3"}), on="complex_id", how="left")
    return dict(b=b, pa=pa, r=r, cf=cf, sd=sd, ml=ml, cand=cand, master=m)


# ───────── P01 배경: 단지마다 주민 구성이 다르다 ─────────
def p01_background(D, out):
    b, m = D["b"], D["master"]
    x = b["인구_60세이상_비율"].dropna() * 100
    fig, ax = _fig(1, size=(11, 5.6))
    bins = np.arange(0, 101, 5)
    cnt, edges = np.histogram(x, bins=bins)
    ax.bar(edges[:-1] + 2.5, cnt, width=4.4, color=CAT[0], edgecolor=SURFACE, linewidth=1.5)
    q1, med, q3 = np.percentile(x, [10, 50, 90])
    ax.axvline(med, color=INK1, linewidth=1.2, linestyle="--")
    ax.text(med + 1, cnt.max() * 0.98, f"중앙값 {med:.0f}%", fontsize=11, color=INK1, va="top")
    ax.annotate("", xy=(q1, cnt.max() * 1.1), xytext=(q3, cnt.max() * 1.1), arrowprops=dict(arrowstyle="<->", color=HI, lw=1.6))
    ax.text((q1 + q3) / 2, cnt.max() * 1.13, f"하위 10% 단지 {q1:.0f}% ↔ 상위 10% 단지 {q3:.0f}%", ha="center", fontsize=11, color=HI, fontweight="bold")
    ax.set_ylim(0, cnt.max() * 1.25)
    ax.set_xlim(0, 100)
    ax.set_xlabel("단지 주민 가운데 60세 이상 비율(%)", fontsize=11, color=INK2)
    ax.set_ylabel("단지 수", fontsize=11, color=INK2)
    hh, pop, old = m["세대수"].sum(), m["총거주인구"].sum(), m["인구_60세이상_수"].sum()
    _head(fig, "배경", f"같은 공공임대라도 단지마다 주민 구성이 크게 다르다",
          f"공단 관리 {len(m)}개 단지·{hh:,.0f}세대·주민 {pop:,.0f}명 가운데 60세 이상은 {_pc(old / pop)}. 단지별로는 {x.min():.0f}%에서 {x.max():.0f}%까지 퍼져 있다")
    _foot(fig, "자료: 단지 통합표(complex_integrated_20261117_v1) 인구 구성. 인구 자료가 있는 단지 기준")
    _save(fig, out)
    return dict(n=int(len(m)), households=float(hh), pop=float(pop), old_share=float(old / pop), p10=float(q1), med=float(med), p90=float(q3),
                min=float(x.min()), max=float(x.max()), n_with=int(len(x)))


# ───────── P02 근거: 고령 비율과 어르신 대상 프로그램 비중 ─────────
def p02_elderly(D, out):
    b = D["b"]
    x = b.dropna(subset=["인구_60세이상_비율", "eld_share"]).copy()
    x = x[x["n_res"] >= 15]
    fig, ax = _fig(1, size=(11, 6.0))
    for g in ED.SUPPLY_ORDER:
        s = x[x["supply_group"] == g]
        if len(s):
            ax.scatter(s["인구_60세이상_비율"] * 100, s["eld_share"] * 100, s=np.clip(s["세대수"] / 12, 14, 180), color=SUPPLY_COLOR[g],
                       alpha=0.8, edgecolor="#ffffff", linewidth=0.6, label=f"{g}({len(s)})")
    q = x["인구_60세이상_비율"].quantile([.25, .75])
    lo, hi = x[x["인구_60세이상_비율"] <= q.iloc[0]], x[x["인구_60세이상_비율"] >= q.iloc[1]]
    for grp, lab, xx in [(lo, "고령 비율 하위 25%", lo["인구_60세이상_비율"].median() * 100), (hi, "상위 25%", hi["인구_60세이상_비율"].median() * 100)]:
        yv = grp["eld_share"].median() * 100
        ax.plot([xx - 6, xx + 6], [yv, yv], color=INK1, linewidth=2.4)
        ax.text(xx, yv + 2.5, f"{lab}\n중앙값 {yv:.0f}%", ha="center", va="bottom", fontsize=10, color=INK1, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", facecolor=SURFACE, edgecolor="none", alpha=0.85))
    ax.set_xlabel("단지 주민 가운데 60세 이상 비율(%)", fontsize=11, color=INK2)
    ax.set_ylabel("어르신 대상 프로그램 비중(%)", fontsize=11, color=INK2)
    ax.legend(loc="upper right", frameon=True, facecolor=SURFACE, edgecolor="none", fontsize=9.5, labelcolor=INK2, title="공급유형(단지 수)", title_fontsize=9.5, ncol=2)
    ax.set_ylim(0, 100)
    r = _rho(x["인구_60세이상_비율"], x["eld_share"])
    rx = _rho(x["인구_60세이상_비율"], x["eld_explicit_share"])
    gap_pop = (hi["인구_60세이상_비율"].median() - lo["인구_60세이상_비율"].median()) * 100
    gap_prog = (hi["eld_share"].median() - lo["eld_share"].median()) * 100
    _head(fig, "문제 1 · 근거", f"고령 비율이 {gap_pop:.0f}%p 높은 단지도 어르신 프로그램 비중은 {gap_prog:.0f}%p만 높다",
          f"점 하나가 단지 하나(크기=세대수). 고령 비율과 어르신 대상 프로그램 비중의 관계는 약하다(순위상관 {r['rho']:+.2f}). 기록에 '어르신'을 명시한 비중만 보면 {rx['rho']:+.2f}")
    _foot(fig, "어르신 대상 = 기록 문구에 고령층이 명시됐거나 프로그램 유형의 기본 대상이 고령층. 주민 대상 기록 15건 이상 단지. 자료: 커뮤니티 NLP(2024-01~2026-06), 단지 통합표")
    _save(fig, out)
    return dict(rho=r, rho_explicit=rx, n=int(len(x)), lo_pop=float(lo["인구_60세이상_비율"].median()), hi_pop=float(hi["인구_60세이상_비율"].median()),
                lo_prog=float(lo["eld_share"].median()), hi_prog=float(hi["eld_share"].median()), gap_pop=float(gap_pop), gap_prog=float(gap_prog),
                q25=float(q.iloc[0]), q75=float(q.iloc[1]))


# ───────── P03 근거: 현장에서 드러난 필요(홈닥터) vs 프로그램 구성 ─────────
def p03_hd_vs_program(D, out):
    b = D["b"]
    x = b[(b["n_res"] >= 15) & b["hd25_의료지원_share"].notna()].copy()
    pairs = [("hd25_의료지원_share", "cf_N3", "홈닥터 지원 중 의료지원 비중(%)", "건강·돌봄 영역 프로그램 비중(%)", "의료"),
             ("hd25_경제지원_share", "cf_N2", "홈닥터 지원 중 경제지원 비중(%)", "생활·경제 영역 프로그램 비중(%)", "경제")]
    fig, axes = _fig(2, size=(12, 5.8))
    res = {}
    for ax, (a, c, xl, yl, key) in zip(axes, pairs):
        ax.scatter(x[a] * 100, x[c] * 100, s=26, color=CAT[0], alpha=0.65, edgecolor="#ffffff", linewidth=0.5)
        r = _rho(x[a], x[c])
        res[key] = r
        ax.set_xlabel(xl, fontsize=10.5, color=INK2)
        ax.set_ylabel(yl, fontsize=10.5, color=INK2)
        ax.text(0.98, 0.96, f"순위상관 {r['rho']:+.2f}\n95% 구간 {r['lo']:+.2f}~{r['hi']:+.2f}", transform=ax.transAxes, ha="right", va="top", fontsize=10.5, color=INK1,
                bbox=dict(boxstyle="round,pad=0.4", facecolor=SURFACE, edgecolor=AXIS))
    _head(fig, "문제 1 · 근거", "홈닥터가 확인한 필요와 그 단지의 프로그램 구성은 거의 따로 움직인다",
          f"왼쪽: 의료지원이 많은 단지라고 건강·돌봄 프로그램이 많지 않다. 오른쪽: 경제지원도 마찬가지. 점 하나가 단지 하나(n={len(x)})")
    _foot(fig, "홈닥터 = 2025년 단지별 지원 내용(생활·가사·의료·경제) 구성비. 프로그램 영역 = NLP가 분류한 필요 영역(N2 생활과 경제, N3 건강과 돌봄) 비중. 상관이며 원인 관계가 아니다")
    _save(fig, out, top=0.78)
    return dict(n=int(len(x)), **{f"rho_{k}": v for k, v in res.items()})


# ───────── P04 근거: 무엇이 프로그램 구성을 설명하나 ─────────
def p04_what_explains(D, out):
    b = D["b"]
    fam = [c for c in b.columns if c.startswith("share_family_F") and c != "share_family_F99"]
    xx = b[(b["n_res"] >= 15)].dropna(subset=["인구_60세이상_비율", "인구_20세미만_비율", "입주기준경과년수", "평형_전용면적가중평균_㎡"]).copy()
    Z = xx[["인구_60세이상_비율", "인구_20세미만_비율", "log_households", "입주기준경과년수", "평형_전용면적가중평균_㎡"]].apply(lambda s: (s - s.mean()) / s.std()).values
    Xd = np.column_stack([Z, pd.get_dummies(xx["supply_group"]).values.astype(float)])
    Xb = pd.get_dummies(xx["지사명"]).values.astype(float)
    kf = KFold(5, shuffle=True, random_state=7)
    rows = []
    for f in fam:
        y = xx[f].fillna(0).values
        ridge = lambda: RidgeCV(alphas=np.logspace(-3, 3, 13))
        rows.append(dict(family=f.replace("share_family_", ""), label=TX.FAMILIES[f.replace("share_family_", "")],
                         r2_resident=cross_val_score(ridge(), Xd, y, cv=kf, scoring="r2").mean(),
                         r2_branch=cross_val_score(ridge(), Xb, y, cv=kf, scoring="r2").mean(),
                         r2_both=cross_val_score(ridge(), np.column_stack([Xd, Xb]), y, cv=kf, scoring="r2").mean()))
    t = pd.DataFrame(rows)
    # 쌍 비교: 주민 구성 차이 5분위별 프로그램 구성 차이
    F = xx[fam].fillna(0).values
    dmix = pdist(F, "braycurtis")
    ddem = pdist(Z)
    same = squareform(np.equal.outer(xx["지사명"].values, xx["지사명"].values).astype(int), checks=False)
    qd = pd.qcut(ddem, 5, labels=False)
    curve = pd.DataFrame([dict(q=k + 1, all=np.median(dmix[qd == k]), same=np.median(dmix[(qd == k) & (same == 1)]), diff=np.median(dmix[(qd == k) & (same == 0)])) for k in range(5)])
    mantel = stats.spearmanr(dmix, ddem)[0]
    # 그림
    fig, axes = _fig(2, size=(12.5, 6.0), gridspec_kw=dict(width_ratios=[1.25, 1]))
    ax = axes[0]
    tt = t.sort_values("r2_resident")
    yy = np.arange(len(tt))
    ax.barh(yy + 0.2, tt["r2_resident"].clip(lower=0) * 100, height=0.38, color=CAT[0], label="주민·단지 여건(고령·아동 비율·규모·연식·면적·공급유형)")
    ax.barh(yy - 0.2, tt["r2_branch"].clip(lower=0) * 100, height=0.38, color=CAT[1], label="관할 지사")
    ax.set_yticks(yy); ax.set_yticklabels(tt["label"], fontsize=9.5, color=INK1)
    ax.set_xlabel("설명되는 몫(교차검증 R², %, 0 미만은 0으로 표시)", fontsize=10, color=INK2)
    ax.grid(axis="x", color=GRID); ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK2)
    ax.set_xlim(0, max(20, float(t[["r2_resident", "r2_branch"]].max().max() * 100 + 4)))
    ax2 = axes[1]
    ax2.plot(curve["q"], curve["same"] * 100, marker="o", color=CAT[1], linewidth=2, label="같은 지사 단지끼리")
    ax2.plot(curve["q"], curve["diff"] * 100, marker="o", color=CAT[0], linewidth=2, label="다른 지사 단지끼리")
    ax2.set_xticks(range(1, 6)); ax2.set_xticklabels(["가장\n비슷", "2", "3", "4", "가장\n다름"], fontsize=9.5)
    ax2.set_xlabel("두 단지의 주민·단지 여건 차이(5분위)", fontsize=10, color=INK2)
    ax2.set_ylabel("두 단지의 프로그램 구성 차이(%)", fontsize=10, color=INK2)
    ax2.set_ylim(0, 70)
    ax2.legend(loc="lower right", frameon=False, fontsize=9.5, labelcolor=INK2)
    n_low = int((t["r2_resident"] < 0.10).sum())
    _head(fig, "문제 1 · 근거", f"프로그램 구성은 주민 여건으로도, 관할 지사로도 거의 설명되지 않는다",
          f"왼쪽: 15개 영역 중 {n_low}개에서 주민 여건의 설명력이 10% 미만이고, 조금이라도 설명되는 영역은 오히려 지사 쪽이 크다. 오른쪽: 여건이 가장 비슷한 단지끼리도 구성이 {curve['all'].iloc[0] * 100:.0f}% 다르다")
    _foot(fig, "프로그램 구성 = 단지별 15개 영역 비중. 구성 차이 = Bray–Curtis 거리(0%=같음, 100%=겹침 없음). 교차검증 R²는 5겹 릿지 회귀. 주민 대상 기록 15건 이상 단지")
    _save(fig, out, top=0.78)
    return dict(table=t, curve=curve, mantel=float(mantel), n=int(len(xx)), n_low=n_low, mean_res=float(t["r2_resident"].mean()), mean_branch=float(t["r2_branch"].mean()),
                max_res=(t.loc[t["r2_resident"].idxmax(), "label"], float(t["r2_resident"].max())), max_branch=(t.loc[t["r2_branch"].idxmax(), "label"], float(t["r2_branch"].max())),
                d_sim=float(curve["all"].iloc[0]), d_far=float(curve["all"].iloc[-1]), d_same=float(np.median(dmix[same == 1])), d_diff=float(np.median(dmix[same == 0])))


# ───────── P05 기준: 규모가 클수록 세대당 프로그램이 적다 ─────────
def _szl(s):
    return s.replace(" 이상", "세대 이상").replace(" 미만", "세대 미만") if ("이상" in s or "미만" in s) else s + "세대"


def p05_size(D, out):
    b = D["b"]
    x = b[b["n_res"].notna() & (b["세대수"] > 0)].copy()
    x["per1000"] = x["n_res"] / 2.5 / x["세대수"] * 1000
    x["per_year"] = x["n_res"] / 2.5
    slope, icpt, rv, pv, se = stats.linregress(np.log(x["세대수"]), np.log(x["per_year"].clip(lower=0.4)))
    bins = [0, 300, 500, 1000, 1500, 10000]
    labs = ["300 미만", "300~499", "500~999", "1,000~1,499", "1,500 이상"]
    x["size_bin"] = pd.cut(x["세대수"], bins=bins, labels=labs, right=False)
    g = x.groupby("size_bin", observed=True).agg(n=("complex_id", "size"), per1000=("per1000", "median"), per_year=("per_year", "median"), hh=("세대수", "median"))
    fig, axes = _fig(2, size=(12.5, 5.8))
    ax = axes[0]
    ax.bar(range(len(g)), g["per_year"], color=CAT[0], width=0.62)
    for i, (v, n) in enumerate(zip(g["per_year"], g["n"])):
        ax.text(i, v + 0.5, f"{v:.0f}건", ha="center", fontsize=10.5, color=INK1)
    ax.set_xticks(range(len(g))); ax.set_xticklabels([f"{l}\n({n}곳)" for l, n in zip(g.index, g["n"])], fontsize=9.5)
    ax.set_title("단지당 연간 주민 프로그램 기록(중앙값)", fontsize=11, color=INK1, loc="left")
    ax.set_xlabel("세대수 구간", fontsize=10, color=INK2)
    ax2 = axes[1]
    pk = int(np.argmax(g["per1000"].values))
    ax2.bar(range(len(g)), g["per1000"], color=[CAT[0] if i == pk else "#9ec3ef" for i in range(len(g))], width=0.62)
    for i, v in enumerate(g["per1000"]):
        ax2.text(i, v + 0.8, f"{v:.0f}건", ha="center", fontsize=10.5, color=INK1, fontweight=("bold" if i == pk else "normal"))
    ax2.set_xticks(range(len(g))); ax2.set_xticklabels(list(g.index), fontsize=9.5)
    ax2.set_title("1,000세대당 연간 기록(중앙값)", fontsize=11, color=INK1, loc="left")
    ax2.set_xlabel("세대수 구간", fontsize=10, color=INK2)
    a, z = pk, len(g) - 1
    hh_ratio = g["hh"].iloc[z] / g["hh"].iloc[a]
    rec_ratio = g["per_year"].iloc[z] / g["per_year"].iloc[a]
    ratio = g["per1000"].iloc[a] / g["per1000"].iloc[z]
    _head(fig, "문제 2 · 기준", f"세대수가 {hh_ratio:.1f}배인 단지도 프로그램은 {rec_ratio:.1f}배: 큰 단지일수록 세대당 기회가 적다",
          f"{_szl(g.index[a])} 단지와 {_szl(g.index[z])} 단지의 중앙값 비교. 1,000세대당으로는 {ratio:.1f}배 차이. 300세대 미만의 작은 단지도 세대당 기록이 적다({g['per1000'].iloc[0]:.0f}건)")
    _foot(fig, "주민 대상 프로그램 기록(2024-01~2026-06, 30개월)을 연간으로 환산. 기록 건수는 공급의 양이며, 프로그램 규모·참여 인원은 반영하지 않는다")
    _save(fig, out, top=0.78)
    return dict(table=g.reset_index(), slope=float(slope), slope_se=float(se), ratio=float(ratio), n=int(len(x)), hh_ratio=float(hh_ratio), rec_ratio=float(rec_ratio),
                peak_bin=str(g.index[a]), last_bin=str(g.index[z]), peak=float(g["per1000"].iloc[a]), large=float(g["per1000"].iloc[z]), smallest=float(g["per1000"].iloc[0]),
                py_peak=float(g["per_year"].iloc[a]), py_large=float(g["per_year"].iloc[z]), hh_peak=float(g["hh"].iloc[a]), hh_large=float(g["hh"].iloc[z]))


# ───────── P06 기준: 필요-공급 4분면 ─────────
def p06_need_supply(D, out):
    b = D["b"]
    x = b[(b["n_res"].notna()) & b["인구_60세이상_비율"].notna() & b["hd_per100"].notna()].copy()
    x["need"] = x[["인구_60세이상_비율", "hd_per100"]].rank(pct=True).mean(axis=1)
    x["need_pct"] = x["need"].rank(pct=True) * 100
    x["supply"] = x["n_res"] / 2.5 / x["세대수"] * 1000
    x["supply_pct"] = x["supply"].rank(pct=True) * 100
    hi_need, lo_sup = x["need_pct"] >= 200 / 3, x["supply_pct"] <= 100 / 3
    lo_need, hi_sup = x["need_pct"] <= 100 / 3, x["supply_pct"] >= 200 / 3
    mis = x[hi_need & lo_sup]
    inv = x[lo_need & hi_sup]
    r = _rho(x["need"], x["supply"])
    fig, ax = _fig(1, size=(11, 6.6))
    ax.grid(False)
    ax.axvspan(200 / 3, 100, ymin=0, ymax=1 / 3, color=HI, alpha=0.08, zorder=0)
    ax.axvspan(0, 100 / 3, ymin=2 / 3, ymax=1, color=CAT[0], alpha=0.06, zorder=0)
    for v in (100 / 3, 200 / 3):
        ax.axvline(v, color=GRID, linewidth=1); ax.axhline(v, color=GRID, linewidth=1)
    other = x[~(hi_need & lo_sup)]
    ax.scatter(other["need_pct"], other["supply_pct"], s=24, color=GRAY_N, alpha=0.8, edgecolor="#ffffff", linewidth=0.4)
    ax.scatter(mis["need_pct"], mis["supply_pct"], s=46, color=HI, alpha=0.95, edgecolor="#ffffff", linewidth=0.6)
    ax.text(99, 34.5, f"필요는 크고 프로그램은 적은 단지 {len(mis)}곳 ({_pc(len(mis) / len(x))})", ha="right", va="bottom", fontsize=12, color=HI, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.25", facecolor=SURFACE, edgecolor="none", alpha=0.9))
    ax.text(1, 98, f"필요는 작고 프로그램은 많은 단지 {len(inv)}곳", ha="left", va="top", fontsize=10.5, color=CAT[0], fontweight="bold")
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.set_xlabel("필요 지수 순위(백분위): 60세 이상 비율 + 홈닥터 지원 강도", fontsize=10.5, color=INK2)
    ax.set_ylabel("프로그램 공급 순위(백분위): 1,000세대당 연간 기록", fontsize=10.5, color=INK2)
    exp = len(x) / 9
    _head(fig, "문제 2 · 기준", f"필요가 큰 단지라고 프로그램이 뚜렷하게 많지 않다: {len(mis)}곳은 '필요 상위·공급 하위'",
          f"필요와 공급의 관계는 약하다(순위상관 {r['rho']:+.2f}, 95% 구간 {r['lo']:+.2f}~{r['hi']:+.2f}). 아무 관계가 없어도 한 칸에 약 {exp:.0f}곳이 들어가니, 실제 {len(mis)}곳은 무작위와 큰 차이가 없다")
    _foot(fig, "필요 지수는 보유 자료로 만든 대리 지표다(60세 이상 비율과 2025년 100세대당 홈닥터 지원 건수의 백분위 평균). 정답 필요가 아니며, 공급은 기록 건수 기준. n=" + str(len(x)))
    _save(fig, out, top=0.82)
    cols = ["complex_id", "단지명", "지사명", "supply_group", "세대수", "인구_60세이상_비율", "hd_per100", "supply", "need_pct", "supply_pct"]
    return dict(rho=r, n=int(len(x)), n_mis=int(len(mis)), n_inv=int(len(inv)), expected=float(exp),
                mis_table=mis[cols].sort_values("need_pct", ascending=False), all_table=x[cols])


# ───────── P07 도달: 기록 단위·대상 명시 ─────────
def p07_reach_unit(D, out):
    r = D["r"]
    items = [("단지 전체 대상 행사·프로그램", r["support_unit_complex_wide"].mean()),
             ("일부 가구에 직접 지원(방문·물품 등)", r["support_unit_household"].mean()),
             ("안부·관계 접촉(전화·방문 확인)", r["support_unit_contact"].mean()),
             ("기록에 대상 집단을 적은 비율", r["t_any_explicit"].mean())]
    fig, ax = _fig(1, size=(11, 5.2))
    ax.grid(axis="y", visible=False); ax.grid(axis="x", color=GRID)
    labs = [i[0] for i in items][::-1]; vals = [i[1] * 100 for i in items][::-1]
    cols = [CAT[3], CAT[1], CAT[1], CAT[0]]
    ax.barh(labs, vals, color=cols, height=0.55)
    for yv, v in enumerate(vals):
        ax.text(v + 1, yv, f"{v:.0f}%", va="center", fontsize=12, color=INK1, fontweight="bold")
    ax.set_xlim(0, 105)
    ax.tick_params(axis="y", labelsize=11, colors=INK1)
    ax.set_xlabel(f"주민 대상 기록 {len(r):,}건 중 비율(%) — 지원 단위는 겹칠 수 있음", fontsize=10, color=INK2)
    _head(fig, "문제 3 · 도달", f"기록의 {_pc(items[0][1])}는 단지 전체 행사이고, 누구를 위한 것인지 적힌 기록은 {_pc(items[3][1])}뿐이다",
          "행사는 '열렸다'는 기록은 남지만 어떤 가구가 참여했고 누가 빠졌는지는 남지 않는다")
    _foot(fig, "지원 단위·대상은 NLP가 활동 내용에서 판정(silver label). 대상 명시 = 활동 문구에 고령층·장애인·아동 등 대상이 적힌 기록")
    _save(fig, out, top=0.80)
    return dict(n=int(len(r)), complex_wide=float(items[0][1]), household=float(items[1][1]), contact=float(items[2][1]), explicit=float(items[3][1]))


# ───────── P08 도달: 활동이 없는 달 ─────────
def p08_reach_months(D, out):
    r = D["r"]
    mon = pd.to_datetime(r["start_date"]).dt.to_period("M")
    keep = (mon >= pd.Period("2024-01", "M")) & (mon <= pd.Period("2026-06", "M"))
    m = mon[keep].groupby(r.loc[keep, "complex_id"]).nunique()
    fig, ax = _fig(1, size=(11, 5.4))
    bins = np.arange(0, 32, 1)
    cnt, _ = np.histogram(m, bins=bins)
    cols = [HI if v < 15 else CAT[0] for v in bins[:-1]]
    ax.bar(bins[:-1], cnt, width=0.8, color=cols)
    med = float(np.median(m))
    ax.axvline(med, color=INK1, linestyle="--", linewidth=1.2)
    ax.text(med - 0.5, cnt.max() * 0.95, f"중앙값 {med:.0f}개월", ha="right", fontsize=11, color=INK1)
    n_half = int((m < 15).sum()); n_full = int((m == 30).sum())
    ax.text(7, cnt.max() * 0.6, f"30개월 중 절반도 안 되는 달에만\n프로그램이 있던 단지 {n_half}곳", ha="center", fontsize=11, color=HI, fontweight="bold")
    ax.set_xlabel("2024-01~2026-06(30개월) 중 주민 대상 기록이 하나라도 있는 달 수", fontsize=10.5, color=INK2)
    ax.set_ylabel("단지 수", fontsize=10.5, color=INK2)
    _head(fig, "문제 3 · 도달", f"매달 프로그램이 이어진 단지는 {n_full}곳({_pc(n_full / len(m))})이고, 중앙값 단지는 30개월 중 {30 - med:.0f}개월이 비었다",
          "프로그램이 없는 달에는 주민이 닿을 통로도 없다. 활동이 몇 달씩 끊기는 단지가 적지 않다")
    _foot(fig, f"주민 대상 기록이 있는 {len(m)}개 단지. 기록 누락과 실제 미운영을 구분할 수 없어 '기록이 없는 달'로 읽는다. 2026년 상반기는 보고 지연 가능성이 있다")
    _save(fig, out, top=0.80)
    return dict(n=int(len(m)), median=med, n_half=n_half, n_full=n_full, mean=float(m.mean()))


# ───────── P09 학습: 같은 프로그램, 수많은 이름 ─────────
def p09_names(D, out):
    r, sd = D["r"], D["sd"]
    n_std = int(r["std_id"].nunique()); n_titles = int(r["title_norm"].nunique()); n_raw = int(r["program_name_raw"].nunique())
    top = sd[sd["scope"] == "PROGRAM"].sort_values("n_records", ascending=False).head(12).iloc[::-1]
    fig, ax = _fig(1, size=(11.5, 6.2))
    ax.grid(axis="y", visible=False); ax.grid(axis="x", color=GRID)
    ax.barh(top["std_name"].map(lambda s: s if len(s) <= 24 else s[:23] + "…"), top["alias_distinct_titles"], color=CAT[0], height=0.6, label="서로 다른 제목 수")
    for yv, (v, n) in enumerate(zip(top["alias_distinct_titles"], top["n_records"])):
        ax.text(v + 6, yv, f"제목 {v}가지 · 기록 {n}건", va="center", fontsize=10, color=INK1)
    ax.set_xlim(0, top["alias_distinct_titles"].max() * 1.42)
    ax.tick_params(axis="y", labelsize=10.5, colors=INK1)
    ax.set_xlabel("같은 프로그램을 적은 서로 다른 제목 수(띄어쓰기·기호를 정리한 뒤)", fontsize=10.5, color=INK2)
    _head(fig, "문제 4 · 학습", f"표준 프로그램 {n_std}종이 제목 {n_titles:,}가지로 적혀 있다",
          f"같은 '찾아가는 공연'도 단지마다 다른 이름으로 기록된다(원문 제목은 {n_raw:,}가지). 이대로는 단지끼리 무엇이 잘 됐는지 비교할 수 없다")
    _foot(fig, "주민 대상 기록 기준. 표준 프로그램 분류는 규칙 + LLM 라벨러(silver label, 독립 표본 일치 87%). 상위 12개 표준 프로그램")
    _save(fig, out, top=0.80)
    return dict(n_std=n_std, n_titles=n_titles, n_raw=n_raw, per_std=float(n_titles / n_std),
                top=[(a, int(b_), int(c)) for a, b_, c in zip(top["std_name"][::-1], top["alias_distinct_titles"][::-1], top["n_records"][::-1])])


# ───────── P10 학습: 기록이 알려주는 것 vs 알려주지 않는 것 ─────────
CHECK_ITEMS = [
    ("있음", "언제·어디서 했나(날짜·장소)", "start_date"),
    ("있음", "무엇을 했나(제목·활동 내용)", "activity_content_raw"),
    ("있음", "몇 번 했나(활동 횟수)", "activity_count"),
    ("있음", "몇 명이 왔나(참여 인원 합계)", "participants_total"),
    ("있음", "누구와 했나(참여 기관 수·유형)", "org_count_raw"),
    ("없음", "서로 다른 주민 몇 명에게 닿았나(고유 참여자)", None),
    ("없음", "꼭 필요했던 가구가 왔나(대상 가구 도달)", None),
    ("없음", "참여 후 무엇이 달라졌나(만족·변화)", None),
    ("없음", "왜 오지 못했나(미참여 사유)", None),
    ("없음", "실제 든 비용(집행액)", None),
]


def p10_record_fields(D, out):
    pa = D["pa"]
    fill = {}
    for st, lab, col in CHECK_ITEMS:
        if col:
            s = pa[col]
            fill[lab] = float((s.notna() & (s.astype(str).str.strip() != "")).mean())
    fig, ax = plt.subplots(figsize=(11, 6.0), dpi=170)
    fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE); ax.axis("off")
    have = [i for i in CHECK_ITEMS if i[0] == "있음"]; miss = [i for i in CHECK_ITEMS if i[0] == "없음"]
    ax.text(0.02, 0.93, "기록에 있다", fontsize=13, color=CAT[2], fontweight="bold", transform=ax.transAxes)
    ax.text(0.53, 0.93, "기록에 없다", fontsize=13, color=HI, fontweight="bold", transform=ax.transAxes)
    for i, (_, lab, col) in enumerate(have):
        y = 0.80 - i * 0.15
        ax.text(0.02, y, r"$\checkmark$", fontsize=17, color=CAT[2], transform=ax.transAxes, va="center")
        ax.text(0.06, y, lab, fontsize=11.5, color=INK1, transform=ax.transAxes, va="center")
        ax.text(0.06, y - 0.055, f"채워진 비율 {fill[lab] * 100:.0f}%", fontsize=9.5, color=INK2, transform=ax.transAxes, va="center")
    for i, (_, lab, _c) in enumerate(miss):
        y = 0.80 - i * 0.15
        ax.text(0.53, y, r"$\times$", fontsize=19, color=HI, transform=ax.transAxes, va="center")
        ax.text(0.57, y, lab, fontsize=11.5, color=INK1, transform=ax.transAxes, va="center")
    fig.text(0.012, 0.995, "문제 4 · 학습", ha="left", va="top", fontsize=10.5, color=CAT[0], fontweight="bold")
    fig.text(0.012, 0.955, "기록은 '무엇을 했나'를 남기지만 '닿았나, 도움이 됐나'는 남기지 않는다", ha="left", va="top", fontsize=16, color=INK1, fontweight="bold")
    fig.text(0.012, 0.885, f"커뮤니티 활동 원자료 {len(pa):,}건의 항목 구성. 오른쪽 항목이 없으니 다음 선정 때 참고할 결과가 쌓이지 않는다", ha="left", va="top", fontsize=10.5, color=INK2)
    _foot(fig, "참여 인원은 행사별 합계라 같은 주민이 여러 번 셀 수 있다(고유 인원 아님). 비용은 원자료에 구분만 있고 금액이 없다(분석의 비용은 모델 추정치)")
    fig.subplots_adjust(top=0.84)
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    return dict(fill=fill, n=int(len(pa)))


# ───────── P11 학습: 활동량과 만족도 ─────────
def p11_volume_vs_satisfaction(D, out):
    b = D["b"]
    x = b[(b["n_total"] >= 30) & b["welfare_satisfaction"].notna() & b["n_res"].notna()].copy()
    x["per1000"] = x["n_res"] / 2.5 / x["세대수"] * 1000
    pairs = [("per1000", "1,000세대당 연간 프로그램 기록", "volume"), ("participation_per_100hh_year", "100세대당 연간 참여 인원(기록)", "participation"), ("std_richness", "운영한 프로그램 종류 수", "variety")]
    fig, axes = _fig(3, size=(13, 5.2), sharey=True)
    res = {}
    for ax, (c, lab, k) in zip(axes, pairs):
        ax.scatter(x[c], x["welfare_satisfaction"], s=28, color=CAT[0], alpha=0.7, edgecolor="#ffffff", linewidth=0.5)
        rr = _rho(x[c], x["welfare_satisfaction"])
        res[k] = rr
        ax.set_xlabel(lab, fontsize=10, color=INK2)
        ax.text(0.97, 0.05, f"ρ={rr['rho']:+.2f}\n({rr['lo']:+.2f}~{rr['hi']:+.2f})", transform=ax.transAxes, ha="right", va="bottom", fontsize=10.5, color=INK1,
                bbox=dict(boxstyle="round,pad=0.35", facecolor=SURFACE, edgecolor=AXIS))
    axes[0].set_ylabel("해피콜 복지 만족도(점)", fontsize=10.5, color=INK2)
    _head(fig, "문제 4 · 학습", "프로그램을 많이·다양하게 해도 주민의 복지 만족도와는 거의 관계가 없다",
          f"2025 해피콜 응답 30명 이상 {len(x)}개 단지. 세 지표 모두 만족도와의 관계가 0 근처다. 활동량을 세는 것만으로는 무엇이 효과적인지 알 수 없다")
    _foot(fig, "해피콜 복지 만족도는 관리소 단위 설문 점수(1:1 연결 단지만). 상관 분석이며, 만족도는 프로그램 외의 요인에도 영향을 받는다")
    _save(fig, out, top=0.78)
    return dict(n=int(len(x)), **{f"rho_{k}": v for k, v in res.items()})


# ───────── P12 기회: 비슷한 단지는 하는데 이 단지는 안 하는 프로그램 ─────────
def demo_neighbors(b, k=10):
    x = b[b["n_res"] >= 15].dropna(subset=["인구_60세이상_비율", "인구_20세미만_비율", "입주기준경과년수", "평형_전용면적가중평균_㎡"]).copy()
    Z = x[["인구_60세이상_비율", "인구_20세미만_비율", "log_households", "입주기준경과년수", "평형_전용면적가중평균_㎡"]].apply(lambda s: (s - s.mean()) / s.std()).values
    Z = np.column_stack([Z, pd.get_dummies(x["supply_group"]).values.astype(float) * 1.5])
    Dm = cdist(Z, Z)
    np.fill_diagonal(Dm, np.inf)
    nn = np.argsort(Dm, axis=1)[:, :k]
    ids = x["complex_id"].values
    return {ids[i]: list(ids[nn[i]]) for i in range(len(ids))}


def p12_peer_gap(D, out, example_ids=("KOH_211", "KOH_212", "KOH_291", "KOH_91")):
    b, ml, sd = D["b"], D["ml"], D["sd"]
    rec = set(sd.loc[(sd["recommendable"] == 1) & (sd["scope"] == "PROGRAM"), "std_id"])
    nb = demo_neighbors(b)
    adopted = ml[ml["n_records"] > 0].groupby("complex_id")["std_id"].apply(set).to_dict()
    name = dict(zip(sd["std_id"], sd["std_name"]))
    rows, ex = [], {}
    for cid, nbs in nb.items():
        own = adopted.get(cid, set())
        share = pd.Series([s for n_ in nbs for s in adopted.get(n_, set()) if s in rec]).value_counts() / len(nbs)
        gap = share[(share >= 0.5) & (~share.index.isin(own))]
        rows.append(dict(complex_id=cid, n_gap=int(len(gap)), n_own=int(len(own & rec))))
        if cid in example_ids:
            ex[cid] = [(name[s], float(v)) for s, v in gap.sort_values(ascending=False).head(6).items()]
    t = pd.DataFrame(rows)
    nm = dict(zip(b["complex_id"], b["단지명"]))
    fig, axes = _fig(2, size=(13, 6.0), gridspec_kw=dict(width_ratios=[1, 1.15]))
    ax = axes[0]
    cnt = t["n_gap"].value_counts().sort_index()
    ax.bar(cnt.index, cnt.values, color=CAT[0], width=0.8)
    med = float(t["n_gap"].median())
    ax.axvline(med, color=INK1, linestyle="--", linewidth=1.2)
    ax.text(med + 0.4, cnt.max() * 1.06, f"중앙값 {med:.0f}개", fontsize=11, color=INK1, va="bottom")
    ax.set_ylim(0, cnt.max() * 1.18)
    ax.set_xlabel("비슷한 단지 10곳 중 절반 이상이 하는데\n이 단지는 30개월간 한 번도 안 한 프로그램 수", fontsize=10, color=INK2)
    ax.set_ylabel("단지 수", fontsize=10.5, color=INK2)
    ax2 = axes[1]
    ax2.axis("off")
    ax2.text(0, 1.0, "현장 실증 단지의 예", fontsize=12, color=INK1, fontweight="bold", transform=ax2.transAxes, va="top")
    y = 0.90
    for cid in example_ids:
        if cid not in ex:
            continue
        ax2.text(0, y, f"{nm.get(cid, cid)}  ·  후보 {int(t.loc[t.complex_id == cid, 'n_gap'].iloc[0])}개 중 상위 3개", fontsize=11, color=CAT[0], fontweight="bold", transform=ax2.transAxes, va="top")
        y -= 0.065
        for s, v in ex[cid][:3]:
            ax2.text(0.03, y, f"· {s if len(s) <= 26 else s[:25] + '…'}  (이웃 {v * 10:.0f}/10곳)", fontsize=10, color=INK1, transform=ax2.transAxes, va="top")
            y -= 0.058
        y -= 0.02
    n0 = int((t["n_gap"] == 0).sum())
    _head(fig, "기회", f"주민 구성이 비슷한 이웃 단지들이 흔히 하는 프로그램이, 단지마다 중앙값 {med:.0f}개씩 빠져 있다",
          f"{len(t)}개 단지 가운데 이런 후보가 하나도 없는 단지는 {n0}곳. 이웃 단지의 경험을 데이터로 옮기면 바로 검토할 후보 목록이 된다")
    _foot(fig, "비슷한 단지 = 60세 이상·20세 미만 비율, 세대수, 연식, 전용면적, 공급유형이 가장 가까운 10곳. 후보는 '검토 대상'이지 필요의 정답이 아니다(현장 확인 필요). 주민 대상 기록 15건 이상 단지")
    _save(fig, out, top=0.78)
    t["단지명"] = t["complex_id"].map(nm)
    return dict(table=t, median=med, n=int(len(t)), n0=n0, examples={nm.get(k, k): v for k, v in ex.items()},
                ex_counts={nm.get(c, c): int(t.loc[t.complex_id == c, "n_gap"].iloc[0]) for c in example_ids if c in set(t.complex_id)},
                p75=float(t["n_gap"].quantile(.75)), neighbors=nb)


def concentration(D):
    sd = D["sd"]
    s = sd[sd["scope"] == "PROGRAM"].sort_values("n_records", ascending=False)
    tot = s["n_records"].sum()
    return dict(n_std=int((s["n_records"] > 0).sum()), top10=float(s["n_records"].head(10).sum() / tot), top20=float(s["n_records"].head(20).sum() / tot),
                median_adopt=float(s["adoption_rate"].median()))
