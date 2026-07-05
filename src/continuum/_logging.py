"""Minimal logging setup — quiet by default, `CONTINUUM_LOG=DEBUG` to see internals."""

from __future__ import annotations

import logging
import os

_configured = False


def get_logger(name: str = "continuum") -> logging.Logger:
    global _configured
    if not _configured:
        level = os.getenv("CONTINUUM_LOG", "WARNING").upper()
        logging.basicConfig(
            level=getattr(logging, level, logging.WARNING),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        _configured = True
    return logging.getLogger(name)
