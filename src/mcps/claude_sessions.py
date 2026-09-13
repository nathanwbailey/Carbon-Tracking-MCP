"""
Session discovery helpers for Claude Code (~/.claude/projects/**/*.jsonl).

No environment-variable reads happen in this module -- callers (stdio and
HTTP server entrypoints) resolve a session_id or cwd from whatever source
fits their transport (env var for stdio, explicit tool parameter for HTTP)
and pass it in here.
"""

from __future__ import annotations

import re
from pathlib import Path

CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"


def find_claude_session_file(session_id: str, projects_root: Path) -> Path | None:
    """Locate a session's .jsonl file by globbing projects_root/*/<session_id>.jsonl."""
    matches = list(projects_root.glob(f"*/{session_id}.jsonl"))
    return matches[0] if matches else None


def slugify_cwd(cwd: Path | str) -> str:
    """Claude Code's project-folder slug encoding: every non-alphanumeric
    character in the project path becomes "-" (lossy)."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def claude_project_dir_for_cwd(cwd: Path | str, projects_root: Path) -> Path | None:
    """Resolve cwd's Claude Code session directory via slug encoding."""
    candidate = projects_root / slugify_cwd(cwd)
    return candidate if candidate.is_dir() else None


def claude_project_dir_for_session(session_id: str, projects_root: Path) -> Path | None:
    """Resolve the parent project directory of a given session's .jsonl file."""
    session_file = find_claude_session_file(session_id, projects_root)
    return session_file.parent if session_file else None


def list_claude_project_sessions(project_dir: Path) -> list[Path]:
    """List every session .jsonl in project_dir, most-recently-modified first."""
    return sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
