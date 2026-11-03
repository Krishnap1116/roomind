"""Room brief + joiner catch-up. One model call each, both logged."""
import json

import roomind as S
from . import meta, store


def _tagged(con, hist: list, rid: str) -> list:
    tags = store.display_tags(con, rid)
    for m in hist:
        t = tags.get(m.get("author_id") or "")
        if t:
            m["author"] = f"{m['author']} ·{t}"
    return hist


def build_brief(con, rid: str, model: str) -> dict:
    hist = _tagged(con, store.recent(con, rid, 50), rid)
    mems = [dict(r) for r in con.execute(
        "SELECT key, value FROM memory WHERE room=?", (rid,))]
    led = [dict(r) for r in con.execute(
        "SELECT what, who, why, status FROM ledger WHERE room=?", (rid,))]
    prompt = ("Summarize this room. Reply ONLY JSON "
              '{"decisions": [{"what": "...", "who": "...", "why": "..."}], '
              '"open": ["..."], "owners": {"name": ["task"]}}. '
              f"Saved notes: {json.dumps(mems)[:1500]} "
              f"Ledger: {json.dumps(led)[:1500]}")
    out = meta.spark_reply(S.MODEL_API_KEY, S.MODEL_API_BASE, model, hist,
                           prompt)
    store.log_cost(con, rid, "brief", model, out["tin"], out["tout"])
    try:
        return json.loads(out["answer"])
    except ValueError:
        return {"summary": out["answer"], "decisions": [], "open": [],
                "owners": {}}


def catchup(con, rid: str, name: str, since_id: int, model: str) -> dict:
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM messages WHERE room=? AND id>? ORDER BY id LIMIT 50",
        (rid, since_id))]
    if not rows:
        return {"summary": "Nothing new.", "decisions": [], "for_you": []}
    rows = _tagged(con, rows, rid)
    prompt = (f"Brief {name} on what they missed. Reply ONLY JSON "
              '{"summary": "...", "decisions": [...], "for_you": [...] }.')
    out = meta.spark_reply(S.MODEL_API_KEY, S.MODEL_API_BASE, model, rows,
                           prompt)
    store.log_cost(con, rid, "catchup", model, out["tin"], out["tout"])
    try:
        return json.loads(out["answer"])
    except ValueError:
        return {"summary": out["answer"], "decisions": [], "for_you": []}
