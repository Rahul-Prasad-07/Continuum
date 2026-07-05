# Continuum Integrations — run it in every AI (web + CLI) via MCP

This is the complete guide to running Continuum and connecting it to any AI: web chats
(Claude web, Grok, ChatGPT, Gemini) and CLI/desktop agents (Claude Code, Codex, Cursor,
Windsurf, …). It also covers the HTTP API and the universal copy‑paste fallback that works
on 100% of AIs with zero setup.

> **TL;DR**
> - **CLI / desktop agents** → connect over **MCP stdio** (`continuum mcp`). No hosting.
> - **Web AIs** → connect over **remote MCP** (`continuum mcp -t streamable-http`) added **by URL**.
> - **Anything else** → **copy‑paste** the `continuum resume` / `continuum export` text. Always works.

---

## 0. The one mental model

Continuum is one engine behind three surfaces — **CLI**, **MCP server**, **HTTP API** — all
exposing the same verbs: `checkpoint · resume · context · export · import · improve · prune ·
distill · lessons · timeline · search · list · status · forget`.

For AIs, the surface that matters is **MCP** (Model Context Protocol). MCP has two transports:

| Transport | Command | Who uses it | Hosting |
|---|---|---|---|
| **stdio** | `continuum mcp` | local agents on your machine (Claude Code, Codex, Cursor, Windsurf) | none — the client launches it |
| **streamable‑http** (remote) | `continuum mcp -t streamable-http --host 0.0.0.0 --port 8771` | web AIs added **by URL** (Claude web, Grok, ChatGPT) | you host it + expose over HTTPS |
| **sse** (remote, legacy) | `continuum mcp -t sse --host 0.0.0.0 --port 8771` | older SSE‑only MCP clients | same as above |

When connected, the AI gets **15 tools** (`continuum_checkpoint`, `continuum_save`,
`continuum_resume`, `continuum_context`, `continuum_export`, `continuum_import`,
`continuum_status`, `continuum_list_projects`, `continuum_search`, `continuum_forget`,
`continuum_improve`, `continuum_prune`, `continuum_distill`, `continuum_lessons`,
`continuum_timeline`). You then just *talk to the AI* — "save this whole chat with continuum",
"resume project auth", "how full is my context?".

---

## 1. Install (once)

```bash
pip install "continuum[mcp,llm]"      # MCP surface + clean LLM extraction
# (or: pip install -e ".[all]" from a checkout)
continuum --version                    # sanity check
```

- **Zero keys needed** to run (local SQLite + heuristic extraction).
- Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` for clean reasoning extraction (recommended).

### Optional: "complete mode" (everything Cognee does + reasoning)
For the full knowledge-graph + semantic retrieval on top of reasoning, use the hosted Cognee
platform — it also runs the LLM/embeddings, so no OpenAI key is required:
```bash
export CONTINUUM_BACKEND=cognee_cloud
export COGNEE_API_URL="https://tenant-XXXX.aws.cognee.ai"
export COGNEE_API_KEY="your-cognee-key"
continuum mode      # → knowledge_graph: True, semantic_retrieval: True, managed_llm: True
```
Everything below (MCP/CLI/HTTP) works the same; checkpoints just also build the Cognee knowledge
graph and resume includes a knowledge-graph answer. Details: [CONTINUUM-VS-COGNEE.md](CONTINUUM-VS-COGNEE.md).

---

# PART A — Web AIs (remote MCP by URL)

Web chats can't launch a local process, so they connect to a **hosted** Continuum over HTTPS.
The flow is always: **(1) run the remote server → (2) expose it over HTTPS → (3) add the URL in
the app → (4) use it in chat.**

## 2. Run the remote MCP server

```bash
export CONTINUUM_TOKEN="pick-a-long-secret"     # optional but recommended (Bearer auth)
export OPENAI_API_KEY="sk-..."                  # optional: clean extraction
# export CONTINUUM_USER="alice"                 # optional: this server's memory is this user's

continuum mcp -t streamable-http --host 0.0.0.0 --port 8771
# → MCP endpoint served at  http://<host>:8771/mcp
```

Notes:
- The endpoint path is **`/mcp`** (for `sse` transport it's `/sse`).
- Opening `/mcp` in a normal browser shows a friendly help page (a raw browser GET returns 406 —
  that's expected; it's an MCP endpoint, not a web page).
- **Tenancy:** the MCP server runs as **one user per process** (the `CONTINUUM_USER` at launch,
  else `default`). To serve multiple isolated users over MCP, run one instance per user (different
  port + `CONTINUUM_USER`), or use the **HTTP API** (Part C) which is multi‑tenant via a header.

## 3. Expose it over HTTPS

Web connectors require a public **HTTPS** URL. Fastest options:

```bash
# Cloudflare Tunnel (no account needed for a quick trycloudflare URL)
cloudflared tunnel --url http://localhost:8771
# → prints https://something.trycloudflare.com   → your MCP URL is  https://something.trycloudflare.com/mcp

# or ngrok
ngrok http 8771
# → https://xxxx.ngrok-free.app  →  https://xxxx.ngrok-free.app/mcp
```

For a permanent deployment, put it on a VPS / Fly / Render behind HTTPS (see `Dockerfile` and
`docker-compose.yml`) with a real domain.

**Host‑header note (tunnels):** by default Continuum disables MCP DNS‑rebinding protection so
tunnel domains work out of the box (security then comes from the secret URL + `CONTINUUM_TOKEN`).
To lock it down, list your domains:
```bash
export CONTINUUM_ALLOWED_HOSTS="something.trycloudflare.com,your-domain.com"
```

---

## 4. Claude web — full step‑by‑step (MCP)

**Goal:** add Continuum as a custom connector in Claude web and use it in any chat.

### 4.1 Prerequisites
- Continuum remote server running and reachable at an HTTPS `…/mcp` URL (sections 2–3).
- A Claude plan that allows **custom connectors** (Pro / Max / Team / Enterprise). Team/Enterprise
  admins may need to enable custom connectors for the workspace.

### 4.2 Add the connector
1. Go to **claude.ai** → click your name/avatar → **Settings**.
2. Open **Connectors** (a.k.a. *Integrations*).
3. Click **Add custom connector** (bottom of the list).
4. **Name:** `Continuum`.
5. **Remote MCP server URL:** paste your `https://<host>/mcp` URL.
6. If the dialog offers an **auth / header** field, add `Authorization: Bearer <CONTINUUM_TOKEN>`.
   If it only accepts a URL (OAuth‑style), keep the URL **secret/unguessable** and, for real
   deployments, front the server with an OAuth proxy. For personal use, a secret tunnel URL +
   token‑less server is fine on a trusted network.
7. Click **Add / Connect**. Claude validates the endpoint and lists the `continuum_*` tools.

### 4.3 Turn it on in a chat
1. Start (or open) a chat.
2. Click the **tools / connectors** control (the plug/📎‑style icon near the message box) and make
   sure **Continuum** is enabled for this conversation.
3. Verify: type **"List my continuum projects."** → Claude calls `continuum_list_projects`. If it
   asks permission to use the tool, allow it.

### 4.4 Use it (natural language)
- **Save the whole chat:** *"Use continuum to save this entire conversation to project `billing`."*
  → calls `continuum_save`/`continuum_checkpoint`.
- **Check you're safe:** *"Continuum, how full is my context — should I checkpoint?"*
  → `continuum_context` returns the window/drift/strength gauge.
- **Resume later / new chat:** open a new chat → *"Resume continuum project `billing` toward the
  webhook retry."* → `continuum_resume` reconstructs the state (including rejected alternatives).
- **Leave Claude for another AI:** *"Export continuum project `billing` as markdown so I can paste
  it into another AI."* → `continuum_export` returns paste‑ready text.

> ⚠️ **Fidelity note:** when Claude calls `continuum_checkpoint`, it passes *what's in its context*.
> For a very long chat that may not be 100% verbatim. For guaranteed full capture, use the
> **copy‑paste + CLI** path (Part D): select the whole chat → save to a file → `continuum checkpoint`.

---

## 5. Grok (grok.com / X) — MCP by URL
Grok supports remote MCP connectors similarly:
1. **Settings → Connectors / Integrations → Add custom MCP server.**
2. URL: `https://<host>/mcp`. Add `Authorization: Bearer <token>` if a header field is offered.
3. Enable it in the composer, then: *"Save this chat to continuum project X"* / *"Resume project X."*

If Grok‑CLI / grok‑build supports MCP config files, use the **generic stdio config** in Part B.

---

## 6. ChatGPT — MCP connector
Custom MCP connectors in ChatGPT are available on **Plus/Pro/Team/Enterprise** (often under
**Settings → Connectors**, or Developer mode / "Add custom connector"):
1. Add a custom connector with URL `https://<host>/mcp`.
2. Provide the bearer token if prompted.
3. Use in chat the same way: *"checkpoint this to continuum project X" / "resume project X."*

Where custom connectors aren't enabled on your plan, use the **copy‑paste fallback** (Part D).

---

## 7. Gemini & everything else
Google Gemini (web) doesn't currently take arbitrary remote MCP servers from the chat UI. Use the
**universal copy‑paste** path (Part D): `continuum resume -p X` → paste into Gemini. If you use a
Gemini **CLI/agent** that speaks MCP, use the generic stdio config (Part B).

---

# PART B — CLI / desktop agents (local MCP stdio)

No hosting, no tunnel. The client launches `continuum mcp` (stdio) itself.

## 8. Claude Code (CLI)
```bash
# add the local MCP server to Claude Code
claude mcp add continuum -- continuum mcp
# verify
claude mcp list
```
Then in Claude Code: *"checkpoint this to continuum project auth" / "resume project auth."*
To scope memory to a user: `claude mcp add continuum -- continuum --user alice mcp`.

## 9. Codex (CLI)
Add to Codex's MCP config (TOML — `~/.codex/config.toml` or your Codex MCP settings):
```toml
[mcp_servers.continuum]
command = "continuum"
args = ["mcp"]
```

## 10. Cursor
Create/edit `.cursor/mcp.json` (project) or the global Cursor MCP settings:
```json
{
  "mcpServers": {
    "continuum": { "command": "continuum", "args": ["mcp"] }
  }
}
```
Reload Cursor; the `continuum_*` tools appear in the agent.

## 11. Windsurf / Claude Desktop / any stdio MCP client
Same shape — point the client's MCP config at the command:
```json
{
  "mcpServers": {
    "continuum": {
      "command": "continuum",
      "args": ["mcp"],
      "env": { "OPENAI_API_KEY": "sk-...", "CONTINUUM_USER": "default" }
    }
  }
}
```
(Claude Desktop config lives in `claude_desktop_config.json`.)

## 12. Point a local client at the REMOTE server instead
If a desktop client supports **remote** MCP, you can skip stdio and use your hosted URL
(`https://<host>/mcp`) with `Authorization: Bearer <token>` — handy to share one memory across
several machines.

---

# PART C — HTTP API (custom apps, browser extensions, scripts)

```bash
export CONTINUUM_TOKEN="secret"      # optional bearer auth
continuum serve                      # http://127.0.0.1:8770   (OpenAPI at /docs)
```
Call it from anything. **Multi‑tenant:** send `X-Continuum-User: <user>` to isolate memory per user.
```bash
curl -X POST localhost:8770/checkpoint \
  -H 'content-type: application/json' -H 'X-Continuum-User: alice' \
  -H 'authorization: Bearer secret' \
  -d '{"project":"auth","text":"use JWT (low ops). reject Redis: lock race. next: refresh endpoint."}'

curl -X POST localhost:8770/context/auth \
  -H 'content-type: application/json' -H 'X-Continuum-User: alice' \
  -d '{"text":"<current chat>","model":"claude"}'

curl "localhost:8770/export/auth?format=md" -H 'X-Continuum-User: alice'   # paste-anywhere doc
```
Endpoints: `POST /checkpoint /resume /improve/{p} /prune/{p} /distill/{p} /import/{p} /context/{p}`,
`GET /status/{p} /projects /lessons /timeline/{p} /export/{p} /health`, `DELETE /projects/{p}`.

---

# PART D — Universal fallback: copy‑paste (works with EVERY AI, zero setup)

No MCP, no plan, no hosting required. This always works:
```bash
# 1) capture (full fidelity): copy the whole chat → save → checkpoint
pbpaste > chat.txt                     # macOS (or paste into chat.txt)
continuum checkpoint chat.txt -p auth

# 2) resume anywhere: print the package → paste into ANY AI
continuum resume -p auth -i "build the refresh endpoint"

# 3) switch platforms: export the whole state as markdown → paste into ChatGPT/Grok/Gemini
continuum export -p auth -f md | pbcopy
```
The output is plain text, so it drops into Claude web, Grok, ChatGPT, Gemini — literally anything.
MCP just removes the copy‑paste step.

---

## 13. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Browser shows **406** at `/mcp` | It's an MCP endpoint, not a web page | Normal — you'll see a help page; add the URL as a connector, don't "visit" it |
| **"Invalid Host header"** | MCP DNS‑rebinding protection vs your tunnel domain | Leave `CONTINUUM_ALLOWED_HOSTS` unset (protection off), or set it to your domain(s) |
| **401 unauthorized** | `CONTINUUM_TOKEN` set but client didn't send it | Add `Authorization: Bearer <token>`; or unset the token for local/personal use |
| Tools don't appear in the AI | Connector not enabled for the chat, or URL wrong | Re‑check the `…/mcp` URL; enable the connector in the composer; re‑connect |
| Checkpoint misses parts of a long chat | MCP passes only what's in context | Use the copy‑paste + CLI path for guaranteed full verbatim |
| Rough/empty reasoning extraction | No LLM key (heuristic mode) | `export OPENAI_API_KEY=…` (or `ANTHROPIC_API_KEY`) and re‑checkpoint |

## 14. Security checklist (hosted)
- Always set `CONTINUUM_TOKEN` and serve over **HTTPS**.
- Keep the tunnel/URL secret; prefer a real domain + auth proxy for production.
- Continuum stores **verbatim** conversation text — treat the data store as sensitive (encrypt the
  volume, isolate per user) before onboarding real users.

---

See also: **[GETTING-STARTED.md](GETTING-STARTED.md)** (install → first save/resume),
**[USE-CASES.md](USE-CASES.md)** (recipes per verb), **[ADD-ANYWHERE.md](ADD-ANYWHERE.md)** (short version).
