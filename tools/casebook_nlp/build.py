# -*- coding: utf-8 -*-
"""주거복지사 활동 사례집 구조화 빌드.

사용: python -m casebook_nlp.build --raw <사례집 OCR 통합본 txt> --ann <추출 JSON 폴더> --out <출력 폴더>
- 사례 분할(segment) → LLM 추출 결과(ann/CBxx.json) 읽기 → 근거 원문 대조 → 코드 연결(std_id·complex_id·대상·기관 유형·필요 영역)
  → 이름 가리기 → 표·근거 카드·장애물 플레이북·검색 청크·엑셀·문서
- 추출 JSON은 원자료처럼 다룬다(사람 검토 결과를 반영해 고칠 수 있음). 같은 입력이면 같은 결과.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from community_nlp import attrs, taxonomy as TX                     # noqa: E402
from community_nlp.package import write_checksums, write_manifest   # noqa: E402
from community_nlp.text_utils import compact                        # noqa: E402
from news_nlp import programs as PG, index as IX, signals as SG     # noqa: E402
from casebook_nlp import segment as SEG, intro as INTRO, docs as DOCS   # noqa: E402

DATA = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")).replace("\\", "/") + "/"
COMM = DATA + "processed/community_nlp_2026_v1/"
MASTER = DATA + "processed/complex_integrated_20261117_v1/data/complex_master.csv"
VERSION = "casebook_programs_v1"
SOURCE = "주거복지사 활동 사례집 「어느 날 삶에 온기가 돌기 시작했다」(주택관리공단, 2025.7.11.)"
rd = lambda p, **k: pd.read_csv(p, encoding="utf-8-sig", low_memory=False, **k)
ELEM_TYPES = ["need", "target", "partner", "resource", "operation", "outcome", "lesson"]
ELEM_KO = {"need": "필요", "target": "대상", "partner": "협력", "resource": "자원", "operation": "운영", "outcome": "성과", "lesson": "교훈"}
OBS_CATS = ["공간·시설", "예산·재원", "인력", "기관 협조", "제도·규정", "주민 참여·신뢰", "정보·인식 부족", "대상자 특성", "운영 부담", "기타"]
SOL_STRATS = ["설득·협상", "대체 자원 연계", "주민 참여 유도", "외부 공모·후원", "제도·규정 활용", "단계적 확대·시범 운영", "방식 변경", "관계 형성·신뢰 쌓기", "기타"]
ROLE_NAME = re.compile(r"([가-힣]{2,4})\s?\((주거복지사|입주민|자활근로자|생활지원사|봉사자|자원봉사자|활동가|강사|센터장|관장|팀장|단장|회장|사회복지사|간호사|[가-힣]{2,10}(?:담당|직원|대표|매니저|코디네이터))\)")
NAME_ROLE_INLINE = re.compile(r"([가-힣]{3})\s(주거복지사|자활근로자|입주민|생활지원사|단장|팀장|센터장|관장)(?=[가-힣\s,.]|$)")


def J(xs):
    xs = list(xs) if xs is not None else []
    return "|".join(str(x) for x in xs if x is not None and str(x) not in ("", "nan"))


def norm_ws(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def mask_names(t, names):
    t = ROLE_NAME.sub(lambda m: f"[{m.group(2)}]({m.group(2)})" if m.group(2) else m.group(0), t)
    for n in sorted(names, key=len, reverse=True):
        if len(n) >= 2:
            t = re.sub(rf"(?<![가-힣]){re.escape(n)}(?=\s?(님|씨|단장|주거복지사|입주민|어르신|할머니|할아버지|이|가|은|는|을|를|의|에게|과|와|도|\(|\s|,|\.|$))", "[이름]", t)
    t = t.replace("[주거복지사](주거복지사)", "[이름](주거복지사)")
    t = re.sub(r"\[(?!이름|전화|이메일)[^\]]{2,10}\]\(([^)]+)\)", r"[이름](\1)", t)
    return SG.mask_text(t)


SURNAMES = set("김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남심노하곽성차주우구민진나지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용예봉경")
SPEAKER_LINE = re.compile(r"^\s*([가-힣]{2,4})\s?\(([^)]{1,15})\)", re.M)          # 대담 줄머리: 윤장기(주거복지사) / 신미영(일산흰돌4)
NOT_PERSON = {"장애인", "중장년", "주택공사", "공동화", "선별도구", "불안척도", "건강안뷰", "세탁세제", "주방세제", "냉동만두", "라면", "품목", "시행", "각장애인", "거복지사",
              "강안뷰", "기부터", "문하여", "박세대", "어느새", "지장애", "하려면"}   # 단어 일부가 잘려 잡힌 것(2026-11-17 확인)


def person_names(text):
    """사람 이름 후보: ① 대담 줄머리의 '이름(역할·단지)' ② '이름(주거복지사 등 역할)' ③ 성씨로 시작하는 3글자+직함. 일반어는 제외."""
    ns = {m.group(1) for m in SPEAKER_LINE.finditer(text)} | {m.group(1) for m in ROLE_NAME.finditer(text)}
    ns |= {m.group(1) for m in NAME_ROLE_INLINE.finditer(text) if m.group(1)[0] in SURNAMES}
    bad_end = ("을", "를", "의", "된", "던", "는", "은", "가", "이", "게", "나", "도", "만", "지", "과", "와", "에", "로", "며", "자", "고", "한", "본", "서", "야", "소", "역")
    return {n for n in ns if n not in NOT_PERSON and n[0] in SURNAMES and 2 <= len(n) <= 4 and not n.endswith(bad_end) and "권역" not in n}


def verify(ev, src_flat):
    if not ev:
        return 0
    return int(norm_ws(ev) in src_flat)


def build(raw_path, ann_dir, out):
    for d in ("", "links", "features", "index", "qa"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    text = open(raw_path, encoding="utf-8").read()
    cases, intro_text = SEG.segment(text)
    master = rd(MASTER)
    sd = rd(COMM + "standard_program_dictionary.csv")
    alias = rd(COMM + "alias_dictionary.csv")
    aidx = PG.AliasIndex(alias, sd)
    valid = set(sd.loc[sd["scope"].isin(["PROGRAM", "HOUSEHOLD_SUPPORT"]), "std_id"])
    name_std = dict(zip(sd["std_id"], sd["std_name"]))
    fam_std = dict(zip(sd["std_id"], sd["std_family_label"]))
    need_std = dict(zip(sd["std_id"], sd["need_domains_def"]))
    pur_std = dict(zip(sd["std_id"], sd["purpose_primary"]))
    id_of = dict(zip(master["단지명"], master["complex_id"]))
    br_of = dict(zip(master["complex_id"], master["지사명"]))
    dep = INTRO.deployment(intro_text, master)
    facts = INTRO.facts(intro_text)

    dec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review_decisions.csv")
    dec = rd(dec_path, dtype=str).fillna("") if os.path.exists(dec_path) else pd.DataFrame(columns=["kind", "key", "value", "decision"])
    std_override = {r["key"]: r["value"] for _, r in dec[(dec["kind"] == "program_std") & (dec["decision"] == "override")].iterrows()}
    dep_confirm = {r["key"]: r["value"] for _, r in dec[(dec["kind"] == "deployment_complex") & (dec["decision"] == "confirm")].iterrows()}
    case_confirm = {(r["key"], r["value"]) for _, r in dec[(dec["kind"] == "case_complex") & (dec["decision"] == "confirm")].iterrows()}
    name_of = dict(zip(master["complex_id"], master["단지명"]))
    for i, r in dep.iterrows():                     # 배치 단지 이름 후보 → 사용자 확정
        if r["name_in_book"] in dep_confirm and r["needs_review"] == 1:
            cid_ = dep_confirm[r["name_in_book"]]
            dep.loc[i, ["complex_id", "complex_name", "match_type", "needs_review", "branch"]] = [cid_, name_of[cid_], r["match_type"] + "+user_confirmed", 0, br_of.get(cid_)]
    C, P, E, O, CX, ev_check = [], [], [], [], [], []
    all_names = set()
    for c in cases:
        all_names |= person_names(c["text"])
    for c in cases:
        cid = c["case_id"]
        a = json.load(open(os.path.join(ann_dir, f"{cid}.json"), encoding="utf-8"))
        src = norm_ws(c["text"])
        # 단지 연결
        cx_rows = []
        for nm in a.get("complexes_mentioned") or []:
            nm2 = re.sub(r"\s+", "", nm)
            if nm2 in id_of:
                cx_rows.append(dict(case_id=cid, complex_id=id_of[nm2], complex_name=nm2, mention=nm, match_type="exact", needs_review=0))
            else:
                base = re.sub(r"단지$", "", nm2)
                hit = [n for n in id_of if n == base]
                if hit:
                    cx_rows.append(dict(case_id=cid, complex_id=id_of[hit[0]], complex_name=hit[0], mention=nm, match_type="exact_after_suffix", needs_review=0))
                else:
                    dmatch = dep[dep["name_in_book"] == nm2]
                    if len(dmatch) and dmatch["complex_id"].notna().iloc[0]:
                        r = dmatch.iloc[0]
                        cx_rows.append(dict(case_id=cid, complex_id=r["complex_id"], complex_name=r["complex_name"], mention=nm, match_type=r["match_type"], needs_review=int(r["needs_review"])))
                    else:
                        # '청주산남2'처럼 통합표에 '청주산남2-1'·'청주산남2-2'로 나뉜 경우: 모두 후보(어느 쪽인지 정할 수 없음)
                        subs = [n for n in id_of if n.startswith(base + "-")]
                        for n in subs:
                            cx_rows.append(dict(case_id=cid, complex_id=id_of[n], complex_name=n, mention=nm, match_type="split_complex_candidate", needs_review=1))
                        if not subs:
                            cx_rows.append(dict(case_id=cid, complex_id=None, complex_name=None, mention=nm, match_type="not_in_integrated_table", needs_review=0))
        for r in cx_rows:                           # 사례 단지 후보 → 사용자 확정
            if r["needs_review"] and (f"{cid}|{r['mention']}", r["complex_id"]) in case_confirm:
                r.update(match_type=r["match_type"] + "+user_confirmed", needs_review=0)
        CX += cx_rows
        ok_cx = [r["complex_id"] for r in cx_rows if r["complex_id"] and not r["needs_review"]]
        # 프로그램
        for k, p in enumerate(a.get("programs") or []):
            pid = f"{cid}_P{k + 1}"
            ptext = " ".join(str(p.get(x) or "") for x in ("summary", "operation", "target"))
            r = PG._rule(p.get("name", ""), ptext)
            knn = aidx.query(PG.strip_orgs(p.get("name", "") + " " + str(p.get("summary") or "")), 3)
            rule_ok = r["std_id"] in valid and not r["fallback"]
            cands = []
            if rule_ok:
                cands.append((r["std_id"], "rule", r["score"]))
            for sid, sim, at in knn:
                if sid in valid and sim >= 0.3:
                    cands.append((sid, "alias_knn", sim))
            if cands:
                votes = pd.DataFrame(cands, columns=["std_id", "method", "score"])
                agg = votes.groupby("std_id").agg(n=("method", "nunique"), methods=("method", lambda s: J(sorted(set(s)))), best=("score", "max")).reset_index()
                top = agg.sort_values(["n", "best"], ascending=False).iloc[0]
                conf = "high" if top["n"] >= 2 else ("medium" if ("rule" in top["methods"] or top["best"] >= 0.5) else "low")
                std, methods = top["std_id"], top["methods"]
                alts = J([f"{s}:{name_std.get(s, '')}" for s in agg.sort_values(["n", "best"], ascending=False)["std_id"][1:3]])
            else:
                std, conf, methods, alts = None, "none", "", ""
            if pid in std_override:                       # review_decisions.csv의 교정(근거는 그 파일의 note)
                alts = J([f"{std}:{name_std.get(std, '')}(자동 판정)"] + ([alts] if alts else [])) if std else alts
                std, conf, methods = std_override[pid], "reviewed", "reviewed_override"
            tg = attrs.extract_targets(compact(p.get("name", "")), compact(str(p.get("target") or "")), "")
            P.append(dict(case_id=cid, program_id=pid, program_name=p.get("name"), program_summary=p.get("summary"), operation=p.get("operation"), target=p.get("target"),
                          start=p.get("start"), std_id=std, std_name=name_std.get(std), std_family=fam_std.get(std), std_confidence=conf, std_methods=methods, std_alternatives=alts,
                          target_codes=J(tg["explicit"]), target_labels=J(SG.labels(TX.TARGETS, tg["explicit"])),
                          need_domain_codes=str(need_std.get(std) or "") if std else "", evidence_found=verify(p.get("evidence"), src), evidence=p.get("evidence")))
            ev_check.append(dict(case_id=cid, field=f"program:{pid}", found=verify(p.get("evidence"), src), evidence=p.get("evidence")))
        # 요소
        for k, e in enumerate(a.get("elements") or []):
            et = e.get("type")
            row = dict(case_id=cid, element_id=f"{cid}_E{k + 1:02d}", type=et, type_ko=ELEM_KO.get(et, et), text=e.get("text"), value=e.get("value"), unit=e.get("unit"),
                       partner_name=e.get("partner_name"), partner_role=e.get("role"), speaker_role=e.get("speaker_role"), evidence=e.get("evidence"),
                       evidence_found=verify(e.get("evidence"), src))
            if et == "partner":
                orgs = attrs.extract_orgs(compact(str(e.get("partner_name") or "")), compact(str(e.get("role") or "") + str(e.get("text") or "")))
                row["partner_org_codes"] = J(sorted(orgs))
                row["partner_org_labels"] = J(SG.labels(TX.ORGS, sorted(orgs)))
            if et == "target":
                tg = attrs.extract_targets("", compact(str(e.get("text") or "") + str(e.get("evidence") or "")), "")
                row["target_codes"] = J(tg["explicit"])
            E.append(row)
            ev_check.append(dict(case_id=cid, field=f"element:{row['element_id']}", found=row["evidence_found"], evidence=e.get("evidence")))
        # 장애물
        for k, o in enumerate(a.get("obstacles") or []):
            row = dict(case_id=cid, obstacle_id=f"{cid}_O{k + 1}", obstacle=o.get("obstacle"), obstacle_category=o.get("obstacle_category"),
                       solution=o.get("solution"), solution_strategy=o.get("solution_strategy"), status=o.get("status"),
                       obstacle_evidence=o.get("obstacle_evidence"), solution_evidence=o.get("solution_evidence"),
                       obstacle_evidence_found=verify(o.get("obstacle_evidence"), src),
                       solution_evidence_found=verify(o.get("solution_evidence"), src) if o.get("solution_evidence") else None)
            O.append(row)
            ev_check.append(dict(case_id=cid, field=f"obstacle:{row['obstacle_id']}", found=row["obstacle_evidence_found"], evidence=o.get("obstacle_evidence")))
            if o.get("solution_evidence"):
                ev_check.append(dict(case_id=cid, field=f"solution:{row['obstacle_id']}", found=row["solution_evidence_found"], evidence=o.get("solution_evidence")))
        C.append(dict(case_id=cid, part=c["part"], domain=c["domain"], region=c["region"], program_title=c["program_title"], summary=a.get("summary"),
                      complex_ids=J(ok_cx), complexes_mentioned=J(a.get("complexes_mentioned") or []), branches=J(sorted({br_of[x] for x in ok_cx if x in br_of})),
                      n_programs=len(a.get("programs") or []), n_elements=len(a.get("elements") or []), n_obstacles=len(a.get("obstacles") or []),
                      n_chars=len(c["text"]), source_lines=f"{c['line_from']}-{c['line_to']}", text_masked=mask_names(c["text"], all_names)))

    Cdf, Pdf, Edf, Odf, CXdf, EV = map(pd.DataFrame, (C, P, E, O, CX, ev_check))
    # 이름 가리기(근거 문장)
    for df, cols in ((Pdf, ["evidence"]), (Edf, ["evidence"]), (Odf, ["obstacle_evidence", "solution_evidence"])):
        for col in cols:
            df[col + "_masked"] = df[col].map(lambda s: mask_names(s, all_names) if isinstance(s, str) else s)
    # 단지·지사를 프로그램 행에도
    Pdf = Pdf.merge(Cdf[["case_id", "domain", "region", "complex_ids", "branches"]], on="case_id", how="left")

    # 근거 카드: 사례×프로그램 1장 — 추천 후보 설명에 붙이는 단위
    def pick(cid, t, n=3):
        s = Edf[(Edf["case_id"] == cid) & (Edf["type"] == t)]
        return s["text"].dropna().head(n).tolist()
    cards = []
    for _, p in Pdf.iterrows():
        cid = p["case_id"]
        partners = Edf[(Edf["case_id"] == cid) & (Edf["type"] == "partner")]
        outs = Edf[(Edf["case_id"] == cid) & (Edf["type"] == "outcome")]
        obs = Odf[Odf["case_id"] == cid]
        card = dict(card_id=p["program_id"], case_id=cid, std_id=p["std_id"], std_name=p["std_name"], std_confidence=p["std_confidence"], program_name=p["program_name"],
                    domain=p["domain"], region=p["region"], complex_ids=p["complex_ids"], branches=p["branches"],
                    headline=f"{p['region']} '{p['program_name']}': {p['program_summary'] or ''}".strip(),
                    need=" / ".join(pick(cid, "need")), target=p["target"] or " / ".join(pick(cid, "target", 2)),
                    partners=" / ".join(f"{r['partner_name'] or ''}({r['partner_role'] or r['text']})" for _, r in partners.head(6).iterrows()),
                    partner_org_labels=J(sorted({x for v in partners.get("partner_org_labels", pd.Series(dtype=str)).fillna("") for x in str(v).split("|") if x})),
                    operation=p["operation"] or " / ".join(pick(cid, "operation", 2)), how_it_runs=" / ".join(pick(cid, "operation", 4)),
                    outcomes=" / ".join(f"{r['text']}" for _, r in outs.head(5).iterrows()),
                    outcome_numbers=J([f"{r['value']:g}{r['unit'] or ''}" for _, r in outs.iterrows() if pd.notna(r["value"]) and isinstance(r["value"], (int, float))]),
                    obstacles_and_solutions=" / ".join(f"[{r['obstacle_category']}] {r['obstacle']} → {r['solution'] if isinstance(r['solution'], str) else '해결 방법 미기재'}" for _, r in obs.iterrows()),
                    lessons=" / ".join(pick(cid, "lesson", 3)), source=SOURCE)
        card["card_text"] = (f"{card['headline']}\n필요: {card['need']}\n대상: {card['target']}\n협력: {card['partners']}\n운영: {card['operation']}\n"
                             f"성과: {card['outcomes']}\n시작할 때 부딪힌 문제와 해결: {card['obstacles_and_solutions'] or '기재 없음'}\n출처: {SOURCE} — 사례 {cid}")
        cards.append(card)
    CARD = pd.DataFrame(cards)
    # 표준 프로그램 → 근거 카드 색인(추천 후보와 std_id로 조인)
    sidx = CARD[CARD["std_id"].notna() & CARD["std_confidence"].isin(["high", "medium", "reviewed"])].groupby(["std_id", "std_name"]).agg(
        n_cards=("card_id", "size"), card_ids=("card_id", J), regions=("region", J), domains=("domain", lambda s: J(sorted(set(s))))).reset_index()
    # 장애물 플레이북: 범주 × 전략 집계
    pb = Odf.groupby(["obstacle_category", "solution_strategy"], dropna=False).agg(n=("obstacle_id", "size"), cases=("case_id", lambda s: J(sorted(set(s)))),
                                                                                    examples=("obstacle", lambda s: " / ".join(s.head(3)))).reset_index().sort_values("n", ascending=False)
    # 검색 청크(가린 본문)
    ch_rows = []
    for _, c in Cdf.iterrows():
        sents = IX.split_sentences(c["text_masked"])
        for ci, idxs in enumerate(IX.make_chunks(sents)):
            ch_rows.append(dict(chunk_id=f"{c['case_id']}_c{ci:02d}", case_id=c["case_id"], chunk_idx=ci, text=(f"[{c['domain']}] {c['region']} | {c['program_title']}\n" if ci == 0 else "") + " ".join(sents[i] for i in idxs)))
    CH = pd.DataFrame(ch_rows)
    prog = sd[sd["scope"].isin(["PROGRAM", "HOUSEHOLD_SUPPORT"])].copy()
    ptxt = (prog["std_name"] + " " + prog["definition_ko"].fillna("") + " " + prog["alias_examples"].fillna("").str.replace(r"\(\d+\)", "", regex=True)).tolist()
    V = IX.build_vectors(CH["text"].tolist(), ptxt)
    np.save(os.path.join(out, "index", "chunk_lsa64.npy"), V["Zc"].astype("float32"))
    np.save(os.path.join(out, "index", "program_lsa64.npy"), V["Zp"].astype("float32"))
    pd.DataFrame({"row": range(len(CH)), "chunk_id": CH["chunk_id"]}).to_csv(os.path.join(out, "index", "chunk_lsa64_rows.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame({"row": range(len(prog)), "std_id": prog["std_id"].values}).to_csv(os.path.join(out, "index", "program_lsa64_rows.csv"), index=False, encoding="utf-8-sig")
    meta = Cdf.set_index("case_id")
    cstd = Pdf.groupby("case_id")["std_id"].apply(lambda s: [x for x in s if isinstance(x, str)])
    with open(os.path.join(out, "chunks.jsonl"), "w", encoding="utf-8") as fh:
        for i, c in CH.iterrows():
            m = meta.loc[c["case_id"]]
            sims = V["sim"][i]
            fh.write(json.dumps(dict(chunk_id=c["chunk_id"], case_id=c["case_id"], source_type="casebook", text=c["text"], domain=m["domain"], region=m["region"],
                                     complex_ids=[x for x in str(m["complex_ids"]).split("|") if x], std_ids=cstd.get(c["case_id"], []),
                                     similar_programs=[[prog["std_id"].iat[j], round(float(sims[j]), 4)] for j in np.argsort(-sims)[:3]]), ensure_ascii=False) + "\n")
    with open(os.path.join(out, "evidence_cards.jsonl"), "w", encoding="utf-8") as fh:
        for _, r in CARD.iterrows():
            fh.write(json.dumps({k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in r.items()}, ensure_ascii=False) + "\n")

    # 저장
    Cdf.to_csv(os.path.join(out, "cases.csv"), index=False, encoding="utf-8-sig")
    Pdf.drop(columns=["evidence"]).to_csv(os.path.join(out, "case_programs.csv"), index=False, encoding="utf-8-sig")
    Edf.drop(columns=["evidence"]).to_csv(os.path.join(out, "case_elements.csv"), index=False, encoding="utf-8-sig")
    Odf.drop(columns=["obstacle_evidence", "solution_evidence"]).to_csv(os.path.join(out, "case_obstacles.csv"), index=False, encoding="utf-8-sig")
    CARD.to_csv(os.path.join(out, "evidence_cards.csv"), index=False, encoding="utf-8-sig")
    CXdf.to_csv(os.path.join(out, "links", "case_complex.csv"), index=False, encoding="utf-8-sig")
    sidx.to_csv(os.path.join(out, "links", "std_id_to_cards.csv"), index=False, encoding="utf-8-sig")
    pb.to_csv(os.path.join(out, "features", "obstacle_playbook.csv"), index=False, encoding="utf-8-sig")
    # 추천 후보와 바로 잇기: 아직 운영하지 않은 후보(community_nlp) 중 사례집 근거 카드가 있는 것
    cand = rd(COMM + "complex_program_candidates.csv", usecols=["complex_id", "complex_name", "std_id", "std_name", "complex_adopted", "peer_group_adoption_rate", "cf_neighbor_adoption_rate", "fills_gap_domain"])
    cj = cand[(cand["complex_adopted"] == 0) & cand["std_id"].isin(set(sidx["std_id"]))].merge(sidx[["std_id", "n_cards", "card_ids", "regions"]], on="std_id")
    cj = cj.sort_values(["complex_id", "peer_group_adoption_rate"], ascending=[True, False])
    cj.to_csv(os.path.join(out, "features", "complex_candidates_with_casebook_cards.csv"), index=False, encoding="utf-8-sig")
    dep.to_csv(os.path.join(out, "features", "welfare_worker_deployment_2025.csv"), index=False, encoding="utf-8-sig")
    facts.to_csv(os.path.join(out, "features", "casebook_facts.csv"), index=False, encoding="utf-8-sig")
    EV.to_csv(os.path.join(out, "qa", "evidence_verification.csv"), index=False, encoding="utf-8-sig")
    rq = [dict(kind="complex_link_candidate", key=r["name_in_book"], detail=f"{r['complex_name']} sim={r['candidate_similarity']}") for _, r in dep[dep["needs_review"] == 1].iterrows()]
    rq += [dict(kind="case_complex_candidate", key=f"{r['case_id']} {r['mention']}", detail=f"{r['complex_id']} {r['complex_name']} ({r['match_type']})") for _, r in CXdf[CXdf["needs_review"] == 1].iterrows()]
    rq += [dict(kind="program_std_low_or_none", key=r["program_id"], detail=f"{r['program_name']} → {r['std_name']} ({r['std_confidence']})") for _, r in Pdf[Pdf["std_confidence"].isin(["low", "none"])].iterrows()]
    rq += [dict(kind="evidence_not_found", key=r["field"], detail=str(r["evidence"])[:120]) for _, r in EV[EV["found"] == 0].iterrows()]
    pd.DataFrame(rq, columns=["kind", "key", "detail"]).to_csv(os.path.join(out, "qa", "review_queue.csv"), index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(os.path.join(out, "casebook_programs_v1.xlsx")) as xw:
        for nm, df in [("근거카드", CARD.drop(columns=["card_text"])), ("사례", Cdf.drop(columns=["text_masked"])), ("프로그램", Pdf.drop(columns=["evidence"])),
                       ("요소", Edf.drop(columns=["evidence"])), ("장애물과해결", Odf.drop(columns=["obstacle_evidence", "solution_evidence"])), ("장애물플레이북", pb),
                       ("배치단지2025", dep), ("개요수치", facts)]:
            df.to_excel(xw, sheet_name=nm, index=False)

    # 점검
    chk = []
    def add(cid, d, res, ok):
        chk.append(dict(check_id=cid, description=d, result=res, status="PASS" if ok else "FAIL"))
    add("K01", "사례 18개 분할", len(Cdf), len(Cdf) == 18)
    add("K02", "사례마다 추출 결과(프로그램 1개 이상)", int((Cdf["n_programs"] >= 1).sum()), (Cdf["n_programs"] >= 1).all())
    add("K03", "근거 인용이 원문과 일치(전체)", f"{int(EV['found'].sum())}/{len(EV)}", EV["found"].mean() >= 0.98)
    add("K04", "요소 유형이 정해진 7종", f"{Edf['type'].isin(ELEM_TYPES).sum()}/{len(Edf)}", Edf["type"].isin(ELEM_TYPES).all())
    add("K05", "장애물 범주·전략이 정해진 값", f"{Odf['obstacle_category'].isin(OBS_CATS).sum()}/{len(Odf)} · {Odf['solution_strategy'].isin(SOL_STRATS + [None]).sum()}/{len(Odf)}",
        Odf["obstacle_category"].isin(OBS_CATS).all() and Odf["solution_strategy"].isin(SOL_STRATS + [None]).all())
    add("K06", "std_id가 표준 사전에 존재", f"{Pdf['std_id'].dropna().isin(set(sd['std_id'])).sum()}/{Pdf['std_id'].notna().sum()}", Pdf["std_id"].dropna().isin(set(sd["std_id"])).all())
    add("K07", "complex_id가 통합표에 존재", f"{CXdf['complex_id'].dropna().isin(set(master['complex_id'])).sum()}/{CXdf['complex_id'].notna().sum()}",
        CXdf["complex_id"].dropna().isin(set(master["complex_id"])).all())
    leak = sum(1 for n in all_names for v in Cdf["text_masked"] if re.search(rf"(?<![가-힣]){re.escape(n)}(?![가-힣])", v))
    add("K08", "가린 본문에 등장인물 이름 잔존(이름+괄호 역할 기준)", leak, leak == 0)
    add("K09", "요약·장애물 문장에 이름 없음", int(sum(1 for n in all_names for v in pd.concat([Cdf["summary"], Odf["obstacle"], Odf["solution"].fillna(""), Edf["text"].fillna("")]) if n in str(v))),
        not any(n in str(v) for n in all_names for v in pd.concat([Cdf["summary"], Odf["obstacle"], Odf["solution"].fillna(""), Edf["text"].fillna("")])))
    add("K10", "개요 수치 근거가 원문에 있음", f"{facts['evidence_found'].sum()}/{len(facts)}", facts["evidence_found"].all())
    add("K11", "참고: 프로그램 std_id 중간 이상·검토 교정 비율", f"{Pdf['std_confidence'].isin(['high', 'medium', 'reviewed']).mean():.0%}", True)
    add("K12", "참고: 배치 단지 통합표 정확 일치", f"{(dep['match_type'] == 'exact').sum()}/{len(dep)}", True)
    CK = pd.DataFrame(chk)
    CK.to_csv(os.path.join(out, "qa", "quality_checks.csv"), index=False, encoding="utf-8-sig")
    summary = dict(version=VERSION, built_at=datetime.now().isoformat(timespec="seconds"), source=SOURCE, raw_path=raw_path, ann_dir=ann_dir,
                   n_cases=len(Cdf), n_programs=len(Pdf), n_elements=len(Edf), element_types=Edf["type"].value_counts().to_dict(), n_obstacles=len(Odf),
                   obstacle_categories=Odf["obstacle_category"].value_counts().to_dict(), solution_strategies=Odf["solution_strategy"].value_counts(dropna=False).to_dict(),
                   n_cards=len(CARD), std_confidence=Pdf["std_confidence"].value_counts().to_dict(), n_std_with_cards=int(len(sidx)),
                   n_deployment=len(dep), deployment_match=dep["match_type"].value_counts().to_dict(), n_chunks=len(CH), evidence_found=f"{int(EV['found'].sum())}/{len(EV)}",
                   checks_pass=int((CK["status"] == "PASS").sum()), checks_total=len(CK))
    write_manifest(out, summary)
    DOCS.write_docs(out, summary, pb, Pdf, Odf)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(CK.to_string())
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--ann", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    build(a.raw, a.ann, a.out)
    write_checksums(a.out)


if __name__ == "__main__":
    main()
