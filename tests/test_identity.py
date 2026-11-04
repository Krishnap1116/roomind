"""Identity slice: same-name members stay distinct, solo names untouched."""
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


def test_every_seat_tagged_with_nick(client):
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    otok = client.post(f"/rooms/{rid}/join",
                       params={"name": "Owner", "invite": inv}).json()["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    ta = client.post(f"/rooms/{rid}/join",
                     params={"name": "Ana", "invite": team}).json()["token"]
    tb = client.post(f"/rooms/{rid}/join",
                     params={"name": "Ana", "invite": team}).json()["token"]
    con = store.connect()
    row = lambda t: con.execute(
        "SELECT id, nick FROM members WHERE token=?", (t,)).fetchone()
    oida, onick = row(otok)
    ida, na = row(ta)
    idb, nb = row(tb)
    store.post_message(con, rid, "Ana", "first", author_id=ida)
    store.post_message(con, rid, "Ana", "second", author_id=idb)
    store.post_message(con, rid, "Owner", "hi", author_id=oida)
    store.post_message(con, rid, "Ben", "hey")
    con.close()
    msgs = client.get(f"/rooms/{rid}/messages",
                      params={"token": otok}).json()
    ana_tags = sorted(m.get("tag") for m in msgs if m["author"] == "Ana")
    assert ana_tags == sorted([na, nb]) and na != nb
    assert [m for m in msgs if m["author"] == "Owner"][0]["tag"] == onick
    assert "tag" not in [m for m in msgs if m["author"] == "Ben"][0]


def test_brief_sees_tagged_names(client, monkeypatch):
    seen = {}

    def fake(api_key, base, model, history, prompt, timeout=60.0, notes=None, system=None,
             effort=None):
        seen["authors"] = [m["author"] for m in history]
        return {"answer": "{}", "reasons": [], "remember": [], "tin": 1,
                "tout": 1}

    monkeypatch.setattr(web.meta, "spark_reply", fake)
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    otok = client.post(f"/rooms/{rid}/join",
                       params={"name": "Owner", "invite": inv}).json()["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    con = store.connect()
    con.execute("INSERT INTO members (id, room, name, role, token)"
                " VALUES ('aa11', ?, 'Ana', 'member', 't1')", (rid,))
    con.execute("INSERT INTO members (id, room, name, role, token)"
                " VALUES ('zz99', ?, 'Ana', 'member', 't2')", (rid,))
    con.commit()
    store.post_message(con, rid, "Ana", "x", author_id="aa11")
    con.close()
    client.get(f"/rooms/{rid}/brief", params={"token": otok})
    assert any("·" in a for a in seen["authors"])
