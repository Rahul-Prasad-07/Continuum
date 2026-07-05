# Continuum — Architecture

Ports-and-adapters (learned from Cognee): one engine, swappable backends & surfaces.

```
 SURFACES (adapters):  CLI (built) · MCP server · browser ext · copy-paste
        │
 ENGINE (continuum.Continuum):
   checkpoint(project, text):
      chunk → add_verbatim (SOURCE OF TRUTH)
      extract → WorkspaceState + ReasoningGraph   (LLM structured output, or heuristic)
      store workspace + merge reasoning graph
   resume(project, intent, budget):
      compose = workspace + rejected-alternatives + graph-guided VERBATIM,  SALIENCE-BOUNDED
        │
 MEMORY BACKEND (port):  LocalBackend (SQLite+FTS, runs anywhere) | CogneeBackend (semantic+graph)
```

## Key design decisions
1. **Capture in flight.** Reasoning-state is destroyed on compaction, so we checkpoint as we go.
2. **Verbatim = source of truth; graph = index.** (ENGRAM Pillar 1 / answers "verbatim beats
   extracted": the graph *finds* the right verbatim; we inject the exact words.)
3. **Salience-bounded resume.** The package is capped (`budget_tokens`) so resuming *shrinks*
   the next context window instead of bloating it — the context math is a net win only with
   this bound (ENGRAM Pillar 2 / forgetting).
4. **Content-addressed** chunks & checkpoints (SHA-256) → dedup, integrity, stable IDs.
5. **Provider-agnostic** output: the resume package is plain text → works with any AI, incl.
   zero-integration copy-paste.
6. **Graceful degradation:** no LLM key → heuristic extractor; Cognee error → local retrieval.
   Continuum always produces a package.

## Modules
| Module | Role |
|---|---|
| `models/reasoning.py` | `ReasoningGraph` (Node/Edge) — the ontology (TMS-inspired) |
| `models/workspace.py` | `WorkspaceState` — the checkpoint snapshot |
| `memory/base.py` | `MemoryBackend` port + `Chunk` |
| `memory/local_backend.py` | SQLite + FTS5 (zero-dep runnable) |
| `memory/cognee_backend.py` | production: Cognee semantic retrieval + local sidecar |
| `llm/client.py` | provider-agnostic JSON extraction (OpenAI-compat / Anthropic) |
| `engine/extractor.py` | text → chunks + WorkspaceState + ReasoningGraph (LLM or heuristic) |
| `engine/composer.py` | hybrid, salience-bounded resume package |
| `engine/continuum.py` | orchestrator: `checkpoint()` / `resume()` / `status()` |
| `cli.py` | the universal surface |

## Cognee's role
Cognee is the production storage + reasoning-graph + hybrid-retrieval engine behind
`CogneeBackend`. Continuum adds: the reasoning ontology, the workspace extractor, salience-
bounded composition, and the surfaces. (You build the ~20% on top of the engine.)

## Roadmap
- Full `cognee.cognify(graph_model=ReasoningGraph)` extraction (custom-ontology graph).
- MCP server (`checkpoint`/`resume` tools) + browser extension + provider proxy.
- Salience/decay scoring (recency+frequency+importance) to keep packages bounded at scale.
- Embeddings-based verbatim retrieval in LocalBackend (optional, offline).
