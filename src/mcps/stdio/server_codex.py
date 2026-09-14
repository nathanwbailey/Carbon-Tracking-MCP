"""
stdio MCP server exposing mcps.energy_estimate's session energy model for
Codex sessions.

Session discovery
------------------
Codex clients must first obtain their active task ID from the Codex task
registry and pass it as ``params.codex_thread_id``. That is the reliable way
to identify "the calling chat". Codex does not reliably set CODEX_THREAD_ID
or a similar identifier for MCP stdio subprocesses, so the server checks that
environment variable only after the explicit ID. Finally, it falls back to the
most-recently-modified indexed thread whose recorded cwd matches this
process's cwd. That last heuristic can pick the wrong thread when multiple
Codex chats share a directory.

"Current project" scoping for collate_project_sessions_energy(): every
indexed thread whose recorded cwd exactly matches the current working
directory.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcps import codex_sessions
from mcps.energy_estimate import estimate_session_from_file
from mcps.mcp_results import collated_energy_result, session_energy_result
from mcps.schema import CollatedEnergyResult, CurrentSessionEnergyInput, SessionEnergyResult, SessionSummary

mcp = FastMCP("carbon-tracking-energy-codex")


@mcp.tool()
def current_session_energy(params: CurrentSessionEnergyInput | None = None) -> SessionEnergyResult:
    """Estimate this Codex task's energy and CO2eq.

    Codex clients must retrieve the active task ID before invoking this tool
    and pass it as ``params.codex_thread_id``. This explicit ID is always
    tried first. The server uses CODEX_THREAD_ID and then a cwd-based guess
    only if the caller cannot provide one.

    Call this proactively whenever the user asks about this chat's energy or
    carbon footprint -- don't wait for them to say "use the MCP".
    """
    params = params or CurrentSessionEnergyInput()
    thread_id = params.codex_thread_id or os.environ.get("CODEX_THREAD_ID")
    if thread_id:
        session_file = codex_sessions.find_codex_thread_file(
            thread_id, codex_sessions.CODEX_STATE_DB, codex_sessions.CODEX_SESSIONS_ROOT
        )
        if not session_file:
            raise ToolError(f"No Codex session log found for thread {thread_id}.")
    else:
        candidates = codex_sessions.codex_project_sessions(Path.cwd(), codex_sessions.CODEX_STATE_DB)
        if not candidates:
            raise ToolError(
                "No codex_thread_id was given, CODEX_THREAD_ID is not set, and no indexed Codex threads "
                f"have a recorded cwd matching {Path.cwd()}, so the calling session could not be identified."
            )
        thread_id, session_file = max(candidates, key=lambda pair: pair[1].stat().st_mtime)

    request_count, wh = estimate_session_from_file(session_file, "codex")
    return session_energy_result("codex", thread_id, session_file, request_count, wh)


@mcp.tool()
def collate_project_sessions_energy() -> CollatedEnergyResult:
    """Total + per-session energy and CO2eq for every Codex thread in the current project.

    Call this proactively whenever the user asks about this project's total
    energy or carbon footprint -- don't wait for them to say "use the MCP".
    """
    sessions = []
    total_wh = 0.0
    for thread_id, session_file in codex_sessions.codex_project_sessions(Path.cwd(), codex_sessions.CODEX_STATE_DB):
        request_count, wh = estimate_session_from_file(session_file, "codex")
        sessions.append(
            SessionSummary(session_id=thread_id, request_count=request_count, estimated_kwh=round(wh / 1000, 3))
        )
        total_wh += wh

    if not sessions:
        raise ToolError("Could not find Codex sessions for the current project.")

    return collated_energy_result("codex", Path.cwd(), sessions, total_wh)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
