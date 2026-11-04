"""Operator slice: grant, daily powers, crown limits, named successor."""
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
    mid = store.connect().execute(
        "SELECT id FROM members WHERE token=?", (mtok,)).fetchone()[0]
    return rid, otok, mtok, mid


def test_grant_and_operator_powers_with_limits(client):
    rid, otok, mtok, mid = _two(client)
    assert client.post(f"/rooms/{rid}/operators",
                       params={"token": otok,
                               "member_id": mid}).json() == {"operator": mid}
    assert client.post(f"/rooms/{rid}/invites",
                       params={"token": mtok, "uses": 2}).status_code == 200
    assert client.post(f"/rooms/{rid}/dissent/mute",
                       params={"token": mtok}).status_code == 200
    assert client.delete(f"/rooms/{rid}",
                         params={"token": mtok}).status_code == 403
    assert client.post(f"/rooms/{rid}/owner",
                       params={"token": mtok,
                               "member_id": mid}).status_code == 403
    assert client.post(f"/rooms/{rid}/operators",
                       params={"token": mtok,
                               "member_id": mid}).status_code == 403


def test_named_successor_and_announcement(client):
    rid, otok, mtok, mid = _two(client)
    assert client.post(f"/rooms/{rid}/leave",
                       params={"token": otok,
                               "successor_id": mid}).json() == {"left": rid}
    roles = {m["name"]: m["role"] for m in client.get(
        f"/rooms/{rid}/members", params={"token": mtok}).json()}
    assert roles == {"M": "owner"}
    bodies = [m["body"] for m in client.get(
        f"/rooms/{rid}/messages", params={"token": mtok}).json()]
    assert any("Crown passed to M" in b for b in bodies)


def test_operator_page_sees_links_not_crown(client):
    rid, otok, mtok, mid = _two(client)
    client.post(f"/rooms/{rid}/operators",
                params={"token": otok, "member_id": mid})
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": mtok}).text
    assert ">Team link</button>" in page
    assert "dataset.r==='owner'" in page
    assert "Leave room</button>" in page
    assert ">People</button>" in page


def test_chat_lines_carry_admin_and_operator_badges(client):
    rid, otok, mtok, mid = _two(client)
    client.post(f"/rooms/{rid}/operators",
                params={"token": otok, "member_id": mid})
    con = store.connect()
    oid = con.execute("SELECT id FROM members WHERE token=?",
                      (otok,)).fetchone()[0]
    store.post_message(con, rid, "O", "mine", author_id=oid)
    store.post_message(con, rid, "M", "duty", author_id=mid)
    con.execute("INSERT INTO members (id, room, name, role, token, nick)"
                " VALUES ('g1', ?, 'G', 'member', 'tok-g', 'Calm Mole')",
                (rid,))
    store.post_message(con, rid, "G", "hi", author_id="g1")
    con.commit()
    con.close()
    rows = {m["author"]: m for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()}
    assert rows["O"]["badge"] == "admin"
    assert rows["M"]["badge"] == "operator"
    assert "badge" not in rows["G"]
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    assert "m.badge?' ['+m.badge+']':''" in page
