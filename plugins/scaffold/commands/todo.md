---
description: Add a task to Apple Reminders with session context (repo + session ID)
argument-hint: <task description>
allowed-tools: Bash(osascript:*), Bash(git:*)
---

Create an Apple Reminder for this task: $ARGUMENTS

Steps:
1. Run these shell commands to gather context:
   ```
   git remote get-url origin 2>/dev/null | sed 's|.*[:/]\([^/]*/[^/]*\)\.git|\1|;s|.*[:/]\([^/]*/[^/]*\)$|\1|' || basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || echo "(no repo)"
   echo "$CLAUDE_CODE_SESSION_ID"
   ```

2. From the task description, write:
   - **title**: a single concise line (≤80 chars) capturing the core action
   - **notes**: 2–4 sentences of context — what needs doing, why it matters, any relevant constraints — followed by two metadata lines:
     ```
     Repo: <repo>
     Session: <session-id>
     ```

3. Create the reminder with this osascript (substitute TITLE and NOTES). This also creates the list if it doesn't exist yet:
   ```
   osascript -e 'tell application "Reminders"
     if not (exists list "Agent Reminders") then make new list with properties {name:"Agent Reminders"}
     tell list "Agent Reminders" to make new reminder with properties {name:"TITLE", body:"NOTES"}
   end tell'
   ```

4. Confirm to the user: show the title and the first line of notes.
