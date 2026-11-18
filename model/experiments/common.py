"""실험 공통: 한 분할(fold)에서 쓰는 점수·지표 계산을 한곳에 모은다."""
import sys, json, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from onter import config as C, data as D, features as F, m1_profile as M1, m2_cases as M2, m3_rank as R, m4_feasibility as M4, evalx as E

sys.stdout.reconfigure(encoding="utf-8")
K = 10


def save(df, name):
    df.to_csv(C.TABLES / f"{name}.csv", index=False, encoding="utf-8-sig")
    return df


def put_summary(key, value):
    p = C.RESULTS / "summary.json"
    s = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    s[key] = value
    p.write_text(json.dumps(s, ensure_ascii=False, indent=1, default=float), encoding="utf-8")


class Fold:
    """한 분할의 학습 행렬·정답·보조 표. 점수는 필요할 때 만들어 캐시한다."""

    def __init__(self, name):
        fd = E.fold_data(name)
        self.name, self.fd = name, fd
        self.X, self.Xc = fd["train"], fd["train_cnt"]
        self.el = fd["elig"].to_numpy()
        self.new, self.cand = fd["new"].to_numpy(), fd["cand_new"].to_numpy()
        self.tr = fd["tr"]
        self.M, self.T = F.need_membership(*self.tr), F.target_membership(*self.tr)
        self.Q = M1.target_distribution(start=self.tr[0], end=self.tr[1])            # 기준 목표 분포(해피콜 기준 + 구조 필요 기울기)
        self.popv = self.X[self.el].mean(0).to_numpy()
        self.c = D.complexes()
        self._sim, self._sc = {}, {}
        self.NF = R.need_fit(self.X, self.M, T=self.T)
        self.NFr = R.row_rank(self.NF, self.cand).to_numpy()

    def sim(self, kind, **kw):
        key = (kind, tuple(sorted(kw.get("weights", {}).items())))
        if key not in self._sim:
            self._sim[key] = M2.sim_matrix(kind, *self.tr, **kw)
        return self._sim[key]

    def score(self, name):
        if name in self._sc:
            return self._sc[name]
        X, Xc, c = self.X, self.Xc, self.c
        if name == "random":
            s = R.random_scores(X)
        elif name == "pop":
            s = R.pop(X)
        elif name == "pop_recent":
            s = R.pop(F.interactions(str(pd.Period(self.tr[1], "M") - 11), self.tr[1]))
        elif name == "diffusion":                              # 최근 6개월에 처음 도입한 단지 비율(확산 속도)
            cut = str(pd.Period(self.tr[1], "M") - 5)
            before = F.interactions(self.tr[0], str(pd.Period(cut, "M") - 1))
            first = ((F.interactions(cut, self.tr[1]) > 0) & (before == 0)).sum(0) / np.maximum((before == 0).sum(0), 1)
            s = pd.DataFrame(np.tile(first.to_numpy(), (len(X), 1)), index=X.index, columns=X.columns)
        elif name == "branch_pop":
            s = R.group_pop(X, c["branch"])
        elif name == "type_pop":
            s = R.group_pop(X, M1.typology(k=3)[0])
        elif name == "inertia":
            s = R.inertia(Xc, X)
        elif name.startswith("knn_"):
            s = R.userknn(X, self.sim(name[4:]))
        elif name == "itemknn":
            s = R.itemknn(X)
        elif name == "ease":
            s = R.ease(X)
        elif name == "svd":
            s = R.svd(X)
        elif name == "als":
            s = R.als(Xc)
        elif name == "ridge":
            s = R.feature_ridge(X)
        elif name == "need_fit":
            s = self.NF
        elif name == "evidence":                               # 근거 융합(이웃 + EASE + 채택률)
            s = R.fuse({k: self.score(k) for k in ("knn_hybrid", "ease", "pop")}, cand=self.cand)
        elif name == "evidence+":                              # 지사 채택률·확산 속도까지 넣은 근거
            s = R.fuse({k: self.score(k) for k in ("knn_hybrid", "ease", "pop", "branch_pop", "diffusion")}, cand=self.cand)
        else:
            raise KeyError(name)
        self._sc[name] = s
        return s

    # 지표
    def rank(self, S):
        return E.rank_metrics(np.asarray(S)[self.el], self.new[self.el], self.cand[self.el])

    def lists(self, top):
        """top: 전체 단지×K 색인. 자격 단지만 잘라 목록 지표를 낸다."""
        t = top[self.el]
        lm = E.list_metrics(t, self.M.to_numpy(), self.Q.to_numpy()[self.el], self.popv)
        lm["need_gain"] = np.take_along_axis(np.nan_to_num(self.NFr[self.el], nan=0.0), t, axis=1).mean(1)
        rel = np.take_along_axis(self.new[self.el], t, axis=1)
        nrel = self.new[self.el].sum(1)
        disc = 1 / np.log2(np.arange(t.shape[1]) + 2)
        idcg = np.array([disc[:int(min(t.shape[1], n))].sum() if n > 0 else np.nan for n in nrel])
        lm["ndcg"] = (rel * disc).sum(1) / idcg
        lm["recall"] = np.where(nrel > 0, rel.sum(1) / np.maximum(nrel, 1), np.nan)
        return lm

    def top(self, S, k=K):
        return E.topk(np.asarray(S), self.cand, k)

    def row(self, label, top, **extra):
        lm = self.lists(top)
        cs = E.catalog_stats(top[self.el], self.X.shape[1])
        return dict(fold=self.name, model=label, **extra, ndcg10=lm["ndcg"].mean(), recall10=lm["recall"].mean(), need_align=lm["need_align"].mean(),
                    need_gain=lm["need_gain"].mean(), pop_pct=lm["pop_pct"].mean(), longtail=lm["longtail"].mean(), coverage=cs["coverage"],
                    gini=cs["gini"], demand_align=demand_align(top[self.el], self.X.columns)), lm


_DEM = None


def demand_dist():
    """해피콜 주거생활지원 이용자(공단 관리 단지 응답 100명)의 8개 항목 분포."""
    global _DEM
    if _DEM is None:
        h = D.happycall_demand()
        h = h[(h["population"] == "residential_life_support_service_users") & (h["group"] == "관리소 소속") & (h["subgroup"] == "주택관리공단")]
        s = h.set_index("metric")["value"].reindex(list(C.DEMAND_PURPOSE)).fillna(0)
        _DEM = s / s.sum()
    return _DEM


def purpose_category():
    inv = {p: k for k, ps in C.DEMAND_PURPOSE.items() for p in ps}
    return D.programs()["purpose"].map(inv)


def demand_align(top, items, weights=None):
    """추천(또는 공급)의 수요 항목 분포가 해피콜 수요 분포와 닮은 정도(1−JSD). 전국 합계 수준의 지표다."""
    cat = purpose_category().reindex(items).to_numpy()
    if weights is None:
        picked = pd.Series(cat[np.asarray(top).ravel()]).dropna().value_counts()
    else:
        picked = pd.Series(np.asarray(weights, float), index=cat).groupby(level=0).sum()
        picked = picked[picked.index.notna()]
    d = demand_dist()
    return float(1 - E.jsd(picked.reindex(d.index).fillna(0).to_numpy(), d.to_numpy()))
