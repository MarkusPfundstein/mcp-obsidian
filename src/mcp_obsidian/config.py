"""Centralized configuration management using Pydantic Settings."""
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for MCP Obsidian server.
    
    Settings are loaded from environment variables or .env file.
    All settings can be overridden via environment variables.
    """
    
    # Required settings
    obsidian_api_key: str = Field(
        ...,
        description="API key for Obsidian Local REST API",
        alias="OBSIDIAN_API_KEY"
    )
    
    # Optional settings with defaults
    obsidian_host: str = Field(
        default="127.0.0.1",
        description="Obsidian REST API host",
        alias="OBSIDIAN_HOST"
    )
    
    obsidian_port: int = Field(
        default=27124,
        description="Obsidian REST API port",
        alias="OBSIDIAN_PORT"
    )
    
    obsidian_protocol: str = Field(
        default="https",
        description="Protocol for Obsidian REST API (http or https)",
        alias="OBSIDIAN_PROTOCOL"
    )
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Use alias for environment variable names
        populate_by_name=True
    )
    
    @field_validator("obsidian_protocol")
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        """Ensure protocol is either http or https."""
        v_lower = v.lower()
        if v_lower not in ("http", "https"):
            # Default to https for security
            return "https"
        return v_lower
    
    @field_validator("obsidian_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Ensure port is in valid range."""
        if not 1 <= v <= 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {v}")
        return v
    
    @property
    def base_url(self) -> str:
        """Construct the base URL for Obsidian API."""
        return f"{self.obsidian_protocol}://{self.obsidian_host}:{self.obsidian_port}"


def get_settings() -> Settings:
    """Get the settings instance.
    
    This function creates a new Settings instance each time it's called,
    allowing for dynamic configuration updates (useful for testing).
    
    For production use, consider caching the settings instance.
    """
    return Settings()


# For backward compatibility and convenience
def get_cached_settings() -> Settings:
    """Get a cached settings instance.
    
    This function returns the same Settings instance on subsequent calls,
    which is more efficient but doesn't pick up environment changes.
    """
    if not hasattr(get_cached_settings, "_instance"):
        get_cached_settings._instance = Settings()
    return get_cached_settings._instance