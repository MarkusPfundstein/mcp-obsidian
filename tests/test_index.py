from __future__ import annotations

import json
from dataclasses import replace

import pytest

from documentation_mcp.index import DocumentationIndex
from documentation_mcp.serialization import serialized_character_count
from documentation_mcp.source import SourceDocumentError

from .conftest import MemorySource


def _index(settings, documents):
    index = DocumentationIndex(settings)
    index.rebuild(MemorySource(documents))
    return index


def test_index_filters_status_type_and_excluded_sources(settings, documents):
    index = _index(settings, documents)
    assert set(index.documents) == {"preferences", "runtime-behavior"}
    assert len(index.sections) == 4
    assert len(index.snapshot) == 64


def test_search_returns_ranked_compact_sections(settings, documents):
    index = _index(settings, documents)
    results = index.search("default retry limit")
    assert results
    assert results[0]["document_id"] == "preferences"
    assert results[0]["heading_path"] == "Service preferences > Defaults"
    assert "heading-match" in results[0]["ranking_reasons"]
    assert all(set(result) == {
        "chunk_id",
        "document_id",
        "heading_path",
        "summary",
        "excerpt",
        "evidence",
        "score",
        "source",
        "route",
        "ranking_reasons",
    } for result in results)


def test_search_applies_metadata_filters(settings, documents):
    index = _index(settings, documents)
    assert index.search("retry", filters={"area": "platform"})
    assert index.search("retry", filters={"area": "other"}) == []
    with pytest.raises(ValueError, match="Unsupported"):
        index.search("retry", filters={"owner": "team"})


def test_related_document_routing_preserves_metadata_filters(settings, documents):
    filtered_documents = dict(documents)
    filtered_documents["Documentation/runtime.md"] = filtered_documents[
        "Documentation/runtime.md"
    ].replace("area: platform", "area: restricted")
    index = _index(settings, filtered_documents)

    results = index.search("retry failure", filters={"area": "platform"})

    assert results
    assert {result["document_id"] for result in results} == {"preferences"}


def test_search_caps_client_limits(settings, documents):
    index = _index(settings, documents)
    results = index.search("retry service", top_k=99, max_total_characters=20_000)
    assert len(results) <= settings.limits.max_sections
    assert len({result["document_id"] for result in results}) <= settings.limits.max_documents
    assert serialized_character_count(results) <= settings.limits.max_total_characters


def test_search_returns_nothing_when_metadata_exceeds_character_budget(settings, documents):
    index = _index(settings, documents)

    assert index.search("retry", max_total_characters=1) == []


def test_related_document_routing_is_bounded(settings, documents):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_total_characters=2_000),
    )
    index = _index(bounded, documents)
    results = index.search("default retry failure")
    assert any(result["route"].startswith("related:") for result in results)
    assert all(result["route"].count("related:") <= 1 for result in results)


def test_role_aware_routing_preserves_canonical_and_behavior_evidence(
    settings,
    routing_documents,
):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_total_characters=4_200),
    )
    index = _index(bounded, routing_documents)

    results = index.search("generate item per region")
    headings = {result["heading_path"] for result in results}

    assert "Preferences Configuration > Interface" in headings
    assert (
        "Runtime processing > Behavior > Changing generate item per region preference"
        in headings
    )
    assert (
        "Transfer representation > Interface > File Format > Per-region mode indicator"
        not in headings
    )
    assert any(result["route"].startswith("related:") for result in results)
    assert len({result["document_id"] for result in results}) <= 2
    assert len(results) <= 4
    assert serialized_character_count(results) <= 4_200


def test_role_aware_routing_is_deterministic_and_does_not_amplify_cycles(
    settings,
    routing_documents,
):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_total_characters=4_200),
    )
    index = _index(bounded, routing_documents)

    first = index.search("generate item per region default behavior")
    second = index.search("generate item per region default behavior")

    assert first == second
    assert len({result["chunk_id"] for result in first}) == len(first)
    routed = [result for result in first if result["route"].startswith("related:")]
    assert len(routed) <= 1
    assert all(
        result["route"] == f"related:{first[0]['document_id']}"
        for result in routed
    )
    assert all(
        result["ranking_reasons"].count("related-document-hop") <= 1
        for result in first
    )


@pytest.mark.parametrize(
    ("limit_changes", "maximum_results", "maximum_documents", "maximum_per_document"),
    (
        ({"max_sections": 2}, 2, 2, 2),
        ({"max_documents": 1}, 4, 1, 2),
        ({"max_sections_per_document": 1}, 4, 2, 1),
    ),
)
def test_role_aware_routing_preserves_selection_limits(
    settings,
    routing_documents,
    limit_changes,
    maximum_results,
    maximum_documents,
    maximum_per_document,
):
    bounded = replace(
        settings,
        limits=replace(
            settings.limits,
            max_total_characters=4_200,
            **limit_changes,
        ),
    )
    index = _index(bounded, routing_documents)

    results = index.search("generate item per region default behavior")
    counts: dict[str, int] = {}
    for result in results:
        counts[result["document_id"]] = counts.get(result["document_id"], 0) + 1

    assert len(results) <= maximum_results
    assert len(counts) <= maximum_documents
    assert all(count <= maximum_per_document for count in counts.values())


def test_related_routing_respects_filters_and_inactive_targets(
    settings,
    routing_documents,
):
    filtered = dict(routing_documents)
    filtered["Documentation/runtime.md"] = filtered[
        "Documentation/runtime.md"
    ].replace("area: platform", "area: restricted")
    filtered["Documentation/transfer.md"] = filtered[
        "Documentation/transfer.md"
    ].replace("area: platform", "area: restricted")
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_total_characters=4_200),
    )
    index = _index(bounded, filtered)

    results = index.search(
        "generate item per region",
        filters={"area": "platform"},
    )

    assert results
    assert {result["document_id"] for result in results} == {"service-preferences"}
    assert "inactive-target" not in index.documents
    assert all("missing-document" not in result["route"] for result in results)


def test_relationship_routing_never_follows_a_second_hop(
    settings,
    routing_documents,
):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_total_characters=4_200),
    )
    index = _index(bounded, routing_documents)

    results = index.search("generate item per region")
    routed = [result for result in results if result["route"].startswith("related:")]

    assert len(routed) <= 1
    assert all(
        result["route"]
        in {"related:service-preferences", "related:runtime-behavior"}
        for result in routed
    )
    assert not any(result["document_id"] == "downstream-format" for result in routed)


def test_relationship_routing_can_be_disabled(settings, routing_documents):
    direct_only = replace(
        settings,
        limits=replace(
            settings.limits,
            max_total_characters=4_200,
            related_document_hops=0,
        ),
    )
    index = _index(direct_only, routing_documents)

    results = index.search("generate item per region default behavior")

    assert results
    assert all(result["route"] == "direct" for result in results)


def test_irrelevant_relationships_do_not_override_direct_ranking(
    settings,
    routing_documents,
):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_total_characters=4_200),
    )
    index = _index(bounded, routing_documents)

    results = index.search("archive checksum downstream consumer")

    assert results[0]["document_id"] == "downstream-format"
    assert results[0]["route"] == "direct"
    assert all(result["route"] == "direct" for result in results)


def test_flat_direct_ranking_remains_relevance_ordered(settings):
    bounded = replace(
        settings,
        allowed_statuses=(),
        allowed_types=(),
        limits=replace(settings.limits, max_total_characters=2_000),
    )
    index = _index(
        bounded,
        {
            "Documentation/strong.md": (
                "# Strong\n\n## Behavior\n\nA worker retries a request after a timeout."
            ),
            "Documentation/weak.md": (
                "# Weak\n\n## Notes\n\nA request can be inspected."
            ),
        },
    )

    results = index.search("retry request timeout")

    assert results[0]["source"] == "Documentation/strong.md"
    assert all(result["route"] == "direct" for result in results)


def test_metadata_section_and_related_lookups(settings, documents):
    index = _index(settings, documents)
    metadata = index.document_metadata("preferences")
    assert metadata["title"] == "Service preferences"
    assert "frontmatter" not in metadata
    assert "must-not-leak" not in json.dumps(metadata)
    assert metadata["tags"] == ["configuration"]
    assert metadata["related_documents"] == ["runtime-behavior"]
    assert set(metadata) == {
        "document_id",
        "source",
        "title",
        "summary",
        "status",
        "type",
        "area",
        "evidence",
        "tags",
        "related_documents",
        "section_count",
    }

    chunk_id = index.documents["preferences"].sections[0].chunk_id
    section = index.document_section(chunk_id=chunk_id, max_characters=12)
    assert len(section["text"]) <= 12
    assert section["truncated"]

    related = index.related_documents("preferences")
    assert [item["document_id"] for item in related] == ["runtime-behavior"]
    assert "must-not-leak" not in json.dumps(related)


def test_unknown_documents_and_sections_fail(settings, documents):
    index = _index(settings, documents)
    with pytest.raises(KeyError, match="Document"):
        index.document_metadata("missing")
    with pytest.raises(KeyError, match="Section"):
        index.document_section(chunk_id="missing")


def test_oversized_document_is_quarantined_without_partial_indexing(settings):
    bounded = replace(
        settings,
        allowed_statuses=(),
        allowed_types=(),
        limits=replace(settings.limits, max_file_bytes=64),
    )
    index = DocumentationIndex(bounded)
    index.rebuild(
        MemorySource(
            {
                "Documentation/large.md": "# Large\n\n" + ("x" * 100),
                "Documentation/valid.md": "# Valid\n\nSmall body.",
            }
        )
    )

    assert set(index.documents_by_source) == {"Documentation/valid.md"}
    assert all(section.source != "Documentation/large.md" for section in index.sections.values())
    assert len(index.index_diagnostics) == 1
    diagnostic = index.index_diagnostics[0]
    assert diagnostic.source == "Documentation/large.md"
    assert diagnostic.reason == "file_too_large"


def test_document_read_error_is_quarantined_without_aborting_build(settings):
    class MalformedSource(MemorySource):
        def read_file(self, path, *, deadline=None):
            if path.endswith("malformed.md"):
                raise SourceDocumentError("invalid_utf8")
            return super().read_file(path, deadline=deadline)

    bounded = replace(settings, allowed_statuses=(), allowed_types=())
    index = DocumentationIndex(bounded)
    index.rebuild(
        MalformedSource(
            {
                "Documentation/malformed.md": "ignored",
                "Documentation/valid.md": "# Valid\n\nSearchable.",
            }
        )
    )

    assert set(index.documents_by_source) == {"Documentation/valid.md"}
    assert index.build_completed is True
    assert index.skipped_document_count == 1
    assert index.index_diagnostics[-1].reason == "invalid_utf8"


def test_duplicate_document_id_is_quarantined_without_aborting_build(settings):
    bounded = replace(settings, allowed_statuses=(), allowed_types=())
    index = DocumentationIndex(bounded)
    index.rebuild(
        MemorySource(
            {
                "Documentation/a.md": (
                    "---\ndocument_id: duplicate\n---\n# First\n\none"
                ),
                "Documentation/b.md": (
                    "---\ndocument_id: duplicate\n---\n# Second\n\ntwo"
                ),
            }
        )
    )

    assert set(index.documents) == {"duplicate"}
    assert index.build_completed is True
    assert index.skipped_document_count == 1
    assert index.index_diagnostics[-1].reason == "duplicate_document_id"


@pytest.mark.parametrize(
    ("limit_changes", "reason"),
    (
        ({"max_index_documents": 1}, "index_document_limit"),
        ({"max_index_sections": 1}, "total_index_sections_limit"),
        ({"max_total_index_tokens": 1}, "total_index_tokens_limit"),
    ),
)
def test_total_index_resources_are_bounded(settings, limit_changes, reason):
    bounded = replace(
        settings,
        allowed_statuses=(),
        allowed_types=(),
        limits=replace(settings.limits, **limit_changes),
    )
    index = DocumentationIndex(bounded)
    index.rebuild(
        MemorySource(
            {
                "Documentation/a.md": "# A\n\none",
                "Documentation/b.md": "# B\n\ntwo",
            }
        )
    )

    assert len(index.documents) == 1
    assert index.index_diagnostics[-1].reason == reason
    assert index.build_completed is (reason != "index_document_limit")


def test_total_source_byte_budget_stops_before_parsing_next_document(settings):
    first = "# A\n\none"
    second = "# B\n\ntwo"
    bounded = replace(
        settings,
        allowed_statuses=(),
        allowed_types=(),
        limits=replace(
            settings.limits,
            max_total_index_bytes=len(first.encode("utf-8")),
        ),
    )
    index = DocumentationIndex(bounded)
    index.rebuild(
        MemorySource(
            {
                "Documentation/a.md": first,
                "Documentation/b.md": second,
            }
        )
    )

    assert set(index.documents_by_source) == {"Documentation/a.md"}
    assert index.source_bytes_processed == len(first.encode("utf-8"))
    assert index.index_diagnostics[-1].reason == "total_index_bytes_limit"
    assert index.build_completed is False


def test_many_source_files_are_bounded_for_generic_sources(settings):
    bounded = replace(
        settings,
        allowed_statuses=(),
        allowed_types=(),
        limits=replace(settings.limits, max_source_files=2),
    )
    index = DocumentationIndex(bounded)
    index.rebuild(
        MemorySource(
            {
                "Documentation/a.md": "# A\n\none",
                "Documentation/b.md": "# B\n\ntwo",
                "Documentation/c.md": "# C\n\nthree",
            }
        )
    )

    assert set(index.documents_by_source) == {
        "Documentation/a.md",
        "Documentation/b.md",
    }
    assert index.index_diagnostics[-1].reason == "source_file_limit"
    assert index.build_completed is False


def test_parser_rejection_quarantines_the_whole_document(settings):
    bounded = replace(
        settings,
        allowed_statuses=(),
        allowed_types=(),
        limits=replace(settings.limits, max_tokens_per_section=2),
    )
    index = DocumentationIndex(bounded)
    index.rebuild(
        MemorySource(
            {
                "Documentation/rejected.md": (
                    "# Rejected\n\nvalid\n\n## Too large\n\none two three"
                ),
                "Documentation/valid.md": "# Valid\n\none two",
            }
        )
    )

    assert set(index.documents_by_source) == {"Documentation/valid.md"}
    assert all(
        section.source != "Documentation/rejected.md"
        for section in index.sections.values()
    )
    assert index.index_diagnostics[-1].reason == "section_token_limit"


def test_index_diagnostics_are_bounded_and_report_truncation(settings):
    bounded = replace(
        settings,
        allowed_statuses=(),
        allowed_types=(),
        limits=replace(settings.limits, max_file_bytes=16),
    )
    files = {
        f"Documentation/oversized-{index:02d}.md": "x" * 17
        for index in range(25)
    }
    index = DocumentationIndex(bounded)
    index.rebuild(MemorySource(files))

    info = index.scope_info()["index_diagnostics"]
    assert info["count"] == 25
    assert info["truncated"] is True
    assert len(info["entries"]) == 20


def test_index_build_deadline_fails_available_with_empty_index(settings):
    now = [0.0]

    class SlowSource:
        def iter_markdown_files(self, *, deadline=None):
            yield "Documentation/a.md"

        def read_file(self, path, *, deadline=None):
            now[0] = 2.0
            return "# A\n\none"

    bounded = replace(
        settings,
        allowed_statuses=(),
        allowed_types=(),
        limits=replace(settings.limits, max_index_build_seconds=1.0),
    )
    index = DocumentationIndex(bounded, clock=lambda: now[0])
    index.rebuild(SlowSource())

    assert index.documents == {}
    assert index.sections == {}
    assert index.index_diagnostic_count == 1
    assert index.index_diagnostics[0].reason == "index_build_time_limit"
