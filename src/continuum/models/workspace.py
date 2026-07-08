"""WorkspaceState — the checkpoint snapshot.

A structured, resumable picture of "where the thinking is right now": goal, decisions and
*why*, rejected alternatives and *why*, open questions, constraints, next steps. This is the
"save game", not the "reached level 4" summary.
"""

from __future__ import annotations

import hashlib
import time
from typing import Optional

from pydantic import BaseModel, Field


class RejectedOption(BaseModel):
    option: str = Field(description="The alternative that was NOT chosen.")
    why_rejected: str = Field(description="The concrete reason it was rejected.")


class Decision(BaseModel):
    choice: str = Field(description="What was decided.")
    why: str = Field(description="Why this was chosen.")
    rejected: list[RejectedOption] = Field(default_factory=list)
    verbatim_ref: Optional[str] = Field(
        default=None, description="Chunk id of the exact source text for this decision."
    )


class WorkspaceState(BaseModel):
    """One checkpoint: the transient working state, made durable."""

    checkpoint_id: str = Field(default="")
    project: str = Field(description="Project/thread this belongs to.")
    timestamp: float = Field(default_factory=lambda: time.time())

    goal: str = Field(default="", description="The overarching objective.")
    current_task: str = Field(default="", description="What we were actively doing.")
    # Salient topics/entities this checkpoint is ABOUT (e.g. "dna mutation", "jwt auth"). Lets
    # `recall` gather every checkpoint on a subject across the whole history — not just the latest.
    topics: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    active_hypotheses: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    code_refs: list[str] = Field(default_factory=list)

    def with_id(self) -> "WorkspaceState":
        """Assign a deterministic, content-addressed checkpoint id (dedup + integrity)."""
        if not self.checkpoint_id:
            payload = self.model_dump_json(exclude={"checkpoint_id", "timestamp"})
            digest = hashlib.sha256(f"{self.project}:{payload}".encode()).hexdigest()[:16]
            self.checkpoint_id = f"cp-{digest}"
        return self
