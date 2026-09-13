import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastmcp.exceptions import ToolError

from mcps import claude_sessions
from mcps.stdio import server_claude


class ClaudeServerTests(unittest.TestCase):
    def test_current_session_energy_preserves_claude_response(self):
        with tempfile.TemporaryDirectory() as directory:
            projects_root = Path(directory)
            project_dir = projects_root / "project"
            project_dir.mkdir()
            session_file = project_dir / "claude-thread.jsonl"
            session_file.write_text(
                json.dumps(
                    {
                        "requestId": "request",
                        "message": {"usage": {"input_tokens": 100, "output_tokens": 10}},
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(claude_sessions, "CLAUDE_PROJECTS_ROOT", projects_root),
                mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "claude-thread"}, clear=True),
            ):
                result = server_claude.current_session_energy()

            self.assertEqual(result.provider, "claude")
            self.assertEqual(result.session_id, "claude-thread")
            self.assertEqual(result.request_count, 1)
            self.assertIsInstance(result.estimated_kg_co2, float)
            self.assertTrue(result.comparisons)

    def test_current_session_energy_errors_without_env_var(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(ToolError):
            server_claude.current_session_energy()

    def test_collate_project_sessions_energy_sums_project_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            projects_root = Path(directory)
            project_dir = projects_root / "project"
            project_dir.mkdir()
            for name in ("one", "two"):
                (project_dir / f"{name}.jsonl").write_text(
                    json.dumps(
                        {
                            "requestId": name,
                            "message": {"usage": {"input_tokens": 100, "output_tokens": 10}},
                        }
                    ),
                    encoding="utf-8",
                )

            with (
                mock.patch.object(claude_sessions, "CLAUDE_PROJECTS_ROOT", projects_root),
                mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "one"}, clear=True),
            ):
                result = server_claude.collate_project_sessions_energy()

            self.assertEqual(result.provider, "claude")
            self.assertEqual(result.session_count, 2)
            self.assertIsInstance(result.estimated_kg_co2, float)


if __name__ == "__main__":
    unittest.main()
