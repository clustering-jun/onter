# -*- coding: utf-8 -*-
"""이전 원본에 붙인 LLM 라벨을 갱신 원본의 행으로 옮긴다.

라벨러가 읽은 단위는 '정규화 제목 + 마스킹한 활동내용'(text key)이다. 원본이 갱신되어도 같은 text key의 행은 같은 활동 문구이므로
라벨을 그대로 쓰고, 문구가 바뀌었거나 새로 생긴 행은 옮기지 않는다(재판정 대상). 행 번호(source_row)는 갱신 원본 기준으로 다시 붙인다.
"""
from collections import defaultdict, deque

import numpy as np
import pandas as pd

from .build_rows import load_raw
from .text_utils import compact, mask_sensitive, title_norm


def text_key(name, complex_name, content):
    return title_norm(mask_sensitive(name), complex_name) + "|" + compact(mask_sensitive(content))


def reference_table(raw_path):
    """라벨이 붙은 이전 원본의 (source_row, complex, start, key)."""
    raw = load_raw(raw_path)
    key = [text_key(n, c, a) for n, c, a in zip(raw["커뮤니티명"], raw["단지명"], raw["활동내용"])]
    return pd.DataFrame(dict(source_row=raw["source_row"].values, complex=raw["단지명"].values,
                             start=raw["커뮤니티시작일자"].dt.strftime("%Y-%m-%d").values, key=key))


def current_table(rows):
    """갱신 원본 분석 행(build_row_table 결과)의 (source_row, complex, start, key)."""
    key = (rows["title_norm"] + "|" + rows["activity_content_masked"].map(compact)).values
    return pd.DataFrame(dict(source_row=rows["source_row"].values, complex=rows["complex_name"].values,
                             start=rows["start_date"].values, key=key))


def row_map(ref, cur):
    """이전 원본 행 → 갱신 원본 행 대응. 우선순위: (단지, 시작일, key) 일대일 → (단지, key) → key.
    반환: DataFrame(old_row, new_row, level) — level=exact/complex_text/text/none."""
    exact = defaultdict(deque)
    by_ck, by_k = {}, {}
    for r in cur.itertuples(index=False):
        exact[(r.complex, r.start, r.key)].append(r.source_row)
        by_ck.setdefault((r.complex, r.key), r.source_row)
        by_k.setdefault(r.key, r.source_row)
    out = []
    for r in ref.itertuples(index=False):
        q = exact.get((r.complex, r.start, r.key))
        if q:
            out.append((r.source_row, q.popleft(), "exact"))
            continue
        v = by_ck.get((r.complex, r.key))
        if v is not None:
            out.append((r.source_row, v, "complex_text"))
            continue
        v = by_k.get(r.key)
        if v is not None:
            out.append((r.source_row, v, "text"))
            continue
        out.append((r.source_row, np.nan, "none"))
    return pd.DataFrame(out, columns=["old_row", "new_row", "level"])


def transfer(frame, rmap):
    """라벨 프레임의 source_row를 갱신 원본 행 번호로 바꾼다(대응이 없는 라벨은 버린다). 원래 번호는 source_row_old에 보존."""
    if frame is None or len(frame) == 0:
        return frame
    m = rmap.dropna(subset=["new_row"]).set_index("old_row")["new_row"]
    g = frame.copy()
    g["source_row_old"] = g["source_row"]
    g["source_row"] = g["source_row"].map(m)
    g = g.dropna(subset=["source_row"])
    g["source_row"] = g["source_row"].astype(int)
    return g.drop_duplicates("source_row").reset_index(drop=True)


def pending_keys(rows_rule, llm):
    """규칙이 불확실(검토 사유)하거나 중간 확신인데 아직 LLM 판정이 없는 text key를 대표 행 1개씩 반환한다.
    정책은 이전 판정 단계와 같다: 불확실(flagged)·medium 확신 행은 LLM이 최종 판정하고, high 확신 행은 규칙 라벨을 유지한다."""
    key = pd.Series((rows_rule["title_norm"] + "|" + rows_rule["activity_content_masked"].map(compact)).values, index=rows_rule["source_row"].values)
    labelled = set(key.loc[key.index.isin(llm["source_row"])]) if llm is not None and len(llm) else set()
    d = rows_rule.assign(key=key.values)
    d["need"] = ((d["needs_llm_review"] == 1) | (d["std_confidence"] == "medium")).astype(int)
    g = d.groupby("key").agg(n_rows=("source_row", "size"), need=("need", "max"), flagged=("needs_llm_review", "max"), rep_row=("source_row", "min"))
    g = g[(g["need"] == 1) & (~g.index.isin(labelled))].reset_index()
    g["reason"] = np.where(g["flagged"] == 1, "flagged", "medium")
    return g.sort_values("rep_row").reset_index(drop=True)
