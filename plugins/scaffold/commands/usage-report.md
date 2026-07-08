---
description: Regenerate an HTML Claude Code usage report (working style, metrics, session diary) for a timeframe and project scope
argument-hint: [timeframe] [project]
allowed-tools: Bash(python3:*), Bash(find:*), Bash(open:*), Bash(git:*)
---

Generate a self-contained HTML usage report summarizing Claude Code activity, for: $ARGUMENTS

## Step 1 — Parse arguments

Two independent, optional values may appear in $ARGUMENTS, in either order, as plain
words or as `--timeframe`/`--project` flags:

- **timeframe** — one of: `<N>d`, `<N>w`, `<N>m`, `<N>y` (e.g. `90d`, `6m`, `1y`), an
  ISO date (`2026-01-01`, meaning "since that date"), or `all`. **Default: `1y`.**
- **project** — a substring to match against a repo/project name (e.g. `gsm.roadmap`,
  `gsm.kri`), or `all` for every project with local session history. **Default: `all`.**

A bare word matching the timeframe patterns above is the timeframe; anything else is
the project filter. If both are ambiguous, ask the user rather than guessing.

## Step 2 — Locate the bundled script and template

```
_root=$(find "$HOME/.claude/plugins" -path "*/scaffold/scripts/usage_report_scan.py" 2>/dev/null | head -1)
_root="${_root%/usage_report_scan.py}"
if [ -z "$_root" ]; then
  _root="$(git rev-parse --show-toplevel 2>/dev/null)/plugins/scaffold/scripts"
fi
echo "$_root"
```

You now have `$_root/usage_report_scan.py` and `$_root/usage-report-template.html`.

## Step 3 — Run the mechanical scan

```
python3 "$_root/usage_report_scan.py" --since <timeframe> --project <project> > /tmp/usage-report-scan.json
```

Read the resulting JSON. It gives you, **already computed and trustworthy**:
- `totals.session_count`, `totals.days_active`, `totals.date_span`
- `totals.daily_counts` — sessions per calendar day (use directly for the daily-activity chart)
- `totals.tool_counts` / `totals.tool_buckets` — exact tool-call tallies (use directly for the tool-composition chart)
- `totals.subagents` — sub-agent spawns by type (use directly for the sub-agent mini-list)
- `totals.skills` — Skill-tool invocations by skill name
- per-project: `pr_urls` (raw `owner/repo#N` mentions), `pr_create_repos` (repos where a `gh pr create` command was actually run), `commit_messages` (best-effort), and the list of session files/dates in scope

If `totals.session_count` is 0, tell the user no sessions matched and stop — do not
fabricate a report.

**Important caveat about `pr_urls`:** this is a raw regex match over everything Claude
ever saw in a tool result, including PR-sweep queries (`is:pr involves:@me`) and web
searches that can surface dozens of unrelated public-repo URLs. **Do not use `pr_urls`
counts directly as "PRs opened/reviewed."** Use it only as a candidate list to check
during Step 4.

## Step 4 — Classify PR activity and write the diary (delegate to sub-agents)

For each project in the scan JSON with a non-trivial session count, spawn a
sub-agent (send them all in one message so they run in parallel) with:
- The list of session files (path = `~/.claude/projects/<dir>/<file>`) and their dates
- The project's raw `pr_urls` and `pr_create_repos` from the scan
- Instructions to: mine the sessions efficiently (grep/targeted reads, not full `cat`
  of every file — these can be large), determine for each PR mention whether it was
  genuinely **opened**, **reviewed/merged/closed**, or **noise** (a PR-sweep/search
  result never actually acted on) by that user in that session, and write a terse,
  factual one-to-three-sentence diary entry per substantive session (skip pure
  meta/Q&A sessions or fold them into one line)
- A request to report back: repo name, `{opened: N, reviewed: N}`, and the diary
  entries grouped by date

This mirrors how this report type has been built before — see the diary style in any
prior `usage-report*.html` output in the repo if one exists, and match its tone:
concrete (cites PR/issue numbers, file names), no fluff, no restating the obvious.

## Step 5 — Compute the "how I work" cards

Using the aggregated tool_buckets, subagents, skills, and PR classification, write
4–6 cards describing patterns actually evidenced in **this run's** data — do not
force a fixed set. Good candidates when supported by the data (reuse this framing,
refresh the numbers, drop any that aren't evidenced this run):
- Multi-repo orchestration (repo count)
- Delegating to sub-agents (spawn count, what kinds of work got delegated)
- Isolating with git worktrees (only if `EnterWorktree` shows up in tool_counts)
- Tracking work as tasks (TaskCreate/TaskUpdate volume)
- Turning prompts into reusable Skills (only if genuinely evidenced — e.g. commits/PRs
  adding `SKILL.md` or `.claude/skills/` files, or explicit skill-creation language in
  session content — otherwise omit this card rather than guess a count)
- PR lifecycle discipline (reviews/closes/defers vs. opens)

## Step 6 — Assemble the report data and render

Compute:
- **stats**: session_count, distinct repos touched (from PR urls' `owner/repo` plus
  any project dirs with no PR data), PRs opened, PRs reviewed/merged/closed,
  sub-agent delegations (sum of `totals.subagents`), and skills authored (from Step 5,
  omit the tile if not measurable this run)
- **charts.daily**: `totals.daily_counts` as `[["M/D", count], ...]` sorted by date —
  include every day in the range (zero-fill gaps), not just days with activity
- **charts.prsByRepo**: `[[repo, opened, reviewed], ...]` sorted descending by total,
  from Step 4's classification — fold long tails into an `"N other repos"` bucket
  past the top ~7
- **charts.toolCalls**: from `totals.tool_buckets`, as
  `[["Bash / shell", n, "var(--cat-red)"], ["File edits (Edit/Write)", n, "var(--cat-blue)"], ["Task tracking", n, "var(--cat-yellow)"], ["Reads", n, "var(--cat-aqua)"], ["Other tools", n, "var(--cat-magenta)"], ["Planning / Q&A", n, "var(--cat-violet)"], ["Sub-agent delegation", n, "var(--cat-green)"]]`
  (keep this exact label→color mapping for consistency across report runs)
- **charts.subagents**: `totals.subagents` as `[[type, count], ...]` sorted descending
- **diary**: from Step 4, grouped by date as `{date: "Jun 23", n: "1 session", items: ["...", ...]}`
- **meta**: title `"Claude Code Usage Report"`, subtitle `"<user's name if known> · Gilead Sciences"`,
  `dateRangeLabel` (e.g. `"Jun 23 – Jul 8, 2026"` or `"trailing 1 year"` for wide ranges),
  and short intros for the how-I-work/metrics/diary sections mentioning the
  timeframe/project filter actually used

Then:
1. Copy `$_root/usage-report-template.html` to the output path (Step 7).
2. Read the copy. Replace the entire `const REPORT = { ... };` statement (the one
   immediately followed by `const ICONS = {`) with `const REPORT = ` followed by
   your computed object as JSON, then `;`. Leave `ICONS` and everything under the
   `RENDER (no data below this line)` marker untouched.

## Step 7 — Write, open, and report back

Output path: `./usage-report-<since>-to-<until><-project-suffix>.html` in the
current working directory (e.g. `usage-report-2025-07-08-to-2026-07-08.html`, or
`usage-report-2026-06-08-to-2026-07-08-gsm-roadmap.html` when a project filter was
used). Run `open <path>` to preview it, and tell the user the path plus a one-line
summary of what's in range (session count, date span, project filter).
