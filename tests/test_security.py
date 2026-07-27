from __future__ import annotations

import pytest

from documentation_mcp.security import (
    SecurityError,
    is_excluded,
    normalize_vault_path,
    path_is_within,
    require_allowed_path,
    require_loopback_https,
)


@pytest.mark.parametrize(
    "url",
    (
        "https://localhost:27124",
        "https://127.0.0.1:27124",
        "https://[::1]:27124",
    ),
)
def test_loopback_https_is_allowed(url):
    assert require_loopback_https(url) == url


@pytest.mark.parametrize(
    "url",
    (
        "http://127.0.0.1:27124",
        "https://example.com:27124",
        "https://user@example.com",
        "https://localhost:27124/vault",
    ),
)
def test_non_local_or_unsafe_urls_are_rejected(url):
    with pytest.raises(SecurityError):
        require_loopback_https(url)


@pytest.mark.parametrize(
    "path",
    (
        "../private.md",
        "Documentation/../../private.md",
        "Documentation/%2e%2e/private.md",
        "Documentation/%252e%252e/private.md",
        "/Documentation/file.md",
        "C:/Documentation/file.md",
        r"Documentation\file.md",
    ),
)
def test_unsafe_vault_paths_are_rejected(path):
    with pytest.raises(SecurityError):
        normalize_vault_path(path)


def test_scope_enforcement():
    roots = ("Documentation",)
    assert require_allowed_path("Documentation/features/a.md", roots) == "Documentation/features/a.md"
    assert path_is_within("Documentation", roots)
    with pytest.raises(SecurityError, match="outside"):
        require_allowed_path("Other/a.md", roots)


def test_excluded_directory_matches_complete_path_component():
    excluded = ("_meta",)
    assert is_excluded("Documentation/_meta/a.md", excluded)
    assert not is_excluded("Documentation/metadata/a.md", excluded)


def test_excluded_path_matches_descendants_only():
    excluded = ("Documentation/private",)
    assert is_excluded("Documentation/private/a.md", excluded)
    assert is_excluded("Documentation/private", excluded)
    assert not is_excluded("Documentation/private-notes/a.md", excluded)
    assert not is_excluded("Documentation/private.md", excluded)
    assert not is_excluded("Other/private/a.md", excluded)


def test_component_exclusion_still_matches_any_complete_component():
    excluded = ("_meta",)
    assert is_excluded("Documentation/area/_meta/a.md", excluded)
    assert is_excluded("Other/_meta/a.md", excluded)
    assert not is_excluded("Documentation/area/_metadata/a.md", excluded)
