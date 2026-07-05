# Continuum vs Cognee — the complete cross-check

**Question this answers:** does Continuum do *everything Cognee does* **plus** reasoning — or is it
only a reasoning layer? **Answer:** on the **Cognee backend** it is a true **superset**: every
checkpoint runs Cognee's full pipeline (ingest → knowledge graph → vector index), scopes by
dataset, supports semantic recall + forget — **and then adds the reasoning layer** Cognee lacks.

Two things to know up front:
1. **You must select a Cognee backend** to get Cognee's knowledge graph + vector retrieval. The
   **default is `local`** (SQLite + keyword search + reasoning graph). Best option:
   **`cognee_cloud`** — the hosted platform, which also runs the LLM/embeddings for you.
2. The knowledge graph is now **used in resume**: every resume adds a
   **`## Knowledge-graph context (from Cognee)`** section (a GRAPH_COMPLETION answer), on top of
   the reasoning graph and semantic chunks. (This closed the earlier gap.)

### Three backends
| `CONTINUUM_BACKEND` | Knowledge graph | Semantic retrieval | LLM/embeddings | Use when |
|---|---|---|---|---|
| `local` (default) | ❌ | keyword (FTS5) | your key (reasoning only) | zero-dep demo / offline |
| `cognee` | ✅ (local SDK) | ✅ | **your** OpenAI key | self-hosted Cognee |
| `cognee_cloud` | ✅ (hosted) | ✅ | **managed by Cognee** | the complete superset ⭐ |

---

## What actually runs (verified in code)

### On `checkpoint`  ([cognee_backend.py](../src/continuum/memory/cognee_backend.py) `add_verbatim`)
| Step | Cognee call | What it gives you |
|---|---|---|
| Ingest | `cognee.add(text, dataset_name=ds)` | raw text into Cognee's pipeline (Cognee #1, #3) |
| Knowledge graph | `cognee.cognify(datasets=[ds])` | entities + relations graph (Cognee #4) |
| Reasoning graph | `cognee.cognify(datasets=[ds], graph_model=ReasoningGraph)` | reasoning schema extracted by Cognee's LLM (best-effort) |
| Sidecar | local SQLite | verbatim mirror + `WorkspaceState` + merged reasoning graph (the reasoning layer) |

### On `resume` / `search`  (`search_verbatim`)
| Step | Cognee call | What it gives you |
|---|---|---|
| Semantic recall | `cognee.search(query_type=SearchType.CHUNKS, datasets=[ds])` | vector/embedding retrieval (Cognee #2, #5) |
| Fallback | local FTS5 | keyword search if Cognee errors (never hard-fails) |

### On `forget`  (`delete_project`)
`cognee.prune.prune_data(dataset=ds)` + local cascade delete (Cognee #7).

> `ds = f"{dataset}:{project}"` and `project` is **user-scoped** by the engine
> (`{user}::{project}`) → per-user + per-project isolation (Cognee #8, extended with multi-tenancy).

---

## Feature-by-feature: Cognee → Continuum

| # | Cognee feature | Continuum? | How Continuum does it | How you use it |
|---|---|---|---|---|
| 1 | **remember / store** | ✅ | `checkpoint` stores verbatim; on cognee backend calls `cognee.add` | `continuum checkpoint chat.txt -p X` · "save this chat" |
| 2 | **recall / retrieve** | ✅ | `search` + resume retrieval; cognee backend = semantic, local = keyword | `continuum search -p X "redis"` · "search project X for redis" |
| 3 | **data ingestion (files/docs)** | ~ partial | ingests any text you checkpoint/pipe in; **no dedicated folder/doc ingester yet** | `cat notes.md \| continuum checkpoint - -p X` (see Gaps) |
| 4 | **knowledge graph extraction** | ✅ built / ~ used | `cognee.cognify()` builds the KG; resume doesn't yet *query* it | automatic on checkpoint (cognee backend) |
| 5 | **vector / semantic retrieval** | ✅ (cognee) | `SearchType.CHUNKS` via embeddings; local backend = FTS5 keyword | automatic in `search`/`resume` on cognee backend |
| 6 | **improve / refine** | ✅ | `improve` = reasoning-graph memify (dedup, resolve superseded) | `continuum improve -p X` · "improve project X" |
| 7 | **forget / delete** | ✅ | `forget` = local cascade + `cognee.prune.prune_data` | `continuum forget -p X` · "forget project X" |
| 8 | **dataset / project scoping** | ✅ superset | project scoping **+ per-user multi-tenancy** (`{user}::{project}`) | `continuum --user alice … -p X` · `X-Continuum-User` header |
| 9 | **CLI + UI surfaces** | ✅ / ~ | full CLI; product **dashboard** (`site/`); inspection via `status`/`timeline`/`search` (no graph-explorer UI) | `continuum status/timeline -p X` |
| 10 | **SDK / API integration** | ✅ | Python `Continuum` engine + FastAPI HTTP API | `from continuum import Continuum` · `continuum serve` |
| 11 | **MCP / plugin integration** | ✅ superset | **15 MCP tools**, stdio + remote | see [INTEGRATIONS.md](INTEGRATIONS.md) |
| 12 | **backend / config flexibility** | ✅ | env-driven: `local`↔`cognee`, LLM keys, budgets, tenancy | see `.env.example` / [GETTING-STARTED.md](GETTING-STARTED.md) |

### What Continuum adds that Cognee does NOT
- **Reasoning-state extraction** — decisions *and why*, **rejected alternatives and why not**.
- **Resume package** — a compact, paste-anywhere reconstruction of the working state.
- **Context-health meter** — window fill + drift + strength, "when to checkpoint".
- **distill → lessons** — durable cross-project insights.
- **timeline** — temporal evolution of the thinking.
- **export / import** — provider-neutral portability (switch AIs / machines).
- **provider-neutral cross-AI continuity** — the whole point.

---

## So, directly answering the two questions

**"Is Continuum retrieval reasoning-oriented only?"**
No. On the **cognee backend**, retrieval uses Cognee's **semantic/vector** search (embeddings)
exactly like Cognee — the reasoning graph *guides* which verbatim to include, it doesn't *replace*
semantic retrieval. On the **local backend** retrieval is keyword (FTS5). Reasoning is added **on
top of**, not **instead of**, normal retrieval.

**"Does Continuum only build a reasoning graph?"**
No. On the cognee backend it builds **Cognee's knowledge graph** (`cognify`) **and** a reasoning
graph. Caveat: resume currently *queries* semantic chunks + the reasoning graph, not the knowledge
graph's entity answers — that's the one real gap to closing the loop (below).

---

## Enable "complete mode" (everything Cognee + reasoning) — hosted, recommended

```bash
pip install "continuum[all]"
export CONTINUUM_BACKEND=cognee_cloud
export COGNEE_API_URL="https://tenant-XXXX.aws.cognee.ai"     # from the Cognee platform
export COGNEE_API_KEY="your-cognee-key"
# (no OpenAI key needed — Cognee cloud runs the LLM + embeddings)
continuum mode          # verify: knowledge_graph: True, semantic_retrieval: True, managed_llm: True
continuum mcp -t streamable-http --host 0.0.0.0 --port 8771   # or `continuum serve`
```
Self-hosting Cognee instead? Use `CONTINUUM_BACKEND=cognee` + your own `OPENAI_API_KEY`.
On the **default** (`local`) backend you still get verbatim + keyword search + the full reasoning
layer + all verbs — just not Cognee's KG/vector retrieval.

**Check what's live anytime:** `continuum mode` (CLI) / *"continuum mode"* (MCP) / `GET /mode` (HTTP).

---

## The three gaps — now CLOSED ✅
1. **Knowledge graph used in resume** — resume calls Cognee `GRAPH_COMPLETION` and adds a
   `## Knowledge-graph context (from Cognee)` section. Verified live.
   ([composer.py](../src/continuum/engine/composer.py) `_knowledge_answer` →
   [cognee_cloud_backend.py](../src/continuum/memory/cognee_cloud_backend.py) `graph_answer`.)
2. **Document ingestion verb** — `continuum ingest` (CLI/`continuum_ingest` MCP/`POST /ingest`)
   adds reference docs as knowledge and runs the full cognify pipeline on the Cognee backends.
3. **Backend visibility** — `continuum mode` shows exactly which layers are active, so you always
   know whether a checkpoint stored the knowledge graph + embeddings or just local keyword.

Continuum is now a true superset: on `cognee_cloud` a single `checkpoint` runs
**ingest → knowledge graph → embeddings** *and* extracts the **reasoning layer** — one solution
that does everything Cognee does plus reasoning-state continuity.
