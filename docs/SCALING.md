# Scaling Continuum to long, multi-topic, months-long work

The core loop (`checkpoint` / `resume` / `export`) is great for a single thread over days. Three
problems appear once work runs for **weeks or months across many subjects**:

1. **`resume` only returns the latest checkpoint.** If you worked on *DNA mutation* three weeks ago
   but your last checkpoint is about *deployment*, `resume` hands you deployment context — the DNA
   reasoning is still stored, just not surfaced.
2. **`export` grows without bound.** A month of verbatim can exceed any context window, so the
   "paste it into another AI" story breaks exactly when you need it most.
3. **No hands-free capture.** You have to remember to say "save this", and you have no automatic
   signal for *when* to switch tabs/providers.

This page documents the layer that fixes all three. Everything here is real and covered by tests
(`tests/test_scale_features.py`), on every surface (CLI / MCP / HTTP).

---

## 1. Recall — resume by *subject*, across the whole history

`recall` gathers **every checkpoint about a subject** (topic or intent), ranks them by real term
overlap (recency is only a tie-breaker — unrelated recent work is *not* pulled in), and composes a
single bounded package: how the thinking evolved, merged decisions (deduped, newest wins),
still-open questions, constraints, the Cognee knowledge-graph answer, and the most relevant
verbatim.

```bash
continuum recall -p x "dna mutation"        # or: continuum resume -p x --topic "dna mutation"
```
- **Say in a web AI:** *"recall our dna-mutation work in project x."* → `continuum_recall`.
- **HTTP:** `POST /recall {"project":"x","subject":"dna mutation"}`.

**How topics are known.** Every `checkpoint` now extracts salient **topics** for the snapshot
(heuristic keyword+bigram extraction with zero deps; the LLM path fills them too). On the Cognee
backends, recall additionally uses semantic `CHUNKS` retrieval and the `GRAPH_COMPLETION` answer,
so it matches by *meaning*, not just keywords — that is what Cognee buys you here.

## 2. Bounded, incremental, and digest export — stay paste-size forever

| Form | Command | What it does |
|---|---|---|
| **Bounded** | `export -p x -f md --max-tokens 5000` | keeps the reasoning-state first, fills the rest of the budget with verbatim, truncates the tail so it always fits the next window |
| **Digest** | `export -p x -f digest` | hierarchical compression: the recent checkpoints in full, everything older collapsed to one line each — a month (or a year) stays a few thousand tokens |
| **Incremental** | `export -p x -f json --since <unix_ts>` | only checkpoints newer than a timestamp — a machine pulls just the delta instead of re-reading everything |

The **digest** is the answer to "won't the export fill the context window?" — no, because old work
is summarized to decisions/open-questions and only recent work is verbatim.

## 3. Autopilot — automatic "switch now" at the threshold

`autopilot` runs the context meter and, when the window crosses a threshold (default **80%**) *or*
uncaptured drift is high *or* nothing is saved yet, returns a **ready-to-paste export** plus an
honest reason.

```bash
cat current_chat.txt | continuum autopilot -p x -m claude --threshold 80
```
- **Say in a web AI:** *"continuum autopilot — am I safe to keep going?"* → `continuum_autopilot`.
  When it says *switch now*, it also gives you the export to paste into a fresh tab / another
  provider.
- **HTTP:** `POST /autopilot/x {"text":"<chat>","model":"claude","threshold":80}`.

## 4. Observe — auto-save a whole session, no explicit "save"

`observe` appends each turn to a rolling buffer (persisted under `CONTINUUM_HOME`) and
**auto-checkpoints** when the buffer crosses `flush_tokens` (default 6000). Call it every turn and
the session saves itself.

```bash
continuum observe -p x < latest_turn.txt      # or --force to flush now
```
- **Say in a web AI:** *"observe this turn into continuum project x"* (or instruct the assistant to
  call `continuum_observe` after every exchange).
- **HTTP:** `POST /observe/x {"turn":"<text>","flush_tokens":6000}`.

## Agent-optimized HTTP (robots query, don't load exports)

So an agent never has to swallow a giant export just to get a fact:

- `GET /search/{project}?q=...&k=6` — structured hits.
- `GET /decisions/{project}` — the latest checkpoint's decisions as JSON (choice / why / rejected).
- `POST /recall` — subject-scoped package.
- `GET /export/{project}?format=digest&max_tokens=4000` — compressed, bounded.

---

## Honest boundaries (what is *not* built, and why)

- **A live % bar inside Claude.ai's or Grok's own chat window is not something Continuum can add** —
  that is the provider's UI, not ours. The buildable equivalents are (a) `autopilot`, which renders
  the bar and auto-hands you the export from inside the conversation via the MCP tool, and (b) a
  live meter in **our** dashboard, which we control. Anyone claiming to inject a bar into a
  third-party chat UI would need a browser extension; that is a separate, optional client.
- **Semantic recall quality depends on the backend.** On `local` it is keyword+topic matching; for
  meaning-based recall across large histories, use `cognee` / `cognee_cloud` (embeddings + graph).
- **Digest/summarization is deterministic**, not LLM-abstractive — it compresses by dropping
  verbatim and keeping decisions/open-questions. It is honest and cheap; an LLM-abstractive digest
  is a future option, not a current claim.
- **`observe`'s buffer is per `CONTINUUM_HOME`.** For multi-process web serving, point observers at
  a shared home (or use the HTTP API, which is multi-tenant per `X-Continuum-User`).
