# Continuum Features, what each one does, and where & when to use it

Every Continuum feature is the same on **Claude web (MCP)**, other web AIs (Grok, ChatGPT),
CLI/desktop agents (Claude Code, Codex, Cursor), and the HTTP API. The *mechanism* differs
(you either **ask the AI** to run a tool, or **type a command**), but the feature is identical.

- On **Claude web / Grok / ChatGPT** with the connector on -> **just ask in plain English**; the AI
  calls the matching `continuum_*` tool.
- On a **CLI** -> run the command.

This page is the reference: for each feature, **what it does**, **when to use it**, the
**phrase to say in a web AI**, and the **CLI** equivalent.

> New here? Read [GETTING-STARTED.md](GETTING-STARTED.md) first, and
> [INTEGRATIONS.md](INTEGRATIONS.md) to connect it to your AI.

---

## Quick "I want to..." map

| I want to... | Feature | Say in Claude web | CLI |
|---|---|---|---|
| Save this chat so I don't lose the thinking | **checkpoint / save** | "save this whole chat to continuum project X" | `continuum checkpoint chat.txt -p X` |
| Pull a chat from Grok/Claude/Codex (no paste) | **capture** | "capture my latest grok session into project X" | `continuum capture -p X --from grok --latest` |
| Add reference docs/notes as knowledge | **ingest** | "ingest these docs into continuum project X" | `continuum ingest notes.md -p X` |
| See which storage layers are active | **mode** | "show continuum mode" | `continuum mode` |
| Continue in a new chat / next day | **resume** | "resume continuum project X" | `continuum resume -p X` |
| Know if I'm about to lose context | **context** | "continuum, how full is my context?" | `continuum context -p X -t chat.txt` |
| Move to another AI / back it up | **export** | "export continuum project X as markdown" | `continuum export -p X -f md` |
| Restore a saved bundle | **import** | (usually CLI) | `continuum import -p X bundle.json` |
| Clean up messy memory | **improve** | "improve continuum project X" | `continuum improve -p X` |
| Shrink memory so resumes stay small | **prune** | "prune continuum project X" | `continuum prune -p X` |
| Turn this project into reusable lessons | **distill** | "distill lessons from continuum project X" | `continuum distill -p X` |
| See lessons I can reuse elsewhere | **lessons** | "show my continuum lessons" | `continuum lessons` |
| See how the plan evolved over time | **timeline** | "show continuum timeline for project X" | `continuum timeline -p X` |
| Find where I decided something | **search** | "search continuum project X for redis" | `continuum search -p X "redis"` |
| See all my projects | **list** | "list my continuum projects" | `continuum list` |
| Check what's saved for a project | **status** | "continuum status of project X" | `continuum status -p X` |
| Permanently delete a project | **forget** | "forget continuum project X" | `continuum forget -p X` |

---

## The core loop (use these 90% of the time)

### 1) `checkpoint` / `save`, capture the thinking
- **What it does:** stores the conversation **verbatim** (the source of truth) *and* extracts a
  **reasoning graph + workspace state**: goal, decisions and *why*, rejected alternatives and *why*,
  constraints, open questions, next steps, each timestamped. Returns a checkpoint id + decision count.
- **When/where to use:** the moment a chat has real reasoning worth keeping, before you hit the
  context limit, at the end of a work session, or right after a key decision. Do it **often**;
  checkpoints are cheap and merge together.
- **Claude web:** *"Use continuum to save this entire conversation to project `billing`."*
  (`continuum_save` / `continuum_checkpoint`)
- **CLI:** `continuum checkpoint chat.txt -p billing`
- **Note: Fidelity:** via MCP the AI passes *what's in its context*, for a very long chat that may
  not be 100% verbatim. For guaranteed full capture, copy the whole chat to a file and use the CLI.

### 2) `resume`, reconstruct anywhere
- **What it does:** builds a compact, **paste-ready resume package**: the working state, the
  **rejected alternatives** (so the AI won't re-propose them), and the exact verbatim that matters, 
  **token-budget-bounded** so it never blows up the next context window.
- **When/where to use:** whenever you start fresh, a new chat, the next day, or a different AI.
  Give it an *intent* ("resuming toward X") so retrieval focuses on what you're about to do.
- **Claude web:** *"Resume continuum project `billing` toward the webhook retry."* (`continuum_resume`)
- **CLI:** `continuum resume -p billing -i "webhook retry"`

### 3) `context`, know when to save (the safety meter)
- **What it does:** gauges the **live conversation**: `window used %` (compression risk),
  `drift %` (thinking not yet checkpointed), and a **0-100 strength score** with a
  `healthy / checkpoint soon / checkpoint now` verdict.
- **When/where to use:** mid-conversation, when a chat feels long, to decide *whether to checkpoint
  now*. Great as a habit before big context-heavy steps.
- **Claude web:** *"Continuum, how full is my context, should I checkpoint?"* (`continuum_context`;
  the AI passes the current transcript as the thing to measure)
- **CLI:** `pbpaste | continuum context -p billing -m claude`

### `ingest`, add reference docs as knowledge (not a conversation)
- **What it does:** stores documents/notes/specs as **knowledge**, verbatim, and on the Cognee
  backends run through the full **ingest -> knowledge-graph** pipeline. Unlike `checkpoint`, it does
  **not** extract reasoning-state (docs aren't decisions).
- **When/where to use:** to give a project background material, an API spec, a design doc, past
  meeting notes, so resume/search can draw on it.
- **Claude web:** *"Ingest this doc into continuum project `billing`."* (`continuum_ingest`)
- **CLI:** `continuum ingest spec.md -p billing`

---

## Portability (move & back up)

### 4) `export`, take the whole state elsewhere
- **What it does:** two shapes. `md` = a human-readable document of the **entire** saved
  state (paste into any AI to continue). `json` = a **lossless bundle** (verbatim + workspaces +
  reasoning graph) for backup or importing into another install/user.
- **When/where to use:** switching platforms (Claude -> ChatGPT/Grok/Gemini) -> use `md`. Backing up
  or moving machines -> use `json`.
- **Claude web:** *"Export continuum project `billing` as markdown so I can paste it elsewhere."*
  (`continuum_export`)
- **CLI:** `continuum export -p billing -f md | pbcopy`, `continuum export -p billing -f json -o b.json`

### 5) `import`, restore a bundle
- **What it does:** loads a `json` bundle into a project (can be a **different user or machine**);
  reasoning + verbatim + workspaces are restored and merged.
- **When/where to use:** new laptop, sharing a project with a teammate, or recovering a backup.
  Usually a CLI/API action.
- **CLI:** `continuum import -p billing-copy b.json`,  **HTTP:** `POST /import/{project}`

---

## Keep memory clean & reusable (run periodically)

### 6) `improve`, self-clean the reasoning graph
- **What it does:** merges near-duplicate reasoning nodes, drops dangling links, and marks
  **superseded** decisions resolved. Heuristic, no LLM needed.
- **When/where to use:** after many checkpoints on the same project, when resumes start feeling
  repetitive or contradictory.
- **Claude web:** *"Improve continuum project `billing`."*, **CLI:** `continuum improve -p billing`

### 7) `prune`, active forgetting (keep resumes small)
- **What it does:** trims low-salience reasoning to the most important nodes (always keeps **Goals**
  and **Open Questions**). **Verbatim source is never deleted**, only the reasoning *index* shrinks.
- **When/where to use:** long-running projects whose resume packages are getting large/noisy.
- **Claude web:** *"Prune continuum project `billing`, keep the top 60."*, **CLI:** `continuum prune -p billing --keep 60`

### 8) `distill`, harvest reusable lessons
- **What it does:** extracts durable, standalone **lessons** from a project (insights + accepted
  decisions' rationale) and stores them in your **cross-project lessons** memory.
- **When/where to use:** at the end of a project/milestone, to turn work into knowledge future
  projects can reuse.
- **Claude web:** *"Distill lessons from continuum project `billing`."*, **CLI:** `continuum distill -p billing`

### 9) `lessons`, reuse what you've learned
- **What it does:** shows your accumulated cross-project lessons (from `distill`).
- **When/where to use:** starting a new project, pull in relevant lessons so you don't repeat past
  mistakes.
- **Claude web:** *"Show my continuum lessons."*, **CLI:** `continuum lessons`

---

## Inspect & manage

### 10) `timeline`, how the thinking evolved
- **What it does:** one row per checkpoint, oldest->newest, when each was saved, decisions and open
  questions at that point. The temporal story of the project.
- **When/where to use:** to review how/when the plan changed, or to explain the project's history.
- **Claude web:** *"Show the continuum timeline for project `billing`."*, **CLI:** `continuum timeline -p billing`

### 11) `search`, find a past passage
- **What it does:** keyword/semantic search over a project's **verbatim** memory; returns the exact
  passages.
- **When/where to use:** "where did we decide X?" / "what did I say about Redis?"
- **Claude web:** *"Search continuum project `billing` for Chargebee."*, **CLI:** `continuum search -p billing "Chargebee"`

### 12) `list`, see your projects
- **What it does:** lists all projects with saved state **for the current user** (scoping hidden).
- **When/where to use:** to recall project names before a resume, or to audit what you've saved.
- **Claude web:** *"List my continuum projects."*, **CLI:** `continuum list`

### 13) `status`, what's saved for a project
- **What it does:** reports user, whether state exists, latest checkpoint id, decision count,
  reasoning nodes/edges, number of checkpoints, extraction mode (llm/heuristic), and backend.
- **When/where to use:** a quick health check before resuming, or to confirm a checkpoint landed.
- **Claude web:** *"What's the continuum status of project `billing`?"*, **CLI:** `continuum status -p billing`

### `mode`, which storage layers are active
- **What it does:** reports the live backend and its capabilities, `knowledge_graph`,
  `semantic_retrieval`, `managed_llm`, and `reasoning_extraction` (llm/heuristic).
- **When/where to use:** to confirm you're in "complete mode" (Cognee KG + embeddings) vs local
  keyword, i.e. to know exactly what a checkpoint stored.
- **Claude web:** *"Show continuum mode."* (`continuum_mode`), **CLI:** `continuum mode`, **HTTP:** `GET /mode`

### 14) `forget`, delete permanently
- **What it does:** irreversibly deletes everything for a project (verbatim + workspaces + reasoning).
- **When/where to use:** when a project is done and you want it gone, or to remove sensitive data.
  **Irreversible**, export first if unsure.
- **Claude web:** *"Forget continuum project `billing`."* (confirm), **CLI:** `continuum forget -p billing`

---

## A realistic Claude-web session (features in order)

1. You've been designing billing in Claude web for a while.
   -> *"Continuum, how full is my context?"* -> **context** says `checkpoint soon`.
2. -> *"Save this whole conversation to continuum project `billing`."* -> **checkpoint**.
3. Claude hits its limit / you open a new chat tomorrow.
   -> *"Resume continuum project `billing` toward the webhook retry."* -> **resume** (knows you
     rejected Chargebee and won't re-suggest it).
4. You want to code it in Cursor instead.
   -> *"Export continuum project `billing` as markdown."* -> **export** -> paste into Cursor
     (or connect the same MCP there and just say "resume project billing").
5. Milestone done.
   -> *"Distill lessons from continuum project `billing`."* -> **distill**; next project -> **lessons**.
6. Housekeeping every so often: **improve** + **prune** to keep it lean; **timeline** to review;
   **forget** when it's truly finished.

---

## Read vs write (so you know what's safe to ask an agent)

| Read-only (safe to auto-run) | Writes / changes state |
|---|---|
| `resume`, `context`, `export`, `lessons`, `timeline`, `search`, `list`, `status` | `checkpoint`/`save`, `import`, `improve`, `prune`, `distill`, `forget` |

`forget` is the only destructive one, it asks to confirm in the CLI and should require an explicit
"yes, delete" when an agent proposes it.

## Same on every platform
The **phrases** above work in any MCP-connected web AI (Claude web, Grok, ChatGPT). The **CLI**
commands work in Claude Code, Codex, Cursor, or a terminal. The **HTTP API** exposes all of them
for your own apps (multi-tenant via `X-Continuum-User`). See [INTEGRATIONS.md](INTEGRATIONS.md).
