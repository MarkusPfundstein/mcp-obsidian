from __future__ import annotations

import ipaddress
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse


class SecurityError(ValueError):
    """Raised when configuration or a requested path violates server policy."""


def require_loopback_https(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != "https":
        raise SecurityError("Obsidian base_url must use HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SecurityError("Obsidian base_url must not contain credentials, query, or fragment")
    if parsed.path not in ("", "/"):
        raise SecurityError("Obsidian base_url must not contain a path")

    hostname = parsed.hostname
    if hostname is None:
        raise SecurityError("Obsidian base_url must include a host")
    if hostname != "localhost":
        try:
            if not ipaddress.ip_address(hostname).is_loopback:
                raise SecurityError("Obsidian base_url must use a loopback host")
        except ValueError as exc:
            raise SecurityError("Obsidian base_url must use localhost or a loopback IP") from exc

    return base_url.rstrip("/")


def normalize_vault_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SecurityError("Vault path must be a non-empty string")

    raw = value.strip()
    if "\\" in raw:
        raise SecurityError("Backslashes are not allowed in vault paths")
    decoded = unquote(unquote(raw))
    if decoded.startswith("/") or decoded.startswith("//"):
        raise SecurityError("Absolute vault paths are not allowed")

    path = PurePosixPath(decoded)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise SecurityError("Vault path contains unsafe components")
    if path.parts and ":" in path.parts[0]:
        raise SecurityError("Drive-qualified vault paths are not allowed")

    return path.as_posix().rstrip("/")


def path_is_within(path: str, roots: tuple[str, ...]) -> bool:
    normalized = normalize_vault_path(path)
    return any(normalized == root or normalized.startswith(f"{root}/") for root in roots)


def require_allowed_path(path: str, roots: tuple[str, ...]) -> str:
    normalized = normalize_vault_path(path)
    if not path_is_within(normalized, roots):
        raise SecurityError("Path is outside the configured documentation scope")
    return normalized


def is_excluded(path: str, excluded_directories: tuple[str, ...]) -> bool:
    normalized = normalize_vault_path(path)
    parts = set(PurePosixPath(normalized).parts)
    for excluded in excluded_directories:
        normalized_excluded = normalize_vault_path(excluded)
        if "/" in normalized_excluded:
            if normalized == normalized_excluded or normalized.startswith(f"{normalized_excluded}/"):
                return True
        elif normalized_excluded in parts:
            return True
    return False
