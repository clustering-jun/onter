# -*- coding: utf-8 -*-
"""연결: 기사 ↔ 단지(complex_id)·지사·지역(시도·시군구)·기관, 그리고 기사 관련도 분류.

단지 연결(사전 대조, 자동 확정은 정확 일치만)
- exact: 공백을 지운 본문에 단지명(예: 인천마전, 제천하소3)이 그대로 있고 바로 뒤가 숫자가 아님 → 확정(high)
- numbered_base: '단지명 기본형(숫자 뗀 것)+[주공]+숫자+단지/관리소/센터' 꼴에서 숫자로 하나가 정해짐 → 확정(high)
- base_only: 기본형만 맞고 숫자가 없거나 단지가 여럿 → 후보(needs_review, 자동 확정 안 함)
이름 추정 연결을 자동 확정하지 않는 원칙은 해피콜 관리소 연결과 같다.
"""
import re

import pandas as pd

SIDO = {"서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시", "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시",
        "세종": "세종특별자치시", "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도", "전북": "전북특별자치도", "전남": "전라남도",
        "경북": "경상북도", "경남": "경상남도", "제주": "제주특별자치도"}
SIDO_RX = re.compile(r"(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|경기도|강원(특별자치)?도|충청북도|충청남도|"
                     r"전북특별자치도|전라북도|전라남도|경상북도|경상남도|제주(특별자치)?도)")

ACTOR_RX = {
    "KOHOM": re.compile(r"주택관리공단|KOHOM|주거행복지원센터|마이홈\s?센터|관리홈닥터"),
    "LH": re.compile(r"한국토지주택공사|\bLH\b|LH(?=[가-힣\s])"),
    "LOCAL_GOV": re.compile(r"[가-힣]{1,4}(시청|구청|군청)|[가-힣]{1,4}(특별)?시는|[가-힣]{1,4}구는|[가-힣]{1,4}군은|행정복지센터|주민센터|보건소|치매안심센터|[가-힣]{1,4}동은"),
    "PUBLIC_CORP": re.compile(r"도시공사|시설관리공단|심사평가원|공공기관|혈액원|진흥원|노인인력개발원"),
    "WELFARE_ORG": re.compile(r"사회복지관|복지관|복지재단|시니어클럽|지역아동센터|노인일자리|사회복지협의회|자원봉사센터"),
    "HEALTH": re.compile(r"병원|금연지원센터|보건소|치매안심센터|정신건강"),
    "COMPANY": re.compile(r"카드|㈜|\(주\)(?!\s*대전)|kt\s?cs|기업|은행"),
    "UNIVERSITY": re.compile(r"대학교|대학(?!원)|총학생회"),
}
SETTING_RX = re.compile(r"공공임대|임대주택|영구임대|국민임대|임대아파트|입주민|단지|관리소|주공")
PARTNERSHIP_RX = re.compile(r"업무협약|협약식|MOU|협약을\s?체결|맞손|손잡")
ORG_NAME_RX = re.compile(r"(?:[가-힣A-Za-z0-9]{1,15}\s?)?[가-힣A-Za-z0-9]{1,15}"
                         r"(종합사회복지관|사회복지관|노인종합복지관|복지관|복지재단|주거행복지원센터|마이홈\s?센터|관리소|지사|지역단|공단|도시공사|시설관리공단|보건소|치매안심센터|"
                         r"금연지원센터|시니어클럽|대학교|병원|협의체|봉사단|연합회|협회|진흥원|개발원|혈액원|심사평가원|행정복지센터|지역아동센터|재단)(?=[\s,·)(은는이가과와의에도을를]|$)")


def compact(s):
    return re.sub(r"\s+", "", str(s or ""))


class ComplexMatcher:
    def __init__(self, master):
        self.m = master[["complex_id", "단지명", "지사명", "기본주소"]].copy()
        self.names = sorted(self.m["단지명"].tolist(), key=len, reverse=True)
        self.id_of = dict(zip(self.m["단지명"], self.m["complex_id"]))
        base = self.m["단지명"].str.replace(r"[\d\-,]+$", "", regex=True).str.replace(r"\(.*?\)", "", regex=True)
        self.m["base"] = base
        self.bases = self.m.groupby("base")["단지명"].apply(list).to_dict()
        self.branches = sorted(self.m["지사명"].unique(), key=len, reverse=True)
        self.sigungu = {}
        for a in self.m["기본주소"].dropna():
            t = a.split()
            if len(t) >= 2 and re.search(r"(시|군|구)$", t[1]):
                self.sigungu[t[1]] = t[0]

    def complexes(self, text):
        c = compact(text)
        hits, taken = [], []
        for nm in self.names:                                    # 긴 이름부터(인천삼산4가 인천삼산보다 먼저)
            if len(nm) < 3:
                continue
            for mt in re.finditer(re.escape(nm), c):
                s, e = mt.span()
                if e < len(c) and c[e].isdigit():
                    continue
                if any(s >= a and e <= b for a, b in taken):
                    continue
                taken.append((s, e))
                hits.append(dict(complex_id=self.id_of[nm], complex_name=nm, mention=c[max(0, s - 4):e + 6], match_type="exact", confidence="high", needs_review=0))
                break
        found = {h["complex_id"] for h in hits}
        for b, nms in self.bases.items():
            if len(b) < 3:
                continue
            for mt in re.finditer(re.escape(b) + r"(주공)?(\d+)?(단지|관리소|아파트|주거행복지원센터|센터)", c):
                if any(mt.start() >= a and mt.end() <= z for a, z in taken):
                    continue
                num = mt.group(2)
                cands = [n for n in nms if (num and re.sub(r"\D", "", n.replace(b, "")) == num)] if num else []
                if len(cands) == 1:
                    cid = self.id_of[cands[0]]
                    if cid not in found:
                        hits.append(dict(complex_id=cid, complex_name=cands[0], mention=mt.group(0), match_type="numbered_base", confidence="high", needs_review=0))
                        found.add(cid)
                else:
                    for n in nms:
                        cid = self.id_of[n]
                        if cid not in found:
                            hits.append(dict(complex_id=cid, complex_name=n, mention=mt.group(0), match_type="base_only", confidence="low", needs_review=1))
                            found.add(cid)
                taken.append(mt.span())
        return hits

    def branch(self, text):
        c = compact(text)
        out = [b for b in self.branches if b in c]
        out += [b for b in ["경기지사"] if "경기지사" in c and b not in out]     # 옛 명칭(경기남부·북부 분리 전)
        return out

    def regions(self, text):
        sido = set()
        for mt in SIDO_RX.finditer(text):
            sido.add(mt.group(0).replace("전라북도", "전북특별자치도").replace("강원도", "강원특별자치도").replace("제주도", "제주특별자치도"))
        for k, v in SIDO.items():
            if re.search(rf"(^|[\s\[(]){k}(\s|[가-힣]{{1,3}}(시|구|군)\b)", text):
                sido.add(v)
        sg = sorted({g for g in self.sigungu if re.search(rf"(^|[\s(]){re.escape(g)}", text) or re.search(rf"{re.escape(g[:-1])}(시|군|구)(는|가|청|의|\s)", text)})
        for g in sg:
            sido.add(self.sigungu[g])
        return sorted(sido), sg


def actors(text):
    return [k for k, rx in ACTOR_RX.items() if rx.search(text)]


def org_names(text):
    seen, out = set(), []
    for mt in ORG_NAME_RX.finditer(text):
        n = re.sub(r"\s+", " ", mt.group(0)).strip()
        if len(n) < 4 or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def relevance(title, body, acts, n_complex):
    """A 공단 단지 현장 / B 공단 협약·사업 / C 다른 공공임대(LH 등) / D 지역 복지(주거취약 대상) / E 관련 낮음"""
    t = title + "\n" + body
    kohom, setting, partner = "KOHOM" in acts, bool(SETTING_RX.search(t)), bool(PARTNERSHIP_RX.search(t))
    if kohom and (n_complex > 0 or re.search(r"관리소|주거행복지원센터|단지", t)) and not (partner and n_complex == 0):
        return "A_kohom_complex_activity"
    if kohom:
        return "B_kohom_partnership_or_branch"
    if "LH" in acts or (setting and re.search(r"임대주택|공공임대|영구임대|주공", t)):
        return "C_other_public_housing"
    if re.search(r"취약계층|독거|주거취약|저소득|어르신|주거급여|복지", t):
        return "D_community_welfare"
    return "E_low_relevance"
