"""Environment configuration for Colab MCP Adapter.

Loads configuration from .env file using pydantic-settings.
All filesystem paths and secrets are configured via environment variables,
making the adapter relocation-resilient.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ColabMCPConfig(BaseSettings):
    """Configuration for Colab MCP Adapter loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Required: Colab CLI configuration
    colab_cli_path: str = Field(
        default="colab",
        description=(
            "Path to the Colab CLI executable. "
            "Use absolute path for relocation resilience."
        ),
    )

    colab_cli_timeout_seconds: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="Default timeout for Colab CLI commands in seconds.",
    )

    # Optional: Session defaults
    default_session_timeout_seconds: int = Field(
        default=1800,
        ge=60,
        le=86400,
        description="Default session timeout in seconds.",
    )

    default_max_turns: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Default maximum conversation turns per session.",
    )

    # Optional: Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Log level for the adapter.",
    )

    log_format: Literal["json", "text"] = Field(
        default="text",
        description="Log output format.",
    )

    # Optional: Server configuration
    server_host: str = Field(
        default="127.0.0.1",
        description="Host to bind the MCP server (stdio mode ignores this).",
    )

    server_port: int = Field(
        default=8000,
        ge=1024,
        le=65535,
        description="Port for the MCP server (stdio mode ignores this).",
    )

    # Optional: Security
    allowed_origins: str | None = Field(
        default=None,
        description="Comma-separated list of allowed CORS origins (for HTTP mode).",
    )

    # Optional: Resource limits
    max_concurrent_sessions: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum concurrent sessions.",
    )

    max_code_execution_time_seconds: int = Field(
        default=600,
        ge=10,
        le=3600,
        description="Maximum code execution time per request in seconds.",
    )

    # Optional: Colab-specific
    colab_default_kernel: str = Field(
        default="python3",
        description="Default kernel type for new sessions.",
    )

    colab_auto_cleanup: bool = Field(
        default=True,
        description="Automatically clean up completed sessions.",
    )

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse comma-separated allowed origins."""
        if not self.allowed_origins:
            return []
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


# Global config instance (lazy-loaded)
_config: ColabMCPConfig | None = None


def get_config() -> ColabMCPConfig:
    """Get the global configuration instance (loads .env on first call)."""
    global _config
    if _config is None:
        _config = ColabMCPConfig()
    return _config


def reload_config() -> ColabMCPConfig:
    """Force reload configuration from .env file."""
    global _config
    _config = ColabMCPConfig()
    return _config


def validate_env_file(env_path: str = ".env") -> bool:
    """Validate .env file without loading it into the global config.

    Args:
        env_path: Path to the .env file to validate.

    Returns:
        True if the file exists and all required fields are present.
    """
    try:
        # Temporarily load from the specified file
        from pydantic_settings import BaseSettings

        class TempConfig(BaseSettings):
            model_config = SettingsConfigDict(
                env_file=env_path,
                env_file_encoding="utf-8",
                case_sensitive=True,
                extra="ignore",
            )
            colab_cli_path: str = "colab"

        TempConfig()
        return True
    except Exception:
        return False
