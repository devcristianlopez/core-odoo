# Multi-agent compatibility

`AGENTS.md` is the canonical instruction file. Other files are pointers so the
same project works across agents without duplicating rules.

| Agent | Rules file | Skills path |
|---|---|---|
| OpenCode | `AGENTS.md` | `.opencode/skills/`, `.claude/skills/`, `.agents/skills/` |
| Claude Code | `CLAUDE.md` (imports `AGENTS.md`) | `.claude/skills/` |
| Codex | `AGENTS.md` | `.agents/skills/` |
| Gemini CLI | `GEMINI.md` | per config |
| Cursor | `.cursor/rules/core-odoo.mdc` | per config |
| Aider | `CONVENTIONS.md` | not applicable |

MCP is configured for OpenCode (`opencode.json`), Claude Code (`.mcp.json`) and
Cursor (`.cursor/mcp.json`).

The canonical skills live in `skills/`. The repository contains symlinks:

```text
.opencode/skills/<name> -> ../../skills/<name>
.claude/skills/<name>   -> ../../skills/<name>
.agents/skills/<name>   -> ../../skills/<name>
```

After adding a skill, refresh the links:

```bash
./scripts/setup-agent-compat.sh
```

> `AGENTS.md` adds project conventions; it does not replace the system prompt or
> the agent definition. If they conflict, follow the agent/system instructions.
