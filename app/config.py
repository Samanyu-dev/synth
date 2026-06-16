"""
Synth MVP configuration — loads all settings from environment variables.

Uses pydantic-settings for type-safe, validated config loading.
Fails at startup with a clear error if required variables are missing.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # Required — Claude API
    anthropic_api_key: str = Field(
        ...,
        description="Anthropic API key for Claude synthesis"
    )

    # Data paths — default to local data/ directory
    triathlon_data_path: str = Field(
        default="data/Copy of Triathlon Training Sync.xlsx",
        description="Path to the triathlon training Excel file"
    )
    rowing_data_path: str = Field(
        default="data/rowing_women_2025-2026 ERGS-2.xlsx",
        description="Path to the rowing erg results Excel file"
    )

    # Database
    db_path: str = Field(
        default="synth.db",
        description="SQLite database file path"
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )

    # Rate limiting
    rate_limit: str = Field(
        default="10/minute",
        description="API rate limit per client IP"
    )

    # Claude model
    claude_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Anthropic model identifier"
    )
    claude_max_tokens: int = Field(
        default=1024,
        description="Max tokens for Claude response"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
