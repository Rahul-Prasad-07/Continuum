"""MCP server surface — add Continuum to ANY MCP-capable AI.

Transports:
  - stdio            : local agents (Claude Code, Codex)
  - sse / streamable-http : REMOTE connector — add by URL in Claude web, Grok, etc.

Tools (users can do everything):
  continuum_checkpoint, continuum_resume, continuum_status,
  continuum_list_projects, continuum_search, continuum_forget

Auth: set CONTINUUM_TOKEN to require `Authorization: Bearer <token>` on the remote transport.

Run:
  continuum mcp                                  # stdio
  continuum mcp --transport streamable-http --host 0.0.0.0 --port 8771
"""

from __future__ import annotations

import os

from continuum.engine import Continuum


def build_server(remote: bool = False):
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as e:  # pragma: no cover
        raise RuntimeError("The MCP surface needs the SDK: pip install 'continuum[mcp]'") from e

    kwargs: dict = {}
    if remote:
        # Remote transports go through a tunnel/proxy, so the incoming Host header is your
        # public domain — not localhost. The MCP SDK's DNS-rebinding protection rejects that
        # with "Invalid Host header". Allow the configured hosts, or disable the check
        # (security then comes from the secret URL + optional CONTINUUM_TOKEN).
        from mcp.server.transport_security import TransportSecuritySettings

        hosts_env = os.getenv("CONTINUUM_ALLOWED_HOSTS", "").strip()
        if hosts_env:
            hosts = [h.strip() for h in hosts_env.split(",") if h.strip()]
            kwargs["transport_security"] = TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=hosts + ["localhost", "127.0.0.1"],
                allowed_origins=["*"],
            )
        else:
            kwargs["transport_security"] = TransportSecuritySettings(
                enable_dns_rebinding_protection=False
            )
        kwargs["stateless_http"] = True  # more compatible with web connectors (e.g. Claude web)

    mcp = FastMCP("continuum", instructions=(
        "Continuum gives you persistent, provider-independent memory of your REASONING — "
        "decisions, rejected alternatives, hypotheses, open questions — not just facts. "
        "Use continuum_checkpoint to save the current conversation's reasoning-state, and "
        "continuum_resume to reconstruct it later (here or in another AI)."
    ), **kwargs)
    engine = Continuum()

    @mcp.tool()
    def continuum_checkpoint(project: str, text: str) -> str:
        """Save the reasoning-state of a conversation so it can be resumed later anywhere.

        Call this whenever the user says things like "save this chat", "save the whole
        conversation", "checkpoint this", "remember where we are", or "back this up with
        continuum". Pass the FULL conversation transcript so far as `text`.

        project: project/thread name. text: the conversation transcript to checkpoint.
        """
        ws = engine.checkpoint(project, text)
        return f"Saved '{project}' (id={ws.checkpoint_id}, {len(ws.decisions)} decisions)."

    @mcp.tool()
    def continuum_save(project: str, text: str) -> str:
        """Alias for checkpoint — "save the whole chat" in one call. Pass the full transcript."""
        ws = engine.checkpoint(project, text)
        return (
            f"Saved the conversation to '{project}' (id={ws.checkpoint_id}, "
            f"{len(ws.decisions)} decisions). Resume it later here or on any other AI with "
            f"continuum_resume, or hand it to the user with continuum_export."
        )

    @mcp.tool()
    def continuum_resume(project: str, intent: str = "") -> str:
        """Reconstruct reasoning-state as a paste-ready resume package to continue the work.

        project: project to resume. intent: what you're resuming toward (optional).
        """
        return engine.resume(project, intent=intent)

    @mcp.tool()
    def continuum_recall(project: str, subject: str) -> str:
        """Resume by SUBJECT across the WHOLE project history — gather every checkpoint about a
        topic or intent, not just the latest one. Use when the user says things like "continue our
        work on X", "what did we decide about X", or the topic was worked on earlier but the most
        recent checkpoint is about something else. Example subject: "dna mutation"."""
        return engine.recall(project, subject)

    @mcp.tool()
    def continuum_status(project: str) -> str:
        """Report saved reasoning-state for a project."""
        return ", ".join(f"{k}={v}" for k, v in engine.status(project).items())

    @mcp.tool()
    def continuum_list_projects() -> str:
        """List all projects that have saved reasoning-state."""
        projects = engine.list_projects()
        return "\n".join(projects) if projects else "(no projects yet)"

    @mcp.tool()
    def continuum_search(project: str, query: str) -> str:
        """Search a project's memory for relevant passages (verbatim)."""
        hits = engine.search(project, query)
        return "\n\n".join(f"- {h}" for h in hits) if hits else "(no matches)"

    @mcp.tool()
    def continuum_forget(project: str) -> str:
        """Permanently delete a project's memory (irreversible)."""
        counts = engine.forget(project)
        return f"Forgot '{project}': {counts}"

    @mcp.tool()
    def continuum_improve(project: str) -> str:
        """Self-improve the reasoning graph: merge duplicate nodes, drop dangling edges,
        resolve superseded decisions. Run periodically to keep memory clean."""
        return f"Improved '{project}': {engine.improve(project)}"

    @mcp.tool()
    def continuum_prune(project: str, keep: int = 60) -> str:
        """Active forgetting: trim low-salience reasoning so resume packages stay small.
        Verbatim source text is never deleted — only the reasoning index is trimmed."""
        return f"Pruned '{project}': {engine.prune(project, keep=keep)}"

    @mcp.tool()
    def continuum_distill(project: str) -> str:
        """Harvest durable lessons from a project into your cross-project memory (reusable
        by future projects)."""
        lessons = engine.distill(project)
        return "\n".join(f"• {l}" for l in lessons) if lessons else "(no lessons found)"

    @mcp.tool()
    def continuum_lessons() -> str:
        """Show your accumulated cross-project lessons (distilled insights)."""
        lessons = engine.lessons()
        return "\n".join(f"• {l}" for l in lessons) if lessons else "(no lessons yet)"

    @mcp.tool()
    def continuum_timeline(project: str) -> str:
        """Show the temporal evolution of the thinking — one line per checkpoint."""
        import datetime as _dt

        rows = engine.timeline(project)
        if not rows:
            return "(no checkpoints yet)"
        return "\n".join(
            f"{_dt.datetime.fromtimestamp(r['timestamp']).strftime('%Y-%m-%d %H:%M')}  "
            f"{r['checkpoint_id']}  decisions={r['decisions']} open_q={r['open_questions']}"
            for r in rows
        )

    @mcp.tool()
    def continuum_export(project: str, format: str = "md") -> str:
        """Export a saved project so the user can move it to a new chat or another AI platform.

        format='md' (default): a paste-anywhere document of the whole conversation-state —
        give it to the user to paste into a fresh chat on any provider.
        format='digest': a COMPRESSED view (recent checkpoints full, older summarized) — use for
        long projects (weeks/months) so it fits the next context window.
        format='json': a lossless bundle for backup or importing into another Continuum.
        """
        import json as _json

        fmt = format if format in ("md", "digest", "json", "transcript") else "md"
        data = engine.export(project, fmt=fmt)
        return data if isinstance(data, str) else _json.dumps(data)

    @mcp.tool()
    def continuum_import(project: str, bundle_json: str) -> str:
        """Import a project from a Continuum JSON bundle (produced by continuum_export json)."""
        import json as _json

        try:
            data = _json.loads(bundle_json)
        except Exception as e:
            return f"Could not parse bundle JSON: {e}"
        return f"Imported into '{project}': {engine.import_project(project, data)}"

    @mcp.tool()
    def continuum_context(project: str, current_chat: str = "", model: str = "claude") -> str:
        """Check how safe THIS conversation is right now: context-window fill, uncaptured drift,
        and a 'strength' score telling you whether to checkpoint before reasoning-state is lost.

        Pass the current conversation transcript as `current_chat` for an accurate gauge.
        """
        from continuum.engine.meter import render_gauge

        report = engine.context(project, live_text=current_chat, model=model)
        return render_gauge(report)

    @mcp.tool()
    def continuum_autopilot(project: str, current_chat: str = "", model: str = "claude",
                            threshold: int = 80) -> str:
        """Watch this conversation and, when the context window crosses `threshold`% (default 80),
        automatically hand back a paste-ready export so the user can switch to a fresh tab or
        another AI before reasoning-state is lost. Call this periodically in a long chat. Pass the
        current transcript as `current_chat`. Below the threshold it just reports health."""
        res = engine.autopilot(project, live_text=current_chat, model=model, threshold_pct=threshold)
        if res["switch_now"]:
            return (res["gauge"] + f"\n\n⚠ SWITCH NOW — {res['reason']}. "
                    "Give the user this portable export to paste into a new chat/provider:\n\n"
                    + res["export"])
        return res["gauge"] + "\n\n✓ healthy — keep working."

    @mcp.tool()
    def continuum_observe(project: str, turn: str, flush_tokens: int = 6000) -> str:
        """Auto-save mode: append THIS exchange (user+assistant turn) to a rolling session buffer;
        Continuum auto-checkpoints when the buffer fills. Call this after every exchange to save an
        entire session with no explicit "save this chat". Pass the latest turn's text as `turn`."""
        res = engine.observe(project, turn, flush_tokens=flush_tokens)
        if res["checkpointed"]:
            return (f"auto-checkpointed '{project}' (id={res['checkpoint_id']}, "
                    f"{res['decisions']} decisions). Buffer cleared; keep calling continuum_observe.")
        return (f"buffered {res['buffered_tokens']}/{res['flush_at']} tokens for '{project}' "
                "(will auto-checkpoint at the threshold).")

    @mcp.tool()
    def continuum_capture(project: str, source: str = "auto", path: str = "") -> str:
        """Import a conversation directly from another AI tool's session file (Grok / Claude Code /
        Codex / generic) — zero copy-paste. Give a `path`, or set `source` (grok/claude_code/codex)
        with no path to grab that tool's most recent session. Great for switching platforms."""
        try:
            info = engine.capture(project, path=path or None, source=source)
        except Exception as e:  # noqa: BLE001
            return f"capture failed: {e}"
        return (f"Captured '{project}' from {info['source']} ({info['turns']} turns, "
                f"{info['decisions']} decisions). Resume it anywhere with continuum_resume.")

    @mcp.tool()
    def continuum_ingest(project: str, text: str) -> str:
        """Add reference material (docs, notes, specs) as KNOWLEDGE to a project. On the Cognee
        backends this runs the full ingest → knowledge-graph pipeline. Use for source documents;
        use continuum_checkpoint for conversations (which also extract reasoning)."""
        return f"Ingested into '{project}': {engine.ingest(project, text)}"

    @mcp.tool()
    def continuum_mode() -> str:
        """Show which storage layers are active right now — backend, knowledge graph, semantic
        retrieval, managed LLM, reasoning extraction — so you know exactly what a checkpoint stores."""
        caps = engine.mode()
        return "\n".join(f"{k}: {v}" for k, v in caps.items())

    return mcp


_LANDING = (
    b"<!doctype html><meta charset=utf-8><title>Continuum MCP</title>"
    b"<div style='font:16px system-ui;max-width:640px;margin:60px auto;padding:0 20px'>"
    b"<h1>Continuum MCP endpoint</h1>"
    b"<p>This is a working <b>MCP server</b>, not a web page, which is why your "
    b"browser shows 406. Add it to your AI as a connector:</p>"
    b"<ol><li>Copy this page's URL (it ends in <code>/mcp</code>).</li>"
    b"<li>In Claude web, open Settings, then Connectors, then "
    b"<b>Add custom connector</b>, paste the URL, and Connect.</li>"
    b"<li>Then say: checkpoint this to project X with continuum.</li></ol>"
    b"<p>Tools include checkpoint, resume, capture, context, export, and more.</p></div>"
)


def _friendly_landing(app):
    """Show a help page to plain browsers; pass MCP clients (SSE Accept) straight through."""
    async def wrapped(scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            accept = headers.get(b"accept", b"").decode()
            path = scope.get("path", "")
            if scope.get("method") == "GET" and "text/event-stream" not in accept \
                    and path in ("", "/", "/mcp", "/sse"):
                await send({"type": "http.response.start", "status": 200,
                            "headers": [(b"content-type", b"text/html; charset=utf-8")]})
                await send({"type": "http.response.body", "body": _LANDING})
                return
        await app(scope, receive, send)

    return wrapped


def _token_middleware(app, token: str):
    """Wrap an ASGI app to require `Authorization: Bearer <token>` (skips /health)."""
    async def middleware(scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            auth = headers.get(b"authorization", b"").decode()
            if auth != f"Bearer {token}":
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
        await app(scope, receive, send)

    return middleware


def serve(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8771) -> None:
    mcp = build_server(remote=transport != "stdio")
    if transport == "stdio":
        mcp.run("stdio")
        return

    # Remote transports → serve the ASGI app (optionally token-gated) via uvicorn.
    import uvicorn

    mcp.settings.host = host
    mcp.settings.port = port
    app_factory = getattr(mcp, "streamable_http_app", None) if transport == "streamable-http" \
        else getattr(mcp, "sse_app", None)
    if app_factory is None:  # older SDK — fall back to built-in runner
        mcp.run(transport)
        return
    app = app_factory()
    app = _friendly_landing(app)  # browser-friendly help; MCP clients pass through
    token = os.getenv("CONTINUUM_TOKEN")
    if token:
        app = _token_middleware(app, token)
    uvicorn.run(app, host=host, port=port)
