"""
stdio MCP server exposing mcps.energy_estimate's session energy model for
Claude Code sessions.

Session discovery
------------------
Claude Code sets CLAUDE_CODE_SESSION_ID in the environment of processes it
launches (including this server, when run locally via stdio), so that env
var is the reliable way to identify "the current chat" -- far more robust
than trying to reverse Claude Code's project-folder slug encoding (every
non-alphanumeric character in the project path becomes "-", which is
lossy). The slug-based lookup is only a best-effort fallback for when the
env var is missing (e.g. manual testing outside Claude Code).

"Current project" scoping for collate_project_sessions_energy(): the
parent directory of the current session's .jsonl file.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastmcp import FastMCP

from mcps import claude_sessions
from mcps.energy_estimate import estimate_session_from_file
from mcps.mcp_results import collated_energy_result, session_energy_result

mcp = FastMCP("carbon-tracking-energy-claude")


def _current_claude_project_dir() -> Path | None:
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if session_id:
        project_dir = claude_sessions.claude_project_dir_for_session(session_id, claude_sessions.CLAUDE_PROJECTS_ROOT)
        if project_dir:
            return project_dir

    return claude_sessions.claude_project_dir_for_cwd(Path.cwd(), claude_sessions.CLAUDE_PROJECTS_ROOT)


@mcp.tool()
def current_session_energy() -> dict:
    """Estimated energy (Wh) and CO2eq for the calling Claude Code session."""
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not session_id:
        return {"error": "CLAUDE_CODE_SESSION_ID is not set."}

    session_file = claude_sessions.find_claude_session_file(session_id, claude_sessions.CLAUDE_PROJECTS_ROOT)
    if not session_file:
        return {"error": f"No session log found for session {session_id} under {claude_sessions.CLAUDE_PROJECTS_ROOT}."}

    request_count, wh = estimate_session_from_file(session_file)
    return session_energy_result("claude", session_id, session_file, request_count, wh)


@mcp.tool()
def collate_project_sessions_energy() -> dict:
    """Total + per-session energy and CO2eq for every Claude Code chat in the current project."""
    project_dir = _current_claude_project_dir()
    if not project_dir:
        return {"error": "Could not determine the current project's Claude Code session directory."}

    files = claude_sessions.list_claude_project_sessions(project_dir)
    sessions = []
    total_wh = 0.0
    for f in files:
        request_count, wh = estimate_session_from_file(f)
        sessions.append({"session_id": f.stem, "request_count": request_count, "estimated_wh": round(wh, 3)})
        total_wh += wh

    return collated_energy_result("claude", project_dir, sessions, total_wh)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
