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

Skip anything the agent can rediscover by reading the code.

Then pick the spawn parameters deliberately — as the lead agent this is your call, so think strategically about model and effort per sub-agent rather than defaulting to your own:

- **Model** (`--model`): judgment-heavy, novel, or framework-shaping work → the strongest available model; well-specified template-following implementation → a mid-tier model (e.g. opus); light mechanical chores → a small fast model (e.g. sonnet or haiku). State the choice and why in your reply.
- **Effort** (`--effort`): inherit by default; raise it for hard verification or judgment work, lower it for mechanical tasks.
- **Name** (`-n`): short display name following the workspace's session-naming convention.
- **Permission mode**: siblings always spawn in auto mode — pass `--permission-mode auto` explicitly rather than relying on inheritance from the parent.

Then run:

`claude --bg --permission-mode auto --model <model> -n "<name>" "<briefing>\n\n---\n\nTASK: $ARGUMENTS"`

(add `--effort <level>` when deviating from the default)
