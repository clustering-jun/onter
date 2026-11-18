# -*- coding: utf-8 -*-
"""임대단지 관리현황 원본에 확정 주소를 반영하고 좌표를 붙인 최종 CSV를 만든다.

입력  data/raw/주택관리공단(주)_임대단지 관리현황_20260901.csv (cp949)
      data/processed/complex_geocode_20261117_v1/complex_coords.csv   (geocode_complexes.py 결과)
      data/processed/complex_geocode_20261117_v1/address_overrides.csv (확정한 주소와 근거)
출력  data/processed/complex_geocode_20261117_v1/주택관리공단(주)_임대단지 관리현황_20260901_주소수정_좌표추가.csv
        원본 54개 열 + 경도 + 위도 + 주소수정내역. 고친 행만 기본주소·상세주소·기본상세·지번기본주소가 바뀐다.

실행  python -I -X utf8 build_final_complex_csv.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geocode_complexes as g

OUT = g.OUT
FINAL = OUT / "주택관리공단(주)_임대단지 관리현황_20260901_주소수정_좌표추가.csv"
STRAY_NUMBER = {"제주아라"}     # 상세주소 앞에 번호 조각 '1'이 남은 행. LH·VWorld는 '인다12길 1'로 일치


def clean_road(full):
    """원본 도로명 문자열 → (도로명+번호, 그 뒤에 붙은 건물명·괄호). 깨진 문자(？)·공백만 보정한다."""
    s = g.squash((full or "").replace("？", " ").replace("?", " "))
    head, paren = (s.split("(", 1) + [""])[:2] if "(" in s else (s, "")
    head = g.squash(head)
    head = g.RE_FIX1.sub(r"\1\2", head)
    head = g.RE_FIX3.sub(r"\1 \2", g.RE_FIX2.sub(r"\1\2 \3", head))
    m = g.RE_ROAD.match(head)
    tail = " ".join(t for t in (head[m.end():].strip(), f"({paren}" if paren else "") if t)
    return (f"{m.group('pre')} {m.group('num')}" if m else head), tail


def typo_fixed(full):
    """깨진 문자(？)와 '봉래길176'·'미리벌중앙 로35' 같은 오타만 고친 전체 문자열.
    '도봉로 180길'처럼 띄어쓰기만 다른 표기는 틀린 주소가 아니므로 그대로 둔다."""
    s = g.squash((full or "").replace("？", " ").replace("?", " "))
    return g.squash(g.RE_FIX3.sub(r"\1 \2", g.RE_FIX2.sub(r"\1\2 \3", s)))


def new_road(r):
    """고친 기본주소(도로명+번호+괄호). 바뀌지 않으면 None."""
    orig = g.squash(r["road_full"])
    split = r["road_extra"][:1].isdigit()           # 건물번호가 상세주소 열로 넘어가 있음
    ovr = r["road_q"] != g.build_road_query(r["road_full"])[0]
    if ovr or r["name"] in STRAY_NUMBER:
        base, tail = clean_road(r["road_full"])
        if r["name"] in STRAY_NUMBER and tail[:1].isdigit():
            tail = tail.split(" ", 1)[1]
        full = " ".join(t for t in (r["road_q"] if ovr else base, tail) if t)
    else:
        full = typo_fixed(r["road_full"])
    return full if full != orig or split else None


def new_parcel(r):
    """고친 지번기본주소(원본의 건물명 꼬리는 유지). 바뀌지 않으면 None."""
    old_q = g.build_parcel_query(r["parcel_full"])
    if r["parcel_q"] == old_q:
        return None
    tail = g.squash(r["parcel_full"]).split()[len(old_q.split()):]
    return " ".join([r["parcel_q"]] + tail)


def reason(r, kind):
    if kind == "parcel" or r["road_q"] != g.build_road_query(r["road_full"])[0]:
        b = r["basis"]
        return "LH 주택별현황집계" if "LH" in b else "마이홈포털" if "마이홈" in b else "사용자 확인"
    if r["name"] in STRAY_NUMBER:
        return "상세주소 열에 남은 번호 조각 '1' 제거. LH·VWorld는 '인다12길 1'로 일치"
    if r["road_extra"][:1].isdigit():
        return "건물번호가 상세주소 열에 있어 기본주소에 합침"
    return "깨진 문자·오타 보정"


def main():
    rows = g.load_rows()
    g.prepare(rows)
    coords = {int(c["excel_row"]): c for c in csv.DictReader((OUT / "complex_coords.csv").open(encoding="utf-8-sig", newline=""))}
    with g.RAW.open(encoding="cp949", newline="") as f:
        data = list(csv.reader(f))
    header, body = data[0], data[1:]
    out = [header + ["경도", "위도", "주소수정내역"]]
    n_fix = 0
    for r, row in zip(rows, body):
        c, notes, row = coords[r["n"]], [], list(row)
        nr, npc = new_road(r), new_parcel(r)
        if nr:
            old = f"{r['road_col']} | {r['road_extra']}" if r["road_extra"][:1].isdigit() else g.squash(r["road_full"])
            notes.append(f"도로명 '{old}' → '{nr}' ({reason(r, 'road')})")
            row[3], row[4], row[5] = nr, "", nr
        if npc:
            notes.append(f"지번 '{g.squash(r['parcel_full'])}' → '{npc}' ({reason(r, 'parcel')})")
            row[6] = npc
        n_fix += bool(notes)
        out.append(row + [c["lon"], c["lat"], " / ".join(notes)])
    assert all(o[-3] and o[-2] for o in out[1:]), "좌표가 빈 행이 있다"
    try:
        enc = "cp949"
        FINAL.write_bytes(b"")
        with FINAL.open("w", encoding=enc, newline="") as f:
            csv.writer(f).writerows(out)
    except UnicodeEncodeError:
        enc = "utf-8-sig"
        with FINAL.open("w", encoding=enc, newline="") as f:
            csv.writer(f).writerows(out)
    print(f"{len(out) - 1}행 중 주소를 고친 행 {n_fix}, 인코딩 {enc} → {FINAL}")


if __name__ == "__main__":
    main()
