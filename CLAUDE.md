# mcp-post-tool-tracker — Claude Project Context

**Type:** FastMCP Server
**Transport:** stdio
**Python:** 3.8+

---

## What This Server Does

Post-execution tool tracking and session progress monitoring for Claude Code. Tracks every tool call, updates session progress metrics, estimates context window usage, enforces task update frequency, and determines commit readiness.

---

## Entry Point

```
server.py
```

Run via `python server.py` — communicates over stdio using the MCP protocol.

---

## Available Tools

- `track_tool_usage` — Record tool call with metadata (name, args, result, duration)
- `increment_progress` — Increment step progress counter for current session
- `clear_enforcement_flag` — Clear a specific enforcement flag after completion
- `get_progress_status` — Get full session progress: steps, tools used, context estimate
- `get_tool_stats` — Aggregate tool usage stats grouped by tool name
- `check_commit_readiness` — Determine if accumulated changes are ready for git commit

---

## Shared Utilities (in this repo)

- `base/` — Shared MCP infrastructure package (response builder, decorators, persistence, clients)
- `mcp_errors.py` — Structured error response helpers
- `input_validator.py` — Null-byte strip, length limits, prompt injection detection
- `rate_limiter.py` — Token bucket rate limiter (enable via ENABLE_RATE_LIMITING=1)

---

## Environment Variables

- `CLAUDE_SESSION_DIR` — Path to session storage directory
- `CLAUDE_TOOL_LOG` — Path to JSONL tool usage log file

---

## Development

### Running locally

```bash
# Install deps
pip install -r requirements.txt

# Run the MCP server (stdio mode)
python server.py
```

### Testing a tool call manually

```python
import subprocess, json

proc = subprocess.Popen(
    ["python", "server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
)
# Send MCP initialize + tool call via stdin
```

### File structure

```
mcp-post-tool-tracker/
+-- server.py          # Main FastMCP server (entry point)
+-- base/              # Shared base package (response, decorators, persistence, clients)
+-- mcp_errors.py      # Error helpers
+-- input_validator.py # Input validation
+-- rate_limiter.py    # Rate limiting
+-- requirements.txt
+-- .gitignore
+-- README.md
+-- CLAUDE.md
```

---

## Key Rules

1. Do NOT edit `base/` directly — it is a copy from `mcp-base` repo
2. To update shared utilities, edit in `mcp-base` and re-copy
3. Keep `server.py` as the single entry point
4. All tool handlers must use `@mcp_tool_handler` decorator for consistent error handling
5. All responses must use `success()` / `error()` / `MCPResponse` builder from `base.response`

---

**Last Updated:** 2026-03-31
