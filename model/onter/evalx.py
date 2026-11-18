"""평가 도구: 시간 분할, 순위 지표, 목록 지표, 통계 검정.

'새 도입 맞히기'는 예측 타당도(현장이 실제로 고를 만한가)를 보는 지표일 뿐 정답이 아니다.
필요 정렬(need alignment)과 함께 보고, 둘의 교환 관계를 따로 그린다.
"""
import numpy as np
import pandas as pd
from . import config as C, features as F


# ───────── 분할 ─────────
def fold_data(fold, min_train=8):
    """롤링 오리진 한 구간. 학습 구간 기록만으로 만든 행렬과, 평가 구간의 '새 도입' 정답을 준다."""
    tr0, tr1, te0, te1 = C.FOLDS[fold]
    train, train_cnt = F.interactions(tr0, tr1), F.interactions(tr0, tr1, "count")
    test = F.interactions(te0, te1)
    ntr, nte = F.window(tr0, tr1).groupby("complex_id").size(), F.window(te0, te1).groupby("complex_id").size()
    ids = train.index
    elig = (ntr.reindex(ids).fillna(0) >= min_train) & (nte.reindex(ids).fillna(0) >= 1)      # 평가 구간에 기록이 아예 없으면 '안 함'과 '안 적음'을 못 가른다
    new = ((test > 0) & (train == 0)).astype(float)
    return dict(fold=fold, train=train, train_cnt=train_cnt, test=test, new=new, cand_new=(train == 0), elig=elig,
                tr=(tr0, tr1), te=(te0, te1))


# ───────── 순위 지표 ─────────
def _order(S, cand, seed=0):
    S = np.asarray(S, float).copy()
    S = S + np.random.default_rng(seed).uniform(0, 1e-9, S.shape)        # 동점은 무작위로 푼다(항목 순서 편향 방지)
    S[~np.asarray(cand, bool)] = -np.inf
    return np.argsort(-S, axis=1)


def rank_metrics(S, rel, cand, ks=(5, 10), seed=0):
    """행(단지)별 Recall@k, NDCG@k, Hit@k, MRR, AUC. 정답이 하나도 없는 행은 NaN."""
    rel, cand = np.asarray(rel, float), np.asarray(cand, bool)
    rel = rel * cand
    order = _order(S, cand, seed)
    rs = np.take_along_axis(rel, order, axis=1)
    nrel, ncand = rel.sum(1), cand.sum(1)
    out = {}
    disc = 1 / np.log2(np.arange(rel.shape[1]) + 2)
    for k in ks:
        hits = rs[:, :k].sum(1)
        dcg = (rs[:, :k] * disc[:k]).sum(1)
        idcg = np.array([disc[:int(min(k, n))].sum() if n > 0 else np.nan for n in nrel])
        out[f"recall@{k}"] = np.where(nrel > 0, hits / np.maximum(nrel, 1), np.nan)
        out[f"ndcg@{k}"] = dcg / idcg
        out[f"hit@{k}"] = np.where(nrel > 0, (hits > 0).astype(float), np.nan)
    first = np.where(rs.sum(1) > 0, rs.argmax(1) + 1, np.inf)
    out["mrr"] = np.where(nrel > 0, 1 / first, np.nan)
    pos = np.arange(1, rel.shape[1] + 1)[None, :]
    sum_rank = (rs * pos).sum(1)                                           # 정답들의 순위 합 → AUC
    nneg = ncand - nrel
    auc = 1 - (sum_rank - nrel * (nrel + 1) / 2) / np.maximum(nrel * nneg, 1)
    out["auc"] = np.where((nrel > 0) & (nneg > 0), auc, np.nan)
    return pd.DataFrame(out)


def topk(S, cand, k=10, seed=0):
    return _order(S, cand, seed)[:, :k]


# ───────── 목록 지표 ─────────
def jsd(p, q, eps=1e-12):
    """젠슨-섀넌 발산(밑 2, 0~1). 행 단위."""
    p, q = np.asarray(p, float), np.asarray(q, float)
    p, q = p / np.maximum(p.sum(-1, keepdims=True), eps), q / np.maximum(q.sum(-1, keepdims=True), eps)
    m = (p + q) / 2
    kl = lambda a, b: np.where(a > 0, a * np.log2(np.maximum(a, eps) / np.maximum(b, eps)), 0).sum(-1)
    return (kl(p, m) + kl(q, m)) / 2


def list_metrics(top, M, Q, pop):
    """추천 목록의 성질. M: 프로그램×분야 소속, Q: 단지×분야 목표 분포, pop: 프로그램 채택률."""
    M, Q, pop = np.asarray(M, float), np.asarray(Q, float), np.asarray(pop, float)
    dist = M[top].mean(1)                                                  # 목록의 분야 분포
    pr = pd.Series(pop).rank(pct=True).to_numpy()
    ent = -(np.where(dist > 0, dist * np.log2(np.maximum(dist, 1e-12)), 0)).sum(1) / np.log2(M.shape[1])
    return pd.DataFrame({"need_align": 1 - jsd(dist, Q), "domain_entropy": ent, "pop_pct": pr[top].mean(1),
                         "longtail": (pr[top] < 0.5).mean(1)})


def catalog_stats(top, n_items):
    cnt = np.bincount(top.ravel(), minlength=n_items).astype(float)
    x = np.sort(cnt)
    n = len(x)
    gini = (2 * (np.arange(1, n + 1) * x).sum() / (n * x.sum()) - (n + 1) / n) if x.sum() > 0 else np.nan
    return {"coverage": float((cnt > 0).mean()), "gini": float(gini)}


# ───────── 통계 ─────────
def boot_mean(x, B=2000, seed=C.SEED):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    bs = x[rng.integers(0, len(x), (B, len(x)))].mean(1)
    return float(x.mean()), float(np.quantile(bs, 0.025)), float(np.quantile(bs, 0.975))


def paired_boot(a, b, B=4000, seed=C.SEED):
    """같은 단지에서 잰 두 방법의 평균 차(a−b), 95% 구간, 양측 p."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = ~np.isnan(a) & ~np.isnan(b)
    d = a[ok] - b[ok]
    if len(d) == 0:
        return dict(diff=np.nan, lo=np.nan, hi=np.nan, p=np.nan, n=0)
    rng = np.random.default_rng(seed)
    bs = d[rng.integers(0, len(d), (B, len(d)))].mean(1)
    p = 2 * min((bs <= 0).mean(), (bs >= 0).mean())
    return dict(diff=float(d.mean()), lo=float(np.quantile(bs, 0.025)), hi=float(np.quantile(bs, 0.975)), p=float(min(1, max(p, 1 / B))), n=int(len(d)))


def holm(p):
    p = np.asarray(p, float)
    order = np.argsort(p)
    adj = np.empty(len(p))
    run = 0
    for i, j in enumerate(order):
        run = max(run, (len(p) - i) * p[j])
        adj[j] = min(1, run)
    return adj


def spearman_ci(x, y, B=2000, seed=C.SEED):
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(d) < 8:
        return dict(rho=np.nan, lo=np.nan, hi=np.nan, n=len(d), p=np.nan)
    rx, ry = d["x"].rank().to_numpy(), d["y"].rank().to_numpy()
    rho = np.corrcoef(rx, ry)[0, 1]
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), (B, len(d)))
    bs = np.array([np.corrcoef(pd.Series(d["x"].to_numpy()[i]).rank(), pd.Series(d["y"].to_numpy()[i]).rank())[0, 1] for i in idx[:500]])
    perm = np.array([np.corrcoef(rx, rng.permutation(ry))[0, 1] for _ in range(B)])
    return dict(rho=float(rho), lo=float(np.nanquantile(bs, 0.025)), hi=float(np.nanquantile(bs, 0.975)), n=int(len(d)),
                p=float(max((np.abs(perm) >= abs(rho)).mean(), 1 / B)))


def partial_spearman(x, y, Z):
    """Z를 통제한 순위 편상관(순위 변환 후 잔차 상관)."""
    d = pd.concat([pd.Series(x, name="x"), pd.Series(y, name="y"), pd.DataFrame(Z)], axis=1).dropna()
    if len(d) < 12:
        return np.nan, len(d)
    R = d.rank().to_numpy()
    Zr = np.column_stack([np.ones(len(d)), R[:, 2:]])
    res = lambda v: v - Zr @ np.linalg.lstsq(Zr, v, rcond=None)[0]
    return float(np.corrcoef(res(R[:, 0]), res(R[:, 1]))[0, 1]), len(d)
