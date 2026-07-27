from __future__ import annotations

import pytest

from documentation_mcp.config import Limits
from documentation_mcp.markdown import DocumentRejected, parse_document


def test_frontmatter_and_heading_paths_are_parsed():
    document = parse_document(
        "Documentation/example.md",
        """---
document_id: example
title: Example
status: active
type: feature-doc
related_documents: [another]
---
# Feature

Introduction.

## Behavior

The feature performs an action.

### Failure handling

The action stops safely.
""",
    )
    assert document.document_id == "example"
    assert document.related_documents == ("another",)
    assert [section.heading_path for section in document.sections] == [
        "Feature",
        "Feature > Behavior",
        "Feature > Behavior > Failure handling",
    ]
    assert document.sections[1].role == "behavior"
    assert document.sections[2].role == "edge-case"


def test_chunk_ids_are_stable_for_unchanged_document():
    content = "# Title\n\n## Defaults\n\nThe default is enabled."
    first = parse_document("Documentation/a.md", content)
    second = parse_document("Documentation/a.md", content)
    assert [section.chunk_id for section in first.sections] == [
        section.chunk_id for section in second.sections
    ]


def test_malformed_frontmatter_does_not_crash_parser():
    document = parse_document(
        "Documentation/a.md",
        "---\ninvalid: [\n---\n# Title\n\nBody.",
    )
    assert document.title == "Title"
    assert document.sections[0].text == "Body."


def test_headingless_document_gets_overview_section():
    document = parse_document("Documentation/plain.md", "Plain documentation body.")
    assert document.sections[0].heading_path == "Overview"
    assert document.sections[0].text == "Plain documentation body."


def test_oversized_document_is_rejected_before_parsing():
    with pytest.raises(DocumentRejected, match="file too large"):
        parse_document(
            "Documentation/large.md",
            "123456",
            Limits(max_file_bytes=5),
        )


def test_oversized_frontmatter_is_rejected():
    content = "---\ntitle: This title is too long\n---\n# Title\n\nBody."
    with pytest.raises(DocumentRejected, match="frontmatter too large"):
        parse_document(
            "Documentation/frontmatter.md",
            content,
            Limits(max_frontmatter_bytes=10),
        )


def test_frontmatter_aliases_are_rejected_before_loading():
    content = """---
tags: &tags [one, two]
copied: *tags
---
# Title

Body.
"""
    with pytest.raises(DocumentRejected, match="alias not allowed"):
        parse_document("Documentation/aliases.md", content)


def test_frontmatter_structure_is_bounded():
    content = """---
outer:
  inner:
    value: nested
---
# Title

Body.
"""
    with pytest.raises(DocumentRejected, match="depth limit"):
        parse_document(
            "Documentation/deep.md",
            content,
            Limits(max_frontmatter_depth=1),
        )


def test_frontmatter_node_count_is_bounded():
    content = """---
first: one
second: two
---
# Title

Body.
"""
    with pytest.raises(DocumentRejected, match="node limit"):
        parse_document(
            "Documentation/many-nodes.md",
            content,
            Limits(max_frontmatter_nodes=2),
        )


def test_document_section_count_is_bounded():
    content = "# One\n\nFirst.\n\n## Two\n\nSecond."
    with pytest.raises(DocumentRejected, match="document section limit"):
        parse_document(
            "Documentation/sections.md",
            content,
            Limits(max_index_sections_per_document=1),
        )


def test_section_token_count_is_bounded():
    with pytest.raises(DocumentRejected, match="section token limit"):
        parse_document(
            "Documentation/tokens.md",
            "# Title\n\none two three",
            Limits(max_tokens_per_section=2),
        )
