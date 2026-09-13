import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from mcps.claude_sessions import (
    claude_project_dir_for_cwd,
    claude_project_dir_for_session,
    find_claude_session_file,
    list_claude_project_sessions,
    slugify_cwd,
)


def _write_session(path):
    path.write_text(
        json.dumps({"requestId": "request", "message": {"usage": {"input_tokens": 100, "output_tokens": 10}}}),
        encoding="utf-8",
    )


class ClaudeSessionsTests(unittest.TestCase):
    def test_find_claude_session_file_hit_and_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            projects_root = Path(directory)
            project_dir = projects_root / "project"
            project_dir.mkdir()
            session_file = project_dir / "thread.jsonl"
            _write_session(session_file)

            self.assertEqual(find_claude_session_file("thread", projects_root), session_file)
            self.assertIsNone(find_claude_session_file("missing", projects_root))

    def test_slugify_cwd_replaces_non_alphanumeric_characters(self):
        self.assertEqual(slugify_cwd("/Users/you/my-project"), "-Users-you-my-project")

    def test_claude_project_dir_for_cwd_hit_and_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            projects_root = Path(directory)
            cwd = "/Users/you/my-project"
            project_dir = projects_root / slugify_cwd(cwd)
            project_dir.mkdir()

            self.assertEqual(claude_project_dir_for_cwd(cwd, projects_root), project_dir)
            self.assertIsNone(claude_project_dir_for_cwd("/no/such/project", projects_root))

    def test_claude_project_dir_for_session_hit_and_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            projects_root = Path(directory)
            project_dir = projects_root / "project"
            project_dir.mkdir()
            _write_session(project_dir / "thread.jsonl")

            self.assertEqual(claude_project_dir_for_session("thread", projects_root), project_dir)
            self.assertIsNone(claude_project_dir_for_session("missing", projects_root))

    def test_list_claude_project_sessions_sorts_most_recent_first(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            older = project_dir / "older.jsonl"
            newer = project_dir / "newer.jsonl"
            _write_session(older)
            _write_session(newer)

            now = time.time()
            os.utime(older, (now - 100, now - 100))
            os.utime(newer, (now, now))

            self.assertEqual(list_claude_project_sessions(project_dir), [newer, older])


if __name__ == "__main__":
    unittest.main()
