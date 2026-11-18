# -*- coding: utf-8 -*-
"""가상 예산 범위 추정(모델 가정값). 원자료에는 금액이 없으므로 '관측 사실'이 아니라 계획용 추정치로만 사용한다.

추정식: 1건의 직접 운영비(물품·재료·강사료·대관·식비 등, 시장가 기준) = (고정비 + 단가 × 유효 참여인원) × 회차계수
- 유효 참여인원: 참여인원_개인 > 0이면 개인, 아니면 (계 − 관리소), 그래도 0이면 계, 모두 0이면 유형별 기본값
- 회차계수: 회차·월 단위로 비용이 늘어나는 유형(교실·식사·방문·시설)만 활동횟수(최대 CAP)를 곱함
- 단지 부담 추정 = 시장가 추정 × 부담계수(소요비용분류·예산주체·외부기관 언급으로 판단)
금액 구간은 유형별 가정이며 실제 집행액·견적이 아니다. 학습 정답·비용 사실로 사용하지 않는다.
"""
import math

VERSION = "budget_assumptions_v1.0"

# 아키타입: (고정비_하한, 고정비_상한, 단가_하한, 단가_상한, 회차반영(per_session|per_month|none), 기본참여인원, 설명)
ARCH = {
    "NONE":        (0, 0, 0, 0, "none", 0, "비용 발생 없음/행정"),
    "INFO":        (0, 100_000, 0, 0, "none", 0, "정보 안내·홍보물 제작 소액"),
    "FREE_EXT":    (0, 50_000, 0, 1_000, "none", 20, "외부기관 무상 제공형(홍보·공간·다과 소액)"),
    "MEETING":     (0, 50_000, 0, 3_000, "none", 15, "회의·간담(다과)"),
    "CAMPAIGN":    (30_000, 300_000, 0, 1_000, "none", 30, "캠페인·홍보물·기념품"),
    "EVENT_S":     (100_000, 400_000, 3_000, 8_000, "none", 25, "소규모 모임·체험(재료·다과)"),
    "EVENT_FEAST": (200_000, 800_000, 6_000, 15_000, "none", 40, "명절·음식·기념 행사(식사·선물)"),
    "PERFORM":     (500_000, 3_000_000, 0, 0, "none", 0, "공연(출연료 시장가, 외부 제공 시 단지 부담 낮음)"),
    "GOODS":       (30_000, 100_000, 8_000, 30_000, "none", 20, "물품·식품 전달(수혜자 1인당 1만~3만원대)"),
    "MEAL":        (0, 30_000, 5_000, 9_000, "per_session", 10, "도시락·반찬 배달(1식 5천~9천원 × 회차)"),
    "MEAL_GROUP":  (50_000, 300_000, 5_000, 12_000, "none", 40, "급식·식사 대접"),
    "CLASS":       (50_000, 150_000, 1_000, 5_000, "per_session", 15, "강좌·교실(강사료 회당 + 재료비)"),
    "SCREEN_EXT":  (0, 150_000, 0, 3_000, "none", 30, "외부기관 검진·상담(단지는 공간·홍보 부담)"),
    "LIVING_EXT":  (0, 100_000, 0, 5_000, "none", 15, "봉사형 생활서비스(이미용 등) 소모품"),
    "LIVING_PAID": (100_000, 500_000, 5_000, 30_000, "none", 10, "방역·세탁 등 유상 서비스 대리"),
    "REPAIR":      (0, 100_000, 50_000, 300_000, "none", 3, "소규모 세대 수리·설치(세대당)"),
    "CLEAN":       (30_000, 300_000, 1_000, 5_000, "none", 30, "청소·정비(장갑·봉투·간식)"),
    "PLANT":       (200_000, 1_500_000, 2_000, 10_000, "none", 30, "식재·조경(묘목·화분·흙)"),
    "FACILITY":    (50_000, 400_000, 0, 0, "per_month", 0, "상설 시설·수거함·기기 운영(월 단위)"),
    "SAFETY_EDU":  (0, 200_000, 0, 2_000, "none", 30, "안전교육·훈련(외부강사 무상 다수)"),
    "VISIT":       (10_000, 100_000, 2_000, 15_000, "per_session", 8, "세대 방문 돌봄(물품·교통)"),
    "EXCURSION":   (200_000, 1_500_000, 10_000, 40_000, "none", 25, "나들이·여행·견학(차량·식비·입장료)"),
}
SESSION_CAP = 60
N_CAP = 400
EXTERNAL_ARCH = {"FREE_EXT", "SCREEN_EXT", "LIVING_EXT", "SAFETY_EDU"}


def effective_participants(total, indiv, staff, default_n):
    """returns (n, basis)"""
    total = 0 if total is None else total
    indiv = 0 if indiv is None else indiv
    staff = 0 if staff is None else staff
    if indiv > 0:
        return min(indiv, N_CAP), "individual"
    if total - staff > 0:
        return min(total - staff, N_CAP), "total_minus_staff"
    if total > 0:
        return min(total, N_CAP), "total"
    return default_n, "default"


def estimate(arch, count, days, total, indiv, staff, cost_class, subject, has_partner, mou_flag, scope="PROGRAM"):
    a = ARCH.get(arch, ARCH["NONE"])
    f_lo, f_hi, u_lo, u_hi, scale, d_n, _ = a
    if scope in ("GOVERNANCE", "ADMIN", "STAFF", "FACILITY_MGMT") and arch in ("NONE", "MEETING"):
        f_lo = f_hi = u_lo = u_hi = 0
    n, nb = effective_participants(total, indiv, staff, d_n)
    cnt = 1 if (count is None or count <= 0) else min(int(count), SESSION_CAP)
    if scale == "per_session":
        k = cnt
    elif scale == "per_month":
        k = max(1, min(24, int(math.ceil((days or 30) / 30.0))))
    else:
        k = 1
    low = (f_lo + u_lo * n) * k
    high = (f_hi + u_hi * n) * k
    mid = (low + high) / 2.0
    # 부담 주체 해석
    if cost_class in ("자체비용", "LH커뮤니티활동비") or subject in ("자체", "LH", "주택관리공단"):
        factor, burden = 1.0, "단지·LH·공단 부담(소요비용 기재, 금액 미상)"
    elif arch in EXTERNAL_ARCH or has_partner or mou_flag:
        factor, burden = 0.15, "외부 제공·후원 추정(단지 부담 낮음)"
    else:
        factor, burden = 0.5, "부담 주체 불명(기타·미기재)"
    return dict(low=round(low, -2), mid=round(mid, -2), high=round(high, -2), n_eff=n, n_basis=nb,
                sessions_used=k, burden=burden, factor=factor, burden_mid=round(mid * factor, -2))


def band(amount):
    if amount is None or amount != amount:
        return ""
    if amount <= 0:
        return "0원(비용 없음)"
    if amount < 100_000:
        return "10만원 미만"
    if amount < 500_000:
        return "10~50만원"
    if amount < 2_000_000:
        return "50~200만원"
    if amount < 10_000_000:
        return "200~1,000만원"
    return "1,000만원 이상"
