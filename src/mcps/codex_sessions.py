"""
Session discovery helpers for Codex (~/.codex/state_5.sqlite +
~/.codex/sessions/**/*.jsonl).

No environment-variable reads happen in this module -- callers resolve a
thread_id or cwd from whatever source fits their transport and pass it in.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

CODEX_HOME = Path.home() / ".codex"
CODEX_STATE_DB = CODEX_HOME / "state_5.sqlite"
CODEX_SESSIONS_ROOT = CODEX_HOME / "sessions"


def find_codex_thread_file(thread_id: str, state_db: Path, sessions_root: Path) -> Path | None:
    """Look up a Codex rollout by thread ID, then fall back to its filename."""
    if state_db.exists():
        try:
            with sqlite3.connect(f"file:{state_db}?mode=ro", uri=True) as conn:
                row = conn.execute("SELECT rollout_path FROM threads WHERE id = ?", (thread_id,)).fetchone()
        except sqlite3.Error:
            row = None
        if row and row[0]:
            path = Path(row[0])
            if path.is_file():
                return path

    matches = list(sessions_root.rglob(f"*{thread_id}.jsonl"))
    return matches[0] if matches else None


def codex_project_sessions(cwd: Path | str, state_db: Path) -> list[tuple[str, Path]]:
    """Return indexed Codex rollouts whose workspace exactly matches cwd."""
    if not state_db.exists():
        return []
    try:
        with sqlite3.connect(f"file:{state_db}?mode=ro", uri=True) as conn:
            rows = conn.execute("SELECT id, rollout_path FROM threads WHERE cwd = ?", (str(cwd),)).fetchall()
    except sqlite3.Error:
        return []
    return [
        (thread_id, Path(rollout_path))
        for thread_id, rollout_path in rows
        if rollout_path and Path(rollout_path).is_file()
    ]
