"""Eval strip engine: grades the watcher against golden transcripts.

v1 scores the pure message-pattern watcher, free and instant.
run_suite_judge grades the model judge instead: same golden set,
accuracy plus speed. Exam calls get logged like any other model
spend, button-triggered only."""
import json
import time

from . import dissent


JUDGE_PROMPT = (
    "You judge one room moment. Reply ONLY JSON "
    '{"fire": true/false, "why": "..."}. Fire true only with concrete '
    "evidence: a line fighting the mission, a ledger fact, a memory fact, "
    "or the speaker's own earlier words. Fast agreement alone is silence.")


def _messages(case: dict, now: float) -> list:
    return [{"author": m["author"], "body": m["body"], "kind": "chat",
             "created_at": now - m.get("ago", 60)}
            for m in case["messages"]]


def score_case(case: dict, now: float = 0.0) -> dict:
    now = now or time.time()
    fired = dissent.watch(_messages(case, now)) is not None
    return {"id": case["id"], "title": case["title"],
            "expected": case["must_fire"], "fired": fired,
            "hit": fired == case["must_fire"], "why": case["why"]}


def run_suite(cases: list, now: float = 0.0) -> dict:
    now = now or time.time()
    details = [score_case(c, now) for c in cases]
    fires = [d for d in details if d["fired"]]
    musts = [d for d in details if d["expected"]]
    true = [d for d in fires if d["expected"]]
    return {
        "total": len(details),
        "score": sum(1 for d in details if d["hit"]),
        "precision": len(true) / len(fires) if fires else 1.0,
        "recall": len(true) / len(musts) if musts else 1.0,
        "false_alarms": [d["id"] for d in fires if not d["expected"]],
        "misses": [d["id"] for d in details
                   if d["expected"] and not d["fired"]],
        "details": details,
    }


def judge_case(call_fn, case: dict) -> dict:
    """One golden case through one model judge. call_fn(history, prompt)
    returns {answer, tin, tout} like meta.spark_reply."""
    hist = [{"author": m["author"], "body": m["body"]}
            for m in case["messages"]]
    ctx = (f" Mission: {case.get('mission', '')}."
           f" Memory: {case.get('memory', {})}.")
    t0 = time.time()
    out = call_fn(hist, JUDGE_PROMPT + ctx)
    try:
        fired = bool(json.loads(out["answer"]).get("fire", False))
    except (ValueError, TypeError, AttributeError):
        fired = False
    return {"fired": fired, "secs": time.time() - t0,
            "tin": out.get("tin", 0), "tout": out.get("tout", 0)}


def score_case_judge(call_fn, case: dict) -> dict:
    """One golden case through the room's own judge: same orders, same
    evidence rules as production. Returns the case verdict plus spend."""
    thread = [{"author": m["author"], "body": m["body"]}
              for m in case["messages"]]
    t0 = time.time()
    r = dissent.judge_line(call_fn, thread, case.get("mission", ""),
                           case.get("memory", {}), [])
    fired = r["fire"]
    return {"id": case["id"], "title": case["title"],
            "expected": case["must_fire"], "fired": fired,
            "hit": fired == case["must_fire"], "why": case["why"],
            "secs": time.time() - t0, "tin": r["tin"], "tout": r["tout"]}


def run_suite_judge(call_fn, cases: list) -> dict:
    details = [score_case_judge(call_fn, c) for c in cases]
    fires = [d for d in details if d["fired"]]
    musts = [d for d in details if d["expected"]]
    true = [d for d in fires if d["expected"]]
    return {
        "total": len(details),
        "score": sum(1 for d in details if d["hit"]),
        "precision": len(true) / len(fires) if fires else 1.0,
        "recall": len(true) / len(musts) if musts else 1.0,
        "false_alarms": [d["id"] for d in fires if not d["expected"]],
        "misses": [d["id"] for d in details
                   if d["expected"] and not d["fired"]],
        "secs": sum(d["secs"] for d in details),
        "tin": sum(d["tin"] for d in details),
        "tout": sum(d["tout"] for d in details),
        "details": details,
    }
