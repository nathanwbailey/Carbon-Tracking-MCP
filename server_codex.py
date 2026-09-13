"""
MCP server exposing energy_estimate.py's session energy model for Codex
sessions.

Session discovery
------------------
Codex sets CODEX_THREAD_ID in the environment of processes it launches
(including this server, when run locally via stdio). That thread ID is
looked up in Codex's local thread index (~/.codex/state_5.sqlite) to find
its rollout .jsonl path, falling back to a filename scan under
~/.codex/sessions if the DB lookup fails or the thread isn't indexed yet.

"Current project" scoping for collate_project_sessions_energy(): every
indexed thread whose recorded cwd exactly matches the current working
directory.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastmcp import FastMCP

from energy_estimate import estimate_session_from_file
from mcp_results import collated_energy_result, session_energy_result

mcp = FastMCP("carbon-tracking-energy-codex")

_CODEX_HOME = Path.home() / ".codex"
_CODEX_STATE_DB = _CODEX_HOME / "state_5.sqlite"
_CODEX_SESSIONS_ROOT = _CODEX_HOME / "sessions"


def _find_codex_thread_file(thread_id: str) -> Path | None:
    """Look up a Codex rollout by thread ID, then fall back to its filename."""
    if _CODEX_STATE_DB.exists():
        try:
            with sqlite3.connect(f"file:{_CODEX_STATE_DB}?mode=ro", uri=True) as conn:
                row = conn.execute(
                    "SELECT rollout_path FROM threads WHERE id = ?", (thread_id,)
                ).fetchone()
        except sqlite3.Error:
            row = None
        if row and row[0]:
            path = Path(row[0])
            if path.is_file():
                return path

    matches = list(_CODEX_SESSIONS_ROOT.rglob(f"*{thread_id}.jsonl"))
    return matches[0] if matches else None


def _codex_project_sessions(cwd: Path) -> list[tuple[str, Path]]:
    """Return indexed Codex rollouts whose workspace exactly matches cwd."""
    if not _CODEX_STATE_DB.exists():
        return []
    try:
        with sqlite3.connect(f"file:{_CODEX_STATE_DB}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT id, rollout_path FROM threads WHERE cwd = ?", (str(cwd),)
            ).fetchall()
    except sqlite3.Error:
        return []
    return [
        (thread_id, Path(rollout_path))
        for thread_id, rollout_path in rows
        if rollout_path and Path(rollout_path).is_file()
    ]


@mcp.tool()
def current_session_energy() -> dict:
    """Estimated energy (Wh) and CO2eq for the calling Codex session."""
    thread_id = os.environ.get("CODEX_THREAD_ID")
    if not thread_id:
        return {"error": "CODEX_THREAD_ID is not set."}

    session_file = _find_codex_thread_file(thread_id)
    if not session_file:
        return {"error": f"No Codex session log found for thread {thread_id}."}

    request_count, wh = estimate_session_from_file(session_file, "codex")
    return session_energy_result("codex", thread_id, session_file, request_count, wh)


@mcp.tool()
def collate_project_sessions_energy() -> dict:
    """Total + per-session energy and CO2eq for every Codex thread in the current project."""
    sessions = []
    total_wh = 0.0
    for thread_id, session_file in _codex_project_sessions(Path.cwd()):
        request_count, wh = estimate_session_from_file(session_file, "codex")
        sessions.append({"session_id": thread_id, "request_count": request_count, "estimated_wh": round(wh, 3)})
        total_wh += wh

    if not sessions:
        return {"error": "Could not find Codex sessions for the current project."}

    return collated_energy_result("codex", Path.cwd(), sessions, total_wh)


if __name__ == "__main__":
    mcp.run()
