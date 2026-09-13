import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from mcps.codex_sessions import codex_project_sessions, find_codex_thread_file


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


class CodexSessionsTests(unittest.TestCase):
    def test_find_codex_thread_file_uses_sqlite_index(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            rollout = tmp_path / "rollout-thread.jsonl"
            _write_rollout(rollout, "response")
            db = tmp_path / "state.sqlite"
            sessions_root = tmp_path / "sessions"
            sessions_root.mkdir()
            _create_thread_db(db, [("thread", str(tmp_path), str(rollout))])

            self.assertEqual(find_codex_thread_file("thread", db, sessions_root), rollout)

    def test_find_codex_thread_file_falls_back_to_filename_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            db = tmp_path / "state.sqlite"
            sessions_root = tmp_path / "sessions"
            sessions_root.mkdir()
            rollout = sessions_root / "rollout-unindexed-thread.jsonl"
            _write_rollout(rollout, "response")

            self.assertEqual(find_codex_thread_file("unindexed-thread", db, sessions_root), rollout)

    def test_find_codex_thread_file_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            db = tmp_path / "state.sqlite"
            sessions_root = tmp_path / "sessions"
            sessions_root.mkdir()

            self.assertIsNone(find_codex_thread_file("missing", db, sessions_root))

    def test_codex_project_sessions_matches_only_given_cwd(self):
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

            results = codex_project_sessions(tmp_path, db)

            self.assertEqual(results, [("current", current)])

    def test_codex_project_sessions_missing_db_returns_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            db = tmp_path / "missing.sqlite"

            self.assertEqual(codex_project_sessions(tmp_path, db), [])


if __name__ == "__main__":
    unittest.main()
