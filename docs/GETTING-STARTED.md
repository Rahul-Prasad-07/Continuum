# Getting Started with Continuum

Save & resume your AI *thinking* across sessions and providers. This walks you from install
to using it everywhere.

---

## Step 1, Install (2 minutes)
```bash
cd Continuum
python3 -m venv .venv            # create an isolated environment
source .venv/bin/activate        # (Windows: .venv\Scripts\activate)
pip install -e ".[all]"          # install continuum + all surfaces (API, MCP, LLM)
continuum --version              # verify: "continuum, version 0.1.0"
```
Runs with **zero API keys** out of the box (local SQLite + heuristic extraction).

## Step 2, Your first save & resume (the core loop)
```bash
# 1) Save a conversation's reasoning-state into a project called "auth"
continuum checkpoint examples/sample_conversation.txt -p auth
#    -> checkpoint saved  project=auth  id=cp-...  decisions=4

# 2) Later / in a new chat, reconstruct it as a resume package
continuum resume -p auth -i "build the token refresh endpoint"
#    -> prints a compact package: goal, decisions, REJECTED alternatives, verbatim, next steps
```
Copy that resume package, paste it into **any** fresh AI chat, and it continues your thinking, 
including *why* you rejected things.

**Checkpoint your own chats:** export/copy a conversation to a `.txt` file (or pipe it in):
```bash
pbpaste | continuum checkpoint - -p myproject       # macOS: checkpoint clipboard
continuum resume -p myproject -i "where I left off"
```

## Step 2.5, Know when to save (context-health meter)
Reasoning-state is *destroyed* when the window fills, so Continuum tells you when you're close.
Pass the current conversation and it scores how safe you are:
```bash
pbpaste | continuum context -p myproject -m claude       # measure the live chat
#  window  [██████████░░░░░░░░░░] 41%  (yellow)
#  drift   [████████████████████] 99% uncaptured
#  strength 20/100
#  -> checkpoint now, you are close to losing reasoning-state
```
- **window**, how full the model's context window is (compression risk).
- **drift**, how much fresh thinking hasn't been checkpointed yet.
- **strength**, 0-100 safety score, with a `healthy` / `checkpoint soon` / `checkpoint now` verdict.

In an MCP-connected AI you just ask *"Continuum, how full is my context?"* and it runs the same gauge.

## Step 2.6, Move to a new chat or another platform (export / import)
```bash
# Paste-anywhere Markdown of the WHOLE saved state -> drop into ChatGPT / Grok / Gemini
continuum export -p myproject -f md | pbcopy

# Lossless bundle for backup or moving to another machine/user
continuum export -p myproject -f json -o myproject.json
continuum import -p myproject-copy myproject.json      # restore into a new project
```

## Step 3, Make it smart (add an API key), optional but recommended
Without a key you get rough heuristic extraction. With one, the reasoning graph is clean:
```bash
export OPENAI_API_KEY=sk-...           # or ANTHROPIC_API_KEY=sk-ant-...
# (optional) export OPENAI_MODEL=gpt-4o-mini
continuum checkpoint examples/sample_conversation.txt -p auth
continuum status -p auth               # llm_mode: llm
```

## Step 4, Manage & refine your memory
```bash
continuum list                         # all your projects
continuum status -p auth               # what's saved for a project
continuum search -p auth "redis"       # find passages in a project
continuum timeline -p auth             # how the thinking evolved (one row per checkpoint)
continuum forget -p auth               # permanently delete a project (asks to confirm)
```
Keep the reasoning memory clean and reusable:
```bash
continuum improve -p auth              # merge duplicate reasoning, drop dead links, resolve superseded
continuum prune -p auth --keep 60      # active forgetting: trim low-salience nodes (verbatim is kept)
continuum distill -p auth              # harvest durable lessons into your cross-project memory
continuum lessons                      # show accumulated lessons reusable by any future project
```

## Step 4.5, Multi-user / teams (isolated memory)
Every user's memory is isolated. Scope any command with `--user` (or the `CONTINUUM_USER` env):
```bash
continuum --user alice checkpoint chat.txt -p billing
continuum --user bob   list            # bob never sees alice's projects
```
Over HTTP, send the `X-Continuum-User` header; each user gets a fully isolated engine.

---

## Step 5, Use it everywhere

### A) Copy-paste, works with ANY AI, zero setup
`continuum resume ...` prints plain text. Paste it into Claude web, Grok, ChatGPT, Gemini, 
anything. This always works.

### B) Claude Code / Codex / Cursor (local MCP)
Add to your MCP config (e.g. `claude_desktop_config.json`):
```json
{ "mcpServers": { "continuum": { "command": "continuum", "args": ["mcp"] } } }
```
Then in chat: *"checkpoint this to project auth with continuum"* / *"resume project auth"*.

### C) Claude web / Grok / ChatGPT (remote MCP by URL)
Host the server, then add it as a connector:
```bash
export CONTINUUM_TOKEN="a-secret"                      # protect it
continuum mcp -t streamable-http --host 0.0.0.0 --port 8771
# -> add https://your-host/mcp  (Authorization: Bearer a-secret)  in the app's Connectors/MCP settings
```
**Full step-by-step for every platform**, Claude web deep-dive, Grok, ChatGPT, Claude Code,
Codex, Cursor, HTTPS tunnels, and troubleshooting: **[INTEGRATIONS.md](INTEGRATIONS.md)**.

### D) HTTP API (browser extension / web app / your own scripts)
```bash
continuum serve                                        # http://127.0.0.1:8770  (/docs for OpenAPI)
curl -X POST localhost:8770/checkpoint -H 'content-type: application/json' \
     -d '{"project":"auth","text":"use JWT because low ops. reject Redis: lock race."}'
curl -X POST localhost:8770/resume -H 'content-type: application/json' \
     -d '{"project":"auth","intent":"refresh endpoint"}'
```

### E) Docker (hosted)
```bash
docker compose up            # API on :8770
```

---

## A real day with Continuum
1. **Morning:** design in Claude web. When it's getting long, copy the chat ->
   `continuum checkpoint chat.txt -p project-x` (or the AI calls `continuum_checkpoint` via MCP).
2. **Afternoon:** open Cursor to code -> `continuum resume -p project-x -i "start the API"` ->
   paste -> Cursor knows your decisions and what you rejected.
3. **Claude hits its limit:** `continuum resume -p project-x` -> paste into Grok/ChatGPT -> continue.
4. **Next week:** `continuum resume -p project-x` -> pick up exactly where you left off.

## Config reference (all optional, see `.env.example`)
| Env | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | none | clean LLM extraction |
| `CONTINUUM_BACKEND` | `local` | `local` (SQLite) or `cognee` (production) |
| `CONTINUUM_HOME` | `~/.continuum` | where memory is stored |
| `CONTINUUM_RESUME_BUDGET` | `8000` | max tokens in a resume package |
| `CONTINUUM_USER` | `default` | tenant id, isolates memory per user (also `--user`) |
| `CONTINUUM_COGNEE_REASONING` | `1` | on the Cognee backend, also extract the reasoning graph via `cognify(graph_model=...)` |
| `CONTINUUM_TOKEN` | none | require bearer auth on API + remote MCP |

## Every verb at a glance
`checkpoint`, `resume`, `context`, `export`, `import`, `improve`, `prune`, `distill`,
`lessons`, `timeline`, `search`, `list`, `status`, `forget`, identical across **CLI**,
**MCP** (any AI), and **HTTP**. See [FEATURES.md](FEATURES.md) for what each command does and when to use it.
