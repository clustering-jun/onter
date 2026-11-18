# -*- coding: utf-8 -*-
"""단지 유형화: 프로그램 구성·운영 패턴·협력 구조의 표준화 변수로 군집화하고 안정성을 검증한다.
유형은 기술적 분류이며 단지의 필요·성과 순위가 아니다. 기록 15건 미만 단지는 '자료 부족'으로 분리한다."""
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.metrics import silhouette_score, silhouette_samples, adjusted_rand_score
from sklearn.preprocessing import StandardScaler

PUR_SHORT = {"P01": "건강증진", "P02": "정신건강", "P03": "돌봄·안부", "P04": "식생활·생필품", "P05": "경제·금융", "P06": "일자리",
             "P07": "교육", "P08": "문화·여가·체육", "P09": "이웃·공동체", "P10": "주거환경", "P11": "안전", "P12": "환경·에너지",
             "P13": "갈등·질서"}
FEATS = ([f"share_purpose_P{i:02d}" for i in range(1, 14)] +
         ["ops_evt_Y_share", "ops_reg_YP_share", "ops_sea_Y_share", "single_day_share", "std_evenness", "std_top1_share",
          "share_mou", "share_part_flag_welfare_org", "share_part_flag_local_gov", "share_burden_ext"])
LOG_FEATS = ["resident_records_per_1000hh_year", "participation_per_100hh_year"]
LABEL = {
    "ops_evt_Y_share": "행사형 비중", "ops_reg_YP_share": "정기 운영 비중", "ops_sea_Y_share": "계절·명절 연동", "single_day_share": "일회성 기록",
    "std_evenness": "프로그램 고른 분포", "std_top1_share": "특정 프로그램 쏠림", "share_mou": "업무협약 연계", "share_part_flag_welfare_org": "복지시설 참여",
    "share_part_flag_local_gov": "지자체 참여", "share_burden_ext": "외부 제공 비중",
    "resident_records_per_1000hh_year": "활동량(세대당)", "participation_per_100hh_year": "참여 규모(세대당)",
}
for k, v in PUR_SHORT.items():
    LABEL[f"share_purpose_{k}"] = v + " 중심"


def _matrix(cf, mask):
    X = cf.loc[mask, FEATS].fillna(0).copy()
    for c in LOG_FEATS:
        X[c] = np.log1p(cf.loc[mask, c].fillna(0))
    return X


def assign_types(cf, k_range=range(3, 10), min_records=15, seed=7, min_cluster_share=0.06):
    cf = cf.copy()
    mask = (cf["n_records_resident"] >= min_records)
    X = _matrix(cf, mask)
    Z = StandardScaler().fit_transform(X.values)
    pca = PCA(n_components=Z.shape[1], random_state=seed).fit(Z)
    var = np.cumsum(pca.explained_variance_ratio_)
    ncomp = int(min(np.searchsorted(var, 0.80) + 1, Z.shape[1]))
    P = PCA(n_components=ncomp, random_state=seed).fit_transform(Z)
    cand = []
    models = {}
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=30, random_state=seed).fit(P)
        models[k] = km
        sil = silhouette_score(P, km.labels_)
        sizes = np.bincount(km.labels_) / len(P)
        # 안정성: 80% 부분표본 군집과 전체 군집의 ARI 중앙값
        rng = np.random.RandomState(seed)
        aris = []
        for _ in range(30):
            idx = rng.choice(len(P), size=int(0.8 * len(P)), replace=False)
            kb = KMeans(n_clusters=k, n_init=5, random_state=int(rng.randint(1e6))).fit(P[idx])
            aris.append(adjusted_rand_score(km.labels_[idx], kb.labels_))
        cand.append(dict(k=k, silhouette=round(float(sil), 4), ari_median=round(float(np.median(aris)), 4),
                         min_cluster_share=round(float(sizes.min()), 4), inertia=round(float(km.inertia_), 1)))
    cand = pd.DataFrame(cand)
    # 선택 규칙: 부분표본 안정성(ARI≥0.5)과 최소 군집 비중(≥8%)을 모두 만족하는 후보 중 가장 세분된 k.
    # 해당 후보가 없으면 ARI·실루엣 순. 실루엣이 낮으면(<0.15) '연속체에 가까운 기술적 유형'임을 보고서에 명시한다.
    ok = cand[(cand["min_cluster_share"] >= max(min_cluster_share, 0.08)) & (cand["ari_median"] >= 0.5)]
    if len(ok):
        pick = ok.sort_values(["k"], ascending=False).iloc[0]
    else:
        ok2 = cand[cand["min_cluster_share"] >= min_cluster_share]
        pick = (ok2 if len(ok2) else cand).sort_values(["ari_median", "silhouette"], ascending=False).iloc[0]
    k = int(pick["k"])
    km = models[k]                      # 선택에 쓴 모형을 그대로 사용(재적합으로 군집 구성이 달라지지 않게)
    lab = km.labels_
    sil_s = silhouette_samples(P, lab)
    dist = np.linalg.norm(P - km.cluster_centers_[lab], axis=1)
    # 이름: 군집 평균 z점수 상위 변수
    zdf = pd.DataFrame(Z, columns=FEATS + LOG_FEATS, index=X.index)
    prof = zdf.groupby(lab).mean()
    names, tops = {}, {}
    for c in range(k):
        s = prof.loc[c].sort_values(ascending=False)
        top = [(f, v) for f, v in s.items() if v > 0.35][:3]
        tops[c] = " / ".join(f"{LABEL.get(f, f)}({v:+.2f})" for f, v in top) if top else "뚜렷한 특징 없음"
        names[c] = None
    cf["complex_type_id"] = "T0"
    cf["complex_type_silhouette"] = np.nan
    cf["complex_type_dist"] = np.nan
    cf.loc[mask, "complex_type_id"] = ["T%d" % (c + 1) for c in lab]
    cf.loc[mask, "complex_type_silhouette"] = np.round(sil_s, 3)
    cf.loc[mask, "complex_type_dist"] = np.round(dist, 3)
    prof_full = X.copy()
    prof_full["cluster"] = ["T%d" % (c + 1) for c in lab]
    means = prof_full.groupby("cluster").mean().round(4)
    means["n_complexes"] = prof_full.groupby("cluster").size()
    means["top_features"] = [tops[int(i[1:]) - 1] for i in means.index]
    info = dict(k=k, ncomp=ncomp, var_explained=round(float(var[ncomp - 1]), 3), candidates=cand, profile=means, silhouette_mean=round(float(sil_s.mean()), 4),
                pick=pick.to_dict())
    return cf, info
