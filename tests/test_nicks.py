"""Nickname slice: unique inside one name, reusable across names."""
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


def _room(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    return j["room_id"], j["token"]


def _team(client, rid, otok, uses=5):
    return client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": uses}).json()["invite"]


def _nicks(client, rid, otok):
    return client.get(f"/rooms/{rid}/members",
                      params={"token": otok}).json()


def test_same_name_never_shares_nick(client):
    rid, otok = _room(client)
    team = _team(client, rid, otok)
    for _ in range(3):
        client.post(f"/rooms/{rid}/join",
                    params={"name": "Ana", "invite": team})
    anas = [m["nick"] for m in _nicks(client, rid, otok)
            if m["name"] == "Ana"]
    assert len(anas) == len(set(anas)) == 3
    assert all(" " in n for n in anas)


def test_nick_retires_with_leaver(client):
    rid, otok = _room(client)
    team = _team(client, rid, otok)
    atok = client.post(f"/rooms/{rid}/join",
                       params={"name": "Ana", "invite": team}).json()["token"]
    gone = [m["nick"] for m in _nicks(client, rid, otok)
            if m["name"] == "Ana"][0]
    client.post(f"/rooms/{rid}/leave", params={"token": atok})
    client.post(f"/rooms/{rid}/join",
                params={"name": "Ana", "invite": team})
    fresh = [m["nick"] for m in _nicks(client, rid, otok)
             if m["name"] == "Ana"]
    assert len(fresh) == 1 and fresh[0] != gone
    used = store.connect().execute(
        "SELECT COUNT(*) AS c FROM used_nicks WHERE room=? AND name='Ana'",
        (rid,)).fetchone()["c"]
    assert used == 2  # leaver's nick stays retired for Anas


def test_other_names_may_share_nick(client):
    rid, otok = _room(client)
    team = _team(client, rid, otok)
    client.post(f"/rooms/{rid}/join",
                params={"name": "Ana", "invite": team})
    btok = client.post(f"/rooms/{rid}/join",
                       params={"name": "Ben", "invite": team}).json()["token"]
    con = store.connect()
    shared = con.execute("SELECT nick FROM members WHERE room=?"
                         " AND name='Ana'", (rid,)).fetchone()[0]
    con.execute("UPDATE members SET nick=? WHERE token=?", (shared, btok))
    con.commit()
    con.close()
    rows = _nicks(client, rid, otok)
    assert [m["nick"] for m in rows if m["name"] == "Ben"] == [shared]
    assert [m["nick"] for m in rows if m["name"] == "Ana"] == [shared]


def test_old_seats_get_backfilled_nicks(client):
    rid, otok = _room(client)
    con = store.connect()
    con.execute("INSERT INTO members (id, room, name, role, token, nick)"
                " VALUES ('old1', ?, 'Vet', 'member', 'tok-old', '')", (rid,))
    con.commit()
    con.close()
    rows = _nicks(client, rid, otok)
    assert [m["nick"] for m in rows if m["name"] == "Vet"][0] != ""


def test_duplicate_chat_tag_is_nick(client):
    rid, otok = _room(client)
    team = _team(client, rid, otok)
    ta = client.post(f"/rooms/{rid}/join",
                     params={"name": "Ana", "invite": team}).json()["token"]
    tb = client.post(f"/rooms/{rid}/join",
                     params={"name": "Ana", "invite": team}).json()["token"]
    con = store.connect()
    ida = con.execute("SELECT id FROM members WHERE token=?",
                      (ta,)).fetchone()[0]
    idb = con.execute("SELECT id FROM members WHERE token=?",
                      (tb,)).fetchone()[0]
    na = con.execute("SELECT nick FROM members WHERE token=?",
                     (ta,)).fetchone()[0]
    nb = con.execute("SELECT nick FROM members WHERE token=?",
                     (tb,)).fetchone()[0]
    store.post_message(con, rid, "Ana", "first", author_id=ida)
    store.post_message(con, rid, "Ana", "second", author_id=idb)
    con.close()
    msgs = client.get(f"/rooms/{rid}/messages",
                      params={"token": otok}).json()
    tags = sorted(m.get("tag") for m in msgs if m["author"] == "Ana")
    assert tags == sorted([na, nb])
