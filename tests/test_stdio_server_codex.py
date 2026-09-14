import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastmcp.exceptions import ToolError

from mcps import codex_sessions
from mcps.schema import CurrentSessionEnergyInput
from mcps.stdio import server_codex


def _write_rollout(path, response_id):
    path.write_text(
        json.dumps(
            {
                "type": "token_usage_record",
                "payload": {
                    "response_id": response_id,
                    "usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 25,
                        "output_tokens": 10,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def _create_thread_db(path, rows):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, cwd TEXT, rollout_path TEXT)")
        conn.executemany("INSERT INTO threads VALUES (?, ?, ?)", rows)


class CodexServerTests(unittest.TestCase):
    def test_current_session_energy_reads_codex_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            rollout = tmp_path / "rollout-thread.jsonl"
            _write_rollout(rollout, "response")
            db = tmp_path / "state.sqlite"
            _create_thread_db(db, [("thread", str(tmp_path), str(rollout))])

            with (
                mock.patch.object(codex_sessions, "CODEX_STATE_DB", db),
                mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "thread"}, clear=True),
            ):
                result = server_codex.current_session_energy()

            self.assertEqual(result.provider, "codex")
            self.assertEqual(result.session_id, "thread")
            self.assertEqual(result.request_count, 1)
            self.assertIsInstance(result.estimated_kg_co2, float)
            self.assertTrue(result.comparisons)

    def test_current_session_energy_prefers_explicit_thread_id_over_env_and_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            wanted = tmp_path / "wanted.jsonl"
            other = tmp_path / "other.jsonl"
            _write_rollout(wanted, "wanted")
            _write_rollout(other, "other")
            db = tmp_path / "state.sqlite"
            _create_thread_db(
                db,
                [
                    ("wanted", str(tmp_path), str(wanted)),
                    ("other", str(tmp_path), str(other)),
                ],
            )

            with (
                mock.patch.object(codex_sessions, "CODEX_STATE_DB", db),
                mock.patch.object(Path, "cwd", return_value=tmp_path),
                mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "other"}, clear=True),
            ):
                result = server_codex.current_session_energy(CurrentSessionEnergyInput(codex_thread_id="wanted"))

            self.assertEqual(result.session_id, "wanted")

    def test_current_session_energy_input_allows_a_missing_id_for_fallbacks(self):
        """Clients may omit the ID only when they cannot obtain the active task ID."""
        self.assertIsNone(CurrentSessionEnergyInput().codex_thread_id)

    def test_current_session_energy_falls_back_to_cwd_when_env_var_unset(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            rollout = tmp_path / "rollout-thread.jsonl"
            _write_rollout(rollout, "response")
            db = tmp_path / "state.sqlite"
            _create_thread_db(db, [("thread", str(tmp_path), str(rollout))])

            with (
                mock.patch.object(codex_sessions, "CODEX_STATE_DB", db),
                mock.patch.object(Path, "cwd", return_value=tmp_path),
                mock.patch.dict(os.environ, {}, clear=True),
            ):
                result = server_codex.current_session_energy()

            self.assertEqual(result.session_id, "thread")

    def test_current_session_energy_errors_without_env_var_or_cwd_match(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            db = tmp_path / "does-not-exist.sqlite"

            with (
                mock.patch.object(codex_sessions, "CODEX_STATE_DB", db),
                mock.patch.dict(os.environ, {}, clear=True),
                self.assertRaises(ToolError),
            ):
                server_codex.current_session_energy()

    def test_collate_project_sessions_uses_only_current_codex_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            current = tmp_path / "current.jsonl"
            other = tmp_path / "other.jsonl"
            _write_rollout(current, "current")
            _write_rollout(other, "other")
            db = tmp_path / "state.sqlite"
            _create_thread_db(
                db,
                [
                    ("current", str(tmp_path), str(current)),
                    ("other", "/another-project", str(other)),
                ],
            )

            with (
                mock.patch.object(codex_sessions, "CODEX_STATE_DB", db),
                mock.patch.object(Path, "cwd", return_value=tmp_path),
                mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "current"}, clear=True),
            ):
                result = server_codex.collate_project_sessions_energy()

            self.assertEqual(result.provider, "codex")
            self.assertEqual(result.session_count, 1)
            self.assertEqual(result.sessions[0].session_id, "current")
            self.assertIsInstance(result.estimated_kg_co2, float)


if __name__ == "__main__":
    unittest.main()
