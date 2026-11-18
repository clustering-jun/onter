# -*- coding: utf-8 -*-
"""문장 분리·검색용 청크·벡터 색인.

- 문장: Kiwi(kiwipiepy) 문장 분리. 실패하면 마침표 규칙으로 나눈다.
- 청크: 문장을 이어 450자 안팎으로 묶고 앞 청크의 마지막 문장을 겹친다(RAG 검색 단위).
- 벡터: 글자 2~4그램 TF-IDF(띄어쓰기·조사 변형에 강함) → LSA(TruncatedSVD)로 압축한 밀집 벡터.
  같은 공간에 표준 프로그램 설명(이름+정의+대표 별칭)도 넣어 '청크 ↔ 프로그램' 유사도를 구한다.
- 핵심어: Kiwi 명사(NNG·NNP) TF-IDF 상위어.
외부 모델(문장 임베딩)이 없는 환경이라 재현 가능한 고전 방식을 썼다. 나중에 임베딩 모델로 바꿔도 chunks.jsonl의 구조는 그대로 쓴다.
"""
import re

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

try:
    from kiwipiepy import Kiwi
    _KIWI = Kiwi()
except Exception:   # noqa: BLE001
    _KIWI = None


def split_sentences(text):
    out = []
    for para in [p for p in text.split("\n") if p.strip()]:
        if _KIWI is not None:
            ss = [s.text.strip() for s in _KIWI.split_into_sents(para)]
        else:
            ss = re.split(r"(?<=[다요]\.)\s+|(?<=[.!?])\s+(?=[가-힣“\"'‘(])", para)
        out += [s for s in ss if len(s.strip()) >= 2]
    return out


def nouns(text):
    if _KIWI is None:
        return re.findall(r"[가-힣]{2,}", text)
    return [t.form for t in _KIWI.tokenize(text) if t.tag in ("NNG", "NNP") and len(t.form) >= 2]


def make_chunks(sentences, max_chars=450, overlap=1):
    chunks, cur = [], []
    for k, s in enumerate(sentences):
        if cur and sum(len(sentences[i]) for i in cur) + len(s) > max_chars:
            chunks.append(cur)
            cur = cur[-overlap:] if overlap else []
        cur.append(k)
    if cur and (not chunks or cur != chunks[-1][-len(cur):]):
        chunks.append(cur)
    return chunks


def build_vectors(chunk_texts, program_texts, dim=64, seed=7):
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True, min_df=1)
    X = vec.fit_transform([re.sub(r"\s+", " ", t) for t in chunk_texts + program_texts])
    k = max(2, min(dim, X.shape[0] - 1, X.shape[1] - 1))
    svd = TruncatedSVD(n_components=k, random_state=seed)
    Z = normalize(svd.fit_transform(X))
    n = len(chunk_texts)
    sim_tfidf = (normalize(X[:n]) @ normalize(X[n:]).T).toarray()
    return dict(vectorizer=vec, svd=svd, X=X, Zc=Z[:n], Zp=Z[n:], sim=sim_tfidf, explained=float(svd.explained_variance_ratio_.sum()))


def keywords(docs, k=8):
    toks = [" ".join(nouns(d)) for d in docs]
    vec = TfidfVectorizer(token_pattern=r"[^ ]+", min_df=1, max_df=0.6, sublinear_tf=True)
    X = vec.fit_transform(toks)
    terms = np.array(vec.get_feature_names_out())
    out = []
    for i in range(X.shape[0]):
        row = X[i].toarray().ravel()
        out.append([terms[j] for j in np.argsort(-row)[:k] if row[j] > 0])
    return out
