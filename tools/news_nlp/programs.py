# -*- coding: utf-8 -*-
"""기사 ↔ 표준 프로그램(std_id) 연결. 커뮤니티 NLP와 같은 코드 체계를 쓴다.

세 가지 신호를 모아 기사별로 합친다.
1) quoted_rule : 따옴표 안 행사명('사랑의 한그릇' 등)을 커뮤니티 NLP 규칙 엔진(classify_row)에 행사명으로, 그 문장을 내용으로 넣어 판정
2) title_rule  : 기사 제목을 행사명으로, 첫 두 문장을 내용으로 넣어 판정
3) alias_knn   : 따옴표 행사명·제목을 30개월 활동 기록의 별칭 사전(alias_dictionary, 9,207개 군집)과 글자 2~3그램 TF-IDF 코사인으로 비교(최근접 이웃)
4) sentence_rule: 활동 동사가 있는 문장마다 규칙 엔진(행사명 없이 내용만) — 보조 신호(low)
확신도: 두 신호 이상이 같은 std_id면 high, 따옴표·제목 규칙 단독 또는 근접도 0.6 이상이면 medium, 그 밖은 low.
규칙·사전에 없는 따옴표 행사명은 '새 프로그램 후보'로 따로 모은다.
"""
import re

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from community_nlp.classify import classify_row

QUOTE_RX = re.compile(r"‘([^’\n]{3,40})’|'([^'\n]{3,40})'|“([^”\n]{3,40})”|\"([^\"\n]{3,40})\"|「([^」\n]{3,40})」|『([^』\n]{3,40})』")
NOT_NAME_START = re.compile(r"^(이라|라고|라며|며\s|고\s|이\s|가\s|은\s|는\s|을\s|를\s|와\s|과\s|의\s|에\s)|라며|라고\s")
# 기관·장소 이름이 프로그램 판정에 끼어들지 않도록 판정 전에 지운다(예: '마이홈센터' → 주거비 상담으로 오판)
ORG_MASK = re.compile(r"주택관리공단(\(주\))?|KOHOM|한국토지주택공사|\bLH\b|마이홈\s?센터|주거행복지원센터|"
                      r"[가-힣0-9]{2,12}(관리소|지사|지역단|종합사회복지관|사회복지관|복지관|복지재단|보건소|치매안심센터)")
# 뉴스 문맥에서 확인된 오판 교정(근거: 2026-11-17 표본 검토)
NEWS_OVERRIDES = [(re.compile(r"반려식물|화분|분갈이|식물\s?클리닉"), "Q03", "H03")]
ACT_VERB = re.compile(r"진행|개최|실시|열었|열어|전달|운영|제공|지원|교육|나눔|협약|캠페인|방문|점검|설치|상담|체험|공연|행사")
SPEECHY = re.compile(r"(다|요|니다|겠다|했다|것)$|[.!?]$|(하게|해서|하며|으로써)\s")
# 새 프로그램 후보는 행사·사업을 가리키는 이름만(노래 제목·인용 문구 제외)
PROGRAM_NOUN = re.compile(r"(행사|축제|사업|교실|캠페인|프로그램|교육|나눔|상담소|클리닉|봉사|공연|잔치|모임|봉사단|지원단|돌봄단|프로젝트|데이|주간|한마당|장터|투어|챌린지|그릇|밥상)\s*$")


class AliasIndex:
    def __init__(self, alias_df, sd):
        rows = []
        for _, r in alias_df.iterrows():
            for v in [r["canonical_title"]] + [x.strip() for x in str(r["variants"]).split(" / ") if x.strip()]:
                rows.append((v, r["std_id"], int(r["n_records"])))
        a = pd.DataFrame(rows, columns=["title", "std_id", "n"]).drop_duplicates(["title", "std_id"])
        nm = sd[["std_id", "std_name"]].rename(columns={"std_name": "title"})
        nm["n"] = 1000
        self.t = pd.concat([a, nm], ignore_index=True)
        self.vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), sublinear_tf=True)
        self.X = self.vec.fit_transform(self.t["title"].map(lambda s: re.sub(r"\s+", "", s)))

    def query(self, phrase, k=3):
        q = self.vec.transform([re.sub(r"\s+", "", phrase)])
        sim = (self.X @ q.T).toarray().ravel()
        top = np.argsort(-sim)[: k * 5]
        out, seen = [], set()
        for i in top:
            sid = self.t["std_id"].iat[i]
            if sid in seen:
                continue
            seen.add(sid)
            out.append((sid, float(sim[i]), self.t["title"].iat[i]))
            if len(out) >= k:
                break
        return out


def quoted_phrases(text):
    out = []
    for mt in QUOTE_RX.finditer(text):
        p = next(g for g in mt.groups() if g).strip()
        if SPEECHY.search(p) or len(p) < 3 or re.fullmatch(r"[\d\s.,]+", p) or NOT_NAME_START.search(p):
            continue
        out.append((p, mt.start()))
    return out


def strip_orgs(s):
    return re.sub(r"\s{2,}", " ", ORG_MASK.sub(" ", s or "")).strip()


def _override(sid, *texts):
    for rx, a, b in NEWS_OVERRIDES:
        if sid == a and any(rx.search(t or "") for t in texts):
            return b
    return sid


def _rule(name, content):
    r = classify_row(strip_orgs(name), strip_orgs(content))
    t = r["primary"]
    return dict(std_id=_override(t["id"], name, content), scope=t.get("scope"), score=float(r["score"]), margin=float(r["margin"]),
                evidence=r["evidence"], fallback=r["fallback"], field=r["evidence_field"])


def link_programs(title, body, sentences, alias_idx, valid_ids, user_alias=None, not_program=()):
    """returns (links: list[dict], new_candidates: list[dict])
    user_alias: 사용자가 확정한 {행사명: std_id}(review_decisions.csv). not_program: 프로그램 이름이 아니라고 확정한 문구."""
    user_alias = user_alias or {}
    ev = []
    lead = " ".join(sentences[:2])
    r = _rule(title, lead)
    if r["std_id"] in valid_ids and not r["fallback"]:
        ev.append(dict(std_id=r["std_id"], method="title_rule", score=r["score"], evidence=title, pos=0))
    for sid, sim, at in alias_idx.query(strip_orgs(title), 1):
        if sim >= 0.45:
            ev.append(dict(std_id=_override(sid, title), method="alias_knn", score=sim, evidence=f"{title} ≈ {at}", pos=0))
    new = []
    full = title + "\n" + body
    for ph, pos in quoted_phrases(full):
        sent = next((s for s in sentences if ph in s), lead)
        r = _rule(ph, sent)
        knn = [(_override(k_[0], ph), k_[1], k_[2]) for k_ in alias_idx.query(strip_orgs(ph), 1)]
        ok_rule = r["std_id"] in valid_ids and not r["fallback"] and "name" in str(r["field"])   # 따옴표 이름 자체가 근거일 때만
        if ph in user_alias:
            ev.append(dict(std_id=user_alias[ph], method="user_alias", score=1.0, evidence=f"{ph} (사용자 확정 별칭)", pos=pos))
            continue
        if ok_rule:
            ev.append(dict(std_id=r["std_id"], method="quoted_rule", score=r["score"], evidence=ph, pos=pos))
        if knn and knn[0][1] >= 0.45:
            ev.append(dict(std_id=knn[0][0], method="alias_knn", score=knn[0][1], evidence=f"{ph} ≈ {knn[0][2]}", pos=pos))
        if (not ok_rule and ph not in not_program and (not knn or knn[0][1] < 0.45) and ACT_VERB.search(sent) and PROGRAM_NOUN.search(ph)
                and ph not in {n["phrase"] for n in new}):
            new.append(dict(phrase=ph, sentence=sent[:200], best_alias=knn[0][2] if knn else "", best_sim=knn[0][1] if knn else 0.0))
    for k, s in enumerate(sentences):
        if not ACT_VERB.search(s):
            continue
        r = _rule("", s)
        if r["std_id"] in valid_ids and not r["fallback"] and r["score"] >= 2.0:
            ev.append(dict(std_id=r["std_id"], method="sentence_rule", score=r["score"], evidence=s[:120], pos=1000 + k))
    if not ev:
        return [], new
    e = pd.DataFrame(ev)
    links = []
    for sid, g in e.groupby("std_id"):
        methods = sorted(set(g["method"]))
        strong = {"title_rule", "quoted_rule"} & set(methods)
        knn_best = g.loc[g["method"] == "alias_knn", "score"].max() if (g["method"] == "alias_knn").any() else 0.0
        n_sig = len(set(methods) - {"sentence_rule"}) + (1 if "sentence_rule" in methods and len(methods) == 1 else 0)
        if "user_alias" in methods or len(set(methods) - {"sentence_rule"}) >= 2 or (strong and "sentence_rule" in methods):
            conf = "high"
        elif strong or knn_best >= 0.6:
            conf = "medium"
        else:
            conf = "low"
        best = g.sort_values(["pos"]).iloc[0]
        links.append(dict(std_id=sid, confidence=conf, methods="|".join(methods), n_signals=int(len(g)), alias_sim_max=round(float(knn_best), 3),
                          first_pos=int(g["pos"].min()), evidence="; ".join(dict.fromkeys(g["evidence"].astype(str).str[:80]))[:300]))
    order = {"high": 0, "medium": 1, "low": 2}
    links.sort(key=lambda d: (order[d["confidence"]], d["first_pos"]))
    for i, d in enumerate(links):
        d["rank"] = i + 1
    return links, new
