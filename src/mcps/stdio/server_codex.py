"""
stdio MCP server exposing mcps.energy_estimate's session energy model for
Codex sessions.

Session discovery
------------------
Codex sets CODEX_THREAD_ID in the environment of processes it launches
(including this server, when run locally via stdio). That thread ID is
looked up via mcps.codex_sessions against Codex's local thread index
(~/.codex/state_5.sqlite), falling back to a filename scan under
~/.codex/sessions if the DB lookup fails or the thread isn't indexed yet.

"Current project" scoping for collate_project_sessions_energy(): every
indexed thread whose recorded cwd exactly matches the current working
directory.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastmcp import FastMCP

from mcps import codex_sessions
from mcps.energy_estimate import estimate_session_from_file
from mcps.mcp_results import collated_energy_result, session_energy_result

mcp = FastMCP("carbon-tracking-energy-codex")


@mcp.tool()
def current_session_energy() -> dict:
    """Estimated energy (Wh) and CO2eq for the calling Codex session."""
    thread_id = os.environ.get("CODEX_THREAD_ID")
    if not thread_id:
        return {"error": "CODEX_THREAD_ID is not set."}

    session_file = codex_sessions.find_codex_thread_file(
        thread_id, codex_sessions.CODEX_STATE_DB, codex_sessions.CODEX_SESSIONS_ROOT
    )
    if not session_file:
        return {"error": f"No Codex session log found for thread {thread_id}."}

    request_count, wh = estimate_session_from_file(session_file, "codex")
    return session_energy_result("codex", thread_id, session_file, request_count, wh)


@mcp.tool()
def collate_project_sessions_energy() -> dict:
    """Total + per-session energy and CO2eq for every Codex thread in the current project."""
    sessions = []
    total_wh = 0.0
    for thread_id, session_file in codex_sessions.codex_project_sessions(Path.cwd(), codex_sessions.CODEX_STATE_DB):
        request_count, wh = estimate_session_from_file(session_file, "codex")
        sessions.append({"session_id": thread_id, "request_count": request_count, "estimated_wh": round(wh, 3)})
        total_wh += wh

    if not sessions:
        return {"error": "Could not find Codex sessions for the current project."}

    return collated_energy_result("codex", Path.cwd(), sessions, total_wh)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
