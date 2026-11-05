# Roomind — shared AI rooms where teams and agents work live 🏆

> 🎥 Demo video: link coming after recording (Nov 4)

*Start solo like any AI chat. Hit Share, and the same chat becomes a live room: teammates and agents, one memory, a referee that speaks only with evidence, and a receipt for every decision — all priced on screen.*

Built for the Meta Global AI Developer Hackathon (Cerebral Valley), Indie track — **Build for Your World** (Oct 26 – Nov 4, 2026).

## The Problem

Shared AI chats are read-only: you can send someone your Claude or ChatGPT thread, but they can't continue it with you. Teams paste screenshots, lose context, and re-ask the same questions — while group chats agree fast on thin ideas with nobody checking.

## Our Solution: Roomind

Open a solo chat. The moment you need people, Share mints invites and the *same* chat becomes a room: every member chats and asks, the agent answers everyone, one memory serves the team, a dissent referee cards thin agreements, stamped decisions land in a ledger, side rooms split off and report back — and a meter prices every model call.

## Features

**Rooms & chat**
- Solo-first: start alone with the agent, Share when you need people.
- Single + team invite links with live joined/left counts and +5 seat top-up.
- Unique nicknames per seat; per-member model choice (your pick, your meter).
- Live chat plus ask/answer slots — each answer lands under its own question.
- Streaming answers with Sources and checkable reasons (Tavily search, full-page reads, Open-Meteo weather).

**Memory**
- Remember/recall via chat; forget with one × per fact; one-click briefs.

**Referee (dissent)**
- Evidence-only cards on rushed or rule-breaking agreement, with quoted receipts.
- Manual "Challenge us", mute with a room-wide badge, expert hats per card.

**Decisions & work**
- Editable proposal cards; stamped decision ledger (overlaps replace, never pile).
- Tasks (assignee + due + Done), versioned docs (draft → propose → approve), live polls, daily reminders with popups (ledger deadlines mirror automatically).

**Side rooms**
- Split off a picked subgroup (one level); member-only roster; one-click share-back lands in main chat and as one ledger row.

**Teammates & red-team**
- @Researcher/@Planner/@Critic answer when mentioned; add/rename/remove your own.
- Away tasks run in the background and land in chat plus under the done task.
- Red-team attacks with ranked flaws, severity, Holds line, and cooldown.

**Running & publishing**
- Owner/operator/member roles, kick, room lock, step out, leave, ownership transfer, close forever.
- Full JSON export (sides included or counted hidden), revokable read-only showcase link.

**Measured**
- Sidebar meter: per-model spend plus room cap; header shows live approval from thumbs.

## Tech Stack

- **Backend:** Python (FastAPI), SQLite, WebSockets.
- **Frontend:** fast single-file web UI, no build step.
- **Models:** Muse Spark via Meta Model API (1.3 default, 1.2/1.1 per member).
- **Data APIs:** Tavily web search, Open-Meteo weather (keyless).

## Why Meta's models matter here

Every answer, memory decision, brief, dissent verdict, red-team attack, and teammate reply is a Muse Spark call — long-context reasoning over live threads plus strict JSON verdicts the referee pipeline parses. The product *is* the model, applied to group reasoning.

## Getting Started

1. **Clone:**
   ```bash
   git clone https://github.com/Krishnap1116/roomind.git
   cd roomind
   ```
2. **Install:**
   ```bash
   python -m venv .venv && . .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Keys:** copy `.env.example` to `.env`, paste `MODEL_API_KEY` (dev.meta.ai) and `SEARCH_API_KEY` (tavily.com, free tier).
4. **Run:** `.venv/bin/uvicorn roomind.web:app --port 8000` → open `http://127.0.0.1:8000`.
5. **Tests:** `python -m pytest -q` (235 passed).

## Room health and the eval harness

The header shows live approval from thumbs; spend lives in the sidebar meter. Behind the API sits the golden harness — ten frozen transcripts the judge grades itself against via Run exam (ten judge calls). It scores 7–9 across runs with zero false alarms; every miss is conservative silence. The bare-nod adoption case stays silent and is parked as a known limit.

## New-work proof

Built Oct 26 – Nov 4, 2026, during the hackathon, in this repo's commit history. No company code, names, accounts, or assets.

## Team

Solo Indie build — [Krishnap1116](https://github.com/Krishnap1116).

## Acknowledgements

Powered by **Meta Muse Spark**. Thanks to Meta and Cerebral Valley for the hackathon.

## License

MIT — see [LICENSE](LICENSE).
