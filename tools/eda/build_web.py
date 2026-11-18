# -*- coding: utf-8 -*-
"""분석 결과 웹 페이지(단일 HTML) 생성: 문제정의·단지 지도/탐색기·단지 현황(EDA)·커뮤니티 프로그램(NLP).

- 차트는 Plotly(cdnjs)로 그리고, 데이터와 차트 정의는 페이지 안에 JSON으로 넣는다(외부 요청 없음, 지도 배경도 내장 외곽선).
- 모든 문장 속 수치는 이 스크립트가 계산한 값에서 만든다.
사용: python build_web.py <EDA 출력 폴더>   → <폴더>/web/index.html
선행: run_eda.py, run_problem.py, korea_outline.py 결과가 있어야 한다.
"""
import json
import math
import os
import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

import eda_data as ED
import eda_figs as F
import problem_def as P
import web_extra as WX
from community_nlp import taxonomy as TX

OUT = sys.argv[1]
ROOT = r"C:/Users/user/Desktop/2026 DRIVE/project/data/"
NLP_AN = ROOT + "archive/processed_support_20261117_v1/community_nlp_2026_v1/analysis/"
TAB = os.path.join(OUT, "tables")
PTAB = os.path.join(OUT, "problem_definition", "tables")
rd = lambda p, **k: pd.read_csv(p, encoding="utf-8-sig", low_memory=False, **k)

CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
HI = "#e34948"
GRAYC = "#a9adb6"
SEQ = [[0, "#d7e6fa"], [0.5, "#5b9be6"], [1, "#163f7a"]]
DIV = [[0, "#184f95"], [0.25, "#6da7ec"], [0.5, "#eeeeea"], [0.75, "#ee8f8e"], [1, "#a82a29"]]
SUPPLY_COLOR = dict(zip(ED.SUPPLY_ORDER, CAT[:5]))


# ───────── 직렬화 도우미 ─────────
def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        if math.isnan(f) or math.isinf(f):
            return None
        return float(f"{f:.5g}")
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if isinstance(o, pd.Series):
        return clean(o.tolist())
    if o is pd.NA or o is pd.NaT:
        return None
    return o


def L(s):
    return [None if (isinstance(v, float) and math.isnan(v)) else v for v in s]


def fig(traces, **layout):
    return dict(data=traces, layout=layout)


def ax(title=None, **kw):
    d = dict(kw)
    if title:
        d["title"] = dict(text=title)
    return d


FIGS, SECTIONS = {}, []


def card(sec, cid, title, body, figs=(), note=None, wide=False, html=None, height=None):
    sec["cards"].append(dict(id=cid, title=title, body=body, figs=list(figs), note=note, wide=wide, html=html, height=height))


def pc(x, d=0):
    return f"{x * 100:.{d}f}%"


# ───────── 자료 ─────────
D = P.load()
b = D["b"].copy()
b = F.add_derived(b) if "hd_per100" not in b.columns else b
S_eda = pickle.load(open(os.path.join(TAB, "summary_values.pkl"), "rb"))
S = pickle.load(open(os.path.join(PTAB, "problem_summary.pkl"), "rb"))
cf, sd, ml, r, pa, master = D["cf"], D["sd"], D["ml"], D["r"], D["pa"], D["master"]
b["comm_per1000"] = b["n_res"] / 2.5 / b["세대수"] * 1000
b["pct_60"] = b["인구_60세이상_비율"] * 100
nm = dict(zip(b["complex_id"], b["단지명"]))
ns = rd(os.path.join(PTAB, "need_supply_index.csv"))
gapt = rd(os.path.join(PTAB, "peer_gap_by_complex.csv"))
nbt = rd(os.path.join(PTAB, "context_neighbors_k10.csv"))
DEM = WX.demand(pa)
b = b.merge(ns[["complex_id", "need_pct", "supply_pct"]], on="complex_id", how="left").merge(gapt[["complex_id", "n_gap"]], on="complex_id", how="left")


def hover_cx(extra):
    return "<b>%{customdata[0]}</b><br>%{customdata[1]} · %{customdata[2]}<br>세대수 %{customdata[3]:,}" + extra + "<extra></extra>"


def cxdata(x, *cols):
    base = [x["단지명"], x["지사명"], x["supply_group"], x["세대수"].fillna(0).astype(int)]
    return np.column_stack(base + [x[c] for c in cols]).tolist()


# ═════════ 1. 한눈에 보기 ═════════
bg = S["bg"]
overview = dict(id="overview", label="한눈에 보기", title="단지마다 다른 필요, 비슷하게 정해지는 프로그램",
                lead=(f"주택관리공단이 관리하는 공공임대 {bg['n']}개 단지({bg['households']:,.0f}세대, 주민 {bg['pop']:,.0f}명)의 단지 자료와 "
                      f"2024년 1월~2026년 6월 커뮤니티 활동 기록 {S['fields']['n']:,}건을 함께 분석했습니다. "
                      "질문은 하나입니다. 복지 프로그램은 각 단지의 필요에 맞게 정해지고 있는가?"),
                stats=[dict(v=f"{bg['n']}", u="개 단지", d="공단 관리 공공임대"), dict(v=f"{bg['households'] / 10000:.1f}", u="만 세대", d=f"주민 {bg['pop'] / 10000:.1f}만 명"),
                       dict(v=pc(bg["old_share"]), u="", d="주민 중 60세 이상"), dict(v=f"{S['fields']['n']:,}", u="건", d="커뮤니티 활동 기록(30개월)"),
                       dict(v=f"{S['names']['n_std']}", u="종", d="표준 프로그램으로 정리"), dict(v=f"{S['names']['n_titles']:,}", u="가지", d="그 프로그램들의 서로 다른 제목")],
                problems=[
                    dict(k="1", name="근거", q="단지에 무엇이 필요한지 재고 정하는가?",
                         a=f"고령 비율이 {S['eld']['gap_pop']:.0f}%p 높은 단지도 어르신 프로그램 비중은 {S['eld']['gap_prog']:.0f}%p만 높다. 프로그램 구성은 주민 여건으로 거의 설명되지 않는다.", go="p-eld"),
                    dict(k="2", name="기준", q="필요가 큰 곳에 더 많이 가는가?",
                         a=f"세대수가 {S['size']['hh_ratio']:.1f}배인 단지도 프로그램은 {S['size']['rec_ratio']:.1f}배. 필요와 공급의 관계는 약하다(ρ={S['ns']['rho']['rho']:+.2f}).", go="p-size"),
                    dict(k="3", name="도달", q="필요한 가구에 닿았는지 아는가?",
                         a=f"기록의 {pc(S['unit']['complex_wide'])}는 단지 전체 행사이고, 대상을 적은 기록은 {pc(S['unit']['explicit'])}. 중앙값 단지는 30개월 중 {30 - S['mon']['median']:.0f}개월이 비었다.", go="p-unit"),
                    dict(k="4", name="학습", q="결과가 쌓여 다음 선정이 나아지는가?",
                         a=f"같은 프로그램이 평균 {S['names']['per_std']:.0f}가지 제목으로 기록되고, 참여·만족 같은 결과 항목이 없다. 활동량은 복지 만족도와 무관했다.", go="p-names"),
                ],
                opportunity=f"주민 구성이 비슷한 이웃 단지 10곳 중 절반 이상이 하는데 이 단지는 하지 않은 프로그램이 단지마다 중앙값 {S['gap']['median']:.0f}개 있습니다. 이 목록이 온터가 검토 후보로 제시하는 출발점입니다.",
                cards=[])
SECTIONS.append(overview)

# ═════════ 2. 문제정의 ═════════
sec = dict(id="problem", label="문제정의", title="복지 프로그램 선정·배분의 네 가지 문제",
           lead="네 문제(근거·기준·도달·학습)를 공단 단지 자료로 하나씩 확인했습니다. 점에 마우스를 올리면 단지 이름과 값이 보입니다. 상관은 원인을 증명하지 않으며, 프로그램 기록은 '공급의 기록'이지 필요의 정답이 아닙니다.",
           cards=[])
SECTIONS.append(sec)

# p01 배경
x = b["pct_60"].dropna()
edges = np.arange(0, 101, 5)
cnt, _ = np.histogram(x, bins=edges)
FIGS["p01"] = fig([dict(type="bar", x=(edges[:-1] + 2.5).tolist(), y=cnt.tolist(), width=4.4, marker=dict(color=CAT[0]),
                        customdata=[[f"{a}~{a + 5}%"] for a in edges[:-1]], hovertemplate="60세 이상 비율 %{customdata[0]}<br>단지 %{y}곳<extra></extra>")],
                  xaxis=ax("단지 주민 가운데 60세 이상 비율(%)", range=[0, 100]), yaxis=ax("단지 수"),
                  shapes=[dict(type="line", x0=bg["med"], x1=bg["med"], y0=0, y1=1, yref="paper", line=dict(dash="dash", width=1.5))],
                  annotations=[dict(x=bg["med"], y=1, yref="paper", text=f"중앙값 {bg['med']:.0f}%", showarrow=False, xanchor="left", yanchor="top", xshift=6)])
card(sec, "p-bg", "같은 공공임대라도 단지마다 주민 구성이 크게 다르다",
     f"60세 이상 비율은 하위 10% 단지 {bg['p10']:.0f}% 이하, 상위 10% 단지 {bg['p90']:.0f}% 이상으로 두 배 넘게 차이 납니다. 봉우리가 둘인 것은 젊은 가구가 많은 국민임대와 고령 가구가 많은 영구임대가 섞여 있기 때문입니다. 필요가 단지마다 다르다는 출발점입니다.",
     ["p01"], note="자료: 단지 통합표 인구 구성")

# p02 고령 vs 어르신 프로그램
x = b[(b["n_res"] >= 15) & b["pct_60"].notna() & b["eld_share"].notna()].copy()
tr = []
for g in ED.SUPPLY_ORDER:
    s = x[x["supply_group"] == g]
    if len(s) == 0:
        continue
    tr.append(dict(type="scatter", mode="markers", name=f"{g}({len(s)})", x=L(s["pct_60"]), y=L(s["eld_share"] * 100),
                   marker=dict(color=SUPPLY_COLOR[g], size=np.clip(np.sqrt(s["세대수"]) / 2.6, 5, 22).tolist(), opacity=0.8, line=dict(width=0.6, color="#ffffff")),
                   customdata=cxdata(s, "pct_60", "eld_share", "n_res"),
                   hovertemplate=hover_cx("<br>60세 이상 %{customdata[4]:.0f}%<br>어르신 대상 프로그램 %{customdata[5]:.0%}<br>주민 대상 기록 %{customdata[6]}건")))
e = S["eld"]
anns = []
for lab, xx, yy in [("고령 하위 25%", e["lo_pop"] * 100, e["lo_prog"] * 100), ("고령 상위 25%", e["hi_pop"] * 100, e["hi_prog"] * 100)]:
    tr.append(dict(type="scatter", mode="lines", x=[xx - 6, xx + 6], y=[yy, yy], line=dict(color="#222", width=3), hoverinfo="skip", showlegend=False))
    anns.append(dict(x=xx, y=yy, text=f"<b>{lab} 중앙값 {yy:.0f}%</b>", showarrow=True, arrowhead=0, ax=0, ay=-150 if yy > 42 else 120, bg=True))
FIGS["p02"] = fig(tr, xaxis=ax("단지 주민 가운데 60세 이상 비율(%)"), yaxis=ax("어르신 대상 프로그램 비중(%)", range=[0, 100]), legend=dict(title=dict(text="공급유형(단지 수)")), annotations=anns)
card(sec, "p-eld", f"고령 비율이 {e['gap_pop']:.0f}%p 높은 단지도 어르신 프로그램 비중은 {e['gap_prog']:.0f}%p만 높다",
     f"고령 비율 하위 25% 단지(중앙값 {e['lo_pop'] * 100:.0f}%)와 상위 25% 단지(중앙값 {e['hi_pop'] * 100:.0f}%)를 비교하면, 어르신 대상 프로그램 비중은 {e['lo_prog'] * 100:.0f}%와 {e['hi_prog'] * 100:.0f}%입니다. "
     f"관계는 약하고(순위상관 {e['rho']['rho']:+.2f}, 95% 구간 {e['rho']['lo']:+.2f}~{e['rho']['hi']:+.2f}), 기록 문구에 어르신을 직접 적은 비중만 보면 관계가 없습니다(ρ={e['rho_explicit']['rho']:+.2f}).",
     ["p02"], note="어르신 대상 = 기록 문구에 고령층이 명시됐거나 프로그램 유형의 기본 대상이 고령층. 주민 대상 기록 15건 이상 단지", wide=True, height=520)

# p03 홈닥터 필요 vs 프로그램 영역
x = b[(b["n_res"] >= 15) & b["hd25_의료지원_share"].notna()].copy()
for key, a_, c_, xl, yl in [("p03a", "hd25_의료지원_share", "cf_N3", "홈닥터 지원 중 의료지원 비중(%)", "건강·돌봄 영역 프로그램 비중(%)"),
                            ("p03b", "hd25_경제지원_share", "cf_N2", "홈닥터 지원 중 경제지원 비중(%)", "생활·경제 영역 프로그램 비중(%)")]:
    FIGS[key] = fig([dict(type="scatter", mode="markers", x=L(x[a_] * 100), y=L(x[c_] * 100), marker=dict(color=CAT[0], size=7, opacity=0.65, line=dict(width=0.5, color="#ffffff")),
                          customdata=cxdata(x, a_, c_), hovertemplate=hover_cx(f"<br>{xl.split('(')[0]} %{{customdata[4]:.0%}}<br>{yl.split('(')[0]} %{{customdata[5]:.0%}}"))],
                    xaxis=ax(xl), yaxis=ax(yl), showlegend=False)
h = S["hdp"]
card(sec, "p-hd", "홈닥터가 확인한 필요와 그 단지의 프로그램 구성은 따로 움직인다",
     f"홈닥터(주거복지 현장 지원)에서 의료지원이 많은 단지라고 건강·돌봄 프로그램이 많지 않습니다(ρ={h['rho_의료']['rho']:+.2f}, 95% 구간 {h['rho_의료']['lo']:+.2f}~{h['rho_의료']['hi']:+.2f}). "
     f"경제지원과 생활·경제 프로그램도 같습니다(ρ={h['rho_경제']['rho']:+.2f}). 이미 쌓인 현장 기록이 프로그램 선정에 쓰이지 않고 있다는 신호입니다.",
     ["p03a", "p03b"], note=f"홈닥터 2025년 지원 내용 구성비 × NLP가 분류한 프로그램 필요 영역 비중. n={h['n']}", wide=True)

# 주민 수요 vs 공급
vs = pd.DataFrame(DEM["vs"]).sort_values("demand_share")
FIGS["p03c"] = fig([dict(type="bar", orientation="h", y=vs["k"].tolist(), x=(vs["demand_share"] * 100).tolist(), name="주민이 원한다고 답한 비중", marker=dict(color=CAT[1]),
                         customdata=vs["demand_pct"].tolist(), hovertemplate="%{y}<br>응답 비중 %{x:.1f}% (응답자의 %{customdata:.1f}%가 선택)<extra>주민 수요</extra>"),
                    dict(type="bar", orientation="h", y=vs["k"].tolist(), x=(vs["supply_share"] * 100).tolist(), name="실제 프로그램 기록 비중", marker=dict(color=CAT[0]),
                         customdata=[" · ".join(p_) for p_ in vs["purposes"]], hovertemplate="%{y}<br>프로그램 기록 비중 %{x:.1f}%<br>(주 목적: %{customdata})<extra>공급</extra>")],
                   barmode="group", xaxis=ax("비중(%)"), yaxis=ax(automargin=True), legend=dict(orientation="h", y=-0.15))
vsi = vs.set_index("k")
rl = DEM["pops"]["residential_life_support_service_users"]
card(sec, "p-demand", f"주민이 원한다는 '경제적 지원'은 수요의 {vsi.loc['경제적 지원', 'demand_share'] * 100:.0f}%인데 공급은 {vsi.loc['경제적 지원', 'supply_share'] * 100:.0f}%, '일자리'는 {vsi.loc['일자리', 'demand_share'] * 100:.0f}% 대 {vsi.loc['일자리', 'supply_share'] * 100:.0f}%",
     f"2025 해피콜에서 주거생활지원 서비스 이용자 {rl['n']}명이 '앞으로 필요한 복지 서비스'로 고른 항목(복수 응답)을 응답 비중으로 바꾸고, 같은 분류로 묶은 실제 프로그램 기록의 비중과 나란히 놓았습니다. "
     "주거환경 개선은 수요와 공급이 비슷하지만, 경제적 지원과 일자리는 공급이 수요에 크게 못 미칩니다. 이웃 소통·신체건강·정신건강은 공급 비중이 수요보다 큽니다.",
     ["p03c"], note="수요: 해피콜 보고서의 전국 응답(공단 외 관리 단지 포함 가능), 복수 응답을 합이 100%가 되도록 환산. 공급: 주민 대상 기록의 주 목적(NLP) 비중. 두 분류의 대응은 분석자가 정한 것이며, '기타' 목적(환경·교육·정보연계 등) 기록은 제외", wide=True, height=440)

# p04 무엇이 설명하나
t = rd(os.path.join(PTAB, "program_mix_explained_r2.csv")).sort_values("r2_resident")
cv = rd(os.path.join(PTAB, "program_mix_vs_context_distance.csv"))
FIGS["p04a"] = fig([dict(type="bar", orientation="h", y=t["label"].tolist(), x=(t["r2_resident"].clip(lower=0) * 100).tolist(), name="주민·단지 여건", marker=dict(color=CAT[0]),
                         customdata=(t["r2_resident"] * 100).tolist(), hovertemplate="%{y}<br>주민·단지 여건 R² %{customdata:.1f}%<extra></extra>"),
                    dict(type="bar", orientation="h", y=t["label"].tolist(), x=(t["r2_branch"].clip(lower=0) * 100).tolist(), name="관할 지사", marker=dict(color=CAT[1]),
                         customdata=(t["r2_branch"] * 100).tolist(), hovertemplate="%{y}<br>관할 지사 R² %{customdata:.1f}%<extra></extra>")],
                   barmode="group", xaxis=ax("설명되는 몫(교차검증 R², %; 0 미만은 0)"), yaxis=ax(automargin=True), legend=dict(orientation="h", y=-0.15))
FIGS["p04b"] = fig([dict(type="scatter", mode="lines+markers", x=cv["q"].tolist(), y=(cv["same"] * 100).tolist(), name="같은 지사 단지끼리", line=dict(color=CAT[1], width=2.5),
                         hovertemplate="여건 차이 %{x}분위<br>프로그램 구성 차이 %{y:.1f}%<extra>같은 지사</extra>"),
                    dict(type="scatter", mode="lines+markers", x=cv["q"].tolist(), y=(cv["diff"] * 100).tolist(), name="다른 지사 단지끼리", line=dict(color=CAT[0], width=2.5),
                         hovertemplate="여건 차이 %{x}분위<br>프로그램 구성 차이 %{y:.1f}%<extra>다른 지사</extra>")],
                   xaxis=ax("두 단지의 주민·단지 여건 차이(1=가장 비슷, 5=가장 다름)", dtick=1), yaxis=ax("두 단지의 프로그램 구성 차이(%)", range=[0, 70]), legend=dict(orientation="h", y=-0.2))
x_ = S["exp"]
card(sec, "p-explain", "프로그램 구성은 주민 여건으로 거의 설명되지 않고, 설명되는 부분은 오히려 지사 쪽이다",
     f"15개 프로그램 영역 비중을 주민·단지 여건(고령·아동 비율, 규모, 연식, 면적, 공급유형)으로 예측하면 {x_['n_low']}개 영역에서 설명력이 10% 미만입니다. "
     f"가장 잘 설명되는 '{x_['max_res'][0]}'도 {x_['max_res'][1] * 100:.0f}%이고, 같은 영역을 관할 지사로 예측하면 {x_['max_branch'][1] * 100:.0f}%입니다. "
     f"오른쪽: 여건이 가장 비슷한 두 단지도 프로그램 구성이 {x_['d_sim'] * 100:.0f}% 다르고, 가장 다른 두 단지({x_['d_far'] * 100:.0f}%)와 큰 차이가 없습니다. 어떤 프로그램을 하는지는 주민보다 현장 관행에 달려 있다는 해석과 맞습니다.",
     ["p04a", "p04b"], note="교차검증 R²: 5겹 릿지 회귀(처음 보는 단지를 얼마나 맞히나). 구성 차이: Bray–Curtis 거리. 주민 대상 기록 15건 이상 단지", wide=True, height=480)

# p05 규모
g = rd(os.path.join(PTAB, "supply_by_size_bin.csv"))
sz = S["size"]
FIGS["p05a"] = fig([dict(type="bar", x=g["size_bin"].tolist(), y=g["per1000"].tolist(), marker=dict(color=[CAT[0] if v == g["per1000"].max() else "#9ec3ef" for v in g["per1000"]]),
                         text=[f"{v:.0f}건" for v in g["per1000"]], textposition="outside", customdata=np.column_stack([g["n"], g["per_year"], g["hh"]]).tolist(),
                         hovertemplate="%{x}세대 (%{customdata[0]}곳)<br>1,000세대당 연간 %{y:.1f}건<br>단지당 연간 %{customdata[1]:.1f}건<br>세대수 중앙값 %{customdata[2]:,.0f}<extra></extra>")],
                   xaxis=ax("세대수 구간"), yaxis=ax("1,000세대당 연간 기록(중앙값)"), showlegend=False)
x = b[b["n_res"].notna()].copy()
x["per_year"] = x["n_res"] / 2.5
xs = np.linspace(np.log(x["세대수"].min()), np.log(x["세대수"].max()), 50)
dsc = rd(NLP_AN + "disp_scaling.csv").iloc[0]
FIGS["p05b"] = fig([dict(type="scatter", mode="markers", x=L(x["세대수"]), y=L(x["per_year"]), marker=dict(color=CAT[0], size=7, opacity=0.6, line=dict(width=0.5, color="#fff")),
                         customdata=cxdata(x, "per_year", "comm_per1000"), hovertemplate=hover_cx("<br>연간 기록 %{customdata[4]:.1f}건<br>1,000세대당 %{customdata[5]:.1f}건"), name="단지"),
                    dict(type="scatter", mode="lines", x=np.exp(xs).tolist(), y=np.exp(dsc["intercept"] + dsc["slope"] * xs).tolist(), line=dict(color=HI, width=2.5),
                         name=f"추세(기울기 {dsc['slope']:.2f})", hoverinfo="skip"),
                    dict(type="scatter", mode="lines", x=np.exp(xs).tolist(), y=(np.exp(xs) * np.exp(dsc["intercept"] + dsc["slope"] * np.log(1000)) / 1000).tolist(),
                         line=dict(color=GRAYC, width=1.5, dash="dot"), name="세대수에 비례했다면", hoverinfo="skip")],
                   xaxis=ax("세대수(로그 눈금)", type="log"), yaxis=ax("연간 주민 프로그램 기록(로그 눈금)", type="log"), legend=dict(orientation="h", y=-0.2))
card(sec, "p-size", f"세대수가 {sz['hh_ratio']:.1f}배인 단지도 프로그램은 {sz['rec_ratio']:.1f}배: 큰 단지일수록 세대당 기회가 적다",
     f"{P._szl(sz['peak_bin'])} 단지(중앙값 {sz['hh_peak']:,.0f}세대)는 1,000세대당 연간 {sz['peak']:.0f}건, {P._szl(sz['last_bin'])} 단지(중앙값 {sz['hh_large']:,.0f}세대)는 {sz['large']:.0f}건입니다. "
     f"세대수가 1% 늘 때 기록은 {sz['slope']:.2f}%만 늘어납니다(오른쪽 빨간 선이 회색 점선보다 완만). 300세대 미만 작은 단지도 {sz['smallest']:.0f}건으로 적습니다. 단지 규모와 정원이 공급을 좌우하는 모습입니다.",
     ["p05a", "p05b"], note="주민 대상 기록(30개월)을 연간으로 환산. 기록 건수는 공급의 양이며 참여 규모는 반영하지 않음", wide=True)

# 지사 격차(기준)
dg = rd(NLP_AN + "disp_group_summary.csv")
dgb = dg[dg["factor"] == "지사"].sort_values("median")
FIGS["p05c"] = fig([dict(type="scatter", mode="markers", x=dgb["median"].tolist(), y=dgb["group"].tolist(), marker=dict(color=CAT[1], size=11),
                         error_x=dict(type="data", symmetric=False, array=(dgb["ci_hi"] - dgb["median"]).tolist(), arrayminus=(dgb["median"] - dgb["ci_lo"]).tolist(), color=GRAYC, thickness=1.5),
                         customdata=np.column_stack([dgb["n"], dgb["ci_lo"], dgb["ci_hi"]]).tolist(),
                         hovertemplate="%{y} (%{customdata[0]}개 단지)<br>중앙값 %{x:.1f}건<br>95% 구간 %{customdata[1]:.1f}~%{customdata[2]:.1f}<extra></extra>")],
                   xaxis=ax("1,000세대당 연간 주민 프로그램 기록(단지 중앙값)"), yaxis=ax(automargin=True), showlegend=False)
card(sec, "p-branch", f"어느 지사에 속하느냐에 따라 세대당 프로그램이 {dgb['median'].iloc[-1] / dgb['median'].iloc[0]:.1f}배 차이 난다",
     f"{dgb['group'].iloc[-1]} 단지의 중앙값은 1,000세대당 연간 {dgb['median'].iloc[-1]:.0f}건, {dgb['group'].iloc[0]}은 {dgb['median'].iloc[0]:.0f}건입니다. "
     "앞에서 본 것처럼 주민 여건은 활동량을 거의 설명하지 못하므로, 지사별 운영 방식·자원 차이가 반영된 것으로 보입니다.",
     ["p05c"], note="가로 막대는 중앙값의 95% 부트스트랩 구간. 주민 대상 기록 15건 이상 단지. 자료: 커뮤니티 NLP 분석(disp_group_summary)")

# p06 필요-공급
nsx = b[b["need_pct"].notna()].copy()
mis = (nsx["need_pct"] >= 200 / 3) & (nsx["supply_pct"] <= 100 / 3)
tr = []
for flag, col, name in [(False, GRAYC, "그 밖의 단지"), (True, HI, "필요 상위·공급 하위")]:
    s = nsx[mis == flag]
    tr.append(dict(type="scatter", mode="markers", name=f"{name}({len(s)})", x=L(s["need_pct"]), y=L(s["supply_pct"]),
                   marker=dict(color=col, size=9 if flag else 7, opacity=0.9, line=dict(width=0.5, color="#fff")),
                   customdata=cxdata(s, "pct_60", "hd_per100", "comm_per1000"),
                   hovertemplate=hover_cx("<br>60세 이상 %{customdata[4]:.0f}%<br>홈닥터 100세대당 월 %{customdata[5]:.1f}건<br>프로그램 1,000세대당 연 %{customdata[6]:.1f}건")))
FIGS["p06"] = fig(tr, xaxis=ax("필요 지수 순위(백분위): 60세 이상 비율 + 홈닥터 지원 강도", range=[0, 100]), yaxis=ax("프로그램 공급 순위(백분위)", range=[0, 100]),
                  shapes=[dict(type="rect", x0=200 / 3, x1=100, y0=0, y1=100 / 3, fillcolor=HI, opacity=0.08, line=dict(width=0), layer="below")]
                  + [dict(type="line", x0=v, x1=v, y0=0, y1=100, line=dict(color="rgba(128,128,128,.3)", width=1), layer="below") for v in (100 / 3, 200 / 3)]
                  + [dict(type="line", y0=v, y1=v, x0=0, x1=100, line=dict(color="rgba(128,128,128,.3)", width=1), layer="below") for v in (100 / 3, 200 / 3)],
                  legend=dict(orientation="h", y=-0.15))
n_ = S["ns"]
card(sec, "p-need", f"필요가 큰 단지라고 프로그램이 뚜렷하게 많지 않다: {n_['n_mis']}곳은 '필요 상위·공급 하위'",
     f"필요 지수(60세 이상 비율과 홈닥터 지원 강도)와 공급(1,000세대당 기록)의 관계는 약합니다(순위상관 {n_['rho']['rho']:+.2f}, 95% 구간 {n_['rho']['lo']:+.2f}~{n_['rho']['hi']:+.2f}). "
     f"관계가 전혀 없어도 한 칸에 약 {n_['expected']:.0f}곳이 들어가는데, 오른쪽 아래 칸에는 {n_['n_mis']}곳이 있습니다. 빨간 점이 우선 살펴볼 단지입니다.",
     ["p06"], note="필요 지수는 보유 자료로 만든 대리 지표이며 정답 필요가 아님. 명단: problem_definition/tables/high_need_low_supply_complexes.csv", wide=True, height=560)

# p07 기록 단위
u = S["unit"]
items = [("단지 전체 대상 행사·프로그램", u["complex_wide"], CAT[0]), ("일부 가구에 직접 지원(방문·물품 등)", u["household"], CAT[1]),
         ("안부·관계 접촉(전화·방문 확인)", u["contact"], CAT[1]), ("기록에 대상 집단을 적은 비율", u["explicit"], CAT[3])][::-1]
FIGS["p07"] = fig([dict(type="bar", orientation="h", y=[i[0] for i in items], x=[i[1] * 100 for i in items], marker=dict(color=[i[2] for i in items]),
                        text=[f"{i[1] * 100:.0f}%" for i in items], textposition="outside", hovertemplate="%{y}<br>%{x:.1f}%<extra></extra>")],
                  xaxis=ax(f"주민 대상 기록 {u['n']:,}건 중 비율(%) — 지원 단위는 겹칠 수 있음", range=[0, 110]), yaxis=ax(automargin=True), showlegend=False)
card(sec, "p-unit", f"기록의 {pc(u['complex_wide'])}는 단지 전체 행사이고, 누구를 위한 것인지 적힌 기록은 {pc(u['explicit'])}",
     "행사가 '열렸다'는 기록은 남지만 어떤 가구가 참여했고 누가 빠졌는지는 남지 않습니다. 가구에 직접 닿는 지원은 일부입니다.",
     ["p07"], note="지원 단위·대상은 NLP가 활동 내용에서 판정한 자동 라벨(silver label)")

# p08 활동 달 수
mon = pd.to_datetime(r["start_date"]).dt.to_period("M")
keep = (mon >= pd.Period("2024-01", "M")) & (mon <= pd.Period("2026-06", "M"))
am = mon[keep].groupby(r.loc[keep, "complex_id"]).nunique()
cnt = am.value_counts().reindex(range(0, 31), fill_value=0)
FIGS["p08"] = fig([dict(type="bar", x=list(range(31)), y=cnt.tolist(), marker=dict(color=[HI if v < 15 else CAT[0] for v in range(31)]),
                        hovertemplate="기록이 있는 달 %{x}개월<br>단지 %{y}곳<extra></extra>")],
                  xaxis=ax("30개월 중 주민 대상 기록이 하나라도 있는 달 수"), yaxis=ax("단지 수"), showlegend=False,
                  shapes=[dict(type="line", x0=S["mon"]["median"], x1=S["mon"]["median"], y0=0, y1=1, yref="paper", line=dict(dash="dash", width=1.5))],
                  annotations=[dict(x=S["mon"]["median"], y=1, yref="paper", text=f"중앙값 {S['mon']['median']:.0f}개월", showarrow=False, xanchor="right", yanchor="top", xshift=-6)])
mo = S["mon"]
card(sec, "p-month", f"매달 프로그램이 이어진 단지는 {mo['n_full']}곳({pc(mo['n_full'] / mo['n'])})뿐이다",
     f"중앙값 단지는 30개월 중 {30 - mo['median']:.0f}개월에 주민 대상 기록이 없습니다. 절반도 안 되는 달에만 기록이 있는 단지가 {mo['n_half']}곳(빨간 막대)입니다. 프로그램이 없는 달에는 주민이 닿을 통로도 없습니다.",
     ["p08"], note="기록 누락과 실제 미운영을 구분할 수 없어 '기록이 없는 달'로 읽음. 2026년 상반기는 보고 지연 가능성")

# p09 이름
top = sd[sd["scope"] == "PROGRAM"].sort_values("n_records", ascending=False).head(15).iloc[::-1]
FIGS["p09"] = fig([dict(type="bar", orientation="h", y=top["std_name"].tolist(), x=top["alias_distinct_titles"].tolist(), marker=dict(color=CAT[0]),
                        customdata=np.column_stack([top["n_records"], top["n_complexes"]]).tolist(),
                        hovertemplate="<b>%{y}</b><br>서로 다른 제목 %{x}가지<br>기록 %{customdata[0]}건 · %{customdata[1]}개 단지<extra></extra>")],
                  xaxis=ax("같은 프로그램을 적은 서로 다른 제목 수(띄어쓰기·기호 정리 후)"), yaxis=ax(automargin=True), showlegend=False)
nn_ = S["names"]
card(sec, "p-names", f"표준 프로그램 {nn_['n_std']}종이 제목 {nn_['n_titles']:,}가지로 적혀 있다",
     f"같은 '찾아가는 공연'도 단지마다 다른 이름으로 기록됩니다(원문 제목은 {nn_['n_raw']:,}가지). 이름이 제각각이면 어느 단지에서 무엇이 잘 됐는지 비교하고 배울 수 없습니다. 이번 분석은 NLP로 이를 {nn_['n_std']}종으로 정리했습니다.",
     ["p09"], note="상위 15개 표준 프로그램(기록 수 기준). 분류는 규칙+LLM 라벨러(독립 표본 일치 87%)", wide=True, height=520)

# p10 기록 항목(HTML)
fill = S["fields"]["fill"]
rows_have = "".join(f"<li><span class='ck ok' aria-hidden='true'>✓</span><span>{lab}<small>채워진 비율 {fill[lab] * 100:.0f}%</small></span></li>" for st, lab, col in P.CHECK_ITEMS if st == "있음")
rows_miss = "".join(f"<li><span class='ck no' aria-hidden='true'>✕</span><span>{lab}</span></li>" for st, lab, col in P.CHECK_ITEMS if st == "없음")
card(sec, "p-fields", "기록은 '무엇을 했나'를 남기지만 '닿았나, 도움이 됐나'는 남기지 않는다",
     f"커뮤니티 활동 원자료 {S['fields']['n']:,}건의 항목을 살펴봤습니다. 오른쪽 항목이 없으니 다음 선정 때 참고할 결과가 쌓이지 않습니다.",
     html=f"<div class='checks'><div><h4 class='ok'>기록에 있다</h4><ul>{rows_have}</ul></div><div><h4 class='no'>기록에 없다</h4><ul>{rows_miss}</ul></div></div>",
     note="참여 인원은 행사별 합계라 같은 주민이 여러 번 셀 수 있음. 비용은 원자료에 구분만 있고 금액이 없음")

# p11 만족도
x = b[(b["n_total"] >= 30) & b["welfare_satisfaction"].notna() & b["n_res"].notna()].copy()
sat = S["sat"]
for key, c_, lab, k in [("p11a", "comm_per1000", "1,000세대당 연간 프로그램 기록", "volume"), ("p11b", "participation_per_100hh_year", "100세대당 연간 참여 인원(기록)", "participation"),
                        ("p11c", "std_richness", "운영한 프로그램 종류 수", "variety")]:
    rr = sat[f"rho_{k}"]
    FIGS[key] = fig([dict(type="scatter", mode="markers", x=L(x[c_]), y=L(x["welfare_satisfaction"]), marker=dict(color=CAT[0], size=8, opacity=0.7, line=dict(width=0.5, color="#fff")),
                          customdata=cxdata(x, c_, "welfare_satisfaction", "n_total"), hovertemplate=hover_cx(f"<br>{lab} %{{customdata[4]:.1f}}<br>복지 만족도 %{{customdata[5]:.1f}}점(응답 %{{customdata[6]}}명)"))],
                    xaxis=ax(lab), yaxis=ax("해피콜 복지 만족도(점)"), showlegend=False,
                    annotations=[dict(x=0.98, y=0.04, xref="paper", yref="paper", xanchor="right", yanchor="bottom", showarrow=False, text=f"ρ={rr['rho']:+.2f} ({rr['lo']:+.2f}~{rr['hi']:+.2f})")])
card(sec, "p-sat", "프로그램을 많이·다양하게 해도 복지 만족도와는 거의 관계가 없다",
     f"2025 해피콜 응답 30명 이상 {sat['n']}개 단지에서 활동량(ρ={sat['rho_volume']['rho']:+.2f}), 참여 규모({sat['rho_participation']['rho']:+.2f}), 프로그램 종류 수({sat['rho_variety']['rho']:+.2f}) 모두 만족도와의 관계가 0에 가깝습니다. "
     "얼마나 했는지 세는 것만으로는 무엇이 도움이 됐는지 알 수 없습니다. 결과를 기록해야 배울 수 있습니다.",
     ["p11a", "p11b", "p11c"], note="해피콜 복지 만족도는 관리소 단위 설문 점수(1:1 연결 단지). 만족도는 프로그램 밖의 요인에도 영향을 받음", wide=True, height=360)

# p12 기회
cnt = gapt["n_gap"].value_counts().sort_index()
FIGS["p12"] = fig([dict(type="bar", x=cnt.index.tolist(), y=cnt.values.tolist(), marker=dict(color=CAT[0]), hovertemplate="후보 %{x}개인 단지 %{y}곳<extra></extra>")],
                  xaxis=ax("비슷한 단지 10곳 중 절반 이상이 하는데 이 단지는 30개월간 한 번도 안 한 프로그램 수"), yaxis=ax("단지 수"), showlegend=False,
                  shapes=[dict(type="line", x0=S["gap"]["median"], x1=S["gap"]["median"], y0=0, y1=1, yref="paper", line=dict(dash="dash", width=1.5))],
                  annotations=[dict(x=S["gap"]["median"], y=1, yref="paper", text=f"중앙값 {S['gap']['median']:.0f}개", showarrow=False, xanchor="left", yanchor="top", xshift=6)])
ex_html = "".join(f"<div class='ex'><b>{k}</b> · 후보 {S['gap']['ex_counts'].get(k, len(v))}개<ul>" + "".join(f"<li>{s} <small>이웃 {sh * 10:.0f}/10곳</small></li>" for s, sh in v[:4]) + "</ul></div>"
                  for k, v in S["gap"]["examples"].items())
card(sec, "p-gap", f"이웃 단지들이 흔히 하는 프로그램이 단지마다 중앙값 {S['gap']['median']:.0f}개씩 빠져 있다",
     "주민 구성이 비슷한 단지 10곳(60세 이상·20세 미만 비율, 세대수, 연식, 면적, 공급유형 기준)의 경험을 모으면 단지마다 바로 검토할 후보 목록이 생깁니다. "
     "아래는 현장 실증 단지의 예입니다. '단지 지도·탐색기'에서 모든 단지의 후보를 볼 수 있습니다. 후보는 검토 대상이지 정답이 아니며 현장 확인이 필요합니다.",
     ["p12"], html=f"<div class='exs'>{ex_html}</div>", wide=True)

# ═════════ 3. 단지 지도·탐색기 ═════════
pcamat = F.pca_matrix(F.add_derived(b.copy()))
b["pc1"], b["pc2"] = PCA(2, random_state=7).fit_transform(pcamat).T.tolist()
adopted = ml[ml["n_records"] > 0].copy()
name_std = dict(zip(sd["std_id"], sd["std_name"]))
rec = set(sd.loc[(sd["recommendable"] == 1) & (sd["scope"] == "PROGRAM"), "std_id"])
adset = adopted.groupby("complex_id")["std_id"].apply(set).to_dict()
nbs = nbt.groupby("complex_id")["neighbor_id"].apply(list).to_dict()
b = b.merge(rd(os.path.join(TAB, "context_clusters.csv")), on="complex_id", how="left")
mcols = [c for c in master.columns if c.startswith(("인구_10", "인구_20대", "인구_30", "인구_40", "인구_50", "인구_60대", "인구_70대", "인구_80대", "인구_90", "인구_100", "거버넌스_2025", "TBM_2025", "업무협약_2025", "일자리지원_2025"))
         or c in ("최고층수", "승강기대수_100세대당", "CCTV대수_100세대당", "주차_세대당", "인구_여자_비율") or (c.startswith("접근성_") and c.endswith("_대표점_km"))]
mcols = [c for c in mcols if c not in b.columns]
b = b.merge(master[["complex_id"] + mcols], on="complex_id", how="left")
b["active_months_res"] = b["complex_id"].map(am)
CX = []
for _, rrow in b.iterrows():
    cid = rrow["complex_id"]
    own = adopted[adopted["complex_id"] == cid].sort_values("n_records", ascending=False)
    gl = []
    if cid in nbs:
        share = pd.Series([s for n_ in nbs[cid] for s in adset.get(n_, set()) if s in rec]).value_counts() / len(nbs[cid])
        g_ = share[(share >= 0.5) & (~share.index.isin(adset.get(cid, set())))].sort_values(ascending=False)
        gl = [[name_std[s], round(float(v), 2)] for s, v in g_.items()]
    CX.append(dict(id=cid, n=rrow["단지명"], br=rrow["지사명"], sg=rrow["supply_group"], st=rrow["공급유형"], lat=rrow["latitude"], lon=rrow["longitude"],
                   addr=rrow["기본주소"], cl=None if pd.isna(rrow.get("env_cluster")) else int(rrow["env_cluster"]) + 1,
                   top=[[name_std.get(s, s), int(n)] for s, n in zip(own["std_id"].head(12), own["n_records"].head(12))], ntypes=int(len(own)),
                   gap=gl[:10], nb=[nm.get(n_, n_) for n_ in nbs.get(cid, [])], pc=[rrow["pc1"], rrow["pc2"]],
                   n_total=None if pd.isna(rrow["n_total"]) else int(rrow["n_total"])))
VARS = WX.variables(b)
TS = WX.timeseries(b)
PYR = WX.pyramid(b)
CAND = WX.candidates(b, nbt, ml, sd)
PROG = WX.programs(b, ml, sd, pa)
VOC = WX.voc()
NEWS = WX.news()
CATALOG = WX.catalog()
outline = json.load(open(os.path.join(OUT, "assets", "korea_outline.geojson"), encoding="utf-8"))["features"][0]["geometry"]
polys = outline["coordinates"] if outline["type"] == "MultiPolygon" else [outline["coordinates"]]
ox, oy = [], []
for poly in polys:
    ring = poly[0]
    ox += [p[0] for p in ring] + [None]
    oy += [p[1] for p in ring] + [None]
explorer = dict(id="explorer", label="단지 지도·탐색기", title="318개 단지를 지도에서 보고, 한 단지씩 살펴보기",
                lead="색으로 볼 지표를 고르고, 점을 누르거나 이름을 검색하면 그 단지의 현황, 실제 운영한 프로그램, 비슷한 단지들이 하는데 이 단지엔 없는 프로그램 후보가 나옵니다. 지도는 끌어서 옮기고 휠로 확대할 수 있습니다.",
                outline=[ox, oy], cards=[])
SECTIONS.append(explorer)
for sid, lab, title, lead in [
    ("compare", "단지 비교", "단지 여러 곳을 나란히 비교하기", "탐색기에서 '비교에 추가'를 누르거나 아래에서 단지를 골라 최대 4곳까지 지표·추세·프로그램을 나란히 봅니다."),
    ("varx", "변수 탐색기", "두 지표의 관계를 직접 골라 보기", "가로·세로축 지표와 색 기준을 고르면 산점도와 순위상관이 바로 계산됩니다. 지사·공급유형으로 거르거나, 묶음별 분포(상자 그림)로 바꿔 볼 수 있습니다. 점을 누르면 그 단지로 이동합니다."),
    ("progdict", "프로그램 사전", "표준 프로그램 하나씩 살펴보기", "프로그램을 고르면 어느 단지가 운영했는지(지도), 언제 몰리는지(월별), 누가 함께하는지, 어떤 이름으로 기록됐는지, 함께 운영되는 프로그램이 무엇인지 보여 줍니다."),
    ("voice", "주민 목소리", "주민이 원한다고 말한 것과 실제 공급", "2025 해피콜의 서비스 수요 응답과 VOC(주민 의견)를 응답자 특성별로 보고, 실제 프로그램 기록과 비교합니다."),
    ("branch", "지사 비교", "13개 지사를 같은 잣대로 비교하기", "지표를 고르면 지사별 단지 분포를 중앙값 순으로 보여 주고, 지사 요약표를 함께 보여 줍니다."),
    ("table", "단지 목록", "318개 단지 전체 표", "열 이름을 누르면 정렬, 위에서 지사·공급유형·이름으로 거를 수 있습니다. 행을 누르면 탐색기로 이동합니다."),
]:
    SECTIONS.append(dict(id=sid, label=lab, title=title, lead=lead, cards=[]))

# ═════════ 4. 단지 현황(EDA) ═════════
sec = dict(id="eda", label="단지 현황 분석", title="단지 통합 자료 탐색: 규모·고령화·홈닥터·접근성·만족도",
           lead="단지 통합표(318개 단지), 홈닥터 월별 자료(2022-01~2026-06), 2025 해피콜을 합쳐 본 결과입니다. 자세한 해설은 EDA 분석보고서에 있습니다.", cards=[])
SECTIONS.append(sec)
ct = pd.crosstab(b["지사명"], b["supply_group"]).reindex(columns=[g for g in ED.SUPPLY_ORDER if g in b["supply_group"].unique()])
ct = ct.loc[ct.sum(axis=1).sort_values().index]
FIGS["e01"] = fig([dict(type="bar", orientation="h", y=ct.index.tolist(), x=ct[g].tolist(), name=g, marker=dict(color=SUPPLY_COLOR[g]), hovertemplate="%{y}<br>" + g + " %{x}곳<extra></extra>")
                   for g in ct.columns], barmode="stack", xaxis=ax("단지 수"), yaxis=ax(automargin=True), legend=dict(orientation="h", y=-0.12))
card(sec, "e-branch", f"지사 {b['지사명'].nunique()}곳에 단지가 고르게 퍼져 있지 않고, 공급유형 구성도 지사마다 다르다",
     f"단지가 가장 많은 지사는 {ct.sum(axis=1).idxmax()}({int(ct.sum(axis=1).max())}곳), 가장 적은 곳은 {ct.sum(axis=1).idxmin()}({int(ct.sum(axis=1).min())}곳)입니다. 국민임대 {int((b['supply_group'] == '국민임대').sum())}곳, 영구임대 {int((b['supply_group'] == '영구임대').sum())}곳이 대부분입니다.",
     ["e01"], height=480)
tr = []
for g in ED.SUPPLY_ORDER:
    s = b[b["supply_group"] == g]
    if len(s):
        tr.append(dict(type="box", y=L(s["세대수"]), name=g, marker=dict(color=SUPPLY_COLOR[g]), boxpoints="all", jitter=0.4, pointpos=0, customdata=cxdata(s),
                       hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>세대수 %{y:,}<extra></extra>"))
FIGS["e02"] = fig(tr, yaxis=ax("세대수", type="log"), showlegend=False)
card(sec, "e-size", f"단지 규모는 {b['세대수'].min():,.0f}세대에서 {b['세대수'].max():,.0f}세대까지, 영구임대가 가장 크다",
     f"세대수 중앙값 {b['세대수'].median():,.0f}세대. 영구임대 단지 중앙값 {b.loc[b['supply_group'] == '영구임대', '세대수'].median():,.0f}세대, 국민임대 {b.loc[b['supply_group'] == '국민임대', '세대수'].median():,.0f}세대입니다.",
     ["e02"], note="세로축 로그 눈금. 점 하나가 단지 하나")
tr = []
for g in ED.SUPPLY_ORDER:
    s = b[b["supply_group"] == g]
    if len(s):
        tr.append(dict(type="scatter", mode="markers", name=g, x=L(s["입주기준경과년수"]), y=L(s["pct_60"]), marker=dict(color=SUPPLY_COLOR[g], size=7, opacity=0.75, line=dict(width=0.5, color="#fff")),
                       customdata=cxdata(s, "입주기준경과년수", "pct_60"), hovertemplate=hover_cx("<br>입주 후 %{customdata[4]:.0f}년<br>60세 이상 %{customdata[5]:.0f}%")))
FIGS["e03"] = fig(tr, xaxis=ax("입주 후 경과 연수(년)"), yaxis=ax("60세 이상 비율(%)"), legend=dict(orientation="h", y=-0.2))
card(sec, "e-age", f"오래된 단지일수록 고령화가 깊다(ρ={S_eda['age']['rho_age']:+.2f})",
     f"영구임대 단지의 60세 이상 비율 중앙값은 {S_eda['age']['by_supply']['영구임대']:.0f}%, 국민임대는 {S_eda['age']['by_supply']['국민임대']:.0f}%입니다. 연식·고령화·공급유형이 함께 움직여 한 변수의 효과만 따로 떼어 보기 어렵습니다.",
     ["e03"])
R = rd(os.path.join(TAB, "spearman_matrix.csv"), index_col=0)
FIGS["e04"] = fig([dict(type="heatmap", z=R.values.round(2).tolist(), x=R.columns.tolist(), y=R.index.tolist(), zmin=-1, zmax=1, colorscale=DIV, reversescale=False,
                        hovertemplate="%{y} × %{x}<br>ρ=%{z:+.2f}<extra></extra>", colorbar=dict(title=dict(text="ρ")))],
                  xaxis=ax(tickangle=-45, automargin=True), yaxis=ax(autorange="reversed", automargin=True))
card(sec, "e-corr", "변수 사이의 순위상관: 규모·연식·고령·면적이 한 덩어리로 움직인다",
     "빨간색은 함께 커지는 관계, 파란색은 반대로 움직이는 관계입니다. 칸에 마우스를 올리면 상관계수가 보입니다.", ["e04"], wide=True, height=620)
hm = rd(os.path.join(TAB, "home_doctor_monthly_totals.csv"))
hm.loc[hm["n_cx"] < 100, "per100"] = np.nan
FIGS["e05"] = fig([dict(type="scatter", mode="lines+markers", x=hm["month"].tolist(), y=L(hm["per100"]), line=dict(color=CAT[0], width=2.5), marker=dict(size=5),
                        customdata=np.column_stack([hm["total"], hm["n_cx"]]).tolist(), connectgaps=False,
                        hovertemplate="%{x}<br>100세대당 %{y:.1f}건<br>전체 %{customdata[0]:,.0f}건 · 단지 %{customdata[1]}곳<extra></extra>")],
                  xaxis=ax("월"), yaxis=ax("홈닥터 지원(100세대당 월)"), showlegend=False)
gap_m = hm[hm["per100"].isna()]["month"].tolist()
card(sec, "e-hd", "홈닥터 지원 강도의 월별 흐름(2022~2026)",
     f"전체 단지 합계를 100세대당으로 나눈 값입니다. {', '.join(gap_m)}은 값이 있는 단지가 100곳 미만이라 선을 끊었습니다(자료 공백).", ["e05"], wide=True)
comp = b.groupby("supply_group")[[f"hd25_{c}_share" for c in ED.HD_COLS]].mean().reindex([g for g in ED.SUPPLY_ORDER if g in b["supply_group"].unique()])
FIGS["e06"] = fig([dict(type="bar", x=comp.index.tolist(), y=(comp[f"hd25_{c}_share"] * 100).tolist(), name=c, marker=dict(color=CAT[i]), hovertemplate="%{x}<br>" + c + " %{y:.1f}%<extra></extra>")
                   for i, c in enumerate(ED.HD_COLS)], barmode="stack", yaxis=ax("지원 내용 구성(%)"), legend=dict(orientation="h", y=-0.15))
card(sec, "e-hdcomp", "홈닥터 지원은 대부분 생활지원이고, 의료·경제지원 비중은 공급유형마다 조금씩 다르다",
     "2025년 단지별 구성비를 공급유형별로 평균했습니다.", ["e06"])
bt = rd(os.path.join(TAB, "forecast_baselines.csv"))
FIGS["e07"] = fig([dict(type="bar", x=s["baseline"].tolist(), y=(s["wape"] * 100).tolist(), name=sp, marker=dict(color=CAT[i]), customdata=np.column_stack([s["mae"], s["r2"]]).tolist(),
                        hovertemplate="%{x}<br>WAPE %{y:.1f}%<br>MAE %{customdata[0]:.1f}건 · R² %{customdata[1]:.2f}<extra>" + sp + "</extra>")
                   for i, (sp, s) in enumerate(bt.groupby("split"))], barmode="group", yaxis=ax("가중 절대오차율 WAPE(%) — 낮을수록 좋음"), legend=dict(orientation="h", y=-0.2))
best = bt[bt["split"].str.contains("test")].sort_values("wape").iloc[0] if bt["split"].str.contains("test").any() else bt.sort_values("wape").iloc[0]
card(sec, "e-base", f"단순 규칙도 강하다: '{best['baseline']}'의 오차율 {best['wape'] * 100:.1f}%",
     "월별 홈닥터 지원 건수를 예측하는 단순 규칙들의 성적입니다. 예측 모델을 만든다면 이 기준선을 넘어야 의미가 있습니다.", ["e07"])
recon = master.groupby("지사명").apply(lambda d: pd.Series(dict(mis=sum(d[f"홈닥터_{y}_합계불일치월수"].sum() for y in (2022, 2023, 2024, 2025, 2026) if f"홈닥터_{y}_합계불일치월수" in d),
                                                              obs=sum(d[c].sum() for c in [f"홈닥터_{y}_관측월수" for y in (2022, 2023, 2024, 2025)] if c in d)))).reset_index()
recon["share"] = recon["mis"] / recon["obs"].replace(0, np.nan)
recon = recon.sort_values("share")
FIGS["e08"] = fig([dict(type="bar", orientation="h", y=recon["지사명"].tolist(), x=(recon["share"] * 100).tolist(), marker=dict(color=[HI if v > 0.3 else CAT[0] for v in recon["share"]]),
                        customdata=np.column_stack([recon["mis"], recon["obs"]]).tolist(), hovertemplate="%{y}<br>합계 불일치 %{x:.0f}%<br>%{customdata[0]:,.0f} / %{customdata[1]:,.0f} 단지-월<extra></extra>")],
                  xaxis=ax("세부 항목 합 ≠ 총건수인 단지-월 비율(%)"), yaxis=ax(automargin=True), showlegend=False)
card(sec, "e-recon", f"홈닥터 자료 품질: 세부 합과 총건수가 어긋나는 달이 지사마다 다르다(최대 {recon['share'].max() * 100:.0f}%)",
     "생활·가사·의료·경제 지원을 더한 값이 '지원 내용 총건수'와 다른 단지-월의 비율입니다. 원자료 확인이 필요한 지사가 있습니다.", ["e08"],
     note="분모는 2022~2025년 관측 월수(2026 상반기는 분자에만 포함될 수 있어 약간 과대 가능)")
fac = [("병원", "접근성_병원_대표점_km"), ("의원", "접근성_의원_대표점_km"), ("약국", "접근성_약국_대표점_km"), ("보건기관", "접근성_보건기관_대표점_km"),
       ("경로당", "접근성_경로당_대표점_km"), ("노인복지관", "접근성_노인복지관_대표점_km"), ("종합사회복지관", "접근성_종합사회복지관_대표점_km")]
fac = [(a_, c_) for a_, c_ in fac if c_ in b.columns]
tr = [dict(type="box", y=L(b[c_]), name=a_, marker=dict(color=CAT[i % 8]), boxpoints="outliers", customdata=cxdata(b), hovertemplate="<b>%{customdata[0]}</b><br>" + a_ + "까지 %{y:.2f}km<extra></extra>")
      for i, (a_, c_) in enumerate(fac)]
FIGS["e09"] = fig(tr, yaxis=ax("단지에서 가장 가까운 시설까지 거리(km, 로그)", type="log"), showlegend=False)
card(sec, "e-access", "생활 시설까지의 거리: 의원·약국은 가깝고 노인복지관·종합사회복지관은 멀다",
     "국토정책지표 250m 격자 접근성을 단지 대표점에 붙였습니다. 상자는 사분위 범위, 점은 멀리 떨어진 단지입니다.", ["e09"])
x = b[b["comm_per1000"].notna() & b["hd_per100"].notna()]
FIGS["e10"] = fig([dict(type="scatter", mode="markers", x=L(x["comm_per1000"]), y=L(x["hd_per100"]), marker=dict(color=[SUPPLY_COLOR.get(g, GRAYC) for g in x["supply_group"]], size=7, opacity=0.7),
                        customdata=cxdata(x, "comm_per1000", "hd_per100"), hovertemplate=hover_cx("<br>프로그램 1,000세대당 %{customdata[4]:.1f}건<br>홈닥터 100세대당 %{customdata[5]:.1f}건"))],
                  xaxis=ax("커뮤니티 프로그램 기록(1,000세대당 연)", type="log"), yaxis=ax("홈닥터 지원(100세대당 월, 2025)"), showlegend=False)
card(sec, "e-commhd", f"커뮤니티 활동과 홈닥터 지원은 약하게만 연결된다(ρ={S_eda['ch']['rho']:+.2f})",
     "두 활동이 많은 단지가 따로따로입니다. 색은 공급유형(파랑 국민임대, 주황 영구임대, 초록 50년 공공임대, 노랑 복합).", ["e10"])
ha = rd(os.path.join(TAB, "happycall_association.csv")).sort_values("rho")
FIGS["e11"] = fig([dict(type="scatter", mode="markers", x=ha["rho"].tolist(), y=ha["variable"].tolist(), marker=dict(size=11, color=[HI if p < 0.05 else GRAYC for p in ha["p_holm"]]),
                        error_x=dict(type="data", symmetric=False, array=(ha["hi"] - ha["rho"]).tolist(), arrayminus=(ha["rho"] - ha["lo"]).tolist(), color=GRAYC),
                        customdata=np.column_stack([ha["lo"], ha["hi"], ha["n"], ha["p_holm"]]).tolist(),
                        hovertemplate="%{y}<br>ρ=%{x:+.2f} (%{customdata[0]:+.2f}~%{customdata[1]:+.2f})<br>n=%{customdata[2]} · 보정 p=%{customdata[3]:.3f}<extra></extra>")],
                  xaxis=ax("해피콜 종합만족도와의 순위상관 ρ", range=[-1, 1], zeroline=True), yaxis=ax(automargin=True), showlegend=False)
card(sec, "e-happy", "해피콜 만족도는 크고 고령화되고 오래된 단지에서 낮다",
     f"빨간 점은 다중비교 보정 후에도 유의한 관계입니다. 응답 30명 이상 단지 {int(ha['n'].iloc[0])}곳. 세대수·고령·연식은 서로 얽혀 있어 각각의 독립 효과로 읽을 수 없습니다.", ["e11"])
tr = []
for k_, s in b.groupby("env_cluster"):
    tr.append(dict(type="scatter", mode="markers", name=f"유형 {int(k_) + 1}({len(s)})", x=L(s["pc1"]), y=L(s["pc2"]), marker=dict(color=CAT[int(k_) % 8], size=7, opacity=0.8),
                   customdata=cxdata(s, "pct_60"), hovertemplate=hover_cx("<br>60세 이상 %{customdata[4]:.0f}%")))
FIGS["e12"] = fig(tr, xaxis=ax("주성분 1"), yaxis=ax("주성분 2"), legend=dict(orientation="h", y=-0.2))
card(sec, "e-pca", f"단지 여건으로 묶으면 {b['env_cluster'].nunique()}개 유형이 나온다",
     "규모·연식·고령·면적·접근성 등을 두 축으로 요약한 지도입니다(주성분 분석 + k-평균). 가까운 점은 여건이 비슷한 단지입니다.", ["e12"])
mi = rd(os.path.join(TAB, "morans_i.csv")).sort_values("morans_I")
FIGS["e13"] = fig([dict(type="bar", orientation="h", y=mi["variable"].tolist(), x=mi["morans_I"].tolist(), marker=dict(color=[CAT[0] if p < 0.05 else GRAYC for p in mi["p_perm"]]),
                        customdata=np.column_stack([mi["p_perm"], mi["null_lo"], mi["null_hi"]]).tolist(),
                        hovertemplate="%{y}<br>Moran's I %{x:.3f}<br>순열 p=%{customdata[0]:.3f}<br>무작위 범위 %{customdata[1]:.3f}~%{customdata[2]:.3f}<extra></extra>")],
                  xaxis=ax("Moran's I (이웃 8개 단지와 닮은 정도)"), yaxis=ax(automargin=True), showlegend=False)
card(sec, "e-moran", "가까운 단지끼리 닮은 변수와 그렇지 않은 변수",
     "파란 막대는 무작위 배치보다 뚜렷하게 이웃끼리 닮은 변수입니다. 모델을 검증할 때 지역 단위로 나눠야 하는 이유입니다.", ["e13"])
ot = rd(os.path.join(TAB, "outlier_complexes.csv"))
card(sec, "e-out", f"유난히 튀는 단지 {ot['complex_id'].nunique()}곳",
     "중앙값에서 크게 벗어난 단지(로버스트 z, |z|>3.5)입니다. 자료 오류인지 실제 특성인지 확인이 필요합니다.",
     html="<div class='tbl'><table><thead><tr><th>단지</th><th>지사</th><th>변수</th><th class='n'>z</th></tr></thead><tbody>"
     + "".join(f"<tr><td>{rw['단지명']}</td><td>{rw['지사명']}</td><td>{rw['variable']}</td><td class='n'>{rw['z']:+.1f}</td></tr>" for _, rw in ot.sort_values("z").iterrows())
     + "</tbody></table></div>")

# ═════════ 5. 커뮤니티 프로그램(NLP) ═════════
sec = dict(id="programs", label="커뮤니티 프로그램 분석", title="2만 건의 활동 기록을 표준 프로그램으로 정리해 본 것",
           lead=f"커뮤니티 활동 기록 {S['fields']['n']:,}건을 규칙과 LLM 라벨러로 {S['names']['n_std']}종의 표준 프로그램과 15개 영역으로 분류했습니다. 라벨은 자동 판정(silver label)이며 독립 표본 일치율은 표준 유형 87%입니다.", cards=[])
SECTIONS.append(sec)
tm = rd(NLP_AN + "time_monthly.csv")
FIGS["n01"] = fig([dict(type="bar", x=tm["month"].tolist(), y=tm["n_resident"].tolist(), marker=dict(color=[CAT[3] if m_ >= "2026-01" else CAT[0] for m_ in tm["month"]]),
                        hovertemplate="%{x}<br>주민 대상 기록 %{y:,}건<extra></extra>")], xaxis=ax("시작 월"), yaxis=ax("주민 대상 기록 수"), showlegend=False)
card(sec, "n-time", "월별 기록 수: 설·가정의 달·추석·연말에 봉우리가 생긴다",
     f"월평균 {tm['n_resident'].mean():.0f}건. 노란 막대(2026년)는 가장 최근 자료라 나중에 보고되는 기록이 더 붙을 수 있어, 연도 비교는 건수보다 비중으로 했습니다.", ["n01"], wide=True)
ts = rd(NLP_AN + "time_season.csv")
FIGS["n02"] = fig([dict(type="bar", x=[f"{m_}월" for m_ in ts["mth"]], y=ts["season_index"].tolist(), marker=dict(color=[CAT[1] if v > 1 else CAT[0] for v in ts["season_index"]]),
                        hovertemplate="%{x}<br>계절 지수 %{y:.2f}<extra></extra>")], yaxis=ax("계절 지수(1 = 평균 달)"), showlegend=False,
                  shapes=[dict(type="line", x0=-0.5, x1=11.5, y0=1, y1=1, line=dict(dash="dot", width=1))])
card(sec, "n-season", f"가장 바쁜 달은 {int(ts.loc[ts['season_index'].idxmax(), 'mth'])}월, 가장 조용한 달은 {int(ts.loc[ts['season_index'].idxmin(), 'mth'])}월",
     "주황 막대는 평균보다 기록이 많은 달입니다. 연도별 차이를 걸러낸 달별 지수입니다.", ["n02"])
fam = r.groupby("std_family_label").size().sort_values()
FIGS["n03"] = fig([dict(type="bar", orientation="h", y=fam.index.tolist(), x=(fam / fam.sum() * 100).tolist(), marker=dict(color=CAT[0]), customdata=fam.tolist(),
                        hovertemplate="%{y}<br>%{x:.1f}% (%{customdata:,}건)<extra></extra>")], xaxis=ax("주민 대상 기록 중 비중(%)"), yaxis=ax(automargin=True), showlegend=False)
card(sec, "n-family", f"가장 많은 영역은 '{fam.index[-1]}'({fam.iloc[-1] / fam.sum() * 100:.0f}%)",
     "15개 프로그램 영역의 비중입니다. 명절·행사, 문화·여가, 주거환경 같은 단지 전체 행사형이 큰 몫을 차지합니다.", ["n03"], height=480)
tl = rd(NLP_AN + "type_landscape.csv").sort_values("rank")
tl20 = tl.head(20).iloc[::-1]
FIGS["n04"] = fig([dict(type="bar", orientation="h", y=tl20["std_name"].tolist(), x=tl20["n_records"].tolist(), marker=dict(color=CAT[0]),
                        customdata=np.column_stack([tl20["n_complexes"], tl20["adoption_rate"] * 100, tl20["std_family_label"]]).tolist(),
                        hovertemplate="<b>%{y}</b><br>%{customdata[2]}<br>기록 %{x}건 · %{customdata[0]}개 단지(채택률 %{customdata[1]:.0f}%)<extra></extra>")],
                  xaxis=ax("기록 수"), yaxis=ax(automargin=True), showlegend=False)
card(sec, "n-top", f"상위 10개 프로그램이 전체 기록의 {S['conc']['top10'] * 100:.0f}%",
     f"표준 프로그램 {S['conc']['n_std']}종 중 상위 20종이 {S['conc']['top20'] * 100:.0f}%를 차지합니다. 막대에 마우스를 올리면 몇 개 단지가 운영했는지(채택률) 보입니다.", ["n04"], wide=True, height=600)
FIGS["n05"] = fig([dict(type="scatter", mode="lines", x=tl["rank"].tolist(), y=(tl["cum_share"] * 100).tolist(), line=dict(color=CAT[0], width=2.5), customdata=tl["std_name"].tolist(),
                        hovertemplate="상위 %{x}종까지<br>누적 %{y:.1f}%<br>(%{customdata})<extra></extra>")],
                  xaxis=ax("표준 프로그램 순위(기록 수)"), yaxis=ax("누적 비중(%)", range=[0, 100]), showlegend=False)
card(sec, "n-cum", "소수 프로그램에 기록이 몰린다", "기록 수 순으로 표준 프로그램을 쌓은 누적 곡선입니다. 곡선이 빨리 올라갈수록 쏠림이 큽니다.", ["n05"])
ed = rd(NLP_AN + "rel_edges.csv").sort_values("lift", ascending=False).head(20).iloc[::-1]
FIGS["n06"] = fig([dict(type="bar", orientation="h", y=[f"{a_} + {c_}" for a_, c_ in zip(ed["std_a_name"], ed["std_b_name"])], x=ed["lift"].tolist(),
                        marker=dict(color=[CAT[0] if s_ else CAT[1] for s_ in ed["same_family"]]), customdata=np.column_stack([ed["n_both"], ed["jaccard"]]).tolist(),
                        hovertemplate="%{y}<br>향상도 %{x:.2f}<br>함께 운영한 단지 %{customdata[0]}곳 · Jaccard %{customdata[1]:.2f}<extra></extra>")],
                  xaxis=ax("향상도(lift): 1보다 클수록 함께 운영되는 경향"), yaxis=ax(automargin=True, tickfont=dict(size=10)), showlegend=False)
card(sec, "n-pair", "함께 운영되는 프로그램 짝 상위 20",
     "같은 단지에서 같이 나타나는 정도입니다. 파란 막대는 같은 영역, 주황은 다른 영역끼리의 짝입니다. 추천에서 '이 프로그램을 하는 단지는 저것도 한다'의 근거가 됩니다.", ["n06"], wide=True, height=620)
pp = rd(NLP_AN + "part_participation_family.csv").sort_values("median")
FIGS["n07"] = fig([dict(type="scatter", mode="markers", y=pp["std_family_label"].tolist(), x=pp["median"].tolist(), marker=dict(color=CAT[0], size=10),
                        error_x=dict(type="data", symmetric=False, array=(pp["q3"] - pp["median"]).tolist(), arrayminus=(pp["median"] - pp["q1"]).tolist(), color=GRAYC),
                        customdata=np.column_stack([pp["q1"], pp["q3"], pp["p90"], pp["n"]]).tolist(),
                        hovertemplate="%{y}<br>참여 인원 중앙값 %{x:.0f}명<br>사분위 %{customdata[0]:.0f}~%{customdata[1]:.0f}명 · 상위10% %{customdata[2]:.0f}명<br>기록 %{customdata[3]:,}건<extra></extra>")],
                  xaxis=ax("한 번 기록당 참여 인원(명, 로그)", type="log"), yaxis=ax(automargin=True), showlegend=False)
card(sec, "n-part", "한 번에 모이는 인원은 영역마다 크게 다르다", "점은 중앙값, 선은 사분위 범위입니다. 참여 인원은 기록된 합계이지 고유 주민 수가 아닙니다.", ["n07"], height=480)
pcs = rd(NLP_AN + "part_cost_share.csv").sort_values("ratio")
FIGS["n08"] = fig([dict(type="bar", orientation="h", y=pcs["std_family_label"].tolist(), x=(pcs["records_share"] * 100).tolist(), name="기록 비중", marker=dict(color=CAT[0]),
                        hovertemplate="%{y}<br>기록 비중 %{x:.1f}%<extra></extra>"),
                   dict(type="bar", orientation="h", y=pcs["std_family_label"].tolist(), x=(pcs["cost_share"] * 100).tolist(), name="추정 비용 비중", marker=dict(color=CAT[1]),
                        hovertemplate="%{y}<br>추정 비용 비중 %{x:.1f}%<extra></extra>")],
                  barmode="group", xaxis=ax("비중(%)"), yaxis=ax(automargin=True), legend=dict(orientation="h", y=-0.12))
card(sec, "n-cost", "추정 비용은 문화·여가와 식생활 지원에 기록 비중보다 크게 쏠린다",
     "비용은 원자료에 금액이 없어 프로그램 유형별 가정으로 추정한 값입니다(모델 추정치, 실제 집행액 아님).", ["n08"], height=520)
cc = rd(NLP_AN + "ctx_context_corr.csv")
pv = cc.pivot(index="context", columns="outcome", values="rho")
FIGS["n09"] = fig([dict(type="heatmap", z=pv.values.round(2).tolist(), x=pv.columns.tolist(), y=pv.index.tolist(), zmin=-0.6, zmax=0.6, colorscale=DIV,
                        hovertemplate="%{y} × %{x}<br>ρ=%{z:+.2f}<extra></extra>", colorbar=dict(title=dict(text="ρ")))],
                  xaxis=ax(automargin=True), yaxis=ax(automargin=True))
card(sec, "n-ctx", "단지 여건은 활동량은 거의 설명하지 못하고, 다양성·참여 규모와는 조금 연결된다",
     "활동량(1,000세대당 기록)은 어떤 여건과도 상관이 0 근처입니다. 오래되고 고령인 단지는 프로그램 종류가 많고 참여 규모가 큽니다.", ["n09"], wide=True, height=520)
tp = rd(NLP_AN + "types_profile_z.csv").set_index("type")
FIGS["n10"] = fig([dict(type="heatmap", z=tp.values.round(2).tolist(), x=tp.columns.tolist(), y=tp.index.tolist(), zmin=-2, zmax=2, colorscale=DIV,
                        hovertemplate="%{y} · %{x}<br>표준화 점수 %{z:+.2f}<extra></extra>", colorbar=dict(title=dict(text="z")))],
                  xaxis=ax(tickangle=-45, automargin=True), yaxis=ax(automargin=True))
card(sec, "n-types", f"프로그램 운영 방식으로 본 단지 유형 {len(tp)}가지",
     "단지별 프로그램 구성과 운영 방식(행사형·정기형, 협력 기관 등)으로 단지를 묶은 결과입니다. 빨간색은 그 유형에서 평균보다 높은 특성입니다.", ["n10"], wide=True, height=420)
tf = rd(NLP_AN + "time_fam_h1.csv").sort_values("diff_pp_25_26")
FIGS["n11"] = fig([dict(type="bar", orientation="h", y=tf["family"].tolist(), x=tf["diff_pp_25_26"].tolist(), marker=dict(color=[HI if v < 0 else CAT[0] for v in tf["diff_pp_25_26"]]),
                        customdata=np.column_stack([tf["share_2025h1"] * 100, tf["share_2026h1"] * 100]).tolist(),
                        hovertemplate="%{y}<br>2025 상반기 %{customdata[0]:.1f}% → 2026 상반기 %{customdata[1]:.1f}%<br>변화 %{x:+.1f}%p<extra></extra>")],
                  xaxis=ax("상반기 비중 변화(%p, 2025→2026)"), yaxis=ax(automargin=True), showlegend=False)
card(sec, "n-shift", "2026년 상반기에 비중이 늘고 줄어든 영역",
     "건수가 아니라 비중으로 비교했습니다(2026년은 보고 지연으로 건수가 적게 잡힐 수 있음).", ["n11"], height=480)

# ═════════ 6. 자료와 방법 ═════════
notes = dict(id="notes", label="자료·방법", title="자료, 방법, 읽을 때 주의할 점", cards=[], lead="",
             html=("<div class='prose'>"
                   "<h3>사용한 자료</h3><ul>"
                   "<li>단지 통합표 <code>complex_integrated_20261117_v1</code>: 318개 단지의 규모·공급유형·인구 구성·시설·접근성·홈닥터 연·월 집계(단지 기본키 <code>complex_id</code>)</li>"
                   f"<li>커뮤니티 활동 NLP <code>community_nlp_2026_v1</code>: 2024-01~2026-06 기록 {S['fields']['n']:,}건(306개 단지)을 표준 프로그램 {S['names']['n_std']}종·15개 영역으로 분류</li>"
                   "<li>2025 해피콜 관리소 평가: 관리소 319곳 중 304곳을 단지에 1:1 연결(통합 관리소 4곳·단지 10개는 단지별 분석에서 제외)</li>"
                   "<li>국토정책지표 250m 격자 접근성(지도 외곽선도 이 격자에서 만들었습니다)</li></ul>"
                   "<h3>읽을 때 주의할 점</h3><ul>"
                   "<li>모든 관계는 상관입니다. 원인을 증명하지 않습니다.</li>"
                   "<li>프로그램 기록은 공급의 기록이고, 홈닥터 지원·해피콜 만족도도 '필요의 정답'이 아닙니다. 필요 지수는 대리 지표입니다.</li>"
                   "<li>참여 인원은 행사별 합계라 같은 주민이 여러 번 셀 수 있습니다. 비용은 모델 추정치입니다.</li>"
                   "<li>NLP 분류는 규칙+LLM 라벨러의 자동 판정(silver label)입니다. 독립 표본 일치율: 범위 96%, 표준 유형 87%, 영역 92%.</li>"
                   "<li>2026년 상반기 기록은 보고 지연으로 적게 잡힐 수 있어 비중으로 비교했습니다.</li>"
                   "<li>'이웃 대비 빠진 프로그램 후보'는 검토 대상 목록이지 추천 결과나 필요 판정이 아닙니다. 현장 확인이 필요합니다.</li></ul>"
                   "<h3>보고서</h3><ul><li>문제정의 분석보고서: <code>eda_20261117_v1/problem_definition/문제정의_분석보고서.md</code></li>"
                   "<li>EDA 분석보고서: <code>eda_20261117_v1/EDA_분석보고서.md</code></li>"
                   "<li>커뮤니티 NLP 분석보고서: <code>archive/processed_support_20261117_v1/community_nlp_2026_v1/분석보고서.md</code></li></ul></div>"))
SECTIONS.append(notes)

DATA = clean(dict(figs=FIGS, sections=SECTIONS, cx=CX, vars=VARS, ts=TS, pyr=PYR, cand=CAND, prog=PROG, dem=DEM, voc=VOC, news=NEWS, catalog=CATALOG, built="2026-11-17"))
payload = json.dumps(DATA, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_template.html"), encoding="utf-8").read()
app = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_template_app.js"), encoding="utf-8").read()
html = tpl.replace("/*__APP__*/", app).replace("/*__DATA__*/null", payload)
os.makedirs(os.path.join(OUT, "web"), exist_ok=True)
# artifact.html: 웹 게시용 본문(문서 골격은 게시할 때 붙는다) / index.html: 내 PC에서 바로 여는 완전한 문서
open(os.path.join(OUT, "web", "artifact.html"), "w", encoding="utf-8").write(html)
full = ("<!doctype html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
        "<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n"
        "</head>\n<body>\n" + html + "\n</body>\n</html>\n")
outp = os.path.join(OUT, "web", "index.html")
open(outp, "w", encoding="utf-8").write(full)
print("written", outp, f"{os.path.getsize(outp) / 1e6:.2f} MB", "figs", len(FIGS), "complexes", len(CX))


# ───────── Netlify 배포 묶음: 파일을 역할별로 나누고 모든 경로를 상대 경로로 둔다(인터넷 없이도 열림) ─────────
def write_netlify(out_dir, zip_path):
    import re
    import shutil
    import zipfile
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(out_dir):   # 폴더가 다른 프로그램에 열려 있어도 되도록 파일만 지운다
        for root, _, files in os.walk(out_dir):
            for fn in files:
                os.remove(os.path.join(root, fn))
    for d in ("assets/vendor", "data"):
        os.makedirs(os.path.join(out_dir, d), exist_ok=True)
    css = re.search(r"<style>(.*?)</style>", tpl, re.S).group(1)
    fonts = re.findall(r'<link rel="(?:preconnect|stylesheet)"[^>]*>', tpl)
    title = re.search(r"<title>(.*?)</title>", tpl).group(1)
    body = tpl[tpl.index("</style>") + len("</style>"):]
    body = body[:body.index('<script src="https://cdnjs')]
    open(os.path.join(out_dir, "assets", "style.css"), "w", encoding="utf-8").write(
        ":root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}[hidden]{display:none!important}\n" + css)
    open(os.path.join(out_dir, "assets", "app.js"), "w", encoding="utf-8").write("const D = window.ONTER_DATA;\n" + app)
    open(os.path.join(out_dir, "data", "dashboard.js"), "w", encoding="utf-8").write(f"/* 분석 자료(기준 {DATA['built']}). build_web.py가 만든다. */\nwindow.ONTER_DATA = " + payload + ";\n")
    shutil.copy(os.path.join(here, "vendor", "plotly-2.34.0.min.js"), os.path.join(out_dir, "assets", "vendor", "plotly-2.34.0.min.js"))
    index = ("<!doctype html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n"
             "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
             "<meta name=\"robots\" content=\"noindex, nofollow\">\n"
             f"<title>{title}</title>\n<meta name=\"description\" content=\"주택관리공단 공공임대 318개 단지의 복지 프로그램 선정·배분 분석(온터팀)\">\n"
             + "\n".join(fonts) + "\n<link rel=\"stylesheet\" href=\"assets/style.css\">\n</head>\n<body>\n" + body.strip() + "\n\n"
             "<script src=\"assets/vendor/plotly-2.34.0.min.js\"></script>\n<script src=\"data/dashboard.js\"></script>\n<script src=\"assets/app.js\"></script>\n</body>\n</html>\n")
    open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8").write(index)
    open(os.path.join(out_dir, "netlify.toml"), "w", encoding="utf-8").write(
        '[build]\n  publish = "."\n\n[[headers]]\n  for = "/*"\n  [headers.values]\n    X-Robots-Tag = "noindex, nofollow"\n    X-Content-Type-Options = "nosniff"\n    Referrer-Policy = "strict-origin-when-cross-origin"\n\n'
        '[[headers]]\n  for = "/assets/vendor/*"\n  [headers.values]\n    Cache-Control = "public, max-age=31536000, immutable"\n')
    open(os.path.join(out_dir, "robots.txt"), "w", encoding="utf-8").write("User-agent: *\nDisallow: /\n")
    open(os.path.join(out_dir, "README.txt"), "w", encoding="utf-8").write(
        "온터 단지 복지 분석 — 배포 묶음\n\n"
        "구성\n  index.html                        첫 화면(모든 경로는 상대 경로)\n  assets/style.css                  화면 모양\n  assets/app.js                     화면 동작\n"
        "  assets/vendor/plotly-2.34.0.min.js  차트 라이브러리(내장, 인터넷 없이 동작)\n  data/dashboard.js                 분석 자료(단지별 수치 포함)\n"
        "  netlify.toml                      Netlify 설정(검색엔진 색인 차단 헤더)\n  robots.txt                        검색엔진 수집 차단\n\n"
        "Netlify에 올리기\n  1) app.netlify.com 로그인 → Sites → 'Add new site' → 'Deploy manually'\n  2) 이 zip을 풀어 나온 폴더(index.html이 있는 폴더)를 끌어다 놓기\n"
        "  3) 수정 후 다시 올릴 때는 그 사이트의 Deploys 탭에 새 폴더를 끌어다 놓기\n\n"
        "내 PC에서 보기\n  index.html을 더블클릭하면 인터넷 없이 열립니다(글꼴만 기본 글꼴로 보일 수 있음).\n\n"
        "주의\n  Netlify 주소는 링크를 아는 누구나 볼 수 있습니다. 단지별 홈닥터·해피콜 수치가 들어 있으니\n"
        "  공개 범위를 정한 뒤 올리세요(비밀번호 보호는 Netlify 유료 기능).\n\n"
        "다시 만들기\n  project/tools/eda 에서  python build_web.py <EDA 폴더>\n")
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(out_dir):
            for fn in files:
                fp = os.path.join(root, fn)
                z.write(fp, os.path.relpath(fp, out_dir).replace(os.sep, "/"))
    print("netlify", out_dir, "zip", zip_path, f"{os.path.getsize(zip_path) / 1e6:.2f} MB")


write_netlify(os.path.join(OUT, "web", "netlify_site"), os.path.join(OUT, "web", "onter_web_netlify.zip"))
