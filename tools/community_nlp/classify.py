# -*- coding: utf-8 -*-
"""표준 프로그램 유형 분류 — 명칭·활동내용을 함께 읽는 사전·규칙 기반 판정 (근거 문자열 보존).

점수 = 명칭 적중(유형 명확도별 가중) + 활동내용 적중 + 주제어(theme) 적중 + 약한 사전분포 보정.
정렬 = 점수 + prio/100 (동점대에서만 prio가 작동). 우산 사업명·보고 접미는 가린 명칭에서 판정한다.
"""
from .std_programs import TYPES, BY_ID, SPEC_W
from .taxonomy import RAW_TYPE_PRIOR
from .text_utils import compact, mask_for_match, umbrella_tags
import re

FIELD_PRIOR_BONUS = 0.15      # 원자료 커뮤니티유형과 같은 가족 → 동점 보조
SAFETY_FIELD_BONUS = 0.15     # 분야=주거안전 → F09/F07 보조
PERF_FLAG_BONUS = 0.6         # 문화예술공연여부=Y → K01
SEC_MIN_PRIO = 56             # 활동내용에서만 잡힌 보조 유형의 최소 prio(명확한 서비스명만)
THEME_W = (1.2, 0.4)

_HOUSEHOLD_CUE = re.compile(r"홈닥터|취약계층|취약세대|소외계층|소외된|저소득|독거|거동불편|수급자|가정방문|세대방문|세대를?방문|방문하여|방문전달|댁방문|돌봄세대|대상세대|대상자")
_PARENTS_DAY = re.compile(r"카네이션|어버이날|경로잔치|효잔치|경로효")
_COMMUNITY_EVENT_CUE = re.compile(r"공연|윷놀이|식사대접|잔치|경로당에서|한마당|다과회|행사참석|초청|합동|모시고")


def _first(rx, text):
    m = rx.search(text)
    return m.group(0) if m else None


def score_types(name, content, raw_type="", field="", perf_flag=""):
    nc = compact(name)
    nm = mask_for_match(nc)
    cc = mask_for_match(compact(content))   # 내용의 사업 포장어도 가림
    name_any = False
    rows = []
    for t in TYPES:
        if t["_x"] and t["_x"].search(nc):
            continue
        hn = None
        for rx in (t["_pat"], t["_n"]):
            if rx is not None:
                hn = _first(rx, nm)
                if hn:
                    break
        hc = None
        if not (t["_xc"] and t["_xc"].search(cc)):
            for rx in (t["_pat"], t["_c"]):
                if rx is not None:
                    hc = _first(rx, cc)
                    if hc:
                        break
        tn = _first(t["_th"], nm) if t["_th"] is not None else None
        tc = _first(t["_th"], cc) if t["_th"] is not None else None
        if hn:
            name_any = True
        rows.append((t, hn, hc, tn, tc))
    prior = RAW_TYPE_PRIOR.get(raw_type, ())
    out = []
    for t, hn, hc, tn, tc in rows:
        w_n, w_c = SPEC_W[t["spec"]]
        if not hn and hc and not name_any:
            w_c = max(w_c, w_n * 0.7)           # 명칭이 포장어뿐이면 내용이 명칭 역할(단, 신뢰도는 medium 이하로 제한)
        s = (w_n if hn else 0.0) + (w_c if hc else 0.0)
        if tn:
            s += THEME_W[0]
        if tc:
            s += THEME_W[1]
        if s <= 0:
            continue
        bonus = 0.0
        if t["fam"] in prior:
            bonus += FIELD_PRIOR_BONUS
        if field == "주거안전" and t["fam"] in ("F09", "F07"):
            bonus += SAFETY_FIELD_BONUS
        if perf_flag == "Y" and t["id"] == "K01":
            bonus += PERF_FLAG_BONUS
        out.append(dict(t=t, score=s + bonus, raw=s, hn=hn or tn, hc=hc or tc, key=s + bonus + t["prio"] / 100.0))
    out.sort(key=lambda r: r["key"], reverse=True)
    return out, name_any


def _override(top_id, cands, name_c, content_c):
    """유형 간 흔한 혼동에 대한 문맥 규칙(명절 행사 vs 취약세대 방문 돌봄 등)."""
    if top_id == "A03" and _PARENTS_DAY.search(content_c):
        for r in cands:
            if r["t"]["id"] == "A01":
                return r
        return dict(t=BY_ID["A01"], score=0.0, raw=0.0, hn=None, hc="override:parents_day_content", key=0.0, forced=True)
    if top_id in ("A02", "A03", "A01") and _HOUSEHOLD_CUE.search(name_c + content_c) and not _COMMUNITY_EVENT_CUE.search(content_c) \
            and not _COMMUNITY_EVENT_CUE.search(name_c):
        for r in cands:
            if r["t"]["id"] == "B01":
                return r
        return dict(t=BY_ID["B01"], score=0.0, raw=0.0, hn=None, hc="override:household_cue", key=0.0, forced=True)
    return None


def classify_row(name, content, raw_type="", field="", perf_flag=""):
    cands, name_any = score_types(name, content, raw_type, field, perf_flag)
    nc = compact(name)
    cc = compact(content)
    umb = umbrella_tags(nc)
    if not cands:
        if umb:  # 포장어만 있고 내용에서 유형이 안 잡힘 → 공동체 사업 기본값(낮은 확신)
            t = BY_ID["O01"]
            return dict(primary=t, secondary=[], score=0.5, margin=0.5, evidence="umbrella:" + "/".join(umb),
                        evidence_field="umbrella", umbrella=umb, n_cands=0, fallback="umbrella_default", override="")
        return dict(primary=BY_ID["Z99"], secondary=[], score=0.0, margin=0.0, evidence="", evidence_field="none",
                    umbrella=umb, n_cands=0, fallback="unmatched", override="")
    top = cands[0]
    ov = _override(top["t"]["id"], cands, nc, cc)
    override = ""
    if ov is not None:
        override = f"{top['t']['id']}->{ov['t']['id']}"
        top = ov
    second = None
    for r in cands:
        if r["t"]["id"] != top["t"]["id"]:
            second = r
            break
    margin = top["score"] - (second["score"] if second else 0.0)
    sec = []
    for r in cands:
        t = r["t"]
        if t["id"] == top["t"]["id"]:
            continue
        ok = (r["hn"] and SPEC_W[t["spec"]][0] >= 2.0) or (r["hc"] and t["spec"] == "H" and t["prio"] >= SEC_MIN_PRIO)
        if ok and t["scope"] in ("PROGRAM", "HOUSEHOLD_SUPPORT") and len(sec) < 3:
            sec.append(dict(id=t["id"], ev=(("name:" + r["hn"]) if r["hn"] else ("content:" + r["hc"]))))
    ef = "name" if top["hn"] else "content"
    ev = ((top["hn"] if top["hn"] else top["hc"]) or "")
    if top["hn"] and top["hc"]:
        ef = "name+content"
    return dict(primary=top["t"], secondary=sec, score=top["score"], margin=margin, evidence=ev, evidence_field=ef,
                umbrella=umb, n_cands=len(cands), fallback="", override=override)
