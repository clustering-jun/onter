"""정적 판(GitHub Pages용)을 만든다. 서버 없이 열 수 있게 화면 파일과, 미리 계산한 API 응답을 한 폴더에 모은다.

    python tools/build_static.py                 # project/docs 에 만든다
    python tools/build_static.py --out ../site   # 다른 곳에
    python tools/build_static.py --limit 5       # 단지 5곳만(시험용)

- 추천은 필요 반영 정도 × 분야 고르게의 격자(W × LAM)로, 실행 계획은 예산 × 프로그램 수의 격자(BUDGET × NMAX)로 미리 계산한다.
- LLM 문장은 새로 만들지 않는다. 배치 결과와 data/llm_cache.json에 있는 것만 싣고, 없으면 규칙 문장·규칙 점검표를 싣는다.
  먼저 tools/prefill_llm.py로 캐시를 채워 두면 그만큼 LLM 문장이 들어간다.
- 사용자 입력(data/user_state.json)은 싣지 않는다. Knowledge Graph 탭은 서버가 있어야 해서 뺀다.
"""
import argparse
import json
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import app as A                      # noqa: E402
import engine as G                   # noqa: E402
from catalog import Catalog          # noqa: E402
from llm_service import LLMService   # noqa: E402

W, LAM = [0.0, 0.2, 0.4, 0.6], [0.0, 0.25, 0.5]
BUDGET, NMAX = [500000, 1000000, 1500000, 2000000], [4, 6, 8]
KS = [5, 10, 15]


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8", newline="\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(G.PROJECT / "docs"))
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    out, t0 = Path(a.out).resolve(), time.time()
    if out.exists():
        if not (out / ".onter-static").exists() and any(out.iterdir()):
            sys.exit(f"{out} 은(는) 이 스크립트가 만든 폴더가 아닙니다. 다른 --out을 주십시오.")
        shutil.rmtree(out)
    shutil.copytree(ROOT / "web", out, ignore=shutil.ignore_patterns("README.txt"))
    (out / ".onter-static").write_text("tools/build_static.py가 만든 폴더. 직접 고치지 않는다.\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    html = (out / "index.html").read_text(encoding="utf-8")
    html = html.replace('    <a data-tab="kg" href="#/kg">Knowledge Graph</a>\n', "")
    html = html.replace('<script type="module" src="js/main.js">', '<script>window.ONTER_STATIC = true;</script>\n<script type="module" src="js/main.js">')
    assert "ONTER_STATIC" in html and 'data-tab="kg"' not in html
    (out / "index.html").write_text(html, encoding="utf-8", newline="\n")

    eng = G.Engine()
    cat = Catalog(eng)
    llm = LLMService(eng, ROOT / "data" / "llm_cache.json")
    llm.status = lambda: dict(available=False, error="정적 판 빌드", cached=len(llm.cache))     # 새로 만들지 않고 있는 것만 쓴다
    A.ENG, A.KG, A.WEB = eng, None, out
    api = out / "api"
    ids = eng.ids[:a.limit or None]
    meta = dict(A.meta(), static=True, kg=False, grid=dict(w=W, lam=LAM, budget=BUDGET, n_max=NMAX), built=time.strftime("%Y-%m-%d %H:%M"))
    dump(api / "meta.json", meta)
    cx = eng.complex_list()
    dump(api / "complexes.json", [c for c in cx if c["id"] in set(ids)] if a.limit else cx)
    progs = cat.programs()
    dump(api / "programs.json", progs)
    for p in progs:
        dump(api / "program" / f"{p['std_id']}.json", cat.program(p["std_id"]))
    for name in ("cases", "happycall", "analytics"):
        dump(api / f"{name}.json", getattr(cat, name)())

    src, prefix_miss = Counter(), 0
    for n, cid in enumerate(ids, 1):
        dump(api / "complex" / f"{cid}.json", dict(complex=eng.complex_detail(cid, None), matrix=eng.program_matrix(cid, None)))
        rec, sids = {}, []
        for w in W:
            for lam in LAM:
                by_k = {k: eng.recommend(cid, w, lam, k, None, None) for k in KS}
                r = by_k[KS[-1]]
                for k in KS[:-1]:                                    # 화면은 긴 목록의 앞부분을 잘라 쓴다. 그래도 되는지 확인
                    prefix_miss += [x["std_id"] for x in by_k[k]["items"]] != [x["std_id"] for x in r["items"][:k]]
                r["mix"] = {str(k): by_k[k]["list_mix"] for k in KS}
                rec[f"{w:g}|{lam:g}"] = r
                sids += [x["std_id"] for x in r["items"]] + [x["std_id"] for d in r["by_domain"] for x in d["items"]]
        dump(api / "rec" / f"{cid}.json", rec)
        cand = {}
        for sid in dict.fromkeys(sids):
            ex, ck = llm.explain(cid, sid), llm.checklist(cid, sid)
            src["explain:" + ex["source"]] += 1
            src["checklist:" + ck["source"]] += 1
            cand[sid] = dict(detail=G.run(lambda: eng.candidate(cid, sid, None)), explain=dict(text=ex["text"], source=ex["source"]),
                             checklist=dict(sections=ck["sections"], source=ck["source"]))
        dump(api / "cand" / f"{cid}.json", cand)
        plans = {}
        for b in BUDGET:
            for nm in NMAX:
                plan = G.run(lambda: eng.plan(cid, None, None, b, None, nm, None, None))
                br = llm.plan_brief(plan, cid)
                src["plan:" + br["source"]] += 1
                plans[f"{b}|{nm}"] = dict(plan=plan, brief=dict(text=br["text"], source=br["source"]))
        dump(api / "plan" / f"{cid}.json", plans)
        if n % 20 == 0 or n == len(ids):
            print(f"  단지 {n}/{len(ids)}  {time.time() - t0:.0f}초", flush=True)

    files = [p for p in out.rglob("*") if p.is_file()]
    summary = dict(built=meta["built"], complexes=len(ids), files=len(files), mb=round(sum(p.stat().st_size for p in files) / 1e6, 1), llm=dict(sorted(src.items())),
                   prefix_mismatch=prefix_miss, seconds=round(time.time() - t0))
    dump(api / "build.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if prefix_miss:
        print(f"주의: 짧은 목록이 긴 목록의 앞부분과 다른 경우가 {prefix_miss}번 있었습니다. 후보 수를 바꿨을 때 서버 판과 다를 수 있습니다.")


if __name__ == "__main__":
    main()
