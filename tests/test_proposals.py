"""Editable stamps: judge hears decisions, humans confirm. No network."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import roomind.dissent as dissent
import roomind.store as store
import roomind.web as web
import roomind as S


@pytest.fixture()
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    monkeypatch.setattr(S, "DB", p)
    monkeypatch.setattr(S, "PAUSED", False)
    return p


@pytest.fixture()
def client(db):
    return TestClient(web.app)


DEC = {"what": "Ship Friday", "who": "Ana", "why": "client waits",
       "deadline": "Fri"}


def _room(client, name="Ana"):
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    tok = client.post(f"/rooms/{rid}/join",
                      params={"name": name, "invite": inv}).json()["token"]
    return rid, tok


def _judge_fake(payload):
    def fake(*a, **k):
        return {"answer": json.dumps(payload), "reasons": [],
                "remember": [], "tin": 1, "tout": 1}

    return fake


SILENT_DEC = {"fire": False, "confidence": "low", "hats": [],
              "source": "thread", "points": [], "question": "",
              "decision": DEC}


def test_decision_rides_silent_verdict_without_dupes(db, monkeypatch):
    monkeypatch.setattr(dissent.meta, "spark_reply",
                        _judge_fake(SILENT_DEC))
    con = store.connect()
    con.execute("INSERT INTO rooms (id, mission) VALUES ('r', 'm')")
    store.post_message(con, "r", "Ana", "Lets ship Friday, I own it")
    card, prop = dissent.judge_room(con, "r", "m")
    assert card is None and prop["what"] == "Ship Friday"
    assert prop["who"] == "Ana" and prop["proposed_by"] == "Ana"
    store.post_message(con, "r", "Ana", "Yes Friday it is")
    card2, prop2 = dissent.judge_room(con, "r", "m")
    assert (card2, prop2) == (None, None)  # same decision, no duplicate
    con.close()


def test_card_and_proposal_together(db, monkeypatch):
    card = {"fire": True, "confidence": "high", "hats": ["deploy"],
            "source": "thread",
            "points": [{"flaw": "no review", "receipt": "Ana: ship it"}],
            "question": "Who reviews?", "decision": DEC}
    monkeypatch.setattr(dissent.meta, "spark_reply", _judge_fake(card))
    con = store.connect()
    con.execute("INSERT INTO rooms (id, mission) VALUES ('r', 'm')")
    store.post_message(con, "r", "Ana", "Ship it Friday, no review")
    fired, prop = dissent.judge_room(con, "r", "m")
    assert fired["question"] == "Who reviews?"
    assert prop["what"] == "Ship Friday"
    con.close()


def test_proposal_doors_confirm_edit_dismiss(client, monkeypatch):
    monkeypatch.setattr(dissent.meta, "spark_reply",
                        _judge_fake(SILENT_DEC))
    rid, tok = _room(client)
    con = store.connect()
    store.post_message(con, rid, "Ana", "Lets ship Friday, I own it")
    con.close()
    r = client.post(f"/rooms/{rid}/dissent/check", params={"token": tok})
    assert r.json()["triggered"] is False
    assert r.json()["proposal"]["what"] == "Ship Friday"
    props = client.get(f"/rooms/{rid}/proposals",
                       params={"token": tok}).json()
    assert len(props) == 1
    pid = props[0]["id"]
    assert client.get(f"/rooms/{rid}/proposals",
                      params={"token": "nope"}).status_code == 403
    c = client.post(f"/rooms/{rid}/proposals/{pid}/confirm",
                    params={"token": tok, "what": "Ship Saturday",
                            "who": "Ben"}).json()
    assert c == {"stamped": pid, "updated": None}
    led = client.get(f"/rooms/{rid}/ledger", params={"token": tok}).json()
    assert (led[0]["what"], led[0]["who"]) == ("Ship Saturday", "Ben")
    assert led[0]["why"] == "client waits"  # untouched fields ride along
    msgs = client.get(f"/rooms/{rid}/messages",
                      params={"token": tok}).json()
    assert msgs[-1]["kind"] == "system" and "stamped" in msgs[-1]["body"]
    assert client.get(f"/rooms/{rid}/proposals",
                      params={"token": tok}).json() == []
    assert client.post(f"/rooms/{rid}/proposals/{pid}/confirm",
                       params={"token": tok}).status_code == 404
    con = store.connect()
    dpid = store.add_proposal(con, rid, "Drop IE", "Ana", "stats", "")["id"]
    con.close()
    assert client.post(f"/rooms/{rid}/proposals/{dpid}/dismiss",
                       params={"token": tok}).json() == {"dismissed": dpid}
    assert client.get(f"/rooms/{rid}/proposals",
                      params={"token": tok}).json() == []
    con = store.connect()
    bpid = store.add_proposal(con, rid, "  ")["id"]
    con.close()
    assert client.post(f"/rooms/{rid}/proposals/{bpid}/confirm",
                       params={"token": tok}).status_code == 400


def test_manual_propose_door(client):
    rid, tok = _room(client)
    p = client.post(f"/rooms/{rid}/proposals",
                    params={"token": tok, "what": "Ship Monday",
                            "who": "Ben", "why": "rest", "deadline": "Mon"}
                    ).json()
    assert p["what"] == "Ship Monday" and p["state"] == "open"
    assert p["proposed_by"] == "Ana"
    assert client.post(f"/rooms/{rid}/proposals",
                       params={"token": tok, "what": "   "}
                       ).status_code == 400
    assert client.post(f"/rooms/{rid}/proposals",
                       params={"token": "nope", "what": "x"}
                       ).status_code == 403


def test_judge_broadcasts_proposal(client, monkeypatch):
    prop = {"id": 3, "room": "r", "what": "Ship Friday", "who": "Ana",
            "why": "x", "deadline": "", "proposed_by": "Ana",
            "state": "open"}
    monkeypatch.setattr(web.dissent, "judge_room",
                        lambda con, rid, model: (None, prop))
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid = j["room_id"]
    seen = []

    class Fake:
        async def send_json(self, p):
            seen.append(p)

    web._live[rid] = {Fake()}
    try:
        asyncio.run(web._judge_later(rid, "m"))
    finally:
        web._live.pop(rid, None)
    assert [p["kind"] for p in seen] == ["proposal"]
    assert json.loads(seen[0]["body"])["what"] == "Ship Friday"


def test_proposal_face_wiring(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    page = client.get(f"/rooms/{j['room_id']}/app",
                      params={"token": j["token"]}).text
    assert "id=props" in page and "propList()" in page
    assert "propHTML" in page and "propEdit" in page
    assert "propConfirm" in page and "propDismiss" in page
    assert "Stamp it" in page
    assert "propNew" in page and "propCreate" in page
    assert "Propose it" in page
    assert "if(m.kind==='proposal'){propList();return;}" in page
    assert page.index("id=side") < page.index("id=props")  # cards below chat
    assert "Updates: " in page and "edit to sharpen" in page


def test_changed_decision_replaces_open_proposal(db, monkeypatch):
    v1 = dict(SILENT_DEC, decision=dict(DEC))
    v2 = dict(SILENT_DEC, decision={"what": "Ship Saturday", "who": "Ben",
                                    "why": "client waits", "deadline": "Sat",
                                    "updates": "", "needs_detail": False})
    calls = []

    def fake(*a, **k):
        calls.append(1)
        return {"answer": json.dumps(v1 if len(calls) == 1 else v2),
                "reasons": [], "remember": [], "tin": 1, "tout": 1}

    monkeypatch.setattr(dissent.meta, "spark_reply", fake)
    con = store.connect()
    con.execute("INSERT INTO rooms (id, mission) VALUES ('r', 'm')")
    store.post_message(con, "r", "Ana", "Lets ship Friday")
    _, p1 = dissent.judge_room(con, "r", "m")
    v2["decision"]["updates"] = f"P{p1['id']}"
    store.post_message(con, "r", "Ana", "Actually Saturday, Ben owns it")
    _, p2 = dissent.judge_room(con, "r", "m")
    assert p1["id"] == p2["id"]  # replaced, not doubled
    assert p2["what"] == "Ship Saturday" and p2["who"] == "Ben"
    assert len(store.list_proposals(con, "r")) == 1
    con.close()


def test_paraphrase_links_without_judge_help(db, monkeypatch):
    old = ("finish AI automation that makes the posts and post the posts"
           " in instagram, facebook, you tube")
    new = ("K does everything for AI automation for"
           " Instagram/Facebook/YouTube posts")
    v = dict(SILENT_DEC, decision={"what": new, "who": "K", "why": "",
                                   "deadline": "", "updates": "",
                                   "needs_detail": False})
    monkeypatch.setattr(dissent.meta, "spark_reply", _judge_fake(v))
    con = store.connect()
    con.execute("INSERT INTO rooms (id, mission) VALUES ('r', 'm')")
    lid = store.add_ledger(con, "r", old, "K, Z", "", "tomorrow")["id"]
    store.post_message(con, "r", "Ana", "K takes the whole automation")
    _, prop = dissent.judge_room(con, "r", "m")
    assert prop["updates"] == f"L{lid}"
    listed = store.list_proposals(con, "r")[0]
    assert listed["updates_what"] == old
    con.close()


def test_short_lines_stay_separate(db, monkeypatch):
    v = dict(SILENT_DEC, decision={"what": "Ship Saturday", "who": "Ben",
                                   "why": "", "deadline": "",
                                   "updates": "", "needs_detail": False})
    monkeypatch.setattr(dissent.meta, "spark_reply", _judge_fake(v))
    con = store.connect()
    con.execute("INSERT INTO rooms (id, mission) VALUES ('r', 'm')")
    store.add_ledger(con, "r", "Ship Friday", "Ana", "", "")
    store.post_message(con, "r", "Ana", "Saturday instead")
    _, prop = dissent.judge_room(con, "r", "m")
    assert prop["updates"] == ""
    bad = dict(SILENT_DEC, decision={"what": "Ship Sunday", "who": "Ben",
                                     "why": "", "deadline": "",
                                     "updates": "ship it friday sometime",
                                     "needs_detail": False})
    monkeypatch.setattr(dissent.meta, "spark_reply", _judge_fake(bad))
    store.post_message(con, "r", "Ana", "Sunday it is")
    _, prop2 = dissent.judge_room(con, "r", "m")
    assert prop2["updates"] == ""  # paraphrase refs never resolve
    con.close()


def test_confirm_updates_stamped_ledger(client, monkeypatch):
    monkeypatch.setattr(dissent.meta, "spark_reply",
                        _judge_fake(SILENT_DEC))
    rid, tok = _room(client)
    con = store.connect()
    lid = store.add_ledger(con, rid, "Ship Friday", "Ana", "client waits",
                           "Fri")["id"]
    pid = store.add_proposal(con, rid, "Ship Saturday", "Ben",
                             "client waits", "Sat", "Ana",
                             f"L{lid}", False)["id"]
    con.close()
    r = client.post(f"/rooms/{rid}/proposals/{pid}/confirm",
                    params={"token": tok}).json()
    assert r == {"stamped": pid, "updated": lid}
    led = client.get(f"/rooms/{rid}/ledger", params={"token": tok}).json()
    assert len(led) == 1 and led[0]["what"] == "Ship Saturday"
    assert led[0]["who"] == "Ben"
    msgs = client.get(f"/rooms/{rid}/messages",
                      params={"token": tok}).json()
    assert "updated: Ship Saturday" in msgs[-1]["body"]


def test_vague_decision_flagged(db, monkeypatch):
    vague = dict(SILENT_DEC, decision={"what": "K to concentrate on this",
                                       "who": "K", "why": "", "deadline": "",
                                       "updates": "", "needs_detail": True})
    monkeypatch.setattr(dissent.meta, "spark_reply", _judge_fake(vague))
    con = store.connect()
    con.execute("INSERT INTO rooms (id, mission) VALUES ('r', 'm')")
    store.post_message(con, "r", "Ana", "K you take this one")
    _, prop = dissent.judge_room(con, "r", "m")
    assert prop["needs_detail"] == 1
    con.close()
    assert "updates" in dissent.JUDGE_PROMPT
    assert "needs_detail" in dissent.JUDGE_PROMPT
