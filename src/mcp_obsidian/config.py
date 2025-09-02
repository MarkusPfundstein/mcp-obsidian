"""Centralized configuration management using Pydantic Settings."""
from typing import Optional, Dict, Any, Tuple, Type
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource


class Settings(BaseSettings):
    """Configuration settings for MCP Obsidian server.
    
    Settings are loaded from environment variables or .env file.
    All settings can be overridden via environment variables.
    """
    
    # Required settings
    obsidian_api_key: str = Field(
        ...,
        description="API key for Obsidian Local REST API"
    )
    
    # Optional settings with defaults
    obsidian_host: str = Field(
        default="127.0.0.1",
        description="Obsidian REST API host"
    )
    
    obsidian_port: int = Field(
        default=27124,
        description="Obsidian REST API port"
    )
    
    obsidian_protocol: str = Field(
        default="https",
        description="Protocol for Obsidian REST API (http or https)"
    )
    
    # Connection settings - CLI-friendly individual fields
    obsidian_connect_timeout: int = Field(
        default=3,
        ge=1,
        le=60,
        description="Connection timeout in seconds"
    )
    
    obsidian_read_timeout: int = Field(
        default=6,
        ge=1,
        le=300,
        description="Read timeout in seconds"
    )
    
    obsidian_verify_ssl: bool = Field(
        default=False,
        description="Verify SSL certificates (set to true for production)"
    )
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Environment variables will be OBSIDIAN_API_KEY, OBSIDIAN_HOST, etc.
        env_prefix=""  # No prefix since field names already start with "obsidian_"
    )
    
    @field_validator("obsidian_protocol")
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        """Ensure protocol is either http or https."""
        v_lower = v.lower()
        if v_lower not in ("http", "https"):
            raise ValueError(f"Protocol must be 'http' or 'https', got '{v}'")
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
    
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """Customize the order of settings sources.
        
        Priority order (highest to lowest):
        1. init_settings (values passed to __init__)
        2. env_settings (environment variables)
        3. dotenv_settings (.env file)
        4. file_secret_settings (not used)
        
        This ensures CLI args passed to __init__ take precedence over everything.
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
        )


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