"""Tests for configuration management."""

import pytest
from pydantic import ValidationError

from junior.config import Settings


class TestSettings:
    """Tests for Settings configuration."""

    def test_settings_with_all_required_fields(self):
        """Test settings with all required fields."""
        settings = Settings(
            github_token="test-token",
            secret_key="test-secret",
        )
        
        assert settings.github_token == "test-token"
        assert settings.secret_key == "test-secret"
        assert settings.default_model == "gpt-4o"  # Default
        assert settings.temperature == 0.1  # Default
        assert settings.log_level == "INFO"  # Default

    def test_settings_with_optional_fields(self):
        """Test settings with optional fields."""
        settings = Settings(
            openai_api_key="openai-key",
            anthropic_api_key="anthropic-key",
            github_token="github-token",
            secret_key="secret",
            default_model="gpt-3.5-turbo",
            temperature=0.5,
            max_tokens=2000,
            log_level="DEBUG",
            debug=True,
        )
        
        assert settings.openai_api_key == "openai-key"
        assert settings.anthropic_api_key == "anthropic-key"
        assert settings.default_model == "gpt-3.5-turbo"
        assert settings.temperature == 0.5
        assert settings.max_tokens == 2000
        assert settings.log_level == "DEBUG"
        assert settings.debug is True

    def test_settings_missing_required_fields(self):
        """Test settings validation with missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        errors = exc_info.value.errors()
        required_fields = {error["loc"][0] for error in errors if error["type"] == "missing"}
        assert "github_token" in required_fields
        assert "secret_key" in required_fields

    def test_settings_code_review_options(self):
        """Test code review specific settings."""
        settings = Settings(
            github_token="test-token",
            secret_key="test-secret",
            enable_security_checks=False,
            enable_performance_checks=True,
            enable_style_checks=False,
            enable_complexity_checks=True,
            max_file_size=50000,
            max_files_per_pr=25,
            review_timeout=600,
        )
        
        assert settings.enable_security_checks is False
        assert settings.enable_performance_checks is True
        assert settings.enable_style_checks is False
        assert settings.enable_complexity_checks is True
        assert settings.max_file_size == 50000
        assert settings.max_files_per_pr == 25
        assert settings.review_timeout == 600

    def test_settings_database_configuration(self):
        """Test database configuration settings."""
        settings = Settings(
            github_token="test-token",
            secret_key="test-secret",
            database_url="postgresql://user:pass@localhost/junior",
        )
        
        assert settings.database_url == "postgresql://user:pass@localhost/junior"

    def test_settings_api_configuration(self):
        """Test API configuration settings."""
        settings = Settings(
            github_token="test-token",
            secret_key="test-secret",
            api_host="127.0.0.1",
            api_port=9000,
        )
        
        assert settings.api_host == "127.0.0.1"
        assert settings.api_port == 9000

    def test_settings_defaults(self):
        """Test default values are set correctly."""
        settings = Settings(
            github_token="test-token",
            secret_key="test-secret",
        )
        
        # AI settings defaults
        assert settings.default_model == "gpt-4o"
        assert settings.temperature == 0.1
        assert settings.max_tokens == 4000
        
        # Application defaults
        assert settings.log_level == "INFO"
        assert settings.debug is False
        assert settings.database_url == "sqlite:///junior.db"
        
        # API defaults
        assert settings.api_host == "0.0.0.0"
        assert settings.api_port == 8000
        
        # Code review defaults
        assert settings.max_file_size == 100000
        assert settings.max_files_per_pr == 50
        assert settings.review_timeout == 300
        assert settings.enable_security_checks is True
        assert settings.enable_performance_checks is True
        assert settings.enable_style_checks is True
        assert settings.enable_complexity_checks is True

    def test_settings_log_level_validation(self):
        """Test log level validation."""
        # Valid log levels
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            settings = Settings(
                github_token="test-token",
                secret_key="test-secret",
                log_level=level,
            )
            assert settings.log_level == level
        
        # Invalid log level should raise validation error
        with pytest.raises(ValidationError):
            Settings(
                github_token="test-token",
                secret_key="test-secret",
                log_level="INVALID",
            )

    def test_settings_from_env_file(self, monkeypatch, tmp_path):
        """Test loading settings from environment file."""
        # Create a temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("""
GITHUB_TOKEN=env-github-token
SECRET_KEY=env-secret-key
OPENAI_API_KEY=env-openai-key
DEFAULT_MODEL=gpt-3.5-turbo
TEMPERATURE=0.7
DEBUG=true
""")
        
        # Change to the temp directory
        monkeypatch.chdir(tmp_path)
        
        # Create settings (should load from .env file)
        settings = Settings()
        
        assert settings.github_token == "env-github-token"
        assert settings.secret_key == "env-secret-key"
        assert settings.openai_api_key == "env-openai-key"
        assert settings.default_model == "gpt-3.5-turbo"
        assert settings.temperature == 0.7
        assert settings.debug is True