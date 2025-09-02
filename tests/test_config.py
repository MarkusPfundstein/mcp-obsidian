"""Tests for the centralized configuration system."""
import pytest
import os
from unittest.mock import patch
from pydantic import ValidationError

# Set test environment before importing
os.environ["OBSIDIAN_API_KEY"] = "test-api-key"

from mcp_obsidian.config import Settings, get_settings
from mcp_obsidian.obsidian import Obsidian


class TestSettings:
    """Test the Settings configuration class."""
    
    def test_settings_from_env(self):
        """Test that settings are loaded from environment variables."""
        with patch.dict(os.environ, {
            "OBSIDIAN_API_KEY": "test-key-123",
            "OBSIDIAN_HOST": "192.168.1.1",
            "OBSIDIAN_PORT": "8080",
            "OBSIDIAN_PROTOCOL": "http"
        }):
            settings = get_settings()
            assert settings.obsidian_api_key == "test-key-123"
            assert settings.obsidian_host == "192.168.1.1"
            assert settings.obsidian_port == 8080
            assert settings.obsidian_protocol == "http"
    
    def test_settings_defaults(self):
        """Test that default values are used when env vars are not set."""
        with patch.dict(os.environ, {"OBSIDIAN_API_KEY": "test-key"}, clear=True):
            settings = get_settings()
            assert settings.obsidian_api_key == "test-key"
            assert settings.obsidian_host == "127.0.0.1"
            assert settings.obsidian_port == 27124
            assert settings.obsidian_protocol == "https"
            assert settings.obsidian_connect_timeout == 3
            assert settings.obsidian_read_timeout == 6
            assert settings.obsidian_verify_ssl is False
    
    def test_settings_missing_api_key(self):
        """Test that missing API key raises validation error."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                get_settings()
            assert "obsidian_api_key" in str(exc_info.value)
    
    def test_protocol_validation(self):
        """Test that protocol is validated and normalized."""
        with patch.dict(os.environ, {
            "OBSIDIAN_API_KEY": "test-key",
            "OBSIDIAN_PROTOCOL": "HTTP"
        }):
            settings = get_settings()
            assert settings.obsidian_protocol == "http"
        
        # Test that invalid protocol raises an error
        with patch.dict(os.environ, {
            "OBSIDIAN_API_KEY": "test-key",
            "OBSIDIAN_PROTOCOL": "invalid"
        }):
            with pytest.raises(ValidationError) as exc_info:
                get_settings()
            assert "Protocol must be 'http' or 'https'" in str(exc_info.value)
    
    def test_port_validation(self):
        """Test that port is validated."""
        with patch.dict(os.environ, {
            "OBSIDIAN_API_KEY": "test-key",
            "OBSIDIAN_PORT": "0"
        }):
            with pytest.raises(ValidationError) as exc_info:
                get_settings()
            assert "Port must be between 1 and 65535" in str(exc_info.value)
        
        with patch.dict(os.environ, {
            "OBSIDIAN_API_KEY": "test-key",
            "OBSIDIAN_PORT": "70000"
        }):
            with pytest.raises(ValidationError) as exc_info:
                get_settings()
            assert "Port must be between 1 and 65535" in str(exc_info.value)
    
    def test_timeout_validation(self):
        """Test that timeout values are validated."""
        # Test connect timeout out of range
        with patch.dict(os.environ, {
            "OBSIDIAN_API_KEY": "test-key",
            "OBSIDIAN_CONNECT_TIMEOUT": "0"  # Below minimum
        }):
            with pytest.raises(ValidationError) as exc_info:
                get_settings()
            assert "greater than or equal to 1" in str(exc_info.value).lower()
        
        # Test read timeout out of range
        with patch.dict(os.environ, {
            "OBSIDIAN_API_KEY": "test-key",
            "OBSIDIAN_READ_TIMEOUT": "301"  # Above maximum
        }):
            with pytest.raises(ValidationError) as exc_info:
                get_settings()
            assert "less than or equal to 300" in str(exc_info.value).lower()
    
    def test_base_url_property(self):
        """Test that base_url is correctly constructed."""
        with patch.dict(os.environ, {
            "OBSIDIAN_API_KEY": "test-key",
            "OBSIDIAN_HOST": "example.com",
            "OBSIDIAN_PORT": "443",
            "OBSIDIAN_PROTOCOL": "https"
        }):
            settings = get_settings()
            assert settings.base_url == "https://example.com:443"


class TestObsidianWithConfig:
    """Test Obsidian client with config object."""
    
    def test_obsidian_with_config_object(self):
        """Test that Obsidian client can be initialized with config object."""
        with patch.dict(os.environ, {
            "OBSIDIAN_API_KEY": "config-key",
            "OBSIDIAN_HOST": "config-host",
            "OBSIDIAN_PORT": "9999",
            "OBSIDIAN_PROTOCOL": "http"
        }):
            config = get_settings()
            client = Obsidian(config=config)
            
            assert client.api_key == "config-key"
            assert client.host == "config-host"
            assert client.port == 9999
            assert client.protocol == "http"
            assert client.get_base_url() == "http://config-host:9999"
            # Verify default timeout and SSL values
            assert client.verify_ssl is False
            assert client.timeout == (3, 6)
    
    def test_obsidian_backward_compatibility(self):
        """Test that Obsidian client still works with individual parameters."""
        client = Obsidian(
            api_key="direct-key",
            host="direct-host",
            port=7777,
            protocol="https"
        )
        
        assert client.api_key == "direct-key"
        assert client.host == "direct-host"
        assert client.port == 7777
        assert client.protocol == "https"
    
    def test_obsidian_with_custom_timeouts(self):
        """Test that Obsidian client uses custom timeout values from config."""
        with patch.dict(os.environ, {
            "OBSIDIAN_API_KEY": "test-key",
            "OBSIDIAN_CONNECT_TIMEOUT": "10",
            "OBSIDIAN_READ_TIMEOUT": "30",
            "OBSIDIAN_VERIFY_SSL": "true"
        }):
            config = get_settings()
            client = Obsidian(config=config)
            
            assert client.timeout == (10, 30)
            assert client.verify_ssl is True
    
    def test_obsidian_config_precedence(self):
        """Test that config object takes precedence over individual parameters."""
        with patch.dict(os.environ, {
            "OBSIDIAN_API_KEY": "config-key",
            "OBSIDIAN_HOST": "config-host"
        }):
            config = get_settings()
            client = Obsidian(
                api_key="ignored-key",
                host="ignored-host",
                config=config
            )
            
            assert client.api_key == "config-key"
            assert client.host == "config-host"