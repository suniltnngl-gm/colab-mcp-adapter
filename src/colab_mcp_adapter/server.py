"""Colab MCP Adapter - stdio MCP server for Google Colab CLI.

Phase C: Session lifecycle tools (create, list, get, stop).
Phase D: Code/file execution tools.
"""

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .adapter import ColabAdapter
from .contracts import (
    CodeExecuteParams,
    ColabMCPError,
    ExecutionResult,
    FileExecuteParams,
    SessionCreateParams,
    SessionCreateResult,
    SessionGetParams,
    SessionGetResult,
    SessionGetURLParams,
    SessionGetURLResult,
    SessionListResult,
    SessionLogParams,
    SessionLogResult,
    SessionStopParams,
    SessionStopResult,
)

mcp = FastMCP("colab-mcp-adapter")
adapter = ColabAdapter()


def _map_error(e: ColabMCPError) -> ToolError:
    """Map ColabMCPError to MCP ToolError with appropriate error code."""
    return ToolError(
        e.message,
        e.code,
        e.status_code,
        e.details,
    )


@mcp.tool()
def colab_session_create(
    name: str | None = None,
    gpu: str | None = None,
    tpu: str | None = None,
    high_mem: bool = False,
) -> SessionCreateResult:
    """Create a new Colab session.

    Args:
        name: Optional session name (auto-generated if omitted)
        gpu: GPU variant: T4, L4, G4, H100, A100
        tpu: TPU variant: v5e1, v6e1
        high_mem: Request high-RAM machine shape (requires Pro/Pro+)

    Returns:
        Session info including name, session_id, hardware, shape, variant, status

    Raises:
        ToolError: SESSION_ALREADY_EXISTS, QUOTA_EXCEEDED, AUTH_EXPIRED, CLI_ERROR
    """
    params = SessionCreateParams(
        name=name,
        gpu=gpu,
        tpu=tpu,
        high_mem=high_mem,
    )
    try:
        return adapter.create_session(params)
    except ColabMCPError as e:
        raise _map_error(e) from e


@mcp.tool()
def colab_session_list() -> SessionListResult:
    """List all active Colab sessions.

    Returns:
        List of sessions with name, session_id, hardware, shape, variant, status

    Raises:
        ToolError: AUTH_EXPIRED, CLI_ERROR
    """
    try:
        return adapter.list_sessions()
    except ColabMCPError as e:
        raise _map_error(e) from e


@mcp.tool()
def colab_session_get(name: str) -> SessionGetResult:
    """Get status of a specific Colab session.

    Args:
        name: Session display name

    Returns:
        Session info including name, session_id, hardware, shape, variant, status

    Raises:
        ToolError: SESSION_NOT_FOUND, AUTH_EXPIRED, CLI_ERROR
    """
    params = SessionGetParams(name=name)
    try:
        return adapter.get_session(params)
    except ColabMCPError as e:
        raise _map_error(e) from e


@mcp.tool()
def colab_session_stop(name: str) -> SessionStopResult:
    """Stop (terminate and delete) a Colab session.

    WARNING: This is a destructive operation. The session and its kernel
    state will be permanently deleted. Files in /content persist on the
    runtime filesystem but the session cannot be resumed.

    Args:
        name: Session display name

    Returns:
        Confirmation that session was terminated

    Raises:
        ToolError: SESSION_NOT_FOUND, AUTH_EXPIRED, CLI_ERROR
    """
    params = SessionStopParams(name=name)
    try:
        return adapter.stop_session(params)
    except ColabMCPError as e:
        raise _map_error(e) from e


@mcp.tool()
def colab_code_execute(
    session: str,
    code: str,
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> ExecutionResult:
    """Execute Python code in a Colab session via stdin pipe.

    Args:
        session: Session display name
        code: Python code to execute
        timeout: Execution timeout in seconds (1-300, default: 30)
        env: Environment variables to set before execution

    Returns:
        Execution result with stdout, stderr, exit_code, execution_time

    Raises:
        ToolError: SESSION_NOT_FOUND, EXECUTION_TIMEOUT, KERNEL_ERROR,
            AUTH_EXPIRED, QUOTA_EXCEEDED, CLI_ERROR
    """
    params = CodeExecuteParams(
        session=session,
        code=code,
        timeout=timeout,
        env=env,
    )
    try:
        return adapter.execute_code(params)
    except ColabMCPError as e:
        raise _map_error(e) from e


@mcp.tool()
def colab_file_execute(
    session: str,
    file_path: str,
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> ExecutionResult:
    """Execute a Python file in a Colab session.

    Args:
        session: Session display name
        file_path: Path to Python file to execute
        timeout: Execution timeout in seconds (1-300, default: 30)
        env: Environment variables to set before execution

    Returns:
        Execution result with stdout, stderr, exit_code, execution_time

    Raises:
        ToolError: SESSION_NOT_FOUND, EXECUTION_TIMEOUT, KERNEL_ERROR,
            AUTH_EXPIRED, QUOTA_EXCEEDED, CLI_ERROR
    """
    params = FileExecuteParams(
        session=session,
        file_path=file_path,
        timeout=timeout,
        env=env,
    )
    try:
        return adapter.execute_file(params)
    except ColabMCPError as e:
        raise _map_error(e) from e


@mcp.tool()
def colab_session_get_url(
    session: str,
    host: str | None = None,
) -> SessionGetURLResult:
    """Get the browser URL for a Colab session.

    Args:
        session: Session display name
        host: Optional Colab frontend host (default: https://colab.research.google.com)

    Returns:
        Full Colab browser URL for the session

    Raises:
        ToolError: SESSION_NOT_FOUND, AUTH_EXPIRED, QUOTA_EXCEEDED, CLI_ERROR
    """
    params = SessionGetURLParams(session=session, host=host)
    try:
        return adapter.get_session_url(params)
    except ColabMCPError as e:
        raise _map_error(e) from e


@mcp.tool()
def colab_session_log(
    session: str | None = None,
    lines: int | None = None,
    type: str | None = None,
) -> SessionLogResult:
    """Get session history logs.

    Args:
        session: Session display name (omit to list all sessions with logs)
        lines: Number of lines to show (default: all)
        type: Filter by event type (e.g., execution, file_operation, session_created)

    Returns:
        Log lines for the session, or list of sessions with logs if session omitted

    Raises:
        ToolError: SESSION_NOT_FOUND, AUTH_EXPIRED, QUOTA_EXCEEDED, CLI_ERROR
    """
    params = SessionLogParams(session=session, lines=lines, type=type)
    try:
        return adapter.get_session_log(params)
    except ColabMCPError as e:
        raise _map_error(e) from e


def main() -> None:
    """Run the MCP server over standard input/output."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
