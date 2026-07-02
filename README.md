# scaffold

Personal Claude Code plugin marketplace — commands for everyday use.

## Commands

| Command | Description |
|---|---|
| `/cheatsheet` | Regenerate and open a config overview (commands, skills, agents, permissions, context files) in Chrome |
| `/spawn <task>` | Spawn a background agent pre-loaded with context from the current session |

## Install

```bash
# 1. Add this repo as a marketplace
/plugin marketplace add jwildfire/scaffold

# 2. Install the plugin
/plugin install scaffold@jwildfire-scaffold
```

That's it. `/cheatsheet` finds its script automatically from the plugin install path — no manual file copying needed.

## Updating

```bash
/plugin update scaffold@jwildfire-scaffold
```

## Notes

- `cheatsheet.py` introspects `~/.claude/` (settings, commands, skills, agents, permissions, context files) and writes `~/.claude/cheatsheet.html`. The script is bundled at `plugins/scaffold/scripts/cheatsheet.py`.
- `spawn` works anywhere — no local dependencies.
