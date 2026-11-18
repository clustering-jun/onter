# -*- coding: utf-8 -*-
"""신호 추출: 대상·목적·필요 영역(커뮤니티 NLP 사전), 수량(인원·가구·물품·금액), 행사일 추정, 취약 신호(문장 근거), 개인정보 가리기."""
import re
from datetime import date, timedelta

from community_nlp import attrs, taxonomy as TX
from community_nlp.text_utils import compact

# 취약 신호 사전: 기사 문장에 나타난 '어려움'의 단서. 필요 영역(N1~N6)과 연결해 두며, 개인 판정이 아니라 기사 서술의 분류다.
VULN = {
    "V_ALONE": ("홀로 사는·독거", "N1", r"독거|홀몸|홀로\s?(사는|지내|생활)|1인\s?가구|혼자\s?(사는|지내)"),
    "V_ISOLATION": ("사회적 고립·외로움", "N1", r"고립|외로움|외롭|단절|은둔|교류가?\s?(없|적)|우울감"),
    "V_LONELY_DEATH": ("고독사 위험(서술)", "N1", r"고독사"),
    "V_POVERTY": ("경제적 어려움", "N2", r"저소득|기초생활|수급(자|가구)|생계|빈곤|체납|형편이?\s?어려|생활이\s?어려|취약계층|사회\s?보호계층"),
    "V_FOOD": ("먹거리·생필품 부족", "N2", r"결식|끼니|먹거리|식생활\s?안정|생필품"),
    "V_HEALTH": ("건강 악화·질환", "N3", r"뇌경색|질환|투병|건강이?\s?악화|거동(이)?\s?불편|와상|만성"),
    "V_DEMENTIA": ("치매", "N3", r"치매"),
    "V_DISABILITY": ("장애", "N3", r"장애인|장애가?\s?있"),
    "V_MENTAL": ("정신건강", "N3", r"우울|자살|정신건강|스트레스|코로나19?\s?블루"),
    "V_OLD_AGE": ("고령·초고령", "N3", r"초고령|고령층|100세|최고령|고령\s?(어르신|입주민)"),
    "V_HOUSING": ("열악한 주거환경", "N4", r"주거환경이?\s?(매우\s?)?열악|노후|곰팡이|누수|도배|장판|주거\s?취약|쪽방|연탄"),
    "V_SAFETY": ("안전 위험(화재·재난)", "N4", r"화재|소방차|진입하기\s?어려|폭염|무더위|한파|재난|낙상|사고\s?예방"),
    "V_DIGITAL": ("디지털 소외", "N6", r"디지털\s?(소외|격차|사각)|키오스크|스마트폰\s?(활용|교육)"),
    "V_JOB": ("일자리·소득 부족", "N6", r"일자리\s?부족|노인빈곤|구직|취업\s?(지원|알선)"),
    "V_ACCESS": ("서비스 접근 어려움", "N1", r"접근성|문턱|사각지대|찾아가는|방문하기\s?어려|이용하는\s?데\s?(물리적|심리적)?\s?부담|발굴"),
}
VULN_RX = {k: re.compile(v[2]) for k, v in VULN.items()}
QTY_RX = re.compile(r"(?P<what>[가-힣A-Za-z]{1,8})?\s?(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?(?P<approx>여)?\s?(?P<unit>명|가구|세대|가정|장|대|개|포기|kg|킬로그램|박스|상자|세트|그릇|인분|만\s?원|억\s?원|원|곳|회|차|기관)")
UNIT_KIND = {"명": "persons", "가구": "households", "세대": "households", "가정": "households", "곳": "places", "기관": "orgs", "회": "sessions", "차": "sessions"}
MONEY = {"원": 1, "만원": 1e4, "만 원": 1e4, "억원": 1e8, "억 원": 1e8}
TITLE_AFTER = r"(센터장|관장|사장|지사장|소장|이사장|회장|대표이사|대표|의원|부총장|총장|국장|본부장|팀장|과장|대리|원장|구청장|시장|군수|교수|신부|단장|위원장|기자)"
# 앞보기(lookahead)만 써서 한 이름 판정이 뒤의 다른 이름을 삼키지 않게 한다(예: '임직원 20여명과 함진규 의원')
NAME_BEFORE_TITLE = re.compile(rf"(?<![가-힣\]])([가-힣]{{2,3}})(?=\s(?:[가-힣A-Za-z0-9()]+\s){{0,2}}[가-힣A-Za-z0-9]*{TITLE_AFTER})")
TITLE_THEN_NAME = re.compile(rf"({TITLE_AFTER}[:\s]\s?)([가-힣]{{2,3}})(?=[\s,)·]|$)")
PHONE = re.compile(r"(?:\(?0\d{1,2}\)?[-\s.]?\d{3,4}[-\s.]?\d{4}|1[5-9]\d{2}-\d{4})")
EMAIL = re.compile(r"[\w.\-]+@[\w\-]+\.[\w.]+")
NOT_NAME = {"주택관", "관리공", "지역사", "앞으로", "공단", "이날", "센터", "복지관", "한편", "특히", "또한", "이어", "지난", "우리", "모든", "전체", "이번", "올해", "행사",
            "당시", "이후", "현재", "해당", "관내", "지역", "단지", "마을", "주민", "직원", "임직원", "어르신", "입주민", "함께", "오늘", "기관", "협회", "그리고", "참석",
            "각종", "등과", "아울러", "이에", "최근", "향후", "평소", "직접", "많은", "여러", "다양한", "모두", "공사", "지사", "이사", "부사", "부장", "실장", "그는", "주최",
            "센터는", "사업", "본부", "협의", "재단", "관리", "경영", "노조", "대표", "회의", "위원", "관리소", "마이홈", "복지", "노인", "보건소", "구청", "시청",
            "군청", "협력", "연합회", "공단의", "단지의", "학교", "대학", "병원", "기업", "전문", "담당", "총괄", "수석", "명예", "초대", "신임", "전임", "현직"}
# 대상 판정 전에 지우는 기관명(예: '여성새로일하기센터'의 '여성', '다문화가족지원센터'의 '다문화'가 대상으로 잡히지 않게)
TARGET_ORG_MASK = re.compile(r"[가-힣0-9·]{2,15}(센터|협회|연합회|재단|클럽|본부|협의체|위원회|연구원|진흥원|개발원)")


def mask_text(t):
    t = PHONE.sub("[전화]", t)
    t = EMAIL.sub("[이메일]", t)
    t = TITLE_THEN_NAME.sub(lambda m: m.group(1) + ("[이름]" if _is_name(m.group(2)) else m.group(2)), t)
    t = NAME_BEFORE_TITLE.sub(lambda m: "[이름]" if _is_name(m.group(1)) else m.group(1), t)
    return t


def _is_name(w):
    """사람 이름으로 볼 2~3글자인지: 불용어·조사·어미로 끝나는 말(넘게·참석한·끝난 등)은 이름이 아니다."""
    return w not in NOT_NAME and not w.endswith(("는", "은", "이", "가", "의", "와", "과", "게", "고", "한", "을", "를", "에", "서", "며", "던", "된", "난",
                                                    "운", "적", "들", "로", "도", "만", "요", "다", "히", "께", "랑", "인", "른", "할", "될", "였"))


def labels(code_map, codes):
    return [code_map.get(c, c) for c in codes]


def semantic(title, body, type_pur=""):
    """대상(원문 명시)·기관 유형·목적(유형 기본 + 원문 단서)·필요 영역·기대효과(원문 단서)."""
    nc, cc = compact(title), compact(body)
    tg = attrs.extract_targets(compact(TARGET_ORG_MASK.sub(" ", title)), compact(TARGET_ORG_MASK.sub(" ", body)), "")
    tg["explicit"] = [t for t in tg["explicit"] if t not in ("STF", "VOL")]      # 직원·봉사자는 제공자이지 수혜 대상이 아니다
    orgs = attrs.extract_orgs(nc, cc)
    pur = attrs.extract_purposes(nc, cc, type_pur)
    purs = [p for p in [pur.get("primary")] + list(pur.get("secondary") or []) + list(pur.get("secondary_text") or []) if p]
    purs = list(dict.fromkeys(purs))
    effects = [k for k, rx in attrs._EFFECT_RX.items() if rx.search(nc + "|" + cc)]
    return dict(targets=tg["explicit"], orgs=sorted(orgs), purposes=purs, needs=attrs.need_domains(purs), effects=effects)


def quantities(text):
    out = []
    for mt in QTY_RX.finditer(text):
        unit = re.sub(r"\s", "", mt.group("unit"))
        num = float(mt.group("num").replace(",", ""))
        kind = UNIT_KIND.get(unit, "money" if "원" in unit else "items")
        if kind == "money":
            num *= MONEY.get(unit, 1)
        ctx = text[max(0, mt.start() - 20): mt.end() + 10]
        if re.search(r"\d{4}년|\d+월|\d+일|제\d+회|\d+주년|\d+층|\d+동|\d+단지", text[max(0, mt.start() - 2): mt.end() + 2]) and kind in ("sessions", "items"):
            continue
        out.append(dict(kind=kind, value=num, unit=unit, approx=int(bool(mt.group("approx"))), what=(mt.group("what") or "").strip(), context=ctx.replace("\n", " ")))
    return out


def event_date(text, published):
    """'지난 6일'·'6일'·'11월 4일' 꼴에서 행사일 추정(게시일보다 앞선 가장 가까운 날)."""
    try:
        pub = date.fromisoformat(str(published)[:10])
    except Exception:
        return None, None
    m = re.search(r"(\d{1,2})월\s?(\d{1,2})일", text)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        for y in (pub.year, pub.year - 1):
            try:
                c = date(y, mo, d)
            except ValueError:
                continue
            if c <= pub + timedelta(days=1):
                return c.isoformat(), "month_day"
    m = re.search(r"(지난|오는)?\s?(\d{1,2})일", text)
    if m:
        d = int(m.group(2))
        for back in range(0, 3):
            y, mo = pub.year, pub.month - back
            while mo <= 0:
                mo += 12
                y -= 1
            try:
                c = date(y, mo, d)
            except ValueError:
                continue
            if c <= pub + timedelta(days=1):
                return c.isoformat(), "day_only"
    if "최근" in text:
        return None, "recent_unspecified"
    return None, None


def vulnerability(sentences):
    rows = []
    for k, s in enumerate(sentences):
        for code, rx in VULN_RX.items():
            mt = rx.search(s)
            if mt:
                rows.append(dict(sent_idx=k, code=code, label=VULN[code][0], need_domain=VULN[code][1], cue=mt.group(0), sentence=s[:220]))
    return rows
