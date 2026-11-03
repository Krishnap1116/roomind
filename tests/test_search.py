"""Web loop: model picks tools, answers carry sources. No network."""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import roomind.agent as agent
import roomind.meta as meta
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


def _call(script):
    seen = []

    def call(msgs):
        seen.append(msgs)
        text = script[min(len(seen) - 1, len(script) - 1)]
        return {"text": text, "tin": 10, "tout": 5}

    return call, seen


def _boom(q):
    raise AssertionError("tool must not run: " + q)


def test_direct_answer_never_searches():
    tools = {"search": _boom, "weather": _boom}
    call, _ = _call(["FINAL Paris is the capital of France."])
    out = agent.run_loop(call, tools, "capital of France?")
    assert out["answer"] == "Paris is the capital of France."
    assert out["searched"] is False and len(out["calls"]) == 1
    assert out["reasons"] == ["answered from model knowledge, no live check"]


def test_search_then_final_cites():
    def do_search(q):
        assert "Mars" in q
        return ("1. NASA slips sample return — budget cuts (http://nasa/x)",
                ["NASA slips sample return (http://nasa/x)"])

    call, seen = _call(["TOOL SEARCH Mars sample return delay",
                        "FINAL It slipped over budget. Sources: NASA (http://nasa/x)"])
    out = agent.run_loop(call, {"search": do_search, "weather": _boom},
                         "why did Mars sample slip?")
    assert out["searched"] is True and len(out["calls"]) == 2
    assert "http://nasa/x" in out["reasons"][0]
    assert "TOOL RESULT" in seen[1][-1]["content"]
    assert "NASA slips" in seen[1][-1]["content"]


def test_two_hops_then_final():
    calls = []

    def do_search(q):
        calls.append(q)
        return (f"hits for {q}", [f"src:{q}"])

    script = ["TOOL SEARCH score", "TOOL SEARCH score final",
              "FINAL 2-1. Sources: src:score final"]
    out = agent.run_loop(_call(script)[0], {"search": do_search,
                                            "weather": _boom}, "score?")
    assert calls == ["score", "score final"]
    assert len(out["calls"]) == 3 and out["searched"] is True


def test_round_cap_forces_final():
    call, _ = _call(["TOOL SEARCH more"] * 6)
    tools = {"search": lambda q: ("thin", []), "weather": _boom}
    out = agent.run_loop(call, tools, "q?", rounds=2)
    assert len(out["calls"]) == 3  # 2 rounds + forced final
    assert out["reasons"] == ["live check came back empty"]


def test_memory_lines_saved():
    call, _ = _call(["FINAL ok\nMEMORY standup :: 9am daily"])
    out = agent.run_loop(call, {"search": _boom, "weather": _boom}, "hi")
    assert out["remember"] == [{"key": "standup", "value": "9am daily"}]


def test_plain_text_is_final_not_a_loop():
    call, _ = _call(["just some words"])
    out = agent.run_loop(call, {"search": _boom, "weather": _boom}, "hi")
    assert out["answer"] == "just some words"
    assert len(out["calls"]) == 1


def test_chatter_around_command_gets_corrected():
    kind, arg, _ = agent._parse("I'll search for it.TOOL SEARCH austin f1")
    assert (kind, arg) == ("format", "")
    seen_calls = []

    def do_search(q):
        seen_calls.append(q)
        return ("Verstappen won (http://f1/x)", ["F1 (http://f1/x)"])

    script = ["I'll search for it.TOOL SEARCH austin f1",
              "TOOL SEARCH austin f1 winner",
              "FINAL Verstappen won. Sources: F1 (http://f1/x)"]
    call, seen = _call(script)
    out = agent.run_loop(call, {"search": do_search, "weather": _boom},
                         "who won F1 Austin?")
    assert out["searched"] is True
    assert seen_calls == ["austin f1 winner"]
    assert any("Wrong shape" in m["content"] for m in seen[0])
    assert "TOOL SEARCH" not in out["answer"]


def test_keyless_search_degrades_without_network():
    res, labels = agent.toolset("")["search"]("anything")
    assert labels == [] and "no key" in res


def test_web_search_tavily_shape(monkeypatch):
    seen = {}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [{"title": "T", "url": "http://t",
                                 "content": "SNIP"}]}

    def fake_post(url, **k):
        seen["url"] = url
        seen["body"] = k["json"]
        return Resp()

    monkeypatch.setattr(agent.tools_mod.httpx, "post", fake_post)
    rows = agent.tools_mod.web_search("q", "tvly-x")
    assert seen["url"] == "https://api.tavily.com/search"
    assert seen["body"]["query"] == "q"
    assert rows == [{"title": "T", "url": "http://t", "snippet": "SNIP"}]


def test_open_page_strips_markup(monkeypatch):
    html = ("<html><head><title>Sample Story</title>"
            "<script>var x = 1;</script></head>"
            "<body><nav>menu links</nav><p>First paragraph here.</p>"
            "<p>Second line &amp; more.</p></body></html>")

    class Resp:
        text = html

        def raise_for_status(self):
            pass

    monkeypatch.setattr(agent.tools_mod.httpx, "get",
                        lambda *a, **k: Resp())
    page = agent.tools_mod.open_page("https://example.com/s")
    assert page["title"] == "Sample Story"
    assert page["text"] == "First paragraph here. Second line & more."
    assert agent.tools_mod.open_page("ftp://x") == {}
    assert agent.tools_mod.open_page("   ") == {}

    def boom(*a, **k):
        raise ValueError("down")

    monkeypatch.setattr(agent.tools_mod.httpx, "get", boom)
    assert agent.tools_mod.open_page("https://example.com/s") == {}


def test_parse_open_command():
    assert agent._parse("TOOL OPEN https://example.com/s") == (
        "open", "https://example.com/s", [])
    kind, _, _ = agent._parse("let me open it. TOOL OPEN https://x")
    assert kind == "format"


def test_search_open_then_final():
    seen = []

    def do_search(q):
        seen.append(("search", q))
        return ("1. Story — short bit (http://x/s)", ["Story (http://x/s)"])

    def do_open(url):
        seen.append(("open", url))
        return ("Opened http://x/s:\nfull story text", ["Story (http://x/s)"])

    script = ["TOOL SEARCH mars delay", "TOOL OPEN http://x/s",
              "FINAL It slipped over budget. Sources: Story (http://x/s)"]
    call, _ = _call(script)
    out = agent.run_loop(call, {"search": do_search, "open": do_open,
                                "weather": _boom}, "why did it slip?")
    assert seen == [("search", "mars delay"), ("open", "http://x/s")]
    assert out["searched"] is True and len(out["calls"]) == 3
    assert "http://x/s" in out["reasons"][0]


def test_toolset_open_labels_page(monkeypatch):
    monkeypatch.setattr(agent.tools_mod, "open_page",
                        lambda u: {"title": "T", "text": "BODY"})
    res, labels = agent.toolset()["open"]("http://x/s")
    assert "BODY" in res and labels == ["T (http://x/s)"]
    monkeypatch.setattr(agent.tools_mod, "open_page", lambda u: {})
    res, labels = agent.toolset()["open"]("http://x/missing")
    assert labels == [] and "Could not open" in res


def test_toolset_weather_labels_source(monkeypatch):
    monkeypatch.setattr(agent.tools_mod, "weather",
                        lambda p: {"place": "Los Angeles", "temp_c": 21.5,
                                   "code": 1})
    res, labels = agent.toolset()["weather"]("LA")
    assert "21.5" in res and labels == ["Open-Meteo: Los Angeles"]


def test_describe_bounds():
    assert agent.tools_mod.describe(63) == "rain"
    assert agent.tools_mod.describe(999) == "unsettled"
    assert agent.tools_mod.describe(None) == "unsettled"
    assert agent.tools_mod.weather("   ") == {}


def test_parse_keeps_multiline_final_and_memory():
    kind, arg, mem = agent._parse("FINAL line one\nline two\nMEMORY k :: v")
    assert (kind, arg) == ("final", "line one\nline two")
    assert mem == [{"key": "k", "value": "v"}]


def test_streaming_final_flows_without_prefix():
    toks = []
    chunks = [("tok", "FINAL hel"), ("tok", "lo\nwor"), ("tok", "ld"),
              ("usage", 3, 1)]
    call = agent.streaming_call(lambda ms: iter(chunks), toks.append)
    out = call([])
    assert "".join(toks) == "hello\nworld"
    assert (out["tin"], out["tout"]) == (3, 1)
    assert out["text"] == "FINAL hello\nworld"


def test_streaming_long_final_hides_memory_tail():
    body = "w " * 150
    toks = []
    chunks = [("tok", "FINAL " + body + "\nMEMORY k :: v"),
              ("usage", 1, 1)]
    call = agent.streaming_call(lambda ms: iter(chunks), toks.append)
    call([])
    assert "".join(toks) == body
    assert len(toks) > 1  # flowed progressively, not one blob


def test_streaming_tool_turn_silent():
    toks = []
    chunks = [("tok", "TOOL SEARCH x\nmore"), ("usage", 1, 1)]
    call = agent.streaming_call(lambda ms: iter(chunks), toks.append)
    out = call([])
    assert toks == [] and out["text"] == "TOOL SEARCH x\nmore"


def test_chat_stream_parses_sse(monkeypatch):
    lines = ["data: " + json.dumps({"choices": [{"delta": {"content": "hi"}}]}),
             "data: " + json.dumps({"choices": [{"delta": {}}],
                                              "usage": {"prompt_tokens": 3,
                                                        "completion_tokens": 1}}),
             "data: [DONE]"]

    class Resp:
        headers = {"content-type": "text/event-stream"}

        def raise_for_status(self):
            pass

        def iter_lines(self):
            return lines

    class Ctx:
        def __enter__(self):
            return Resp()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(meta.httpx, "stream", lambda *a, **k: Ctx())
    assert list(meta.chat_stream("k", "http://x", "m", [])) == [("tok", "hi"),
                                                                ("usage", 3, 1)]


def test_chat_stream_falls_back_without_sse(monkeypatch):
    body = json.dumps({"choices": [{"message": {"content": "ALL"}}],
                       "usage": {"prompt_tokens": 5,
                                 "completion_tokens": 2}})

    class Resp:
        headers = {"content-type": "application/json"}

        def raise_for_status(self):
            pass

        def read(self):
            return body

    class Ctx:
        def __enter__(self):
            return Resp()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(meta.httpx, "stream", lambda *a, **k: Ctx())
    assert list(meta.chat_stream("k", "http://x", "m", [])) == [("tok", "ALL"),
                                                                ("usage", 5, 2)]


def test_askstream_streams_then_saves(client, monkeypatch):
    seen = {}

    def fake_stream(api_key, base, model, messages, timeout=120.0, effort=""):
        seen["effort"] = effort
        yield ("tok", "FINAL hel")
        yield ("tok", "lo")
        yield ("usage", 3, 1)

    monkeypatch.setattr(web.meta, "chat_stream", fake_stream)
    monkeypatch.setattr(S, "ASK_EFFORT", "minimal")
    monkeypatch.setattr(web.dissent, "maybe_fire",
                        lambda con, rid, model: None)
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    r = client.get(f"/rooms/{rid}/askstream",
                   params={"token": otok, "text": "hi?"})
    assert r.status_code == 200
    assert seen["effort"] == "minimal"
    assert '"tok": "hello"' in r.text
    assert '"done": {"answer": "hello"' in r.text
    msgs = client.get(f"/rooms/{rid}/messages",
                      params={"token": otok}).json()
    assert [(m["author"], m["kind"]) for m in msgs] == [("O", "ask"),
                                                        ("agent", "answer")]
    u = client.get(f"/rooms/{rid}/usage", params={"token": otok}).json()
    assert u["by_model"][S.SPARK_MODEL]["tin"] == 3
    assert client.get(f"/rooms/{rid}/askstream",
                      params={"token": otok, "text": "   "}).status_code == 400


def test_effort_rides_payloads(monkeypatch):
    seen = {}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}],
                    "usage": {}}

    def fake_post(*a, **k):
        seen["payload"] = k["json"]
        return Resp()

    monkeypatch.setattr(meta.httpx, "post", fake_post)
    meta.chat("k", "http://x", "m", [], effort="low")
    assert seen["payload"]["reasoning_effort"] == "low"
    meta.chat("k", "http://x", "m", [])
    assert "reasoning_effort" not in seen["payload"]
    monkeypatch.setattr(S, "JUDGE_EFFORT", "medium")
    meta.spark_reply("k", "http://x", "m", [], "hi")
    assert seen["payload"]["reasoning_effort"] == "medium"
    meta.spark_reply("k", "http://x", "m", [], "hi", effort="low")
    assert seen["payload"]["reasoning_effort"] == "low"
    meta.spark_reply("k", "http://x", "m", [], "hi", effort="")
    assert "reasoning_effort" not in seen["payload"]

    class Resp2:
        headers = {"content-type": "application/json"}

        def raise_for_status(self):
            pass

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "A"}}],
                               "usage": {}})

    class Ctx:
        def __enter__(self):
            return Resp2()

        def __exit__(self, *a):
            return False

    def fake_stream(*a, **k):
        seen["payload"] = k["json"]
        return Ctx()

    monkeypatch.setattr(meta.httpx, "stream", fake_stream)
    list(meta.chat_stream("k", "http://x", "m", [], effort="low"))
    assert seen["payload"]["reasoning_effort"] == "low"


def test_second_question_sees_first_answer(client, monkeypatch):
    seen = []

    def fake_stream(api_key, base, model, messages, timeout=120.0, effort=""):
        seen.append([m["content"] for m in messages])
        yield ("tok", "FINAL done")
        yield ("usage", 1, 1)

    monkeypatch.setattr(web.meta, "chat_stream", fake_stream)
    monkeypatch.setattr(web.dissent, "judge_room",
                        lambda con, rid, model: (None, None))
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    client.get(f"/rooms/{rid}/askstream",
               params={"token": otok, "text": "first question"})
    client.get(f"/rooms/{rid}/askstream",
               params={"token": otok, "text": "second question"})
    assert any("first question" in c for c in seen[1])
    assert any("done" in c for c in seen[1])
    assert "already covers" in agent.LOOP_SYS


def test_simultaneous_asks_serialize(client, monkeypatch):
    log = []
    release = threading.Event()
    entered1 = threading.Event()

    def fake_stream(api_key, base, model, messages, timeout=120.0, effort=""):
        q = messages[-1]["content"]
        log.append(("enter", q))
        if q == "Q1":
            entered1.set()
            assert release.wait(timeout=10)
        log.append(("exit", q))
        yield ("tok", "FINAL ok")
        yield ("usage", 1, 1)

    monkeypatch.setattr(web.meta, "chat_stream", fake_stream)
    monkeypatch.setattr(web.dissent, "judge_room",
                        lambda con, rid, model: (None, None))
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    codes = {}

    def ask(tag):
        r = client.get(f"/rooms/{rid}/askstream",
                       params={"token": otok, "text": tag})
        codes[tag] = r.status_code

    t1 = threading.Thread(target=ask, args=("Q1",), daemon=True)
    t2 = threading.Thread(target=ask, args=("Q2",), daemon=True)
    try:
        t1.start()
        assert entered1.wait(timeout=5)
        t2.start()
        time.sleep(0.3)
        assert ("enter", "Q2") not in log  # waits its turn
    finally:
        release.set()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert codes == {"Q1": 200, "Q2": 200}
    assert log.index(("exit", "Q1")) < log.index(("enter", "Q2"))


def test_askstream_midstream_error_note(client, monkeypatch):
    def boom(*a, **k):
        raise ValueError("down")
        yield ("tok", "never")

    monkeypatch.setattr(web.meta, "chat_stream", boom)
    monkeypatch.setattr(web.dissent, "maybe_fire",
                        lambda con, rid, model: None)
    j = client.post("/rooms", params={"mission": "M",
                                      "name": "O"}).json()
    rid, otok = j["room_id"], j["token"]
    r = client.get(f"/rooms/{rid}/askstream",
                   params={"token": otok, "text": "hi?"})
    assert r.status_code == 200
    assert "Model unavailable right now." in r.text
    msgs = client.get(f"/rooms/{rid}/messages",
                      params={"token": otok}).json()
    assert [m["kind"] for m in msgs] == ["ask"]  # question kept, no answer
