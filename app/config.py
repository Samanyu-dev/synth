"""
Synth MVP configuration — loads all settings from environment variables.

Uses pydantic-settings for type-safe, validated config loading.
Fails at startup with a clear error if required variables are missing.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # Required — Gemini API
    gemini_api_key: str = Field(
        ...,
        description="Gemini API key for synthesis"
    )

    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for Claude synthesis"
    )

    # Data paths — default to local data/ directory
    triathlon_daily_csv: str = Field(
        default="data/Copy of Triathlon Training Sync-daily_summary.csv",
        description="Path to the triathlon daily summary CSV"
    )
    triathlon_activities_csv: str = Field(
        default="data/Copy of Triathlon Training Sync-activities_raw.csv",
        description="Path to the triathlon activities CSV"
    )
    rowing_data_dir: str = Field(
        default="data",
        description="Directory containing rowing erg CSV files"
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

    # Strava OAuth
    strava_client_id: str = Field(
        default="",
        description="Strava API Client ID"
    )
    strava_client_secret: str = Field(
        default="",
        description="Strava API Client Secret"
    )

    # Google Sheets
    google_sheet_id: str = Field(
        default="",
        description="Google Sheet ID for two-way sync"
    )
    google_service_account_json: str = Field(
        default="",
        description="Google Service Account credentials JSON string"
    )
    google_service_account_file: str = Field(
        default="",
        description="Path to Google Service Account credentials JSON file"
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
