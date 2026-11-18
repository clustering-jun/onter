# -*- coding: utf-8 -*-
"""통합 데이터 EDA: 분석 계산 + 그림. 각 함수는 그림을 저장하고 요약 수치(dict)를 돌려준다(보고서 문장은 이 수치에서 만든다)."""
import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
from community_nlp.figures import SURFACE, INK1, INK2, INK3, GRID, AXIS, CAT, SEQ, GRAY_N, _base, _title, _save
from community_nlp.figures_extra import DIV, _short
from community_nlp.analysis_extra import spearman_boot, holm, gini
from community_nlp import josa as J
from community_nlp import taxonomy as TX
import eda_data as ED

SG_COLOR = dict(zip(ED.SUPPLY_ORDER, CAT[:5]))
HD = ED.HD_COLS


def _pc(x, d=0):
    return f"{x * 100:.{d}f}%"


def _fmt_p(p):
    return "p<0.001" if p < 0.001 else f"p={p:.3f}"


def _sp(x, y):
    m = x.notna() & y.notna()
    r, p, lo, hi, n = spearman_boot(x[m].values, y[m].values, n_boot=800)
    return r, p, lo, hi, n


def cramers_v(a, b):
    t = pd.crosstab(a, b)
    chi2 = stats.chi2_contingency(t, correction=False)[0]
    n = t.values.sum()
    return float(np.sqrt(chi2 / (n * (min(t.shape) - 1)))), t


# ───────────── 01 자료 목록·결측 ─────────────
def fig_inventory(d, out):
    cd = d["cd"]
    g = cd.groupby("출처자료").agg(n=("컬럼명", "size"), n_missing=("결측수", lambda s: int((s > 0).sum()))).sort_values("n")
    fig, ax = _base((8.6, 5.6))
    ax.barh(g.index, g["n"], height=0.62, color=CAT[0], label="전체 열")
    ax.barh(g.index, g["n_missing"], height=0.62, color=CAT[1], label="결측이 있는 열")
    for y, (n, m) in enumerate(zip(g["n"], g["n_missing"])):
        ax.text(n + 2, y, f"{n}개 (결측 있는 열 {m})", va="center", fontsize=8, color=INK1)
    ax.set_xlim(0, g["n"].max() * 1.35)
    ax.legend(loc="lower right", frameon=False, fontsize=8.5, labelcolor=INK2)
    big = g["n"].idxmax()
    _title(fig, f"통합표 {len(cd)}개 열의 {_pc(g.loc[big, 'n'] / len(cd))}가 {J.q(big)} 출처다", f"출처자료별 열 수. 주황은 그 가운데 결측이 있는 열 수(단지통합 컬럼명세 기준)")
    _save(fig, out)
    return dict(n_cols=int(len(cd)), top_source=big, top_n=int(g.loc[big, "n"]), n_sources=int(len(g)), n_with_missing=int((cd["결측수"] > 0).sum()))


def fig_missing(d, out):
    cd = d["cd"]
    m = cd[cd["결측률"] > 0].sort_values("결측률", ascending=False).head(25).iloc[::-1]
    fig, ax = _base((8.8, 7.0))
    ax.barh([_short(c, 30) for c in m["컬럼명"]], m["결측률"] * 100, height=0.62, color=CAT[0])
    for y, v in enumerate(m["결측률"] * 100):
        ax.text(v + 0.6, y, f"{v:.0f}%", va="center", fontsize=7.8, color=INK1)
    ax.set_xlim(0, 105)
    ax.tick_params(axis="y", labelsize=7.6)
    n0 = int((cd["결측률"] > 0).sum())
    n50 = int((cd["결측률"] >= 0.5).sum())
    _title(fig, f"결측이 있는 열은 {n0}개이고 절반 이상 비어 있는 열은 {n50}개다", "결측률 상위 25개 열(%). 결측은 0이 아니라 '해당 없음·미관측'으로 해석해야 하는 열이 많다")
    _save(fig, out)
    return dict(n_missing_cols=n0, n_half_missing=n50, top_missing=[(r["컬럼명"], float(r["결측률"])) for _, r in m.iloc[::-1].head(5).iterrows()],
                n_complete=int((cd["결측률"] == 0).sum()))


# ───────────── 02 단지 개요 ─────────────
def fig_branch_supply(b, out):
    t = pd.crosstab(b["지사명"], b["supply_group"]).reindex(columns=ED.SUPPLY_ORDER, fill_value=0)
    t = t.loc[t.sum(axis=1).sort_values().index]
    fig, ax = _base((8.8, 5.6))
    left = np.zeros(len(t))
    for k in ED.SUPPLY_ORDER:
        ax.barh(t.index, t[k], left=left, height=0.64, color=SG_COLOR[k], edgecolor=SURFACE, linewidth=1.2, label=k)
        left += t[k].values
    for y, v in enumerate(t.sum(axis=1)):
        ax.text(v + 0.5, y, f"{int(v)}", va="center", fontsize=8, color=INK1)
    ax.legend(loc="lower right", frameon=False, fontsize=8.2, labelcolor=INK2)
    tot = t.sum(axis=1)
    sg = b["supply_group"].value_counts()
    _title(fig, f"{len(b)}개 단지 중 {J.qgwawa(sg.index[0])} {J.q(sg.index[1])}{J.iga(sg.index[1])} {_pc((sg.iloc[0] + sg.iloc[1]) / len(b))}를 차지한다",
           f"지사별 단지 수(공급유형 묶음별). 가장 많은 지사는 {tot.idxmax()}({int(tot.max())}개), 가장 적은 지사는 {tot.idxmin()}({int(tot.min())}개)")
    _save(fig, out)
    return dict(n=int(len(b)), supply=sg.to_dict(), branch_max=(tot.idxmax(), int(tot.max())), branch_min=(tot.idxmin(), int(tot.min())), n_branch=int(len(tot)),
                n_mixed=int((b["supply_group"] == "복합 공급").sum()))


def fig_size(b, out):
    fig, axs = plt.subplots(1, 2, figsize=(9.6, 4.6), dpi=160, gridspec_kw=dict(width_ratios=[1.1, 1]))
    fig.patch.set_facecolor(SURFACE)
    for ax in axs:
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.5, length=0)
    ax = axs[0]
    ax.hist(b["log_households"], bins=22, color=CAT[0], edgecolor=SURFACE)
    med = b["세대수"].median()
    ax.axvline(np.log10(med), color=INK1, lw=1)
    ax.text(np.log10(med) + 0.02, ax.get_ylim()[1] * 0.92, f"중앙값 {med:,.0f}세대", fontsize=8.4, color=INK1)
    ax.set_xticks([1.5, 2, 2.5, 3, 3.5])
    ax.set_xticklabels(["30", "100", "300", "1,000", "3,000"])
    ax.set_xlabel("세대수(로그 눈금)", fontsize=8.5, color=INK2)
    ax.set_ylabel("단지 수", fontsize=8.5, color=INK2)
    ax = axs[1]
    order = ED.SUPPLY_ORDER
    data = [b.loc[b["supply_group"] == k, "세대수"].values for k in order]
    bp = ax.boxplot(data, vert=False, patch_artist=True, widths=0.55, showfliers=True, flierprops=dict(marker="o", ms=3, mfc=GRAY_N, mec="none"))
    for p, k in zip(bp["boxes"], order):
        p.set(facecolor=SG_COLOR[k], edgecolor=INK2, alpha=0.9)
    for m in bp["medians"]:
        m.set(color=INK1, lw=1.4)
    for w in bp["whiskers"] + bp["caps"]:
        w.set(color=INK3)
    ax.set_xscale("log")
    ax.set_yticks(range(1, len(order) + 1))
    ax.set_yticklabels([f"{k} (n={len(v)})" for k, v in zip(order, data)])
    ax.invert_yaxis()
    ax.set_xlabel("세대수(로그 눈금)", fontsize=8.5, color=INK2)
    ax.set_xticks([30, 100, 300, 1000, 3000])
    ax.set_xticklabels(["30", "100", "300", "1,000", "3,000"])
    ax.minorticks_off()
    g = gini(b["세대수"].values)
    top10 = b["세대수"].nlargest(int(len(b) * 0.1)).sum() / b["세대수"].sum()
    kw = stats.kruskal(*[x for x in data if len(x) > 2])
    fig.text(0.012, 0.985, f"단지 규모는 오른쪽으로 길게 늘어진 분포다: 중앙값 {med:,.0f}세대, 최대 {int(b['세대수'].max()):,}세대", ha="left", va="top", fontsize=12.2, color=INK1, fontweight="bold")
    fig.text(0.012, 0.925, f"지니계수 {g:.2f}, 상위 10% 단지가 전체 세대의 {_pc(top10)}. 공급유형 묶음 사이 규모 차이는 크루스칼-월리스 {_fmt_p(kw.pvalue)}", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.84, wspace=0.42, left=0.08, right=0.97, bottom=0.14)
    _save(fig, out)
    return dict(median=float(med), q1=float(b["세대수"].quantile(.25)), q3=float(b["세대수"].quantile(.75)), max=int(b["세대수"].max()), min=int(b["세대수"].min()),
                gini=float(g), top10=float(top10), kw_p=float(kw.pvalue), by_supply={k: float(b.loc[b["supply_group"] == k, "세대수"].median()) for k in order})


OUTLINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "eda_20261117_v1", "assets", "korea_outline.geojson")


def draw_korea(ax, face="#ecebe6", edge="#c9c8c2"):
    """격자 기반 육지 외곽선(korea_outline.py 산출)을 배경으로 그린다. 파일이 없으면 아무것도 그리지 않는다."""
    import json
    from matplotlib.patches import Polygon as MPoly
    if not os.path.exists(OUTLINE):
        return False
    g = json.load(open(OUTLINE, encoding="utf-8"))["features"][0]["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    for poly in polys:
        ax.add_patch(MPoly(np.array(poly[0]), closed=True, facecolor=face, edgecolor=edge, linewidth=0.5, zorder=0))
        for hole in poly[1:]:
            ax.add_patch(MPoly(np.array(hole), closed=True, facecolor=SURFACE, edgecolor=edge, linewidth=0.4, zorder=0))
    return True


def fig_map(b, out):
    fig, ax = _base((6.8, 7.6))
    ax.spines["bottom"].set_visible(False)
    draw_korea(ax)
    ax.set_xlim(124.5, 131.2); ax.set_ylim(33.0, 38.7)
    v = b["hd25_support"] / b["hd25_n_months"] / b["세대수"] * 100
    sc = ax.scatter(b["longitude"], b["latitude"], c=v, cmap=SEQ, s=np.clip(b["세대수"] / 14, 8, 220), edgecolor="#ffffff", linewidth=0.6, alpha=0.95, zorder=3)
    ax.set_aspect(1 / np.cos(np.radians(36)))
    ax.set_xticks([]); ax.set_yticks([])
    cb = fig.colorbar(sc, ax=ax, shrink=0.55, pad=0.01)
    cb.set_label("홈닥터 지원 건수(100세대당 월평균, 2025)", fontsize=8.2, color=INK2)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=8, colors=INK2, length=0)
    for sz, lab in [(200, "2,800세대"), (70, "1,000세대"), (21, "300세대")]:
        ax.scatter([], [], s=min(sz, 220), color=GRAY_N, label=lab)
    ax.legend(title="점 크기=세대수", loc="lower left", frameon=False, fontsize=7.8, title_fontsize=8, labelcolor=INK2)
    r = _sp(b["longitude"], v)
    _title(fig, "전국 318개 단지의 위치: 수도권과 영남·호남에 모여 있고 지원 강도(색)는 이웃 단지끼리도 차이가 난다", "위치 = 좌표(경도·위도), 색 = 2025년 100세대당 월평균 지원 건수, 크기 = 세대수. 울릉·제주 단지도 함께 표시")
    _save(fig, out)
    return dict(lon_rng=(float(b["longitude"].min()), float(b["longitude"].max())), lat_rng=(float(b["latitude"].min()), float(b["latitude"].max())))


def fig_age(b, out):
    fig, axs = plt.subplots(1, 2, figsize=(9.8, 4.7), dpi=160, gridspec_kw=dict(width_ratios=[1, 1.15]))
    fig.patch.set_facecolor(SURFACE)
    for ax in axs:
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.5, length=0)
    ax = axs[0]
    order = ED.SUPPLY_ORDER
    data = [b.loc[b["supply_group"] == k, "인구_60세이상_비율"].values * 100 for k in order]
    bp = ax.boxplot(data, vert=False, patch_artist=True, widths=0.55, showfliers=False)
    rng = np.random.default_rng(7)
    for i, (x, k) in enumerate(zip(data, order)):
        ax.scatter(x, rng.normal(i + 1, 0.07, len(x)), s=7, color=SG_COLOR[k], alpha=0.55, edgecolor="none", zorder=3)
    for p, k in zip(bp["boxes"], order):
        p.set(facecolor="none", edgecolor=INK2)
    for m in bp["medians"]:
        m.set(color=INK1, lw=1.4)
    for w in bp["whiskers"] + bp["caps"]:
        w.set(color=INK3)
    ax.set_yticks(range(1, len(order) + 1))
    ax.set_yticklabels([f"{k} (n={len(v)})" for k, v in zip(order, data)])
    ax.invert_yaxis()
    ax.set_xlabel("60세 이상 인구 비율(%)", fontsize=8.5, color=INK2)
    kw = stats.kruskal(*[x for x in data if len(x) > 2])
    ax = axs[1]
    x, y = b["입주기준경과년수"], b["인구_60세이상_비율"] * 100
    for k in order:
        m = b["supply_group"] == k
        ax.scatter(x[m], y[m], s=14, color=SG_COLOR[k], alpha=0.75, edgecolor="none", label=k)
    bins = pd.cut(x, [0, 10, 20, 25, 30, 33, 40])
    med = y.groupby(bins, observed=True).median()
    cen = x.groupby(bins, observed=True).median()
    ax.plot(cen, med, color=INK1, lw=1.6, marker="o", ms=4)
    ax.set_xlabel("입주 후 경과 연수", fontsize=8.5, color=INK2)
    ax.set_ylabel("60세 이상 인구 비율(%)", fontsize=8.5, color=INK2)
    ax.legend(frameon=False, fontsize=7.8, labelcolor=INK2, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=5, columnspacing=1.0, handletextpad=0.2)
    r = _sp(x, y / 100)
    fig.text(0.012, 0.985, f"고령화는 입주 후 오래된 단지에서 뚜렷하다(ρ={r[0]:.2f}), 중앙값은 {y.median():.0f}%", ha="left", va="top", fontsize=12.2, color=INK1, fontweight="bold")
    fig.text(0.012, 0.925, f"왼쪽: 공급유형 묶음별 분포(차이 검정 {_fmt_p(kw.pvalue)}). 오른쪽: 경과 연수 구간별 중앙값(검은 선), 점은 단지", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.84, wspace=0.55, left=0.12, right=0.98, bottom=0.2)
    _save(fig, out)
    med_sg = {k: float(np.median(v)) for k, v in zip(order, data)}
    return dict(median60=float(y.median()), p90=float(y.quantile(.9)), n_over70=int((y > 70).sum()), rho_age=r[0], rho_lo=r[2], rho_hi=r[3], kw_p=float(kw.pvalue), by_supply=med_sg, max_sg=max(med_sg, key=med_sg.get), min_sg=min(med_sg, key=med_sg.get))


CORR_VARS = [("세대수", "세대수"), ("입주기준경과년수", "경과 연수"), ("평형_전용면적가중평균_㎡", "전용면적"), ("평형_40㎡미만세대비율", "40㎡ 미만 비율"), ("인구_60세이상_비율", "60세+ 비율"),
             ("인구_80세이상_비율", "80세+ 비율"), ("인구_20세미만_비율", "20세 미만 비율"), ("인구_여자_비율", "여자 비율"), ("hd_per100", "홈닥터 100세대당"), ("커뮤니티_per1000", "커뮤니티 활동/1000세대"),
             ("std_richness", "프로그램 유형 수"), ("접근성_병원_500m_평균_km", "병원 거리"), ("접근성_약국_500m_평균_km", "약국 거리"), ("접근성_경로당_500m_평균_km", "경로당 거리"),
             ("접근성_노인복지관_500m_평균_km", "노인복지관 거리"), ("접근성_종합사회복지관_500m_평균_km", "사회복지관 거리"), ("접근성_보건기관_500m_평균_km", "보건기관 거리")]


def add_derived(b):
    b["hd_per100"] = b["hd25_support"] / b["hd25_n_months"] / b["세대수"] * 100
    b["커뮤니티_per1000"] = b["resident_records_per_1000hh_year"]
    return b


def fig_corr(b, out):
    cols = [c for c, _ in CORR_VARS]
    labs = [l for _, l in CORR_VARS]
    R = b[cols].corr(method="spearman").values
    n = len(cols)
    fig, ax = plt.subplots(figsize=(9.4, 8.2), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    im = ax.imshow(R, cmap=DIV, vmin=-1, vmax=1)
    ax.set_xticks(range(n)); ax.set_yticks(range(n))
    ax.set_xticklabels(labs, rotation=60, ha="right", fontsize=8)
    ax.set_yticklabels(labs, fontsize=8)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(n):
        for j in range(n):
            if i != j and abs(R[i, j]) >= 0.3:
                ax.text(j, i, f"{R[i, j]:.2f}".replace("0.", ".").replace("-", "-"), ha="center", va="center", fontsize=6.4, color="white" if abs(R[i, j]) > 0.6 else INK1)
    cb = fig.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=8, colors=INK2, length=0)
    cb.set_label("스피어만 상관계수", fontsize=8.2, color=INK2)
    iu = np.triu_indices(n, 1)
    order = np.argsort(-np.abs(R[iu]))
    top = [(labs[iu[0][k]], labs[iu[1][k]], float(R[iu][k])) for k in order[:6]]
    fig.text(0.012, 0.985, f"강한 상관은 '고령화-경과 연수-규모'와 '시설 접근성끼리'에 모여 있다", ha="left", va="top", fontsize=12.4, color=INK1, fontweight="bold")
    fig.text(0.012, 0.953, f"{n}개 변수의 순위상관(단지 단위, 쌍별 결측 제외). 칸 숫자는 |ρ|≥0.3인 쌍만 표시", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.9, left=0.2, bottom=0.2)
    _save(fig, out)
    return dict(top=top, n_vars=n, share_strong=float((np.abs(R[iu]) >= 0.5).mean()), n_pairs=int(len(iu[0])), R=pd.DataFrame(R, index=labs, columns=labs))


# ───────────── 03 홈닥터 시계열 ─────────────
def fig_hd_time(d, out):
    hd = d["hd"].copy()
    hd["m"] = pd.PeriodIndex(hd["기간"], freq="M")
    g = hd.groupby("m").agg(total=("지원내용총건수", "sum"), n_cx=("complex_id", "nunique"), hh=("세대수", "sum"))
    g["per100"] = g["total"] / g["hh"] * 100
    idx = pd.period_range("2022-01", "2026-06", freq="M")
    g = g.reindex(idx)
    sparse = g["n_cx"] < 100
    g.loc[sparse, ["total", "per100"]] = np.nan
    x = np.arange(len(idx))
    fig, axs = plt.subplots(3, 1, figsize=(9.2, 7.4), dpi=160, sharex=True, gridspec_kw=dict(height_ratios=[1.1, 1.1, 0.7]))
    fig.patch.set_facecolor(SURFACE)
    for ax in axs:
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.5, length=0)
        ax.grid(axis="y", color=GRID, lw=0.7)
    axs[0].plot(x, g["total"], color=CAT[0], lw=1.8)
    axs[0].set_ylabel("지원 건수 합계(건)", fontsize=8.4, color=INK2)
    axs[1].plot(x, g["per100"], color=CAT[2], lw=1.8)
    axs[1].set_ylabel("100세대당 지원 건수", fontsize=8.4, color=INK2)
    axs[2].bar(x, g["n_cx"], color=CAT[3], width=0.8)
    for i in np.where(sparse)[0]:
        axs[0].annotate(f"{idx[i]}: 자료 있는 단지 {int(g['n_cx'].iloc[i])}곳뿐이라 제외", (i, 30000), xytext=(i + 2, 30000), fontsize=8, color=INK1, va="center",
                        arrowprops=dict(arrowstyle="-", color=INK3, lw=0.8))
    axs[2].set_ylabel("관측 단지 수", fontsize=8.4, color=INK2)
    axs[2].set_ylim(g["n_cx"].min() * 0.9, g["n_cx"].max() * 1.03)
    ticks = [i for i, p in enumerate(idx) if p.month == 1]
    axs[2].set_xticks(ticks)
    axs[2].set_xticklabels([str(idx[i].year) for i in ticks])
    cov_min = int(g["n_cx"].min())
    ym = g["per100"].groupby(g.index.year).mean()
    gap_m = [str(p) for p in idx[sparse]]
    pk = g["per100"].idxmax()
    fig.text(0.012, 0.985, f"홈닥터 지원은 월 {g['total'].min():,.0f}~{g['total'].max():,.0f}건, 100세대당 {g['per100'].min():.1f}~{g['per100'].max():.1f}건 범위에서 움직인다", ha="left", va="top", fontsize=12.2, color=INK1, fontweight="bold")
    fig.text(0.012, 0.953, f"월별 전체 단지 합계(위), 세대 규모를 보정한 100세대당 지원 건수(가운데), 그 달에 자료가 있는 단지 수(아래). 2026년은 6월까지. 2024-01은 자료가 거의 없어 선을 끊었다", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.9, hspace=0.25, left=0.1, right=0.98, bottom=0.06)
    _save(fig, out)
    return dict(tot_min=float(g["total"].min()), tot_max=float(g["total"].max()), p_min=float(g["per100"].min()), p_max=float(g["per100"].max()), peak=str(pk), cov_min=cov_min, cov_max=int(g["n_cx"].max()),
                year_mean={int(k): float(v) for k, v in ym.items()}, gap_months=gap_m, gap_n=[int(n) for n in g['n_cx'][sparse]], monthly=g.reset_index().rename(columns={"index": "month"}).astype({"month": str}))


def fig_hd_comp(d, b, out):
    hd = d["hd"]
    y = hd.groupby("년도")[HD].sum()
    sh = y.div(y.sum(axis=1), axis=0) * 100
    h = hd[hd["년도"] == 2025].groupby("지사명")[HD].sum()
    shb = h.div(h.sum(axis=1), axis=0) * 100
    shb = shb.sort_values("생활지원")
    fig, axs = plt.subplots(1, 2, figsize=(10.2, 5.0), dpi=160, gridspec_kw=dict(width_ratios=[0.8, 1.2]))
    fig.patch.set_facecolor(SURFACE)
    for ax in axs:
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.5, length=0)
    ax = axs[0]
    bottom = np.zeros(len(sh))
    for c, col in zip(HD, CAT[:4]):
        ax.bar(sh.index.astype(str), sh[c], bottom=bottom, color=col, edgecolor=SURFACE, linewidth=1.2, label=c.replace("지원", ""), width=0.66)
        for i, v in enumerate(sh[c]):
            if v > 6:
                ax.text(i, bottom[i] + v / 2, f"{v:.0f}", ha="center", va="center", fontsize=8, color="white")
        bottom += sh[c].values
    ax.set_ylabel("지원 건수 구성(%)", fontsize=8.5, color=INK2)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.09))
    ax = axs[1]
    left = np.zeros(len(shb))
    for c, col in zip(HD, CAT[:4]):
        ax.barh(shb.index, shb[c], left=left, color=col, edgecolor=SURFACE, linewidth=1.0, height=0.7)
        left += shb[c].values
    ax.set_xlabel("2025년 지원 건수 구성(%)", fontsize=8.5, color=INK2)
    ax.set_xlim(0, 100)
    life = float(sh["생활지원"].mean())
    fig.text(0.012, 0.985, f"홈닥터 지원의 {_pc(sh['생활지원'].mean() / 100)}는 생활지원이고 의료·경제 지원은 {_pc((sh['의료지원'].mean() + sh['경제지원'].mean()) / 100)}에 그친다", ha="left", va="top", fontsize=12.2, color=INK1, fontweight="bold")
    rng_b0 = shb["의료지원"].max() - shb["의료지원"].min()
    rng_y0 = sh["의료지원"].max() - sh["의료지원"].min()
    fig.text(0.012, 0.925, f"왼쪽: 연도별 구성(%, 건수 합계 기준). 오른쪽: 2025년 지사별 구성. 의료지원 비중의 범위는 지사 간 {rng_b0:.0f}%p, 연도 간 {rng_y0:.1f}%p", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.82, wspace=0.28, left=0.07, right=0.98, bottom=0.1)
    _save(fig, out)
    rng_b = shb["의료지원"].max() - shb["의료지원"].min()
    rng_y = sh["의료지원"].max() - sh["의료지원"].min()
    return dict(share_mean={c: float(sh[c].mean()) for c in HD}, med_branch_range=float(rng_b), med_year_range=float(rng_y), med_hi=(shb["의료지원"].idxmax(), float(shb["의료지원"].max())),
                med_lo=(shb["의료지원"].idxmin(), float(shb["의료지원"].min())), by_year=sh)


def fig_hd_dist(d, out):
    hd = d["hd"].copy()
    hd["per100"] = hd["지원내용총건수"] / hd["세대수"] * 100
    fig, axs = plt.subplots(1, 3, figsize=(11.6, 4.5), dpi=160, gridspec_kw=dict(width_ratios=[1, 1.05, 1]))
    fig.patch.set_facecolor(SURFACE)
    for ax in axs:
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.3, length=0)
    ax = axs[0]
    v = hd["per100"].clip(upper=100)
    ax.hist(v, bins=40, color=CAT[0], edgecolor=SURFACE)
    z = float((hd["지원내용총건수"] == 0).mean())
    ax.set_xlabel("월별 100세대당 지원 건수(100 초과는 100으로 표시)", fontsize=8.3, color=INK2)
    ax.set_ylabel("단지-월 관측 수", fontsize=8.3, color=INK2)
    ax.text(0.98, 0.9, f"지원 0건인 달 {_pc(z, 1)}\n중앙값 {hd['per100'].median():.1f}", transform=ax.transAxes, ha="right", va="top", fontsize=8.5, color=INK1)
    ax = axs[1]
    cal = hd[~((hd["년도"] == 2024) & (hd["월"] == 1))].groupby(["년도", "월"])["per100"].mean().reset_index()   # 2024-01은 10개 단지만 있어 제외
    for yr, col in zip([2022, 2023, 2024, 2025], CAT[:4]):
        s = cal[cal["년도"] == yr]
        ax.plot(s["월"], s["per100"] / s["per100"].mean(), color=col, lw=1.6, marker="o", ms=3.2, label=str(yr))
    ax.axhline(1, color=AXIS, lw=0.8)
    ax.set_xticks(range(1, 13))
    ax.set_xlabel("달력 월", fontsize=8.3, color=INK2)
    ax.set_ylabel("계절 지수(연평균=1)", fontsize=8.3, color=INK2)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, ncol=2, loc="lower right")
    sea = cal[cal["년도"].isin([2022, 2023, 2024, 2025])].groupby("월")["per100"].mean()
    ax = axs[2]
    gp = hd[hd["년도"].isin([2024, 2025])].groupby("complex_id")["per100"].agg(["mean", "std"])
    gp = gp[gp["mean"] > 0]
    ax.scatter(gp["mean"], gp["std"] / gp["mean"], s=11, color=CAT[0], alpha=0.6, edgecolor="none")
    ax.set_xscale("log")
    ax.set_xlabel("단지 평균(2024~25, 로그 눈금)", fontsize=8.3, color=INK2)
    ax.set_ylabel("월별 변동계수(표준편차/평균)", fontsize=8.3, color=INK2)
    ax.set_xticks([1, 3, 10, 30]); ax.set_xticklabels(["1", "3", "10", "30"]); ax.minorticks_off()
    r = _sp(gp["mean"], gp["std"] / gp["mean"])
    # ICC(1): 2025 단지 간 분산 비율
    h25 = hd[(hd["년도"] == 2025)]
    grp = h25.groupby("complex_id")["per100"]
    k = grp.size().mean()
    msb = ((grp.mean() - h25["per100"].mean()) ** 2 * grp.size()).sum() / (grp.ngroups - 1)
    msw = ((h25["per100"] - grp.transform("mean")) ** 2).sum() / (len(h25) - grp.ngroups)
    icc = (msb - msw) / (msb + (k - 1) * msw)
    fig.text(0.012, 0.985, f"단지 간 차이가 월별 변동보다 크다: 2025년 월별 값 변동의 {_pc(icc)}가 단지 간 차이(ICC)다", ha="left", va="top", fontsize=12.2, color=INK1, fontweight="bold")
    fig.text(0.012, 0.925, "왼쪽: 단지-월 값의 분포(오른쪽으로 긴 꼬리). 가운데: 연도별 계절 지수. 오른쪽: 평균이 낮은 단지일수록 월별 흔들림(변동계수)이 크다", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.84, wspace=0.34, left=0.06, right=0.99, bottom=0.14)
    _save(fig, out)
    return dict(zero_share=z, median=float(hd["per100"].median()), p90=float(hd["per100"].quantile(.9)), p99=float(hd["per100"].quantile(.99)), icc=float(icc), peak_m=int(sea.idxmax()), low_m=int(sea.idxmin()),
                sea_hi=float(sea.max() / sea.mean()), sea_lo=float(sea.min() / sea.mean()), cv_rho=r[0], n=int(len(hd)))


# ───────────── 04 예측 기준선 ─────────────
def baseline_eval(d):
    mp = d["mp"]
    m = mp[(mp["source_observed"] == 1)].copy()
    tr = m[m["suggested_split"] == "train_2022_2024"].groupby("complex_id")["recorded_support_count"].mean().rename("train_mean")
    m = m.merge(tr, on="complex_id", how="left")
    cols = {"직전 달 값(lag1)": "lag1_support", "1년 전 같은 달(lag12)": "lag12_support", "직전 3개월 평균": "prior3_mean_support", "직전 6개월 평균": "prior6_mean_support", "훈련기간(2022~24) 단지 평균": "train_mean"}
    res = []
    for split in ["validation_2025", "test_2026_H1"]:
        s = m[(m["suggested_split"] == split) & (m["eligible_history6"] == 1)].dropna(subset=list(cols.values()))
        y = s["recorded_support_count"]
        for nm, c in cols.items():
            e = (s[c] - y).abs()
            res.append(dict(split=split, baseline=nm, n=int(len(s)), mae=float(e.mean()), wape=float(e.sum() / y.sum()), rmse=float(np.sqrt(((s[c] - y) ** 2).mean())),
                            r2=float(1 - ((s[c] - y) ** 2).sum() / ((y - y.mean()) ** 2).sum())))
        # 달력월 평균(전체 단지)
    return pd.DataFrame(res), m


def fig_baseline(d, out):
    t, m = baseline_eval(d)
    fig, axs = plt.subplots(1, 2, figsize=(10.2, 4.7), dpi=160, gridspec_kw=dict(width_ratios=[1.15, 1]))
    fig.patch.set_facecolor(SURFACE)
    for ax in axs:
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.5, length=0)
    ax = axs[0]
    names = list(t["baseline"].unique())[::-1]
    h = 0.36
    for i, (sp, col, lab) in enumerate([("validation_2025", CAT[0], "검증 2025"), ("test_2026_H1", CAT[1], "시험 2026 상반기")]):
        s = t[t["split"] == sp].set_index("baseline").loc[names]
        ax.barh(np.arange(len(names)) + (i - 0.5) * h, s["wape"] * 100, height=h * 0.92, color=col, label=lab)
        for y, v in enumerate(s["wape"] * 100):
            ax.text(v + 0.5, y + (i - 0.5) * h, f"{v:.1f}%", va="center", fontsize=7.8, color=INK1)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8.4)
    ax.set_xlabel("가중 절대오차율 WAPE(%) = Σ|오차| / Σ실측", fontsize=8.4, color=INK2)
    ax.legend(frameon=False, fontsize=8.2, labelcolor=INK2, loc="upper right")
    ax.set_xlim(0, t["wape"].max() * 100 * 1.18)
    ax = axs[1]
    s = m[(m["suggested_split"] == "test_2026_H1") & (m["eligible_history6"] == 1)].dropna(subset=["lag1_support"])
    ax.scatter(s["lag1_support"] + 1, s["recorded_support_count"] + 1, s=7, color=CAT[0], alpha=0.35, edgecolor="none")
    lim = [1, max(s["lag1_support"].max(), s["recorded_support_count"].max()) * 1.2]
    ax.plot(lim, lim, color=INK1, lw=1)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("직전 달 지원 건수 + 1(로그)", fontsize=8.4, color=INK2)
    ax.set_ylabel("이번 달 지원 건수 + 1(로그)", fontsize=8.4, color=INK2)
    ax.minorticks_off()
    t26 = t[t["split"] == "test_2026_H1"].set_index("baseline")
    best = t26["wape"].idxmin()
    fig.text(0.012, 0.985, f"단순 규칙만으로도 오차율 {t26['wape'].min() * 100:.0f}%대다: 가장 낮은 기준선은 {J.q(best)}", ha="left", va="top", fontsize=12.2, color=INK1, fontweight="bold")
    fig.text(0.012, 0.925, f"홈닥터 월별 지원 건수 예측의 기준선(과거 6개월 이력이 있는 관측만). 어떤 모델이든 이 기준선보다 낮아야 의미가 있다. 오른쪽: 시험기간 직전 달 값과 실측(대각선 = 완전 일치)", ha="left", va="top", fontsize=8.6, color=INK2)
    fig.subplots_adjust(top=0.84, wspace=0.4, left=0.2, right=0.98, bottom=0.14)
    _save(fig, out)
    return dict(table=t, best=best, best_wape=float(t26["wape"].min()), worst_wape=float(t26["wape"].max()), n_test=int(t26["n"].iloc[0]), n_val=int(t[t["split"] == "validation_2025"]["n"].iloc[0]))


def fig_recon(d, out):
    hd = d["hd"].copy()
    hd["bad"] = (hd["지원합계대조차이"].fillna(0) != 0).astype(int)
    y = hd.groupby("년도")["bad"].agg(["sum", "mean"])
    b = hd.groupby("지사명")["bad"].mean().sort_values()
    c = hd[hd["bad"] == 1]["지원합계대조차이"]
    fig, axs = plt.subplots(1, 2, figsize=(9.8, 4.6), dpi=160, gridspec_kw=dict(width_ratios=[0.8, 1.2]))
    fig.patch.set_facecolor(SURFACE)
    for ax in axs:
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.5, length=0)
    axs[0].bar(y.index.astype(str), y["mean"] * 100, color=CAT[0], width=0.62)
    for i, v in enumerate(y["mean"] * 100):
        axs[0].text(i, v + 0.15, f"{v:.1f}%", ha="center", fontsize=8.2, color=INK1)
    axs[0].set_ylabel("합계 불일치 달의 비율(%)", fontsize=8.5, color=INK2)
    axs[1].barh(b.index, b * 100, color=CAT[0], height=0.62)
    for i, v in enumerate(b * 100):
        axs[1].text(v + 0.1, i, f"{v:.1f}%", va="center", fontsize=8, color=INK1)
    axs[1].set_xlabel("지사별 합계 불일치 달의 비율(%)", fontsize=8.5, color=INK2)
    fig.text(0.012, 0.985, f"세부 합과 총건수가 어긋나는 달이 전체의 {_pc(hd['bad'].mean(), 1)}다(최대 지사 {b.idxmax()} {b.max() * 100:.1f}%)", ha="left", va="top", fontsize=12.2, color=INK1, fontweight="bold")
    fig.text(0.012, 0.925, "생활·가사·의료·경제 지원 건수의 합이 '지원내용총건수'와 다른 단지-월. 모델 입력에서는 이 달을 표시해 두고 원자료 확인이 필요하다", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.84, wspace=0.35, left=0.08, right=0.98, bottom=0.12)
    _save(fig, out)
    return dict(share=float(hd["bad"].mean()), n=int(hd["bad"].sum()), by_year=y["mean"].to_dict(), top_branch=(b.idxmax(), float(b.max())), low_branch=(b.idxmin(), float(b.min())), med_diff=float(c.median()) if len(c) else 0.0,
                n_cx=int(hd.loc[hd["bad"] == 1, "complex_id"].nunique()))


# ───────────── 05 접근성 ─────────────
def fig_access(b, out):
    cols = [c for c in b.columns if c.startswith("접근성_") and c.endswith("_500m_평균_km")]
    lab = {c: c.replace("접근성_", "").replace("_500m_평균_km", "") for c in cols}
    med = b[cols].median().sort_values()
    fig, ax = _base((8.8, 6.2))
    data = [b[c].dropna().values for c in med.index]
    bp = ax.boxplot(data, vert=False, patch_artist=True, widths=0.6, showfliers=True, flierprops=dict(marker="o", ms=2.6, mfc=GRAY_N, mec="none"))
    for p in bp["boxes"]:
        p.set(facecolor=CAT[0], edgecolor=INK2, alpha=0.85)
    for m in bp["medians"]:
        m.set(color=INK1, lw=1.4)
    for w in bp["whiskers"] + bp["caps"]:
        w.set(color=INK3)
    ax.set_xscale("log")
    ax.set_yticks(range(1, len(med) + 1))
    ax.set_yticklabels([f"{lab[c]} (n={len(v)})" for c, v in zip(med.index, data)])
    ax.set_xticks([0.3, 1, 3, 10, 30, 100]); ax.set_xticklabels(["0.3", "1", "3", "10", "30", "100"]); ax.minorticks_off()
    ax.set_xlabel("단지 중심에서 500m 내 격자의 평균 접근 거리(km, 로그 눈금)", fontsize=8.5, color=INK2)
    ax.tick_params(axis="y", labelsize=8)
    near = [lab[c] for c in med.index[:3]]
    far = [lab[c] for c in med.index[-3:]][::-1]
    _title(fig, f"가까운 시설은 {', '.join(near)}, 먼 시설은 {', '.join(far)} 쪽이다(중앙값 {med.iloc[0]:.1f}→{med.iloc[-1]:.0f}km)", "시설 종류별 단지 단위 접근 거리 분포(값이 클수록 멀다). 접근성 결측은 0km가 아니며 해당 격자·시설이 없다는 뜻일 수 있다")
    _save(fig, out)
    return dict(near=near, far=far, med={lab[c]: float(v) for c, v in med.items()}, n_types=len(cols), n_over5=int((b["접근성_병원_500m_평균_km"] > 5).sum()))


def fig_access_hd(b, out):
    pairs = [("접근성_병원_500m_평균_km", "병원"), ("접근성_의원_500m_평균_km", "의원"), ("접근성_약국_500m_평균_km", "약국"), ("접근성_보건기관_500m_평균_km", "보건기관")]
    y = b["hd25_의료지원_share"] * 100
    fig, axs = plt.subplots(2, 2, figsize=(9.2, 7.0), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    st = {}
    for ax, (c, nm) in zip(axs.ravel(), pairs):
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8, length=0)
        m = b[c].notna() & y.notna()
        ax.scatter(b.loc[m, c], y[m], s=11, color=CAT[0], alpha=0.55, edgecolor="none")
        ax.set_xscale("log")
        ax.set_xticks([0.3, 1, 3, 10, 30]); ax.set_xticklabels(["0.3", "1", "3", "10", "30"]); ax.minorticks_off()
        r = _sp(b[c], y)
        st[nm] = r
        ax.set_title(f"{nm} 거리 ↔ 의료지원 비중: ρ={r[0]:+.2f} (95% {r[2]:+.2f}~{r[3]:+.2f})", fontsize=8.6, color=INK1, loc="left")
        ax.set_xlabel(f"{nm}까지 평균 거리(km)", fontsize=8.2, color=INK2)
        ax.set_ylabel("2025 의료지원 비중(%)", fontsize=8.2, color=INK2)
    ps = holm([v[1] for v in st.values()])
    n_sig = int(sum(p < 0.05 for p in ps))
    fig.text(0.012, 0.985, f"의료시설이 멀수록 의료지원 비중이 높다는 증거는 {'약하다' if n_sig == 0 else '일부 있다'}(보정 후 유의 {n_sig}/4)", ha="left", va="top", fontsize=12.2, color=INK1, fontweight="bold")
    fig.text(0.012, 0.953, "단지 단위 산점도(홈닥터 2025년 지원 건수 중 의료지원 비중, 지원이 있는 단지만). 상관은 인과가 아니며 지역·단지 유형이 섞여 있다", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.87, hspace=0.42, wspace=0.28, left=0.08, right=0.98, bottom=0.07)
    _save(fig, out)
    return dict(rho={k: v[0] for k, v in st.items()}, p_holm=dict(zip(st, ps)), n_sig=n_sig, n=int(st["병원"][4]))


# ───────────── 06 교차 분석(커뮤니티×홈닥터×여건) ─────────────
def fig_comm_hd(b, out):
    cm = b[b["low_data_flag"] == 0].copy()
    fams = [c for c in cm.columns if c.startswith("share_family_F") and not c.endswith("F99")]
    prev = cm[fams].mean().sort_values(ascending=False)
    fams = list(prev.index[:12])
    fl = lambda c: TX.FAMILIES.get(c.replace("share_family_", ""), c)
    ycols = [("hd25_생활지원_per100", "생활지원"), ("hd25_가사지원_per100", "가사지원"), ("hd25_의료지원_per100", "의료지원"), ("hd25_경제지원_per100", "경제지원"), ("hd_per100", "전체")]
    R = np.full((len(fams), len(ycols)), np.nan)
    P = np.ones_like(R)
    for i, f in enumerate(fams):
        for j, (yc, _) in enumerate(ycols):
            r = _sp(cm[f], cm[yc])
            R[i, j], P[i, j] = r[0], r[1]
    Pa = holm(P.ravel()).reshape(P.shape)
    fig, axs = plt.subplots(1, 2, figsize=(11.0, 5.4), dpi=160, gridspec_kw=dict(width_ratios=[1, 1.15]))
    fig.patch.set_facecolor(SURFACE)
    ax = axs[0]
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=8.3, length=0)
    m = cm["커뮤니티_per1000"].notna() & cm["hd_per100"].notna()
    ax.scatter(cm.loc[m, "커뮤니티_per1000"], cm.loc[m, "hd_per100"], s=12, color=CAT[0], alpha=0.6, edgecolor="none")
    ax.set_xscale("log")
    ax.set_xticks([3, 10, 30, 100, 300]); ax.set_xticklabels(["3", "10", "30", "100", "300"]); ax.minorticks_off()
    rr = _sp(cm["커뮤니티_per1000"], cm["hd_per100"])
    ax.set_xlabel("커뮤니티 주민 대상 기록(세대 1000당 연, 로그 눈금)", fontsize=8.3, color=INK2)
    ax.set_ylabel("홈닥터 지원(100세대당 월평균, 2025)", fontsize=8.3, color=INK2)
    ax.set_title(f"ρ={rr[0]:+.2f} (95% {rr[2]:+.2f}~{rr[3]:+.2f}), n={rr[4]}", fontsize=8.8, color=INK1, loc="left")
    ax = axs[1]
    ax.set_facecolor(SURFACE)
    vmax = max(0.35, np.nanmax(np.abs(R)))
    im = ax.imshow(R, cmap=DIV, vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(ycols))); ax.set_xticklabels([l for _, l in ycols], fontsize=8.4)
    ax.set_yticks(range(len(fams))); ax.set_yticklabels([_short(fl(f), 16) for f in fams], fontsize=8)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(len(fams)):
        for j in range(len(ycols)):
            star = "*" if Pa[i, j] < 0.05 else ""
            ax.text(j, i, f"{R[i, j]:+.2f}{star}".replace("+0.", "+.").replace("-0.", "-."), ha="center", va="center", fontsize=7, color="white" if abs(R[i, j]) > vmax * 0.65 else INK1)
    cb = fig.colorbar(im, ax=ax, shrink=0.7, pad=0.02)
    cb.outline.set_visible(False); cb.ax.tick_params(labelsize=7.8, colors=INK2, length=0)
    cb.set_label("스피어만 ρ (* = Holm 보정 p<0.05)", fontsize=8, color=INK2)
    n_sig = int((Pa < 0.05).sum())
    idx = np.unravel_index(np.nanargmax(np.abs(R)), R.shape)
    fig.text(0.012, 0.985, f"커뮤니티 활동량과 홈닥터 지원 강도의 관계는 약하다(ρ={rr[0]:+.2f}, 95% 구간 {rr[2]:+.2f}~{rr[3]:+.2f}); 가족별 관계는 {n_sig}/{R.size}개만 유의", ha="left", va="top", fontsize=12.2, color=INK1, fontweight="bold")
    fig.text(0.012, 0.925, f"왼쪽: 단지 단위 산점도. 오른쪽: 프로그램 가족 비중(행)과 홈닥터 지원 종류별 100세대당 건수(열)의 상관. 주민 대상 기록 15건 이상 {len(cm)}개 단지", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.84, wspace=0.45, left=0.07, right=0.98, bottom=0.11)
    _save(fig, out)
    return dict(rho=rr[0], lo=rr[2], hi=rr[3], p=rr[1], n=rr[4], n_sig=n_sig, n_tests=int(R.size), strongest=(fl(fams[idx[0]]), ycols[idx[1]][1], float(R[idx])),
                R=pd.DataFrame(R, index=[fl(f) for f in fams], columns=[l for _, l in ycols]))


def fig_type_supply(b, out):
    x = b[b["complex_type_id"].notna() & (b["complex_type_id"] != "T0")]
    v, t = cramers_v(x["complex_type_id"], x["supply_group"])
    t = t.reindex(columns=[c for c in ED.SUPPLY_ORDER if c in t.columns])
    pr = t.div(t.sum(axis=1), axis=0) * 100
    chi = stats.chi2_contingency(t, correction=False)
    mi = np.unravel_index(np.argmax(pr.values), pr.shape)
    mx_r, mx_c, mx_v = pr.index[mi[0]], pr.columns[mi[1]], float(pr.values[mi])
    fig, ax = plt.subplots(figsize=(7.6, 4.6), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    im = ax.imshow(pr.values, cmap=SEQ, vmin=0, vmax=max(60, pr.values.max()), aspect="auto")
    ax.set_xticks(range(pr.shape[1])); ax.set_xticklabels(pr.columns, fontsize=8.6)
    ax.set_yticks(range(pr.shape[0])); ax.set_yticklabels([f"{k} (n={int(t.loc[k].sum())})" for k in pr.index], fontsize=8.6)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(pr.shape[0]):
        for j in range(pr.shape[1]):
            ax.text(j, i, f"{pr.values[i, j]:.0f}%\n({int(t.values[i, j])})", ha="center", va="center", fontsize=7.8, color="white" if pr.values[i, j] > 35 else INK1)
    cb = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cb.outline.set_visible(False); cb.ax.tick_params(labelsize=8, colors=INK2, length=0)
    cb.set_label("행 기준 비율(%)", fontsize=8.2, color=INK2)
    fig.text(0.012, 0.985, f"커뮤니티 활동 유형 {mx_r}의 {mx_v:.0f}%가 {mx_c} 단지다(크레이머 V={v:.2f}, 카이제곱 {_fmt_p(chi[1])})", ha="left", va="top", fontsize=12.0, color=INK1, fontweight="bold")
    fig.text(0.012, 0.935, "행 = 프로그램 구성비로 나눈 단지 유형(T1~T5), 열 = 공급유형 묶음. 칸: 행 기준 비율(괄호는 단지 수)", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.86, left=0.17, right=0.98, bottom=0.1)
    _save(fig, out)
    return dict(v=v, p=float(chi[1]), n=int(len(x)), table=t, max_cell=(mx_r, mx_c, mx_v))


def fig_type_demo(b, out):
    x = b[b["complex_type_id"].notna() & (b["complex_type_id"] != "T0")].copy()
    types = sorted(x["complex_type_id"].unique())
    vars_ = [("log_households", "세대수(상용로그)", None), ("인구_60세이상_비율", "60세 이상 비율", 100), ("입주기준경과년수", "입주 후 경과 연수", None), ("hd_per100", "홈닥터 100세대당(2025)", None)]
    fig, axs = plt.subplots(1, 4, figsize=(11.6, 4.2), dpi=160, sharey=True)
    fig.patch.set_facecolor(SURFACE)
    res = {}
    for ax, (c, lab, mul) in zip(axs, vars_):
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.2, length=0)
        data = [(x.loc[x["complex_type_id"] == t, c].dropna() * (mul or 1)).values for t in types]
        bp = ax.boxplot(data, vert=False, patch_artist=True, widths=0.55, showfliers=False)
        for p in bp["boxes"]:
            p.set(facecolor=CAT[0], edgecolor=INK2, alpha=0.85)
        for m in bp["medians"]:
            m.set(color=INK1, lw=1.4)
        for w in bp["whiskers"] + bp["caps"]:
            w.set(color=INK3)
        ax.set_yticks(range(1, len(types) + 1))
        ax.set_yticklabels([f"{t} (n={len(v)})" for t, v in zip(types, data)], fontsize=8.2)
        ax.set_xlabel(lab, fontsize=8.3, color=INK2)
        kw = stats.kruskal(*[v for v in data if len(v) > 2])
        n = sum(len(v) for v in data)
        eps = max((kw.statistic - len(data) + 1) / (n - len(data)), 0)
        ax.set_title(f"{_fmt_p(kw.pvalue)}, ε²={eps:.2f}", fontsize=8.4, color=INK1, loc="left")
        res[lab] = (float(kw.pvalue), float(eps))
    axs[0].invert_yaxis()
    best = max(res, key=lambda k: res[k][1])
    fig.text(0.012, 0.985, f"단지 유형은 {J.q(best)}에서 가장 크게 갈리고(ε²={res[best][1]:.2f}), 홈닥터 지원 강도는 거의 갈리지 않는다(ε²={res['홈닥터 100세대당(2025)'][1]:.2f})", ha="left", va="top", fontsize=12.2, color=INK1, fontweight="bold")
    fig.text(0.012, 0.925, "커뮤니티 활동 구성으로 묶은 단지 유형(T1~T5)별 단지 여건 분포. 제목 아래 p=크루스칼-월리스 검정, ε²=효과 크기", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.84, wspace=0.12, left=0.07, right=0.99, bottom=0.14)
    _save(fig, out)
    return dict(res=res, best=best)


# ───────────── 07 해피콜 ─────────────
def fig_happy(d, out):
    hc = d["hc"].copy()
    hc["reliable"] = hc["n_total"] >= 30
    fig, axs = plt.subplots(1, 2, figsize=(10.2, 5.0), dpi=160, gridspec_kw=dict(width_ratios=[0.9, 1.1]))
    fig.patch.set_facecolor(SURFACE)
    for ax in axs:
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.3, length=0)
    ax = axs[0]
    bins = np.linspace(hc["overall_satisfaction"].min(), hc["overall_satisfaction"].max(), 24)
    ax.hist([hc.loc[hc["reliable"], "overall_satisfaction"], hc.loc[~hc["reliable"], "overall_satisfaction"]], bins=bins, stacked=True, color=[CAT[0], CAT[3]], edgecolor=SURFACE,
            label=[f"응답 30명 이상({int(hc['reliable'].sum())}곳)", f"30명 미만({int((~hc['reliable']).sum())}곳)"])
    ax.legend(frameon=False, fontsize=8.2, labelcolor=INK2, loc="upper left")
    ax.set_xlabel("종합만족도(점)", fontsize=8.4, color=INK2)
    ax.set_ylabel("관리소 수", fontsize=8.4, color=INK2)
    ax = axs[1]
    br = hc.groupby("branch")["overall_satisfaction"].median().sort_values()
    data = [hc.loc[hc["branch"] == k, "overall_satisfaction"].dropna().values for k in br.index]
    bp = ax.boxplot(data, vert=False, patch_artist=True, widths=0.58, showfliers=True, flierprops=dict(marker="o", ms=2.6, mfc=GRAY_N, mec="none"))
    for p in bp["boxes"]:
        p.set(facecolor=CAT[0], edgecolor=INK2, alpha=0.85)
    for m in bp["medians"]:
        m.set(color=INK1, lw=1.4)
    for w in bp["whiskers"] + bp["caps"]:
        w.set(color=INK3)
    ax.set_yticks(range(1, len(br) + 1)); ax.set_yticklabels([f"{k} ({len(v)})" for k, v in zip(br.index, data)], fontsize=8)
    ax.set_xlabel("종합만족도(점)", fontsize=8.4, color=INK2)
    kw = stats.kruskal(*[v for v in data if len(v) > 2])
    fig.text(0.012, 0.985, f"종합만족도는 중앙값 {hc['overall_satisfaction'].median():.1f}점이고, 지사 간 차이는 {'있다' if kw.pvalue < 0.05 else '뚜렷하지 않다'}({_fmt_p(kw.pvalue)})", ha="left", va="top", fontsize=12.2, color=INK1, fontweight="bold")
    fig.text(0.012, 0.925, f"2025 해피콜 관리소 {len(hc)}곳. 응답 30명 미만 관리소는 점수가 불안정하다(왼쪽 주황). 오른쪽: 지사별 분포(괄호는 관리소 수)", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.84, wspace=0.55, left=0.07, right=0.98, bottom=0.12)
    _save(fig, out)
    return dict(n=int(len(hc)), median=float(hc["overall_satisfaction"].median()), q1=float(hc["overall_satisfaction"].quantile(.25)), q3=float(hc["overall_satisfaction"].quantile(.75)),
                n_small=int((~hc["reliable"]).sum()), kw_p=float(kw.pvalue), br_hi=(br.index[-1], float(br.iloc[-1])), br_lo=(br.index[0], float(br.iloc[0])), min=float(hc["overall_satisfaction"].min()), max=float(hc["overall_satisfaction"].max()))


def fig_happy_assoc(b, out):
    x = b[b["overall_satisfaction"].notna() & (b["n_total"] >= 30)].copy()
    vs = [("log_households", "세대수(로그)"), ("인구_60세이상_비율", "60세 이상 비율"), ("입주기준경과년수", "입주 후 경과 연수"), ("평형_전용면적가중평균_㎡", "전용면적"), ("hd_per100", "홈닥터 100세대당"),
          ("커뮤니티_per1000", "커뮤니티 활동/1000세대"), ("std_richness", "프로그램 유형 수"), ("접근성_병원_500m_평균_km", "병원 거리"), ("접근성_경로당_500m_평균_km", "경로당 거리")]
    out_rows = []
    for c, l in vs:
        r = _sp(x[c], x["overall_satisfaction"])
        out_rows.append((l, *r))
    ps = holm([r[2] for r in out_rows])
    out_rows = [(*r, p) for r, p in zip(out_rows, ps)]
    out_rows.sort(key=lambda r: r[1])
    fig, ax = _base((8.4, 4.8))
    for i, (l, rho, p, lo, hi, n, pa) in enumerate(out_rows):
        sig = pa < 0.05
        ax.plot([lo, hi], [i, i], color=CAT[0], lw=1.6)
        ax.scatter([rho], [i], s=38, color=CAT[0] if sig else SURFACE, edgecolor=CAT[0], linewidth=1.4, zorder=3)
    ax.axvline(0, color=INK3, lw=0.9)
    ax.set_yticks(range(len(out_rows)))
    ax.set_yticklabels([r[0] for r in out_rows], fontsize=8.6)
    ax.set_xlabel("스피어만 ρ와 95% 부트스트랩 구간(채운 점 = Holm 보정 유의)", fontsize=8.5, color=INK2)
    ax.invert_yaxis()
    ns = int(sum(r[6] < 0.05 for r in out_rows))
    big = max(out_rows, key=lambda r: abs(r[1]))
    neg, pos = out_rows[0], out_rows[-1]
    _title(fig, f"만족도는 {J.q(neg[0])}가 클수록 낮고 {J.q(pos[0])}이 클수록 높다(보정 후 유의 {ns}/{len(out_rows)}, 최대 |ρ|={abs(big[1]):.2f})", f"해피콜 종합만족도와 단지 변수(1:1 연결 관리소 중 응답 30명 이상 {len(x)}곳). 세대수·고령·경과 연수·전용면적은 서로 강하게 얽혀 있어 각각의 독립 효과로 읽을 수 없다(탐색 분석)")
    _save(fig, out)
    return dict(n=int(len(x)), n_sig=ns, big=(big[0], float(big[1])), rows=out_rows)


# ───────────── 08 다변량·공간 ─────────────
PCA_VARS = ["log_households", "입주기준경과년수", "평형_전용면적가중평균_㎡", "평형_40㎡미만세대비율", "인구_60세이상_비율", "인구_80세이상_비율", "인구_20세미만_비율", "인구_여자_비율", "hd_per100",
            "접근성_병원_500m_평균_km", "접근성_약국_500m_평균_km", "접근성_경로당_500m_평균_km", "접근성_노인복지관_500m_평균_km", "접근성_종합사회복지관_500m_평균_km", "접근성_보건기관_500m_평균_km", "접근성_초등학교_500m_평균_km"]
PCA_LABEL = {"log_households": "세대수", "입주기준경과년수": "경과 연수", "평형_전용면적가중평균_㎡": "전용면적", "평형_40㎡미만세대비율": "40㎡미만 비율", "인구_60세이상_비율": "60세+", "인구_80세이상_비율": "80세+",
             "인구_20세미만_비율": "20세미만", "인구_여자_비율": "여자 비율", "hd_per100": "홈닥터/100세대", "접근성_병원_500m_평균_km": "병원 거리", "접근성_약국_500m_평균_km": "약국 거리",
             "접근성_경로당_500m_평균_km": "경로당 거리", "접근성_노인복지관_500m_평균_km": "노인복지관 거리", "접근성_종합사회복지관_500m_평균_km": "사회복지관 거리", "접근성_보건기관_500m_평균_km": "보건기관 거리",
             "접근성_초등학교_500m_평균_km": "초등학교 거리"}


def pca_matrix(b):
    X = b[PCA_VARS].copy()
    for c in PCA_VARS:
        if "접근성_" in c:
            X[c] = np.log10(X[c])
    X = X.fillna(X.median())
    return StandardScaler().fit_transform(X)


def fig_pca(b, out):
    Z = pca_matrix(b)
    p = PCA(n_components=8, random_state=7).fit(Z)
    sc = p.transform(Z)
    fig, axs = plt.subplots(1, 3, figsize=(12.4, 4.8), dpi=160, gridspec_kw=dict(width_ratios=[1, 1.35, 1.1]))
    fig.patch.set_facecolor(SURFACE)
    for ax in axs:
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.2, length=0)
    ev = p.explained_variance_ratio_
    axs[0].bar(range(1, 9), ev * 100, color=CAT[0], width=0.65)
    axs[0].plot(range(1, 9), np.cumsum(ev) * 100, color=INK1, lw=1.4, marker="o", ms=3.5)
    axs[0].set_xlabel("주성분", fontsize=8.4, color=INK2)
    axs[0].set_ylabel("설명 분산(%) · 선 = 누적", fontsize=8.4, color=INK2)
    ax = axs[1]
    for k in ED.SUPPLY_ORDER:
        m = (b["supply_group"] == k).values
        ax.scatter(sc[m, 0], sc[m, 1], s=14, color=SG_COLOR[k], alpha=0.75, edgecolor="none", label=k)
    ax.axhline(0, color=AXIS, lw=0.7); ax.axvline(0, color=AXIS, lw=0.7)
    ax.set_xlabel(f"PC1 ({ev[0] * 100:.0f}%)", fontsize=8.4, color=INK2)
    ax.set_ylabel(f"PC2 ({ev[1] * 100:.0f}%)", fontsize=8.4, color=INK2)
    ax.legend(frameon=False, fontsize=7.6, labelcolor=INK2, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.14), columnspacing=0.8, handletextpad=0.2)
    ax = axs[2]
    L = pd.DataFrame(p.components_[:2].T, index=[PCA_LABEL[c] for c in PCA_VARS], columns=["PC1", "PC2"])
    top = L["PC1"].abs().sort_values(ascending=False).head(9).index
    l1 = L.loc[top, "PC1"].iloc[::-1]
    ax.barh(l1.index, l1.values, color=[CAT[0] if v > 0 else CAT[1] for v in l1.values], height=0.62)
    ax.axvline(0, color=INK3, lw=0.8)
    ax.set_xlabel("PC1 적재값(파랑 +, 주황 -)", fontsize=8.4, color=INK2)
    ax.tick_params(axis="y", labelsize=8)
    n90 = int(np.searchsorted(np.cumsum(ev), 0.9) + 1) if np.cumsum(ev)[-1] >= 0.9 else 8
    fig.text(0.012, 0.985, f"단지 여건 {len(PCA_VARS)}개 변수는 소수의 축으로 요약되지 않는다: PC1~PC3 누적 {_pc(ev[:3].sum())}", ha="left", va="top", fontsize=12.2, color=INK1, fontweight="bold")
    fig.text(0.012, 0.925, "표준화한 단지 여건(규모·연령·면적·접근성·홈닥터)의 주성분분석. 접근성 거리는 로그 변환, 결측은 중앙값으로 대체. 점 색 = 공급유형 묶음", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.84, wspace=0.42, left=0.06, right=0.98, bottom=0.19)
    _save(fig, out)
    return dict(ev=[float(x) for x in ev], cum3=float(ev[:3].sum()), n90=n90, pc1_top=[(i, float(v)) for i, v in L["PC1"].reindex(L["PC1"].abs().sort_values(ascending=False).index)[:4].items()],
                pc2_top=[(i, float(v)) for i, v in L["PC2"].reindex(L["PC2"].abs().sort_values(ascending=False).index)[:3].items()], scores=sc[:, :5])


def fig_kmeans(b, scores, out):
    rows = []
    for k in range(2, 9):
        km = KMeans(n_clusters=k, n_init=10, random_state=7).fit(scores)
        rows.append((k, silhouette_score(scores, km.labels_), km.inertia_))
    best_k = max(rows, key=lambda r: r[1])[0]
    k = 5 if best_k < 3 else best_k
    km = KMeans(n_clusters=k, n_init=20, random_state=7).fit(scores)
    b = b.copy()
    b["cl"] = km.labels_
    Z = pca_matrix(b)
    zdf = pd.DataFrame(Z, columns=[PCA_LABEL[c] for c in PCA_VARS])
    zdf["cl"] = km.labels_
    prof = zdf.groupby("cl").mean()
    size = b["cl"].value_counts().sort_index()
    ordr = prof["60세+"].sort_values().index
    prof = prof.loc[ordr]
    fig, axs = plt.subplots(1, 2, figsize=(11.2, 4.9), dpi=160, gridspec_kw=dict(width_ratios=[0.55, 1.6]))
    fig.patch.set_facecolor(SURFACE)
    ax = axs[0]
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=8.2, length=0)
    ax.plot([r[0] for r in rows], [r[1] for r in rows], color=CAT[0], lw=1.8, marker="o", ms=4)
    ax.axvline(k, color=INK3, lw=0.9, ls=":")
    ax.set_xlabel("군집 수 k", fontsize=8.4, color=INK2)
    ax.set_ylabel("평균 실루엣", fontsize=8.4, color=INK2)
    ax = axs[1]
    vm = max(1.2, float(np.abs(prof.values).max()))
    im = ax.imshow(prof.values.T, cmap=DIV, vmin=-vm, vmax=vm, aspect="auto")
    ax.set_xticks(range(len(prof))); ax.set_xticklabels([f"C{i + 1}\n(n={int(size[c])})" for i, c in enumerate(prof.index)], fontsize=8.4)
    ax.set_yticks(range(prof.shape[1])); ax.set_yticklabels(prof.columns, fontsize=8)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(prof.shape[1]):
        for j in range(len(prof)):
            ax.text(j, i, f"{prof.values[j, i]:+.1f}", ha="center", va="center", fontsize=7.2, color="white" if abs(prof.values[j, i]) > vm * 0.6 else INK1)
    cb = fig.colorbar(im, ax=ax, shrink=0.75, pad=0.02)
    cb.outline.set_visible(False); cb.ax.tick_params(labelsize=7.8, colors=INK2, length=0)
    cb.set_label("군집 평균 z 점수", fontsize=8, color=INK2)
    x = b[b["complex_type_id"].notna() & (b["complex_type_id"] != "T0")]
    ari = adjusted_rand_score(x["cl"], x["complex_type_id"])
    ari_sup = adjusted_rand_score(b["cl"], b["supply_group"])
    sil = silhouette_score(scores, km.labels_)
    fig.text(0.012, 0.985, f"여건으로 묶은 단지 군집(k={k})은 경계가 약하고(실루엣 {sil:.2f}), 커뮤니티 유형과도 거의 겹치지 않는다(ARI {ari:.2f})", ha="left", va="top", fontsize=12.0, color=INK1, fontweight="bold")
    fig.text(0.012, 0.925, "PCA 상위 5개 점수에 k-평균. 왼쪽: k별 평균 실루엣(점선 = 선택 k). 오른쪽: 군집별 변수 평균(z 점수, 고령 비율 순). ARI 0=무관, 1=일치", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.84, wspace=0.45, left=0.06, right=0.98, bottom=0.13)
    _save(fig, out)
    return dict(k=int(k), sil=float(sil), ari_type=float(ari), ari_supply=float(ari_sup), best_k=int(best_k), sizes={int(a): int(c) for a, c in size.items()}, sil_by_k=rows,
                labels=pd.Series(km.labels_, index=b["complex_id"]))


def moran(x, W, n_perm=999, seed=7):
    z = x - x.mean()
    num = (W * np.outer(z, z)).sum()
    I = len(x) / W.sum() * num / (z ** 2).sum()
    rng = np.random.default_rng(seed)
    null = np.empty(n_perm)
    for i in range(n_perm):
        zp = rng.permutation(z)
        null[i] = len(x) / W.sum() * (W * np.outer(zp, zp)).sum() / (zp ** 2).sum()
    p = (1 + (np.abs(null) >= abs(I)).sum()) / (n_perm + 1)
    return float(I), float(p), float(np.percentile(null, 2.5)), float(np.percentile(null, 97.5))


def knn_weights(b, k=8):
    la, lo = b["latitude"].values, b["longitude"].values
    D = ED.haversine(la[:, None], lo[:, None], la[None, :], lo[None, :])
    np.fill_diagonal(D, np.inf)
    W = np.zeros_like(D)
    idx = np.argsort(D, axis=1)[:, :k]
    for i in range(len(b)):
        W[i, idx[i]] = 1.0 / k
    return W, D


def fig_spatial(b, out):
    W, D = knn_weights(b, 8)
    nn = np.sort(D, axis=1)[:, 0]
    vs = [("hd_per100", "홈닥터 100세대당"), ("인구_60세이상_비율", "60세 이상 비율"), ("log_households", "세대수(로그)"), ("입주기준경과년수", "입주 후 경과 연수"),
          ("커뮤니티_per1000", "커뮤니티 활동/1000세대"), ("std_richness", "프로그램 유형 수"), ("접근성_병원_500m_평균_km", "병원 거리"), ("평형_전용면적가중평균_㎡", "전용면적")]
    res = []
    for c, l in vs:
        s = b[c]
        m = s.notna().values
        if m.sum() < len(b):
            s = s.fillna(s.median())
        x = s.values.astype(float)
        if "접근성" in c:
            x = np.log10(x)
        I, p, lo, hi = moran(x, W)
        res.append((l, I, p, lo, hi))
    res.sort(key=lambda r: r[1])
    fig, axs = plt.subplots(1, 2, figsize=(10.4, 4.8), dpi=160, gridspec_kw=dict(width_ratios=[1.25, 1]))
    fig.patch.set_facecolor(SURFACE)
    for ax in axs:
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.4, length=0)
    ax = axs[0]
    for i, (l, I, p, lo, hi) in enumerate(res):
        ax.plot([lo, hi], [i, i], color=GRAY_N, lw=7, solid_capstyle="round", zorder=1)
        ax.scatter([I], [i], s=40, color=CAT[0] if p < 0.05 else SURFACE, edgecolor=CAT[0], linewidth=1.4, zorder=3)
    ax.axvline(0, color=INK3, lw=0.8)
    ax.set_yticks(range(len(res))); ax.set_yticklabels([r[0] for r in res], fontsize=8.6)
    ax.set_xlabel("Moran's I (회색 = 위치를 무작위로 섞었을 때 95% 범위)", fontsize=8.4, color=INK2)
    ax = axs[1]
    h = b["hd_per100"].values
    zc = (h - h.mean()) / h.std()
    lag = W @ zc
    ax.scatter(zc, lag, s=12, color=CAT[0], alpha=0.55, edgecolor="none")
    sl = np.polyfit(zc, lag, 1)
    xs = np.array([zc.min(), zc.max()])
    ax.plot(xs, sl[0] * xs + sl[1], color=INK1, lw=1.4)
    ax.axhline(0, color=AXIS, lw=0.7); ax.axvline(0, color=AXIS, lw=0.7)
    ax.set_xlabel("자기 값(표준화)", fontsize=8.4, color=INK2)
    ax.set_ylabel("가까운 8개 단지 평균(표준화)", fontsize=8.4, color=INK2)
    ax.set_title("홈닥터 100세대당의 모란 산점도", fontsize=8.8, color=INK1, loc="left")
    top = res[-1]
    ns = sum(r[2] < 0.05 for r in res)
    hdI = next(r for r in res if r[0] == "홈닥터 100세대당")
    fig.text(0.012, 0.985, f"공간 자기상관은 {J.q(top[0])}에서 가장 크고({top[1]:.2f}), 홈닥터 지원 강도는 약하다({hdI[1]:.2f})", ha="left", va="top", fontsize=12.0, color=INK1, fontweight="bold")
    fig.text(0.012, 0.925, f"가장 가까운 8개 단지를 이웃으로 한 공간 자기상관(순열 999회, 유의 {ns}/{len(res)}). 이웃 단지 평균과 자기 값이 비슷할수록 I가 크다 → 지역 단위 분할 검증을 검토할 근거", ha="left", va="top", fontsize=8.5, color=INK2)
    fig.subplots_adjust(top=0.84, wspace=0.4, left=0.2, right=0.98, bottom=0.14)
    _save(fig, out)
    return dict(rows=res, hd=hdI, n_sig=int(ns), nn_median=float(np.median(nn)), nn_max=float(nn.max()), top=top)


def fig_trend(b, out):
    x = b["홈닥터_2026_상반기_전년동기증감률"]
    v = x.dropna().clip(-1, 1) * 100
    fig, axs = plt.subplots(1, 3, figsize=(11.4, 4.4), dpi=160, gridspec_kw=dict(width_ratios=[1, 1, 1.1]))
    fig.patch.set_facecolor(SURFACE)
    for ax in axs:
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.3, length=0)
    ax = axs[0]
    ax.hist(v, bins=30, color=CAT[0], edgecolor=SURFACE)
    ax.axvline(0, color=INK1, lw=1)
    ax.axvline(v.median(), color=CAT[1], lw=1.4)
    ax.text(v.median() + 3, ax.get_ylim()[1] * 0.9, f"중앙값 {v.median():+.1f}%", fontsize=8.4, color=CAT[1])
    ax.set_xlabel("2026 상반기 전년 동기 대비 증감률(%, ±100%로 절단)", fontsize=8.3, color=INK2)
    ax.set_ylabel("단지 수", fontsize=8.3, color=INK2)
    ax = axs[1]
    lvl = b["hd25_support"] / b["hd25_n_months"] / b["세대수"] * 100
    m = x.notna() & lvl.notna()
    ax.scatter(lvl[m], x[m].clip(-1, 1) * 100, s=11, color=CAT[0], alpha=0.55, edgecolor="none")
    ax.axhline(0, color=AXIS, lw=0.8)
    r = _sp(lvl, x)
    ax.set_xlabel("2025년 100세대당 월평균 지원", fontsize=8.3, color=INK2)
    ax.set_ylabel("증감률(%)", fontsize=8.3, color=INK2)
    ax.set_title(f"ρ={r[0]:+.2f} (95% {r[2]:+.2f}~{r[3]:+.2f})", fontsize=8.6, color=INK1, loc="left")
    ax = axs[2]
    g = b.assign(ch=x.clip(-1, 1) * 100).groupby("지사명")["ch"].median().sort_values()
    ax.barh(g.index, g.values, color=[CAT[0] if v >= 0 else CAT[1] for v in g.values], height=0.62)
    ax.axvline(0, color=INK3, lw=0.8)
    ax.set_xlabel("지사별 중앙값(%)", fontsize=8.3, color=INK2)
    ax.tick_params(axis="y", labelsize=8)
    fig.text(0.012, 0.985, f"2026 상반기 지원은 전년 동기보다 중앙값 {v.median():+.1f}%이고, 2025년에 높았던 단지일수록 더 줄었다(ρ={r[0]:+.2f})", ha="left", va="top", fontsize=12.0, color=INK1, fontweight="bold")
    fig.text(0.012, 0.925, f"전년 동기 대비 증감률(홈닥터, {int(m.sum())}개 단지). 값이 높았던 곳이 낮아지는 평균 회귀가 섞여 있어 '감소 추세'로 단정할 수 없다", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.84, wspace=0.45, left=0.06, right=0.99, bottom=0.14)
    _save(fig, out)
    return dict(median=float(v.median()), share_down=float((x.dropna() < 0).mean()), rho=r[0], lo=r[2], hi=r[3], n=int(m.sum()), br_lo=(g.index[0], float(g.iloc[0])), br_hi=(g.index[-1], float(g.iloc[-1])))


def fig_presence(b, out):
    cols = [("커뮤니티_2025_활동횟수", "커뮤니티 활동"), ("업무협약_2025_기록건수", "업무협약"), ("일자리지원_2025_기록건수", "일자리지원"), ("거버넌스_2025_회의건수", "거버넌스 회의")]
    g = pd.DataFrame({l: b[c].notna().groupby(b["지사명"]).mean() * 100 for c, l in cols})
    g = g.loc[g.mean(axis=1).sort_values().index]
    fig, ax = _base((8.6, 5.6))
    for (c, l), col in zip(cols, CAT[:4]):
        ax.scatter(g[l], range(len(g)), s=42, color=col, label=l, zorder=3, edgecolor=SURFACE, linewidth=0.8)
    for i in range(len(g)):
        ax.plot([g.iloc[i].min(), g.iloc[i].max()], [i, i], color=GRID, lw=2, zorder=1)
    ax.set_yticks(range(len(g))); ax.set_yticklabels(g.index, fontsize=8.6)
    ax.set_xlabel("2025년 기록이 있는 단지 비율(%)", fontsize=8.5, color=INK2)
    ax.legend(frameon=False, fontsize=8.2, labelcolor=INK2, ncol=4, loc="upper center", bbox_to_anchor=(0.45, -0.08))
    tot = {l: float(b[c].notna().mean()) for c, l in cols}
    low = min(tot, key=tot.get)
    _title(fig, f"기록 유무는 항목마다 다르다: {J.q(low)}은 {_pc(tot[low])}의 단지에만 있다(커뮤니티 활동 {_pc(tot['커뮤니티 활동'])})", "지사별 2025년 기록이 있는 단지 비율. 기록이 없는 것은 0건이 아니라 '해당 기록 없음'이며, 입력 관행 차이일 수 있다", y=0.97)
    _save(fig, out)
    return dict(tot=tot, low=low)


def fig_outliers(b, out):
    cols = [("hd_per100", "홈닥터 100세대당"), ("커뮤니티_per1000", "커뮤니티 활동/1000세대")]
    fig, axs = plt.subplots(1, 2, figsize=(10.4, 5.2), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    tabs, cnts = [], []
    for ax, (c, l) in zip(axs, cols):
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8, length=0)
        x = b[["complex_id", "단지명", "지사명", c]].dropna()
        v = np.log1p(x[c]) if c != "hd_per100" else x[c]
        med = v.median()
        mad = (v - med).abs().median() * 1.4826
        x = x.assign(z=(v - med) / mad)
        t = pd.concat([x.nlargest(8, "z"), x.nsmallest(7, "z")]).sort_values("z")
        ax.barh([f"{n} ({s[:2]})" for n, s in zip(t["단지명"], t["지사명"])], t["z"], color=[CAT[1] if z > 0 else CAT[0] for z in t["z"]], height=0.62)
        ax.axvline(0, color=INK3, lw=0.8)
        ax.axvline(3.5, color=GRAY_N, lw=0.8, ls=":"); ax.axvline(-3.5, color=GRAY_N, lw=0.8, ls=":")
        ax.set_xlabel(f"{l}의 로버스트 z (점선 = ±3.5)", fontsize=8.3, color=INK2)
        ax.tick_params(axis="y", labelsize=7.8)
        t = t.assign(variable=l)
        tabs.append(t)
        cnts.append(int((x["z"].abs() > 3.5).sum()))
        ax.set_title(f"{l}: |z|>3.5인 단지 {cnts[-1]}개", fontsize=8.8, color=INK1, loc="left")
    fig.text(0.012, 0.985, f"극단값(|z|>3.5) 단지가 홈닥터 지원에서 {cnts[0]}개, 커뮤니티 활동에서 {cnts[1]}개 있어 모형에서 따로 확인해야 한다", ha="left", va="top", fontsize=12.2, color=INK1, fontweight="bold")
    fig.text(0.012, 0.935, "중앙값과 MAD(중앙값 절대편차)로 만든 로버스트 z 점수의 양 끝 15개 단지(주황 = 높음, 파랑 = 낮음). 극단값은 오류가 아닐 수 있다 → 원자료 확인 후 처리", ha="left", va="top", fontsize=8.6, color=INK2)
    fig.subplots_adjust(top=0.86, wspace=0.95, left=0.2, right=0.98, bottom=0.1)
    _save(fig, out)
    return dict(table=pd.concat(tabs))


def extra_stats(b, d):
    """보고서 본문용 추가 수치(그림 없음)."""
    S = {}
    x = b[b["hd_per100"].notna()]
    for nm, col in (("branch", "지사명"), ("supply", "supply_group")):
        gs = [g["hd_per100"].values for _, g in x.groupby(col) if len(g) > 2]
        kw = stats.kruskal(*gs)
        n = sum(len(g) for g in gs)
        S[f"hd_by_{nm}"] = (float(kw.pvalue), float(max((kw.statistic - len(gs) + 1) / (n - len(gs)), 0)))
    for nm, c in (("households", "log_households"), ("age60", "인구_60세이상_비율"), ("years", "입주기준경과년수"), ("area", "평형_전용면적가중평균_㎡")):
        r = _sp(b[c], b["hd_per100"])
        S[f"hd_rho_{nm}"] = (r[0], r[2], r[3])
    r = _sp(b["log_households"], b["resident_records_per_1000hh_year"])
    S["comm_rho_households"] = (r[0], r[2], r[3])
    r = _sp(b["인구_60세이상_비율"], b["resident_records_per_1000hh_year"])
    S["comm_rho_age60"] = (r[0], r[2], r[3])
    S["n_comm"] = int(b["in_community"].sum())
    S["n_low_data"] = int((b["low_data_flag"] == 1).sum())
    S["n_hc_exact"] = int(b["happycall_source_name"].notna().sum())
    S["n_zero_hd25"] = int((b["hd_per100"].fillna(0) == 0).sum())
    mp = d["mp"]
    S["mp_rows"] = int(len(mp))
    S["mp_observed"] = int((mp["source_observed"] == 1).sum())
    S["mp_eligible"] = int(((mp["source_observed"] == 1) & (mp["eligible_history6"] == 1)).sum())
    S["mp_splits"] = mp["suggested_split"].value_counts().to_dict()
    S["n_loc_groups"] = int(mp["모델_위치그룹"].nunique())
    S["max_loc_group"] = int(mp.groupby("모델_위치그룹")["complex_id"].nunique().max())
    return S
