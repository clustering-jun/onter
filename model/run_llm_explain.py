"""추천 근거 문장을 로컬 LLM(Ollama)으로 다듬는 배치.

    powershell -ExecutionPolicy Bypass -File serve_ollama.ps1     # 서버(병렬 8)
    python run_llm_explain.py --sample 300                        # 표본으로 속도·통과율 점검
    python run_llm_explain.py                                     # 전체 3,180건

- 결과는 outputs/llm/explanations_llm.jsonl에 한 줄씩 바로 쓴다(체크포인트). 중간에 끊겨도 다시 실행하면 남은 것만 한다.
- 문장마다 check_grounded(사실에 없는 숫자·단정 표현)와 형식 검사를 하고, 떨어지면 이유를 붙여 한 번 더 시킨 뒤 그래도 떨어지면 템플릿 문장을 쓴다.
- 끝나면 통과율·속도를 results/llm_explain_summary.json에 남긴다.
"""
import argparse
import json
import random
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from onter import config as C, explain as X, llm as L

SRC = C.OUTPUTS / "recommendations_detail.jsonl"
OUT_DIR = C.OUTPUTS / "llm"


def key(r):
    return f"{r['complex_id']}|{r['std_id']}"


def load_done(path):
    done = {}
    if path.exists():
        for line in path.open(encoding="utf-8"):
            try:
                r = json.loads(line)
                done[r["key"]] = r
            except (json.JSONDecodeError, KeyError):   # 끊기면서 반쯤 쓰인 줄
                continue
    return done


def summarize(rows, sec, workers, fn):
    n = len(rows)
    src = Counter(r["source"] for r in rows)
    first = sum(r["source"] == "llm" and r["attempts"] == 1 for r in rows)
    fails = [t["check"] for r in rows for t in r["tries"] if not t["check"]["ok"]]
    llm = [r for r in rows if r["source"] == "llm"]
    return dict(model=fn.model, options=fn.options, workers=workers, n=n,
                pass_first_try=round(first / n, 4), pass_after_retry=round(src["llm"] / n, 4), template_fallback=round(src["template_fallback"] / n, 4),
                fail_reasons=dict(unknown_numbers=sum(bool(c["unknown_numbers"]) for c in fails), banned=sum(bool(c["banned"]) for c in fails),
                                  form=dict(Counter(w for c in fails for w in c["form"])),
                                  binding=dict(Counter(w.split(":")[0] for c in fails for w in c["binding"]))),
                banned_terms=dict(Counter(b for c in fails for b in c["banned"])),
                mean_chars_llm=round(sum(len(r["text"]) for r in llm) / max(1, len(llm)), 1),
                mean_chars_template=round(sum(len(r["draft"]) for r in rows) / n, 1),
                names_program=round(sum(r["name"] in r["text"] for r in llm) / max(1, len(llm)), 4),
                says_candidate=round(sum("후보" in r["text"] for r in llm) / max(1, len(llm)), 4),
                seconds=round(sec, 1), per_item_sec=round(sec / max(1, n), 3), items_per_min=round(60 * n / max(sec, 1e-9), 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0, help="무작위 표본 크기(0이면 전체)")
    ap.add_argument("--workers", type=int, default=8, help="동시 요청 수. 서버의 OLLAMA_NUM_PARALLEL과 맞춘다")
    ap.add_argument("--retries", type=int, default=1)
    ap.add_argument("--temperature", type=float, default=L.OPTIONS["temperature"])
    ap.add_argument("--model", default=L.MODEL)
    ap.add_argument("--tag", default="", help="출력 파일 이름에 붙일 꼬리표(비교 실험용)")
    ap.add_argument("--fresh", action="store_true", help="체크포인트를 버리고 처음부터")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    err = L.ping(a.model)
    if err:
        sys.exit(err)
    recs = [json.loads(l) for l in SRC.open(encoding="utf-8")]
    if a.sample:
        recs = random.Random(C.SEED).sample(recs, a.sample)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = (f"_{a.tag}" if a.tag else "") + (f"_sample{a.sample}" if a.sample else "")
    out = OUT_DIR / f"explanations_llm{tag}.jsonl"
    if a.fresh and out.exists():
        out.unlink()
    done = load_done(out)
    todo = [r for r in recs if key(r) not in done]
    print(f"대상 {len(recs)}건, 이미 끝난 것 {len(recs) - len(todo)}건, 남은 것 {len(todo)}건 → {out.name}")

    fn = L.ollama_fn(model=a.model, system=X.SYSTEM, temperature=a.temperature)
    lock, t0, new = threading.Lock(), time.time(), []

    def work(rec):
        t = time.time()
        try:
            res = X.explain(rec, llm_fn=fn, retries=a.retries)
        except Exception as e:   # 서버 오류는 저장하지 않는다 → 다음 실행에서 다시 한다
            return rec, None, repr(e)
        return rec, dict(key=key(rec), complex_id=rec["complex_id"], std_id=rec["std_id"], rank=rec["rank"], name=rec["name"], text=res["text"], source=res["source"],
                         attempts=res["attempts"], draft=X.template(rec), tries=res["tries"], sec=round(time.time() - t, 2)), None

    errors = 0
    if out.exists() and out.stat().st_size and not out.read_bytes().endswith(b"\n"):   # 끊기면서 반쯤 쓰인 줄에 새 줄이 붙지 않게
        out.open("a", encoding="utf-8").write("\n")
    with out.open("a", encoding="utf-8") as f, ThreadPoolExecutor(a.workers) as ex:
        for i, fut in enumerate(as_completed([ex.submit(work, r) for r in todo]), 1):
            rec, row, e = fut.result()
            if row is None:
                errors += 1
                if errors <= 3:
                    print("  오류:", key(rec), e)
                continue
            with lock:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
            new.append(row)
            if i % 50 == 0 or i == len(todo):
                ok = sum(r["source"] == "llm" for r in new)
                el = time.time() - t0
                print(f"  {i}/{len(todo)}  통과 {ok / len(new):.1%}  {60 * len(new) / el:.0f}건/분  남은 시간 약 {(len(todo) - i) * el / i / 60:.1f}분")

    sec = time.time() - t0
    rows = list(load_done(out).values())
    if not rows:
        sys.exit("결과가 없습니다.")
    s = summarize(rows, sec, a.workers, fn)
    if new:   # 속도는 이번 실행분으로만 계산
        s.update(seconds=round(sec, 1), n_this_run=len(new), per_item_sec=round(sec / len(new), 3), items_per_min=round(60 * len(new) / sec, 1),
                 tokens_per_sec=round(fn.tokens / sec, 1))
    else:
        s.update(seconds=None, n_this_run=0, per_item_sec=None, items_per_min=None)
    s["errors"] = errors
    (C.RESULTS / f"llm_explain_summary{tag}.json").write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(s, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
