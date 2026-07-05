# Continuum on Claude web — real use cases, step by step

Two ways to drive Continuum:
- **MCP (in-chat)** — you connected the server; you just *ask Claude* to use it. Convenient.
- **CLI / copy-paste** — you run commands and paste text. Most reliable, works on any platform.

Rule of thumb: **MCP for convenience, export+CLI for guaranteed full-fidelity capture.**

---

## 0. One-time setup (MCP)
1. Run the server + tunnel, get the `https://.../mcp` URL (full walkthrough: [INTEGRATIONS.md](INTEGRATIONS.md)).
2. Claude web → **Settings → Connectors → Add custom connector** → paste the `/mcp` URL → Connect.
3. Verify: *"List my continuum projects."* → Claude calls the tool.

---

## Use case 1 — Save the WHOLE chat conversation

### Option A — In-chat via MCP (quick, ongoing)
In the chat, say:
> *"Use continuum to checkpoint this entire conversation to project `myproject`. Include the full transcript."*

Claude calls `continuum_checkpoint`. ⚠️ Claude passes what's in its context — great for ongoing
capture, but for a very long chat it may not include 100% verbatim.

### Option B — Export + CLI (guaranteed full fidelity) ✅ recommended for "the whole chat"
1. Scroll to the **top** of the Claude conversation.
2. Select the entire conversation (drag from first message to last) and **copy**.
3. Save it to a file:
   ```bash
   pbpaste > chat.txt          # macOS  (or paste into a new chat.txt manually)
   ```
4. Checkpoint it:
   ```bash
   continuum checkpoint chat.txt -p myproject
   ```
This stores the exact, complete conversation as the source of truth.

**Tip:** do this whenever a chat gets long or before you hit the limit — checkpoint often.

---

## Use case 2 — New chat, continue where you left off

### Via MCP
Open a **new Claude chat** and say:
> *"Use continuum to resume project `myproject` toward the token refresh endpoint."*

Claude pulls the resume package and continues — with your decisions and what you rejected.

### Via copy-paste (always works)
```bash
continuum resume -p myproject -i "continue the refresh endpoint"
```
Copy the printed package → paste into the new chat → *"Continue from this state."*

---

## Use case 3 — Switch platforms (Claude → Grok / ChatGPT / Gemini)

**You do NOT copy the raw 200k-token transcript.** You move the compact **resume package**
(state, not transcript — that's the whole point).

1. (Once) checkpoint the Claude chat — Use case 1.
2. Generate the package:
   ```bash
   continuum resume -p myproject -i "continue where we left off"
   ```
3. **Copy it → paste into Grok** (or ChatGPT/Gemini) → *"Continue from this reasoning state."*

Grok now knows the goal, decisions, rejected options, constraints, and next steps — even though
it never saw the original chat. If Grok supports MCP connectors, add the same `/mcp` URL there and
just say *"resume project myproject."*

> Want more raw detail carried over? Raise the budget: `continuum resume -p myproject -b 16000`.
> (The new platform's own context window still caps how much it can hold — that's the original
> limit Continuum is managing for you.)

---

## Use case 4 — Coding handoff (Claude web → Cursor / Claude Code)
1. Checkpoint the design chat (Use case 1).
2. In Cursor/Claude Code (with the local MCP or CLI):
   ```bash
   continuum resume -p myproject -i "start implementing the API"
   ```
   Paste into the coding agent → it codes *with* your architectural decisions.

---

## Use case 5 — Find a past decision
> *"Search continuum project myproject for redis."*   (MCP)
```bash
continuum search -p myproject "redis"                  # CLI
```
Returns the exact passages where you discussed it.

---

## Use case 6 — Manage projects
| Do | MCP phrase | CLI |
|---|---|---|
| See all projects | "list my continuum projects" | `continuum list` |
| Check a project | "continuum status of myproject" | `continuum status -p myproject` |
| Delete a project | "forget continuum project myproject" | `continuum forget -p myproject` |

**Use separate projects per topic** (`auth`, `billing`, `research-x`) so resumes stay focused.

---

## Use case 7 — Share with a teammate
- Send them the resume package text (they paste into their AI), **or**
- Host the MCP server for the team (stable URL + `CONTINUUM_TOKEN`) so everyone shares memory.

---

## Use case 8 — Check if you're about to lose your reasoning (context health)
> *"Continuum, how full is my context and should I checkpoint?"*   (MCP → `continuum_context`)
```bash
pbpaste | continuum context -p myproject -m claude               # CLI, measures the live chat
```
You get a gauge: **window** used, **drift** (uncaptured thinking), a **strength** score, and a
`healthy` / `checkpoint soon` / `checkpoint now` verdict. Save before it turns red.

---

## Use case 9 — Export the whole state / move machines (export + import)
```bash
# Human-readable, paste into ANY new chat on any provider:
continuum export -p myproject -f md | pbcopy

# Lossless bundle — back it up or move it to another machine / user:
continuum export -p myproject -f json -o myproject.json
continuum import -p myproject myproject.json                      # restore anywhere
```
The Markdown export is the "start a fresh chat" path; the JSON bundle is the "migrate / back up"
path. Both are provider-neutral — no lock-in.

---

## Use case 10 — Reuse lessons across projects (improve · prune · distill · lessons)
```bash
continuum improve  -p myproject          # clean the reasoning graph (dedup, resolve superseded)
continuum prune    -p myproject --keep 60 # active forgetting so resumes stay small
continuum distill  -p myproject          # harvest durable lessons from this project
continuum lessons                        # reuse them across every future project
continuum timeline -p myproject          # see how the thinking evolved over time
```

---

## When to do what (habit)
- **Context check:** anytime a chat feels long — `continuum context` tells you if reasoning is at risk.
- **Checkpoint:** when the meter says `checkpoint soon/now`, before the context limit, or at end of session.
- **Resume:** when you open a new chat, switch providers, or come back the next day.
- **Export:** when moving to another platform or backing up; **import** to restore on a new machine.
- **Improve/prune/distill:** periodically, to keep memory clean and turn work into reusable lessons.
- **Search/list/timeline:** when you forget where or when something was decided.

## Reliability notes
- **Fullest capture = export + CLI** (Option B). MCP checkpoint depends on what Claude includes.
- **Set `OPENAI_API_KEY`** for clean reasoning extraction (else heuristic/rough).
- Keep the **tunnel + server running** for MCP; the copy-paste path needs neither.
