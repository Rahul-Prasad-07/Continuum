# Add Continuum anywhere

> **Looking for the full, step‑by‑step guide** (Claude web deep‑dive, Grok, ChatGPT, Codex,
> Cursor, tunnels, troubleshooting)? See **[INTEGRATIONS.md](INTEGRATIONS.md)**. This page is the
> short version.

Continuum ships an **MCP server** so any MCP-capable AI can call it. Two ways to connect:
**local (stdio)** for desktop/coding agents, and **remote (HTTP)** — added by URL — for web
AIs like Claude web, Grok, ChatGPT, etc.

Tools every surface gets (**15**): `continuum_checkpoint`, `continuum_save`, `continuum_resume`,
`continuum_context`, `continuum_export`, `continuum_import`, `continuum_status`,
`continuum_list_projects`, `continuum_search`, `continuum_forget`, `continuum_improve`,
`continuum_prune`, `continuum_distill`, `continuum_lessons`, `continuum_timeline` — users can do
everything.

---

## 1. Host the remote MCP server
```bash
pip install "continuum[mcp,llm]"
export CONTINUUM_TOKEN="choose-a-secret"          # protects the endpoint
continuum mcp -t streamable-http --host 0.0.0.0 --port 8771
# → serves the MCP endpoint at  http://<your-host>:8771/mcp
```
Deploy it on any box/VPS/Fly/Render (see `Dockerfile`). Put it behind HTTPS in production.
The `CONTINUUM_TOKEN` requires `Authorization: Bearer <token>` on every request.

> Local-only? Skip hosting and use stdio (section 4).

---

## 2. Add it to a WEB AI (Claude web, Grok, ChatGPT, …)
These platforms add MCP servers as **connectors by URL** (naming varies by product):
1. Open the app's **Settings → Connectors / Integrations / MCP servers**.
2. **Add custom / remote MCP server.**
3. URL: `https://<your-host>/mcp`  (streamable-http) — or the `/sse` URL for SSE-only clients.
4. Auth header: `Authorization: Bearer <CONTINUUM_TOKEN>`.
5. Save. The `continuum_*` tools appear; the AI can now checkpoint, resume, check context & more.

Then in any chat:
- *"Checkpoint this conversation to project 'auth' with continuum."*
- (next day, anywhere) *"Resume project 'auth' toward the refresh endpoint with continuum."*

> Availability of "custom remote MCP" depends on the platform/plan. Where it isn't available
> yet, use the **copy-paste** fallback (section 5) — it works on 100% of AIs today.

---

## 3. Add it to a CODING agent (Claude Code, Codex, Cursor)
Local stdio, no hosting needed. Example `claude_desktop_config.json` / MCP config:
```json
{
  "mcpServers": {
    "continuum": { "command": "continuum", "args": ["mcp"] }
  }
}
```
Or point at the remote URL if the client supports remote MCP.

---

## 4. Local stdio (any stdio MCP client)
```bash
continuum mcp            # speaks MCP over stdio
```

---

## 5. Universal fallback — copy-paste (works with EVERY AI, zero setup)
No MCP support anywhere? Use the CLI or HTTP API and paste the text:
```bash
continuum checkpoint chat.txt -p auth
continuum resume -p auth -i "build the refresh endpoint"   # paste output into any chat
```
The resume package is plain text, so it drops into Claude web, Grok web, ChatGPT, Gemini —
literally anything. Integrations just remove the copy-paste step.

---

## Security notes
- Always set `CONTINUUM_TOKEN` for a hosted server; serve over HTTPS.
- The same token protects the HTTP API (`Authorization: Bearer …`).
- Continuum stores verbatim conversation text — treat the data store as sensitive (encrypt
  volume, per-user isolation) before onboarding real users.
