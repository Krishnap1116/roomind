"""Deadline reminders: date words, windows, and the nudge itself.

No background scheduler. The server checks lazily on room activity:
in a chosen window and not yet nudged today means one post, max.
"""
import datetime
import re

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday")


def now_local() -> datetime.datetime:
    return datetime.datetime.now()


def _norm(s) -> str:
    return " ".join((s or "").split()).lower()


def due_label(text: str) -> str:
    """'by X' exactly once, even when X already starts with 'by'."""
    t = (text or "").strip()
    if not t:
        return "no date"
    if re.match(r"(?i)^by(\s|$)", t):
        return t
    return f"by {t}"


def parse_due(text: str, today=None) -> str:
    """Date words to YYYY-MM-DD. Unparseable means '', never a guess."""
    word = (text or "").strip().lower()
    if word.startswith("by "):
        word = word[3:].strip()
    if not word:
        return ""
    base = today or now_local().date()
    if word in ("today", "tonight"):
        return base.isoformat()
    if word in ("tomorrow", "tmrw", "tmr"):
        return (base + datetime.timedelta(days=1)).isoformat()
    if word == "yesterday":
        return (base - datetime.timedelta(days=1)).isoformat()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", word)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)),
                                 int(m.group(3))).isoformat()
        except ValueError:
            return ""
    if word in WEEKDAYS:
        delta = (WEEKDAYS.index(word) - base.weekday()) % 7
        return (base + datetime.timedelta(days=delta)).isoformat()
    return ""


def normalize_at(value: str):
    """'off' or zero-padded HH:MM. Anything else means None."""
    v = (value or "").strip().lower()
    if v == "off":
        return "off"
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", v)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


def due_at(sched: str, now, last_mark: str) -> bool:
    """True when the daily time has come and today is unstamped."""
    at = normalize_at(sched)
    if not at or at == "off":
        return False
    if last_mark == now.date().isoformat():
        return False
    return (now.hour, now.minute) >= (int(at[:2]), int(at[3:]))


def flag(due: str, today: str) -> str:
    if not due:
        return ""
    if due < today:
        return "OVERDUE"
    if due == today:
        return "DUE TODAY"
    return ""


def compose(mission: str, ledger_rows: list, reminder_rows: list,
            today: str) -> str:
    """One nudge body. Empty string when nothing is open."""
    lines = []
    seen = set()
    open_whats = set()
    done_lids = set()
    for r in reminder_rows:
        by = (r.get("created_by") or "")
        if r.get("done") and by.startswith("ledger:") and by[7:].isdigit():
            done_lids.add(int(by[7:]))
    for row in ledger_rows:
        if row.get("status", "open") != "open":
            continue
        if row.get("id") in done_lids:
            continue  # mirror was finished, even if the line predates that
        f = flag(row.get("due_date") or "", today)
        bit = due_label(row.get("deadline") or "")
        if f:
            bit += f" [{f}]"
        who = f" — {row['who']}" if row.get("who") else ""
        key = (_norm(row.get("what")), _norm(row.get("who")),
               row.get("due_date") or _norm(row.get("deadline")))
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"• {row['what']}{who} ({bit})")
        open_whats.add((row["what"] or "").strip().lower())
    for row in reminder_rows:
        if row.get("done"):
            continue
        if (row.get("created_by") or "").startswith("ledger:") \
                and (row.get("text") or "").strip().lower() in open_whats:
            continue  # mirror of a listed ledger line, not a second fact
        f = flag(row.get("due_date") or "", today)
        bit = due_label(row.get("due_text") or "")
        if f:
            bit += f" [{f}]"
        who = f" — {row['owner']}" if row.get("owner") else ""
        key = (_norm(row.get("text")), _norm(row.get("owner")),
               row.get("due_date") or _norm(row.get("due_text")))
        if key in seen:
            continue  # same fact already listed, whatever its source
        seen.add(key)
        lines.append(f"• {row['text']}{who} ({bit})")
    if not lines:
        return ""
    head = f"Reminder — {mission}" if mission else "Reminder"
    return head + "\n" + "\n".join(lines)
