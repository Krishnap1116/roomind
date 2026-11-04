"""Dissent engine: model judge with veto pre-filter. Team-lead bar.

Word lists only ever silence, never fire. Every surviving line is judged
by the model against mission, ledger, memory, and the thread.
watch() below is the retired keyword trigger; the golden scorer grades
it until step 5 rewires scoring to the judge."""
import json
import re
import time

import roomind as S
from . import memory, meta, remind, store

AGREE = ["yes", "yeah", "yep", "agreed", "agree", "+1", "ship it", "lets do",
         "let's do", "go for", "looks good", "lgtm", "do it", "approved",
         "approve", "perfect", "great", "sounds good"]
OBJECT = ["but ", "however", "risk", "what about", "why ", "?", "no ",
          "nope", "wait", "hold on", "concern", "disagree", "instead",
          "unless", "flaw"]

VETO = ["what if", "suppose", "supposing", "lol", "haha", "joke", "imagine",
        "jk"]

JUDGE_PROMPT = (
    "ROOM JUDGE. The latest line in context decides. Reply ONLY JSON "
    '{"fire": true/false, "confidence": "high"/"low", "hats": ["...", '
    "up to 3], \"source\": one of memory/ledger/mission/thread/model, "
    '"points": [{"flaw": "...", "receipt": "..."}], "question": "...", '
    '"conflict": {"key": "...", "memory_says": "...", "room_says": "..."} '
    "or null}. First name up to 3 hats the latest line touches, areas "
    "like code, deploy, contracts, data, and judge every claim as a "
    "senior in each hat. Then extract the latest line's checkable "
    "claims: facts, decisions, numbers, promises. Opinions, feelings, "
    "jokes, what-ifs are not claims: with none, fire=false. Then count "
    "the thread's checkable reasons for the latest decision: a review "
    "done, tests run, numbers checked, named evidence in the room's own "
    "lines, never your assumptions. Fire true when any rule below holds, "
    "quoting receipts from the room's own words: (1) the adopted claim "
    "breaks a Room fact standing rule or open ledger item: a broken rule "
    "is the strongest evidence, fill conflict with that fact's key, what "
    "memory claims, and what the room claims; (2) the speaker's latest "
    "line breaks their own earlier line in this thread: quote both; "
    "(3) the thread adopts a decision, a claim plus at least one agreeing "
    "nod like yes, +1, do it, or sounds good, with zero checkable reasons: "
    "verdict without thought fires, quote the claim and each nod; a bare "
    "imperative like ship it or migrate X tonight plus bare nods with no "
    "reason stated anywhere always fires; a timing assertion justifies when, "
    "never whether it is safe: without verification it is zero reasons; a "
    "bare intention, or mere acknowledgment like noted, ok, or "
    "seen is not a reason and not a nod; (4) the adopted claim fights the "
    "stated mission: cutting against a stated constraint, freeze, or safety "
    "rule counts as fighting it; (5) the thread ignores the mission for "
    "five-plus lines: fire with a drift point. "
    "Facts marked old whisper: never fire on an old fact "
    "alone. Fast agreement with reasons is silence. Exploration is "
    "silence. A real objection anywhere in the thread overrides rules 1 "
    "to 4: the room checks itself, silence. confidence=high when your "
    "receipts quote the room's own words for every point, else low. "
    "If source is your own knowledge, phrase the question "
    "humbly. Max 2 points. Receipts must quote the room's own words. "
    "Also listen for team decisions: if the latest lines adopt one, even loosely worded, fill "
    '"decision": {"what": "...", "who": "...", "why": "...", '
    '"deadline": "...", "updates": "L{id}"/"P{id}" or null, "needs_detail": true/false}; else "decision": null. A decision can ride silence. Resolve this/that/it to the concrete topic from the thread. Stamped lines show as L1, L2; open cards as P1, P2. If this decision changes one, set updates to its ref. If the topic stays unclear, set needs_detail true. Leave who, why, or deadline empty when unknown; humans complete them in review.'
    ' Need-plus-agreement proposes: a line stating a need, plan, or deadline ("need to", "must", "by tonight", "finish X") followed by agreement ("sure", "yes", "u are right", "lets do it") is an adopted decision even with zero detail. Resolve this/that/it against the whole thread INCLUDING the agent ask/answer lines above the chat. Fill decision only when the what names something stated in the thread, mission, or proposed whats, marking needs_detail true when thin; never invent a topic: if "this" has no referent anywhere, return null, since no decision beats a guessed one.')

SOURCES = ("memory", "ledger", "mission", "thread", "model")

REPAIR = " Return ONLY the JSON object, no other words."


def vetoed(body: str) -> bool:
    low = " " + (body or "").lower()
    return any(v in low for v in VETO)


SEVERE = ["ship", "deploy", "delete", "pay", "publish", "launch",
          "merge", "release"]


def severe(body: str) -> bool:
    """Irreversible verbs classify, never fire alone: the judge must
    still find evidence. Severe plus evidence skips the arm wait."""
    low = " " + (body or "").lower()
    return any(re.search(r"\b" + v + r"\w*\b", low) for v in SEVERE)


def watch(messages: list, window_s: float = 180.0):
    """Pure detection. Returns {claim, agreers} or None."""
    humans = [m for m in messages if m.get("kind") == "chat"
              and m.get("author") not in ("agent", "dissent")]
    if len(humans) < 2:
        return None
    recent = humans[-6:]
    agreers = {}
    for m in recent:
        low = " " + m["body"].lower()
        if any(a in low for a in AGREE):
            agreers[m["author"]] = m
    if len(agreers) < 2:
        return None
    first_t = min(m["created_at"] for m in agreers.values())
    if time.time() - first_t > window_s:
        return None
    for m in recent:
        if m["created_at"] >= first_t:
            low = " " + m["body"].lower()
            if any(o in low for o in OBJECT):
                return None
    claim = None
    for m in reversed(humans):
        b = m["body"].strip()
        low = " " + b.lower()
        if len(b) > 15 and not any(a in low for a in AGREE):
            claim = b[:500]
            break
    if not claim:
        return None
    return {"claim": claim, "agreers": sorted(agreers)}


def judge_line(call_fn, thread: list, mission: str, facts: dict,
               ledger: list, proposals=None) -> dict:
    """One latest line through the model judge. Returns {fire, points,
    question, tin, tout}; fire False on any doubt or bad reply."""
    fact_txt = "; ".join(f"{k}: {v}" for k, v in list(facts.items())[:8])
    led_txt = "; ".join(
        f"[L{l.get('id')}] {l.get('what', '')}"
        f" (by {l.get('deadline', 'no date')})"
        for l in ledger[:5])
    prop_txt = "; ".join(f"[P{p.get('id')}] {p.get('what', '')}"
                         for p in (proposals or [])[:5])
    prompt = (JUDGE_PROMPT + f" Mission: {mission or 'none'}."
              f" Room facts: {fact_txt or 'none'}."
              f" Open ledger: {led_txt or 'none'}."
              f" Open proposals: {prop_txt or 'none'}.")
    try:
        out = call_fn(thread, prompt)
        card = json.loads(out["answer"])
    except Exception:
        try:  # one repair retry: restate the JSON-only order
            out = call_fn(thread, prompt + REPAIR)
            card = json.loads(out["answer"])
        except Exception:
            return {"fire": False, "points": [], "question": "",
                    "decision": None, "tin": 0, "tout": 0}
    points = [p for p in card.get("points", []) if isinstance(p, dict)][:2]
    cf = card.get("conflict")
    conflict = cf if isinstance(cf, dict) and cf.get("key") else None
    hats = [str(h)[:24] for h in card.get("hats", []) if str(h).strip()][:3]
    source = card.get("source") if card.get("source") in SOURCES else "thread"
    confident = card.get("confidence") == "high"
    dec = card.get("decision")
    decision = None
    if isinstance(dec, dict) and str(dec.get("what", "")).strip():
        raw_upd = str(dec.get("updates", "") or "").strip().upper()
        upd_ref = raw_upd if re.match(r"^[LP]\d+$", raw_upd) else ""
        decision = {"what": str(dec["what"])[:500],
                    "who": str(dec.get("who", ""))[:80],
                    "why": str(dec.get("why", ""))[:500],
                    "deadline": str(dec.get("deadline", ""))[:40],
                    "updates": upd_ref,
                    "needs_detail": bool(dec.get("needs_detail"))}
    if not card.get("fire") or not points or not card.get("question"):
        return {"fire": False, "points": [], "question": "",
                "conflict": None, "confident": False, "hats": hats,
                "source": source, "decision": decision,
                "tin": out.get("tin", 0), "tout": out.get("tout", 0)}
    return {"fire": True, "points": points, "question": card["question"],
            "conflict": conflict, "confident": confident, "hats": hats,
            "source": source, "decision": decision,
            "tin": out.get("tin", 0), "tout": out.get("tout", 0)}


def _read_queue(con, rid: str) -> list:
    rows = con.execute("SELECT body FROM dissent_queue WHERE room=?"
                       " ORDER BY id", (rid,))
    out = []
    for r in rows:
        try:
            card = json.loads(r["body"])
        except ValueError:
            continue
        if isinstance(card, dict):
            out.append(card)
    return out


def queue_card(con, rid: str, card: dict) -> None:
    con.execute("INSERT INTO dissent_queue (room, body, created_at)"
                " VALUES (?,?,?)",
                (rid, json.dumps(card), time.time()))
    con.commit()


def pop_queued(con, rid: str):
    while True:
        row = con.execute("SELECT id, body FROM dissent_queue WHERE room=?"
                          " ORDER BY id LIMIT 1", (rid,)).fetchone()
        if not row:
            return None
        con.execute("DELETE FROM dissent_queue WHERE id=?", (row["id"],))
        con.commit()
        try:
            card = json.loads(row["body"])
        except ValueError:
            continue
        if isinstance(card, dict):
            return card


STALE_PROMPT = (
    "You are a freshness checker. Claim from earlier: {claim}."
    " Recent room lines: {thread}."
    ' Reply JSON only: {{"still_true": true}} unless the room resolved,'
    ' contradicted, or abandoned the claim, then {{"still_true": false}}.'
)


def still_true(call_fn, thread: list, card: dict) -> bool:
    """True unless the room clearly moved past the card. Fail-open."""
    try:
        lines = " | ".join(f"{m['author']}: {m['body']}"
                           for m in thread[-12:])
        claim = f"{card.get('question', '')} / " \
            f"{json.dumps(card.get('points', []))}"
        out = call_fn([], STALE_PROMPT.format(claim=claim[:800],
                                              thread=lines[:2000]))
        return bool(json.loads(out["answer"]).get("still_true", True))
    except Exception:
        return True


def _note(con, rid: str, mid: int, outcome: str) -> None:
    """One-line trace of the last judge run. Powers the Plan tab status."""
    memory.remember(con, rid, "dissent_last_run",
                    json.dumps({"at": time.time(), "mid": mid,
                                "outcome": outcome}))


def judge_room(con, rid: str, model: str):
    """One judge call. Returns (card or None, proposal or None)."""
    if S.PAUSED:
        _note(con, rid, 0, "paused")
        return None, None
    if store.room_cost(con, rid) >= S.MAX_ROOM_COST:
        _note(con, rid, 0, "budget-spent")
        return None, None
    mem = {r["key"]: r["value"] for r in con.execute(
        "SELECT key, value FROM memory WHERE room=?", (rid,))}
    if mem.get("dissent_muted") == "1":
        _note(con, rid, 0, "muted")
        return None, None
    hist = store.recent(con, rid, 12)
    if not hist:
        _note(con, rid, 0, "empty")
        return None, None
    try:
        last = int(mem.get("last_dissent_mid", "0"))
    except ValueError:
        last = 0
    if last > 0 and hist[-1]["id"] - last < 8:
        _note(con, rid, hist[-1]["id"], "cooling-down")
        return None, None
    latest = None
    for m in reversed(hist):
        if m.get("kind") == "chat" \
                and m.get("author") not in ("agent", "dissent"):
            latest = m
            break
    if not latest:
        _note(con, rid, hist[-1]["id"], "no-chat")
        return None, None
    if vetoed(latest.get("body", "")):
        _note(con, rid, hist[-1]["id"], "vetoed")
        return None, None
    try:
        cursor = int(mem.get("dissent_cursor", "0") or 0)
    except ValueError:
        cursor = 0
    if hist[-1]["id"] <= cursor:
        _note(con, rid, hist[-1]["id"], "nothing-new")
        return None, None  # nothing new since the last read
    from . import memory as _memmod
    _memmod.remember(con, rid, "dissent_cursor", str(hist[-1]["id"]))
    row = con.execute("SELECT mission FROM rooms WHERE id=?",
                      (rid,)).fetchone()
    mission = row["mission"] if row else ""
    ages = {r["key"]: r["updated_at"] or 0 for r in con.execute(
        "SELECT key, updated_at FROM memory WHERE room=?", (rid,))}
    facts = {}
    for k, v in mem.items():
        if k in ("dissent_muted", "last_dissent_mid", "dissent_armed",
                 "dissent_cursor", "last_redteam_at", "dissent_last_run"):
            continue
        age_d = (time.time() - ages[k]) / 86400 if ages.get(k) else 0
        facts[k] = f"{v} [{int(age_d)} days old]" if age_d > 7 else v
    ledger = [dict(r) for r in con.execute(
        "SELECT id, what, deadline FROM ledger WHERE room=? AND status='open'"
        " ORDER BY id", (rid,))]
    call = lambda h, p: meta.spark_reply(  # noqa: E731
        S.MODEL_API_KEY, S.MODEL_API_BASE, model, h, p)
    open_props = store.list_proposals(con, rid)
    verdict = judge_line(call, hist, mission, facts, ledger, open_props)
    proposal = None
    dec = verdict.get("decision")
    if dec:
        what = dec["what"].strip()
        needs = bool(dec.get("needs_detail"))
        same = [p for p in open_props
                if p["what"].strip().lower() == what.lower()]
        if what and not same:
            ref = dec.get("updates") or ""
            if ref.startswith("P"):
                older = store.get_proposal(con, rid, int(ref[1:]))
                if not older or older["state"] != "open":
                    ref = ""
            if not ref:
                hit = store.find_similar_open(con, rid, what)
                if hit:
                    ref = f"{hit[0]}{hit[1]}"
            if ref.startswith("P"):
                store.update_proposal(con, rid, int(ref[1:]), dec["what"],
                                      dec["who"], dec["why"], dec["deadline"],
                                      "", needs)
                proposal = store.get_proposal(con, rid, int(ref[1:]))
            else:
                proposal = store.add_proposal(con, rid, dec["what"],
                                              dec["who"], dec["why"],
                                              dec["deadline"],
                                              latest.get("author", ""), ref,
                                              needs)
    if not verdict["fire"]:
        _note(con, rid, hist[-1]["id"],
              "proposal" if proposal else "silent")
        return None, proposal
    from . import memory
    try:
        armed = json.loads(mem.get("dissent_armed", ""))
    except ValueError:
        armed = None
    window = 4 if store.room_strict(con, rid) else 8
    fresh = (isinstance(armed, dict)
             and hist[-1]["id"] - armed.get("mid", 0) < window
             and time.time() - armed.get("at", 0) < 600)
    recent_chat = [m for m in hist
                   if m.get("kind") == "chat"
                   and m.get("author") not in ("agent", "dissent")][-3:]
    sev_window = any(severe(m.get("body", "")) for m in recent_chat)
    if not verdict["confident"] or (not sev_window and not fresh):
        memory.remember(con, rid, "dissent_armed",
                        json.dumps({"mid": latest["id"],
                                    "at": time.time()}))
        _note(con, rid, hist[-1]["id"],
              "proposal" if proposal else "armed")
        return None, proposal
    memory.forget(con, rid, "dissent_armed")
    store.log_cost(con, rid, "dissent", model, verdict["tin"],
                   verdict["tout"])
    body = {"points": verdict["points"], "question": verdict["question"],
            "conflict": verdict["conflict"], "hats": verdict["hats"],
            "source": verdict["source"]}
    open_card = con.execute(
        "SELECT id FROM messages WHERE room=? AND kind='dissent'"
        " AND (rating IS NULL OR rating=0) ORDER BY id DESC LIMIT 1",
        (rid,)).fetchone()
    if open_card:
        queue_card(con, rid, body)
        memory.remember(con, rid, "last_dissent_mid", str(hist[-1]["id"]))
        _note(con, rid, hist[-1]["id"], "queued")
        return None, proposal
    mid = store.post_message(con, rid, "dissent", json.dumps(body),
                             kind="dissent", model=model)
    memory.remember(con, rid, "last_dissent_mid", str(mid))
    card = {"id": mid, **body}
    _note(con, rid, hist[-1]["id"], "card")
    return card, proposal


def maybe_fire(con, rid: str, model: str):
    """One counter-card max per stretch. Returns card dict or None."""
    card, _ = judge_room(con, rid, model)
    return card


REDTEAM_PROMPT = (
    "You are the red team. Attack this room's plan, hard but honest. "
    'Reply ONLY JSON {"verdict": "one-line attack summary", '
    '"flaws": [{"flaw": "...", "receipt": "quote, [Lid], or artifact/task'
    ' title", "severity": "high|med|low"}], '
    '"strongest": "the one part of the plan that survives, one line"}. '
    "Rules: return 1 to 3 flaws, worst first; return fewer rather than "
    "padding weak ones, since a padded flaw is worse than silence. "
    "Every flaw needs a receipt "
    "from the thread, ledger, artifacts, or tasks below; no receipt, no flaw. "
    "Never invent facts, names, or numbers. Severity high means the plan "
    "fails as written; med means it limps; low means polish. Always name "
    "the strongest part so the team knows what to keep.")

REDTEAM_COOLDOWN_S = 600


def redteam_room(con, rid: str, model: str):
    """One deliberate attack. Returns (card or None, reason)."""
    if S.PAUSED:
        return None, "engine paused"
    if store.room_cost(con, rid) >= S.MAX_ROOM_COST:
        return None, "budget spent"
    mem = {r["key"]: r["value"] for r in con.execute(
        "SELECT key, value FROM memory WHERE room=?", (rid,))}
    try:
        last = float(mem.get("last_redteam_at", "0"))
    except ValueError:
        last = 0
    if time.time() - last < REDTEAM_COOLDOWN_S:
        return None, "cooling down"
    hist = [m for m in store.recent(con, rid, 30)
            if m.get("kind") in ("chat", "system", "ask", "answer")]
    if not hist:
        return None, "empty room"
    row = con.execute("SELECT mission FROM rooms WHERE id=?",
                      (rid,)).fetchone()
    mission = row["mission"] if row else ""
    led_txt = "; ".join(
        f"[L{l['id']}] {l['what']} ({remind.due_label(l['deadline'])})"
        for l in con.execute(
            "SELECT id, what, deadline FROM ledger WHERE room=?"
            " AND status='open' ORDER BY id", (rid,)).fetchall()[:8])
    prop_txt = "; ".join(
        f"[P{p['id']}] {p['what']}"
        for p in con.execute(
            "SELECT id, what FROM proposals WHERE room=?"
            " AND state='open' ORDER BY id", (rid,)).fetchall()[:5])
    art_txt = "; ".join(
        f"{a['title']} [{a['kind']}/{a['status']}]"
        for a in con.execute(
            "SELECT title, kind, status FROM artifacts WHERE room=?"
            " AND status!='applied' ORDER BY id", (rid,)).fetchall()[:6])
    task_txt = "; ".join(
        f"{t['title']} ({t['assignee'] or 'unassigned'}"
        f"{', by ' + t['due_text'] if t['due_text'] else ''})"
        for t in con.execute(
            "SELECT title, assignee, due_text FROM tasks WHERE room=?"
            " AND status='open' ORDER BY id", (rid,)).fetchall()[:8])
    prompt = (REDTEAM_PROMPT + f" Mission: {mission or 'none'}."
              f" Open ledger: {led_txt or 'none'}."
              f" Open proposals: {prop_txt or 'none'}."
              f" Artifacts: {art_txt or 'none'}."
              f" Open tasks: {task_txt or 'none'}.")
    try:
        out = meta.spark_reply(S.MODEL_API_KEY, S.MODEL_API_BASE,
                               model, hist, prompt, effort="high",
                               hist_n=30)
        card = json.loads(out["answer"])
    except Exception:
        try:  # one repair retry: restate the JSON-only order
            out = meta.spark_reply(S.MODEL_API_KEY, S.MODEL_API_BASE,
                                   model, hist, prompt + REPAIR,
                                   effort="high", hist_n=30)
            card = json.loads(out["answer"])
        except Exception:
            return None, "attack failed"
    flaws = []
    for item in card.get("flaws", [])[:3]:
        if not isinstance(item, dict) \
                or not str(item.get("flaw", "")).strip():
            continue
        sev = str(item.get("severity", "med")).lower()
        flaws.append({"flaw": str(item["flaw"])[:500],
                      "receipt": str(item.get("receipt", ""))[:300],
                      "severity": sev if sev in ("high", "med", "low")
                      else "med"})
    if not flaws or not str(card.get("verdict", "")).strip():
        return None, "attack failed"
    store.log_cost(con, rid, "redteam", model, out.get("tin", 0),
                   out.get("tout", 0))
    body = {"flaws": flaws,
            "verdict": str(card["verdict"])[:300],
            "strongest": str(card.get("strongest", ""))[:300]}
    mid = store.post_message(con, rid, "redteam", json.dumps(body),
                             kind="redteam", model=model)
    from . import memory as _memmod
    _memmod.remember(con, rid, "last_redteam_at", str(time.time()))
    card_out = {"id": mid, **body}
    return card_out, ""
