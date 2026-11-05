"""Side rooms: split off, members-only, share back."""
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


def _three(client):
    rid, otok, mtok = _two(client)
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    ctok = client.post(f"/rooms/{rid}/join",
                       params={"name": "C", "invite": team}).json()["token"]
    return rid, otok, mtok, ctok


def _ids(client, rid, otok):
    ms = client.get(f"/rooms/{rid}/members",
                    params={"token": otok}).json()
    return {m["name"]: m["id"] for m in ms}


def test_side_create_and_list(client):
    rid, otok, mtok, ctok = _three(client)
    ids = _ids(client, rid, otok)
    assert client.post(f"/rooms/{rid}/side",
                       params={"token": "nope", "mission": "x"}
                       ).status_code == 403
    assert client.post(f"/rooms/{rid}/side",
                       params={"token": mtok, "mission": "x",
                               "mids": "nope"}).status_code == 400
    j = client.post(f"/rooms/{rid}/side",
                    params={"token": mtok, "mission": "Design sprint",
                            "mids": ids["C"]}
                    ).json()
    assert client.get(f"/rooms/{rid}/sides",
                      params={"token": "nope"}).status_code == 403
    assert client.get(f"/rooms/{rid}/sides",
                      params={"token": otok}).json() == []
    mine = client.get(f"/rooms/{rid}/sides",
                      params={"token": ctok}).json()
    assert mine == [{"room_id": j["room_id"],
                     "mission": "Design sprint"}]
    names = [m["name"] for m in client.get(
        f"/rooms/{j['room_id']}/members",
        params={"token": j["token"]}).json()]
    assert sorted(names) == ["C", "M"]
    bodies = [m["body"] for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()]
    assert any("M opened side room 'Design sprint' with C" in b
               for b in bodies)
    assert client.post(f"/rooms/{j['room_id']}/side",
                       params={"token": j["token"], "mission": "deeper"}
                       ).status_code == 400


def test_side_needs_shared_room(client):
    j = client.post("/rooms", params={"mission": "Solo",
                                      "name": "S"}).json()
    r = client.post(f"/rooms/{j['room_id']}/side",
                    params={"token": j["token"], "mission": "x"})
    assert r.status_code == 400
    assert r.json()["detail"] == "split needs a shared room"


def test_open_side_members_only(client):
    rid, otok, mtok, ctok = _three(client)
    ids = _ids(client, rid, otok)
    s = client.post(f"/rooms/{rid}/side",
                    params={"token": mtok, "mission": "S",
                            "mids": ids["C"]}).json()
    sid = s["room_id"]
    assert client.post(f"/rooms/{rid}/open-side",
                       params={"ptoken": otok}).status_code == 404
    assert client.post(f"/rooms/{sid}/open-side",
                       params={"ptoken": "stranger"}
                       ).status_code == 403
    assert client.post(f"/rooms/{sid}/open-side",
                       params={"ptoken": otok}).status_code == 403
    assert client.post(f"/rooms/{sid}/open-side",
                       params={"ptoken": mtok}).json() == {
                           "token": s["token"]}
    cside = client.post(f"/rooms/{sid}/open-side",
                        params={"ptoken": ctok}).json()["token"]
    names = [m["name"] for m in client.get(
        f"/rooms/{sid}/members", params={"token": cside}).json()]
    assert sorted(names) == ["C", "M"]


def test_roster_add_remove(client):
    rid, otok, mtok, ctok = _three(client)
    ids = _ids(client, rid, otok)
    s = client.post(f"/rooms/{rid}/side",
                    params={"token": mtok, "mission": "S",
                            "mids": ids["C"]}).json()
    sid, stok = s["room_id"], s["token"]
    cside = client.post(f"/rooms/{sid}/open-side",
                        params={"ptoken": ctok}).json()["token"]
    assert client.get(f"/rooms/{sid}/roster",
                      params={"token": cside}).status_code == 403
    assert client.post(f"/rooms/{sid}/roster/add",
                       params={"token": cside,
                               "mid": ids["O"]}).status_code == 403
    assert client.get(f"/rooms/{rid}/roster",
                      params={"token": otok}).status_code == 400
    ros = client.get(f"/rooms/{sid}/roster",
                     params={"token": stok}).json()
    assert sorted(m["name"] for m in ros["side"]) == ["C", "M"]
    assert [m["name"] for m in ros["main"]] == ["O"]
    assert client.post(f"/rooms/{sid}/roster/add",
                       params={"token": stok,
                               "mid": "nope"}).status_code == 404
    added = client.post(f"/rooms/{sid}/roster/add",
                        params={"token": stok,
                                "mid": ids["O"]}).json()
    assert added["new"] is True
    ot = added["token"]
    assert client.post(f"/rooms/{sid}/open-side",
                       params={"ptoken": otok}).json() == {"token": ot}
    bodies = [m["body"] for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()]
    assert any("O joined side room 'S'" in b for b in bodies)
    side_bodies = [m["body"] for m in client.get(
        f"/rooms/{sid}/messages", params={"token": stok}).json()]
    assert any("M added O to the side room" in b for b in side_bodies)
    omid = [m["id"] for m in client.get(
        f"/rooms/{sid}/members", params={"token": stok}).json()
        if m["name"] == "O"][0]
    assert client.post(f"/rooms/{sid}/members/{omid}/kick",
                       params={"token": cside}).status_code == 403
    assert client.post(f"/rooms/{sid}/members/{omid}/kick",
                       params={"token": stok}).json() == {"kicked": omid}
    assert client.get(f"/rooms/{rid}/sides",
                      params={"token": otok}).json() == []
    assert client.get(f"/rooms/{sid}/messages",
                      params={"token": ot}).status_code == 403


def test_side_invites_closed(client):
    rid, otok, mtok = _two(client)
    sid = client.post(f"/rooms/{rid}/side",
                      params={"token": mtok, "mission": "S"}
                      ).json()["room_id"]
    stok = client.post(f"/rooms/{sid}/open-side",
                       params={"ptoken": mtok}).json()["token"]
    assert client.post(f"/rooms/{sid}/invites",
                       params={"token": stok, "uses": 5}
                       ).status_code == 400
    assert client.post(f"/rooms/{sid}/join",
                       params={"name": "O", "invite": "whatever"}
                       ).status_code == 400


def test_share_back_reports_decisions(client):
    rid, otok, mtok, ctok = _three(client)
    ids = _ids(client, rid, otok)
    s = client.post(f"/rooms/{rid}/side",
                    params={"token": mtok, "mission": "Design",
                            "mids": ids["O"]}
                    ).json()
    sid, stok = s["room_id"], s["token"]
    ot = client.post(f"/rooms/{sid}/open-side",
                     params={"ptoken": otok}).json()["token"]
    assert client.post(f"/rooms/{sid}/share-back",
                       params={"token": ot}).status_code == 403
    assert client.post(f"/rooms/{rid}/share-back",
                       params={"token": otok}).status_code == 400
    assert client.post(f"/rooms/{sid}/share-back",
                       params={"token": stok}
                       ).json() == {"shared": rid}
    bodies = [m["body"] for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()]
    assert any("no stamped decisions yet" in b for b in bodies)
    client.post(f"/rooms/{sid}/ledger",
                params={"token": stok, "what": "ship v2",
                        "who": "M", "deadline": "Friday"})
    client.post(f"/rooms/{sid}/share-back", params={"token": stok})
    bodies = [m["body"] for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()]
    rep = [b for b in bodies if "reports (by M)" in b][-1]
    assert "Side room 'Design'" in rep
    assert "ship v2 — M (by Friday)" in rep
    assert f"room {sid}" in rep
    led = client.get(f"/rooms/{rid}/ledger",
                     params={"token": otok}).json()
    reps = [r for r in led if r["why"] == f"side-report:{sid}"]
    assert len(reps) == 1
    assert "Side room 'Design' reports (by M)" in reps[0]["what"]
    assert "ship v2 — M (by Friday)" in reps[0]["what"]
    client.post(f"/rooms/{sid}/ledger",
                params={"token": stok, "what": "cut trailer",
                        "who": "M", "deadline": "by tonight"})
    client.post(f"/rooms/{sid}/share-back", params={"token": stok})
    led = client.get(f"/rooms/{rid}/ledger",
                     params={"token": otok}).json()
    reps = [r for r in led if r["why"] == f"side-report:{sid}"]
    assert len(reps) == 1  # re-share still replaces
    assert "cut trailer — M (by tonight)" in reps[0]["what"]
    assert "by by" not in reps[0]["what"]


def test_locks_cover_sides(client):
    rid, otok, mtok, ctok = _three(client)
    ids = _ids(client, rid, otok)
    sid = client.post(f"/rooms/{rid}/side",
                      params={"token": mtok, "mission": "S"}
                      ).json()["room_id"]
    stok = client.post(f"/rooms/{sid}/open-side",
                       params={"ptoken": mtok}).json()["token"]
    client.post(f"/rooms/{rid}/lock", params={"token": otok, "on": True})
    assert client.post(f"/rooms/{rid}/side",
                       params={"token": mtok, "mission": "x"}
                       ).status_code == 403
    assert client.post(f"/rooms/{sid}/share-back",
                       params={"token": stok}).status_code == 403
    assert client.post(f"/rooms/{sid}/roster/add",
                       params={"token": stok,
                               "mid": ids["O"]}).status_code == 403
    client.post(f"/rooms/{rid}/lock", params={"token": otok, "on": False})
    client.post(f"/rooms/{sid}/lock", params={"token": stok, "on": True})
    assert client.post(f"/rooms/{sid}/share-back",
                       params={"token": stok}).status_code == 403
    assert client.post(f"/rooms/{sid}/roster/add",
                       params={"token": stok,
                               "mid": ids["O"]}).status_code == 403


def test_side_pages_and_solo(client):
    rid, otok, mtok, ctok = _three(client)
    ids = _ids(client, rid, otok)
    s = client.post(f"/rooms/{rid}/side",
                    params={"token": mtok, "mission": "Design",
                            "mids": ids["O"]}
                    ).json()
    sid, stok = s["room_id"], s["token"]
    main = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    for marker in ("id=sidesec", "id=sides", "id=sideinput",
                   "id=sidepick", "sidesList()", "sidePicker()",
                   "sideOpen(", "sideCreate()", "shareBack()",
                   "goMain()", "const PARENT=''", "New side room",
                   "open-side", "Single link", "id=incside",
                   "Include sides"):
        assert marker in main
    assert "← Main" not in main and "Report to main" not in main
    owner = client.get(f"/rooms/{sid}/app",
                       params={"token": stok}).text
    for marker in ("id=rostersec", "id=rosterpick", "rosterAdd()",
                   "roster();"):
        assert marker in owner
    assert f"const PARENT='{rid}'" in owner
    assert "← Main" in owner and "Report to main" in owner
    assert "Single link" not in owner and "Team link" not in owner
    assert "sech>Read-only link</div>" in owner
    assert "Invite links" not in owner
    ot = client.post(f"/rooms/{sid}/open-side",
                     params={"ptoken": otok}).json()["token"]
    guest = client.get(f"/rooms/{sid}/app",
                       params={"token": ot}).text
    assert "← Main" in guest and "Report to main" not in guest
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "Solo"}).json()
    solo = client.get(f"/rooms/{j['room_id']}/app",
                      params={"token": j["token"]}).text
    assert ",#sidesec" in solo


def test_side_seat_reuses_main_nick(client):
    rid, otok, mtok, ctok = _three(client)
    ids = _ids(client, rid, otok)
    s = client.post(f"/rooms/{rid}/side",
                    params={"token": mtok, "mission": "Design",
                            "mids": ids["O"]}).json()
    sid, stok = s["room_id"], s["token"]
    main = {m["name"]: m["nick"] for m in
            client.get(f"/rooms/{rid}/members",
                       params={"token": otok}).json()}
    side = {m["name"]: m["nick"] for m in
            client.get(f"/rooms/{sid}/members",
                       params={"token": stok}).json()}
    assert side["M"] == main["M"]  # creator keeps nick
    assert side["O"] == main["O"]  # picked seat keeps nick


def test_stale_side_nick_aligns(db):
    con = store.connect()
    main = store.new_room(con, "M", "O")
    rid = main["room_id"]
    oid = con.execute("SELECT id, nick FROM members WHERE room=?",
                      (rid,)).fetchone()
    s = store.new_room(con, "S", "O", oid["id"])
    sid = s["room_id"]
    store.set_parent(con, sid, rid)
    con.execute("UPDATE members SET nick=? WHERE room=?",
                ("Stale Nick", sid))
    store.ensure_nicks(con, sid)
    now = con.execute("SELECT nick FROM members WHERE room=?",
                      (sid,)).fetchone()["nick"]
    con.close()
    assert now == oid["nick"]


def test_side_rooms_marked_in_lists(client):
    rid, otok, mtok = _two(client)
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    assert "parent:PARENT" in page  # pins carry the parent link
    assert "(p.parent?'↳ ':'')" in page  # sidebar marks sides
    home = client.get("/").text
    assert "(p.parent?'↳ ':'')" in home  # shelf marks sides too


def test_brief_include_sides(client, monkeypatch):
    rid, otok, mtok, ctok = _three(client)
    ids = _ids(client, rid, otok)
    s = client.post(f"/rooms/{rid}/side",
                    params={"token": mtok, "mission": "S",
                            "mids": ids["C"]}).json()
    sid, stok = s["room_id"], s["token"]
    con = store.connect()
    store.post_message(con, sid, "M", "side secret plan", kind="chat")
    con.close()
    client.post(f"/rooms/{sid}/ledger",
                params={"token": stok, "what": "ship v2", "who": "M"})
    client.post(f"/rooms/{sid}/share-back", params={"token": stok})
    seen = {}

    def fake(api_key, base, model, history, prompt, timeout=60.0,
             notes=None, effort=None, system=None):
        seen["dump"] = json.dumps(history) + prompt
        seen["n"] = seen.get("n", 0) + 1
        return {"answer": json.dumps({"decisions": [], "open": [],
                                      "owners": {}}),
                "reasons": [], "remember": [], "tin": 1, "tout": 1}

    monkeypatch.setattr(web.meta, "spark_reply", fake)
    b = client.get(f"/rooms/{rid}/brief",
                   params={"token": otok,
                           "include_sides": True}).json()
    assert seen["n"] == 1
    assert "side secret plan" not in seen["dump"]
    assert "reports (by M)" in seen["dump"]
    assert b["sides_hidden"] == 1
    assert any(q["room"] == "S" and "reports (by M)" in q["text"]
               for q in b["quotes"])
    assert not any(q["text"] == "ship v2" for q in b["quotes"])
    m = client.get(f"/rooms/{rid}/brief",
                   params={"token": mtok,
                           "include_sides": True}).json()
    assert "side secret plan" in seen["dump"]
    assert m["sides_hidden"] == 0
    assert {"room": "S", "text": "ship v2"} in m["quotes"]
    plain = client.get(f"/rooms/{rid}/brief",
                       params={"token": otok}).json()
    assert "quotes" not in plain and "sides_hidden" not in plain


def test_slow_doors_show_working_state(client):
    rid, otok, mtok = _two(client)
    page = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    assert "Briefing…" in page
    assert "Judging the thread…" in page
