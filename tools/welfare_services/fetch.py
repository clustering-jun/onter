"""한국사회보장정보원 복지서비스 목록을 받아 data/processed/welfare_services_v1/에 저장한다(공공데이터포털).

    python tools/welfare_services/fetch.py

- 중앙부처: B554287/NationalWelfareInformationsV001/NationalWelfarelistV001 (개발계정 하루 100회)
- 지자체:   B554287/LocalGovernmentWelfareInformations/LcgvWelfarelist       (개발계정 하루 1,000회)
- 목록 조회만 쓴다(한 번 실행에 약 12회). 상세 조회는 서비스마다 한 번씩 불러야 해서 하루 한도를 넘는다. 자세한 내용은 복지로 링크로 넘긴다.
- 인증키는 project/.secrets/data_go_kr.key 또는 환경 변수 DATA_GO_KR_KEY에서 읽는다. 저장소에는 올리지 않는다.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
OUT = PROJECT / "data" / "processed" / "welfare_services_v1"
BASE = "https://apis.data.go.kr/B554287"
ROWS = 500


def key():
    k = os.environ.get("DATA_GO_KR_KEY") or ""
    f = PROJECT / ".secrets" / "data_go_kr.key"
    if not k and f.exists():
        k = f.read_text(encoding="utf-8").strip()
    if not k:
        sys.exit("인증키가 없습니다. project/.secrets/data_go_kr.key에 넣거나 DATA_GO_KR_KEY로 주십시오.")
    return k


def fetch_all(path, extra):
    rows, page, total = [], 1, None
    while total is None or len(rows) < total:
        q = urllib.parse.urlencode(dict(serviceKey=key(), pageNo=page, numOfRows=ROWS, **extra))
        with urllib.request.urlopen(f"{BASE}/{path}?{q}", timeout=60) as r:
            root = ET.fromstring(r.read())
        if root.findtext("resultCode") not in ("0", "00"):
            sys.exit(f"{path}: {root.findtext('resultCode')} {root.findtext('resultMessage') or ET.tostring(root, encoding='unicode')[:300]}")
        total = int(root.findtext("totalCount"))
        got = [{c.tag: (c.text or "").strip() for c in s} for s in root.findall("servList")]
        if not got:
            break
        rows += got
        print(f"  {path.split('/')[-1]} {len(rows)}/{total}", flush=True)
        page += 1
        time.sleep(0.3)
    return rows


def arr(v):
    return [x.strip().replace(" · ", "·") for x in (v or "").split(",") if x.strip()]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    central = [dict(id=r["servId"], name=r["servNm"], org=" ".join(filter(None, [r.get("jurMnofNm"), r.get("jurOrgNm")])), digest=r.get("servDgst", ""),
                    life=arr(r.get("lifeArray")), theme=arr(r.get("intrsThemaArray")), target=arr(r.get("trgterIndvdlArray")), cycle=r.get("sprtCycNm", ""), kind=r.get("srvPvsnNm", ""),
                    tel=r.get("rprsCtadr", ""), online=r.get("onapPsbltYn") == "Y", views=int(r.get("inqNum") or 0), link=r.get("servDtlLink", ""))
               for r in fetch_all("NationalWelfareInformationsV001/NationalWelfarelistV001", dict(callTp="L", srchKeyCode="001"))]
    local = [dict(id=r["servId"], name=r["servNm"], org=r.get("bizChrDeptNm", ""), sido=r.get("ctpvNm", ""), sgg=r.get("sggNm", ""), digest=r.get("servDgst", ""),
                  life=arr(r.get("lifeNmArray")), theme=arr(r.get("intrsThemaNmArray")), target=arr(r.get("trgterIndvdlNmArray")), cycle=r.get("sprtCycNm", ""), kind=r.get("srvPvsnNm", ""),
                  apply=r.get("aplyMtdNm", ""), views=int(r.get("inqNum") or 0), updated=r.get("lastModYmd", ""), link=r.get("servDtlLink", ""))
             for r in fetch_all("LocalGovernmentWelfareInformations/LcgvWelfarelist", {})]
    for name, rows in (("central", central), ("local", local)):
        rows = list({r["id"]: r for r in rows}.values())
        (OUT / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    meta = dict(fetched=time.strftime("%Y-%m-%d"), source="한국사회보장정보원(공공데이터포털) 중앙부처복지서비스·지자체복지서비스 목록 조회", central=len(central), local=len(local))
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
