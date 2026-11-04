"""Red-team hour: deliberate ranked attacks with receipts, resolvable."""
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


ATTACK = {"verdict": "Plan fails on testing",
          "flaws": [{"flaw": "no tests", "receipt": "M: ship it",
                     "severity": "high"},
                    {"flaw": "one owner", "receipt": "[L1]",
                     "severity": "med"}],
          "strongest": "scope is tight"}


def _two(client):
    j = client.post("/rooms", params={"mission": "Ship Friday",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    mtok = client.post(f"/rooms/{rid}/join",
                       params={"name": "M", "invite": team}).json()["token"]
    return rid, otok, mtok


def _plan(client, rid, otok, mtok):
    con = store.connect()
    store.post_message(con, rid, "M", "lets ship it friday", kind="chat")
    con.close()
    client.post(f"/rooms/{rid}/ledger",
                params={"token": mtok, "what": "ship friday",
                        "who": "M"})
    client.post(f"/rooms/{rid}/artifacts",
                params={"token": mtok, "title": "Launch plan",
                        "body": "steps"})
    client.post(f"/rooms/{rid}/tasks",
                params={"token": mtok, "title": "Cut trailer",
                        "assignee": "M"})


def _fake(seen, answer=None):
    def fake(api_key, base, model, history, prompt, timeout=60.0,
             notes=None, effort=None, hist_n=None):
        seen["dump"] = json.dumps(history) + prompt
        seen["effort"] = effort
        seen["hist_n"] = hist_n
        return {"answer": json.dumps(answer if answer is not None
                                     else ATTACK),
                "reasons": [], "remember": [], "tin": 1, "tout": 1}
    return fake


def test_redteam_runs_and_posts(client, monkeypatch):
    rid, otok, mtok = _two(client)
    _plan(client, rid, otok, mtok)
    seen = {}
    monkeypatch.setattr(web.meta, "spark_reply", _fake(seen))
    r = client.post(f"/rooms/{rid}/redteam",
                    params={"token": mtok}).json()
    assert r["triggered"] is True and r["reason"] == ""
    card = r["card"]
    assert card["verdict"] == "Plan fails on testing"
    assert [f["severity"] for f in card["flaws"]] == ["high", "med"]
    assert card["strongest"] == "scope is tight"
    assert "lets ship it friday" in seen["dump"]
    assert "[L" in seen["dump"] and "Launch plan" in seen["dump"]
    assert "Cut trailer" in seen["dump"]
    assert seen["effort"] == "high"
    assert seen["hist_n"] == 30
    kinds = [m["kind"] for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()]
    assert "redteam" in kinds


def test_redteam_cooldown(client, monkeypatch):
    rid, otok, mtok = _two(client)
    _plan(client, rid, otok, mtok)
    monkeypatch.setattr(web.meta, "spark_reply", _fake({}))
    assert client.post(f"/rooms/{rid}/redteam",
                       params={"token": mtok}).json()["triggered"] is True
    again = client.post(f"/rooms/{rid}/redteam",
                        params={"token": otok}).json()
    assert again["triggered"] is False
    assert again["reason"] == "cooling down"


def test_redteam_resolve(client, monkeypatch):
    rid, otok, mtok = _two(client)
    _plan(client, rid, otok, mtok)
    monkeypatch.setattr(web.meta, "spark_reply", _fake({}))
    mid = client.post(f"/rooms/{rid}/redteam",
                      params={"token": mtok}).json()["card"]["id"]
    assert client.post(f"/rooms/{rid}/redteam/{mid}/resolve",
                       params={"token": otok,
                               "verdict": "maybe"}).status_code == 400
    assert client.post(f"/rooms/{rid}/redteam/999/resolve",
                       params={"token": otok,
                               "verdict": "fixed"}).status_code == 404
    chat_id = [m["id"] for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()
        if m["kind"] == "chat"][0]
    assert client.post(f"/rooms/{rid}/redteam/{chat_id}/resolve",
                       params={"token": otok,
                               "verdict": "fixed"}).status_code == 404
    out = client.post(f"/rooms/{rid}/redteam/{mid}/resolve",
                      params={"token": mtok,
                              "verdict": "fixed"}).json()
    assert out == {"id": mid, "resolved": "fixed"}
    rated = [m for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()
        if m["id"] == mid][0]
    assert rated["rating"] == 1


def test_redteam_gates(client, monkeypatch):
    rid, otok, mtok = _two(client)
    monkeypatch.setattr(web.meta, "spark_reply", _fake({}))
    assert client.post(f"/rooms/{rid}/redteam",
                       params={"token": "nope"}).status_code == 403
    fresh = client.post(f"/rooms/{rid}/redteam",
                        params={"token": mtok}).json()
    assert fresh["triggered"] is False
    assert fresh["reason"] == "empty room"
    _plan(client, rid, otok, mtok)
    client.post(f"/rooms/{rid}/lock", params={"token": otok, "on": True})
    assert client.post(f"/rooms/{rid}/redteam",
                       params={"token": mtok}).status_code == 403


def test_redteam_bad_model_and_mute(client, monkeypatch):
    rid, otok, mtok = _two(client)
    _plan(client, rid, otok, mtok)
    monkeypatch.setattr(web.meta, "spark_reply",
                        _fake({}, answer={"nope": True}))
    bad = client.post(f"/rooms/{rid}/redteam",
                      params={"token": mtok}).json()
    assert bad["triggered"] is False
    assert bad["reason"] == "attack failed"
    monkeypatch.setattr(web.meta, "spark_reply", _fake({}))
    client.post(f"/rooms/{rid}/dissent/mute",
                params={"token": otok, "on": True})
    good = client.post(f"/rooms/{rid}/redteam",
                       params={"token": mtok}).json()
    assert good["triggered"] is True


def test_redteam_section_lists_cards(client, monkeypatch):
    import roomind.dissent as dissent
    assert "padded flaw is worse than silence" in dissent.REDTEAM_PROMPT
    rid, otok, mtok = _two(client)
    _plan(client, rid, otok, mtok)
    monkeypatch.setattr(web.meta, "spark_reply", _fake({}))
    assert client.get(f"/rooms/{rid}/redteam",
                      params={"token": "nope"}).status_code == 403
    assert client.get(f"/rooms/{rid}/redteam",
                      params={"token": otok}).json() == []
    mid = client.post(f"/rooms/{rid}/redteam",
                      params={"token": mtok}).json()["card"]["id"]
    cards = client.get(f"/rooms/{rid}/redteam",
                       params={"token": otok}).json()
    assert [c["id"] for c in cards] == [mid]
    assert cards[0]["verdict"] == "Plan fails on testing"
    assert len(cards[0]["flaws"]) == 2


def test_redteam_ui_markers(client):
    rid, otok, mtok = _two(client)
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    for marker in (">Attack our plan</button>", "redteam()",
                   "id=redsec", "redList();", "redHTML(",
                   "redResolve(", "kind==='redteam'",
                   "Attacking the plan"):
        assert marker in page
    assert "showRedteam(" not in page


def test_redteam_retries_malformed_reply_once(client, monkeypatch):
    calls = []
    prompts = []

    def flaky(api_key, base, model, history, prompt, timeout=60.0,
              notes=None, effort=None, hist_n=None):
        calls.append(1)
        prompts.append(prompt)
        if len(calls) == 1:
            return {"answer": "not json {{{", "reasons": [],
                    "remember": [], "tin": 1, "tout": 1}
        return {"answer": json.dumps(ATTACK), "reasons": [],
                "remember": [], "tin": 1, "tout": 1}

    rid, otok, mtok = _two(client)
    _plan(client, rid, otok, mtok)
    monkeypatch.setattr(web.meta, "spark_reply", flaky)
    out = client.post(f"/rooms/{rid}/redteam",
                      params={"token": otok}).json()
    assert out["triggered"] is True
    assert len(calls) == 2
    assert prompts[1].endswith("Return ONLY the JSON object, no other words.")


def test_redteam_quiet_after_two_bad_replies(client, monkeypatch):
    calls = []

    def broken(*a, **k):
        calls.append(1)
        raise RuntimeError("down")

    rid, otok, mtok = _two(client)
    _plan(client, rid, otok, mtok)
    monkeypatch.setattr(web.meta, "spark_reply", broken)
    out = client.post(f"/rooms/{rid}/redteam",
                      params={"token": otok}).json()
    assert out["triggered"] is False
    assert out["reason"] == "attack failed"
    assert len(calls) == 2


def test_resolve_posts_history_note(client, monkeypatch):
    seen = {}
    rid, otok, mtok = _two(client)
    _plan(client, rid, otok, mtok)
    monkeypatch.setattr(web.meta, "spark_reply", _fake(seen))
    mid = client.post(f"/rooms/{rid}/redteam",
                      params={"token": otok}).json()["card"]["id"]
    out = client.post(f"/rooms/{rid}/redteam/{mid}/resolve",
                      params={"token": otok, "verdict": "fixed"}).json()
    assert out == {"id": mid, "resolved": "fixed"}
    bodies = [m["body"] for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()]
    assert "O marked attack fixed: Plan fails on testing" in bodies
