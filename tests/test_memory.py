"""Step 2 slice: memory, brief, catch-up. No network calls."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import roomind.memory as memory
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


def test_recall_ranks_best_match(db):
    con = store.connect()
    memory.remember(con, "r", "standup time", "9am daily")
    memory.remember(con, "r", "deploy day", "friday")
    got = memory.recall(con, "r", "when is standup")
    assert got and got[0]["key"] == "standup time"
    memory.remember(con, "r", "standup time", "9am daily")
    n = con.execute("SELECT n FROM memory WHERE room='r' AND key='standup time'"
                    ).fetchone()[0]
    assert n == 2
    memory.forget(con, "r", "deploy day")
    assert memory.recall(con, "r", "deploy") == []
    con.close()


def test_ask_saves_and_reuses_memory(client, monkeypatch):
    seen = []

    def fake(call, tools, question, history=None, notes=None, rounds=3):
        seen.append((question, notes or []))
        return {"answer": "ok", "reasons": ["r"],
                "remember": [{"key": "standup", "value": "9am daily"}],
                "calls": [{"tin": 1, "tout": 1}], "searched": False}

    monkeypatch.setattr(web.agent, "run_loop", fake)
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    tok = client.post(f"/rooms/{rid}/join",
                      params={"name": "A", "invite": inv}).json()["token"]
    client.post(f"/rooms/{rid}/ask", params={"token": tok, "text": "hi"})
    client.post(f"/rooms/{rid}/ask",
                params={"token": tok, "text": "when is standup"})
    asks = [n for p, n in seen if "ROOM JUDGE" not in p]
    assert asks[0] == []  # nothing known on first ask
    assert any(n["key"] == "standup" for n in asks[1])  # reused on second


def test_brief_shape_and_catchup_empty(client, monkeypatch):
    def fake(api_key, base, model, history, prompt, timeout=60.0, notes=None):
        return {"answer": json.dumps({"decisions": [{"what": "x", "who": "A",
                                                     "why": "y"}],
                                      "open": [], "owners": {}}),
                "reasons": [], "remember": [], "tin": 1, "tout": 1}

    monkeypatch.setattr(web.meta, "spark_reply", fake)
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    tok = client.post(f"/rooms/{rid}/join",
                      params={"name": "A", "invite": inv}).json()["token"]
    b = client.get(f"/rooms/{rid}/brief", params={"token": tok}).json()
    assert b["decisions"][0]["what"] == "x"

    def boom(*a, **k):
        raise AssertionError("model must not be called")

    monkeypatch.setattr(web.meta, "spark_reply", boom)
    c = client.get(f"/rooms/{rid}/catchup",
                   params={"token": tok, "since_id": 9999}).json()
    assert c["summary"] == "Nothing new."
