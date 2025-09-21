"""Configuration management for Junior."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # AI Provider Configuration
    openai_api_key: str | None = Field(None, description="OpenAI API key")
    anthropic_api_key: str | None = Field(None, description="Anthropic API key")

    # Default AI model settings
    default_model: str = Field("gpt-4o", description="Default AI model to use")
    temperature: float = Field(0.1, description="AI model temperature")
    max_tokens: int = Field(4000, description="Maximum tokens for AI responses")

    # GitHub Configuration
    github_token: str | None = Field(None, description="GitHub personal access token")
    github_webhook_secret: str | None = Field(None, description="GitHub webhook secret")

    # Application Configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO", description="Logging level"
    )
    debug: bool = Field(False, description="Enable debug mode")

    # Database Configuration
    database_url: str = Field(
        "sqlite:///junior.db", description="Database connection URL"
    )

    # API Configuration
    api_host: str = Field("0.0.0.0", description="API host")
    api_port: int = Field(8000, description="API port")

    # Security
    secret_key: str | None = Field(None, description="Secret key for security")

    # Code Review Settings
    max_file_size: int = Field(
        100000, description="Maximum file size to review (bytes)"
    )
    max_files_per_pr: int = Field(50, description="Maximum files per PR to review")
    review_timeout: int = Field(300, description="Review timeout in seconds")

    # AI Review Settings
    enable_security_checks: bool = Field(
        True, description="Enable security vulnerability checks"
    )
    enable_performance_checks: bool = Field(
        True, description="Enable performance checks"
    )
    enable_style_checks: bool = Field(True, description="Enable code style checks")
    enable_complexity_checks: bool = Field(True, description="Enable complexity checks")
    
    # AI Token Management
    max_tokens_per_request: int = Field(
        25000, description="Maximum tokens per AI request to prevent rate limits"
    )
    max_diff_chars: int = Field(
        50000, description="Maximum characters for diff content sent to AI"
    )
    max_structure_chars: int = Field(
        10000, description="Maximum characters for project structure context"
    )
    
    # ReAct Agent Settings
    enable_react_agent: bool = Field(
        True, description="Enable ReAct agent for dynamic repository analysis during reviews"
    )
    react_agent_max_iterations: int = Field(
        3, description="Maximum iterations for ReAct agent to prevent runaway execution"
    )
    react_agent_timeout: int = Field(
        45, description="Timeout in seconds for ReAct agent execution"
    )


# Global settings instance
settings = Settings()
