# -*- coding: utf-8 -*-
"""웹 페이지 v2 추가 자료: 변수 사전, 단지별 시계열·인구·후보, 프로그램 사전, 주민 수요(해피콜), VOC, 뉴스, 자료 목록.
build_web.py가 불러 쓴다. 모든 값은 원자료·처리 자료에서 계산하며, 문장은 만들지 않는다(웹이 수치를 보여 준다)."""
import json
import os
import re

import numpy as np
import pandas as pd

ROOT = r"C:/Users/user/Desktop/2026 DRIVE/project/data/"
COMM = ROOT + "processed/community_nlp_2026_v1/"
HAPPY = ROOT + "processed/happycall_2025_v1/"
rd = lambda p, **k: pd.read_csv(p, encoding="utf-8-sig", low_memory=False, **k)

FAC = ["병원", "의원", "종합병원", "응급의료시설", "약국", "보건기관", "경로당", "노인교실", "노인복지관", "노인여가복지시설",
       "종합사회복지관", "어린이집", "유치원", "영유아교육돌봄시설", "온종일돌봄센터", "초등학교"]
AGES = ["10대미만", "10대", "20대", "30대", "40대", "50대", "60대", "70대", "80대", "90대", "100대"]
DEMAND_MAP = {  # 해피콜 '주거생활지원' 수요 항목 → 프로그램 주 목적(NLP)
    "주거환경 개선": ["주거환경·위생·시설개선", "안전·재난예방"],
    "경제적 지원": ["식생활·생필품 지원", "경제·금융 지원"],
    "문화생활": ["여가·문화·체육"],
    "일자리": ["일자리·취업"],
    "이웃 소통": ["이웃관계·공동체 활성화"],
    "신체건강": ["건강증진·질병예방"],
    "돌봄": ["돌봄·안부확인"],
    "정신건강": ["정신건강·심리지원"],
}


def variables(b):
    """단지 변수 사전과 값 배열(단지 순서는 b의 행 순서)."""
    V = []

    def add(k, label, unit, fmt, grp, s, higher="", note=""):
        V.append(dict(k=k, label=label, unit=unit, fmt=fmt, grp=grp, note=note, v=[None if pd.isna(x) else float(x) for x in s]))
    add("hh", "세대수", "세대", ",.0f", "규모·구조", b["세대수"])
    add("age", "입주 후 경과 연수", "년", ".0f", "규모·구조", b["입주기준경과년수"])
    add("area", "평균 전용면적", "㎡", ".1f", "규모·구조", b["평형_전용면적가중평균_㎡"])
    add("small40", "40㎡ 미만 세대 비율", "%", ".0f", "규모·구조", b["평형_40㎡미만세대비율"] * (100 if b["평형_40㎡미만세대비율"].max() <= 1.01 else 1))
    add("floors", "최고 층수", "층", ".0f", "규모·구조", b.get("최고층수", pd.Series(np.nan, index=b.index)))
    add("elev", "승강기(100세대당)", "대", ".1f", "규모·구조", b.get("승강기대수_100세대당", pd.Series(np.nan, index=b.index)))
    add("cctv", "CCTV(100세대당)", "대", ".1f", "규모·구조", b.get("CCTV대수_100세대당", pd.Series(np.nan, index=b.index)))
    add("park", "세대당 주차면", "면", ".2f", "규모·구조", b.get("주차_세대당", pd.Series(np.nan, index=b.index)))
    add("pop", "총 거주인구", "명", ",.0f", "주민", b["총거주인구"])
    add("p60", "60세 이상 비율", "%", ".0f", "주민", b["인구_60세이상_비율"] * 100)
    add("p80", "80세 이상 비율", "%", ".0f", "주민", b["인구_80세이상_비율"] * 100)
    add("p20", "20세 미만 비율", "%", ".0f", "주민", b["인구_20세미만_비율"] * 100)
    add("pf", "여성 비율", "%", ".0f", "주민", b["인구_여자_비율"] * 100 if "인구_여자_비율" in b else pd.Series(np.nan, index=b.index))
    add("hd", "홈닥터 지원(100세대당 월, 2025)", "건", ".1f", "홈닥터", b["hd_per100"])
    for c, lab in [("생활지원", "생활지원"), ("가사지원", "가사지원"), ("의료지원", "의료지원"), ("경제지원", "경제지원")]:
        add("hd_" + c, f"홈닥터 중 {lab} 비중", "%", ".0f", "홈닥터", b[f"hd25_{c}_share"] * 100)
    add("comm", "프로그램 기록(1,000세대당 연)", "건", ".1f", "프로그램", b["comm_per1000"])
    add("nres", "주민 대상 기록(30개월)", "건", ",.0f", "프로그램", b["n_res"])
    add("rich", "운영한 프로그램 종류", "종", ".0f", "프로그램", b["std_richness"])
    add("part", "참여 인원(100세대당 연, 기록)", "명", ",.0f", "프로그램", b["participation_per_100hh_year"])
    add("eld", "어르신 대상 프로그램 비중", "%", ".0f", "프로그램", b["eld_share"] * 100)
    add("months", "기록이 있는 달(30개월 중)", "개월", ".0f", "프로그램", b["active_months_res"])
    add("gap", "이웃 대비 빠진 프로그램 후보", "개", ".0f", "프로그램", b["n_gap"])
    add("partner", "협력 기관 유형 수", "종", ".0f", "프로그램", b["partner_org_type_richness"])
    add("repeat", "반복 운영 기록 비율", "%", ".0f", "프로그램", b["repeat_record_share"] * 100)
    for f, lab in [("F04", "건강증진"), ("F10", "문화·여가"), ("F07", "주거환경·시설"), ("F02", "돌봄·안부"), ("F14", "공동체·참여")]:
        add("fam_" + f, f"{lab} 영역 비중", "%", ".0f", "프로그램", b[f"share_family_{f}"] * 100)
    add("gov", "거버넌스 회의(2025)", "건", ".0f", "운영", b["거버넌스_2025_회의건수"])
    add("tbm", "작업전 안전모임 TBM(2025)", "회", ".0f", "운영", b["TBM_2025_관측행수"])
    add("mou", "주거복지 업무협약(2025)", "건", ".0f", "운영", b["업무협약_2025_기록건수"])
    add("job", "일자리 지원 기록(2025)", "건", ".0f", "운영", b["일자리지원_2025_기록건수"])
    add("sat", "해피콜 종합만족도", "점", ".1f", "만족도", b["overall_satisfaction"])
    add("satw", "해피콜 복지 만족도", "점", ".1f", "만족도", b["welfare_satisfaction"])
    add("sath", "해피콜 주택관리 만족도", "점", ".1f", "만족도", b["housing_management_satisfaction"])
    add("need", "필요 지수(백분위)", "", ".0f", "필요·공급", b["need_pct"], note="60세 이상 비율 + 홈닥터 지원 강도")
    add("supply", "공급 지수(백분위)", "", ".0f", "필요·공급", b["supply_pct"], note="1,000세대당 기록")
    for f in FAC:
        c = f"접근성_{f}_대표점_km"
        if c in b.columns:
            add("acc_" + f, f"{f}까지 거리", "km", ".2f", "생활 접근성", b[c])
    return V


def timeseries(b):
    p = rd(ROOT + "processed/complex_month_panel_20261117_v1/complex_month_panel.csv",
           usecols=["complex_id", "target_month", "source_observed", "recorded_support_count", "recorded_households", "community_resident_records_same_month", "community_window"])
    months = sorted(p["target_month"].unique())
    p["hd"] = np.where(p["source_observed"] == 1, p["recorded_support_count"] / p["recorded_households"] * 100, np.nan)
    hd = p.pivot(index="complex_id", columns="target_month", values="hd").reindex(index=b["complex_id"], columns=months)
    cm = p.pivot(index="complex_id", columns="target_month", values="community_resident_records_same_month").reindex(index=b["complex_id"], columns=months)
    cmonths = [m for m in months if "2024-01" <= m <= "2026-06"]
    cm = cm[cmonths]
    n_obs = hd.notna().sum(axis=0)
    med = hd.median(axis=0).where(n_obs >= 100)
    rnd = lambda a: [None if pd.isna(x) else round(float(x), 2) for x in a]
    return dict(months=months, cmonths=cmonths, hd=[rnd(r) for r in hd.values], hd_med=rnd(med.values),
                comm=[[None if pd.isna(x) else int(x) for x in r] for r in cm.values], comm_med=rnd(cm.median(axis=0).values))


def pyramid(b):
    out = []
    for _, r in b.iterrows():
        f_ = [r.get(f"인구_{a}(여자)") for a in AGES]
        m_ = [r.get(f"인구_{a}(남자)") for a in AGES]
        out.append(None if all(pd.isna(x) for x in f_ + m_) else [[0 if pd.isna(x) else int(x) for x in m_], [0 if pd.isna(x) else int(x) for x in f_]])
    return dict(ages=["0~9", "10대", "20대", "30대", "40대", "50대", "60대", "70대", "80대", "90대", "100+"], v=out)


def candidates(b, nbt, ml, sd, top=10):
    """단지별 검토 후보: 아직 운영하지 않은 추천 가능 프로그램을 세 가지 이웃 신호의 평균으로 정렬(시연용 규칙 점수)."""
    ca = rd(COMM + "complex_program_candidates.csv")
    rec = set(sd.loc[(sd["recommendable"] == 1) & (sd["scope"] == "PROGRAM"), "std_id"])
    ca = ca[(ca["complex_adopted"] == 0) & ca["std_id"].isin(rec)].copy()
    ad = ml[ml["n_records"] > 0].groupby("complex_id")["std_id"].apply(set).to_dict()
    nbs = nbt.groupby("complex_id")["neighbor_id"].apply(list).to_dict()
    demo = {}
    for cid, ns in nbs.items():
        s = pd.Series([x for n in ns for x in ad.get(n, set())]).value_counts() / len(ns)
        demo[cid] = s.to_dict()
    ca["demo"] = [demo.get(c, {}).get(s, np.nan) for c, s in zip(ca["complex_id"], ca["std_id"])]
    sig = ca[["demo", "peer_group_adoption_rate", "cf_neighbor_adoption_rate"]]
    ca["score"] = sig.mean(axis=1, skipna=True) + 0.05 * ca["fills_gap_domain"].fillna(0)
    fam = dict(zip(sd["std_id"], sd["std_family_label"]))
    nd = {"N1": "안부와 관계", "N2": "생활과 경제", "N3": "건강과 돌봄", "N4": "주거환경과 생활안전", "N5": "문화와 활동", "N6": "일자리와 학습"}
    out = {}
    for cid, g in ca.sort_values("score", ascending=False).groupby("complex_id", sort=False):
        rows = []
        for _, r in g.head(top).iterrows():
            rows.append([r["std_id"], round(float(r["score"]), 3), None if pd.isna(r["demo"]) else round(float(r["demo"]), 2),
                         round(float(r["peer_group_adoption_rate"]), 2), round(float(r["cf_neighbor_adoption_rate"]), 2),
                         int(r["fills_gap_domain"] or 0), nd.get(r["need_domain_primary"], ""), round(float(r["season_share_next_month"] or 0), 3),
                         None if pd.isna(r["cost_ratio_to_complex_median"]) else round(float(r["cost_ratio_to_complex_median"]), 2)])
        out[cid] = rows
    return [out.get(c, []) for c in b["complex_id"]]


def programs(b, ml, sd, pa):
    """프로그램 사전: 표준 프로그램별 요약과 운영 단지."""
    co = rd(COMM + "std_cooccurrence.csv")
    idx = {c: i for i, c in enumerate(b["complex_id"])}
    sg = dict(zip(b["complex_id"], b["supply_group"]))
    r = pa[pa["in_resident_scope"] == 1]
    tgt = r.groupby("std_id")["target_explicit_labels"].apply(lambda s: s.dropna().str.split("|").explode().value_counts().head(3).index.tolist() if s.notna().any() else [])
    # 주거복지사 활동 사례집 근거 카드(casebook_programs_v1): 프로그램별 '비슷한 단지는 이렇게 했다'
    cards_path = ROOT + "processed/casebook_programs_v1/evidence_cards.csv"
    cards = rd(cards_path) if os.path.exists(cards_path) else pd.DataFrame(columns=["std_id"])
    cards = cards[cards["std_id"].notna() & cards.get("std_confidence", pd.Series(dtype=str)).isin(["high", "medium", "reviewed"])]
    clean = lambda v: "" if pd.isna(v) else str(v)
    card_of = {sid: [dict(id=r["card_id"], region=clean(r["region"]), name=clean(r["program_name"]), headline=clean(r["headline"]), need=clean(r["need"]),
                          target=clean(r["target"]), partners=clean(r["partners"]), operation=clean(r["operation"]), outcomes=clean(r["outcomes"]),
                          obstacles=clean(r["obstacles_and_solutions"])) for _, r in g.iterrows()] for sid, g in cards.groupby("std_id")}
    P = []
    for _, s in sd[sd["scope"] == "PROGRAM"].sort_values("n_records", ascending=False).iterrows():
        sid = s["std_id"]
        m = ml[(ml["std_id"] == sid) & (ml["n_records"] > 0)]
        cx = [[idx[c], int(n)] for c, n in zip(m["complex_id"], m["n_records"]) if c in idx]
        by_sg = {}
        for g in b["supply_group"].dropna().unique():
            tot = (b["supply_group"] == g) & b["n_res"].notna()
            have = m["complex_id"].map(sg).eq(g).sum()
            by_sg[g] = round(float(have / tot.sum()), 3) if tot.sum() else None
        cc = co[(co["std_a"] == sid) | (co["std_b"] == sid)].sort_values("lift", ascending=False).head(6)
        pair = [[(r_["std_b_name"] if r_["std_a"] == sid else r_["std_a_name"]), float(r_["lift"]), int(r_["n_both"])] for _, r_ in cc.iterrows()]
        aliases = [a.strip() for a in str(s.get("alias_examples") or "").split(" / ") if a.strip()][:6]
        P.append(dict(id=sid, name=s["std_name"], fam=s["std_family_label"], rec=int(s.get("recommendable") or 0), n=int(s["n_records"]), ncx=int(s["n_complexes"]),
                      adopt=float(s["adoption_rate"]), titles=int(s["alias_distinct_titles"] or 0), months=[float(s[f"month_share_{m_:02d}"] or 0) for m_ in range(1, 13)],
                      part=s["participants_total_median"], cost=s["est_cost_mid_median_krw"], evt=s["op_evt_Y_share"], reg=s["op_reg_Y_share"],
                      partners=[p_ for p_ in str(s.get("partner_org_top3") or "").split("|") if p_ and p_ != "nan"], aliases=aliases,
                      targets=tgt.get(sid, []), definition=str(s.get("definition_ko") or ""), by_sg=by_sg, pairs=pair, cx=cx,
                      n24=int(s["n_2024"]), n25=int(s["n_2025"]), n26=int(s["n_2026h1"]), cases=card_of.get(sid, [])))
    return P


def demand(pa):
    s = rd(HAPPY + "service_demand.csv")
    s = s.drop_duplicates(subset=["population", "scope", "group", "subgroup", "metric"])
    pops = {"residential_life_support_service_users": "주거생활지원 서비스 이용자", "social_isolation_service_users": "사회적 고립 지원 서비스 이용자"}
    out = {}
    for pk, plab in pops.items():
        x = s[s["population"] == pk]
        ov = x[x["scope"] == "overall"]
        metrics = ov.sort_values("value", ascending=False)["metric"].tolist()
        n_all = int(ov["n"].iloc[0]) if len(ov) else None
        groups = {}
        for g, gx in x[x["scope"] == "respondent_subgroup"].groupby("group"):
            subs = list(dict.fromkeys(gx["subgroup"].tolist()))
            groups[g] = dict(subs=subs, n=[int(gx[gx["subgroup"] == sb]["n"].iloc[0]) if len(gx[gx["subgroup"] == sb]) else None for sb in subs],
                             v=[[None if gx[(gx["subgroup"] == sb) & (gx["metric"] == mt)].empty else float(gx[(gx["subgroup"] == sb) & (gx["metric"] == mt)]["value"].iloc[0]) for mt in metrics] for sb in subs])
        out[pk] = dict(label=plab, n=n_all, metrics=metrics, overall=[float(ov[ov["metric"] == mt]["value"].iloc[0]) for mt in metrics], groups=groups)
    # 수요 vs 공급(주 목적 비중)
    r = pa[pa["in_resident_scope"] == 1]
    sh = r["purpose_primary_label"].value_counts(normalize=True)
    rl = out["residential_life_support_service_users"]
    dem = dict(zip(rl["metrics"], rl["overall"]))
    tot = sum(dem[k] for k in DEMAND_MAP if k in dem)
    vs = []
    for k, labs in DEMAND_MAP.items():
        if k in dem:
            vs.append(dict(k=k, demand_pct=dem[k], demand_share=dem[k] / tot, supply_share_all=float(sum(sh.get(l, 0) for l in labs)), purposes=labs))
    # 수요와 같은 기준으로 맞춘다: 대응되는 8개 항목 안에서의 비중(대응 없는 '기타' 목적 기록은 양쪽 모두 제외)
    stot = sum(v["supply_share_all"] for v in vs)
    for v in vs:
        v["supply_share"] = v["supply_share_all"] / stot
    return dict(pops=out, vs=vs, n_records=int(len(r)), matched_record_share=float(stot))


def voc():
    v = rd(HAPPY + "voc.csv")
    rows = []
    for cat, g in v.groupby("category_raw"):
        m = re.search(r"\((\d+)\)\s*$", str(cat))
        name = re.sub(r"\s*\(\d+\)\s*$", "", str(cat)).strip()
        tags = sorted({t for x in g["need_tags_suggested"].dropna() for t in json.loads(x)})
        rows.append(dict(cat=name, n=int(m.group(1)) if m else None, items=int(len(g)), tags=tags))
    return sorted(rows, key=lambda d: -(d["n"] or 0))


def news():
    """정제된 뉴스(housing_welfare_news_v1)의 대표 기사: 제목·링크와 연결된 표준 프로그램·단지(본문은 싣지 않는다)."""
    a = rd(ROOT + "processed/housing_welfare_news_v1/articles.csv")
    a = a[a["is_representative"] == 1]
    out = [dict(date=r["date"], title=r["title"], url=r["url"], host=r["outlet"], prog="" if pd.isna(r["primary_std_name"]) else r["primary_std_name"],
                cx=[] if pd.isna(r["complex_ids"]) else str(r["complex_ids"]).split("|")) for _, r in a.iterrows()]
    return sorted(out, key=lambda d: d["date"] or "", reverse=True)


def catalog():
    items = [
        ("단지 통합표", "processed/complex_integrated_20261117_v1/data/complex_master.csv", "318개 단지의 규모·인구·시설·접근성·운영 집계"),
        ("홈닥터 월별", "processed/complex_integrated_20261117_v1/data/home_doctor_monthly.csv", "단지×월 지원 건수(2022-01~2026-06)"),
        ("단지×월 패널", "processed/complex_month_panel_20261117_v1/complex_month_panel.csv", "홈닥터+커뮤니티 월별, 과거 시차 특성"),
        ("커뮤니티 활동 기록(NLP)", "processed/community_nlp_2026_v1/program_analysis.csv", "2024-01~2026-06 활동 기록, 표준 프로그램 분류"),
        ("표준 프로그램 사전", "processed/community_nlp_2026_v1/standard_program_dictionary.csv", "표준 프로그램 정의·통계"),
        ("단지×프로그램 후보", "processed/community_nlp_2026_v1/complex_program_candidates.csv", "추천 후보 쌍과 특성"),
        ("해피콜 관리소 점수", "processed/happycall_2025_v1/management_scores.csv", "2025 관리소별 만족도"),
        ("해피콜 서비스 수요", "processed/happycall_2025_v1/service_demand.csv", "응답자 특성별 희망 서비스"),
        ("해피콜 VOC", "processed/happycall_2025_v1/voc.csv", "주민 의견 범주"),
        ("해피콜 통계(긴 형식)", "processed/happycall_2025_v1/statistics_long.csv", "보고서 표의 모든 수치"),
        ("관리소–단지 연결표", "processed/complex_keys_20261117_v1/happycall_office_map_confirmed.csv", "2026-11-17 확정"),
        ("주거복지사 사례집 근거 카드", "processed/casebook_programs_v1/evidence_cards.csv", "사례 18개 → 필요·대상·협력·운영·성과·장애물과 해결"),
        ("사례집 장애물과 해결", "processed/casebook_programs_v1/case_obstacles.csv", "사업 시작·운영 중 부딪힌 문제와 푼 방법"),
        ("주거복지 뉴스(정제)", "processed/housing_welfare_news_v1/articles.csv", "공단 관련 기사 정제·표준 프로그램·단지 연결"),
        ("뉴스 문장 근거", "processed/housing_welfare_news_v1/sentences.csv", "기사 문장(이름·연락처 가림)"),
    ]
    out = []
    for name, path, desc in items:
        fp = ROOT + path
        if not os.path.exists(fp):
            continue
        if fp.endswith(".jsonl"):
            n, c = sum(1 for _ in open(fp, encoding="utf-8")), None
        else:
            hdr = pd.read_csv(fp, encoding="utf-8-sig", nrows=0)
            n, c = sum(1 for _ in open(fp, encoding="utf-8-sig")) - 1, len(hdr.columns)
        out.append(dict(name=name, path=path, desc=desc, rows=n, cols=c))
    raw = sorted(f for f in os.listdir(ROOT + "raw") if f.endswith(".csv"))
    return dict(items=out, raw=raw)
