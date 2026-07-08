#!/usr/bin/env python3
"""Mine local Claude Code session transcripts (~/.claude/projects/*/*.jsonl) for
usage-report metrics: sessions, tool-call volume, sub-agent/skill usage, PR/commit
mentions, and daily activity. Emits one JSON object to stdout.

This script is deliberately mechanical (counts, regexes, date filtering) — it does
not attempt to write narrative summaries. The /usage-report command pairs this
output with LLM-written diary text for the sessions in scope.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"

TOOL_BUCKETS = {
    "Bash / shell": {"Bash"},
    "File edits (Edit/Write)": {"Edit", "Write", "NotebookEdit"},
    "Task tracking": {"TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TaskOutput", "TaskStop"},
    "Reads": {"Read"},
    "Sub-agent delegation": {"Agent"},
    "Planning / Q&A": {"AskUserQuestion", "ExitPlanMode", "EnterPlanMode"},
}

PR_URL_RE = re.compile(r"github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)")
PR_CREATE_RE = re.compile(r"gh\s+pr\s+create")
PR_REPO_FLAG_RE = re.compile(r"--repo[= ]([\w.-]+/[\w.-]+)")
COMMIT_RE = re.compile(r"git\s+commit\b[^\n]*?-m\s+['\"]([^'\"]{3,120})")


def parse_timeframe(s):
    """Return a cutoff datetime (UTC) for a timeframe string, or None for 'all'."""
    if s is None or s.lower() in ("all", "any", "ever"):
        return None
    s = s.strip().lower()
    m = re.match(r"^(\d+)\s*([dwmy])$", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = {"d": 1, "w": 7, "m": 30, "y": 365}[unit] * n
        return datetime.now(timezone.utc) - timedelta(days=days)
    try:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except ValueError:
        raise SystemExit(f"Could not parse --since value: {s!r} (expected e.g. 1y, 90d, 6m, or an ISO date)")


def normalize(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def session_timestamp(path):
    """Best-effort session start time: first JSONL line's timestamp field, else mtime."""
    try:
        with open(path, "r", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    break
                ts = obj.get("timestamp")
                if ts:
                    try:
                        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except ValueError:
                        pass
                break
    except OSError:
        pass
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def iter_content_blocks(record):
    msg = record.get("message")
    if not isinstance(msg, dict):
        return
    content = msg.get("content")
    if isinstance(content, str):
        return
    if not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, dict):
            yield block


def stringify_result_content(block):
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and isinstance(c.get("text"), str):
                parts.append(c["text"])
        return "\n".join(parts)
    return ""


def scan_session(path):
    """Return per-session aggregates from a single transcript file."""
    tool_counts = {}
    subagents = {}
    skills = {}
    pr_urls = set()
    pr_create_repos = []
    commit_messages = []

    try:
        with open(path, "r", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for block in iter_content_blocks(record):
                    btype = block.get("type")
                    if btype == "tool_use":
                        name = block.get("name", "Unknown")
                        tool_counts[name] = tool_counts.get(name, 0) + 1
                        inp = block.get("input") or {}
                        if name == "Agent":
                            sub = inp.get("subagent_type", "general-purpose")
                            subagents[sub] = subagents.get(sub, 0) + 1
                        elif name == "Skill":
                            sk = inp.get("skill", "unknown")
                            skills[sk] = skills.get(sk, 0) + 1
                        elif name == "Bash":
                            cmd = inp.get("command", "")
                            if PR_CREATE_RE.search(cmd):
                                repo_m = PR_REPO_FLAG_RE.search(cmd)
                                pr_create_repos.append(repo_m.group(1) if repo_m else None)
                            for cm in COMMIT_RE.finditer(cmd):
                                commit_messages.append(cm.group(1))
                    elif btype == "tool_result":
                        text = stringify_result_content(block)
                        for m in PR_URL_RE.finditer(text):
                            pr_urls.add(f"{m.group(1)}#{m.group(2)}")
    except OSError:
        pass

    return {
        "tool_counts": tool_counts,
        "subagents": subagents,
        "skills": skills,
        "pr_urls": sorted(pr_urls),
        "pr_create_repos": pr_create_repos,
        "commit_messages": commit_messages,
    }


def merge_counts(dst, src):
    for k, v in src.items():
        dst[k] = dst.get(k, 0) + v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="1y", help="Timeframe: 1y, 90d, 6m, an ISO date, or 'all' (default: 1y)")
    ap.add_argument("--project", default="all", help="Substring to match against project folder names, or 'all' (default: all)")
    args = ap.parse_args()

    cutoff = parse_timeframe(args.since)
    project_needle = None if args.project.lower() == "all" else normalize(args.project)

    if not PROJECTS_DIR.exists():
        print(json.dumps({"error": f"{PROJECTS_DIR} does not exist"}))
        sys.exit(1)

    projects_out = []
    totals_tools = {}
    totals_subagents = {}
    totals_skills = {}
    daily_counts = {}
    all_dates = []

    for proj_dir in sorted(PROJECTS_DIR.iterdir()):
        if not proj_dir.is_dir():
            continue
        if project_needle and project_needle not in normalize(proj_dir.name):
            continue

        sessions = []
        proj_tools = {}
        proj_subagents = {}
        proj_skills = {}
        proj_pr_urls = set()
        proj_pr_create_repos = []
        proj_commits = []

        for jsonl in sorted(proj_dir.glob("*.jsonl")):
            ts = session_timestamp(jsonl)
            if cutoff and ts < cutoff:
                continue
            date_str = ts.date().isoformat()
            agg = scan_session(jsonl)
            sessions.append({
                "file": jsonl.name,
                "date": date_str,
                "timestamp": ts.isoformat(),
            })
            merge_counts(proj_tools, agg["tool_counts"])
            merge_counts(proj_subagents, agg["subagents"])
            merge_counts(proj_skills, agg["skills"])
            proj_pr_urls |= set(agg["pr_urls"])
            proj_pr_create_repos.extend(agg["pr_create_repos"])
            proj_commits.extend(agg["commit_messages"])
            daily_counts[date_str] = daily_counts.get(date_str, 0) + 1
            all_dates.append(date_str)

        if not sessions:
            continue

        merge_counts(totals_tools, proj_tools)
        merge_counts(totals_subagents, proj_subagents)
        merge_counts(totals_skills, proj_skills)

        projects_out.append({
            "dir": proj_dir.name,
            "session_count": len(sessions),
            "sessions": sessions,
            "tool_counts": proj_tools,
            "subagents": proj_subagents,
            "skills": proj_skills,
            "pr_urls": sorted(proj_pr_urls),
            "pr_create_repos": [r for r in proj_pr_create_repos if r],
            "commit_messages": proj_commits[:50],
        })

    buckets = {name: 0 for name in TOOL_BUCKETS}
    buckets["Other tools"] = 0
    for tool_name, count in totals_tools.items():
        placed = False
        for bucket_name, members in TOOL_BUCKETS.items():
            if tool_name in members:
                buckets[bucket_name] += count
                placed = True
                break
        if not placed:
            buckets["Other tools"] += count

    result = {
        "since": args.since,
        "cutoff": cutoff.date().isoformat() if cutoff else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_filter": args.project,
        "projects": projects_out,
        "totals": {
            "session_count": sum(p["session_count"] for p in projects_out),
            "days_active": len(set(all_dates)),
            "date_span": {
                "first": min(all_dates) if all_dates else None,
                "last": max(all_dates) if all_dates else None,
            },
            "daily_counts": dict(sorted(daily_counts.items())),
            "tool_counts": totals_tools,
            "tool_buckets": buckets,
            "subagents": totals_subagents,
            "skills": totals_skills,
        },
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
