"""Context-window strength meter — "how safe is my reasoning right now?"

Users asked to *see* the health of the live conversation: how full the model's context window
is, and how much of the current thinking has NOT been checkpointed yet (drift). When either
gets high, the provider will start compressing/dropping and reasoning-state is destroyed — so
this is the signal that tells you (or an agent) *when* to checkpoint, before it's too late.

No LLM needed; a rough chars/4 token model is enough for a gauge.
"""

from __future__ import annotations

from continuum.memory.base import MemoryBackend

# Rough usable context windows per provider family (tokens). Used only for the "how full" gauge.
MODEL_WINDOWS = {
    "claude": 200_000,
    "gpt": 128_000,
    "gpt-4o": 128_000,
    "o1": 200_000,
    "gemini": 1_000_000,
    "grok": 131_072,
    "default": 200_000,
}


def _toks(s: str) -> int:
    return max(0, len(s) // 4)  # tokens ≈ chars / 4


def window_for(model: str | None) -> int:
    if not model:
        return MODEL_WINDOWS["default"]
    m = model.lower()
    for key, win in MODEL_WINDOWS.items():
        if key in m:
            return win
    return MODEL_WINDOWS["default"]


def _zone(pct: float) -> str:
    if pct >= 90:
        return "red"
    if pct >= 75:
        return "orange"
    if pct >= 50:
        return "yellow"
    return "green"


def context_report(
    backend: MemoryBackend,
    scoped_project: str,
    display_name: str,
    live_text: str = "",
    window: int = 200_000,
) -> dict:
    """Gauge the live conversation's safety.

    live_text : the CURRENT conversation transcript (paste it in to measure real fill).
    window    : the model's usable context window in tokens.
    """
    live = _toks(live_text)
    window = max(1, window)
    window_used_pct = round(100 * live / window, 1)

    ws = backend.latest_workspace(scoped_project)
    graph = backend.get_reasoning(scoped_project)
    captured = ws is not None
    stored_toks = sum(_toks(c.text) for c in backend.all_chunks(scoped_project))

    # Drift = live reasoning that exceeds what's already checkpointed (uncaptured risk).
    unsaved = max(0, live - stored_toks)
    unsaved_pct = round(100 * unsaved / live, 1) if live else 0.0

    # Strength (0..100): how safe your reasoning-state is from loss right now.
    strength = 100.0
    strength -= window_used_pct                 # fuller window → weaker (compression risk)
    if not captured:
        strength -= 30                          # no safety net at all
    strength -= min(40.0, unsaved_pct * 0.4)    # drift → weaker
    strength = max(0, round(strength))

    if not captured or window_used_pct >= 75 or unsaved_pct >= 50:
        recommendation = "checkpoint now — you are close to losing reasoning-state"
        action = "checkpoint_now"
    elif window_used_pct >= 50 or unsaved_pct >= 30:
        recommendation = "checkpoint soon — drift is building"
        action = "checkpoint_soon"
    else:
        recommendation = "healthy — reasoning-state is safe"
        action = "healthy"

    return {
        "project": display_name,
        "live_tokens": live,
        "window_tokens": window,
        "window_used_pct": window_used_pct,
        "zone": _zone(window_used_pct),
        "captured": captured,
        "checkpoint_id": ws.checkpoint_id if ws else None,
        "stored_tokens": stored_toks,
        "unsaved_tokens": unsaved,
        "unsaved_pct": unsaved_pct,
        "reasoning_nodes": len(graph.nodes),
        "decisions": len(ws.decisions) if ws else 0,
        "open_questions": len(ws.open_questions) if ws else 0,
        "strength": strength,
        "recommendation": recommendation,
        "action": action,
    }


def render_gauge(report: dict) -> str:
    """A compact text gauge for CLI/MCP surfaces."""

    def bar(pct: float, width: int = 24) -> str:
        fill = int(round(width * min(100.0, pct) / 100))
        return "█" * fill + "░" * (width - fill)

    zone_mark = {"green": "🟢", "yellow": "🟡", "orange": "🟠", "red": "🔴"}
    lines = [
        f"Continuum context health — project: {report['project']}",
        f"  window  [{bar(report['window_used_pct'])}] "
        f"{report['window_used_pct']}%  {zone_mark.get(report['zone'], '')} ({report['zone']})",
        f"  saved   {'yes' if report['captured'] else 'NO — nothing checkpointed'}"
        + (f"  id={report['checkpoint_id']}" if report['captured'] else ""),
        f"  drift   [{bar(report['unsaved_pct'])}] {report['unsaved_pct']}% uncaptured "
        f"({report['unsaved_tokens']} tok)",
        f"  strength {report['strength']}/100",
        f"  → {report['recommendation']}",
    ]
    return "\n".join(lines)
