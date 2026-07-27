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


@pytest.fixture
def routing_documents() -> dict[str, str]:
    return {
        "Documentation/preferences.md": """---
document_id: service-preferences
title: Service preferences
summary: Canonical service configuration.
status: active
type: feature-doc
area: platform
evidence: specified
related_documents: [runtime-behavior, transfer-format, missing-document]
---
# Preferences Configuration

## Interface

Generate item per region is a service preference with a documented default.

| Setting | Default | Purpose |
| --- | --- | --- |
| generate_item_per_region | true | Generate one item for every active region. |
| processing_interval | Standard | Select the processing interval. |

## Validation

The processing interval must be a supported value.
""",
        "Documentation/runtime.md": """---
document_id: runtime-behavior
title: Runtime behavior
summary: Operational generation behavior.
status: active
type: feature-doc
area: platform
evidence: observed
related_documents: [service-preferences, transfer-format]
---
# Runtime processing

## Behavior

### Changing generate item per region preference

When generate item per region is enabled, processing creates one item for each
active region using the configured processing interval.

## Failure handling

An invalid region is skipped and recorded without stopping other regions.
""",
        "Documentation/transfer.md": """---
document_id: transfer-format
title: Transfer representation
summary: Peripheral import and export representation.
status: active
type: feature-doc
area: platform
evidence: specified
related_documents: [runtime-behavior, downstream-format]
---
# Transfer representation

## Interface

### File Format

#### Per-region mode indicator

Import and export files serialize the generate item per region flag as a field.
""",
        "Documentation/downstream.md": """---
document_id: downstream-format
title: Downstream format
summary: A second-hop representation.
status: active
type: feature-doc
area: platform
evidence: specified
---
# Downstream format

## Reference

The archive checksum representation is used only by a downstream consumer.
""",
        "Documentation/inactive.md": """---
document_id: inactive-target
title: Inactive target
summary: Content excluded from the active index.
status: draft
type: feature-doc
area: platform
related_documents: [service-preferences]
---
# Inactive target

## Interface

This inactive interface must not participate in routing.
""",
    }
