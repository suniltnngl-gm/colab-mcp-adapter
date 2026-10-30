# Colab MCP Adapter

A local, Windows-compatible stdio MCP server for the Google Colab CLI.

**Authentication:** Uses the existing Colab CLI OAuth2 flow. The adapter never reads, copies, prints, or modifies CLI credential files.

**No GCP/ADC required** — wraps the local `colab` CLI instead of the hosted Colab API.

This adapter is a local interactive-compute integration, not a distributed worker. Google Colab's free managed runtimes prohibit running distributed-computing workers; do not use this adapter as part of a worker pool.

---

## Features (8 Tools)

### Phase C: Session Lifecycle
| Tool | CLI Command | Description |
|------|-------------|-------------|
| `colab_session_create` | `colab new [--session NAME] [--gpu GPU] [--tpu TPU] [--high-mem]` | Create a new Colab session |
| `colab_session_list` | `colab sessions` | List all active sessions |
| `colab_session_get` | `colab status --session <name>` | Get session status |
| `colab_session_stop` | `colab stop --session <name>` | Stop (terminate & delete) session |

### Phase D: Code/File Execution
| Tool | CLI Command | Description |
|------|-------------|-------------|
| `colab_code_execute` | `echo "code" \| colab exec --session <name>` | Execute Python code via stdin pipe |
| `colab_file_execute` | `colab exec --session <name> --file <path>` | Execute a Python file |

### Phase E: URL/Log
| Tool | CLI Command | Description |
|------|-------------|-------------|
| `colab_session_get_url` | `colab url --session <name> [--host <host>]` | Get browser URL for session |
| `colab_session_log` | `colab log [--session <name>] [--lines N] [--type TYPE]` | Get session history logs |

---

## Architecture

```
OpenCode v2 (MCP Client)
    │ stdio transport (clean JSON-RPC)
    ▼
Colab MCP Adapter (FastMCP 2.14.7)
    │ subprocess (no shell=True)
    ▼
Colab CLI 0.7.5 (OAuth2 via ~/.config/colab-cli/token.json)
    │ HTTPS
    ▼
Google Colab Free Tier
```

---

## Requirements

- Python ≥3.11 (tested on 3.12.15, 3.15.1)
- `uv` package manager
- Google Colab CLI 0.7.5+ (`uv tool install google-colab-cli`)
- Colab CLI authenticated (`colab login`)

---

## Installation

```bash
# Clone and install
git clone <repo-url>
cd colab-mcp-adapter
uv sync --extra dev

# Run tests
uv run pytest

# Run server
uv run colab-mcp-adapter
```

---

## OpenCode Integration

For OpenCode v2, add the MCP server to `~/.config/opencode/opencode.jsonc`:

```jsonc
{
  "mcp": {
    "servers": {
      "colab": {
        "type": "local",
        "command": ["uv", "run", "colab-mcp-adapter"],
        "cwd": "C:\\Users\\<user>\\Projects\\colab-mcp-adapter",
        "timeout": 30000
      }
    }
  }
}
```

OpenCode v2 agents use ordered permission rules. This example allows routine inspection and code execution, while requiring approval for file execution and destructive session termination:

```jsonc
{
  "agents": {
    "colab-researcher": {
      "description": "Conduct computational research using Colab sessions",
      "mode": "primary",
      "system": "Use existing sessions when possible. Never print secrets. Ask for explicit approval before file execution or stopping a session.",
      "permissions": [
        { "action": "colab_colab_session_list", "resource": "*", "effect": "allow" },
        { "action": "colab_colab_session_get", "resource": "*", "effect": "allow" },
        { "action": "colab_colab_session_get_url", "resource": "*", "effect": "allow" },
        { "action": "colab_colab_session_log", "resource": "*", "effect": "allow" },
        { "action": "colab_colab_session_create", "resource": "*", "effect": "allow" },
        { "action": "colab_colab_code_execute", "resource": "*", "effect": "allow" },
        { "action": "colab_colab_file_execute", "resource": "*", "effect": "ask" },
        { "action": "colab_colab_session_stop", "resource": "*", "effect": "ask" }
      ]
    }
  }
}
```

These configuration examples target OpenCode v2. OpenCode v1 uses a different configuration schema; use documentation matching the installed version.

---

## Safeguards

| Safeguard | Implementation |
|-----------|----------------|
| **No `shell=True`** | Argument arrays only (`subprocess.run(args_list)`) |
| **No token exposure** | Never reads `token.json`; CLI handles OAuth2 |
| **Session ID validation** | Regex `^m-s-[a-z0-9-]+$` on all operations |
| **Defensive parsing** | Regex with fallbacks, skips `[colab]` lines |
| **Error mapping** | CLI stderr → MCP codes (404, 409, 408, 401, 429, 500) |
| **Bounded timeouts** | Per-call configurable (1–300s) |
| **Separate stdout/stderr** | Independent capture in `CLIResult` |
| **Destructive stop gated** | Explicit warning, termination verified |

---

## Testing

```bash
# All tests (71 passing)
uv run pytest

# Protocol tests only
uv run pytest tests/test_stdio_protocol.py -v

# Unit tests only
uv run pytest tests/test_adapter.py -v
```

---

## Project Structure

```
colab-mcp-adapter/
├── pyproject.toml
├── uv.lock
├── README.md
├── PHASE-B-VERIFICATION.md
├── PHASE-C-VERIFICATION.md
├── PHASE-D-VERIFICATION.md
├── PHASE-E-VERIFICATION.md
├── PHASE-F-VERIFICATION.md
├── RELEASE-MANIFEST.md
├── RELEASE-READINESS.md
├── USAGE-PLAN.md
├── src/
│   └── colab_mcp_adapter/
│       ├── __init__.py
│       ├── __main__.py
│       ├── contracts.py      # Pydantic models & error classes
│       ├── parser.py         # CLI output parsing
│       ├── adapter.py        # Core subprocess wrapper
│       └── server.py         # FastMCP server with 8 tools
└── tests/
    ├── test_adapter.py       # 69 unit tests (mocked CLI)
    └── test_stdio_protocol.py # 2 protocol tests (real server)
```

---

## Verification Reports

| Phase | Report |
|-------|--------|
| B | [PHASE-B-VERIFICATION.md](PHASE-B-VERIFICATION.md) |
| C | [PHASE-C-VERIFICATION.md](PHASE-C-VERIFICATION.md) |
| D | [PHASE-D-VERIFICATION.md](PHASE-D-VERIFICATION.md) |
| E | [PHASE-E-VERIFICATION.md](PHASE-E-VERIFICATION.md) |
| F | [PHASE-F-VERIFICATION.md](PHASE-F-VERIFICATION.md) |

---

## License

MIT