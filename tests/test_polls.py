"""Quick votes: one-tap polls with live tallies, anyone closes."""
import json
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


def _ask(client, rid, tok, question="Ship Friday?", options=None):
    return client.post(f"/rooms/{rid}/polls",
                       params={"token": tok, "question": question,
                               "options": json.dumps(
                                   options if options is not None
                                   else ["Yes", "No"])})


def test_poll_create_list_validation(client):
    rid, otok, mtok = _two(client)
    assert client.post(f"/rooms/{rid}/polls",
                       params={"token": "nope", "question": "Q?",
                               "options": '["A","B"]'}).status_code == 403
    assert _ask(client, rid, mtok, question=" ").status_code == 400
    assert _ask(client, rid, mtok,
                options=["Only"]).status_code == 400
    assert _ask(client, rid, mtok,
                options=["A", "B", "C", "D", "E"]).status_code == 400
    assert _ask(client, rid, mtok,
                options=["A", " "]).status_code == 400
    assert client.post(f"/rooms/{rid}/polls",
                       params={"token": mtok, "question": "Q?",
                               "options": "nope"}).status_code == 400
    p = _ask(client, rid, mtok).json()
    assert p["state"] == "open" and p["options"] == ["Yes", "No"]
    assert p["created_by"] == "M"
    rows = client.get(f"/rooms/{rid}/polls",
                      params={"token": otok}).json()
    assert [r["question"] for r in rows] == ["Ship Friday?"]
    assert rows[0]["tally"] == [0, 0] and rows[0]["total"] == 0
    assert rows[0]["my_vote"] is None


def test_poll_vote_change_tally(client):
    rid, otok, mtok = _two(client)
    pid = _ask(client, rid, mtok).json()["id"]
    assert client.post(f"/rooms/{rid}/polls/{pid}/vote",
                       params={"token": mtok,
                               "option": 5}).status_code == 400
    assert client.post(f"/rooms/{rid}/polls/999/vote",
                       params={"token": mtok,
                               "option": 0}).status_code == 404
    assert client.post(f"/rooms/{rid}/polls/{pid}/vote",
                       params={"token": mtok, "option": 0}
                       ).json() == {"voted": 0}
    client.post(f"/rooms/{rid}/polls/{pid}/vote",
                params={"token": otok, "option": 1})
    client.post(f"/rooms/{rid}/polls/{pid}/vote",
                params={"token": mtok, "option": 1})
    mine = client.get(f"/rooms/{rid}/polls",
                      params={"token": mtok}).json()[0]
    assert mine["tally"] == [0, 2] and mine["total"] == 2
    assert mine["my_vote"] == 1
    assert len(mine["by_option"][1]) == 2
    other = client.get(f"/rooms/{rid}/polls",
                       params={"token": otok}).json()[0]
    assert other["my_vote"] == 1


def test_poll_close(client):
    rid, otok, mtok = _two(client)
    pid = _ask(client, rid, mtok).json()["id"]
    assert client.post(f"/rooms/{rid}/polls/999/close",
                       params={"token": mtok}).status_code == 404
    assert client.post(f"/rooms/{rid}/polls/{pid}/close",
                       params={"token": mtok}).json()["state"] == "closed"
    assert client.post(f"/rooms/{rid}/polls/{pid}/vote",
                       params={"token": otok,
                               "option": 0}).status_code == 400


def test_poll_lock(client):
    rid, otok, mtok = _two(client)
    pid = _ask(client, rid, mtok).json()["id"]
    client.post(f"/rooms/{rid}/lock", params={"token": otok, "on": True})
    assert _ask(client, rid, mtok).status_code == 403
    assert client.post(f"/rooms/{rid}/polls/{pid}/vote",
                       params={"token": mtok,
                               "option": 0}).status_code == 403
    assert client.post(f"/rooms/{rid}/polls/{pid}/close",
                       params={"token": mtok}).status_code == 403
    assert client.get(f"/rooms/{rid}/polls",
                      params={"token": mtok}
                      ).json()[0]["question"] == "Ship Friday?"


def test_poll_ui_markers(client):
    rid, otok, mtok = _two(client)
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    for marker in ("id=polls", "pollList()", "pollHTML(", "pollNew()",
                   "pollCreate()", "pollVote(", "pollClose(",
                   ">+ Vote</button>", "kind==='poll'"):
        assert marker in page
