import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server_codex


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

            with mock.patch.object(server_codex, "_CODEX_STATE_DB", db), mock.patch.dict(
                os.environ, {"CODEX_THREAD_ID": "thread"}, clear=True
            ):
                result = server_codex.current_session_energy()

            self.assertEqual(result["provider"], "codex")
            self.assertEqual(result["session_id"], "thread")
            self.assertEqual(result["request_count"], 1)
            self.assertIn("estimated_kg_co2", result)
            self.assertIn("comparisons", result)

    def test_current_session_energy_errors_without_env_var(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            result = server_codex.current_session_energy()

        self.assertIn("error", result)

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

            with mock.patch.object(server_codex, "_CODEX_STATE_DB", db), mock.patch.object(
                server_codex.Path, "cwd", return_value=tmp_path
            ), mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "current"}, clear=True):
                result = server_codex.collate_project_sessions_energy()

            self.assertEqual(result["provider"], "codex")
            self.assertEqual(result["session_count"], 1)
            self.assertEqual(result["sessions"][0]["session_id"], "current")
            self.assertIn("estimated_kg_co2", result)


if __name__ == "__main__":
    unittest.main()
