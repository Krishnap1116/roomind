"""Step 3 slice: dissent engine + decision ledger. No network calls."""
import asyncio
import json
import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import roomind.dissent as dissent
import roomind.memory as memory
import roomind.store as store
import roomind.web as web
import roomind as S

CARD = {"fire": True, "confidence": "high", "hats": ["deploy"],
        "source": "memory",
        "points": [{"flaw": "no date", "receipt": "Ana: ship Friday"}],
        "question": "Who ships it?"}
SILENT = {"fire": False, "points": [], "question": ""}


@pytest.fixture()
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    monkeypatch.setattr(S, "DB", p)
    monkeypatch.setattr(S, "PAUSED", False)
    return p


@pytest.fixture()
def client(db):
    return TestClient(web.app)


def _room(client, name="Ana"):
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    tok = client.post(f"/rooms/{rid}/join",
                      params={"name": name, "invite": inv}).json()["token"]
    return rid, tok


def test_watch_triggers_and_objection_silences(db):
    con = store.connect()
    store.post_message(con, "r", "Ana", "Should we ship Friday morning?")
    store.post_message(con, "r", "Ben", "yes ship it")
    store.post_message(con, "r", "Ana", "yes lets do it")
    hit = dissent.watch(store.recent(con, "r"))
    assert hit and hit["agreers"] == ["Ana", "Ben"]
    store.post_message(con, "r", "Ben", "wait, what about tests?")
    assert dissent.watch(store.recent(con, "r")) is None
    con.close()


def test_cooldown_and_mute_block(db, monkeypatch):
    con = store.connect()
    store.post_message(con, "r", "Ana", "Should we ship Friday morning?")
    store.post_message(con, "r", "Ben", "yes ship it")
    store.post_message(con, "r", "Ana", "yes lets do it")
    memory.remember(con, "r", "last_dissent_mid", "9999")
    assert dissent.maybe_fire(con, "r", "m") is None
    memory.forget(con, "r", "last_dissent_mid")
    memory.remember(con, "r", "dissent_muted", "1")
    assert dissent.maybe_fire(con, "r", "m") is None
    con.close()


def test_check_posts_card_and_ledger_roundtrip(client, monkeypatch):
    def fake(api_key, base, model, history, prompt, timeout=60.0, notes=None):
        return {"answer": json.dumps(CARD), "reasons": [], "remember": [],
                "tin": 1, "tout": 1}

    monkeypatch.setattr(web.meta, "spark_reply", fake)
    rid, tok = _room(client)
    con = store.connect()
    store.post_message(con, rid, "Ana", "Should we leave Friday morning?")
    store.post_message(con, rid, "Ben", "yes")
    store.post_message(con, rid, "Ana", "yes lets do it")
    con.close()
    r0 = client.post(f"/rooms/{rid}/dissent/check", params={"token": tok})
    assert r0.json()["triggered"] is False  # first signal arms silently
    con = store.connect()
    store.post_message(con, rid, "Ben", "still yes")
    con.close()
    r = client.post(f"/rooms/{rid}/dissent/check", params={"token": tok})
    assert r.json()["triggered"] is True  # second signal fires
    msgs = client.get(f"/rooms/{rid}/messages",
                      params={"token": tok}).json()
    assert msgs[-1]["kind"] == "dissent"
    r2 = client.post(f"/rooms/{rid}/dissent/check", params={"token": tok})
    assert r2.json()["triggered"] is False  # cooldown holds
    led = client.post(f"/rooms/{rid}/ledger",
                      params={"token": tok, "what": "Ship Friday",
                              "who": "Ana", "why": "client waits"}).json()
    assert led["id"] >= 1
    rows = client.get(f"/rooms/{rid}/ledger", params={"token": tok}).json()
    assert rows[0]["what"] == "Ship Friday"


def test_ask_autofires_card(client, monkeypatch):
    def fake(api_key, base, model, history, prompt, timeout=60.0, notes=None):
        if "ROOM JUDGE" in prompt:
            return {"answer": json.dumps(CARD), "reasons": [],
                    "remember": [], "tin": 1, "tout": 1}
        return {"answer": "noted", "reasons": ["r"], "remember": [],
                "tin": 1, "tout": 1}

    monkeypatch.setattr(web.meta, "spark_reply", fake)
    monkeypatch.setattr(web.agent, "run_loop",
                        lambda *a, **k: {"answer": "noted",
                                         "reasons": ["r"], "remember": [],
                                         "calls": [{"tin": 1, "tout": 1}],
                                         "searched": False})
    rid, tok = _room(client)
    con = store.connect()
    store.post_message(con, rid, "Ana", "Ship it Friday")
    con.close()
    r = client.post(f"/rooms/{rid}/ask",
                    params={"token": tok, "text": "any thoughts?"})
    assert r.json()["answer"] == "noted"  # reply out first
    cards = []
    deadline = time.time() + 5
    while time.time() < deadline:  # judge follows async now
        msgs = client.get(f"/rooms/{rid}/messages",
                          params={"token": tok}).json()
        cards = [json.loads(m["body"]) for m in msgs
                 if m["kind"] == "dissent"]
        if cards:
            break
        time.sleep(0.05)
    assert cards and cards[-1]["question"] == "Who ships it?"


def test_live_socket_broadcasts(client, monkeypatch):
    def fake(api_key, base, model, history, prompt, timeout=60.0, notes=None):
        return {"answer": json.dumps(SILENT), "reasons": [], "remember": [],
                "tin": 1, "tout": 1}

    monkeypatch.setattr(web.meta, "spark_reply", fake)
    rid, tok = _room(client)
    with client.websocket_connect(f"/rooms/{rid}/live?token={tok}") as ws:
        ws.send_text("hello room")
        msg = ws.receive_json()
        assert msg["author"] == "Ana" and msg["body"] == "hello room"


def test_chat_broadcasts_before_judge_card(client, monkeypatch):
    card = {"id": 7, "points": [], "question": "q?", "conflict": None,
            "hats": [], "source": "thread"}
    monkeypatch.setattr(web.dissent, "judge_room",
                        lambda con, rid, model: (card, None))
    rid, tok = _room(client)
    with client.websocket_connect(f"/rooms/{rid}/live?token={tok}") as ws:
        ws.send_text("hello")
        first = ws.receive_json()
        second = ws.receive_json()
        assert first["body"] == "hello" and "kind" not in first
        assert second["kind"] == "dissent"


def test_chat_stays_instant_while_judge_blocked(client, monkeypatch):
    started = threading.Event()
    release = threading.Event()
    card = {"id": 9, "points": [], "question": "q?", "conflict": None,
            "hats": [], "source": "thread"}

    def slow(con, rid, model):
        started.set()
        assert release.wait(timeout=10)
        return card

    monkeypatch.setattr(web.dissent, "judge_room",
                        lambda con, rid, model: (slow(con, rid, model),
                                                 None))
    rid, tok = _room(client)
    with client.websocket_connect(f"/rooms/{rid}/live?token={tok}") as ws:
        try:
            ws.send_text("first")
            first = ws.receive_json()
            assert first["body"] == "first" and "kind" not in first
            assert started.wait(timeout=5)  # monitor is mid-run
            box: queue.Queue = queue.Queue()

            def recv_second():
                try:
                    box.put(ws.receive_json())
                except Exception as exc:  # noqa: BLE001 - surfaced below
                    box.put(exc)

            worker = threading.Thread(target=recv_second, daemon=True)
            worker.start()
            ws.send_text("second")
            second = box.get(timeout=5)  # lands while judge still blocked
            assert not isinstance(second, Exception)
            assert second["body"] == "second" and "kind" not in second
        finally:
            release.set()


def test_cursor_skips_reread(db, monkeypatch):
    calls = []

    def fake(*a, **k):
        calls.append(1)
        return {"answer": json.dumps(SILENT), "reasons": [],
                "remember": [], "tin": 1, "tout": 1}

    monkeypatch.setattr(dissent.meta, "spark_reply", fake)
    con = store.connect()
    con.execute("INSERT INTO rooms (id, mission) VALUES ('r', 'm')")
    store.post_message(con, "r", "Ana", "hello world there")
    assert dissent.judge_room(con, "r", "m") == (None, None)
    assert dissent.judge_room(con, "r", "m") == (None, None)
    assert len(calls) == 1  # second read finds nothing new, no call
    store.post_message(con, "r", "Ana", "one more line here")
    dissent.judge_room(con, "r", "m")
    assert len(calls) == 2
    con.close()


def test_second_card_queues_until_first_rated(client, monkeypatch):
    monkeypatch.setattr(web.meta, "spark_reply",
                        lambda *a, **k: {"answer": json.dumps(CARD),
                                         "reasons": [], "remember": [],
                                         "tin": 1, "tout": 1})
    rid, tok = _room(client)
    con = store.connect()
    store.post_message(con, rid, "Ana", "Ship it Friday, no review")
    con.close()
    first = client.post(f"/rooms/{rid}/dissent/check",
                        params={"token": tok}).json()
    assert first["triggered"] is True
    con = store.connect()
    for i in range(8):
        store.post_message(con, rid, "Ana", f"filler note {i}")
    store.post_message(con, rid, "Ana", "Ship it Monday, no review")
    con.close()
    second = client.post(f"/rooms/{rid}/dissent/check",
                         params={"token": tok}).json()
    assert second["triggered"] is False  # queued behind the open card
    con = store.connect()
    queued = dissent._read_queue(con, rid)
    con.close()
    assert len(queued) == 1
    seen = []

    class Fake:
        async def send_json(self, p):
            seen.append(p)

    web._live[rid] = {Fake()}
    try:
        msgs = client.get(f"/rooms/{rid}/messages",
                          params={"token": tok}).json()
        aid = [m for m in msgs if m["kind"] == "dissent"][0]["id"]
        client.post(f"/rooms/{rid}/messages/{aid}/rate",
                    params={"token": tok, "up": True})
    finally:
        web._live.pop(rid, None)
    assert [p["kind"] for p in seen] == ["dissent"]  # next pops live
    msgs = client.get(f"/rooms/{rid}/messages",
                      params={"token": tok}).json()
    cards = [m for m in msgs if m["kind"] == "dissent"]
    assert [c["rating"] for c in cards] == [1, 0]


def test_card_queue_keeps_all(db):
    con = store.connect()
    for i in range(25):
        dissent.queue_card(con, "r", {"question": f"q{i}"})
    q = dissent._read_queue(con, "r")
    assert len(q) == 25 and q[0]["question"] == "q0"
    con.close()


def _seed_card(con, rid, question):
    return {"points": [], "question": question, "conflict": None,
            "hats": [], "source": "thread"}


def test_pop_skips_stale_card(client, monkeypatch):
    def fake(*a, **k):
        fresh = "stale claim" not in a[4].lower()
        return {"answer": json.dumps({"still_true": fresh})}

    monkeypatch.setattr(web.meta, "spark_reply", fake)
    rid, tok = _room(client)
    con = store.connect()
    store.post_message(con, rid, "Ana", "hello world there")
    aid = store.post_message(con, rid, "dissent",
                             json.dumps(_seed_card(con, rid, "open one")),
                             kind="dissent")
    dissent.queue_card(con, rid, _seed_card(con, rid, "stale claim here"))
    dissent.queue_card(con, rid, _seed_card(con, rid, "fresh claim here"))
    con.close()
    seen = []

    class Fake:
        async def send_json(self, p):
            seen.append(p)

    web._live[rid] = {Fake()}
    try:
        client.post(f"/rooms/{rid}/messages/{aid}/rate",
                    params={"token": tok, "up": True})
    finally:
        web._live.pop(rid, None)
    assert len(seen) == 1
    assert json.loads(seen[0]["body"])["question"] == "fresh claim here"
    con = store.connect()
    assert dissent._read_queue(con, rid) == []
    con.close()


def test_pop_fail_open_on_model_error(client, monkeypatch):
    def boom(*a, **k):
        raise ValueError("down")

    monkeypatch.setattr(web.meta, "spark_reply", boom)
    rid, tok = _room(client)
    con = store.connect()
    aid = store.post_message(con, rid, "dissent",
                             json.dumps(_seed_card(con, rid, "open one")),
                             kind="dissent")
    dissent.queue_card(con, rid, _seed_card(con, rid, "queued one"))
    con.close()
    client.post(f"/rooms/{rid}/messages/{aid}/rate",
                params={"token": tok, "up": False})
    msgs = client.get(f"/rooms/{rid}/messages",
                      params={"token": tok}).json()
    assert len([m for m in msgs if m["kind"] == "dissent"]) == 2


def test_rated_cards_hidden_on_page(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    page = client.get(f"/rooms/{j['room_id']}/app",
                      params={"token": j["token"]}).text
    assert "if(!m.rating)showDissent(m,box2);" in page


def test_judge_debounce_restarts(monkeypatch):
    monkeypatch.setattr(S, "JUDGE_IDLE_S", 60.0)
    monkeypatch.setattr(S, "JUDGE_MAXWAIT_S", 60.0)

    async def go():
        web._spawn_judge("r", "m")
        first = web._judge_pending["r"]
        web._spawn_judge("r", "m")
        second = web._judge_pending["r"]
        assert second is not first
        assert first.cancelling() >= 1
        second.cancel()
        try:
            await second
        except asyncio.CancelledError:
            pass
        web._judge_pending.pop("r", None)
        web._judge_first.pop("r", None)

    asyncio.run(go())


def test_judge_maxwait_runs_now(monkeypatch):
    monkeypatch.setattr(S, "JUDGE_IDLE_S", 60.0)
    monkeypatch.setattr(S, "JUDGE_MAXWAIT_S", 0.0)
    ran = []

    async def fake_later(rid, model):
        ran.append(rid)

    monkeypatch.setattr(web, "_judge_later", fake_later)

    async def go():
        web._spawn_judge("r", "m")
        await asyncio.sleep(0.05)

    asyncio.run(go())
    assert ran == ["r"]
    assert "r" not in web._judge_pending


def test_veto_silences_without_model(db, monkeypatch):
    def boom(h, p):
        raise AssertionError("model must not wake")

    assert dissent.vetoed("what if we delete it all?")
    assert dissent.vetoed("lol ship it")
    assert not dissent.vetoed("We ship Friday with no review step")
    con = store.connect()
    store.post_message(con, "r", "Ana", "what if we delete it all?")
    assert dissent.maybe_fire(con, "r", "m") is None
    con.close()
    assert dissent.judge_line(boom, [], "m", {}, [])["fire"] is False


def test_judge_fires_only_on_evidence_and_wires_context(db, monkeypatch):
    seen = {}

    def fake(api_key, base, model, history, prompt, timeout=60.0, notes=None):
        seen["prompt"] = prompt
        return {"answer": json.dumps(SILENT), "reasons": [],
                "remember": [], "tin": 1, "tout": 1}

    monkeypatch.setattr(dissent.meta, "spark_reply", fake)
    con = store.connect()
    con.execute("INSERT INTO rooms (id, mission) VALUES ('r', 'Safe ships')")
    memory.remember(con, "r", "deploy rule", "Ravi reviews all deploys")
    memory.remember(con, "r", "freeze", "starts Monday")
    import time as _t
    con.execute("UPDATE memory SET updated_at=? WHERE room='r' AND key='freeze'",
                (_t.time() - 10 * 86400,))
    con.commit()
    store.add_ledger(con, "r", "Ship Friday", "Ana", "client waits",
                     "Friday")
    store.post_message(con, "r", "Ana", "We ship Friday with no review")
    assert dissent.maybe_fire(con, "r", "m") is None  # judge said silent
    assert "Safe ships" in seen["prompt"]
    assert "Ravi reviews all deploys" in seen["prompt"]
    assert "all deploys;" in seen["prompt"]  # fresh fact wears no label
    assert "starts Monday [10 days old]" in seen["prompt"]
    assert "checkable claims" in seen["prompt"]
    assert "never fire on an old fact alone" in seen["prompt"]
    con.close()


def test_severe_plus_evidence_fires_at_once(client, monkeypatch):
    def fake(api_key, base, model, history, prompt, timeout=60.0, notes=None):
        return {"answer": json.dumps(CARD), "reasons": [], "remember": [],
                "tin": 1, "tout": 1}

    monkeypatch.setattr(web.meta, "spark_reply", fake)
    rid, tok = _room(client)
    con = store.connect()
    store.post_message(con, rid, "Ana", "Ship it Friday, no review")
    con.close()
    r = client.post(f"/rooms/{rid}/dissent/check", params={"token": tok})
    assert r.json()["triggered"] is True  # severe skips the arm wait


def test_arm_expires_after_eight_messages(client, monkeypatch):
    def fake(api_key, base, model, history, prompt, timeout=60.0, notes=None):
        return {"answer": json.dumps(CARD), "reasons": [], "remember": [],
                "tin": 1, "tout": 1}

    monkeypatch.setattr(web.meta, "spark_reply", fake)
    rid, tok = _room(client)
    con = store.connect()
    store.post_message(con, rid, "Ana", "plain claim one")
    con.close()
    r0 = client.post(f"/rooms/{rid}/dissent/check", params={"token": tok})
    assert r0.json()["triggered"] is False
    con = store.connect()
    for i in range(8):
        store.post_message(con, rid, "Ana", f"filler line {i}")
    con.close()
    r1 = client.post(f"/rooms/{rid}/dissent/check", params={"token": tok})
    assert r1.json()["triggered"] is False  # stale arm, re-arms instead


def test_judge_orders_cover_thin_verdicts_and_drift():
    assert "verdict without thought" in dissent.JUDGE_PROMPT
    assert "ignores the mission" in dissent.JUDGE_PROMPT
    assert "Fast agreement with reasons is silence" in dissent.JUDGE_PROMPT
    assert "up to 3 hats" in dissent.JUDGE_PROMPT
    assert "confidence" in dissent.JUDGE_PROMPT


def test_low_confidence_arms_but_never_fires(client, monkeypatch):
    low = dict(CARD, confidence="low")

    def fake(api_key, base, model, history, prompt, timeout=60.0, notes=None):
        return {"answer": json.dumps(low), "reasons": [], "remember": [],
                "tin": 1, "tout": 1}

    monkeypatch.setattr(web.meta, "spark_reply", fake)
    rid, tok = _room(client)
    con = store.connect()
    store.post_message(con, rid, "Ana", "Ship it Friday, no review")
    con.close()
    r0 = client.post(f"/rooms/{rid}/dissent/check", params={"token": tok})
    assert r0.json()["triggered"] is False  # severe but unsure: arm only
    con = store.connect()
    store.post_message(con, rid, "Ana", "Delete the backups too")
    con.close()
    r1 = client.post(f"/rooms/{rid}/dissent/check", params={"token": tok})
    assert r1.json()["triggered"] is False  # unsure twice: still silent
    assert store.connect().execute(
        "SELECT value FROM memory WHERE room=? AND key='dissent_armed'",
        (rid,)).fetchone() is not None


def test_hats_and_source_ride_card_and_face(client, monkeypatch):
    def fake(api_key, base, model, history, prompt, timeout=60.0, notes=None):
        return {"answer": json.dumps(CARD), "reasons": [], "remember": [],
                "tin": 1, "tout": 1}

    monkeypatch.setattr(web.meta, "spark_reply", fake)
    rid, tok = _room(client)
    con = store.connect()
    store.post_message(con, rid, "Ana", "Ship it Friday, no review")
    con.close()
    client.post(f"/rooms/{rid}/dissent/check", params={"token": tok})
    body = store.connect().execute(
        "SELECT body FROM messages WHERE kind='dissent'").fetchone()[0]
    card = json.loads(body)
    assert card["hats"] == ["deploy"] and card["source"] == "memory"
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": tok}).text
    assert "Hats: '" in page and "From: '" in page


def test_severe_word_bounds():
    assert dissent.severe("Ship it Friday")
    assert dissent.severe("we are shipping now")
    assert not dissent.severe("our relationship is fine")
    assert not dissent.severe("yes lets do it")


CONFLICT_CARD = {"fire": True, "confidence": "high",
                 "hats": ["planning"], "source": "memory",
                 "points": [{"flaw": "date clash",
                             "receipt": "Ana: ship Sunday"}],
                 "question": "Which freeze date is current?",
                 "conflict": {"key": "freeze", "memory_says": "Monday",
                              "room_says": "Sunday"}}


def test_conflict_rides_card_and_fix_repairs(db, monkeypatch):
    def fake(api_key, base, model, history, prompt, timeout=60.0, notes=None):
        return {"answer": json.dumps(CONFLICT_CARD), "reasons": [],
                "remember": [], "tin": 1, "tout": 1}

    monkeypatch.setattr(dissent.meta, "spark_reply", fake)
    con = store.connect()
    con.execute("INSERT INTO rooms (id, mission) VALUES ('r', 'm')")
    memory.remember(con, "r", "freeze", "Monday")
    store.post_message(con, "r", "Ana", "Ship it Sunday, freeze moved")
    card = dissent.maybe_fire(con, "r", "m")
    assert card["conflict"] == CONFLICT_CARD["conflict"]
    body = con.execute("SELECT body FROM messages WHERE kind='dissent'"
                       ).fetchone()[0]
    assert json.loads(body)["conflict"]["key"] == "freeze"
    con.close()


def test_fix_door_manager_only_and_blank_rejected(client):
    rid, otok = _room(client)
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    mtok = client.post(f"/rooms/{rid}/join",
                       params={"name": "G",
                               "invite": team}).json()["token"]
    assert client.post(f"/rooms/{rid}/memory/fix",
                       params={"token": mtok, "key": "freeze",
                               "value": "Sunday"}).status_code == 403
    assert client.post(f"/rooms/{rid}/memory/fix",
                       params={"token": otok, "key": " ",
                               "value": "Sunday"}).status_code == 400
    assert client.post(f"/rooms/{rid}/memory/fix",
                       params={"token": otok, "key": "Freeze",
                               "value": "Sunday"}).json() == {
                                   "fixed": "freeze"}
    val = store.connect().execute(
        "SELECT value FROM memory WHERE room=? AND key='freeze'",
        (rid,)).fetchone()[0]
    assert val == "Sunday"


def test_card_face_wiring(client):
    rid, otok = _room(client)
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    assert "showDissent(m,box2)" in page  # cards arrive live now
    assert "memory/fix" in page
    assert "Room is right" in page
    assert "Fair catch" in page and "False alarm" in page
    assert "ISMANAGE" in page  # fix button hides for guests


def test_verdicts_tighten_and_floor_holds(client, monkeypatch):
    def fake(api_key, base, model, history, prompt, timeout=60.0, notes=None):
        return {"answer": json.dumps(CARD), "reasons": [], "remember": [],
                "tin": 1, "tout": 1}

    monkeypatch.setattr(web.meta, "spark_reply", fake)
    rid, otok = _room(client)
    con = store.connect()
    ids = [store.post_message(con, rid, "dissent", "{}", kind="dissent")
           for _ in range(3)]
    con.close()
    for mid in ids:
        client.post(f"/rooms/{rid}/messages/{mid}/rate",
                    params={"token": otok, "up": False})
    assert store.room_strict(store.connect(), rid) is True
    con = store.connect()
    store.post_message(con, rid, "Ana", "plain claim one")
    con.close()
    r0 = client.post(f"/rooms/{rid}/dissent/check", params={"token": otok})
    assert r0.json()["triggered"] is False
    con = store.connect()
    for i in range(5):
        store.post_message(con, rid, "Ana", f"filler line {i}")
    store.post_message(con, rid, "Ana", "still plain")
    con.close()
    r1 = client.post(f"/rooms/{rid}/dissent/check", params={"token": otok})
    assert r1.json()["triggered"] is False  # strict window: 6 >= 4
    con = store.connect()
    store.post_message(con, rid, "Ana", "Ship it now")
    con.close()
    r2 = client.post(f"/rooms/{rid}/dissent/check", params={"token": otok})
    assert r2.json()["triggered"] is True  # floor: severe always speaks
