"""Away tasks: background work that lands while humans are gone."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

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


def _two(client):
    j = client.post("/rooms", params={"mission": "Ship Friday",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    mtok = client.post(f"/rooms/{rid}/join",
                       params={"name": "M", "invite": team}).json()["token"]
    return rid, otok, mtok


def _mate_id(client, rid, otok, name="Researcher"):
    mates = client.get(f"/rooms/{rid}/teammates",
                       params={"token": otok}).json()
    return [m["id"] for m in mates if m["name"] == name][0]


def _assign(client, rid, tok, tid, instruction="research X", due="today"):
    return client.post(f"/rooms/{rid}/away",
                       params={"token": tok, "teammate": tid,
                               "instruction": instruction, "due": due})


def _fake_loop(seen):
    def fake(call, tools, question, history=None, notes=None, rounds=3):
        seen.append(question)
        return {"answer": "done while away", "reasons": ["r"],
                "remember": [], "calls": [{"tin": 1, "tout": 1}]}
    return fake


def test_away_assign_list_delete(client):
    rid, otok, mtok = _two(client)
    tid = _mate_id(client, rid, otok)
    assert client.get(f"/rooms/{rid}/away",
                      params={"token": "nope"}).status_code == 403
    assert _assign(client, rid, "nope", tid).status_code == 403
    assert _assign(client, rid, mtok, 999).status_code == 404
    assert _assign(client, rid, mtok, tid,
                   instruction=" ").status_code == 400
    assert _assign(client, rid, mtok, tid, due="xyzzy").status_code == 400
    task = _assign(client, rid, mtok, tid).json()
    assert task["status"] == "pending"
    assert task["teammate_name"] == "Researcher"
    rows = client.get(f"/rooms/{rid}/away",
                      params={"token": otok}).json()
    assert [t["instruction"] for t in rows] == ["research X"]
    assert client.post(f"/rooms/{rid}/away/999/delete",
                       params={"token": mtok}).status_code == 404
    assert client.post(f"/rooms/{rid}/away/{task['id']}/delete",
                       params={"token": mtok}).json() == {
                           "deleted": task["id"]}
    assert client.get(f"/rooms/{rid}/away",
                      params={"token": otok}).json() == []


def test_away_lock(client):
    rid, otok, mtok = _two(client)
    tid = _mate_id(client, rid, otok)
    task = _assign(client, rid, mtok, tid).json()
    client.post(f"/rooms/{rid}/lock", params={"token": otok, "on": True})
    assert _assign(client, rid, mtok, tid).status_code == 403
    assert client.post(f"/rooms/{rid}/away/{task['id']}/delete",
                       params={"token": mtok}).status_code == 403
    assert len(client.get(f"/rooms/{rid}/away",
                          params={"token": mtok}).json()) == 1


def test_away_tick_runs_due(client, monkeypatch):
    seen = []
    monkeypatch.setattr(web.agent, "run_loop", _fake_loop(seen))
    rid, otok, mtok = _two(client)
    tid = _mate_id(client, rid, otok)
    client.post(f"/rooms/{rid}/model",
                params={"token": mtok, "model": "muse-spark-1.2"})
    _assign(client, rid, mtok, tid, due="today")
    future = _assign(client, rid, mtok, tid, instruction="later",
                      due="tomorrow").json()
    casts = web._away_tick()
    assert len(casts) == 1
    room, payload = casts[0]
    assert room == rid and payload["kind"] == "answer"
    assert payload["author"] == "Researcher"
    assert payload["body"] == "done while away"
    assert payload["reasons"] == ["r"]
    assert "[You are Researcher, researcher." in seen[0]
    assert "research X" in seen[0]
    rows = {t["id"]: t for t in client.get(
        f"/rooms/{rid}/away", params={"token": otok}).json()}
    done = [t for t in rows.values() if t["instruction"] == "research X"][0]
    assert done["status"] == "done" and done["answer_mid"] > 0
    assert done["answer"] == "done while away"
    assert rows[future["id"]]["answer"] == ""
    assert rows[future["id"]]["status"] == "pending"
    answers = [m for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()
        if m["kind"] == "answer"]
    assert [a["model"] for a in answers] == ["muse-spark-1.2"]


def test_away_tick_skips_locked_and_spent(client, monkeypatch):
    monkeypatch.setattr(web.agent, "run_loop", _fake_loop([]))
    rid, otok, mtok = _two(client)
    tid = _mate_id(client, rid, otok)
    mine = _assign(client, rid, mtok, tid).json()["id"]
    client.post(f"/rooms/{rid}/lock", params={"token": otok, "on": True})
    assert web._away_tick() == []
    client.post(f"/rooms/{rid}/lock", params={"token": otok, "on": False})
    monkeypatch.setattr(S, "MAX_ROOM_COST", 0.0)
    assert web._away_tick() == []
    rows = client.get(f"/rooms/{rid}/away",
                      params={"token": otok}).json()
    assert rows[0]["status"] == "pending" and rows[0]["id"] == mine


def test_away_tick_gone_teammate_fails(client, monkeypatch):
    monkeypatch.setattr(web.agent, "run_loop", _fake_loop([]))
    rid, otok, mtok = _two(client)
    tid = _mate_id(client, rid, otok)
    _assign(client, rid, mtok, tid)
    client.delete(f"/rooms/{rid}/teammates/{tid}",
                  params={"token": otok})
    assert web._away_tick() == []
    rows = client.get(f"/rooms/{rid}/away",
                      params={"token": otok}).json()
    assert rows[0]["status"] == "failed"


def test_away_tick_retries_then_fails(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("model down")

    monkeypatch.setattr(web.agent, "run_loop", boom)
    rid, otok, mtok = _two(client)
    tid = _mate_id(client, rid, otok)
    _assign(client, rid, mtok, tid)
    assert web._away_tick() == []
    first = client.get(f"/rooms/{rid}/away",
                       params={"token": otok}).json()[0]
    assert (first["status"], first["attempts"]) == ("pending", 1)
    web._away_tick()
    web._away_tick()
    last = client.get(f"/rooms/{rid}/away",
                      params={"token": otok}).json()[0]
    assert (last["status"], last["attempts"]) == ("failed", 3)


def test_away_tick_paused(client, monkeypatch):
    monkeypatch.setattr(web.agent, "run_loop", _fake_loop([]))
    rid, otok, mtok = _two(client)
    tid = _mate_id(client, rid, otok)
    _assign(client, rid, mtok, tid)
    monkeypatch.setattr(S, "PAUSED", True)
    assert web._away_tick() == []


def test_away_ui_markers(client):
    rid, otok, mtok = _two(client)
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    for marker in ("Away tasks", "teamAssign()", "awayDel(",
                   "id=aw", ">Assign</button>",
                   "Runs in the background when due", "a.answer"):
        assert marker in page
