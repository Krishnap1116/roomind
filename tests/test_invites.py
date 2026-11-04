"""Invite fix: team links with use counts, owner-only minting."""
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


def _owner(client):
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    tok = client.post(f"/rooms/{rid}/join",
                      params={"name": "Owner",
                              "invite": inv}).json()["token"]
    return rid, tok


def test_team_link_serves_many_then_dies(client):
    rid, tok = _owner(client)
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": tok, "uses": 3,
                               "hours": 24}).json()["invite"]
    for name in ("A", "B", "C"):
        r = client.post(f"/rooms/{rid}/join",
                        params={"name": name, "invite": team})
        assert r.status_code == 200
    fourth = client.post(f"/rooms/{rid}/join",
                         params={"name": "D", "invite": team})
    assert fourth.status_code == 403


def test_mint_owner_only_and_single_still_single(client):
    rid, tok = _owner(client)
    solo = client.post(f"/rooms/{rid}/invites",
                       params={"token": tok, "uses": 1}).json()["invite"]
    solo_tok = client.post(f"/rooms/{rid}/join",
                         params={"name": "Solo",
                                 "invite": solo}).json()["token"]
    assert client.post(f"/rooms/{rid}/join",
                       params={"name": "Late",
                               "invite": solo}).status_code == 403
    denied = client.post(f"/rooms/{rid}/invites",
                         params={"token": solo_tok, "uses": 5})
    assert denied.status_code == 403


def test_topup_adds_uses_owner_only(client):
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    otok = client.post(f"/rooms/{rid}/join",
                       params={"name": "O", "invite": inv}).json()["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 1}).json()["invite"]
    assert client.post(f"/rooms/{rid}/join",
                       params={"name": "A",
                               "invite": team}).status_code == 200
    assert client.post(f"/rooms/{rid}/join",
                       params={"name": "B",
                               "invite": team}).status_code == 403
    up = client.post(f"/rooms/{rid}/invites/topup",
                     params={"token": otok, "invite": team,
                             "add_uses": 5}).json()
    assert up["left"] == 5
    assert client.post(f"/rooms/{rid}/join",
                       params={"name": "B",
                               "invite": team}).status_code == 200
    rows = client.get(f"/rooms/{rid}/invites",
                      params={"token": otok}).json()
    assert any(r["token"] == team for r in rows)


def test_links_list_shows_live_counts(client):
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    otok = client.post(f"/rooms/{rid}/join",
                       params={"name": "O", "invite": inv}).json()["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    for name in ("A", "B"):
        client.post(f"/rooms/{rid}/join",
                    params={"name": name, "invite": team})
    row = [r for r in client.get(f"/rooms/{rid}/invites",
                                 params={"token": otok}).json()
           if r["token"] == team][0]
    assert (row["used"], row["left"], row["max_uses"]) == (2, 3, 5)


def test_creator_walks_straight_in(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "Owner"}).json()
    assert "token" in j and "invite" not in j  # no spare invite minted
    msgs = client.get(f"/rooms/{j['room_id']}/messages",
                      params={"token": j["token"]})
    assert msgs.status_code == 200
    rows = client.get(f"/rooms/{j['room_id']}/invites",
                      params={"token": j["token"]}).json()
    assert rows == []


def test_join_errors_tell_room_from_invite(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "Owner"}).json()
    rid, otok = j["room_id"], j["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    r = client.post("/rooms/deadbeef/join",
                    params={"name": "X", "invite": team})
    assert r.status_code == 404
    assert r.json()["detail"] == "no such room"
    r = client.post(f"/rooms/{rid}/join",
                    params={"name": "X", "invite": "wrong"})
    assert r.status_code == 403
    assert r.json()["detail"] == "bad or expired invite"
    r = client.post(f"/rooms/{rid}/join",
                    params={"name": "Spacy", "invite": f"  {team}  "})
    assert r.status_code == 200  # pasted whitespace never blocks entry
