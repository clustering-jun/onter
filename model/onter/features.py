"""공통 특징 계층: 단지 특징 행렬, 기간별 단지×프로그램 행렬, 프로그램 속성 행렬.

기간(start, end)을 받는 함수는 그 기간의 기록만 쓴다. 평가에서 미래가 섞이지 않게 하는 유일한 통로다.
"""
from functools import lru_cache
import numpy as np
import pandas as pd
from . import config as C, data as D

# 단지 특징 묶음. need 쪽(구조)과 capacity 쪽(조직·공간)을 섞지 않도록 나눠 둔다
GROUPS = {
    "demo": ["age60", "age70", "age80", "age_u20", "age_work", "female", "pph"],
    "housing": ["log_hh", "years", "area_avg", "small_unit", "rooms", "perm", "national", "pub50", "happy", "elev100", "cctv100", "parking"],
    "access": [f"d_{f}" for f in C.FACILITIES] + ["n_fac500", "rg_metro", "rg_gun"],
    "service": ["hd", "hd_life", "hd_chores", "hd_medical", "hd_econ"],          # 이용으로 드러난 필요(공급에 오염될 수 있음)
    "space": ["sp_senior", "sp_gym", "sp_hall", "sp_daycare", "sp_library", "sp_welfare"],
    "org": ["deployed", "mou25", "gov25", "job25"],                              # 조직 여건(필요가 아니라 실행 역량)
}
STRUCT = ["demo", "housing", "access"]                                           # 필요 측 구조 특징(이용·조직 제외)


@lru_cache(maxsize=None)
def complex_frame():
    c = D.complexes().copy()
    c["rg_metro"], c["rg_gun"] = (c["region"] == "대도시 자치구").astype(int), (c["region"] == "군 지역").astype(int)
    for f in C.FACILITIES:                                # 거리는 꼬리가 길어 로그로 본다
        c[f"d_{f}"] = np.log1p(c[f"d_{f}"])
    return c


def matrix(groups=STRUCT, ids=None):
    """표준화한 단지 특징 행렬(DataFrame). 결측은 중앙값으로 채우고 채웠다는 사실은 따로 세지 않는다(결측률 낮음)."""
    c = complex_frame()
    cols = [x for g in groups for x in GROUPS[g]]
    X = c[cols].astype(float)
    X = X.fillna(X.median())
    X = (X - X.mean()) / X.std(ddof=0).replace(0, 1)
    return X if ids is None else X.loc[ids]


def group_slices(groups):
    out, i = {}, 0
    for g in groups:
        out[g] = slice(i, i + len(GROUPS[g]))
        i += len(GROUPS[g])
    return out


def window(start, end, resident_only=True):
    r = D.records(resident_only)
    return r[r["ym"].between(start, end)]


def interactions(start, end, kind="binary"):
    """단지(318)×추천 대상 프로그램(96) 행렬. kind: binary(운영 여부) / count(기록 수) / months(기록 있는 달 수)."""
    r = window(start, end)
    items, ids = D.programs().index, D.complexes().index
    r = r[r["std_id"].isin(items)]
    if kind == "months":
        m = r.groupby(["complex_id", "std_id"])["ym"].nunique().unstack(fill_value=0)
    else:
        m = r.groupby(["complex_id", "std_id"]).size().unstack(fill_value=0)
    m = m.reindex(index=ids, columns=items, fill_value=0).astype(float)
    return (m > 0).astype(float) if kind == "binary" else m


def active_complexes(start, end, min_records=1):
    n = window(start, end).groupby("complex_id").size()
    return n[n >= min_records].index


def _multi_share(r, col, codes):
    """기록의 다중 코드 열(예: 'N1|N5')을 프로그램×코드 비중 행렬로."""
    x = r[["std_id", col]].dropna()
    x = x.assign(code=x[col].str.split("|")).explode("code")
    x = x[x["code"].isin(codes)]
    t = x.groupby(["std_id", "code"]).size().unstack(fill_value=0).reindex(columns=codes, fill_value=0)
    n = r.groupby("std_id").size()
    return t.div(n.reindex(t.index), axis=0)


def need_membership(start=C.FIRST_MONTH, end=C.LAST_MONTH, blend=0.5):
    """프로그램×필요 분야 소속(행 합 1). 정의(사전)와 기간 내 기록의 분야 표기를 섞는다.

    분야가 없는 상담·정보형(N0)은 여섯 분야에 고르게 걸친 '통로 프로그램'으로 둔다.
    """
    p = D.programs()
    df = pd.DataFrame(0.0, index=p.index, columns=C.NEED_IDS)
    for i, (needs, prim) in enumerate(zip(p["needs"], p["need_primary"])):
        for n in needs:
            df.iloc[i, C.NEED_IDS.index(n)] += 1.0
        if isinstance(prim, str):
            df.iloc[i, C.NEED_IDS.index(prim)] += 1.0          # 주 분야에 가중
    emp = _multi_share(window(start, end), "need_domains", C.NEED_IDS).reindex(p.index).fillna(0)
    norm = lambda t: t.div(t.sum(axis=1).replace(0, np.nan), axis=0)
    a, b = norm(df), norm(emp)
    m = a.fillna(b) * (1 - blend) + b.fillna(a) * blend
    m = norm(m).fillna(1 / len(C.NEED_IDS))
    return m


TARGETS = ["ELD", "ELD1", "VUL", "DIS", "CHD", "MID", "WOM", "JOB", "CRI", "ALL"]


def target_membership(start=C.FIRST_MONTH, end=C.LAST_MONTH):
    """프로그램×대상 비중. 원문에 대상이 적힌 기록을 우선하고 없으면 유형 기본값을 쓴다."""
    p = D.programs()
    r = window(start, end)
    r = r.assign(tg=r["target_explicit"].fillna(r["target_type_default"]))
    emp = _multi_share(r, "tg", TARGETS).reindex(p.index)
    de = pd.DataFrame(0.0, index=p.index, columns=TARGETS)
    for i, ts in enumerate(p["targets"]):
        for t in ts:
            if t in TARGETS:
                de.iloc[i, TARGETS.index(t)] = 1.0
    return emp.fillna(de)


@lru_cache(maxsize=None)
def item_taxonomy():
    """프로그램 정의 속성의 원-핫 행렬(가족·목적·방식·서비스·운영·자원·대상). 내용 기반 유사도에 쓴다."""
    p = D.programs()
    parts = [pd.get_dummies(p["family"], prefix="fam"), pd.get_dummies(p["purpose"], prefix="pur")]
    for col in ["modes", "services", "ops", "resources", "targets", "needs"]:
        codes = sorted({x for l in p[col] for x in l})
        parts.append(pd.DataFrame([[int(c in l) for c in codes] for l in p[col]], index=p.index, columns=[f"{col}_{c}" for c in codes]))
    return pd.concat(parts, axis=1).astype(float)


def cosine(A, B=None):
    A = np.asarray(A, float)
    B = A if B is None else np.asarray(B, float)
    na, nb = np.linalg.norm(A, axis=1, keepdims=True), np.linalg.norm(B, axis=1, keepdims=True)
    return (A / np.where(na == 0, 1, na)) @ (B / np.where(nb == 0, 1, nb)).T


def haversine(lat, lon):
    la, lo = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    dla, dlo = la[:, None] - la[None, :], lo[:, None] - lo[None, :]
    a = np.sin(dla / 2) ** 2 + np.cos(la)[:, None] * np.cos(la)[None, :] * np.sin(dlo / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def pct_rank(s):
    """0~1 백분위 순위(동점은 평균 순위). 결측은 결측으로 둔다."""
    return s.rank(pct=True, method="average")
