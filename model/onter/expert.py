"""전문가 검토 응답(expert_request/온터_전문가_검토요청(완료).xlsx) 로더.

쓰임의 한계(05_expert_label_request.md)
- 평가자 1명의 응답이다. 평가자 간 일치도를 잴 수 없으므로 '정답'이 아니라 '한 전문가의 판단'으로 다룬다.
- 순위 모델을 이 응답으로 학습시키지 않는다. 평가, 조절값 점검, 실행 요건(비용·인력·공간·협력기관) 교체에만 쓴다.
"""
import re
import numpy as np
import pandas as pd
from . import config as C, data as D

DIR = C.ROOT / "expert_request"
FILE = DIR / "온터_전문가_검토요청(완료).xlsx"
KEY = DIR / "pool_key.csv"            # 평가ID → 단지·프로그램·후보를 낸 방법(전문가에게 보내지 않은 파일)
RANKS = DIR / "pool_ranks.csv"        # 요청 당시 네 방법의 상위 5개 순위(기본값이 바뀌어도 평가가 흔들리지 않게 고정)
PLACE_BY_LABEL = {"세대 방문": "home", "경로당": "senior", "복지관": "welfare", "관리동·회의실·커뮤니티실": "hall", "단지 밖": "offsite", "단지 안 야외·공용부": "onsite"}
INTERNAL = {"단지", "공단", "LH"}       # 비용 부담 주체 가운데 공단 쪽 재원


def available():
    return FILE.exists() and KEY.exists()


def _split(s):
    return [x.strip() for x in re.split(r"\s*/\s*", str(s)) if x.strip() and x.strip() != "nan"]


def sheet_a():
    """단지×프로그램 평가: need(0~3), feas(0~3), y(우선 추천 1/0)와 단지·프로그램 ID, 후보를 낸 방법."""
    a = pd.read_excel(FILE, sheet_name="A_단지프로그램평가")
    a.columns = ["eval_id", "complex", "branch", "desc", "hist", "program", "pdesc", "need", "feas", "yn", "memo"]
    k = pd.read_csv(KEY)
    a = a.merge(k, on="eval_id", how="left", validate="1:1")
    a["y"] = (a["yn"].astype(str).str.upper().str.strip() == "Y").astype(int)
    return a[["eval_id", "complex_id", "complex", "std_id", "program", "sources", "need", "feas", "y"]]


def sheet_b():
    """프로그램 실행 요건(전문가 값). 색인 std_id."""
    b = pd.read_excel(FILE, sheet_name="B_프로그램실행요건")
    b.columns = ["std_id", "name", "domain", "d_cost", "d_staff", "d_place", "d_partner", "cost", "payer", "staff", "space", "partner", "nowelf", "diff", "memo"]
    og = {v: k for k, v in D.codebook()["partner_org"].items()}
    out = pd.DataFrame(index=b["std_id"])
    out["x_cost_session"] = b["cost"].to_numpy() * 1e4                       # 1회 실제 비용(원)
    out["x_staff_hours"] = b["staff"].to_numpy().astype(float)               # 1회 필요 인력(명×시간)
    out["x_difficulty"] = b["diff"].to_numpy().astype(float)                 # 1 쉬움 ~ 5 어려움
    out["x_needs_welfare_worker"] = (b["nowelf"].astype(str).str.upper().str.strip() == "N").to_numpy().astype(int)
    pay = [_split(s) for s in b["payer"]]
    w = lambda n: np.array([1 / (i + 1) for i in range(n)]) / sum(1 / (i + 1) for i in range(n))      # 먼저 적은 주체가 더 많이 부담한다고 본다(가정)
    out["x_internal_share"] = [float(sum(wi for p, wi in zip(ps, w(len(ps))) if p in INTERNAL)) if ps else np.nan for ps in pay]
    out["x_payers"] = ["|".join(ps) for ps in pay]
    out["x_places"] = ["|".join(PLACE_BY_LABEL[x] for x in _split(s) if x in PLACE_BY_LABEL) for s in b["space"]]
    out["x_partners"] = ["|".join(og[x] for x in _split(s) if x in og) for s in b["partner"]]
    out["x_self_run"] = [int("없음" in str(s)) for s in b["partner"]]
    return out


def sheet_c():
    """필요 지표의 적절성(0~3). m1_profile.INDICATORS와 같은 순서로 만들었으므로 순서로 맞춘다."""
    from . import m1_profile as M1
    c = pd.read_excel(FILE, sheet_name="C_필요지표")
    keys = [(d, v, col, w, lab) for d in C.NEED_IDS for v in ("S", "E") for col, _, w, lab in M1.INDICATORS[d][v]]
    assert len(keys) == len(c) and all(k[4] == lab for k, lab in zip(keys, c["지표"])), "C 시트 순서가 지표 정의와 다르다"
    return pd.DataFrame(keys, columns=["domain", "variant", "col", "weight", "label"]).assign(rating=c.iloc[:, 5].to_numpy().astype(float))


def sheet_d():
    """단지별 여섯 분야 100점 배분(합 1로 바꿈). 색인 complex_id."""
    d = pd.read_excel(FILE, sheet_name="D_단지필요분야")
    ids = sheet_a().drop_duplicates("complex").set_index("complex")["complex_id"]
    pts = d.iloc[:, 2:8].astype(float)
    pts.columns = C.NEED_IDS
    pts.index = d["단지"].map(ids)
    return pts.div(pts.sum(axis=1), axis=0), pd.Series(d.iloc[:, 9].to_numpy(), index=pts.index, name="memo")
