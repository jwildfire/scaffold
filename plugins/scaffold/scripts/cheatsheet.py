#!/usr/bin/env python3
"""Regenerate ~/.claude/cheatsheet.html by introspecting Claude Code config.

Discovers:
  - ~/.claude/settings.json           (user-global model/theme/hooks/permissions)
  - ~/.claude/commands/*.md           (custom slash commands)
  - ~/.claude/skills/*/SKILL.md       (custom skills)
  - ~/.claude/agents/*                (custom subagents)
  - ~/github/**/.claude/settings*.json (workspace + per-repo permissions)
  - ~/github/**/CLAUDE.md, AGENTS.md  (context files; root + one repo level)

The Default-tab content (built-in skills/subagents/commands/shell passthrough)
is hardcoded here — Claude Code doesn't expose those as files, so changes
require editing this script.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from html import escape
from pathlib import Path

HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
GH_DIR = HOME / "github"
OUTPUT = CLAUDE_DIR / "cheatsheet.html"

# ---------- harness defaults (what never prompts) ----------
HARNESS_AUTO_GIT = {
    "status", "log", "diff", "show", "blame", "branch", "tag", "remote",
    "ls-files", "ls-remote", "rev-parse", "describe", "stash", "reflog",
    "shortlog", "cat-file", "for-each-ref", "worktree", "config",
}
HARNESS_AUTO_GH = {"pr", "issue", "run", "workflow", "repo", "release", "auth", "api"}
HARNESS_AUTO_DOCKER = {"ps", "images", "logs", "inspect"}

# ---------- pattern → description (best-effort, ordered) ----------
DESC_RULES: list[tuple[str, str]] = [
    (r"^Bash\(gh search\b", "GitHub search across repos / issues / code"),
    (r"^Bash\(gh pr\b", "All `gh pr` subcommands"),
    (r"^Bash\(gh api\b", "Raw GitHub API calls (incl. POST/PATCH/DELETE)"),
    (r"^Bash\(gh issue\b", "All `gh issue` subcommands"),
    (r"^Bash\(gh repo\b", "All `gh repo` subcommands"),
    (r"^Bash\(gh run\b", "All `gh run` subcommands"),
    (r"^Bash\(gh workflow\b", "All `gh workflow` subcommands"),
    (r"^Bash\(gh search\b", "GitHub search across repos / issues / code"),
    (r"^Bash\(code\b", "Open files / dirs in VS Code"),
    (r'^Bash\(open -a "Google Chrome"', "Open URLs / files in Chrome"),
    (r"^Bash\(open\b", "macOS `open` (any target)"),
    (r"^Bash\(mv ISSUE_", "Rename issue draft files (drafts workflow)"),
    (r"^Bash\(sed -i '' 's\|<!-- STATUS:", "Update STATUS markers in markdown drafts"),
    (r"^Bash\(git\b", "git command"),
    (r"^Bash\(", "Bash command"),
    (r"^mcp__", "MCP tool"),
]


def describe(pattern: str) -> str:
    for pat, desc in DESC_RULES:
        if re.search(pat, pattern):
            return desc
    return ""


def redundancy_note(pattern: str) -> str:
    """Return a redundancy/duplicate note if covered by harness defaults."""
    m = re.match(r"Bash\(git ([\w-]+)", pattern)
    if m and m.group(1) in HARNESS_AUTO_GIT:
        return "redundant — harness auto-allows read views"
    m = re.match(r"Bash\(gh ([\w-]+)", pattern)
    if m and m.group(1) in HARNESS_AUTO_GH:
        if m.group(1) == "api":
            return "redundant for GET; also allows POST/PATCH/DELETE (intentional?)"
        return "redundant — harness auto-allows read views"
    m = re.match(r"Bash\(docker ([\w-]+)", pattern)
    if m and m.group(1) in HARNESS_AUTO_DOCKER:
        return "redundant — harness auto-allows read views"
    return ""


# ---------- discovery ----------
def read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body) from a markdown file."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    fm_raw = text[4:end]
    body = text[end + 4:].lstrip("\n")
    fm: dict = {}
    for line in fm_raw.splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return fm, body


def discover_commands() -> list[dict]:
    out = []
    d = CLAUDE_DIR / "commands"
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.md")):
        fm, body = parse_frontmatter(f.read_text(errors="ignore"))
        out.append({
            "name": f.stem,
            "description": fm.get("description", "").strip('"') or body.strip().splitlines()[0][:80],
        })
    return out


def discover_skills() -> tuple[list[dict], str | None]:
    """Return (skills, symlink_target_or_None)."""
    d = CLAUDE_DIR / "skills"
    symlink_target = None
    if d.is_symlink():
        try:
            symlink_target = str(d.resolve().relative_to(HOME).as_posix())
            symlink_target = f"~/{symlink_target}"
        except Exception:
            symlink_target = str(d.resolve())
    if not d.exists():
        return [], symlink_target
    skills = []
    for sub in sorted(d.iterdir()):
        if not sub.is_dir():
            continue
        skill_md = sub / "SKILL.md"
        desc = ""
        if skill_md.exists():
            fm, body = parse_frontmatter(skill_md.read_text(errors="ignore"))
            desc = fm.get("description", "").strip('"')
            if not desc:
                desc = body.strip().splitlines()[0][:120] if body.strip() else ""
        skills.append({"name": sub.name, "description": desc})
    return skills, symlink_target


def discover_agents() -> list[dict]:
    d = CLAUDE_DIR / "agents"
    if not d.exists():
        return []
    agents = []
    for sub in sorted(d.iterdir()):
        if sub.suffix == ".md":
            fm, body = parse_frontmatter(sub.read_text(errors="ignore"))
            agents.append({
                "name": fm.get("name", sub.stem),
                "description": fm.get("description", "").strip('"'),
            })
    return agents


def discover_permission_files() -> list[dict]:
    """Find permission-bearing settings files under ~/.claude and ~/github/."""
    files: list[dict] = []
    # User-global
    p = CLAUDE_DIR / "settings.json"
    if p.exists():
        files.append({
            "label": "User-global",
            "path": p,
            "display_path": "~/.claude/settings.json",
        })
    # Workspace + per-repo (one level: ~/github/.claude/* and ~/github/<repo>/.claude/*)
    if GH_DIR.exists():
        candidates: list[Path] = []
        # workspace root
        candidates += [GH_DIR / ".claude" / "settings.json", GH_DIR / ".claude" / "settings.local.json"]
        # per repo (single level under github/)
        for repo in sorted(GH_DIR.iterdir()):
            if not repo.is_dir() or repo.name.startswith("."):
                continue
            for fn in ("settings.json", "settings.local.json"):
                candidates.append(repo / ".claude" / fn)
        for f in candidates:
            if not f.exists():
                continue
            kind = "local" if f.name == "settings.local.json" else "shared"
            parent = f.parent.parent  # the repo root
            if parent == GH_DIR:
                label = f"Workspace {kind}"
            else:
                label = f"Repo: {parent.name} ({kind})"
            try:
                display = "~/" + str(f.relative_to(HOME).as_posix())
            except ValueError:
                display = str(f)
            files.append({"label": label, "path": f, "display_path": display})
    return files


def aggregate_permissions(perm_files: list[dict]) -> list[dict]:
    """Returns list of {file_label, file_display, patterns: [{pattern, description, redundant, duplicate}]}."""
    seen_patterns: dict[str, str] = {}  # pattern -> first file label
    out = []
    for pf in perm_files:
        data = read_json(pf["path"])
        allow = (data.get("permissions") or {}).get("allow") or []
        entries = []
        for pat in allow:
            note_parts: list[str] = []
            r = redundancy_note(pat)
            if r:
                note_parts.append(r)
            if pat in seen_patterns:
                note_parts.append(f"duplicate of entry in {seen_patterns[pat]}")
            else:
                seen_patterns[pat] = pf["label"]
            entries.append({
                "pattern": pat,
                "description": describe(pat),
                "annotations": note_parts,
            })
        out.append({
            "label": pf["label"],
            "display_path": pf["display_path"],
            "patterns": entries,
        })
    return out


def discover_context_files(cwd: Path) -> list[dict]:
    """Find CLAUDE.md / AGENTS.md files; classify load-status relative to cwd."""
    results: list[dict] = []
    seen: set[Path] = set()

    def add(path: Path, status: str, note: str):
        try:
            key = path.resolve(strict=False)
        except Exception:
            key = path
        if key in seen:
            return
        seen.add(key)
        try:
            display = "~/" + str(path.relative_to(HOME).as_posix())
        except ValueError:
            display = str(path)
        results.append({"path": path, "display": display, "status": status, "note": note})

    # User-global CLAUDE.md
    p = CLAUDE_DIR / "CLAUDE.md"
    if p.exists():
        target = ""
        if p.is_symlink():
            try:
                target = "~/" + str(p.resolve().relative_to(HOME).as_posix())
            except Exception:
                target = str(p.resolve())
            add(p, "loaded", f"user-global; symlink → <code>{escape(target)}</code>")
        else:
            add(p, "loaded", "user-global")
    else:
        add(p, "missing", "recommended: symlink → <code>~/github/.github/AGENTS.md</code> to put ecosystem context into every session")

    # Workspace CLAUDE.md (~/github/CLAUDE.md)
    p = GH_DIR / "CLAUDE.md"
    if p.exists():
        loaded = cwd_is_under(cwd, GH_DIR)
        add(p, "loaded" if loaded else "when cwd",
            "workspace pointer; auto-loaded when cwd is under <code>~/github/</code>")
        # Detect pointers inside it
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            text = ""
        for m in re.finditer(r"~?/[\w./\-]*?/(AGENTS\.md|CLAUDE\.md)", text):
            ref = m.group(0)
            ref_path = Path(os.path.expanduser(ref if ref.startswith("~") else str(HOME / ref.lstrip("/"))))
            if ref_path.exists() and ref_path != p:
                add(ref_path, "via pointer",
                    "referenced by <code>~/github/CLAUDE.md</code>; loaded if Claude follows the pointer")

    # Per-repo AGENTS.md / CLAUDE.md (one level deep)
    if GH_DIR.exists():
        for repo in sorted(GH_DIR.iterdir()):
            if not repo.is_dir() or repo.name.startswith("."):
                continue
            for fname in ("AGENTS.md", "CLAUDE.md", ".github/AGENTS.md", ".github/CLAUDE.md"):
                p = repo / fname
                if p.exists():
                    loaded = cwd_is_under(cwd, repo)
                    add(p, "loaded" if loaded else "when cwd",
                        f"loads when working inside <code>{repo.name}</code>")
    return results


def cwd_is_under(cwd: Path, ancestor: Path) -> bool:
    try:
        cwd.resolve().relative_to(ancestor.resolve())
        return True
    except ValueError:
        return False


# ---------- HTML rendering ----------
CSS_AND_JS = """
<style>
  :root {
    --bg: #0f1419; --panel: #1a2027; --panel-2: #232a33;
    --border: #2f3845; --accent: #d97757; --accent-soft: #b8623f;
    --text: #e6e6e6; --text-dim: #9ba6b3; --text-faint: #6b7686;
    --custom: #7ab8ff; --default: #9ba6b3;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0;
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 14px; line-height: 1.5;
  }
  .wrap { max-width: 1200px; margin: 0 auto; padding: 28px 32px 60px; }
  header {
    border-bottom: 1px solid var(--border);
    padding-bottom: 16px; margin-bottom: 20px;
    display: flex; justify-content: space-between; align-items: baseline;
  }
  h1 { margin: 0; font-size: 22px; font-weight: 600; letter-spacing: -0.01em; }
  .sub { color: var(--text-dim); font-size: 12px; font-family: var(--mono); }
  .tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 24px; }
  .tab {
    background: none; border: none; color: var(--text-faint);
    font-family: inherit; font-size: 13px; font-weight: 600;
    letter-spacing: 0.05em; text-transform: uppercase;
    padding: 10px 18px; cursor: pointer;
    border-bottom: 2px solid transparent; margin-bottom: -1px;
  }
  .tab:hover { color: var(--text-dim); }
  .tab.active { color: var(--custom); border-bottom-color: var(--custom); }
  .tab.active.default-tab { color: var(--default); border-bottom-color: var(--default); }
  .tab-pane { display: none; }
  .tab-pane.active { display: block; }
  h3 { margin: 4px 0 8px; font-size: 13px; font-weight: 600; color: var(--text); }
  h3 .h3-sub { font-weight: 400; color: var(--text-faint); font-size: 12px; margin-left: 6px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; padding: 14px 16px; }
  .panel.wide { grid-column: 1 / -1; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  td { padding: 5px 8px 5px 0; vertical-align: top; border-bottom: 1px solid rgba(255,255,255,0.03); }
  tr:last-child td { border-bottom: none; }
  td.name { font-family: var(--mono); color: var(--accent); white-space: nowrap; width: 1%; padding-right: 14px; }
  td.desc { color: var(--text-dim); }
  .empty { color: var(--text-faint); font-style: italic; padding: 4px 0; }
  code {
    font-family: var(--mono); background: var(--panel-2);
    padding: 1px 5px; border-radius: 3px; font-size: 12px; color: var(--accent);
  }
  .kv { font-family: var(--mono); font-size: 12px; }
  .kv .k { color: var(--text-dim); }
  .kv .v { color: var(--text); }
  .note { font-size: 12px; color: var(--text-faint); margin-top: 6px; }
  .redundant { color: var(--text-faint); font-style: italic; }
  .scope-legend {
    font-family: var(--mono); font-size: 12px; color: var(--text-dim);
    background: var(--panel-2); padding: 8px 10px; border-radius: 4px; margin-bottom: 12px;
  }
  .auto-allow { font-family: var(--mono); font-size: 12px; color: var(--text-dim); line-height: 1.8; }
  .auto-allow code { background: transparent; padding: 0; color: var(--text-dim); }
  .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
  .panel-header h3 { margin: 0; }
  .toggle { display: inline-flex; background: var(--panel-2); border-radius: 4px; padding: 2px; font-family: var(--mono); font-size: 11px; }
  .toggle button {
    background: none; border: none; color: var(--text-faint);
    padding: 4px 10px; cursor: pointer; border-radius: 3px;
    font-family: inherit; font-size: inherit;
  }
  .toggle button.active { background: var(--border); color: var(--text); }
  .allow-view { display: none; }
  .allow-view.active { display: block; }
  .scope-group { margin-bottom: 14px; }
  .scope-group:last-child { margin-bottom: 0; }
  .scope-title { font-family: var(--mono); font-size: 12px; color: var(--text-dim); font-weight: 600; margin-bottom: 6px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    font-family: var(--mono); font-size: 12px;
    background: var(--panel-2); color: var(--accent);
    padding: 4px 9px; border-radius: 3px;
    border: 1px solid transparent; cursor: help;
  }
  .chip.redundant { color: var(--text-faint); border-style: dashed; border-color: var(--border); }
  .ctx-row { display: flex; gap: 10px; padding: 4px 0; align-items: baseline; }
  .ctx-status {
    font-family: var(--mono); font-size: 10px;
    padding: 2px 6px; border-radius: 3px;
    text-transform: uppercase; letter-spacing: 0.05em;
    flex-shrink: 0; width: 92px; text-align: center;
  }
  .ctx-loaded { background: rgba(122,184,255,0.15); color: var(--custom); }
  .ctx-conditional { background: rgba(217,119,87,0.12); color: var(--accent); }
  .ctx-missing { background: var(--panel-2); color: var(--text-faint); }
  .ctx-path { font-family: var(--mono); font-size: 12px; color: var(--text); }
  .ctx-note { color: var(--text-dim); font-size: 12px; }
</style>
"""

JS_TAIL = """
<script>
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b === btn));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === 'tab-' + target));
    });
  });
  const toggle = document.getElementById('allow-toggle');
  if (toggle) {
    toggle.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('click', () => {
        const view = btn.dataset.view;
        toggle.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn));
        document.querySelectorAll('.allow-view').forEach(v => v.classList.toggle('active', v.dataset.view === view));
      });
    });
  }
</script>
"""


def md_inline(s: str) -> str:
    """Escape HTML, then convert markdown `code` spans to <code>."""
    s = escape(s)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", s)


def row(name: str, desc: str) -> str:
    return f'<tr><td class="name">{escape(name)}</td><td class="desc">{desc}</td></tr>'


def render_commands(commands: list[dict]) -> str:
    if not commands:
        return '<div class="empty">none defined &mdash; <code>~/.claude/commands/</code> does not exist or is empty</div>'
    rows = "\n".join(row(f"/{c['name']}", md_inline(c['description'])) for c in commands)
    return f'<table>{rows}</table><div class="note">Source: <code>~/.claude/commands/</code></div>'


def render_skills(skills: list[dict], symlink_target: str | None) -> str:
    if not skills:
        body = '<div class="empty">none defined &mdash; <code>~/.claude/skills/</code> is empty or absent</div>'
    else:
        rows = "\n".join(row(s["name"], md_inline(s["description"])) for s in skills)
        body = f"<table>{rows}</table>"
    if symlink_target:
        note = f'<div class="note">Symlinked: <code>~/.claude/skills/</code> &rarr; <code>{escape(symlink_target)}</code></div>'
    else:
        note = '<div class="note">Source: <code>~/.claude/skills/</code></div>'
    return body + note


def render_agents(agents: list[dict]) -> str:
    if not agents:
        return '<div class="empty">none defined &mdash; <code>~/.claude/agents/</code> does not exist</div>'
    rows = "\n".join(row(a["name"], md_inline(a["description"])) for a in agents)
    return f'<table>{rows}</table>'


def render_settings(settings: dict) -> str:
    items = []
    for key in ("model", "theme"):
        v = settings.get(key)
        if v:
            items.append(f'<div><span class="k">{key}:</span> <span class="v">{escape(str(v))}</span></div>')
    other_keys = [k for k in settings.keys() if k not in ("model", "theme", "permissions", "hooks")]
    for k in other_keys:
        items.append(f'<div><span class="k">{escape(k)}:</span> <span class="v">{escape(str(settings[k]))[:60]}</span></div>')
    body = '<div class="kv">' + "".join(items) + "</div>" if items else '<div class="empty">no user-global settings</div>'
    return body + '<div class="note">Source: <code>~/.claude/settings.json</code> (user-global)</div>'


def render_hooks(settings: dict) -> str:
    hooks = settings.get("hooks") or {}
    if not hooks:
        return '<div class="empty">none configured</div>'
    rows = []
    for event, handlers in hooks.items():
        if isinstance(handlers, list):
            for h in handlers:
                cmd = h.get("command") if isinstance(h, dict) else str(h)
                rows.append(row(event, escape(str(cmd))))
        else:
            rows.append(row(event, escape(str(handlers))))
    return f'<table>{"".join(rows)}</table>'


def render_context_files(context_files: list[dict]) -> str:
    if not context_files:
        return '<div class="empty">no context files found</div>'
    rows = []
    for cf in context_files:
        status = cf["status"]
        cls = {"loaded": "ctx-loaded", "when cwd": "ctx-conditional",
               "via pointer": "ctx-conditional", "missing": "ctx-missing"}.get(status, "ctx-missing")
        rows.append(
            f'<div class="ctx-row"><span class="ctx-status {cls}">{escape(status)}</span>'
            f'<span class="ctx-path">{escape(cf["display"])}</span>'
            f'<span class="ctx-note">{cf["note"]}</span></div>'
        )
    note = ('<div class="note" style="margin-top: 10px;">Claude Code walks up from cwd loading '
            '<code>CLAUDE.md</code> at each level; <code>AGENTS.md</code> files load the same way in recent versions. '
            '<em>loaded</em> = in this session\'s context now; <em>when cwd</em> = auto-loads when working inside that tree; '
            '<em>via pointer</em> = not auto-loaded, only read because another file references it; '
            '<em>missing</em> = not on disk.</div>')
    return "".join(rows) + note


def render_permissions(perms: list[dict]) -> str:
    # Filter out groups with no patterns (file exists but empty)
    perms = [p for p in perms if p["patterns"]]
    if not perms:
        chips_body = '<div class="empty">no custom permissions defined</div>'
        detailed_body = chips_body
    else:
        # Simple (chips) view
        chip_groups = []
        for grp in perms:
            chips = []
            for entry in grp["patterns"]:
                ann = entry["annotations"]
                tip = entry["description"] or entry["pattern"]
                if ann:
                    tip += " — " + "; ".join(ann)
                cls = "chip redundant" if ann else "chip"
                chips.append(f'<span class="{cls}" title="{escape(tip)}">{escape(entry["pattern"])}</span>')
            chip_groups.append(
                f'<div class="scope-group">'
                f'<div class="scope-title">{escape(grp["label"])} &middot; <code>{escape(grp["display_path"])}</code></div>'
                f'<div class="chips">{"".join(chips)}</div></div>'
            )
        chips_body = ("".join(chip_groups) +
                      '<div class="note">Hover any chip for details &middot; dashed = redundant or duplicated &middot; '
                      'switch to <strong>Detailed</strong> for inline notes and the harness auto-allow list.</div>')

        # Detailed (table) view
        detailed_rows = []
        for grp in perms:
            detailed_rows.append(
                f'<tr><td class="name" style="color: var(--text-dim); font-weight: 600; padding-top: 14px;" colspan="2">'
                f'{escape(grp["label"])} &middot; <code>{escape(grp["display_path"])}</code></td></tr>'
            )
            for entry in grp["patterns"]:
                ann = entry["annotations"]
                desc_html = md_inline(entry["description"])
                if ann:
                    desc_html += f' <span class="redundant">&mdash; {md_inline("; ".join(ann))}</span>'
                detailed_rows.append(
                    f'<tr><td class="name">{escape(entry["pattern"])}</td>'
                    f'<td class="desc">{desc_html}</td></tr>'
                )
        detailed_body = f"""
        <div class="scope-legend">
          <strong style="color: var(--text);">scope &mdash;</strong>
          <code>~/.claude/settings.json</code> user-global &middot;
          <code>&lt;repo&gt;/.claude/settings.json</code> shared, committed &middot;
          <code>&lt;repo&gt;/.claude/settings.local.json</code> local, gitignored
        </div>
        <h3 style="margin-top: 4px;">Harness auto-allows <span class="h3-sub">never prompt, no entry needed</span></h3>
        <div class="auto-allow">
          <code>cd</code> <code>ls</code> <code>cat</code> <code>echo</code> <code>head</code> <code>tail</code> <code>wc</code> <code>diff</code> <code>grep</code> <code>rg</code> <code>jq</code> <code>find</code> <code>sort</code> <code>uniq</code> <code>date</code> <code>ps</code> <code>which</code> <code>printf</code> <code>sed</code> (read-only exprs) &middot;
          all read-only <code>git</code> (<code>status</code>/<code>log</code>/<code>diff</code>/<code>show</code>/<code>branch</code>/<code>tag</code>/<code>worktree</code>/&hellip;) &middot;
          <code>gh pr</code>/<code>issue</code>/<code>repo</code>/<code>api</code>/<code>run</code>/<code>workflow</code>/<code>auth</code> read views &middot;
          <code>docker ps</code>/<code>images</code>/<code>logs</code>/<code>inspect</code>
          <div class="note">Source of truth: <code>src/tools/BashTool/readOnlyValidation.ts</code> &amp; <code>src/utils/shell/readOnlyCommandValidation.ts</code></div>
        </div>
        <h3 style="margin-top: 18px;">Custom entries</h3>
        <table>{"".join(detailed_rows)}</table>"""

    return f"""
    <div class="panel-header">
      <h3>Permissions / Allowlist</h3>
      <div class="toggle" id="allow-toggle">
        <button data-view="simple" class="active">Simple</button>
        <button data-view="detailed">Detailed</button>
      </div>
    </div>
    <div class="allow-view active" data-view="simple">{chips_body}</div>
    <div class="allow-view" data-view="detailed">{detailed_body}</div>
    """


DEFAULT_TAB_HTML = """
<section id="tab-default" class="tab-pane">
<div class="grid">

  <div class="panel wide">
    <h3>Built-in Skills <span class="h3-sub">also invokable as <code>/&lt;name&gt;</code></span></h3>
    <table>
      <tr><td class="name">/code-review</td><td class="desc">Review current diff for bugs &amp; cleanups at chosen effort level</td></tr>
      <tr><td class="name">/simplify</td><td class="desc">Apply reuse/efficiency cleanups to changed code (quality-only, no bug hunt)</td></tr>
      <tr><td class="name">/review</td><td class="desc">Review a GitHub PR (use /code-review for the local working diff)</td></tr>
      <tr><td class="name">/security-review</td><td class="desc">Security review of pending changes on the current branch</td></tr>
      <tr><td class="name">/verify</td><td class="desc">Run the app and observe behavior to confirm a change works</td></tr>
      <tr><td class="name">/run</td><td class="desc">Launch and drive this project's app to see a change working</td></tr>
      <tr><td class="name">/init</td><td class="desc">Initialize a new CLAUDE.md with codebase documentation</td></tr>
      <tr><td class="name">/loop</td><td class="desc">Run a prompt or slash command on a recurring interval (or self-paced)</td></tr>
      <tr><td class="name">/schedule</td><td class="desc">Create / manage scheduled cloud agents (cron routines)</td></tr>
      <tr><td class="name">/update-config</td><td class="desc">Configure the harness via <code>settings.json</code> (permissions, hooks, env vars)</td></tr>
      <tr><td class="name">/fewer-permission-prompts</td><td class="desc">Scan transcripts &amp; allowlist common read-only tool calls in project settings</td></tr>
      <tr><td class="name">/keybindings-help</td><td class="desc">Customize keyboard shortcuts and chord bindings</td></tr>
      <tr><td class="name">/claude-api</td><td class="desc">Reference for Claude API / SDK (model ids, pricing, tools, caching)</td></tr>
    </table>
  </div>

  <div class="panel wide">
    <h3>Built-in Subagents <span class="h3-sub">Agent tool</span></h3>
    <table>
      <tr><td class="name">claude</td><td class="desc">Catch-all for tasks that don't fit a more specific agent. Full tool access.</td></tr>
      <tr><td class="name">Explore</td><td class="desc">Read-only search for finding files / symbols / references. Specify breadth: quick, medium, very thorough.</td></tr>
      <tr><td class="name">Plan</td><td class="desc">Software architect; designs implementation plans and identifies critical files</td></tr>
      <tr><td class="name">general-purpose</td><td class="desc">Multi-step research / search / execution when target is uncertain</td></tr>
      <tr><td class="name">claude-code-guide</td><td class="desc">Q&amp;A about Claude Code, Agent SDK, and the Claude API itself</td></tr>
      <tr><td class="name">statusline-setup</td><td class="desc">Configure the Claude Code status line</td></tr>
    </table>
  </div>

  <div class="panel">
    <h3>Common Built-in Commands</h3>
    <table>
      <tr><td class="name">/help</td><td class="desc">Help with using Claude Code</td></tr>
      <tr><td class="name">/agents</td><td class="desc">Open FleetView (background agents)</td></tr>
      <tr><td class="name">/config</td><td class="desc">Open settings UI</td></tr>
      <tr><td class="name">/memory</td><td class="desc">Manage CLAUDE.md memory</td></tr>
      <tr><td class="name">/clear</td><td class="desc">Clear conversation</td></tr>
      <tr><td class="name">/compact</td><td class="desc">Compact context manually</td></tr>
      <tr><td class="name">/model</td><td class="desc">Switch model for this session</td></tr>
      <tr><td class="name">/cost</td><td class="desc">Show session token / cost usage</td></tr>
      <tr><td class="name">/resume</td><td class="desc">Resume a previous session</td></tr>
      <tr><td class="name">/fast</td><td class="desc">Toggle Opus fast mode</td></tr>
    </table>
  </div>

  <div class="panel">
    <h3>Shell Passthrough</h3>
    <table>
      <tr><td class="name">! &lt;cmd&gt;</td><td class="desc">Run a shell command in this session; output appears inline</td></tr>
      <tr><td class="name">! claude --bg "..."</td><td class="desc">Spawn a background agent visible in <code>claude agents</code> (also: <code>/spawn</code>)</td></tr>
      <tr><td class="name">! claude --bg --exec '...'</td><td class="desc">Run a shell command as a background job</td></tr>
    </table>
  </div>

</div>
</section>
"""


def render(settings, commands, skills, skills_symlink, agents, perms, context_files) -> str:
    today = date.today().isoformat()
    user = os.environ.get("USER", "")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Claude Code Cheat Sheet</title>
{CSS_AND_JS}
</head><body>
<div class="wrap">

<header>
  <h1>Claude Code Cheat Sheet</h1>
  <div class="sub">{escape(user)} &middot; generated {today}</div>
</header>

<div class="tabs">
  <button class="tab active" data-tab="custom">Custom</button>
  <button class="tab default-tab" data-tab="default">Default</button>
</div>

<section id="tab-custom" class="tab-pane active">
<div class="grid">

  <div class="panel"><h3>Slash Commands</h3>{render_commands(commands)}</div>
  <div class="panel"><h3>Skills</h3>{render_skills(skills, skills_symlink)}</div>
  <div class="panel"><h3>Subagents</h3>{render_agents(agents)}</div>
  <div class="panel"><h3>Settings</h3>{render_settings(settings)}</div>
  <div class="panel"><h3>Hooks</h3>{render_hooks(settings)}</div>

  <div class="panel wide">
    <h3>Context Files <span class="h3-sub">CLAUDE.md / AGENTS.md loaded into the model's context</span></h3>
    {render_context_files(context_files)}
  </div>

  <div class="panel wide">
    {render_permissions(perms)}
  </div>

</div>
</section>

{DEFAULT_TAB_HTML}

<div class="note" style="margin-top: 32px; text-align: center;">
  Regenerated by <code>~/.claude/cheatsheet.py</code> &middot; open via <code>/cheatsheet</code>
</div>

</div>
{JS_TAIL}
</body></html>
"""


def main():
    cwd = Path.cwd()
    settings = read_json(CLAUDE_DIR / "settings.json")
    commands = discover_commands()
    skills, skills_symlink = discover_skills()
    agents = discover_agents()
    perm_files = discover_permission_files()
    perms = aggregate_permissions(perm_files)
    context_files = discover_context_files(cwd)
    html = render(settings, commands, skills, skills_symlink, agents, perms, context_files)
    OUTPUT.write_text(html)
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
