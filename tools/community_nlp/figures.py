# -*- coding: utf-8 -*-
"""보고서용 그림(PNG). dataviz 방법론: 형태는 데이터의 역할로 고르고, 범주 색은 고정 순서(검증된 팔레트),
순차 색은 단일 색상 밝기 순, 이중축 금지, 제목은 발견을 말하고 단위는 부제에, 격자는 최소, 직접 라벨."""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.colors import LinearSegmentedColormap

from . import taxonomy as TX

SURFACE = "#fcfcfb"
INK1, INK2, INK3 = "#0b0b0b", "#52514e", "#7b7a76"
GRID, AXIS = "#e9e8e4", "#cfcec9"
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]   # 검증된 고정 순서
BLUE_RAMP = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
SEQ = LinearSegmentedColormap.from_list("blue_seq", BLUE_RAMP)
GRAY_N, GRAY_U = "#bdbcb6", "#e6e5e1"

for name in ("Malgun Gothic",):
    if any(f.name == name for f in fm.fontManager.ttflist):
        plt.rcParams["font.family"] = name
plt.rcParams["axes.unicode_minus"] = False


def _base(figsize=(8.4, 4.8)):
    fig, ax = plt.subplots(figsize=figsize, dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=8.5, length=0)
    return fig, ax


def _title(fig, title, sub=None, y=0.985):
    fig.text(0.012, y, title, ha="left", va="top", fontsize=12.5, color=INK1, fontweight="bold")
    if sub:
        fig.text(0.012, y - 0.065, sub, ha="left", va="top", fontsize=8.8, color=INK2)


def _save(fig, path):
    fig.savefig(path, facecolor=SURFACE, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return path


def fig_family_distribution(rows, out):
    res = rows[rows["in_resident_scope"] == 1]
    vc = res["std_family_label"].value_counts()
    vc = vc.drop(labels=[x for x in vc.index if x == TX.FAMILIES["F99"]], errors="ignore")
    s = (vc / len(res) * 100).sort_values()
    fig, ax = _base((8.4, 5.2))
    ax.barh(s.index, s.values, height=0.62, color=CAT[0])
    for y, v in enumerate(s.values):
        ax.text(v + 0.25, y, f"{v:.1f}%", va="center", fontsize=8.2, color=INK1)
    ax.set_xlim(0, s.max() * 1.15)
    ax.xaxis.set_visible(False)
    ax.tick_params(axis="y", labelsize=8.8, colors=INK1)
    top5 = float(s.values[-5:].sum())
    _title(fig, f"상위 5개 가족이 {top5:.0f}%를 차지하며 비중이 가장 작은 '{s.index[0]}'은 {s.values[0]:.1f}%",
           f"표준 프로그램 가족별 기록 비중(주민 대상 {len(res):,}건, 2024-01~2026-06). 미분류 제외")
    fig.subplots_adjust(top=0.84)
    return _save(fig, out)


def fig_ops_states(rows, out):
    res = rows[rows["in_resident_scope"] == 1]
    cols = [("상시형", "op_always"), ("정기형", "op_regular"), ("행사형", "op_event"), ("수시형", "op_adhoc"), ("계절형", "op_seasonal")]
    states = [("Y", "확정", "#184f95"), ("P", "개연", "#86b6ef"), ("N", "반증", GRAY_N), ("U", "미확인", GRAY_U)]
    fig, ax = _base((8.4, 3.9))
    for i, (lab, c) in enumerate(cols[::-1]):
        vc = res[c].value_counts(normalize=True) * 100
        left = 0.0
        for st, sl, colr in states:
            v = float(vc.get(st, 0.0))
            ax.barh(i, v, left=left, height=0.58, color=colr, edgecolor=SURFACE, linewidth=1.6)
            if v >= 6:
                ax.text(left + v / 2, i, f"{v:.0f}%", ha="center", va="center", fontsize=8.2,
                        color=("#ffffff" if st == "Y" else INK1))
            left += v
    ax.set_yticks(range(len(cols)))
    ax.set_yticklabels([c[0] for c in cols[::-1]], fontsize=9.2, color=INK1)
    ax.set_xlim(0, 100)
    ax.xaxis.set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=colr) for _, _, colr in states]
    ax.legend(handles, [f"{k} {l}" for k, l, _ in states], ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.02), frameon=False,
              fontsize=8.5, labelcolor=INK2, handlelength=1.1)
    yp = {lab: float(res[c].isin(["Y", "P"]).mean() * 100) for lab, c in cols}
    _title(fig, f"행사형은 {yp['행사형']:.0f}%가 확정·개연이지만 정기형 {yp['정기형']:.0f}%·계절형 {yp['계절형']:.0f}%·수시형 {yp['수시형']:.0f}%·상시형 {yp['상시형']:.0f}%만 근거가 있다",
           "운영 특성 5종 상태 구성(주민 대상 기록 기준). Y 확정·P 개연·N 반증·U 미확인")
    fig.subplots_adjust(top=0.80, bottom=0.13)
    return _save(fig, out)


def fig_seasonality(rows, out):
    res = rows[rows["in_resident_scope"] == 1]
    fam = res["std_family_label"].value_counts().index.tolist()
    fam = [f for f in fam if f != TX.FAMILIES["F99"]]
    mat = pd.crosstab(res["std_family_label"], res["start_month"]).reindex(index=fam, columns=range(1, 13), fill_value=0)
    mat = mat.div(mat.sum(axis=1), axis=0) * 100
    fig, ax = _base((8.4, 5.4))
    ax.spines["bottom"].set_visible(False)
    im = ax.imshow(mat.values, aspect="auto", cmap=SEQ, vmin=0, vmax=max(20, np.nanpercentile(mat.values, 98)))
    ax.set_xticks(range(12))
    ax.set_xticklabels([f"{m}월" for m in range(1, 13)], fontsize=8.5, color=INK2)
    ax.set_yticks(range(len(fam)))
    ax.set_yticklabels(fam, fontsize=8.6, color=INK1)
    for i in range(mat.shape[0]):
        for j in range(12):
            v = mat.values[i, j]
            if v >= 13:
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7.6, color=("#ffffff" if v > 15 else INK1))
    ax.set_xticks(np.arange(-.5, 12, 1), minor=True)
    ax.set_yticks(np.arange(-.5, len(fam), 1), minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=1.5)
    ax.tick_params(which="minor", length=0)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.015)
    cb.ax.tick_params(labelsize=7.5, colors=INK2, length=0)
    cb.outline.set_visible(False)
    pk = mat.max(axis=1).sort_values(ascending=False)
    f1, f2 = pk.index[0], pk.index[1]
    m1, m2 = int(mat.loc[f1].idxmax()), int(mat.loc[f2].idxmax())
    _title(fig, f"'{f1}'은 {m1}월에 {pk.iloc[0]:.0f}%, '{f2}'는 {m2}월에 {pk.iloc[1]:.0f}%가 몰려 계절성이 가장 뚜렷하다",
           "가족별 시작월 분포(각 행 합=100%, 칸 숫자는 13% 이상만 표기)")
    fig.subplots_adjust(top=0.86)
    return _save(fig, out)


def fig_complex_scatter(cf, out):
    d = cf[cf["n_records_resident"] > 0].copy()
    low = d["n_records_resident"] < 15
    fig, ax = _base((8.0, 5.0))
    ax.grid(color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.scatter(d.loc[~low, "std_richness"], d.loc[~low, "std_top1_share"] * 100, s=26, color=CAT[0], alpha=0.62, linewidth=0.8, edgecolor=SURFACE)
    ax.scatter(d.loc[low, "std_richness"], d.loc[low, "std_top1_share"] * 100, s=26, color="#9a9994", alpha=0.9, linewidth=0.8, edgecolor=SURFACE)
    ax.set_xlabel("서로 다른 표준 프로그램 유형 수(다양성)", fontsize=8.8, color=INK2)
    ax.set_ylabel("최다 유형이 차지하는 비중 %(집중도)", fontsize=8.8, color=INK2)
    ax.spines["left"].set_visible(True)
    ax.spines["left"].set_color(AXIS)
    r = d.sort_values("n_records_resident", ascending=False).head(3)
    for _, x in r.iterrows():
        ax.annotate(f"{x['complex_name']} ({int(x['n_records_resident'])}건)", (x["std_richness"], x["std_top1_share"] * 100),
                    xytext=(6, 8), textcoords="offset points", fontsize=7.8, color=INK1,
                    bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec="none", alpha=0.85))   # 점과 겹쳐도 읽히도록 배경
    ax.legend(handles=[plt.Line2D([0], [0], marker="o", ls="", color=CAT[0], alpha=0.7, label="주민 대상 기록 15건 이상"),
                       plt.Line2D([0], [0], marker="o", ls="", color="#9a9994", label="15건 미만(자료 부족)")],
              loc="upper right", frameon=False, fontsize=8.3, labelcolor=INK2)
    rho = float(d.loc[~low, ["std_richness", "std_top1_share"]].corr(method="spearman").iloc[0, 1])
    word = "쏠림이 작아진다" if rho < 0 else "쏠림이 커진다"
    _title(fig, f"운영하는 유형이 많은 단지일수록 최다 유형 쏠림이 {'작다' if rho < 0 else '크다'}(순위상관 ρ={rho:.2f})",
           f"단지별 유형 수와 최다 유형 점유율(단지 {len(d)}개; ρ는 기록 15건 이상 단지)")
    fig.subplots_adjust(top=0.84)
    return _save(fig, out)


def fig_complex_types(cf, tinfo, out, feats_for_xy=("share_purpose_P09", "ops_evt_Y_share")):
    d = cf[cf["complex_type_id"] != "T0"].copy()
    types = sorted(d["complex_type_id"].unique())
    k = len(types)
    ncol = min(3, k)
    nrow = int(np.ceil(k / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(8.8, 2.9 * nrow), dpi=160, sharex=True, sharey=True)
    fig.patch.set_facecolor(SURFACE)
    axes = np.atleast_1d(axes).ravel()
    fx, fy = feats_for_xy
    for ax, t in zip(axes, types):
        ax.set_facecolor(SURFACE)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.spines["left"].set_color(AXIS)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=7.6, length=0)
        o = d[d["complex_type_id"] != t]
        m = d[d["complex_type_id"] == t]
        ax.scatter(o[fx] * 100, o[fy] * 100, s=11, color="#d7d6d1", linewidth=0)
        ax.scatter(m[fx] * 100, m[fy] * 100, s=17, color=CAT[0], alpha=0.85, linewidth=0.6, edgecolor=SURFACE)
        ax.set_title(f"{t} · {len(m)}개 단지", fontsize=9, color=INK1, loc="left")
        ax.grid(color=GRID, linewidth=0.5)
        ax.set_axisbelow(True)
    for ax in axes[len(types):]:
        ax.axis("off")
    fig.text(0.5, 0.01, "이웃·공동체 목적 기록 비중 %", ha="center", fontsize=8.5, color=INK2)
    fig.text(0.005, 0.5, "행사형(확정) 비중 %", rotation=90, va="center", fontsize=8.5, color=INK2)
    fig.suptitle("유형 간 경계는 뚜렷하지 않다 — 단지 유형은 연속체 위의 기술적 구분",
                 x=0.012, y=1.02, ha="left", fontsize=12.5, color=INK1, fontweight="bold")
    fig.text(0.012, 0.985, f"유형별 강조(파랑) vs 나머지(회색). 평균 실루엣 {tinfo['silhouette_mean']:.2f}, 부분표본 안정성 ARI {tinfo['pick']['ari_median']:.2f}",
             ha="left", va="top", fontsize=8.8, color=INK2)
    fig.tight_layout(rect=(0.03, 0.03, 1, 0.95))
    return _save(fig, out)


def fig_gap_domains(cf, out):
    d = cf[(cf["n_records_resident"] >= 15)]
    labs = [TX.NEED_DOMAINS[k] for k in ["N1", "N2", "N3", "N4", "N5", "N6"]]
    zero = [float(d[f"gap_{k}_zero_12m"].mean() * 100) for k in ["N1", "N2", "N3", "N4", "N5", "N6"]]
    low = [float(((d[f"gap_{k}_flag"] == 1) & (d[f"gap_{k}_zero_12m"] == 0)).mean() * 100) for k in ["N1", "N2", "N3", "N4", "N5", "N6"]]
    fig, ax = _base((8.4, 4.2))
    y = np.arange(len(labs))[::-1]
    ax.barh(y, zero, height=0.56, color=CAT[0], label="최근 12개월 0건")
    ax.barh(y, low, left=zero, height=0.56, color=CAT[1], edgecolor=SURFACE, linewidth=1.6, label="0건은 아니지만 피어 그룹 하위 20%")
    for yi, a, b in zip(y, zero, low):
        ax.text(a + b + 0.8, yi, f"{a + b:.0f}%", va="center", fontsize=8.5, color=INK1)
        if a >= 5:
            ax.text(a / 2, yi, f"{a:.0f}", ha="center", va="center", fontsize=8, color="#ffffff")
        if b >= 5:
            ax.text(a + b / 2, yi, f"{b:.0f}", ha="center", va="center", fontsize=8, color=INK1)
    ax.set_yticks(y)
    ax.set_yticklabels(labs, fontsize=9, color=INK1)
    ax.set_xlim(0, max(np.array(zero) + np.array(low)) * 1.18)
    ax.xaxis.set_visible(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=2, frameon=False, fontsize=8.3, labelcolor=INK2)   # 가장 긴 막대와 겹치지 않도록 축 아래
    tot = {l: a + b for l, a, b in zip(labs, zero, low)}
    top_l = max(tot, key=tot.get)
    _title(fig, f"공급 공백은 '{top_l}' 분야에서 가장 흔하다({tot[top_l]:.0f}% 단지)",
           f"필요 분야별 공급 공백 단지 비율(주민 대상 기록 15건 이상 단지 {len(d)}개). 공백은 필요의 정답이 아니라 공급 신호")
    fig.subplots_adjust(top=0.82, bottom=0.12)
    return _save(fig, out)


def fig_validation(val, out):
    """val: dict(name -> compare 결과). 필드별 일치도(두 표본이 있으면 두 시리즈)."""
    items = [("범위(scope) 정확도", "scope_acc"), ("표준 유형 정확도", "std_acc_valid"), ("유형 가족 정확도", "family_acc_valid"),
             ("주 목적 정확도", "purpose_primary_acc")]
    ops_labels = {"ALW": "상시형", "REG": "정기형", "EVT": "행사형", "ADH": "수시형", "SEA": "계절형"}
    names = list(val.keys())
    fig, ax = _base((8.4, 5.2))
    rows_y = []
    for lab, key in items:
        rows_y.append((lab, [val[n][key] * 100 for n in names]))
    for k, lab in ops_labels.items():
        rows_y.append((f"{lab} 이진 일치(Y·P vs N·U)", [float(val[n]["ops_table"].set_index("op").loc[k, "binary_YP_agree"]) * 100 for n in names]))
    n_rows = len(rows_y)
    h = min(0.5, 0.86 / len(names))
    for j, nme in enumerate(names):
        ys = np.arange(n_rows)[::-1] + (j - (len(names) - 1) / 2) * h
        vals = [r[1][j] for r in rows_y]
        ax.barh(ys, vals, height=h * 0.92, color=CAT[j], label=nme)
        for yy, v in zip(ys, vals):
            ax.text(v + 0.8, yy, f"{v:.0f}", va="center", fontsize=7.8, color=INK1)
    ax.set_yticks(np.arange(n_rows)[::-1])
    ax.set_yticklabels([r[0] for r in rows_y], fontsize=8.6, color=INK1)
    ax.set_xlim(0, 108)
    ax.xaxis.set_visible(False)
    if len(names) > 1:
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.03), ncol=len(names), frameon=False, fontsize=8.3, labelcolor=INK2)
    last = names[-1]
    _title(fig, f"독립 LLM 라벨러와 일치: 범위 {val[last]['scope_acc'] * 100:.0f}%·유형 가족 {val[last]['family_acc_valid'] * 100:.0f}%·표준 유형 {val[last]['std_acc_valid'] * 100:.0f}%",
           "일치율 %. 라벨러는 규칙 결과를 보지 못한 채 원문을 직접 읽고 판정")
    fig.subplots_adjust(top=0.84, bottom=0.10)
    return _save(fig, out)


def fig_budget(rows, out):
    res = rows[(rows["in_resident_scope"] == 1) & (rows["est_cost_mid_krw"] > 0)]
    g = res.groupby("std_family_label")["est_cost_mid_krw"].agg(["median", lambda s: s.quantile(0.1), lambda s: s.quantile(0.9), "size"])
    g.columns = ["med", "p10", "p90", "n"]
    g = g[g["n"] >= 30].sort_values("med")
    fig, ax = _base((8.4, 5.0))
    y = np.arange(len(g))
    ax.hlines(y, g["p10"] / 1e4, g["p90"] / 1e4, color="#9ec5f4", linewidth=3.2)
    ax.scatter(g["med"] / 1e4, y, s=34, color=CAT[0], zorder=3, linewidth=0.8, edgecolor=SURFACE)
    for yi, (m, a, b) in enumerate(zip(g["med"] / 1e4, g["p10"] / 1e4, g["p90"] / 1e4)):
        ax.text(b + 1.5, yi, f"{m:,.0f}만", va="center", fontsize=8, color=INK1)
    ax.set_yticks(y)
    ax.set_yticklabels(g.index, fontsize=8.6, color=INK1)
    ax.set_xlabel("건당 직접 운영비 추정(만원, 점=중앙값, 선=10~90분위)", fontsize=8.6, color=INK2)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    _title(fig, f"모델 추정: 건당 운영비 중앙값은 '{g.index[-1]}' {g['med'].iloc[-1] / 1e4:,.0f}만원으로 가장 크고 '{g.index[0]}' {g['med'].iloc[0] / 1e4:,.0f}만원으로 가장 작다",
           "표준 프로그램 가족별 건당 가상 예산(시장가 기준 추정치이며 실제 집행액이 아님)")
    fig.subplots_adjust(top=0.84)
    return _save(fig, out)


def make_all(res, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    P = lambda f: os.path.join(out_dir, f)
    paths = []
    rows, cf = res["rows"], res["cf"]
    paths.append(fig_family_distribution(rows, P("fig01_std_family_distribution.png")))
    paths.append(fig_ops_states(rows, P("fig02_ops_states.png")))
    paths.append(fig_seasonality(rows, P("fig03_family_seasonality.png")))
    paths.append(fig_complex_scatter(cf, P("fig04_complex_diversity_concentration.png")))
    paths.append(fig_complex_types(cf, res["tinfo"], P("fig05_complex_types.png")))
    paths.append(fig_gap_domains(cf, P("fig06_supply_gap_by_need_domain.png")))
    paths.append(fig_budget(rows, P("fig07_estimated_budget_by_family.png")))
    vsel = {}
    for k, v in (res.get("val") or {}).items():
        if k.startswith("B("):
            vsel[k.replace("B(독립 표본, ", "B 독립 표본 · ")[:-1]] = v
    vf = res.get("val_final") or {}
    for k, v in vf.items():
        if k.startswith("C("):
            vsel[k.replace("C(갱신분 신규 문구 표본, ", "C 갱신분 신규 문구(규칙 high 확신) · ")[:-1]] = v
    for k, v in vf.items():            # 마지막 시리즈 = B 최종 라벨(그림 제목에 쓰임)
        if k.startswith("B("):
            vsel[k.replace("B(독립 표본, ", "B 독립 표본 · ")[:-1]] = v
    if vsel:
        paths.append(fig_validation(vsel, P("fig08_llm_validation_agreement.png")))
    return paths
