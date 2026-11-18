# -*- coding: utf-8 -*-
"""임대단지 주소 → 좌표 (VWorld Geocoder 2.0) + 도로명·지번 교차검증.

입력  data/raw/주택관리공단(주)_임대단지 관리현황_20260901.csv (cp949)
출력  data/processed/complex_geocode_20261117_v1/
        complex_coords.csv       단지별 좌표 + 검증 컬럼 (자동확정 행만 lon/lat 채움)
        address_review.csv       사람이 확인해야 하는 주소 질문 목록
        audit/vworld_raw.jsonl   API 응답 캐시 (인증키 미포함)
      address_overrides.csv      (선택) 사용자가 확인한 주소. 있으면 원본 대신 이 값을 조회

실행  VWORLD_KEY=<인증키> python -I -X utf8 geocode_complexes.py [--no-fetch]

원칙  원본 주소를 임의로 고치지 않는다. 공백·특수문자 같은 형식 보정만 하고,
      글자가 바뀌는 수정(청주→충주 등)은 질문 목록에 올려 사용자가 확인한다.
      VWorld는 정확히 일치하는 주소가 없으면 비슷한 주소로 '대체'해서 돌려주므로
      응답의 도로명·번지가 질의와 같은지 따로 검사한다.
"""
import argparse
import csv
import json
import math
import os
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "주택관리공단(주)_임대단지 관리현황_20260901.csv"
INTEG = ROOT / "data" / "processed" / "complex_integrated_20261117_v1"
OUT = ROOT / "data" / "processed" / "complex_geocode_20261117_v1"
CACHE = OUT / "audit" / "vworld_raw.jsonl"
OVERRIDES = OUT / "address_overrides.csv"
API = "https://api.vworld.kr/req/address"

DIST_OK_M = 500          # 도로명 좌표↔지번 좌표 허용 거리 (대단지는 필지 중심과 건물 입구가 멀다)
WORKERS = 2              # VWorld는 동시 호출이 많으면 502·연결 끊김이 난다

# 사용자가 전달한 'LLM 제안 오류 목록'. 근거 없는 추정이므로 자동 적용하지 않고 조회 증거만 붙여 질문한다.
LLM_FIXES = {
    "충주연수2": {"parcel": "충청북도 충주시 연수동 1231", "note": "지번 '청주시'→'충주시'"},
    "대구황금3": {"parcel": "대구광역시 수성구 황금동 965", "note": "지번 '수정구'→'수성구'"},
    "남양주마석": {"parcel": "경기도 남양주시 화도읍 마석우리 531", "note": "지번 '화동읍'→'화도읍'"},
    "진주평거2": {"parcel": "경상남도 진주시 평거동 392", "note": "지번 '펑거동'→'평거동'"},
    "안산고잔1": {"parcel": "경기도 안산시 상록구 사동 1534", "note": "지번에 동 이름 누락 → '사동'"},
    "백동KCC스위첸": {"road": "경기도 부천시 소사구 은성로67번길 12",
                  "parcel": "경기도 부천시 소사구 소사본동 424", "note": "'부천시' 뒤 구 누락 → '소사구'"},
    "약대아이파크": {"road": "경기도 부천시 원미구 평천로 679",
                 "parcel": "경기도 부천시 원미구 약대동 216-1", "note": "'부천시' 뒤 구 누락 → '원미구'"},
}
# 도로명에 건물번호가 없다고 지적된 9곳 — LLM이 'base 값'이라며 준 '도로명 + 번호'
LLM_NO_NUMBER = {
    "서울번동5": "한천로115길 20", "서울중계9": "노원로16길 15", "서울월계1": "초안산로1길 15",
    "분당목련1": "판교로 607", "광명하안13": "하안로 238", "김포마송": "김포대로2270번길 40",
    "충주연수2": "주공길 7", "대전판암4": "동부로 56-8", "제주고성": "고성서3길 14",
}
LLM_SAME_PLACE = {"평택미군난방관리단", "평택미군가족주택관리단", "평택미군에너지관리단",
                  "JDC제주첨단리슈빌", "JDC리슈빌(청약)"}      # LLM: 실제로 같은 장소라 문제없어 보임
LLM_DUP_SUSPECT = {"대전둔산1", "대전둔산3", "시흥능곡6", "시흥능곡7"}  # LLM: 복사 오류 의심

RE_FIX1 = re.compile(r"(로|길)\s+([동서남북]?\d+(?:번)?길)")        # '도봉로 180길' → '도봉로180길'
RE_FIX2 = re.compile(r"(\S+?)\s+(로|길)(\d+(?:-\d+)?)(?=[\s,(]|$)")  # '미리벌중앙 로35' → '미리벌중앙로 35'
RE_FIX3 = re.compile(r"(?<=[가-힣])(로|길)(\d+(?:-\d+)?)(?=[\s,(]|$)")  # '봉래길176' → '봉래길 176'
RE_ROAD = re.compile(r"^(?P<pre>.+?[로길])\s+(?P<num>\d+(?:-\d+)?)(?=[\s,]|$)")
RE_LOT = re.compile(r"산?\d+(?:-\d+)?")
RE_GLUED_LOT = re.compile(r"(.+[동리가읍면])(산?\d+(?:-\d+)?)")
RE_PAREN_DONG = re.compile(r"^([가-힣0-9]+(?:동|리|가|읍|면))(?:\s+(\d+(?:-\d+)?))?$")


def squash(s):
    return re.sub(r"[\s 　]+", " ", s).strip()


def nospace(s):
    return re.sub(r"\s+", "", s or "")


def haversine_m(x1, y1, x2, y2):
    p1, p2 = math.radians(y1), math.radians(y2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(x2 - x1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))


# ───────────────────────── 주소 문자열 → 질의 ─────────────────────────

def road_parts(addr):
    """'경기도 수원시 팔달구 창룡대로210번길 13' → (지역, 도로명, 건물번호). 못 읽으면 None."""
    m = RE_ROAD.match(addr or "")
    if not m or m.group("pre") != (addr or "").rsplit(" ", 1)[0]:
        return None
    toks = m.group("pre").split()
    return " ".join(toks[:-1]), toks[-1], m.group("num")


def build_road_query(full):
    """기본상세(도로명) → (질의, 적용한 형식 보정 목록). 괄호·건물명·특수문자 제거, 도로명 공백 정리."""
    fixes = []
    s = full or ""
    if "？" in s or "?" in s:
        fixes.append("깨진 문자(？) 제거")
        s = s.replace("？", " ").replace("?", " ")
    head = squash(squash(s).split("(")[0])
    head = RE_FIX1.sub(r"\1\2", head)
    fixed = RE_FIX3.sub(r"\1 \2", RE_FIX2.sub(r"\1\2 \3", head))
    if fixed != head:
        fixes.append("도로명 공백 보정")
    m = RE_ROAD.match(fixed)
    if not m:
        return None, fixes
    return f"{m.group('pre')} {m.group('num')}", fixes


def build_parcel_query(full):
    """지번기본주소 → '시도 시군구 동 본번-부번' (뒤에 붙은 건물명 제거). 못 읽으면 None."""
    toks = squash(full or "").split()
    for j, t in enumerate(toks):
        if j >= 2 and RE_LOT.fullmatch(t):
            return " ".join(toks[:j + 1])
        m = RE_GLUED_LOT.fullmatch(t)
        if j >= 2 and m:
            return " ".join(toks[:j] + [m.group(1), m.group(2)])
    return None


def paren_dong(full):
    """도로명 괄호 안의 첫 항목이 동·리면 (동, 번지) 반환. 예: '(번동, …)' → ('번동', None)."""
    m = re.search(r"\(([^)]*)\)", full or "")
    if not m:
        return None, None
    first = squash(m.group(1).split(",")[0])
    d = RE_PAREN_DONG.match(first)
    return (d.group(1), d.group(2)) if d else (None, None)


def exact_road(addr, res):
    if not res or res.get("status") != "OK":
        return False
    parts = road_parts(addr)
    if not parts:
        return False
    region, token, num = parts
    st = res["st"]
    reg, qreg = nospace(st.get("level1", "") + st.get("level2", "")), nospace(region)
    # 질의에 구가 빠져 있으면 VWorld가 보충하므로 서로 앞부분이 같으면 같은 지역으로 본다
    return (nospace(token) == nospace(st.get("level4L")) and num == (st.get("level5") or "").strip()
            and (qreg.startswith(reg) or reg.startswith(qreg)))


def exact_parcel(addr, res):
    return bool(res) and res.get("status") == "OK" and nospace(addr) == nospace(res["text"])


# ───────────────────────── VWorld ─────────────────────────

class VWorld:
    """API 호출(fwd_raw/rev_raw)과 캐시 조회(fwd/rev)를 분리한다. 판정 단계는 캐시만 읽는다."""

    def __init__(self, key, cache_path):
        self.key, self.path = key, cache_path
        self.cache = {}
        self.fail_streak = 0
        self.lock = threading.Lock()
        self.local = threading.local()
        if cache_path.exists():
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    d = json.loads(line)
                    self.cache[d["k"]] = d["r"]

    def _call(self, params):
        sess = getattr(self.local, "s", None) or requests.Session()
        self.local.s = sess
        for attempt in range(4):
            if self.fail_streak >= 3:           # 서버가 연속으로 실패하면 전체가 잠시 쉰다
                time.sleep(min(60, 5 * self.fail_streak))
            try:
                r = sess.get(API, params=dict(params, key=self.key), timeout=20)
                resp = r.json().get("response", {})
                if resp.get("status") in ("OK", "NOT_FOUND"):
                    self.fail_streak = 0
                    return {k: resp[k] for k in ("status", "refined", "result", "input") if k in resp}
                err = resp.get("error", {})
                if "KEY" in str(err.get("code", "")).upper():
                    sys.exit(f"인증키 오류: {err}")
            except (requests.RequestException, ValueError):     # 502·연결 끊김 등
                pass
            self.fail_streak += 1
            time.sleep(1.5 * (attempt + 1))
        return None

    def _fetch(self, key, params):
        if key in self.cache:
            return
        resp = self._call(params)
        if resp is not None:
            with self.lock:
                self.cache[key] = resp
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"k": key, "r": resp}, ensure_ascii=False) + "\n")
        time.sleep(0.12)

    def fwd_raw(self, typ, addr):
        self._fetch(f"fwd|{typ}|{addr}", dict(
            service="address", request="getcoord", version="2.0", crs="epsg:4326", address=addr,
            refine="true", simple="false", format="json", type=typ))

    def rev_raw(self, x, y):
        self._fetch(f"rev|{x:.6f},{y:.6f}", dict(
            service="address", request="getAddress", version="2.0", crs="epsg:4326", point=f"{x:.6f},{y:.6f}",
            format="json", type="both", zipcode="true", simple="false"))

    def fwd(self, typ, addr):
        """캐시된 정방향 결과 {'status','x','y','text','st'}. 조회하지 못했으면 None."""
        resp = self.cache.get(f"fwd|{typ}|{addr}") if addr else None
        if resp is None:
            return None
        if resp.get("status") != "OK":
            return {"status": resp.get("status")}
        pt = resp["result"]["point"]
        return {"status": "OK", "x": float(pt["x"]), "y": float(pt["y"]),
                "text": resp["refined"]["text"], "st": resp["refined"]["structure"]}

    def rev(self, x, y):
        """캐시된 역조회 결과 {'parcel': {zip,text}, 'road': {zip,text}}. 없으면 None."""
        resp = self.cache.get(f"rev|{x:.6f},{y:.6f}")
        if not resp or resp.get("status") != "OK":
            return None
        return {it["type"]: {"zip": it.get("zipcode", ""), "text": it.get("text", "")} for it in resp["result"]}


def prefetch(vw, rows, keys):
    """① 정방향 질의 ② 도로명 좌표 역조회 ③ 우편번호·거리가 안 맞는 행의 지번 좌표와 LLM 수정안 좌표 역조회.
    서버가 불안정하면 일부가 비므로 몇 건이 비었는지 돌려준다(다시 실행하면 이어서 조회)."""
    def run(fn, items):
        with ThreadPoolExecutor(WORKERS) as ex:
            list(ex.map(fn, items))

    def point(typ, addr):
        res = vw.fwd(typ, addr)
        ok = res and (exact_road(addr, res) if typ == "road" else exact_parcel(addr, res))
        return (round(res["x"], 6), round(res["y"], 6)) if ok else None

    run(lambda k: vw.fwd_raw(*k), sorted(keys))
    road_pts = {p for r in rows if r["road_q"] and (p := point("road", r["road_q"]))}
    run(lambda p: vw.rev_raw(*p), sorted(road_pts))
    need = set()
    for r in rows:
        rp = point("road", r["road_q"]) if r["road_q"] else None
        pp = point("parcel", r["parcel_q"]) if r["parcel_q"] else None
        far = rp and pp and haversine_m(*rp, *pp) > DIST_OK_M
        if pp and (far or not (rp and zip_hit(vw.rev(*rp), r["zip"]))):
            need.add(pp)
    for fx in LLM_FIXES.values():
        for typ in ("road", "parcel"):
            if typ in fx and (p := point(typ, fx[typ])):
                need.add(p)
    run(lambda p: vw.rev_raw(*p), sorted(need))
    missing = [k for k in keys if f"fwd|{k[0]}|{k[1]}" not in vw.cache]
    return len(keys), len(road_pts) + len(need), len(missing)


# ───────────────────────── 읽기 ─────────────────────────

def load_rows():
    with RAW.open(encoding="cp949", newline="") as f:
        data = list(csv.reader(f))
    ids, codes = {}, {}
    base = INTEG / "detail" / "base.csv"
    if base.exists():
        with base.open(encoding="utf-8-sig", newline="") as f:
            ids = {r["단지명"]: r["complex_id"] for r in csv.DictReader(f)}
    link = INTEG / "spatial" / "complex_legal_dong_linkage.csv"
    if link.exists():
        with link.open(encoding="utf-8-sig", newline="") as f:
            codes = {r["단지명"]: r["법정동코드"] for r in csv.DictReader(f)}
    rows = []
    for i, r in enumerate(data[1:], start=2):       # 엑셀 행 번호(헤더=1)
        full = r[5].strip() or squash(r[3] + " " + r[4])
        rows.append({"n": i, "id": ids.get(r[0], ""), "name": r[0], "village": r[1], "zip": r[2].strip(),
                     "road_col": r[3].strip(), "road_extra": r[4].strip(), "road_full": full,
                     "parcel_full": r[6].strip(), "prev_code": codes.get(r[0], "")})
    return rows


def load_overrides():
    if not OVERRIDES.exists():
        return {}
    with OVERRIDES.open(encoding="utf-8-sig", newline="") as f:
        return {int(r["excel_row"]): r for r in csv.DictReader(f)}


# ───────────────────────── 판정 ─────────────────────────

def prepare(rows):
    """질의 문자열을 만들고(사용자 확정 주소 우선) 조회할 (type, 주소) 집합을 돌려준다."""
    ov = load_overrides()
    keys = set()
    for r in rows:
        o = ov.get(r["n"], {})
        if o.get("road_address", "").strip():
            r["road_q"], r["fmt"] = squash(o["road_address"]), ["사용자 확정 주소"]
        else:
            r["road_q"], r["fmt"] = build_road_query(r["road_full"])
        r["parcel_q"] = squash(o["parcel_address"]) if o.get("parcel_address", "").strip() \
            else build_parcel_query(r["parcel_full"])
        r["confirmed"] = bool(o)
        r["basis_type"], r["basis"] = o.get("basis_type", "").strip() or "사용자", o.get("basis", "").strip()
        for typ in ("road", "parcel"):
            if r[typ + "_q"]:
                keys.add((typ, r[typ + "_q"]))
    for fx in LLM_FIXES.values():
        for typ in ("road", "parcel"):
            if typ in fx:
                keys.add((typ, fx[typ]))
    return keys


def load_lh_check():
    """compare_lh_addresses.py가 만든 LH 공식 자료 대조 결과 (없으면 빈 dict)."""
    p = OUT / "lh_address_check.csv"
    if not p.exists():
        return {}
    with p.open(encoding="utf-8-sig", newline="") as f:
        return {int(r["excel_row"]): r for r in csv.DictReader(f)}


def evaluate(rows, vw):
    lh_check = load_lh_check()
    dup_road, dup_parcel = defaultdict(list), defaultdict(list)
    for r in rows:
        if r["road_q"]:
            dup_road[r["road_q"]].append(r["name"])
        if r["parcel_q"]:
            dup_parcel[r["parcel_q"]].append(r["name"])

    evs = []
    for r in rows:
        e = {"row": r, "reasons": [], "infos": []}
        e["road"], e["parcel"] = vw.fwd("road", r["road_q"]), vw.fwd("parcel", r["parcel_q"])
        e["road_exact"] = bool(r["road_q"]) and exact_road(r["road_q"], e["road"])
        e["parcel_exact"] = bool(r["parcel_q"]) and exact_parcel(r["parcel_q"], e["parcel"])
        e["rev_road"] = vw.rev(e["road"]["x"], e["road"]["y"]) if e["road_exact"] else None
        e["rev_parcel"] = vw.rev(e["parcel"]["x"], e["parcel"]["y"]) if e["parcel_exact"] else None
        e["dist"] = haversine_m(e["road"]["x"], e["road"]["y"], e["parcel"]["x"], e["parcel"]["y"]) \
            if e["road_exact"] and e["parcel_exact"] else None
        zips = [v["zip"] for rv in (e["rev_road"], e["rev_parcel"]) if rv for v in rv.values()]
        e["rev_zip"] = "/".join(sorted(set(z for z in zips if z)))
        e["zip_ok"] = (r["zip"] in zips) if zips else None
        e["region_filled"] = False      # 도로명에 구가 빠져 있어 VWorld가 보충한 경우
        if e["road_exact"]:
            reg = nospace(e["road"]["st"].get("level1", "") + e["road"]["st"].get("level2", ""))
            qreg = nospace(road_parts(r["road_q"])[0])
            e["region_filled"] = len(reg) > len(qreg) and reg.startswith(qreg)
        e["dups"] = sorted(set(dup_road.get(r["road_q"], []) + dup_parcel.get(r["parcel_q"], [])) - {r["name"]})
        e["lh"] = lh_check.get(r["n"])
        pd_, pl_ = paren_dong(r["road_full"])
        pq = (r["parcel_q"] or "").split()
        e["paren"] = (pd_, pl_, pq[-2] if len(pq) >= 2 else None, pq[-1] if pq else None)
        evs.append(e)
    return evs


def zip_hit(rev, fz):
    return bool(rev) and any(v["zip"] == fz for v in rev.values())


def variant(vw, typ, addr):
    """LLM 수정안 같은 대체 주소를 조회한 증거."""
    res = vw.fwd(typ, addr)
    ok = exact_road(addr, res) if typ == "road" else exact_parcel(addr, res)
    return {"addr": addr, "res": res, "exact": ok, "rev": vw.rev(res["x"], res["y"]) if ok else None}


def desc(label, addr, res, ok):
    if res is None:
        return f"{label} '{addr}': 조회 안 함"
    if res["status"] != "OK":
        return f"{label} '{addr}': 조회 결과 없음"
    pt = f"({res['x']:.5f}, {res['y']:.5f})"
    if ok:
        return f"{label} '{addr}': 정확히 일치 {pt}"
    return f"{label} '{addr}': 정확히 일치하지 않음 → VWorld가 '{res['text']}'(으)로 대체 {pt}"


def judge(e):
    """사유(reasons)가 하나라도 있으면 좌표 확정을 보류하고 사용자에게 묻는다.
    참고(infos)는 좌표는 확정한 채 남기는 메모. 둘 다 (코드, 문장) 목록이다."""
    r, R, I = e["row"], e["reasons"], e["infos"]
    anchored = e["road_exact"] and e["zip_ok"] is True    # 도로명 정확 일치 + 우편번호 일치면 좌표는 믿을 수 있다
    consistent = e["dist"] is not None and e["dist"] <= DIST_OK_M
    for typ, label in (("road", "도로명"), ("parcel", "지번")):
        q, res, ok = r[typ + "_q"], e[typ], e[typ + "_exact"]
        if not q:
            msg = f"{label}에서 주소를 읽지 못함"
        elif not res or res["status"] != "OK":
            msg = f"{label} '{q}'을(를) VWorld에서 찾지 못함"
        elif not ok:
            msg = f"{label} '{q}'은(는) VWorld에 없어 '{res['text']}'(으)로 대체됨"
        else:
            continue
        if typ == "parcel" and anchored:    # 지번 문자열만 확인 안 됨 — 좌표에는 영향 없다
            I.append(("PARCEL_ONLY", msg))
        else:
            R.append((typ.upper(), msg))
    if e["region_filled"]:
        R.append(("REGION", f"도로명에 구가 빠져 있어 VWorld가 '{e['road']['st']['level2']}'(으)로 보충함"))
    if e["dist"] is not None:
        reg = [nospace(e[t]["st"].get("level1", "") + e[t]["st"].get("level2", "")) for t in ("road", "parcel")]
        if reg[0] != reg[1]:
            R.append(("REGION", f"도로명 결과는 '{e['road']['st']['level2']}', 지번 결과는 '{e['parcel']['st']['level2']}'(으)로 시군구가 다름"))
        if e["dist"] > DIST_OK_M:
            R.append(("DIST", f"도로명 좌표와 지번 좌표가 {e['dist']:.0f}m 떨어져 있음"))
    if e["zip_ok"] is False:
        msg = f"파일 우편번호 {r['zip']} ≠ 좌표의 우편번호 {e['rev_zip']}"
        (I if e["road_exact"] and e["parcel_exact"] and consistent else R).append(("ZIP", msg))
    pdong, plot, dong, lot = e["paren"]
    if plot and lot and plot != lot:
        msg = f"도로명 괄호의 번지 '{pdong} {plot}' ≠ 지번주소 '{dong} {lot}'"
        if anchored and lot_of(e["rev_road"]).endswith(" " + plot):
            I.append(("PAREN_LOT", msg + " (VWorld 역조회 지번은 괄호 쪽과 같음)"))
        else:
            R.append(("PAREN_LOT", msg))
    if not r["confirmed"]:      # 사용자가 이미 확인한 행은 다시 묻지 않는다
        if e["dups"]:
            R.append(("DUP", "도로명 또는 지번이 같은 다른 단지: " + ", ".join(e["dups"])))
        if r["name"] in LLM_FIXES:
            R.append(("LLM_FIX", "LLM 제안 수정: " + LLM_FIXES[r["name"]]["note"]))
        if r["name"] in LLM_NO_NUMBER:
            R.append(("LLM_NUM", "LLM 제안: 도로명 건물번호를 '" + LLM_NO_NUMBER[r["name"]] + "'(으)로 채움"))
    I.extend(("FMT", f) for f in r["fmt"] if f != "사용자 확정 주소")
    if pdong and dong and pdong != dong:
        I.append(("PAREN_DONG", f"도로명 괄호의 동 '{pdong}' ≠ 지번주소의 동 '{dong}'"))
    if r["road_extra"][:1].isdigit():
        I.append(("NUM_EXTRA", "건물번호가 기본주소가 아니라 상세주소 열에 있어 합쳐서 조회"))
    code8 = ((e["parcel"] or {}).get("st", {}).get("level4LC") or "")[:8] if e["parcel_exact"] else ""
    if r["prev_code"] and code8 and r["prev_code"] != code8:
        I.append(("LINKAGE", f"기존 법정동 연계 코드 {r['prev_code']} ≠ VWorld {code8}"))
    lh = e.get("lh")
    if lh and lh.get("LH_단지코드") and not r["confirmed"]:      # 확정한 행은 LH 대조 메모를 남기지 않는다
        if lh["도로명_일치"] == "아니오":
            d = lh.get("LH도로명_거리m")
            I.append(("LH_ROAD", f"LH 도로명 '{lh['LH_도로명'].split(' ', 2)[-1]}'와 번호가 다름" + (f" (좌표 차이 {d}m)" if d else "")))
        if lh["지번_일치"] == "아니오":
            I.append(("LH_PARCEL", "LH 대조: " + next(s for s in lh["비고"].split("; ") if s.startswith("지번"))))
    if R:
        e["status"] = "확인필요"
    elif r["confirmed"]:
        e["status"] = {"공식자료": "공식자료확인", "정황": "정황확인"}.get(r["basis_type"], "사용자확정")
    else:
        e["status"] = "자동확정"
    return e


def lot_of(rev):
    """역조회 결과에서 지번 주소 문자열."""
    return ((rev or {}).get("parcel") or {}).get("text", "")


def building_name(text):
    """VWorld 도로명 정제주소 '… (월평동,주공아파트1단지)'에서 건물명 부분."""
    if "(" not in (text or ""):
        return ""
    inner = text[text.index("(") + 1:text.rindex(")")]
    return inner.split(",", 1)[1].strip() if "," in inner else ""


def review_items(evs, vw):
    """질문 목록. A~D는 답이 필요한 질문(좌표 보류), E는 좌표를 확정한 채 남기는 참고.
    한 단지는 가장 우선하는 구분 하나에만 올린다."""
    by_name = {e["row"]["name"]: e for e in evs}
    items, done = [], set()

    def add(group, members, issue, evidence, opinion, need="Y"):
        rs = [m["row"] for m in members]
        done.update(r["name"] for r in rs)
        items.append({"구분": group, "답변필요": need, "엑셀행": "/".join(str(r["n"]) for r in rs),
                      "단지명": " / ".join(r["name"] for r in rs), "마을명": " / ".join(r["village"] for r in rs),
                      "우편번호": rs[0]["zip"], "도로명(원본)": rs[0]["road_full"], "지번(원본)": rs[0]["parcel_full"],
                      "쟁점": issue, "VWorld 조회 증거": "\n".join(evidence), "내 판단": opinion,
                      "확인한 도로명": "", "확인한 지번": "", "비고": ""})

    # A. LLM이 지목한 오타 수정안 — 원본과 수정안을 모두 조회해 증거로 붙인다
    for name, fx in LLM_FIXES.items():
        e = by_name[name]
        r, fz = e["row"], e["row"]["zip"]
        if r["confirmed"]:
            continue
        vr = variant(vw, "road", fx["road"]) if "road" in fx else None
        vp = variant(vw, "parcel", fx["parcel"]) if "parcel" in fx else None
        road_ok = vr["exact"] if vr else e["road_exact"]
        parcel_ok = vp["exact"] if vp else e["parcel_exact"]
        rres, pres = (vr["res"] if vr else e["road"]), (vp["res"] if vp else e["parcel"])
        parcel_q = vp["addr"] if vp else r["parcel_q"]
        ev = [desc("원본 도로명", r["road_q"], e["road"], e["road_exact"]),
              desc("원본 지번", r["parcel_q"], e["parcel"], e["parcel_exact"])]
        if vr:
            ev.append(desc("LLM 수정 도로명", vr["addr"], vr["res"], vr["exact"]))
        if vp:
            ev.append(desc("LLM 수정 지번", vp["addr"], vp["res"], vp["exact"]))
        dist = haversine_m(rres["x"], rres["y"], pres["x"], pres["y"]) if road_ok and parcel_ok else None
        rev = vr["rev"] if vr else e["rev_road"]
        if dist is not None:
            ev.append(f"수정안 기준 도로명↔지번 좌표 거리 {dist:.0f}m")
        if lot_of(rev):
            ev.append(f"도로명 좌표의 지번(VWorld 역조회): {lot_of(rev)}")
        zips = [rev, vp["rev"] if vp else e["rev_parcel"]]
        zip_ok = any(zip_hit(z, fz) for z in zips)
        ev.append(f"우편번호: 파일 {fz} / 수정안 좌표 " + ("일치" if zip_ok else "불일치 또는 확인불가"))
        if name in LLM_NO_NUMBER:
            parts = road_parts(r["road_q"])
            ev.append(f"건물번호: 상세주소 열 '{r['road_extra']}'에서 읽은 '{parts[1]} {parts[2]}' — LLM 값 '{LLM_NO_NUMBER[name]}'과 "
                      + ("같음" if nospace(f"{parts[1]} {parts[2]}") == nospace(LLM_NO_NUMBER[name]) else "다름"))
        if parcel_ok and road_ok and dist is not None and dist <= DIST_OK_M and zip_ok:
            same = nospace(lot_of(rev)) == nospace(parcel_q)
            op = "수정안이 타당해 보임: 수정안이 정확히 일치하고 도로명 좌표·우편번호와 맞음" + \
                 (", VWorld가 도로명 좌표의 지번을 수정안과 똑같이 알려줌" if same else f", 다만 도로명 좌표의 지번은 '{lot_of(rev)}'로 번지가 다름")
        elif parcel_ok and road_ok:
            op = "수정안은 VWorld에 존재하나 도로명·우편번호와 맞는지 불확실 — 직접 확인 필요"
        else:
            op = "수정안도 조회가 맞지 않음 — 직접 확인 필요"
        add("A. LLM 오타 수정안", [e], fx["note"], ev, op)

    # B. 도로명 건물번호 (LLM 값이 상세주소 열의 값과 같은지)
    for name, tail in LLM_NO_NUMBER.items():
        e = by_name[name]
        r = e["row"]
        if name in done or r["confirmed"]:
            continue
        parts = road_parts(r["road_q"])
        mine = f"{parts[1]} {parts[2]}" if parts else ""
        same = nospace(mine) == nospace(tail)
        ev = [f"기본주소 열: '{r['road_col']}' / 상세주소 열: '{r['road_extra']}'",
              f"합쳐서 읽은 도로명+번호: '{mine}' — LLM 값 '{tail}'과 " + ("같음" if same else "다름"),
              desc("도로명", r["road_q"], e["road"], e["road_exact"]),
              desc("지번", r["parcel_q"], e["parcel"], e["parcel_exact"])]
        if e["dist"] is not None:
            ev.append(f"도로명↔지번 좌표 거리 {e['dist']:.0f}m, 우편번호 {r['zip']} " + ("일치" if e["zip_ok"] else "불일치/확인불가"))
        op = "번호가 이 파일의 상세주소 열에 이미 있음 — 그대로 확정해도 될 것으로 보임" if same else "LLM 값과 파일 값이 다름 — 직접 확인 필요"
        add("B. 도로명 건물번호 (LLM)", [e], "도로명 건물번호가 기본주소 열에서 잘려 상세주소 열로 넘어가 있음", ev, op)

    # C. 같은 도로명·지번을 쓰는 단지 묶음
    seen = set()
    for e in evs:
        if e["row"]["name"] in done or not e["dups"]:
            continue
        group = tuple(sorted([e["row"]["name"]] + e["dups"]))
        if group in seen:
            continue
        seen.add(group)
        members = sorted((by_name[n] for n in group), key=lambda m: m["row"]["n"])
        if all(m["row"]["confirmed"] for m in members):
            continue
        ev = []
        for m in members:
            mr, rd = m["row"], m["road"]
            ev.append(f"[{mr['n']}행 {mr['name']}] 마을명 '{mr['village']}', 우편번호 {mr['zip']}")
            ev.append(f"    도로명 '{mr['road_q']}' → VWorld '{rd['text']}' ({rd['x']:.5f}, {rd['y']:.5f})")
            ev.append(f"    지번(파일) '{mr['parcel_q']}' / 이 도로명 좌표의 지번(VWorld) '{lot_of(m['rev_road'])}'")
        first = members[0]
        for m in members[1:]:
            ev.append(f"{first['row']['name']} ↔ {m['row']['name']} 도로명 좌표 거리 {haversine_m(first['road']['x'], first['road']['y'], m['road']['x'], m['road']['y']):.0f}m")
        same_road = len({m["row"]["road_q"] for m in members}) == 1
        bname = building_name(first["road"]["text"])
        if set(group) <= LLM_SAME_PLACE:
            op = "같은 게이트·같은 단지로 보임 (LLM 의견)" + (f", VWorld도 이 주소를 '{bname}'로 등록" if bname else "") + " — 맞는지 확인"
        elif same_road:
            op = "도로명·지번이 모두 같아 한쪽 주소가 복사됐을 가능성" + (f" (VWorld는 이 주소를 '{bname}'로 등록)" if bname else "") + " — 각 단지의 실제 주소 확인 필요"
        else:
            lots = ", ".join(f"{m['row']['name']}={lot_of(m['rev_road']).split()[-1]}" for m in members)
            op = f"도로명은 서로 달라 구분되지만 지번만 같음. VWorld가 각 도로명 좌표에 붙인 지번: {lots} — 지번이 다르게 나오는 쪽 확인 필요"
        add("C. 같은 주소를 쓰는 단지", members, "서로 다른 단지가 같은 도로명 또는 지번을 씀", ev, op)

    # D. 그 밖에 좌표를 확정하지 못한 행
    for e in evs:
        r = e["row"]
        if r["name"] in done or not e["reasons"]:
            continue
        ev = [desc("도로명", r["road_q"], e["road"], e["road_exact"]),
              desc("지번", r["parcel_q"], e["parcel"], e["parcel_exact"])]
        if e["dist"] is not None:
            ev.append(f"도로명↔지번 좌표 거리 {e['dist']:.0f}m")
        if lot_of(e["rev_road"]):
            ev.append(f"도로명 좌표의 지번(VWorld 역조회): {lot_of(e['rev_road'])}")
        if e["rev_parcel"] and e["rev_parcel"].get("road"):
            ev.append(f"지번 좌표의 도로명(VWorld 역조회): {e['rev_parcel']['road']['text']}")
        ev.append(f"우편번호: 파일 {r['zip']} / 좌표 {e['rev_zip'] or '확인불가'}")
        add("D. 조회 불일치·실패", [e], " / ".join(t for _, t in e["reasons"]), ev, "직접 확인 필요")

    # G. 공식 자료 없이 정황으로만 확정한 행 — 같은 근거끼리 묶어 확인을 요청한다
    by_basis = defaultdict(list)
    for e in evs:
        if e["status"] == "정황확인":
            by_basis[e["row"]["basis"]].append(e)
    for basis, members in by_basis.items():
        ev = [f"근거: {basis}"]
        for m in members:
            mr = m["row"]
            ev.append(f"[{mr['n']}행 {mr['name']}] " + desc("도로명", mr["road_q"], m["road"], m["road_exact"])
                      + f", 우편번호 파일 {mr['zip']} / 좌표 {m['rev_zip'] or '확인불가'}")
        add("G. 정황으로만 확정", members, "공식 자료로는 확인하지 못함", ev, "좌표는 파일 주소 그대로 임시 확정. 다르면 알려주세요")

    # F. 공식 자료(LH)와 도로명 번호가 다른 단지 — 둘 다 실재하는 주소라 파일 값을 유지했다
    for e in evs:
        lh = e.get("lh")
        if not lh or lh.get("도로명_일치") != "아니오" or e["row"]["confirmed"]:
            continue
        r, d = e["row"], lh.get("LH도로명_거리m")
        ev = [f"파일 '{r['road_q']}' / LH(2025-03) '{lh['LH_도로명']}'",
              f"LH 주소 조회: {lh['LH도로명_조회']}" + (f", 파일 주소와 좌표 {d}m 차이" if d else ""),
              f"우편번호 파일 {r['zip']} / LH {lh['LH_우편번호']}"]
        add("F. LH와 도로명 번호가 다름", [e], "같은 단지의 다른 건물 번호로 보임", ev,
            "파일(관리현황) 주소를 유지함. LH 주소로 바꾸려면 알려주세요")

    # E. 좌표는 확정했지만 알려둘 것 (답변 불필요)
    notes = {"PARCEL_ONLY": "지번 열만 VWorld에서 확인 안 됨(신축 등으로 지번이 바뀌었을 수 있음)",
             "PAREN_LOT": "도로명 괄호의 번지와 지번 열이 다름", "ZIP": "주소는 일치하고 우편번호만 다름",
             "FMT": "조회용으로 주소 형식만 보정"}
    for e in evs:
        r = e["row"]
        codes = [c for c, _ in e["infos"] if c in notes]
        if r["name"] in done or r["confirmed"] or e["reasons"] or not codes:
            continue
        ev = [t for c, t in e["infos"] if c in notes]
        if "PARCEL_ONLY" in codes or "PAREN_LOT" in codes:
            ev.append(f"VWorld가 도로명 좌표에 붙인 지번: {lot_of(e['rev_road'])}")
            lh = e.get("lh")
            if lh and lh.get("LH_지번"):
                ev.append(f"LH 주택별현황집계(2025-03) 지번 '{lh['LH_지번']}' → 파일과 " + ("같음" if lh["지번_일치"] == "예" else "다름"))
        if "FMT" in codes:
            ev.append(f"원본 '{r['road_full']}' → 조회 '{r['road_q']}'")
        ev.append(f"도로명 정확 일치, 우편번호 파일 {r['zip']} / 좌표 {e['rev_zip'] or '확인불가'}")
        add("E. 참고 (좌표 확정)", [e], "; ".join(notes[c] for c in dict.fromkeys(codes)), ev,
            "좌표는 도로명 기준으로 확정. 필요할 때만 해당 열을 고치면 됨", need="참고(답변 불필요)")
    qn = nn = 0
    for it in items:
        if it["답변필요"] == "Y":
            qn += 1
            it["질문번호"] = f"Q{qn}"
        else:
            nn += 1
            it["질문번호"] = f"N{nn}"
    return items


def fmt(v, nd=6):
    return "" if v is None else f"{v:.{nd}f}"


def match_label(res, ok):
    return "미조회" if res is None else ("없음" if res["status"] != "OK" else ("정확" if ok else "대체"))


def write_outputs(evs, items):
    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["excel_row", "complex_id", "단지명", "마을명", "우편번호", "판정", "lon", "lat", "좌표출처",
            "도로명_조회값", "road_일치", "road_lon", "road_lat", "road_정제주소",
            "지번_조회값", "parcel_일치", "parcel_lon", "parcel_lat", "parcel_정제주소", "법정동코드8",
            "도로_지번_거리m", "우편번호_검증", "좌표_우편번호", "역조회_지번", "확인근거", "확인사유", "참고"]
    with (OUT / "complex_coords.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        for e in evs:
            r, rd, pc = e["row"], e["road"], e["parcel"]
            auto = e["status"] != "확인필요"
            w.writerow({
                "excel_row": r["n"], "complex_id": r["id"], "단지명": r["name"], "마을명": r["village"],
                "우편번호": r["zip"], "판정": e["status"],
                "lon": fmt(rd["x"]) if auto else "", "lat": fmt(rd["y"]) if auto else "",
                "좌표출처": "도로명" if auto else "",
                "도로명_조회값": r["road_q"] or "", "road_일치": match_label(rd, e["road_exact"]),
                "road_lon": fmt(rd["x"]) if rd and rd["status"] == "OK" else "",
                "road_lat": fmt(rd["y"]) if rd and rd["status"] == "OK" else "",
                "road_정제주소": rd["text"] if rd and rd["status"] == "OK" else "",
                "지번_조회값": r["parcel_q"] or "", "parcel_일치": match_label(pc, e["parcel_exact"]),
                "parcel_lon": fmt(pc["x"]) if pc and pc["status"] == "OK" else "",
                "parcel_lat": fmt(pc["y"]) if pc and pc["status"] == "OK" else "",
                "parcel_정제주소": pc["text"] if pc and pc["status"] == "OK" else "",
                "법정동코드8": ((pc or {}).get("st", {}).get("level4LC") or "")[:8] if e["parcel_exact"] else "",
                "도로_지번_거리m": fmt(e["dist"], 0), "우편번호_검증": {True: "일치", False: "불일치", None: "확인불가"}[e["zip_ok"]],
                "좌표_우편번호": e["rev_zip"],
                "역조회_지번": ((e["rev_road"] or {}).get("parcel") or {}).get("text", ""),
                "확인근거": f"[{r['basis_type']}] {r['basis']}" if r["confirmed"] else "",
                "확인사유": " | ".join(t for _, t in e["reasons"]), "참고": " | ".join(t for _, t in e["infos"])})
    rcols = ["질문번호", "답변필요", "구분", "엑셀행", "단지명", "마을명", "우편번호", "도로명(원본)", "지번(원본)", "쟁점",
             "VWorld 조회 증거", "내 판단", "확인한 도로명", "확인한 지번", "비고"]
    with (OUT / "address_review.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, rcols)
        w.writeheader()
        w.writerows(items)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-fetch", action="store_true", help="캐시만 사용 (API 호출 안 함)")
    args = ap.parse_args()
    key = os.environ.get("VWORLD_KEY")
    if not key and not args.no_fetch:
        sys.exit("환경변수 VWORLD_KEY(VWorld 인증키)가 필요합니다.")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    keys = prepare(rows)
    vw = VWorld(key, CACHE)
    if not args.no_fetch:
        nf, nr, miss = prefetch(vw, rows, keys)
        print(f"정방향 {nf}건, 역지오코딩 {nr}건 조회 (캐시 {len(vw.cache)}건, 정방향 미조회 {miss}건)")
    evs = [judge(e) for e in evaluate(rows, vw)]
    items = review_items(evs, vw)
    write_outputs(evs, items)
    n_ask = sum(it["답변필요"] == "Y" for it in items)
    cnt = {s: sum(e["status"] == s for e in evs) for s in ("자동확정", "공식자료확인", "정황확인", "사용자확정", "확인필요")}
    print(f"단지 {len(evs)}곳: " + ", ".join(f"{s} {n}" for s, n in cnt.items() if n)
          + f" (답변 필요한 질문 {n_ask}건, 참고 {len(items) - n_ask}건) → {OUT}")


if __name__ == "__main__":
    main()
