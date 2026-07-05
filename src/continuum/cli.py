"""Continuum CLI — the universal surface (works with any AI tool via copy-paste)."""

from __future__ import annotations

import json
import os
import sys

import click

from continuum.engine import Continuum


@click.group()
@click.version_option("0.1.0", prog_name="continuum")
@click.option("--user", "-u", default=None,
              help="Tenant/user id — isolates memory per user. Env: CONTINUUM_USER")
def main(user: str | None) -> None:
    """Continuum — save & resume your AI thinking across sessions and providers."""
    if user:
        os.environ["CONTINUUM_USER"] = user  # picked up by Config (per-instantiation)


@main.command()
@click.argument("source", type=click.File("r"), default="-")
@click.option("--project", "-p", required=True, help="Project/thread name.")
def checkpoint(source, project: str) -> None:
    """Checkpoint a conversation (file or stdin) into resumable reasoning-state."""
    text = source.read()
    if not text.strip():
        click.echo("Nothing to checkpoint (empty input).", err=True)
        sys.exit(1)
    c = Continuum()
    ws = c.checkpoint(project, text)
    click.echo(
        click.style("✓ checkpoint saved", fg="green")
        + f"  project={project}  id={ws.checkpoint_id}  "
        f"decisions={len(ws.decisions)}  mode={c.status(project)['llm_mode']}"
    )


@main.command()
@click.option("--project", "-p", required=True, help="Project/thread name.")
@click.option("--intent", "-i", default="", help="What you're resuming toward.")
@click.option("--budget", "-b", default=None, type=int, help="Max tokens for the package.")
def resume(project: str, intent: str, budget: int | None) -> None:
    """Print a resume package — paste it into ANY new chat/provider to continue."""
    c = Continuum()
    click.echo(c.resume(project, intent=intent, budget_tokens=budget))


@main.command()
@click.option("--project", "-p", required=True)
def status(project: str) -> None:
    """Show saved state for a project."""
    c = Continuum()
    s = c.status(project)
    for k, v in s.items():
        click.echo(f"{k:>16}: {v}")


@main.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8770, type=int)
def serve(host: str, port: int) -> None:
    """Run the HTTP API (for browser extension / web / integrations)."""
    from continuum.surfaces.api import serve as _serve

    click.echo(f"Continuum API on http://{host}:{port}  (docs at /docs)")
    _serve(host, port)


@main.command()
@click.option("--transport", "-t", default="stdio",
              type=click.Choice(["stdio", "sse", "streamable-http"]))
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8771, type=int)
def mcp(transport: str, host: str, port: int) -> None:
    """Run the MCP server. stdio (local) or sse/streamable-http (remote connector).

    Remote example (add by URL in Claude web / Grok / etc.):
        continuum mcp -t streamable-http --host 0.0.0.0 --port 8771
    """
    from continuum.surfaces.mcp_server import serve as _serve

    if transport != "stdio":
        click.echo(f"Continuum MCP ({transport}) on http://{host}:{port}", err=True)
    _serve(transport, host, port)


@main.command(name="list")
def list_projects() -> None:
    """List all projects with saved state."""
    for p in Continuum().list_projects():
        click.echo(p)


@main.command()
@click.option("--project", "-p", required=True, help="Project to capture into.")
@click.option("--from", "-F", "source", default="auto",
              type=click.Choice(["auto", "grok", "claude_code", "codex", "jsonl", "markdown"]),
              help="Which tool's session format (auto-detects from a given file).")
@click.option("--file", "path", type=click.Path(exists=True), default=None,
              help="Path to the session file. Omit with --from to grab the latest session.")
@click.option("--latest", is_flag=True, help="Use the most recent session for --from (no --file needed).")
def capture(project: str, source: str, path: str | None, latest: bool) -> None:
    """Import a conversation straight from another AI tool's session store (zero copy-paste).

    Examples:
      continuum capture -p work --from grok --latest         # newest Grok session
      continuum capture -p work --file chat.jsonl            # auto-detect format
      continuum capture -p work --from codex --latest        # newest Codex rollout
    """
    if latest and not path:
        path = None  # engine resolves latest for `source`
    try:
        info = Continuum().capture(project, path=path, source=source)
    except (ValueError, FileNotFoundError) as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    click.echo(
        click.style("✓ captured", fg="green")
        + f"  project={project}  source={info['source']}  turns={info['turns']}  "
        f"id={info['checkpoint_id']}  decisions={info['decisions']}\n  from: {info['path']}"
    )


@main.command()
@click.argument("source", type=click.File("r"), default="-")
@click.option("--project", "-p", required=True, help="Project to add the knowledge to.")
def ingest(source, project: str) -> None:
    """Ingest reference docs/notes as knowledge (verbatim + knowledge graph on Cognee backends).

    Unlike `checkpoint`, this does not extract reasoning — it's source material, not a conversation.
    """
    text = source.read()
    if not text.strip():
        click.echo("Nothing to ingest (empty input).", err=True)
        sys.exit(1)
    click.echo(f"ingested into {project}: {Continuum().ingest(project, text)}")


@main.command()
def mode() -> None:
    """Show which storage layers are active right now (backend, knowledge graph, semantic, LLM)."""
    for k, v in Continuum().mode().items():
        click.echo(f"{k:>22}: {v}")


@main.command()
@click.option("--project", "-p", required=True)
@click.argument("query")
def search(project: str, query: str) -> None:
    """Search a project's memory for a query."""
    for hit in Continuum().search(project, query):
        click.echo(f"- {hit}")


@main.command()
@click.option("--project", "-p", required=True)
@click.confirmation_option(prompt="Permanently delete this project's memory?")
def forget(project: str) -> None:
    """Permanently delete a project's memory."""
    click.echo(f"forgot {project}: {Continuum().forget(project)}")


@main.command()
@click.option("--project", "-p", required=True)
def improve(project: str) -> None:
    """Self-improve the reasoning graph (dedup, drop dangling edges, resolve superseded)."""
    click.echo(f"improved {project}: {Continuum().improve(project)}")


@main.command()
@click.option("--project", "-p", required=True)
@click.option("--keep", default=60, type=int, help="Max nodes to keep.")
@click.option("--min-score", default=0.5, type=float, help="Min salience to keep.")
def prune(project: str, keep: int, min_score: float) -> None:
    """Active forgetting — trim low-salience reasoning (verbatim source is kept)."""
    click.echo(f"pruned {project}: {Continuum().prune(project, keep=keep, min_score=min_score)}")


@main.command()
@click.option("--project", "-p", required=True)
def distill(project: str) -> None:
    """Harvest durable lessons from a project into your cross-project memory."""
    for l in Continuum().distill(project):
        click.echo(f"• {l}")


@main.command()
def lessons() -> None:
    """Show your accumulated cross-project lessons."""
    for l in Continuum().lessons():
        click.echo(f"• {l}")


@main.command()
@click.option("--project", "-p", required=True)
@click.option("--format", "-f", "fmt", default="json",
              type=click.Choice(["json", "md", "transcript"]),
              help="json = lossless bundle; md = reasoning-state doc; transcript = full conversation.")
@click.option("--out", "-o", type=click.File("w"), default="-",
              help="Write to a file (default: stdout).")
def export(project: str, fmt: str, out) -> None:
    """Export a project to move it to a new chat, another platform, or a backup."""
    data = Continuum().export(project, fmt=fmt)
    text = data if isinstance(data, str) else json.dumps(data, indent=2)
    out.write(text + ("\n" if not text.endswith("\n") else ""))


@main.command(name="import")
@click.option("--project", "-p", required=True, help="Project name to import INTO.")
@click.argument("source", type=click.File("r"), default="-")
def import_(project: str, source) -> None:
    """Import a bundle (from `continuum export`) into a project. Reads file or stdin."""
    try:
        data = json.load(source)
    except json.JSONDecodeError as e:
        click.echo(f"Not a valid JSON bundle: {e}", err=True)
        sys.exit(1)
    stats = Continuum().import_project(project, data)
    click.echo(click.style("✓ imported", fg="green") + f"  {stats}")


@main.command()
@click.option("--project", "-p", required=True)
@click.option("--text", "-t", "source", type=click.File("r"), default=None,
              help="Current conversation transcript to measure (file or '-' for stdin).")
@click.option("--model", "-m", default="", help="Model family for window size (claude/gpt/gemini/grok).")
@click.option("--window", "-w", default=0, type=int, help="Override context window (tokens).")
def context(project: str, source, model: str, window: int) -> None:
    """Show context-window health & reasoning 'strength' — when to checkpoint before losing state."""
    from continuum.engine.meter import render_gauge

    live = source.read() if source else ""
    report = Continuum().context(project, live_text=live, model=model, window=window)
    click.echo(render_gauge(report))


@main.command()
@click.option("--project", "-p", required=True)
def timeline(project: str) -> None:
    """Show the temporal evolution of the thinking (one row per checkpoint)."""
    import datetime as _dt

    for row in Continuum().timeline(project):
        ts = _dt.datetime.fromtimestamp(row["timestamp"]).strftime("%Y-%m-%d %H:%M")
        click.echo(
            f"{ts}  {row['checkpoint_id']}  "
            f"decisions={row['decisions']} open_q={row['open_questions']}  "
            f"task={row['current_task'][:60]}"
        )


if __name__ == "__main__":
    main()
