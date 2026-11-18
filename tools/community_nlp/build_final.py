# -*- coding: utf-8 -*-
"""최종 산출물 생성: 규칙 엔진 + 독립 LLM 판정 → 프로그램·단지·사전·후보 특성 → 품질 검증 → 그림·카탈로그·보고서·README 저장.

annotation_dir 구조:  A/out_A_*.jsonl (규칙 개발용 블라인드 표본), ADJ/·ADJ2/out_*.jsonl (규칙이 불확실·중간 확신 행의 LLM 판정),
                      B/out_B_*.jsonl (최종 독립 검증 표본). 라벨러 원 응답은 산출물 폴더의 llm_annotations/에 보존한다.
"""
import glob
import json
import os
import shutil
import sys
import time

import numpy as np
import pandas as pd

from . import annotation as AN
from . import validate as VA
from . import run_pipeline as RP
from . import catalog as CT
from . import figures as FG
from . import package as PK
from . import report_build as RB
from . import budget as BG
from . import label_transfer as LT
from . import source_diff as SD
from . import integrated as LI
from . import analysis_extra as AX
from . import figures_extra as FGX
from .build_rows import load_raw, build_row_table
from .text_utils import compact, mask_sensitive


def _read(paths):
    recs, bad = AN.read_annotations(sorted(paths))
    return VA.ann_frame(recs), bad


def make_llm_frame(rows0, A, ADJ):
    """판정을 동일 텍스트(title_norm+내용)의 모든 행으로 전파한다. ADJ는 'batch' 열(ADJ/ADJ2)을 가진 프레임."""
    key = (rows0["title_norm"] + "|" + rows0["activity_content_masked"].map(compact)).values
    kmap = dict(zip(rows0["source_row"].values, key))
    lab = pd.concat([ADJ, A.assign(batch="A")], ignore_index=True)
    lab["key"] = lab["source_row"].map(kmap)
    lab = lab.dropna(subset=["key"]).drop_duplicates("key", keep="first")
    base = pd.DataFrame({"source_row": rows0["source_row"].values, "key": key})
    out = base.merge(lab.rename(columns={"source_row": "label_row"}), on="key", how="inner")
    # 동일 텍스트는 동일 라벨: 규칙이 불확실한 행이 있는 텍스트 그룹, 또는 LLM 판정 배치(ADJ·ADJ2)로 보낸 그룹은 LLM 판정으로 확정한다.
    flag_keys = set(key[((rows0["needs_llm_review"] == 1) | (rows0["std_confidence"] == "medium")).values])    # 불확실·중간 확신 문구는 LLM 판정이 최종
    out["force"] = out["key"].isin(flag_keys) | out["batch"].isin(["ADJ", "ADJ2", "ADJ3"])
    out["batch"] = np.where(out["source_row"] == out["label_row"], out["batch"], out["batch"] + "+propagated")
    return out.drop(columns=["key", "label_row"])


def batch_completion(ann_dir, sub, pat):
    """배치별 입력 행 수와 산출 행 수(라벨러가 중간에 중단된 배치를 확인하기 위함)."""
    out = []
    for inp in sorted(glob.glob(os.path.join(ann_dir, sub, f"{pat}_*.jsonl"))):
        b = os.path.basename(inp)[:-6]
        n_in = sum(1 for ln in open(inp, encoding="utf-8") if ln.strip())
        o = os.path.join(ann_dir, sub, f"out_{b}.jsonl")
        n_out = sum(1 for ln in open(o, encoding="utf-8") if ln.strip()) if os.path.exists(o) else 0
        out.append(dict(batch=b, n_input=n_in, n_output=n_out))
    return out


def _label_source_table(v):
    m = v["merged"].copy()
    from .std_programs import BY_ID
    m["fam_llm"] = m["llm_std"].map(lambda x: BY_ID[x]["fam"] if x in BY_ID else "")
    m["valid"] = m["llm_std"].isin(list(BY_ID.keys()))
    m = m[m["valid"]]
    g = m.groupby("label_source").apply(lambda d: pd.Series(dict(n=len(d), std_acc=(d["std_id"] == d["llm_std"]).mean(),
                                                                  fam_acc=(d["std_family"] == d["fam_llm"]).mean())), include_groups=False)
    g = g.reset_index().rename(columns={"label_source": "라벨 출처", "n": "행 수", "std_acc": "유형 일치", "fam_acc": "가족 일치"})
    g["행 수"] = g["행 수"].astype(int)
    g["라벨 출처"] = g["라벨 출처"].map({"rule": "규칙 확정", "llm": "LLM 판정 확정"}).fillna(g["라벨 출처"])
    return g


def build(raw_path, ann_dir, logf=print, label_ref_path=None, id_table=None):
    """label_ref_path: A·ADJ·ADJ2·B 라벨이 붙은 이전 원본. 주면 같은 활동 문구(text key)의 행으로 라벨을 옮긴다.
    ADJ3(갱신 원본에서 새로 판정한 배치)는 현재 원본 행 번호를 쓰므로 옮기지 않는다."""
    raw_full = load_raw(raw_path)
    raw = raw_full
    scope = dict(n_source_rows=int(len(raw_full)), n_source_complexes=int(raw_full["단지명"].nunique()), n_rows=int(len(raw_full)), n_excluded_rows=0, excluded_complexes={})
    if id_table is not None:      # 통합표에 없는 단지는 분석에서 제외한다(source_row는 원본 엑셀 행 번호 그대로)
        inn = raw_full["단지명"].isin(set(id_table["단지명"]))
        excl = raw_full.loc[~inn]
        raw = raw_full.loc[inn].copy()
        raw.attrs.update(raw_full.attrs)
        scope.update(n_rows=int(len(raw)), n_excluded_rows=int(len(excl)), excluded_complexes={k: int(v) for k, v in excl["단지명"].value_counts().items()})
        logf("통합표 기준 단지 필터:", scope)
    A, bA = _read(glob.glob(os.path.join(ann_dir, "A", "out_A_*.jsonl")))
    J1, bJ1 = _read(glob.glob(os.path.join(ann_dir, "ADJ", "out_ADJ_*.jsonl")))
    J2, bJ2 = _read(glob.glob(os.path.join(ann_dir, "ADJ2", "out_ADJ2_*.jsonl")))
    J3, bJ3 = _read(glob.glob(os.path.join(ann_dir, "ADJ3", "out_ADJ3_*.jsonl")))
    B, bB = _read(glob.glob(os.path.join(ann_dir, "B", "out_B_*.jsonl")))
    B1, _ = _read(glob.glob(os.path.join(ann_dir, "B", "out_B_01.jsonl")))
    B23, _ = _read(glob.glob(os.path.join(ann_dir, "B", "out_B_02.jsonl")) + glob.glob(os.path.join(ann_dir, "B", "out_B_03.jsonl")))
    rows_rule = build_row_table(raw)                                  # 규칙 엔진 단독 결과(검증·비교용)
    info = dict(n_labels_old=dict(A=len(A), ADJ=len(J1), ADJ2=len(J2), B=len(B)), n_labels_new=dict(ADJ3=len(J3)), row_map=None, transfer={}, scope=scope)
    map_csv = os.path.join(ann_dir, "previous_to_current_row_map.csv")
    rmap = None
    if label_ref_path:
        rmap = LT.row_map(LT.reference_table(label_ref_path), LT.current_table(rows_rule))
    elif os.path.exists(map_csv):     # 산출물의 llm_annotations/를 그대로 쓰면 저장된 이전→현재 행 번호 대응표로 옮긴다(이전 원본이 없어도 재현 가능)
        rmap = pd.read_csv(map_csv, encoding="utf-8-sig").rename(columns={"previous_source_row": "old_row", "source_row": "new_row", "match_level": "level"})
    if rmap is not None:
        info["row_map"] = rmap
        info["transfer"] = {"이전 원본 행": int(len(rmap)), "갱신 원본에서 같은 문구로 찾은 행": int(rmap["new_row"].notna().sum()),
                            "일치 수준": {k: int(v) for k, v in rmap["level"].value_counts().items()}}
        A, J1, J2, B, B1, B23 = (LT.transfer(f, rmap) for f in (A, J1, J2, B, B1, B23))
    present = set(rows_rule["source_row"])         # 분석 대상 행에 해당하는 라벨만 쓴다(제외 단지의 라벨은 버린다)
    A, J1, J2, J3, B, B1, B23 = (f if f is None or len(f) == 0 else f[f["source_row"].isin(present)].reset_index(drop=True) for f in (A, J1, J2, J3, B, B1, B23))
    info["n_labels_transferred"] = dict(A=len(A), ADJ=len(J1), ADJ2=len(J2), B=len(B))
    info["n_labels_new"] = dict(ADJ3=len(J3))
    if rmap is not None:
        logf("라벨 이월:", info["n_labels_old"], "→", info["n_labels_transferred"], info["transfer"])
    parts = [f.assign(batch=b) for f, b in ((J1, "ADJ"), (J2, "ADJ2"), (J3, "ADJ3")) if len(f)]
    ADJ = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=list(A.columns) + ["batch"])
    logf(f"LLM labels: A={len(A)} ADJ={len(J1)} ADJ2={len(J2)} ADJ3={len(J3)} B={len(B)}  bad={len(bA) + len(bJ1) + len(bJ2) + len(bJ3) + len(bB)}")
    llm = make_llm_frame(rows_rule, A, ADJ)
    logf(f"LLM frame rows (after propagation): {len(llm)}")
    val_rule = {}
    if len(A):
        val_rule["A(규칙 개발 표본, 규칙 단독)"] = VA.compare(rows_rule, A)
    if len(B):
        val_rule["B(독립 표본, 규칙 단독)"] = VA.compare(rows_rule, B)
    return raw, rows_rule, llm, A, ADJ, B, val_rule, (B1, B23), info


def finalize(raw_path, ann_dir, out_dir, guideline_paths=(), seed=7, logf=print, label_ref_path=None, integrated_path=None):
    t0 = time.time()
    ig = LI.load_integrated(integrated_path) if integrated_path else None
    idt = LI.id_table(ig) if ig is not None else None
    upd_tbl = None
    raw, rows_rule, llm, A, ADJ, B, val_rule, (B1, B23), info = build(raw_path, ann_dir, logf, label_ref_path, id_table=idt)
    rows_final = build_row_table(raw, llm=llm)
    logf("최종 행 테이블:", rows_final.shape, rows_final["label_source"].value_counts().to_dict())
    res = RP.run(raw_path, out_dir, rows=rows_final, raw=raw, llm=llm, seed=seed, logf=logf, id_table=idt)
    res["id_table"] = idt
    meta = dict(src=SD.describe_source(raw_path), sheet=raw.attrs.get("sheet"), n_cols=int(raw.shape[1] - 1),
                label_info={k: v for k, v in info.items() if k != "row_map"},
                batch_completion={s: batch_completion(ann_dir, s, s) for s in ("A", "ADJ", "ADJ2", "ADJ3", "B", "C")}, scope=info["scope"])
    if idt is not None:
        meta["id_source"] = SD.describe_source(integrated_path)
        meta["n_integrated"] = int(len(idt))
        meta["n_integrated_without_records"] = int(len(set(idt["단지명"]) - set(rows_final["complex_name"])))
    if label_ref_path:
        meta["ref"] = SD.describe_source(label_ref_path)
        meta["update"] = SD.compare_sources(label_ref_path, raw_path, with_table=True)
        chg = meta["update"].pop("_table")
        chg["커뮤니티명"] = chg["커뮤니티명"].map(mask_sensitive)                      # 식별 패턴은 이 목록에서도 가린다
        for c in ("previous_source_row", "source_row"):
            chg[c] = chg[c].astype("Int64")                                          # 행 번호는 정수로(결측은 빈 칸)
        if idt is not None:
            idm = dict(zip(idt["단지명"], idt["complex_id"]))
            chg.insert(list(chg.columns).index("단지명"), "complex_id", chg["단지명"].map(idm))
            chg["in_analysis"] = chg["단지명"].isin(idm).astype(int)                  # 통합표에 없어 분석에서 뺀 단지는 0
        chg.to_csv(os.path.join(out_dir, "validation", "source_update_changes.csv"), index=False, encoding="utf-8-sig")
        upd_tbl = chg
    # ── LLM이 '목록에 맞는 유형이 없다(NEW/Z99)'고 답한 문구: 사전 보완 후보 ──
    nz = rows_final[rows_final["std_id_llm"].isin(["NEW", "Z99"])]
    gap = (nz.assign(llm_new_name=nz["llm_new_name"].replace("", "(이름 없음·내용 불명)"))
           .groupby(["std_id_llm", "llm_new_name"])
           .agg(n_rows=("source_row", "size"), n_complexes=("complex_name", "nunique"),
                final_std=("std_id", lambda s: " / ".join(f"{k}×{v}" for k, v in s.value_counts().items())),
                final_confidence=("std_confidence", lambda s: " / ".join(f"{k}×{v}" for k, v in s.value_counts().items())),
                example_titles=("program_name_masked", lambda s: " / ".join(s.drop_duplicates().head(3))),
                example_source_rows=("source_row", lambda s: "|".join(str(x) for x in s.head(5))))
           .reset_index().sort_values(["n_rows"], ascending=False))
    gap.to_csv(os.path.join(out_dir, "validation", "dictionary_gap_candidates.csv"), index=False, encoding="utf-8-sig")
    z_ans = nz[nz["std_id_llm"] == "Z99"]
    n_ans = nz[nz["std_id_llm"] == "NEW"]
    hi_nz = n_ans[n_ans["std_confidence"] == "high"]          # NEW 응답인데 규칙이 high 확신으로 사전 유형에 연결한 행
    meta["new_type"] = dict(n_rows=int(len(nz)), n_new=int((nz["std_id_llm"] == "NEW").sum()), n_z99=int((nz["std_id_llm"] == "Z99").sum()),
                            n_rule_high=int(len(hi_nz)), high_by_std={k: int(v) for k, v in hi_nz["std_id"].value_counts().items()},
                            n_added_types=int(hi_nz["std_id"].isin(["E06", "H06", "I10", "M05"]).sum()),
                            n_new_high=int((n_ans["std_confidence"] == "high").sum()), n_new_review=int((n_ans["needs_llm_review"] == 1).sum()),
                            n_z99_to_z99=int((z_ans["std_id"] == "Z99").sum()), n_z99_other=int((z_ans["std_id"] != "Z99").sum()),
                            n_review=int((nz["needs_llm_review"] == 1).sum()), n_final_z99=int(((nz["needs_llm_review"] == 1) & (nz["std_id"] == "Z99")).sum()),
                            n_names=int(gap.loc[gap["std_id_llm"] == "NEW", "llm_new_name"].nunique()))
    res["meta"] = meta
    P = lambda f: os.path.join(out_dir, f)
    os.makedirs(P("source_snapshot"), exist_ok=True)            # 재현을 위해 분석에 쓴 원본 엑셀의 사본을 함께 둔다(원본 파일은 변경하지 않는다)
    shutil.copy2(raw_path, P("source_snapshot/" + os.path.basename(raw_path)))
    # ── 검증 결과 저장 ──
    val_final = {}
    if len(B):
        vf = VA.compare(rows_final, B)
        vf["by_label_source"] = _label_source_table(vf)
        val_final["B(독립 표본, 최종 라벨)"] = vf
        if len(B1) and len(B23):
            v1 = VA.compare(rows_final, B1)
            v23 = VA.compare(rows_final, B23)
            val_final[f"B1(규칙 보정 시 참고한 {v1['n']}행, 최종 라벨)"] = v1
            val_final[f"B2·B3(보정에 쓰지 않은 {v23['n']}행, 최종 라벨)"] = v23
    C, _ = _read(glob.glob(os.path.join(ann_dir, "C", "out_C_*.jsonl")))
    n_c_all = int(len(C))
    if len(C):
        C = C[C["source_row"].isin(set(rows_final["source_row"]))].reset_index(drop=True)      # 제외 단지의 행은 뺀다
    if len(C):
        c_info = dict(n=int(len(C)), n_excluded=n_c_all - int(len(C)))
        if label_ref_path:     # C는 갱신 반영 시점의 새·변경 문구로 뽑았으므로, 이후 마스킹 보강으로 이전 파일과 같은 문구로 확인된 행 수를 센다
            oldkeys = set(LT.reference_table(label_ref_path)["key"])
            key_final = rows_final["title_norm"] + "|" + rows_final["activity_content_masked"].map(compact)
            c_info["n_same_text_as_previous"] = int(key_final[rows_final["source_row"].isin(C["source_row"])].isin(oldkeys).sum())
        meta["c_info"] = c_info
        vc = VA.compare(rows_final, C)
        vc["by_label_source"] = _label_source_table(vc)
        val_final["C(갱신분 신규 문구 표본, 최종 라벨)"] = vc
    res["val"] = val_rule
    res["val_final"] = val_final
    vt = []
    from .report import validation_tables
    for name, d in list(val_rule.items()) + list(val_final.items()):
        vt.append(validation_tables({name: d}))
    vsum = pd.concat(vt, ignore_index=True) if vt else pd.DataFrame()
    vsum.to_csv(P("validation/llm_validation_summary.csv"), index=False, encoding="utf-8-sig")
    for name, d in list(val_rule.items()) + list(val_final.items()):
        tag = name.split("(")[0] + ("_final" if "최종" in name else "_rule")
        d["ops_table"].to_csv(P(f"validation/ops_agreement_{tag}.csv"), index=False, encoding="utf-8-sig")
        d["target_table"].to_csv(P(f"validation/target_agreement_{tag}.csv"), index=False, encoding="utf-8-sig")
        d["confusions"].to_csv(P(f"validation/std_confusions_{tag}.csv"), index=False, encoding="utf-8-sig")
        keep = ["source_row", "program_name_masked", "activity_content_masked", "std_id", "std_name", "std_confidence", "label_source", "llm_std",
                "llm_conf", "llm_why", "scope", "llm_scope", "purpose_primary", "llm_p1", "op_always", "op_regular", "op_event", "op_adhoc", "op_seasonal",
                "llm_op_ALW", "llm_op_REG", "llm_op_EVT", "llm_op_ADH", "llm_op_SEA", "target_explicit", "llm_tg"]
        d["merged"][[c for c in keep if c in d["merged"].columns]].to_csv(P(f"validation/rows_compare_{tag}.csv"), index=False, encoding="utf-8-sig")
    # ── 라벨러 원 응답·지침 보존 ──
    for sub in ("A", "ADJ", "ADJ2", "ADJ3", "B", "C"):
        src = os.path.join(ann_dir, sub)
        if os.path.isdir(src):
            dst = P(f"llm_annotations/{sub}")
            os.makedirs(dst, exist_ok=True)
            for f in glob.glob(os.path.join(src, "*.jsonl")) + glob.glob(os.path.join(src, "wave_keys_*.csv")):
                shutil.copy2(f, dst)
    if info.get("row_map") is not None:
        rm_out = info["row_map"].rename(columns={"old_row": "previous_source_row", "new_row": "source_row", "level": "match_level"}).copy()
        rm_out["previous_source_row"] = rm_out["previous_source_row"].astype("Int64")
        rm_out["source_row"] = rm_out["source_row"].astype("Int64")
        rm_out.to_csv(P("llm_annotations/previous_to_current_row_map.csv"), index=False, encoding="utf-8-sig")
    for gp in guideline_paths:
        if os.path.exists(gp):
            shutil.copy2(gp, P("llm_annotations/" + os.path.basename(gp)))
    # ── 특성 카탈로그 ──
    rows, cf, dic, cand = res["rows"], res["cf"], res["dic"], res["cand"]
    cat_row = CT.build_row_catalog(rows)
    cat_cx = CT.build_catalog(cf, "complex(단지)", CT.CX_RULES)
    cat_dic = CT.build_catalog(dic, "item(표준 프로그램)", CT.DICT_RULES)
    cat_cand = CT.build_catalog(cand, "pair(단지×표준 프로그램)", CT.CAND_RULES)
    catalog = pd.concat([cat_row, cat_cx, cat_dic, cat_cand], ignore_index=True)
    catalog.to_csv(P("feature_catalog.csv"), index=False, encoding="utf-8-sig")
    missing = catalog[catalog["definition"] == "(설명 미작성)"]
    logf("카탈로그:", len(catalog), "특성, 설명 미작성", len(missing), missing["feature"].tolist()[:20])
    res["catalog"] = catalog
    # ── 그림 ──
    figs = FG.make_all(res, P("figures"))
    figs_rel = {os.path.basename(f)[:5]: "figures/" + os.path.basename(f) for f in figs}
    # ── 심화 분석(제5장): 표·그림 ──
    extra = AX.run(res, ig, upd_tbl, seed=seed)
    os.makedirs(P("analysis"), exist_ok=True)
    for k, tb in extra["T"].items():
        tb.to_csv(P(f"analysis/{k}.csv"), index=False, encoding="utf-8-sig")
    xf = FGX.make_all(extra, P("figures"))
    figs_rel.update({k: "figures/" + os.path.basename(v) for k, v in xf.items()})
    res["extra"] = extra
    res["figs_rel"] = figs_rel
    res["budget_path"] = P("budget_assumptions.csv")
    # ── 보고서·README ──
    RB.build_report(res, P("분석보고서.md"), figs_rel=figs_rel, extra=extra)
    from . import docs as DC
    DC.write_excel(res, out_dir)
    DC.write_readme(res, out_dir, None)
    # ── 스키마·매니페스트·체크섬 ──
    frames = {"program_analysis.csv": rows, "complex_features.csv": cf, "standard_program_dictionary.csv": dic, "complex_program_candidates.csv": cand}
    cats = {"program_analysis.csv": cat_row, "complex_features.csv": cat_cx, "standard_program_dictionary.csv": cat_dic, "complex_program_candidates.csv": cat_cand}
    PK.write_schemas(out_dir, frames, cats)
    import platform, hashlib
    import sklearn
    code_hash = {}
    code_dir = os.path.dirname(os.path.abspath(__file__))
    for fn in sorted(os.listdir(code_dir)):
        if fn.endswith(".py"):
            code_hash[fn] = PK.sha256_file(os.path.join(code_dir, fn))
    vf = list(val_final.values())[0] if val_final else None
    vc = val_final.get("C(갱신분 신규 문구 표본, 최종 라벨)")
    manifest = dict(
        document_id="community_nlp_2026_v1",
        dataset_version="1.0.0",
        generated_at=pd.Timestamp.now().isoformat(timespec="seconds"),
        source_path=raw_path,
        source_name=meta["src"]["name"],
        source_sheet=meta["sheet"],
        source_bytes=meta["src"]["bytes"],
        source_snapshot="source_snapshot/" + meta["src"]["name"],
        source_sha256=meta["src"]["sha256"],
        previous_source=(None if "ref" not in meta else dict(name=meta["ref"]["name"], sha256=meta["ref"]["sha256"], rows=meta["update"]["n_old"])),
        source_update=meta.get("update"),
        source_rows=int(meta["scope"]["n_source_rows"]),
        analysis_rows=int(len(raw)),
        excluded_rows=int(meta["scope"]["n_excluded_rows"]),
        excluded_complexes=meta["scope"]["excluded_complexes"],
        source_complexes=int(meta["scope"]["n_source_complexes"]),
        analysis_complexes=int(rows["complex_name"].nunique()),
        complex_id_source=(None if "id_source" not in meta else dict(name=meta["id_source"]["name"], sha256=meta["id_source"]["sha256"], n_complexes=meta["n_integrated"],
                                                                     n_without_records=meta["n_integrated_without_records"])),
        observation_window=["2024-01-01", "2026-06-30"],
        counts=dict(program_rows=int(len(rows)), resident_scope_rows=int(rows["in_resident_scope"].sum()), complexes=int(len(cf)),
                    standard_types=int((dic[dic["std_id"] != "Z99"]["n_records"] > 0).sum()), alias_clusters=int(rows["alias_cluster_id"].nunique()),
                    candidate_pairs=int(len(cand)), features_row=int(rows.shape[1]), features_complex=int(cf.shape[1]), catalog_entries=int(len(catalog))),
        label_policy=dict(
            kind="silver_label_draft",
            rule="regex_lexicon_with_priority_and_confidence",
            llm="independent_blind_labelers_adjudicate_uncertain_and_medium_confidence_rows_only",
            label_source_counts={k: int(v) for k, v in rows["label_source"].value_counts().items()},
            std_confidence_counts={k: int(v) for k, v in rows["std_confidence"].value_counts().items()},
            not_ground_truth="Not an expert-validated label. Participation is recorded headcount (not unique residents). Budget is a model estimate. Supply gap is not a need label.",
            ops_states={"Y": "confirmed", "P": "probable", "N": "refuted", "U": "unknown"}),
        llm_annotation=dict(
            labels_used={"A": int(len(A)), **{k: int(v) for k, v in (ADJ["batch"].value_counts().items() if len(ADJ) else [])}, "B": int(len(B)), "C": int(len(C))},
            labels_in_previous_source=info.get("n_labels_old"), labels_carried_over=info.get("n_labels_transferred"),
            batch_completion=meta["batch_completion"],
            guideline_versions=["v1.0(A)", "v1.1(ADJ,B)", "v1.2(ADJ2,ADJ3,C)"],
            note="Labelers did not see rule outputs. Raw labeler outputs are preserved in llm_annotations/ (A·ADJ·ADJ2·B use the previous file's row numbers; "
                 "see previous_to_current_row_map.csv. ADJ3·C use the current file's row numbers)."),
        validation=dict(
            qa_pass=int((res["qa"]["status"] == "PASS").sum()), qa_fail=int((res["qa"]["status"] == "FAIL").sum()), qa_total=int(len(res["qa"])),
            independent_B=(None if vf is None else dict(n=int(vf["n"]), scope_acc=round(float(vf["scope_acc"]), 4), std_acc=round(float(vf["std_acc_valid"]), 4),
                                                       family_acc=round(float(vf["family_acc_valid"]), 4), purpose_primary_acc=round(float(vf["purpose_primary_acc"]), 4))),
            new_text_C=(None if vc is None else dict(n=int(vc["n"]), scope_acc=round(float(vc["scope_acc"]), 4), std_acc=round(float(vc["std_acc_valid"]), 4),
                                                    family_acc=round(float(vc["family_acc_valid"]), 4), purpose_primary_acc=round(float(vc["purpose_primary_acc"]), 4)))),
        versions=dict(taxonomy="taxonomy_v1.0", std_programs="std_programs_v1.0", budget="budget_assumptions_v1.0", python=platform.python_version(),
                      pandas=pd.__version__, numpy=np.__version__, sklearn=sklearn.__version__),
        code_sha256=code_hash,
        design_basis=["온터_데이터반영_연구방법론_v4_20261117", "온터_NLP_특성설계_연구방법론_v5_20261117"],
    )
    PK.write_manifest(out_dir, manifest)
    PK.write_checksums(out_dir)
    res["elapsed_total"] = time.time() - t0
    return res


def main(argv=None):
    """명령행 실행: python -m community_nlp.build_final --raw 원본.xlsx --ann 판정폴더 --out 출력폴더 [--label-ref 이전원본.xlsx] [--integrated 단지통합.xlsx] [--guideline 파일 ...]"""
    import argparse
    ap = argparse.ArgumentParser(description="커뮤니티 활동 NLP 구조화 산출물 생성")
    ap.add_argument("--raw", required=True, help="분석할 원본 엑셀")
    ap.add_argument("--ann", required=True, help="LLM 라벨러 판정 폴더(A·ADJ·ADJ2·ADJ3·B·C 하위 폴더; 산출물의 llm_annotations/ 가능)")
    ap.add_argument("--out", required=True, help="출력 폴더(없으면 만든다)")
    ap.add_argument("--label-ref", default=None, help="A·ADJ·ADJ2·B 라벨이 붙은 이전 원본 엑셀(생략하면 --ann 안의 previous_to_current_row_map.csv를 쓴다)")
    ap.add_argument("--integrated", default=None, help="단지통합 엑셀(complex_id 기준). 주면 ID를 붙이고 통합표에 없는 단지는 제외한다")
    ap.add_argument("--guideline", nargs="*", default=[], help="출력 폴더로 복사할 라벨러 지침서")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    res = finalize(a.raw, a.ann, a.out, guideline_paths=a.guideline, seed=a.seed, label_ref_path=a.label_ref, integrated_path=a.integrated)
    print("완료:", a.out, "QA", res["qa"]["status"].value_counts().to_dict())


if __name__ == "__main__":
    main()
