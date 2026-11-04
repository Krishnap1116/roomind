# Roomind — shared AI rooms where teams and agents work live 🏆

> 🎥 Demo video: link coming after recording (Nov 4)

*Start solo like any AI chat. Hit Share, and the same chat becomes a live room: teammates and agents, one memory, a referee that speaks only with evidence, and a receipt for every decision — all priced on screen.*

Built for the Meta Global AI Developer Hackathon (Cerebral Valley), Indie track — **Build for Your World** (Oct 26 – Nov 4, 2026).

## The Problem

Shared AI chats are read-only: you can send someone your Claude or ChatGPT thread, but they can't continue it with you. Teams paste screenshots, lose context, and re-ask the same questions — while group chats agree fast on thin ideas with nobody checking.

## Our Solution: Roomind

Open a solo chat. The moment you need people, Share mints invites and the *same* chat becomes a room: every member chats and asks, the agent answers everyone, one memory serves the team, a dissent referee cards thin agreements, stamped decisions land in a ledger, side rooms split off and report back — and a meter prices every model call.

## Core Features

- Solo-first agent chat with live web search, full-page reads, and weather.
- One-click Share: invites, nicknames, operators, per-member model choice.
- Room memory: remember/recall/forget, briefs, catch-up.
- Dissent referee: evidence-only cards on rushed agreement, manual challenge, mute.
- Decision ledger with editable stamps, reminders, tasks, artifacts, polls.
- Side rooms with member-only rosters and share-back reports.
- Red-team attacks, teammate agents (@Researcher/@Planner/@Critic), away tasks.
- Measured everything: per-model spend, approval, cost per decision, trust.

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
   git clone https://github.com/Krishnapriyankaponnaganti/roomind.git
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

The header shows live room health only: answer approval from thumbs, cost per decision, and a trust word. The golden harness — ten frozen transcripts the judge grades itself against — lives one click down in Room tab → Details, with a manual Run exam (ten judge calls). It scores 7–9 across runs with zero false alarms; every miss is conservative silence. The bare-nod adoption case stays silent and is parked as a known limit.

## New-work proof

Built Oct 26 – Nov 4, 2026, during the hackathon, in this repo's commit history. No company code, names, accounts, or assets.

## Team

Solo Indie build — [Krishnapriyankaponnaganti](https://github.com/Krishnapriyankaponnaganti).

## Acknowledgements

Powered by **Meta Muse Spark**. Thanks to Meta and Cerebral Valley for the hackathon.

## License

MIT — see [LICENSE](LICENSE).
