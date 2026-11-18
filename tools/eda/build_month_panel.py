# -*- coding: utf-8 -*-
"""단지×월 통합 패널: 홈닥터 월별 모델 패널(model_monthly_panel)에 커뮤니티 활동의 월별 집계와 과거 시차 특성을 붙인다.

규칙
- 키는 (complex_id, target_month). 행은 model_monthly_panel과 같다(17,172행; 단지 318 × 54개월).
- 커뮤니티 기록은 2024-01~2026-06에만 있다. 그 전 달과 기록이 없는 단지는 결측(NaN)이며 0이 아니다(community_window=0).
- 커뮤니티 시차 특성은 해당 달 이전 자료만 쓴다(미래 정보 누수 방지). 같은 달의 값은 community_*_same_month로 구분해 두며, 예측 대상 시점에 알 수 없으면 쓰지 않는다.
- 2026-01~06은 보고 지연 가능성이 있어 community_lag_risk=1로 표시한다.
출력: processed/complex_month_panel_20261117_v1/
"""
import os
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "processed")).replace("\\", "/") + "/"
COMM = os.environ.get("EDA_COMMUNITY") or (ROOT + "community_nlp_2026_v1/")
OUT = os.environ.get("PANEL_OUT") or (ROOT + "complex_month_panel_20261117_v1/")
rd = lambda p, **k: pd.read_csv(p, encoding="utf-8-sig", **k)


def main():
    os.makedirs(OUT, exist_ok=True)
    mp = rd(ROOT + "complex_integrated_20261117_v1/data/model_monthly_panel.csv")
    pa = rd(COMM + "program_analysis.csv", usecols=["complex_id", "start_date", "in_resident_scope", "participants_total", "std_id", "std_family", "scope"], low_memory=False)
    pa["month"] = pd.to_datetime(pa["start_date"]).dt.to_period("M").astype(str)
    res = pa[pa["in_resident_scope"] == 1]
    g = pa.groupby(["complex_id", "month"]).size().rename("community_records_all")
    r = res.groupby(["complex_id", "month"]).agg(community_resident_records=("scope", "size"), community_participants=("participants_total", "sum"),
                                                 community_distinct_std=("std_id", "nunique"))
    c = pd.concat([g, r], axis=1).reset_index().rename(columns={"month": "target_month"})
    p = mp.merge(c, on=["complex_id", "target_month"], how="left")
    in_comm = set(pa["complex_id"])
    window = (p["target_month"] >= "2024-01") & (p["target_month"] <= "2026-06")
    p["community_window"] = (window & p["complex_id"].isin(in_comm)).astype(int)
    cols = ["community_records_all", "community_resident_records", "community_participants", "community_distinct_std"]
    for col in cols:        # 관측 창 안의 단지에서 기록이 없는 달은 0, 창 밖·미수록 단지는 결측
        p[col] = np.where(p["community_window"] == 1, p[col].fillna(0), np.nan)
    p = p.rename(columns={c_: c_ + "_same_month" for c_ in cols})
    p = p.sort_values(["complex_id", "target_month"]).reset_index(drop=True)
    base = p.groupby("complex_id")
    for col in ("community_resident_records_same_month", "community_participants_same_month"):
        short = col.replace("_same_month", "")
        sh = base[col].shift(1)
        p[f"{short}_lag1"] = sh
        p[f"{short}_prior3_sum"] = sh.groupby(p["complex_id"]).transform(lambda s: s.rolling(3, min_periods=3).sum().shift(0))
    p["community_lag_risk"] = (p["target_month"] >= "2026-01").astype(int)
    p["hd_per100_households"] = p["recorded_support_count"] / p["recorded_households"] * 100
    p["month_of_year"] = p["target_month"].str[5:].astype(int)
    p["year"] = p["target_month"].str[:4].astype(int)
    first = ["complex_id", "단지명", "target_month", "year", "month_of_year", "suggested_split", "source_observed", "eligible_history6"]
    p = p[first + [c_ for c_ in p.columns if c_ not in first]]
    p.to_csv(OUT + "complex_month_panel.csv", index=False, encoding="utf-8-sig")
    p.to_parquet(OUT + "complex_month_panel.parquet", index=False) if _has_pyarrow() else None
    dd = pd.DataFrame([
        ("complex_id", "단지 기본키(통합표)", "식별자"), ("target_month", "예측 대상 달(YYYY-MM)", "식별자"),
        ("source_observed", "그 달 홈닥터 원자료가 있으면 1(0이면 결측, 0건이 아님)", "품질"), ("eligible_history6", "직전 6개월 이력이 충분하면 1", "학습 가능 조건"),
        ("suggested_split", "시간 분할 제안(2022~24 학습, 2025 검증, 2026 상반기 시험)", "분할"),
        ("recorded_support_count / recorded_households", "홈닥터 지원 건수 / 세대수(기록값)", "대상·분모"),
        ("lag1_*, prior3_*, prior6_*, lag12_support", "홈닥터 과거 값(해당 달 이전만 사용)", "과거 특성"),
        ("community_*_same_month", "같은 달의 커뮤니티 기록 집계. 대상 시점에 알 수 없으면 입력으로 쓰지 않는다", "동시점(누수 주의)"),
        ("community_resident_records_lag1 / _prior3_sum", "직전 달·직전 3개월 합(과거만)", "과거 특성"),
        ("community_window", "그 단지·달이 커뮤니티 관측 창(2024-01~2026-06, 수록 단지)이면 1. 0이면 community_* 는 결측", "품질"),
        ("community_lag_risk", "2026-01 이후 달이면 1(보고 지연으로 과소 계상 가능)", "품질"),
        ("hd_per100_households", "100세대당 지원 건수", "파생"),
    ], columns=["컬럼", "설명", "역할"])
    dd.to_csv(OUT + "column_notes.csv", index=False, encoding="utf-8-sig")
    print(p.shape, "window rows", int(p["community_window"].sum()))
    print(p[p["community_window"] == 1][["community_resident_records_same_month", "community_participants_same_month"]].describe().T)


def _has_pyarrow():
    try:
        import pyarrow  # noqa: F401
        return True
    except Exception:
        return False


if __name__ == "__main__":
    main()
