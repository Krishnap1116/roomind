"""UI slice: homepage, room page, forget door, usage meter."""
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


def test_homepage_and_room_page(client):
    assert "Roomind" in client.get("/").text
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    tok = client.post(f"/rooms/{rid}/join",
                      params={"name": "Ana", "invite": inv}).json()["token"]
    page = client.get(f"/rooms/{rid}/app", params={"token": tok})
    assert page.status_code == 200 and "Ana" in page.text
    bad = client.get(f"/rooms/{rid}/app", params={"token": "nope"})
    assert bad.status_code == 200
    assert "You are no longer in this room" in bad.text


def test_forget_door_and_usage_meter(client, monkeypatch):
    monkeypatch.setattr(web.agent, "run_loop",
                        lambda *a, **k: {"answer": "ok", "reasons": [],
                                         "remember": [],
                                         "calls": [{"tin": 100, "tout": 20}],
                                         "searched": False})
    rid = client.post("/rooms", params={"mission": "M"}).json()["room_id"]
    inv = store.connect().execute(
        "SELECT token FROM invites WHERE room=?", (rid,)).fetchone()[0]
    tok = client.post(f"/rooms/{rid}/join",
                      params={"name": "A", "invite": inv}).json()["token"]
    client.post(f"/rooms/{rid}/ask", params={"token": tok, "text": "hi"})
    u = client.get(f"/rooms/{rid}/usage", params={"token": tok}).json()
    assert u["by_model"][S.SPARK_MODEL]["tin"] == 100
    assert u["by_model"][S.SPARK_MODEL]["window"] == 1_000_000
    con = store.connect()
    import roomind.memory as memory
    memory.remember(con, rid, "standup", "9am")
    con.close()
    assert client.delete(f"/rooms/{rid}/memory",
                         params={"token": tok,
                                 "key": "standup"}).json() == {"forgotten":
                                                               "standup",
                                                               "removed":
                                                               True}
    assert client.delete(f"/rooms/{rid}/memory",
                         params={"token": tok,
                                 "key": "standup"}).json()["removed"] is False


def test_invite_buttons_owner_only(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "Owner"}).json()
    rid, otok = j["room_id"], j["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    mtok = client.post(f"/rooms/{rid}/join",
                       params={"name": "Guest",
                               "invite": team}).json()["token"]
    owner_page = client.get(f"/rooms/{rid}/app",
                            params={"token": otok}).text
    guest_page = client.get(f"/rooms/{rid}/app",
                            params={"token": mtok}).text
    assert "Team link" in owner_page
    assert "Team link" not in guest_page
    assert "Single link" not in guest_page
    assert "const ISOWNER=true" in owner_page
    assert "const ISOWNER=false" in guest_page
    assert "if(ISOWNER)links()" in owner_page
    assert "Room <b>'+" in owner_page  # live list carries share info


def test_room_script_has_no_escaped_quote_traps(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "Owner"}).json()
    page = client.get(f"/rooms/{j['room_id']}/app",
                      params={"token": j["token"]}).text
    js = page.split("<script>")[1].split("</script>")[0]
    assert "\\'" not in js  # broke every button once; never again


def test_shelf_pins_each_seat_not_each_room(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "Owner"}).json()
    room_js = client.get(f"/rooms/{j['room_id']}/app",
                         params={"token": j["token"]}).text
    assert room_js.count("p.rid===R&&p.token===T") == 2  # pin + cleanup
    assert "p.rid!==R" not in room_js  # the old seat-eating filter
    home_js = client.get("/").text
    assert "p.token===i[1]" in home_js  # drop removes one seat only


def test_shelf_is_personal_and_named(client):
    j = client.post("/rooms", params={"mission": "Ship Friday",
                                      "name": "K"}).json()
    page = client.get(f"/rooms/{j['room_id']}/app",
                      params={"token": j["token"]}).text
    assert 'const MISSION="Ship Friday"' in page
    assert "mission:MISSION" in page  # pin carries the room name
    assert "sessionStorage.setItem('roomind.me'" in page
    assert "roomind.tab" in page  # each tab gets its own mark
    assert "tab:tab" in page  # pin carries the tab mark
    home = client.get("/").text
    assert "p.tab===tab" in home  # only this tab's seats, names ignored
    assert ":[]" in home  # stranger tab sees zero rows
    assert "This tab knows nobody yet." in home
    assert " as '+" not in home and " as P" not in home  # no join-as wording
    assert "p.mission||p.rid" in home  # name shown, id only as fallback


def test_app_shell_markers(client):
    j = client.post("/rooms", params={"mission": "Ship Friday",
                                      "name": "K"}).json()
    page = client.get(f"/rooms/{j['room_id']}/app",
                      params={"token": j["token"]}).text
    for marker in ("id=bar", "id=rooms", "id=mecard", "id=menu", "id=top",
                   "id=wrap", "id=agentcol", "id=roomcol", "sideRooms()",
                   "sideMe()", "openRoom(", "toggleBar()", 'class="msg',
                   "id=rmmenu", "class=rmrow", "roomMenu(",
                   "rmLeave(", "rmClose(", "dropPin(", "⋮",
                   'class="msg agent"', 'class="card dissent"',
                   'class="card prop"', "rel=icon", "fonts.googleapis.com",
                   "prefers-reduced-motion", "Outfit"):
        assert marker in page
    assert page.index("id=bar") < page.index("id=thread")
    assert "Ship Friday" in page  # mission in the header
    home = client.get("/").text
    assert "Roomind" in home and "My rooms" in home
    assert "fonts.googleapis.com" in home


def test_room_tabs_and_plain_labels(client):
    j = client.post("/rooms", params={"mission": "Ship Friday",
                                      "name": "K"}).json()
    page = client.get(f"/rooms/{j['room_id']}/app",
                      params={"token": j["token"]}).text
    for marker in ("tabbtn-chat", "tabbtn-plan", "tabbtn-work",
                   "tabbtn-room", "tabbtn-share", "id=tab-chat",
                   "id=tab-plan", "id=tab-work", "id=tab-room",
                   "id=tab-share", "id=invout", "id=planout",
                   "id=workout", "id=roomout", "function tab(",
                   "#tab-chat #side", "flex:1 1 auto",
                   "max-height:none", "min-height:0",
                   "border-radius:16px;overflow:hidden",
                   "flex:1 1 auto;min-height:0;overflow-y:auto",
                   "stick2",
                   "#chatrow{flex:none", "window._shown",
                   "dueLabel(", "setInterval(slotSweep,30000);setInterval(meter,30000);return ms;",
                   "function ping(", "class=dot", "ping('chat')",
                   "ping('plan')", "ping('work')", "ping('room')",
                   "ping('share')", ">Invites</button>",
                   "class=sech", "Open cards", "Red-team findings",
                   "Invite links", "Room controls", "sech>People</div>",
                   "class=primary", "class=quiet", "newGuard(box",
                   "querySelector('.newform')",
                   "querySelectorAll('.card.dissent')",
                   "empty-note", "No docs yet", "No tasks yet",
                   "No votes running", "Nothing open",
                   "No findings yet", "renderBrief(",
                   "renderLedger(",
                   "renderCheck(", "u.by_model", "memKeys()",
                   "id=memkeys", "Remembers:",
                   "<b>Decisions</b>", "<b>Open</b>",
                   "forgetKeyBy(", "memToggle()",
                   "more</button>", "resultBox(", "class=result",
                   "class=rhead", "resultBox('Summary',",
                   "resultBox('Decisions',", "resultBox('Team',",
                   "Copy invite", "Copy room id",
                   "invrow", "+5 seats", "Invite code",
                   "Leaving never refills it.", "slotAns(",
                   "slotHTML(", "ansHTML(", "byAsk",
                   "<b>Ledger</b>", "<b>Side rooms</b>",
                   "sidePickOpen(", "sidePickDone(",
                   "Select people", "let _seen=0",
                   ">Summary</button>", ">Decisions</button>",
                   ">Log decision</button>",
                   ">Attack our plan</button>", ">+ Doc</button>",
                   "id=meter", "id=mutebtn", "Unmute judge",
                   "mutebadge", "Judge listening", "judgestate",
                   "kind==='muted'", "Already settled by someone",
                   "_wsWasOpen", "Approval: ", "/decision",
                   "Trust: ", "detailslink",
                   "Exam never run.", ".msg.sys", "sys?' sys'",
                   "Exam already running", "_examRun",
                   "Precision ", "Recall ",
                   ">Download</button>", ">Read-only link</button>",
                   ">Add member</button>", ">Remove</button>",
                   "Make operator", ">Start vote</button>",
                   ">Add reminder</button>", "New decision",
                   "New doc, plan, or patch", ">Submit</button>",
                   ">Mark done</button>", ">+5 seats</button>",
                   "Cost $", "Remove via People",
                   "slotAns(m);ping('chat')", "Due (required)",
                   "e.Detail", "t.status!=='open'",
                   "a.status==='done'", "<div class=meta>Answer</div>",
                   "<br><input id=au", "people();roster();",
                   "overflow-wrap:anywhere",
                   "sech>Red team</div>", "sech>Recap</div>",
                   "sech>Decisions</div>"):
        assert marker in page
    for gone in ("Room chat", ">Brief</button>", ">Ledger</button>",
                 ">Propose</button>", ">Challenge us</button>",
                 ">Red-team us</button>", ">Artifact</button>",
                 ">Spend</button>", ">Export</button>",
                 ">Showcase</button>", ">Links</button>",
                 "Mute/unmute", "Share back",
                 ">Kick</button>", ">Operator</button>", "Propose it",
                 ">Ask it</button>", "Remind us", "No links",
                 "New proposal", "New artifact", "Spend $",
                 ">Review us</button>", "alert(r.ok?'muted",
                 "id=mutestate class=meta", "h+=' · OK '",
                 "s/ans'", "/dec'", "' · P '", "' · R '",
                 "' · Trust '",
                 "getElementById('out')", "id=out>",
                 "#chatrow{position:sticky",
                 "\"<p><b>\"+l.token", "'+(i+1)+'.",
                 "border-radius:16px;overflow-y:auto",
                 "flex:1 0 auto;min-height:100%",
                 "('by '+esc(m.due_text))",
                 "(by '+esc(l.deadline)", "· by '+esc(p.deadline)",
                 "Golden: ", "Answer: ", "Answer time: "):
        assert gone not in page
    assert page.index("id=tab-chat") < page.index("id=tab-plan")
    assert page.index("id=tab-plan") < page.index("id=tab-work")
    assert page.index("id=tab-work") < page.index("id=tab-room")
    assert page.index("id=tab-room") < page.index("id=tab-share")
    assert page.index("id=tab-chat") < page.index("id=side")
    assert page.index("id=side") < page.index("id=tab-plan")
    assert page.index("id=tab-plan") < page.index("id=props")
    assert page.index("id=tab-work") < page.index("id=arts")
    assert page.index("id=tab-share") < page.index("id=share")
    assert page.index("id=tab-share") < page.index("id=invout")
    assert page.index("id=tab-plan") < page.index("id=planout")
    assert page.index("id=planout") < page.index("id=tab-work")
    assert page.index("id=planout") < page.index("id=props")
    assert page.index("id=tab-work") < page.index("id=workout")
    assert page.index("id=workout") < page.index("id=tab-room")
    assert page.index("id=workout") < page.index("id=rems")
    assert page.index("id=tab-room") < page.index("id=roomout")
    assert page.index("id=roomout") < page.index("id=tab-share")


def test_share_tab_member_note(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "Owner"}).json()
    rid, otok = j["room_id"], j["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    mtok = client.post(f"/rooms/{rid}/join",
                       params={"name": "Guest",
                               "invite": team}).json()["token"]
    guest = client.get(f"/rooms/{rid}/app",
                       params={"token": mtok}).text
    assert "id=tab-share" in guest  # tab exists for everyone
    assert "ask them for one" in guest
    assert "Team link" not in guest and "Single link" not in guest
    assert ">Read-only link</button>" not in guest
