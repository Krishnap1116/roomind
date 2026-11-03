"""Live doors: rooms, join-by-link, chat sockets, agent answers."""
import asyncio
import json
import queue
import threading
import time

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi import WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse

import httpx

import roomind as S
from . import agent, brief, dissent, eval as strip, golden, memory, meta
from . import store, ui

app = FastAPI(title="Roomind")
_live: dict[str, set] = {}
_live_who: dict = {}
_judge_tasks: set[asyncio.Task] = set()
_judge_locks: dict[str, threading.Lock] = {}
_ask_locks: dict[str, threading.Lock] = {}


@app.exception_handler(httpx.HTTPError)
async def _model_down(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": "model unavailable"}, status_code=503)


def _db():
    return store.connect()


def _manage(me) -> bool:
    return bool(me) and me["role"] in ("owner", "operator")


async def _evict(rid: str) -> None:
    """Hang up every open tab on a deleted room, with a note first."""
    for peer in list(_live.pop(rid, set())):
        _live_who.pop(peer, None)
        try:
            await peer.send_json({"kind": "closed"})
        except Exception:
            pass
        try:
            await peer.close(code=4000)
        except Exception:
            pass


async def _cast(rid: str, payload: dict) -> None:
    """Push one live note to every open tab. Never fails the caller."""
    dead = []
    for peer in _live.get(rid, set()):
        try:
            await peer.send_json(payload)
        except Exception:
            dead.append(peer)
    for d in dead:
        _live[rid].discard(d)
        _live_who.pop(d, None)


def _judge_sync(rid: str, model_name: str, lock: threading.Lock):
    """Blocking monitor verdict, one at a time per room, off the loop."""
    with lock:
        con = _db()
        try:
            return dissent.judge_room(con, rid, model_name)
        finally:
            con.close()


async def _judge_later(rid: str, model_name: str) -> None:
    """Dissent verdict after the reply is out. Card follows live."""
    lock = _judge_locks.setdefault(rid, threading.Lock())
    card, proposal = await asyncio.to_thread(_judge_sync, rid, model_name,
                                             lock)
    if card:
        await _cast(rid, {"id": card["id"], "author": "dissent",
                          "kind": "dissent", "body": json.dumps(card)})
    if proposal:
        await _cast(rid, {"id": proposal["id"], "author": "room",
                          "kind": "proposal", "body": json.dumps(proposal)})


def _drop_judge(task: asyncio.Task) -> None:
    _judge_tasks.discard(task)
    if not task.cancelled():
        task.exception()  # retrieved: monitor faults never touch chat


_judge_pending: dict[str, asyncio.Task] = {}
_judge_first: dict[str, float] = {}


def _spawn_judge(rid: str, model_name: str) -> None:
    """Debounced monitor: idle seconds after quiet, maxwait at latest."""
    loop = asyncio.get_running_loop()
    now = loop.time()
    _judge_first.setdefault(rid, now)
    old = _judge_pending.pop(rid, None)
    if old is not None and not old.done():
        old.cancel()
    if now - _judge_first[rid] >= S.JUDGE_MAXWAIT_S:
        _judge_first.pop(rid, None)
        task = loop.create_task(_judge_later(rid, model_name))
        _judge_tasks.add(task)
        task.add_done_callback(_drop_judge)
        return

    async def _wait():
        await asyncio.sleep(S.JUDGE_IDLE_S)
        _judge_pending.pop(rid, None)
        _judge_first.pop(rid, None)
        await _judge_later(rid, model_name)

    task = loop.create_task(_wait())
    _judge_tasks.add(task)
    task.add_done_callback(_drop_judge)
    _judge_pending[rid] = task


@app.get("/healthz")
def healthz():
    return {"ok": True, "paused": S.PAUSED}


@app.get("/", response_class=HTMLResponse)
def home():
    return ui.homepage()


@app.get("/rooms/{rid}/app", response_class=HTMLResponse)
def room_app(rid: str, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        room = con.execute("SELECT mission FROM rooms WHERE id=?",
                           (rid,)).fetchone()
        if not me:
            if room:
                return ui.gone_page()
            return ui.closed_page()
        seats = con.execute("SELECT COUNT(*) AS c FROM members"
                            " WHERE room=?", (rid,)).fetchone()["c"]
        return ui.room_page(rid, me["name"], me["role"],
                            room["mission"] if room else "",
                            seats < 2)
    finally:
        con.close()


@app.post("/rooms")
def create_room(mission: str, name: str = ""):
    con = _db()
    try:
        return store.new_room(con, mission[:200] or "Untitled mission",
                              name[:40])
    finally:
        con.close()


@app.post("/rooms/{rid}/join")
def join(rid: str, name: str, invite: str):
    con = _db()
    try:
        try:
            return store.join_member(con, rid, name.strip() or "Guest", invite)
        except LookupError:
            raise HTTPException(403, "bad or expired invite")
    finally:
        con.close()


@app.get("/rooms/{rid}/messages")
def messages(rid: str, token: str, n: int = 30):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        rows = store.recent(con, rid, min(n, 100))
        tags = store.display_tags(con, rid)
        badges = store.role_badges(con, rid)
        for m in rows:
            t = tags.get(m.get("author_id") or "")
            if t:
                m["tag"] = t
            b = badges.get(m.get("author_id") or "")
            if b:
                m["badge"] = b
        return rows
    finally:
        con.close()


@app.post("/rooms/{rid}/ask")
async def ask(rid: str, token: str, text: str, model: str = ""):
    if S.PAUSED:
        raise HTTPException(503, "engine paused")
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        text = text.strip()
        if not text:
            raise HTTPException(400, "empty question")
        if store.room_cost(con, rid) >= S.MAX_ROOM_COST:
            raise HTTPException(402, "room budget spent")
        tag = store.display_tags(con, rid).get(me["id"])
        badge = store.role_badges(con, rid).get(me["id"])
        qid = store.post_message(con, rid, me["name"], text, kind="ask",
                                 author_id=me["id"])
        hist = store.recent(con, rid)
        noted = memory.recall(con, rid, text)
        await _cast(rid, {"id": qid, "author": me["name"], "tag": tag,
                          "badge": badge, "kind": "ask", "body": text})
        model_name = model or me["model"] or S.SPARK_MODEL
        tools = agent.toolset(S.SEARCH_API_KEY, S.SEARCH_BASE)
        t0 = time.time()
        out = agent.run_loop(
            lambda ms: meta.chat(S.MODEL_API_KEY, S.MODEL_API_BASE,
                                 model_name, ms, effort=S.ASK_EFFORT),
            tools, text, history=hist, notes=noted)
        secs = time.time() - t0
        for item in out.get("remember", [])[:2]:
            if isinstance(item, dict):
                memory.remember(con, rid, str(item.get("key", "")),
                                str(item.get("value", "")))
        tin = sum(c["tin"] for c in out["calls"])
        tout = sum(c["tout"] for c in out["calls"])
        store.log_cost(con, rid, "ask", model_name, tin, tout, secs)
        aid = store.post_message(con, rid, "agent", out["answer"],
                                 kind="answer",
                                 model=model_name,
                                 reasons="\n".join(out["reasons"]))
        await _cast(rid, {"id": aid, "author": "agent", "kind": "answer",
                          "body": out["answer"]})
        _spawn_judge(rid, S.SPARK_MODEL)
        return {"answer": out["answer"], "reasons": out["reasons"]}
    finally:
        con.close()


@app.get("/rooms/{rid}/askstream")
async def askstream(rid: str, token: str, text: str, model: str = ""):
    """Ask over server-sent events: Final tokens flow live, then done."""
    if S.PAUSED:
        raise HTTPException(503, "engine paused")
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        text = text.strip()
        if not text:
            raise HTTPException(400, "empty question")
        if store.room_cost(con, rid) >= S.MAX_ROOM_COST:
            raise HTTPException(402, "room budget spent")
        tag = store.display_tags(con, rid).get(me["id"])
        badge = store.role_badges(con, rid).get(me["id"])
        qid = store.post_message(con, rid, me["name"], text, kind="ask",
                                 author_id=me["id"])
        my_model = me["model"] or ""
    finally:
        con.close()
    await _cast(rid, {"id": qid, "author": me["name"], "tag": tag,
                      "badge": badge, "kind": "ask", "body": text})
    model_name = model or my_model or S.SPARK_MODEL
    tools = agent.toolset(S.SEARCH_API_KEY, S.SEARCH_BASE)

    async def gen():
        qq: queue.Queue = queue.Queue()
        box: dict = {}

        def work():
            lock = _ask_locks.setdefault(rid, threading.Lock())
            with lock:
                con0 = _db()
                try:
                    hist = store.recent(con0, rid, 12)
                    noted = memory.recall(con0, rid, text)
                finally:
                    con0.close()
                try:
                    box["out"] = agent.run_loop(agent.streaming_call(
                        lambda ms: meta.chat_stream(
                            S.MODEL_API_KEY, S.MODEL_API_BASE, model_name, ms,
                            effort=S.ASK_EFFORT),
                        lambda t: qq.put(("tok", t))), tools, text,
                        history=hist, notes=noted)
                except Exception as exc:  # noqa: BLE001 - mid-stream note
                    box["err"] = exc
                finally:
                    qq.put(("end", None))

        t0 = time.time()
        threading.Thread(target=work, daemon=True).start()
        while True:
            kind, val = await asyncio.to_thread(qq.get)
            if kind == "end":
                break
            yield f"data: {json.dumps({'tok': val})}\n\n"
        secs = time.time() - t0
        if "err" in box:
            yield f"data: {json.dumps({'error': 'Model unavailable right now.'})}\n\n"
            return
        out = box["out"]
        con2 = _db()
        try:
            for item in out.get("remember", [])[:2]:
                if isinstance(item, dict):
                    memory.remember(con2, rid, str(item.get("key", "")),
                                    str(item.get("value", "")))
            tin = sum(c["tin"] for c in out["calls"])
            tout = sum(c["tout"] for c in out["calls"])
            store.log_cost(con2, rid, "ask", model_name, tin, tout, secs)
            aid = store.post_message(con2, rid, "agent", out["answer"],
                                     kind="answer", model=model_name,
                                     reasons="\n".join(out["reasons"]))
        finally:
            con2.close()
        await _cast(rid, {"id": aid, "author": "agent", "kind": "answer",
                          "body": out["answer"]})
        yield f"data: {json.dumps({'done': {'answer': out['answer'], 'reasons': out['reasons']}})}\n\n"

    _spawn_judge(rid, S.SPARK_MODEL)
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/rooms/{rid}/brief")
def room_brief(rid: str, token: str, model: str = ""):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        return brief.build_brief(con, rid,
                                 model or me["model"] or S.SPARK_MODEL)
    finally:
        con.close()


@app.get("/rooms/{rid}/catchup")
def catchup(rid: str, token: str, since_id: int = 0, model: str = ""):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        return brief.catchup(con, rid, me["name"], since_id,
                             model or me["model"] or S.SPARK_MODEL)
    finally:
        con.close()


@app.post("/rooms/{rid}/dissent/check")
def dissent_check(rid: str, token: str, model: str = ""):
    if S.PAUSED:
        raise HTTPException(503, "engine paused")
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        card, proposal = dissent.judge_room(con, rid,
                                               model or S.SPARK_MODEL)
        return {"triggered": bool(card), "card": card,
                "proposal": proposal}
    finally:
        con.close()


@app.post("/rooms/{rid}/dissent/mute")
def dissent_mute(rid: str, token: str, on: bool = True):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        memory.remember(con, rid, "dissent_muted", "1" if on else "0")
        return {"muted": on}
    finally:
        con.close()


@app.get("/rooms/{rid}/proposals")
def proposals_list(rid: str, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        return store.list_proposals(con, rid)
    finally:
        con.close()


@app.post("/rooms/{rid}/proposals")
async def proposal_create(rid: str, token: str, what: str, who: str = "",
                          why: str = "", deadline: str = ""):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        what = what.strip()
        if not what:
            raise HTTPException(400, "empty decision")
        prop = store.add_proposal(con, rid, what, who.strip(),
                                  why.strip(), deadline.strip(),
                                  me["name"])
    finally:
        con.close()
    await _cast(rid, {"id": prop["id"], "author": "room",
                      "kind": "proposal", "body": json.dumps(prop)})
    return prop


@app.post("/rooms/{rid}/proposals/{pid}/confirm")
async def proposal_confirm(rid: str, pid: int, token: str, what: str = "",
                           who: str = "", why: str = "",
                           deadline: str = ""):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        prop = store.get_proposal(con, rid, pid)
        if not prop or prop["state"] != "open":
            raise HTTPException(404, "proposal gone")
        what = (what or prop["what"]).strip()
        if not what:
            raise HTTPException(400, "empty decision")
        who = (who or prop["who"]).strip()
        why = (why or prop["why"]).strip()
        deadline = (deadline or prop["deadline"]).strip()
        store.settle_proposal(con, rid, pid, "confirmed", what, who, why,
                              deadline)
        target = None
        ref = (prop["updates"] or "").strip().upper()
        if ref.startswith("L") and ref[1:].isdigit():
            target = store.get_ledger(con, rid, int(ref[1:]))
        if target:
            store.update_ledger(con, rid, target["id"], what, who, why,
                                deadline)
            action = "updated"
        else:
            store.add_ledger(con, rid, what, who, why, deadline)
            action = "stamped"
        mid = store.post_message(con, rid, "room",
                                 f"{me['name']} {action}: {what}",
                                 kind="system")
    finally:
        con.close()
    await _cast(rid, {"id": mid, "author": "room", "kind": "system",
                      "body": f"{action}: {what}"})
    await _cast(rid, {"kind": "proposal", "id": pid, "state": "confirmed"})
    return {"stamped": pid, "updated": target["id"] if target else None}


@app.post("/rooms/{rid}/proposals/{pid}/dismiss")
async def proposal_dismiss(rid: str, pid: int, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        prop = store.get_proposal(con, rid, pid)
        if not prop or prop["state"] != "open":
            raise HTTPException(404, "proposal gone")
        store.settle_proposal(con, rid, pid, "dismissed", prop["what"],
                              prop["who"], prop["why"], prop["deadline"])
    finally:
        con.close()
    await _cast(rid, {"kind": "proposal", "id": pid, "state": "dismissed"})
    return {"dismissed": pid}


@app.post("/rooms/{rid}/ledger")
def ledger_add(rid: str, token: str, what: str, who: str = "",
               why: str = "", deadline: str = ""):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        return store.add_ledger(con, rid, what, who, why, deadline)
    finally:
        con.close()


@app.get("/rooms/{rid}/ledger")
def ledger_list(rid: str, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        return store.list_ledger(con, rid)
    finally:
        con.close()


@app.delete("/rooms/{rid}/memory")
def memory_forget(rid: str, token: str, key: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        memory.forget(con, rid, key)
        return {"forgotten": key.strip().lower()[:80]}
    finally:
        con.close()


@app.post("/rooms/{rid}/memory/fix")
def memory_fix(rid: str, token: str, key: str, value: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        if not key.strip() or not value.strip():
            raise HTTPException(400, "key and value required")
        memory.remember(con, rid, key, value)
        return {"fixed": key.strip().lower()[:80]}
    finally:
        con.close()


@app.post("/rooms/{rid}/messages/{mid}/rate")
async def rate_message(rid: str, mid: int, token: str, up: bool = True):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        try:
            out = store.rate_message(con, rid, mid, up)
        except LookupError:
            raise HTTPException(404, "no such message")
        except ValueError as e:
            raise HTTPException(400, str(e))
        row = con.execute("SELECT kind FROM messages WHERE id=? AND room=?",
                          (mid, rid)).fetchone()
        is_card = bool(row and row["kind"] == "dissent")
    finally:
        con.close()
    popped = None
    if is_card:
        popped = await asyncio.to_thread(_pop_fresh, rid)
    if popped:
        body = {k: popped[k] for k in ("points", "question", "conflict",
                                      "hats", "source")}
        await _cast(rid, {"id": popped["id"], "author": "dissent",
                          "kind": "dissent", "body": json.dumps(body)})
    return out


def _pop_fresh(rid: str):
    """Next queued card still true. Stale ones drop silently."""
    con = _db()
    try:
        while True:
            card = dissent.pop_queued(con, rid)
            if not card:
                return None
            hist = store.recent(con, rid, 12)
            call = lambda h, p: meta.spark_reply(  # noqa: E731
                S.MODEL_API_KEY, S.MODEL_API_BASE, S.SPARK_MODEL, h, p)
            if dissent.still_true(call, hist, card):
                pid = store.post_message(con, rid, "dissent",
                                         json.dumps(card), kind="dissent")
                return {"id": pid, **card}
    finally:
        con.close()


@app.get("/rooms/{rid}/eval")
def eval_strip(rid: str, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        cached = store.load_golden(con, rid)
        out = {"golden": json.loads(cached) if cached else None}
        out.update(store.strip_numbers(con, rid))
        return out
    finally:
        con.close()


@app.post("/rooms/{rid}/eval/exam")
def eval_exam(rid: str, token: str, model: str = ""):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        if not S.MODEL_API_KEY:
            raise HTTPException(503, "hosted model key missing")
        name = model or S.SPARK_MODEL
        fn = lambda h, p: meta.spark_reply(  # noqa: E731
            S.MODEL_API_KEY, S.MODEL_API_BASE, name, h, p)
        rep = strip.run_suite_judge(fn, golden.GOLDEN)
        rep["at"] = time.time()
        rep["model"] = name
        store.log_cost(con, rid, "eval-exam", name, rep["tin"],
                       rep["tout"], rep["secs"])
        store.save_golden(con, rid, json.dumps(rep))
        return rep
    finally:
        con.close()


@app.get("/rooms/{rid}/usage")
def usage(rid: str, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        rows = con.execute(
            "SELECT model, COALESCE(SUM(tin),0) AS tin,"
            " COALESCE(SUM(tout),0) AS tout, COALESCE(SUM(usd),0) AS usd"
            " FROM costs WHERE room=? GROUP BY model", (rid,))
        by_model = {r["model"]: {"tin": r["tin"], "tout": r["tout"],
                                 "usd": round(r["usd"], 4),
                                 "window": meta.WINDOWS.get(r["model"])}
                    for r in rows}
        return {"spent_usd": round(store.room_cost(con, rid), 4),
                "cap_usd": S.MAX_ROOM_COST, "by_model": by_model,
                "default": S.SPARK_MODEL}
    finally:
        con.close()


@app.post("/rooms/{rid}/invites")
def mint_invites(rid: str, token: str, uses: int = 1, hours: int = 24):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        return store.mint_invite(con, rid, "member", uses, hours)
    finally:
        con.close()


@app.post("/rooms/{rid}/leave")
async def leave(rid: str, token: str, successor_id: str = ""):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        others = [m for m in store.list_members(con, rid)
                  if m["id"] != me["id"]]
        if me["role"] == "owner" and others:
            if successor_id:
                if successor_id not in {m["id"] for m in others}:
                    raise HTTPException(404, "no such member")
                store.transfer_owner(con, rid, successor_id)
            else:
                nxt = store.oldest_successor(con, rid, me["id"])
                store.transfer_owner(con, rid, nxt)
                successor_id = nxt
            who = [m for m in others if m["id"] == successor_id][0]["name"]
            store.post_message(con, rid, "room",
                               f"Crown passed to {who}.", kind="system")
        con.execute("DELETE FROM members WHERE room=? AND token=?",
                    (rid, token))
        con.commit()
        if not store.list_members(con, rid):
            store.delete_room(con, rid)
            await _evict(rid)
            return {"left": rid, "closed": True}
        return {"left": rid}
    finally:
        con.close()


@app.post("/rooms/{rid}/members/{mid}/kick")
async def kick_member(rid: str, mid: str, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        target = store.member_by_id(con, rid, mid)
        if not target:
            raise HTTPException(404, "no such member")
        if target["id"] == me["id"]:
            raise HTTPException(400, "leave instead of kicking yourself")
        if target["role"] == "owner" or (
                target["role"] == "operator" and me["role"] != "owner"):
            raise HTTPException(403, "cannot kick them")
        store.remove_member(con, rid, mid)
        sys_id = store.post_message(con, rid, "room",
                                    f"{me['name']} kicked {target['name']}.",
                                    kind="system")
        name = target["name"]
    finally:
        con.close()
    await _cast(rid, {"id": sys_id, "author": "room", "kind": "system",
                      "body": f"kicked: {name}"})
    for peer in list(_live.get(rid, set())):
        if _live_who.get(peer) == mid:
            try:
                await peer.send_json({"kind": "kicked"})
            except Exception:
                pass
            try:
                await peer.close(code=4001)
            except Exception:
                pass
            _live.get(rid, set()).discard(peer)
            _live_who.pop(peer, None)
    return {"kicked": mid}


@app.get("/rooms/{rid}/state")
def room_state(rid: str, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        return {"locked": store.room_locked(con, rid),
                "model": me["model"] or "",
                "default": S.SPARK_MODEL}
    finally:
        con.close()


@app.get("/rooms/{rid}/models")
def room_models(rid: str, token: str):
    """Chat models the server key can use. Live list, verified fallback."""
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
    finally:
        con.close()
    ids = [m for m in meta.list_models(S.MODEL_API_KEY, S.MODEL_API_BASE)
           if "spark" in m]
    if not ids:
        ids = ["muse-spark-1.3", "muse-spark-1.2", "muse-spark-1.1"]
    ids = [S.SPARK_MODEL] + [m for m in ids if m != S.SPARK_MODEL]
    return {"models": ids, "default": S.SPARK_MODEL}


@app.post("/rooms/{rid}/lock")
async def set_lock(rid: str, token: str, on: bool = True):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        store.set_room_locked(con, rid, on)
        word = "locked" if on else "unlocked"
        sys_id = store.post_message(con, rid, "room",
                                    f"{me['name']} {word} the room.",
                                    kind="system")
    finally:
        con.close()
    await _cast(rid, {"id": sys_id, "author": "room", "kind": "system",
                      "body": f"room {word}"})
    return {"locked": on}


@app.post("/rooms/{rid}/model")
def set_model(rid: str, token: str, model: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        model = model.strip()
        if not model:
            raise HTTPException(400, "empty model")
        store.set_member_model(con, rid, me["id"], model)
        return {"model": model[:80]}
    finally:
        con.close()


@app.get("/rooms/{rid}/invites")
def list_invites(rid: str, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        return store.list_invites(con, rid)
    finally:
        con.close()


@app.post("/rooms/{rid}/invites/topup")
def topup_invite(rid: str, token: str, invite: str, add_uses: int = 5):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        try:
            return store.topup_invite(con, rid, invite, add_uses)
        except LookupError:
            raise HTTPException(404, "no such invite")
    finally:
        con.close()


@app.get("/rooms/{rid}/members")
def members(rid: str, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        store.ensure_nicks(con, rid)
        return store.list_members(con, rid)
    finally:
        con.close()


@app.post("/rooms/{rid}/operators")
def grant_operator(rid: str, token: str, member_id: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me or me["role"] != "owner":
            raise HTTPException(403, "owner only")
        try:
            return store.set_operator(con, rid, member_id)
        except LookupError:
            raise HTTPException(404, "no such member")
    finally:
        con.close()


@app.post("/rooms/{rid}/owner")
def make_owner(rid: str, token: str, member_id: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me or me["role"] != "owner":
            raise HTTPException(403, "owner only")
        try:
            return store.transfer_owner(con, rid, member_id)
        except LookupError:
            raise HTTPException(404, "no such member")
    finally:
        con.close()


@app.delete("/rooms/{rid}")
async def wipe(rid: str, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me or me["role"] != "owner":
            raise HTTPException(403, "owner only")
        store.delete_room(con, rid)
        await _evict(rid)
        return {"deleted": rid}
    finally:
        con.close()


@app.websocket("/rooms/{rid}/live")
async def live(ws: WebSocket, rid: str, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            await ws.close(code=4403)
            return
    finally:
        con.close()
    await ws.accept()
    _live.setdefault(rid, set()).add(ws)
    _live_who[ws] = me["id"]
    try:
        while True:
            text = (await ws.receive_text())[:4000]
            con = _db()
            try:
                if store.room_locked(con, rid):
                    try:
                        await ws.send_json({"kind": "locked",
                                            "body": "Room is locked."})
                    except Exception:
                        pass
                    continue
                mid = store.post_message(con, rid, me["name"], text,
                                         author_id=me["id"])
                tag = store.display_tags(con, rid).get(me["id"])
                badge = store.role_badges(con, rid).get(me["id"])
            finally:
                con.close()
            await _cast(rid, {"id": mid, "author": me["name"],
                              "tag": tag, "badge": badge, "body": text})
            _spawn_judge(rid, S.SPARK_MODEL)
    except WebSocketDisconnect:
        _live[rid].discard(ws)
        _live_who.pop(ws, None)
