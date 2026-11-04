"""Room tasks: assigned work with due dates, done and timelines."""
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


def test_task_create_list_flags(client):
    rid, otok, mtok = _two(client)
    assert client.post(f"/rooms/{rid}/tasks",
                       params={"token": "nope",
                               "title": "t"}).status_code == 403
    assert client.post(f"/rooms/{rid}/tasks",
                       params={"token": mtok,
                               "title": " "}).status_code == 400
    t = client.post(f"/rooms/{rid}/tasks",
                    params={"token": mtok, "title": "Cut the trailer",
                            "details": "60 seconds",
                            "assignee": "M",
                            "due": "Friday"}).json()
    assert t["status"] == "open" and t["assignee"] == "M"
    assert t["created_by"] == "M"
    rows = client.get(f"/rooms/{rid}/tasks",
                      params={"token": otok}).json()
    assert [r["title"] for r in rows] == ["Cut the trailer"]
    assert "flag" in rows[0] and "due_date" in rows[0]


def test_task_edit_done_reopen(client):
    rid, otok, mtok = _two(client)
    t = client.post(f"/rooms/{rid}/tasks",
                    params={"token": mtok, "title": "Draft",
                            "assignee": "M"}).json()
    tid = t["id"]
    e = client.post(f"/rooms/{rid}/tasks/{tid}/edit",
                    params={"token": otok, "assignee": "O",
                            "due": "Friday"}).json()
    assert e["title"] == "Draft" and e["assignee"] == "O"
    assert e["due_text"] == "Friday"
    assert client.post(f"/rooms/{rid}/tasks/999/edit",
                       params={"token": otok}).status_code == 404
    assert client.post(f"/rooms/{rid}/tasks/{tid}/done",
                       params={"token": mtok}).json()["status"] == "done"
    assert client.post(f"/rooms/{rid}/tasks/{tid}/done",
                       params={"token": mtok}).json()["status"] == "done"
    assert client.post(f"/rooms/{rid}/tasks/{tid}/reopen",
                       params={"token": otok}).json()["status"] == "open"
    rows = client.get(f"/rooms/{rid}/tasks",
                      params={"token": otok}).json()
    assert rows[0]["status"] == "open"


def test_task_done_first_timeline(client):
    rid, otok, mtok = _two(client)
    a = client.post(f"/rooms/{rid}/tasks",
                    params={"token": mtok, "title": "First"}).json()
    client.post(f"/rooms/{rid}/tasks",
                params={"token": mtok, "title": "Second"})
    client.post(f"/rooms/{rid}/tasks/{a['id']}/done",
                params={"token": mtok})
    rows = client.get(f"/rooms/{rid}/tasks",
                      params={"token": otok}).json()
    assert [r["title"] for r in rows] == ["Second", "First"]


def test_task_delete(client):
    rid, otok, mtok = _two(client)
    t = client.post(f"/rooms/{rid}/tasks",
                    params={"token": mtok, "title": "Gone"}).json()
    assert client.post(f"/rooms/{rid}/tasks/999/delete",
                       params={"token": mtok}).status_code == 404
    assert client.post(f"/rooms/{rid}/tasks/{t['id']}/delete",
                       params={"token": mtok}).json() == {"deleted": t["id"]}
    assert client.get(f"/rooms/{rid}/tasks",
                      params={"token": otok}).json() == []


def test_task_lock(client):
    rid, otok, mtok = _two(client)
    t = client.post(f"/rooms/{rid}/tasks",
                    params={"token": mtok, "title": "T"}).json()
    client.post(f"/rooms/{rid}/lock", params={"token": otok, "on": True})
    assert client.post(f"/rooms/{rid}/tasks",
                       params={"token": mtok,
                               "title": "T2"}).status_code == 403
    assert client.post(f"/rooms/{rid}/tasks/{t['id']}/edit",
                       params={"token": mtok,
                               "title": "X"}).status_code == 403
    assert client.post(f"/rooms/{rid}/tasks/{t['id']}/done",
                       params={"token": mtok}).status_code == 403
    assert client.post(f"/rooms/{rid}/tasks/{t['id']}/delete",
                       params={"token": mtok}).status_code == 403
    assert client.get(f"/rooms/{rid}/tasks",
                      params={"token": mtok}).json()[0]["title"] == "T"


def test_task_ui_markers(client):
    rid, otok, mtok = _two(client)
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    for marker in ("id=tasks", "taskList()", "taskHTML(", "taskNew()",
                   "taskCreate()", "taskEdit(", "taskSave(",
                   "taskDone(", "taskReopen(", "taskDel(",
                   ">+ Task</button>", "kind==='task'"):
        assert marker in page
