"""
MCP server exposing energy_estimate.py's session energy model for Claude
Code sessions.

Session discovery
------------------
Claude Code sets CLAUDE_CODE_SESSION_ID in the environment of processes it
launches (including this server, when run locally via stdio), so that env
var is the reliable way to identify "the current chat" -- far more robust
than trying to reverse Claude Code's project-folder slug encoding (every
non-alphanumeric character in the project path becomes "-", which is
lossy). The slug-based lookup below is only a best-effort fallback for when
the env var is missing (e.g. manual testing outside Claude Code).

"Current project" scoping for collate_project_sessions_energy(): the
parent directory of the current session's .jsonl file.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastmcp import FastMCP

from energy_estimate import estimate_session_from_file
from mcp_results import collated_energy_result, session_energy_result

mcp = FastMCP("carbon-tracking-energy-claude")

_CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"


def _find_claude_session_file(session_id: str) -> Path | None:
    matches = list(_CLAUDE_PROJECTS_ROOT.glob(f"*/{session_id}.jsonl"))
    return matches[0] if matches else None


def _current_claude_project_dir() -> Path | None:
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if session_id:
        session_file = _find_claude_session_file(session_id)
        if session_file:
            return session_file.parent

    # Best-effort fallback when the env var isn't set: Claude Code's slug
    # encoding replaces every non-alphanumeric character with "-".
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(Path.cwd()))
    candidate = _CLAUDE_PROJECTS_ROOT / slug
    return candidate if candidate.is_dir() else None


@mcp.tool()
def current_session_energy() -> dict:
    """Estimated energy (Wh) and CO2eq for the calling Claude Code session."""
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not session_id:
        return {"error": "CLAUDE_CODE_SESSION_ID is not set."}

    session_file = _find_claude_session_file(session_id)
    if not session_file:
        return {"error": f"No session log found for session {session_id} under {_CLAUDE_PROJECTS_ROOT}."}

    request_count, wh = estimate_session_from_file(session_file)
    return session_energy_result("claude", session_id, session_file, request_count, wh)


@mcp.tool()
def collate_project_sessions_energy() -> dict:
    """Total + per-session energy and CO2eq for every Claude Code chat in the current project."""
    project_dir = _current_claude_project_dir()
    if not project_dir:
        return {"error": "Could not determine the current project's Claude Code session directory."}

    files = sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    sessions = []
    total_wh = 0.0
    for f in files:
        request_count, wh = estimate_session_from_file(f)
        sessions.append({"session_id": f.stem, "request_count": request_count, "estimated_wh": round(wh, 3)})
        total_wh += wh

    return collated_energy_result("claude", project_dir, sessions, total_wh)


if __name__ == "__main__":
    mcp.run()
