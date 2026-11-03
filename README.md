# Roomind

Shared AI rooms where teams plus agents work live. Room remembers as one
team, briefs late joiners in seconds, talks the room out of fast mistakes
with receipts, and stamps every call in a ledger. All measured on screen.

Indie-track build for the Meta Global AI Developer Hackathon, built solo
Oct 28 – Nov 4, 2026. Theme: Build for Your World.

## Use it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your Meta key, never commit it
uvicorn roomind.web:app --port 8000
```

Open `http://localhost:8000`. Create a room, share the invite link, chat.
Ask the agent anything. Watch reasons, briefs, dissent cards, and the
dollar meter. Run tests: `python -m pytest -q`.

## How a room works

Messages append live for everyone. Agent answers carry checkable reasons
and remember lasting facts. Fast thin agreement triggers one dissent card
with receipts from the room's own words. Humans decide; the ledger stamps
what, who, why, deadline. Late joiners read a catch-up brief, never scroll
forever. Owner mute makes the agent ask-only. Pause freezes all agent
moves. Delete wipes the room completely.

## Production path

SQLite serves the demo. Production moves to hosted Postgres behind the
store module, the single swap boundary. Tables map one to one.

## Roadmap

Model switching UI, images and voice notes, side rooms with share-back,
cross-room brief quotes, artifacts with approvals, deadline enforcement,
budget guard, agent teammate roles, away tasks, fork and merge, votes,
threaded replies, red-team hour, room templates, export pack, showcase
links, multi-language rooms, task board, scheduled briefings, sandboxed
code-run, live audio, PDF and video files, per-person keys, integrations,
installable app, audit widening, end-to-end encryption, single sign-on.
