# Colab MCP Adapter — Usage Plan for OpenCode Agents

> **Prerequisite:** OpenCode config updated with `colab` MCP server (see README)

---

## Quick Start

```bash
# 1. Ensure Colab CLI is authenticated
colab login

# 2. Start OpenCode (loads MCP servers automatically)
opencode
```

---

## Common Workflows

### 1. Research Session (Create → Execute → Get URL)

```python
# Agent pseudo-code
session = await colab_session_create(name="research-pytorch", gpu="T4")
url = await colab_session_get_url(session=session.name)
# Open URL in browser for interactive work
result = await colab_code_execute(session=session.name, code="""
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")
""")
# Ask the user for explicit approval before stopping the session.
```

### 2. Batch Execution (Create → Execute File → Logs → Stop)

```python
# For reproducible runs with scripts
session = await colab_session_create(name="batch-training")
await colab_file_execute(session=session.name, file_path="/workspace/train.py")
logs = await colab_session_log(session=session.name, type="execution")
# Ask the user for explicit approval before stopping the session.
await colab_session_stop(name=session.name)
```

### 3. Iterative Development (Reuse Session)

```python
# Create once, execute multiple times
session = await colab_session_create(name="dev-session")

# Iteration 1
await colab_code_execute(session=session.name, code="import pandas as pd; df = pd.read_csv('data.csv')")

# Iteration 2
await colab_code_execute(session=session.name, code="df.head()")

# Iteration 3
await colab_code_execute(session=session.name, code="df.describe()")

# Check logs
logs = await colab_session_log(session=session.name, lines=50)

# Ask the user for explicit approval before stopping the session.
await colab_session_stop(name=session.name)
```

### 4. Resource-Constrained (CPU Only, No Persistence)

```python
# Quick CPU session for lightweight tasks
session = await colab_session_create(name="quick-cpu")
result = await colab_code_execute(
    session=session.name,
    code="print(sum(range(1000000)))",
    timeout=10
)
await colab_session_stop(name=session.name)
```

---

## Tool Reference

| Tool | Required Params | Optional Params | Typical Use |
|------|-----------------|-----------------|-------------|
| `colab_session_create` | — | `name`, `gpu`, `tpu`, `high_mem` | Provision runtime |
| `colab_session_list` | — | — | Discover active sessions |
| `colab_session_get` | `name` | — | Check status |
| `colab_session_stop` | `name` | — | Terminate session |
| `colab_code_execute` | `session`, `code` | `timeout`, `env` | Run inline code |
| `colab_file_execute` | `session`, `file_path` | `timeout`, `env` | Run script file |
| `colab_session_get_url` | `session` | `host` | Get browser URL |
| `colab_session_log` | — | `session`, `lines`, `type` | View history |

---

## GPU/TPU Selection

The adapter passes a requested accelerator label to the Colab CLI; it cannot guarantee that Colab will assign that hardware. Free-tier GPU/TPU availability, resource limits, and session lifetime vary and are not guaranteed. Check current provider terms and the runtime that Colab actually assigns before planning a workload. Do not use free managed Colab runtimes as distributed-computing workers.

```python
# Requesting an accelerator does not guarantee availability.
await colab_session_create(name="gpu-run", gpu="T4")

# Request high-memory CPU
await colab_session_create(name="highmem", high_mem=True)
```

---

## Environment Variables

```python
# Pass an approved secret through the env parameter. Never print it or include
# its value in notebook output, logs, or saved artifacts.
await colab_code_execute(
    session=session.name,
    code="import os; assert os.environ.get('SERVICE_TOKEN')",
    env={"SERVICE_TOKEN": "<supply through an approved secret channel>"}
)
```

---

## Timeout Guidelines

| Operation | Default | Recommended Max |
|-----------|---------|-----------------|
| Session create | 120s | 180s (GPU provisioning) |
| Code execute | 30s | 300s (long training) |
| File execute | 30s | 300s |
| URL/Log | 30s | 60s |

```python
# Long-running training
await colab_code_execute(
    session=session.name,
    code="train_model()",
    timeout=300  # 5 minutes
)
```

---

## Error Handling Patterns

```python
try:
    result = await colab_code_execute(session=name, code="...")
except ToolError as e:
    if e.code == "SESSION_NOT_FOUND":
        # Session was stopped externally, recreate
        session = await colab_session_create(name=name)
    elif e.code == "EXECUTION_TIMEOUT":
        # Increase timeout or optimize code
        logs = await colab_session_log(session=name, lines=20)
    elif e.code == "KERNEL_ERROR":
        # Code error - check stderr
        print(f"Kernel error: {e.message}")
    elif e.code == "QUOTA_EXCEEDED":
        # Wait or use CPU fallback
        session = await colab_session_create(name=name)  # No GPU
```

---

## Session Lifecycle Best Practices

### ✅ Do
- **Reuse sessions** for iterative work (avoids re-provisioning)
- **Name sessions descriptively** (`"training-bert"`, `"eda-pandas"`)
- **Ask for explicit approval before stopping a session** (stopping permanently deletes the session and kernel state)
- **Use `colab_session_log`** to debug failures
- **Set appropriate timeouts** for long operations

### ❌ Don't
- **Create many sessions** in parallel (quota limits)
- **Leave GPU sessions idle** (consumes quota)
- **Assume session persists** across OpenCode restarts
- **Put secrets in code** — use `env` parameter
- **Run distributed-computing workers on free managed Colab runtimes**

---

## Quota Management

Colab does not publish a guaranteed free-tier GPU-hour or concurrency allowance. Resource availability and usage limits fluctuate. Do not rely on fixed session counts, accelerator models, or reset schedules. Check existing sessions before requesting new ones and comply with the current Colab terms.

```python
# Check active sessions before creating
sessions = await colab_session_list()
for session in sessions.sessions:
    print(f"{session.name}: {session.status} ({session.hardware})")
```

---

## Debugging Checklist

| Symptom | Check |
|---------|-------|
| `SESSION_NOT_FOUND` | Session stopped? `colab_session_list` |
| `EXECUTION_TIMEOUT` | Increase timeout? Code hanging? |
| `KERNEL_ERROR` | Check stderr in result? Syntax error? |
| `QUOTA_EXCEEDED` | Too many GPU sessions? Tier limit? |
| `AUTH_EXPIRED` | Run `colab login` in terminal |
| Slow provisioning | GPU unavailable? Try CPU fallback |

---

## Example Agent Prompt

```markdown
You are a Colab Research Assistant with access to 8 Colab tools.

Workflow for new tasks:
1. Check existing sessions: `colab_session_list`
2. Create session with appropriate resources: `colab_session_create`
3. Execute code/files: `colab_code_execute` / `colab_file_execute`
4. Monitor progress: `colab_session_log` / `colab_session_get`
5. Get browser URL for interactive work: `colab_session_get_url`
6. Ask the user for explicit approval before stopping a session: `colab_session_stop`

Resource guidelines:
- Default to CPU for exploration
- Request T4 for ML training
- Use high_mem for large datasets
- Set timeout based on operation complexity

Error handling:
- On SESSION_NOT_FOUND → recreate
- On EXECUTION_TIMEOUT → check logs, increase timeout
- On QUOTA_EXCEEDED → fallback to CPU or wait
```

---

## Troubleshooting Commands

```bash
# Check Colab CLI directly
colab sessions
colab status --session <name>
colab log --session <name>

# Re-authenticate if needed
colab login

# Check OpenCode MCP connection
opencode debug mcp
```

---

## Next Steps

1. **Configure agent** with Colab permissions in OpenCode
2. **Test workflow** with a simple session create/execute/stop
3. **Build agent skills** for your specific domain (ML, data analysis, etc.)
4. **Monitor quota** and adjust session patterns accordingly