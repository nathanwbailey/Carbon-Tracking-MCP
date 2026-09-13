import json
import tempfile
import unittest
from pathlib import Path

from mcps.energy_estimate import estimate_request_energy_wh, estimate_session_from_file, load_codex_session


class CodexSessionTests(unittest.TestCase):
    def test_claude_provider_remains_default(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "session.jsonl"
            log.write_text(
                json.dumps(
                    {
                        "requestId": "request",
                        "message": {
                            "usage": {"input_tokens": 100, "output_tokens": 10},
                        },
                    }
                ),
                encoding="utf-8",
            )

            count, wh = estimate_session_from_file(log)

            self.assertEqual(count, 1)
            self.assertAlmostEqual(wh, estimate_request_energy_wh(100, 10))

    def test_load_codex_session_splits_cached_input_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "rollout.jsonl"
            records = [
                {"type": "not_usage", "payload": {}},
                {
                    "type": "token_usage_record",
                    "payload": {
                        "response_id": "first",
                        "usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 40,
                            "output_tokens": 10,
                            "reasoning_output_tokens": 7,
                        },
                    },
                },
                {
                    "type": "token_usage_record",
                    "payload": {
                        "response_id": "first",
                        "usage": {
                            "input_tokens": 120,
                            "cached_input_tokens": 50,
                            "cache_write_input_tokens": 15,
                            "output_tokens": 20,
                        },
                    },
                },
                {
                    "type": "token_usage_record",
                    "payload": {
                        "response_id": "second",
                        "usage": {"input_tokens": 25, "cached_input_tokens": 30, "output_tokens": 5},
                    },
                },
            ]
            log.write_text("not json\n" + "\n".join(json.dumps(record) for record in records), encoding="utf-8")

            self.assertEqual(
                load_codex_session(log),
                [
                    {
                        "model": None,
                        "input_tokens": 70,
                        "output_tokens": 20,
                        "cache_read_tokens": 50,
                        "cache_write_5m_tokens": 15,
                        "cache_write_1h_tokens": 0,
                    },
                    {
                        "model": None,
                        "input_tokens": 0,
                        "output_tokens": 5,
                        "cache_read_tokens": 30,
                        "cache_write_5m_tokens": 0,
                        "cache_write_1h_tokens": 0,
                    },
                ],
            )

    def test_codex_estimate_does_not_double_count_reasoning_output(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "rollout.jsonl"
            log.write_text(
                json.dumps(
                    {
                        "type": "token_usage_record",
                        "payload": {
                            "response_id": "response",
                            "usage": {
                                "input_tokens": 1_000_000,
                                "cached_input_tokens": 500_000,
                                "cache_write_input_tokens": 250_000,
                                "output_tokens": 1_000_000,
                                "reasoning_output_tokens": 900_000,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            count, wh = estimate_session_from_file(log, "codex")

            self.assertEqual(count, 1)
            self.assertAlmostEqual(
                wh,
                estimate_request_energy_wh(
                    input_tokens=500_000,
                    cache_read_tokens=500_000,
                    cache_write_5m_tokens=250_000,
                    output_tokens=1_000_000,
                ),
            )
