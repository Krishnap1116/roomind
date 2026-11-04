"""Live doors: rooms, join-by-link, chat sockets, agent answers."""
import asyncio
import json
import queue
import re
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi import WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response, StreamingResponse

import httpx

import roomind as S
from . import agent, brief, dissent, eval as strip, golden, memory, meta
from . import remind, store, ui

@asynccontextmanager
async def _life(app: FastAPI):
    task = asyncio.get_running_loop().create_task(_away_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="Roomind", lifespan=_life)
_live: dict[str, set] = {}
_live_who: dict = {}
_judge_tasks: set[asyncio.Task] = set()
_judge_locks: dict[str, threading.Lock] = {}
_ask_locks: dict[str, threading.Lock] = {}
_exam_locks: dict[str, threading.Lock] = {}


@app.exception_handler(httpx.HTTPError)
async def _model_down(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": "model unavailable"}, status_code=503)


def _db():
    return store.connect()


def _manage(me) -> bool:
    return bool(me) and me["role"] in ("owner", "operator")


async def _maybe_remind(rid: str, force: bool = False) -> bool:
    """One nudge per day past the set time, posted live."""
    con = _db()
    try:
        if store.room_locked(con, rid):
            return False
        now = remind.now_local()
        today = now.date().isoformat()
        if not force and not remind.due_at(
                store.room_remind_at(con, rid), now,
                store.room_last_remind(con, rid)):
            return False
        body = remind.compose(store.room_mission(con, rid),
                              store.list_ledger(con, rid),
                              store.list_reminders(con, rid), today)
        if not body:
            return False
        mid = store.post_message(con, rid, "room", body, kind="system")
        if not force:
            store.set_last_remind(con, rid, today)
    finally:
        con.close()
    await _cast(rid, {"id": mid, "author": "room", "kind": "remind",
                      "body": body})
    return True


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


def _find_mention(text: str, mates: list):
    """First @teammate in the line. Returns (mate, question) or (None, '')."""
    for mate in mates:
        found = re.search(r"@" + re.escape(mate["name"]) + r"\b", text,
                          re.IGNORECASE)
        if found:
            rest = (text[:found.start()] + text[found.end():]).strip()
            return mate, re.sub(r"\s+", " ", rest)
    return None, ""


def _teammate_sync(rid: str, mate: dict, question: str,
                   model_name: str):
    lock = _ask_locks.setdefault(rid, threading.Lock())
    with lock:
        con0 = _db()
        try:
            if S.PAUSED or store.room_locked(con0, rid) \
                    or store.room_cost(con0, rid) >= S.MAX_ROOM_COST:
                return None
            hist = store.recent(con0, rid, 12)
            noted = memory.recall(con0, rid, question)
        finally:
            con0.close()
        tools = agent.toolset(S.SEARCH_API_KEY, S.SEARCH_BASE)
        t0 = time.time()
        try:
            out = agent.run_loop(
                lambda ms: meta.chat(S.MODEL_API_KEY, S.MODEL_API_BASE,
                                     model_name, ms, effort=S.ASK_EFFORT),
                tools,
                f"[You are {mate['name']}, {mate['role']}."
                f" {mate['instructions']}]\n\n{question}",
                history=hist, notes=noted)
        except Exception:
            return None
        return out, time.time() - t0


async def _teammate_later(rid: str, mate: dict, question: str,
                          model_name: str) -> None:
    try:
        done = await asyncio.to_thread(_teammate_sync, rid, mate,
                                       question, model_name)
    except Exception:
        return
    if not done:
        return
    out, secs = done
    con = _db()
    try:
        for item in out.get("remember", [])[:2]:
            if isinstance(item, dict):
                memory.remember(con, rid, str(item.get("key", "")),
                                str(item.get("value", "")))
        tin = sum(c["tin"] for c in out["calls"])
        tout = sum(c["tout"] for c in out["calls"])
        store.log_cost(con, rid, "mention", model_name, tin, tout, secs)
        aid = store.post_message(con, rid, mate["name"], out["answer"],
                                 kind="answer", model=model_name,
                                 reasons="\n".join(out["reasons"]))
    finally:
        con.close()
    await _cast(rid, {"id": aid, "author": mate["name"], "kind": "answer",
                      "body": out["answer"], "reasons": out["reasons"]})


def _away_run(task: dict):
    """Run one due away-task serially. Returns (rid, cast) or None."""
    rid = task["room"]
    lock = _ask_locks.setdefault(rid, threading.Lock())
    with lock:
        con = _db()
        try:
            rows = [t for t in store.list_away(con, rid)
                    if t["id"] == task["id"]]
            if not rows or rows[0]["status"] != "pending":
                return None
            task = rows[0]
            if S.PAUSED or store.room_locked(con, rid) \
                    or store.room_cost(con, rid) >= S.MAX_ROOM_COST:
                return None
            mate = store.get_teammate(con, rid, task["teammate_id"])
            if not mate:
                store.mark_away(con, task["id"], "failed",
                                task["attempts"])
                return None
            store.mark_away(con, task["id"], "working",
                            task["attempts"])
            hist = store.recent(con, rid, 12)
            noted = memory.recall(con, rid, task["instruction"])
            creator = con.execute(
                "SELECT model FROM members WHERE room=? AND id=?",
                (rid, task["creator_id"])).fetchone()
            model_name = (creator["model"] or S.SPARK_MODEL) \
                if creator else S.SPARK_MODEL
        finally:
            con.close()
        tools = agent.toolset(S.SEARCH_API_KEY, S.SEARCH_BASE)
        t0 = time.time()
        try:
            out = agent.run_loop(
                lambda ms: meta.chat(S.MODEL_API_KEY, S.MODEL_API_BASE,
                                     model_name, ms, effort=S.ASK_EFFORT),
                tools,
                f"[You are {mate['name']}, {mate['role']}."
                f" {mate['instructions']}]\n\n{task['instruction']}",
                history=hist, notes=noted)
        except Exception:
            attempts = task["attempts"] + 1
            con2 = _db()
            try:
                store.mark_away(con2, task["id"],
                                "failed" if attempts >= 3 else "pending",
                                attempts)
            finally:
                con2.close()
            return None
        secs = time.time() - t0
        con3 = _db()
        try:
            for item in out.get("remember", [])[:2]:
                if isinstance(item, dict):
                    memory.remember(con3, rid, str(item.get("key", "")),
                                    str(item.get("value", "")))
            tin = sum(c["tin"] for c in out["calls"])
            tout = sum(c["tout"] for c in out["calls"])
            store.log_cost(con3, rid, "away", model_name, tin, tout,
                           secs)
            aid = store.post_message(con3, rid, mate["name"],
                                     out["answer"], kind="answer",
                                     model=model_name,
                                     reasons="\n".join(out["reasons"]))
            store.mark_away(con3, task["id"], "done",
                            task["attempts"], aid)
        finally:
            con3.close()
        return rid, {"id": aid, "author": mate["name"], "kind": "answer",
                     "body": out["answer"], "reasons": out["reasons"]}


def _away_tick() -> list:
    """One pass over every due away-task. Returns casts to deliver."""
    if S.PAUSED:
        return []
    con = _db()
    try:
        today = remind.now_local().date().isoformat()
        due = store.due_away(con, today)
    finally:
        con.close()
    casts = []
    for task in due:
        done = _away_run(task)
        if done:
            casts.append(done)
    return casts


async def _away_loop() -> None:
    while True:
        await asyncio.sleep(S.AWAY_TICK_S)
        try:
            for rid, payload in await asyncio.to_thread(_away_tick):
                await _cast(rid, payload)
        except Exception:
            pass


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
                            seats < 2, store.room_parent(con, rid),
                            me["id"])
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


@app.post("/rooms/{rid}/side")
async def side_create(rid: str, token: str, mission: str,
                      mids: str = ""):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        if store.room_parent(con, rid):
            raise HTTPException(400, "side rooms stay one level deep")
        seats = con.execute("SELECT COUNT(*) AS c FROM members"
                            " WHERE room=?", (rid,)).fetchone()["c"]
        if seats < 2:
            raise HTTPException(400, "split needs a shared room")
        picked = []
        for mid in [m.strip() for m in mids.split(",") if m.strip()]:
            if mid == me["id"]:
                continue
            target = store.member_by_id(con, rid, mid)
            if not target:
                raise HTTPException(400, "pick people from this room")
            picked.append(target)
        mission = mission[:200].strip() or "Untitled side mission"
        out = store.new_room(con, mission, me["name"], me["id"])
        store.set_parent(con, out["room_id"], rid)
        for target in picked:
            store.seat_member(con, out["room_id"], target["name"],
                              "member", target["id"])
        store.ensure_nicks(con, out["room_id"])
        with_names = (" with " + ", ".join(t["name"] for t in picked)
                      if picked else "")
        sys_id = store.post_message(con, rid, "room",
                                    f"{me['name']} opened side room"
                                    f" '{mission}'{with_names}"
                                    f" ({out['room_id']}).",
                                    kind="system")
    finally:
        con.close()
    await _cast(rid, {"id": sys_id, "author": "room", "kind": "system",
                      "body": f"side room: {mission}"})
    return out


@app.get("/rooms/{rid}/sides")
def sides_list(rid: str, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        return [s for s in store.list_sides(con, rid)
                if store.member_by_origin(con, s["room_id"], me["id"])]
    finally:
        con.close()


@app.post("/rooms/{sid}/open-side")
def open_side(sid: str, ptoken: str):
    con = _db()
    try:
        parent = store.room_parent(con, sid)
        if not parent:
            raise HTTPException(404, "not a side room")
        pm = store.member_by_token(con, parent, ptoken)
        if not pm:
            raise HTTPException(403, "parent seat required")
        old = store.member_by_origin(con, sid, pm["id"])
        if not old:
            raise HTTPException(403, "side seat required")
        return {"token": old["token"]}
    finally:
        con.close()


@app.get("/rooms/{sid}/roster")
def side_roster(sid: str, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, sid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        parent = store.room_parent(con, sid)
        if not parent:
            raise HTTPException(400, "main rooms use invites")
        side = store.list_members(con, sid)
        origins = {m["origin"] for m in con.execute(
            "SELECT origin FROM members WHERE room=?", (sid,))}
        main = [m for m in store.list_members(con, parent)
                if m["id"] not in origins]
        return {"side": side, "main": main}
    finally:
        con.close()


@app.post("/rooms/{sid}/roster/add")
async def roster_add(sid: str, token: str, mid: str):
    con = _db()
    try:
        me = store.member_by_token(con, sid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        parent = store.room_parent(con, sid)
        if not parent:
            raise HTTPException(400, "main rooms use invites")
        if store.room_locked(con, sid) or store.room_locked(con, parent):
            raise HTTPException(403, "room locked")
        target = store.member_by_id(con, parent, mid)
        if not target:
            raise HTTPException(404, "no such member in the main room")
        old = store.member_by_origin(con, sid, target["id"])
        if old:
            return {"token": old["token"], "new": False}
        seat = store.seat_member(con, sid, target["name"], "member",
                                 target["id"])
        mission = store.room_mission(con, sid)
        sys_main = store.post_message(con, parent, "room",
                                      f"{target['name']} joined side room"
                                      f" '{mission}' ({sid}).",
                                      kind="system")
        sys_side = store.post_message(con, sid, "room",
                                      f"{me['name']} added {target['name']}"
                                      " to the side room.",
                                      kind="system")
    finally:
        con.close()
    await _cast(parent, {"id": sys_main, "author": "room", "kind": "system",
                         "body": f"{target['name']} joined side room:"
                                 f" {mission}"})
    await _cast(sid, {"id": sys_side, "author": "room", "kind": "system",
                      "body": f"added: {target['name']}"})
    return {"token": seat["token"], "new": True}


@app.post("/rooms/{sid}/share-back")
async def share_back(sid: str, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, sid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        parent = store.room_parent(con, sid)
        if not parent:
            raise HTTPException(400, "main rooms have nowhere to report")
        if store.room_locked(con, sid) or store.room_locked(con, parent):
            raise HTTPException(403, "room locked")
        mission = store.room_mission(con, sid)
        open_led = [r for r in store.list_ledger(con, sid)
                    if r.get("status", "open") == "open"]
        chats = con.execute("SELECT COUNT(*) AS c FROM messages"
                            " WHERE room=? AND kind='chat'",
                            (sid,)).fetchone()["c"]
        if open_led:
            lines = "\n".join(
                f"• {r['what']}"
                f"{' — ' + r['who'] if r.get('who') else ''}"
                f"{' (' + remind.due_label(r['deadline']) + ')' if r.get('deadline') else ''}"
                for r in open_led)
        else:
            lines = "(no stamped decisions yet)"
        body = (f"Side room '{mission}' reports (by {me['name']}):\n"
                f"{lines}\n{chats} chats · room {sid}")
        sys_id = store.post_message(con, parent, "room", body,
                                    kind="system")
        marker = f"side-report:{sid}"
        live = [r for r in store.list_ledger(con, parent)
                if r.get("status", "open") == "open"
                and r.get("why") == marker]
        if live:
            store.update_ledger(con, parent, live[0]["id"], body,
                                me["name"], marker)
        else:
            store.add_ledger(con, parent, body, me["name"], marker)
    finally:
        con.close()
    await _cast(parent, {"id": sys_id, "author": "room", "kind": "system",
                         "body": body})
    return {"shared": parent}


@app.post("/rooms/{rid}/join")
def join(rid: str, name: str, invite: str):
    con = _db()
    try:
        if not con.execute("SELECT 1 FROM rooms WHERE id=?",
                           (rid,)).fetchone():
            raise HTTPException(404, "no such room")
        if store.room_parent(con, rid):
            raise HTTPException(400, "side rooms seat from the main room")
        try:
            return store.join_member(con, rid, name.strip() or "Guest",
                                     invite)
        except LookupError:
            raise HTTPException(403, "bad or expired invite")
    finally:
        con.close()


@app.get("/rooms/{rid}/messages")
async def messages(rid: str, token: str, n: int = 30):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        await _maybe_remind(rid)
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
                          "badge": badge, "kind": "ask", "body": text,
                          "author_id": me["id"]})
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
                                 reasons="\n".join(out["reasons"]),
                                 ask_id=qid)
        await _cast(rid, {"id": aid, "author": "agent", "kind": "answer",
                          "body": out["answer"], "reasons": out["reasons"],
                          "ask_id": qid})
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
                      "badge": badge, "kind": "ask", "body": text,
                      "author_id": me["id"]})
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
                                     reasons="\n".join(out["reasons"]),
                                     ask_id=qid)
        finally:
            con2.close()
        await _cast(rid, {"id": aid, "author": "agent", "kind": "answer",
                          "body": out["answer"], "reasons": out["reasons"],
                          "ask_id": qid})
        yield f"data: {json.dumps({'done': {'answer': out['answer'], 'reasons': out['reasons']}})}\n\n"

    _spawn_judge(rid, S.SPARK_MODEL)
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/rooms/{rid}/brief")
def room_brief(rid: str, token: str, model: str = "",
               include_sides: bool = False):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        return brief.build_brief(con, rid,
                                 model or me["model"] or S.SPARK_MODEL,
                                 include_sides, me["id"])
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
async def dissent_mute(rid: str, token: str, on: bool = True):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        memory.remember(con, rid, "dissent_muted", "1" if on else "0")
    finally:
        con.close()
    await _cast(rid, {"kind": "muted", "muted": on})
    return {"muted": on}


def _red_cards(con, rid: str) -> list:
    cards = []
    for r in store.list_redteam(con, rid):
        try:
            body = json.loads(r["body"])
        except ValueError:
            continue
        cards.append({"id": r["id"], "rating": r["rating"],
                      "flaws": body.get("flaws", []),
                      "verdict": body.get("verdict", ""),
                      "strongest": body.get("strongest", "")})
    return cards


@app.get("/rooms/{rid}/redteam")
def redteam_list(rid: str, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        return _red_cards(con, rid)
    finally:
        con.close()


@app.post("/rooms/{rid}/redteam")
async def redteam_run(rid: str, token: str, model: str = ""):
    if S.PAUSED:
        raise HTTPException(503, "engine paused")
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        card, reason = dissent.redteam_room(con, rid,
                                            model or S.SPARK_MODEL)
    finally:
        con.close()
    if card:
        body = {k: card[k] for k in ("flaws", "verdict", "strongest")}
        await _cast(rid, {"id": card["id"], "author": "redteam",
                         "kind": "redteam", "body": json.dumps(body)})
    return {"triggered": bool(card), "card": card, "reason": reason}


@app.post("/rooms/{rid}/redteam/{mid}/resolve")
async def redteam_resolve(rid: str, mid: int, token: str, verdict: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        if verdict not in ("fixed", "accepted", "dismissed"):
            raise HTTPException(400, "fixed, accepted, or dismissed")
        out = store.resolve_redteam(con, rid, mid, verdict)
        if not out:
            raise HTTPException(404, "no such attack card")
        brow = con.execute("SELECT body FROM messages WHERE id=? AND room=?",
                           (mid, rid)).fetchone()
        try:
            vtxt = str(json.loads((brow["body"] if brow else "") or "{}").get(
                "verdict", ""))[:80]
        except ValueError:
            vtxt = ""
        note = f"{me['name']} marked attack {verdict}"
        if vtxt:
            note += f": {vtxt}"
        sys_id = store.post_message(con, rid, "room", note, kind="system")
    finally:
        con.close()
    await _cast(rid, {"id": sys_id, "author": "room", "kind": "system",
                      "body": note})
    await _cast(rid, {"id": mid, "author": "redteam",
                      "kind": "redteam", "rating": 1, "body": verdict})
    return out


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
        who, why, deadline = who.strip(), why.strip(), deadline.strip()
        want = " ".join(what.split()).lower()
        same = [p for p in store.list_proposals(con, rid)
                if " ".join(p["what"].split()).lower() == want]
        if same:
            prop = same[0]
            store.update_proposal(con, rid, prop["id"], what, who, why,
                                  deadline, prop["updates"] or "",
                                  bool(prop["needs_detail"]))
            prop = store.get_proposal(con, rid, prop["id"])
        else:
            hit = store.find_similar_open(con, rid, what)
            old = store.get_proposal(con, rid, hit[1]) \
                if hit and hit[0] == "P" else None
            if old and old["state"] == "open":
                store.update_proposal(con, rid, old["id"], what, who,
                                      why, deadline, old["updates"] or "",
                                      bool(old["needs_detail"]))
                prop = store.get_proposal(con, rid, old["id"])
            else:
                ref = f"L{hit[1]}" if hit and hit[0] == "L" else ""
                prop = store.add_proposal(con, rid, what, who, why,
                                          deadline, me["name"], ref, False)
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
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        prop = store.get_proposal(con, rid, pid)
        if not prop or prop["state"] != "open":
            raise HTTPException(404, "proposal gone")
        store.settle_proposal(con, rid, pid, "dismissed", prop["what"],
                              prop["who"], prop["why"], prop["deadline"])
        note = f"{me['name']} dismissed: {prop['what']}"
        sys_id = store.post_message(con, rid, "room", note, kind="system")
    finally:
        con.close()
    await _cast(rid, {"id": sys_id, "author": "room", "kind": "system",
                      "body": note})
    await _cast(rid, {"kind": "proposal", "id": pid, "state": "dismissed"})
    return {"dismissed": pid}


@app.get("/rooms/{rid}/reminders")
def reminders_list(rid: str, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        today = remind.now_local().date().isoformat()
        rows = store.list_reminders(con, rid)
        for row in rows:
            row["flag"] = remind.flag(row.get("due_date") or "", today)
        return {"reminders": rows,
                "sched": store.room_remind_at(con, rid)}
    finally:
        con.close()


@app.post("/rooms/{rid}/reminders")
async def reminder_add(rid: str, token: str, text: str, due: str = "",
                       owner: str = ""):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        text = text.strip()
        if not text:
            raise HTTPException(400, "empty reminder")
        out = store.add_reminder(con, rid, text, due.strip(),
                                 owner.strip(), me["name"])
    finally:
        con.close()
    await _cast(rid, {"kind": "reminder"})
    return out


@app.post("/rooms/{rid}/reminders/{mid}")
async def reminder_edit(rid: str, mid: int, token: str,
                        text: str | None = None,
                        due: str | None = None,
                        owner: str | None = None,
                        done: bool | None = None):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        ok = store.update_reminder(
            con, rid, mid, (text or "").strip(),
            None if due is None else due.strip(),
            None if owner is None else owner.strip(), done)
        if not ok:
            raise HTTPException(404, "reminder gone")
    finally:
        con.close()
    await _cast(rid, {"kind": "reminder"})
    return {"updated": mid}


@app.delete("/rooms/{rid}/reminders/{mid}")
async def reminder_delete(rid: str, mid: int, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        if not store.delete_reminder(con, rid, mid):
            raise HTTPException(404, "reminder gone")
    finally:
        con.close()
    await _cast(rid, {"kind": "reminder"})
    return {"deleted": mid}


@app.post("/rooms/{rid}/remind-time")
def remind_time(rid: str, token: str, at: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        at = remind.normalize_at(at)
        if not at:
            raise HTTPException(400, "use HH:MM, 24-hour, or off")
        store.set_remind_at(con, rid, at)
        return {"sched": at}
    finally:
        con.close()


@app.post("/rooms/{rid}/remind-now")
async def remind_now(rid: str, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
    finally:
        con.close()
    return {"posted": await _maybe_remind(rid, force=True)}


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


@app.post("/rooms/{rid}/artifacts")
async def artifact_create(rid: str, token: str, title: str, body: str,
                          kind: str = "doc"):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        title, body = title.strip(), body.strip()
        if not title or not body:
            raise HTTPException(400, "title and body required")
        art = store.add_artifact(con, rid, title, kind.strip() or "doc",
                                 body, me["name"])
    finally:
        con.close()
    await _cast(rid, {"id": art["id"], "author": "room",
                      "kind": "artifact", "body": art["title"]})
    return art


@app.get("/rooms/{rid}/artifacts")
def artifact_list(rid: str, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        return store.list_artifacts(con, rid)
    finally:
        con.close()


@app.get("/rooms/{rid}/artifacts/{aid}")
def artifact_get(rid: str, aid: int, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        art = store.get_artifact(con, rid, aid)
        if not art:
            raise HTTPException(404, "no such artifact")
        return art
    finally:
        con.close()


@app.get("/rooms/{rid}/artifacts/{aid}/versions")
def artifact_versions(rid: str, aid: int, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        if not store.get_artifact(con, rid, aid):
            raise HTTPException(404, "no such artifact")
        return store.list_versions(con, rid, aid)
    finally:
        con.close()


@app.post("/rooms/{rid}/artifacts/{aid}/edit")
async def artifact_edit(rid: str, aid: int, token: str, body: str,
                        title: str = "", kind: str = ""):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        if not body.strip():
            raise HTTPException(400, "body required")
        art = store.edit_artifact(con, rid, aid, title.strip(),
                                  kind.strip(), body.strip(), me["name"])
        if not art:
            raise HTTPException(404, "no such artifact")
    finally:
        con.close()
    await _cast(rid, {"id": art["id"], "author": "room",
                      "kind": "artifact", "body": art["title"]})
    return art


async def _artifact_move(rid: str, aid: int, token: str, to: str,
                         refused: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        art = store.move_artifact(con, rid, aid, to, me["name"])
        if art is None:
            raise HTTPException(404, "no such artifact")
        if art is False:
            raise HTTPException(400, refused)
    finally:
        con.close()
    await _cast(rid, {"id": art["id"], "author": "room",
                      "kind": "artifact", "body": art["title"]})
    return art


@app.post("/rooms/{rid}/artifacts/{aid}/propose")
async def artifact_propose(rid: str, aid: int, token: str):
    return await _artifact_move(rid, aid, token, "proposed",
                                "only drafts can be proposed")


@app.post("/rooms/{rid}/artifacts/{aid}/approve")
async def artifact_approve(rid: str, aid: int, token: str):
    return await _artifact_move(rid, aid, token, "approved",
                                "propose it first")


@app.post("/rooms/{rid}/artifacts/{aid}/apply")
async def artifact_apply(rid: str, aid: int, token: str):
    return await _artifact_move(rid, aid, token, "applied",
                                "approve it first")


@app.post("/rooms/{rid}/tasks")
async def task_create(rid: str, token: str, title: str, details: str = "",
                      assignee: str = "", due: str = ""):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        if not title.strip():
            raise HTTPException(400, "title required")
        task = store.add_task(con, rid, title.strip(), details.strip(),
                              assignee.strip(), due.strip(), me["name"])
    finally:
        con.close()
    await _cast(rid, {"id": task["id"], "author": "room",
                      "kind": "task", "body": task["title"]})
    return task


@app.get("/rooms/{rid}/tasks")
def task_list(rid: str, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        today = remind.now_local().date().isoformat()
        rows = store.list_tasks(con, rid)
        for row in rows:
            row["flag"] = remind.flag(row.get("due_date") or "", today)
        return rows
    finally:
        con.close()


@app.post("/rooms/{rid}/tasks/{tid}/edit")
async def task_edit(rid: str, tid: int, token: str, title: str = "",
                    details: str = "", assignee: str = "", due: str = ""):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        task = store.edit_task(con, rid, tid, title.strip(),
                               details.strip(), assignee.strip(),
                               due.strip())
        if not task:
            raise HTTPException(404, "no such task")
    finally:
        con.close()
    await _cast(rid, {"id": task["id"], "author": "room",
                      "kind": "task", "body": task["title"]})
    return task


@app.post("/rooms/{rid}/tasks/{tid}/done")
async def task_done(rid: str, tid: int, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        task = store.set_task_done(con, rid, tid, True)
        if not task:
            raise HTTPException(404, "no such task")
    finally:
        con.close()
    await _cast(rid, {"id": task["id"], "author": "room",
                      "kind": "task", "body": task["title"]})
    return task


@app.post("/rooms/{rid}/tasks/{tid}/reopen")
async def task_reopen(rid: str, tid: int, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        task = store.set_task_done(con, rid, tid, False)
        if not task:
            raise HTTPException(404, "no such task")
    finally:
        con.close()
    await _cast(rid, {"id": task["id"], "author": "room",
                      "kind": "task", "body": task["title"]})
    return task


@app.post("/rooms/{rid}/tasks/{tid}/delete")
async def task_delete(rid: str, tid: int, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        if not store.delete_task(con, rid, tid):
            raise HTTPException(404, "no such task")
    finally:
        con.close()
    await _cast(rid, {"id": tid, "author": "room",
                      "kind": "task", "body": "deleted"})
    return {"deleted": tid}


def _poll_view(con, poll: dict, mid: str) -> dict:
    votes = store.poll_votes(con, poll["room"], poll["id"])
    tally = [0] * len(poll["options"])
    by_option: list = [[] for _ in poll["options"]]
    mine = None
    for v in votes:
        idx = v["option_idx"]
        if 0 <= idx < len(tally):
            tally[idx] += 1
            by_option[idx].append(
                f"{v['name']} ·{v['nick']}" if v["nick"] else v["name"])
        if v["member_id"] == mid:
            mine = idx
    poll["tally"] = tally
    poll["total"] = sum(tally)
    poll["by_option"] = by_option
    poll["my_vote"] = mine
    return poll


@app.post("/rooms/{rid}/polls")
async def poll_create(rid: str, token: str, question: str, options: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        try:
            opts = [o.strip()[:80] for o in json.loads(options)]
        except (ValueError, TypeError):
            raise HTTPException(400, "options must be a JSON list")
        opts = [o for o in opts if o]
        if not question.strip() or not 2 <= len(opts) <= 4:
            raise HTTPException(400, "ask 2 to 4 options")
        poll = store.add_poll(con, rid, question.strip(), opts,
                              me["name"])
    finally:
        con.close()
    await _cast(rid, {"id": poll["id"], "author": "room",
                      "kind": "poll", "body": poll["question"]})
    return poll


@app.get("/rooms/{rid}/polls")
def poll_list(rid: str, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        return [_poll_view(con, p, me["id"])
                for p in store.list_polls(con, rid)]
    finally:
        con.close()


@app.post("/rooms/{rid}/polls/{pid}/vote")
async def poll_vote(rid: str, pid: int, token: str, option: int):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        poll = store.get_poll(con, rid, pid)
        if not poll:
            raise HTTPException(404, "no such poll")
        if poll["state"] != "open":
            raise HTTPException(400, "poll closed")
        if not 0 <= option < len(poll["options"]):
            raise HTTPException(400, "no such option")
        store.vote_poll(con, rid, pid, me["id"], me["name"],
                        me["nick"] or "", option)
    finally:
        con.close()
    await _cast(rid, {"id": pid, "author": "room",
                      "kind": "poll", "body": poll["question"]})
    return {"voted": option}


@app.post("/rooms/{rid}/polls/{pid}/close")
async def poll_close(rid: str, pid: int, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        poll = store.get_poll(con, rid, pid)
        if not poll:
            raise HTTPException(404, "no such poll")
        poll = store.close_poll(con, rid, pid)
    finally:
        con.close()
    await _cast(rid, {"id": pid, "author": "room",
                      "kind": "poll", "body": poll["question"]})
    return poll


def _room_pack(con, rid: str) -> dict:
    return {
            "room": rid,
            "mission": store.room_mission(con, rid),
            "members": [
                {"name": m["name"], "nick": m["nick"], "role": m["role"]}
                for m in store.list_members(con, rid)],
            "messages": [
                {"id": m["id"], "author": m["author"],
                 "kind": m["kind"], "body": m["body"],
                 "rating": m["rating"], "created_at": m["created_at"]}
                for m in con.execute(
                    "SELECT * FROM messages WHERE room=? ORDER BY id",
                    (rid,))],
            "ledger": store.list_ledger(con, rid),
            "proposals": [
                dict(r) for r in con.execute(
                    "SELECT * FROM proposals WHERE room=? ORDER BY id",
                    (rid,))],
            "artifacts": [
                {**dict(r), "versions": store.list_versions(
                    con, rid, r["id"])}
                for r in con.execute(
                    "SELECT * FROM artifacts WHERE room=? ORDER BY id",
                    (rid,))],
            "tasks": store.list_tasks(con, rid),
            "polls": [
                _poll_view(con, {**dict(r),
                                 "options": json.loads(r["options"])}, "")
                for r in con.execute(
                    "SELECT * FROM polls WHERE room=? ORDER BY id",
                    (rid,))],
            "reminders": store.list_reminders(con, rid),
        }


@app.get("/rooms/{rid}/teammates")
def teammate_list(rid: str, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        return store.list_teammates(con, rid)
    finally:
        con.close()


@app.post("/rooms/{rid}/teammates")
def teammate_add(rid: str, token: str, name: str, role: str = "",
                 instructions: str = ""):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        if not name.strip():
            raise HTTPException(400, "name required")
        mate = store.add_teammate(con, rid, name.strip(), role.strip(),
                                  instructions.strip(), me["name"])
        if not mate:
            raise HTTPException(400, "name taken")
        return mate
    finally:
        con.close()


@app.post("/rooms/{rid}/teammates/{tid}/edit")
def teammate_edit(rid: str, tid: int, token: str, name: str = "",
                  role: str = "", instructions: str = ""):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        mate = store.edit_teammate(con, rid, tid, name.strip(),
                                   role.strip(), instructions.strip())
        if mate is None:
            raise HTTPException(404, "no such teammate")
        if mate is False:
            raise HTTPException(400, "name taken")
        return mate
    finally:
        con.close()


@app.delete("/rooms/{rid}/teammates/{tid}")
def teammate_delete(rid: str, tid: int, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        if not store.delete_teammate(con, rid, tid):
            raise HTTPException(404, "no such teammate")
        return {"removed": tid}
    finally:
        con.close()


@app.get("/rooms/{rid}/away")
def away_list(rid: str, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        return store.list_away(con, rid)
    finally:
        con.close()


@app.post("/rooms/{rid}/away")
def away_assign(rid: str, token: str, teammate: int, instruction: str,
                due: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        mate = store.get_teammate(con, rid, teammate)
        if not mate:
            raise HTTPException(404, "no such teammate")
        if not instruction.strip():
            raise HTTPException(400, "instruction required")
        if not remind.parse_due(due.strip()):
            raise HTTPException(400, "give a due date like Friday")
        return store.add_away(con, rid, mate, instruction.strip(),
                              due.strip(), me["name"], me["id"])
    finally:
        con.close()


@app.post("/rooms/{rid}/away/{aid}/delete")
def away_delete(rid: str, aid: int, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        rows = [t for t in store.list_away(con, rid) if t["id"] == aid]
        if not rows:
            raise HTTPException(404, "no such away task")
        store.delete_away(con, rid, aid)
        return {"deleted": aid}
    finally:
        con.close()


@app.get("/rooms/{rid}/export")
def room_export(rid: str, token: str, include_sides: bool = False):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        pack = _room_pack(con, rid)
        pack["exported_at"] = time.time()
        if include_sides and not store.room_parent(con, rid):
            pack["sides"] = []
            hidden = 0
            for s in store.list_sides(con, rid):
                if store.member_by_origin(con, s["room_id"], me["id"]):
                    pack["sides"].append(_room_pack(con, s["room_id"]))
                else:
                    hidden += 1
            pack["sides_hidden"] = hidden
    finally:
        con.close()
    return Response(
        content=json.dumps(pack, indent=1),
        media_type="application/json",
        headers={"Content-Disposition":
                 f"attachment; filename=room-{rid}.json"})


def _showcase_data(con, rid: str) -> dict:
    polls = []
    for row in con.execute("SELECT * FROM polls WHERE room=? ORDER BY id",
                           (rid,)):
        p = dict(row)
        p["options"] = json.loads(p["options"])
        polls.append(_poll_view(con, p, ""))
    chats = [
        {"author": m["author"], "kind": m["kind"], "body": m["body"]}
        for m in store.recent(con, rid, 50)
        if m.get("kind") in ("chat", "system", "ask", "answer")]
    return {
        "mission": store.room_mission(con, rid),
        "people": [{"name": m["name"], "nick": m["nick"],
                    "role": m["role"]}
                   for m in store.list_members(con, rid)],
        "ledger": [dict(r) for r in con.execute(
            "SELECT what, who, why, deadline FROM ledger WHERE room=?"
            " AND status='open' ORDER BY id", (rid,))],
        "artifacts": [dict(r) for r in con.execute(
            "SELECT title, kind, version, status, body FROM artifacts"
            " WHERE room=? ORDER BY id", (rid,))],
        "tasks": [dict(r) for r in con.execute(
            "SELECT title, details, assignee, due_text, status FROM tasks"
            " WHERE room=? ORDER BY id", (rid,))],
        "polls": polls,
        "redteam": _red_cards(con, rid),
        "chats": chats,
    }


@app.get("/rooms/{rid}/showcase")
def showcase_get(rid: str, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        tok = store.get_showcase(con, rid)
        return {"url": f"/show/{tok}" if tok else ""}
    finally:
        con.close()


@app.post("/rooms/{rid}/showcase")
def showcase_mint(rid: str, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        tok = store.mint_showcase(con, rid, me["name"])
        return {"url": f"/show/{tok}"}
    finally:
        con.close()


@app.delete("/rooms/{rid}/showcase")
def showcase_revoke(rid: str, token: str):
    con = _db()
    try:
        me = store.member_by_token(con, rid, token)
        if not _manage(me):
            raise HTTPException(403, "owner or operator only")
        return {"revoked": store.revoke_showcase(con, rid)}
    finally:
        con.close()


@app.get("/show/{token}", response_class=HTMLResponse)
def showcase_view(token: str):
    con = _db()
    try:
        rid = store.room_by_showcase(con, token)
        if not rid:
            raise HTTPException(404, "no such showcase")
        return ui.showcase_page(_showcase_data(con, rid))
    finally:
        con.close()


@app.get("/rooms/{rid}/memory")
def memory_keys(rid: str, token: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        return memory.keys(con, rid)
    finally:
        con.close()


@app.delete("/rooms/{rid}/memory")
def memory_forget(rid: str, token: str, key: str):
    con = _db()
    try:
        if not store.member_by_token(con, rid, token):
            raise HTTPException(403, "bad token")
        gone = memory.forget(con, rid, key)
        return {"forgotten": key.strip().lower()[:80], "removed": gone}
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
        me = store.member_by_token(con, rid, token)
        if not me:
            raise HTTPException(403, "bad token")
        if store.room_locked(con, rid):
            raise HTTPException(403, "room locked")
        try:
            out = store.rate_message(con, rid, mid, up)
        except LookupError:
            raise HTTPException(404, "no such message")
        except ValueError as e:
            raise HTTPException(400, str(e))
        row = con.execute("SELECT kind, body FROM messages WHERE id=? AND room=?",
                          (mid, rid)).fetchone()
        is_card = bool(row and row["kind"] == "dissent")
        note, sys_id = "", 0
        if is_card:
            try:
                q = str(json.loads(row["body"] or "{}").get("question",
                                                            ""))[:80]
            except ValueError:
                q = ""
            word = "fair catch" if up else "false alarm"
            note = f"{me['name']} closed dissent as {word}"
            if q:
                note += f": {q}"
            sys_id = store.post_message(con, rid, "room", note,
                                        kind="system")
    finally:
        con.close()
    if is_card and note:
        await _cast(rid, {"id": sys_id, "author": "room", "kind": "system",
                          "body": note})
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
    lock = _exam_locks.setdefault(rid, threading.Lock())
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "exam already running")
    try:
        return _eval_exam_locked(rid, token, model)
    finally:
        lock.release()


def _eval_exam_locked(rid: str, token: str, model: str = ""):
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
        if store.room_parent(con, rid):
            raise HTTPException(400, "side rooms seat from the main room")
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
        row = con.execute("SELECT value FROM memory WHERE room=? AND key=?",
                          (rid, "dissent_muted")).fetchone()
        lrow = con.execute("SELECT value FROM memory WHERE room=? AND key=?",
                           (rid, "dissent_last_run")).fetchone()
        judge_last = None
        if lrow:
            try:
                judge_last = json.loads(lrow["value"])
            except ValueError:
                judge_last = None
        return {"locked": store.room_locked(con, rid),
                "model": me["model"] or "",
                "default": S.SPARK_MODEL,
                "dissent_muted": bool(row and row["value"] == "1"),
                "judge_last": judge_last}
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
                              "tag": tag, "badge": badge, "body": text,
                              "author_id": me["id"]})
            _spawn_judge(rid, S.SPARK_MODEL)
            if "@" in text and not S.PAUSED:
                con2 = _db()
                try:
                    mate, question = _find_mention(
                        text, store.list_teammates(con2, rid))
                    model_name = S.SPARK_MODEL
                    iid = 0
                    if mate:
                        fresh = store.member_by_token(con2, rid, token)
                        if fresh and fresh["model"]:
                            model_name = fresh["model"]
                        if not question:
                            intro = (f"I'm {mate['name']}, {mate['role']}."
                                     " Mention me with a question.")
                            iid = store.post_message(
                                con2, rid, mate["name"], intro,
                                kind="answer", model=model_name)
                finally:
                    con2.close()
                if mate and not question:
                    await _cast(rid, {"id": iid, "author": mate["name"],
                                      "kind": "answer", "body": intro})
                elif mate:
                    asyncio.get_running_loop().create_task(
                        _teammate_later(rid, mate, question, model_name))
            await _maybe_remind(rid)
    except WebSocketDisconnect:
        _live[rid].discard(ws)
        _live_who.pop(ws, None)
