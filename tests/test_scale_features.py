"""Tests for the scalability layer: topic/intent recall, bounded/incremental/digest export,
autopilot auto-export, and session auto-capture (observe). Local backend only — no network."""

import json
import os
import tempfile
import time

from continuum import Continuum
from continuum.config import Config


def _engine(tmp, **cfg):
    c = Config(backend="local", db_path=os.path.join(tmp, "c.db"), **cfg)
    return Continuum(config=c)


def _claude_session(tmp, name, turns):
    """Write a synthetic Claude Code session .jsonl (list of (role, text))."""
    p = os.path.join(tmp, name)
    with open(p, "w") as f:
        for role, text in turns:
            f.write(json.dumps({
                "type": role,
                "message": {"role": role, "content": [{"type": "text", "text": text}]},
            }) + "\n")
    return p


# ---------------------------------------------------------------- topic/intent recall
def test_recall_gathers_the_right_subject_not_the_latest_checkpoint():
    """The DNA-mutation scenario: work on a subject weeks ago, then unrelated work, then recall.
    resume() would return the latest (infra) checkpoint; recall() must surface the DNA work."""
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        c.checkpoint("x", "We decided DNA mutation at codon position 42 changes protein folding. "
                          "We use a computational model because wet-lab is slow.")
        c.checkpoint("x", "DNA mutation rate depends on codon position. We must validate with "
                          "wet-lab data before publishing.")
        # unrelated later work — this becomes the LATEST checkpoint
        c.checkpoint("x", "We decided to use Docker for deployment because it is reproducible. "
                          "Infrastructure setup is complete.")

        latest = c.resume("x")                       # latest = infra
        assert "Docker" in latest or "Infrastructure" in latest.lower()

        recalled = c.recall("x", "dna mutation")     # subject = the old work
        assert "mutation" in recalled.lower()
        assert "codon" in recalled.lower()
        # recall pulls from multiple matching checkpoints, not just one
        assert "How this subject evolved" in recalled
        # only the 2 DNA checkpoints match — the unrelated Docker/infra one is excluded
        assert "2 of 3 checkpoints" in recalled
        assert "Docker" not in recalled


def test_recall_merges_decisions_across_checkpoints():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        c.checkpoint("x", "We use JWT for auth because it is stateless.")
        c.checkpoint("x", "We use Postgres for storage because it is relational. auth still JWT.")
        out = c.recall("x", "auth jwt storage")
        assert "Decisions so far" in out
        assert "jwt" in out.lower()


def test_recall_empty_project_is_graceful():
    with tempfile.TemporaryDirectory() as tmp:
        assert "Nothing to recall" in _engine(tmp).recall("nope", "anything")


def test_topics_are_extracted_on_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        ws = c.checkpoint("x", "DNA mutation research. DNA mutation affects folding. "
                              "Mutation rate matters. DNA is the subject here.")
        assert ws.topics, "expected heuristic topics to be populated"
        assert any("mutation" in t or "dna" in t for t in ws.topics)


# ---------------------------------------------------------------- bounded / incremental / digest
def test_bounded_markdown_export_respects_budget():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        # many small paragraphs → many verbatim chunks (realistic long conversation)
        big = "\n\n".join(
            f"User: point number {i} about alpha beta gamma delta topic." for i in range(200)
        )
        c.checkpoint("x", big)
        full = c.export("x", fmt="md")
        bounded = c.export("x", fmt="md", max_tokens=500)
        assert len(bounded) < len(full)
        # reasoning-state header is always kept; verbatim gets truncated to fit
        assert "CONTINUUM EXPORT" in bounded
        assert "truncated" in bounded.lower()


def test_incremental_bundle_only_newer_checkpoints():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        c.checkpoint("x", "First decision: use A because reasons.")
        cutoff = time.time()
        time.sleep(0.01)
        c.checkpoint("x", "Second decision: use B because other reasons.")
        full = c.export("x", fmt="json")
        delta = c.export("x", fmt="json", since=cutoff)
        assert full["counts"]["workspaces"] == 2
        assert delta["counts"]["workspaces"] == 1
        assert delta["incremental"] is True


def test_digest_compresses_long_history():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        for i in range(12):
            c.checkpoint("x", f"Checkpoint {i}: we decided option{i} because reason{i}. "
                             f"open question {i}?")
        digest = c.export("x", fmt="digest", max_tokens=2000)
        assert "CONTINUUM DIGEST" in digest
        assert "Earlier history" in digest      # old checkpoints summarized
        assert "Recent work" in digest          # recent kept in detail
        assert len(digest) // 4 <= 2200          # roughly within budget


# ---------------------------------------------------------------- autopilot (auto-export)
def test_autopilot_triggers_export_over_threshold():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        text = "We decided X because Y. " * 50
        c.checkpoint("x", text)
        # live text is small and already captured → low fill, low drift → healthy, no switch
        small = c.autopilot("x", live_text=text, model="claude", threshold_pct=80)
        assert small["switch_now"] is False
        assert small["export"] is None
        # huge live text pushes window fill over 80%
        big = c.autopilot("x", live_text="word " * 60000, model="claude", threshold_pct=80)
        assert big["switch_now"] is True
        assert big["export"] and "CONTINUUM EXPORT" in big["export"]


def test_autopilot_flags_uncaptured_project():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        # nothing checkpointed → action is checkpoint_now → switch_now regardless of fill
        res = c.autopilot("fresh", live_text="a little text", model="claude")
        assert res["switch_now"] is True


# ---------------------------------------------------------------- observe (session auto-capture)
def test_observe_buffers_then_auto_checkpoints():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        r1 = c.observe("x", "User: hi. Assistant: hello.", flush_tokens=200)
        assert r1["checkpointed"] is False
        assert r1["buffered_tokens"] > 0
        # push the buffer over the small threshold
        r2 = c.observe("x", "User: " + ("more text here " * 100), flush_tokens=200)
        assert r2["checkpointed"] is True
        assert r2["checkpoint_id"]
        # a checkpoint now exists and the buffer was cleared
        assert c.status("x")["checkpoints"] == 1


def test_observe_force_flushes_now():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        c.observe("x", "User: small note. Assistant: ok.", flush_tokens=100000)
        r = c.observe("x", "User: another. Assistant: done.", flush_tokens=100000, force=True)
        assert r["checkpointed"] is True
        assert c.status("x")["checkpoints"] == 1


# ---------------------------------------------------------------- autosave (hook-driven, debounced)
def test_autosave_reads_session_file_and_debounces():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        # a small session: below the debounce threshold → no checkpoint yet
        small = _claude_session(tmp, "s.jsonl", [
            ("user", "let's use JWT"), ("assistant", "ok, JWT it is because stateless"),
        ])
        r1 = c.autosave("proj", source="claude_code", path=small, min_new_tokens=1500)
        assert r1["saved"] is False
        assert c.status("proj")["checkpoints"] == 0

        # session grows past the threshold → exactly one checkpoint fires
        big = _claude_session(tmp, "s.jsonl", [
            ("user", "let's use JWT"), ("assistant", "ok, JWT it is because stateless"),
            ("user", "now add refresh " + "detail " * 800),
            ("assistant", "done, " + "reasoning " * 800),
        ])
        r2 = c.autosave("proj", source="claude_code", path=big, min_new_tokens=1500)
        assert r2["saved"] is True
        assert c.status("proj")["checkpoints"] == 1

        # no further growth → debounced, still one checkpoint (not spammed every call)
        r3 = c.autosave("proj", source="claude_code", path=big, min_new_tokens=1500)
        assert r3["saved"] is False
        assert c.status("proj")["checkpoints"] == 1


def test_autosave_empty_session_is_graceful():
    with tempfile.TemporaryDirectory() as tmp:
        empty = os.path.join(tmp, "empty.jsonl")
        open(empty, "w").close()
        r = _engine(tmp).autosave("proj", source="claude_code", path=empty)
        assert r["saved"] is False
        assert "empty" in r["reason"]
        assert _engine(tmp).status("proj")["checkpoints"] == 0
