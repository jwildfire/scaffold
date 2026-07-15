# scaffold

Personal Claude Code plugin marketplace — commands for everyday use.

## Commands

| Command | Description |
|---|---|
| `/cheatsheet` | Regenerate and open a config overview (commands, skills, agents, permissions, context files) in Chrome |
| `/todo <task>` | Add a reminder to Apple Reminders with a summary, notes, repo name, and session ID |
| `/usage-report [timeframe] [project]` | Regenerate an HTML Claude Code usage report (working style, metrics, session diary) — defaults to the trailing 1 year across all projects |

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
- `spawn` moved to the obot.agent session framework as the `session-spawn` skill (2026-07-14) — it carries the session scratchpad heartbeat now, which is workspace machinery, not a general-purpose command.
- `usage-report` mines `~/.claude/projects/*/*.jsonl` session transcripts. `usage_report_scan.py` does the mechanical counting (sessions, tool-call volume, PR/commit mentions, daily activity); the command delegates PR classification and diary-writing to sub-agents, then renders `usage-report-template.html` with the computed data. Nothing leaves your machine.
