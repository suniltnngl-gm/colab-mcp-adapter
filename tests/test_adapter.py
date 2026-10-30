"""Unit tests for Colab MCP Adapter - Phase C session lifecycle tools.

Tests use mocked subprocess to avoid real CLI calls.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from colab_mcp_adapter.adapter import ColabAdapter, CLIResult
from colab_mcp_adapter.contracts import (
    SessionCreateParams,
    SessionGetParams,
    SessionStopParams,
    CodeExecuteParams,
    FileExecuteParams,
    ExecutionResult,
    SessionGetURLParams,
    SessionGetURLResult,
    SessionLogParams,
    SessionLogResult,
    SessionNotFoundError,
    SessionAlreadyExistsError,
    SessionNotReadyError,
    ExecutionTimeoutError,
    KernelError,
    AuthExpiredError,
    QuotaExceededError,
    CLIError,
)
from colab_mcp_adapter.parser import (
    parse_session_line,
    parse_sessions_output,
    parse_status_output,
    parse_create_output,
    validate_session_id,
    classify_cli_error,
    parse_url_output,
    parse_log_output,
    parse_log_list_output,
    ParsedSession,
)


# --- Parser Tests ---

class TestSessionLineParsing:
    """Tests for parsing session lines from CLI output."""

    def test_parse_session_line_with_status(self):
        line = "[test-session] m-s-abc123 | Hardware: GPU | Shape: Standard | Variant: T4 | Status: IDLE"
        parsed = parse_session_line(line)
        
        assert parsed is not None
        assert parsed.name == "test-session"
        assert parsed.session_id == "m-s-abc123"
        assert parsed.hardware == "GPU"
        assert parsed.shape == "Standard"
        assert parsed.variant == "T4"
        assert parsed.status == "IDLE"

    def test_parse_session_line_without_status(self):
        line = "[test-session] m-s-abc123 | Hardware: CPU | Shape: Standard | Variant: DEFAULT"
        parsed = parse_session_line(line)
        
        assert parsed is not None
        assert parsed.name == "test-session"
        assert parsed.session_id == "m-s-abc123"
        assert parsed.hardware == "CPU"
        assert parsed.shape == "Standard"
        assert parsed.variant == "DEFAULT"
        assert parsed.status is None

    def test_parse_session_line_invalid_format(self):
        line = "not a valid session line"
        parsed = parse_session_line(line)
        assert parsed is None

    def test_parse_session_line_empty(self):
        assert parse_session_line("") is None
        assert parse_session_line("   ") is None

    def test_parse_session_line_colab_prefix(self):
        # Lines starting with [colab] are informational, not session lines
        line = "[colab] Creating session 'test'..."
        parsed = parse_session_line(line)
        assert parsed is None

    def test_parse_sessions_output_multiple(self):
        output = """[session1] m-s-id1 | Hardware: CPU | Shape: Standard | Variant: DEFAULT | Status: IDLE
[session2] m-s-id2 | Hardware: GPU | Shape: High-Mem | Variant: T4 | Status: RUNNING"""
        sessions = parse_sessions_output(output)
        
        assert len(sessions) == 2
        assert sessions[0].name == "session1"
        assert sessions[1].name == "session2"

    def test_parse_sessions_output_with_colab_lines(self):
        output = """[colab] Creating session 'test'...
[session1] m-s-id1 | Hardware: CPU | Shape: Standard | Variant: DEFAULT | Status: IDLE
[colab] Session READY."""
        sessions = parse_sessions_output(output)
        
        assert len(sessions) == 1
        assert sessions[0].name == "session1"

    def test_parse_sessions_output_empty(self):
        output = "[colab] No active sessions found on server."
        sessions = parse_sessions_output(output)
        assert sessions == []

    def test_parse_status_output(self):
        output = """[test-session] m-s-abc123 | Hardware: GPU | Shape: Standard | Variant: T4 | Status: RUNNING"""
        parsed = parse_status_output(output)
        
        assert parsed is not None
        assert parsed.name == "test-session"
        assert parsed.session_id == "m-s-abc123"
        assert parsed.status == "RUNNING"

    def test_parse_create_output(self):
        output = """[colab] Creating session 'my-session'...
[colab] Session READY."""
        parsed = parse_create_output(output)
        
        assert parsed is not None
        assert parsed.name == "my-session"
        assert parsed.status == "CREATING"

    def test_parse_create_output_no_match(self):
        output = "[colab] Session READY."
        parsed = parse_create_output(output)
        assert parsed is None


class TestSessionIdValidation:
    """Tests for session ID validation."""

    def test_valid_session_ids(self):
        assert validate_session_id("m-s-abc123")
        assert validate_session_id("m-s-use4b1-2c0p5n2ccm9l5")
        assert validate_session_id("m-s-a1b2c3")

    def test_invalid_session_ids(self):
        assert not validate_session_id("m-s-")
        assert not validate_session_id("m-x-abc123")
        assert not validate_session_id("abc123")
        assert not validate_session_id("")
        assert not validate_session_id("m-s-ABC123")  # uppercase not allowed


class TestErrorClassification:
    """Tests for CLI error classification."""

    def test_session_not_found(self):
        stderr = "[colab] Session 'my-session' not found."
        code, status, details = classify_cli_error(stderr, 1)
        assert code == "SESSION_NOT_FOUND"
        assert status == 404
        assert details["session_name"] == "my-session"

    def test_already_exists(self):
        stderr = "Error: session already exists"
        code, status, details = classify_cli_error(stderr, 1)
        assert code == "SESSION_ALREADY_EXISTS"
        assert status == 409

    def test_not_ready(self):
        stderr = "Session not ready for operation"
        code, status, details = classify_cli_error(stderr, 1)
        assert code == "SESSION_NOT_READY"
        assert status == 409

    def test_timeout(self):
        stderr = "Timeout waiting for reply"
        code, status, details = classify_cli_error(stderr, 1)
        assert code == "EXECUTION_TIMEOUT"
        assert status == 408

    def test_quota_exceeded(self):
        stderr = "quota exceeded for this account"
        code, status, details = classify_cli_error(stderr, 1)
        assert code == "QUOTA_EXCEEDED"
        assert status == 429

    def test_auth_expired(self):
        stderr = "authentication failed: token expired"
        code, status, details = classify_cli_error(stderr, 1)
        assert code == "AUTH_EXPIRED"
        assert status == 401

    def test_generic_cli_error(self):
        stderr = "Unknown error occurred"
        code, status, details = classify_cli_error(stderr, 2)
        assert code == "CLI_ERROR"
        assert status == 500
        assert details["exit_code"] == 2


# --- Adapter Tests (Mocked) ---

class MockedColabAdapter(ColabAdapter):
    """ColabAdapter with mocked _run_cli for testing."""
    
    def __init__(self, mock_results: dict[tuple[str, ...], CLIResult]):
        super().__init__(colab_cmd="colab")
        self._mock_results = mock_results
        self._call_log: list[tuple[list[str], int, str | None]] = []
    
    def _run_cli(self, args: list[str], timeout: int, stdin_input: str | None = None) -> CLIResult:
        """Mock _run_cli - receives args WITHOUT colab_cmd prefix (since we override the method)."""
        self._call_log.append((args, timeout, stdin_input))
        key = tuple(args)
        return self._mock_results.get(key, CLIResult(0, "", ""))


class TestColabAdapterCreateSession:
    """Tests for create_session with mocked CLI."""

    def test_create_session_basic(self):
        mock_results = {
            ("new",): CLIResult(0, "[colab] Creating session 'test'...\n[colab] Session READY.\n", ""),
            ("status", "--session", "test"): CLIResult(
                0,
                "[test] m-s-abc123 | Hardware: CPU | Shape: Standard | Variant: DEFAULT | Status: IDLE\n",
                ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.create_session(SessionCreateParams())
        
        assert result.name == "test"
        assert result.session_id == "m-s-abc123"
        assert result.hardware == "CPU"
        assert result.shape == "Standard"
        assert result.variant == "DEFAULT"
        assert result.status == "IDLE"

    def test_create_session_with_name(self):
        mock_results = {
            ("new", "--session", "my-session"): CLIResult(
                0, "[colab] Creating session 'my-session'...\n[colab] Session READY.\n", ""
            ),
            ("status", "--session", "my-session"): CLIResult(
                0,
                "[my-session] m-s-xyz789 | Hardware: GPU | Shape: High-Mem | Variant: T4 | Status: IDLE\n",
                ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.create_session(SessionCreateParams(name="my-session"))
        
        assert result.name == "my-session"
        assert result.session_id == "m-s-xyz789"

    def test_create_session_with_gpu(self):
        mock_results = {
            ("new", "--gpu", "T4"): CLIResult(0, "[colab] Creating session 'auto-name'...\n[colab] Session READY.\n", ""),
            ("status", "--session", "auto-name"): CLIResult(
                0,
                "[auto-name] m-s-gpu1 | Hardware: GPU | Shape: Standard | Variant: T4 | Status: IDLE\n",
                ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.create_session(SessionCreateParams(gpu="T4"))
        
        assert result.hardware == "GPU"
        assert result.variant == "T4"

    def test_create_session_already_exists(self):
        mock_results = {
            ("new", "--session", "existing"): CLIResult(1, "", "Error: session already exists"),
        }
        adapter = MockedColabAdapter(mock_results)
        
        with pytest.raises(SessionAlreadyExistsError):
            adapter.create_session(SessionCreateParams(name="existing"))

    def test_create_session_quota_exceeded(self):
        mock_results = {
            ("new",): CLIResult(1, "", "quota exceeded for this account"),
        }
        adapter = MockedColabAdapter(mock_results)
        
        with pytest.raises(QuotaExceededError):
            adapter.create_session(SessionCreateParams())


class TestColabAdapterListSessions:
    """Tests for list_sessions with mocked CLI."""

    def test_list_sessions_multiple(self):
        mock_results = {
            ("sessions",): CLIResult(
                0,
                """[session1] m-s-id1 | Hardware: CPU | Shape: Standard | Variant: DEFAULT | Status: IDLE
[session2] m-s-id2 | Hardware: GPU | Shape: High-Mem | Variant: T4 | Status: RUNNING""",
                ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.list_sessions()
        
        assert len(result.sessions) == 2
        assert result.sessions[0].name == "session1"
        assert result.sessions[1].name == "session2"

    def test_list_sessions_empty(self):
        mock_results = {
            ("sessions",): CLIResult(0, "[colab] No active sessions found on server.\n", ""),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.list_sessions()
        
        assert result.sessions == []


class TestColabAdapterGetSession:
    """Tests for get_session with mocked CLI."""

    def test_get_session_found(self):
        mock_results = {
            ("status", "--session", "test"): CLIResult(
                0,
                "[test] m-s-abc123 | Hardware: CPU | Shape: Standard | Variant: DEFAULT | Status: IDLE\n",
                ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.get_session(SessionGetParams(name="test"))
        
        assert result.name == "test"
        assert result.session_id == "m-s-abc123"
        assert result.status == "IDLE"

    def test_get_session_not_found(self):
        mock_results = {
            ("status", "--session", "nonexistent"): CLIResult(
                1, "", "[colab] Session 'nonexistent' not found.\n"
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        with pytest.raises(SessionNotFoundError) as exc_info:
            adapter.get_session(SessionGetParams(name="nonexistent"))
        
        assert exc_info.value.details["session_name"] == "nonexistent"

    def test_get_session_empty_name(self):
        adapter = MockedColabAdapter({})
        
        with pytest.raises(SessionNotFoundError):
            adapter.get_session(SessionGetParams(name=""))


class TestColabAdapterStopSession:
    """Tests for stop_session with mocked CLI."""

    def test_stop_session_success(self):
        mock_results = {
            ("stop", "--session", "test"): CLIResult(
                0, "[colab] Stopping session 'test'...\n[colab] Session terminated.\n", ""
            ),
            ("status", "--session", "test"): CLIResult(
                1, "", "[colab] Session 'test' not found.\n"
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.stop_session(SessionStopParams(name="test"))
        
        assert result.name == "test"
        assert result.terminated is True

    def test_stop_session_not_found(self):
        mock_results = {
            ("stop", "--session", "nonexistent"): CLIResult(
                1, "", "[colab] Session 'nonexistent' not found.\n"
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        with pytest.raises(SessionNotFoundError):
            adapter.stop_session(SessionStopParams(name="nonexistent"))

    def test_stop_session_still_exists_after_stop(self):
        mock_results = {
            ("stop", "--session", "test"): CLIResult(0, "[colab] Stopping session 'test'...\n[colab] Session terminated.\n", ""),
            ("status", "--session", "test"): CLIResult(
                0, "[test] m-s-abc123 | Hardware: CPU | Shape: Standard | Variant: DEFAULT | Status: IDLE\n", ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        with pytest.raises(SessionNotReadyError):
            adapter.stop_session(SessionStopParams(name="test"))


# --- Contract Model Tests ---

class TestContractModels:
    """Tests for Pydantic contract models."""

    def test_session_create_params_defaults(self):
        params = SessionCreateParams()
        assert params.name is None
        assert params.gpu is None
        assert params.tpu is None
        assert params.high_mem is False

    def test_session_create_params_all_fields(self):
        params = SessionCreateParams(
            name="test",
            gpu="T4",
            tpu="v5e1",
            high_mem=True,
        )
        assert params.name == "test"
        assert params.gpu == "T4"
        assert params.tpu == "v5e1"
        assert params.high_mem is True

    def test_session_info_model(self):
        from colab_mcp_adapter.contracts import SessionInfo
        info = SessionInfo(
            name="test",
            session_id="m-s-abc123",
            hardware="GPU",
            shape="Standard",
            variant="T4",
            status="IDLE",
        )
        assert info.name == "test"
        assert info.session_id == "m-s-abc123"


class TestExecutionContractModels:
    """Tests for Phase D execution contract models."""

    def test_code_execute_params_defaults(self):
        params = CodeExecuteParams(session="test", code="print('hello')")
        assert params.session == "test"
        assert params.code == "print('hello')"
        assert params.timeout == 30
        assert params.env is None

    def test_code_execute_params_all_fields(self):
        params = CodeExecuteParams(
            session="test",
            code="print('hello')",
            timeout=60,
            env={"FOO": "bar", "BAZ": "qux"},
        )
        assert params.session == "test"
        assert params.code == "print('hello')"
        assert params.timeout == 60
        assert params.env == {"FOO": "bar", "BAZ": "qux"}

    def test_code_execute_params_timeout_validation(self):
        with pytest.raises(Exception):  # Pydantic validation error
            CodeExecuteParams(session="test", code="print()", timeout=0)
        with pytest.raises(Exception):
            CodeExecuteParams(session="test", code="print()", timeout=301)

    def test_file_execute_params_defaults(self):
        params = FileExecuteParams(session="test", file_path="/path/to/script.py")
        assert params.session == "test"
        assert params.file_path == "/path/to/script.py"
        assert params.timeout == 30
        assert params.env is None

    def test_execution_result_model(self):
        result = ExecutionResult(
            stdout="hello\n",
            stderr="",
            exit_code=0,
            execution_time=1.5,
        )
        assert result.stdout == "hello\n"
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.execution_time == 1.5


# --- Adapter Tests for Phase D: Execution ---

class TestColabAdapterExecuteCode:
    """Tests for execute_code with mocked CLI."""

    def test_execute_code_basic(self):
        mock_results = {
            ("exec", "--session", "test"): CLIResult(
                0, "hello\n", ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.execute_code(CodeExecuteParams(session="test", code="print('hello')"))
        
        assert result.stdout == "hello\n"
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.execution_time >= 0

    def test_execute_code_with_env(self):
        mock_results = {
            ("exec", "--session", "test"): CLIResult(
                0, "FOO=bar\n", ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.execute_code(
            CodeExecuteParams(
                session="test",
                code="import os; print(os.environ.get('FOO'))",
                env={"FOO": "bar"},
            )
        )
        
        assert result.stdout == "FOO=bar\n"

    def test_execute_code_session_not_found(self):
        mock_results = {
            ("exec", "--session", "nonexistent"): CLIResult(
                1, "", "[colab] Session 'nonexistent' not found.\n"
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        with pytest.raises(SessionNotFoundError):
            adapter.execute_code(CodeExecuteParams(session="nonexistent", code="print()"))

    def test_execute_code_timeout(self):
        mock_results = {
            ("exec", "--session", "test"): CLIResult(
                -1, "", "", timed_out=True
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        with pytest.raises(ExecutionTimeoutError) as exc_info:
            adapter.execute_code(CodeExecuteParams(session="test", code="import time; time.sleep(100)", timeout=10))
        
        assert exc_info.value.details["timeout_seconds"] == 10

    def test_execute_code_kernel_error(self):
        mock_results = {
            ("exec", "--session", "test"): CLIResult(
                1, "", "Traceback (most recent call last):\n  File ...\nNameError: name 'x' is not defined\n"
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        with pytest.raises(KernelError):
            adapter.execute_code(CodeExecuteParams(session="test", code="print(x)"))


class TestColabAdapterExecuteFile:
    """Tests for execute_file with mocked CLI."""

    def test_execute_file_basic(self):
        mock_results = {
            ("exec", "--session", "test", "--file", "/path/script.py"): CLIResult(
                0, "from file\n", ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.execute_file(FileExecuteParams(session="test", file_path="/path/script.py"))
        
        assert result.stdout == "from file\n"
        assert result.stderr == ""
        assert result.exit_code == 0

    def test_execute_file_session_not_found(self):
        mock_results = {
            ("exec", "--session", "nonexistent", "--file", "/path/script.py"): CLIResult(
                1, "", "[colab] Session 'nonexistent' not found.\n"
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        with pytest.raises(SessionNotFoundError):
            adapter.execute_file(FileExecuteParams(session="nonexistent", file_path="/path/script.py"))

    def test_execute_file_not_found(self):
        mock_results = {
            ("exec", "--session", "test", "--file", "/nonexistent.py"): CLIResult(
                1, "", "Error: no such file or directory: '/nonexistent.py'\n"
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        with pytest.raises(CLIError) as exc_info:
            adapter.execute_file(FileExecuteParams(session="test", file_path="/nonexistent.py"))
        
        assert "File not found" in exc_info.value.message

    def test_execute_file_timeout(self):
        mock_results = {
            ("exec", "--session", "test", "--file", "/path/slow.py"): CLIResult(
                -1, "", "", timed_out=True
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        with pytest.raises(ExecutionTimeoutError):
            adapter.execute_file(FileExecuteParams(session="test", file_path="/path/slow.py", timeout=5))

    def test_execute_file_kernel_error(self):
        mock_results = {
            ("exec", "--session", "test", "--file", "/path/error.py"): CLIResult(
                1, "", "Traceback (most recent call last):\nValueError: test error\n"
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        with pytest.raises(KernelError):
            adapter.execute_file(FileExecuteParams(session="test", file_path="/path/error.py"))


# --- Phase E: URL/Log Parser Tests ---

class TestUrlParsing:
    """Tests for parsing URL output."""

    def test_parse_url_output(self):
        output = "https://colab.research.google.com/notebooks/empty.ipynb?dbu=%2Ftun%2Fm%2Fm-s-test#datalabBackendUrl=https://colab.research.google.com/tun/m/m-s-test"
        url = parse_url_output(output)
        assert url == output

    def test_parse_url_output_with_colab_prefix(self):
        output = """[colab] Getting URL...
https://colab.research.google.com/notebooks/empty.ipynb?dbu=..."""
        url = parse_url_output(output)
        assert url == "https://colab.research.google.com/notebooks/empty.ipynb?dbu=..."

    def test_parse_url_output_no_url(self):
        output = "[colab] Session 'test' not found."
        url = parse_url_output(output)
        assert url is None

    def test_parse_url_output_empty(self):
        assert parse_url_output("") is None


class TestLogParsing:
    """Tests for parsing log output."""

    def test_parse_log_output_with_events(self):
        output = """[2026-10-30 13:34:27] EVENT: session_created
[2026-10-30 13:35:50] EXEC: print('hello')..."""
        logs = parse_log_output(output)
        assert len(logs) == 2
        assert logs[0] == "[2026-10-30 13:34:27] EVENT: session_created"
        assert logs[1] == "[2026-10-30 13:35:50] EXEC: print('hello')..."

    def test_parse_log_output_skips_colab_lines(self):
        output = """[colab] Getting logs...
[2026-10-30 13:34:27] EVENT: session_created"""
        logs = parse_log_output(output)
        assert len(logs) == 1
        assert logs[0] == "[2026-10-30 13:34:27] EVENT: session_created"

    def test_parse_log_output_empty(self):
        assert parse_log_output("") == []
        assert parse_log_output("[colab] No history found") == []


class TestLogListParsing:
    """Tests for parsing log list output (no session)."""

    def test_parse_log_list_output(self):
        output = """[colab] Sessions with history logs:
  session1
  session2
  test-session"""
        sessions = parse_log_list_output(output)
        assert sessions == ["session1", "session2", "test-session"]

    def test_parse_log_list_output_empty(self):
        assert parse_log_list_output("") == []


# --- Phase E: URL/Log Adapter Tests ---

class TestColabAdapterGetSessionUrl:
    """Tests for get_session_url with mocked CLI."""

    def test_get_session_url_basic(self):
        mock_results = {
            ("url", "--session", "test"): CLIResult(
                0, "https://colab.research.google.com/notebooks/empty.ipynb?dbu=test", ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.get_session_url(SessionGetURLParams(session="test"))
        
        assert result.url == "https://colab.research.google.com/notebooks/empty.ipynb?dbu=test"

    def test_get_session_url_with_host(self):
        mock_results = {
            ("url", "--session", "test", "--host", "https://custom.colab.com"): CLIResult(
                0, "https://custom.colab.com/notebooks/empty.ipynb?dbu=test", ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.get_session_url(SessionGetURLParams(session="test", host="https://custom.colab.com"))
        
        assert result.url == "https://custom.colab.com/notebooks/empty.ipynb?dbu=test"

    def test_get_session_url_not_found(self):
        mock_results = {
            ("url", "--session", "nonexistent"): CLIResult(
                1, "", "[colab] Session 'nonexistent' not found.\n"
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        with pytest.raises(SessionNotFoundError):
            adapter.get_session_url(SessionGetURLParams(session="nonexistent"))

    def test_get_session_url_empty_name(self):
        adapter = MockedColabAdapter({})
        
        with pytest.raises(SessionNotFoundError):
            adapter.get_session_url(SessionGetURLParams(session=""))


class TestColabAdapterGetSessionLog:
    """Tests for get_session_log with mocked CLI."""

    def test_get_session_log_with_session(self):
        mock_results = {
            ("log", "--session", "test"): CLIResult(
                0, """[2026-10-30 13:34:27] EVENT: session_created
[2026-10-30 13:35:50] EXEC: print('hello')...""", ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.get_session_log(SessionLogParams(session="test"))
        
        assert result.session == "test"
        assert len(result.logs) == 2
        assert result.logs[0] == "[2026-10-30 13:34:27] EVENT: session_created"

    def test_get_session_log_with_lines(self):
        mock_results = {
            ("log", "--session", "test", "--lines", "5"): CLIResult(
                0, "[2026-10-30 13:34:27] EVENT: session_created", ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.get_session_log(SessionLogParams(session="test", lines=5))
        
        assert result.session == "test"

    def test_get_session_log_with_type(self):
        mock_results = {
            ("log", "--session", "test", "--type", "execution"): CLIResult(
                0, "[2026-10-30 13:35:50] EXEC: print('hello')...", ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.get_session_log(SessionLogParams(session="test", type="execution"))
        
        assert result.session == "test"
        assert result.logs[0].startswith("[2026-10-30 13:35:50] EXEC:")

    def test_get_session_log_list_all(self):
        mock_results = {
            ("log",): CLIResult(
                0, """[colab] Sessions with history logs:
  session1
  session2""", ""
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        result = adapter.get_session_log(SessionLogParams())
        
        assert result.session is None
        assert result.logs == ["session1", "session2"]

    def test_get_session_log_not_found(self):
        mock_results = {
            ("log", "--session", "nonexistent"): CLIResult(
                1, "", "[colab] No history found for session 'nonexistent'.\n"
            ),
        }
        adapter = MockedColabAdapter(mock_results)
        
        with pytest.raises(SessionNotFoundError):
            adapter.get_session_log(SessionLogParams(session="nonexistent"))