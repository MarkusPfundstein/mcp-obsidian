from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .security import normalize_vault_path, path_is_within, require_loopback_https


class ConfigurationError(ValueError):
    """Raised for invalid or incomplete server configuration."""


@dataclass(frozen=True)
class Limits:
    top_k: int = 5
    max_total_characters: int = 12_000
    max_sections: int = 4
    max_documents: int = 2
    max_sections_per_document: int = 2
    related_document_hops: int = 1
    max_file_bytes: int = 1_048_576
    max_total_index_bytes: int = 33_554_432
    max_source_files: int = 2_000
    max_source_directories: int = 500
    max_directory_entries: int = 5_000
    max_directory_response_bytes: int = 1_048_576
    max_index_documents: int = 1_000
    max_index_sections: int = 10_000
    max_index_sections_per_document: int = 200
    max_tokens_per_section: int = 10_000
    max_total_index_tokens: int = 500_000
    max_frontmatter_bytes: int = 65_536
    max_frontmatter_nodes: int = 1_000
    max_frontmatter_depth: int = 20
    max_index_build_seconds: float = 120.0

    def __post_init__(self) -> None:
        positive = {
            "top_k": self.top_k,
            "max_total_characters": self.max_total_characters,
            "max_sections": self.max_sections,
            "max_documents": self.max_documents,
            "max_sections_per_document": self.max_sections_per_document,
            "max_file_bytes": self.max_file_bytes,
            "max_total_index_bytes": self.max_total_index_bytes,
            "max_source_files": self.max_source_files,
            "max_source_directories": self.max_source_directories,
            "max_directory_entries": self.max_directory_entries,
            "max_directory_response_bytes": self.max_directory_response_bytes,
            "max_index_documents": self.max_index_documents,
            "max_index_sections": self.max_index_sections,
            "max_index_sections_per_document": self.max_index_sections_per_document,
            "max_tokens_per_section": self.max_tokens_per_section,
            "max_total_index_tokens": self.max_total_index_tokens,
            "max_frontmatter_bytes": self.max_frontmatter_bytes,
            "max_frontmatter_nodes": self.max_frontmatter_nodes,
            "max_frontmatter_depth": self.max_frontmatter_depth,
        }
        for name, value in positive.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ConfigurationError(f"{name} must be a positive integer")
        if (
            not isinstance(self.max_index_build_seconds, (int, float))
            or isinstance(self.max_index_build_seconds, bool)
            or self.max_index_build_seconds <= 0
        ):
            raise ConfigurationError("max_index_build_seconds must be a positive number")
        if (
            not isinstance(self.related_document_hops, int)
            or isinstance(self.related_document_hops, bool)
            or self.related_document_hops not in (0, 1)
        ):
            raise ConfigurationError("related_document_hops must be 0 or 1")


@dataclass(frozen=True)
class ObsidianSettings:
    base_url: str
    ca_certificate: Path
    api_key: str
    connect_timeout_seconds: float = 3.0
    read_timeout_seconds: float = 10.0
    request_retry_attempts: int = 3
    retry_backoff_seconds: float = 0.25

    def __post_init__(self) -> None:
        require_loopback_https(self.base_url)
        if not self.api_key:
            raise ConfigurationError("DOCUMENTATION_MCP_OBSIDIAN_API_KEY is required")
        if not self.ca_certificate.is_file():
            raise ConfigurationError("Configured CA certificate does not exist")
        if self.connect_timeout_seconds <= 0 or self.read_timeout_seconds <= 0:
            raise ConfigurationError("Obsidian timeouts must be positive")
        if (
            not isinstance(self.request_retry_attempts, int)
            or isinstance(self.request_retry_attempts, bool)
            or not 1 <= self.request_retry_attempts <= 5
        ):
            raise ConfigurationError("request_retry_attempts must be between 1 and 5")
        if (
            not isinstance(self.retry_backoff_seconds, (int, float))
            or isinstance(self.retry_backoff_seconds, bool)
            or not 0 < self.retry_backoff_seconds <= 5
        ):
            raise ConfigurationError(
                "retry_backoff_seconds must be greater than 0 and at most 5"
            )


@dataclass(frozen=True)
class Settings:
    allowed_directories: tuple[str, ...]
    allowed_statuses: tuple[str, ...]
    allowed_types: tuple[str, ...]
    excluded_directories: tuple[str, ...]
    limits: Limits
    obsidian: ObsidianSettings
    backend: str = "obsidian"

    def __post_init__(self) -> None:
        if self.backend != "obsidian":
            raise ConfigurationError("Only the obsidian backend is supported in this release")
        if not self.allowed_directories:
            raise ConfigurationError("At least one allowed_directory is required")
        for excluded in self.excluded_directories:
            if "/" in excluded and not path_is_within(excluded, self.allowed_directories):
                raise ConfigurationError(
                    f"Scoped excluded_directory is outside allowed_directories: {excluded}"
                )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{name} must be a TOML table")
    return value


def _strings(value: Any, name: str, *, required: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigurationError(f"{name} must be an array of strings")
    result = tuple(item.strip() for item in value if item.strip())
    if required and not result:
        raise ConfigurationError(f"{name} must contain at least one value")
    return result


def load_settings(
    config_path: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    path = Path(config_path).expanduser()
    if not path.is_file():
        raise ConfigurationError(f"Configuration file does not exist: {path}")

    with path.open("rb") as stream:
        data = tomllib.load(stream)

    env = os.environ if environ is None else environ
    limits_data = _mapping(data.get("limits", {}), "limits")
    obsidian_data = _mapping(data.get("obsidian", {}), "obsidian")

    try:
        allowed_directories = tuple(
            normalize_vault_path(item)
            for item in _strings(data.get("allowed_directories"), "allowed_directories", required=True)
        )
        excluded = tuple(
            normalize_vault_path(item)
            for item in _strings(data.get("excluded_directories", []), "excluded_directories")
        )
        limits = Limits(
            top_k=limits_data.get("top_k", 5),
            max_total_characters=limits_data.get("max_total_characters", 12_000),
            max_sections=limits_data.get("max_sections", 4),
            max_documents=limits_data.get("max_documents", 2),
            max_sections_per_document=limits_data.get("max_sections_per_document", 2),
            related_document_hops=limits_data.get("related_document_hops", 1),
            max_file_bytes=limits_data.get("max_file_bytes", 1_048_576),
            max_total_index_bytes=limits_data.get("max_total_index_bytes", 33_554_432),
            max_source_files=limits_data.get("max_source_files", 2_000),
            max_source_directories=limits_data.get("max_source_directories", 500),
            max_directory_entries=limits_data.get("max_directory_entries", 5_000),
            max_directory_response_bytes=limits_data.get(
                "max_directory_response_bytes", 1_048_576
            ),
            max_index_documents=limits_data.get("max_index_documents", 1_000),
            max_index_sections=limits_data.get("max_index_sections", 10_000),
            max_index_sections_per_document=limits_data.get(
                "max_index_sections_per_document", 200
            ),
            max_tokens_per_section=limits_data.get("max_tokens_per_section", 10_000),
            max_total_index_tokens=limits_data.get("max_total_index_tokens", 500_000),
            max_frontmatter_bytes=limits_data.get("max_frontmatter_bytes", 65_536),
            max_frontmatter_nodes=limits_data.get("max_frontmatter_nodes", 1_000),
            max_frontmatter_depth=limits_data.get("max_frontmatter_depth", 20),
            max_index_build_seconds=limits_data.get("max_index_build_seconds", 120.0),
        )
        ca_certificate = Path(str(obsidian_data["ca_certificate"])).expanduser()
        obsidian = ObsidianSettings(
            base_url=require_loopback_https(str(obsidian_data.get("base_url", ""))),
            ca_certificate=ca_certificate,
            api_key=env.get("DOCUMENTATION_MCP_OBSIDIAN_API_KEY", ""),
            connect_timeout_seconds=float(obsidian_data.get("connect_timeout_seconds", 3.0)),
            read_timeout_seconds=float(obsidian_data.get("read_timeout_seconds", 10.0)),
            request_retry_attempts=obsidian_data.get("request_retry_attempts", 3),
            retry_backoff_seconds=obsidian_data.get("retry_backoff_seconds", 0.25),
        )
    except KeyError as exc:
        raise ConfigurationError(f"Missing configuration value: obsidian.{exc.args[0]}") from exc
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ConfigurationError):
            raise
        raise ConfigurationError(str(exc)) from exc

    return Settings(
        backend=str(data.get("backend", "obsidian")),
        allowed_directories=allowed_directories,
        allowed_statuses=_strings(data.get("allowed_statuses", []), "allowed_statuses"),
        allowed_types=_strings(data.get("allowed_types", []), "allowed_types"),
        excluded_directories=excluded,
        limits=limits,
        obsidian=obsidian,
    )
