"""End-to-end stdio protocol smoke test for Phases C-E."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def _exercise_stdio_protocol() -> tuple[str, list[object], str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env["PYTHONUNBUFFERED"] = "1"

    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "colab_mcp_adapter"],
        env=env,
        cwd=PROJECT_ROOT,
    )

    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr_capture:
        async with stdio_client(server, errlog=stderr_capture) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                initialize = await session.initialize()
                tool_result = await session.list_tools()

        stderr_capture.seek(0)
        stderr_output = stderr_capture.read()

    return initialize.serverInfo.name, tool_result.tools, stderr_output


def test_initialize_and_tools_list_use_clean_jsonrpc_stdio() -> None:
    server_name, tools, stderr_output = asyncio.run(_exercise_stdio_protocol())

    assert server_name == "colab-mcp-adapter"
    # Phase C + D + E: 8 tools registered (4 session lifecycle + 2 execution + 2 URL/log)
    tool_names = {t.name for t in tools}
    expected_tools = {
        "colab_session_create",
        "colab_session_list",
        "colab_session_get",
        "colab_session_stop",
        "colab_code_execute",
        "colab_file_execute",
        "colab_session_get_url",
        "colab_session_log",
    }
    assert tool_names == expected_tools
    # MCP stdout is parsed by the SDK; stderr is captured through a separate
    # operating-system file handle.
    assert isinstance(stderr_output, str)


def test_tool_schemas_have_required_fields() -> None:
    """Verify each tool has proper input schema."""
    server_name, tools, _ = asyncio.run(_exercise_stdio_protocol())

    tool_map = {t.name: t for t in tools}

    # colab_session_create has optional fields
    create_schema = tool_map["colab_session_create"].inputSchema
    assert create_schema["type"] == "object"
    props = create_schema["properties"]
    assert "name" in props
    assert "gpu" in props
    assert "tpu" in props
    assert "high_mem" in props
    # All optional
    assert create_schema.get("required", []) == []

    # colab_session_list has no input
    list_schema = tool_map["colab_session_list"].inputSchema
    assert list_schema["type"] == "object"
    assert list_schema["properties"] == {}

    # colab_session_get requires name
    get_schema = tool_map["colab_session_get"].inputSchema
    assert get_schema["type"] == "object"
    assert "name" in get_schema["properties"]
    assert get_schema["required"] == ["name"]

    # colab_session_stop requires name
    stop_schema = tool_map["colab_session_stop"].inputSchema
    assert stop_schema["type"] == "object"
    assert "name" in stop_schema["properties"]
    assert stop_schema["required"] == ["name"]

    # colab_code_execute requires session and code
    code_schema = tool_map["colab_code_execute"].inputSchema
    assert code_schema["type"] == "object"
    code_props = code_schema["properties"]
    assert "session" in code_props
    assert "code" in code_props
    assert "timeout" in code_props
    assert "env" in code_props
    assert code_schema["required"] == ["session", "code"]
    # timeout has default
    assert code_props["timeout"]["type"] == "integer"
    assert code_props["timeout"]["default"] == 30

    # colab_file_execute requires session and file_path
    file_schema = tool_map["colab_file_execute"].inputSchema
    assert file_schema["type"] == "object"
    file_props = file_schema["properties"]
    assert "session" in file_props
    assert "file_path" in file_props
    assert "timeout" in file_props
    assert "env" in file_props
    assert file_schema["required"] == ["session", "file_path"]
    assert file_props["timeout"]["default"] == 30

    # colab_session_get_url requires session
    url_schema = tool_map["colab_session_get_url"].inputSchema
    assert url_schema["type"] == "object"
    url_props = url_schema["properties"]
    assert "session" in url_props
    assert "host" in url_props
    assert url_schema["required"] == ["session"]

    # colab_session_log has optional session, lines, type
    log_schema = tool_map["colab_session_log"].inputSchema
    assert log_schema["type"] == "object"
    log_props = log_schema["properties"]
    assert "session" in log_props
    assert "lines" in log_props
    assert "type" in log_props
    assert log_schema.get("required", []) == []  # All optional
    # lines uses anyOf [integer, null]
    assert "anyOf" in log_props["lines"]
    assert any(opt.get("type") == "integer" for opt in log_props["lines"]["anyOf"])
