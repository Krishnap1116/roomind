"""Model catalog: live list when the key works, verified fallback."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import roomind.meta as meta
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


def test_models_fallback_without_key(client, monkeypatch):
    monkeypatch.setattr(S, "MODEL_API_KEY", "")
    monkeypatch.setattr(meta.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("no network without a key")))
    rid, tok = _room(client)
    j = client.get(f"/rooms/{rid}/models", params={"token": tok}).json()
    assert j["models"] == ["muse-spark-1.3", "muse-spark-1.2",
                           "muse-spark-1.1"]
    assert j["models"][0] == j["default"] == S.SPARK_MODEL
    assert client.get(f"/rooms/{rid}/models",
                      params={"token": "nope"}).status_code == 403


def test_models_live_list_filtered_to_chat(client, monkeypatch):
    monkeypatch.setattr(S, "MODEL_API_KEY", "k")

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"id": "muse-spark-1.2"},
                             {"id": "sam-3.1"},
                             {"id": "muse-image-1.0"},
                             {"id": "muse-voice-transcribe-1.0"},
                             {"id": "muse-spark-1.3-contributor"}]}

    monkeypatch.setattr(meta.httpx, "get", lambda *a, **k: Resp())
    rid, tok = _room(client)
    j = client.get(f"/rooms/{rid}/models", params={"token": tok}).json()
    assert j["models"] == ["muse-spark-1.3", "muse-spark-1.2",
                           "muse-spark-1.3-contributor"]


def test_models_live_failure_falls_back(client, monkeypatch):
    monkeypatch.setattr(S, "MODEL_API_KEY", "k")

    def boom(*a, **k):
        raise ValueError("down")

    monkeypatch.setattr(meta.httpx, "get", boom)
    rid, tok = _room(client)
    j = client.get(f"/rooms/{rid}/models", params={"token": tok}).json()
    assert j["models"][:3] == ["muse-spark-1.3", "muse-spark-1.2",
                               "muse-spark-1.1"]


def test_meter_shows_only_my_model(client):
    rid, otok = _room(client)
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    mtok = client.post(f"/rooms/{rid}/join",
                       params={"name": "M", "invite": team}).json()["token"]
    client.post(f"/rooms/{rid}/model",
                params={"token": mtok, "model": "muse-spark-1.2"})
    ms = {m["name"]: m for m in client.get(
        f"/rooms/{rid}/members", params={"token": otok}).json()}
    assert ms["M"]["model"] == "muse-spark-1.2"
    assert ms["O"]["model"] == ""
    u = client.get(f"/rooms/{rid}/usage",
                   params={"token": otok}).json()
    assert u["default"] == S.SPARK_MODEL
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    assert "<p id=meter>" in page and "<span id=meter" not in page
    assert "· Model: '" in page
    assert "m.model||u.default" not in page  # no room-wide pick list
    assert "members?token" in page  # people list still fetches members
    assert page.index("id=q") < page.index("id=modelsel")
    assert page.index("id=modelsel") < page.index("id=sendbtn")


def test_preset_models_have_windows(client, monkeypatch):
    monkeypatch.setattr(web.agent, "run_loop",
                        lambda *a, **k: {"answer": "ok", "reasons": [],
                                         "remember": [],
                                         "calls": [{"tin": 1, "tout": 1}],
                                         "searched": False})
    rid, tok = _room(client)
    client.post(f"/rooms/{rid}/ask",
                params={"token": tok, "text": "hi",
                        "model": "muse-spark-1.2"})
    u = client.get(f"/rooms/{rid}/usage",
                   params={"token": tok}).json()
    assert u["by_model"]["muse-spark-1.2"]["window"] == 1_000_000
