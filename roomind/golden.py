"""Golden transcripts: the exam paper. Ten cases, mine; the user's ten
join as USER-01..10. must_fire follows the team-lead bar, not the old
keyword watcher, so today's score starts red on purpose and climbs as
the watcher is rewritten. mission/memory/ledger ride along for the
evidence-first watcher; the v1 scorer grades message patterns only."""

GOLDEN = [
    {
        "id": "F1", "title": "rush past a review rule", "must_fire": True,
        "why": "Claim fights a memory fact, two fast agreers, ship verb.",
        "mission": "Ship Friday safely",
        "memory": {"deploy rule": "all deploys need Ravi's review"},
        "messages": [
            {"author": "Kim", "body": "We ship Friday with no review step",
             "ago": 150},
            {"author": "Sam", "body": "sounds good, let's do Friday",
             "ago": 100},
            {"author": "Ana", "body": "+1", "ago": 60},
        ],
    },
    {
        "id": "F2", "title": "self-contradiction ships", "must_fire": True,
        "why": "Kim's Sunday ship fights her own Monday freeze line.",
        "mission": "Respect the freeze",
        "memory": {"freeze": "freeze starts Monday, Kim posted it"},
        "messages": [
            {"author": "Kim",
             "body": "Freeze starts Monday, so we ship Sunday night",
             "ago": 150},
            {"author": "Sam", "body": "do it", "ago": 100},
        ],
    },
    {
        "id": "F3", "title": "verdict without thought", "must_fire": True,
        "why": "Big call, two nods, zero visible thought.",
        "mission": "Keep the database safe",
        "memory": {},
        "messages": [
            {"author": "Kim", "body": "Migrate the database tonight",
             "ago": 50},
            {"author": "Sam", "body": "yes", "ago": 40},
            {"author": "Ana", "body": "yep", "ago": 30},
        ],
    },
    {
        "id": "F4", "title": "fact memory denies", "must_fire": True,
        "why": "Compatible claim vs memory's broken-auth fact, tests cut.",
        "mission": "Safe API upgrade",
        "memory": {"v2 auth": "API v2 breaks auth headers"},
        "messages": [
            {"author": "Kim", "body": "API v2 is fully compatible",
             "ago": 150},
            {"author": "Sam", "body": "sounds good, skip the compat tests",
             "ago": 100},
            {"author": "Ana", "body": "+1", "ago": 60},
        ],
    },
    {
        "id": "F5", "title": "drift from mission", "must_fire": True,
        "why": "Five lines on logos, mission is checkout errors.",
        "mission": "Cut checkout errors",
        "memory": {},
        "messages": [
            {"author": "Kim", "body": "New logo looks nice", "ago": 200},
            {"author": "Sam", "body": "love the blue tone", "ago": 170},
            {"author": "Ana", "body": "ship the logo today", "ago": 140},
            {"author": "Kim", "body": "homepage banner next", "ago": 110},
            {"author": "Sam", "body": "nice, fonts after", "ago": 80},
        ],
    },
    {
        "id": "S1", "title": "joke, not a call", "must_fire": False,
        "why": "One loud line plus a laugh. No second voice.",
        "mission": "Ship Friday safely",
        "memory": {},
        "messages": [
            {"author": "Kim", "body": "ship it and nap forever", "ago": 100},
            {"author": "Sam", "body": "lol", "ago": 60},
        ],
    },
    {
        "id": "S2", "title": "experts agree with reasons", "must_fire": False,
        "why": "Fast nods on reviewed, tested work. Silence is correct.",
        "mission": "Ship Friday safely",
        "memory": {"review": "Ravi reviewed the plan Tuesday"},
        "messages": [
            {"author": "Kim",
             "body": "Ravi reviewed the plan Tuesday, tests are green",
             "ago": 150},
            {"author": "Sam", "body": "agree, the numbers look solid",
             "ago": 100},
            {"author": "Ana", "body": "yes, go", "ago": 60},
        ],
    },
    {
        "id": "S3", "title": "exploration breathes", "must_fire": False,
        "why": "What-ifs and maybes are thinking, not claims.",
        "mission": "Faster catalog",
        "memory": {},
        "messages": [
            {"author": "Kim", "body": "what if we cache the whole catalog?",
             "ago": 100},
            {"author": "Sam", "body": "maybe, but what about memory?",
             "ago": 60},
        ],
    },
    {
        "id": "S4", "title": "single voice plans", "must_fire": False,
        "why": "One person thinking aloud, nobody agrees to anything.",
        "mission": "Clean auth module",
        "memory": {},
        "messages": [
            {"author": "Kim", "body": "I will rewrite the auth module tonight",
             "ago": 100},
            {"author": "Sam", "body": "noted", "ago": 60},
        ],
    },
    {
        "id": "S5", "title": "objection vetoes", "must_fire": False,
        "why": "Two nods, then a real question. The room checks itself.",
        "mission": "Safe deploy",
        "memory": {},
        "messages": [
            {"author": "Kim", "body": "Deploy now, do it", "ago": 150},
            {"author": "Sam", "body": "yes", "ago": 100},
            {"author": "Ana", "body": "wait, what about the queue depth?",
             "ago": 60},
        ],
    },
]
