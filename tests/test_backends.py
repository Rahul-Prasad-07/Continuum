"""Backend capability + new-verb tests (local backend only — no network)."""

import os
import tempfile

from continuum import Continuum
from continuum.config import Config
from continuum.memory import get_backend


def _engine(tmp, **cfg):
    c = Config(backend="local", db_path=os.path.join(tmp, "c.db"), **cfg)
    return Continuum(config=c)


def test_local_capabilities_are_honest():
    with tempfile.TemporaryDirectory() as tmp:
        caps = _engine(tmp).mode()
        assert caps["backend"] == "local"
        assert caps["reasoning_graph"] is True
        assert caps["knowledge_graph"] is False        # local has no KG
        assert caps["semantic_retrieval"] is False      # keyword only
        assert caps["reasoning_extraction"] in ("llm", "heuristic")


def test_local_graph_answer_is_none():
    with tempfile.TemporaryDirectory() as tmp:
        b = get_backend("local", os.path.join(tmp, "c.db"))
        assert b.graph_answer("p", "anything") is None


def test_status_includes_capabilities():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        c.checkpoint("p", "User: use X because Y. next: ship.")
        s = c.status("p")
        assert "capabilities" in s
        assert s["capabilities"]["backend"] == "local"


def test_ingest_stores_knowledge_without_reasoning():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        stats = c.ingest("docs", "Stripe supports idempotency keys for safe webhook retries.")
        assert stats["chunks"] >= 1
        # ingested text is searchable as verbatim
        assert any("idempotency" in h.lower() for h in c.search("docs", "idempotency"))


def test_cognee_cloud_backend_offline_is_defensive():
    # No api_url/api_key → backend is "not live" and must not raise; falls back to local.
    with tempfile.TemporaryDirectory() as tmp:
        b = get_backend("cognee_cloud", os.path.join(tmp, "c.db"), dataset="continuum")
        caps = b.capabilities()
        assert caps["backend"] == "cognee_cloud"
        assert caps["connected"] is False
        assert b.graph_answer("p", "q") is None      # no network call when offline
