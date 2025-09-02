"""Tests for the CLI using Typer's CliRunner."""
import pytest
from typer.testing import CliRunner
import typer
import asyncio
import os

from mcp_obsidian.cli import main
from mcp_obsidian import __version__


# Create a Typer app for testing
app = typer.Typer()
app.command()(main)


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Override the global mock_env_vars to not set any defaults for CLI tests."""
    # Don't set any environment variables for CLI tests
    # This overrides the autouse fixture from conftest.py
    pass


@pytest.fixture
def runner():
    """Provide a CliRunner instance for tests."""
    return CliRunner()


@pytest.fixture
def clean_env(monkeypatch):
    """Clean environment variables for testing."""
    # Remove any Obsidian-related env vars
    env_vars = [
        "OBSIDIAN_API_KEY",
        "OBSIDIAN_HOST", 
        "OBSIDIAN_PORT",
        "OBSIDIAN_PROTOCOL",
        "OBSIDIAN_CONNECT_TIMEOUT",
        "OBSIDIAN_READ_TIMEOUT",
        "OBSIDIAN_VERIFY_SSL"
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)


def test_help(runner):
    """Test that --help works."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "MCP server for Obsidian integration" in result.stdout
    assert "--api-key" in result.stdout
    assert "--host" in result.stdout
    assert "--port" in result.stdout
    assert "--version" in result.stdout
    assert "--config-check" in result.stdout


def test_version(runner):
    """Test that --version works."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"mcp-obsidian version: {__version__}" in result.stdout


def test_config_check_with_api_key(runner):
    """Test --config-check with valid configuration."""
    result = runner.invoke(app, ["--config-check", "--api-key", "test123"])
    assert result.exit_code == 0
    assert "Current configuration:" in result.stdout
    assert "API Key: ***" in result.stdout
    assert "Host: 127.0.0.1" in result.stdout
    assert "Port: 27124" in result.stdout
    assert "✓ Configuration is valid" in result.stdout


def test_config_check_without_api_key(runner, clean_env):
    """Test --config-check without API key shows error."""
    result = runner.invoke(app, ["--config-check"])
    assert result.exit_code == 1
    assert "Configuration error" in result.stdout or "Field required" in result.stdout


def test_custom_host_and_port(runner):
    """Test configuration with custom host and port."""
    result = runner.invoke(app, [
        "--config-check",
        "--api-key", "test123",
        "--host", "192.168.1.100",
        "--port", "8080"
    ])
    assert result.exit_code == 0
    assert "Host: 192.168.1.100" in result.stdout
    assert "Port: 8080" in result.stdout


def test_custom_protocol(runner):
    """Test configuration with custom protocol."""
    result = runner.invoke(app, [
        "--config-check",
        "--api-key", "test123",
        "--protocol", "http"
    ])
    assert result.exit_code == 0
    assert "Protocol: http" in result.stdout
    assert "Base URL: http://127.0.0.1:27124" in result.stdout


def test_timeout_settings(runner):
    """Test timeout configuration."""
    result = runner.invoke(app, [
        "--config-check",
        "--api-key", "test123",
        "--connect-timeout", "10",
        "--read-timeout", "30"
    ])
    assert result.exit_code == 0
    assert "Connect Timeout: 10s" in result.stdout
    assert "Read Timeout: 30s" in result.stdout


def test_ssl_verification_enabled(runner):
    """Test SSL verification enabled."""
    result = runner.invoke(app, [
        "--config-check",
        "--api-key", "test123",
        "--verify-ssl"
    ])
    assert result.exit_code == 0
    assert "Verify SSL: True" in result.stdout


def test_ssl_verification_disabled(runner):
    """Test SSL verification disabled."""
    result = runner.invoke(app, [
        "--config-check",
        "--api-key", "test123",
        "--no-verify-ssl"
    ])
    assert result.exit_code == 0
    assert "Verify SSL: False" in result.stdout


def test_invalid_port(runner):
    """Test that invalid port values are rejected."""
    result = runner.invoke(app, [
        "--config-check",
        "--api-key", "test123",
        "--port", "not-a-number"
    ])
    assert result.exit_code != 0
    assert "Invalid value" in result.stdout or "Error" in result.stdout


def test_connect_timeout_too_high(runner):
    """Test that connect timeout over 60 is rejected."""
    result = runner.invoke(app, [
        "--config-check",
        "--api-key", "test123",
        "--connect-timeout", "100"
    ])
    assert result.exit_code != 0


def test_read_timeout_too_high(runner):
    """Test that read timeout over 300 is rejected."""
    result = runner.invoke(app, [
        "--config-check",
        "--api-key", "test123",
        "--read-timeout", "400"
    ])
    assert result.exit_code != 0


def test_server_starts_with_valid_config(runner, mocker):
    """Test that server starts with valid configuration."""
    # Mock the async server.main to avoid actual server startup
    mock_server_main = mocker.patch('mcp_obsidian.server.main')
    future = asyncio.Future()
    future.set_result(None)
    mock_server_main.return_value = future
    
    result = runner.invoke(app, [
        "--api-key", "test123",
        "--host", "localhost",
        "--port", "8080"
    ])
    
    # Server should have been called
    mock_server_main.assert_called_once()


def test_verbose_logging(runner):
    """Test verbose logging option."""
    result = runner.invoke(app, [
        "--config-check",
        "--api-key", "test123",
        "--verbose"
    ])
    assert result.exit_code == 0
    # Verbose flag should work without errors


def test_verbose_short_option(runner):
    """Test verbose logging with short option -v."""
    result = runner.invoke(app, [
        "--config-check",
        "--api-key", "test123",
        "-v"
    ])
    assert result.exit_code == 0


def test_environment_variable_override(runner, monkeypatch):
    """Test that CLI arguments override environment variables."""
    monkeypatch.setenv("OBSIDIAN_API_KEY", "env_key")
    monkeypatch.setenv("OBSIDIAN_HOST", "env_host")
    
    result = runner.invoke(app, [
        "--config-check",
        "--api-key", "cli_key",
        "--host", "cli_host"
    ])
    assert result.exit_code == 0
    # CLI values should be used, not env values
    assert "Host: cli_host" in result.stdout
    # API key should show last 4 chars of CLI key
    assert "***_key" in result.stdout


def test_environment_variables_used_when_no_cli_args(runner, monkeypatch):
    """Test that environment variables are used when no CLI args provided."""
    monkeypatch.setenv("OBSIDIAN_API_KEY", "env_api_key")
    monkeypatch.setenv("OBSIDIAN_HOST", "env.example.com")
    monkeypatch.setenv("OBSIDIAN_PORT", "9999")
    
    result = runner.invoke(app, ["--config-check"])
    assert result.exit_code == 0
    assert "Host: env.example.com" in result.stdout
    assert "Port: 9999" in result.stdout
    assert "***_key" in result.stdout  # Last 4 chars of env_api_key


def test_missing_required_api_key(runner, clean_env):
    """Test that missing API key causes error when trying to run server."""
    result = runner.invoke(app, [])
    assert result.exit_code == 1
    assert "Configuration error" in result.stdout or "Field required" in result.stdout


def test_protocol_validation(runner):
    """Test that only http and https protocols are accepted."""
    result = runner.invoke(app, [
        "--config-check",
        "--api-key", "test123",
        "--protocol", "ftp"  # Invalid protocol
    ])
    assert result.exit_code == 1
    assert "Configuration error" in result.stdout or "Protocol must be" in result.stdout


def test_all_cli_options_together(runner):
    """Test using all CLI options together."""
    result = runner.invoke(app, [
        "--config-check",
        "--api-key", "full_test_key",
        "--host", "test.local",
        "--port", "3000",
        "--protocol", "http",
        "--connect-timeout", "5",
        "--read-timeout", "10",
        "--verify-ssl",
        "--verbose"
    ])
    assert result.exit_code == 0
    assert "Host: test.local" in result.stdout
    assert "Port: 3000" in result.stdout
    assert "Protocol: http" in result.stdout
    assert "Base URL: http://test.local:3000" in result.stdout
    assert "Connect Timeout: 5s" in result.stdout
    assert "Read Timeout: 10s" in result.stdout
    assert "Verify SSL: True" in result.stdout
    assert "✓ Configuration is valid" in result.stdout


def test_config_check_with_partial_options(runner):
    """Test config check with some options from CLI and rest as defaults."""
    result = runner.invoke(app, [
        "--config-check",
        "--api-key", "test123",
        "--port", "5000"
    ])
    assert result.exit_code == 0
    assert "Host: 127.0.0.1" in result.stdout  # Default
    assert "Port: 5000" in result.stdout  # From CLI
    assert "Protocol: https" in result.stdout  # Default
    assert "Connect Timeout: 3s" in result.stdout  # Default
    assert "Read Timeout: 6s" in result.stdout  # Default