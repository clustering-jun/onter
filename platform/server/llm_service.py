"""로컬 LLM(Ollama) 서비스: 추천 근거 문장, 실행 점검표, 연간 묶음 메모.

원칙
- LLM은 문장만 만든다. 입력은 엔진이 만든 사실 목록뿐이고, 순위·필요·비용 계산에는 쓰지 않는다.
- 출력은 검사를 통과해야 쓴다(사실에 없는 숫자, 단정 표현, 형식). 떨어지면 한 번 다시 시키고, 그래도 떨어지면 규칙으로 만든 기본값을 돌려준다.
- 결과는 data/llm_cache.json에 사실 목록의 해시로 저장한다. 사실이 바뀌면 다시 만든다.
"""
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

from engine import C, X, run
from onter import llm as L

SECTIONS = ["준비", "협력·자원", "진행", "확인·기록", "주의"]
LOOSE = ["참여율", "효과", "성공", "통찰", "월부터", "월까지", "분기", "상대적으로", "비교적", "확인 중"]      # 사실에 없는 해석·기간 표현
MONTH_RANGE = re.compile(r"\d+\s*월\s*[~\-–]")

CHECK_SYSTEM = """당신은 공공임대 단지 관리소 직원이 복지 프로그램을 처음 실행할 때 쓸 '실행 점검표'를 만듭니다.
규칙:
1. '사실'에 있는 내용만 씁니다. 사실에 없는 숫자·기관·장소·사례를 만들지 않습니다. 숫자는 사실에 적힌 그대로 옮깁니다.
2. 항목은 직원이 바로 할 수 있는 행동으로 씁니다("~한다", "~확인한다"). 한 항목은 한 문장, 60자 안팎입니다.
3. 이 단지의 여건(협력 이력, 공간, 주거복지사 배치)을 반영합니다. 여건이 '이력·가까운 시설 없음'이면 새로 연락해야 한다고 씁니다.
4. 사례집의 걸림돌과 해결은 '주의'에 넣고, 다른 단지의 해결 방법이 이 단지에서도 통한다고 단정하지 않습니다.
5. 효과를 약속하지 않습니다. '반드시', '예방할 수 있다', '해결됩니다'를 쓰지 않습니다.
6. 아래 형식의 JSON만 출력합니다. 다섯 묶음을 모두 채우고 묶음마다 2~4개 항목을 씁니다(주의는 1~4개).
{"준비": ["..."], "협력·자원": ["..."], "진행": ["..."], "확인·기록": ["..."], "주의": ["..."]}"""

PLAN_SYSTEM = """당신은 공공임대 단지 관리소 직원에게 한 해 동안 새로 검토할 프로그램 묶음을 설명합니다.
규칙:
1. '사실'에 있는 내용과 숫자만 씁니다. 숫자는 그대로 옮기고 다시 계산하지 않습니다. 인력은 반드시 'N명×시간'으로 씁니다.
2. 이 묶음은 정해진 예산·인력 한도 안에서 고른 '검토 후보'이며 확정이 아니라는 점을 밝힙니다.
3. 달은 사실에 적힌 '겹치는 달'만 말합니다. '몇 월부터 몇 월까지' 같은 기간으로 바꾸지 않습니다.
4. 사실에 '주의' 줄이 있을 때만 주거복지사를 말합니다. 없으면 말하지 않습니다.
5. 숫자를 평가하지 않습니다('상대적으로', '비교적', '낮은 편' 같은 말을 붙이지 않습니다). 효과를 약속하지 않습니다.
6. 프로그램 이름은 사실에 적힌 그대로(가운뎃점·괄호까지) 쓰거나 아예 쓰지 않습니다. 이름을 쪼개거나 줄이지 않습니다. 이름을 다 늘어놓기보다 분야와 개수로 말하는 편이 좋습니다.
7. 존댓말 4문장 이내, 한 문단, 문장만 출력합니다.

예시
사실:
- 단지: 가나1
- 묶음: 3개
- 공단 쪽 연간 비용 합계: 약 30만 원(한도 50만 원)
- 연간 인력 합계: 약 40명×시간(한도 60명×시간)
- 프로그램: 건강 강좌 / 분야 건강과 돌봄 / 많이 열린 달 5·6·9월 / 난이도 5단계 중 1
- 프로그램: 명절 나눔 / 분야 안부와 관계 / 많이 열린 달 9·1·2월 / 난이도 5단계 중 2
- 프로그램: 텃밭 가꾸기 / 분야 문화와 활동 / 많이 열린 달 4·5·6월 / 난이도 5단계 중 3
- 겹치는 달: 없음
출력:
가나1 단지의 검토 후보 묶음은 건강 강좌, 명절 나눔, 텃밭 가꾸기 3개이며 확정된 계획이 아니라 검토를 위한 후보입니다. 공단 쪽 연간 비용은 약 30만 원으로 한도 50만 원 안에 있고, 인력은 약 40명×시간으로 한도 60명×시간 안에 있습니다. 건강과 돌봄, 안부와 관계, 문화와 활동 분야가 하나씩 들어 있으며 기록상 일정이 겹치는 달은 없습니다."""


def _nums(text):
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*", text)}


class LLMService:
    def __init__(self, eng, cache_path):
        self.e = eng
        self.path = Path(cache_path)
        self.lock = threading.Lock()
        self.cache = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self._ok, self._ok_at = None, 0
        self._dirty = False
        threading.Thread(target=self._flush_loop, daemon=True).start()

    # ───────── 공통 ─────────
    def status(self):
        if time.time() - self._ok_at > 20:
            err = L.ping()
            self._ok, self._ok_at = dict(available=err is None, error=err, model=L.MODEL, via="sdk" if L.ollama else "http"), time.time()
        return dict(self._ok, cached=len(self.cache))

    def _put(self, key, val):
        with self.lock:
            self.cache[key] = val
            self._dirty = True

    def _flush(self):
        """캐시를 한 줄에 한 건씩 쓴다(임시 파일에 쓰고 바꿔치기해서 쓰다 끊겨도 깨지지 않는다)."""
        with self.lock:
            if not self._dirty:
                return
            body = "{\n" + ",\n".join(json.dumps(k) + ": " + json.dumps(v, ensure_ascii=False) for k, v in sorted(self.cache.items())) + "\n}\n"
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(body, encoding="utf-8", newline="\n")
            os.replace(tmp, self.path)
            self._dirty = False

    def _flush_loop(self):
        while True:                                                    # 미리 만들기 배치처럼 몰려 들어올 때 매번 쓰지 않도록 2초마다 모아 쓴다
            time.sleep(2)
            try:
                self._flush()
            except OSError:
                pass

    @staticmethod
    def _key(kind, text):
        return kind + ":" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]

    def _chat(self, system, user, as_json=False, **opt):
        body = dict(model=L.MODEL, messages=[dict(role="system", content=system), dict(role="user", content=user)], stream=False, keep_alive="30m",
                    options={**L.OPTIONS, **opt})
        if as_json:
            body["format"] = "json"
        return L._http(L.HOST, "/api/chat", body, timeout=90)["message"]["content"]

    # ───────── 근거 문장 ─────────
    def explain(self, cid, sid, st=None, force=False):
        rec = run(lambda: self.e.rec_dict(cid, sid, st))
        draft = X.template(rec)
        off = self.e.llm_cache.get(f"{cid}|{sid}")
        if not force and off and off["source"] == "llm" and off.get("draft") == draft:   # 배치로 미리 만든 문장(사실이 같을 때만)
            return dict(text=off["text"], source="llm", origin="batch", draft=draft)
        key = self._key("explain", X.facts_text(rec) + draft)
        if key in self.cache and not force:
            return dict(self.cache[key], origin="cache", draft=draft)
        if not self.status()["available"]:
            return dict(text=draft, source="template", origin="llm_unavailable", draft=draft)
        t0 = time.time()
        try:
            res = X.explain(rec, llm_fn=L.ollama_fn(system=X.SYSTEM), retries=1)
        except Exception as e:
            return dict(text=draft, source="template", origin=f"error:{type(e).__name__}", draft=draft)
        out = dict(text=res["text"], source=res["source"], attempts=res["attempts"], sec=round(time.time() - t0, 1),
                   why=None if res["source"] == "llm" else res["check"])
        self._put(key, out)
        return dict(out, origin="live", draft=draft)

    # ───────── 실행 점검표 ─────────
    def checklist_facts(self, rec):
        e, ck = self.e, rec["check"]
        cid, sid = rec["complex_id"], rec["std_id"]
        c = e.c.loc[cid]
        rows = [f"프로그램: {rec['name']} (분야: {C.NEED.get(rec['domain'], '여러 분야')})", f"내용: {str(e.p.at[sid, 'definition']).split(': ', 1)[-1][:150]}",
                f"단지: {c['name']}, {int(c['hh']):,}세대, 주거복지사 {'배치' if c['deployed'] else '미배치'}"]
        if ck.get("basis") == "expert":
            rows.append(f"꼭 필요한 공간: {', '.join(ck['essential_places']) or '정해진 것 없음'}")
            if ck["self_run"]:
                rows.append("협력기관: 없이 자체 운영 가능")
            for p in ck["essential_partners"]:
                rows.append(f"꼭 필요한 협력기관: {p['type']} — 이 단지 여건: {p['status']}")
            cs = ck["cost_session"] // 10000
            rows.append(f"1회 비용: 약 {cs:,}만 원, 부담 주체: {'·'.join(ck['payers'])}" if cs else f"1회 비용: 거의 없음, 부담 주체: {'·'.join(ck['payers'])}")
            rows.append(f"1회 인력: 약 {ck['staff_hours_session']:g}명×시간, 실행 난이도: 5단계 중 {ck['difficulty']}(숫자가 클수록 어려움)")
        else:
            for p in ck["partners"][:3]:
                rows.append(f"자주 함께 한 기관: {p['type']} — 이 단지 여건: {p['status']}")
            rows.append(f"장소: {', '.join(ck['place'])}")
        if ck["resources"]:
            rows.append(f"필요 자원: {', '.join(ck['resources'])}")
        rows.append(f"기록상 많이 열린 달: {ck['peak_months'].replace('|', '·')}월")
        rows.append(f"다른 단지의 참여 규모(중앙값): {ck['participants_med']}명")
        for x in rec["evidence"]["peer_records"][:3]:
            rows.append(f"비슷한 단지 사례: {x['complex']}({x['month']}) '{x['title']}'" + (f" — 함께 한 곳: {', '.join(x['partners'][:2])}" if x["partners"] else ""))
        for x in rec["evidence"]["casebook"][:1]:
            rows.append(f"사례집({x['relation']}): {x['headline'][:90]}")
            if x.get("obstacles"):
                rows.append(f"사례집의 걸림돌과 해결: {x['obstacles'][:200]}")
        for o in ck["obstacles"][:3]:
            rows.append(f"예상 걸림돌 유형: {o['obstacle']} — 사례집에서 쓴 해결 방식: {o['strategy']}({o['n']}건)")
        if ck.get("welfare_gap"):
            rows.append("주의: 주거복지사가 있어야 하는 프로그램으로 검토되었는데 이 단지는 미배치")
        return "\n".join("- " + r for r in rows)

    @staticmethod
    def check_checklist(obj, facts):
        """형식과 근거 검사. 통과하면 (정리된 점검표, None), 아니면 (None, 이유)."""
        if not isinstance(obj, dict):
            return None, "JSON 객체가 아님"
        out, allowed = [], _nums(facts) | {"1", "2", "3", "4", "5"}
        for s in SECTIONS:
            items = obj.get(s)
            if not isinstance(items, list):
                return None, f"'{s}' 묶음이 없음"
            items = [re.sub(r"\s+", " ", str(x)).strip(" -·•") for x in items if str(x).strip()]
            if not (1 <= len(items) <= 5):
                return None, f"'{s}' 항목 수 {len(items)}"
            for it in items:
                if len(it) > 150 or len(it) < 6:
                    return None, f"항목 길이 {len(it)}"
                bad = [b for b in X.BANNED if b in it]
                if bad:
                    return None, f"단정 표현 {bad}"
                if re.search("[一-鿿぀-ヿ]", it):
                    return None, "한자·가나"
                extra = _nums(it) - allowed
                if extra:
                    return None, f"사실에 없는 숫자 {sorted(extra)}"
                loose = [w for w in LOOSE if w in it]
                if loose or MONTH_RANGE.search(it):
                    return None, f"사실에 없는 해석·기간 표현 {loose or ['월 범위']}"
                if "주거복지사" in it and "주거복지사 미배치" in facts and s != "주의" and "미배치" not in it and "없" not in it:
                    return None, "미배치 단지인데 주거복지사가 하는 일로 씀"
            out.append(dict(section=s, items=items))
        return out, None

    def checklist(self, cid, sid, st=None, force=False):
        rec = run(lambda: self.e.rec_dict(cid, sid, st))
        rule, facts = run(lambda: (self.e.rule_checklist(rec), self.checklist_facts(rec)))
        key = self._key("check", facts)
        if key in self.cache and not force:
            return dict(self.cache[key], origin="cache", rule=rule)
        if not self.status()["available"]:
            return dict(sections=rule, source="rule", origin="llm_unavailable", rule=rule)
        t0, why, tries = time.time(), None, []
        prompt = f"사실:\n{facts}\n\n이 단지에서 이 프로그램을 처음 실행하기 위한 점검표를 JSON으로 출력하십시오."
        for i in range(2):
            try:
                raw = self._chat(CHECK_SYSTEM, prompt if i == 0 else prompt + f"\n(앞서 쓴 점검표는 검사에서 떨어졌습니다: {why}. 규칙을 지켜 다시 쓰십시오.)",
                                 as_json=True, temperature=0.2, num_predict=700, num_ctx=4096)
                obj = json.loads(raw)
            except json.JSONDecodeError:
                why = "출력 오류(JSON이 아님)"
                tries.append(why)
                continue
            except Exception as e:                                     # 서버 오류·시간 초과는 저장하지 않는다 → 다음에 다시 만든다
                return dict(sections=rule, source="rule", origin=f"error:{type(e).__name__}", rule=rule)
            secs, why = self.check_checklist(obj, facts)
            tries.append(why or "통과")
            if secs:
                out = dict(sections=secs, source="llm", attempts=i + 1, sec=round(time.time() - t0, 1), tries=tries)
                self._put(key, out)
                return dict(out, origin="live", rule=rule)
        out = dict(sections=rule, source="rule_fallback", attempts=2, sec=round(time.time() - t0, 1), tries=tries)
        self._put(key, out)
        return dict(out, origin="live", rule=rule)

    # ───────── 연간 묶음 메모 ─────────
    @staticmethod
    def plan_template(plan, name):
        if not plan["items"]:
            return f"{name}: 지금 조건으로는 고를 수 있는 프로그램이 없습니다. 예산이나 인력 한도를 늘려 보십시오."
        s = [f"{name}의 검토 후보 묶음은 {plan['n']}개입니다: {', '.join(i['name'] for i in plan['items'])}.",
             f"공단 쪽 연간 비용은 약 {round(plan['cost'] / 10000):,}만 원(한도 {round(plan['budget'] / 10000):,}만 원), 인력은 약 {round(plan['hours']):,}명×시간(한도 {round(plan['hours_limit']):,}명×시간)으로 추정됩니다."]
        busy = [f"{m}월({len(v)}개)" for m, v in plan["calendar"].items() if len(v) >= 2]
        if busy:
            s.append(f"기록상 많이 열린 달로 보면 {', '.join(busy)}에 일정이 겹칠 수 있습니다.")
        gap = [i["name"] for i in plan["items"] if i["welfare_gap"]]
        if gap:
            s.append(f"{', '.join(gap)}은(는) 주거복지사가 있어야 하는 프로그램으로 검토되었는데 이 단지는 미배치입니다.")
        if plan["relaxed"]:
            s.append("필요 분야별 최소 개수 조건은 한도 안에서 맞출 수 없어 뺐습니다.")
        return " ".join(s)

    def plan_brief(self, plan, cid, force=False):
        name = run(lambda: str(self.e.c.at[cid, "name"]))
        draft = self.plan_template(plan, name)
        if not plan["items"]:
            return dict(text=draft, source="template", draft=draft)
        rows = [f"단지: {name}", f"묶음: {plan['n']}개", f"공단 쪽 연간 비용 합계: 약 {round(plan['cost'] / 10000):,}만 원(한도 {round(plan['budget'] / 10000):,}만 원)",
                f"연간 인력 합계: 약 {round(plan['hours']):,}명×시간(한도 {round(plan['hours_limit']):,}명×시간)"]
        for i in plan["items"]:
            rows.append(f"프로그램: {i['name']} / 분야 {i['domain_label']} / 많이 열린 달 {'·'.join(i['months'])}월 / 난이도 5단계 중 {i['difficulty']}" + (" / 주의: 주거복지사 필요인데 미배치" if i["welfare_gap"] else ""))
        if plan["relaxed"]:
            rows.append("분야별 최소 개수 조건은 한도 안에서 맞출 수 없어 뺌")
        busy = [f"{m}월({len(v)}개)" for m, v in plan["calendar"].items() if len(v) >= 2]
        rows.append("겹치는 달(가장 많이 열린 달 기준): " + (", ".join(busy) if busy else "없음"))
        facts = "\n".join("- " + r for r in rows)
        key = self._key("plan", facts)
        if key in self.cache and not force:
            return dict(self.cache[key], origin="cache", draft=draft)
        if not self.status()["available"]:
            return dict(text=draft, source="template", origin="llm_unavailable", draft=draft)
        res, why = None, None
        for i in range(2):                                             # 검사에서 떨어지면 이유를 붙여 한 번 더
            try:
                out = X.clean(self._chat(PLAN_SYSTEM, f"사실:\n{facts}\n" + (f"(앞서 쓴 설명은 검사에서 떨어졌습니다: {why}. 규칙을 지켜 다시 쓰십시오.)\n" if why else "") + "출력:",
                                         temperature=0.15, num_predict=340, num_ctx=4096))
            except Exception as e:
                return dict(text=draft, source="template", origin=f"error:{type(e).__name__}", draft=draft)
            extra = _nums(out) - _nums(facts)
            bad = [b for b in X.BANNED if b in out] + [w for w in LOOSE if w in out]
            if MONTH_RANGE.search(out):
                bad.append("월 범위")
            if "주거복지사" in out and "미배치" not in facts:
                bad.append("사실에 없는 주거복지사 언급")
            hrs = f"{round(plan['hours']):,}"
            if hrs in out and not re.search(re.escape(hrs) + r"\s*명\s*×\s*시간", out):
                bad.append("인력 단위(명×시간으로 써야 함)")
            for it in plan["items"]:                                  # 프로그램 이름을 쪼개거나 바꿔 쓰면 다른 프로그램처럼 읽힌다
                head = re.split(r"[·(]", it["name"])[0].strip()
                if len(head) >= 2 and head in out and it["name"] not in out:
                    bad.append(f"프로그램 이름을 바꿔 씀({it['name']})")
                    break
            n_sent = len(re.findall(r"[.!?](?:\s|$)", out))
            if n_sent > 5:
                bad.append("문장 수")
            if "후보" not in out:
                bad.append("'후보'라는 말이 없음")
            ok = not extra and not bad and 30 <= len(out) <= 600
            why = "; ".join(filter(None, ["사실에 없는 숫자 " + ", ".join(sorted(extra)) if extra else "", "쓰면 안 되는 표현 " + ", ".join(bad) if bad else ""]))
            res = dict(text=out if ok else draft, source="llm" if ok else "template_fallback", attempts=i + 1, why=None if ok else why)
            if ok:
                break
        self._put(key, res)
        return dict(res, origin="live", draft=draft)
