"""Leave door revokes the leaver's token; custom team sizes respected."""
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


def test_leave_revokes_token_and_custom_uses(client):
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    owner = client.post(f"/rooms/{rid}/join",
                        params={"name": "O", "invite": inv}).json()["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": owner, "uses": 2,
                               "hours": 24}).json()["invite"]
    a = client.post(f"/rooms/{rid}/join",
                    params={"name": "A", "invite": team}).json()["token"]
    assert client.post(f"/rooms/{rid}/leave",
                       params={"token": a}).json() == {"left": rid}
    assert client.get(f"/rooms/{rid}/messages",
                      params={"token": a}).status_code == 403
    b = client.post(f"/rooms/{rid}/join",
                    params={"name": "B", "invite": team}).json()["token"]
    assert client.get(f"/rooms/{rid}/messages",
                      params={"token": b}).status_code == 200


def test_leaver_sees_gone_page_and_leave_confirms(client):
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    owner = client.post(f"/rooms/{rid}/join",
                        params={"name": "O", "invite": inv}).json()["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": owner, "uses": 2,
                               "hours": 24}).json()["invite"]
    a = client.post(f"/rooms/{rid}/join",
                    params={"name": "A", "invite": team}).json()["token"]
    page = client.get(f"/rooms/{rid}/app", params={"token": a}).text
    assert "Leave this room? Your access ends at once" in page
    assert "You are the last seat." in page
    assert "No one can access it after." in page
    client.post(f"/rooms/{rid}/leave", params={"token": a})
    gone = client.get(f"/rooms/{rid}/app", params={"token": a})
    assert gone.status_code == 200
    assert "You are no longer in this room" in gone.text
    assert "bad token" not in gone.text


def test_closed_room_shows_closed_page(client):
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    owner = client.post(f"/rooms/{rid}/join",
                        params={"name": "O", "invite": inv}).json()["token"]
    client.delete(f"/rooms/{rid}", params={"token": owner})
    shut = client.get(f"/rooms/{rid}/app", params={"token": owner})
    assert shut.status_code == 200
    assert "This room is closed" in shut.text
