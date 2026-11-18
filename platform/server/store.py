"""사용자 입력 저장소: 단지별 '확인된 필요', 제외한 프로그램, 메모. data/user_state.json 한 파일(잠금 + 원자적 쓰기).

제외 종류
- infeasible: 운영 불가능(다시 추천하지 않는다)
- already   : 이미 운영 중인데 기록이 없다(기록 누락으로 보고 후보에서 뺀다)
- not_now   : 지금은 아님(보류). 후보가 모자랄 때만, 뺀 횟수가 2번 이하인 것까지 다시 보여 줄 수 있다. 3번째로 빼면 더는 나오지 않는다.
"""
import json
import os
import threading
import time
from pathlib import Path

KINDS = {"infeasible", "already", "not_now"}
LEVELS = {"high", "mid", "low"}


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.data = {"complexes": {}, "log": []}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.path.rename(self.path.with_suffix(".broken.json"))
        self.data.setdefault("complexes", {})
        self.data.setdefault("log", [])

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def _cx(self, cid):
        return self.data["complexes"].setdefault(cid, {"confirmed": {}, "excluded": {}, "memo": ""})

    def _log(self, **kw):
        self.data["log"].append(dict(ts=time.strftime("%Y-%m-%d %H:%M:%S"), **kw))
        self.data["log"] = self.data["log"][-500:]

    def get(self, cid):
        with self.lock:
            return json.loads(json.dumps(self.data["complexes"].get(cid, {"confirmed": {}, "excluded": {}, "memo": ""})))

    def confirm(self, cid, domain, level, note=""):
        """확인된 필요를 넣거나(level=high/mid/low) 지운다(level=None)."""
        with self.lock:
            c = self._cx(cid)
            if level in LEVELS:
                c["confirmed"][domain] = dict(level=level, note=str(note or "")[:300], ts=time.strftime("%Y-%m-%d"))
            else:
                c["confirmed"].pop(domain, None)
            self._log(action="confirm", complex_id=cid, domain=domain, level=level)
            self._save()

    def exclude(self, cid, sid, kind, note=""):
        if kind not in KINDS:
            raise ValueError("kind")
        with self.lock:
            c = self._cx(cid)
            old = c["excluded"].get(sid)
            count = (old.get("count", 1) + 1) if old and old.get("kind") == "not_now" and kind == "not_now" else 1
            c["excluded"][sid] = dict(kind=kind, count=count, note=str(note or "")[:300], ts=time.strftime("%Y-%m-%d"))
            self._log(action="exclude", complex_id=cid, std_id=sid, kind=kind, count=count)
            self._save()
            return count

    def restore(self, cid, sid):
        with self.lock:
            self._cx(cid)["excluded"].pop(sid, None)
            self._log(action="restore", complex_id=cid, std_id=sid)
            self._save()

    def memo(self, cid, text):
        with self.lock:
            self._cx(cid)["memo"] = str(text or "")[:2000]
            self._save()
