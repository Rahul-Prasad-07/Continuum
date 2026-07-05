"""Provider-agnostic LLM client for structured (JSON) extraction.

Supports any OpenAI-compatible endpoint and Anthropic, selected by env vars. If no key (or
httpx) is available, `available()` is False and callers use the heuristic extractor instead —
so Continuum always runs.
"""

from __future__ import annotations

import json
import os
from typing import Optional


class LLMClient:
    def __init__(self) -> None:
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.openai_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
        try:
            import httpx  # noqa: F401

            self._httpx = True
        except Exception:
            self._httpx = False

    def available(self) -> bool:
        return self._httpx and bool(self.openai_key or self.anthropic_key)

    def complete_json(self, system: str, user: str, max_tokens: int = 4000) -> Optional[dict]:
        """Return a parsed JSON object, or None on failure."""
        if not self.available():
            return None
        import httpx

        try:
            if self.openai_key:
                r = httpx.post(
                    f"{self.openai_base}/chat/completions",
                    headers={"Authorization": f"Bearer {self.openai_key}"},
                    json={
                        "model": self.openai_model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "response_format": {"type": "json_object"},
                        "max_tokens": max_tokens,
                    },
                    timeout=120,
                )
                r.raise_for_status()
                return json.loads(r.json()["choices"][0]["message"]["content"])
            else:  # Anthropic
                r = httpx.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.anthropic_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": self.anthropic_model,
                        "max_tokens": max_tokens,
                        "system": system + "\nRespond with ONLY a valid JSON object.",
                        "messages": [{"role": "user", "content": user}],
                    },
                    timeout=120,
                )
                r.raise_for_status()
                text = r.json()["content"][0]["text"]
                return json.loads(text[text.index("{") : text.rindex("}") + 1])
        except Exception:
            return None
