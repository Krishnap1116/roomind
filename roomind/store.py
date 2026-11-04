"""SQLite store. The single swap boundary: all SQL lives here.

Demo runs SQLite (trivial load, delete-means-gone). Production swaps this
module's insides for hosted Postgres; every caller keeps working unchanged.
"""
import json
import random
import re
import secrets
import sqlite3
import time

import roomind as S
from . import remind

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS rooms (
  id TEXT PRIMARY KEY, mission TEXT NOT NULL, depth TEXT DEFAULT 'normal',
  cost_cap REAL DEFAULT 5.0, paused INT DEFAULT 0, model TEXT DEFAULT '',
  locked INT DEFAULT 0, created_at REAL);
CREATE TABLE IF NOT EXISTS invites (
  token TEXT PRIMARY KEY, room TEXT NOT NULL, role TEXT DEFAULT 'member',
  expires_at REAL NOT NULL, used INT DEFAULT 0, max_uses INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS members (
  id TEXT PRIMARY KEY, room TEXT NOT NULL, name TEXT NOT NULL,
  role TEXT DEFAULT 'member', token TEXT NOT NULL, nick TEXT DEFAULT '',
  joined_at REAL);
CREATE TABLE IF NOT EXISTS used_nicks (
  room TEXT NOT NULL, name TEXT NOT NULL, nick TEXT NOT NULL,
  PRIMARY KEY (room, name, nick));
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL, author TEXT NOT NULL,
  kind TEXT DEFAULT 'chat', model TEXT DEFAULT '', body TEXT NOT NULL,
  reasons TEXT DEFAULT '', author_id TEXT DEFAULT '', rating INT DEFAULT 0,
  ask_id INT DEFAULT 0, created_at REAL);
CREATE TABLE IF NOT EXISTS memory (
  room TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
  n INT DEFAULT 1, updated_at REAL, PRIMARY KEY (room, key));
CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL, what TEXT NOT NULL,
  who TEXT DEFAULT '', why TEXT DEFAULT '', deadline TEXT DEFAULT '',
  status TEXT DEFAULT 'open', created_at REAL);
CREATE TABLE IF NOT EXISTS proposals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL, what TEXT NOT NULL,
  who TEXT DEFAULT '', why TEXT DEFAULT '', deadline TEXT DEFAULT '',
  proposed_by TEXT DEFAULT '', state TEXT DEFAULT 'open',
  updates TEXT DEFAULT '', needs_detail INT DEFAULT 0, created_at REAL);
CREATE TABLE IF NOT EXISTS dissent_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL,
  body TEXT NOT NULL, created_at REAL);
CREATE TABLE IF NOT EXISTS eval_runs (
  room TEXT PRIMARY KEY, report TEXT NOT NULL, created_at REAL);
CREATE TABLE IF NOT EXISTS costs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL, call TEXT NOT NULL,
  model TEXT NOT NULL, tin INT DEFAULT 0, tout INT DEFAULT 0,
  usd REAL DEFAULT 0.0, secs REAL DEFAULT 0.0, created_at REAL);
CREATE TABLE IF NOT EXISTS reminders (
  id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL,
  text TEXT NOT NULL, due_text TEXT DEFAULT '', due_date TEXT DEFAULT '',
  owner TEXT DEFAULT '', done INT DEFAULT 0, created_by TEXT DEFAULT '',
  created_at REAL);
CREATE TABLE IF NOT EXISTS artifacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL,
  title TEXT NOT NULL, kind TEXT DEFAULT 'doc', body TEXT NOT NULL,
  version INT DEFAULT 1, status TEXT DEFAULT 'draft',
  created_by TEXT DEFAULT '', approved_by TEXT DEFAULT '',
  created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS artifact_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, artifact_id INT NOT NULL,
  room TEXT NOT NULL, version INT NOT NULL, body TEXT NOT NULL,
  edited_by TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL,
  title TEXT NOT NULL, details TEXT DEFAULT '',
  assignee TEXT DEFAULT '', due_text TEXT DEFAULT '',
  due_date TEXT DEFAULT '', status TEXT DEFAULT 'open',
  created_by TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS polls (
  id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL,
  question TEXT NOT NULL, options TEXT NOT NULL,
  state TEXT DEFAULT 'open', created_by TEXT DEFAULT '',
  created_at REAL);
CREATE TABLE IF NOT EXISTS votes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, poll_id INT NOT NULL,
  room TEXT NOT NULL, member_id TEXT NOT NULL, name TEXT DEFAULT '',
  nick TEXT DEFAULT '', option_idx INT NOT NULL, created_at REAL,
  UNIQUE(poll_id, member_id));
CREATE TABLE IF NOT EXISTS showcase (
  token TEXT PRIMARY KEY, room TEXT NOT NULL, created_by TEXT DEFAULT '',
  created_at REAL);
CREATE TABLE IF NOT EXISTS teammates (
  id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL,
  name TEXT NOT NULL, role TEXT DEFAULT 'teammate',
  instructions TEXT DEFAULT '', created_by TEXT DEFAULT '',
  created_at REAL);
CREATE TABLE IF NOT EXISTS away_tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL,
  teammate_id INT NOT NULL, teammate_name TEXT DEFAULT '',
  instruction TEXT NOT NULL, due_text TEXT DEFAULT '',
  due_date TEXT DEFAULT '', status TEXT DEFAULT 'pending',
  attempts INT DEFAULT 0, created_by TEXT DEFAULT '',
  creator_id TEXT DEFAULT '', answer_mid INT DEFAULT 0,
  created_at REAL);
"""

DEFAULT_MATES = [
    ("Researcher", "researcher",
     "Find facts fast. Search the web when the answer needs fresh or"
     " external info. Always cite sources."),
    ("Planner", "planner",
     "Break work into small sequenced steps with owners and rough"
     " timelines. Ask one clarifying question when the goal is vague."),
    ("Critic", "critic",
     "Attack the plan like red-team: worst flaw first, every claim needs"
     " a receipt from the thread. Never invent facts."),
]


def connect(path: str = "") -> sqlite3.Connection:
    con = sqlite3.connect(path or S.DB)
    con.row_factory = sqlite3.Row
    try:
        cols = [r[1] for r in
                con.execute("PRAGMA table_info(used_nicks)").fetchall()]
        if cols and "name" not in cols:
            con.execute("DROP TABLE used_nicks")
    except sqlite3.OperationalError:
        pass
    con.executescript(SCHEMA)
    try:
        con.execute("ALTER TABLE invites ADD COLUMN max_uses INT DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE messages ADD COLUMN author_id TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE members ADD COLUMN nick TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE messages DROP COLUMN re")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE messages ADD COLUMN ask_id INT DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE messages ADD COLUMN rating INT DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE costs ADD COLUMN secs REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE proposals ADD COLUMN updates TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE proposals ADD COLUMN needs_detail INT DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE rooms ADD COLUMN model TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE rooms ADD COLUMN locked INT DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE members ADD COLUMN model TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE rooms ADD COLUMN remind_at TEXT"
                    " DEFAULT '09:00'")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE rooms ADD COLUMN last_remind TEXT"
                    " DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE ledger ADD COLUMN due_date TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE rooms ADD COLUMN parent TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE members ADD COLUMN origin TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    return con


NICK_ADJ = ("Swift", "Bright", "Calm", "Bold", "Crisp", "Dapper", "Eager",
            "Fair", "Gentle", "Happy", "Jolly", "Kind", "Lively", "Merry",
            "Neat", "Noble", "Quick", "Quiet", "Rosy", "Sunny", "Tidy",
            "Vivid", "Warm", "Witty", "Zesty", "Clever", "Frosty", "Golden",
            "Misty", "Ivory", "Jade", "Lunar", "Maple")
NICK_NOUN = ("Fox", "Owl", "Bear", "Wolf", "Finch", "Otter", "Hare", "Lynx",
             "Wren", "Mole", "Badger", "Heron", "Newt", "Quail", "Raven",
             "Sparrow", "Trout", "Falcon", "Egret", "Jay", "Lark", "Tern",
             "Mouse", "Shrew", "Stoat", "Weasel", "Bison", "Camel", "Dingo",
             "Gecko", "Hyena", "Iguana")


def deal_nick(con: sqlite3.Connection, room: str, name: str) -> str:
    """Nickname unique inside one name in one room, forever, even after
    leave, so old chat lines keep pointing at the right Ana. Other names
    may freely reuse it."""
    used = {r[0] for r in con.execute(
        "SELECT nick FROM used_nicks WHERE room=? AND name=?", (room, name))}
    nick = ""
    for _ in range(60):
        cand = f"{random.choice(NICK_ADJ)} {random.choice(NICK_NOUN)}"
        if cand not in used:
            nick = cand
            break
    if not nick:
        nick = (f"{random.choice(NICK_ADJ)} {random.choice(NICK_NOUN)}"
                f" {len(used) + 1}")
    con.execute("INSERT OR IGNORE INTO used_nicks (room, name, nick)"
                " VALUES (?,?,?)", (room, name, nick))
    return nick


def _origin_nick(con: sqlite3.Connection, room: str, origin: str) -> str:
    """Nick of the parent-room member this side seat comes from."""
    parent = room_parent(con, room)
    if not parent or not origin:
        return ""
    row = con.execute("SELECT nick FROM members WHERE room=? AND id=?",
                      (parent, origin)).fetchone()
    return row["nick"] if row and row["nick"] else ""


def claim_nick(con: sqlite3.Connection, room: str, name: str,
               want: str = "") -> str:
    """Reuse want when free for (room, name), else deal fresh."""
    if want:
        taken = con.execute(
            "SELECT 1 FROM used_nicks WHERE room=? AND name=? AND nick=?",
            (room, name, want)).fetchone()
        if not taken:
            con.execute("INSERT OR IGNORE INTO used_nicks (room, name, nick)"
                        " VALUES (?,?,?)", (room, name, want))
            return want
    return deal_nick(con, room, name)


def ensure_nicks(con: sqlite3.Connection, room: str) -> None:
    con.execute("INSERT OR IGNORE INTO used_nicks (room, name, nick)"
                " SELECT room, name, nick FROM members"
                " WHERE room=? AND nick IS NOT NULL AND nick<>''", (room,))
    missing = con.execute(
        "SELECT id, name FROM members WHERE room=?"
        " AND (nick IS NULL OR nick='')",
        (room,)).fetchall()
    for r in missing:
        con.execute("UPDATE members SET nick=? WHERE id=?",
                    (deal_nick(con, room, r["name"]), r["id"]))
    if room_parent(con, room):
        for r in con.execute(
                "SELECT id, name, nick, origin FROM members WHERE room=?"
                " AND origin IS NOT NULL AND origin<>''", (room,)):
            want = _origin_nick(con, room, r["origin"])
            if not want or want == r["nick"]:
                continue
            taken = con.execute(
                "SELECT 1 FROM used_nicks WHERE room=? AND name=? AND nick=?",
                (room, r["name"], want)).fetchone()
            if taken:
                continue
            con.execute("UPDATE members SET nick=? WHERE id=?",
                        (want, r["id"]))
            con.execute("INSERT OR IGNORE INTO used_nicks (room, name, nick)"
                        " VALUES (?,?,?)", (room, r["name"], want))
    con.commit()


def new_room(con: sqlite3.Connection, mission: str,
             owner_name: str = "", origin: str = "") -> dict:
    rid = secrets.token_hex(4)
    con.execute(
        "INSERT INTO rooms (id, mission, cost_cap, created_at) VALUES (?,?,?,?)",
        (rid, mission, S.MAX_ROOM_COST, time.time()),
    )
    for name, role, how in DEFAULT_MATES:
        con.execute(
            "INSERT INTO teammates (room, name, role, instructions,"
            " created_by, created_at) VALUES (?,?,?,?,?,?)",
            (rid, name, role, how, "room", time.time()))
    con.commit()
    out = {"room_id": rid}
    if owner_name.strip():
        mid, mtok = secrets.token_hex(4), secrets.token_urlsafe(16)
        con.execute(
            "INSERT INTO members (id, room, name, role, token, nick,"
            " origin, joined_at) VALUES (?,?,?,?,?,?,?,?)",
            (mid, rid, owner_name[:40], "owner", mtok,
             deal_nick(con, rid, owner_name[:40]), origin[:16],
             time.time()))
        con.commit()
        out.update({"name": owner_name[:40], "token": mtok})
    else:
        tok = secrets.token_urlsafe(12)
        con.execute(
            "INSERT INTO invites (token, room, role, expires_at)"
            " VALUES (?,?,?,?)",
            (tok, rid, "owner", time.time() + 7 * 86400))
        con.commit()
        out["invite"] = tok
    return out


def join_member(con: sqlite3.Connection, room: str, name: str, invite: str) -> dict:
    invite = (invite or "").strip()
    inv = con.execute(
        "SELECT * FROM invites WHERE token=? AND room=?", (invite, room)
    ).fetchone()
    if not inv or inv["expires_at"] < time.time() \
            or inv["used"] >= (inv["max_uses"] or 1):
        raise LookupError("bad or expired invite")
    ensure_nicks(con, room)
    con.execute("UPDATE invites SET used=used+1 WHERE token=?", (invite,))
    mid, tok = secrets.token_hex(4), secrets.token_urlsafe(16)
    con.execute(
        "INSERT INTO members (id, room, name, role, token, nick, joined_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (mid, room, name[:40], inv["role"], tok,
         deal_nick(con, room, name[:40]), time.time()),
    )
    parent = room_parent(con, room)
    if parent:
        sibs = con.execute("SELECT id FROM members WHERE room=? AND name=?",
                           (parent, name[:40])).fetchall()
        if len(sibs) == 1:
            con.execute("UPDATE members SET origin=? WHERE id=? AND room=?",
                        (sibs[0]["id"][:16], mid, room))
    con.commit()
    return {"member_id": mid, "name": name[:40], "role": inv["role"], "token": tok}


def seat_member(con: sqlite3.Connection, room: str, name: str,
                role: str = "member", origin: str = "") -> dict:
    """Direct seat, no invite. Side rooms seat parent members this way."""
    ensure_nicks(con, room)
    mid, tok = secrets.token_hex(4), secrets.token_urlsafe(16)
    con.execute(
        "INSERT INTO members (id, room, name, role, token, nick,"
        " origin, joined_at) VALUES (?,?,?,?,?,?,?,?)",
        (mid, room, name[:40], role, tok,
         claim_nick(con, room, name[:40],
                    _origin_nick(con, room, origin[:16])),
         origin[:16], time.time()))
    con.commit()
    return {"member_id": mid, "token": tok}


def member_by_origin(con: sqlite3.Connection, room: str, origin: str):
    if not origin:
        return None
    return con.execute(
        "SELECT * FROM members WHERE room=? AND origin=?",
        (room, origin)).fetchone()


def room_parent(con: sqlite3.Connection, room: str) -> str:
    row = con.execute("SELECT parent FROM rooms WHERE id=?",
                      (room,)).fetchone()
    return row["parent"] if row and row["parent"] else ""


def set_parent(con: sqlite3.Connection, room: str, parent: str) -> None:
    con.execute("UPDATE rooms SET parent=? WHERE id=?", (parent, room))
    con.commit()


def list_sides(con: sqlite3.Connection, room: str) -> list:
    return [{"room_id": r["id"], "mission": r["mission"]}
            for r in con.execute(
                "SELECT id, mission FROM rooms WHERE parent=?"
                " ORDER BY created_at", (room,))]


def mint_invite(con: sqlite3.Connection, room: str, role: str = "member",
                uses: int = 1, hours: int = 24) -> dict:
    uses = max(1, min(int(uses), 50))
    hours = max(0, min(int(hours), 87600))
    tok = secrets.token_urlsafe(12)
    exp = 4102444800.0 if hours <= 0 else time.time() + hours * 3600
    con.execute("INSERT INTO invites (token, room, role, expires_at, max_uses)"
                " VALUES (?,?,?,?,?)",
                (tok, room, role, exp, uses))
    con.commit()
    return {"invite": tok, "uses": uses, "hours": hours}


def list_invites(con: sqlite3.Connection, room: str) -> list:
    return [dict(r) for r in con.execute(
        "SELECT token, role, expires_at, used, max_uses,"
        " (max_uses - used) AS left"
        " FROM invites WHERE room=? ORDER BY expires_at", (room,))]


def topup_invite(con: sqlite3.Connection, room: str, token: str,
                 add: int) -> dict:
    add = max(1, min(int(add), 50))
    inv = con.execute("SELECT * FROM invites WHERE token=? AND room=?",
                      (token, room)).fetchone()
    if not inv:
        raise LookupError("no such invite")
    new_max = min((inv["max_uses"] or 1) + add, 50)
    con.execute("UPDATE invites SET max_uses=? WHERE token=?",
                (new_max, token))
    con.commit()
    return {"invite": token, "uses": new_max,
            "left": new_max - inv["used"]}


def member_by_token(con: sqlite3.Connection, room: str, token: str):
    return con.execute(
        "SELECT * FROM members WHERE room=? AND token=?", (room, token)
    ).fetchone()


def member_by_id(con: sqlite3.Connection, room: str, mid: str):
    return con.execute(
        "SELECT * FROM members WHERE room=? AND id=?", (room, mid)
    ).fetchone()


def remove_member(con: sqlite3.Connection, room: str, mid: str) -> None:
    con.execute("DELETE FROM members WHERE room=? AND id=?", (room, mid))
    con.commit()


def room_locked(con: sqlite3.Connection, room: str) -> bool:
    row = con.execute("SELECT locked FROM rooms WHERE id=?",
                      (room,)).fetchone()
    return bool(row and row["locked"])


def set_room_locked(con: sqlite3.Connection, room: str, on: bool) -> None:
    con.execute("UPDATE rooms SET locked=? WHERE id=?",
                (1 if on else 0, room))
    con.commit()


def set_member_model(con: sqlite3.Connection, room: str, mid: str,
                   model: str) -> None:
    """Personal model choice. Empty string follows the server default."""
    con.execute("UPDATE members SET model=? WHERE room=? AND id=?",
                (model[:80], room, mid))
    con.commit()


def post_message(con: sqlite3.Connection, room: str, author: str, body: str,
                 kind: str = "chat", model: str = "", reasons: str = "",
                 author_id: str = "", ask_id: int = 0) -> int:
    cur = con.execute(
        "INSERT INTO messages (room, author, kind, model, body, reasons,"
        " author_id, ask_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (room, author, kind, model, body[:4000], reasons[:2000],
         author_id[:16], ask_id or 0, time.time()),
    )
    con.commit()
    return cur.lastrowid


def list_members(con: sqlite3.Connection, room: str) -> list:
    return [dict(r) for r in con.execute(
        "SELECT id, name, role, nick, model FROM members WHERE room=?"
        " ORDER BY joined_at",
        (room,))]


def transfer_owner(con: sqlite3.Connection, room: str, new_id: str) -> dict:
    row = con.execute("SELECT id FROM members WHERE room=? AND id=?",
                      (room, new_id)).fetchone()
    if not row:
        raise LookupError("no such member")
    con.execute("UPDATE members SET role='member'"
                " WHERE room=? AND role='owner'", (room,))
    con.execute("UPDATE members SET role='owner' WHERE room=? AND id=?",
                (room, new_id))
    con.commit()
    return {"owner": new_id}


def set_operator(con, room: str, member_id: str) -> dict:
    row = con.execute("SELECT id FROM members WHERE room=? AND id=?",
                      (room, member_id)).fetchone()
    if not row:
        raise LookupError("no such member")
    con.execute("UPDATE members SET role='operator' WHERE room=? AND id=?",
                (room, member_id))
    con.commit()
    return {"operator": member_id}


def oldest_successor(con, room: str, exclude_id: str):
    row = con.execute(
        "SELECT id FROM members WHERE room=? AND id!=? AND role='operator'"
        " ORDER BY joined_at LIMIT 1", (room, exclude_id)).fetchone()
    if not row:
        row = con.execute(
            "SELECT id FROM members WHERE room=? AND id!=?"
            " ORDER BY joined_at LIMIT 1", (room, exclude_id)).fetchone()
    return row["id"] if row else None


def role_badges(con: sqlite3.Connection, room: str) -> dict:
    """member_id -> badge, only for seats with power."""
    return {r["id"]: ("admin" if r["role"] == "owner" else "operator")
            for r in con.execute(
                "SELECT id, role FROM members WHERE room=?"
                " AND role IN ('owner','operator')", (room,))}


def display_tags(con: sqlite3.Connection, room: str) -> dict:
    """member_id -> nickname, for every seat. Uniqueness lives inside
    each name, so every line can wear its nick without confusion."""
    members = [dict(r) for r in con.execute(
        "SELECT id, nick FROM members WHERE room=?", (room,))]
    return {m["id"]: (m["nick"] or m["id"][:4]) for m in members}


def recent(con: sqlite3.Connection, room: str, n: int = 30) -> list:
    return [dict(r) for r in con.execute(
        "SELECT * FROM messages WHERE room=? ORDER BY id DESC LIMIT ?", (room, n))][::-1]


def log_cost(con: sqlite3.Connection, room: str, call: str, model: str,
             tin: int, tout: int, secs: float = 0.0) -> float:
    usd = tin / 1e6 * S.PRICE_IN_PER_M + tout / 1e6 * S.PRICE_OUT_PER_M
    con.execute(
        "INSERT INTO costs (room, call, model, tin, tout, usd, secs,"
        " created_at) VALUES (?,?,?,?,?,?,?,?)",
        (room, call, model, tin, tout, usd, secs, time.time()),
    )
    con.commit()
    return usd


def rate_message(con: sqlite3.Connection, room: str, mid: int,
                 up: bool) -> dict:
    row = con.execute("SELECT kind FROM messages WHERE id=? AND room=?",
                      (mid, room)).fetchone()
    if not row:
        raise LookupError("no such message")
    if row["kind"] not in ("answer", "dissent"):
        raise ValueError("answers and cards only")
    cur = con.execute("UPDATE messages SET rating=? WHERE id=? AND room=?",
                      (1 if up else -1, mid, room))
    con.commit()
    if not cur.rowcount:
        raise LookupError("no such message")
    return {"id": mid, "rating": 1 if up else -1}


def resolve_redteam(con: sqlite3.Connection, room: str, mid: int,
                    verdict: str):
    row = con.execute("SELECT kind FROM messages WHERE id=? AND room=?",
                      (mid, room)).fetchone()
    if not row or row["kind"] != "redteam":
        return None
    con.execute("UPDATE messages SET rating=? WHERE id=? AND room=?",
                ({"fixed": 1, "accepted": 2, "dismissed": 3}[verdict],
                 mid, room))
    con.commit()
    return {"id": mid, "resolved": verdict}


def list_redteam(con: sqlite3.Connection, room: str) -> list:
    return [dict(r) for r in con.execute(
        "SELECT id, body, rating, created_at FROM messages"
        " WHERE room=? AND kind='redteam' ORDER BY id", (room,))]


def _eval_doc(con: sqlite3.Connection, room: str) -> dict:
    row = con.execute("SELECT report FROM eval_runs WHERE room=?",
                      (room,)).fetchone()
    if not row:
        return {}
    try:
        doc = json.loads(row["report"])
    except ValueError:
        return {}
    if not isinstance(doc, dict):
        return {}
    if "sides" in doc:
        return {"duel": doc}  # pre-step-5 row: duel report stored bare
    return doc


def _save_eval_doc(con: sqlite3.Connection, room: str, doc: dict) -> None:
    con.execute("INSERT INTO eval_runs (room, report, created_at)"
                " VALUES (?,?,?) ON CONFLICT(room) DO UPDATE SET"
                " report=excluded.report, created_at=excluded.created_at",
                (room, json.dumps(doc), time.time()))
    con.commit()


def save_golden(con: sqlite3.Connection, room: str, report: str) -> None:
    doc = _eval_doc(con, room)
    doc["golden"] = json.loads(report)
    _save_eval_doc(con, room, doc)


def load_golden(con: sqlite3.Connection, room: str):
    gold = _eval_doc(con, room).get("golden")
    return json.dumps(gold) if gold else None


def _rated(con: sqlite3.Connection, room: str, kind: str):
    row = con.execute(
        "SELECT COUNT(*) AS n,"
        " COALESCE(SUM(CASE WHEN rating>0 THEN 1 ELSE 0 END),0) AS ups"
        " FROM messages WHERE room=? AND kind=? AND rating!=0",
        (room, kind)).fetchone()
    return row["n"], row["ups"]


def room_trust(con: sqlite3.Connection, room: str) -> dict:
    """Trust word from card verdicts. muted > strained > watching."""
    n, ups = _rated(con, room, "dissent")
    mem = con.execute("SELECT value FROM memory WHERE room=?"
                      " AND key='dissent_muted'", (room,)).fetchone()
    if mem and mem["value"] == "1":
        word = "muted"
    elif n == 0:
        word = "watching"
    elif ups / n >= 0.7:
        word = "trusted"
    elif ups / n < 0.5:
        word = "strained"
    else:
        word = "watching"
    return {"word": word, "pct": (ups / n) if n else None, "n": n}


def room_strict(con: sqlite3.Connection, room: str) -> bool:
    """False alarms auto-tighten the bar: three-plus verdicts under
    half fair shrinks the arm window. The severe bypass never passes
    through here, so ledger and mission evidence always speaks."""
    n, ups = _rated(con, room, "dissent")
    return n >= 3 and ups / n < 0.5


def strip_numbers(con: sqlite3.Connection, room: str) -> dict:
    row = con.execute(
        "SELECT COUNT(*) AS n,"
        " COALESCE(SUM(CASE WHEN rating>0 THEN 1 ELSE 0 END),0) AS ups"
        " FROM messages WHERE room=? AND kind='answer' AND rating!=0",
        (room,)).fetchone()
    n, ups = row["n"], row["ups"]
    spd = con.execute("SELECT AVG(secs) AS a, COUNT(*) AS c FROM costs"
                      " WHERE room=? AND call='ask'", (room,)).fetchone()
    dec = con.execute("SELECT COUNT(*) AS c FROM ledger WHERE room=?",
                      (room,)).fetchone()["c"]
    spend = room_cost(con, room)
    return {
        "approval": {"pct": (ups / n) if n else None, "n": n},
        "speed_s": spd["a"] if spd["c"] else None,
        "decisions": dec,
        "spend_usd": spend,
        "cost_per_decision": (spend / dec) if dec else None,
        "trust": room_trust(con, room),
    }


def room_cost(con: sqlite3.Connection, room: str) -> float:
    row = con.execute(
        "SELECT COALESCE(SUM(usd),0) AS t FROM costs WHERE room=?", (room,)).fetchone()
    return row["t"]


def add_ledger(con: sqlite3.Connection, room: str, what: str, who: str = "",
               why: str = "", deadline: str = "") -> dict:
    cur = con.execute(
        "INSERT INTO ledger (room, what, who, why, deadline, due_date,"
        " created_at) VALUES (?,?,?,?,?,?,?)",
        (room, what[:500], who[:80], why[:500], deadline[:40],
         remind.parse_due(deadline), time.time()))
    lid = cur.lastrowid
    if deadline.strip():
        dup = [r for r in list_reminders(con, room)
               if not r["done"]
               and r["text"].strip().lower() == what.strip().lower()]
        if not dup:
            add_reminder(con, room, what[:500], deadline[:40],
                         who[:80], f"ledger:{lid}")
    con.commit()
    return {"id": lid}


def list_ledger(con: sqlite3.Connection, room: str) -> list:
    return [dict(r) for r in con.execute(
        "SELECT * FROM ledger WHERE room=? ORDER BY id", (room,))]


def add_proposal(con: sqlite3.Connection, room: str, what: str, who: str = "",
                 why: str = "", deadline: str = "", by: str = "",
                 updates: str = "", needs: bool = False) -> dict:
    cur = con.execute(
        "INSERT INTO proposals (room, what, who, why, deadline, proposed_by,"
        " state, updates, needs_detail, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (room, what[:500], who[:80], why[:500], deadline[:40], by[:80],
         "open", updates[:500], 1 if needs else 0, time.time()))
    con.commit()
    return {"id": cur.lastrowid, "room": room, "what": what[:500],
            "who": who[:80], "why": why[:500], "deadline": deadline[:40],
            "proposed_by": by[:80], "state": "open",
            "updates": updates[:500], "needs_detail": 1 if needs else 0}


def update_proposal(con: sqlite3.Connection, room: str, pid: int, what: str,
                    who: str = "", why: str = "", deadline: str = "",
                    updates: str = "", needs: bool = False) -> None:
    con.execute(
        "UPDATE proposals SET what=?, who=?, why=?, deadline=?, updates=?,"
        " needs_detail=? WHERE room=? AND id=? AND state='open'",
        (what[:500], who[:80], why[:500], deadline[:40], updates[:500],
         1 if needs else 0, room, pid))
    con.commit()


def find_open_ledger(con: sqlite3.Connection, room: str, what: str):
    want = " ".join(what.split()).lower()
    for r in con.execute("SELECT * FROM ledger WHERE room=? AND status='open'"
                         " ORDER BY id", (room,)):
        if " ".join(r["what"].split()).lower() == want:
            return dict(r)
    return None


def update_ledger(con: sqlite3.Connection, room: str, lid: int, what: str,
                  who: str = "", why: str = "", deadline: str = "") -> bool:
    cur = con.execute(
        "UPDATE ledger SET what=?, who=?, why=?, deadline=?, due_date=?"
        " WHERE room=? AND id=?",
        (what[:500], who[:80], why[:500], deadline[:40],
         remind.parse_due(deadline), room, lid))
    if cur.rowcount:
        linked = [r for r in list_reminders(con, room)
                  if not r["done"] and r["created_by"] == f"ledger:{lid}"]
        for r in linked:
            update_reminder(con, room, r["id"], what[:500],
                            deadline[:40], who[:80])
    con.commit()
    return cur.rowcount > 0


def add_artifact(con: sqlite3.Connection, room: str, title: str,
                 kind: str, body: str, by: str) -> dict:
    now = time.time()
    cur = con.execute(
        "INSERT INTO artifacts (room, title, kind, body, version, status,"
        " created_by, created_at, updated_at)"
        " VALUES (?,?,?,?,1,'draft',?,?,?)",
        (room, title[:120], (kind or "doc")[:12], body[:4000],
         by[:80], now, now))
    aid = cur.lastrowid
    con.execute(
        "INSERT INTO artifact_versions (artifact_id, room, version, body,"
        " edited_by, created_at) VALUES (?,?,1,?,?,?)",
        (aid, room, body[:4000], by[:80], now))
    con.commit()
    return get_artifact(con, room, aid)


def get_artifact(con: sqlite3.Connection, room: str, aid: int):
    row = con.execute("SELECT * FROM artifacts WHERE room=? AND id=?",
                      (room, aid)).fetchone()
    return dict(row) if row else None


def list_artifacts(con: sqlite3.Connection, room: str) -> list:
    return [dict(r) for r in con.execute(
        "SELECT * FROM artifacts WHERE room=? ORDER BY id", (room,))]


def list_versions(con: sqlite3.Connection, room: str, aid: int) -> list:
    return [dict(r) for r in con.execute(
        "SELECT version, body, edited_by, created_at FROM artifact_versions"
        " WHERE room=? AND artifact_id=? ORDER BY version", (room, aid))]


def edit_artifact(con: sqlite3.Connection, room: str, aid: int, title: str,
                  kind: str, body: str, by: str):
    cur = get_artifact(con, room, aid)
    if not cur:
        return None
    now = time.time()
    con.execute(
        "UPDATE artifacts SET title=?, kind=?, body=?, version=?,"
        " status='draft', approved_by='', updated_at=? WHERE room=? AND id=?",
        (title[:120] or cur["title"], (kind or cur["kind"])[:12],
         body[:4000], cur["version"] + 1, now, room, aid))
    con.execute(
        "INSERT INTO artifact_versions (artifact_id, room, version, body,"
        " edited_by, created_at) VALUES (?,?,?,?,?,?)",
        (aid, room, cur["version"] + 1, body[:4000], by[:80], now))
    con.commit()
    return get_artifact(con, room, aid)


def move_artifact(con: sqlite3.Connection, room: str, aid: int, to: str,
                  by: str):
    cur = get_artifact(con, room, aid)
    if not cur:
        return None
    want = {"proposed": "draft", "approved": "proposed",
            "applied": "approved"}.get(to)
    if cur["status"] != want:
        return False
    con.execute(
        "UPDATE artifacts SET status=?, approved_by=?, updated_at=?"
        " WHERE room=? AND id=?",
        (to, by[:80] if to == "approved" else cur["approved_by"],
         time.time(), room, aid))
    con.commit()
    return get_artifact(con, room, aid)


def add_task(con: sqlite3.Connection, room: str, title: str, details: str,
             assignee: str, due: str, by: str) -> dict:
    cur = con.execute(
        "INSERT INTO tasks (room, title, details, assignee, due_text,"
        " due_date, status, created_by, created_at)"
        " VALUES (?,?,?,?,?,?,'open',?,?)",
        (room, title[:200], details[:2000], assignee[:80], due[:40],
         remind.parse_due(due), by[:80], time.time()))
    con.commit()
    return get_task(con, room, cur.lastrowid)


def get_task(con: sqlite3.Connection, room: str, tid: int):
    row = con.execute("SELECT * FROM tasks WHERE room=? AND id=?",
                      (room, tid)).fetchone()
    return dict(row) if row else None


def list_tasks(con: sqlite3.Connection, room: str) -> list:
    return [dict(r) for r in con.execute(
        "SELECT * FROM tasks WHERE room=? ORDER BY"
        " CASE WHEN status='open' THEN 0 ELSE 1 END,"
        " CASE WHEN due_date='' THEN 1 ELSE 0 END, due_date, id",
        (room,))]


def edit_task(con: sqlite3.Connection, room: str, tid: int, title: str,
              details: str, assignee: str, due: str):
    cur = get_task(con, room, tid)
    if not cur:
        return None
    con.execute(
        "UPDATE tasks SET title=?, details=?, assignee=?, due_text=?,"
        " due_date=? WHERE room=? AND id=?",
        (title[:200] or cur["title"], details[:2000], assignee[:80],
         due[:40], remind.parse_due(due), room, tid))
    con.commit()
    return get_task(con, room, tid)


def set_task_done(con: sqlite3.Connection, room: str, tid: int,
                  done: bool):
    if not get_task(con, room, tid):
        return None
    con.execute("UPDATE tasks SET status=? WHERE room=? AND id=?",
                ("done" if done else "open", room, tid))
    con.commit()
    return get_task(con, room, tid)


def delete_task(con: sqlite3.Connection, room: str, tid: int) -> bool:
    cur = con.execute("DELETE FROM tasks WHERE room=? AND id=?",
                      (room, tid))
    con.commit()
    return cur.rowcount > 0


def add_poll(con: sqlite3.Connection, room: str, question: str,
             options: list, by: str) -> dict:
    cur = con.execute(
        "INSERT INTO polls (room, question, options, state, created_by,"
        " created_at) VALUES (?,?,?,'open',?,?)",
        (room, question[:200], json.dumps(options[:4]),
         by[:80], time.time()))
    con.commit()
    return get_poll(con, room, cur.lastrowid)


def get_poll(con: sqlite3.Connection, room: str, pid: int):
    row = con.execute("SELECT * FROM polls WHERE room=? AND id=?",
                      (room, pid)).fetchone()
    if not row:
        return None
    poll = dict(row)
    poll["options"] = json.loads(poll["options"])
    return poll


def list_polls(con: sqlite3.Connection, room: str) -> list:
    rows = con.execute(
        "SELECT * FROM polls WHERE room=? ORDER BY"
        " CASE WHEN state='open' THEN 0 ELSE 1 END, id", (room,))
    polls = []
    for row in rows:
        poll = dict(row)
        poll["options"] = json.loads(poll["options"])
        polls.append(poll)
    return polls


def vote_poll(con: sqlite3.Connection, room: str, pid: int, mid: str,
              name: str, nick: str, idx: int) -> None:
    con.execute(
        "INSERT INTO votes (poll_id, room, member_id, name, nick,"
        " option_idx, created_at) VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(poll_id, member_id) DO UPDATE SET option_idx=?,"
        " name=?, nick=?",
        (pid, room, mid, name[:80], nick[:80], idx, time.time(),
         idx, name[:80], nick[:80]))
    con.commit()


def poll_votes(con: sqlite3.Connection, room: str, pid: int) -> list:
    return [dict(r) for r in con.execute(
        "SELECT member_id, name, nick, option_idx FROM votes"
        " WHERE room=? AND poll_id=?", (room, pid))]


def close_poll(con: sqlite3.Connection, room: str, pid: int):
    con.execute("UPDATE polls SET state='closed' WHERE room=? AND id=?",
                (room, pid))
    con.commit()
    return get_poll(con, room, pid)


def get_showcase(con: sqlite3.Connection, room: str):
    row = con.execute("SELECT token FROM showcase WHERE room=?",
                      (room,)).fetchone()
    return row["token"] if row else ""


def mint_showcase(con: sqlite3.Connection, room: str, by: str) -> str:
    old = get_showcase(con, room)
    if old:
        return old
    tok = secrets.token_urlsafe(16)
    con.execute("INSERT INTO showcase (token, room, created_by, created_at)"
                " VALUES (?,?,?,?)", (tok, room, by[:80], time.time()))
    con.commit()
    return tok


def revoke_showcase(con: sqlite3.Connection, room: str) -> bool:
    cur = con.execute("DELETE FROM showcase WHERE room=?", (room,))
    con.commit()
    return cur.rowcount > 0


def room_by_showcase(con: sqlite3.Connection, token: str) -> str:
    row = con.execute("SELECT room FROM showcase WHERE token=?",
                      (token,)).fetchone()
    return row["room"] if row else ""


def list_teammates(con: sqlite3.Connection, room: str) -> list:
    return [dict(r) for r in con.execute(
        "SELECT * FROM teammates WHERE room=? ORDER BY id", (room,))]


def get_teammate(con: sqlite3.Connection, room: str, tid: int):
    row = con.execute("SELECT * FROM teammates WHERE room=? AND id=?",
                      (room, tid)).fetchone()
    return dict(row) if row else None


def _mate_taken(con: sqlite3.Connection, room: str, name: str,
                skip: int = 0) -> bool:
    row = con.execute(
        "SELECT id FROM teammates WHERE room=? AND lower(name)=lower(?)",
        (room, name)).fetchone()
    return bool(row and row["id"] != skip)


def add_teammate(con: sqlite3.Connection, room: str, name: str, role: str,
                 instructions: str, by: str):
    if _mate_taken(con, room, name):
        return None
    cur = con.execute(
        "INSERT INTO teammates (room, name, role, instructions,"
        " created_by, created_at) VALUES (?,?,?,?,?,?)",
        (room, name[:40], (role or "teammate")[:80],
         instructions[:500], by[:80], time.time()))
    con.commit()
    return get_teammate(con, room, cur.lastrowid)


def edit_teammate(con: sqlite3.Connection, room: str, tid: int, name: str,
                  role: str, instructions: str):
    cur = get_teammate(con, room, tid)
    if not cur:
        return None
    name = name[:40] or cur["name"]
    if _mate_taken(con, room, name, tid):
        return False
    con.execute(
        "UPDATE teammates SET name=?, role=?, instructions=?"
        " WHERE room=? AND id=?",
        (name, role[:80], instructions[:500], room, tid))
    con.commit()
    return get_teammate(con, room, tid)


def delete_teammate(con: sqlite3.Connection, room: str, tid: int) -> bool:
    cur = con.execute("DELETE FROM teammates WHERE room=? AND id=?",
                      (room, tid))
    con.commit()
    return cur.rowcount > 0


def add_away(con: sqlite3.Connection, room: str, mate: dict,
             instruction: str, due: str, by: str, creator_id: str) -> dict:
    cur = con.execute(
        "INSERT INTO away_tasks (room, teammate_id, teammate_name,"
        " instruction, due_text, due_date, status, created_by,"
        " creator_id, created_at)"
        " VALUES (?,?,?,?,?,?,'pending',?,?,?)",
        (room, mate["id"], mate["name"][:40], instruction[:2000],
         due[:40], remind.parse_due(due), by[:80], creator_id[:16],
         time.time()))
    con.commit()
    row = con.execute("SELECT * FROM away_tasks WHERE id=?",
                      (cur.lastrowid,)).fetchone()
    return dict(row)


def list_away(con: sqlite3.Connection, room: str) -> list:
    return [dict(r) for r in con.execute(
        "SELECT a.*, COALESCE(m.body, '') AS answer FROM away_tasks a"
        " LEFT JOIN messages m ON m.id=a.answer_mid AND m.room=a.room"
        " WHERE a.room=? ORDER BY a.id", (room,))]


def delete_away(con: sqlite3.Connection, room: str, aid: int) -> bool:
    cur = con.execute("DELETE FROM away_tasks WHERE room=? AND id=?",
                      (room, aid))
    con.commit()
    return cur.rowcount > 0


def due_away(con: sqlite3.Connection, today: str) -> list:
    return [dict(r) for r in con.execute(
        "SELECT * FROM away_tasks WHERE status='pending'"
        " AND due_date!='' AND due_date<=? ORDER BY id", (today,))]


def mark_away(con: sqlite3.Connection, aid: int, status: str,
              attempts: int = 0, answer_mid: int = 0) -> None:
    con.execute("UPDATE away_tasks SET status=?, attempts=?,"
                " answer_mid=? WHERE id=?",
                (status, attempts, answer_mid, aid))
    con.commit()


def add_reminder(con: sqlite3.Connection, room: str, text: str,
                 due: str = "", owner: str = "", by: str = "") -> dict:
    cur = con.execute(
        "INSERT INTO reminders (room, text, due_text, due_date, owner,"
        " created_by, created_at) VALUES (?,?,?,?,?,?,?)",
        (room, text[:500], due[:40], remind.parse_due(due), owner[:80],
         by[:80], time.time()))
    con.commit()
    return {"id": cur.lastrowid}


def list_reminders(con: sqlite3.Connection, room: str) -> list:
    return [dict(r) for r in con.execute(
        "SELECT * FROM reminders WHERE room=? ORDER BY done,"
        " CASE WHEN due_date='' THEN 1 ELSE 0 END, due_date, id",
        (room,))]


def get_reminder(con: sqlite3.Connection, room: str, rid: int):
    return con.execute(
        "SELECT * FROM reminders WHERE room=? AND id=?",
        (room, rid)).fetchone()


def update_reminder(con: sqlite3.Connection, room: str, rid: int,
                    text: str = "", due=None, owner=None,
                    done=None) -> bool:
    row = get_reminder(con, room, rid)
    if not row:
        return False
    text = (text or row["text"])[:500]
    due_text = row["due_text"] if due is None else due[:40]
    owner = row["owner"] if owner is None else owner[:80]
    done = row["done"] if done is None else (1 if done else 0)
    con.execute(
        "UPDATE reminders SET text=?, due_text=?, due_date=?, owner=?,"
        " done=? WHERE room=? AND id=?",
        (text, due_text, remind.parse_due(due_text), owner, done,
         room, rid))
    by = row["created_by"] or ""
    if by.startswith("ledger:") and by[7:].isdigit():
        con.execute("UPDATE ledger SET status=? WHERE room=? AND id=?",
                    ("done" if done else "open", room, int(by[7:])))
    con.commit()
    return True


def delete_reminder(con: sqlite3.Connection, room: str, rid: int) -> bool:
    cur = con.execute("DELETE FROM reminders WHERE room=? AND id=?",
                      (room, rid))
    con.commit()
    return cur.rowcount > 0


def room_mission(con: sqlite3.Connection, room: str) -> str:
    row = con.execute("SELECT mission FROM rooms WHERE id=?",
                      (room,)).fetchone()
    return row["mission"] if row else ""


def room_remind_at(con: sqlite3.Connection, room: str) -> str:
    row = con.execute("SELECT remind_at FROM rooms WHERE id=?",
                      (room,)).fetchone()
    at = remind.normalize_at(row["remind_at"] if row else "")
    return at or "09:00"


def set_remind_at(con: sqlite3.Connection, room: str, at: str) -> None:
    con.execute("UPDATE rooms SET remind_at=? WHERE id=?", (at, room))
    con.commit()


def room_last_remind(con: sqlite3.Connection, room: str) -> str:
    row = con.execute("SELECT last_remind FROM rooms WHERE id=?",
                      (room,)).fetchone()
    return row["last_remind"] if row and row["last_remind"] else ""


def set_last_remind(con: sqlite3.Connection, room: str, mark: str) -> None:
    con.execute("UPDATE rooms SET last_remind=? WHERE id=?", (mark, room))
    con.commit()


def list_proposals(con: sqlite3.Connection, room: str,
                   state: str = "open") -> list:
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM proposals WHERE room=? AND state=? ORDER BY id",
        (room, state))]
    for p in rows:
        p["updates_what"] = ""
        ref = (p["updates"] or "").strip().upper()
        if ref.startswith("L") and ref[1:].isdigit():
            led = get_ledger(con, room, int(ref[1:]))
            if led:
                p["updates_what"] = led["what"]
    return rows


STOPWORDS = frozenset("""the a an to and or of for on in is are be it its
    this that these those with from by as at we our my your their his her
    will shall should would could can do does did done so if then than too
    just about into over after before up out off all also get got let lets
    s t m re ve ll d""".split())


def _content_words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower())
            if w not in STOPWORDS and len(w) > 1}


def _overlap(a: set, b: set) -> float:
    if not a or not b or min(len(a), len(b)) < 5:
        return 0.0
    score = len(a & b) / min(len(a), len(b))
    return score if score >= 0.5 else 0.0


def find_similar_open(con: sqlite3.Connection, room: str, what: str):
    """Best (kind, id) among open cards and stamped lines: exact text
    always links; paraphrases link on word overlap. None when unsure."""
    want = " ".join(what.split()).lower()
    words = _content_words(what)
    best = None
    for p in list_proposals(con, room):
        w = " ".join(p["what"].split()).lower()
        if w == want:
            continue  # exact card dupes stay silent upstream
        s = _overlap(words, _content_words(p["what"]))
        if s and (best is None or s > best[0]):
            best = (s, "P", p["id"])
    for r in con.execute("SELECT id, what FROM ledger WHERE room=?"
                         " AND status='open' ORDER BY id", (room,)):
        w = " ".join(r["what"].split()).lower()
        if w == want:
            return ("L", r["id"])
        s = _overlap(words, _content_words(r["what"]))
        if s and (best is None or s > best[0]):
            best = (s, "L", r["id"])
    return (best[1], best[2]) if best else None


def get_ledger(con: sqlite3.Connection, room: str, lid: int):
    r = con.execute("SELECT * FROM ledger WHERE room=? AND id=?",
                    (room, lid)).fetchone()
    return dict(r) if r else None


def get_proposal(con: sqlite3.Connection, room: str, pid: int):
    r = con.execute("SELECT * FROM proposals WHERE room=? AND id=?",
                    (room, pid)).fetchone()
    return dict(r) if r else None


def settle_proposal(con: sqlite3.Connection, room: str, pid: int,
                    state: str, what: str = "", who: str = "",
                    why: str = "", deadline: str = "") -> bool:
    cur = con.execute(
        "UPDATE proposals SET state=?, what=?, who=?, why=?, deadline=?"
        " WHERE room=? AND id=? AND state='open'",
        (state, what[:500], who[:80], why[:500], deadline[:40], room, pid))
    con.commit()
    return cur.rowcount > 0


def delete_room(con: sqlite3.Connection, room: str) -> None:
    for t in ("costs", "ledger", "memory", "messages", "members", "invites",
              "used_nicks", "eval_runs", "rooms"):
        col = "id" if t == "rooms" else ("token" if False else "room")
        key = "id" if t in ("rooms",) else ("room" if t != "invites" else "room")
        con.execute(f"DELETE FROM {t} WHERE {key}=?", (room,))
    con.commit()
