"""로컬 LLM(Ollama) 연결. explain.explain(rec, llm_fn=...)에 넣을 llm_fn을 만든다.

서버는 serve_ollama.ps1로 띄운다(병렬 슬롯 수는 서버 환경변수 OLLAMA_NUM_PARALLEL로 정해진다).
숫자를 지어내지 않게 temperature를 낮게 두고, 빨리 끝나게 출력 길이와 문맥 길이를 줄였다.
"""
import json
import urllib.request
from . import config as C

try:                                  # SDK가 있으면 쓰고, 없거나 깨져 있으면(의존 패키지 버전 충돌 등) HTTP로 직접 부른다
    import ollama
except Exception:
    ollama = None

MODEL = "exaone3.5:7.8b"
HOST = "http://localhost:11434"
OPTIONS = dict(temperature=0.15, top_p=0.9, repeat_penalty=1.05, num_predict=220, num_ctx=2048, seed=C.SEED)


def _http(host, path, body=None, timeout=120):
    req = urllib.request.Request(host + path, data=None if body is None else json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ollama_fn(model=MODEL, host=HOST, system=None, keep_alive="30m", timeout=120, **options):
    """llm_fn(prompt)->str. 스레드 여러 개가 같이 써도 된다."""
    client = ollama.Client(host=host, timeout=timeout) if ollama else None
    opt = {**OPTIONS, **options}

    def fn(prompt):
        msgs = ([dict(role="system", content=system)] if system else []) + [dict(role="user", content=prompt)]
        if client:
            r = client.chat(model=model, messages=msgs, options=opt, keep_alive=keep_alive, stream=False)
        else:
            r = _http(host, "/api/chat", dict(model=model, messages=msgs, options=opt, keep_alive=keep_alive, stream=False), timeout)
        fn.tokens += r.get("eval_count") or 0
        return r["message"]["content"]

    fn.tokens = 0
    fn.model, fn.options, fn.via = model, opt, "sdk" if client else "http"
    return fn


def ping(model=MODEL, host=HOST):
    """서버가 떠 있고 모델이 받아져 있는지 확인. 문제가 있으면 이유를 돌려준다."""
    try:
        names = [m.model for m in ollama.Client(host=host, timeout=5).list().models] if ollama else [m["name"] for m in _http(host, "/api/tags", timeout=5)["models"]]
    except Exception as e:
        return f"Ollama 서버에 연결할 수 없습니다({host}). serve_ollama.ps1을 먼저 실행하십시오. [{type(e).__name__}]"
    return None if model in names else f"모델 {model}이 없습니다. 받은 모델: {names}"
