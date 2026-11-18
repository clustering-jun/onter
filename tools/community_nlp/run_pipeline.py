# -*- coding: utf-8 -*-
"""전체 파이프라인: 원본 → 프로그램 단위 분석 → 단지 집계 → 사전·후보·잠재요인 → 품질 점검 → 산출물 저장.

사용:
  python -m community_nlp.run_pipeline --raw <xlsx> --out <dir> --llm <adjudication.jsonl ...> --val A=<jsonl...> B=<jsonl...>
"""
import argparse
import glob
import hashlib
import json
import os
import shutil
import sys
import time

import numpy as np
import pandas as pd

from . import taxonomy as TX
from . import std_programs as SPM
from . import budget as BG
from . import aggregate as AG
from . import annotation as AN
from . import validate as VA
from . import typology as TY
from . import variants as VR
from . import catalog as CT
from . import qa_checks as QA
from .build_rows import load_raw, build_row_table

OUT_VERSION = "community_nlp_2026_v1"


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def read_llm(paths):
    recs, bad = AN.read_annotations(paths)
    return VA.ann_frame(recs), bad


def save_csv(df, path):
    df.to_csv(path, index=False, encoding="utf-8-sig")


def save_jsonl(df, path):
    """JSONL: None·NaN·빈 문자열 필드는 생략한다(없음 = 결측; 0이 아님)."""
    with open(path, "w", encoding="utf-8") as f:
        for rec in df.to_dict("records"):
            d = {}
            for k, v in rec.items():
                if v is None or (isinstance(v, float) and np.isnan(v)) or (isinstance(v, str) and v == ""):
                    continue
                d[k] = v.item() if hasattr(v, "item") else v
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def codebook_frame():
    rows = []
    def add(kind, mp, extra=None):
        for k, v in mp.items():
            rows.append(dict(code_type=kind, code=k, label=v, note=(extra or {}).get(k, "")))
    add("scope(기록 범위)", TX.SCOPES)
    add("family(표준 유형 가족)", TX.FAMILIES)
    add("purpose(복지 목적)", TX.PURPOSES, {k: "필요분야 " + TX.NEED_DOMAINS[v] for k, v in TX.PURPOSE_TO_NEED.items()})
    add("need_domain(v4 필요 분야)", TX.NEED_DOMAINS)
    add("target(지원 대상)", TX.TARGETS)
    add("service(제공 서비스)", TX.SERVICES)
    add("mode(제공 방식)", TX.MODES)
    add("support_unit(v4 지원 단위)", TX.SUPPORT_UNITS)
    add("op(운영 특성)", TX.OPS)
    add("op_state(운영 특성 상태)", TX.OPS_STATES)
    add("effect(기대 효과)", TX.EFFECTS)
    add("resource(필요 자원)", TX.RESOURCES)
    add("partner_org(협력기관 유형)", TX.ORGS)
    return pd.DataFrame(rows)


def budget_frame():
    rows = []
    for k, (flo, fhi, ulo, uhi, scale, dn, desc) in BG.ARCH.items():
        rows.append(dict(archetype=k, fixed_low_krw=flo, fixed_high_krw=fhi, unit_low_krw=ulo, unit_high_krw=uhi, session_scaling=scale,
                         default_participants=dn, description=desc))
    return pd.DataFrame(rows)


def _insert_id(df, id_map, key="complex_name"):
    """단지명 열 바로 앞에 complex_id(단지통합 엑셀 기준)를 넣는다."""
    if not id_map or key not in df.columns or "complex_id" in df.columns:
        return df
    out = df.copy()
    out.insert(list(out.columns).index(key), "complex_id", out[key].map(id_map))
    return out


def run(raw_path, out_dir, llm_paths=(), val_sets=None, ops_from_llm=False, copy_ann=True, seed=7, skip_robust=False, logf=print, rows=None, raw=None, llm=None,
        id_table=None):
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    for sub in ("validation", "llm_annotations", "figures"):
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
    logf(f"[1/9] 원본 읽기: {raw_path}")
    if raw is None:
        raw = load_raw(raw_path)
    if llm is None:
        llm, bad = read_llm(list(llm_paths)) if llm_paths else (pd.DataFrame(), [])
        if bad:
            logf("LLM 파일 경고:", bad[:5])
    logf(f"      raw {raw.shape}, llm labels {len(llm)}")
    logf("[2/9] 프로그램 단위 분석 테이블 생성")
    if rows is None:
        rows = build_row_table(raw, llm=llm, ops_from_llm=ops_from_llm)
    id_map = None if id_table is None else dict(zip(id_table["단지명"], id_table["complex_id"]))
    rows = _insert_id(rows, id_map)
    logf("[3/9] 별칭 군집·대표 명칭")
    cid, canon = VR.build_alias_clusters(rows)
    rows["alias_cluster_id"] = cid
    rows["canonical_title"] = canon
    logf("[4/9] 표준 프로그램 사전·단지 집계")
    dic = AG.build_dictionary(rows)
    cf = AG.build_complex_features(rows, dic)
    cf = AG.add_gap_features(cf, rows)
    cf, S = AG.add_peers(cf, rows)
    logf("[5/9] 유형화·잠재요인·동시시행")
    cf, tinfo = TY.assign_types(cf, seed=seed)
    wdf, hdf, comp, linfo = AG.latent_factors(rows, dic, cf, seed=seed)
    cf = cf.merge(wdf.reset_index().rename(columns={"index": "complex_name"}), on="complex_name", how="left")
    dic = dic.merge(hdf.reset_index().rename(columns={"index": "std_id"}), on="std_id", how="left")
    cf["summary_ko"] = AG.complex_summary_ko(cf)
    co = AG.cooccurrence(rows, dic, cf=cf)
    cand = AG.build_candidates(cf, rows, dic, S)
    long = AG.build_complex_std_long(rows)
    wide = long.pivot_table(index="complex_name", columns="std_id", values="n_records", fill_value=0).reset_index()
    alias = (rows.groupby(["alias_cluster_id", "std_id", "canonical_title"])
             .agg(n_records=("source_row", "size"), n_complexes=("complex_name", "nunique"), n_title_variants=("title_norm", "nunique"),
                  variants=("program_name_masked", lambda s: " / ".join(s.value_counts().head(5).index)))
             .reset_index().sort_values("n_records", ascending=False))
    cf, cand, long, wide = (_insert_id(x, id_map) for x in (cf, cand, long, wide))
    logf("[6/9] 품질 점검")
    qa = QA.run_checks(raw, rows, dic, cf, cand, long, set(SPM.BY_ID.keys()), id_table=id_table)
    robust = pd.DataFrame() if skip_robust else QA.robustness_test(raw)
    logf("[7/9] LLM 독립 검증 비교")
    val_summaries = {}
    if val_sets:
        for name, paths in val_sets.items():
            ann, badv = read_llm(paths)
            if len(ann) == 0:
                continue
            val_summaries[name] = VA.compare(rows, ann)
    logf("[8/9] 저장")
    P = lambda f: os.path.join(out_dir, f)
    rows_out = rows.copy()
    save_csv(rows_out, P("program_analysis.csv"))
    save_jsonl(rows_out, P("program_analysis.jsonl"))
    save_csv(cf, P("complex_features.csv"))
    save_jsonl(cf, P("complex_features.jsonl"))
    save_csv(long, P("complex_std_matrix_long.csv"))
    save_csv(wide, P("complex_std_matrix_wide.csv"))
    save_csv(cand, P("complex_program_candidates.csv"))
    save_csv(dic, P("standard_program_dictionary.csv"))
    save_jsonl(dic, P("standard_program_dictionary.jsonl"))
    save_csv(alias, P("alias_dictionary.csv"))
    save_csv(_insert_id(wdf.reset_index().rename(columns={"index": "complex_name"}), id_map), P("complex_latent_factors.csv"))
    save_csv(hdf.reset_index().rename(columns={"index": "std_id"}), P("std_latent_factors.csv"))
    save_csv(comp, P("latent_components.csv"))
    save_csv(co, P("std_cooccurrence.csv"))
    save_csv(tinfo["profile"].reset_index(), P("complex_types.csv"))
    save_csv(tinfo["candidates"], P("validation/complex_type_k_selection.csv"))
    save_csv(codebook_frame(), P("codebook_taxonomy.csv"))
    save_csv(budget_frame(), P("budget_assumptions.csv"))
    save_csv(qa, P("validation/qa_checks.csv"))
    if len(robust):
        save_csv(robust, P("validation/robustness_perturbation.csv"))
    return dict(raw=raw, rows=rows, dic=dic, cf=cf, cand=cand, long=long, wide=wide, alias=alias, co=co, comp=comp, tinfo=tinfo, linfo=linfo,
                qa=qa, robust=robust, val=val_summaries, llm=llm, wdf=wdf, hdf=hdf, elapsed=time.time() - t0)
