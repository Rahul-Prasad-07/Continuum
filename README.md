# Continuum

Continuum is a reasoning memory for AI. It saves the thinking behind a conversation (the decisions, the alternatives you rejected, the open questions) and rebuilds that state in any other chat, session, or provider.

Most memory tools remember facts, which you can always look up again. They do not remember reasoning, and reasoning is the thing that gets destroyed the moment a context window fills up or a chat ends. Continuum captures that reasoning while you work and hands it back as state, not as a raw transcript, so you never have to re explain yourself to your AI.

## What it does

* **Checkpoint** a conversation. Continuum stores the exact text as the source of truth and extracts a reasoning graph of goals, decisions, rejected options, hypotheses, and open questions.
* **Resume** anywhere. It produces a compact, provider neutral package you can paste into any new chat or a different model, and it remembers what you rejected and why so the model does not re propose it.
* **Capture** from other tools. It reads Grok, Claude Code, and Codex session files directly, with no copy and paste, so switching tools loses nothing.
* **Watch your context health.** A meter shows how full the window is and how much fresh thinking has not been saved yet, and tells you when to checkpoint before anything is lost.
* **Move and back up.** Export the whole state as Markdown, a full transcript, or a lossless JSON bundle, and import it on another machine or into another project.
* **Keep memory clean.** Per user isolation, plus improve, prune, distill, and lessons to deduplicate reasoning and reuse durable insights across projects.

The full command set is the same across the CLI, MCP, and HTTP: checkpoint, save, resume, capture, ingest, context, export, import, improve, prune, distill, lessons, timeline, search, mode, list, status, forget.

## Install

Requires Python 3.10 or newer.

```bash
git clone https://github.com/<your-username>/continuum.git
cd continuum
pip install -e ".[all]"
continuum --version
```

Continuum runs with zero services and zero API keys out of the box, using a local SQLite store and a heuristic extractor. Add an LLM key for cleaner extraction, or point it at Cognee for the full knowledge graph (see Configuration).

## Quickstart

```bash
# 1. Save a conversation into a project called "auth"
continuum checkpoint examples/sample_conversation.txt -p auth

# 2. Rebuild it later, in any chat or any provider
continuum resume -p auth -i "build the token refresh endpoint"

# 3. Check what is stored
continuum status -p auth
```

Copy the resume output, paste it into a fresh chat on any AI, and it continues your work, including the decisions you made and the options you already ruled out.

## Configuration

Everything is environment driven and optional.

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` | none | Clean LLM extraction instead of heuristic mode |
| `OPENAI_MODEL` | `gpt-4o-mini` | Extraction model |
| `CONTINUUM_BACKEND` | `local` | `local` (SQLite), `cognee` (local SDK), or `cognee_cloud` (hosted) |
| `COGNEE_API_URL` and `COGNEE_API_KEY` | none | Hosted Cognee platform, which runs the knowledge graph, embeddings, and LLM for you |
| `CONTINUUM_HOME` | `~/.continuum` | Where memory is stored |
| `CONTINUUM_RESUME_BUDGET` | `8000` | Maximum tokens in a resume package |
| `CONTINUUM_USER` | `default` | Tenant id that isolates memory per user (also `--user`) |
| `CONTINUUM_TOKEN` | none | Requires a bearer token on the HTTP API and remote MCP |

On `cognee_cloud`, the Cognee platform provides the LLM and embeddings, so no OpenAI key is needed for the knowledge graph side. Run `continuum mode` at any time to see which layers are active.

## Ways to use it

One engine sits behind three surfaces, so a beginner and an autonomous agent use the exact same product.

```bash
continuum checkpoint chat.txt -p auth     # CLI, works with any AI by copy and paste
continuum resume -p auth                   # print a package, paste it anywhere
continuum serve                            # HTTP API on port 8770
continuum mcp                              # MCP server over stdio for local agents
docker compose up                          # containerized API
```

**MCP.** Continuum ships an MCP server that exposes every verb as a tool (eighteen tools in total). Local agents such as Claude Code, Codex, and Cursor connect over stdio. Web AIs such as Claude, Grok, and ChatGPT connect to a remote server by URL:

```bash
continuum mcp -t streamable-http --host 0.0.0.0 --port 8771
```

Then add `https://your-host/mcp` as a custom connector. Full per platform instructions are in [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md).

**HTTP API.** `POST /checkpoint`, `/resume`, `/ingest`, `/improve/{p}`, `/prune/{p}`, `/distill/{p}`, `/import/{p}`, `/context/{p}`. `GET /status/{p}`, `/projects`, `/lessons`, `/timeline/{p}`, `/export/{p}`, `/mode`, `/health`. `DELETE /projects/{p}`. Multi tenant through the `X-Continuum-User` header, with optional bearer auth. Interactive docs at `/docs`.

**Copy and paste.** The resume package is plain text, so it works with any AI with no integration at all. Integrations simply remove the copy and paste step.

## How it works

A checkpoint keeps two things: the verbatim conversation as the source of truth, and a merged reasoning graph plus a workspace snapshot as the structured index. A resume uses both. The graph decides what matters, the verbatim supplies the exact words, and the result is bounded by a token budget so it shrinks the next context window rather than bloating it.

On the Cognee backends, a checkpoint also runs the full ingest, knowledge graph, and embedding pipeline, and a resume can include an answer synthesized from the knowledge graph. In that mode Continuum is a superset of Cognee: everything Cognee stores, plus the reasoning layer. See [docs/CONTINUUM-VS-COGNEE.md](docs/CONTINUUM-VS-COGNEE.md).

## Deploy

`render.yaml` and the `Dockerfile` are ready for a hosted deployment of the API and the remote MCP server, with the static dashboard in `site/`. Step by step instructions for Render, Fly, Railway, and a plain VPS are in [docs/DEPLOY.md](docs/DEPLOY.md).

## Project status

Continuum is a working product with a test suite that passes and a core loop verified end to end on real data, including a live Cognee tenant and real Grok, Claude Code, and Codex sessions. It is well suited to individual and power user work today.

It is honest about its edges. Extraction quality depends on the LLM behind it and is rougher in heuristic mode. The MCP server is one tenant per process, while the HTTP API is the multi tenant surface. Storage assumes a single box and has not been load tested at scale. Hosted sync, accounts, single sign on, and the paid tiers shown on the dashboard are planned, not yet built.

## Documentation

* [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md), install to first save and resume
* [docs/FEATURES.md](docs/FEATURES.md), every command, what it does, and when to use it
* [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md), connect it to any AI, web or CLI
* [docs/SWITCHING-PLATFORMS.md](docs/SWITCHING-PLATFORMS.md), move a conversation between tools
* [docs/CONTINUUM-VS-COGNEE.md](docs/CONTINUUM-VS-COGNEE.md), how Continuum uses and extends Cognee
* [docs/DEPLOY.md](docs/DEPLOY.md), take it live
* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), how the pieces fit together

## License

MIT.
