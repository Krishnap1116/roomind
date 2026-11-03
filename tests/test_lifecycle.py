"""Lifecycle slice: transfer, guarded leave, auto-close, members list."""
import asyncio
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
    rid = client.post("/rooms", params={"mission": "M",
                                        "name": "O"}).json()["room_id"]
    con = store.connect()
    otok = con.execute("SELECT token FROM members WHERE room=? AND name='O'",
                       (rid,)).fetchone()[0]
    con.close()
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    mtok = client.post(f"/rooms/{rid}/join",
                       params={"name": "M", "invite": team}).json()["token"]
    return rid, otok, mtok


def test_transfer_moves_crown(client):
    rid, otok, mtok = _two(client)
    mid = store.connect().execute(
        "SELECT id FROM members WHERE token=?", (mtok,)).fetchone()[0]
    assert client.post(f"/rooms/{rid}/owner",
                       params={"token": otok,
                               "member_id": mid}).json() == {"owner": mid}
    roles = {m["name"]: m["role"] for m in client.get(
        f"/rooms/{rid}/members", params={"token": mtok}).json()}
    assert roles == {"O": "member", "M": "owner"}
    assert client.post(f"/rooms/{rid}/owner",
                       params={"token": otok,
                               "member_id": mid}).status_code == 403
    assert client.post(f"/rooms/{rid}/owner",
                       params={"token": mtok,
                               "member_id": "nope"}).status_code == 404


def test_owner_leave_autopass_and_last_out_closes(client):
    rid, otok, mtok = _two(client)
    assert client.post(f"/rooms/{rid}/leave",
                       params={"token": otok}).json() == {"left": rid}
    roles = {m["name"]: m["role"] for m in client.get(
        f"/rooms/{rid}/members", params={"token": mtok}).json()}
    assert roles == {"M": "owner"}
    gone = client.post(f"/rooms/{rid}/leave", params={"token": mtok}).json()
    assert gone == {"left": rid, "closed": True}
    assert client.get(f"/rooms/{rid}/messages",
                      params={"token": mtok}).status_code == 403


def test_members_list_open_but_crown_stays_owner_only(client):
    rid, otok, mtok = _two(client)
    assert len(client.get(f"/rooms/{rid}/members",
                          params={"token": otok}).json()) == 2
    assert len(client.get(f"/rooms/{rid}/members",
                          params={"token": mtok}).json()) == 2
    owner_page = client.get(f"/rooms/{rid}/app",
                            params={"token": otok}).text
    guest_page = client.get(f"/rooms/{rid}/app",
                            params={"token": mtok}).text
    for marker in (">People</button>", ">Close room</button>", ">Step out</button>"):
        assert marker in owner_page
    assert ">People</button>" in guest_page
    assert ">Close room</button>" not in guest_page
    assert ">Step out</button>" in guest_page
    assert "if(ISOWNER)" in guest_page  # crown buttons gated in list
    mid = store.connect().execute(
        "SELECT id FROM members WHERE token=?", (mtok,)).fetchone()[0]
    assert client.post(f"/rooms/{rid}/operators",
                       params={"token": mtok,
                               "member_id": mid}).status_code == 403
    assert client.post(f"/rooms/{rid}/owner",
                       params={"token": mtok,
                               "member_id": mid}).status_code == 403
    assert owner_page.count("esc(m.nick)") == 2  # roster + picker
    assert "avatar(" not in owner_page  # colors gone, nicknames rule


def test_close_hangs_up_open_tabs(client):
    rid, otok, mtok = _two(client)
    sent = []

    class Peer:
        async def send_json(self, m):
            sent.append(("json", m))

        async def close(self, code=1000):
            sent.append(("close", code))

    page = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    assert "m.kind==='closed'" in page  # tab reloads into closed page
    web._live[rid] = {Peer(), Peer()}
    asyncio.run(web._evict(rid))
    assert len(sent) == 4
    for i in (0, 2):  # each tab: note first, hang-up second
        assert sent[i] == ("json", {"kind": "closed"})
        assert sent[i + 1] == ("close", 4000)
    assert rid not in web._live
    assert client.delete(f"/rooms/{rid}",
                         params={"token": otok}).json() == {"deleted": rid}
    assert "My rooms" in client.get("/").text
