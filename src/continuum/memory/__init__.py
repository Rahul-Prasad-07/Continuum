"""Memory backends (ports-and-adapters)."""

from continuum.memory.base import Chunk, MemoryBackend
from continuum.memory.local_backend import LocalBackend


def get_backend(kind: str, db_path: str, **kwargs) -> MemoryBackend:
    """Factory: pick a backend by name.
    'local'        — SQLite + keyword, zero-dep, runs anywhere.
    'cognee'       — local Cognee SDK (you configure the LLM/embeddings).
    'cognee_cloud' — hosted Cognee platform (managed LLM/embeddings; the complete superset).
    """
    if kind == "cognee_cloud":
        from continuum.memory.cognee_cloud_backend import CogneeCloudBackend

        return CogneeCloudBackend(db_path, **kwargs)
    if kind == "cognee":
        from continuum.memory.cognee_backend import CogneeBackend

        kwargs.pop("api_url", None)  # SDK backend doesn't take cloud kwargs
        kwargs.pop("api_key", None)
        return CogneeBackend(db_path, **kwargs)
    return LocalBackend(db_path)  # local ignores production kwargs


__all__ = ["Chunk", "MemoryBackend", "LocalBackend", "get_backend"]
