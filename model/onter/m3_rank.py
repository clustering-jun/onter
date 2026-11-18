"""모듈 3. 프로그램 순위.

세 종류의 신호를 따로 만든 뒤 섞는다.
- 근거(evidence): 비슷한 단지가 하는가(이웃), 지금 하는 것과 어울리는가(EASE), 널리 검증됐는가(채택률) — 활동 기록에서 온다.
- 필요(need): 단지의 필요 프로파일·주민 구성과 프로그램의 분야·대상이 맞는가 — 기록을 쓰지 않는 지식 기반 점수다.
- 보정(calibration): 추천 목록의 분야 구성이 단지의 목표 분포(Q)를 닮도록 다시 고른다(Steck 2018 방식).

모든 점수 함수는 단지×프로그램 DataFrame을 돌려주고, 학습 구간의 행렬만 입력으로 받는다.
"""
import numpy as np
import pandas as pd
from . import config as C, data as D, features as F, m1_profile as M1


def _df(a, like):
    return pd.DataFrame(np.asarray(a, float), index=like.index, columns=like.columns)


def _active(X):
    return (X.sum(axis=1) > 0).to_numpy()


# ───────── 기준선 ─────────
def random_scores(X, seed=C.SEED):
    return _df(np.random.default_rng(seed).random(X.shape), X)


def pop(X):
    """전체 채택률(기록 있는 단지 중 이 프로그램을 운영한 비율)."""
    a = _active(X)
    return _df(np.tile(X[a].mean(axis=0).to_numpy(), (len(X), 1)), X)


def group_pop(X, groups, shrink=10.0):
    """집단(지사·유형 등) 안 채택률. 자기 단지는 빼고, 작은 집단은 전체 채택률 쪽으로 당긴다."""
    a = _active(X)
    g = pd.Series(groups).reindex(X.index)
    p0 = X[a].mean(axis=0).to_numpy()
    out = np.zeros(X.shape)
    Xa = X.to_numpy() * a[:, None]
    for _, idx in g.groupby(g).groups.items():
        pos = X.index.get_indexer(idx)
        s, n = Xa[pos].sum(0), a[pos].sum()
        for i in pos:
            ni, si = n - a[i], s - Xa[i]
            out[i] = (si + shrink * p0) / (ni + shrink)
    return _df(out, X)


def inertia(Xcount, X):
    """자기 단지가 하던 것(기록 수) + 동점은 채택률. '올해도 작년처럼'의 기준선."""
    return _df(np.log1p(Xcount.to_numpy()) + 1e-3 * pop(X).to_numpy(), X)


# ───────── 협업 필터링 ─────────
def userknn(X, S, k=20, shrink=0.0):
    """이웃 단지의 가중 채택률. S는 단지 유사도 표, 이웃은 기록 있는 단지에서만 고른다."""
    a = _active(X)
    Sm = S.reindex(index=X.index, columns=X.index).to_numpy().copy()
    Sm[:, ~a] = 0
    np.fill_diagonal(Sm, 0)
    if k and k < Sm.shape[1]:
        th = -np.partition(-Sm, k - 1, axis=1)[:, k - 1][:, None]
        Sm = np.where(Sm >= th, Sm, 0)
    return _df(Sm @ X.to_numpy() / (Sm.sum(1, keepdims=True) + shrink + 1e-12), X)


def itemknn(X, k=20):
    """프로그램 동시 운영(코사인) 기반: 지금 하는 프로그램들과 함께 운영되는 프로그램."""
    A = X.to_numpy()[_active(X)]
    S = F.cosine(A.T)
    np.fill_diagonal(S, 0)
    if k and k < S.shape[0]:
        th = -np.partition(-S, k - 1, axis=1)[:, k - 1][:, None]
        S = np.where(S >= th, S, 0)
    return _df(X.to_numpy() @ S.T / (np.abs(S).sum(1)[None, :] + 1e-12), X)


def ease(X, lam=20.0):
    """EASE(Steck 2019): 프로그램 간 선형 자기부호화기의 닫힌 해. 작은 자료에서 강한 협업 기준선."""
    A = X.to_numpy()[_active(X)]
    P = np.linalg.inv(A.T @ A + lam * np.eye(A.shape[1]))
    B = -P / np.diag(P)[None, :]
    np.fill_diagonal(B, 0)
    return _df(X.to_numpy() @ B, X)


def svd(X, rank=12):
    A = X.to_numpy()
    a = _active(X)
    mu = A[a].mean(0)
    U, s, Vt = np.linalg.svd(A[a] - mu, full_matrices=False)
    V = Vt[:rank].T
    return _df((A - mu) @ V @ V.T + mu, X)


def als(Xcount, rank=12, alpha=8.0, reg=2.0, iters=12, seed=C.SEED):
    """암묵 피드백 ALS(Hu·Koren·Volinsky 2008). 신뢰도 = 1 + α·log(1+기록 수)."""
    R = Xcount.to_numpy()
    a = (R.sum(1) > 0)
    P = (R[a] > 0).astype(float)
    Cf = 1 + alpha * np.log1p(R[a])
    rng = np.random.default_rng(seed)
    n, m = P.shape
    U, V = rng.normal(0, 0.1, (n, rank)), rng.normal(0, 0.1, (m, rank))
    I = reg * np.eye(rank)
    for _ in range(iters):
        for u in range(n):
            Cu = Cf[u]
            U[u] = np.linalg.solve((V * Cu[:, None]).T @ V + I, (V * Cu[:, None]).T @ P[u])
        for i in range(m):
            Ci = Cf[:, i]
            V[i] = np.linalg.solve((U * Ci[:, None]).T @ U + I, (U * Ci[:, None]).T @ P[:, i])
    out = np.zeros(R.shape)
    out[a] = U @ V.T
    return _df(out, Xcount)


def feature_ridge(X, groups=F.STRUCT, lam=30.0, folds=5, seed=C.SEED):
    """단지 특징 → 프로그램 채택(다중 출력 릿지). 기록 없는 단지에도 점수를 줄 수 있다.

    기록 있는 단지의 점수는 교차 적합(자기 자신을 빼고 맞춘 모형의 예측)으로 낸다.
    """
    Z = F.matrix(groups, X.index).to_numpy()
    Z = np.column_stack([np.ones(len(Z)), Z])
    Y, a = X.to_numpy(), _active(X)
    fit = lambda tr: np.linalg.solve(Z[tr].T @ Z[tr] + lam * np.eye(Z.shape[1]), Z[tr].T @ Y[tr])
    out = np.zeros(Y.shape)
    idx = np.where(a)[0]
    perm = np.random.default_rng(seed).permutation(idx)
    for f in range(folds):
        te = perm[f::folds]
        out[te] = Z[te] @ fit(np.setdiff1d(idx, te))
    out[~a] = Z[~a] @ fit(idx)
    return _df(out, X)


# ───────── 지식 기반(필요·대상 적합) ─────────
def need_fit(X, M, need=None, T=None, A=None, target_weight=0.5):
    """필요 적합도 = Σ_d 필요(d)·소속(p,d), 여기에 대상 적합(주민 구성×프로그램 대상)을 곱해 조정한다. 기록을 쓰지 않는다."""
    need = M1.need_table("S") if need is None else need
    s = need.reindex(X.index)[C.NEED_IDS].to_numpy() @ M.reindex(X.columns)[C.NEED_IDS].to_numpy().T
    if T is not None and target_weight > 0:
        A = M1.target_affinity() if A is None else A
        Tm = T.reindex(X.columns)[F.TARGETS].fillna(0).to_numpy()
        tf = A.reindex(X.index)[F.TARGETS].to_numpy() @ Tm.T / np.maximum(Tm.sum(1)[None, :], 1e-9)
        tf = np.where(Tm.sum(1)[None, :] > 0, tf, 0.5)
        s = s * ((1 - target_weight) + target_weight * 2 * tf)
    return _df(s, X)


# ───────── 융합 ─────────
def row_rank(S, cand=None):
    """행(단지)별 백분위 순위. 후보가 아닌 칸은 NaN."""
    A = S.to_numpy().astype(float).copy()
    if cand is not None:
        A[~np.asarray(cand, bool)] = np.nan
    return _df(pd.DataFrame(A).rank(axis=1, pct=True).to_numpy(), S)


def fuse(scores, weights=None, cand=None, method="rank"):
    """여러 점수를 섞는다. rank: 백분위 순위의 가중 평균, rrf: 역순위 융합."""
    names = list(scores)
    w = np.array([1.0 if weights is None else weights.get(n, 0.0) for n in names])
    like = scores[names[0]]
    if method == "rrf":
        out = 0
        for n, wi in zip(names, w):
            A = scores[n].to_numpy().astype(float).copy()
            if cand is not None:
                A[~np.asarray(cand, bool)] = -np.inf
            r = (-A).argsort(1).argsort(1) + 1
            out = out + wi / (60 + r)
        return _df(out, like)
    out = sum(wi * row_rank(scores[n], cand).fillna(0).to_numpy() for n, wi in zip(names, w)) / max(w.sum(), 1e-12)
    return _df(out, like)


def calibrated_topk(S, cand, M, Q, k=10, lam=0.5, alpha=0.01):
    """필요 보정 재순위: 점수 합과 '목록의 분야 분포가 목표 분포 Q에서 벗어난 정도(KL)'를 함께 최적화하는 탐욕 선택."""
    R = row_rank(S, cand).fillna(-1).to_numpy()
    Mm, Qm, cand = M.reindex(S.columns)[C.NEED_IDS].to_numpy(), Q.reindex(S.index)[C.NEED_IDS].to_numpy(), np.asarray(cand, bool)
    top = np.zeros((len(S), k), int)
    for u in range(len(S)):
        avail = cand[u].copy()
        if avail.sum() < k:                                                # 후보가 모자라면 전체에서 채운다
            avail = np.ones_like(avail)
        acc, q = np.zeros(Mm.shape[1]), np.maximum(Qm[u], 1e-9)
        for t in range(k):
            p = (acc[None, :] + Mm) / (t + 1)
            p = (1 - alpha) * p + alpha * q
            kl = (q * np.log(q / p)).sum(1)
            obj = (1 - lam) * R[u] - lam * kl
            obj[~avail] = -np.inf
            j = int(obj.argmax())
            top[u, t], avail[j] = j, False
            acc += Mm[j]
    return top


# ───────── 온터 기본 순위기 ─────────
# w_need, lam은 검증 분할 A에서 고른 값이다(experiments/exp_ranking.py의 select)
DEFAULT = dict(w_need=0.2, lam=0.25, k_peer=20, sim="hybrid", evidence=("peer", "ease", "pop"), base="demand", beta=2.0)


def onter_scores(X, S, M, T, w_need=DEFAULT["w_need"], k_peer=DEFAULT["k_peer"], evidence=DEFAULT["evidence"], need=None, cand=None,
                 feas=None, w_feas=0.0, parts_out=None):
    """근거 점수와 필요 점수를 순위로 섞은 기본 점수. parts_out(dict)을 주면 성분 점수를 담아 준다(설명용)."""
    parts = {}
    if "peer" in evidence:
        parts["peer"] = userknn(X, S, k_peer)
    if "ease" in evidence:
        parts["ease"] = ease(X)
    if "pop" in evidence:
        parts["pop"] = pop(X)
    ev = fuse(parts, cand=cand)
    nf = need_fit(X, M, need=need, T=T)
    comp = {"evidence": ev, "need": nf}
    w = {"evidence": 1 - w_need, "need": w_need}
    if feas is not None and w_feas > 0:
        comp["feas"], w["feas"] = feas, w_feas
    if parts_out is not None:
        parts_out.update(parts, **comp)
    return fuse(comp, w, cand=cand)
