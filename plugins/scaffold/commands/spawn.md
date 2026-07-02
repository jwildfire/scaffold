---
description: Spawn a background claude agent with context from this session
allowed-tools: Bash(claude --bg:*)
---

Spawn a background agent to handle: $ARGUMENTS

First, write a concise context briefing (under ~300 words) capturing what this new agent needs from the current session:
- cwd and key file paths already touched
- Findings, decisions, or constraints established here
- Recent errors, command outputs, or state worth knowing
- What's already been tried and ruled out

Skip anything the agent can rediscover by reading the code. Then run:

`claude --bg "<briefing>\n\n---\n\nTASK: $ARGUMENTS"`
