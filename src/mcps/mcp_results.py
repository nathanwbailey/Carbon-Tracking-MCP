"""
Shared MCP tool-result shaping for the Claude Code and Codex energy servers.

server_claude.py and server_codex.py discover sessions completely
differently (JSONL glob under ~/.claude/projects vs. a sqlite thread-index
lookup under ~/.codex), but once each has a (request_count, wh) pair or a
list of already-shaped SessionSummary models, the response shape they
build is identical -- this module is the one place that shape is defined,
so the two providers can't drift apart from each other.
"""

from __future__ import annotations

from pathlib import Path

from mcps.carbon_equivalents import co2_summary
from mcps.schema import CollatedEnergyResult, SessionEnergyResult, SessionSummary


def session_energy_result(
    provider: str, session_id: str, file: Path, request_count: int, wh: float
) -> SessionEnergyResult:
    summary = co2_summary(wh)
    return SessionEnergyResult(
        provider=provider,
        session_id=session_id,
        file=str(file),
        request_count=request_count,
        estimated_kwh=round(wh / 1000, 3),
        estimated_kg_co2=summary.estimated_kg_co2,
        comparisons=summary.comparisons,
    )


def collated_energy_result(
    provider: str, project_dir: Path, sessions: list[SessionSummary], total_wh: float
) -> CollatedEnergyResult:
    summary = co2_summary(total_wh)
    return CollatedEnergyResult(
        provider=provider,
        project_dir=str(project_dir),
        session_count=len(sessions),
        total_estimated_kwh=round(total_wh / 1000, 3),
        sessions=sessions,
        estimated_kg_co2=summary.estimated_kg_co2,
        comparisons=summary.comparisons,
    )
