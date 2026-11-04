"""Artifacts: versioned docs/plans/patches with approvals, humans apply."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

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
    j = client.post("/rooms", params={"mission": "Ship Friday",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    mtok = client.post(f"/rooms/{rid}/join",
                       params={"name": "M", "invite": team}).json()["token"]
    return rid, otok, mtok


def test_artifact_create_list_get(client):
    rid, otok, mtok = _two(client)
    assert client.post(f"/rooms/{rid}/artifacts",
                       params={"token": "nope", "title": "t",
                               "body": "b"}).status_code == 403
    assert client.post(f"/rooms/{rid}/artifacts",
                       params={"token": mtok, "title": " ",
                               "body": "b"}).status_code == 400
    assert client.post(f"/rooms/{rid}/artifacts",
                       params={"token": mtok, "title": "t",
                               "body": " "}).status_code == 400
    a = client.post(f"/rooms/{rid}/artifacts",
                    params={"token": mtok, "title": "Launch plan",
                            "kind": "plan",
                            "body": "step one"}).json()
    assert a["version"] == 1 and a["status"] == "draft"
    assert a["kind"] == "plan" and a["created_by"] == "M"
    items = client.get(f"/rooms/{rid}/artifacts",
                       params={"token": otok}).json()
    assert [x["title"] for x in items] == ["Launch plan"]
    one = client.get(f"/rooms/{rid}/artifacts/{a['id']}",
                     params={"token": otok}).json()
    assert one["body"] == "step one"
    assert client.get(f"/rooms/{rid}/artifacts/999",
                      params={"token": otok}).status_code == 404


def test_artifact_versions(client):
    rid, otok, mtok = _two(client)
    a = client.post(f"/rooms/{rid}/artifacts",
                    params={"token": mtok, "title": "Doc",
                            "body": "v1"}).json()
    aid = a["id"]
    assert client.post(f"/rooms/{rid}/artifacts/{aid}/edit",
                       params={"token": mtok,
                               "body": " "}).status_code == 400
    b = client.post(f"/rooms/{rid}/artifacts/{aid}/edit",
                    params={"token": otok, "title": "Doc v2",
                            "body": "v2"}).json()
    assert b["version"] == 2 and b["title"] == "Doc v2"
    vs = client.get(f"/rooms/{rid}/artifacts/{aid}/versions",
                    params={"token": mtok}).json()
    assert [(v["version"], v["body"], v["edited_by"]) for v in vs] == [
        (1, "v1", "M"), (2, "v2", "O")]
    client.post(f"/rooms/{rid}/artifacts/{aid}/propose",
                params={"token": mtok})
    client.post(f"/rooms/{rid}/artifacts/{aid}/approve",
                params={"token": otok})
    c = client.post(f"/rooms/{rid}/artifacts/{aid}/edit",
                    params={"token": mtok, "body": "v3"}).json()
    assert c["version"] == 3 and c["status"] == "draft"
    assert c["approved_by"] == ""


def test_artifact_approvals(client):
    rid, otok, mtok = _two(client)
    a = client.post(f"/rooms/{rid}/artifacts",
                    params={"token": mtok, "title": "Patch",
                            "kind": "patch",
                            "body": "diff here"}).json()
    aid = a["id"]
    assert client.post(f"/rooms/{rid}/artifacts/{aid}/approve",
                       params={"token": mtok}).status_code == 400
    assert client.post(f"/rooms/{rid}/artifacts/{aid}/apply",
                       params={"token": mtok}).status_code == 400
    assert client.post(f"/rooms/{rid}/artifacts/{aid}/propose",
                       params={"token": mtok}).json()["status"] == "proposed"
    assert client.post(f"/rooms/{rid}/artifacts/{aid}/propose",
                       params={"token": mtok}).status_code == 400
    done = client.post(f"/rooms/{rid}/artifacts/{aid}/approve",
                       params={"token": mtok}).json()
    assert done["status"] == "approved" and done["approved_by"] == "M"
    assert client.post(f"/rooms/{rid}/artifacts/{aid}/apply",
                       params={"token": otok}).json()["status"] == "applied"


def test_artifact_lock(client):
    rid, otok, mtok = _two(client)
    a = client.post(f"/rooms/{rid}/artifacts",
                    params={"token": mtok, "title": "T",
                            "body": "b"}).json()
    client.post(f"/rooms/{rid}/lock", params={"token": otok, "on": True})
    assert client.post(f"/rooms/{rid}/artifacts",
                       params={"token": mtok, "title": "T2",
                               "body": "b"}).status_code == 403
    assert client.post(f"/rooms/{rid}/artifacts/{a['id']}/edit",
                       params={"token": mtok,
                               "body": "b2"}).status_code == 403
    assert client.post(f"/rooms/{rid}/artifacts/{a['id']}/propose",
                       params={"token": mtok}).status_code == 403
    assert client.get(f"/rooms/{rid}/artifacts",
                      params={"token": mtok}).json()[0]["title"] == "T"
    assert client.get(f"/rooms/{rid}/artifacts/{a['id']}/versions",
                      params={"token": mtok}).json()[0]["body"] == "b"


def test_artifact_ui_markers(client):
    rid, otok, mtok = _two(client)
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    for marker in ("id=arts", "artList()", "artHTML(", "artNew()",
                   "artCreate()", "artEdit(", "artSave(", "artAct(",
                   "artHist(", ">+ Doc</button>",
                   "kind==='artifact'"):
        assert marker in page
