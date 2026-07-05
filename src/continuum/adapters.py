"""Native session adapters — read each AI tool's on-disk conversation store and normalize it to
one canonical transcript, so switching platforms needs zero copy-paste.

Continuum becomes the neutral hub: `capture` reads a Grok / Claude Code / Codex / generic session
file, turns it into `User: … / Assistant: …` text, and hands it to `checkpoint` (which extracts
reasoning + stores verbatim + builds the knowledge graph on the Cognee backends). From there you
`resume` in any other tool. No provider lock-in, nothing lost.

Formats (verified on disk):
  - grok        ~/.grok/sessions/<enc-cwd>/<id>/chat_history.jsonl   {type, content}
  - claude_code ~/.claude/projects/<enc>/<uuid>.jsonl                {type, message:{role,content[]}}
  - codex       ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl         {type:response_item, payload:{type:message,role,content[]}}
  - jsonl/md    generic role-tagged fallbacks
"""

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

# roles we keep in a portable transcript (drop system/developer/tool noise)
_KEEP = {"user", "assistant"}


def _text_from(content) -> str:
    """Pull plain text out of a string or a list of content blocks (Anthropic/OpenAI/Grok shapes)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for b in content:
            if not isinstance(b, dict):
                parts.append(str(b))
                continue
            t = b.get("type")
            if t in (None, "text", "input_text", "output_text"):
                if b.get("text"):
                    parts.append(str(b["text"]))
            # skip thinking / tool_use / tool_result / images for a clean transcript
        return "\n".join(parts).strip()
    return ""


def _clean_user(text: str) -> str:
    """Strip environment wrappers some tools inject into user turns."""
    m = re.search(r"<user_query>\s*(.*?)\s*</user_query>", text, re.S)
    if m:
        return m.group(1).strip()
    low = text.lstrip().lower()
    if low.startswith("<user_info") or low.startswith("<environment") or low.startswith("<system"):
        return ""  # pure environment/system context, not a real user message
    return text.strip()


def _assemble(turns: list[tuple[str, str]]) -> str:
    """turns = [(role, text)] → canonical `Role: text` transcript the extractor understands."""
    out = []
    for role, text in turns:
        text = text.strip()
        if not text:
            continue
        label = "User" if role == "user" else "Assistant"
        out.append(f"{label}: {text}")
    return "\n\n".join(out)


# ---------------------------------------------------------------- per-platform parsers
def from_grok(path: str) -> str:
    turns = []
    for line in _lines(path):
        d = _loads(line)
        if not d:
            continue
        role = d.get("type")
        if role not in _KEEP:
            continue
        text = _text_from(d.get("content"))
        if role == "user":
            text = _clean_user(text)
        turns.append((role, text))
    return _assemble(turns)


def from_claude_code(path: str) -> str:
    turns = []
    for line in _lines(path):
        d = _loads(line)
        if not d or d.get("type") not in _KEEP:
            continue
        msg = d.get("message") or {}
        role = msg.get("role") or d.get("type")
        if role not in _KEEP:
            continue
        text = _text_from(msg.get("content"))
        if role == "user":
            text = _clean_user(text)
        turns.append((role, text))
    return _assemble(turns)


def from_codex(path: str) -> str:
    turns = []
    for line in _lines(path):
        d = _loads(line)
        if not d or d.get("type") != "response_item":
            continue
        p = d.get("payload") or {}
        if p.get("type") != "message":
            continue
        role = p.get("role")
        if role not in _KEEP:
            continue
        text = _text_from(p.get("content"))
        if role == "user":
            text = _clean_user(text)
        turns.append((role, text))
    return _assemble(turns)


def from_generic_jsonl(path: str) -> str:
    """Best-effort: any JSONL with a role-ish key and a content/text key."""
    turns = []
    for line in _lines(path):
        d = _loads(line)
        if not d:
            continue
        role = d.get("role") or d.get("type") or d.get("sender")
        if role not in _KEEP:
            continue
        text = _text_from(d.get("content") or d.get("text") or d.get("message"))
        turns.append((role, _clean_user(text) if role == "user" else text))
    return _assemble(turns)


def from_markdown(path: str) -> str:
    """A role-tagged markdown transcript (## User / ## Assistant, or 'User:' lines) passes through."""
    return Path(path).read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- detection + discovery
_PARSERS = {
    "grok": from_grok,
    "claude_code": from_claude_code,
    "claude": from_claude_code,
    "codex": from_codex,
    "jsonl": from_generic_jsonl,
    "markdown": from_markdown,
    "md": from_markdown,
}


def detect(path: str) -> str:
    """Sniff the format from the first record."""
    p = str(path)
    if p.endswith((".md", ".markdown", ".txt")):
        return "markdown"
    for line in _lines(path):
        d = _loads(line)
        if not d:
            continue
        if d.get("type") == "response_item" or (isinstance(d.get("payload"), dict)):
            return "codex"
        if isinstance(d.get("message"), dict) and "content" in d["message"]:
            return "claude_code"
        if set(d.keys()) <= {"type", "content"} and "content" in d:
            return "grok"
        return "jsonl"
    return "markdown"


def parse_file(path: str, source: str = "auto") -> str:
    """Parse a session file into a canonical transcript. source='auto' detects the format."""
    src = detect(path) if source in ("auto", "", None) else source
    parser = _PARSERS.get(src, from_generic_jsonl)
    return parser(str(path))


_SESSION_GLOBS = {
    "grok": ["~/.grok/sessions/*/*/chat_history.jsonl"],
    "claude_code": ["~/.claude/projects/*/*.jsonl"],
    "claude": ["~/.claude/projects/*/*.jsonl"],
    "codex": ["~/.codex/sessions/*/*/*/rollout-*.jsonl", "~/.codex/archived_sessions/rollout-*.jsonl"],
}


def latest_session(source: str) -> str | None:
    """Find the most-recently-modified session file for a platform (so `capture --latest` just works)."""
    files = []
    for pat in _SESSION_GLOBS.get(source, []):
        files += glob.glob(os.path.expanduser(pat))
    return max(files, key=os.path.getmtime) if files else None


def list_sessions(source: str, limit: int = 10) -> list[str]:
    files = []
    for pat in _SESSION_GLOBS.get(source, []):
        files += glob.glob(os.path.expanduser(pat))
    return sorted(files, key=os.path.getmtime, reverse=True)[:limit]


# ---------------------------------------------------------------- io helpers
def _lines(path: str):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line:
                yield line


def _loads(line: str):
    try:
        return json.loads(line)
    except Exception:
        return None
