# Deploy Continuum live (for any user)

Continuum runs as a normal container. This guide gets it **live on the internet** so anyone can
use it — via the HTTP API and/or as a remote MCP connector in Claude web, Grok, ChatGPT.

## What "live for any users" needs
1. **A host** that runs the container (Render / Fly / Railway / any VPS).
2. **A public HTTPS URL** (all of these give you one).
3. **A persistent disk** for `/data` (so memory survives restarts).
4. **A bearer token** (`CONTINUUM_TOKEN`) so the endpoint isn't open to the world.
5. *(optional)* **Cognee Cloud** creds for the full knowledge-graph superset, and/or an
   **LLM key** for clean reasoning extraction.

Two services ship in the blueprint:
- **continuum-api** — the HTTP API. Multi-tenant: each user is isolated by the `X-Continuum-User`
  header. This is the backbone for apps and multi-user.
- **continuum-mcp** — the remote MCP server you add as a connector in web AIs. It is **one tenant
  per process** (set `CONTINUUM_USER` to scope it); for a personal connector that's fine.

---

## Option A — Render (blueprint, easiest)
1. Push this repo to GitHub (Render deploys from a repo).
2. Render → **New + → Blueprint** → pick the repo. Render reads [`render.yaml`](../render.yaml).
3. It creates **continuum-api** and **continuum-mcp**. `CONTINUUM_TOKEN` is auto-generated; fill
   optional secrets (`COGNEE_API_URL`, `COGNEE_API_KEY`, `OPENAI_API_KEY`) in the dashboard.
4. Deploy. You get URLs like `https://continuum-api.onrender.com` and
   `https://continuum-mcp.onrender.com`.
5. Verify: open `https://continuum-api.onrender.com/health` → `{"ok":true,...}`.

> Render's free tier has no persistent disk and sleeps when idle — use **Starter** (what the
> blueprint sets) so `/data` persists.

## Option B — Fly.io
```bash
fly launch --no-deploy          # detects the Dockerfile; creates fly.toml
fly volumes create continuum_data --size 1
# in fly.toml: mount continuum_data → /data, set internal_port = 8770, [http_service] health check /health
fly secrets set CONTINUUM_TOKEN=$(openssl rand -hex 24)
# optional: fly secrets set COGNEE_API_URL=... COGNEE_API_KEY=... OPENAI_API_KEY=...
fly deploy
```

## Option C — Railway / any Docker host
Point it at the repo (Dockerfile is auto-detected), add a volume at `/data`, set
`CONTINUUM_TOKEN`, expose port `8770`. Done.

## Option D — Your own VPS (Docker Compose)
```bash
git clone <your-repo> && cd Continuum
CONTINUUM_TOKEN=$(openssl rand -hex 24) docker compose up -d   # API on :8770
# put it behind Caddy/nginx for HTTPS
```

---

## After it's live

### Use the HTTP API
```bash
curl https://YOUR-API/health
curl -X POST https://YOUR-API/checkpoint \
  -H 'authorization: Bearer <CONTINUUM_TOKEN>' \
  -H 'X-Continuum-User: alice' -H 'content-type: application/json' \
  -d '{"project":"auth","text":"use JWT (low ops). reject Redis: lock race. next: refresh."}'
```

### Add the MCP connector (Claude web / Grok / ChatGPT)
Add `https://YOUR-MCP/mcp` as a custom connector (with `Authorization: Bearer <token>` if the
client supports a header). Full per-platform steps: [INTEGRATIONS.md](INTEGRATIONS.md).

### Turn on "complete mode" (Cognee knowledge graph)
Set on the service: `CONTINUUM_BACKEND=cognee_cloud`, `COGNEE_API_URL`, `COGNEE_API_KEY`. Then
`GET /mode` shows `knowledge_graph: true`.

---

## Env vars (deployment matrix)
| Var | Needed | Purpose |
|---|---|---|
| `CONTINUUM_TOKEN` | strongly recommended | bearer auth on API + remote MCP |
| `CONTINUUM_HOME` | yes (set to `/data`) | where memory persists (mount a disk here) |
| `CONTINUUM_BACKEND` | default `local` | `local` · `cognee` · `cognee_cloud` |
| `COGNEE_API_URL` / `COGNEE_API_KEY` | for `cognee_cloud` | managed KG + embeddings + LLM |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | optional | clean (non-heuristic) reasoning extraction |
| `CONTINUUM_ALLOWED_HOSTS` | MCP behind a domain | comma-separated allowed Host headers |
| `CONTINUUM_USER` | optional (MCP) | scope a single-tenant MCP server to one user |

## Deploy the dashboard (static site)
The marketing site is a single self-contained file: `site/index.html` (no build step, no external
assets). Host it anywhere that serves static files:

- **Render static site:** New + -> Static Site -> repo -> Publish directory `site` -> Deploy.
- **Cloudflare Pages / Netlify / Vercel:** connect the repo, set output/publish dir to `site`.
- **GitHub Pages:** push, then Settings -> Pages -> deploy from `/site`.
- **Any box:** `python -m http.server` from inside `site/`, or drop `index.html` behind nginx.

After the API/MCP is live, edit `site/index.html` and replace the placeholder
`https://your-app.onrender.com/mcp` with your real MCP URL so visitors can copy it.

## Publish the CLI to PyPI (so `pipx install continuum` works)
The dashboard/docs tell users `pipx install continuum`. That only works once the package is
published. Until then, users install from the repo (`pip install -e ".[all]"`). To publish:
```bash
pip install build twine
python -m build                      # builds wheel + sdist from pyproject.toml
twine upload dist/*                  # needs a PyPI account + token; name must be free
```
Deployment does NOT need this (the Docker image installs from source); it only matters for the
one-line CLI install.

## Honest limits for a public deployment
- **MCP is one tenant per process.** A single public MCP server puts everyone under one memory
  space. For real multi-user, use the **HTTP API** (per-user header) or run one MCP instance per
  user. True multi-tenant MCP is a roadmap item.
- **SQLite on a disk** is fine for one box / modest load; it is not built for high-concurrency
  multi-node. For scale, move storage to `cognee_cloud` (centralized) and/or a shared DB — a
  future backend.
- **Set the token and HTTPS.** The store holds verbatim conversation text — treat it as sensitive.
