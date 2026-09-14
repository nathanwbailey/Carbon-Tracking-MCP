"""
Typed pydantic models for every value that crosses an mcps MCP tool boundary
-- both so FastMCP generates a real, field-described JSON schema for clients,
and so internal callers get static typing instead of untyped dicts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CurrentSessionEnergyInput(BaseModel):
    codex_thread_id: str | None = Field(
        default=None,
        description=(
            "The active Codex task's ID. Codex clients must retrieve their current task ID before calling "
            "current_session_energy and pass it here; this is the first and most reliable identification method. "
            "Leave unset only when the client genuinely cannot obtain its task ID, in which case the server uses "
            "environment and working-directory fallbacks."
        ),
    )


class CO2Comparison(BaseModel):
    id: str = Field(
        description="Stable identifier for the comparison activity (matches an entry in carbon_equivalents.json)."
    )
    label: str = Field(description="Human-readable label for the comparison activity, e.g. 'washing machine cycle'.")
    count: float = Field(description="How many of this activity the estimated CO2eq is equivalent to.")


class CO2Summary(BaseModel):
    estimated_kg_co2: float = Field(
        description="Estimated CO2-equivalent emissions for the given energy figure, in kilograms."
    )
    comparisons: list[CO2Comparison] = Field(description="Everyday-activity equivalents for the estimated CO2eq.")


class SessionSummary(BaseModel):
    session_id: str = Field(description="Claude Code session ID or Codex thread ID for this session.")
    request_count: int = Field(description="Number of deduplicated API requests/turns in this session.")
    estimated_kwh: float = Field(description="Estimated energy used by this session, in kilowatt-hours.")


class SessionEnergyResult(BaseModel):
    provider: str = Field(description="Coding-agent provider this session belongs to ('claude' or 'codex').")
    session_id: str = Field(description="Claude Code session ID or Codex thread ID being reported on.")
    file: str = Field(description="Absolute path to the session's local log file that was parsed.")
    request_count: int = Field(description="Number of deduplicated API requests/turns in this session.")
    estimated_kwh: float = Field(description="Estimated energy used by this session, in kilowatt-hours.")
    estimated_kg_co2: float = Field(description="Estimated CO2-equivalent emissions for this session, in kilograms.")
    comparisons: list[CO2Comparison] = Field(
        description="Everyday-activity equivalents for this session's estimated CO2eq."
    )


class CollatedEnergyResult(BaseModel):
    provider: str = Field(description="Coding-agent provider these sessions belong to ('claude' or 'codex').")
    project_dir: str = Field(description="Absolute path to the project's session-log directory that was scanned.")
    session_count: int = Field(description="Number of sessions included in this total.")
    total_estimated_kwh: float = Field(
        description="Total estimated energy across all included sessions, in kilowatt-hours."
    )
    sessions: list[SessionSummary] = Field(description="Per-session breakdown of request count and estimated energy.")
    estimated_kg_co2: float = Field(description="Estimated CO2-equivalent emissions for the total, in kilograms.")
    comparisons: list[CO2Comparison] = Field(description="Everyday-activity equivalents for the total estimated CO2eq.")
