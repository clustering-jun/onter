# -*- coding: utf-8 -*-
"""사례집 앞부분: 주거복지사 배치 단지 목록(2025)과 영구임대·사업 개요 수치.

배치 단지는 통합표 단지명과 정확히 같을 때만 확정한다. 다르면 같은 지사의 비슷한 이름을 후보로만 둔다
(OCR 오타로 보이는 경우도 자동 교정하지 않는다: 주소·이름 보정은 확인 후 적용하는 원칙).
"""
import difflib
import re

import pandas as pd

ROW_RX = re.compile(r"^(?P<region>[가-힣·]+)\s*/\s*(?P<n>\d+)개소\s*/\s*(?P<names>.+)$")
REGION_BRANCH = {"서울": ["서울지사"], "경기북부": ["경기북부지사"], "경기남부": ["경기남부지사"], "인천": ["인천지사"], "부산·울산": ["부산울산지사"], "강원": ["강원지사"],
                 "충북": ["충북지사"], "대전·충남": ["대전충남지사"], "전북": ["전북지사"], "광주·전남": ["광주전남지사"], "대구·경북": ["대구경북지사"], "경남": ["경남지사"],
                 "제주": ["제주지사"]}

# 개요 수치: (주제, 항목, 값, 단위, 기준, 원문 근거) — 근거는 원문 대조로 검증한다
FACTS = [
    ("영구임대 입주민", "전체 가구", 122482, "가구", "2024년 말 계약자", "전체 122,482가구"),
    ("영구임대 입주민", "생계·의료급여 수급자 비율", 72.1, "%", "2024년 말 계약자", "생계·의료급여 수급자 72.1% 88,255가구"),
    ("영구임대 입주민", "생계·의료급여 수급자 가구", 88255, "가구", "2024년 말 계약자", "생계·의료급여 수급자 72.1% 88,255가구"),
    ("영구임대 입주민", "장애인 비율", 30.8, "%", "2024년 말 계약자", "장애인 30.8% 37,700가구"),
    ("영구임대 입주민", "장애인 가구", 37700, "가구", "2024년 말 계약자", "장애인 30.8% 37,700가구"),
    ("영구임대 입주민", "1인가구 비율", 76.6, "%", "2024년 말 계약자", "1인가구 76.6% 93,852가구"),
    ("영구임대 입주민", "1인가구", 93852, "가구", "2024년 말 계약자", "1인가구 76.6% 93,852가구"),
    ("영구임대 입주민", "1인가구 중 40세 이하 청년", 2.3, "%", "2024년 말 계약자", "40세 이하 청년 1인가구 2.3% 2,156가구"),
    ("영구임대 입주민", "1인가구 중 40~64세 독거 중장년", 32.6, "%", "2024년 말 계약자", "40~64세 독거 중장년 32.6% 30,593가구"),
    ("영구임대 입주민", "1인가구 중 65세 이상 독거 어르신", 65.1, "%", "2024년 말 계약자", "65세 이상 독거 어르신 65.1% 61,103가구"),
    ("영구임대 입주민", "65세 이상 독거 어르신 가구", 61103, "가구", "2024년 말 계약자", "65세 이상 독거 어르신 65.1% 61,103가구"),
    ("영구임대주택", "임대료 수준(시세 대비)", 30, "%", "-", "시중 시세 30% 수준으로 공급하는 전용면적 40㎡ 이하의 임대주택"),
    ("주거복지사 배치사업", "배치 인력", 1, "명/단지", "2025년", "단지별 1명(국가공인 '주거복지사' 자격증을 취득한 전문인력) 배치"),
    ("주거복지사 배치사업", "시범사업 단지", 15, "개소", "2019년", "2019년 LH 영구임대주택 주거복지사 배치 시범사업 시행(15개소)"),
    ("주거복지사 배치사업", "확대 단지(500세대 이상)", 111, "개소", "2023년", "2023년 500세대 이상 LH 영구임대주택으로 확대(111개소, 국비 지원)"),
]


def deployment(intro_text, master):
    rows = []
    for line in intro_text.split("\n"):
        m = ROW_RX.match(line.strip())
        if not m:
            continue
        for nm in m.group("names").split():
            rows.append(dict(region=m.group("region"), region_count=int(m.group("n")), name_in_book=nm))
    d = pd.DataFrame(rows)
    names = set(master["단지명"])
    id_of = dict(zip(master["단지명"], master["complex_id"]))
    br_of = dict(zip(master["단지명"], master["지사명"]))
    out = []
    for _, r in d.iterrows():
        nm = r["name_in_book"]
        if nm in names:
            out.append({**r, "complex_id": id_of[nm], "complex_name": nm, "match_type": "exact", "needs_review": 0, "candidate_similarity": 1.0})
            continue
        pool = master[master["지사명"].isin(REGION_BRANCH.get(r["region"], []))]["단지명"].tolist() or list(names)
        best = max(pool, key=lambda x: difflib.SequenceMatcher(None, nm, x).ratio()) if pool else None
        sim = difflib.SequenceMatcher(None, nm, best).ratio() if best else 0.0
        if best and sim >= 0.75:
            out.append({**r, "complex_id": id_of[best], "complex_name": best, "match_type": "candidate_similar_name", "needs_review": 1, "candidate_similarity": round(sim, 3)})
        else:
            out.append({**r, "complex_id": None, "complex_name": None, "match_type": "not_in_integrated_table", "needs_review": 0, "candidate_similarity": round(sim, 3)})
    out = pd.DataFrame(out)
    out["branch"] = out["complex_name"].map(br_of)
    return out


def facts(intro_text):
    flat = re.sub(r"\s+", " ", intro_text)
    rows = []
    for k, (topic, item, val, unit, asof, ev) in enumerate(FACTS):
        rows.append(dict(fact_id=f"F{k + 1:02d}", topic=topic, item=item, value=val, unit=unit, as_of=asof, evidence=ev, evidence_found=int(ev in flat),
                         source="주거복지사 활동 사례집(주택관리공단, 2025.7.11.) 앞부분"))
    return pd.DataFrame(rows)
