from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from documentation_mcp.config import ConfigurationError, Limits, load_settings


def _write_config(
    tmp_path: Path,
    certificate: Path,
    extra: str = "",
    *,
    allowed_directories: str = '["Documentation"]',
    excluded_directories: str = '["_meta"]',
) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        f"""
backend = "obsidian"
allowed_directories = {allowed_directories}
allowed_statuses = ["active"]
allowed_types = []
excluded_directories = {excluded_directories}

[limits]
top_k = 3
max_total_characters = 1000
max_sections = 3
max_documents = 2
max_sections_per_document = 2
related_document_hops = 1

[obsidian]
base_url = "https://localhost:27124"
ca_certificate = "{certificate.as_posix()}"
{extra}
""",
        encoding="utf-8",
    )
    return path


def test_load_settings_requires_api_key(tmp_path, certificate):
    path = _write_config(tmp_path, certificate)
    with pytest.raises(ConfigurationError, match="API_KEY"):
        load_settings(path, environ={})


def test_load_settings_parses_safe_configuration(tmp_path, certificate):
    settings = load_settings(
        _write_config(tmp_path, certificate),
        environ={"DOCUMENTATION_MCP_OBSIDIAN_API_KEY": "secret"},
    )
    assert settings.allowed_directories == ("Documentation",)
    assert settings.limits.top_k == 3
    assert settings.obsidian.api_key == "secret"


def test_load_settings_parses_bounded_request_retry_policy(tmp_path, certificate):
    settings = load_settings(
        _write_config(
            tmp_path,
            certificate,
            extra=(
                "request_retry_attempts = 4\n"
                "retry_backoff_seconds = 0.5\n"
            ),
        ),
        environ={"DOCUMENTATION_MCP_OBSIDIAN_API_KEY": "secret"},
    )

    assert settings.obsidian.request_retry_attempts == 4
    assert settings.obsidian.retry_backoff_seconds == 0.5


def test_documented_minimal_configuration_applies_defaults(tmp_path, certificate):
    path = tmp_path / "config.toml"
    path.write_text(
        f"""
allowed_directories = ["Documentation"]

[obsidian]
base_url = "https://127.0.0.1:27124"
ca_certificate = "{certificate.as_posix()}"
""",
        encoding="utf-8",
    )

    settings = load_settings(
        path,
        environ={"DOCUMENTATION_MCP_OBSIDIAN_API_KEY": "secret"},
    )

    assert settings.backend == "obsidian"
    assert settings.allowed_statuses == ()
    assert settings.allowed_types == ()
    assert settings.excluded_directories == ()
    assert settings.limits == Limits()
    assert settings.obsidian.connect_timeout_seconds == 3.0
    assert settings.obsidian.read_timeout_seconds == 10.0


def test_missing_certificate_fails_closed(tmp_path):
    missing = tmp_path / "missing.crt"
    path = _write_config(tmp_path, missing)
    with pytest.raises(ConfigurationError, match="certificate"):
        load_settings(path, environ={"DOCUMENTATION_MCP_OBSIDIAN_API_KEY": "secret"})


def test_scoped_exclusion_within_allowed_root_is_accepted(tmp_path, certificate):
    settings = load_settings(
        _write_config(
            tmp_path,
            certificate,
            allowed_directories='["Documentation", "Team"]',
            excluded_directories='["Team/private"]',
        ),
        environ={"DOCUMENTATION_MCP_OBSIDIAN_API_KEY": "secret"},
    )
    assert settings.allowed_directories == ("Documentation", "Team")
    assert settings.excluded_directories == ("Team/private",)


def test_scoped_exclusion_outside_allowed_roots_fails_closed(tmp_path, certificate):
    with pytest.raises(ConfigurationError, match="outside allowed_directories"):
        load_settings(
            _write_config(
                tmp_path,
                certificate,
                excluded_directories='["Other/private"]',
            ),
            environ={"DOCUMENTATION_MCP_OBSIDIAN_API_KEY": "secret"},
        )


@pytest.mark.parametrize(
    "name",
    (
        "top_k",
        "max_sections",
        "max_documents",
        "max_file_bytes",
        "max_total_index_bytes",
        "max_source_files",
        "max_source_directories",
        "max_directory_entries",
        "max_directory_response_bytes",
        "max_index_documents",
        "max_index_sections",
        "max_index_sections_per_document",
        "max_tokens_per_section",
        "max_total_index_tokens",
        "max_frontmatter_bytes",
        "max_frontmatter_nodes",
        "max_frontmatter_depth",
    ),
)
def test_limits_must_be_positive(name):
    arguments = {name: 0}
    with pytest.raises(ConfigurationError, match=name):
        Limits(**arguments)


def test_related_hops_are_bounded():
    with pytest.raises(ConfigurationError, match="0 or 1"):
        Limits(related_document_hops=2)


@pytest.mark.parametrize("value", (0, -1, True, "120"))
def test_index_build_deadline_must_be_a_positive_number(value):
    with pytest.raises(ConfigurationError, match="max_index_build_seconds"):
        Limits(max_index_build_seconds=value)


@pytest.mark.parametrize("value", (0, 6, True, 1.5))
def test_request_retry_attempts_are_bounded(settings, value):
    with pytest.raises(ConfigurationError, match="request_retry_attempts"):
        replace(settings.obsidian, request_retry_attempts=value)


@pytest.mark.parametrize("value", (0, -1, 6, True, "0.25"))
def test_retry_backoff_is_bounded(settings, value):
    with pytest.raises(ConfigurationError, match="retry_backoff_seconds"):
        replace(settings.obsidian, retry_backoff_seconds=value)
