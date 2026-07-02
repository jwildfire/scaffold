---
description: Add a task to Apple Reminders (default) or a GitHub issue (--gh flag)
argument-hint: [--gh] <task description>
allowed-tools: Bash(osascript:*), Bash(git:*), Bash(gh issue create:*)
---

Create a todo for: $ARGUMENTS

## Step 1 — Parse destination

Check if $ARGUMENTS starts with `--gh` (with or without a space before the task).
- If `--gh` is present: destination is **GitHub issue**. Strip the flag; the remaining text is the task.
- Otherwise: destination is **Apple Reminders**.

## Step 2 — Gather context

Run:
```
git remote get-url origin 2>/dev/null | sed 's|.*[:/]\([^/]*/[^/]*\)\.git|\1|;s|.*[:/]\([^/]*/[^/]*\)$|\1|' || basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || echo "(no repo)"
echo "$CLAUDE_CODE_SESSION_ID"
```

If destination is GitHub issue and the repo is unclear or the working directory contains multiple repos, ask the user which repo before proceeding.

## Step 3 — Compose content

From the task description write:
- **title**: a single concise line (≤80 chars) capturing the core action
- **notes**: 2–4 sentences of context — what needs doing, why it matters, any relevant constraints — followed by:
  ```
  Repo: <repo>
  Session: <session-id>
  ```

## Step 4 — Create the todo

**Apple Reminders** (default):
```
osascript -e 'tell application "Reminders"
  if not (exists list "Agent Reminders") then make new list with properties {name:"Agent Reminders"}
  tell list "Agent Reminders" to make new reminder with properties {name:"TITLE", body:"NOTES"}
end tell'
```

**GitHub issue** (`--gh`):
```
gh issue create --repo REPO --title "TITLE" --body "NOTES"
```

## Step 5 — Confirm

Show the user: destination, title, and first sentence of notes.
