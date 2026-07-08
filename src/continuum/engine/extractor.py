"""Extractor — conversation text -> verbatim chunks + WorkspaceState + ReasoningGraph.

Two modes:
- LLM (schema-constrained generation) when a key is configured — high quality.
- Heuristic (pattern matching) fallback — so Continuum always produces *something* to demo.
"""

from __future__ import annotations

import re

from continuum.llm import LLMClient
from continuum.memory.base import Chunk
from continuum.models import (
    Decision,
    ReasoningEdge,
    ReasoningGraph,
    ReasoningNode,
    RejectedOption,
    WorkspaceState,
)

_SYSTEM = (
    "You extract the REASONING STATE of a working conversation so it can be resumed later. "
    "Capture the goal, current task, decisions (with WHY), rejected alternatives (with why "
    "rejected), active hypotheses, constraints, open questions, blockers, next steps, code "
    "refs. Also produce a reasoning graph of typed nodes (Goal/Decision/Alternative/"
    "Hypothesis/Evidence/Constraint/OpenQuestion/Task/CodeRef/Insight) and edges "
    "(chosen_because/rejected_because/depends_on/supersedes/blocks/answers/...). "
    "Be faithful; do not invent."
)


def chunk_conversation(text: str, project: str) -> list[Chunk]:
    """Split into verbatim chunks (paragraph/turn granularity) — the source of truth."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [Chunk(project=project, index=i, text=p).with_id() for i, p in enumerate(parts)]


def extract(
    text: str, project: str, chunks: list[Chunk], llm: LLMClient
) -> tuple[WorkspaceState, ReasoningGraph]:
    if llm.available():
        result = _extract_llm(text, project, llm)
        if result:
            return result
    return _extract_heuristic(text, project, chunks)


# ---------------------------------------------------------------- LLM path
def _extract_llm(text: str, project: str, llm: LLMClient):
    schema_hint = (
        '{"workspace": {"goal": str, "current_task": str, '
        '"topics": [str], '
        '"decisions": [{"choice": str, "why": str, "rejected": [{"option": str, '
        '"why_rejected": str}]}], "active_hypotheses": [str], "constraints": [str], '
        '"open_questions": [str], "blocked_by": [str], "next_steps": [str], "code_refs": [str]}, '
        '"reasoning": {"nodes": [{"id": str, "name": str, "kind": str, "description": str, '
        '"status": str}], "edges": [{"source_node_id": str, "target_node_id": str, '
        '"relation": str, "description": str}]}}'
    )
    data = llm.complete_json(
        _SYSTEM,
        f"Conversation:\n\n{text[:24000]}\n\nReturn JSON exactly matching:\n{schema_hint}",
    )
    if not data:
        return None
    try:
        ws = WorkspaceState(project=project, **_coerce_workspace(data.get("workspace", {})))
        rg = ReasoningGraph.model_validate(data.get("reasoning", {"nodes": [], "edges": []}))
        return ws.with_id(), rg
    except Exception:
        return None


def _coerce_workspace(w: dict) -> dict:
    keys = [
        "goal", "current_task", "topics", "decisions", "active_hypotheses", "constraints",
        "open_questions", "blocked_by", "next_steps", "code_refs",
    ]
    return {k: w[k] for k in keys if k in w}


# ---------------------------------------------------------------- heuristic path
_SENT = re.compile(r"[^.!?\n]+[.!?]?")
_DECISION = re.compile(r"\b(let'?s use|we'?ll use|i'?ll use|use|go with|chose|decided|pick)\b", re.I)
_REJECT = re.compile(r"\b(not use|don'?t use|reject|avoid|instead of|rather than|too |won'?t)\b", re.I)
_WHY = re.compile(r"\b(because|since|as it|due to)\b", re.I)


def _extract_heuristic(text: str, project: str, chunks: list[Chunk]):
    sents = [s.strip() for s in _SENT.findall(text) if s.strip()]

    def ref_for(sent: str) -> str | None:
        for ch in chunks:
            if sent[:40] in ch.text:
                return ch.id
        return None

    decisions, questions, hypotheses, constraints, nodes, edges = [], [], [], [], [], []
    for s in sents:
        if s.endswith("?"):
            questions.append(s)
        if _DECISION.search(s) and not _REJECT.search(s):
            why = _extract_why(s)
            nid = f"decision:{_slug(s)}"
            decisions.append(Decision(choice=s, why=why, verbatim_ref=ref_for(s)))
            nodes.append(
                ReasoningNode(id=nid, name=_short(s), kind="Decision", description=s,
                              status="accepted", verbatim_ref=ref_for(s))
            )
        elif _REJECT.search(s):
            nid = f"alt:{_slug(s)}"
            nodes.append(
                ReasoningNode(id=nid, name=_short(s), kind="Alternative", description=s,
                              status="rejected", verbatim_ref=ref_for(s))
            )
            if decisions:
                edges.append(
                    ReasoningEdge(source_node_id=nid,
                                  target_node_id=f"decision:{_slug(decisions[-1].choice)}",
                                  relation="rejected_because", description=s)
                )
            if decisions and not decisions[-1].rejected:
                decisions[-1].rejected.append(RejectedOption(option=_short(s), why_rejected=s))
        if re.search(r"\b(must|should|need to|require|constraint|can'?t exceed)\b", s, re.I):
            constraints.append(s)
        if re.search(r"\b(maybe|might|hypothesis|try|test if|what if)\b", s, re.I):
            hypotheses.append(s)

    goal = next((s for s in sents if re.search(r"\b(build|design|goal|want to|trying to)\b", s, re.I)), "")
    ws = WorkspaceState(
        project=project, goal=goal[:200], current_task=(sents[-1] if sents else ""),
        topics=topics_of(text), decisions=decisions[:12], active_hypotheses=hypotheses[:8],
        constraints=constraints[:8], open_questions=questions[:8],
        next_steps=[], code_refs=re.findall(r"[\w/]+\.\w{1,4}(?::\d+)?", text)[:12],
    ).with_id()
    return ws, ReasoningGraph(nodes=nodes[:40], edges=edges[:60])


_TOPIC_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is", "it", "we", "i",
    "this", "that", "with", "was", "are", "you", "our", "not", "but", "can", "will", "have",
    "has", "how", "what", "why", "let", "lets", "use", "using", "now", "so", "if", "as", "be",
    "do", "does", "from", "they", "them", "your", "my", "me", "at", "by", "up", "out", "all",
    "one", "two", "get", "got", "make", "made", "want", "wants", "need", "needs", "should",
}


def topics_of(text: str, k: int = 8) -> list[str]:
    """Heuristic topic keywords for a conversation: the most frequent salient words + notable
    two-word phrases. Cheap, no LLM — enough to let `recall` find every checkpoint on a subject."""
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", text.lower())
             if w not in _TOPIC_STOP]
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    # notable adjacent bigrams (both words salient) — captures "dna mutation", "jwt auth"
    bigrams: dict[str, int] = {}
    for a, b in zip(words, words[1:]):
        bigrams[f"{a} {b}"] = bigrams.get(f"{a} {b}", 0) + 1
    top_bi = [p for p, c in sorted(bigrams.items(), key=lambda t: t[1], reverse=True) if c >= 2][:4]
    top_uni = [w for w, _ in sorted(freq.items(), key=lambda t: t[1], reverse=True)][:k]
    # keep phrases first (more specific), then fill with single words, deduped
    out: list[str] = []
    for t in top_bi + top_uni:
        if t not in out and not any(t in o for o in out):
            out.append(t)
    return out[:k]


def _extract_why(s: str) -> str:
    """Pull the reason clause after a 'why' marker, robust to which marker matched."""
    low = s.lower()
    for marker in ("because", "since", "due to", "as it"):
        i = low.find(marker)
        if i != -1:
            return s[i + len(marker):].strip(" ,.")
    return ""


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "x"


def _short(s: str, n: int = 60) -> str:
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"
