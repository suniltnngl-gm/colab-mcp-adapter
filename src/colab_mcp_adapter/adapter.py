"""Core adapter: subprocess management and CLI wrapping for Colab CLI.

This module handles all subprocess interactions with the `colab` CLI,
enforcing safety constraints:
- No shell=True (argument arrays only)
- Stdin pipe for code execution
- Bounded timeouts
- Separate stdout/stderr capture
- Never reads token.json
"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass

from .contracts import (
    AuthExpiredError,
    CLIError,
    CodeExecuteParams,
    ExecutionResult,
    ExecutionTimeoutError,
    FileExecuteParams,
    KernelError,
    QuotaExceededError,
    SessionAlreadyExistsError,
    SessionCreateParams,
    SessionCreateResult,
    SessionGetParams,
    SessionGetResult,
    SessionGetURLParams,
    SessionGetURLResult,
    SessionListResult,
    SessionLogParams,
    SessionLogResult,
    SessionNotFoundError,
    SessionNotReadyError,
    SessionStopParams,
    SessionStopResult,
)
from .parser import (
    classify_cli_error,
    parse_create_output,
    parse_log_list_output,
    parse_log_output,
    parse_sessions_output,
    parse_status_output,
    parse_url_output,
    validate_session_id,
)


@dataclass
class CLIResult:
    """Result of a CLI command execution."""
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class ColabAdapter:
    """Adapter for Google Colab CLI operations.

    All subprocess calls use argument arrays (no shell=True).
    Code is passed via stdin pipe.
    Timeouts are enforced on all operations.
    """

    # Default timeouts (seconds)
    DEFAULT_CREATE_TIMEOUT = 120  # Session creation can take a while
    DEFAULT_LIST_TIMEOUT = 30
    DEFAULT_STATUS_TIMEOUT = 30
    DEFAULT_STOP_TIMEOUT = 30
    DEFAULT_EXEC_TIMEOUT = 30

    def __init__(
        self,
        colab_cmd: str = "colab",
        default_timeout: int = 30,
    ):
        """Initialize adapter.

        Args:
            colab_cmd: Path to colab CLI executable (default: "colab" on PATH)
            default_timeout: Default timeout for operations in seconds
        """
        self.colab_cmd = colab_cmd
        self.default_timeout = default_timeout

    def _run_cli(
        self,
        args: list[str],
        timeout: int,
        stdin_input: str | None = None,
    ) -> CLIResult:
        """Run a colab CLI command with safety constraints.

        Args:
            args: Command arguments (e.g., ["colab", "sessions"])
            timeout: Timeout in seconds
            stdin_input: Optional input to pass via stdin

        Returns:
            CLIResult with exit_code, stdout, stderr
        """
        # Build full command array (never shell=True)
        cmd = [self.colab_cmd] + args

        try:
            result = subprocess.run(
                cmd,
                input=stdin_input.encode() if stdin_input else None,
                capture_output=True,
                timeout=timeout,
                check=False,  # We handle exit codes ourselves
            )
            return CLIResult(
                exit_code=result.returncode,
                stdout=result.stdout.decode(errors="replace"),
                stderr=result.stderr.decode(errors="replace"),
                timed_out=False,
            )
        except subprocess.TimeoutExpired as e:
            return CLIResult(
                exit_code=-1,
                stdout=e.stdout.decode(errors="replace") if e.stdout else "",
                stderr=e.stderr.decode(errors="replace") if e.stderr else "",
                timed_out=True,
            )
        except FileNotFoundError:
            return CLIResult(
                exit_code=-1,
                stdout="",
                stderr=f"CLI not found: {self.colab_cmd}",
                timed_out=False,
            )
        except Exception as e:
            return CLIResult(
                exit_code=-1,
                stdout="",
                stderr=f"Unexpected error: {type(e).__name__}: {e}",
                timed_out=False,
            )

    async def _run_cli_async(
        self,
        args: list[str],
        timeout: int,
        stdin_input: str | None = None,
    ) -> CLIResult:
        """Run a colab CLI command asynchronously."""
        cmd = [self.colab_cmd] + args

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if stdin_input else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(
                        input=stdin_input.encode() if stdin_input else None
                    ),
                    timeout=timeout,
                )
                return CLIResult(
                    exit_code=process.returncode or 0,
                    stdout=stdout_bytes.decode(errors="replace"),
                    stderr=stderr_bytes.decode(errors="replace"),
                    timed_out=False,
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                return CLIResult(
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    timed_out=True,
                )
        except FileNotFoundError:
            return CLIResult(
                exit_code=-1,
                stdout="",
                stderr=f"CLI not found: {self.colab_cmd}",
                timed_out=False,
            )
        except Exception as e:
            return CLIResult(
                exit_code=-1,
                stdout="",
                stderr=f"Unexpected error: {type(e).__name__}: {e}",
                timed_out=False,
            )

    def _check_result(self, result: CLIResult, operation: str) -> None:
        """Check CLI result and raise appropriate exception on error."""
        if result.timed_out:
            raise ExecutionTimeoutError(timeout=self.default_timeout)

        if result.exit_code != 0:
            error_code, status_code, details = classify_cli_error(result.stderr, result.exit_code)

            # Map to specific exceptions
            if error_code == "SESSION_NOT_FOUND":
                raise SessionNotFoundError(details.get("session_name", "unknown"), details)
            elif error_code == "SESSION_ALREADY_EXISTS":
                raise SessionAlreadyExistsError(details.get("session_name", "unknown"), details)
            elif error_code == "SESSION_NOT_READY":
                raise SessionNotReadyError(details.get("session_name", "unknown"), details)
            elif error_code == "EXECUTION_TIMEOUT":
                raise ExecutionTimeoutError(
                details.get("timeout_seconds", self.default_timeout), details
            )
            elif error_code == "AUTH_EXPIRED":
                raise AuthExpiredError(details)
            elif error_code == "QUOTA_EXCEEDED":
                raise QuotaExceededError(details)
            elif error_code == "KERNEL_ERROR":
                raise KernelError(result.stderr, details)
            else:
                raise CLIError(result.stderr or f"{operation} failed", result.exit_code, details)

    # --- Session Lifecycle Operations ---

    def create_session(self, params: SessionCreateParams) -> SessionCreateResult:
        """Create a new Colab session.

        Args:
            params: Session creation parameters

        Returns:
            SessionCreateResult with session details

        Raises:
            SessionAlreadyExistsError: If session name conflicts
            QuotaExceededError: If resource quota exceeded
            AuthExpiredError: If authentication expired
            CLIError: For other CLI errors
        """
        args = ["new"]
        if params.name:
            args.extend(["--session", params.name])
        if params.gpu:
            args.extend(["--gpu", params.gpu])
        if params.tpu:
            args.extend(["--tpu", params.tpu])
        if params.high_mem:
            args.append("--high-mem")

        result = self._run_cli(args, timeout=self.DEFAULT_CREATE_TIMEOUT)
        self._check_result(result, "create_session")

        # Parse create output to get session name
        create_parsed = parse_create_output(result.stdout)
        session_name = create_parsed.name if create_parsed else (params.name or "unknown")

        # Get full session details via status
        # Note: The session might still be creating, so we may need to wait
        status_result = self.get_session(SessionGetParams(name=session_name))

        return SessionCreateResult(
            name=status_result.name,
            session_id=status_result.session_id,
            hardware=status_result.hardware,
            shape=status_result.shape,
            variant=status_result.variant,
            status=status_result.status,
        )

    async def create_session_async(self, params: SessionCreateParams) -> SessionCreateResult:
        """Async version of create_session."""
        args = ["new"]
        if params.name:
            args.extend(["--session", params.name])
        if params.gpu:
            args.extend(["--gpu", params.gpu])
        if params.tpu:
            args.extend(["--tpu", params.tpu])
        if params.high_mem:
            args.append("--high-mem")

        result = await self._run_cli_async(args, timeout=self.DEFAULT_CREATE_TIMEOUT)
        self._check_result(result, "create_session")

        create_parsed = parse_create_output(result.stdout)
        session_name = create_parsed.name if create_parsed else (params.name or "unknown")

        status_result = await self.get_session_async(SessionGetParams(name=session_name))

        return SessionCreateResult(
            name=status_result.name,
            session_id=status_result.session_id,
            hardware=status_result.hardware,
            shape=status_result.shape,
            variant=status_result.variant,
            status=status_result.status,
        )

    def list_sessions(self) -> SessionListResult:
        """List all active Colab sessions.

        Returns:
            SessionListResult with list of sessions
        """
        result = self._run_cli(["sessions"], timeout=self.DEFAULT_LIST_TIMEOUT)
        self._check_result(result, "list_sessions")

        parsed_sessions = parse_sessions_output(result.stdout)
        sessions = [s.to_session_info() for s in parsed_sessions]

        return SessionListResult(sessions=sessions)

    async def list_sessions_async(self) -> SessionListResult:
        """Async version of list_sessions."""
        result = await self._run_cli_async(["sessions"], timeout=self.DEFAULT_LIST_TIMEOUT)
        self._check_result(result, "list_sessions")

        parsed_sessions = parse_sessions_output(result.stdout)
        sessions = [s.to_session_info() for s in parsed_sessions]

        return SessionListResult(sessions=sessions)

    def get_session(self, params: SessionGetParams) -> SessionGetResult:
        """Get status of a specific session.

        Args:
            params: Session name to query

        Returns:
            SessionGetResult with session details

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        if not params.name:
            raise SessionNotFoundError("unknown", {"reason": "empty session name"})

        result = self._run_cli(
            ["status", "--session", params.name],
            timeout=self.DEFAULT_STATUS_TIMEOUT,
        )
        self._check_result(result, "get_session")

        parsed = parse_status_output(result.stdout)
        if not parsed:
            raise SessionNotFoundError(params.name, {"stdout": result.stdout})

        if not validate_session_id(parsed.session_id):
            raise CLIError(
                f"Invalid session ID format: {parsed.session_id}",
                result.exit_code,
                {"session_id": parsed.session_id},
            )

        return SessionGetResult(
            name=parsed.name,
            session_id=parsed.session_id,
            hardware=parsed.hardware,
            shape=parsed.shape,
            variant=parsed.variant,
            status=parsed.status or "UNKNOWN",
        )

    async def get_session_async(self, params: SessionGetParams) -> SessionGetResult:
        """Async version of get_session."""
        if not params.name:
            raise SessionNotFoundError("unknown", {"reason": "empty session name"})

        result = await self._run_cli_async(
            ["status", "--session", params.name],
            timeout=self.DEFAULT_STATUS_TIMEOUT,
        )
        self._check_result(result, "get_session")

        parsed = parse_status_output(result.stdout)
        if not parsed:
            raise SessionNotFoundError(params.name, {"stdout": result.stdout})

        if not validate_session_id(parsed.session_id):
            raise CLIError(
                f"Invalid session ID format: {parsed.session_id}",
                result.exit_code,
                {"session_id": parsed.session_id},
            )

        return SessionGetResult(
            name=parsed.name,
            session_id=parsed.session_id,
            hardware=parsed.hardware,
            shape=parsed.shape,
            variant=parsed.variant,
            status=parsed.status or "UNKNOWN",
        )

    def stop_session(self, params: SessionStopParams) -> SessionStopResult:
        """Stop (terminate and delete) a Colab session.

        WARNING: This is a destructive operation. The session and its kernel
        state will be permanently deleted. Files in /content persist on the
        runtime filesystem but the session cannot be resumed.

        Args:
            params: Session name to stop

        Returns:
            SessionStopResult confirming termination

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        if not params.name:
            raise SessionNotFoundError("unknown", {"reason": "empty session name"})

        result = self._run_cli(
            ["stop", "--session", params.name],
            timeout=self.DEFAULT_STOP_TIMEOUT,
        )
        self._check_result(result, "stop_session")

        # Verify session is gone
        try:
            self.get_session(SessionGetParams(name=params.name))
            # If we get here, session still exists (unexpected)
            raise SessionNotReadyError(params.name, {"reason": "session still exists after stop"})
        except SessionNotFoundError:
            # Expected - session is gone
            pass

        return SessionStopResult(name=params.name, terminated=True)

    async def stop_session_async(self, params: SessionStopParams) -> SessionStopResult:
        """Async version of stop_session."""
        if not params.name:
            raise SessionNotFoundError("unknown", {"reason": "empty session name"})

        result = await self._run_cli_async(
            ["stop", "--session", params.name],
            timeout=self.DEFAULT_STOP_TIMEOUT,
        )
        self._check_result(result, "stop_session")

        try:
            await self.get_session_async(SessionGetParams(name=params.name))
            raise SessionNotReadyError(params.name, {"reason": "session still exists after stop"})
        except SessionNotFoundError:
            pass

        return SessionStopResult(name=params.name, terminated=True)

    # --- Phase D: Code/File Execution Operations ---

    def execute_code(self, params: CodeExecuteParams) -> ExecutionResult:
        """Execute Python code in a Colab session via stdin pipe.

        Args:
            params: Execution parameters (session, code, timeout, env)

        Returns:
            ExecutionResult with stdout, stderr, exit_code, execution_time

        Raises:
            SessionNotFoundError: If session doesn't exist
            ExecutionTimeoutError: If execution exceeds timeout
            KernelError: If kernel returns an error
            CLIError: For other CLI errors
        """
        if not params.session:
            raise SessionNotFoundError("unknown", {"reason": "empty session name"})

        # Build env prefix if provided
        code = params.code
        if params.env:
            env_lines = [f"import os; os.environ['{k}'] = '{v}'" for k, v in params.env.items()]
            code = "\n".join(env_lines) + "\n" + code

        import time
        start_time = time.time()

        result = self._run_cli(
            ["exec", "--session", params.session],
            timeout=params.timeout,
            stdin_input=code,
        )

        execution_time = time.time() - start_time

        if result.timed_out:
            raise ExecutionTimeoutError(params.timeout, {
                "session": params.session,
                "partial_stdout": result.stdout,
                "partial_stderr": result.stderr,
            })

        # Check for session not found (special handling for exec)
        if result.exit_code != 0:
            stderr_lower = result.stderr.lower()
            if "session" in stderr_lower and "not found" in stderr_lower:
                raise SessionNotFoundError(params.session, {"stderr": result.stderr})
            if "timeout" in stderr_lower:
                raise ExecutionTimeoutError(params.timeout, {"stderr": result.stderr})
            # Kernel errors typically have tracebacks in stderr
            if "traceback" in stderr_lower or "error" in stderr_lower:
                raise KernelError(result.stderr, {"exit_code": result.exit_code})
            # Other CLI errors
            error_code, status_code, details = classify_cli_error(result.stderr, result.exit_code)
            if error_code == "AUTH_EXPIRED":
                raise AuthExpiredError(details)
            elif error_code == "QUOTA_EXCEEDED":
                raise QuotaExceededError(details)
            else:
                raise CLIError(result.stderr or "Execution failed", result.exit_code, details)

        return ExecutionResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            execution_time=execution_time,
        )

    async def execute_code_async(self, params: CodeExecuteParams) -> ExecutionResult:
        """Async version of execute_code."""
        if not params.session:
            raise SessionNotFoundError("unknown", {"reason": "empty session name"})

        code = params.code
        if params.env:
            env_lines = [f"import os; os.environ['{k}'] = '{v}'" for k, v in params.env.items()]
            code = "\n".join(env_lines) + "\n" + code

        import time
        start_time = time.time()

        result = await self._run_cli_async(
            ["exec", "--session", params.session],
            timeout=params.timeout,
            stdin_input=code,
        )

        execution_time = time.time() - start_time

        if result.timed_out:
            raise ExecutionTimeoutError(params.timeout, {
                "session": params.session,
                "partial_stdout": result.stdout,
                "partial_stderr": result.stderr,
            })

        if result.exit_code != 0:
            stderr_lower = result.stderr.lower()
            if "session" in stderr_lower and "not found" in stderr_lower:
                raise SessionNotFoundError(params.session, {"stderr": result.stderr})
            if "timeout" in stderr_lower:
                raise ExecutionTimeoutError(params.timeout, {"stderr": result.stderr})
            if "traceback" in stderr_lower or "error" in stderr_lower:
                raise KernelError(result.stderr, {"exit_code": result.exit_code})
            error_code, status_code, details = classify_cli_error(result.stderr, result.exit_code)
            if error_code == "AUTH_EXPIRED":
                raise AuthExpiredError(details)
            elif error_code == "QUOTA_EXCEEDED":
                raise QuotaExceededError(details)
            else:
                raise CLIError(result.stderr or "Execution failed", result.exit_code, details)

        return ExecutionResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            execution_time=execution_time,
        )

    # --- Phase E: URL/Log Operations ---

    DEFAULT_URL_TIMEOUT = 30
    DEFAULT_LOG_TIMEOUT = 30

    def get_session_url(self, params: SessionGetURLParams) -> SessionGetURLResult:
        """Get the browser URL for a Colab session.

        Args:
            params: Session name and optional host

        Returns:
            SessionGetURLResult with the full URL

        Raises:
            SessionNotFoundError: If session doesn't exist
            CLIError: For other CLI errors
        """
        if not params.session:
            raise SessionNotFoundError("unknown", {"reason": "empty session name"})

        args = ["url", "--session", params.session]
        if params.host:
            args.extend(["--host", params.host])

        result = self._run_cli(args, timeout=self.DEFAULT_URL_TIMEOUT)

        if result.timed_out:
            raise ExecutionTimeoutError(self.DEFAULT_URL_TIMEOUT)

        if result.exit_code != 0:
            error_code, status_code, details = classify_cli_error(result.stderr, result.exit_code)
            if error_code == "SESSION_NOT_FOUND":
                raise SessionNotFoundError(params.session, details)
            elif error_code == "AUTH_EXPIRED":
                raise AuthExpiredError(details)
            elif error_code == "QUOTA_EXCEEDED":
                raise QuotaExceededError(details)
            else:
                raise CLIError(result.stderr or "URL fetch failed", result.exit_code, details)

        url = parse_url_output(result.stdout)
        if not url:
            raise CLIError("No URL found in output", result.exit_code, {"stdout": result.stdout})

        return SessionGetURLResult(url=url)

    async def get_session_url_async(self, params: SessionGetURLParams) -> SessionGetURLResult:
        """Async version of get_session_url."""
        if not params.session:
            raise SessionNotFoundError("unknown", {"reason": "empty session name"})

        args = ["url", "--session", params.session]
        if params.host:
            args.extend(["--host", params.host])

        result = await self._run_cli_async(args, timeout=self.DEFAULT_URL_TIMEOUT)

        if result.timed_out:
            raise ExecutionTimeoutError(self.DEFAULT_URL_TIMEOUT)

        if result.exit_code != 0:
            error_code, status_code, details = classify_cli_error(result.stderr, result.exit_code)
            if error_code == "SESSION_NOT_FOUND":
                raise SessionNotFoundError(params.session, details)
            elif error_code == "AUTH_EXPIRED":
                raise AuthExpiredError(details)
            elif error_code == "QUOTA_EXCEEDED":
                raise QuotaExceededError(details)
            else:
                raise CLIError(result.stderr or "URL fetch failed", result.exit_code, details)

        url = parse_url_output(result.stdout)
        if not url:
            raise CLIError("No URL found in output", result.exit_code, {"stdout": result.stdout})

        return SessionGetURLResult(url=url)

    def get_session_log(self, params: SessionLogParams) -> SessionLogResult:
        """Get session history logs.

        Args:
            params: Session name (optional), lines limit, and type filter

        Returns:
            SessionLogResult with log lines or session list

        Raises:
            SessionNotFoundError: If session doesn't exist or has no history
            CLIError: For other CLI errors
        """
        args = ["log"]
        if params.session:
            args.extend(["--session", params.session])
        if params.lines:
            args.extend(["--lines", str(params.lines)])
        if params.type:
            args.extend(["--type", params.type])

        result = self._run_cli(args, timeout=self.DEFAULT_LOG_TIMEOUT)

        if result.timed_out:
            raise ExecutionTimeoutError(self.DEFAULT_LOG_TIMEOUT)

        if result.exit_code != 0:
            error_code, status_code, details = classify_cli_error(result.stderr, result.exit_code)
            if error_code == "SESSION_NOT_FOUND":
                raise SessionNotFoundError(params.session or "unknown", details)
            elif error_code == "AUTH_EXPIRED":
                raise AuthExpiredError(details)
            elif error_code == "QUOTA_EXCEEDED":
                raise QuotaExceededError(details)
            else:
                raise CLIError(result.stderr or "Log fetch failed", result.exit_code, details)

        if params.session:
            logs = parse_log_output(result.stdout)
            return SessionLogResult(logs=logs, session=params.session)
        else:
            sessions = parse_log_list_output(result.stdout)
            return SessionLogResult(logs=sessions, session=None)

    async def get_session_log_async(self, params: SessionLogParams) -> SessionLogResult:
        """Async version of get_session_log."""
        args = ["log"]
        if params.session:
            args.extend(["--session", params.session])
        if params.lines:
            args.extend(["--lines", str(params.lines)])
        if params.type:
            args.extend(["--type", params.type])

        result = await self._run_cli_async(args, timeout=self.DEFAULT_LOG_TIMEOUT)

        if result.timed_out:
            raise ExecutionTimeoutError(self.DEFAULT_LOG_TIMEOUT)

        if result.exit_code != 0:
            error_code, status_code, details = classify_cli_error(result.stderr, result.exit_code)
            if error_code == "SESSION_NOT_FOUND":
                raise SessionNotFoundError(params.session or "unknown", details)
            elif error_code == "AUTH_EXPIRED":
                raise AuthExpiredError(details)
            elif error_code == "QUOTA_EXCEEDED":
                raise QuotaExceededError(details)
            else:
                raise CLIError(result.stderr or "Log fetch failed", result.exit_code, details)

        if params.session:
            logs = parse_log_output(result.stdout)
            return SessionLogResult(logs=logs, session=params.session)
        else:
            sessions = parse_log_list_output(result.stdout)
            return SessionLogResult(logs=sessions, session=None)

    def execute_file(self, params: FileExecuteParams) -> ExecutionResult:
        """Execute a Python file in a Colab session.

        Args:
            params: Execution parameters (session, file_path, timeout, env)

        Returns:
            ExecutionResult with stdout, stderr, exit_code, execution_time

        Raises:
            SessionNotFoundError: If session doesn't exist
            ExecutionTimeoutError: If execution exceeds timeout
            KernelError: If kernel returns an error
            CLIError: For other CLI errors (including file not found)
        """
        if not params.session:
            raise SessionNotFoundError("unknown", {"reason": "empty session name"})

        import time
        start_time = time.time()

        args = ["exec", "--session", params.session, "--file", params.file_path]

        result = self._run_cli(args, timeout=params.timeout)

        execution_time = time.time() - start_time

        if result.timed_out:
            raise ExecutionTimeoutError(params.timeout, {
                "session": params.session,
                "partial_stdout": result.stdout,
                "partial_stderr": result.stderr,
            })

        if result.exit_code != 0:
            stderr_lower = result.stderr.lower()
            if "session" in stderr_lower and "not found" in stderr_lower:
                raise SessionNotFoundError(params.session, {"stderr": result.stderr})
            if "timeout" in stderr_lower:
                raise ExecutionTimeoutError(params.timeout, {"stderr": result.stderr})
            if "no such file" in stderr_lower or "file not found" in stderr_lower:
                raise CLIError(
                f"File not found: {params.file_path}",
                result.exit_code,
                {"file_path": params.file_path},
            )
            if "traceback" in stderr_lower or "error" in stderr_lower:
                raise KernelError(result.stderr, {"exit_code": result.exit_code})
            error_code, status_code, details = classify_cli_error(result.stderr, result.exit_code)
            if error_code == "AUTH_EXPIRED":
                raise AuthExpiredError(details)
            elif error_code == "QUOTA_EXCEEDED":
                raise QuotaExceededError(details)
            else:
                raise CLIError(result.stderr or "Execution failed", result.exit_code, details)

        return ExecutionResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            execution_time=execution_time,
        )

    async def execute_file_async(self, params: FileExecuteParams) -> ExecutionResult:
        """Async version of execute_file."""
        if not params.session:
            raise SessionNotFoundError("unknown", {"reason": "empty session name"})

        import time
        start_time = time.time()

        args = ["exec", "--session", params.session, "--file", params.file_path]

        result = await self._run_cli_async(args, timeout=params.timeout)

        execution_time = time.time() - start_time

        if result.timed_out:
            raise ExecutionTimeoutError(params.timeout, {
                "session": params.session,
                "partial_stdout": result.stdout,
                "partial_stderr": result.stderr,
            })

        if result.exit_code != 0:
            stderr_lower = result.stderr.lower()
            if "session" in stderr_lower and "not found" in stderr_lower:
                raise SessionNotFoundError(params.session, {"stderr": result.stderr})
            if "timeout" in stderr_lower:
                raise ExecutionTimeoutError(params.timeout, {"stderr": result.stderr})
            if "no such file" in stderr_lower or "file not found" in stderr_lower:
                raise CLIError(
                f"File not found: {params.file_path}",
                result.exit_code,
                {"file_path": params.file_path},
            )
            if "traceback" in stderr_lower or "error" in stderr_lower:
                raise KernelError(result.stderr, {"exit_code": result.exit_code})
            error_code, status_code, details = classify_cli_error(result.stderr, result.exit_code)
            if error_code == "AUTH_EXPIRED":
                raise AuthExpiredError(details)
            elif error_code == "QUOTA_EXCEEDED":
                raise QuotaExceededError(details)
            else:
                raise CLIError(result.stderr or "Execution failed", result.exit_code, details)

        return ExecutionResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            execution_time=execution_time,
        )
