"""Eval slice: golden transcripts, scorer, strip numbers, no UI yet."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import roomind.store as store
import roomind.web as web
import roomind as S
from roomind import eval as ev
from roomind import golden


@pytest.fixture()
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    monkeypatch.setattr(S, "DB", p)
    monkeypatch.setattr(S, "PAUSED", False)
    return p


@pytest.fixture()
def client(db):
    return TestClient(web.app)


def _case(cid, must):
    return {"id": cid, "title": cid, "must_fire": must, "why": "t",
            "messages": [{"author": "A", "body": "x", "ago": 10}]}


def test_suite_math_counts_right(monkeypatch):
    calls = {"F1": {"claim": "c", "agreers": ["A"]}, "F2": None,
             "S1": {"claim": "c", "agreers": ["A"]}, "S2": None}
    monkeypatch.setattr(ev.dissent, "watch",
                        lambda msgs: calls.get(msgs[0]["author"]))
    cases = []
    for cid, must in (("F1", True), ("F2", True), ("S1", False),
                      ("S2", False)):
        c = _case(cid, must)
        c["messages"][0]["author"] = cid
        cases.append(c)
    rep = ev.run_suite(cases, now=1000.0)
    assert rep["total"] == 4 and rep["score"] == 2
    assert rep["precision"] == 0.5 and rep["recall"] == 0.5
    assert rep["false_alarms"] == ["S1"] and rep["misses"] == ["F2"]


def test_golden_baseline_is_seven_of_ten():
    rep = ev.run_suite(golden.GOLDEN)
    assert rep["total"] == 10 and rep["score"] == 7
    assert rep["false_alarms"] == ["S2"]  # nods on sound work
    assert rep["misses"] == ["F2", "F5"]  # memory-blind, mission-blind
    assert rep["precision"] == 0.75 and rep["recall"] == 0.6


def test_rate_and_approval_percent(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    con = store.connect()
    a = store.post_message(con, rid, "agent", "one", kind="answer")
    b = store.post_message(con, rid, "agent", "two", kind="answer")
    c = store.post_message(con, rid, "O", "chat")
    con.close()
    assert client.post(f"/rooms/{rid}/messages/{a}/rate",
                       params={"token": otok,
                               "up": True}).json() == {"id": a, "rating": 1}
    client.post(f"/rooms/{rid}/messages/{b}/rate",
                params={"token": otok, "up": False})
    assert client.post(f"/rooms/{rid}/messages/{c}/rate",
                       params={"token": otok,
                               "up": True}).status_code == 400
    e = client.get(f"/rooms/{rid}/eval", params={"token": otok}).json()
    assert e["approval"] == {"pct": 0.5, "n": 2}
    assert client.post(f"/rooms/{rid}/messages/999/rate",
                       params={"token": otok}).status_code == 404
    assert client.get(f"/rooms/{rid}/eval",
                      params={"token": "nope"}).status_code == 403


def test_eval_speed_and_cost_per_decision(client, monkeypatch):
    monkeypatch.setattr(web.agent, "run_loop",
                        lambda *a, **k: {"answer": "ok", "reasons": [],
                                         "remember": [],
                                         "calls": [{"tin": 100, "tout": 20}],
                                         "searched": False})
    monkeypatch.setattr(S, "PRICE_IN_PER_M", 1000.0)
    monkeypatch.setattr(S, "PRICE_OUT_PER_M", 2000.0)
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    e0 = client.get(f"/rooms/{rid}/eval", params={"token": otok}).json()
    assert e0["speed_s"] is None and e0["cost_per_decision"] is None
    assert e0["approval"] == {"pct": None, "n": 0}
    assert e0["golden"] is None  # judge-graded exam runs on demand
    client.post(f"/rooms/{rid}/ask", params={"token": otok, "text": "hi"})
    con = store.connect()
    store.add_ledger(con, rid, "ship it", "O", "tests green")
    store.add_ledger(con, rid, "docs", "O", "demo needs them")
    con.close()
    e1 = client.get(f"/rooms/{rid}/eval", params={"token": otok}).json()
    assert e1["speed_s"] is not None and e1["speed_s"] >= 0
    assert e1["decisions"] == 2
    assert abs(e1["cost_per_decision"] - e1["spend_usd"] / 2) < 1e-9
    assert e1["spend_usd"] > 0


def _judge_fake(fire_words):
    def fake(api_key, base, model, history, prompt, timeout=60.0,
             notes=None):
        text = " ".join(m["body"] for m in history)
        fire = any(w in text for w in fire_words)
        return {"answer": '{"fire": %s, "points": [{"flaw": "f", '
                '"receipt": "r"}], "question": "q"}'
                % ("true" if fire else "false"),
                "reasons": [], "remember": [], "tin": 10, "tout": 5}
    return fake


def test_strip_face_wiring(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    mtok = client.post(f"/rooms/{rid}/join",
                       params={"name": "G",
                               "invite": team}).json()["token"]
    owner_page = client.get(f"/rooms/{rid}/app",
                            params={"token": otok}).text
    guest_page = client.get(f"/rooms/{rid}/app",
                            params={"token": mtok}).text
    assert "id=strip" in owner_page and "evalPanel()" in owner_page
    assert "let h='Approval: '" in owner_page  # bar shows live health only
    assert "Test the referee" in owner_page and "Exam never run" in owner_page
    assert "cost_per_decision" in owner_page
    assert "showAns(m)" in owner_page  # answers get thumbs
    assert "messages/'+v[0]+'/rate" in owner_page
    assert "Run duel" not in owner_page and "runDuel" not in owner_page
    assert "const ISMANAGE=true" in owner_page
    assert "const ISMANAGE=false" in guest_page  # button hides for guests


def test_model_failure_is_clean_503(client, monkeypatch):
    import httpx

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(web.meta, "chat", boom)
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    r = client.post(f"/rooms/{j['room_id']}/ask",
                    params={"token": j["token"], "text": "hi"})
    assert r.status_code == 503
    page = client.get(f"/rooms/{j['room_id']}/app",
                      params={"token": j["token"]}).text
    assert "Send failed." in page  # mid-stream note arrives live instead
    assert "key missing" not in page


def test_exam_lock_rejects_overlap(client):
    import threading
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    lock = web._exam_locks.setdefault(rid, threading.Lock())
    lock.acquire()
    try:
        r = client.post(f"/rooms/{rid}/eval/exam", params={"token": otok})
        assert r.status_code == 409
    finally:
        lock.release()


def test_trust_words_follow_verdicts(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    e = lambda: client.get(f"/rooms/{rid}/eval",
                           params={"token": otok}).json()["trust"]
    assert e() == {"word": "watching", "pct": None, "n": 0}
    con = store.connect()
    ids = [store.post_message(con, rid, "dissent", "{}", kind="dissent")
           for _ in range(4)]
    con.close()
    client.post(f"/rooms/{rid}/messages/{ids[0]}/rate",
                params={"token": otok, "up": True})
    client.post(f"/rooms/{rid}/messages/{ids[1]}/rate",
                params={"token": otok, "up": True})
    assert e()["word"] == "trusted"
    client.post(f"/rooms/{rid}/messages/{ids[2]}/rate",
                params={"token": otok, "up": False})
    client.post(f"/rooms/{rid}/messages/{ids[3]}/rate",
                params={"token": otok, "up": False})
    assert e() == {"word": "watching", "pct": 0.5, "n": 4}
    client.post(f"/rooms/{rid}/messages/{ids[0]}/rate",
                params={"token": otok, "up": False})
    assert e()["word"] == "strained"
    client.post(f"/rooms/{rid}/dissent/mute",
                params={"token": otok, "on": True})
    assert e()["word"] == "muted"
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    assert "Trust: '+tr.word" in page  # trust lives in Details panel, not the strip


def _suite_case(cid, must, body):
    return {"id": cid, "title": cid, "must_fire": must, "why": "t",
            "mission": "m", "memory": {},
            "messages": [{"author": "A", "body": body, "ago": 10}]}


def test_run_suite_judge_math():
    fn = lambda h, p: {"answer": '{"fire": %s, "points": [{"flaw": "f", '
                                 '"receipt": "r"}], "question": "q"}' % (
        "true" if "FIREME" in " ".join(m["body"] for m in h) else "false"),
        "tin": 10, "tout": 5}
    cases = [_suite_case("F1", True, "please FIREME now"),
             _suite_case("S1", False, "just chatting")]
    rep = ev.run_suite_judge(fn, cases)
    assert (rep["score"], rep["total"]) == (2, 2)
    assert (rep["precision"], rep["recall"]) == (1.0, 1.0)
    assert (rep["tin"], rep["tout"]) == (20, 10)


def test_exam_endpoint_caches_report(client, monkeypatch):
    monkeypatch.setattr(web.meta, "spark_reply",
                        _judge_fake(["the", "a", "e"]))
    monkeypatch.setattr(S, "MODEL_API_KEY", "k")
    monkeypatch.setattr(S, "PRICE_IN_PER_M", 1000.0)
    monkeypatch.setattr(S, "PRICE_OUT_PER_M", 2000.0)
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    mtok = client.post(f"/rooms/{rid}/join",
                       params={"name": "G",
                               "invite": team}).json()["token"]
    assert client.post(f"/rooms/{rid}/eval/exam",
                       params={"token": mtok}).status_code == 403
    rep = client.post(f"/rooms/{rid}/eval/exam",
                      params={"token": otok}).json()
    assert rep["score"] == 5  # always-fire fake lands the 5 F-cases
    assert rep["model"] and rep["at"] > 0
    e = client.get(f"/rooms/{rid}/eval", params={"token": otok}).json()
    assert e["golden"]["score"] == 5  # bar reads the saved report
    assert e["spend_usd"] > 0
    monkeypatch.setattr(S, "MODEL_API_KEY", "")
    assert client.post(f"/rooms/{rid}/eval/exam",
                       params={"token": otok}).status_code == 503
