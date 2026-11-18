# -*- coding: utf-8 -*-
"""심화 분석 그림(fig09~). dataviz 방법론을 따른다: 형태는 데이터의 역할로 고르고, 범주 색은 고정 순서, 순차 색은 단일 색상 밝기 순,
발산 색은 파랑↔빨강+회색 중간, 이중축 금지, 제목은 발견을 말하고 단위·정의는 부제에, 격자는 최소, 직접 라벨."""
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.lines import Line2D

from . import josa as J
from .figures import SURFACE, INK1, INK2, INK3, GRID, AXIS, CAT, SEQ, GRAY_N, GRAY_U, _base, _title, _save

DIV = LinearSegmentedColormap.from_list("div_br", ["#184f95", "#6da7ec", "#f0efec", "#ee8f8e", "#a82a29"])
GRAYLINE = "#9a9994"


def _clean(ax, grid_axis="x"):
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)


def _p(p):
    return "p<0.001" if p < 0.001 else f"p={p:.3f}"


def _plain_log_axis(ax, which="x", ticks=None):
    from matplotlib.ticker import FuncFormatter, NullLocator
    axis = ax.xaxis if which == "x" else ax.yaxis
    if ticks is not None:
        (ax.set_xticks if which == "x" else ax.set_yticks)(ticks)
    axis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}" if v >= 1 else f"{v:g}"))
    axis.set_minor_locator(NullLocator())


def _short(s, n=14):
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


# ───────────────────────── 5.1 공급 지형 ─────────────────────────
def fig_pareto(T, S, out):
    g = T["type_landscape"]
    s = S["landscape"]
    fig, ax = _base((8.4, 4.6))
    ax.fill_between(g["rank"], g["cum_share"] * 100, color="#cde2fb", linewidth=0)
    ax.plot(g["rank"], g["cum_share"] * 100, color=CAT[0], linewidth=2)
    for k, lab, dy in ((s["k50"], 50, -9), (s["k80"], 80, -9), (s["k90"], 90, -9)):
        ax.plot([k, k], [0, lab], color=INK3, linewidth=0.8, linestyle=(0, (3, 3)))
        ax.plot([0, k], [lab, lab], color=INK3, linewidth=0.8, linestyle=(0, (3, 3)))
        ax.scatter([k], [lab], s=36, color=CAT[1], zorder=4, edgecolor=SURFACE, linewidth=1.2)
        ax.text(k + 1.2, lab + dy, f"상위 {k}개 → {lab}%", fontsize=8.6, color=INK1, va="center")
    ax.set_xlim(0, len(g) + 1)
    ax.set_ylim(0, 102)
    ax.set_xlabel("표준 프로그램 유형(기록 수가 많은 순서)", fontsize=8.8, color=INK2)
    ax.set_ylabel("누적 기록 비중 %", fontsize=8.8, color=INK2)
    _clean(ax, "y")
    _title(fig, f"상위 {s['k50']}개 유형이 기록의 절반, {s['k80']}개가 80%를 채운다",
           f"주민 대상 기록 {s['total']:,}건·표준 유형 {s['n_types']}종(미분류 제외). 곡선이 가파르게 올라갈수록 소수 프로그램에 기록이 쏠린다")
    fig.subplots_adjust(top=0.84)
    return _save(fig, out)


def fig_breadth_depth(T, S, out):
    g = T["type_landscape"].copy()
    s = S["landscape"]
    fig, ax = _base((8.4, 5.2))
    sz = 24 + 900 * (g["n_records"] / g["n_records"].max())
    ax.scatter(g["adoption_rate"] * 100, g["records_per_adopter_mean"], s=sz, color=CAT[0], alpha=0.42, edgecolor=SURFACE, linewidth=1.0)
    ax.set_yscale("log")
    _plain_log_axis(ax, "y", [1, 2, 3, 5, 8, 12])
    ax.axvline(50, color=INK3, linewidth=0.8, linestyle=(0, (3, 3)))
    ax.axvline(10, color=INK3, linewidth=0.8, linestyle=(0, (3, 3)))
    ymax = g["records_per_adopter_mean"].max()
    ax.set_ylim(0.85, ymax * 1.35)
    ax.text(51, ymax * 1.25, "단지 절반 이상이 시행", fontsize=8, color=INK2, va="top")
    ax.text(11, ymax * 1.25, "10% 미만(틈새)", fontsize=8, color=INK2, va="top")
    lab = pd.concat([g.head(6), g.sort_values("records_per_adopter_mean", ascending=False).head(2)]).drop_duplicates("std_id")
    fig.canvas.draw()
    placed = []                                  # (x, y) 화면 좌표: 가까운 라벨끼리 세로로 밀어 겹침을 줄인다
    for r in lab.sort_values("records_per_adopter_mean", ascending=False).itertuples():
        px, py = ax.transData.transform((r.adoption_rate * 100, r.records_per_adopter_mean))
        dy = 8
        while any(abs((px + 10) - qx) < 190 and abs((py + dy) - qy) < 15 for qx, qy in placed):
            dy -= 15
        placed.append((px + 10, py + dy))
        ax.annotate(_short(r.std_name, 16), (r.adoption_rate * 100, r.records_per_adopter_mean), xytext=(10, dy), textcoords="offset pixels", fontsize=7.6, color=INK1,
                    bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec="none", alpha=0.85), arrowprops=dict(arrowstyle="-", color=INK3, linewidth=0.6))
    ax.set_xlim(0, 100)
    ax.set_xlabel("시행 단지 비율 % (폭)", fontsize=8.8, color=INK2)
    ax.set_ylabel("시행 단지당 기록 수 평균(깊이, 로그 눈금)", fontsize=8.8, color=INK2)
    _clean(ax, "y")
    _title(fig, f"단지 절반 이상이 하는 프로그램은 {s['n_universal']}개뿐이고, {s['n_niche']}개는 10% 미만의 단지만 한다",
           "점 하나 = 표준 유형 1개, 점 크기 = 전체 기록 수. 오른쪽 위일수록 널리 그리고 자주 한다")
    fig.subplots_adjust(top=0.86)
    return _save(fig, out)


# ───────────────────────── 5.2 시간 흐름 ─────────────────────────
def fig_monthly_profile(T, S, out):
    m = T["time_monthly"]
    s = S["time"]
    fig, ax = _base((8.4, 4.6))
    cols = {2024: CAT[2], 2025: CAT[0], 2026: CAT[1]}
    for y, c in cols.items():
        d = m[m["year"] == y]
        ax.plot(d["mth"], d["n_resident"], color=c, linewidth=2.2, marker="o", markersize=4.5, markeredgecolor=SURFACE, markeredgewidth=1.0,
                linestyle="-" if y != 2026 else (0, (4, 2)))
        if y == 2026:
            last = d.iloc[-1]
            ax.text(last["mth"] + 0.2, last["n_resident"], "2026년(1~6월)", color=INK1, fontsize=8.6, va="center")
    pk = sorted(s["peak_months"])
    ax.annotate(f"{pk[0]}·{pk[1]}월에 몰림", (pk[1], m[(m['year'] == 2025) & (m['mth'] == pk[1])]['n_resident'].iloc[0]), xytext=(-86, 14), textcoords="offset points",
                fontsize=8.4, color=INK1, arrowprops=dict(arrowstyle="-", color=INK3, linewidth=0.8))
    ax.legend(handles=[Line2D([0], [0], color=cols[2024], lw=2.2, marker="o", ms=4.5, label="2024년"), Line2D([0], [0], color=cols[2025], lw=2.2, marker="o", ms=4.5, label="2025년"),
                       Line2D([0], [0], color=cols[2026], lw=2.2, marker="o", ms=4.5, ls=(0, (4, 2)), label="2026년(1~6월)")], loc="upper right", frameon=False, fontsize=8.4, labelcolor=INK2)
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels([f"{i}월" for i in range(1, 13)])
    ax.set_xlim(0.6, 13.6)
    ax.set_ylim(0, m["n_resident"].max() * 1.12)
    ax.set_ylabel("월별 주민 대상 기록 수(시작일 기준)", fontsize=8.8, color=INK2)
    _clean(ax, "y")
    tr = sorted(s["trough_months"])
    _title(fig, f"기록은 봄({pk[0]}·{pk[1]}월)에 가장 많고 겨울({tr[0]}·{tr[1]}월)에 가장 적다",
           "같은 달을 해마다 겹쳐 본 것. 2026년(점선)은 6월까지이며 최근 달은 입력이 덜 채워졌을 수 있다(아래 보고 지연 그림)")
    fig.subplots_adjust(top=0.84)
    return _save(fig, out)


def fig_h1_dumbbell(T, S, out):
    d = T["time_fam_h1"].copy()
    s = S["time"]
    fig, ax = _base((8.4, 5.4))
    y = np.arange(len(d))
    ax.hlines(y, d["share_2025h1"] * 100, d["share_2026h1"] * 100, color="#9ec5f4", linewidth=3)
    ax.scatter(d["share_2025h1"] * 100, y, s=46, color=GRAYLINE, zorder=3, edgecolor=SURFACE, linewidth=1)
    ax.scatter(d["share_2026h1"] * 100, y, s=52, color=CAT[0], zorder=4, edgecolor=SURFACE, linewidth=1)
    xmax = float(max(d["share_2025h1"].max(), d["share_2026h1"].max()) * 100)
    for yi, (a, b, df) in enumerate(zip(d["share_2025h1"] * 100, d["share_2026h1"] * 100, d["diff_pp_25_26"])):
        ax.text(max(a, b) + 0.5, yi, ("0.0" if abs(df) < 0.05 else f"{df:+.1f}") + "%p", va="center", fontsize=8, color=INK1)
    ax.set_yticks(y)
    ax.set_yticklabels(d["family"], fontsize=8.6, color=INK1)
    ax.set_xlim(0, xmax * 1.18)
    ax.set_xlabel("상반기(1~6월) 주민 대상 기록 중 비중 %", fontsize=8.8, color=INK2)
    ax.legend(handles=[Line2D([0], [0], marker="o", ls="", color=GRAYLINE, label="2025 상반기"), Line2D([0], [0], marker="o", ls="", color=CAT[0], label="2026 상반기")],
              loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=2, frameon=False, fontsize=8.4, labelcolor=INK2)
    _clean(ax, "x")
    r0 = s["rise"][0]
    _title(fig, f"2026 상반기에는 {J.q(r0[0])}의 비중이 {r0[1]:+.1f}%p로 가장 크게 늘었다",
           "건수가 아니라 구성비로 비교했다(최근 달의 입력 지연이 모든 가족에 비슷하게 작용한다고 가정). 선이 길수록 구성이 많이 바뀐 가족")
    fig.subplots_adjust(top=0.88, bottom=0.14)
    return _save(fig, out)


def fig_reporting_lag(T, S, out):
    m = T["time_monthly"].copy()
    s = S["time"]
    fig, ax = _base((8.4, 4.4))
    x = np.arange(len(m))
    base = m["n_rows"] - m["n_added_in_update"]
    ax.bar(x, base, color="#9ec5f4", width=0.72, label="이전 스냅샷에도 있던 기록")
    ax.bar(x, m["n_added_in_update"], bottom=base, color=CAT[1], width=0.72, label="이번 갱신에서 추가된 기록")
    ticks = [i for i in range(len(m)) if m.loc[i, "mth"] in (1, 7)]
    ax.set_xticks(ticks)
    ax.set_xticklabels([m.loc[i, "month"] for i in ticks], fontsize=8.4)
    j = int(m["added_share"].idxmax())
    ax.set_ylim(0, m["n_rows"].max() * 1.32)
    ax.annotate(f"{m.loc[j, 'month']}: 기록의 {m.loc[j, 'added_share'] * 100:.0f}%가\n갱신에서 새로 추가됨", (j, m.loc[j, "n_rows"]), xytext=(-175, 62), textcoords="offset points",
                fontsize=8.4, color=INK1, arrowprops=dict(arrowstyle="-", color=INK3, linewidth=0.8))
    ax.set_ylabel("월별 기록 수(전체 범위, 시작일 기준)", fontsize=8.8, color=INK2)
    ax.legend(loc="upper left", frameon=False, fontsize=8.4, labelcolor=INK2)
    _clean(ax, "y")
    _title(fig, f"갱신으로 추가된 기록 {s['added_total']}건 중 {s['added_last6']}건이 2026년 1~6월에 몰렸다",
           f"최근 6개월은 기록의 {s['added_share_last6'] * 100:.0f}%가 갱신에서 새로 들어왔다(그 이전 24개월은 {s['added_share_before'] * 100:.2f}%). 최근 달은 입력이 늦다")
    fig.subplots_adjust(top=0.84)
    return _save(fig, out)


# ───────────────────────── 5.3 단지 간 격차·규모 ─────────────────────────
def fig_lorenz(P, T, S, out):
    cx = P["cx"]
    s = S["disp"]
    from .analysis_extra import lorenz
    fig, ax = _base((6.6, 6.0))
    x1, y1 = lorenz(cx["n_records_resident"].values)
    x2, y2 = lorenz(cx["resident_records_per_1000hh_year"].fillna(0).values)
    ax.plot([0, 1], [0, 1], color=INK3, linewidth=1, linestyle=(0, (4, 3)))
    ax.fill_between(x1, y1, x1, color="#cde2fb", linewidth=0)
    ax.plot(x1, y1, color=CAT[0], linewidth=2.2)
    ax.plot(x2, y2, color=CAT[1], linewidth=2.2)
    ax.legend(handles=[Line2D([0], [0], color=CAT[0], lw=2.2, label=f"단지별 기록 수 (지니 {s['gini_vol']:.2f})"),
                       Line2D([0], [0], color=CAT[1], lw=2.2, label=f"세대 1000당 활동량 (지니 {s['gini_int']:.2f})"),
                       Line2D([0], [0], color=INK3, lw=1, ls=(0, (4, 3)), label="완전 평등선")], loc="upper left", frameon=False, fontsize=8.6, labelcolor=INK2)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.set_xticks(np.linspace(0, 1, 6))
    ax.set_xticklabels([f"{int(t * 100)}%" for t in np.linspace(0, 1, 6)])
    ax.set_yticks(np.linspace(0, 1, 6))
    ax.set_yticklabels([f"{int(t * 100)}%" for t in np.linspace(0, 1, 6)])
    ax.set_xlabel("단지 누적 비율(기록이 적은 단지부터)", fontsize=8.8, color=INK2)
    ax.set_ylabel("기록 누적 비중", fontsize=8.8, color=INK2)
    _clean(ax, "both")
    _title(fig, f"단지 간 격차는 중간 수준(지니 {s['gini_vol']:.2f}): 상위 10% 단지가 기록의 {s['top10_vol'] * 100:.0f}%",
           f"하위 절반 단지의 몫은 {s['bottom50_vol'] * 100:.0f}%. 곡선이 대각선에서 멀수록 불평등({len(cx)}개 단지)")
    fig.subplots_adjust(top=0.88)
    return _save(fig, out)


def fig_size_scaling(P, T, S, out):
    cx = P["cx"]
    s = S["disp"]
    fig, axs = plt.subplots(1, 2, figsize=(9.4, 4.7), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    specs = [("n_records_resident", None, "기록 수", s["slope_rec"], s["slope_rec_lo"], s["slope_rec_hi"], s["r2_rec"], "records"),
             ("participants_total_sum", None, "참여인원 합", s["slope_par"], s["slope_par_lo"], s["slope_par_hi"], s["r2_par"], "participants")]
    sc = T["disp_scaling"].set_index("outcome")
    for ax, (col, _, lab, slope, lo, hi, r2, key) in zip(axs, specs):
        d = cx[(cx[col].fillna(0) > 0) & (cx["households"] > 0)]
        ax.set_facecolor(SURFACE)
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.4, length=0)
        ax.scatter(d["households"], d[col], s=16, color=CAT[0], alpha=0.5, edgecolor="none")
        row = sc.loc[lab]
        xs = np.array([d["households"].min(), d["households"].max()])
        ax.plot(xs, np.exp(row["intercept"]) * xs ** row["slope"], color=CAT[1], linewidth=2)
        ref = np.exp(np.log(d[col]).mean() - np.log(d["households"]).mean()) * xs
        ax.plot(xs, ref, color=INK3, linewidth=1, linestyle=(0, (4, 3)))
        ax.set_xscale("log")
        ax.set_yscale("log")
        _plain_log_axis(ax, "x", [100, 300, 1000, 3000])
        _plain_log_axis(ax, "y")
        ax.set_xlabel("세대수(로그 눈금)", fontsize=8.6, color=INK2)
        ax.set_ylabel(lab + "(30개월 합, 로그 눈금)", fontsize=8.6, color=INK2)
        ax.set_title(f"{lab}: 기울기 {slope:.2f} (95% 구간 {lo:.2f}~{hi:.2f})", fontsize=9.2, color=INK1, loc="left")
        ax.grid(color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
    axs[0].legend(handles=[Line2D([0], [0], color=CAT[1], lw=2, label="추정 직선"), Line2D([0], [0], color=INK3, lw=1, ls=(0, (4, 3)), label="기울기 1(세대수에 비례)")],
                  loc="upper left", frameon=False, fontsize=8, labelcolor=INK2)
    fig.text(0.012, 0.995, f"큰 단지일수록 세대당 활동은 줄고(기울기 {s['slope_rec']:.2f}), 참여인원은 세대수보다 더 빨리 는다(기울기 {s['slope_par']:.2f})", ha="left", va="top",
             fontsize=12.2, color=INK1, fontweight="bold")
    fig.text(0.012, 0.945, "점 하나 = 단지 1개. 두 축 모두 로그 눈금이라 직선의 기울기가 '세대수가 1% 늘 때 기록(참여)이 몇 % 느는가'(탄력성)", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.80, wspace=0.28, bottom=0.12)
    return _save(fig, out)


def fig_group_compare(P, T, S, out):
    main = P["main"]
    s = S["disp"]
    gs = T["disp_group_summary"]
    fig, axs = plt.subplots(1, 2, figsize=(9.4, 4.6), dpi=160, sharey=True)
    fig.patch.set_facecolor(SURFACE)
    for ax, (col, lab) in zip(axs, (("supply_group", "공급군"), ("size_tertile", "규모 3분위(S·M·L)"))):
        ax.set_facecolor(SURFACE)
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.6, length=0)
        order = list(gs[gs["factor"] == lab].sort_values("median")["group"])
        data = [main.loc[main[col] == k, "resident_records_per_1000hh_year"].dropna().values for k in order]
        vp = ax.violinplot(data, showextrema=False, widths=0.8)
        for b in vp["bodies"]:
            b.set_facecolor("#9ec5f4")
            b.set_edgecolor("none")
            b.set_alpha(0.85)
        for i, d in enumerate(data, 1):
            q1, med, q3 = np.percentile(d, [25, 50, 75])
            ax.vlines(i, q1, q3, color=CAT[0], linewidth=4)
            ax.scatter([i], [med], s=30, color=SURFACE, zorder=5, edgecolor=CAT[0], linewidth=1.5)
        ax.set_xticks(range(1, len(order) + 1))
        ax.set_xticklabels([f"{k}\n(n={len(d)})" for k, d in zip(order, data)], fontsize=8.6)
        t = s["tests"][lab]
        ax.set_title(f"{lab}: 검정 {_p(t['p'])}, 효과크기 ε²={t['epsilon2']:.2f}", fontsize=9.2, color=INK1, loc="left")
        ax.grid(axis="y", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
    axs[0].set_ylabel("세대 1000당 연 기록 수(활동량)", fontsize=8.8, color=INK2)
    t1, t2 = s["tests"]["공급군"], s["tests"]["규모 3분위(S·M·L)"]
    head = ("공급군(영구·국민·공공50)에 따른 활동량 차이는 없고" if t1["p"] >= 0.05 else "공급군에 따라 활동량이 다르고") + (", 단지 규모에 따라서는 뚜렷하게 다르다" if t2["p"] < 0.05 else ", 규모에 따른 차이도 없다")
    fig.text(0.012, 0.995, head, ha="left", va="top", fontsize=12.5, color=INK1, fontweight="bold")
    fig.text(0.012, 0.935, "바이올린 = 분포의 모양, 굵은 선 = 25~75분위, 흰 점 = 중앙값. 기록 15건 이상 단지만 비교(Kruskal-Wallis 검정)", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.80, wspace=0.08, bottom=0.14)
    return _save(fig, out)


def fig_branch(T, S, out):
    gs = T["disp_group_summary"]
    d = gs[gs["factor"] == "지사"].sort_values("median").reset_index(drop=True)
    s = S["disp"]
    fig, ax = _base((8.0, 5.2))
    y = np.arange(len(d))
    ax.hlines(y, d["ci_lo"], d["ci_hi"], color="#9ec5f4", linewidth=3)
    ax.scatter(d["median"], y, s=46, color=CAT[0], zorder=3, edgecolor=SURFACE, linewidth=1)
    ax.axvline(s["median_int"], color=INK3, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(s["median_int"] + 0.8, len(d) - 0.35, f"전체 중앙값 {s['median_int']:.0f}", fontsize=8.2, color=INK2, va="bottom")
    for yi, r in enumerate(d.itertuples()):
        ax.text(r.ci_hi + 1.0, yi, f"{r.median:.0f}  (n={r.n})", va="center", fontsize=8, color=INK1)
    ax.set_yticks(y)
    ax.set_yticklabels(d["group"], fontsize=8.8, color=INK1)
    ax.set_xlim(0, d["ci_hi"].max() * 1.22)
    ax.set_xlabel("세대 1000당 연 기록 수의 중앙값(막대 = 부트스트랩 95% 구간)", fontsize=8.8, color=INK2)
    _clean(ax, "x")
    t = s["tests"]["지사"]
    lo, hi = s["branch_lo"], s["branch_hi"]
    _title(fig, f"지사에 따라 활동량이 크게 다르다: {hi[0]} {hi[1]:.0f} 대 {lo[0]} {lo[1]:.0f}",
           f"기록 15건 이상 {s['n_main']}개 단지, 지사 {s['branch_n']}곳. 지사 간 차이 검정 {_p(t['p'])}, 효과크기 ε²={t['epsilon2']:.2f}")
    fig.subplots_adjust(top=0.88)
    return _save(fig, out)


# ───────────────────────── 5.4 단지 구성 유형 ─────────────────────────
def fig_type_profile(T, S, A, out):
    prof = A["types"]["prof"].copy()
    s = S["types"]
    var = prof.var(axis=0).sort_values(ascending=False)
    cols = list(var.index[:12])
    M = prof[cols]
    cols = sorted(cols, key=lambda c: (M[c].idxmax(), -M[c].max()))
    M = M[cols]
    fig, ax = _base((9.0, 4.6))
    ax.spines["bottom"].set_visible(False)
    norm = TwoSlopeNorm(vmin=-2.0, vcenter=0, vmax=2.0)
    im = ax.imshow(M.values, cmap=DIV, norm=norm, aspect="auto")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M.values[i, j]
            if abs(v) >= 0.5:
                ax.text(j, i, f"{v:+.1f}", ha="center", va="center", fontsize=8, color=("#ffffff" if abs(v) > 1.2 else INK1))
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([_short(c, 9) for c in cols], rotation=40, ha="right", fontsize=8.2, color=INK1)
    ax.set_yticks(range(M.shape[0]))
    ax.set_yticklabels([f"{t} ({s['sizes'].get(t, 0)}개 단지)" for t in M.index], fontsize=8.8, color=INK1)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cb.set_label("평균 대비 표준편차(z 점수)", fontsize=8.2, color=INK2)
    cb.ax.tick_params(labelsize=7.8, colors=INK2)
    cb.outline.set_visible(False)
    zmin = float(prof.max(axis=1).min())
    _title(fig, f"{s['k']}개 유형 모두 한두 가지 지표에서 평균보다 {zmin:.1f} 표준편차 이상 높다",
           "유형별 평균 z 점수(0 = 단지 전체 평균, 파랑 = 평균보다 낮음, 빨강 = 높음). 유형을 가르는 상위 12개 지표만 표시, |z|≥0.5만 숫자 표기")
    fig.subplots_adjust(top=0.84, bottom=0.26)
    return _save(fig, out)


def fig_clustermap(P, T, S, A, out):
    from matplotlib.gridspec import GridSpec
    from matplotlib.patches import Patch
    from matplotlib.colors import ListedColormap
    from . import taxonomy as TX
    a = A["types"]
    F, ro, co = a["F"], a["row_order"], a["col_order"]
    M = F.values[ro][:, co] * 100
    types = np.asarray(a["types"])[ro]
    tlist = sorted(set(types))
    tcol = {t: CAT[i] for i, t in enumerate(tlist)}
    fig = plt.figure(figsize=(8.8, 7.0), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    gs = GridSpec(1, 3, width_ratios=[0.025, 1, 0.03], wspace=0.02, left=0.08, right=0.94, top=0.84, bottom=0.2)
    ax0, ax1, axc = fig.add_subplot(gs[0]), fig.add_subplot(gs[1]), fig.add_subplot(gs[2])
    strip = np.array([tlist.index(t) for t in types])[:, None]
    ax0.imshow(strip, cmap=ListedColormap([tcol[t] for t in tlist]), aspect="auto", interpolation="nearest")
    ax0.axis("off")
    im = ax1.imshow(M, cmap=SEQ, aspect="auto", vmin=0, vmax=float(np.percentile(M, 98)), interpolation="nearest")
    labs = [TX.FAMILIES[c.replace("share_family_", "")] for c in np.asarray(a["fcols"])[co]]
    ax1.set_xticks(range(len(labs)))
    ax1.set_xticklabels([_short(l, 10) for l in labs], rotation=55, ha="right", fontsize=8.2, color=INK1)
    ax1.set_yticks([])
    for sp in ax1.spines.values():
        sp.set_visible(False)
    cb = fig.colorbar(im, cax=axc)
    cb.set_label("가족별 기록 비중 %", fontsize=8.2, color=INK2)
    cb.ax.tick_params(labelsize=7.8, colors=INK2)
    cb.outline.set_visible(False)
    fig.legend(handles=[Patch(color=tcol[t], label=f"{t} ({int((types == t).sum())}개)") for t in tlist], loc="lower center", ncol=len(tlist), frameon=False, fontsize=8.4,
               labelcolor=INK2, bbox_to_anchor=(0.5, 0.0))
    s = S["types"]
    _title(fig, f"구성비가 비슷한 단지끼리 이웃해 있다: 이웃한 단지가 같은 유형일 확률 {s['adj_same'] * 100:.0f}% (우연이면 {s['adj_chance'] * 100:.0f}%)",
           f"가족 {len(labs)}개 × 단지 {len(types)}개. 행·열 모두 위계적 군집(Ward) 순서로 정렬. 진한 칸 = 그 가족의 기록 비중이 큰 단지, 왼쪽 색띠 = 단지 유형")
    return _save(fig, out)


# ───────────────────────── 5.5 참여·비용 ─────────────────────────
def fig_participation_family(T, S, out):
    g = T["part_participation_family"].copy()
    s = S["part"]
    fig, ax = _base((8.4, 5.4))
    y = np.arange(len(g))
    ax.hlines(y, g["p10"], g["p90"], color="#9ec5f4", linewidth=1.6)
    ax.hlines(y, g["q1"], g["q3"], color=CAT[0], linewidth=7)
    ax.scatter(g["median"], y, s=30, color=SURFACE, zorder=4, edgecolor=CAT[0], linewidth=1.6)
    ax.axvline(s["median_all"], color=INK3, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(s["median_all"] * 1.04, len(g) - 0.3, f"전체 중앙값 {s['median_all']:.0f}명", fontsize=8.2, color=INK2, va="bottom")
    for yi, r in enumerate(g.itertuples()):
        ax.text(r.p90 * 1.12, yi, f"{r.median:.0f}명", va="center", fontsize=8, color=INK1)
    ax.set_xscale("log")
    _plain_log_axis(ax, "x", [3, 10, 30, 100, 300, 1000])
    ax.set_yticks(y)
    ax.set_yticklabels(g["std_family_label"], fontsize=8.8, color=INK1)
    ax.set_xlim(2, g["p90"].max() * 2.2)
    ax.set_xlabel("기록 1건의 참여인원(로그 눈금; 굵은 선 = 25~75분위, 가는 선 = 10~90분위, 흰 점 = 중앙값)", fontsize=8.6, color=INK2)
    _clean(ax, "x")
    _title(fig, f"기록 1건당 참여인원의 중앙값은 가족에 따라 {s['top_median'] / s['low_median']:.1f}배 차이난다({s['low_median']:.0f}~{s['top_median']:.0f}명)",
           f"가장 큰 가족 {J.q(s['top_family'])}, 가장 작은 가족 {J.q(s['low_family'])}. 참여인원이 있는 주민 대상 기록 기준이며 상위 1% 큰 행사({s['n_p99']}건)가 전체 참여인원의 {s['share_p99_participants'] * 100:.0f}%를 차지한다")
    fig.subplots_adjust(top=0.88)
    return _save(fig, out)


def fig_cost_share(T, S, out):
    c = T["part_cost_share"].sort_values("cost_share").reset_index(drop=True)
    s = S["part"]
    fig, ax = _base((8.4, 5.4))
    y = np.arange(len(c))
    ax.hlines(y, c["records_share"] * 100, c["cost_share"] * 100, color="#9ec5f4", linewidth=3)
    ax.scatter(c["records_share"] * 100, y, s=44, color=GRAYLINE, zorder=3, edgecolor=SURFACE, linewidth=1)
    ax.scatter(c["cost_share"] * 100, y, s=52, color=CAT[0], zorder=4, edgecolor=SURFACE, linewidth=1)
    for yi, r in enumerate(c.itertuples()):
        ax.text(max(r.records_share, r.cost_share) * 100 + 0.5, yi, f"×{r.ratio:.1f}", va="center", fontsize=8, color=INK1)
    ax.set_yticks(y)
    ax.set_yticklabels(c["std_family_label"], fontsize=8.8, color=INK1)
    ax.set_xlim(0, max(c["records_share"].max(), c["cost_share"].max()) * 100 * 1.15)
    ax.set_xlabel("비중 %  (오른쪽 숫자 = 비용 비중 ÷ 건수 비중)", fontsize=8.8, color=INK2)
    ax.legend(handles=[Line2D([0], [0], marker="o", ls="", color=GRAYLINE, label="기록 건수 비중"), Line2D([0], [0], marker="o", ls="", color=CAT[0], label="모델 추정 비용 비중")],
              loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=2, frameon=False, fontsize=8.4, labelcolor=INK2)
    _clean(ax, "x")
    n = s["top3_cost_names"]
    _title(fig, f"추정 비용으로는 {J.q(n[0])}·{J.q(n[1])}·{J.q(n[2])} 세 가족이 {s['top3_cost_share'] * 100:.0f}%를 차지한다",
           "비용은 실제 집행액이 아니라 프로그램 유형별 가정(budget_assumptions.csv)으로 추정한 값이다. 건수 비중과 비교해 어떤 가족이 '무거운'지 본다")
    fig.subplots_adjust(top=0.88, bottom=0.14)
    return _save(fig, out)


# ───────────────────────── 5.6 협력·운영 ─────────────────────────
def _heat(ax, M, rows, cols, fmt="{:.0f}", thresh=5.0, vmax=None):
    vm = vmax or float(np.percentile(M, 97))
    im = ax.imshow(M, cmap=SEQ, aspect="auto", vmin=0, vmax=vm)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M[i, j]
            if v >= thresh:
                ax.text(j, i, fmt.format(v), ha="center", va="center", fontsize=7.8, color=("#ffffff" if v > vm * 0.55 else INK1))
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([_short(c, 11) for c in cols], rotation=40, ha="right", fontsize=8.2, color=INK1)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows, fontsize=8.6, color=INK1)
    for sp in ax.spines.values():
        sp.set_visible(False)
    return im


def fig_org_family(T, S, out):
    d = T["coop_org_by_family"]
    s = S["coop"]
    rows, cols = list(d["family"]), [c for c in d.columns if c != "family"]
    M = d[cols].values * 100
    fig, ax = _base((9.0, 5.8))
    ax.spines["bottom"].set_visible(False)
    im = _heat(ax, M, rows, cols, thresh=4.0)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cb.set_label("그 협력기관이 원문에 언급된 기록 비중 %", fontsize=8.2, color=INK2)
    cb.ax.tick_params(labelsize=7.8, colors=INK2)
    cb.outline.set_visible(False)
    a, b, v = s["fam_org_best"][0]
    _title(fig, f"협력기관은 가족마다 다르다: {J.q(a)} 기록의 {v * 100:.0f}%가 {J.qgwawa(b)} 함께 언급된다",
           f"원문에 협력기관 유형이 언급된 기록은 전체의 {s['org_any'] * 100:.0f}%뿐이라 이 그림은 '언급된 협력'의 모양이다. 4% 이상인 칸에 숫자 표기")
    fig.subplots_adjust(top=0.86, bottom=0.24)
    return _save(fig, out)


def fig_ops_family(T, S, out):
    d = T["coop_ops_by_family"]
    s = S["coop"]
    rows, cols = list(d["family"]), [c for c in d.columns if c != "family"]
    M = d[cols].values * 100
    fig, ax = _base((7.6, 5.6))
    ax.spines["bottom"].set_visible(False)
    im = _heat(ax, M, rows, cols, thresh=0.5, vmax=100)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label("확정(Y)+개연(P) 비중 %", fontsize=8.2, color=INK2)
    cb.ax.tick_params(labelsize=7.8, colors=INK2)
    cb.outline.set_visible(False)
    _title(fig, f"행사형은 '{s['evt_top']}' {s['evt_top_v'] * 100:.0f}%, 정기형은 '{s['reg_top']}' {s['reg_top_v'] * 100:.0f}%로 가장 높다",
           "가족별로 운영 특성이 확정(Y) 또는 개연(P)인 기록의 비중. 운영 특성은 다중 라벨이라 한 줄의 합이 100%가 아니다")
    fig.subplots_adjust(top=0.86, bottom=0.18)
    return _save(fig, out)


# ───────────────────────── 5.7 프로그램 간 관계 ─────────────────────────
def fig_network(T, S, A, out, n_show=20):
    """리프트가 큰 프로그램 쌍(연결 수가 많은 허브가 겹쳐 보이는 네트워크 대신 막대로 그린다)."""
    e = T["rel_edges"].head(n_show).iloc[::-1].reset_index(drop=True)
    fig, ax = _base((10.0, 7.0))
    lab = [f"{_short(a, 17)}  +  {_short(b, 17)}" for a, b in zip(e["std_a_name"], e["std_b_name"])]
    cols = [CAT[0] if sm else GRAYLINE for sm in e["same_family"]]
    ax.barh(range(len(e)), e["lift"], color=cols, height=0.62)
    for y, (l, n) in enumerate(zip(e["lift"], e["n_both"])):
        ax.text(l + 0.02, y, f"{l:.2f}  (동시 {int(n)}개 단지)", va="center", fontsize=7.6, color=INK1)
    ax.axvline(1, color=INK3, lw=0.9, ls=":")
    ax.set_yticks(range(len(e)))
    ax.set_yticklabels(lab, fontsize=7.8)
    ax.set_xlim(0, e["lift"].max() * 1.32)
    ax.set_xlabel("리프트 = 함께 시행한 단지 비율 ÷ (각각의 시행 비율의 곱). 1(점선)이면 독립", fontsize=8.3, color=INK2)
    fig.legend(handles=[Line2D([0], [0], color=CAT[0], lw=6, label="같은 가족 안의 쌍"), Line2D([0], [0], color=GRAYLINE, lw=6, label="다른 가족 사이의 쌍")],
               loc="lower center", ncol=2, frameon=False, fontsize=8.6, labelcolor=INK2, bbox_to_anchor=(0.55, -0.01))
    n_diff = int(len(e) - e["same_family"].sum())
    _title(fig, f"함께 시행되는 정도가 큰 상위 {len(e)}쌍 중 {n_diff}쌍은 서로 다른 가족의 프로그램이다",
           "두 유형을 모두 20개 이상 단지에서 함께 시행한 쌍의 리프트(우연보다 얼마나 자주 함께 시행되는지) 순서")
    fig.subplots_adjust(top=0.88, bottom=0.1, left=0.4)
    return _save(fig, out)


def fig_corr(S, A, out):
    from scipy.cluster.hierarchy import linkage, leaves_list
    from scipy.spatial.distance import squareform
    R = A["rel"]["R"].copy()
    s = S["rel"]
    D = 1 - R.abs().values
    np.fill_diagonal(D, 0)
    order = leaves_list(linkage(squareform(D, checks=False), method="average"))
    R = R.iloc[order, order]
    fig, ax = _base((7.8, 6.6))
    ax.spines["bottom"].set_visible(False)
    im = ax.imshow(R.values, cmap=DIV, norm=TwoSlopeNorm(vmin=-1, vcenter=0, vmax=1))
    for i in range(len(R)):
        for j in range(len(R)):
            v = R.values[i, j]
            if i != j:
                ax.text(j, i, f"{v:.2f}".replace("0.", "."), ha="center", va="center", fontsize=6.8, color=("#ffffff" if abs(v) > 0.6 else INK1))
    ax.set_xticks(range(len(R)))
    ax.set_xticklabels(R.columns, rotation=50, ha="right", fontsize=8.2, color=INK1)
    ax.set_yticks(range(len(R)))
    ax.set_yticklabels(R.index, fontsize=8.2, color=INK1)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.set_label("스피어만 상관계수 ρ", fontsize=8.2, color=INK2)
    cb.ax.tick_params(labelsize=7.8, colors=INK2)
    cb.outline.set_visible(False)
    a, b, r = s["top_neg"][0]
    _title(fig, f"단지 지표들은 서로 얽혀 있다: {J.qgwawa(a)} {J.qeunneun(b)} 반대로 움직인다(ρ={r:.2f})",
           f"기록 15건 이상 단지의 지표 {s['n_vars']}개 간 순위상관. 파랑 = 음의 관계, 빨강 = 양의 관계. 비슷한 지표끼리 이웃하도록 정렬")
    fig.subplots_adjust(top=0.88, bottom=0.2)
    return _save(fig, out)


# ───────────────────────── 5.8 단지 여건과의 관계 ─────────────────────────
def fig_context_forest(T, S, out):
    c = T["ctx_context_corr"]
    s = S["ctx"]
    outs = list(dict.fromkeys(c["outcome"]))
    fig, axs = plt.subplots(1, len(outs), figsize=(10.4, 5.2), dpi=160, sharey=True)
    fig.patch.set_facecolor(SURFACE)
    base = c[c["outcome"] == outs[0]].sort_values("rho")
    order = list(base["context"])
    for ax, o in zip(np.atleast_1d(axs), outs):
        d = c[c["outcome"] == o].set_index("context").loc[order].reset_index()
        ax.set_facecolor(SURFACE)
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8.2, length=0)
        y = np.arange(len(d))
        ax.axvline(0, color=INK3, linewidth=0.9)
        ax.hlines(y, d["ci_lo"], d["ci_hi"], color="#9ec5f4", linewidth=2.4)
        sig = (d["p_holm"] < 0.05).values
        ax.scatter(d.loc[sig, "rho"], y[sig], s=38, color=CAT[0], zorder=3, edgecolor=SURFACE, linewidth=1)
        ax.scatter(d.loc[~sig, "rho"], y[~sig], s=38, color=SURFACE, zorder=3, edgecolor=CAT[0], linewidth=1.5)
        ax.set_xlim(-0.65, 0.65)
        ax.set_yticks(y)
        ax.set_yticklabels(d["context"], fontsize=8.4, color=INK1)
        ax.set_title(o, fontsize=8.8, color=INK1, loc="left")
        ax.grid(axis="x", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.set_xlabel("스피어만 ρ (막대 = 95% 부트스트랩 구간)", fontsize=8, color=INK2)
    fig.legend(handles=[Line2D([0], [0], marker="o", ls="", color=CAT[0], label="유의(Holm 보정 p<0.05)"),
                        Line2D([0], [0], marker="o", ls="", markerfacecolor=SURFACE, markeredgecolor=CAT[0], color=CAT[0], label="유의하지 않음")],
               loc="lower center", ncol=2, frameon=False, fontsize=8.4, labelcolor=INK2, bbox_to_anchor=(0.6, -0.02))
    st = s["strong"][0]
    short_out = {"활동량": "활동량", "프로그램 다양성": "다양성", "참여 규모": "참여 규모"}
    so = next((v for k, v in short_out.items() if st[0].startswith(k)), st[0])
    fig.text(0.012, 0.995, f"단지 여건과 활동의 관계는 대체로 약하다(가장 큰 |ρ|={abs(st[2]):.2f}: '{st[1]}' ↔ '{so}')", ha="left", va="top", fontsize=12.2, color=INK1, fontweight="bold")
    fig.text(0.012, 0.94, f"기록 15건 이상 {s['n']}개 단지, 검정 {s['n_tests']}개 중 {s['n_sig']}개가 다중 비교 보정 후에도 유의. 상관은 인과가 아니다", ha="left", va="top", fontsize=8.8, color=INK2)
    fig.subplots_adjust(top=0.82, wspace=0.12, bottom=0.17, left=0.2)
    return _save(fig, out)


def fig_regression(T, S, out):
    r = T["ctx_regression"].iloc[1:].copy()
    s = S["ctx"]
    r["lo_pct"] = (np.exp(r["ci_lo"]) - 1) * 100
    r["hi_pct"] = (np.exp(r["ci_hi"]) - 1) * 100
    r = r.sort_values("pct_change_per_sd").reset_index(drop=True)
    fig, ax = _base((8.2, 4.4))
    y = np.arange(len(r))
    ax.axvline(0, color=INK3, linewidth=0.9)
    sig = ((r["lo_pct"] > 0) | (r["hi_pct"] < 0)).values
    ax.hlines(y, r["lo_pct"], r["hi_pct"], color="#9ec5f4", linewidth=3)
    ax.scatter(r.loc[sig, "pct_change_per_sd"], y[sig], s=46, color=CAT[0], zorder=3, edgecolor=SURFACE, linewidth=1)
    ax.scatter(r.loc[~sig, "pct_change_per_sd"], y[~sig], s=46, color=SURFACE, zorder=3, edgecolor=CAT[0], linewidth=1.5)
    for yi, rr in enumerate(r.itertuples()):
        ax.text(rr.hi_pct + 1.5, yi, f"{rr.pct_change_per_sd:+.0f}%", va="center", fontsize=8.2, color=INK1)
    ax.set_yticks(y)
    ax.set_yticklabels(r["term"], fontsize=8.8, color=INK1)
    ax.set_xlabel("설명변수가 1 표준편차 커질 때 세대 1000당 활동량의 변화율 %(막대 = 95% 부트스트랩 구간)", fontsize=8.4, color=INK2)
    _clean(ax, "x")
    k = int(sig.sum())
    _title(fig, f"여건 {len(r)}개를 함께 보면 {k}개만 세대당 활동량과 뚜렷하게 연관된다(설명력 R²={s['r2']:.2f})",
           "다중 회귀(종속변수: 활동량의 로그, 설명변수: 표준화). 진한 점 = 95% 구간이 0을 포함하지 않음. 연관이지 원인이 아니다")
    fig.subplots_adjust(top=0.84)
    return _save(fig, out)


def fig_geo(P, S, out):
    cx = P["cx"]
    s = S["disp"]
    d = cx.dropna(subset=["longitude", "latitude"]).copy()
    main = d[d["low_data_flag"] == 0].copy()
    low = d[d["low_data_flag"] == 1]
    q = pd.qcut(main["resident_records_per_1000hh_year"], 5, labels=False, duplicates="drop")
    shades = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
    fig, ax = _base((6.6, 7.2))
    ax.spines["bottom"].set_visible(False)
    ax.scatter(low["longitude"], low["latitude"], s=18, color=GRAY_N, alpha=0.8, edgecolor="none", zorder=1)
    for k in range(5):
        m = main[q == k]
        ax.scatter(m["longitude"], m["latitude"], s=18 + 0.075 * m["households"], color=shades[k], alpha=0.9, edgecolor=SURFACE, linewidth=0.6, zorder=2)
    ax.set_aspect(1 / np.cos(np.radians(36)))
    ax.set_xticks([])
    ax.set_yticks([])
    edges = main["resident_records_per_1000hh_year"].quantile([0, .2, .4, .6, .8, 1]).values
    ax.legend(handles=[Line2D([0], [0], marker="o", ls="", color=shades[k], label=f"{edges[k]:.0f}~{edges[k + 1]:.0f}") for k in range(5)] + [Line2D([0], [0], marker="o", ls="", color=GRAY_N, label="기록 15건 미만")],
              title="세대 1000당 연 기록 수(5분위)", loc="lower right", frameon=False, fontsize=8, title_fontsize=8.2, labelcolor=INK2)
    hi, lo = s["branch_hi"], s["branch_lo"]
    _title(fig, f"활동량은 지역에 따라 다르다: 지사별 중앙값 {hi[0]} {hi[1]:.0f}, {lo[0]} {lo[1]:.0f}",
           "점 = 단지(크기 = 세대수, 색 = 활동량 5분위). 지도 배경 없이 위·경도만 그렸다(좌표는 단지통합 엑셀의 사용자 보정 좌표)")
    fig.subplots_adjust(top=0.9)
    return _save(fig, out)


# ───────────────────────── 전체 생성 ─────────────────────────
def make_all(R, out_dir):
    """심화 분석 그림 전체를 만든다. 반환: {'fig09': 경로, ...}"""
    P, T, S, A = R["P"], R["T"], R["S"], R["A"]
    os.makedirs(out_dir, exist_ok=True)
    f = lambda n: os.path.join(out_dir, n)
    jobs = [("fig09", lambda: fig_pareto(T, S, f("fig09_type_pareto.png"))),
            ("fig10", lambda: fig_breadth_depth(T, S, f("fig10_breadth_depth.png"))),
            ("fig11", lambda: fig_monthly_profile(T, S, f("fig11_monthly_profile.png"))),
            ("fig12", lambda: fig_h1_dumbbell(T, S, f("fig12_h1_family_shift.png"))),
            ("fig13", lambda: fig_reporting_lag(T, S, f("fig13_reporting_lag.png"))),
            ("fig14", lambda: fig_lorenz(P, T, S, f("fig14_lorenz_inequality.png"))),
            ("fig15", lambda: fig_size_scaling(P, T, S, f("fig15_size_scaling.png"))),
            ("fig16", lambda: fig_group_compare(P, T, S, f("fig16_group_violin.png"))),
            ("fig17", lambda: fig_branch(T, S, f("fig17_branch_dotplot.png"))),
            ("fig18", lambda: fig_type_profile(T, S, A, f("fig18_type_profile_heatmap.png"))),
            ("fig19", lambda: fig_clustermap(P, T, S, A, f("fig19_composition_clustermap.png"))),
            ("fig20", lambda: fig_participation_family(T, S, f("fig20_participation_by_family.png"))),
            ("fig21", lambda: fig_cost_share(T, S, f("fig21_cost_vs_records_share.png"))),
            ("fig22", lambda: fig_org_family(T, S, f("fig22_partner_by_family.png"))),
            ("fig23", lambda: fig_ops_family(T, S, f("fig23_ops_by_family.png"))),
            ("fig24", lambda: fig_network(T, S, A, f("fig24_cooccurrence_top_pairs.png"))),
            ("fig25", lambda: fig_corr(S, A, f("fig25_feature_correlation.png")))]
    if "ctx" in S:
        jobs += [("fig26", lambda: fig_context_forest(T, S, f("fig26_context_correlation.png"))),
                 ("fig27", lambda: fig_regression(T, S, f("fig27_regression_effects.png"))),
                 ("fig28", lambda: fig_geo(P, S, f("fig28_geo_activity.png")))]
    paths = {}
    for k, fn in jobs:
        paths[k] = fn()
    return paths
