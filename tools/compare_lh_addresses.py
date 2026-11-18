# -*- coding: utf-8 -*-
"""관리현황 주소를 LH 공식 자료(주택별현황집계, 2025-03-05)와 대조한다.

입력  data/raw/주택관리공단(주)_임대단지 관리현황_20260901.csv
      data/raw/한국토지주택공사_주택별현황집계_20250305.csv
      (선택) 통합 파일의 LH_단지코드 연결, VWorld 캐시
출력  data/processed/complex_geocode_20261117_v1/lh_address_check.csv

실행  [VWORLD_KEY=<인증키>] python -I -X utf8 compare_lh_addresses.py
      키가 있으면 도로명 번호가 다른 단지의 LH 주소도 VWorld로 조회해 우리 좌표와의 거리를 잰다.

주의  LH 자료는 2025-03 기준이라 이후 생긴 단지(신축·매입약정)는 매칭되지 않고,
      행정구역 개편(검단구, 전남광주통합특별시)은 다르게 적혀 있다. 도로명은 '도로명+번호'만 비교한다.
"""
import csv
import os
import re
import sys
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geocode_complexes as g

LH = g.ROOT / "data" / "raw" / "한국토지주택공사_주택별현황집계_20250305.csv"
MASTER = g.INTEG / "data" / "complex_master.csv"
LH_COLS = ["본부", "LH코드", "관리", "단지명", "시군구", "법정seq", "법정주소", "산", "본번", "부번", "법정상세",
           "우편", "도로주소", "도로상세", "유형", "전용", "주거공용", "공급", "호수", "입주시작", "입주종료"]


def load_lh():
    """LH코드별 대표 행(주소는 공급유형 행마다 같다)과 단지명 색인."""
    with LH.open(encoding="utf-8-sig", newline="") as f:
        data = list(csv.reader(f))[1:]
    by_code = OrderedDict()
    for row in data:
        r = dict(zip(LH_COLS, row))
        by_code.setdefault(r["LH코드"], r)
    by_name = {}
    for r in by_code.values():
        by_name.setdefault(g.nospace(r["단지명"]), []).append(r)     # 같은 이름이 여러 LH코드인 경우가 있다 (예: 광주쌍촌)
    return by_code, by_name


def lh_road(r):
    return g.build_road_query((r["도로주소"] + " " + r["도로상세"]).strip())[0]


def lh_parcel(r):
    """법정주소에 번지가 이미 붙은 행도 있고 본번·부번에 따로 있는 행도 있다."""
    base = g.squash(r["법정주소"])
    if r["본번"] and not re.search(r"\d$", base):
        lot = ("산" if r["산"] == "산번지" else "") + r["본번"] + (f"-{r['부번']}" if r["부번"] not in ("", "0") else "")
        base = f"{base} {lot}"
    return g.build_parcel_query(base)


def road_key(q):
    p = g.road_parts(q) if q else None
    return g.nospace(p[1] + p[2]) if p else ""


def parcel_key(q):
    t = (q or "").split()
    return g.nospace(" ".join(t[-2:])) if len(t) >= 2 else ""


def parcel_tokens(q):
    """시도는 개편으로 달라질 수 있어 뺀 나머지 토큰 (시군구·읍면동·번지)."""
    return (q or "").split()[1:]


def main():
    key = os.environ.get("VWORLD_KEY")
    rows = g.load_rows()
    for r in rows:      # 원본 파일 값 그대로 비교한다 (확인 결과를 담은 address_overrides.csv는 적용하지 않는다)
        r["road_q"], _ = g.build_road_query(r["road_full"])
        r["parcel_q"] = g.build_parcel_query(r["parcel_full"])
    by_code, by_name = load_lh()
    codes = {}
    if MASTER.exists():
        with MASTER.open(encoding="utf-8-sig", newline="") as f:
            codes = {r["단지명"]: r["LH_단지코드"] for r in csv.DictReader(f)}
    vw = g.VWorld(key, g.CACHE)
    out, alt = [], []

    def score(r, c):
        """우편번호 > 도로명 > 지번 순으로 우리 주소와 잘 맞는 LH 후보를 고른다."""
        return 4 * (c["우편"] == r["zip"]) + 2 * (road_key(lh_road(c)) == road_key(r["road_q"])) \
            + (parcel_key(lh_parcel(c)) == parcel_key(r["parcel_q"]))

    for r in rows:
        cands = list(by_name.get(g.nospace(r["name"]), []))
        if codes.get(r["name"]) in by_code and by_code[codes[r["name"]]] not in cands:
            cands.append(by_code[codes[r["name"]]])
        lh = max(cands, key=lambda c: score(r, c)) if cands else None
        how = "단지명" + (f" (같은 이름 {len(cands)}건 중 선택)" if len(cands) > 1 else "")
        o = {"excel_row": r["n"], "단지명": r["name"], "매칭": how if lh else "LH 2025-03 자료에 없음"}
        if lh:
            lr, lp = lh_road(lh), lh_parcel(lh)
            same_road, same_parcel = road_key(r["road_q"]) == road_key(lr), parcel_tokens(r["parcel_q"]) == parcel_tokens(lp)
            notes = []
            if road_key(lr) and same_road and (r["road_q"] or "").split()[:2] != (lr or "").split()[:2]:
                notes.append("행정구역 개편(시군구·시도 명칭만 다름)")
            if not same_road:
                notes.append("도로명 번호가 다름")
                alt.append((r, lr))
            if not lp:
                notes.append("LH 지번 없음")
            elif not same_parcel:
                po, pl = parcel_tokens(r["parcel_q"]), parcel_tokens(lp)
                notes.append("지번 표기가 다름: 파일 " + (",".join(t for t in po if t not in pl) or "-")
                             + " / LH " + (",".join(t for t in pl if t not in po) or "-"))
            o.update({"LH_단지코드": lh["LH코드"], "LH_단지명": lh["단지명"], "파일_도로명": r["road_q"], "LH_도로명": lr,
                      "도로명_일치": "예" if same_road else "아니오", "파일_지번": r["parcel_q"], "LH_지번": lp or "",
                      "지번_일치": "" if not lp else ("예" if same_parcel else "아니오"),
                      "파일_우편번호": r["zip"], "LH_우편번호": lh["우편"], "비고": "; ".join(notes)})
        out.append(o)
    # LH는 개편 전 지역명(광주광역시 등)을 쓰므로, 조회할 때는 우리 파일의 지역명에 LH의 도로명+번호를 붙인다
    alt = [(r, f"{g.road_parts(r['road_q'])[0]} {g.road_parts(lq)[1]} {g.road_parts(lq)[2]}") for r, lq in alt]
    if key:
        for r, lq in alt:
            vw.fwd_raw("road", lq)
    byrow = {o["excel_row"]: o for o in out}
    for r, lq in alt:
        res, ours = vw.fwd("road", lq), vw.fwd("road", r["road_q"])
        o = byrow[r["n"]]
        if res and res["status"] == "OK" and g.exact_road(lq, res) and ours and ours["status"] == "OK":
            o["LH도로명_조회"] = "정확 일치"
            o["LH도로명_거리m"] = f"{g.haversine_m(res['x'], res['y'], ours['x'], ours['y']):.0f}"
        else:
            o["LH도로명_조회"] = "조회 안 됨"
    cols = ["excel_row", "단지명", "매칭", "LH_단지코드", "LH_단지명", "파일_도로명", "LH_도로명", "도로명_일치",
            "LH도로명_조회", "LH도로명_거리m", "파일_지번", "LH_지번", "지번_일치", "파일_우편번호", "LH_우편번호", "비고"]
    g.OUT.mkdir(parents=True, exist_ok=True)
    with (g.OUT / "lh_address_check.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, cols, restval="")
        w.writeheader()
        w.writerows(out)
    m = [o for o in out if "LH_단지코드" in o]
    print(f"단지 {len(out)}곳 중 LH 매칭 {len(m)}곳, 도로명 번호가 다른 곳 {sum(o['도로명_일치'] == '아니오' for o in m)}, "
          f"지번이 다른 곳 {sum(o['지번_일치'] == '아니오' for o in m)} → {g.OUT / 'lh_address_check.csv'}")


if __name__ == "__main__":
    main()
