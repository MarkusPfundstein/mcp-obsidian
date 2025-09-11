"""Settings resolution utilities for mcp-obsidian.

This module adds support for configuring the server by pointing to an
Obsidian vault (or any parent directory down to the plugin's
``data.json``) containing the Local REST API plugin configuration.

Precedence (highest last applied):
        1. .env / environment defaults
        2. CLI overrides (protocol/host/port)
        3. Plugin configuration (api key + ports + enabled protocols)

Protocol selection rules:
        * If only one of secure/insecure server is enabled in plugin config,
            that protocol is forced.
        * If both are enabled, we keep the chosen protocol (CLI/env/default)
            with preference for https when none supplied and https enabled.

Exported API:
        - resolve_settings: main entry returning a ResolvedSettings instance
        - load_plugin_config: parse plugin configuration if present
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional


class ResolvedSettings:
    """Container for resolved connection settings.

    Attributes
    ----------
    api_key: str
        API key for the Obsidian Local REST API.
    host: str
        Hostname to connect to (defaults to localhost).
    port: int
        Port corresponding to chosen protocol.
    protocol: str
        Either ``http`` or ``https``.
    source: str
        Human readable description of precedence used.
    extra: dict
        Raw plugin configuration values (if any) for diagnostics.

    """

    def __init__(
        self,
        api_key: str,
        host: str,
        port: int,
        protocol: str,
        source: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Initialize resolved settings container."""
        self.api_key = api_key
        self.host = host
        self.port = port
        self.protocol = protocol
        self.source = source
        self.extra = extra or {}

    def export_env(self) -> None:
        """Export values to process environment for existing code paths."""
        os.environ["OBSIDIAN_API_KEY"] = self.api_key
        os.environ["OBSIDIAN_HOST"] = self.host
        os.environ["OBSIDIAN_PORT"] = str(self.port)
        os.environ["OBSIDIAN_PROTOCOL"] = self.protocol

    def as_dict(self) -> dict[str, Any]:
        """Return a dict snapshot of the settings for logging/debugging."""
        return {
            "api_key": self.api_key,
            "host": self.host,
            "port": self.port,
            "protocol": self.protocol,
            "source": self.source,
            **{f"extra_{k}": v for k, v in self.extra.items()},
        }


PLUGIN_RELATIVE = Path(".obsidian/plugins/obsidian-local-rest-api/data.json")


def _locate_plugin_config(base_path: Path) -> Optional[Path]:
    """Locate plugin ``data.json`` starting from a flexible user path.

    The user may supply any of:
        * Vault root
        * ``<vault>/.obsidian``
        * ``<vault>/.obsidian/plugins``
        * ``<vault>/.obsidian/plugins/obsidian-local-rest-api``
        * Full path to ``data.json``

    Parameters
    ----------
    base_path: Path
        User supplied path.

    Returns
    -------
    Path | None
        Resolved path to ``data.json`` if found.

    """
    p = base_path
    if p.is_file():
        if p.name == "data.json" and "obsidian-local-rest-api" in str(p.parent):
            return p
        return None

    # If user gave a directory, try progressively
    # 1) direct path might already be plugin dir
    candidate_files = []
    if (p / "data.json").exists():  # plugin dir case
        candidate_files.append(p / "data.json")
    candidate_files.append(p / PLUGIN_RELATIVE)  # vault root case
    # .obsidian provided
    candidate_files.append(p / "plugins/obsidian-local-rest-api/data.json")
    # plugins dir provided
    candidate_files.append(p / "obsidian-local-rest-api/data.json")

    for c in candidate_files:
        if c.exists():
            return c
    return None


def load_plugin_config(path_like: str | None) -> Optional[dict[str, Any]]:
    """Load and normalize plugin configuration if present.

    Parameters
    ----------
    path_like: str | None
        Path hint provided by user.

    Returns
    -------
    dict | None
        Normalized configuration dict or None if not found.

    """
    if not path_like:
        return None
    base = Path(path_like).expanduser().resolve()
    cfg_path = _locate_plugin_config(base)
    if not cfg_path:
        return None
    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # broad but deliberate: config read issues
        msg = f"Failed reading plugin config at {cfg_path}: {exc!s}"
        raise RuntimeError(msg) from exc
    return {
        "api_key": data.get("apiKey"),
        "https_port": data.get("port"),
        "http_port": data.get("insecurePort"),
        "secure_enabled": bool(data.get("enableSecureServer")),
        "insecure_enabled": bool(data.get("enableInsecureServer")),
        "_config_path": str(cfg_path),
    }


def resolve_settings(
    vault_path: str | None,
    cli_protocol: str | None,
    cli_host: str | None,
    cli_port: int | None,
) -> ResolvedSettings:
    """Resolve final settings.

    Parameters
    ----------
    vault_path: str | None
        Optional path pointing at vault or plugin config.
    cli_protocol: str | None
        Protocol override from CLI (http/https).
    cli_host: str | None
        Host override from CLI.
    cli_port: int | None
        Port override from CLI.

    Returns
    -------
    ResolvedSettings
        Effective configuration with side-effect of exporting env vars.

    """
    env_api_key = os.getenv("OBSIDIAN_API_KEY")
    host = cli_host or os.getenv("OBSIDIAN_HOST", "127.0.0.1")
    port = cli_port or int(os.getenv("OBSIDIAN_PORT", "27124"))
    protocol = (cli_protocol or os.getenv("OBSIDIAN_PROTOCOL", "https")).lower()

    plugin = load_plugin_config(vault_path)
    source_parts: list[str] = ["env/defaults"]
    if cli_host:
        source_parts.append("cli-host")
    if cli_port is not None:
        source_parts.append("cli-port")
    if cli_protocol:
        source_parts.append("cli-protocol")

    api_key = env_api_key
    if plugin:
        source_parts.append("plugin-config")
        if plugin.get("api_key"):
            api_key = plugin["api_key"]
        https_enabled = plugin.get("secure_enabled", False)
        http_enabled = plugin.get("insecure_enabled", False)
        https_port = plugin.get("https_port") or 27124
        http_port = plugin.get("http_port") or 27123

        single_secure = https_enabled and not http_enabled
        single_insecure = http_enabled and not https_enabled
        both_or_none = not single_secure and not single_insecure

        if single_secure:
            protocol, port = "https", https_port
        elif single_insecure:
            protocol, port = "http", http_port
        else:  # both enabled or neither
            if protocol not in {"http", "https"}:
                protocol = "https" if https_enabled else "http"
            if protocol == "https" and https_enabled:
                port = https_port
            elif protocol == "http" and http_enabled:
                port = http_port
            elif protocol == "https" and not https_enabled and not both_or_none:
                err = (
                    "Protocol https requested but secure server disabled in plugin "
                    "config"
                )
                raise RuntimeError(err)
            elif protocol == "http" and not http_enabled and not both_or_none:
                err = (
                    "Protocol http requested but insecure server disabled in plugin "
                    "config"
                )
                raise RuntimeError(err)

    if not api_key:
        msg = "OBSIDIAN_API_KEY not found via env or plugin configuration."
        raise RuntimeError(msg)

    rs = ResolvedSettings(
        api_key=api_key,
        host=host,
        port=port,
        protocol=protocol,
        source="+".join(source_parts),
        extra=plugin or {},
    )
    rs.export_env()
    return rs
