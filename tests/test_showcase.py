"""Export pack plus showcase link. Reads stay open, secrets never leak."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import roomind.web as web
import roomind as S
import roomind.store as store


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


def _fill(client, rid, otok, mtok):
    con = store.connect()
    store.post_message(con, rid, "M", "hello team", kind="chat")
    con.close()
    client.post(f"/rooms/{rid}/ledger",
                params={"token": mtok, "what": "ship friday",
                        "who": "M"})
    client.post(f"/rooms/{rid}/artifacts",
                params={"token": mtok, "title": "Launch plan",
                        "body": "steps"})
    client.post(f"/rooms/{rid}/tasks",
                params={"token": mtok, "title": "Cut trailer"})
    client.post(f"/rooms/{rid}/polls",
                params={"token": mtok, "question": "Ship?",
                        "options": json.dumps(["Yes", "No"])})


def test_export_pack(client):
    rid, otok, mtok = _two(client)
    _fill(client, rid, otok, mtok)
    assert client.get(f"/rooms/{rid}/export",
                      params={"token": "nope"}).status_code == 403
    r = client.get(f"/rooms/{rid}/export", params={"token": mtok})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert f"room-{rid}.json" in r.headers["content-disposition"]
    pack = json.loads(r.text)
    assert pack["mission"] == "Ship Friday"
    for key in ("members", "messages", "ledger", "proposals",
                "artifacts", "tasks", "polls", "reminders"):
        assert key in pack
    assert pack["ledger"][0]["what"] == "ship friday"
    assert pack["artifacts"][0]["versions"][0]["body"] == "steps"
    assert pack["polls"][0]["options"] == ["Yes", "No"]
    assert '"token"' not in r.text
    assert "sides" not in pack and "sides_hidden" not in pack


def test_export_include_sides(client):
    rid, otok, mtok = _two(client)
    s = client.post(f"/rooms/{rid}/side",
                    params={"token": mtok, "mission": "S"}).json()
    sid = s["room_id"]
    con = store.connect()
    store.post_message(con, sid, "M", "side secret", kind="chat")
    con.close()
    mine = client.get(f"/rooms/{rid}/export",
                      params={"token": mtok,
                              "include_sides": True}).json()
    assert mine["sides_hidden"] == 0
    assert [p["mission"] for p in mine["sides"]] == ["S"]
    assert "side secret" in json.dumps(mine["sides"])
    other = client.get(f"/rooms/{rid}/export",
                       params={"token": otok,
                               "include_sides": True}).json()
    assert other["sides"] == [] and other["sides_hidden"] == 1
    assert "side secret" not in json.dumps(other)


def test_showcase_flow(client):
    rid, otok, mtok = _two(client)
    _fill(client, rid, otok, mtok)
    assert client.get(f"/rooms/{rid}/showcase",
                      params={"token": otok}).json() == {"url": ""}
    assert client.post(f"/rooms/{rid}/showcase",
                       params={"token": mtok}).status_code == 403
    assert client.get("/show/nope").status_code == 404
    url = client.post(f"/rooms/{rid}/showcase",
                      params={"token": otok}).json()["url"]
    assert url.startswith("/show/")
    again = client.post(f"/rooms/{rid}/showcase",
                        params={"token": otok}).json()["url"]
    assert again == url
    page = client.get(url).text
    for marker in ("Ship Friday", "ship friday", "Launch plan",
                   "Cut trailer", "Ship?", "hello team",
                   "Side rooms stay private"):
        assert marker in page
    assert client.delete(f"/rooms/{rid}/showcase",
                         params={"token": mtok}).status_code == 403
    assert client.delete(f"/rooms/{rid}/showcase",
                         params={"token": otok}).json() == {
                             "revoked": True}
    assert client.get(url).status_code == 404
    assert client.get(f"/rooms/{rid}/showcase",
                      params={"token": otok}).json() == {"url": ""}


def test_showcase_side_wall(client):
    rid, otok, mtok = _two(client)
    s = client.post(f"/rooms/{rid}/side",
                    params={"token": mtok, "mission": "S"}).json()
    sid, stok = s["room_id"], s["token"]
    con = store.connect()
    store.post_message(con, sid, "M", "side secret", kind="chat")
    con.close()
    client.post(f"/rooms/{sid}/ledger",
                params={"token": stok, "what": "sideonly plan",
                        "who": "M"})
    client.post(f"/rooms/{sid}/share-back", params={"token": stok})
    url = client.post(f"/rooms/{rid}/showcase",
                      params={"token": otok}).json()["url"]
    page = client.get(url).text
    assert "reports (by M)" in page
    assert "sideonly plan" in page
    assert "side secret" not in page


def test_showcase_lock(client):
    rid, otok, mtok = _two(client)
    _fill(client, rid, otok, mtok)
    url = client.post(f"/rooms/{rid}/showcase",
                      params={"token": otok}).json()["url"]
    client.post(f"/rooms/{rid}/lock", params={"token": otok, "on": True})
    assert client.get(f"/rooms/{rid}/export",
                      params={"token": mtok}).status_code == 200
    assert client.get(url).status_code == 200


def test_showcase_ui_markers(client):
    rid, otok, mtok = _two(client)
    owner = client.get(f"/rooms/{rid}/app",
                       params={"token": otok}).text
    for marker in (">Download</button>", ">Read-only link</button>",
                   "exportRoom(", "showcase(", "revokeShowcase(",
                   "id=expside", "Include sides"):
        assert marker in owner
    guest = client.get(f"/rooms/{rid}/app",
                       params={"token": mtok}).text
    assert ">Download</button>" in guest
    assert ">Read-only link</button>" not in guest
