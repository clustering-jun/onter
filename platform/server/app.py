"""온터 웹 플랫폼 서버. 표준 라이브러리 HTTP 서버 + project/model 엔진.

    python server/app.py --port 8770      →  http://127.0.0.1:8770

- /api/*      플랫폼 API(JSON)
- /kg/*       지식 그래프 탐색 시제품(project/knowledge_graph)을 그대로 붙인다. 원본 파일은 고치지 않는다.
- 그 밖       web/ 정적 파일
"""
import argparse
import colorsys
import re
import importlib.util
import json
import mimetypes
import socket
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import engine as G
from catalog import Catalog
from llm_service import LLMService
from store import Store

WEB = ROOT / "web"
KG_DIR = G.PROJECT / "knowledge_graph"
ENG = CAT = LLM = STORE = KG = None


def boot():
    global ENG, CAT, LLM, STORE, KG
    ENG = G.Engine()
    CAT = Catalog(ENG)
    (ROOT / "data").mkdir(exist_ok=True)
    STORE = Store(ROOT / "data" / "user_state.json")
    LLM = LLMService(ENG, ROOT / "data" / "llm_cache.json")
    if (KG_DIR / "server.py").exists() and (KG_DIR / "data" / "knowledge.sqlite").exists():
        spec = importlib.util.spec_from_file_location("onter_kg_server", KG_DIR / "server.py")
        KG = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(KG)


def meta():
    return dict(needs=G.C.NEED, need_ids=G.C.NEED_IDS, types=G.TYPE_LABEL, type_info=ENG.type_info, status=G.Engine.STATUS_KO,
                defaults=dict(w=G.R.DEFAULT["w_need"], lam=G.R.DEFAULT["lam"], budget=1e6, hours=G.M4.LOAD_HOURS, n_max=6, k=10),
                expert=ENG.expert, months=ENG.months, photos=sorted(x.stem for x in (WEB / 'img' / 'complex').glob('*.jpg') if x.stem != 'default'), kg=KG is not None, load_sec=ENG.load_sec, max_resurface=G.MAX_RESURFACE, uncertain_width=G.UNCERTAIN_WIDTH,
                counts=dict(complexes=len(ENG.ids), with_records=int(ENG.has_rec.sum()), programs=len(ENG.items), records=int(len(ENG.records))))


def num(q, k, default=None):
    v = q.get(k)
    return default if v in (None, "") else float(v)


def api_get(route, q):
    cid, sid = q.get("id"), q.get("sid")
    if cid and cid not in ENG.ix:
        raise KeyError(f"단지 {cid}")
    if sid and sid not in ENG.jx:
        raise KeyError(f"프로그램 {sid}")
    st = STORE.get(cid) if cid else None
    if route == "health":
        return dict(ok=True, service="onter-platform", load_sec=ENG.load_sec)
    if route == "meta":
        return meta()
    if route == "complexes":
        return ENG.complex_list()
    if route == "complex":
        return ENG.complex_detail(cid, st)
    if route == "matrix":
        return ENG.program_matrix(cid, st)
    if route == "recommend":
        return ENG.recommend(cid, num(q, "w"), num(q, "lam"), int(num(q, "k", 10)), q.get("domain") or None, st)
    if route == "candidate":
        return ENG.candidate(cid, sid, st)
    if route == "programs":
        return CAT.programs()
    if route == "program":
        return CAT.program(sid)
    if route == "search":
        return CAT.search(q.get("q", ""))
    if route == "cases":
        return CAT.cases()
    if route == "happycall":
        return CAT.happycall()
    if route == "analytics":
        return CAT.analytics()
    if route == "welfare":
        return CAT.welfare()
    if route == "state":
        return dict(STORE.get(cid), excluded_view=ENG._excluded_view(st))
    if route == "llm/status":
        return LLM.status()
    raise LookupError(route)


def api_post(route, b):
    cid, sid = b.get("id"), b.get("sid")
    if cid not in ENG.ix:
        raise KeyError(f"단지 {cid}")
    if sid and sid not in ENG.jx:
        raise KeyError(f"프로그램 {sid}")
    if route == "plan":
        st = STORE.get(cid)
        return ENG.plan(cid, b.get("w"), b.get("lam"), b.get("budget", 1e6), b.get("hours"), b.get("n_max", 6), b.get("min_domains"), st)
    if route == "state/confirm":
        if b.get("domain") not in G.C.NEED_IDS:
            raise ValueError("domain")
        STORE.confirm(cid, b["domain"], b.get("level"), b.get("note", ""))
        return dict(ok=True, state=STORE.get(cid))
    if route == "state/exclude":
        n = STORE.exclude(cid, sid, b.get("kind"), b.get("note", ""))
        return dict(ok=True, count=n, will_resurface=b.get("kind") == "not_now" and n <= G.MAX_RESURFACE)
    if route == "state/restore":
        STORE.restore(cid, sid)
        return dict(ok=True)
    if route == "state/memo":
        STORE.memo(cid, b.get("memo", ""))
        return dict(ok=True)
    st = STORE.get(cid)
    if route == "llm/explain":
        return LLM.explain(cid, sid, st, bool(b.get("force")))
    if route == "llm/checklist":
        return LLM.checklist(cid, sid, st, bool(b.get("force")))
    if route == "llm/plan":
        plan = G.run(lambda: ENG.plan(cid, b.get("w"), b.get("lam"), b.get("budget", 1e6), b.get("hours"), b.get("n_max", 6), b.get("min_domains"), st))
        return dict(LLM.plan_brief(plan, cid, bool(b.get("force"))), plan=plan)
    raise LookupError(route)


# Knowledge Graph 시제품은 초록·베이지 계열이다. 원본을 고치지 않고, 내보낼 때 초록 기운이 도는 색만 플랫폼의 청록·회색 계열로 바꾼다.
KG_HEX = re.compile(r"#([0-9a-fA-F]{6})\b")
KG_NODE = re.compile(r"#(367d64|5c9271|a6b9ae|93a975|9aa67f|92aca6)\b")
KG_HEAD = ('<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">'
           '<link rel="stylesheet" href="/css/kg_embed.css">')


KG_TITLE = re.compile(r"^(.*?)\s*'([^']+)'\s*:\s*(.*)$")


def _kg_short(o):
    """사례·사례 카드의 긴 제목(지역 '이름': 설명…)을 '이름 (지역) — 설명 앞부분'으로 줄인다. 원래 제목은 attrs.full_title에 남긴다."""
    if isinstance(o, list):
        return [_kg_short(x) for x in o]
    if isinstance(o, dict):
        if o.get("kind") in ("card", "case") and isinstance(o.get("label"), str):
            m = KG_TITLE.match(o["label"])
            if m:
                region, name, desc = m.groups()
                o = dict(o, label=f"{name} ({region})" + (f" — {desc[:26]}…" if len(desc) > 28 else f" — {desc}" if desc else ""))
                if isinstance(o.get("attrs"), dict):
                    o["attrs"] = dict(o["attrs"], full_title=m.group(0))
        return {k: _kg_short(v) for k, v in o.items()}
    return o


KG_FONT = re.compile(r"font-size:(\d+(?:\.\d+)?)px")


def _kg_bigger(m):
    """Knowledge Graph 화면의 작은 글씨를 키운다(10~12px가 많아 읽기 어려웠다)."""
    v = float(m.group(1))
    return "font-size:%gpx" % (v if v >= 18 else max(14, v + 3) if v < 14 else v + 2)


def _kg_recolor(m):
    r, g, b = (int(m.group(1)[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, sat = colorsys.rgb_to_hls(r, g, b)
    if not (0.17 <= h <= 0.50) or sat < 0.04:                    # 초록 기운(노랑초록~청록)이 아니면 그대로
        return m.group(0)
    if sat < 0.30 or l > 0.80:                                   # 옅은 바탕·테두리 → 차가운 회색
        h2, s2 = 0.60, min(sat, 0.16) * 0.7
    else:                                                        # 진한 초록 → 플랫폼 강조색(청록)
        h2, s2 = 0.543, min(0.65, sat * 1.15)
    r2, g2, b2 = colorsys.hls_to_rgb(h2, l, s2)
    return "#%02x%02x%02x" % (round(r2 * 255), round(g2 * 255), round(b2 * 255))


class Handler(BaseHTTPRequestHandler):
    server_version = "OnterPlatform/1.0"
    protocol_version = "HTTP/1.1"                                     # 연결을 유지해 손잡이를 움직일 때마다 새로 연결하지 않는다

    def log_message(self, *a):
        pass

    def send_json(self, value, status=200):
        if getattr(self, "_kg", False):
            value = _kg_short(value)
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def send_file(self, target, patch=None):
        raw = target.read_bytes()
        if patch:
            raw = patch(raw.decode("utf-8")).encode("utf-8")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if target.suffix in (".html", ".css", ".js", ".json", ".svg") else ""))
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def _guard(self, fn, on_engine=True):
        t0 = time.perf_counter()
        try:
            out = G.run(fn) if on_engine else fn()                    # 계산은 엔진 일꾼 스레드에서, LLM 호출은 요청 스레드에서
            if isinstance(out, dict):
                out.setdefault("_server_ms", round((time.perf_counter() - t0) * 1000, 2))
            self.send_json(out)
        except (KeyError, LookupError) as e:
            self.send_json(dict(error=f"찾을 수 없습니다: {e}"), 404)
        except (ValueError, TypeError) as e:
            self.send_json(dict(error=f"요청 값이 잘못되었습니다: {e}"), 400)
        except Exception as e:                                        # 서버가 죽지 않게 하고 원인을 돌려준다
            traceback.print_exc()
            self.send_json(dict(error=f"{type(e).__name__}: {e}"), 500)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        route = urllib.parse.unquote(u.path)
        q = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        if route.startswith("/api/"):
            return self._guard(lambda: api_get(route[5:], q))
        if route.startswith("/kg"):
            return self.kg(route, u)
        rel = route.lstrip("/") or "index.html"
        target = (WEB / rel).resolve()
        if not target.is_relative_to(WEB.resolve()) or not target.is_file():
            return self.send_error(404)
        self.send_file(target)

    def do_POST(self):
        route = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if not route.startswith("/api/"):
            return self.send_error(404)
        if "application/json" not in (self.headers.get("Content-Type") or ""):     # 다른 사이트의 양식 전송(text/plain)으로 메모·제외를 바꾸지 못하게 한다. fetch의 JSON 요청은 사전 확인을 거친다
            return self.send_json(dict(error="Content-Type은 application/json이어야 합니다"), 415)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
            if not isinstance(body, dict):
                raise ValueError("본문은 JSON 객체여야 합니다")
        except (ValueError, UnicodeDecodeError) as e:
            return self.send_json(dict(error=f"요청 본문을 읽을 수 없습니다: {e}"), 400)
        self._guard(lambda: api_post(route[5:], body), on_engine=not route.startswith("/api/llm/"))

    # 지식 그래프 시제품: API는 그쪽 핸들러에 맡기고, 화면 파일은 API 주소만 /kg/api로 바꿔 내보낸다
    def kg(self, route, u):
        if KG is None:
            return self.send_json(dict(error="지식 그래프 자료가 없습니다(project/knowledge_graph에서 build_graph.py 실행)."), 404)
        if route.startswith("/kg/api/"):
            self.path = route[3:] + ("?" + u.query if u.query else "")
            self._kg = True
            try:
                return KG.Handler.do_GET(self)
            finally:
                self._kg = False
        rel = route[4:].lstrip("/") or "index.html"
        target = (KG.WEB / rel).resolve()
        if not target.is_relative_to(KG.WEB.resolve()) or not target.is_file():
            return self.send_error(404)
        patch = {".js": lambda s: KG_NODE.sub(_kg_recolor, s.replace("fetch('/api/'", "fetch('/kg/api/'")), ".css": lambda s: KG_FONT.sub(_kg_bigger, KG_HEX.sub(_kg_recolor, s)),
                 ".html": lambda s: s.replace("</head>", KG_HEAD + "</head>")}.get(target.suffix)
        self.send_file(target, patch)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    print("엔진을 올리는 중…", flush=True)
    boot()
    print(f"온터 플랫폼: http://{a.host}:{a.port}  (엔진 적재 {ENG.load_sec}초, 지식 그래프 {'연결' if KG else '없음'})", flush=True)
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer.request_queue_size = 128                      # 한꺼번에 몰리는 연결을 끊지 않게 대기열을 늘린다
    if a.host == "127.0.0.1":                                         # 브라우저가 localhost를 ::1로 먼저 찾을 때 0.3초쯤 늦어지지 않게 IPv6 루프백에서도 받는다
        try:
            class V6(ThreadingHTTPServer):
                address_family = socket.AF_INET6
            threading.Thread(target=V6(("::1", a.port), Handler).serve_forever, daemon=True).start()
        except OSError:
            pass
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
