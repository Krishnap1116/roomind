"""Room memory: small counted facts. No training, just remembering."""
import time


def remember(con, room: str, key: str, value: str):
    key, value = key.strip().lower()[:80], value.strip()[:500]
    if not key or not value:
        return None
    row = con.execute("SELECT n FROM memory WHERE room=? AND key=?",
                      (room, key)).fetchone()
    if row:
        con.execute("UPDATE memory SET value=?, n=n+1, updated_at=?"
                    " WHERE room=? AND key=?", (value, time.time(), room, key))
    else:
        con.execute("INSERT INTO memory (room, key, value, updated_at)"
                    " VALUES (?,?,?,?)", (room, key, value, time.time()))
    con.commit()
    return key


STOP = set("the a an and or to of in on for with is are was were be do does"
           " did what when where who how why not no yes please thanks".split())


def _words(s: str) -> set:
    return {w.strip(".,!?;:").lower() for w in s.split()} - STOP - {""}


def recall(con, room: str, query: str, n: int = 3) -> list:
    q = _words(query)
    if not q:
        return []
    out = []
    for r in con.execute("SELECT key, value, n FROM memory WHERE room=?",
                         (room,)):
        hit = len(q & _words(r["key"] + " " + r["value"]))
        if hit:
            out.append((hit + min(r["n"], 5) * 0.1, r["key"], r["value"]))
    out.sort(reverse=True)
    return [{"key": k, "value": v} for _, k, v in out[:n]]


def forget(con, room: str, key: str) -> None:
    con.execute("DELETE FROM memory WHERE room=? AND key=?",
                (room, key.strip().lower()))
    con.commit()
