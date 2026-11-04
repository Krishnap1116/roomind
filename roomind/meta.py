"""Meta Model API client. Chat-completions shape, priced + logged per call."""
import json

import httpx

import roomind as S


def list_models(api_key: str, base: str, timeout: float = 15.0) -> list:
    """Model ids the key can see. Empty list on any failure."""
    if not api_key:
        return []
    try:
        r = httpx.get(f"{base}/models",
                      headers={"Authorization": f"Bearer {api_key}"},
                      timeout=timeout)
        r.raise_for_status()
        data = r.json().get("data", [])
        return [m.get("id", "") for m in data if m.get("id")]
    except Exception:
        return []

WINDOWS = {"muse-spark-1.3": 1_000_000,
           "muse-spark-1.2": 1_000_000,
           "muse-spark-1.1": 1_000_000}

SYSTEM = (
    "You answer inside a shared team room. Reply ONLY as JSON:"
    ' {"answer": "...", "reasons": ["...", "..."],'
    ' "remember": [{"key": "...", "value": "..."}]}.'
    " reasons: short, checkable, grounded in the room's own words."
    " remember: at most 2 lasting facts worth keeping (names, decisions,"
    " preferences). Empty list most of the time."
)


def spark_reply(api_key: str, base: str, model: str, history: list,
                prompt: str, timeout: float = 60.0,
                notes: list | None = None,
                effort: str | None = None,
                hist_n: int = 12,
                system: str | None = None) -> dict:
    """One reasoning call. Returns {answer, reasons, remember, tin, tout}."""
    msgs = [{"role": "system", "content": system or SYSTEM}]
    if notes:
        lines = "\n".join(f"- {n['key']}: {n['value']}" for n in notes[:5])
        msgs.append({"role": "system", "content": "Room notes:\n" + lines})
    msgs += [{"role": "user" if m["author"] != "agent" else "assistant",
              "content": f"{m['author']}: {m['body']}"}
             for m in history[-hist_n:]]
    msgs.append({"role": "user", "content": prompt})
    payload = {"model": model, "messages": msgs,
               "response_format": {"type": "json_object"}}
    eff = S.JUDGE_EFFORT if effort is None else effort
    if eff:
        payload["reasoning_effort"] = eff
    r = httpx.post(f"{base}/chat/completions",
                   headers={"Authorization": f"Bearer {api_key}"},
                   json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    txt = data["choices"][0]["message"]["content"]
    use = data.get("usage", {})
    def _mem(items):
        out = []
        for it in (items or [])[:2]:
            if isinstance(it, dict) and str(it.get("key", "")).strip() \
                    and str(it.get("value", "")).strip():
                out.append({"key": str(it["key"])[:80],
                            "value": str(it["value"])[:500]})
        return out

    try:
        parsed = json.loads(txt)
        return {"answer": parsed.get("answer", txt),
                "reasons": parsed.get("reasons", [])[:4],
                "remember": _mem(parsed.get("remember")),
                "tin": use.get("prompt_tokens", 0),
                "tout": use.get("completion_tokens", 0)}
    except (ValueError, KeyError):
        return {"answer": txt, "reasons": [], "remember": [],
                "tin": use.get("prompt_tokens", 0),
                "tout": use.get("completion_tokens", 0)}


def chat(api_key: str, base: str, model: str, messages: list,
         timeout: float = 60.0, effort: str = "") -> dict:
    """One raw text turn. Returns {text, tin, tout}."""
    payload = {"model": model, "messages": messages}
    if effort:
        payload["reasoning_effort"] = effort
    r = httpx.post(f"{base}/chat/completions",
                   headers={"Authorization": f"Bearer {api_key}"},
                   json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    use = data.get("usage", {})
    return {"text": data["choices"][0]["message"]["content"],
            "tin": use.get("prompt_tokens", 0),
            "tout": use.get("completion_tokens", 0)}


def chat_stream(api_key: str, base: str, model: str, messages: list,
                timeout: float = 120.0, effort: str = ""):
    """Yield ('tok', text) deltas, then ('usage', tin, tout).
    Falls back to one chunk when the API answers without SSE."""
    tin = tout = 0
    payload = {"model": model, "messages": messages, "stream": True,
               "stream_options": {"include_usage": True}}
    if effort:
        payload["reasoning_effort"] = effort
    with httpx.stream("POST", f"{base}/chat/completions",
                      headers={"Authorization": f"Bearer {api_key}"},
                      json=payload, timeout=timeout) as r:
        r.raise_for_status()
        if "text/event-stream" not in r.headers.get("content-type", ""):
            data = json.loads(r.read())
            txt = data["choices"][0]["message"]["content"]
            use = data.get("usage", {})
            yield ("tok", txt)
            yield ("usage", use.get("prompt_tokens", 0),
                   use.get("completion_tokens", 0))
            return
        for line in r.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except ValueError:
                continue
            for choice in chunk.get("choices", []):
                tok = (choice.get("delta") or {}).get("content")
                if tok:
                    yield ("tok", tok)
            use = chunk.get("usage")
            if use:
                tin, tout = use.get("prompt_tokens", 0), \
                    use.get("completion_tokens", 0)
    yield ("usage", tin, tout)
