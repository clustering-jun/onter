# -*- coding: utf-8 -*-
"""주거복지 뉴스·보도자료 구조화 빌드.

사용: python -m news_nlp.build --raw <크롤링 articles.jsonl> --out <출력 폴더>
같은 입력이면 같은 결과(정렬·난수 고정). 결과 폴더 구조는 README.md에 적는다.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from community_nlp import taxonomy as TX                       # noqa: E402
from community_nlp.package import write_checksums, write_manifest   # noqa: E402
from news_nlp import clean as C, link as LK, programs as PG, signals as SG, index as IX, docs as DC   # noqa: E402

DATA = r"C:/Users/user/Desktop/2026 DRIVE/project/data/"
COMM = DATA + "processed/community_nlp_2026_v1/"
MASTER = DATA + "processed/complex_integrated_20261117_v1/data/complex_master.csv"
VERSION = "housing_welfare_news_v1"
rd = lambda p, **k: pd.read_csv(p, encoding="utf-8-sig", low_memory=False, **k)
def J(xs):
    xs = list(xs) if xs is not None else []
    return "|".join(str(x) for x in xs if x is not None and str(x) not in ("", "nan"))


def news_id(d):
    h = hashlib.sha1((d.get("final_url") or d["url"]).encode("utf-8")).hexdigest()[:6]
    return f"N{str(d.get('date') or '00000000').replace('-', '')}_{h}"


def outlet(url):
    h = re.sub(r"^https?://([^/]+).*$", r"\1", url or "")
    return re.sub(r"^(www|m|mobile|biz|news|v)\.", "", h)


def reuse_policy(s):
    s = str(s or "")
    if "공공누리 제1유형" in s:
        return "kogl_type1_attribution"
    if "공공누리 제2유형" in s:
        return "kogl_type2_noncommercial"
    return "internal_analysis_only"


def clean_title(t):
    return re.sub(r"^\s*\[(포토뉴스|동네뉴스|단신|충북|[가-힣]{1,4})\]\s*", "", C.norm(t))


def sentence_role(s, k):
    if k == 0:
        return "lead"
    if re.search(r"[“\"].{4,}[”\"]\s*(라|이)?(고|며|면서)?\s*(말했|밝혔|전했|강조했|덧붙였|다짐했|했다)", s) or re.search(r"(말했다|밝혔다|전했다|덧붙였다|강조했다)\.?$", s):
        return "quote"
    if re.match(r"^[-▲▶■•·]", s):
        return "bullet"
    return "body"


def dedup(arts):
    texts = [a["title"] + " " + a["body_clean"] for a in arts]
    vec = TfidfVectorizer(analyzer="char", ngram_range=(3, 3), sublinear_tf=True)
    X = normalize(vec.fit_transform([re.sub(r"\s+", "", t) for t in texts]))
    S = (X @ X.T).toarray()
    n = len(arts)
    parent = list(range(n))

    def f(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            same_day = arts[i]["date"] == arts[j]["date"]
            t_ov = C.overlap(arts[i]["title"], arts[j]["title"])
            if S[i, j] >= 0.45 or (same_day and (S[i, j] >= 0.3 or t_ov >= 0.5)):
                parent[f(i)] = f(j)
                pairs.append((arts[i]["news_id"], arts[j]["news_id"], round(float(S[i, j]), 3), round(t_ov, 3), int(same_day)))
    groups = defaultdict(list)
    for i in range(n):
        groups[f(i)].append(i)
    for g in groups.values():
        rep = max(g, key=lambda i: (not arts[i]["is_snippet"], len(arts[i]["body_clean"])))
        cid = "D" + arts[rep]["news_id"][1:]
        for i in g:
            arts[i]["dup_cluster"] = cid
            arts[i]["dup_size"] = len(g)
            arts[i]["is_representative"] = int(i == rep)
    return pd.DataFrame(pairs, columns=["news_id_a", "news_id_b", "cosine_char3", "title_overlap", "same_date"])


def build(raw_path, out):
    os.makedirs(out, exist_ok=True)
    for d in ("links", "signals", "features", "index", "qa"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    raw = [json.loads(l) for l in open(raw_path, encoding="utf-8") if l.strip()]
    master = rd(MASTER)
    sd = rd(COMM + "standard_program_dictionary.csv")
    alias = rd(COMM + "alias_dictionary.csv")
    valid = set(sd.loc[sd["scope"].isin(["PROGRAM", "HOUSEHOLD_SUPPORT"]), "std_id"])
    name_std = dict(zip(sd["std_id"], sd["std_name"]))
    fam_std = dict(zip(sd["std_id"], sd["std_family_label"]))
    pur_std = dict(zip(sd["std_id"], sd["purpose_primary"]))
    need_std = dict(zip(sd["std_id"], sd["need_domains_def"]))
    cm = LK.ComplexMatcher(master)
    aidx = PG.AliasIndex(alias, sd)
    # 사용자 검토 결정(review_decisions.csv): 단지 연결 확정, 별칭 추가, '프로그램 아님' 문구
    dec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review_decisions.csv")
    dec = rd(dec_path, dtype=str).fillna("") if os.path.exists(dec_path) else pd.DataFrame(columns=["kind", "news_id", "key", "value", "decision"])
    cx_confirm = {(r["news_id"], r["key"]) for _, r in dec[(dec["kind"] == "complex_link") & (dec["decision"] == "confirm")].iterrows()}
    cx_reject = {(r["news_id"], r["key"]) for _, r in dec[(dec["kind"] == "complex_link") & (dec["decision"] == "reject")].iterrows()}
    user_alias = {r["key"]: r["value"] for _, r in dec[(dec["kind"] == "program_alias") & (dec["decision"] == "add_alias")].iterrows()}
    not_program = set(dec.loc[(dec["kind"] == "program_phrase") & (dec["decision"] == "not_a_program"), "key"])

    arts, sent_rows, cx_rows, prog_rows, org_rows, qty_rows, vul_rows, new_rows, clean_log = [], [], [], [], [], [], [], [], []
    for k, d in enumerate(raw):
        nid = news_id(d)
        title = clean_title(d["title"])
        cr = C.clean_article(title, d.get("body", ""))
        body = cr["body_clean"]
        sents = IX.split_sentences(body)
        a = dict(news_id=nid, source_order=k + 1, date=str(d.get("date") or "")[:10], title=title, title_raw=d["title"], url=d.get("final_url") or d["url"],
                 outlet=outlet(d.get("final_url") or d["url"]), reuse_status_raw=d.get("reuse_status"), reuse_policy=reuse_policy(d.get("reuse_status")),
                 crawl_status="fetch_failed_body_from_cache" if d.get("reuse_status") == "접근 실패" else "fetched",
                 collected_at=d.get("collected_at"), raw_chars=len(d.get("body") or ""), body_clean=body, n_chars=len(body), n_sentences=len(sents),
                 subtitles=J(cr["subtitles"]), captions=J(cr["captions"])[:400], is_snippet=int(cr["is_snippet"]), cut_tail=int(cr["cut_tail"]),
                 truncated=int(bool(body) and not C.END.search(body.split("\n")[-1])), hardwrapped=int(cr.get("hardwrapped", False)))
        clean_log.append(dict(news_id=nid, raw_lines=cr["n_lines"], kept_lines=cr["n_kept"], raw_chars=a["raw_chars"], clean_chars=a["n_chars"],
                              kept_char_ratio=round(a["n_chars"] / max(1, a["raw_chars"]), 3), is_snippet=a["is_snippet"], cut_tail=a["cut_tail"], hardwrapped=a["hardwrapped"]))
        full = title + "\n" + body
        for j, s in enumerate(sents):
            sent_rows.append(dict(news_id=nid, sent_idx=j, role=sentence_role(s, j), text=s, text_masked=SG.mask_text(s), n_chars=len(s)))
        hits = [h for h in cm.complexes(full) if (nid, h["complex_id"]) not in cx_reject]
        for h in hits:
            if h["needs_review"] and (nid, h["complex_id"]) in cx_confirm:
                h.update(match_type=h["match_type"] + "+user_confirmed", confidence="high", needs_review=0)
            cx_rows.append(dict(news_id=nid, **h))
        a["branches"] = J(cm.branch(full))
        sido, sgg = cm.regions(full)
        a["sido"], a["sigungu"] = J(sido), J(sgg)
        acts = LK.actors(full)
        a["actor_types"] = J(acts)
        for o in LK.org_names(full):
            org_rows.append(dict(news_id=nid, org_name=o))
        a["relevance"] = LK.relevance(title, body, acts, sum(1 for h in hits if not h["needs_review"]))
        a["is_partnership"] = int(bool(LK.PARTNERSHIP_RX.search(full)))
        links, new = PG.link_programs(title, body, sents, aidx, valid, user_alias, not_program)
        for L_ in links:
            prog_rows.append(dict(news_id=nid, std_name=name_std.get(L_["std_id"]), std_family=fam_std.get(L_["std_id"]), **L_))
        for nw in new:
            new_rows.append(dict(news_id=nid, **nw))
        prim = next((L_ for L_ in links if L_["confidence"] in ("high", "medium")), None)
        a["primary_std_id"] = prim["std_id"] if prim else ""
        a["primary_std_name"] = name_std.get(prim["std_id"], "") if prim else ""
        a["primary_std_confidence"] = prim["confidence"] if prim else ""
        a["std_ids"] = J([L_["std_id"] for L_ in links if L_["confidence"] != "low"])
        sem = SG.semantic(title, body, pur_std.get(a["primary_std_id"], "") or "")
        a["target_codes"], a["target_labels"] = J(sem["targets"]), J(SG.labels(TX.TARGETS, sem["targets"]))
        a["org_type_codes"], a["org_type_labels"] = J(sem["orgs"]), J(SG.labels(TX.ORGS, sem["orgs"]) if isinstance(TX.ORGS, dict) else sem["orgs"])
        a["purpose_codes"], a["purpose_labels"] = J(sem["purposes"]), J(SG.labels(TX.PURPOSES, sem["purposes"]))
        nd = list(dict.fromkeys(sem["needs"] + [x for x in str(need_std.get(a["primary_std_id"], "") or "").split("|") if x and x != "nan"]))
        a["need_domain_codes"], a["need_domain_labels"] = J(nd), J(SG.labels(TX.NEED_DOMAINS, nd))
        a["effect_codes"] = J(sem["effects"])
        for q in SG.quantities(body):
            qty_rows.append(dict(news_id=nid, **q))
        qs = [q for q in SG.quantities(body)]
        a["persons_max"] = max([q["value"] for q in qs if q["kind"] == "persons"], default=None)
        a["households_max"] = max([q["value"] for q in qs if q["kind"] == "households"], default=None)
        a["money_max_krw"] = max([q["value"] for q in qs if q["kind"] == "money"], default=None)
        ed, eb = SG.event_date(body[:400], a["date"])
        a["event_date_est"], a["event_date_basis"] = ed, eb
        vs = SG.vulnerability(sents)
        for v in vs:
            vul_rows.append(dict(news_id=nid, **v))
        a["vuln_codes"] = J(sorted({v["code"] for v in vs}))
        a["title_masked"] = SG.mask_text(title)
        a["body_masked"] = SG.mask_text(body)
        arts.append(a)

    pairs = dedup(arts)
    A = pd.DataFrame(arts)
    S_ = pd.DataFrame(sent_rows)
    # 청크·벡터
    ch_rows = []
    for _, a in A.iterrows():
        ss = S_[S_["news_id"] == a["news_id"]].sort_values("sent_idx")
        texts = ss["text_masked"].tolist()
        for ci, idxs in enumerate(IX.make_chunks(texts)):
            ch_rows.append(dict(chunk_id=f"{a['news_id']}_c{ci:02d}", news_id=a["news_id"], chunk_idx=ci, sent_from=idxs[0], sent_to=idxs[-1],
                                text=(a["title_masked"] + "\n" if ci == 0 else "") + " ".join(texts[i] for i in idxs)))
    CH = pd.DataFrame(ch_rows)
    prog = sd[sd["scope"].isin(["PROGRAM", "HOUSEHOLD_SUPPORT"])].copy()
    ptxt = (prog["std_name"] + " " + prog["definition_ko"].fillna("") + " " + prog["alias_examples"].fillna("").str.replace(r"\(\d+\)", "", regex=True)).tolist()
    V = IX.build_vectors(CH["text"].tolist(), ptxt)
    np.save(os.path.join(out, "index", "chunk_lsa64.npy"), V["Zc"].astype("float32"))
    np.save(os.path.join(out, "index", "program_lsa64.npy"), V["Zp"].astype("float32"))
    pd.DataFrame({"row": range(len(CH)), "chunk_id": CH["chunk_id"]}).to_csv(os.path.join(out, "index", "chunk_lsa64_rows.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame({"row": range(len(prog)), "std_id": prog["std_id"].values}).to_csv(os.path.join(out, "index", "program_lsa64_rows.csv"), index=False, encoding="utf-8-sig")
    top = []
    for i, cid in enumerate(CH["chunk_id"]):
        sims = V["sim"][i]
        for r_, j in enumerate(np.argsort(-sims)[:3]):
            top.append(dict(chunk_id=cid, rank=r_ + 1, std_id=prog["std_id"].iat[j], std_name=prog["std_name"].iat[j], cosine_tfidf=round(float(sims[j]), 4)))
    TOP = pd.DataFrame(top)
    TOP.to_csv(os.path.join(out, "index", "chunk_program_similarity_top3.csv"), index=False, encoding="utf-8-sig")
    kw = IX.keywords((A["title"] + " " + A["body_clean"]).tolist())
    A["keywords"] = ["|".join(k) for k in kw]
    with open(os.path.join(out, "chunks.jsonl"), "w", encoding="utf-8") as fh:
        meta = A.set_index("news_id")
        for _, c in CH.iterrows():
            m = meta.loc[c["news_id"]]
            t3 = TOP[TOP["chunk_id"] == c["chunk_id"]]
            fh.write(json.dumps(dict(chunk_id=c["chunk_id"], news_id=c["news_id"], chunk_idx=int(c["chunk_idx"]), text=c["text"], date=m["date"], outlet=m["outlet"],
                                     relevance=m["relevance"], is_representative=int(m["is_representative"]), reuse_policy=m["reuse_policy"],
                                     complex_ids=[x["complex_id"] for x in cx_rows if x["news_id"] == c["news_id"] and not x["needs_review"]],
                                     branches=[x for x in str(m["branches"]).split("|") if x], std_ids=[x for x in str(m["std_ids"]).split("|") if x],
                                     need_domains=[x for x in str(m["need_domain_codes"]).split("|") if x], vuln_codes=[x for x in str(m["vuln_codes"]).split("|") if x],
                                     similar_programs=t3[["std_id", "cosine_tfidf"]].values.tolist()), ensure_ascii=False) + "\n")

    # 링크·신호 표
    CX = pd.DataFrame(cx_rows)
    PRG = pd.DataFrame(prog_rows)
    ORG = pd.DataFrame(org_rows)
    QTY = pd.DataFrame(qty_rows)
    VUL = pd.DataFrame(vul_rows)
    NEW = pd.DataFrame(new_rows)
    A["complex_ids"] = A["news_id"].map(CX[CX["needs_review"] == 0].groupby("news_id")["complex_id"].apply(J)).fillna("") if len(CX) else ""
    A["complex_ids_review"] = A["news_id"].map(CX[CX["needs_review"] == 1].groupby("news_id")["complex_id"].apply(J)).fillna("") if len(CX) else ""

    # 집계 특성(대표 기사만: 같은 사건의 중복 보도는 한 번만 센다)
    rep = A[A["is_representative"] == 1]
    P = PRG.merge(A[["news_id", "is_representative", "date", "relevance", "title"]], on="news_id")
    P = P[(P["is_representative"] == 1) & (P["confidence"] != "low")]
    pe = P.groupby("std_id").agg(n_articles=("news_id", "nunique"), n_high=("confidence", lambda s: int((s == "high").sum())),
                                 first_date=("date", "min"), last_date=("date", "max"),
                                 n_kohom=("relevance", lambda s: int(s.str.startswith(("A_", "B_")).sum())),
                                 example_titles=("title", lambda s: " / ".join(s.head(3)))).reset_index()
    pe["std_name"] = pe["std_id"].map(name_std)
    pe["std_family"] = pe["std_id"].map(fam_std)
    pe["community_records_30m"] = pe["std_id"].map(dict(zip(sd["std_id"], sd["n_records"])))
    pe["community_adoption_rate"] = pe["std_id"].map(dict(zip(sd["std_id"], sd["adoption_rate"])))
    tg = A.set_index("news_id")["target_labels"]
    pe["targets_in_news"] = pe["std_id"].map(P.groupby("std_id")["news_id"].apply(lambda s: J(sorted({t for n in s for t in str(tg.get(n, "")).split("|") if t}))))
    pe = pe[["std_id", "std_name", "std_family", "n_articles", "n_high", "n_kohom", "first_date", "last_date", "community_records_30m", "community_adoption_rate", "targets_in_news", "example_titles"]]
    pe.sort_values("n_articles", ascending=False).to_csv(os.path.join(out, "features", "program_news_evidence.csv"), index=False, encoding="utf-8-sig")
    if len(CX):
        X_ = CX[CX["needs_review"] == 0].merge(A[["news_id", "date", "std_ids", "vuln_codes", "is_representative"]], on="news_id")
        X_ = X_[X_["is_representative"] == 1]
        cf = X_.groupby(["complex_id", "complex_name"]).agg(n_articles=("news_id", "nunique"), first_date=("date", "min"), last_date=("date", "max"),
                                                            std_ids=("std_ids", lambda s: J(sorted({x for v in s for x in str(v).split("|") if x}))),
                                                            vuln_codes=("vuln_codes", lambda s: J(sorted({x for v in s for x in str(v).split("|") if x}))),
                                                            news_ids=("news_id", J)).reset_index()
        cf.to_csv(os.path.join(out, "features", "complex_news_features.csv"), index=False, encoding="utf-8-sig")
    br = A[A["is_representative"] == 1].assign(branch=A["branches"].str.split("|")).explode("branch")
    br = br[br["branch"].fillna("") != ""].groupby("branch").agg(n_articles=("news_id", "nunique"), first_date=("date", "min"), last_date=("date", "max"),
                                                                 std_ids=("std_ids", lambda s: J(sorted({x for v in s for x in str(v).split("|") if x})))).reset_index()
    br.to_csv(os.path.join(out, "features", "branch_news_features.csv"), index=False, encoding="utf-8-sig")
    vf = VUL.merge(A[["news_id", "is_representative"]], on="news_id") if len(VUL) else VUL
    if len(vf):
        vs = vf[vf["is_representative"] == 1].groupby(["code", "label", "need_domain"]).agg(n_articles=("news_id", "nunique"), n_sentences=("sentence", "size")).reset_index()
        vs.sort_values("n_articles", ascending=False).to_csv(os.path.join(out, "features", "vulnerability_signal_summary.csv"), index=False, encoding="utf-8-sig")

    # 저장
    core = ["news_id", "source_order", "date", "event_date_est", "event_date_basis", "title", "outlet", "url", "relevance", "is_partnership", "dup_cluster", "dup_size",
            "is_representative", "primary_std_id", "primary_std_name", "primary_std_confidence", "std_ids", "complex_ids", "complex_ids_review", "branches", "sido", "sigungu",
            "actor_types", "target_codes", "target_labels", "org_type_codes", "org_type_labels", "purpose_codes", "purpose_labels", "need_domain_codes", "need_domain_labels",
            "effect_codes", "vuln_codes", "persons_max", "households_max", "money_max_krw", "keywords", "n_chars", "n_sentences", "is_snippet", "cut_tail", "truncated",
            "crawl_status", "reuse_status_raw", "reuse_policy", "collected_at"]
    A[core + ["title_masked", "body_masked"]].to_csv(os.path.join(out, "articles.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(out, "articles.jsonl"), "w", encoding="utf-8") as fh:
        for _, r in A[core + ["title_masked", "body_masked", "body_clean", "subtitles", "captions"]].iterrows():
            o = {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in r.items()}
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    S_.to_csv(os.path.join(out, "sentences.csv"), index=False, encoding="utf-8-sig")
    PRG.to_csv(os.path.join(out, "links", "article_program.csv"), index=False, encoding="utf-8-sig")
    CX.to_csv(os.path.join(out, "links", "article_complex.csv"), index=False, encoding="utf-8-sig")
    ORG.to_csv(os.path.join(out, "links", "article_org.csv"), index=False, encoding="utf-8-sig")
    QTY.to_csv(os.path.join(out, "signals", "quantities.csv"), index=False, encoding="utf-8-sig")
    VUL.to_csv(os.path.join(out, "signals", "vulnerability_sentences.csv"), index=False, encoding="utf-8-sig")
    NEW.to_csv(os.path.join(out, "signals", "new_program_candidates.csv"), index=False, encoding="utf-8-sig")
    pairs.to_csv(os.path.join(out, "qa", "duplicate_pairs.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(clean_log).to_csv(os.path.join(out, "qa", "cleaning_log.csv"), index=False, encoding="utf-8-sig")

    # 검토 대기열
    rq = []
    for _, r in CX[CX["needs_review"] == 1].iterrows() if len(CX) else []:
        rq.append(dict(kind="complex_link_base_only", news_id=r["news_id"], item=f"{r['complex_id']} {r['complex_name']}", detail=r["mention"]))
    low = PRG.merge(A[["news_id", "relevance", "primary_std_id"]], on="news_id")
    for _, r in A[(A["primary_std_id"] == "") & A["relevance"].str.startswith(("A_", "B_"))].iterrows():
        rq.append(dict(kind="kohom_article_without_program", news_id=r["news_id"], item=r["title"], detail=r["relevance"]))
    for _, r in A[(A["is_snippet"] == 1) | (A["n_chars"] == 0) | (A["truncated"] == 1)].iterrows():
        rq.append(dict(kind="short_or_truncated_body", news_id=r["news_id"], item=r["title"], detail=f"chars={r['n_chars']} snippet={r['is_snippet']} truncated={r['truncated']}"))
    for _, r in NEW.iterrows() if len(NEW) else []:
        rq.append(dict(kind="new_program_candidate", news_id=r["news_id"], item=r["phrase"], detail=f"best={r['best_alias']} sim={r['best_sim']:.2f}"))
    pd.DataFrame(rq).to_csv(os.path.join(out, "qa", "review_queue.csv"), index=False, encoding="utf-8-sig")

    # 점검
    chk = []
    def add(cid, d, res, ok):
        chk.append(dict(check_id=cid, description=d, result=res, status="PASS" if ok else "FAIL"))
    add("N01", "news_id 유일", f"{A['news_id'].nunique()}/{len(A)}", A["news_id"].is_unique)
    add("N02", "원자료 기사 수 = 산출 기사 수", f"{len(raw)} → {len(A)}", len(raw) == len(A))
    add("N03", "본문이 빈 기사 수(정제 후)", int((A["n_chars"] == 0).sum()), (A["n_chars"] == 0).sum() == 0)
    add("N04", "정제 본문에 저작권·메뉴 표기 잔존", int(A["body_clean"].str.contains(r"무단\s*전재|재배포|저작권자|글자크기|로그인").sum()), not A["body_clean"].str.contains(r"무단\s*전재|재배포|저작권자|글자크기|로그인").any())
    add("N05", "가린 본문에 전화·이메일 잔존", int(A["body_masked"].str.contains(SG.PHONE.pattern + "|" + SG.EMAIL.pattern).sum()), not A["body_masked"].str.contains(SG.PHONE.pattern + "|" + SG.EMAIL.pattern).any())
    ids = set(master["complex_id"])
    add("N06", "단지 연결 complex_id가 통합표에 존재", f"{CX['complex_id'].isin(ids).sum() if len(CX) else 0}/{len(CX)}", CX["complex_id"].isin(ids).all() if len(CX) else True)
    add("N07", "프로그램 연결 std_id가 표준 사전에 존재", f"{PRG['std_id'].isin(set(sd['std_id'])).sum()}/{len(PRG)}", PRG["std_id"].isin(set(sd["std_id"])).all())
    add("N08", "중복 묶음마다 대표 기사 1건", f"{A.groupby('dup_cluster')['is_representative'].sum().eq(1).all()}", A.groupby("dup_cluster")["is_representative"].sum().eq(1).all())
    add("N09", "모든 기사에 문장이 1개 이상(빈 본문 제외)", int((A[A['n_chars'] > 0]['n_sentences'] == 0).sum()), (A[A["n_chars"] > 0]["n_sentences"] > 0).all())
    add("N10", "청크마다 벡터 1개", f"{len(CH)} chunks / {V['Zc'].shape[0]} vectors", len(CH) == V["Zc"].shape[0])
    add("N11", "참고: 공단 관련 대표 기사(A·B) 중 프로그램(중간 이상) 연결 비율", f"{(rep[rep['relevance'].str.startswith(('A_','B_'))]['primary_std_id'] != '').mean():.0%}", True)
    add("N12", "참고: LSA 64차원 설명 분산", f"{V['explained']:.2f}", True)
    CK = pd.DataFrame(chk)
    CK.to_csv(os.path.join(out, "qa", "quality_checks.csv"), index=False, encoding="utf-8-sig")
    summary = dict(version=VERSION, built_at=datetime.now().isoformat(timespec="seconds"), raw_path=raw_path, n_articles=len(A), n_representative=int(A["is_representative"].sum()),
                   n_dup_clusters_multi=int((A.groupby("dup_cluster").size() > 1).sum()), relevance=A["relevance"].value_counts().to_dict(),
                   n_sentences=len(S_), n_chunks=len(CH), n_program_links=len(PRG), program_link_confidence=PRG["confidence"].value_counts().to_dict(),
                   n_complex_links=int((CX["needs_review"] == 0).sum()) if len(CX) else 0, n_complex_link_candidates=int((CX["needs_review"] == 1).sum()) if len(CX) else 0,
                   n_vuln_sentences=len(VUL), n_new_program_candidates=len(NEW), checks_pass=int((CK["status"] == "PASS").sum()), checks_total=len(CK),
                   reuse_policy=A["reuse_policy"].value_counts().to_dict(), lsa_explained=V["explained"])
    write_manifest(out, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(CK.to_string())
    return A, summary


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    _, summary = build(a.raw, a.out)
    DC.write_docs(a.out, summary)
    write_checksums(a.out)


if __name__ == "__main__":
    main()
