"""Claude-shape loop: the model picks tools for a few rounds, then FINAL."""
from . import search as tools_mod

LOOP_SYS = (
    "You answer inside a shared team room. Reply with ONLY one command line, nothing else:"
    " TOOL SEARCH <query> | TOOL OPEN <url> | TOOL WEATHER <place> | FINAL <answer>."
    " You HAVE live tools: web search, page opening, and weather. Never claim you lack"
    " live access or current data; use a tool instead."
    " Search first when the question touches anything current or changing:"
    " news, prices, weather, scores, tools, services, comparisons,"
    " recommendations, recent events, anything after training."
    " Weather or temperature questions always use TOOL WEATHER."
    " Open the most promising result with TOOL OPEN when snippets are thin."
    " Otherwise answer Final directly from knowledge. If a previous answer already covers this, reply briefly pointing to it, never a full repeat."
    " You have {n} tool rounds. Tool results arrive as TOOL RESULT."
    " FINAL answers that used tool results must end with Sources: ... naming them."
    " If results are thin or empty, answer with what you have and say what you"
    " could not verify. Never invent tool results."
    " Optional second line (max 2): MEMORY <key> :: <value> for lasting facts."
)


def _parse(text: str) -> tuple:
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    mem, body = [], []
    for line in lines[1:]:
        if line.upper().startswith("MEMORY ") and "::" in line \
                and len(mem) < 2:
            k, v = line[7:].split("::", 1)
            if k.strip() and v.strip():
                mem.append({"key": k.strip()[:80],
                            "value": v.strip()[:500]})
                continue
        body.append(line)
    first = lines[0] if lines else ""
    up = first.upper()
    if up.startswith("TOOL SEARCH "):
        return ("search", first[12:].strip(), mem)
    if up.startswith("TOOL WEATHER "):
        return ("weather", first[13:].strip(), mem)
    if up.startswith("TOOL OPEN "):
        return ("open", first[10:].strip(), mem)
    if up.startswith("FINAL "):
        head = first[6:].strip()
        rest = "\n".join(body)
        return ("final", (head + ("\n" + rest if rest else "")).strip(),
                mem)
    tail = "\n".join([first] + body).strip()
    up = tail.upper()
    if "TOOL SEARCH " in up or "TOOL WEATHER " in up or "TOOL OPEN " in up:
        return ("format", "", mem)  # chatter around a command: correct it
    return ("final", tail, mem)


def _done(answer, calls, sources, remember, used):
    if sources:
        reasons = sources[:4]
    elif used:
        reasons = ["live check came back empty"]
    else:
        reasons = ["answered from model knowledge, no live check"]
    return {"answer": answer, "reasons": reasons,
            "remember": remember[:2], "calls": calls,
            "searched": used}


def run_loop(call, tools: dict, question: str, history=None,
             notes=None, rounds: int = 3) -> dict:
    """Drive TOOL/FINAL turns. call(msgs)->{text,tin,tout}. Bounded."""
    msgs = [{"role": "system",
             "content": LOOP_SYS.replace("{n}", str(rounds))}]
    if notes:
        lines = "\n".join(f"- {n['key']}: {n['value']}" for n in notes[:5])
        msgs.append({"role": "system", "content": "Room notes:\n" + lines})
    msgs += [{"role": "user" if m["author"] != "agent" else "assistant",
              "content": f"{m['author']}: {m['body']}"}
             for m in (history or [])[-12:]]
    msgs.append({"role": "user", "content": question})
    calls, sources, remember = [], [], []
    used = False
    for _ in range(rounds):
        out = call(msgs)
        calls.append({"tin": out["tin"], "tout": out["tout"]})
        kind, arg, mem = _parse(out["text"])
        for m in mem:
            if m not in remember:
                remember.append(m)
        if kind == "final":
            return _done(arg or out["text"].strip(), calls, sources,
                         remember, used)
        if kind == "format":
            res = ("Wrong shape. Reply with ONLY one command line, nothing"
                   " else: TOOL SEARCH <query> | TOOL OPEN <url> |"
                   " TOOL WEATHER <place> | FINAL <answer>.")
        else:
            fn = tools.get(kind)
            if not arg or fn is None:
                res = "Your tool call was empty. Retry or reply FINAL."
            else:
                used = True
                res, labels = fn(arg)
                sources.extend(lb for lb in labels if lb not in sources)
        msgs.append({"role": "assistant", "content": out["text"]})
        msgs.append({"role": "user",
                     "content": "TOOL RESULT:\n" + res[:2000]})
    msgs.append({"role": "user", "content": "Tool budget spent. Reply FINAL"
                                            " with your best answer now."})
    out = call(msgs)
    calls.append({"tin": out["tin"], "tout": out["tout"]})
    kind, arg, mem = _parse(out["text"])
    for m in mem:
        if m not in remember:
            remember.append(m)
    if kind == "final" and arg:
        return _done(arg, calls, sources, remember, used)
    return _done(out["text"].strip(), calls, sources, remember, used)


def streaming_call(stream_fn, on_token):
    """call-compatible turn over a token stream. Emits FINAL text only:
    tool turns stay silent, the FINAL prefix and MEMORY tails are hidden."""

    def call(msgs):
        buf, tin, tout = "", 0, 0
        live, dead, sent, pre = False, False, 0, 0
        for ev in stream_fn(msgs):
            if ev[0] == "usage":
                tin, tout = ev[1], ev[2]
                continue
            buf += ev[1]
            if not live and not dead and "\n" in buf:
                kind, _, _ = _parse(buf.split("\n", 1)[0])
                if kind == "final":
                    live = True
                    ln = buf.split("\n", 1)[0]
                    if ln.upper().startswith("FINAL "):
                        pre = buf.index(ln) + 6
                else:
                    dead = True
            if live:
                cut = max(sent, len(buf) - 200)
                if cut > sent:
                    on_token(buf[sent:cut] if sent else buf[pre:cut])
                    sent = cut
        if not live and not dead:
            kind, _, _ = _parse(buf)
            live = kind == "final"
            if live and buf.lstrip().upper().startswith("FINAL "):
                pre = len(buf) - len(buf.lstrip()) + 6
        if live:
            tail = buf[sent:] if sent else buf[pre:]
            tail = "\n".join(ln for ln in tail.split("\n")
                             if not ln.strip().upper().startswith("MEMORY "))
            on_token(tail)
        return {"text": buf, "tin": tin, "tout": tout}

    return call


def toolset(search_key: str = "",
            search_base: str = "https://api.tavily.com") -> dict:
    """Live tools over search.py. Keyless search degrades, never crashes."""

    def do_search(q):
        rows = tools_mod.web_search(q, search_key, search_base or
                                    "https://api.tavily.com")
        if not rows:
            if not search_key:
                return ("Web search is unavailable (no key). Answer from"
                        " knowledge and say you could not check live.", [])
            return ("No results found. Answer with what you have and say"
                    " what you could not verify.", [])
        lines = [f"{i + 1}. {r['title']} — {r['snippet']} ({r['url']})"
                 for i, r in enumerate(rows)]
        labels = [f"{r['title']} ({r['url']})" for r in rows[:3]
                  if r["url"] or r["title"]]
        return ("\n".join(lines), labels or ["web search"])

    def do_weather(place):
        w = tools_mod.weather(place)
        if not w or w.get("temp_c") is None:
            return (f"Weather lookup failed for {place}. Say so,"
                    " do not guess.", [])
        label = f"Open-Meteo: {w.get('place', place)}"
        return (f"{w.get('place', place)}: {w['temp_c']}°C,"
                f" {tools_mod.describe(w.get('code'))}.", [label])

    def do_open(url):
        page = tools_mod.open_page(url)
        if not page or not page.get("text"):
            return (f"Could not open {url}. Answer from the snippets and"
                    " say what you could not verify.", [])
        label = f"{page.get('title') or url} ({url})"
        return (f"Opened {url}:\n{page['text'][:2000]}", [label])

    return {"search": do_search, "weather": do_weather, "open": do_open}
