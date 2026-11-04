"""Deadline reminders: dates, CRUD, schedule, lazy nudge, page."""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import roomind.remind as remind
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


def _two(client):
    j = client.post("/rooms", params={"mission": "Ship Friday",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    mtok = client.post(f"/rooms/{rid}/join",
                       params={"name": "M", "invite": team}).json()["token"]
    return rid, otok, mtok


def _at(monkeypatch, day, hour, minute=0):
    monkeypatch.setattr(remind, "now_local",
                        lambda: datetime.datetime(2026, 11, day, hour,
                                                  minute))


def test_parse_due_words():
    tue = datetime.date(2026, 11, 3)  # a Tuesday
    assert remind.parse_due("today", tue) == "2026-11-03"
    assert remind.parse_due("tomorrow", tue) == "2026-11-04"
    assert remind.parse_due("Friday", tue) == "2026-11-06"
    assert remind.parse_due("tuesday", tue) == "2026-11-03"
    assert remind.parse_due("2026-12-25", tue) == "2026-12-25"
    assert remind.parse_due("2026-13-99", tue) == ""
    assert remind.parse_due("soon-ish", tue) == ""
    assert remind.parse_due("", tue) == ""
    assert remind.parse_due("by Friday", tue) == "2026-11-06"
    assert remind.parse_due("By tomorrow", tue) == "2026-11-04"
    assert remind.parse_due("tonight", tue) == "2026-11-03"
    assert remind.parse_due("by tonight", tue) == "2026-11-03"


def test_sched_normalize_and_due():
    assert remind.normalize_at("9:00") == "09:00"
    assert remind.normalize_at(" 18:30 ") == "18:30"
    assert remind.normalize_at("OFF") == "off"
    assert remind.normalize_at("hourly") is None
    assert remind.normalize_at("25:00") is None
    assert remind.normalize_at("9:99") is None
    assert remind.normalize_at("9am") is None
    at = lambda d, h, m=0: datetime.datetime(2026, 11, d, h, m)
    assert remind.due_at("09:00", at(3, 9, 0), "") is True
    assert remind.due_at("09:00", at(3, 8, 59), "") is False
    assert remind.due_at("09:00", at(3, 15, 0), "") is True
    assert remind.due_at("09:00", at(3, 15, 0), "2026-11-03") is False
    assert remind.due_at("09:00", at(4, 9, 0), "2026-11-03") is True
    assert remind.due_at("off", at(3, 15, 0), "") is False
    assert remind.due_at("bogus", at(3, 15, 0), "") is False


def test_crud_open_to_everyone(client):
    rid, otok, mtok = _two(client)
    assert client.post(f"/rooms/{rid}/reminders",
                       params={"token": mtok, "text": "   "}
                       ).status_code == 400
    mid = client.post(f"/rooms/{rid}/reminders",
                      params={"token": mtok, "text": "pay invoice",
                              "due": "tomorrow", "owner": "M"}
                      ).json()["id"]
    rows = client.get(f"/rooms/{rid}/reminders",
                      params={"token": otok}).json()["reminders"]
    assert [(r["text"], r["due_text"], r["owner"]) for r in rows] == [
        ("pay invoice", "tomorrow", "M")]
    assert rows[0]["due_date"] == "2026-11-04"  # pinned clock + tomorrow
    assert client.post(f"/rooms/{rid}/reminders/{mid}",
                       params={"token": mtok, "text": "pay invoice!",
                               "done": True}).json() == {"updated": mid}
    rows = client.get(f"/rooms/{rid}/reminders",
                      params={"token": otok}).json()["reminders"]
    assert (rows[0]["text"], rows[0]["done"]) == ("pay invoice!", 1)
    assert client.post(f"/rooms/{rid}/reminders/999",
                       params={"token": mtok, "text": "x"}
                       ).status_code == 404
    assert client.delete(f"/rooms/{rid}/reminders/{mid}",
                         params={"token": mtok}
                         ).json() == {"deleted": mid}
    assert client.get(f"/rooms/{rid}/reminders",
                      params={"token": otok}
                      ).json()["reminders"] == []


def test_time_manager_only(client):
    rid, otok, mtok = _two(client)
    assert client.get(f"/rooms/{rid}/reminders",
                      params={"token": otok}).json()["sched"] == "09:00"
    assert client.post(f"/rooms/{rid}/remind-time",
                       params={"token": mtok, "at": "18:00"}
                       ).status_code == 403
    assert client.post(f"/rooms/{rid}/remind-time",
                       params={"token": otok, "at": "hourly"}
                       ).status_code == 400
    assert client.post(f"/rooms/{rid}/remind-time",
                       params={"token": otok, "at": "9:30"}
                       ).json() == {"sched": "09:30"}
    assert client.post(f"/rooms/{rid}/remind-time",
                       params={"token": otok, "at": "off"}
                       ).json() == {"sched": "off"}


def test_remind_now_posts_nudge(client):
    rid, otok, mtok = _two(client)
    client.post(f"/rooms/{rid}/ledger",
                params={"token": otok, "what": "ship it",
                        "deadline": "yesterday"})
    m1 = client.post(f"/rooms/{rid}/reminders",
                     params={"token": mtok, "text": "call ana",
                             "due": "today"}).json()["id"]
    m2 = client.post(f"/rooms/{rid}/reminders",
                     params={"token": mtok, "text": "old news"}
                     ).json()["id"]
    client.post(f"/rooms/{rid}/reminders/{m2}",
                params={"token": mtok, "done": True})
    assert client.post(f"/rooms/{rid}/remind-now",
                       params={"token": mtok}).json() == {"posted": True}
    bodies = [m["body"] for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()]
    assert len(bodies) == 1
    nudge = bodies[0]
    assert nudge.startswith("Reminder — Ship Friday")
    assert "ship it" in nudge and "OVERDUE" in nudge
    assert "call ana" in nudge and "DUE TODAY" in nudge
    assert "old news" not in nudge
    assert m1 and m2


def test_ledger_stamp_mirrors_reminder(client):
    rid, otok, mtok = _two(client)
    client.post(f"/rooms/{rid}/ledger",
                params={"token": otok, "what": "ship it",
                        "who": "O", "deadline": "Friday"})
    client.post(f"/rooms/{rid}/ledger",
                params={"token": otok, "what": "no date yet"})
    rows = client.get(f"/rooms/{rid}/reminders",
                      params={"token": otok}).json()["reminders"]
    assert [(r["text"], r["due_text"], r["owner"]) for r in rows] == [
        ("ship it", "Friday", "O")]
    assert rows[0]["due_date"] == "2026-11-06"
    client.post(f"/rooms/{rid}/ledger",
                params={"token": otok, "what": "ship it",
                        "deadline": "Friday"})
    rows = client.get(f"/rooms/{rid}/reminders",
                      params={"token": otok}).json()["reminders"]
    assert len(rows) == 1  # same text never mirrors twice


def test_ledger_update_refreshes_mirror(client):
    rid, otok, mtok = _two(client)
    lid = client.post(f"/rooms/{rid}/ledger",
                      params={"token": otok, "what": "ship it",
                              "deadline": "Friday"}).json()["id"]
    con = store.connect()
    try:
        assert store.update_ledger(con, rid, lid, "ship v2", "M", "",
                                   "tomorrow")
        rows = store.list_reminders(con, rid)
        assert [(r["text"], r["due_text"], r["owner"]) for r in rows] == [
            ("ship v2", "tomorrow", "M")]
        assert store.delete_reminder(con, rid, rows[0]["id"])
        assert store.update_ledger(con, rid, lid, "ship v3", "M", "",
                                   "today")
        assert store.list_reminders(con, rid) == []  # human cut stays cut
    finally:
        con.close()


def test_nudge_casts_popup_event(client):
    rid, otok, mtok = _two(client)
    client.post(f"/rooms/{rid}/reminders",
                params={"token": mtok, "text": "standup"})
    seen = []

    class Fake:
        async def send_json(self, p):
            seen.append(p)

    web._live[rid] = {Fake()}
    try:
        client.post(f"/rooms/{rid}/remind-now",
                    params={"token": mtok})
    finally:
        web._live.pop(rid, None)
    assert [p["kind"] for p in seen] == ["remind"]
    assert seen[0]["body"].startswith("Reminder")


def test_remind_now_empty_posts_nothing(client):
    rid, otok, mtok = _two(client)
    assert client.post(f"/rooms/{rid}/remind-now",
                       params={"token": mtok}).json() == {"posted": False}
    assert client.get(f"/rooms/{rid}/messages",
                      params={"token": otok}).json() == []


def _nudges(client, rid, otok):
    bodies = [m["body"] for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()]
    return [b for b in bodies if b.startswith("Reminder")]


def test_lazy_nudge_once_per_day(client, monkeypatch):
    rid, otok, mtok = _two(client)
    client.post(f"/rooms/{rid}/reminders",
                params={"token": mtok, "text": "standup"})
    client.post(f"/rooms/{rid}/remind-time",
                params={"token": otok, "at": "08:00"})
    _at(monkeypatch, 3, 7, 59)
    client.get(f"/rooms/{rid}/messages", params={"token": otok})
    assert _nudges(client, rid, otok) == []
    _at(monkeypatch, 3, 8, 0)
    client.get(f"/rooms/{rid}/messages", params={"token": otok})
    client.get(f"/rooms/{rid}/messages", params={"token": otok})
    assert len(_nudges(client, rid, otok)) == 1
    _at(monkeypatch, 4, 8, 0)
    client.get(f"/rooms/{rid}/messages", params={"token": otok})
    assert len(_nudges(client, rid, otok)) == 2
    client.post(f"/rooms/{rid}/remind-time",
                params={"token": otok, "at": "off"})
    _at(monkeypatch, 5, 8, 0)
    client.get(f"/rooms/{rid}/messages", params={"token": otok})
    assert len(_nudges(client, rid, otok)) == 2


def test_lock_freezes_reminder_writes(client):
    rid, otok, mtok = _two(client)
    mid = client.post(f"/rooms/{rid}/reminders",
                      params={"token": mtok, "text": "x"}).json()["id"]
    client.post(f"/rooms/{rid}/lock", params={"token": otok, "on": True})
    assert client.post(f"/rooms/{rid}/reminders",
                       params={"token": mtok, "text": "y"}
                       ).status_code == 403
    assert client.post(f"/rooms/{rid}/reminders/{mid}",
                       params={"token": mtok, "text": "z"}
                       ).status_code == 403
    assert client.delete(f"/rooms/{rid}/reminders/{mid}",
                         params={"token": mtok}).status_code == 403
    assert client.post(f"/rooms/{rid}/remind-now",
                       params={"token": mtok}).status_code == 403


def test_page_has_reminder_space(client):
    rid, otok, mtok = _two(client)
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    for marker in ("id=rems", "remindNow()", "id=remindtime",
                   "remList()", "remHTML(", "remCreate()", "remEdit(",
                   "remSave(", "remDone(", "remDelete(", "setRemindTime(",
                   "m.kind==='reminder'", "Add reminder", "New reminder",
                   "HH:MM or off", "nudgeback", "showRemind(",
                   "dismissNudge()", "m.kind==='remind'", "Got it"):
        assert marker in page
    guest = client.get(f"/rooms/{rid}/app",
                       params={"token": mtok}).text
    assert "id=remindtime" in guest  # rendered, JS-gated to managers
    assert "(ISMANAGE&&!ISSOLO)" in guest
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "Solo"}).json()
    solo = client.get(f"/rooms/{j['room_id']}/app",
                      params={"token": j["token"]}).text
    assert "button[onclick='remindNow()']" in solo
    assert "input#remindtime" in solo


def test_nudge_skips_ledger_mirror_duplicate():
    led = [{"what": "tools selection", "who": "Z", "deadline": "Wed",
            "due_date": "", "status": "open"}]
    rems = [{"text": "tools selection", "owner": "Z", "due_text": "Wed",
             "due_date": "", "done": 0, "created_by": "ledger:1"},
            {"text": "buy milk", "owner": "", "due_text": "",
             "due_date": "", "done": 0, "created_by": "Z"}]
    body = remind.compose("M", led, rems, "2026-11-03")
    assert body.count("tools selection") == 1
    assert "buy milk" in body


def test_nudge_skips_manual_duplicate_of_ledger():
    led = [{"what": "tools selection", "who": "Z + Krishna",
            "deadline": "Wednesday", "due_date": "2026-11-04",
            "status": "open"}]
    rems = [{"text": "tools selection", "owner": "Z + Krishna",
             "due_text": "Wednesday", "due_date": "2026-11-04",
             "done": 0, "created_by": "Z"}]
    body = remind.compose("M", led, rems, "2026-11-03")
    assert body.count("tools selection") == 1
    other = [{"text": "tools selection", "owner": "Ana",
              "due_text": "Wednesday", "due_date": "2026-11-04",
              "done": 0, "created_by": "Ana"}]
    body = remind.compose("M", led, other, "2026-11-03")
    assert body.count("tools selection") == 2  # different owner stays


def test_done_mirror_closes_ledger_line(client):
    rid, otok, mtok = _two(client)
    client.post(f"/rooms/{rid}/ledger",
                params={"token": otok, "what": "ship it",
                        "who": "O", "deadline": "Friday"})
    mid = client.get(f"/rooms/{rid}/reminders",
                     params={"token": otok}).json()["reminders"][0]["id"]
    client.post(f"/rooms/{rid}/reminders/{mid}",
                params={"token": mtok, "done": True})
    led = client.get(f"/rooms/{rid}/ledger",
                     params={"token": otok}).json()
    assert led[0]["status"] == "done"
    assert client.post(f"/rooms/{rid}/remind-now",
                       params={"token": mtok}).json() == {"posted": False}
    client.post(f"/rooms/{rid}/reminders/{mid}",
                params={"token": mtok, "done": False})
    led = client.get(f"/rooms/{rid}/ledger",
                     params={"token": otok}).json()
    assert led[0]["status"] == "open"


def test_nudge_skips_ledger_with_done_mirror():
    led = [{"id": 1, "what": "tools selection", "who": "Z",
            "deadline": "Wed", "due_date": "", "status": "open"}]
    rems = [{"text": "tools selection", "owner": "Z", "due_text": "Wed",
             "due_date": "", "done": 1, "created_by": "ledger:1"}]
    assert remind.compose("M", led, rems, "2026-11-03") == ""


def test_due_label_never_doubles_by():
    assert remind.due_label("Friday") == "by Friday"
    assert remind.due_label("by Friday") == "by Friday"
    assert remind.due_label("") == "no date"
    led = [{"what": "entire automation", "who": "", "deadline": "by Friday",
            "due_date": "2026-11-06", "status": "open"}]
    body = remind.compose("M", led, [], "2026-11-03")
    assert "by by Friday" not in body
    assert "(by Friday)" in body
