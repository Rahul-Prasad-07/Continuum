#!/usr/bin/env python3
"""Claude Code Stop-hook: auto-checkpoint the CURRENT session into Continuum after every turn.

Claude Code runs a `Stop` hook when the assistant finishes a response (i.e. once per turn). It
passes JSON on stdin including `transcript_path` (the exact session .jsonl) and `cwd`. This script
hands that session to Continuum, which checkpoints it — debounced, so only real new content
triggers a checkpoint. No model cooperation needed: this is the genuinely-automatic autosave.

Install (once): add to ~/.claude/settings.json (or a project .claude/settings.json):

    {
      "hooks": {
        "Stop": [
          { "hooks": [
              { "type": "command",
                "command": "python3 /ABS/PATH/deploy/hooks/continuum_autosave.py" }
          ] }
        ]
      }
    }

Project name = $CONTINUUM_PROJECT, else the working-directory name (so each repo autosaves to its
own Continuum project automatically). Always exits 0 so it can never block Claude Code.
"""
from __future__ import annotations

import json
import os
import sys


def main() -> int:
    data = {}
    try:
        raw = sys.stdin.read()
        if raw.strip():
            data = json.loads(raw)
    except Exception:
        data = {}

    cwd = data.get("cwd") or os.getcwd()
    project = os.getenv("CONTINUUM_PROJECT") or os.path.basename(cwd) or "session"
    path = data.get("transcript_path")  # the exact current session; else Continuum finds the latest

    try:
        from continuum import Continuum

        res = Continuum().autosave(project, source="claude_code", path=path)
        # Keep hook output quiet unless something was saved (visible in `claude --debug`).
        if res.get("saved"):
            print(f"continuum: autosaved {project} ({res['checkpoint_id']})", file=sys.stderr)
    except Exception as e:  # never break the session on an autosave error
        print(f"continuum autosave skipped: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
