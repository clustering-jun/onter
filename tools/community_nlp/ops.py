# -*- coding: utf-8 -*-
"""운영 특성 5종(상시·정기·행사·수시·계절) 다중라벨 판정.

상태: Y 확정(원문 명시 또는 원문+일정 일치) / P 개연(일정·횟수·반복기록·유형 관행) / N 반증 / U 미확인.
원칙(v5): 기록 건수만으로 고정 주기를 확정하지 않고, 기간이 길다고 상시로 확정하지 않으며,
날짜가 특정 월이라는 사실만으로 계절형으로 보지 않는다. 연말 일괄 종료일은 행정 관행으로 보고 기간 증거에서 제외한다.
"""
import re
import pandas as pd

# ── 원문 단서(compact 텍스트용; 공백 없음) ──────────────────────────────────
RX_ALW = re.compile(r"상시|연중|항시|상설|365일|연중무휴|상시운영|상시제공|상시개방|상시접수|상시모집|늘열려|언제든|상주|지속운영|계속운영")
RX_REG_FREQ = re.compile(
    r"매주|매월|매달|매일|격주|격월|월\d+회|주\d+회|월간|주간|매분기|분기별|반기별|연\d+회|정례|정기적|주기적|"
    r"정기모임|정기회의|정기총회|정기\w{0,2}(방문|운영|상담|점검|진행|개최)|월례|\d+주간|(월|화|수|목|금)요일마다|매주(월|화|수|목|금)|"
    r"주\d회|월\d회|주1회|월1회|정기")
RX_SERIES = re.compile(r"(?<![\d월일])(제)?\d{1,2}(차시|차수|회차|차|기수)(?!례)")
RX_PERIOD_LABEL = re.compile(r"상반기|하반기|[1-4]분기|분기")
RX_FACILITY = re.compile(r"수거함|운영실|운영소|빨래방|도서관|공유냉장고|공유공구|쉼터|사랑방|상담실|무인|설치및운영|설치운영|운영")
RX_ADH = re.compile(
    r"수시|필요시|요청시|신청(세대|시|자|받아|한)|상황발생|발생시|민원(발생|접수|처리)|긴급(지원|복지|돌봄|상황|연락|출동)|즉시|사례발생|의뢰|희망(세대|자)|"
    r"필요한세대|필요에따라|수시로|상담요청|건별|그때그때|요청세대|발굴시|접수후|대상자발생")
RX_EVT = re.compile(
    r"행사|잔치|축제|대회|발대식|개소식|기념식|기념행사|박람회|바자회|운동회|한마당|페스티벌|페스타|문화제|전시회|공연|음악회|콘서트|"
    r"캠페인|설명회|나들이|체험|투어|견학|소풍|데이|day|의날|시상식|출범식|결의대회|경연|장기자랑|백일장|사생대회|발표회|환영식|위촉식|송년회|신년하례|위령제|점등식")
RX_SEA_STRONG = re.compile(
    r"설맞이|설날|설명절|설연휴|새해|신년|추석|한가위|명절|정월대보름|대보름|단오|동지|추수감사|세배|떡국|송편|윷놀이|연말|송년|크리스마스|성탄|"
    r"폭염|무더위|혹서|혹한|한파|여름철|겨울철|동절기|하절기|하계|동계|여름나기|겨울나기|월동|김장|초복|중복|말복|복날|삼계탕|봄맞이|봄꽃|벚꽃|"
    r"가을맞이|단풍|식목|장마|태풍|해빙기|환절기|난방|냉방|제설|낙엽|방학|(봄|여름|가을|겨울)(철|맞이|나기|꽃|소풍|나들이|캠프|준비)")
RX_SEA_WEAK = re.compile(r"예초|제초|풀뽑기|모종|파종|수확|김매기|연막소독|해충방제|방충|손바닥정원|꽃밭|식재|텃밭|도시농부|낙엽|제설|염화칼슘|동파|보온덮개|월동|장마|침수|호우|태풍|미세먼지|황사")
RX_CAL = re.compile(r"어버이날|어린이날|스승의날|부부의날|가정의달|노인의날|어르신의날|지구의날|에너지의날|국민안전의날|세계\w{1,6}(의날|날)|한글날|성년의날|식목일|장애인의날|경로의날|환경의날|물의날|보건의날|자원봉사자의날|소방의날|금연의날|치매극복의날|자살예방의날|독립|광복|현충")

FREQ_DAYS = [  # (패턴, 간격일, 라벨)
    (re.compile(r"매일"), 1, "매일"),
    (re.compile(r"주\d회|주1회|매주|주간|(월|화|수|목|금)요일마다"), 7, "주간"),
    (re.compile(r"격주"), 14, "격주"),
    (re.compile(r"월2회"), 15, "월2회"),
    (re.compile(r"월\d회|월1회|매월|매달|월간|월례"), 30, "월간"),
    (re.compile(r"격월"), 61, "격월"),
    (re.compile(r"매분기|분기별|[1-4]분기"), 91, "분기"),
    (re.compile(r"반기별|상반기|하반기"), 182, "반기"),
    (re.compile(r"연1회|연\d회|매년|연례"), 365, "연간"),
]

SEASON_MONTHS = {
    "명절": {1, 2, 3, 9, 10},
    "김장철": {10, 11, 12},
    "폭염/한파": {6, 7, 8, 9, 12, 1, 2},
    "절기": {1, 2, 3, 5, 6, 7, 8, 11, 12},
    "기념일": {4, 5, 6, 8, 9, 10},
    "기념일(4월)": {4},
    "봄/식목": {3, 4, 5, 10},
    "여름방역": {5, 6, 7, 8, 9},
}


def _date_stats(start, end):
    try:
        s = pd.Timestamp(start)
        e = pd.Timestamp(end)
    except Exception:
        return dict(days=None, single=False, anomalous=True, year_end=False, start_month=None)
    anomalous = (e < s) or (e.year >= 2027)
    days = None if anomalous else int((e - s).days) + 1
    # 연말 일괄 종료일 관행: 12-31 종료이면서 시작이 1-1이 아닌 경우 기간은 증거로 쓰지 않는다.
    year_end = (e.month == 12 and e.day == 31 and not (s.month == 1 and s.day == 1)) and (days is not None and days > 31)
    return dict(days=days, single=(days == 1), anomalous=anomalous, year_end=year_end, start_month=s.month)


def derive_ops(nc, cc, start, end, count, type_ops="", type_season="", rep=None, scope="PROGRAM"):
    """returns dict(state={ALW,REG,EVT,ADH,SEA}, basis={...}, interval_days, interval_label, series_no, period_label, calendar_tag, flags)"""
    n = nc + "|" + cc
    ds = _date_stats(start, end)
    days, single = ds["days"], ds["single"]
    cnt = int(count) if pd.notna(count) else None
    prior = set(x for x in (type_ops or "").split("+") if x)
    ev = {k: [] for k in ("ALW", "REG", "EVT", "ADH", "SEA")}
    st = {}

    m_alw = RX_ALW.search(n)
    m_reg = RX_REG_FREQ.search(n)
    m_ser = RX_SERIES.search(nc) or RX_SERIES.search(cc)
    m_per = RX_PERIOD_LABEL.search(nc)
    m_adh = RX_ADH.search(n)
    m_evt_n = RX_EVT.search(nc)
    m_evt = m_evt_n or RX_EVT.search(cc)
    m_sea = RX_SEA_STRONG.search(n)
    m_cal = RX_CAL.search(n)

    # ── 상시형 ──
    if m_alw:
        st["ALW"] = "Y"; ev["ALW"].append("text:" + m_alw.group(0))
    elif "ALW" in prior and not (single and m_evt) and ((days and days >= 14 and not ds["year_end"]) or RX_FACILITY.search(n)):
        st["ALW"] = "P"; ev["ALW"].append("type_prior+facility_or_period(%sd)" % days)
    elif single and (cnt is None or cnt <= 1):
        st["ALW"] = "N"; ev["ALW"].append("single_day")
    elif days is not None and days <= 2:
        st["ALW"] = "N"; ev["ALW"].append("short_period")
    elif m_evt and days is not None and days <= 31:
        st["ALW"] = "N"; ev["ALW"].append("dated_event")
    elif days is not None and days <= 31 and (cnt is None or cnt <= 3) and "ALW" not in prior and not m_reg:
        st["ALW"] = "N"; ev["ALW"].append("short_discrete_activity")
    else:
        st["ALW"] = "U"

    # ── 정기형 ──
    rep = rep or {}
    if m_reg:
        st["REG"] = "Y"; ev["REG"].append("text:" + m_reg.group(0))
    elif m_ser:
        st["REG"] = "P"; ev["REG"].append("series:" + m_ser.group(0))
    elif m_per:
        st["REG"] = "P"; ev["REG"].append("period_label:" + m_per.group(0))
    elif cnt and cnt >= 3 and days and days >= 14 and not ds["year_end"]:
        st["REG"] = "P"; ev["REG"].append("date_count(%d회/%dd)" % (cnt, days))
    elif rep.get("n", 0) >= 3 and rep.get("months", 0) >= 3 and rep.get("gap_med") is not None and rep["gap_med"] <= 100:
        st["REG"] = "P"; ev["REG"].append("repeat(%d records/%d months, gap_med=%dd)" % (rep["n"], rep["months"], rep["gap_med"]))
    elif "REG" in prior and ((cnt and cnt >= 3) or (cnt and cnt >= 2 and days and days >= 14 and not ds["year_end"])):
        st["REG"] = "P"; ev["REG"].append("type_prior+schedule")
    elif single and (cnt is None or cnt <= 1) and not m_reg and rep.get("n", 0) <= 2:
        st["REG"] = "N"; ev["REG"].append("one_off_record_no_cadence_cue")
    elif m_evt_n and days is not None and days <= 7 and (cnt is None or cnt <= 2) and rep.get("n", 0) <= 2:
        st["REG"] = "N"; ev["REG"].append("short_event_record")
    else:
        st["REG"] = "U"

    # ── 행사형 ──
    if m_evt and days is not None and days <= 7:
        st["EVT"] = "Y"; ev["EVT"].append("text:" + m_evt.group(0) + "+short_period")
    elif m_evt and days is None:
        st["EVT"] = "Y"; ev["EVT"].append("text:" + m_evt.group(0))
    elif m_evt:
        st["EVT"] = "P"; ev["EVT"].append("text:%s+long_period" % m_evt.group(0))
    elif scope in ("GOVERNANCE", "FACILITY_MGMT", "ADMIN"):
        st["EVT"] = "N"; ev["EVT"].append("scope_" + scope)
    elif (m_alw or m_reg) and not m_evt:
        st["EVT"] = "N"; ev["EVT"].append("continuous_cue_without_event_word")
    elif "EVT" in prior and days is not None and days <= 7 and (cnt is None or cnt <= 2):
        st["EVT"] = "P"; ev["EVT"].append("type_prior+short_period")
    elif "EVT" not in prior:
        st["EVT"] = "N"; ev["EVT"].append("service_type_without_event_word")
    else:
        st["EVT"] = "U"

    # ── 수시형 ──
    if m_adh:
        st["ADH"] = "Y"; ev["ADH"].append("text:" + m_adh.group(0))
    elif "ADH" in prior and not (single and (m_evt or m_ser)):
        st["ADH"] = "P"; ev["ADH"].append("type_prior")
    elif single or st["EVT"] in ("Y", "P") or st["REG"] in ("Y", "P"):
        st["ADH"] = "N"; ev["ADH"].append("planned_or_dated_activity")
    else:
        st["ADH"] = "U"

    # ── 계절형 ──
    cal_tag = ""
    if m_sea:
        st["SEA"] = "Y"; ev["SEA"].append("text:" + m_sea.group(0))
        w = m_sea.group(0)
        if re.search(r"설|추석|한가위|명절|대보름|단오|동지|추수감사|세배|떡국|송편|윷놀이", w):
            cal_tag = "명절"
        elif re.search(r"새해|신년|연말|송년|크리스마스|성탄", w):
            cal_tag = "연말연시"
        elif re.search(r"폭염|무더위|혹서|여름|하계|하절기|복날|삼계탕|초복|중복|말복|냉방|장마|태풍", w):
            cal_tag = "여름"
        elif re.search(r"혹한|한파|겨울|동절기|동계|월동|난방|김장|제설", w):
            cal_tag = "겨울"
        elif re.search(r"봄|벚꽃|식목|해빙", w):
            cal_tag = "봄"
        elif re.search(r"가을|단풍|낙엽", w):
            cal_tag = "가을"
        else:
            cal_tag = "계절"
    elif m_cal:
        st["SEA"] = "P"; ev["SEA"].append("calendar_day:" + m_cal.group(0)); cal_tag = "기념일"
    elif type_season and ds["start_month"] in SEASON_MONTHS.get(type_season, set()):
        st["SEA"] = "P"; ev["SEA"].append("type_season(%s)+month(%d)" % (type_season, ds["start_month"])); cal_tag = type_season
    elif RX_SEA_WEAK.search(n):
        mw = RX_SEA_WEAK.search(n)
        st["SEA"] = "P"; ev["SEA"].append("seasonal_work:" + mw.group(0)); cal_tag = "계절작업"
    elif len(n) >= 10 and not type_season:
        st["SEA"] = "N"; ev["SEA"].append("no_seasonal_cue")
    else:
        st["SEA"] = "U"

    # ── 간격 추정 ──
    interval, ilabel, ibasis = None, "", ""
    for rx, d, lab in FREQ_DAYS:
        if rx.search(n):
            interval, ilabel, ibasis = d, lab, "text"
            break
    if interval is None and cnt and cnt >= 2 and days and days > 1 and not ds["year_end"]:
        interval, ilabel, ibasis = round((days - 1) / (cnt - 1), 1), "일정추정", "date_count"

    flags = []
    if ds["anomalous"]:
        flags.append("date_anomaly")
    if ds["year_end"]:
        flags.append("year_end_default_end_date")
    if m_alw and single:
        flags.append("alw_text_vs_single_day")
    if st["EVT"] == "Y" and st["ALW"] == "Y":
        flags.append("evt_and_alw_both")
    if st["REG"] == "Y" and cnt is not None and cnt <= 1 and single and not m_ser:
        flags.append("reg_text_single_record")
    return dict(state=st, basis=ev, interval_days=interval, interval_label=ilabel, interval_basis=ibasis,
                series_no=(m_ser.group(0) if m_ser else ""), period_label=(m_per.group(0) if m_per else ""),
                calendar_tag=cal_tag, flags=flags, days=days, year_end=ds["year_end"], single=single)


def primary_op(st, basis):
    """주된 운영 유형(화면 표시용). 텍스트 근거 Y > 일정 근거 Y > P 순, 동률은 정기>상시>수시>행사>계절."""
    order = ["REG", "ALW", "ADH", "EVT", "SEA"]
    for lvl in ("Y", "P"):
        c = [k for k in order if st.get(k) == lvl]
        if c:
            if lvl == "Y" and len(c) > 1 and c[-1] == "SEA":
                c = [k for k in c if k != "SEA"] or c
            return c[0]
    return ""
