# -*- coding: utf-8 -*-
"""산출물 포장: manifest·체크섬·스키마·엑셀 요약 통합본."""
import hashlib
import json
import os
import datetime as dt
import numpy as np
import pandas as pd


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def write_checksums(out_dir, exclude=("file_checksums.json",)):
    items = {}
    for root, _, files in os.walk(out_dir):
        for fn in sorted(files):
            if fn in exclude:
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, out_dir).replace("\\", "/")
            items[rel] = dict(sha256=sha256_file(p), bytes=os.path.getsize(p))
    with open(os.path.join(out_dir, "file_checksums.json"), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return items


def _json_safe(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (pd.Timestamp, dt.date)):
        return str(o)
    return str(o)


def write_manifest(out_dir, manifest):
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=_json_safe)


def write_schemas(out_dir, frames, catalogs):
    """frames: {파일명: DataFrame}, catalogs: {파일명: 카탈로그 DataFrame(feature, role, definition...)}"""
    out = {}
    for name, df in frames.items():
        cat = catalogs.get(name)
        cmap = {}
        if cat is not None:
            cmap = cat.set_index("feature")[["role", "definition", "unit_denominator", "window", "missing_handling"]].to_dict("index")
        out[name] = dict(
            n_rows=int(len(df)),
            fields=[dict(name=c, dtype=str(df[c].dtype), nullable=bool(df[c].isna().any()), **cmap.get(c, {})) for c in df.columns])
    with open(os.path.join(out_dir, "record_schemas.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=_json_safe)


def write_xlsx(path, sheets, col_widths=None):
    """sheets: {시트명: DataFrame}. 시트명은 31자 이하."""
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, df in sheets.items():
            d = df.copy()
            d.to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            ws.freeze_panes = "B2"
            for i, c in enumerate(d.columns, 1):
                w = min(48, max(8, int(d[c].astype(str).str.len().quantile(0.9)) + 2 if len(d) else 10, len(str(c)) + 2))
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
