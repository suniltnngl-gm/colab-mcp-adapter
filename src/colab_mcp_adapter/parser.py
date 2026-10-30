"""CLI output parsing for Colab CLI.

Parses session lines from `colab sessions` and `colab status` output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .contracts import SessionInfo


# Regex for parsing session lines from `colab sessions` and `colab status`
# Format: [name] m-s-<id> | Hardware: <hw> | Shape: <shape> | Variant: <variant> [| Status: <status>]
# Hardware/Shape/Variant can contain hyphens (e.g., High-Mem)
SESSION_LINE_REGEX = re.compile(
    r'^\[(.+?)\]\s+'               # [name]
    r'(m-s-[a-z0-9-]+)\s+'         # session_id (m-s-<alphanumeric and hyphens>)
    r'\|\s+Hardware:\s+([\w-]+)\s+'  # Hardware: <hw> (allows hyphens)
    r'\|\s+Shape:\s+([\w-]+)\s+'     # Shape: <shape> (allows hyphens)
    r'\|\s+Variant:\s+([\w-]+)'      # Variant: <variant> (allows hyphens)
    r'(?:\s+\|\s+Status:\s+(\w+))?'  # Optional | Status: <status>
    r'$'
)

# Session ID validation regex (allows hyphens in the alphanumeric part)
SESSION_ID_REGEX = re.compile(r'^m-s-[a-z0-9-]+$')

# Error patterns
ERROR_SESSION_NOT_FOUND = re.compile(r"Session '(.+?)' not found")
ERROR_ALREADY_EXISTS = re.compile(r"already exists", re.IGNORECASE)
ERROR_NOT_READY = re.compile(r"not ready", re.IGNORECASE)
ERROR_TIMEOUT = re.compile(r"Timeout|timeout", re.IGNORECASE)
ERROR_QUOTA_EXCEEDED = re.compile(r"quota exceeded|quota_exceeded", re.IGNORECASE)
ERROR_AUTH = re.compile(r"auth|credential|token|unauthorized", re.IGNORECASE)


@dataclass
class ParsedSession:
    """Parsed session from CLI output."""
    name: str
    session_id: str
    hardware: str
    shape: str
    variant: str
    status: Optional[str] = None

    def to_session_info(self) -> SessionInfo:
        """Convert to SessionInfo model."""
        return SessionInfo(
            name=self.name,
            session_id=self.session_id,
            hardware=self.hardware,
            shape=self.shape,
            variant=self.variant,
            status=self.status,
        )


def validate_session_id(session_id: str) -> bool:
    """Validate session ID format (m-s-<alphanumeric>)."""
    return bool(SESSION_ID_REGEX.match(session_id))


def parse_session_line(line: str) -> Optional[ParsedSession]:
    """Parse a single session line from `colab sessions` or `colab status` output.
    
    Args:
        line: A single line of CLI output
        
    Returns:
        ParsedSession if line matches, None otherwise
    """
    line = line.strip()
    if not line:
        return None
    
    match = SESSION_LINE_REGEX.match(line)
    if not match:
        return None
    
    name, session_id, hardware, shape, variant, status = match.groups()
    
    if not validate_session_id(session_id):
        return None
    
    return ParsedSession(
        name=name,
        session_id=session_id,
        hardware=hardware,
        shape=shape,
        variant=variant,
        status=status,
    )


def parse_sessions_output(output: str) -> list[ParsedSession]:
    """Parse multiple session lines from `colab sessions` output.
    
    Args:
        output: Full stdout from `colab sessions`
        
    Returns:
        List of parsed sessions (empty if none found)
    """
    sessions = []
    for line in output.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        # Skip informational lines like "[colab] No active sessions found on server."
        if line.startswith('[colab]'):
            continue
        parsed = parse_session_line(line)
        if parsed:
            sessions.append(parsed)
    return sessions


def parse_status_output(output: str) -> Optional[ParsedSession]:
    """Parse `colab status --session <name>` output.
    
    Args:
        output: Full stdout from `colab status`
        
    Returns:
        ParsedSession if found, None otherwise
    """
    for line in output.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        # Skip error lines
        if line.startswith('[colab]'):
            continue
        parsed = parse_session_line(line)
        if parsed:
            return parsed
    return None


def parse_create_output(output: str) -> Optional[ParsedSession]:
    """Parse `colab new` output to extract session info.
    
    Output format:
    [colab] Creating session 'name'...
    [colab] Session READY.
    
    The session name is in the first line. We need to follow up with `colab status`
    to get full details, but we can extract the name here.
    """
    # The name is in the "Creating session 'name'..." line
    for line in output.strip().split('\n'):
        line = line.strip()
        if "Creating session" in line:
            # Extract name from: [colab] Creating session 'name'...
            match = re.search(r"Creating session '(.+?)'", line)
            if match:
                name = match.group(1)
                # We can't get full details from create output alone
                # Return minimal parsed session; caller should call status
                return ParsedSession(
                    name=name,
                    session_id="",  # Will be filled by status call
                    hardware="",
                    shape="",
                    variant="",
                    status="CREATING",
                )
    return None


def classify_cli_error(stderr: str, exit_code: int) -> tuple[str, int, dict]:
    """Classify CLI error from stderr and exit code.
    
    Returns:
        Tuple of (error_code, status_code, details)
    """
    stderr_lower = stderr.lower()
    
    if ERROR_SESSION_NOT_FOUND.search(stderr):
        match = ERROR_SESSION_NOT_FOUND.search(stderr)
        session_name = match.group(1) if match else "unknown"
        return ("SESSION_NOT_FOUND", 404, {"session_name": session_name})
    
    if ERROR_ALREADY_EXISTS.search(stderr):
        return ("SESSION_ALREADY_EXISTS", 409, {})
    
    if ERROR_NOT_READY.search(stderr):
        return ("SESSION_NOT_READY", 409, {})
    
    if ERROR_TIMEOUT.search(stderr):
        return ("EXECUTION_TIMEOUT", 408, {})
    
    if ERROR_QUOTA_EXCEEDED.search(stderr):
        return ("QUOTA_EXCEEDED", 429, {})
    
    if ERROR_AUTH.search(stderr):
        return ("AUTH_EXPIRED", 401, {})
    
    if "no history found" in stderr_lower:
        match = re.search(r"session '(.+?)'", stderr)
        session_name = match.group(1) if match else "unknown"
        return ("SESSION_NOT_FOUND", 404, {"session_name": session_name, "reason": "no_history"})
    
    # Generic CLI error
    return ("CLI_ERROR", 500, {"exit_code": exit_code, "stderr": stderr[:500]})


def parse_url_output(output: str) -> Optional[str]:
    """Parse `colab url --session <name>` output.
    
    Returns:
        URL string if found, None otherwise
    """
    for line in output.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        # Skip error lines
        if line.startswith('[colab]'):
            continue
        # URL should be a single line starting with https://
        if line.startswith('https://'):
            return line
    return None


def parse_log_output(output: str) -> list[str]:
    """Parse `colab log --session <name>` output.
    
    Returns:
        List of log lines (empty if none found)
    """
    logs = []
    for line in output.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        # Skip informational/error lines
        if line.startswith('[colab]'):
            continue
        # Log lines have format: [timestamp] EVENT: ... or [timestamp] EXEC: ...
        if line.startswith('['):
            logs.append(line)
    return logs


def parse_log_list_output(output: str) -> list[str]:
    """Parse `colab log` (no session) output - list of sessions with logs.
    
    Returns:
        List of session names/identifiers
    """
    sessions = []
    for line in output.strip().split('\n'):
        if not line:
            continue
        if line.startswith('[colab]'):
            continue
        # Sessions are listed with indentation: "  session-name"
        # Check BEFORE stripping
        if line.startswith('  '):
            sessions.append(line.strip())
    return sessions