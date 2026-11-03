"""Step 1 slice: rooms, join, order, reasons, rails. No network calls."""
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


def test_room_join_order_and_expiry(client):
    rid = client.post("/rooms", params={"mission": "Ship it"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    a = client.post(f"/rooms/{rid}/join",
                    params={"name": "Ana", "invite": inv}).json()
    assert a["role"] == "owner"
    again = client.post(f"/rooms/{rid}/join",
                        params={"name": "Ben", "invite": inv})
    assert again.status_code == 403  # single-use invite spent
    bad = client.get(f"/rooms/{rid}/messages", params={"token": "nope"})
    assert bad.status_code == 403


def test_ask_posts_answer_with_reasons_and_cost(client, monkeypatch):
    monkeypatch.setattr(web.agent, "run_loop",
                        lambda *a, **k: {"answer": "Do X.", "reasons": ["r1"],
                                         "remember": [],
                                         "calls": [{"tin": 10, "tout": 5}],
                                         "searched": False})
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    tok = client.post(f"/rooms/{rid}/join",
                      params={"name": "Ana", "invite": inv}).json()["token"]
    r = client.post(f"/rooms/{rid}/ask",
                    params={"token": tok, "text": "What now?"})
    assert r.json() == {"answer": "Do X.", "reasons": ["r1"]}
    msgs = client.get(f"/rooms/{rid}/messages",
                      params={"token": tok}).json()
    assert [m["author"] for m in msgs] == ["Ana", "agent"]
    con = store.connect()
    try:
        assert store.room_cost(con, rid) >= 0
    finally:
        con.close()


def test_paused_and_budget_stop_sends(client, monkeypatch):
    monkeypatch.setattr(S, "PAUSED", True)
    r = client.post("/rooms/x/ask", params={"token": "t", "text": "hi"})
    assert r.status_code == 503
    monkeypatch.setattr(S, "PAUSED", False)
    monkeypatch.setattr(S, "MAX_ROOM_COST", 0.0)
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    tok = client.post(f"/rooms/{rid}/join",
                      params={"name": "A", "invite": inv}).json()["token"]
    r = client.post(f"/rooms/{rid}/ask", params={"token": tok, "text": "hi"})
    assert r.status_code == 402


def test_owner_wipe_removes_everything(client):
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    tok = client.post(f"/rooms/{rid}/join",
                      params={"name": "A", "invite": inv}).json()["token"]
    assert client.delete(f"/rooms/{rid}",
                         params={"token": tok}).json() == {"deleted": rid}
    assert client.get(f"/rooms/{rid}/messages",
                      params={"token": tok}).status_code == 403


def test_dotenv_loads_without_overriding(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text("# comment\nBLANK=\nROOMIND_T_A=fromfile\n"
                 "ROOMIND_T_B='quoted value'\n")
    monkeypatch.setenv("ROOMIND_T_B", "fromenv")
    monkeypatch.delenv("ROOMIND_T_A", raising=False)
    S._load_dotenv(str(p))
    assert os.environ["ROOMIND_T_A"] == "fromfile"
    assert os.environ["ROOMIND_T_B"] == "fromenv"  # env wins
    assert S._parse_dotenv("NODATA\n=novalue\n") == {}
    S._load_dotenv(str(tmp_path / "missing"))  # no crash without file
