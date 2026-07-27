from __future__ import annotations

from pathlib import Path

import pytest

from documentation_mcp.config import Limits, ObsidianSettings, Settings


class MemorySource:
    def __init__(self, files: dict[str, str]):
        self.files = files

    def iter_markdown_files(self, *, deadline=None):
        return iter(sorted(self.files))

    def read_file(self, path: str, *, deadline=None) -> str:
        return self.files[path]


@pytest.fixture
def certificate(tmp_path: Path) -> Path:
    path = tmp_path / "local-ca.crt"
    path.write_text("synthetic test certificate", encoding="utf-8")
    return path


@pytest.fixture
def settings(certificate: Path) -> Settings:
    return Settings(
        allowed_directories=("Documentation",),
        allowed_statuses=("active", "unreviewed"),
        allowed_types=("feature-doc",),
        excluded_directories=("_inventory", "_meta"),
        limits=Limits(
            top_k=5,
            max_total_characters=500,
            max_sections=4,
            max_documents=2,
            max_sections_per_document=2,
            related_document_hops=1,
        ),
        obsidian=ObsidianSettings(
            base_url="https://127.0.0.1:27124",
            ca_certificate=certificate,
            api_key="synthetic-key",
        ),
    )


@pytest.fixture
def documents() -> dict[str, str]:
    return {
        "Documentation/preferences.md": """---
document_id: preferences
title: Service preferences
summary: Configurable service defaults.
status: active
type: feature-doc
area: platform
evidence: specified
private_token: direct-secret-must-not-leak
tags:
  - configuration
  - private_token: nested-tag-secret-must-not-leak
  - [nested-list-secret-must-not-leak]
related_documents:
  - runtime-behavior
  - id: nested-related-secret-must-not-leak
---
# Service preferences

## Defaults

The default retry limit is three attempts.

## Validation

The retry limit must be a positive integer.
""",
        "Documentation/runtime.md": """---
document_id: runtime-behavior
title: Runtime behavior
summary: Runtime processing after a failed request.
status: active
type: feature-doc
area: platform
evidence: observed
internal_owner: private-owner-must-not-leak
tags: [runtime]
related_documents: [preferences]
---
# Runtime behavior

## Processing

Failed requests are retried until the configured retry limit is reached.

## Failure handling

The service records a terminal failure after the final attempt.
""",
        "Documentation/_meta/ignored.md": """---
document_id: generated
status: active
type: feature-doc
---
# Generated

This file must not be indexed.
""",
    }
