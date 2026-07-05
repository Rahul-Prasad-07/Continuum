"""Portability + context-meter tests — export/import round-trip and the strength gauge."""

import os
import tempfile

from continuum import Continuum
from continuum.config import Config

SAMPLE = """User: building billing. Goal: low ops, no vendor lock-in.

Assistant: use Stripe with stateless webhooks.

User: let's not use Chargebee because of pricing lock-in. Next: webhook retry with idempotency.
"""


def _engine(tmp, user="default"):
    cfg = Config(backend="local", db_path=os.path.join(tmp, "c.db"), user=user)
    return Continuum(config=cfg)


def test_export_md_is_paste_ready():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        c.checkpoint("billing", SAMPLE)
        md = c.export("billing", fmt="md")
        assert "CONTINUUM EXPORT" in md
        assert "Chargebee" in md  # rejected alternative preserved
        assert "Full conversation" in md


def test_export_import_roundtrip_across_users():
    with tempfile.TemporaryDirectory() as tmp:
        alice = _engine(tmp, user="alice")
        alice.checkpoint("billing", SAMPLE)
        bundle = alice.export("billing", fmt="json")
        assert bundle["continuum_bundle"] == 1
        assert bundle["counts"]["verbatim"] >= 1

        bob = _engine(tmp, user="bob")
        assert bob.list_projects() == []
        stats = bob.import_project("copy", bundle)
        assert stats["imported_verbatim"] >= 1
        assert bob.list_projects() == ["copy"]
        # reasoning survived the trip
        pkg = bob.resume("copy", intent="webhook retry")
        assert "Chargebee" in pkg


def test_import_rejects_non_bundle():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        try:
            c.import_project("x", {"not": "a bundle"})
            assert False, "should have raised"
        except ValueError:
            pass


def test_context_meter_flags_drift():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        c.checkpoint("billing", SAMPLE)
        # small live text ≈ what's saved → healthy
        healthy = c.context("billing", live_text=SAMPLE, model="claude")
        assert healthy["captured"] is True
        assert healthy["action"] in ("healthy", "checkpoint_soon")
        # large uncaptured live text → should urge a checkpoint
        big = SAMPLE + ("reasoning " * 5000)
        risky = c.context("billing", live_text=big, model="claude")
        assert risky["unsaved_pct"] > 50
        assert risky["action"] == "checkpoint_now"
        assert risky["strength"] < healthy["strength"]


def test_context_meter_no_state():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        rep = c.context("empty", live_text="hello", model="gpt")
        assert rep["captured"] is False
        assert rep["action"] == "checkpoint_now"
