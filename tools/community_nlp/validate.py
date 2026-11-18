# -*- coding: utf-8 -*-
"""독립 LLM 라벨러 결과와 파이프라인 라벨의 일치도 평가 + 정합성 점검."""
import json
import re
import numpy as np
import pandas as pd

from .std_programs import BY_ID
from .text_utils import compact
from . import taxonomy as TX

OPS_KEYS = ["ALW", "REG", "EVT", "ADH", "SEA"]
_SEASONAL_CARE = r"(명절|설맞이|추석|새해|연말|폭염|무더위|한파|겨울나기|혹서|혹한|여름나기)"
OPS_COL = {"ALW": "op_always", "REG": "op_regular", "EVT": "op_event", "ADH": "op_adhoc", "SEA": "op_seasonal"}
STATES = ["Y", "P", "N", "U"]


def ann_frame(recs):
    out = []
    for d in recs:
        try:
            ops = d.get("ops", {}) or {}
            out.append(dict(source_row=int(d["r"]), llm_scope=d.get("scope", ""), llm_std=d.get("std", ""), llm_new_name=d.get("new_name", ""),
                            llm_p1=d.get("p1", ""), llm_p2="|".join(d.get("p2", []) or []), llm_tg="|".join(d.get("tg", []) or []),
                            llm_conf=d.get("conf", ""), llm_why=d.get("why", ""),
                            **{f"llm_op_{k}": ops.get(k, "") for k in OPS_KEYS}))
        except Exception:
            continue
    return pd.DataFrame(out)


def cohen_kappa(a, b, labels=None):
    a = pd.Series(a).astype(str).values
    b = pd.Series(b).astype(str).values
    labels = labels or sorted(set(a) | set(b))
    n = len(a)
    if n == 0:
        return np.nan
    po = (a == b).mean()
    pe = sum(((a == l).mean()) * ((b == l).mean()) for l in labels)
    return float((po - pe) / (1 - pe)) if pe < 1 else 1.0


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else np.nan
    r = tp / (tp + fn) if tp + fn else np.nan
    f = 2 * p * r / (p + r) if (p == p and r == r and (p + r) > 0) else np.nan
    return p, r, f


def compare(rows, ann, rule_prefix="", rule_cols=None, ignore_repeat_basis=True, harmonize=True):
    """rows: 파이프라인 라벨(규칙 또는 최종). rows의 llm_* 감사 열은 비교용 llm_* 열과 충돌하므로 제외한다."""
    rows = rows.drop(columns=[c for c in rows.columns if c.startswith("llm_")], errors="ignore")
    m = rows.merge(ann, on="source_row", how="inner")
    m["llm_std_raw"] = m["llm_std"]
    if harmonize:
        # 지침 v1.1의 '관리홈닥터 세대→B05' 문구와 사전 설계(계절 돌봄 물품 전달=B01)의 불일치를 최종 라벨과 같은 방식으로 보정한다.
        cue = (m["program_name_masked"].astype(str) + m["activity_content_masked"].astype(str)).map(compact).str.contains(_SEASONAL_CARE, regex=True)
        m.loc[(m["llm_std"] == "B05") & cue, "llm_std"] = "B01"
    if ignore_repeat_basis:
        # 라벨러는 다른 기록(반복 이력)을 보지 못하므로, 반복 기록만을 근거로 한 정기형 P는 레코드 수준 비교에서 U로 본다.
        only_repeat = m["op_basis"].str.contains(r"REG:repeat", regex=True) & (m["op_regular"] == "P")
        m.loc[only_repeat, "op_regular"] = "U"
    res = {}
    n = len(m)
    res["n"] = n
    # 범위
    res["scope_acc"] = float((m["scope"] == m["llm_scope"]).mean())
    resident_rule = m["scope"].isin(TX.RESIDENT_SCOPES)
    resident_llm = m["llm_scope"].isin(TX.RESIDENT_SCOPES)
    res["resident_scope_agree"] = float((resident_rule == resident_llm).mean())
    res["scope_kappa"] = cohen_kappa(m["scope"], m["llm_scope"])
    # 표준 유형
    m["llm_family"] = m["llm_std"].map(lambda x: BY_ID[x]["fam"] if x in BY_ID else ("F99" if x in ("Z99", "NEW") else ""))
    valid = m["llm_std"].isin(list(BY_ID.keys()))
    res["llm_valid_std_share"] = float(valid.mean())
    res["llm_NEW_share"] = float((m["llm_std"] == "NEW").mean())
    res["llm_Z99_share"] = float((m["llm_std"] == "Z99").mean())
    res["std_acc_all"] = float((m["std_id"] == m["llm_std"]).mean())
    res["std_acc_valid"] = float((m.loc[valid, "std_id"] == m.loc[valid, "llm_std"]).mean())
    res["family_acc_valid"] = float((m.loc[valid, "std_family"] == m.loc[valid, "llm_family"]).mean())
    strata = {}
    for c in ["high", "medium", "low"]:
        s = m[(m["std_confidence"] == c) & valid]
        strata[c] = dict(n=int(len(s)), std_acc=float((s["std_id"] == s["llm_std"]).mean()) if len(s) else np.nan,
                         family_acc=float((s["std_family"] == s["llm_family"]).mean()) if len(s) else np.nan)
    res["std_by_confidence"] = strata
    conf_pairs = m[valid & (m["std_id"] != m["llm_std"])].groupby(["std_id", "llm_std"]).size().sort_values(ascending=False).head(40)
    res["confusions"] = conf_pairs.reset_index().rename(columns={0: "n"})
    # 목적
    res["purpose_primary_acc"] = float((m["purpose_primary"] == m["llm_p1"]).mean())
    def _plist(r):
        return set([r["purpose_primary"]] + [x for x in str(r["purpose_secondary"]).split("|") if x])
    def _llist(r):
        return set([r["llm_p1"]] + [x for x in str(r["llm_p2"]).split("|") if x])
    res["purpose_set_overlap"] = float(np.mean([len(_plist(r) & _llist(r)) > 0 for _, r in m.iterrows()]))
    # 대상(원문 명시)
    tg_rows = []
    for k in TX.TARGETS:
        rule = m["target_explicit"].map(lambda x: k in str(x).split("|"))
        llm = m["llm_tg"].map(lambda x: k in str(x).split("|"))
        tp = int((rule & llm).sum()); fp = int((rule & ~llm).sum()); fn = int((~rule & llm).sum())
        p, r_, f = prf(tp, fp, fn)
        tg_rows.append(dict(target=k, label=TX.TARGETS[k], support_llm=int(llm.sum()), support_rule=int(rule.sum()), tp=tp, fp=fp, fn=fn,
                            precision=p, recall=r_, f1=f))
    tg = pd.DataFrame(tg_rows)
    res["target_table"] = tg
    TP = tg["tp"].sum(); FP = tg["fp"].sum(); FN = tg["fn"].sum()
    res["target_micro_prf"] = prf(TP, FP, FN)
    # 운영 특성
    ops_rows = []
    cms = {}
    for k in OPS_KEYS:
        a = m[OPS_COL[k]].astype(str); b = m[f"llm_op_{k}"].astype(str)
        exact = float((a == b).mean())
        pa = a.isin(["Y", "P"]); pb = b.isin(["Y", "P"])
        ya = a == "Y"; yb = b == "Y"
        ops_rows.append(dict(op=k, label=TX.OPS[k], exact_agree=exact, kappa_exact=cohen_kappa(a, b, STATES),
                             binary_YP_agree=float((pa == pb).mean()), kappa_binary_YP=cohen_kappa(pa, pb),
                             strict_Y_agree=float((ya == yb).mean()), kappa_strict_Y=cohen_kappa(ya, yb),
                             rule_Y_share=float(ya.mean()), llm_Y_share=float(yb.mean()), rule_YP_share=float(pa.mean()), llm_YP_share=float(pb.mean())))
        cms[k] = pd.crosstab(a, b).reindex(index=STATES, columns=STATES, fill_value=0)
    res["ops_table"] = pd.DataFrame(ops_rows)
    res["ops_confusion"] = cms
    res["merged"] = m
    return res
