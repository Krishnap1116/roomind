"""Agent teammates: default crew, owner-run roster, @mention answers."""
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


def _room(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "Ana"}).json()
    return j["room_id"], j["token"]


def _fake_loop(seen):
    def fake(call, tools, question, history=None, notes=None, rounds=3):
        seen.append(question)
        return {"answer": "here you go", "reasons": ["r"],
                "remember": [], "calls": [{"tin": 1, "tout": 1}]}
    return fake


def _quiet_judge(monkeypatch):
    monkeypatch.setattr(web.dissent, "judge_room",
                        lambda con, rid, model: (None, None))


def test_defaults_seeded(client):
    rid, otok, mtok = _two(client)
    mates = client.get(f"/rooms/{rid}/teammates",
                       params={"token": mtok}).json()
    assert [(m["name"], m["role"]) for m in mates] == [
        ("Researcher", "researcher"), ("Planner", "planner"),
        ("Critic", "critic")]
    assert all(m["instructions"] for m in mates)
    assert client.get(f"/rooms/{rid}/teammates",
                      params={"token": "nope"}).status_code == 403
    sid = client.post(f"/rooms/{rid}/side",
                      params={"token": mtok, "mission": "S"}
                      ).json()["room_id"]
    stok = client.post(f"/rooms/{sid}/open-side",
                       params={"ptoken": mtok}).json()["token"]
    assert len(client.get(f"/rooms/{sid}/teammates",
                          params={"token": stok}).json()) == 3


def test_add_edit_remove(client):
    rid, otok, mtok = _two(client)
    assert client.post(f"/rooms/{rid}/teammates",
                       params={"token": mtok, "name": "X"}
                       ).status_code == 403
    assert client.post(f"/rooms/{rid}/teammates",
                       params={"token": otok, "name": " "}
                       ).status_code == 400
    assert client.post(f"/rooms/{rid}/teammates",
                       params={"token": otok, "name": "researcher"}
                       ).status_code == 400
    mate = client.post(f"/rooms/{rid}/teammates",
                       params={"token": otok, "name": "Sara",
                               "role": "designer",
                               "instructions": "keep it simple"}).json()
    assert mate["role"] == "designer"
    assert client.post(f"/rooms/{rid}/teammates/999/edit",
                       params={"token": otok}).status_code == 404
    assert client.post(f"/rooms/{rid}/teammates/{mate['id']}/edit",
                       params={"token": mtok}).status_code == 403
    assert client.post(f"/rooms/{rid}/teammates/{mate['id']}/edit",
                       params={"token": otok,
                               "name": "Critic"}).status_code == 400
    edited = client.post(f"/rooms/{rid}/teammates/{mate['id']}/edit",
                         params={"token": otok, "role": "lead designer"}
                         ).json()
    assert edited["name"] == "Sara" and edited["role"] == "lead designer"
    assert client.delete(f"/rooms/{rid}/teammates/{mate['id']}",
                         params={"token": mtok}).status_code == 403
    assert client.delete(f"/rooms/{rid}/teammates/999",
                         params={"token": otok}).status_code == 404
    assert client.delete(f"/rooms/{rid}/teammates/{mate['id']}",
                         params={"token": otok}).json() == {
                             "removed": mate["id"]}
    names = [m["name"] for m in client.get(
        f"/rooms/{rid}/teammates", params={"token": otok}).json()]
    assert "Sara" not in names


def test_teammate_lock(client):
    rid, otok, mtok = _two(client)
    tid = client.get(f"/rooms/{rid}/teammates",
                     params={"token": otok}).json()[0]["id"]
    client.post(f"/rooms/{rid}/lock", params={"token": otok, "on": True})
    assert client.post(f"/rooms/{rid}/teammates",
                       params={"token": otok, "name": "X"}
                       ).status_code == 403
    assert client.post(f"/rooms/{rid}/teammates/{tid}/edit",
                       params={"token": otok, "role": "Y"}
                       ).status_code == 403
    assert client.delete(f"/rooms/{rid}/teammates/{tid}",
                         params={"token": otok}).status_code == 403
    assert len(client.get(f"/rooms/{rid}/teammates",
                          params={"token": mtok}).json()) == 3


def test_mention_answers_in_role(client, monkeypatch):
    seen = []
    monkeypatch.setattr(web.agent, "run_loop", _fake_loop(seen))
    _quiet_judge(monkeypatch)
    rid, tok = _room(client)
    with client.websocket_connect(
            f"/rooms/{rid}/live?token={tok}") as ws:
        ws.send_text("@Researcher find launch laps")
        echo = ws.receive_json()
        assert echo["body"] == "@Researcher find launch laps"
        ans = ws.receive_json()
        assert ans["kind"] == "answer" and ans["author"] == "Researcher"
        assert ans["body"] == "here you go"
        assert ans["reasons"] == ["r"]
    assert len(seen) == 1
    assert "[You are Researcher, researcher." in seen[0]
    assert "Always cite sources." in seen[0]
    assert "find launch laps" in seen[0]
    assert "@Researcher" not in seen[0]


def test_mention_uses_member_model(client, monkeypatch):
    monkeypatch.setattr(web.agent, "run_loop", _fake_loop([]))
    _quiet_judge(monkeypatch)
    rid, otok, mtok = _two(client)
    client.post(f"/rooms/{rid}/model",
                params={"token": mtok, "model": "muse-spark-1.2"})
    with client.websocket_connect(
            f"/rooms/{rid}/live?token={mtok}") as ws:
        ws.send_text("@Planner plan it")
        ws.receive_json()
        ans = ws.receive_json()
        assert ans["author"] == "Planner"
    rows = client.get(f"/rooms/{rid}/messages",
                      params={"token": otok}).json()
    assert [m["model"] for m in rows if m["kind"] == "answer"] == [
        "muse-spark-1.2"]


def test_blank_mention_intros_without_model(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("model must not be called")

    monkeypatch.setattr(web.agent, "run_loop", boom)
    _quiet_judge(monkeypatch)
    rid, tok = _room(client)
    with client.websocket_connect(
            f"/rooms/{rid}/live?token={tok}") as ws:
        ws.send_text("@Critic")
        ws.receive_json()
        ans = ws.receive_json()
        assert ans["kind"] == "answer" and ans["author"] == "Critic"
        assert "Mention me with a question" in ans["body"]


def test_unknown_mention_stays_silent(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("model must not be called")

    monkeypatch.setattr(web.agent, "run_loop", boom)
    _quiet_judge(monkeypatch)
    rid, tok = _room(client)
    with client.websocket_connect(
            f"/rooms/{rid}/live?token={tok}") as ws:
        ws.send_text("@Nobody hi there")
        echo = ws.receive_json()
        assert echo["body"] == "@Nobody hi there"
    rows = client.get(f"/rooms/{rid}/messages",
                      params={"token": tok}).json()
    assert [m for m in rows if m["kind"] == "answer"] == []


def test_teammate_ui_markers(client):
    rid, otok, mtok = _two(client)
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    for marker in (">Team</button>", "team()", "teamAdd()",
                   "teamEdit(", "teamSave(", "teamDel(",
                   "@Name to ask"):
        assert marker in page
