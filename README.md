# mcp-post-tool-tracker

A FastMCP server providing **Post Tool Tracker** capabilities for Claude Code workflows.

---

## Overview

Post-execution tool tracking and session progress monitoring for Claude Code. Tracks every tool call, updates session progress metrics, estimates context window usage, enforces task update frequency, and determines commit readiness.

---

## Tools

| Tool | Description |
|------|-------------|
| `track_tool_usage` | Record tool call with metadata (name, args, result, duration) |
| `increment_progress` | Increment step progress counter for current session |
| `clear_enforcement_flag` | Clear a specific enforcement flag after completion |
| `get_progress_status` | Get full session progress: steps, tools used, context estimate |
| `get_tool_stats` | Aggregate tool usage stats grouped by tool name |
| `check_commit_readiness` | Determine if accumulated changes are ready for git commit |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/techdeveloper-org/mcp-post-tool-tracker.git
cd mcp-post-tool-tracker
```

### 2. Install dependencies

```bash
pip install mcp fastmcp
```

### 3. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

---

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `CLAUDE_SESSION_DIR` | Path to session storage directory |
| `CLAUDE_TOOL_LOG` | Path to JSONL tool usage log file |

---

## Usage in Claude Code

Add to your `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "post-tool-tracker": {
      "command": "python",
      "args": [
        "/path/to/mcp-post-tool-tracker/server.py"
      ],
      "env": {}
    }
  }
}
```

---

## Benefits

- Full audit trail of every tool call within a session
- Context window estimation prevents silent truncation surprises
- Complexity-aware phase execution (tracks multi-phase task progress)
- Commit readiness signal integrates with git-ops MCP

---

## Requirements

- Python 3.8+
- `mcp fastmcp`
- See `requirements.txt` for pinned versions

---

## Project Context

This MCP server is part of the **Claude Workflow Engine** ecosystem — a LangGraph-based
orchestration pipeline for automating Claude Code development workflows.

Related repos:
- [`claude-workflow-engine`](https://github.com/techdeveloper-org/claude-workflow-engine) — Main pipeline
- [`mcp-base`](https://github.com/techdeveloper-org/mcp-base) — Shared base utilities used by all MCP servers

---

## License

Private — techdeveloper-org
