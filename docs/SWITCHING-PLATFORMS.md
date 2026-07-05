# Switching platforms losslessly, Claude to Grok to Codex to Claude web

The problem with moving a conversation between AIs: each tool stores chats in its **own** format,
and none of them carry your **reasoning** (decisions, rejected alternatives, open questions) across
the jump. You end up pasting a giant transcript and re-explaining yourself.

Continuum is the **neutral hub**. It reads any tool's native session store, normalizes it, keeps
verbatim + reasoning + (on Cognee) the knowledge graph, and re-emits it anywhere. You move
**state, not transcript**, small, exact, and provider-independent.

```
 Grok ─┐                                   ┌─► Claude Code   (MCP: "resume project X")
Claude ─┤  capture -> [ Continuum hub ]  resume/export ->  ├─► Claude web    (paste resume package)
 Codex ─┘   (native session files)                       └─► ChatGPT/Grok  (paste transcript/md)
```

---

## The two directions

### IN, `capture` (read another tool's session, zero copy-paste)
Continuum reads the session file directly and checkpoints it.

```bash
# newest session for a tool (auto-locates the file):
continuum capture -p work --from grok --latest
continuum capture -p work --from claude_code --latest
continuum capture -p work --from codex --latest

# a specific file (format auto-detected):
continuum capture -p work --file ~/.grok/sessions/<enc>/<id>/chat_history.jsonl
```
Supported natively (verified formats): **grok** (`chat_history.jsonl`), **claude_code**
(`~/.claude/projects/*/*.jsonl`), **codex** (`~/.codex/sessions/**/rollout-*.jsonl`), plus generic
**jsonl** and role-tagged **markdown**. System/developer/tool-noise turns are dropped; only the
real user/assistant conversation is kept.

Claude web has no local file, so from Claude web you either let the AI call `continuum_save`
(MCP) or copy the chat and `continuum checkpoint -`.

### OUT, `resume` / `export` (re-emit for the target)
Pick the artifact that fits where you're going:

| You're moving to... | Use | Why |
|---|---|---|
| Any MCP AI (Claude Code, Claude web, Grok, Codex) | say *"resume project X"* (`continuum_resume`) | no paste; the AI pulls state itself |
| A chat with no connector | `continuum resume -p X` -> paste | compact **reasoning-state** package (small) |
| A tool where you want the *whole* chat | `continuum export -p X -f transcript` | clean full conversation (grok-`export` style) |
| Another Continuum / a backup | `continuum export -p X -f json` | lossless bundle -> `continuum import` |

Three export levels, by how much you want to carry:
- **`resume`**, just the working state + rejected alternatives + the relevant verbatim (smallest).
- **`export -f md`**, reasoning-state doc + full verbatim (paste-anywhere).
- **`export -f transcript`**, the entire conversation, clean and role-tagged (grok-style).
- **`export -f json`**, everything, lossless, re-importable.

---

## Playbooks

### Grok -> Claude Code
```bash
continuum capture -p feature --from grok --latest      # pull the Grok session
# in Claude Code (MCP connected):  "resume continuum project feature"
```

### Claude Code -> Claude web (hit the context limit)
```bash
continuum capture -p feature --from claude_code --latest
continuum resume -p feature | pbcopy                    # paste into Claude web
```

### Codex -> Grok
```bash
continuum capture -p feature --from codex --latest
continuum export -p feature -f transcript | pbcopy      # or `resume` for just the state
```

### Round-trip / migrate a machine
```bash
continuum export -p feature -f json -o feature.json     # on machine A
continuum import -p feature feature.json                # on machine B
```

---

## Why this is lossless (and efficient)
- **Verbatim** is the source of truth, the exact words are stored, so `export -f transcript`
  reproduces the whole chat.
- **Reasoning-state** travels as structure (decisions + *why*, rejected + *why not*, open
  questions), the part Grok/Claude/Codex exports throw away.
- **Knowledge graph** (on `cognee_cloud`) travels as synthesized answers in resume.
- **Efficient:** you usually paste the *resume package* (a few KB), not a 200k-token transcript, 
  the target model's own context window stays free for new work. Check safety anytime with
  `continuum context -p X`.

## What's captured vs dropped (clean transcript)
| Kept | Dropped |
|---|---|
| user + assistant text | system / developer prompts |
| the actual conversation | tool call payloads, tool results, images |
| (re-extracted) decisions, rejected alternatives, open questions | model-internal "thinking" blocks |

Want tool calls included too? That's a planned `--include-tools` flag; today the transcript is the
clean conversation, which is what resumes best on another provider.

See also: [FEATURES.md](FEATURES.md) and [INTEGRATIONS.md](INTEGRATIONS.md).
