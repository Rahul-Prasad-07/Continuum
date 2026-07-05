# Continuum — Status & Roadmap (aimed vs built, and the path to "dead simple")

## Aim
A "Conversation OS": save & resume AI **reasoning-state** (decisions, rejected alternatives,
hypotheses — not just facts), captured **in flight**, reconstructable **anywhere, on any AI,
with zero effort.**

## Built so far (the hard 70% — engine + plumbing, tested)
| Layer | Status |
|---|---|
| Engine: checkpoint/resume, reasoning graph, workspace state, verbatim **hybrid**, **salience**-bounded | ✅ |
| Backends: local SQLite + Cognee adapter (ports-and-adapters) | ✅ |
| LLM extraction: OpenAI/Anthropic + heuristic fallback | ✅ (heuristic = rough) |
| Surfaces: CLI (8 cmds), HTTP API (+bearer auth), MCP (stdio + remote streamable-http/sse, 6 tools) | ✅ |
| Fixes: DNS-rebinding host allow, friendly landing page | ✅ |
| Ops: Docker, docker-compose, GitHub CI, 10 tests, docs | ✅ |

## The gap — why it's not yet "very simple"
Today = power-user simple (venv → install → server → tunnel → connector → export/paste).
Missing = the **experience layer**:
| Friction now | "Very simple" needs |
|---|---|
| self-host: venv, server, tunnel | **zero setup** |
| manual export / copy-paste | **automatic capture** |
| heuristic without a key | **clean extraction always** |
| CLI/API only | **a button / UI in the chat** |
| everyone self-hosts | **a hosted option** |

## Path to the ideal product (prioritized)
1. **Browser extension** ← next. Delivers advanced+simple+anywhere at once:
   - install once → "💾 Save / ↻ Resume" buttons in claude.ai/chatgpt/grok/gemini
   - Save = auto-read whole visible chat → checkpoint (no copy-paste)
   - Resume = auto-paste resume package into the input box (no CLI)
   - talks to the HTTP API we already built (local or hosted)
2. **Hosted cloud backend** (`continuum.app`) — no self-host; accounts, encryption, multi-tenant.
3. **Clean extraction by default** — use the user's connected AI / bundled key; heuristic = last resort.
4. **Auto-checkpoint triggers** — capture before context fills (invisible), not just on click.
5. **Tiny dashboard** — view/search/manage projects visually.
6. **One-line installer** for the local/power path.

## Bottom line
The brain is built (the hard, defensible part). What's left is the **face**. Next build =
**browser extension + hosted backend** → turns the working engine into a one-click product for
any user, on any AI, anywhere.

### Ties to: README, GETTING-STARTED, USE-CASES, ADD-ANYWHERE; study/cognee-hackathon/* (research).
