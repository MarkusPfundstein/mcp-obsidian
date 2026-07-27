from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from threading import Event
from typing import Any

import pytest

from documentation_mcp import server
from documentation_mcp.source import SourceDocumentError, SourceError
from documentation_mcp.tools import TOOL_NAMES, tool_definitions

from .conftest import MemorySource


def _run(awaitable):
    return asyncio.run(awaitable)


def test_exact_read_only_tool_surface():
    names = {tool.name for tool in tool_definitions()}
    assert names == TOOL_NAMES
    assert all(term not in name for name in names for term in ("append", "patch", "put", "delete"))


def test_configure_and_call_search(settings, documents):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_total_characters=1_000),
    )
    server.configure(bounded, MemorySource(documents))
    response = _run(server.call_tool("search_docs", {"query": "retry default"}))
    payload = json.loads(response[0].text)
    assert payload["retrieved_chunk_count"] >= 1
    assert payload["index_snapshot"]


def test_search_budget_applies_to_serialized_json_with_escaping_and_unicode(settings):
    bounded = replace(
        settings,
        allowed_statuses=(),
        allowed_types=(),
        limits=replace(settings.limits, max_total_characters=12_000),
    )
    adversarial_text = 'retry "' + ('\\\t\x01é漢🙂"' * 4_000)
    documents = {
        "Documentation/escaping.md": (
            "# Escaping\n\n"
            "## Retry\n\n"
            f"{adversarial_text}"
        )
    }
    server.configure(bounded, MemorySource(documents))

    response = _run(
        server.call_tool(
            "search_docs",
            {"query": "retry", "max_total_characters": 12_000},
        )
    )
    text = response[0].text
    payload = json.loads(text)

    assert payload["results"]
    assert len(text) <= 12_000
    assert '\\"' in text
    assert "\\\\" in text
    assert "\\t" in text
    assert "\\u0001" in text
    assert "é漢🙂" in text
    assert '\t' in payload["results"][0]["excerpt"]
    assert "\x01" in payload["results"][0]["excerpt"]


def test_search_rejects_budget_smaller_than_response_envelope(settings, documents):
    server.configure(settings, MemorySource(documents))

    with pytest.raises(RuntimeError, match="too small for the search response envelope"):
        _run(
            server.call_tool(
                "search_docs",
                {"query": "retry", "max_total_characters": 1},
            )
        )


def test_scope_reports_read_only_access(settings, documents):
    server.configure(settings, MemorySource(documents))
    response = _run(server.call_tool("scope_info", {}))
    payload = json.loads(response[0].text)
    assert payload["access"] == "read-only"
    assert payload["allowed_directories"] == ["Documentation"]
    assert payload["refresh"]["status"] == "success"
    assert payload["refresh"]["last_success_at"]


def test_failed_refresh_atomically_preserves_last_known_good_index(settings):
    class RefreshableSource(MemorySource):
        fail = False

        def iter_markdown_files(self, *, deadline=None):
            if self.fail:
                raise SourceError("temporary source failure")
            return super().iter_markdown_files(deadline=deadline)

    bounded = replace(settings, allowed_statuses=(), allowed_types=())
    source = RefreshableSource(
        {"Documentation/old.md": "# Old\n\nstable searchable content"}
    )
    service = server.configure(bounded, source)
    original_index = service.index
    original_snapshot = original_index.snapshot

    source.files = {"Documentation/new.md": "# New\n\nfresh replacement content"}
    source.fail = True
    failed = _run(server.call_tool("refresh_index", {}))
    failed_payload = json.loads(failed[0].text)

    assert failed_payload["refresh"]["status"] == "failed"
    assert failed_payload["refresh"]["last_known_good_preserved"] is True
    assert failed_payload["refresh"]["indexing_errors"]["entries"] == [
        {"reason": "source_error", "source": "<refresh>"}
    ]
    assert service.index is original_index
    assert service.index.snapshot == original_snapshot

    source.fail = False
    succeeded = _run(server.call_tool("refresh_index", {}))
    succeeded_payload = json.loads(succeeded[0].text)

    assert succeeded_payload["refresh"]["status"] == "success"
    assert succeeded_payload["refresh"]["changed"] is True
    assert succeeded_payload["refresh"]["last_known_good_preserved"] is False
    assert service.index is not original_index
    assert set(service.index.documents_by_source) == {"Documentation/new.md"}


def test_incomplete_refresh_preserves_last_known_good_index(settings):
    bounded = replace(
        settings,
        allowed_statuses=(),
        allowed_types=(),
        limits=replace(settings.limits, max_source_files=1),
    )
    source = MemorySource(
        {"Documentation/original.md": "# Original\n\nstable searchable content"}
    )
    service = server.configure(bounded, source)
    original_index = service.index
    original_snapshot = original_index.snapshot

    source.files = {
        "Documentation/a-partial.md": "# Partial\n\nincomplete replacement",
        "Documentation/b-unseen.md": "# Unseen\n\nmust not disappear",
    }
    failed = _run(server.call_tool("refresh_index", {}))
    payload = json.loads(failed[0].text)

    assert payload["refresh"]["status"] == "failed"
    assert payload["refresh"]["last_known_good_preserved"] is True
    assert payload["refresh"]["indexing_errors"]["entries"][-1]["reason"] == (
        "source_file_limit"
    )
    assert service.index is original_index
    assert service.index.snapshot == original_snapshot


def test_failed_refresh_preserves_diagnostics_recorded_before_fatal_error(settings):
    class PartiallyFailingSource(MemorySource):
        def read_file(self, path, *, deadline=None):
            if path.endswith("a-malformed.md"):
                raise SourceDocumentError("invalid_utf8")
            raise SourceError("source became unavailable")

    source = PartiallyFailingSource(
        {
            "Documentation/a-malformed.md": "ignored",
            "Documentation/b-fatal.md": "ignored",
        }
    )
    service = server.configure(settings, source)
    payload = service.refresh_info()

    assert payload["status"] == "failed"
    assert payload["skipped_documents"] == 1
    assert payload["indexing_errors"]["entries"] == [
        {"source": "Documentation/a-malformed.md", "reason": "invalid_utf8"},
        {"source": "<refresh>", "reason": "source_error"},
    ]


def test_search_uses_active_index_while_refresh_builds_in_worker(settings):
    started = Event()
    release = Event()

    class BlockingSource(MemorySource):
        block = False

        def read_file(self, path, *, deadline=None):
            if self.block:
                started.set()
                if not release.wait(timeout=5):
                    raise SourceError("test refresh was not released")
            return super().read_file(path, deadline=deadline)

    bounded = replace(settings, allowed_statuses=(), allowed_types=())
    source = BlockingSource(
        {"Documentation/old.md": "# Old\n\nstable searchable content"}
    )
    server.configure(bounded, source)
    source.files = {"Documentation/new.md": "# New\n\nfresh replacement content"}
    source.block = True

    async def exercise_concurrent_refresh():
        async def run_refresh() -> None:
            await server.call_tool("refresh_index", {})

        refresh_task = asyncio.create_task(run_refresh())
        try:
            assert await asyncio.to_thread(started.wait, 1)
            scope_response: Any = await asyncio.wait_for(
                server.call_tool("scope_info", {}),
                timeout=2,
            )
            search_response: Any = await asyncio.wait_for(
                server.call_tool("search_docs", {"query": "stable"}),
                timeout=2,
            )
            scope_payload = json.loads(scope_response[0].text)
            search_payload = json.loads(search_response[0].text)
            assert scope_payload["refresh"]["status"] == "running"
            assert search_payload["results"][0]["source"] == "Documentation/old.md"
        finally:
            release.set()
        await refresh_task

    _run(exercise_concurrent_refresh())


def test_initial_source_failure_starts_with_diagnosed_empty_index(settings):
    class UnavailableSource(MemorySource):
        def iter_markdown_files(self, *, deadline=None):
            raise SourceError("source unavailable")

    service = server.configure(settings, UnavailableSource({}))
    response = _run(server.call_tool("scope_info", {}))
    payload = json.loads(response[0].text)

    assert service.index.documents == {}
    assert payload["refresh"]["status"] == "failed"
    assert payload["refresh"]["last_success_at"] is None
    assert payload["refresh"]["last_known_good_preserved"] is False
    assert payload["refresh"]["indexing_errors"]["count"] == 1


def test_refresh_reports_skipped_documents_and_indexing_errors(settings):
    bounded = replace(settings, allowed_statuses=(), allowed_types=())
    duplicate_documents = {
        "Documentation/a.md": (
            "---\ndocument_id: duplicate\n---\n# First\n\none"
        ),
        "Documentation/b.md": (
            "---\ndocument_id: duplicate\n---\n# Second\n\ntwo"
        ),
    }
    server.configure(bounded, MemorySource(duplicate_documents))
    response = _run(server.call_tool("scope_info", {}))
    payload = json.loads(response[0].text)

    assert payload["refresh"]["status"] == "success_with_warnings"
    assert payload["refresh"]["duration_ms"] >= 0
    assert payload["refresh"]["skipped_documents"] == 1
    assert payload["refresh"]["indexing_errors"]["count"] == 1
    assert payload["index_diagnostics"]["skipped_documents"] == 1


@pytest.mark.parametrize("tool_name", ("get_document_metadata", "get_related_documents"))
def test_metadata_tools_never_serialize_private_frontmatter(tool_name, settings, documents):
    server.configure(settings, MemorySource(documents))
    response = _run(server.call_tool(tool_name, {"document_id": "preferences"}))
    assert "must-not-leak" not in response[0].text
    assert "frontmatter" not in response[0].text


def test_invalid_arguments_and_unknown_tools_are_rejected(settings, documents):
    server.configure(settings, MemorySource(documents))
    with pytest.raises(RuntimeError, match="object"):
        _run(server.call_tool("scope_info", None))
    with pytest.raises(RuntimeError, match="Unknown tool"):
        _run(server.call_tool("missing", {}))
