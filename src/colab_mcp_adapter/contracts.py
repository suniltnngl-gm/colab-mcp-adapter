"""MCP tool contracts for Colab operations.

Phase C: Session lifecycle tools (create, list, get, stop).
Phase D: Code/file execution tools.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field


# --- Common Types ---

class SessionInfo(BaseModel):
    """Information about a Colab session."""
    name: str = Field(description="Display name of the session")
    session_id: str = Field(description="Unique session ID (format: m-s-<alphanumeric>)")
    hardware: str = Field(description="Hardware type (CPU, T4, L4, etc.)")
    shape: str = Field(description="Machine shape (Standard, High-Mem, etc.)")
    variant: str = Field(description="Variant (DEFAULT, etc.)")
    status: Optional[str] = Field(default=None, description="Session status (IDLE, RUNNING, CREATING)")


class SessionCreateParams(BaseModel):
    """Parameters for creating a new Colab session."""
    name: Optional[str] = Field(default=None, description="Optional session name (auto-generated if omitted)")
    gpu: Optional[str] = Field(default=None, description="GPU variant: T4, L4, G4, H100, A100")
    tpu: Optional[str] = Field(default=None, description="TPU variant: v5e1, v6e1")
    high_mem: bool = Field(default=False, description="Request high-RAM machine shape (requires Pro/Pro+)")


class SessionCreateResult(BaseModel):
    """Result of session creation."""
    name: str
    session_id: str
    hardware: str
    shape: str
    variant: str
    status: str = "CREATING"


class SessionListResult(BaseModel):
    """Result of listing sessions."""
    sessions: list[SessionInfo]


class SessionGetParams(BaseModel):
    """Parameters for getting session status."""
    name: str = Field(description="Session display name")


class SessionGetResult(BaseModel):
    """Result of getting session status."""
    name: str
    session_id: str
    hardware: str
    shape: str
    variant: str
    status: str


class SessionStopParams(BaseModel):
    """Parameters for stopping a session."""
    name: str = Field(description="Session display name")


class SessionStopResult(BaseModel):
    """Result of stopping a session."""
    name: str
    terminated: bool = True


# --- Phase D: Code/File Execution Types ---

class CodeExecuteParams(BaseModel):
    """Parameters for executing code in a Colab session."""
    session: str = Field(description="Session display name")
    code: str = Field(description="Python code to execute")
    timeout: int = Field(default=30, description="Execution timeout in seconds", ge=1, le=300)
    env: Optional[dict[str, str]] = Field(default=None, description="Environment variables to set")


class FileExecuteParams(BaseModel):
    """Parameters for executing a file in a Colab session."""
    session: str = Field(description="Session display name")
    file_path: str = Field(description="Path to Python file to execute")
    timeout: int = Field(default=30, description="Execution timeout in seconds", ge=1, le=300)
    env: Optional[dict[str, str]] = Field(default=None, description="Environment variables to set")


class ExecutionResult(BaseModel):
    """Result of code/file execution."""
    stdout: str = Field(description="Standard output from execution")
    stderr: str = Field(description="Standard error from execution")
    exit_code: int = Field(description="Process exit code (0 = success)")
    execution_time: float = Field(description="Execution time in seconds")


# --- Phase E: URL/Log Types ---

class SessionGetURLParams(BaseModel):
    """Parameters for getting session URL."""
    session: str = Field(description="Session display name")
    host: Optional[str] = Field(default=None, description="Colab frontend host (default: https://colab.research.google.com)")


class SessionGetURLResult(BaseModel):
    """Result of getting session URL."""
    url: str = Field(description="Full Colab browser URL for the session")


class SessionLogParams(BaseModel):
    """Parameters for getting session logs."""
    session: Optional[str] = Field(default=None, description="Session display name (omit to list all sessions with logs)")
    lines: Optional[int] = Field(default=None, description="Number of lines to show (default: all)", ge=1)
    type: Optional[str] = Field(default=None, description="Filter by event type (e.g., execution, file_operation, session_created)")


class SessionLogResult(BaseModel):
    """Result of getting session logs."""
    logs: list[str] = Field(description="Log lines")
    session: Optional[str] = Field(default=None, description="Session name (None if listing all sessions)")


# --- Error Types ---

class ColabMCPError(Exception):
    """Base exception for Colab MCP adapter errors."""
    
    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 500,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class SessionNotFoundError(ColabMCPError):
    """Session not found."""
    def __init__(self, name: str, details: Optional[dict] = None):
        super().__init__(
            f"Session '{name}' not found",
            "SESSION_NOT_FOUND",
            404,
            {"session_name": name, **(details or {})},
        )


class SessionAlreadyExistsError(ColabMCPError):
    """Session name already exists."""
    def __init__(self, name: str, details: Optional[dict] = None):
        super().__init__(
            f"Session '{name}' already exists",
            "SESSION_ALREADY_EXISTS",
            409,
            {"session_name": name, **(details or {})},
        )


class SessionNotReadyError(ColabMCPError):
    """Session not ready for operation."""
    def __init__(self, name: str, details: Optional[dict] = None):
        super().__init__(
            f"Session '{name}' not ready",
            "SESSION_NOT_READY",
            409,
            {"session_name": name, **(details or {})},
        )


class ExecutionTimeoutError(ColabMCPError):
    """Execution timed out."""
    def __init__(self, timeout: int, details: Optional[dict] = None):
        super().__init__(
            f"Execution timed out after {timeout}s",
            "EXECUTION_TIMEOUT",
            408,
            {"timeout_seconds": timeout, **(details or {})},
        )


class KernelError(ColabMCPError):
    """Kernel execution error."""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            f"Kernel error: {message}",
            "KERNEL_ERROR",
            500,
            details or {},
        )


class AuthExpiredError(ColabMCPError):
    """Authentication expired."""
    def __init__(self, details: Optional[dict] = None):
        super().__init__(
            "Authentication expired; re-authentication required",
            "AUTH_EXPIRED",
            401,
            details or {},
        )


class QuotaExceededError(ColabMCPError):
    """Resource quota exceeded."""
    def __init__(self, details: Optional[dict] = None):
        super().__init__(
            "Resource quota exceeded",
            "QUOTA_EXCEEDED",
            429,
            details or {},
        )


class CLIError(ColabMCPError):
    """Generic CLI error."""
    def __init__(self, message: str, exit_code: int, details: Optional[dict] = None):
        super().__init__(
            message,
            "CLI_ERROR",
            500,
            {"exit_code": exit_code, **(details or {})},
        )


# Error code mapping from CLI stderr patterns
ERROR_PATTERNS = [
    (r"Session '(.+?)' not found", SessionNotFoundError),
    (r"already exists", SessionAlreadyExistsError),
    (r"not ready", SessionNotReadyError),
    (r"Timeout|timeout", ExecutionTimeoutError),
    (r"quota exceeded|quota_exceeded", QuotaExceededError),
    (r"auth|credential|token|unauthorized", AuthExpiredError),
]

# Exit codes that indicate session not found (both 0 and 1 observed in practice)
SESSION_NOT_FOUND_EXIT_CODES = {0, 1}