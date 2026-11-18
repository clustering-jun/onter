# -*- coding: utf-8 -*-
"""원본 파일 설명(이름·크기·SHA256)과 이전 원본과의 차이 비교(보고서·manifest용)."""
import collections
import os

import pandas as pd

from .build_rows import COL_RENAME
from .package import sha256_file

DATE_COLS = ("커뮤니티시작일자", "커뮤니티종료일자")
KEY = ["단지명", "커뮤니티명", "커뮤니티시작일자"]


def describe_source(path):
    xl = pd.ExcelFile(path)
    return dict(name=os.path.basename(path), bytes=int(os.path.getsize(path)), sha256=sha256_file(path), sheets=list(xl.sheet_names))


def _read(path):
    xl = pd.ExcelFile(path)
    sheet = "Sheet1" if "Sheet1" in xl.sheet_names else xl.sheet_names[0]
    return xl.parse(sheet, dtype=object).rename(columns=COL_RENAME)


def _norm(df):
    d = df.copy()
    for c in d.columns:
        if c in DATE_COLS:
            d[c] = pd.to_datetime(d[c], errors="coerce").dt.strftime("%Y-%m-%d")
        else:
            d[c] = d[c].map(lambda x: " ".join(str(x).split()) if isinstance(x, str) else ("" if pd.isna(x) else str(int(x)) if float(x).is_integer() else str(x)))
    return d


def compare_sources(old_path, new_path, with_table=False):
    """이전 원본 대비 갱신 원본: 동일 행·수정 행(단지+명칭+시작일이 같고 다른 열 값이 바뀐 행)·추가 행·삭제 행과 연도별 건수.
    with_table=True이면 결과 dict의 '_table'에 행 단위 변경 목록(DataFrame)을 담는다."""
    o, n = _norm(_read(old_path)), _norm(_read(new_path))
    cols = list(o.columns)
    if list(n.columns) != cols:
        raise ValueError("열 구성이 달라 비교할 수 없다")
    so, sn = o[cols].apply(tuple, axis=1), n[cols].apply(tuple, axis=1)
    o["_row"], n["_row"] = o.index.values + 2, n.index.values + 2      # 엑셀 행 번호(헤더=1행)
    co, cn = collections.Counter(so), collections.Counter(sn)
    identical = sum((co & cn).values())
    o["_sig"], n["_sig"] = so, sn
    # 서명이 같은 행은 두 파일의 공통 개수만큼을 '동일'로 보고, 초과분만 한쪽에만 있는 행으로 센다(완전 중복 행 때문에 일대일이 아닐 수 있음)
    o["_cc"], n["_cc"] = o.groupby("_sig").cumcount(), n.groupby("_sig").cumcount()
    o_only = o[o["_cc"].values >= o["_sig"].map(lambda s: min(co[s], cn.get(s, 0))).values]
    n_only = n[n["_cc"].values >= n["_sig"].map(lambda s: min(cn[s], co.get(s, 0))).values]
    mo = o_only.drop_duplicates(KEY).merge(n_only.drop_duplicates(KEY), on=KEY, suffixes=("_old", "_new"))
    changed = {}
    for c in cols:
        if c in KEY:
            continue
        k = int((mo[c + "_old"] != mo[c + "_new"]).sum())
        if k:
            changed[c] = k
    mk = set(map(tuple, mo[KEY].values))
    n_in = [tuple(r) in mk for r in n_only[KEY].values]
    o_in = [tuple(r) in mk for r in o_only[KEY].values]
    pure_new = n_only[[not x for x in n_in]]
    pure_old = o_only[[not x for x in o_in]]
    yr = lambda df: pd.to_datetime(df["커뮤니티시작일자"], errors="coerce").dt.year.value_counts().sort_index()
    asint = lambda s: {int(k): int(v) for k, v in s.items()}
    table = None
    if with_table:
        tbl = []
        for r in mo.to_dict("records"):
            ch = [c for c in cols if c not in KEY and r[c + "_old"] != r[c + "_new"]]
            tbl.append(dict(change_type="modified", previous_source_row=int(r["_row_old"]), source_row=int(r["_row_new"]), 단지명=r["단지명"], 커뮤니티명=r["커뮤니티명"],
                            시작일자=r["커뮤니티시작일자"], changed_columns="|".join(ch)))
        for r in pure_new.to_dict("records"):
            tbl.append(dict(change_type="added", previous_source_row=None, source_row=int(r["_row"]), 단지명=r["단지명"], 커뮤니티명=r["커뮤니티명"],
                            시작일자=r["커뮤니티시작일자"], changed_columns=""))
        for r in pure_old.to_dict("records"):
            tbl.append(dict(change_type="removed", previous_source_row=int(r["_row"]), source_row=None, 단지명=r["단지명"], 커뮤니티명=r["커뮤니티명"],
                            시작일자=r["커뮤니티시작일자"], changed_columns=""))
        table = pd.DataFrame(tbl)
    out = dict(
        n_old=int(len(o)), n_new=int(len(n)), identical=int(identical), modified=int(len(mo)), modified_old_rows=int(sum(o_in)), modified_new_rows=int(sum(n_in)),
        added=int(len(pure_new)), removed=int(len(pure_old)),
        by_year_old=asint(yr(o)), by_year_new=asint(yr(n)), added_by_year=asint(yr(pure_new)), removed_by_year=asint(yr(pure_old)),
        changed_fields=dict(sorted(changed.items(), key=lambda x: -x[1])),
        n_complex_old=int(o["단지명"].nunique()), n_complex_new=int(n["단지명"].nunique()),
        new_complexes=sorted(set(n["단지명"]) - set(o["단지명"])), removed_complexes=sorted(set(o["단지명"]) - set(n["단지명"])),
        added_months=asint(pd.to_datetime(pure_new["커뮤니티시작일자"], errors="coerce").dt.to_period("M").astype(str).str.replace("-", "").astype(int).value_counts().sort_index()) if len(pure_new) else {},
    )
    if with_table:
        out["_table"] = table
    return out
