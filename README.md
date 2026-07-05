# Continuum 🧠↻

**Reasoning-state continuity for AI.** Save & resume your AI *thinking* — decisions, rejected
alternatives, hypotheses (not just facts) — across sessions and providers.

> Everyone else solves *retrieval* ("what fact to fetch"). Continuum solves *continuity*
> ("how to resume the thinking"). Because reasoning-state is **destroyed, not un-retrieved**,
> it must be **captured in flight** — and transferred as **state, not transcript**.

## What it does
- **Checkpoint** a conversation → extract a reasoning graph + workspace state, keep verbatim.
- **Resume** in *any* new chat/provider → a compact, provider-agnostic **resume package** you
  paste anywhere (Claude, GPT, Gemini, Cursor, Claude Code…).
- Remembers **what you rejected and why** — across a provider switch.
- **Context-health meter** — see how full the window is and when to save *before* reasoning is lost.
- **Export / import** — move the whole state to a new chat, another platform, or a backup.
- **Multi-tenant, self-cleaning memory** — per-user isolation, `improve`/`prune`/`distill`/`lessons`.

Full verb set (identical across CLI, MCP, and HTTP): `checkpoint` · `resume` · `context` ·
`capture` · `ingest` · `export` · `import` · `improve` · `prune` · `distill` · `lessons` ·
`timeline` · `search` · `mode` · `list` · `status` · `forget`.

**Cross-platform switching:** `capture` reads Grok / Claude Code / Codex native session files
directly (zero copy-paste), normalizes them, and checkpoints — then `resume` anywhere. See
[docs/SWITCHING-PLATFORMS.md](docs/SWITCHING-PLATFORMS.md).

**Complete superset of Cognee:** with `CONTINUUM_BACKEND=cognee_cloud`, every checkpoint runs
Cognee's managed **ingest → knowledge graph → embeddings** pipeline **and** extracts the reasoning
layer; resume includes a Cognee knowledge-graph answer. See
[docs/CONTINUUM-VS-COGNEE.md](docs/CONTINUUM-VS-COGNEE.md). Run `continuum mode` to see which layers
are active.

## Quickstart
```bash
python3 -m venv .venv && ./.venv/bin/pip install pydantic click
export PYTHONPATH=src

# 1. checkpoint a conversation (file or stdin)
./.venv/bin/python -m continuum.cli checkpoint examples/sample_conversation.txt -p auth

# 2. resume anywhere — paste the output into a fresh chat / different provider
./.venv/bin/python -m continuum.cli resume -p auth -i "build the token refresh endpoint"

# status
./.venv/bin/python -m continuum.cli status -p auth
```

Runs with **zero services / zero API keys** (local SQLite + heuristic extraction). Add a key
for clean LLM extraction, or `CONTINUUM_BACKEND=cognee` for production semantic retrieval.

## Configure (all optional)
| Env | Default | What |
|---|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | — | enable clean LLM extraction |
| `OPENAI_MODEL` | `gpt-4o-mini` | extraction model |
| `CONTINUUM_BACKEND` | `local` | `local` (SQLite) · `cognee` (SDK) · `cognee_cloud` (hosted, complete) |
| `COGNEE_API_URL` / `COGNEE_API_KEY` | — | Cognee **cloud** platform (managed KG + embeddings + LLM) |
| `CONTINUUM_HOME` | `~/.continuum` | data dir |
| `CONTINUUM_RESUME_BUDGET` | `8000` | max tokens in the resume package |
| `CONTINUUM_USER` | `default` | tenant id — isolates memory per user (also `--user`) |
| `CONTINUUM_COGNEE_REASONING` | `1` | Cognee backend: also extract the reasoning graph via `cognify(graph_model=…)` |

## Surfaces (any user, any platform)
One engine, many faces — pick your integration:
```bash
pip install -e ".[all]"          # or .[api] / .[mcp] / .[llm]

continuum checkpoint chat.txt -p auth     # CLI (universal, copy-paste)
continuum resume -p auth -i "..."         # CLI resume → paste anywhere
continuum serve                           # HTTP API on :8770 (browser ext / web / integrations)
continuum mcp                             # MCP server (Claude Code / Codex / any MCP agent)
docker compose up                         # containerized API
```
- **HTTP API:** `POST /checkpoint · /resume · /improve · /prune · /distill · /import · /context` · `GET /status · /projects · /lessons · /timeline · /export · /health` · `DELETE /projects/{p}`. Multi-tenant via `X-Continuum-User`; optional `CONTINUUM_TOKEN` bearer auth. (`/docs` for OpenAPI.)
- **MCP (add anywhere):** 15 tools including `continuum_save`, `continuum_context`, `continuum_export`/`import`, plus checkpoint/resume/improve/prune/distill/lessons/timeline/search/status/list/forget.
  - **local (stdio):** Claude Code, Codex, Cursor.
  - **remote (HTTP):** `continuum mcp -t streamable-http --host 0.0.0.0 --port 8771` → add by URL as a **connector in Claude web / Grok / ChatGPT**.
  - **Full step-by-step for every platform** (Claude web deep-dive, Grok, ChatGPT, Claude Code, Codex, Cursor, tunnels, troubleshooting): **[docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)**.
- **Copy-paste:** the resume package is plain text → works with *any* AI, zero integration.
- **Product overview / dashboard:** [site/index.html](site/index.html) — problem, comparison vs memory layers, live context-health gauge, features, integrations, pricing.

## How it works
`checkpoint()` → verbatim (source of truth) + `WorkspaceState` + `ReasoningGraph`.
`resume()` → hybrid retrieval (graph finds → verbatim included), **salience-bounded** so it
shrinks context instead of bloating it. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Status
Working product: engine + CLI + HTTP API + MCP server + Docker + CI, tested. Backends: local
SQLite (zero-dep) and [Cognee](https://github.com/topoteretes/cognee) (production). Roadmap:
browser extension, embeddings in local backend, salience/decay tuning at scale.

MIT.
