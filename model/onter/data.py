"""전처리 데이터 로더. processed 폴더의 표를 complex_id / std_id 기준으로 읽어 모델용 열을 만든다.

원칙
- 조인 키는 complex_id, std_id뿐이다. 단지명 문자열로 잇지 않는다.
- 결측을 0으로 바꾸지 않는다(0이 '없음'을 뜻하는 열만 예외로 표시).
- 고독사 기록은 입력으로 쓰지 않고 타당도 점검에만 쓴다(통합표 명세의 '별도결과').
"""
from functools import lru_cache
import json
import numpy as np
import pandas as pd
from . import config as C

rd = lambda p, **k: pd.read_csv(C.DATA / p, encoding="utf-8-sig", low_memory=False, **k)


def region_type(addr):
    t = str(addr).split()
    if len(t) < 2:
        return None
    if t[1].endswith("군"):
        return "군 지역"
    if ("특별시" in t[0] or "광역시" in t[0]) and t[1].endswith("구"):
        return "대도시 자치구"
    return "시 지역"


def _winsor(s, hi=0.99):
    return s.clip(upper=s.quantile(hi))


@lru_cache(maxsize=None)
def complexes():
    """단지 1행(318). 모델용 파생 열을 영문 이름으로 붙인다."""
    m = rd("complex_integrated_20261117_v1/data/complex_master.csv").set_index("complex_id")
    d = pd.DataFrame(index=m.index)
    d["name"], d["branch"], d["addr"] = m["단지명"], m["지사명"], m["기본주소"]
    d["region"] = d["addr"].map(region_type)
    d["lon"], d["lat"] = m["longitude"], m["latitude"]
    d["supply"] = m["공급유형"]
    for k, kw in {"perm": "영구임대", "national": "국민임대", "pub50": "공공임대(50년)", "happy": "행복주택"}.items():
        d[k] = m["공급유형"].str.contains(kw, regex=False).astype(int)
    d["hh"] = m["세대수"].astype(float)
    d["log_hh"] = np.log(d["hh"])
    d["pop"] = m["총거주인구"].astype(float)
    d["pph"] = (d["pop"] / d["hh"]).clip(0.5, 4)                      # 세대당 인구(낮을수록 1인 가구가 많다는 대리 지표)
    d["age60"], d["age70"], d["age80"] = m["인구_60세이상_비율"], m["인구_70세이상_비율"], m["인구_80세이상_비율"]
    d["age_u20"], d["female"] = m["인구_20세미만_비율"], m["인구_여자_비율"]
    band = lambda b: m[f"인구_{b}(여자)"].fillna(0) + m[f"인구_{b}(남자)"].fillna(0)
    d["age_work"] = sum(band(b) for b in ["20대", "30대", "40대", "50대"]) / d["pop"]
    for b in C.AGE_BANDS:                                             # 해피콜 연령 보정용 연령대 인구
        d[f"n_{b}"] = band(b)
    d["years"] = m["입주기준경과년수"]
    d["area_avg"], d["small_unit"], d["rooms"] = m["평형_전용면적가중평균_㎡"], m["평형_40㎡미만세대비율"], m["평형_방수가중평균"]
    d["elev100"], d["cctv100"] = _winsor(m["승강기대수_100세대당"]), _winsor(m["CCTV대수_100세대당"])
    d["parking"] = m["주차_세대당"]
    d["heating"] = m["난방방식"]
    # 단지 안 공간. 면적 원값에 이상치가 있어 '있음' 여부와 상한을 둔 세대당 면적만 쓴다
    for k, col in {"senior": "경로당_연면적_제곱미터", "gym": "주민운동시설_연면적_제곱미터", "hall": "입주자집회소_연면적_제곱미터",
                   "daycare": "어린이집_연면적_제곱미터", "library": "도서관_연면적_제곱미터"}.items():
        a = m[col].fillna(0)
        d[f"sp_{k}"] = (a > 0).astype(int)
        d[f"spa_{k}"] = (a.clip(upper=a[a > 0].quantile(0.95)) / d["hh"]).fillna(0)
    op = m["복지관운영주체명"].astype("string").str.strip()
    d["sp_welfare"] = (op.notna() & ~op.isin(["해당없음", "없음", "0", ""])).astype(int)
    d["welfare_operator"] = op.where(d["sp_welfare"] == 1)
    d["n_space"] = d[[c for c in d.columns if c.startswith("sp_")]].sum(axis=1)
    # 단지 밖 시설까지 거리(km). 500m 평균 → 1000m 평균 → 대표점 순으로 채운다. 결측은 0km가 아니다
    for f in C.FACILITIES:
        s = m[f"접근성_{f}_500m_평균_km"]
        for alt in (f"접근성_{f}_1000m_평균_km", f"접근성_{f}_대표점_km"):
            if alt in m.columns:
                s = s.fillna(m[alt])
        d[f"d_{f}"] = s
    d["n_fac500"] = m["접근성_500m_유효시설종류수"]
    # 홈닥터(세대 방문 지원) 2025: 100세대당 월평균 건수와 항목별 건수
    mon = m["홈닥터_2025_관측월수"].replace(0, np.nan)
    d["hd"] = m["홈닥터_2025_100세대당월평균지원건수"]
    for k, col in {"life": "생활지원", "chores": "가사지원", "medical": "의료지원", "econ": "경제지원"}.items():
        d[f"hd_{k}"] = m[f"홈닥터_2025_{col}"] / mon / d["hh"] * 100
    tot = m["홈닥터_2025_지원내용총건수"].replace(0, np.nan)
    d["hd_medical_share"], d["hd_econ_share"] = m["홈닥터_2025_의료지원"] / tot, m["홈닥터_2025_경제지원"] / tot
    d["hd_trend"] = m["홈닥터_2026_상반기_전년동기증감률"]
    # 기록이 없으면 '없음'으로 보는 건수(원표가 발생 건만 적는 자료)
    d["mou25"], d["job25"], d["gov25"] = m["업무협약_2025_기록건수"].fillna(0), m["일자리지원_2025_기록건수"].fillna(0), m["거버넌스_2025_회의건수"].fillna(0)
    d["mou25_expert"] = m["업무협약_2025_전문인력여부_Y행수"].fillna(0)
    d["ld_total"] = m[[c for c in m.columns if c.startswith("고독사_")]].sum(axis=1)        # 타당도 점검 전용
    dep = rd("casebook_programs_v1/features/welfare_worker_deployment_2025.csv")
    d["deployed"] = d.index.isin(dep["complex_id"].dropna()).astype(int)
    kx = rd("complex_keys_20261117_v1/complex_key_crosswalk.csv").set_index("complex_id")
    d["in_community"] = kx["in_community_nlp"].reindex(d.index).fillna(0).astype(int)
    return d


RECORD_COLS = ["record_id", "complex_id", "std_id", "std_name", "std_family", "scope", "in_resident_scope", "purpose_primary", "need_domain_primary",
               "need_domains", "target_explicit", "target_type_default", "service_codes", "mode_explicit", "mode_type_default",
               "support_unit_complex_wide", "support_unit_household", "support_unit_contact", "op_primary", "partner_org_codes",
               "resource_explicit", "resource_type_default", "start_date", "activity_count", "duration_days", "participants_total",
               "participants_individual", "participants_institutional", "org_count_raw", "cost_class_raw", "budget_subject_raw",
               "budget_archetype", "est_cost_mid_krw", "est_burden_class", "est_burden_mid_krw", "flag_mou", "flag_external_contest",
               "place_masked", "program_name_masked", "activity_content_masked", "low_info_text_flag", "content_len",
               "hq_template_flag", "std_confidence", "label_source", "title_norm"]


@lru_cache(maxsize=None)
def records(resident_only=True):
    """커뮤니티 활동 기록. ym(YYYY-MM)을 붙이고, 기본은 주민 대상 기록만 준다."""
    r = rd("community_nlp_2026_v1/program_analysis.csv", usecols=RECORD_COLS)
    r["ym"] = pd.to_datetime(r["start_date"], errors="coerce").dt.strftime("%Y-%m")
    r = r[r["ym"].between(C.FIRST_MONTH, C.LAST_MONTH)]
    if resident_only:
        r = r[r["in_resident_scope"] == 1]
    return r.reset_index(drop=True)


def _codes(s):
    return [] if pd.isna(s) else [x for x in str(s).split("|") if x]


@lru_cache(maxsize=None)
def programs():
    """추천 대상 표준 프로그램(96종)과 정의 속성. 기간별 통계는 여기 두지 않는다(누수 방지)."""
    sd = rd("community_nlp_2026_v1/standard_program_dictionary.csv")
    sd = sd[sd["recommendable"] == 1].set_index("std_id")
    cb = rd("community_nlp_2026_v1/codebook_taxonomy.csv")
    lab2code = {t: dict(zip(g["label"], g["code"])) for t, g in cb.groupby("code_type")}
    key = lambda prefix: next(k for k in lab2code if k.startswith(prefix))
    p = pd.DataFrame(index=sd.index)
    p["name"], p["family"], p["family_label"], p["scope"] = sd["std_name"], sd["std_family"], sd["std_family_label"], sd["scope"]
    p["purpose"] = sd["purpose_primary"]
    p["need_primary"] = p["purpose"].map(C.PURPOSE_NEED)
    p["needs"] = sd["need_domains_def"].map(lambda s: [C.NEED_BY_LABEL[x] for x in _codes(s) if x in C.NEED_BY_LABEL])
    p["needs"] = [n if n else ([q] if isinstance(q, str) else []) for n, q in zip(p["needs"], p["need_primary"])]
    for col, typ, out in [("target_default", "target", "targets"), ("mode_default", "mode", "modes"), ("ops_typical", "op(", "ops"),
                          ("resource_default", "resource", "resources"), ("service_default", "service", "services"),
                          ("effect_default", "effect", "effects")]:
        mp = lab2code[key(typ)]
        p[out] = sd[col].map(lambda s: [mp[x] for x in _codes(s) if x in mp])
    p["archetype"], p["season_tag"], p["definition"] = sd["budget_archetype"], sd["season_tag"], sd["definition_ko"]
    return p


@lru_cache(maxsize=None)
def codebook():
    cb = rd("community_nlp_2026_v1/codebook_taxonomy.csv")
    return {t.split("(")[0]: dict(zip(g["code"], g["label"])) for t, g in cb.groupby("code_type")}


@lru_cache(maxsize=None)
def happycall_scores():
    """해피콜 관리소 점수를 단지에 붙인다. 통합 관리소(여러 단지 합산)와 미연결은 뺀다."""
    mp = rd("complex_keys_20261117_v1/happycall_office_map_confirmed.csv")
    mp = mp[mp["match_type"].isin(["exact", "confirmed_name_variant"]) & (mp["complexes_for_office"] == 1)]
    ms = rd("happycall_2025_v1/management_scores.csv")
    cols = ["source_name", "n_total", "small_sample", "overall_satisfaction", "pcsi", "major_service_satisfaction", "welfare_satisfaction",
            "housing_management_satisfaction", "rental_operation_satisfaction"]
    h = mp[["source_name", "complex_id"]].merge(ms[cols], on="source_name", how="left").drop_duplicates("complex_id")
    return h.set_index("complex_id")


@lru_cache(maxsize=None)
def happycall_demand():
    """해피콜 수요 응답(전국·응답자 구분 집계). 단지별 정답이 아니다."""
    return rd("happycall_2025_v1/service_demand.csv")[["population", "scope", "group", "subgroup", "metric", "value", "n"]]


@lru_cache(maxsize=None)
def casebook():
    b = "casebook_programs_v1/"
    return dict(cards=rd(b + "evidence_cards.csv"), obstacles=rd(b + "case_obstacles.csv"), playbook=rd(b + "features/obstacle_playbook.csv"),
                elements=rd(b + "case_elements.csv"), link=rd(b + "links/std_id_to_cards.csv"), cases=rd(b + "cases.csv"),
                deployment=rd(b + "features/welfare_worker_deployment_2025.csv"))


@lru_cache(maxsize=None)
def news():
    b = "housing_welfare_news_v1/"
    return dict(articles=rd(b + "articles.csv"), article_program=rd(b + "links/article_program.csv"),
                program_evidence=rd(b + "features/program_news_evidence.csv"), article_complex=rd(b + "links/article_complex.csv"))


def read_jsonl(rel):
    with open(C.DATA / rel, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]
