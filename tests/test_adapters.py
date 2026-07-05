"""Native session adapters — parse each platform's format from small synthetic fixtures."""

import json
import os
import tempfile

from continuum import adapters
from continuum import Continuum
from continuum.config import Config


def _w(tmp, name, lines):
    p = os.path.join(tmp, name)
    with open(p, "w") as f:
        for l in lines:
            f.write((json.dumps(l) if isinstance(l, dict) else l) + "\n")
    return p


def test_grok_format():
    with tempfile.TemporaryDirectory() as tmp:
        p = _w(tmp, "chat_history.jsonl", [
            {"type": "system", "content": "you are grok"},
            {"type": "user", "content": [{"type": "text", "text": "<user_query>\nuse Postgres, not Mongo\n</user_query>"}]},
            {"type": "assistant", "content": [{"type": "text", "text": "Agreed: Postgres for ACID."}]},
        ])
        assert adapters.detect(p) == "grok"
        t = adapters.parse_file(p, "grok")
        assert "User: use Postgres, not Mongo" in t
        assert "Assistant: Agreed: Postgres for ACID." in t
        assert "you are grok" not in t  # system dropped


def test_claude_code_format():
    with tempfile.TemporaryDirectory() as tmp:
        p = _w(tmp, "s.jsonl", [
            {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "reject Redis, lock race"}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "hmm"},
                {"type": "text", "text": "OK, JWT stateless."}]}},
            {"type": "file-history-snapshot", "snapshot": {}},
        ])
        assert adapters.detect(p) == "claude_code"
        t = adapters.parse_file(p, "auto")
        assert "User: reject Redis, lock race" in t
        assert "Assistant: OK, JWT stateless." in t
        assert "hmm" not in t  # thinking dropped


def test_codex_format():
    with tempfile.TemporaryDirectory() as tmp:
        p = _w(tmp, "rollout-x.jsonl", [
            {"type": "session_meta", "payload": {"id": "x"}},
            {"type": "response_item", "payload": {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "policy"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "use Stripe"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Stripe it is."}]}},
            {"type": "response_item", "payload": {"type": "reasoning", "content": []}},
        ])
        assert adapters.detect(p) == "codex"
        t = adapters.parse_file(p, "codex")
        assert "User: use Stripe" in t
        assert "Assistant: Stripe it is." in t
        assert "policy" not in t  # developer dropped


def test_capture_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        p = _w(tmp, "chat_history.jsonl", [
            {"type": "user", "content": "goal: low-ops auth. not Chargebee (lock-in)."},
            {"type": "assistant", "content": "Use Stripe + JWT."},
        ])
        c = Continuum(Config(backend="local", db_path=os.path.join(tmp, "c.db")))
        info = c.capture("switch", path=p, source="grok")
        assert info["turns"] == 2
        pkg = c.resume("switch")
        assert "Stripe" in pkg


def test_capture_requires_source_for_latest():
    with tempfile.TemporaryDirectory() as tmp:
        c = Continuum(Config(backend="local", db_path=os.path.join(tmp, "c.db")))
        try:
            c.capture("x", path=None, source="auto")
            assert False, "should require a source"
        except ValueError:
            pass
