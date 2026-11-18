"""실험 표를 읽어 그림 2장과 docs/02_experiments.md를 만든다. 해석 문장은 아래에 고정해 두고, 표는 결과 파일에서 그대로 옮긴다.

python experiments/make_report.py
"""
from common import *
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
T = lambda n: pd.read_csv(C.TABLES / f"{n}.csv")
INK, MUTED, BLUE, RED, GRAY = "#1b1f27", "#5a6272", "#2a78d6", "#e34948", "#9aa3b2"


def md(df, cols=None, n=None):
    d = df if cols is None else df[cols]
    d = d.head(n) if n else d
    f = lambda v: "" if (isinstance(v, float) and np.isnan(v)) else (f"{v:.3f}" if isinstance(v, float) else str(v))
    return "\n".join(["| " + " | ".join(d.columns) + " |", "|" + "---|" * len(d.columns)] + ["| " + " | ".join(f(v) for v in r) + " |" for r in d.itertuples(index=False)])


def figures():
    r = T("e3_ranking_models")
    b = r[r.fold == C.MAIN_FOLD].set_index("model")
    keep = ["random", "need_fit", "itemknn", "als", "ease", "ridge", "knn_struct", "pop", "knn_hybrid", "branch_pop", "evidence", "evidence+", "onter"]
    names = {"random": "무작위", "need_fit": "필요 적합만", "itemknn": "프로그램 kNN", "als": "ALS", "ease": "EASE", "ridge": "특징 릿지", "knn_struct": "이웃(구조)",
             "pop": "채택률", "knn_hybrid": "이웃(혼합)", "branch_pop": "지사 채택률", "evidence": "근거 융합", "evidence+": "근거 융합+", "onter": "온터(기본)"}
    fig, ax = plt.subplots(1, 2, figsize=(11.5, 4.6), dpi=140)
    for a, met, title in [(ax[0], "ndcg10", "새 도입 맞히기 (NDCG@10)"), (ax[1], "need_gain", "추천 목록의 필요 적합 (0~1)")]:
        v = b.loc[keep, met]
        a.barh([names[k] for k in keep], v, color=[RED if k == "onter" else (BLUE if k in ("pop", "evidence") else GRAY) for k in keep], height=0.62)
        for i, x in enumerate(v):
            a.text(x + 0.005, i, f"{x:.2f}", va="center", fontsize=8.5, color=INK)
        a.set_title(title, fontsize=11, loc="left", color=INK)
        a.spines[["top", "right"]].set_visible(False)
        a.tick_params(labelsize=9)
    fig.suptitle(f"채택률을 뚜렷이 넘는 개인화 모델은 없고, 필요 적합만으로는 무작위와 같다 (평가 구간 {C.FOLDS[C.MAIN_FOLD][2]}~{C.FOLDS[C.MAIN_FOLD][3]})", fontsize=12, x=0.01, ha="left", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(C.FIGS / "f1_model_comparison.png")
    plt.close(fig)
    t = T("e4_tradeoff")
    fig, ax = plt.subplots(1, 2, figsize=(11.5, 4.6), dpi=140)
    col = {"fusion": BLUE, "two_stage": "#1baf7a", "calib": "#eda100", "two_stage+calib": GRAY}
    lab = {"fusion": "점수 융합(필요 가중 w)", "two_stage": "2단계(후보 n개 → 필요 순)", "calib": "필요 보정(λ)", "two_stage+calib": "2단계+보정"}
    for a, y, yl in [(ax[0], "need_gain", "필요 적합"), (ax[1], "need_align", "필요 정렬(목표 분포와 닮음)")]:
        for m, g in t.groupby("model"):
            g = g.sort_values("recall10")
            a.plot(g["recall10"], g[y], "o-" if m != "two_stage+calib" else "o", color=col[m], label=lab[m], ms=4, lw=1.5)
        o = b.loc["onter"]
        a.scatter([o["recall10"]], [o[y]], s=120, facecolors="none", edgecolors=RED, linewidths=2, zorder=5, label="온터 기본값")
        a.set_xlabel("새 도입 재현율@10", fontsize=9.5)
        a.set_ylabel(yl, fontsize=9.5)
        a.spines[["top", "right"]].set_visible(False)
        a.grid(alpha=0.25)
    ax[0].legend(fontsize=8.5, frameon=False)
    fig.suptitle("예측을 조금 내주면 필요 쪽을 크게 얻는다: 조절 손잡이별 교환 곡선", fontsize=12, x=0.01, ha="left", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(C.FIGS / "f2_tradeoff.png")
    plt.close(fig)


def report():
    s = json.loads((C.RESULTS / "summary.json").read_text(encoding="utf-8"))
    r = T("e3_ranking_models")
    piv = r.pivot_table(index="model", columns="fold", values="ndcg10").round(3).reset_index()
    order = ["random", "pop", "pop_recent", "diffusion", "branch_pop", "type_pop", "knn_demo", "knn_struct", "knn_need", "knn_behav", "knn_geo", "knn_branch", "knn_hybrid",
             "itemknn", "ease", "svd", "als", "ridge", "need_fit", "evidence", "evidence+", "ltr_gbdt", "ltr_gbdt(-need_fit)", "onter"]
    piv = piv.set_index("model").reindex(order).reset_index()
    b = r[r.fold == C.MAIN_FOLD].set_index("model").reindex([m for m in order if not m.startswith("ltr")]).reset_index()
    tests = T("e3_tests_vs_pop")
    tn = tests[tests.metric == "ndcg"][["model", "diff", "lo", "hi", "p", "p_holm"]]
    L = []
    A = L.append
    A("# 실험 보고서: 비교 실험과 절제 실험\n")
    A("자동 생성: `python experiments/make_report.py`. 표의 숫자는 `results/tables/*.csv`에서 그대로 옮겼다. 해석은 2026-11-18 실행 결과 기준이다.\n")
    A("## 0. 평가 설계\n")
    A("- **분할**: 롤링 오리진 3개. A(학습 2024 → 평가 2025), B(학습 2024-01~2025-06 → 평가 2025-07~2026-06, 주 분할), C(학습 2024~2025 → 평가 2026 상반기, 보고 지연 위험).")
    A("- **대상**: 추천 대상 표준 프로그램 96종. 평가 단지는 학습 구간 기록 8건 이상이고 평가 구간에 기록이 있는 단지.")
    A("- **새 도입 맞히기**: 학습 구간에 한 번도 안 한 프로그램 가운데 평가 구간에 새로 한 것을 상위 10개 안에 얼마나 넣는가(NDCG@10, 재현율@10, AUC). 예측 타당도 지표이고 정답이 아니다.")
    A("- **필요 쪽 지표**: 필요 적합(need_gain, 목록에 든 프로그램의 필요 적합 백분위 평균), 필요 정렬(need_align, 목록의 분야 분포와 단지 목표 분포의 1−JSD). 설계 목표를 재는 지표라서 필요를 쓰는 방법에 유리하다. 그래서 외부 기준(해피콜 수요, 전문가 판정)을 따로 둔다.")
    A("- **수요 정렬**(demand_align): 추천 목록을 전국으로 합친 수요 항목 분포와 해피콜 수요 분포의 1−JSD.")
    A("- **검정**: 단지 단위 짝지은 부트스트랩(4,000회), 여러 모델 비교는 Holm 보정.\n")
    A("## 1. E3 순위 모델 비교\n")
    A("![모델 비교](../results/figures/f1_model_comparison.png)\n")
    A(f"### 주 분할 {C.MAIN_FOLD}\n")
    A(md(b, ["model", "ndcg10", "recall10", "auc", "need_align", "need_gain", "demand_align", "pop_pct", "coverage", "n"]))
    A("\n### 분할별 NDCG@10\n")
    A(md(piv))
    A("\n### 채택률 기준선 대비 차이(주 분할, NDCG@10)\n")
    A(md(tn))
    A("\n**읽는 법**\n")
    A("1. **채택률(pop)이 매우 강하다.** 이웃·EASE·행렬분해·특징 릿지 어느 것도 Holm 보정 후 채택률을 넘지 못했다. 지사 채택률과 확산 속도까지 섞은 `evidence+`만 +0.019로 유의했다. 새 도입은 '그 단지다움'보다 '전국에서 얼마나 퍼졌나'로 설명된다.")
    A("2. **필요 적합만 쓰면 무작위와 같다**(NDCG 0.111 대 0.113, AUC 0.51). 단지의 구조적 필요는 실제 도입을 예측하지 못한다. 문제 정의('프로그램이 필요를 따라가지 않는다')를 추천 모델의 눈으로 다시 확인한 결과다.")
    A("3. **행동 지도학습(GBDT 순위 학습)도 채택률 수준이다**(분할 C). 필요 적합 특징을 빼도 넣어도 차이가 작다. 도입 기록을 정답으로 학습하면 현상 유지를 복제할 뿐이다.")
    A("4. 그래서 온터는 도입 예측을 목표로 삼지 않는다. 근거 점수는 '현장이 실제로 고를 만한 범위'를 지키는 데 쓰고, 그 안에서 필요 쪽으로 기울인다.\n")
    A("### 분야별 순위 품질(분야 안 새 도입 NDCG@3)\n")
    A(md(T("e3_per_domain").pivot_table(index=["domain", "label"], columns="model", values="ndcg3").round(3).reset_index()))
    A("\n### 기록 없는 단지 모의(학습 이력을 가린 단지의 평가 구간 운영 맞히기)\n")
    A(md(T("e3_cold_start")))
    A("\n기록이 없어도 지사·거리 이웃의 채택률로 채택률 기준선보다 조금 낫게 시작할 수 있다(구간이 겹쳐 차이는 작다). 기록 없는 12개 단지에는 구조+거리 이웃을 쓴다.\n")
    A("### 집단별 성능(온터 기본값 대 채택률)\n")
    A(md(T("e3_fairness")))
    A("\n작은 단지·주거복지사 미배치 단지에서 성능이 더 나쁘지 않다. 원격 유형(S3, 24곳)은 두 방법 모두 낮다.\n")
    A("## 2. E4 교환 관계와 절제\n")
    A("![교환 곡선](../results/figures/f2_tradeoff.png)\n")
    d = s["onter_default"]
    A(f"**기본값 고르기**: 검증 분할 A에서 '새 도입 재현율이 근거 모델의 90% 이상이고 필요 정렬 0.95 이상'인 구성 중 필요 적합이 가장 큰 것 → 필요 가중 w={d['w_need']}, 보정 λ={d['lam']}. 주 분할 B에서 재현율 0.389(근거 0.412의 95%), 필요 적합 0.68(근거 0.52), 필요 정렬 0.946(근거 0.904).\n")
    A(md(T("e4_tradeoff"), ["model", "knob", "ndcg10", "recall10", "need_align", "need_gain", "demand_align", "coverage"]))
    A("\n### 절제(주 분할, 기본값에서 하나씩 바꿈. d_는 기본값 대비 차이)\n")
    A(md(T("e4_ablation"), ["model", "ndcg10", "recall10", "need_align", "need_gain", "demand_align", "coverage", "d_ndcg", "p_ndcg", "d_align", "p_align"]))
    A("\n**읽는 법**\n")
    A("1. 필요 점수를 빼면 필요 적합이 0.68 → 0.54로 떨어지고, 보정을 빼면 필요 정렬이 0.946 → 0.931로 떨어진다. 두 장치는 서로 다른 일을 한다(점수는 '맞는 프로그램', 보정은 '분야 구성').")
    A("2. 근거 성분(이웃·EASE·채택률)을 하나씩 빼도, 이웃 정의나 이웃 수를 바꿔도 유의한 차이가 없다. 근거 쪽은 무엇을 쓰든 비슷하므로 설명하기 쉬운 '비슷한 단지 몇 곳이 운영'을 남긴다.")
    A("3. 목표 분포의 기준(해피콜·현 공급·균등)과 기울기 β는 도입 예측에 거의 영향이 없다. 해피콜 연령 보정 합성 추정은 전국 분포와 사실상 같다(단지 간 표준편차 0.1~0.5%p).")
    A("4. 필요 지수에 이용 실적(홈닥터)을 넣어도 나아지지 않는다.\n")
    A("## 3. E1 필요 지수\n")
    A(f"- 여섯 분야 필요 백분위의 주성분 비중: {s['need_pca_share']}. 첫 축이 69%다. N1~N4는 '고령·영구임대' 한 축으로 함께 움직이고 N6은 그 반대다. 지금 자료로는 분야를 여섯 개로 따로 가를 힘이 약하다(단지별 1인 가구·수급·장애 자료가 없기 때문).")
    A(f"- 필요 상위 1/3이면서 공급 하위 1/3인 '우선 검토' 분야가 하나 이상인 단지: {s['priority']['complexes_any']}곳 / {s['priority']['n']}곳.\n")
    A("### 가중치·지표를 흔들었을 때의 안정성\n")
    A(md(T("e1_need_stability")))
    A("\n### 필요(구조) ↔ 공급 순위상관\n")
    A(md(T("e1_need_vs_supply")))
    A("\n### 수렴 타당도(지수에 넣지 않은 자료와의 관계)\n")
    A(md(T("e1_need_convergent")))
    A("\n**읽는 법**: 구조 필요 지수는 홈닥터 이용 실적과 같은 방향으로 움직이지 않는다(약한 음의 상관). 홈닥터 100세대당 건수가 작은 단지에서 크게 나오는 자료 특성과 공급 의존성 때문으로 보이며, 이용 실적으로는 필요 지수를 검증할 수 없다. N1은 과거 고독사 기록 유무와 ρ=+0.42(규모 통제 +0.36)로 같은 방향이다(점검 전용, 입력·발표 훅으로 쓰지 않음). **결론: 필요 지수는 외부 검증이 부족하다. 전문가 판정(시트 C·D)이 필요하다.**\n")
    A("### 단지 유형(구조 특징 군집)\n")
    A(md(T("e1_typology_k")))
    A("")
    A(md(T("e1_typology_types")))
    A("\n## 4. E2 유사 단지 정의\n")
    A(md(T("e2_similarity_predictive")))
    A("")
    A(md(T("e2_similarity_homogeneity")))
    A("\n**읽는 법**: 어떤 정의로 이웃을 골라도 새 도입 예측은 채택률과 유의하게 다르지 않다. 혼합(구조 0.5·행동 0.3·거리 0.2)이 두 분할에서 가장 높지만 차이는 구간 안이다. 대신 성질이 다르다. 구조 이웃은 주민·주거가 닮았고(구조 거리 4.2) 멀리 있다(중앙 139km). 거리 이웃은 79%가 같은 지사라 협력기관을 공유할 수 있지만 주민 구성은 무작위 수준이다. 혼합은 그 중간이다(구조 거리 5.0, 같은 지사 41%, 57km). 화면에서는 '구성이 닮은 단지'와 '가까운 단지'를 따로 보여 주는 편이 정직하다.\n")
    A("## 5. E5 실행 검토\n")
    A(md(T("e5_feasibility_validity")))
    A("\n**읽는 법**: 규칙으로 만든 실행 가능성 점수는 새 도입을 예측하지 못한다(AUC 0.48). 점수에 섞으면 오히려 나빠진다. 그래서 **순위 점수에 넣지 않고 점검표와 제약 조건으로만 쓴다.** 성분 가운데 인력(staff)만 0.52로 방향이 맞았다.\n")
    A(md(T("e5_requirement_lift")))
    dd = s["deployment_dependence"]
    A(f"\n세대 방문형 프로그램은 주거복지사 미배치 단지에서 새 도입률이 낮다(5.6% 대 9.4%). 영구임대 단지를 규모로 층화한 오즈비로 보면 {dd['n_programs']}종 가운데 {dd['n_or_gt1_sig']}종이 배치 단지에서 유의하게 더 많이 운영되고, 덜 운영되는 것은 {dd['n_or_lt1_sig']}종이다(중앙 오즈비 {dd['median_or']:.1f}). 이 {dd['n_or_gt1_sig']}종을 '주거복지사 의존 프로그램'으로 표시한다. 협력기관 여건과 경로당 유무는 뚜렷한 차이를 만들지 못했다.\n")
    A(md(T("e5_deployment_dependence"), ["std_id", "name", "adopt_deployed", "adopt_not", "mh_or", "lo", "hi"], 10))
    A("\n### 제약 묶음 선택: 탐욕 대 정수계획\n")
    A(md(T("e5_portfolio")))
    A("\n탐욕 선택은 최적값의 63~90%에 그치고 예산이 빠듯하면 제약을 어긴다(100만 원에서 52%만 충족). 정수계획은 단지당 0.005초 안팎이라 그대로 쓴다.\n")
    A("## 6. E6 해피콜을 유사 정답으로\n")
    A(md(T("e6_demand_alignment")))
    A("")
    A(md(T("e6_demand_distribution")))
    A("\n**읽는 법**: 해피콜을 전혀 쓰지 않은 구성(base=uniform)의 추천도 현재 공급보다 주민 수요 분포에 가깝다(차이 +0.016, 95% 구간 +0.007~+0.025). '경제적 지원'은 공급 12.5% → 추천 22%로 수요(25%)에 다가간다. '일자리'는 여전히 모자란다(수요 10.5%, 추천 3.7%): 일자리 프로그램 종류가 적고 다른 단지에서도 드물어 근거 점수가 낮기 때문이다.\n")
    A(md(T("e6_happycall_outcome")))
    A("\n관리소 단위 복지 만족도는 현 공급의 필요 정렬·공급량·종류 수 어느 것과도 관계가 없다(ρ≈0). 해피콜 만족도는 단지별 정답으로 쓸 수 없다. 종합 만족도와 '우선 검토 분야 수'의 음의 상관은 규모·고령·영구임대를 통제하면 사라진다.\n")
    A("## 7. E7 프로그램·사례 검색\n")
    A(md(T("e7_retrieval")))
    A("\n학습 구간 제목을 색인에 넣고 세 방법을 순위 융합하면, 처음 보는 활동 제목의 74%를 첫 순위에, 90%를 3순위 안에 맞는 표준 프로그램으로 잇는다. 새 기록 입력 때 '표준 프로그램 자동 제안'에 쓸 수 있는 수준이다. 뉴스·사례집은 표본이 작다(55건, 19건).\n")
    if (C.TABLES / "e8_methods_pooled.csv").exists():
        e8(A, s)
    A("## 9. 한계\n")
    A("- 새 도입은 '기록 기준'이다. 안 한 것과 안 적은 것을 가를 수 없다.")
    A("- 필요 쪽 지표는 설계 목표를 잰 것이다. 외부 검증은 해피콜 전국 분포(약함)와 고독사 기록(N1 한 분야)뿐이다.")
    A("- 비용·인력은 전문가 1명의 검토값으로 바꿨다. 부담 주체별 비중은 적힌 순서로 나눈 가정이다.")
    A("- 전문가 응답은 평가자 1명이고, 단지 요약과 시스템 산출물을 보고 작성한 흔적이 있어 필요 지수의 독립 검증으로 볼 수 없다.")
    A("- 표준 프로그램 분류는 자동 판정이다(표본 일치율 87%).")
    (C.ROOT / "docs" / "02_experiments.md").write_text("\n".join(L), encoding="utf-8")


def e8(A, s):
    xa, xn, xr = s["expert_a"], s["expert_need"], s["expert_requirements"]
    A("## 8. E8 전문가 검토 응답 반영\n")
    A(f"응답: 시트 A {xa['n']}행(단지 {xa['complexes']}곳 × 프로그램 {xa['programs']}종), B 96종, C 지표 24개, D 단지 24곳. **평가자 1명**이라 평가자 간 일치도는 잴 수 없다. 순위 모델 학습에는 쓰지 않았다.\n")
    A("**응답을 읽을 때의 주의**\n")
    A(f"1. 등급의 대부분이 프로그램에 따라 정해진다. 필요 등급 분산의 {xa['r2_program']['need']:.0%}, 실행 등급의 {xa['r2_program']['feas']:.0%}가 프로그램 평균으로 설명된다. 단지에 따른 차이는 작다.")
    A(f"2. 우선 추천 Y가 단지마다 {xa['y_per_complex'][0]}~{xa['y_per_complex'][1]}개로 거의 같다. 개수를 맞춰 고른 것으로 보이므로 단지 간 Y 비율 비교는 뜻이 없다.")
    A("3. 시트 D의 한 줄 의견에 시스템 산출물의 표현(유형 S3, 공급 백분위, 'N4 필요 1위')이 들어 있다. 평가자가 단지 프로파일을 보고 작성했다면 필요 지수와의 일치는 독립 검증이 아니다.\n")
    A("### 8.1 후보를 낸 방법별 전문가 등급(요청 당시 각 방법의 상위 5개)\n")
    A(md(T("e8_methods_pooled")))
    A("")
    A(md(T("e8_methods_tests")[lambda d: d.gain.isin(["y", "need", "feas"])], ["gain", "a", "b", "diff", "lo", "hi", "p", "p_holm"]))
    A(f"\n**읽는 법**: 네 방법 모두 무작위 후보(우선 추천 {s['expert_methods']['random_y']:.0%})보다 훨씬 높다. 우선 추천 기준으로는 네 방법 사이에 유의한 차이가 없다. 필요 적합만 쓴 방법은 필요 등급이 가장 높지만 실행 등급이 뚜렷이 낮다(Holm 보정 후에도 유의). 온터 기본값은 필요 등급을 채택률보다 올리면서 실행 등급을 거의 지킨다. 도입 기록으로 본 결과('필요 적합만으로는 현장이 고르지 않는다')와 전문가 판단이 같은 방향이다.\n")
    A("### 8.2 성분 점수와 전문가 등급(단지 안 순위상관의 평균)\n")
    A(md(T("e8_component_validity")))
    A("")
    A(md(T("e8_within_program")))
    A("\n**읽는 법**: 채택률·근거 점수는 '실행할 수 있는가'와 강하게 맞고(ρ≈0.55) '필요한가'와는 무관하다. 필요 적합은 '필요한가'와 맞고(ρ≈0.27) 실행과는 반대 방향이다. 두 점수가 서로 다른 것을 잰다는 설계 가정이 확인된다. 같은 프로그램이 단지마다 다르게 평가된 부분만 봐도 필요 적합·필요 지수는 전문가 필요 등급과 같은 방향이고(ρ≈0.2), 근거 점수는 그렇지 않다.\n")
    A("### 8.3 조절값 점검(판정된 후보만 줄 세운 NDCG@5, 우선 추천 기준)\n")
    A(md(T("e8_decision_table")))
    A("")
    A(md(T("e8_split_half")))
    A("\n**읽는 법**: 전문가 우선 추천은 필요 가중 w를 0.3~0.5로 올리고 보정(λ)을 끈 구성에서 가장 높다. 그러나 w를 올리면 새 도입 재현율이 계속 떨어진다. 단지 24곳을 반으로 나눠 한쪽에서 고르고 다른 쪽에서 기본값과 비교하면 이득의 95% 구간이 0을 포함한다. 평가자 1명, 독립성 문제까지 고려해 **기본값(w=0.2, λ=0.25)은 바꾸지 않았다.** 대신 w를 화면에서 조절할 수 있게 하고(0~0.5) 이 표를 안내로 쓴다. 실행 가능성 점수를 순위에 섞는 것은 전문가 기준으로도 이득이 없다.\n")
    A("### 8.4 필요 지수(시트 D·C)\n")
    A(md(T("e8_need_vs_expert_domain")))
    A("")
    A(md(T("e8_need_distribution_align")))
    A("")
    A(md(T("e8_weight_sensitivity")))
    A(f"\n**읽는 법**: 전문가의 분야별 배점은 필요 백분위와 강하게 맞는다(ρ 0.52~0.96). 다만 위 주의 3 때문에 독립 검증이라고 할 수 없다. 전문가 배분은 현재 공급 비중과는 닮지 않았고(단지 안 순위상관 ≈0) 구조 필요와 닮았다. 지표 적절성 등급으로 가중치를 바꾸면 다섯 분야는 거의 그대로이고(ρ≥0.98) '문화와 활동'만 크게 바뀐다. 전문가는 '단지 안 공용 공간 종류'를 낮게 평가했는데(1점), 그 가중치를 낮추면 같은 전문가의 시트 D 배점과 반대 방향이 된다. 응답 안에서 서로 어긋나므로 **가중치는 그대로 두고 '문화와 활동'을 불확실한 분야로 표시한다.** 이용 실적(홈닥터) 지표는 평균 {xn['usage_indicator_rating_mean']:.1f}점으로 구조 지표({xn['struct_indicator_rating_mean']:.1f}점)보다 낮아, 기본 지수에서 뺀 설계와 맞는다.\n")
    A("### 8.5 실행 요건(시트 B)\n")
    A(md(T("e8_requirements_agreement")))
    A("")
    A(md(T("e8_feasibility_validity")))
    A("")
    A(md(T("e8_requirement_lift")))
    A("")
    A(md(T("e8_portfolio_expert")))
    A(f"\n**읽는 법**: 기록에서 추정한 1회 비용은 전문가 값과 순위가 맞지만(ρ=0.71) 약 1.5배 높았다. 인력 부담 등급은 전문가 값과 약하게만 맞았다(ρ≈0.35). 그래서 **비용·인력·필수 공간·필수 협력기관·주거복지사 필요 여부를 전문가 값으로 바꿨다**(초안은 `_draft` 열). 전문가 요건으로 만든 실행 가능성은 새 도입을 우연보다 잘 맞힌다(AUC 0.59, 규칙 기반 0.48). 전문가가 '주거복지사 필요'라고 한 {xr['n_needs_welfare_worker']}종은 미배치 단지의 새 도입률이 3.2%로 배치 단지 8.0%의 절반 이하다. 그래도 순위에 섞으면 도입 예측이 나아지지 않으므로 순위에는 넣지 않고, **'주거복지사 필요인데 미배치' 경고와 묶음 선택의 제약**으로 쓴다. 초안 요건으로 고른 묶음의 절반 남짓이 전문가 값으로는 한도를 넘는다.\n")


if __name__ == "__main__":
    figures()
    report()
    print("report written")
