"""Configuration (env-driven, sensible defaults). Runs with zero config."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _home() -> Path:
    return Path(os.getenv("CONTINUUM_HOME", str(Path.home() / ".continuum")))


@dataclass
class Config:
    backend: str = os.getenv("CONTINUUM_BACKEND", "local")  # "local" | "cognee" | "cognee_cloud"
    db_path: str = str(_home() / "continuum.db")
    dataset: str = os.getenv("CONTINUUM_DATASET", "continuum")
    resume_budget_tokens: int = int(os.getenv("CONTINUUM_RESUME_BUDGET", "8000"))
    # Cognee Cloud platform (hosted): the managed API does ingestion, knowledge-graph build,
    # embeddings and LLM for you — so no local OpenAI key is needed for the Cognee side.
    cognee_api_url: str = field(default_factory=lambda: os.getenv("COGNEE_API_URL", ""))
    cognee_api_key: str = field(default_factory=lambda: os.getenv("COGNEE_API_KEY", ""))
    # Multi-tenant: every user's memory is isolated. Read at instantiation (not import) so
    # the CLI `--user` flag / env can take effect per-call.
    user: str = field(default_factory=lambda: os.getenv("CONTINUUM_USER", "default"))
    # Let Cognee's LLM extract a reasoning graph via cognify(graph_model=ReasoningGraph)
    # alongside our own extractor (best-effort enrichment).
    cognee_reasoning: bool = field(
        default_factory=lambda: os.getenv("CONTINUUM_COGNEE_REASONING", "1") == "1"
    )

    def ensure_home(self) -> "Config":
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        return self
