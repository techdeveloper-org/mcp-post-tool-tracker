# mcp-post-tool-tracker

![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue)
![License MIT](https://img.shields.io/badge/License-MIT-green)
![Part of ai-native-sdlc-engine](https://img.shields.io/badge/Part%20of-claude--workflow--engine-orange)

A FastMCP server that tracks tool usage, session progress, and commit readiness after every tool call in a Claude Code session. It is invoked automatically by the **PostToolUse** Claude Code hook and persists rich activity data to `tool-tracker.jsonl` and `session-progress.json`.

This server is one of 13 MCP servers in the [Claude Workflow Engine](https://github.com/techdeveloper-org/ai-native-sdlc-engine) ecosystem — a LangGraph orchestration pipeline for automating Claude Code development workflows.

---

## Features

- **Automatic tool tracking** — logs every tool call (name, status, file touched, command run, edit size) to a per-session `tool-tracker.jsonl`
- **Session progress metering** — accumulates a 0-100 progress score using complexity-weighted deltas per tool type
- **Context window estimation** — estimates context window usage percentage from tool call volume and content size
- **Commit readiness detection** — signals when accumulated file edits justify an automatic commit (3+ files, 50%+ progress, or completed task)
- **Enforcement flag clearing** — automatically clears `task-breakdown-pending` and `skill-selection-pending` flags when qualifying tools are invoked
- **Task update frequency enforcement** — warns when more than 5 tool calls occur without a `TaskUpdate`, enforced at complexity >= 3
- **Complexity-aware phase enforcement** — warns when file writes happen at complexity >= 6 without any tasks created
- **Manual progress control** — allows the caller to increment progress with an explicit delta and reason

---

## Tool Reference

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `track_tool_usage` | Main entry point. Records a completed tool call with rich activity data, updates progress, logs to `tool-tracker.jsonl`, clears enforcement flags, and emits task-frequency warnings. | `tool_name` (str, required), `tool_input` (JSON str, default `{}`), `is_error` (bool, default `false`), `response_chars` (int, default `0`) |
| `increment_progress` | Manually increments the session progress score by an arbitrary delta. | `delta` (int, default `5`, range 1-20), `reason` (str, optional) |
| `clear_enforcement_flag` | Removes a named enforcement flag file for the current session. | `flag_name` (str, required): `task-breakdown-pending` or `skill-selection-pending` |
| `get_progress_status` | Returns the current session progress snapshot: score, task counts, error count, tool counts, modified files list, context estimate, and tools-since-last-update counter. | _(none)_ |
| `get_tool_stats` | Reads `tool-tracker.jsonl` and returns aggregate statistics: total entries, per-tool call counts, error count, and the set of modified files. | _(none)_ |
| `check_commit_readiness` | Evaluates modified file count, progress score, and completed task count to determine whether an automatic commit should be triggered. Returns `should_commit` boolean and the matching reason. | _(none)_ |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/techdeveloper-org/mcp-post-tool-tracker.git
cd mcp-post-tool-tracker
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

The server depends on:
- `mcp` (FastMCP framework, `mcp.server.fastmcp`)
- `base/` — shared library included in this repository (copy of [mcp-base](https://github.com/techdeveloper-org/mcp-base))
- `utils/path_resolver.py` — cross-platform config directory resolver from the parent workspace

### 3. Register with Claude Code

Add the server to your Claude Code `settings.json` and wire the **PostToolUse** hook:

```json
{
  "mcpServers": {
    "post-tool-tracker": {
      "command": "python",
      "args": ["/absolute/path/to/mcp-post-tool-tracker/server.py"],
      "transport": "stdio"
    }
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python /absolute/path/to/post-tool-tracker.py"
          }
        ]
      }
    ]
  }
}
```

Replace `/absolute/path/to/` with the actual path on your system. The `settings.json` file is located at `~/.claude/settings.json` on macOS/Linux and `%USERPROFILE%\.claude\settings.json` on Windows.

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_CONFIG_DIR` | `~/.claude` | Base config directory. Resolved by `utils/path_resolver.get_config_dir()`. Override to relocate all session data. |

### File Paths (resolved at runtime)

| File | Path | Purpose |
|------|------|---------|
| Session progress | `$CLAUDE_CONFIG_DIR/logs/session-progress.json` | Mutable progress state for current session |
| Tool tracker log | `$CLAUDE_CONFIG_DIR/logs/sessions/{session_id}/tool-tracker.jsonl` | Append-only JSONL activity log |
| Flow trace | `$CLAUDE_CONFIG_DIR/logs/sessions/{session_id}/flow-trace.json` | Complexity score source (read-only, written by Level 3 pipeline) |
| Enforcement flags | `$CLAUDE_CONFIG_DIR/logs/sessions/{session_id}/flags/{flag-name}.json` | Cleared automatically on qualifying tool calls |
| Current session | `$CLAUDE_CONFIG_DIR/.current-session.json` | Active session ID (written by mcp-session-mgr) |

### PostToolUse Hook Flow

Claude Code invokes the **PostToolUse** hook after every tool call in the session. The hook script calls `track_tool_usage` via the MCP server, passing:

- `tool_name` — the name of the tool that just executed
- `tool_input` — the JSON-serialized input parameters the tool received
- `is_error` — whether the tool call produced an error result
- `response_chars` — the character length of the tool response (used for context window estimation)

The server processes the call synchronously and returns a JSON result. The hook script can inspect `warnings` in the response to surface task-frequency or phase enforcement alerts to the user in real time.

---

## Usage Examples

### Example 1: Track a file write

Called automatically by the PostToolUse hook after a `Write` tool call:

```python
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="python",
    args=["/path/to/mcp-post-tool-tracker/server.py"]
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("track_tool_usage", {
            "tool_name": "Write",
            "tool_input": json.dumps({
                "file_path": "/project/src/api/users.py",
                "content": "# generated content ..."
            }),
            "is_error": False,
            "response_chars": 1240
        })
        # result includes: progress_delta=8, total_progress, context_estimate_pct, warnings
        print(result)
```

### Example 2: Check commit readiness before a git step

```python
result = await session.call_tool("check_commit_readiness", {})
data = json.loads(result.content[0].text)

if data["should_commit"]:
    print(f"Commit recommended: {data['reason']}")
    print(f"Modified files ({data['modified_count']}): {data['modified_files']}")
else:
    print("Not ready to commit yet.")
```

Sample response:

```json
{
  "success": true,
  "should_commit": true,
  "modified_files": ["src/api/users.py", "src/services/auth.py", "tests/test_users.py"],
  "modified_count": 3,
  "progress": 42,
  "tasks_completed": 0,
  "reason": "3+ files modified"
}
```

### Example 3: Read the current session progress snapshot

```python
result = await session.call_tool("get_progress_status", {})
status = json.loads(result.content[0].text)

print(f"Progress:               {status['total_progress']}%")
print(f"Context window:         {status['context_estimate_pct']}%")
print(f"Tools since TaskUpdate: {status['tools_since_last_update']}")
print(f"Modified files:         {status['modified_files']}")
```

Sample response:

```json
{
  "success": true,
  "total_progress": 38,
  "tasks_created": 2,
  "tasks_completed": 1,
  "errors_seen": 0,
  "tool_counts": {"Read": 6, "Edit": 3, "Bash": 2, "Write": 1},
  "total_tool_calls": 12,
  "last_tool": "Edit",
  "modified_files": ["src/models/user.py", "src/routes/users.py"],
  "context_estimate_pct": 27,
  "tools_since_last_update": 3,
  "session_id": "20260414-143022"
}
```

### Example 4: Get aggregate tool statistics for the session

```python
result = await session.call_tool("get_tool_stats", {})
stats = json.loads(result.content[0].text)

print(f"Total tool calls: {stats['total_entries']}")
print(f"Errors:           {stats['errors']}")
print(f"By tool:          {stats['by_tool']}")
print(f"Files modified:   {stats['files_modified']}")
```

---

## Integration with Claude Workflow Engine

This server sits at position 7 in the MCP server stack and cooperates with two other servers:

- **mcp-session-mgr** — writes `.current-session.json` and `flow-trace.json` that this server reads for session ID resolution and complexity scoring
- **mcp-pre-tool-gate** — sets `task-breakdown-pending` and `skill-selection-pending` enforcement flags that this server clears when qualifying tools (`TaskCreate`, `Skill`) are invoked

### Progress Delta Reference

The server applies the following base progress deltas per tool call. At complexity >= 8 the delta is halved; at complexity >= 15 it is quartered (minimum 1).

| Tool | Base Delta |
|------|-----------|
| `Write` | 8 |
| `Edit`, `NotebookEdit` | 5 |
| `Agent` | 4 |
| `Bash` | 3 |
| `TaskCreate` | 2 |
| `Skill` | 2 |
| `WebSearch`, `WebFetch` | 1 |
| `Read`, `Grep`, `Glob`, `TaskUpdate` | 1 |

### Commit Readiness Logic

`check_commit_readiness` returns `should_commit: true` when any of the following conditions hold:

- 3 or more files have been modified since the last commit
- Session progress is at or above 50% and at least 1 file has been modified
- At least 1 task has been marked completed

---

## Related Servers

| Server | Purpose |
|--------|---------|
| [mcp-pre-tool-gate](https://github.com/techdeveloper-org/mcp-pre-tool-gate) | Pre-tool validation; sets enforcement flags this server clears |
| [mcp-session-mgr](https://github.com/techdeveloper-org/mcp-session-mgr) | Session lifecycle; writes session ID and flow-trace this server reads |
| [mcp-git-ops](https://github.com/techdeveloper-org/mcp-git-ops) | Git operations; consumes commit readiness signal from this server |
| [mcp-token-optimizer](https://github.com/techdeveloper-org/mcp-token-optimizer) | Token reduction; 60-85% context savings via smart reads |

All 13 servers and the shared base library are documented in the [Claude Workflow Engine](https://github.com/techdeveloper-org/ai-native-sdlc-engine) repository.

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes and add tests
4. Ensure all tests pass: `pytest tests/`
5. Submit a pull request

Please follow PEP 8, include type hints on all new functions, and keep tool handlers thin — delegate business logic to helper functions so they remain unit-testable.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
