"""Room brief + joiner catch-up. One model call each, both logged."""
import json

import roomind as S
from . import meta, store


SHAPE_SYS = ("You summarize shared team rooms. Reply with exactly"
             " the JSON shape the request specifies. No other keys.")


def _as_json(text: str):
    """Parse a model reply: direct JSON, else the first {...} span."""
    try:
        return json.loads(text)
    except ValueError:
        pass
    i, j = (text or "").find("{"), (text or "").rfind("}")
    if 0 <= i < j:
        try:
            return json.loads(text[i:j + 1])
        except ValueError:
            return None
    return None


def _tagged(con, hist: list, rid: str) -> list:
    tags = store.display_tags(con, rid)
    for m in hist:
        t = tags.get(m.get("author_id") or "")
        if t:
            m["author"] = f"{m['author']} ·{t}"
    return hist


_CACHE: dict = {}


def _fingerprint(con, rid: str, model: str, include_sides: bool,
                 me_id: str) -> tuple:
    max_mid = con.execute("SELECT COALESCE(MAX(id),0) FROM messages"
                          " WHERE room=?", (rid,)).fetchone()[0]
    mem = con.execute("SELECT COUNT(*), COALESCE(MAX(updated_at),0)"
                      " FROM memory WHERE room=?", (rid,)).fetchone()
    led = con.execute("SELECT COUNT(*) FROM ledger WHERE room=?",
                      (rid,)).fetchone()[0]
    sides = len(store.list_sides(con, rid)) if include_sides else 0
    return (rid, model, include_sides, me_id, max_mid, mem[0], mem[1],
            led, sides)


def build_brief(con, rid: str, model: str, include_sides: bool = False,
                me_id: str = "") -> dict:
    fp = _fingerprint(con, rid, model, include_sides, me_id)
    if fp in _CACHE:
        return _CACHE[fp]
    hist = _tagged(con, store.recent(con, rid, 50), rid)
    mems = [dict(r) for r in con.execute(
        "SELECT key, value FROM memory WHERE room=?", (rid,))]
    led = [dict(r) for r in con.execute(
        "SELECT what, who, why, status FROM ledger WHERE room=?", (rid,))]
    quotes = [{"room": "main", "text": r["what"]} for r in con.execute(
        "SELECT what FROM ledger WHERE room=? AND status='open'"
        " AND (why IS NULL OR why NOT LIKE 'side-report:%')", (rid,))]
    side_lines: list = []
    hidden = 0
    if include_sides and not store.room_parent(con, rid):
        for s in store.list_sides(con, rid):
            sid = s["room_id"]
            mission = s["mission"] or sid
            if me_id and store.member_by_origin(con, sid, me_id):
                for m in _tagged(con, store.recent(con, sid, 15), sid):
                    side_lines.append(f"[{mission}] {m.get('author')}:"
                                      f" {m.get('body')}")
                for r in con.execute(
                        "SELECT what FROM ledger WHERE room=? AND"
                        " status='open'", (sid,)):
                    quotes.append({"room": mission, "text": r["what"]})
            else:
                hidden += 1
        for r in con.execute(
                "SELECT what, why FROM ledger WHERE room=? AND"
                " status='open' AND why LIKE 'side-report:%'", (rid,)):
            marker = (r["why"] or "").split(":", 1)[1].split()[0]
            mission = store.room_mission(con, marker) or marker
            quotes.append({"room": mission, "text": r["what"]})
    prompt = ("Summarize this room in short. Reply with a single JSON"
              " object and nothing else. No sentences before or after it. "
              '{"decisions": [{"what": "...", "who": "...", "why": "..."}], '
              '"open": ["..."], "owners": {"name": ["task"]}}. '
              "At most 6 items per list, one line each. "
              f"Saved notes: {json.dumps(mems)[:1500]} "
              f"Ledger: {json.dumps(led)[:1500]}")
    if side_lines:
        prompt += f" Side rooms: {' | '.join(side_lines)[:3000]}"
    out = meta.spark_reply(S.MODEL_API_KEY, S.MODEL_API_BASE, model, hist,
                           prompt, effort=S.ASK_EFFORT,
                           system=SHAPE_SYS)
    store.log_cost(con, rid, "brief", model, out["tin"], out["tout"])
    brief = _as_json(out["answer"])
    if not isinstance(brief, dict):
        brief = {"summary": out["answer"], "decisions": [], "open": [],
                 "owners": {}}
    brief["decisions"] = (brief.get("decisions") or [])[:6]
    brief["open"] = (brief.get("open") or [])[:6]
    owners = brief.get("owners") or {}
    brief["owners"] = {k: (v or [])[:6] for k, v in owners.items()} \
        if isinstance(owners, dict) else {}
    if include_sides:
        brief["quotes"] = quotes[:8]
        brief["sides_hidden"] = hidden
    if len(_CACHE) > 500:
        _CACHE.clear()
    _CACHE[fp] = brief
    return brief


def catchup(con, rid: str, name: str, since_id: int, model: str) -> dict:
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM messages WHERE room=? AND id>? ORDER BY id LIMIT 50",
        (rid, since_id))]
    if not rows:
        return {"summary": "Nothing new.", "decisions": [], "for_you": []}
    rows = _tagged(con, rows, rid)
    prompt = (f"Brief {name} on what they missed, in 3 sentences or"
              " fewer. Reply with a single JSON object and nothing else."
              " No sentences before or after."
              ' {"summary": "...", "decisions": [...], "for_you": [...] }.'
              " At most 6 items per list.")
    out = meta.spark_reply(S.MODEL_API_KEY, S.MODEL_API_BASE, model, rows,
                           prompt, effort=S.ASK_EFFORT,
                           system=SHAPE_SYS)
    store.log_cost(con, rid, "catchup", model, out["tin"], out["tout"])
    parsed = _as_json(out["answer"])
    if isinstance(parsed, dict):
        parsed["decisions"] = (parsed.get("decisions") or [])[:6]
        parsed["for_you"] = (parsed.get("for_you") or [])[:6]
        return parsed
    return {"summary": out["answer"], "decisions": [], "for_you": []}
