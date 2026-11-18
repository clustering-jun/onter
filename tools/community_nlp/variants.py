# -*- coding: utf-8 -*-
"""표준 유형 내부의 명칭 변이 묶음(별칭 군집) — 연·월·차수·단지명을 뺀 제목이 비슷한 활동을 하나의 대표 명칭으로 정리.
군집은 '같은 표준 유형 안에서만' 만든다. 유사도 하나로 서로 다른 유형을 합치지 않는다(v5)."""
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import AgglomerativeClustering


def build_alias_clusters(rows, threshold=0.5, min_title_len=2):
    cnames = sorted({c for c in rows["complex_name"].unique() if len(c) >= 3}, key=lambda c: (-len(c), c))   # 길이가 같으면 이름순(실행마다 같은 결과)
    """rows: std_id, title_norm, program_name_masked 포함. 반환: rows에 alias_cluster_id, canonical_title 추가한 Series 2개."""
    cluster_id = pd.Series("", index=rows.index, dtype=object)
    canon = pd.Series("", index=rows.index, dtype=object)
    for sid, sub in rows.groupby("std_id"):
        titles = sub["title_norm"].value_counts()
        uniq = titles.index.tolist()
        if len(uniq) == 1:
            lab = {uniq[0]: 0}
        else:
            vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), min_df=1, sublinear_tf=True)
            X = vec.fit_transform([u if u else "_" for u in uniq]).toarray()
            nz = np.linalg.norm(X, axis=1) > 0
            lab = {}
            nxt = 0
            if nz.sum() >= 2:
                ac = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="average", distance_threshold=threshold).fit(X[nz])
                for u, l in zip(np.array(uniq, dtype=object)[nz], ac.labels_):
                    lab[u] = int(l)
                nxt = int(ac.labels_.max()) + 1
            elif nz.sum() == 1:
                lab[np.array(uniq, dtype=object)[nz][0]] = 0
                nxt = 1
            for u in np.array(uniq, dtype=object)[~nz]:
                lab[u] = nxt
                nxt += 1
        # 군집 대표: 군집 내 가장 많은 title_norm → 그 title_norm을 가진 원문 명칭 중 가장 흔한 마스킹 명칭
        members = {}
        for t, l in lab.items():
            members.setdefault(l, []).append(t)
        rep_title = {}
        for l, ts in members.items():
            best = max(ts, key=lambda x: titles[x])
            rep_title[l] = best
        # 대표 표시명: best title_norm에 속한 행의 마스킹 원문명 중 최빈값에서 연·월·차수 표기를 제거한 형태
        disp = {}
        for l, best in rep_title.items():
            names = sub.loc[sub["title_norm"] == best, "program_name_masked"]
            disp[l] = _clean_display(names.value_counts().index[0], cnames)
        for idx, t in zip(sub.index, sub["title_norm"]):
            l = lab[t]
            cluster_id[idx] = f"{sid}-{l:03d}"
            canon[idx] = disp[l]
    return cluster_id, canon


import re
_YEAR = re.compile(r"(20)?\d{2}\s*년도?|`\d{2}|’\d{2}")
_MONTH = re.compile(r"\d{1,2}\s*월|\d{1,2}\s*[~\-]\s*\d{1,2}\s*월")
_ORD = re.compile(r"(제\s*)?\d+\s*(차시|차수|차|회차|회|기수)")
_HALF = re.compile(r"(상|하)반기|[1-4]\s*분기")
_TAIL = re.compile(r"\s*(실시|시행|진행|개최|보고|결과|운영)\s*$")


def _clean_display(s, cnames=()):
    s = str(s)
    for c in cnames:
        if c in s:
            s = s.replace(c, " ")
        base = re.sub(r"\d+$", "", c)
        if len(base) >= 3 and base in s:
            s = s.replace(base, " ")
    s = _YEAR.sub("", s)
    s = _MONTH.sub("", s)
    s = _ORD.sub("", s)
    s = _HALF.sub("", s)
    s = re.sub(r"[\[\]\(\)「」『』“”\"']+", " ", s)
    prev = None
    while prev != s:
        prev = s
        s = _TAIL.sub("", s.strip())
    s = re.sub(r"\s+", " ", s).strip(" _-·,")
    return s or str(s)
