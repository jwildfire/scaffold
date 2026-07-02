---
description: Regenerate and open the Claude config cheat sheet in Chrome
allowed-tools: Bash(python3:*), Bash(open:*)
---

Run the following shell command exactly:

```
_cs=$(find "$HOME/.claude/plugins" -path "*/scaffold/scripts/cheatsheet.py" 2>/dev/null | head -1); python3 "${_cs:-$HOME/.claude/cheatsheet.py}" && open -a "Google Chrome" "$HOME/.claude/cheatsheet.html"
```
