"""Kick plus lock plus model switch: doors, rules, sockets, page."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

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


def _two(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    mtok = client.post(f"/rooms/{rid}/join",
                       params={"name": "M", "invite": team}).json()["token"]
    return rid, otok, mtok


def _mid(token):
    con = store.connect()
    try:
        return con.execute("SELECT id FROM members WHERE token=?",
                           (token,)).fetchone()[0]
    finally:
        con.close()


def _fake_ask(monkeypatch):
    monkeypatch.setattr(web.agent, "run_loop",
                        lambda *a, **k: {"answer": "ok", "reasons": [],
                                         "remember": [],
                                         "calls": [{"tin": 1, "tout": 1}],
                                         "searched": False})


def test_kick_removes_and_announces(client):
    rid, otok, mtok = _two(client)
    mid = _mid(mtok)
    r = client.post(f"/rooms/{rid}/members/{mid}/kick",
                    params={"token": otok})
    assert r.json() == {"kicked": mid}
    names = [m["name"] for m in client.get(
        f"/rooms/{rid}/members", params={"token": otok}).json()]
    assert names == ["O"]
    assert client.post(f"/rooms/{rid}/ask",
                       params={"token": mtok, "text": "hi"}
                       ).status_code == 403
    bodies = [m["body"] for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()]
    assert any("kicked M" in b for b in bodies)


def test_kick_rules(client):
    rid, otok, mtok = _two(client)
    assert client.post(f"/rooms/{rid}/members/{_mid(otok)}/kick",
                       params={"token": mtok}).status_code == 403
    assert client.post(f"/rooms/{rid}/members/{_mid(otok)}/kick",
                       params={"token": otok}).status_code == 400
    assert client.post(f"/rooms/{rid}/members/{_mid(mtok)}/kick",
                       params={"token": mtok}).status_code == 403
    client.post(f"/rooms/{rid}/operators",
                params={"token": otok, "member_id": _mid(mtok)})
    assert client.post(f"/rooms/{rid}/members/{_mid(otok)}/kick",
                       params={"token": mtok}).status_code == 403


def test_operator_kicks_member_not_operator(client):
    rid, otok, mtok = _two(client)
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    ntok = client.post(f"/rooms/{rid}/join",
                       params={"name": "N", "invite": team}).json()["token"]
    client.post(f"/rooms/{rid}/operators",
                params={"token": otok, "member_id": _mid(mtok)})
    assert client.post(f"/rooms/{rid}/members/{_mid(ntok)}/kick",
                       params={"token": mtok}).status_code == 200
    otok2 = client.post(f"/rooms/{rid}/join",
                        params={"name": "P", "invite": team}
                        ).json()["token"]
    client.post(f"/rooms/{rid}/operators",
                params={"token": otok, "member_id": _mid(otok2)})
    assert client.post(f"/rooms/{rid}/members/{_mid(otok2)}/kick",
                       params={"token": mtok}).status_code == 403


def test_kick_closes_live_socket(client):
    rid, otok, mtok = _two(client)

    class Fake:
        def __init__(self):
            self.notes = []
            self.codes = []

        async def send_json(self, p):
            self.notes.append(p)

        async def close(self, code=1000):
            self.codes.append(code)

    sock = Fake()
    web._live.setdefault(rid, set()).add(sock)
    web._live_who[sock] = _mid(mtok)
    try:
        client.post(f"/rooms/{rid}/members/{_mid(mtok)}/kick",
                    params={"token": otok})
    finally:
        web._live.pop(rid, None)
        web._live_who.pop(sock, None)
    assert sock.notes[-1] == {"kind": "kicked"}
    assert any(n.get("kind") == "system" for n in sock.notes)
    assert sock.codes == [4001]


def test_lock_freezes_writes_until_unlock(client, monkeypatch):
    _fake_ask(monkeypatch)
    rid, otok, mtok = _two(client)
    assert client.post(f"/rooms/{rid}/lock",
                       params={"token": mtok, "on": True}
                       ).status_code == 403
    assert client.post(f"/rooms/{rid}/lock",
                       params={"token": otok, "on": True}
                       ).json() == {"locked": True}
    assert client.get(f"/rooms/{rid}/state",
                      params={"token": otok}).json()["locked"] is True
    assert client.post(f"/rooms/{rid}/ask",
                       params={"token": otok, "text": "hi"}
                       ).status_code == 403
    assert client.post(f"/rooms/{rid}/proposals",
                       params={"token": otok, "what": "ship"}
                       ).status_code == 403
    assert client.post(f"/rooms/{rid}/dissent/check",
                       params={"token": otok}).status_code == 403
    assert client.post(f"/rooms/{rid}/lock",
                       params={"token": otok, "on": False}
                       ).json() == {"locked": False}
    assert client.post(f"/rooms/{rid}/ask",
                       params={"token": otok, "text": "hi"}
                       ).status_code == 200


def test_locked_chat_socket_gets_note(client):
    rid, otok, mtok = _two(client)
    client.post(f"/rooms/{rid}/lock",
                params={"token": otok, "on": True})
    with client.websocket_connect(
            f"/rooms/{rid}/live?token={mtok}") as ws:
        ws.send_text("hello?")
        assert ws.receive_json() == {"kind": "locked",
                                     "body": "Room is locked."}
    kinds = [m["kind"] for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()]
    assert "chat" not in kinds


def test_model_choice_is_personal(client, monkeypatch):
    _fake_ask(monkeypatch)
    judged = []
    monkeypatch.setattr(web, "_spawn_judge",
                        lambda rid, name: judged.append(name))
    rid, otok, mtok = _two(client)
    assert client.post(f"/rooms/{rid}/model",
                       params={"token": otok, "model": "   "}
                       ).status_code == 400
    assert client.post(f"/rooms/{rid}/model",
                       params={"token": mtok, "model": "m-x"}
                       ).json() == {"model": "m-x"}
    kinds = [m["kind"] for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()]
    assert kinds == []  # personal pick, nothing announced
    client.post(f"/rooms/{rid}/ask",
                params={"token": mtok, "text": "hi"})
    client.post(f"/rooms/{rid}/ask",
                params={"token": otok, "text": "yo"})
    u = client.get(f"/rooms/{rid}/usage",
                   params={"token": otok}).json()
    assert "m-x" in u["by_model"]  # member's pick used for member
    assert S.SPARK_MODEL in u["by_model"]  # owner untouched on default
    client.post(f"/rooms/{rid}/ask",
                params={"token": mtok, "text": "again", "model": "m-y"})
    u = client.get(f"/rooms/{rid}/usage",
                   params={"token": otok}).json()
    assert "m-y" in u["by_model"]  # per-call param still wins
    assert client.get(f"/rooms/{rid}/state",
                      params={"token": mtok}
                      ).json() == {"locked": False, "model": "m-x",
                                   "default": S.SPARK_MODEL,
                                   "dissent_muted": False, "judge_last": None}
    assert client.get(f"/rooms/{rid}/state",
                      params={"token": otok}
                      ).json() == {"locked": False, "model": "",
                                   "default": S.SPARK_MODEL,
                                   "dissent_muted": False, "judge_last": None}
    assert judged == [S.SPARK_MODEL] * 3  # monitor never follows picks


def test_page_has_kick_lock_model_meter(client):
    rid, otok, mtok = _two(client)
    owner_page = client.get(f"/rooms/{rid}/app",
                            params={"token": otok}).text
    for marker in ("lockRoom()", "id=modelsel", "id=meter",
                   "kickSeat(this)", "kind==='kicked'",
                   "code===4001", "setModel(", "id=mutebtn"):
        assert marker in owner_page
    guest_page = client.get(f"/rooms/{rid}/app",
                            params={"token": mtok}).text
    assert "id=lockbtn" not in guest_page
    assert "id=mutebtn" not in guest_page
    assert "id=modelsel" in guest_page  # dropdown is everyone
    assert "const ISMANAGE=false" in guest_page  # kick rows never render
    assert "const ISMANAGE=true" in owner_page
    assert "id=meter" in guest_page
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "Solo"}).json()
    solo_page = client.get(f"/rooms/{j['room_id']}/app",
                           params={"token": j["token"]}).text
    assert "button[onclick='lockRoom()']" in solo_page  # lock stays hidden
    assert "select#modelsel" not in solo_page  # dropdown stays in solo
    assert "id=modelsel" in solo_page
