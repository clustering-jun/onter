"""모듈 2. 유사 단지와 프로그램 사례.

'유사'를 한 가지로 정하지 않는다. 구조(주민·주거·접근성), 필요 프로파일, 운영 이력(행동), 거리, 지사를 따로 만들고
실험으로 비교한 뒤 섞는다. 사례는 세 곳에서 찾는다: 비슷한 단지의 활동 기록, 주거복지사 사례집 카드, 뉴스.
"""
from functools import lru_cache
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from . import config as C, data as D, features as F, m1_profile as M1

SIM_KINDS = ["demo", "struct", "need", "behav", "geo", "branch", "hybrid"]
HYBRID_W = {"struct": 0.5, "behav": 0.3, "geo": 0.2}


def _rbf(X):
    X = np.asarray(X, float)
    d2 = ((X[:, None, :] - X[None, :, :]) ** 2).sum(-1)
    return np.exp(-d2 / np.median(d2[d2 > 0]))


def behavior_vectors(start, end):
    """운영 이력 벡터: 프로그램별 기록 있는 달 수(log) × idf. 흔한 프로그램보다 드문 선택이 닮음을 더 잘 드러낸다."""
    X = F.interactions(start, end, "months")
    df = (X > 0).sum(axis=0)
    idf = np.log((1 + (X.sum(axis=1) > 0).sum()) / (1 + df)) + 1
    return np.log1p(X) * idf


def sim_matrix(kind, start=C.FIRST_MONTH, end=C.LAST_MONTH, weights=None):
    """단지×단지 유사도(0~1, 대각 0). 행동 유사도는 주어진 기간의 기록만 쓴다."""
    ids = D.complexes().index
    c = D.complexes()
    if kind == "demo":
        S = _rbf(F.matrix(["demo"]))
    elif kind == "struct":
        S = _rbf(F.matrix(F.STRUCT))
    elif kind == "need":
        S = _rbf(M1.need_table("S"))
    elif kind == "behav":
        S = np.clip(F.cosine(behavior_vectors(start, end)), 0, 1)
    elif kind == "geo":
        S = 1 / (1 + F.haversine(c["lat"], c["lon"]) / 10.0)               # 10km에서 0.5
    elif kind == "branch":
        S = (c["branch"].to_numpy()[:, None] == c["branch"].to_numpy()[None, :]).astype(float)
        S = S * (0.5 + 0.5 * np.random.default_rng(C.SEED).random(S.shape))  # 지사 안에서는 무작위 순서
    elif kind == "hybrid":
        w = weights or HYBRID_W
        parts = {k: pd.DataFrame(sim_matrix(k, start, end), index=ids, columns=ids).rank(axis=1, pct=True).to_numpy() for k in w}
        S = sum(w[k] * parts[k] for k in w) / sum(w.values())
        if "behav" in w:                                                     # 기록 없는 단지는 행동 유사도를 빼고 다시 섞는다
            cold = ~np.isin(ids, F.active_complexes(start, end))
            rest = {k: v for k, v in w.items() if k != "behav"} or {"struct": 1.0}
            parts.setdefault("struct", pd.DataFrame(sim_matrix("struct"), index=ids, columns=ids).rank(axis=1, pct=True).to_numpy())
            S[cold] = (sum(rest[k] * parts[k] for k in rest) / sum(rest.values()))[cold]
    else:
        raise ValueError(kind)
    S = np.array(S, float)
    np.fill_diagonal(S, 0)
    return pd.DataFrame(S, index=ids, columns=ids)


def peers(S, cid, k=10, pool=None):
    """유사도 표에서 한 단지의 상위 k개 이웃. pool을 주면 그 안에서만 고른다(예: 기록 있는 단지)."""
    s = S.loc[cid]
    if pool is not None:
        s = s[s.index.isin(pool)]
    return s.nlargest(k)


# ───────── 프로그램 문서와 검색 ─────────
@lru_cache(maxsize=None)
def program_docs():
    sd = D.rd("community_nlp_2026_v1/standard_program_dictionary.csv").set_index("std_id").reindex(D.programs().index)
    txt = sd["std_name"].fillna("") + " " + sd["definition_ko"].fillna("")
    return txt


def train_title_docs(start, end, max_titles=300):
    """기간 내 기록의 제목·내용을 프로그램별로 모은 문서(검색 색인용). 평가 때는 학습 구간만 넣는다."""
    r = F.window(start, end)
    r = r[r["std_id"].isin(D.programs().index)]
    t = (r["program_name_masked"].fillna("") + " " + r["activity_content_masked"].fillna("")).str.slice(0, 200)
    g = t.groupby(r["std_id"]).agg(lambda s: " // ".join(s.drop_duplicates().head(max_titles)))
    return (program_docs() + " " + g.reindex(D.programs().index).fillna(""))


class ProgramSearch:
    """자유 문장 → 표준 프로그램. 글자 n-gram TF-IDF, LSA, BM25를 따로 쓰거나 순위 융합(RRF)한다."""

    def __init__(self, docs, lsa_dim=64):
        self.ids = list(docs.index)
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True, min_df=1)
        self.X = self.vec.fit_transform(docs.to_numpy())
        self.svd = TruncatedSVD(min(lsa_dim, len(self.ids) - 1), random_state=C.SEED).fit(self.X)
        self.Z = self.svd.transform(self.X)
        # BM25(글자 2-gram 토큰)
        self.cv = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 2), use_idf=False, norm=None)
        tf = self.cv.fit_transform(docs.to_numpy()).toarray()
        self.tf, dl = tf, tf.sum(1)
        df = (tf > 0).sum(0)
        self.idf = np.log(1 + (len(self.ids) - df + 0.5) / (df + 0.5))
        k1, b = 1.2, 0.75
        self.bm = tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl[:, None] / dl.mean()))

    def scores(self, queries, method="tfidf"):
        q = list(queries)
        if method == "tfidf":
            return (self.vec.transform(q) @ self.X.T).toarray()
        if method == "lsa":
            return F.cosine(self.svd.transform(self.vec.transform(q)), self.Z)
        if method == "bm25":
            qt = (self.cv.transform(q).toarray() > 0).astype(float)
            return qt @ (self.bm * self.idf).T
        if method == "rrf":
            out = 0
            for m in ("tfidf", "bm25", "lsa"):
                r = (-self.scores(q, m)).argsort(1).argsort(1) + 1
                out = out + 1 / (60 + r)
            return out
        raise ValueError(method)

    def search(self, query, k=5, method="rrf"):
        s = self.scores([query], method)[0]
        top = np.argsort(-s)[:k]
        return [(self.ids[i], float(s[i])) for i in top]


# ───────── 프로그램 간 유사도(관련 프로그램·사례 대체용) ─────────
def item_sim(kind="hybrid", start=C.FIRST_MONTH, end=C.LAST_MONTH):
    ids = D.programs().index
    if kind == "taxonomy":
        S = F.cosine(F.item_taxonomy())
    elif kind == "text":
        ps = ProgramSearch(program_docs())
        S = F.cosine(ps.Z)
    elif kind == "cooc":
        X = F.interactions(start, end).to_numpy()
        inter = X.T @ X
        n = X.sum(0)
        S = inter / np.maximum(n[:, None] + n[None, :] - inter, 1)        # 자카드
    else:
        S = (item_sim("taxonomy", start, end).rank(axis=1, pct=True) + item_sim("text", start, end).rank(axis=1, pct=True)
             + item_sim("cooc", start, end).rank(axis=1, pct=True)).to_numpy() / 3
    S = np.array(S, float)
    np.fill_diagonal(S, 0)
    return pd.DataFrame(S, index=ids, columns=ids)


# ───────── 사례 검색 ─────────
def _snip(s, n=110):
    s = "" if pd.isna(s) else " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + "…"


def peer_cases(cid, std_id, S, k=3, start=C.FIRST_MONTH, end=C.LAST_MONTH):
    """비슷한 단지가 이 프로그램을 운영한 기록. 유사도·최근성·기록의 정보량으로 고르고 단지당 1건만 싣는다."""
    r = F.window(start, end)
    r = r[(r["std_id"] == std_id) & (r["complex_id"] != cid)]
    if r.empty:
        return []
    c, og = D.complexes(), D.codebook()["partner_org"]
    sim = S.loc[cid].reindex(r["complex_id"]).to_numpy()
    rec = (pd.PeriodIndex(r["ym"], freq="M") - pd.Period(start, "M")).map(lambda x: x.n).to_numpy() / 30.0
    info = (r["low_info_text_flag"].fillna(0) == 0).to_numpy() * 0.5 + np.clip(r["content_len"].fillna(0).to_numpy() / 80, 0, 1) * 0.5
    r = r.assign(_score=pd.Series(sim).rank(pct=True).to_numpy() * 0.6 + rec * 0.15 + info * 0.25, _sim=sim)
    r = r.sort_values("_score", ascending=False).drop_duplicates("complex_id").head(k)
    out = []
    for _, x in r.iterrows():
        partners = [og.get(o, o) for o in str(x["partner_org_codes"]).split("|")] if pd.notna(x["partner_org_codes"]) else []
        out.append(dict(source="peer_record", complex_id=x["complex_id"], complex=c.at[x["complex_id"], "name"], similarity=round(float(x["_sim"]), 3),
                        month=x["ym"], title=_snip(x["program_name_masked"], 60), content=_snip(x["activity_content_masked"]),
                        participants=None if pd.isna(x["participants_total"]) else int(x["participants_total"]), partners=partners,
                        place=_snip(x["place_masked"], 30), record_id=x["record_id"]))
    return out


def casebook_cards(std_id, k=2, IS=None):
    """사례집 근거 카드. 같은 프로그램 카드가 없으면 가장 가까운 프로그램의 카드를 '비슷한 프로그램'으로 붙인다."""
    cards = D.casebook()["cards"]
    hit = cards[cards["std_id"] == std_id]
    rel = "같은 프로그램"
    if hit.empty and IS is not None:
        have = [s for s in cards["std_id"].dropna().unique() if s in IS.index]
        near = IS.loc[std_id, have].nlargest(1)
        if len(near) and near.iloc[0] >= 0.97:                              # 충분히 가까울 때만 대신 싣는다
            hit, rel = cards[cards["std_id"] == near.index[0]], f"비슷한 프로그램({D.programs().at[near.index[0], 'name']})"
    return [dict(source="casebook", relation=rel, card_id=x["card_id"], headline=x["headline"], region=x["region"], need=_snip(x["need"], 160),
                 how=_snip(x["how_it_runs"], 160), partners=_snip(x["partners"], 120), outcomes=_snip(x["outcomes"], 160),
                 obstacles=_snip(x["obstacles_and_solutions"], 200)) for _, x in hit.head(k).iterrows()]


def news_for(std_id, k=2):
    n = D.news()
    ap, ar = n["article_program"], n["articles"].set_index("news_id")
    hit = ap[(ap["std_id"] == std_id) & (ap["confidence"] != "low")].sort_values("rank")
    out = []
    for nid in hit["news_id"].drop_duplicates().head(k):
        if nid in ar.index and ar.at[nid, "is_representative"] == 1:
            out.append(dict(source="news", news_id=nid, date=ar.at[nid, "date"], title=ar.at[nid, "title"], outlet=ar.at[nid, "outlet"], url=ar.at[nid, "url"]))
    return out                                                              # 본문은 싣지 않는다(재사용 허락 미확인) — 제목과 링크만


def evidence_bundle(cid, std_id, S, IS=None, k=3):
    return dict(peer_records=peer_cases(cid, std_id, S, k), casebook=casebook_cards(std_id, 2, IS), news=news_for(std_id, 2))
