# -*- coding: utf-8 -*-
"""분석 보고서(Markdown) 생성: 모든 수치는 최종 산출 데이터에서 계산해 삽입한다(서술은 수치에 종속)."""
import numpy as np
import pandas as pd

from . import taxonomy as TX
from . import budget as BG
from .std_programs import TYPES, BY_ID


def md_table(df, floatfmt=None, max_rows=None):
    d = df.copy()
    if max_rows:
        d = d.head(max_rows)
    cols = list(d.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for i in range(len(d)):
        cells = []
        for c in cols:
            v = d[c].iloc[i]          # 열 dtype 보존(iterrows는 정수를 float로 올려 'k=3.00'처럼 보이게 함)
            if isinstance(v, (float, np.floating)):
                if np.isnan(v):
                    cells.append("")
                elif floatfmt and c in floatfmt:
                    cells.append(floatfmt[c].format(v))
                else:
                    cells.append(f"{v:,.2f}" if abs(v) < 1000 else f"{v:,.0f}")
            elif isinstance(v, (int, np.integer)):
                cells.append(f"{int(v):,}")
            else:
                cells.append(str(v).replace("|", "/"))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def validation_tables(val):
    """val: {표본명: compare 결과} → 요약 표 DataFrame."""
    rows = []
    for name, v in val.items():
        t = v["ops_table"].set_index("op")
        tg = v["target_table"]
        tg2 = tg[tg["target"] != "ALL"]
        tp, fp, fn = tg2["tp"].sum(), tg2["fp"].sum(), tg2["fn"].sum()
        p = tp / (tp + fp) if tp + fp else np.nan
        r = tp / (tp + fn) if tp + fn else np.nan
        f = 2 * p * r / (p + r) if (p + r) else np.nan
        rows.append({
            "표본": name, "행 수": v["n"], "범위(scope) 일치": v["scope_acc"], "주민 대상 여부 일치": v["resident_scope_agree"],
            "표준 유형 일치": v["std_acc_valid"], "유형 가족 일치": v["family_acc_valid"],
            "주 목적 일치": v["purpose_primary_acc"], "목적 겹침": v["purpose_set_overlap"],
            "대상 F1(ALL 제외)": f,
            "상시 이진": t.loc["ALW", "binary_YP_agree"], "정기 이진": t.loc["REG", "binary_YP_agree"], "행사 이진": t.loc["EVT", "binary_YP_agree"],
            "수시 이진": t.loc["ADH", "binary_YP_agree"], "계절 이진": t.loc["SEA", "binary_YP_agree"],
        })
    return pd.DataFrame(rows)


def conf_strata_table(val):
    rows = []
    for name, v in val.items():
        for k, d in v["std_by_confidence"].items():
            rows.append({"표본": name, "규칙 확신": k, "행 수": d["n"], "유형 일치": d["std_acc"], "가족 일치": d["family_acc"]})
    return pd.DataFrame(rows)


def ops_kappa_table(v):
    t = v["ops_table"].copy()
    t = t[["label", "exact_agree", "kappa_exact", "binary_YP_agree", "kappa_binary_YP", "rule_Y_share", "llm_Y_share", "rule_YP_share", "llm_YP_share"]]
    t.columns = ["운영 특성", "4상태 정확 일치", "κ(4상태)", "이진 일치(Y·P)", "κ(이진)", "규칙 Y 비율", "LLM Y 비율", "규칙 Y·P 비율", "LLM Y·P 비율"]
    return t


def dictionary_summary(dic):
    d = dic[(dic["n_records"] > 0)].copy()
    d = d.sort_values("n_records", ascending=False)
    out = d[["std_id", "std_name", "std_family_label", "scope_label", "n_records", "n_complexes", "adoption_rate", "op_evt_Y_share", "op_reg_YP_share", "est_cost_mid_median_krw"]].copy()
    out.columns = ["ID", "표준 프로그램", "가족", "범위", "기록 수", "시행 단지", "채택률", "행사형(Y) 비율", "정기(Y·P) 비율", "건당 추정 예산 중앙(원)"]
    out["채택률"] = out["채택률"].map(lambda x: f"{x * 100:.0f}%")
    out["행사형(Y) 비율"] = out["행사형(Y) 비율"].map(lambda x: f"{x * 100:.0f}%")
    out["정기(Y·P) 비율"] = out["정기(Y·P) 비율"].map(lambda x: f"{x * 100:.0f}%")
    out["건당 추정 예산 중앙(원)"] = out["건당 추정 예산 중앙(원)"].map(lambda x: f"{x:,.0f}")
    return out
