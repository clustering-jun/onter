"""LLM 결과를 미리 만들어 둔다. 실행 중인 플랫폼 서버의 API를 불러서, 서버의 캐시(data/llm_cache.json)에 쌓이게 한다.

    python server/app.py --port 8770          # 먼저 서버를 띄운다(Ollama도 떠 있어야 한다)
    python tools/prefill_llm.py               # 전부
    python tools/prefill_llm.py --only plan   # 한 단계만(plan, explain, checklist)
    python tools/prefill_llm.py --top 5       # 점검표는 단지마다 위에서 5개까지만

만드는 것(기본 조건의 화면에 나오는 것)
- plan      실행 계획의 묶음 설명: 단지 318곳 × 조건 12가지(예산 50만·100만·150만·200만 원 × 개수 4·6·8개 이내)
- explain   추천 근거 문장: 순위 10개는 배치(project/model/outputs/llm)로 이미 있으므로, 분야별 보기에만 나오는 후보
- checklist 실행 점검표: 순위 10개와 분야별 보기의 후보. 순위가 높은 것부터 만든다

읽기 좋은 사본을 data/llm_generated/*.jsonl에 한 줄씩 남긴다(체크포인트를 겸한다). 끊겨도 다시 실행하면 남은 것만 한다.
서버 오류로 실패한 건은 남기지 않으므로 다시 실행하면 다시 시도한다.
"""
import argparse
import json
import sys
import threading
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "llm_generated"
BUDGETS, NMAX = [1000000, 500000, 1500000, 2000000], [6, 4, 8]            # 정적 사이트(tools/build_static.py)의 실행 계획 격자와 같다. 기본 조건이 맨 앞
PLAN_VARIANTS = [(f"예산 {b // 10000}만 원·{n}개 이내", dict(budget=b, n_max=n)) for n in NMAX for b in BUDGETS]


def call(base, path, body=None, timeout=300):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def load_done(path):
    done = set()
    if path.exists():
        for line in path.open(encoding="utf-8"):
            try:
                done.add(json.loads(line)["key"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def run_phase(name, jobs, work, workers):
    """jobs: [(key, 인자)] → work(인자)가 돌려준 dict를 jsonl에 쓴다. None이면(서버 오류) 쓰지 않는다."""
    path = OUT / f"{name}.jsonl"
    done = load_done(path)
    todo = [(k, a) for k, a in jobs if k not in done]
    print(f"[{name}] 대상 {len(jobs)}건, 끝난 것 {len(jobs) - len(todo)}건, 남은 것 {len(todo)}건", flush=True)
    if not todo:
        return
    if path.exists() and path.stat().st_size and not path.read_bytes().endswith(b"\n"):
        path.open("a", encoding="utf-8").write("\n")
    lock, t0, src, err = threading.Lock(), time.time(), Counter(), 0

    def one(k, a):
        try:
            return k, work(a)
        except Exception as e:
            return k, dict(_error=repr(e))

    with path.open("a", encoding="utf-8") as f, ThreadPoolExecutor(workers) as ex:
        for i, fut in enumerate(as_completed([ex.submit(one, k, a) for k, a in todo]), 1):
            k, row = fut.result()
            if row is None or "_error" in row:
                err += 1
                if err <= 3 and row:
                    print("  오류:", k, row["_error"], flush=True)
            else:
                src[row["source"]] += 1
                with lock:
                    f.write(json.dumps(dict(key=k, **row), ensure_ascii=False) + "\n")
                    f.flush()
            if i % 50 == 0 or i == len(todo):
                el = time.time() - t0
                print(f"  {i}/{len(todo)}  {dict(src)}  오류 {err}  {60 * i / el:.0f}건/분  남은 시간 약 {(len(todo) - i) * el / i / 60:.0f}분", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8770")
    ap.add_argument("--workers", type=int, default=6, help="동시 요청 수. Ollama의 OLLAMA_NUM_PARALLEL과 맞춘다")
    ap.add_argument("--only", choices=["plan", "explain", "checklist"])
    ap.add_argument("--top", type=int, default=10, help="점검표를 만들 순위 범위")
    ap.add_argument("--variants", type=int, default=len(PLAN_VARIANTS), help="묶음 설명을 만들 조건 수(앞에서부터. 1이면 기본 조건만)")
    ap.add_argument("--no-extra", action="store_true", help="점검표에서 분야별 보기에만 나오는 후보는 뺀다")
    ap.add_argument("--limit", type=int, default=0, help="단지 수 제한(시험용)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    st = call(a.base, "/api/llm/status")
    if not st["available"]:
        sys.exit(f"LLM을 쓸 수 없습니다: {st['error']}")
    OUT.mkdir(parents=True, exist_ok=True)
    complexes = call(a.base, "/api/complexes")
    complexes = complexes["items"] if isinstance(complexes, dict) else complexes
    names = {c["id"]: c["name"] for c in complexes}
    ids = list(names)[:a.limit or None]

    # 단지마다 화면에 나오는 후보: 순위 목록과 분야별 보기
    ranked, extra = [], []
    for cid in ids:
        r = call(a.base, f"/api/recommend?id={cid}")
        top = {x["std_id"] for x in r["items"]}
        ranked += [(x["rank"], cid, x["std_id"], x["name"]) for x in r["items"]]
        seen = set(top)
        for d in r["by_domain"]:
            for x in d["items"]:
                if x["std_id"] not in seen:
                    seen.add(x["std_id"])
                    extra.append((99, cid, x["std_id"], x["name"]))
    ranked.sort()                                                      # 순위 1을 모든 단지에서 먼저
    print(f"단지 {len(ids)}곳, 순위 후보 {len(ranked)}건, 분야별 보기에만 나오는 후보 {len(extra)}건", flush=True)

    def w_plan(arg):
        cid, label, opt = arg
        x = call(a.base, "/api/llm/plan", dict(id=cid, **opt))
        if str(x.get("origin", "")).startswith("error") or x["source"] == "template" and x["plan"]["items"]:
            return None
        return dict(complex_id=cid, complex=names[cid], variant=label, n=x["plan"]["n"], programs=[i["name"] for i in x["plan"]["items"]],
                    text=x["text"], source=x["source"], draft=x["draft"], why=x.get("why"))

    def w_explain(arg):
        rank, cid, sid, name = arg
        x = call(a.base, "/api/llm/explain", dict(id=cid, sid=sid))
        if x.get("origin", "").startswith(("error", "llm_unavailable")):
            return None
        return dict(complex_id=cid, complex=names[cid], std_id=sid, name=name, text=x["text"], source=x["source"], draft=x["draft"])

    def w_check(arg):
        rank, cid, sid, name = arg
        x = call(a.base, "/api/llm/checklist", dict(id=cid, sid=sid))
        if x.get("origin", "").startswith(("error", "llm_unavailable")):
            return None
        return dict(complex_id=cid, complex=names[cid], std_id=sid, name=name, rank=None if rank == 99 else rank, sections=x["sections"], source=x["source"], tries=x.get("tries"))

    phases = [("plan", [(f"{cid}|{label}", (cid, label, opt)) for label, opt in PLAN_VARIANTS[:a.variants] for cid in ids], w_plan),
              ("explain", [(f"{c}|{s}", (r, c, s, n)) for r, c, s, n in extra], w_explain),
              ("checklist", [(f"{c}|{s}", (r, c, s, n)) for r, c, s, n in [x for x in ranked if x[0] <= a.top] + ([] if a.no_extra else extra)], w_check)]
    for name, jobs, work in phases:
        if not a.only or a.only == name:
            run_phase(name, jobs, work, a.workers)

    summary = {}
    for name, _, _ in phases:
        p = OUT / f"{name}.jsonl"
        if p.exists():
            rows = [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]
            summary[name] = dict(n=len(rows), by_source=dict(Counter(r["source"] for r in rows)))
    summary["cache_entries"] = call(a.base, "/api/llm/status")["cached"]
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
