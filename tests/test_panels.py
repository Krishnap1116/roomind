"""Twin panels step one: questions split from chatter, two panels."""
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


def test_ask_posts_question_kind(client, monkeypatch):
    monkeypatch.setattr(web.agent, "run_loop",
                        lambda *a, **k: {"answer": "ok", "reasons": [],
                                         "remember": [],
                                         "calls": [{"tin": 1, "tout": 1}],
                                         "searched": False})
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    client.post(f"/rooms/{rid}/ask", params={"token": otok, "text": "hi?"})
    kinds = [(m["author"], m["kind"]) for m in client.get(
        f"/rooms/{rid}/messages", params={"token": otok}).json()]
    assert kinds == [("O", "ask"), ("agent", "answer")]


def test_answer_links_ask_id(client, monkeypatch):
    monkeypatch.setattr(web.agent, "run_loop",
                        lambda *a, **k: {"answer": "ok", "reasons": [],
                                         "remember": [],
                                         "calls": [{"tin": 1, "tout": 1}],
                                         "searched": False})
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    client.post(f"/rooms/{rid}/ask",
                params={"token": otok, "text": "best tools here?"})
    msgs = client.get(f"/rooms/{rid}/messages",
                      params={"token": otok}).json()
    ask, ans = msgs[0], [m for m in msgs if m["kind"] == "answer"][0]
    assert ans["ask_id"] == ask["id"]
    assert ask.get("ask_id", 0) == 0  # questions carry none


def test_room_page_has_twin_panels(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    page = client.get(f"/rooms/{j['room_id']}/app",
                      params={"token": j["token"]}).text
    assert "id=thread" in page and "id=side" in page
    assert "m.kind==='ask'" in page  # questions route to main
    assert "showDissent(m,document.getElementById('props'))" in page  # cards judge from plan
    assert "flex-direction:column" in page  # narrow screens stack
    assert page.index("id=thread") < page.index("id=q") < page.index("id=side")
    assert page.index("id=side") < page.index("id=t ")  # each input home


def test_solo_first_doors_and_share(client):
    home = client.get("/").text
    assert "New chat" in home and "createChat()" in home
    assert "New room" in home and "Team code" in home
    assert "uses=20&hours=0" in home  # room door mints a team link
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    mtok = client.post(f"/rooms/{rid}/join",
                       params={"name": "G",
                               "invite": team}).json()["token"]
    owner_page = client.get(f"/rooms/{rid}/app",
                            params={"token": otok}).text
    guest_page = client.get(f"/rooms/{rid}/app",
                            params={"token": mtok}).text
    assert "id=share" in owner_page and "shareBox()" in owner_page
    assert "Solo chat." in owner_page and "Invite more" in owner_page
    assert "shareRoom()" in owner_page
    assert "shareBox()" in guest_page  # renders, but ISMANAGE hides it


def test_solo_face_hides_chat_and_links(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    solo = client.get(f"/rooms/{rid}/app",
                      params={"token": otok}).text
    assert "const ISSOLO=true" in solo
    assert "getElementById('chatrow')" in solo
    assert "button[onclick='links()']" in solo
    assert "button[onclick='check()']" not in solo
    assert "button[onclick^='invite(']" in solo
    assert "getElementById('uses')" in solo
    assert "Ask your first question below." in solo
    assert "Chat wakes when the second seat joins." in solo
    team = client.post(f"/rooms/{rid}/invites",
                       params={"token": otok, "uses": 5}).json()["invite"]
    mtok = client.post(f"/rooms/{rid}/join",
                       params={"name": "G",
                               "invite": team}).json()["token"]
    duo = client.get(f"/rooms/{rid}/app",
                     params={"token": mtok}).text
    assert "const ISSOLO=false" in duo
    assert "Say hello." in duo


def test_links_never_expire_by_default(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    inv = client.post(f"/rooms/{rid}/invites",
                      params={"token": otok, "uses": 5,
                              "hours": 0}).json()["invite"]
    exp = store.connect().execute(
        "SELECT expires_at FROM invites WHERE token=?",
        (inv,)).fetchone()[0]
    assert exp > 4102444800.0 - 1
    assert client.post(f"/rooms/{rid}/join",
                       params={"name": "G",
                               "invite": inv}).status_code == 200
    home = client.get("/").text
    assert "hours=168" not in home
    assert "uses=20&hours=0" in home
    room_page = client.get(f"/rooms/{rid}/app",
                           params={"token": otok}).text
    assert "hours=24" not in room_page and "hours=0" in room_page


def test_send_button_and_guards(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    page = client.get(f"/rooms/{j['room_id']}/app",
                      params={"token": j["token"]}).text
    assert "id=sendbtn" in page and "<svg" in page
    assert ">Ask</button>" not in page
    assert 'if(event.key==="Enter"&&!event.shiftKey){event.preventDefault();ask()}' in page
    assert 'if(event.key==="Enter"&&!event.shiftKey){event.preventDefault();send()}' in page
    assert "<textarea id=q" in page and "<textarea id=t" in page
    assert "grow(this)" in page and "pre-wrap" in page
    assert "window._lastQ" in page and "b.disabled=true" in page
    assert "Retry" in page and "load();return" in page  # failure: note + retry
    assert "id=dots" in page and "id=echo" in page
    assert "id=emptyq" in page and "class=src" in page
    assert "linkify(" in page and "Why: " not in page
    assert "id=emptyc" in page and "getElementById('emptyc')" in page
    assert "placeholder='Say hello... (Shift+Enter for a new line)'" in page
    assert "Say hello.</p>" not in page  # hint lives in the input now
    assert "length>1)location.reload()" in page  # solo wakes on join
    assert "askstream" in page and "EventSource" in page
    assert "id=stream" in page and "askRetry()" in page
    assert "<b>M</b>" in page and "rmission" not in page
    assert "const MYID=" in page and "function mine(m)" in page
    assert "msg'+(isMe?' me':'')" in page
    for marker in ("id=newback", "id=newcard", "id=nm", "id=nn",
                   "newChat()", "newChatGo()", "newChatHide()",
                   "copyTxt(", "copyBoth(", "Copy both",
                   "class=mrow", "class=plain",
                   "width:fit-content"):
        assert marker in page


def test_empty_ask_rejected(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    r = client.post(f"/rooms/{rid}/ask",
                    params={"token": otok, "text": "   "})
    assert r.status_code == 400
    assert client.get(f"/rooms/{rid}/messages",
                      params={"token": otok}).json() == []


def test_ask_broadcasts_live(client, monkeypatch):
    monkeypatch.setattr(web.agent, "run_loop",
                        lambda *a, **k: {"answer": "ok", "reasons": [],
                                         "remember": [],
                                         "calls": [{"tin": 1, "tout": 1}],
                                         "searched": False})
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    seen = []

    class Fake:
        async def send_json(self, p):
            seen.append(p)

    web._live[rid] = {Fake()}
    try:
        client.post(f"/rooms/{rid}/ask",
                    params={"token": otok, "text": "hi?"})
    finally:
        web._live.pop(rid, None)
    assert [(p["kind"], p["body"]) for p in seen] == [("ask", "hi?"),
                                                      ("answer", "ok")]


def test_live_routes_by_kind(client):
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    page = client.get(f"/rooms/{j['room_id']}/app",
                      params={"token": j["token"]}).text
    assert "if(m.kind==='answer'){slotAns(m);ping('chat');return;}" in page
    assert "slotHTML(m.id)" in page and "No answer arrived." in page
    assert "getElementById('echo')" in page  # own echo swaps in place
    assert "e1.outerHTML" in page
    assert "if(m.kind==='ask'){const e1=" in page
    assert "show(who(m),m.body,box,true);box.innerHTML+=slotHTML(m.id);" in page
    assert "box2,mine(m)" in page  # side chat keeps direction
    assert "if(m.kind==='dissent'){showDissent(m,document.getElementById('props'));tab('plan');return;}" in page
