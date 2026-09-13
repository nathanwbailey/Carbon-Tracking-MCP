"""
claude_energy_estimate.py

Pricing-ratio energy model for a Claude Code coding-agent session,
following Simon P. Couch's methodology:

    https://simonpcouch.com/blog/2026-01-20-cc-impact/

METHOD

Couch derived three (context_length -> input_wh_per_mtok) anchor points
from Epoch AI's ChatGPT-4o energy estimates.
We added 500K-token context as a fourth anchor point, based on code from EpochAI: https://colab.research.google.com/drive/1dnhL0lkjsk-isAH-j02pFUbv1g12hEm1#scrollTo=dN0Ezyr4qXAQ

We are assuming that one is smart and keeps context window at roughly half the max context length of the model (1M tokens). The anchor points are:

    context_tokens   input_wh_per_mtok   output_wh_per_mtok
    ~130                    110                 540
    ~10,000                 200                 990
    ~100,000                390                1,950
    ~500,000               1,267               6,336

This module uses the 500K-token anchor directly (input_wh_per_mtok=1,267,
output_wh_per_mtok=6,336) as a fixed rate for every request, on the
assumption that a well-managed agent session runs at roughly that context
length -- rather than fitting a power law across the anchor points and
extrapolating to other context lengths.

Cache-read and cache-write rates aren't in Couch's anchor data, so they're
derived from that fixed input rate using the same napkin-math logic Couch
used for output tokens (price ratio -> energy ratio), with a single
universal ratio (no per-model pricing table):

    Anthropic prices cache reads at ~1/10th the cost of input tokens, and
    cache writes at a ~25% premium over input tokens.

    cache_read_wh_per_mtok  = input_wh_per_mtok * 0.10
    cache_write_wh_per_mtok = input_wh_per_mtok * 1.25

CAVEATS (read before trusting any number this script produces):
  - "Energy scales with price" is a guess, not a measurement
  - The cache-read/cache-write ratios above are a single flat napkin-math
    approximation, not per-model pricing -- actual cache pricing varies
    by model and by cache TTL (5-minute vs. 1-hour) on the real Anthropic
    pricing table; this module intentionally ignores that variation.
  - Using a single 500K-anchor rate for every request means very short
    requests (few-hundred-token) are overestimated and very long ones
    (approaching 1M tokens) are underestimated relative to Couch's own
    context-scaled anchors above.

DATA SOURCES

Claude Code JSONL files under ~/.claude/projects/**/*.jsonl, normalized to
a per-request shape (model, input_tokens, output_tokens, cache_read_tokens,
cache_write_5m_tokens, cache_write_1h_tokens). Cache writes are split by
TTL where the log provides it (usage.cache_creation.ephemeral_5m_input_tokens
/ ephemeral_1h_input_tokens); older logs without that breakdown are assumed
to be 5m-tier.

Codex rollout JSONL files under ~/.codex/sessions/**/*.jsonl record a
``token_usage_record`` for each model response. Codex's ``input_tokens``
includes ``cached_input_tokens``, so the parser splits it into ordinary input
and cache reads before using the shared energy model. Codex reports cache
writes as ``cache_write_input_tokens`` without a TTL, so they use the same
5-minute fallback as older Claude Code logs.

Use this for order-of-magnitude, directional comparisons only -- not as
an audited carbon/energy figure.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from mcps.carbon_equivalents import co2_summary

# --- Fixed rates, anchored at 500K-token context ---------------------------
# Our 500K-context anchor point, used directly (no power-law fit/
# extrapolation, no per-model pricing table -- see module docstring).
_INPUT_WH_PER_MTOK = 1_267.0
_OUTPUT_WH_PER_MTOK = 6_336.0

# Cache pricing ratios, applied to the input rate (see module docstring):
# Anthropic prices cache reads at ~1/10th the cost of input tokens, and
# cache writes at a ~25% premium over input tokens. A single ratio is used
# for both cache-write TTL tiers (5m/1h) -- no per-model differentiation.
_CACHE_READ_RATIO = 0.10
_CACHE_WRITE_RATIO = 1.25

_CACHE_READ_WH_PER_MTOK = _INPUT_WH_PER_MTOK * _CACHE_READ_RATIO
_CACHE_WRITE_WH_PER_MTOK = _INPUT_WH_PER_MTOK * _CACHE_WRITE_RATIO


@dataclass
class EnergyRates:
    input: float = _INPUT_WH_PER_MTOK
    output: float = _OUTPUT_WH_PER_MTOK
    cache_read: float = _CACHE_READ_WH_PER_MTOK
    cache_write: float = _CACHE_WRITE_WH_PER_MTOK


def estimate_request_energy_wh(
    input_tokens: int,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_5m_tokens: int = 0,
    cache_write_1h_tokens: int = 0,
) -> float:
    """Energy (Wh) for one API request/turn, using fixed rates anchored at
    500K-token context (see module docstring) -- the same rates for every
    request, regardless of its actual context length or model."""
    cache_write_tokens = cache_write_5m_tokens + cache_write_1h_tokens
    rates = EnergyRates()
    return (
        input_tokens * rates.input
        + output_tokens * rates.output
        + cache_read_tokens * rates.cache_read
        + cache_write_tokens * rates.cache_write
    ) / 1_000_000


def estimate_session_energy_wh(requests: list[dict]) -> float:
    """Sum per-request energy over a list of dicts as produced by
    load_claude_code_session()."""
    return sum(
        estimate_request_energy_wh(
            input_tokens=r.get("input_tokens", 0),
            output_tokens=r.get("output_tokens", 0),
            cache_read_tokens=r.get("cache_read_tokens", 0),
            cache_write_5m_tokens=r.get("cache_write_5m_tokens", 0),
            cache_write_1h_tokens=r.get("cache_write_1h_tokens", 0),
        )
        for r in requests
    )


# --- Claude Code (JSONL) -------------------------------------------------


def load_claude_code_session(path: str | Path) -> list[dict]:
    """Parse a Claude Code JSONL session log (~/.claude/projects/**/*.jsonl),
    deduplicating streamed events by requestId (multiple stream events
    share identical token counts per request).

    Extracts the model name and, where available, the TTL breakdown of
    cache-creation tokens (usage.cache_creation.ephemeral_5m_input_tokens /
    ephemeral_1h_input_tokens). Older logs without that breakdown have
    their whole cache_creation_input_tokens total treated as 5m-tier.
    """
    seen: dict[str, dict] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = entry.get("message") or {}
            usage = message.get("usage") or entry.get("usage")
            request_id = entry.get("requestId") or entry.get("request_id")
            if not usage or not request_id:
                continue

            cache_creation = usage.get("cache_creation")
            if cache_creation:
                write_5m = cache_creation.get("ephemeral_5m_input_tokens", 0)
                write_1h = cache_creation.get("ephemeral_1h_input_tokens", 0)
            else:
                write_5m = usage.get("cache_creation_input_tokens", 0)
                write_1h = 0

            seen[request_id] = {
                "model": message.get("model") or entry.get("model"),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
                "cache_write_5m_tokens": write_5m,
                "cache_write_1h_tokens": write_1h,
            }
    return list(seen.values())


def load_codex_session(path: str | Path) -> list[dict]:
    """Parse a Codex rollout JSONL session log into normalized requests.

    ``usage`` is response-local. The accompanying turn/thread totals are
    cumulative snapshots and must not be summed. ``input_tokens`` includes
    cached input, so cached tokens are represented as cache reads instead.
    """
    seen: dict[str, dict] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "token_usage_record":
                continue
            payload = entry.get("payload") or {}
            usage = payload.get("usage") or {}
            response_id = payload.get("response_id")
            if not usage or not response_id:
                continue
            input_tokens = usage.get("input_tokens", 0)
            cached_input_tokens = usage.get("cached_input_tokens", 0)
            cache_write_tokens = usage.get("cache_write_input_tokens", 0)
            seen[response_id] = {
                "model": payload.get("model"),
                "input_tokens": max(0, input_tokens - cached_input_tokens),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_read_tokens": cached_input_tokens,
                "cache_write_5m_tokens": cache_write_tokens,
                "cache_write_1h_tokens": 0,
            }
    return list(seen.values())


def load_session(path: str | Path, provider: str = "claude") -> list[dict]:
    """Load normalized token requests for a supported coding-agent provider."""
    if provider == "claude":
        return load_claude_code_session(path)
    if provider == "codex":
        return load_codex_session(path)
    raise ValueError(f"Unsupported session provider: {provider}")


def estimate_session_from_file(path: str | Path, provider: str = "claude") -> tuple[int, float]:
    """Parse one provider session file and return (request_count, estimated_wh)."""
    requests = load_session(path, provider)
    return len(requests), estimate_session_energy_wh(requests)


def find_claude_code_sessions(base_dir: str | Path | None = None) -> list[Path]:
    """List Claude Code session JSONL files under ~/.claude/projects (or a
    given base dir), most-recently-modified first."""
    base = Path(base_dir) if base_dir else Path.home() / ".claude" / "projects"
    if not base.exists():
        return []
    files = list(base.rglob("*.jsonl"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_jsonl", help="Path to a Claude Code session .jsonl file")
    parser.add_argument(
        "--provider",
        choices=("claude", "codex"),
        default="claude",
        help="Session-log provider (default: claude)",
    )
    args = parser.parse_args()

    n, wh = estimate_session_from_file(args.session_jsonl, args.provider)
    print(f"{n} deduplicated requests")
    print(f"Estimated session energy: {wh:.1f} Wh")

    summary = co2_summary(wh)
    print(f"Estimated CO2eq: {summary.estimated_kg_co2:.3f} kg (UK grid average)")
    for comparison in summary.comparisons:
        print(f"  ~ {comparison.count:g} x {comparison.label}")


if __name__ == "__main__":
    main()
