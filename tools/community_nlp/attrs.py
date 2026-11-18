# -*- coding: utf-8 -*-
"""원문 단서 기반 속성 추출: 지원 대상(명시/추정 분리)·협력기관·기대효과·필요자원·부수 목적·사업 계열.
원문에 없는 대상·효과·비용은 '유형 사전 추정'으로만 저장하고 원문 명시와 구분한다."""
import re
from .std_programs import BY_ID
from .taxonomy import PURPOSE_TO_NEED

# ── 지원 대상 단서(수혜 집단 기준) ───────────────────────────────────────
# 원문에 '수혜 집단'으로 명시된 경우만 explicit로 본다. 제공자·논의 안건·행사 참가 기관으로 언급된 단어는 제외한다.
TARGET_CUES = {
    "ELD1": r"독거|홀몸|홀로\s?(계신|사는)|혼자\s?(사는|계신)|독거노인|독거어르신|독거세대",
    "ELD": r"어르신|노인|고령|65세|경로(?!당)|시니어|실버|노년|할머니|할아버지|장수어르신|만65|75세|80세|60세이상",
    "VUL": r"취약계층|취약세대|취약가구|저소득|기초생활|수급|차상위|결식|한부모|조손|어려운이웃|소외계층|소외된|복지소외|생계곤란|저소득층",
    "DIS": r"장애인(?!\w{0,3}(인식|차별|인권))|장애세대|장애가구|보장구|휠체어|시각장애|청각장애|지체장애|발달장애|중증장애|난청",
    "CHD": r"아동|어린이|청소년|초등|학생|영유아|유아|방학|꿈나무|자녀|아이들|키즈|유치원|어린이집|돌봄교실|해피아이",
    "MID": r"중장년|중년|1인가구|독거\s?중년|독거남성|중년남성",
    "WOM": r"여성|엄마|맘카페|부녀|주부|산모|경력단절",
    "JOB": r"구직|취업|미취업|청년|실업|취준|재취업|일자리를?(찾|구)",
    "MUL": r"다문화|외국인|이주민|결혼이민|북한이탈|새터민|이주배경",
    "NEW": r"신규\s?입주|신규\s?세대|새이웃|신입주|입주\s?초",
    "CRI": r"위기가구|위기세대|저장강박|사례대상|정신질환|고독사\s?(세대|위험|고위험)|주거위기|퇴거위기|은둔|고립가구|고립\s?(세대|위험)",
    "STF": r"직원|근로자(?!배려)|경비원|미화원|종사자|용역직원|전직원|실무자",
    "VOL": r"(자원봉사자|봉사단|활동가|리더|지킴이)\w{0,3}(교육|양성|발대식|위촉|수료)|(교육|양성|위촉)\w{0,3}(활동가|리더|지킴이)",
    "ALL": r"전\s?세대|전체\s?세대|전체\s?입주|누구나|지역주민|모든\s?세대|모든\s?입주민",
}
_TARGET_RX = {k: re.compile(v.replace(r"\s?", "")) for k, v in TARGET_CUES.items()}
_AGE_RX = re.compile(r"(만)?(\d{2})세(이상|이하|미만)?")
# 제공자·주체로 쓰인 표현은 대상 판정 전에 지운다.
_PROVIDER_MASK = re.compile(r"주거복지사|사회복지사|복지관|복지센터|협의체위원|위원회|임차인대표")


def extract_targets(nc, cc, type_default, scope="PROGRAM"):
    """returns dict(explicit=[...], inferred=[...], basis=text|type_default|mixed|unknown, age=...)
    - 구체 대상이 하나라도 명시되면 ALL은 넣지 않는다(ALL은 '전체 입주민 대상'이 구체 대상 없이 명시된 경우).
    - GOVERNANCE 범위(회의·위원회)는 수혜 대상을 두지 않는다(STAFF 범위는 STF)."""
    text = _PROVIDER_MASK.sub("", nc + "|" + cc)
    ex = [k for k, rx in _TARGET_RX.items() if rx.search(text)]
    if scope == "GOVERNANCE":
        ex = []
    elif scope == "STAFF":
        ex = [k for k in ex if k in ("STF", "ALL")] or ["STF"]
        ex = [k for k in ex if k != "ALL"]
    if len([k for k in ex if k != "ALL"]) > 0 and "ALL" in ex:
        ex.remove("ALL")
    # 독거(ELD1)가 있으면 ELD는 별도 단서(어르신 등)가 있을 때만 유지: 이미 별도 정규식으로 판정
    inferred = [t for t in type_default if t not in ex]
    if ex and inferred:
        basis = "mixed"
    elif ex:
        basis = "text"
    elif inferred:
        basis = "type_default"
    else:
        basis = "unknown"
    age = ""
    m = _AGE_RX.search(cc) or _AGE_RX.search(nc)
    if m:
        age = m.group(0)
    return dict(explicit=ex, inferred=inferred, basis=basis, age=age)


# ── 협력기관(원문 언급) ────────────────────────────────────────────────────
ORG_CUES = {
    "OG01": r"시청|구청|군청|도청|행정복지센터|주민센터|동주민센터|읍사무소|면사무소|지자체|시의회|구의회|시니어일자리센터|보건복지부|자치구|광역시|특별시|시민과|시장님|군수|구청장",
    "OG02": r"보건소|보건기관|보건지소|보건진료소|정신건강복지센터|정신건강증진센터|치매안심센터|금연지원센터|결핵협회|건강증진센터|광역심리지원센터|심리지원센터",
    "OG03": r"복지관|복지센터|사회복지|복지재단|종합사회복지관|노인복지관|장애인복지관|자원봉사센터|다문화가족지원센터|가족센터|건강가정|지역아동센터|복지법인|무한돌봄",
    "OG04": r"지역사회보장협의체|보장협의체|지사협|복지협의체|마을보듬이|복지위원",
    "OG05": r"서민금융|신용회복|법률구조|근로복지공단|새일센터|고용센터|일자리센터|고용노동|한국장학재단|국민연금|건강보험|법무|변호사|노동청|주택금융|근로자건강센터|인력개발센터|여성인력개발",
    "OG06": r"푸드뱅크|푸드마켓|사랑의열매|공동모금회|월드비전|굿네이버스|해피빈|후원회|후원기관|아름다운가게",
    "OG07": r"교회|성당|사찰|불교|천주교|기독교|성결|종교|선교|목사|신부|스님|법당",
    "OG08": r"주식회사|㈜|\(주\)|기업|은행|증권|보험|삼성|현대|sk|lg|롯데|하나은행|농협|신한|우리은행|국민은행|nh|kb|esg|결연업체|1사1단지|운수|백화점|마트|홈플러스|이마트|cj|한화|포스코|kt|스타벅스|유한킴벌리|아모레|라이온스|로타리",
    "OG09": r"대학교|대학|학교|초등학교|중학교|고등학교|학과|교육청|사이버대",
    "OG10": r"새마을|부녀회|바르게살기|적십자|자원봉사|봉사단|통장|이장|청년회|직능|봉사회|청년회의소|여성단체|의용소방대",
    "OG11": r"소방서|소방|경찰|파출소|한전|한국전력|수자원공사|환경공단|가스공사|산림청|철도공사|코레일|건강보험공단|도로교통공단|농어촌공사|시설관리공단|교통안전공단|전기안전공사|가스안전공사|자연휴양림|산림복지|한국에너지공단|서울에너지공사",
    "OG12": r"병원|의원|한의원|치과|의료원|메디컬|약국|한방병원|의료기관|보건의료",
    "OG13": r"\blh\b|lh|한국토지주택공사|주택관리공단|주거복지사|관리홈닥터|지역본부|주택관리",
    "OG14": r"문화재단|예술단|문화원|문화센터|문화예술회관|극단|오케스트라|합창단|국악원|아트센터|문화복지|문화나눔|예술인|박물관",
    "OG15": r"노인회|경로당|노인정|노인복지|시니어클럽|노인종합|대한노인회|노인대학|노인일자리|양로원",
    "OG16": r"임차인대표|입주자대표|동대표|자생단체|자치회|자율방범대|주민자치|입주민봉사단|주민봉사단|마을공동체|주민협의|입주민자치|주민복지협의회",
}
_ORG_RX = {k: re.compile(v) for k, v in ORG_CUES.items()}


def extract_orgs(nc, cc):
    text = nc + "|" + cc
    hits = {}
    for k, rx in _ORG_RX.items():
        m = rx.search(text)
        if m:
            hits[k] = m.group(0)
    return hits  # code -> matched keyword


# ── 부수 목적 단서(원문 명시 기반) ─────────────────────────────────────────
PURPOSE_CUES = {
    "P03": r"고독사|고립|안부|외로움|고독|돌봄|살피",
    "P02": r"정서|우울|스트레스|정신건강|심리|마음건강|자살|생명존중|치유|힐링",
    "P01": r"건강|질환|질병|검진|치료|체조|운동|건강증진|예방접종",
    "P09": r"소통|화합|교류|공동체|이웃|친목|어울림|유대|관계",
    "P04": r"식사|반찬|도시락|식품|생필품|물품지원|쌀|김장|결식|식재료",
    "P05": r"금융|경제적|자립|대출|채무|부채|생계|관리비|체납|경제",
    "P06": r"일자리|취업|구직|창업|직업",
    "P07": r"교육|강좌|교실|학습|역량|문해|스마트폰|디지털|강의",
    "P08": r"문화|여가|취미|공연|예술|체험|여행|관람|스포츠",
    "P10": r"주거환경|청결|청소|위생|쾌적|방역|환경개선|정비|도배|수리",
    "P11": r"안전|화재|범죄|재난|사고예방|응급|소방|심폐|방범",
    "P12": r"환경보호|에너지|탄소|재활용|분리배출|자원순환|친환경|esg|기후",
    "P13": r"갈등|분쟁|층간소음|질서|예절|민원",
    "P14": r"정보제공|정보안내|상담|연계|제도안내|서비스안내",
    "P15": r"회의|협의|위원회|간담|의견수렴",
}
_PURPOSE_RX = {k: re.compile(v) for k, v in PURPOSE_CUES.items()}


def extract_purposes(nc, cc, type_pur):
    """type_pur: 'P01+P09'. 반환: primary, secondary(원문 단서 포함 최대 2), basis."""
    base = [p for p in type_pur.split("+") if p]
    primary = base[0] if base else ""
    sec = base[1:]
    text_cues = []
    cont = cc
    for k, rx in _PURPOSE_RX.items():
        if k == primary or k in sec:
            continue
        # 내용에서 2회 이상 또는 명칭에서 적중한 경우만 부수 목적으로 채택(잡음 억제)
        n_hit = len(rx.findall(cont))
        if rx.search(nc) or n_hit >= 2:
            text_cues.append((k, n_hit + (2 if rx.search(nc) else 0)))
    text_cues.sort(key=lambda x: -x[1])
    sec_text = [k for k, _ in text_cues[:max(0, 3 - 1 - len(sec))]]
    return dict(primary=primary, secondary=sec, secondary_text=sec_text)


def need_domains(purposes):
    out = []
    for p in purposes:
        n = PURPOSE_TO_NEED.get(p)
        if n and n not in out:
            out.append(n)
    return out


# ── 기대효과(원문 명시) ────────────────────────────────────────────────────
EFFECT_CUES = {
    "EF01": r"정서적?(안정|지지)|심리적?(안정|지지)|정서안정|고독감|외로움|우울감|고립감|고독사예방|사회적고립|말벗|마음의위안",
    "EF02": r"건강증진|건강(을)?유지|질병예방|조기발견|조기진단|건강관리|건강한삶|삶의질|면역|체력",
    "EF03": r"경제적(부담|지원|자립)|비용부담|생계(지원|부담)|가계|부담경감|부담을덜",
    "EF04": r"생활편의|불편해소|편의증진|불편을|편리",
    "EF05": r"공동체|소통|화합|유대|교류|이웃간|친목|어울림|관계형성|단절",
    "EF06": r"쾌적|위생|깨끗|청결|주거환경|환경개선|악취|해충",
    "EF07": r"안전사고|범죄예방|화재예방|재난|안전의식|안전확보|사고예방|낙상",
    "EF08": r"역량|지식|인식(제고|개선|향상)|능력|교육효과|이해도|정보격차",
    "EF09": r"탄소|환경보호|에너지절(감|약)|자원순환|온실가스|친환경|기후위기",
    "EF10": r"갈등(완화|해소|예방)|분쟁|질서|배려|민원감소",
    "EF11": r"정보(접근|제공)|서비스이용|복지서비스|접근성|이용촉진|연계",
    "EF12": r"문화향유|여가|취미|문화소외|문화생활|문화적",
}
_EFFECT_RX = {k: re.compile(v) for k, v in EFFECT_CUES.items()}


def extract_effects(nc, cc, type_default):
    text = nc + "|" + cc
    ex = [k for k, rx in _EFFECT_RX.items() if rx.search(text)]
    inferred = [e for e in type_default if e and e not in ex]
    return dict(explicit=ex, inferred=inferred)


# ── 필요 자원 ──────────────────────────────────────────────────────────────
RES_CUES = {
    "RS01": r"강사|전문가|전문요원|상담사|전문상담|의사|간호사|치료사|지도사|교수|전문인력",
    "RS02": r"협약|연계|유관기관|후원|지원받아|협업|합동|제휴|기관과|센터와|복지관과|보건소와|공단과",
    "RS03": r"봉사|자원봉사|봉사단|재능기부|자원활동",
    "RS05": r"경로당|회의실|광장|강당|도서관|커뮤니티센터|주민공동시설|어울림센터|공용공간|복지관",
    "RS06": r"물품|식재료|재료|키트|세트|꾸러미|선물|식품|반찬|쌀|용품",
    "RS07": r"버스|차량|이동식|이동\w{0,3}(상담|진료)|트럭",
    "RS10": r"기기|장비|측정기|로봇|스마트|수거함|설비|키오스크",
}
_RES_RX = {k: re.compile(v) for k, v in RES_CUES.items()}


def extract_resources(nc, cc, type_default):
    text = nc + "|" + cc
    ex = [k for k, rx in _RES_RX.items() if rx.search(text)]
    inferred = [r for r in type_default if r and r not in ex]
    return dict(explicit=ex, inferred=inferred)


# ── 사업 계열(우산) 및 데이터 맥락 ───────────────────────────────────────
FUNDING_CUES = re.compile(r"공모|지원사업|지원금|보조금|투자사업|사업비|국비|시비|도비|구비|기금|모금|후원금|특화사업")


# ── 제공 방식(원문 단서) ───────────────────────────────────────────────────
MODE_CUES = {
    "M1": r"세대방문|가정방문|방문하여|방문전달|댁방문|직접방문|방문서비스|방문상담|방문돌봄|세대를방문|방문점검|방문\w{0,2}(안부|서비스|전달)|가가호호|세대\w{0,2}방문",
    "M2": r"찾아가는|이동(상담|진료|식|세탁|빨래|도서관|검진|서비스|무료)|버스|출장|순회|이동\w{0,2}소|찾아\w{0,2}가",
    "M3": r"행사|교실|모임|교육|강좌|수업|체험|공연|잔치|대회|축제|워크숍|설명회|한마당|클래스|동아리",
    "M4": r"상설|수거함|빨래방|도서관|쉼터|공유냉장고|사랑방|문고|무인|운영실|운영소|센터운영|상담실|공부방운영",
    "M5": r"홍보|안내|게시|배포|리플렛|전단|안내문|포스터|현수막|방송|캠페인",
    "M7": r"(?<![a-z])ai(?![a-z])|인공지능|온라인|비대면|화상|스마트|로봇|키오스크|iot|돌봄플러그|앱",
    "M8": r"봉사단|자원봉사|동아리|자율방범|입주민\w{0,3}(주도|참여|봉사)|주민주도|회원|재능기부",
    "M9": r"전달|배달|배부|증정|지급|꾸러미|세트|도시락|반찬|선물|나눔",
    "M10": r"점검|순찰|모니터링|방범|확인|감시|관찰",
}
_MODE_RX = {k: re.compile(v) for k, v in MODE_CUES.items()}
_COOP_RX = re.compile(r"협약|연계|협업|후원|지원받|유관기관|합동|제휴|위탁|협력|기탁|공모")


def extract_modes(nc, cc, type_default, orgs, mou_flag, ext_contest_flag):
    text = nc + "|" + cc
    ex = [k for k, rx in _MODE_RX.items() if rx.search(text)]
    # 기관연계형: 협력기관 언급·협약·공모·후원 단서
    if (orgs and any(k not in ("OG13",) for k in orgs)) or mou_flag == "Y" or ext_contest_flag == "Y" or _COOP_RX.search(text):
        ex.append("M6")
    ex = [m for m in dict.fromkeys(ex)]
    inferred = [m for m in type_default if m not in ex]
    return dict(explicit=ex, inferred=inferred)


# ── 원문 수치 단서(자유 서술에서 추출; 검증되지 않은 관측) ─────────────────────
_NUM_PATS = {
    "households": re.compile(r"(\d{1,4})\s*(?:세대|가구)(?!수)"),
    "persons": re.compile(r"(\d{1,4})\s*(?:명|인)(?!분|가구)"),
    "kg": re.compile(r"(\d{1,5})\s*(?:kg|㎏|킬로)", re.I),
    "items": re.compile(r"(\d{1,4})\s*(?:개|대|포|박스|세트|장|채|점|권|병|팩)"),
    "won": re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)\s*(만|천)?\s*원"),
    "dates": re.compile(r"\d{1,2}\s*[/.]\s*\d{1,2}(?![\d])"),
    "sessions": re.compile(r"(\d{1,3})\s*(?:회차|차시|회)"),
}


def extract_numeric_mentions(name, content):
    """텍스트에 적힌 수혜 세대 수·인원·금액·물량·일자 표기·회차. 값이 없으면 None(0이 아님)."""
    t = f"{name} {content}"
    out = {}
    for k in ("households", "persons", "kg", "items", "sessions"):
        vals = [int(m.group(1)) for m in _NUM_PATS[k].finditer(t)]
        vals = [v for v in vals if v > 0]
        out[k] = max(vals) if vals else None
    won = []
    for m in _NUM_PATS["won"].finditer(t):
        v = float(m.group(1).replace(",", ""))
        if m.group(2) == "만":
            v *= 10000
        elif m.group(2) == "천":
            v *= 1000
        if v >= 1000:
            won.append(v)
    out["won"] = max(won) if won else None
    out["dates"] = len(_NUM_PATS["dates"].findall(t)) or None
    return out
