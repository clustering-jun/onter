# -*- coding: utf-8 -*-
"""LLM 라벨러(서브에이전트) 연동: 지침서 생성, 배치 파일 작성, 결과 수집·비교.
규칙 엔진의 결과는 라벨러에게 보여주지 않는다(블라인드). 라벨러는 원문을 직접 읽고 판단한다."""
import json
import os
import re
import random
import pandas as pd

from . import taxonomy as TX
from .std_programs import TYPES

OPS_KEYS = ["ALW", "REG", "EVT", "ADH", "SEA"]


def _hint(pat):
    toks = [t for t in re.split(r"\|", pat) if t and not re.search(r"[\\(\[\{]", t)]
    return ", ".join(toks[:9])


def write_guideline(path, include_ops=True, version="v1.1"):
    L = []
    L.append(f"# 커뮤니티 활동 구조화 라벨링 지침 (taxonomy_v1 / std_programs_v1, 지침 {version})\n")
    L.append("""당신은 한국어 공공임대주택 주거복지 커뮤니티 활동 기록을 읽고 구조화하는 라벨러입니다.
각 행은 [분야 | 원자료 커뮤니티유형 | 활동명 | 활동내용 | 기간 | 활동횟수 | 플래그]로 주어집니다.
**활동명과 활동내용을 함께 읽고 맥락으로 판단**하세요. 스크립트·정규식·키워드 자동 분류를 만들어 일괄 처리하지 말고, 행마다 직접 읽고 판단합니다.
원문에 없는 대상·효과·비용을 지어내지 않습니다. 근거가 부족하면 'U'(미확인) 또는 낮은 확신으로 표시합니다.
""")
    L.append("## 1. 범위(scope) — 이 기록이 무엇인가\n")
    for k, v in TX.SCOPES.items():
        L.append(f"- {k}: {v}")
    L.append("""
판정 요령: **scope는 선택한 std 유형 목록에 적힌 scope를 기본값으로 따릅니다.** 기록이 명백히 다른 성격일 때만 바꿉니다
(예: 특정 세대(동호수·위기세대) 개별 지원·사례관리 → HOUSEHOLD_SUPPORT, 회의·위원회·간담회·협의체·협약식 → GOVERNANCE,
직원·근로자·경비·미화원 대상 교육/건강/안전 → STAFF, 승강기·소방설비 점검·공사·보수 같은 시설 관리 업무 → FACILITY_MGMT,
표창·실적제출·공고·계약 등 서비스 제공이 없는 행정 기록 → ADMIN). 복지·행정 정보 안내·홍보(G06)와 안부·살피기(B02)는 PROGRAM입니다.
""")
    L.append("## 2. 표준 프로그램 유형(std) — 가장 핵심. 목록에서 하나를 고르세요\n")
    L.append("기준: **무엇을 제공하는가(핵심 서비스·행동)**로 정합니다. '고독사 예방·ESG·마을공동체·특화사업·우리동네' 같은 주제·사업명은 유형이 아니라 목적/사업 계열입니다. 활동명이 사업 포장어뿐이면 활동내용으로 판단합니다. '찾아가는'은 방식이지 유형이 아닙니다(찾아가는 결핵검진 → D01).")
    L.append("여러 서비스가 섞인 종합 이동상담(우리동네 복지상담소 등)은 G01. 어느 유형에도 맞지 않으면 std='NEW'와 new_name(짧은 한글 명칭)을 쓰고, 정보가 전혀 부족하면 std='Z99'.\n")
    fam = {}
    for t in TYPES:
        fam.setdefault(t["fam"], []).append(t)
    for f, ts in fam.items():
        L.append(f"### {f} {TX.FAMILIES[f]}")
        for t in ts:
            L.append(f"- {t['id']} | {t['name']} | scope={t['scope']} | 예: {_hint(t['pat'])}")
    L.append("""
### 유형이 겹칠 때의 우선 규칙(동점 해소)
- 명절·기념일·폭염·한파 + **취약세대(관리홈닥터 세대 포함) 방문·물품 전달** → B01. 관리홈닥터 세대의 정기 방문·점검·안부·밑반찬 같은 상시 돌봄 → B05. 명절·기념일 + **주민 공통 행사**(공연·식사·윷놀이·잔치) → A01/A02/A03.
- 정신건강 상담 + 자살예방 혼합: 활동명에 자살예방·생명존중이 있으면 E02, 아니면 E01. 여러 서비스가 섞인 이동상담·복지상담소 → G01.
- 행사·캠페인의 '주제'(탄소중립·ESG·고독사 예방·마을만들기)보다 **실제로 하는 일**(식재·만들기·수거·교육·검진 등)을 유형으로 고릅니다.
- 후원·기부 물품 전달: 식품·쌀 → C04, 그 외 물품 → C05(기업·단체의 후원 자체가 핵심이면 O05).
- 같은 활동이 두 유형에 걸치고 판단이 어려우면 활동내용에 더 구체적으로 나온 서비스를 고르고 conf를 M으로 합니다.
""")
    L.append("## 3. 복지 목적(주 1개 p1 + 부수 0~2개 p2)\n")
    for k, v in TX.PURPOSES.items():
        L.append(f"- {k}: {v}")
    L.append("\n## 4. 지원 대상(tg) — **원문에 명시된 대상만** (없으면 빈 목록 [])\n")
    for k, v in TX.TARGETS.items():
        L.append(f"- {k}: {v}")
    if include_ops:
        L.append("""
## 5. 운영 특성 5종(ops) — 다중라벨, 각 항목을 Y/P/N/U로 판정
값: Y 확정(원문 명시 또는 원문+일정 일치) / P 개연(일정·횟수·유형 관행 등 간접 근거) / N 반증(일정·원문이 해당 특성과 배치) / U 미확인(근거 부족).
- ALW 상시형: 원문에 상시·연중·상설·항시 제공이 명시되면 Y. 상설 시설·수거함·공유냉장고처럼 계속 운영되는 성격이고 기간이 길면 P. 하루짜리 기록이면 N. **기간이 길다는 이유만으로 Y 금지.**
- REG 정기형: 매주·매월·월 N회·격주·정기·분기별 등 반복 주기가 원문에 있으면 Y. N차/회차/상·하반기 표기, 활동횟수 3회 이상이 2주 이상 기간에 걸침 → P. 일회성 행사 기록이면 N. 근거 없으면 U. **기록 건수만으로 고정 주기 확정 금지.**
- EVT 행사형: 특정 행사(행사·잔치·축제·대회·공연·캠페인·설명회·체험 등)이고 개최 기간이 짧으면(약 7일 이하) Y, 행사지만 기간이 길면 P, 상시·정기 운영 서비스면 N, 근거 없으면 U. **모든 단일 기록을 행사로 분류하지 않음.**
- ADH 수시형: 요청·신청 발생 시, 상황별, 필요 시 제공이 명시되면 Y. 사례관리·민원·응급 대응처럼 성격상 수시이면 P. 날짜가 고정된 행사는 N. **일정을 모른다는 이유만으로 수시 판정 금지(U).**
- SEA 계절형: 명절·혹서·혹한·김장·특정 계절/절기 연동이 원문에 있으면 Y. 기념일(어버이날·지구의 날 등)이나 유형 관행이면 P. 계절 단서가 없으면 N. 판단 불가면 U. **날짜가 특정 월이라는 사실만으로 Y 금지.**
- 기록 시작·종료일이 연말(12/31)로 일괄 입력된 경우는 행정 관행일 수 있으니 기간 증거로 쓰지 않습니다.

## 6. 출력 형식 — 입력 행마다 JSON 한 줄(JSONL), 입력과 같은 행 수·같은 순서
{"r":<입력의 r>,"scope":"PROGRAM","std":"H01","new_name":"","p1":"P10","p2":["P09"],"tg":["ALL","ELD"],"ops":{"ALW":"N","REG":"U","EVT":"Y","ADH":"N","SEA":"P"},"conf":"H","why":"단지 대청소 행사"}
- conf: H(확실) / M(보통) / L(애매). why: 25자 이내 핵심 근거.
- 목록의 코드만 사용(std는 위 ID 또는 NEW/Z99). 큰따옴표 JSON만 출력(주석·설명 금지).
""")
    else:
        L.append("""
## 5. 출력 형식 — 입력 행마다 JSON 한 줄(JSONL), 입력과 같은 행 수·같은 순서 (운영 특성은 라벨링하지 않음)
{"r":<입력의 r>,"scope":"PROGRAM","std":"H01","new_name":"","p1":"P10","p2":["P09"],"tg":["ALL","ELD"],"conf":"H","why":"단지 대청소 행사"}
- conf: H(확실) / M(보통) / L(애매). why: 20자 이내 핵심 근거.
- 목록의 코드만 사용(std는 위 ID 또는 NEW/Z99). 큰따옴표 JSON만 출력(주석·설명 금지).
- tg는 원문에 대상이 **명시된 경우만** 적고(명시 없으면 []), '입주민'이 일반 행사의 수혜자로만 나오면 ALL을 쓰지 않습니다(ALL은 '전 세대·전체 입주민 대상'이 명시될 때).
""")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def make_batches(rows, source_rows, out_dir, batch_size, prefix="batch", seed=1):
    """rows: build_row_table 결과. 라벨러에게는 마스킹된 원문과 일정·횟수만 제공한다."""
    os.makedirs(out_dir, exist_ok=True)
    sub = rows[rows["source_row"].isin(list(source_rows))].copy()
    sub = sub.sample(frac=1.0, random_state=seed)
    paths = []
    for i in range(0, len(sub), batch_size):
        part = sub.iloc[i:i + batch_size]
        p = os.path.join(out_dir, f"{prefix}_{i // batch_size + 1:02d}.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for _, r in part.iterrows():
                flags = []
                if r["flag_culture_performance"]:
                    flags.append("문화예술공연=Y")
                if r["flag_mou"]:
                    flags.append("업무협약=Y")
                if r["flag_external_contest"]:
                    flags.append("외부공모=Y")
                d = dict(r=int(r["source_row"]), 분야=r["field"], 유형=r["raw_community_type"], 활동명=r["program_name_masked"],
                         활동내용=r["activity_content_masked"], 기간=f'{r["start_date"]}~{r["end_date"]}',
                         활동횟수=(None if pd.isna(r["activity_count"]) else int(r["activity_count"])), 플래그=",".join(flags))
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        paths.append(p)
    return paths


def read_annotations(paths):
    recs = []
    bad = []
    for p in paths:
        if not os.path.exists(p):
            bad.append((p, "missing"))
            continue
        with open(p, encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    recs.append(d)
                except Exception as e:
                    bad.append((p, f"line {ln}: {e}"))
    return recs, bad
