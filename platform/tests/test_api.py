"""플랫폼 API 점검(서버를 띄우지 않고 함수로 직접 부른다).  python tests/test_api.py [--llm]"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
sys.stdout.reconfigure(encoding="utf-8")
import app, engine as G
import numpy as np, pandas as pd

app.boot()
E, ok = app.ENG, []


def check(name, cond, info=""):
    ok.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name, info)


# 1. 모든 GET 경로가 JSON으로 나간다(NaN 없음)
cid = "KOH_1"
for route, q in [("meta", {}), ("complexes", {}), ("complex", {"id": cid}), ("matrix", {"id": cid}), ("recommend", {"id": cid}), ("programs", {}), ("program", {"sid": "I02"}),
                 ("search", {"q": "빨래"}), ("cases", {}), ("happycall", {}), ("analytics", {}), ("state", {"id": cid}), ("llm/status", {})]:
    try:
        out = app.api_get(route, q)
        raw = json.dumps(out, ensure_ascii=False, allow_nan=False)
        check(f"GET {route}", len(raw) > 2, f"{len(raw):,}자")
    except Exception as e:
        check(f"GET {route}", False, repr(e))

# 2. 기본 순위는 오프라인 산출물과 같다
ref = pd.read_csv(G.C.OUTPUTS / "m3_recommendations_top10.csv")
same = sum([x["std_id"] for x in E.recommend(c)["items"]] == list(g.sort_values("rank").std_id) for c, g in ref.groupby("complex_id"))
check("기본 순위 = 오프라인 산출물", same == ref.complex_id.nunique(), f"{same}/{ref.complex_id.nunique()}")

# 3. 속도
ms = [E.recommend(c)["ms"] for c in E.ids]
pl = [E.plan(c) for c in E.ids]
check("순위 재계산 속도", np.median(ms) < 10, f"중앙 {np.median(ms):.1f}ms, 최대 {max(ms):.1f}ms")
check("정수계획 풀이 속도", np.median([p["solve_ms"] for p in pl]) < 10, f"중앙 {np.median([p['solve_ms'] for p in pl]):.1f}ms, 최대 {max(p['solve_ms'] for p in pl):.1f}ms")
check("묶음이 한도를 지킨다", all(p["cost"] <= p["budget"] + 1 and p["hours"] <= p["hours_limit"] + 1e-6 and p["n"] <= p["n_max"] for p in pl if p["feasible"]))

# 4. 상태 구분과 제외 정책
norec = [c for c in E.ids if c not in E.act][0]
r = E.recommend(norec)
check("기록 없는 단지는 '기록 없음'으로 표시", all(x["status"] == "no_record" for x in r["items"]) and not r["has_records"])
r0 = E.recommend(cid)
a, b, c3 = [x["std_id"] for x in r0["items"][:3]]
st = {"excluded": {a: {"kind": "infeasible", "count": 1}, b: {"kind": "not_now", "count": 1}, c3: {"kind": "already", "count": 1}}, "confirmed": {}}
r1 = E.recommend(cid, st=st)
got = [x["std_id"] for x in r1["items"]]
check("제외한 프로그램은 후보가 충분하면 나오지 않는다", not ({a, b, c3} & set(got)) and len(got) == 10)
stt = E.statuses(cid, st)
check("상태 구분", stt[a] == "infeasible" and stt[b] == "snoozed" and stt[c3] == "declared")
# 후보 부족: 분야 하나로 좁히고 그 분야 후보를 모두 '지금은 아님'으로 뺀다
dom = "N6"
fresh = [x["std_id"] for x in E.recommend(cid, domain=dom)["items"] if x["tag"] == "fresh"]
st2 = {"excluded": {s: {"kind": "not_now", "count": 1} for s in fresh[:-1]} | {fresh[-1]: {"kind": "infeasible", "count": 1}}, "confirmed": {}}
r2 = E.recommend(cid, domain=dom, st=st2)
tags = {x["std_id"]: x["tag"] for x in r2["items"]}
check("후보 부족 때 '운영 불가능'은 되살리지 않는다", fresh[-1] not in tags, str(r2["shortage"]))
check("'지금은 아님' 1~2회는 다시 보여 줄 수 있다", all(tags.get(s) == "resurfaced" for s in fresh[:-1]))
st3 = {"excluded": {s: {"kind": "not_now", "count": 3} for s in fresh}, "confirmed": {}}
r3 = E.recommend(cid, domain=dom, st=st3)
check("3번 뺀 프로그램은 더 나오지 않는다", not (set(fresh) & {x["std_id"] for x in r3["items"]}), f"보여 준 수 {len(r3['items'])}")
check("채운 순서: 새 후보 → 재개 검토 → 다시 제안", [x["tag"] for x in r2["items"]] == sorted([x["tag"] for x in r2["items"]], key=["fresh", "resume", "resurfaced"].index))

# 5. 확인된 필요가 순위에 반영된다
st4 = {"excluded": {}, "confirmed": {"N6": {"level": "high"}, "N1": {"level": "low"}}}
r4 = E.recommend(cid, st=st4)
n6 = lambda r: sum(x["domain"] == "N6" for x in r["items"])
check("확인된 필요 반영('높음' 분야에서 2개 이상)", n6(r4) >= 2 and n6(r4) > n6(r0) and r4["confirmed_used"] == ["N1", "N6"], f"N6 프로그램 {n6(r0)}개 → {n6(r4)}개")

# 6. 조절 손잡이
check("w를 올리면 필요 적합이 오른다", np.mean([x["hidden"]["need_fit_pct"] for x in E.recommend(cid, w=0.5, lam=0)["items"]]) > np.mean([x["hidden"]["need_fit_pct"] for x in E.recommend(cid, w=0, lam=0)["items"]]))
p1, p2 = E.plan(cid, budget=2e5, hours=30), E.plan(cid, budget=3e6, hours=200, n_max=8)
check("한도를 줄이면 묶음이 줄어든다", p1["cost"] <= 2e5 and p1["hours"] <= 30 and p2["n"] >= p1["n"], f"{p1['n']}개 → {p2['n']}개")

# 7. 후보 상세·점검표
cd = E.candidate(cid, a)
check("후보 상세", len(cd["rule_checklist"]) == 5 and cd["explanation"]["template"] and "evidence" in cd)
check("배치 LLM 문장 연결", sum(E.candidate(cid, x["std_id"])["explanation"]["llm"] is not None for x in r0["items"]) >= 5)

# 8. 결측 표시
d = E.complex_detail(norec)
check("기록 없는 단지의 운영 수치는 결측(None)", d["activity"]["n_records"] is None and d["has_records"] is False)
miss = [c for c in E.ids if pd.isna(E.c.at[c, "d_병원"])][0]
check("거리 결측은 0이 아니라 None", [x for x in E.complex_detail(miss)["near"] if x["label"] == "병원"][0]["km"] is None)

# 9. LLM(선택)
if "--llm" in sys.argv:
    s = app.LLM.status()
    check("LLM 서버", s["available"], str(s))
    if s["available"]:
        t = time.time(); ck = app.LLM.checklist(cid, a, force=True)
        check("LLM 실행 점검표", ck["source"] in ("llm", "rule_fallback") and len(ck["sections"]) == 5, f"{ck['source']} {ck.get('tries')} {time.time() - t:.1f}초")
        print(json.dumps(ck["sections"], ensure_ascii=False, indent=1))
        ex = app.LLM.explain(cid, a)
        check("LLM 근거 문장", ex["text"] and ex["source"] in ("llm", "template", "template_fallback"), f"{ex['source']} / {ex['origin']}")
        pb = app.LLM.plan_brief(E.plan(cid), cid)
        check("LLM 묶음 메모", bool(pb["text"]), pb["source"]); print(pb["text"])

print(f"\n{sum(ok)}/{len(ok)} 통과")
sys.exit(0 if all(ok) else 1)
