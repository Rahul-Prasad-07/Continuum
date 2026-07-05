"""End-to-end smoke test — checkpoint then resume, no external services."""

import os
import tempfile

from continuum import Continuum
from continuum.config import Config

SAMPLE = """User: I'm building auth. Goal: low-ops login.

Assistant: Let's use JWT with PKCE. It's stateless, no session store to run.

User: Let's not use Redis because the eviction policy caused a lock race last month.
Constraint: access tokens must expire in 15 minutes. Next step: build the refresh endpoint.
"""


def _engine(tmp):
    cfg = Config(backend="local", db_path=os.path.join(tmp, "c.db"))
    return Continuum(config=cfg)


def test_checkpoint_and_resume():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        ws = c.checkpoint("auth", SAMPLE)
        assert ws.checkpoint_id.startswith("cp-")
        assert c.status("auth")["has_state"] is True

        pkg = c.resume("auth", intent="build the refresh endpoint")
        assert "RESUME PACKAGE" in pkg
        assert "auth" in pkg
        # captured a decision and kept verbatim about Redis (the reasoning)
        assert "JWT" in pkg or "PKCE" in pkg
        assert "Redis" in pkg


def test_resume_empty_project():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        assert "Nothing to resume" in c.resume("nope")


def test_list_search_forget():
    with tempfile.TemporaryDirectory() as tmp:
        c = _engine(tmp)
        c.checkpoint("a", SAMPLE)
        c.checkpoint("b", "User: use Stripe because payouts are faster.")
        assert set(c.list_projects()) == {"a", "b"}
        assert any("Redis" in h for h in c.search("a", "redis"))
        c.forget("b")
        assert c.list_projects() == ["a"]
