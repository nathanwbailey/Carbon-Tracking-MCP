# Carbon Tracking MCP

MCP servers that estimate the energy used by your Claude Code and Codex sessions, so you can ask for it directly from within a chat: "how much energy has this chat used?" or "how much has this whole project cost?"

They wrap a small pricing-ratio energy model (`src/mcps/energy_estimate.py`) around each tool's local session logs — no telemetry, no network calls. The Claude Code server reads `~/.claude/projects/**/*.jsonl`; the Codex server reads Codex's local thread index (`~/.codex/state_5.sqlite`) and rollout logs under `~/.codex/sessions/`. Both run over the stdio MCP transport (`src/mcps/stdio/`), spawned fresh per chat by Claude Code/Codex.

## What it does

Each server exposes the same two MCP tools, scoped to its own provider:

| Tool | Answers |
|---|---|
| `current_session_energy` | How much energy has *this* chat used so far? |
| `collate_project_sessions_energy` | How much energy has *every* chat in this project used, in total? |

Example output:

```json
{
  "session_id": "afc721a3-0d77-4c5f-b1f5-24074d03fa7d",
  "file": "/Users/you/.claude/projects/-Users-you-my-project/afc721a3-....jsonl",
  "request_count": 60,
  "estimated_kwh": 1.018,
  "estimated_kg_co2": 0.144,
  "comparisons": [
    {"id": "washing_machine_cycle", "label": "washing machine cycle", "count": 0.14},
    {"id": "kettle_boil", "label": "kettle boil", "count": 1.44}
  ]
}
```

```json
{
  "project_dir": "/Users/you/.claude/projects/-Users-you-my-project",
  "session_count": 3,
  "total_estimated_kwh": 1.545,
  "sessions": [
    {"session_id": "afc721a3-...", "request_count": 60, "estimated_kwh": 1.018},
    {"session_id": "8ee8cb6f-...", "request_count": 5, "estimated_kwh": 0.073},
    {"session_id": "2aabc643-...", "request_count": 38, "estimated_kwh": 0.86}
  ],
  "estimated_kg_co2": 0.218,
  "comparisons": [
    {"id": "washing_machine_cycle", "label": "washing machine cycle", "count": 0.22}
  ]
}
```

`estimated_kg_co2` and `comparisons` (both tools' full comparison list is longer than shown above — see `carbon_equivalents.json`) convert the estimated energy into CO2eq using a rough UK grid carbon intensity figure, then express it against everyday activities (washing machine cycles, EV charges, flights, ...). See "CO2eq comparisons" below.

Both tools return a typed, field-described [pydantic](https://docs.pydantic.dev/) model (`src/mcps/schema.py`), so MCP clients get a real JSON schema for the response shape rather than an untyped object. If a session/project can't be found, the tool raises a proper MCP tool error instead of returning a disguised "successful" result.

On the Claude Code server, `current_session_energy` identifies "this chat" via the `CLAUDE_CODE_SESSION_ID` environment variable that Claude Code sets on every process it launches (including the server). On the Codex server, it's identified via the `CODEX_THREAD_ID` environment variable, resolved to a rollout file through Codex's `state_5.sqlite` thread index (falling back to a filename scan under `~/.codex/sessions/` if the thread isn't indexed). Either tool's `collate_project_sessions_energy` then sums every other session belonging to the current project — every sibling `.jsonl` for Claude Code, every indexed thread with a matching `cwd` for Codex.

## Install

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/<you>/carbon-tracking-mcp.git
cd carbon-tracking-mcp
uv sync
```

This installs console-script entry points (`carbon-tracking-stdio-claude`, `carbon-tracking-stdio-codex`) backed by the `mcps` package under `src/`.

Register whichever server(s) you use **globally**, so they're available in every project rather than just this one.

### Claude Code

```bash
claude mcp add --scope user carbon-tracking-energy-claude -- uv run --directory /path/to/carbon-tracking-mcp carbon-tracking-stdio-claude
```

Restart or start a new session and the tools become available. Verify with:

```bash
claude mcp get carbon-tracking-energy-claude
```

### Codex

```bash
codex mcp add carbon-tracking-energy-codex -- uv run --directory /path/to/carbon-tracking-mcp carbon-tracking-stdio-codex
```

`codex mcp add` writes to `~/.codex/config.toml`, which Codex CLI, the IDE extension, and the desktop app all share — there's no per-project scope to choose, so this is global by default. Restart or start a new session and check `/mcp` inside Codex to verify the server is connected. Alternatively, add the entry by hand:

```toml
[mcp_servers.carbon-tracking-energy-codex]
command = "uv"
args = ["run", "--directory", "/path/to/carbon-tracking-mcp", "carbon-tracking-stdio-codex"]
```

## Standalone CLI

`src/mcps/energy_estimate.py` also works as a plain script, independent of MCP:

```bash
uv run carbon-tracking-energy-estimate ~/.claude/projects/<project>/<session-id>.jsonl
```

```
60 deduplicated requests
Estimated session energy: 1.0181 kWh
```

## The energy model

Follows [Simon P. Couch's methodology](https://simonpcouch.com/blog/2026-01-20-cc-impact/): Wh-per-million-tokens rates are estimated from Epoch AI's ChatGPT-4o energy figures, using the *price ratio* between input/output/cache tokens as a proxy for their *energy ratio* (Anthropic doesn't publish energy numbers directly). 

Couch's article was published when models still used 200k token context windows. Models have a context window of 1M tokens now. We assume one is smart and keeps their context window around half this. So, we added 500K-token context as a fourth anchor point, based on code from EpochAI: https://colab.research.google.com/drive/1dnhL0lkjsk-isAH-j02pFUbv1g12hEm1#scrollTo=dN0Ezyr4qXAQ, which is used to compute energy. 

**Read this before trusting the numbers:**
- "Energy scales with price" is an assumption, not a measurement.
- Cache-read/cache-write rates are a flat napkin-math ratio applied to the input rate, not real per-model pricing.
- A single fixed rate is used for every request regardless of its actual context length, so short requests are overestimated and very long ones (near 1M tokens) are underestimated relative to a context-scaled model.
- EpochAI note that cost/energy scales quadratically with input length as expected due to the attention mechanism. However, there are certainly innovations that improve on quadratic scaling. So this is a pessimistic estimation. 

Treat every number here as **order-of-magnitude and directional** — useful for comparing sessions against each other, not as an audited carbon/energy figure.

## CO2eq comparisons

`carbon_equivalents.py` converts an energy estimate (Wh) into kgCO2eq using a grid carbon intensity figure (default: a 2026 UK grid average of 141 gCO2/kWh, from [Purely Energy's 2026 grid report](https://www.purelyenergy.co.uk/grid-report/2026)) and expresses that total against everyday activities defined in `carbon_equivalents.json` — washing machine cycles, EV charges, flights, a kg of beef, and so on. Entries in that file are either `kwh` (converted through the grid intensity) or a direct `kg_co2` figure for things that aren't grid electricity (car miles, flights, food).

Same caveat as above: this is a rough, directional comparison, not an audited figure — grid intensity varies by country, time of day, and year.

## Project layout

```
src/mcps/
  schema.py                # pydantic models (with field descriptions) for every tool input/output
  energy_estimate.py       # the energy model + Claude Code/Codex session-log parsers (also runnable as a CLI)
  carbon_equivalents.py    # Wh -> kgCO2eq conversion + everyday-activity comparisons
  carbon_equivalents.json  # the comparison database (grid intensity + activity list)
  mcp_results.py           # shared MCP tool-result shaping used by every server below
  claude_sessions.py       # Claude Code session discovery (glob under ~/.claude/projects)
  codex_sessions.py        # Codex session discovery (sqlite thread index + ~/.codex/sessions)
  stdio/
    server_claude.py       # FastMCP server for Claude Code sessions
    server_codex.py        # FastMCP server for Codex sessions
```

## License

[MIT](LICENSE)
