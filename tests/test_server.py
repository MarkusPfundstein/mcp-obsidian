from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from threading import Event, Thread
from typing import Any

import pytest

from documentation_mcp import server
from documentation_mcp.source import SourceDocumentError, SourceError
from documentation_mcp.tools import TOOL_NAMES, tool_definitions

from .conftest import MemorySource


def _run(awaitable):
    return asyncio.run(awaitable)


def _configure(settings: Any, source: Any):
    service = server.configure(settings, source)
    service.refresh_index()
    return service


def test_exact_read_only_tool_surface():
    names = {tool.name for tool in tool_definitions()}
    assert names == TOOL_NAMES
    assert all(term not in name for name in names for term in ("append", "patch", "put", "delete"))


def test_configure_exposes_scope_but_rejects_retrieval_without_reading_the_source(
    settings,
    documents,
):
    class UnreadSource(MemorySource):
        def iter_markdown_files(self, *, deadline=None):
            raise AssertionError("configure must not read the documentation source")

    service = server.configure(settings, UnreadSource(documents))

    scope_response = _run(server.call_tool("scope_info", {}))
    scope = json.loads(scope_response[0].text)

    assert service.index.documents == {}
    assert scope["refresh"]["status"] == "never"
    assert scope["index_snapshot"] == service.index.snapshot
    with pytest.raises(RuntimeError, match="documentation index is not ready"):
        _run(server.call_tool("search_docs", {"query": "retry default"}))


def test_run_starts_stdio_before_initial_refresh_worker(
    monkeypatch,
    settings,
    documents,
):
    import mcp.server.stdio as mcp_stdio

    transport_started = Event()
    refresh_started = Event()
    release_refresh = Event()

    class BlockingInitialSource(MemorySource):
        def iter_markdown_files(self, *, deadline=None):
            assert transport_started.is_set()
            refresh_started.set()
            if not release_refresh.wait(timeout=5):
                raise SourceError("test initial refresh was not released")
            return super().iter_markdown_files(deadline=deadline)

    service = server.configure(settings, BlockingInitialSource(documents))

    @asynccontextmanager
    async def fake_stdio_server():
        transport_started.set()
        yield object(), object()

    async def fake_app_run(read_stream, write_stream, initialization_options):
        del read_stream, write_stream, initialization_options
        try:
            assert await asyncio.to_thread(refresh_started.wait, 1)
            scope_response: Any = await server.call_tool("scope_info", {})
            scope = json.loads(scope_response[0].text)
            assert scope["refresh"]["status"] == "running"
            assert scope["index_snapshot"] == service.index.snapshot
            with pytest.raises(
                RuntimeError,
                match="documentation index is not ready",
            ):
                await server.call_tool(
                    "search_docs",
                    {"query": "retry default"},
                )
        finally:
            release_refresh.set()

    monkeypatch.setattr(mcp_stdio, "stdio_server", fake_stdio_server)
    monkeypatch.setattr(server.app, "run", fake_app_run)

    _run(server.run())

    assert service.refresh_info()["status"] == "success"
    assert service.index.documents


def test_configure_and_call_search(settings, documents):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_total_characters=1_000),
    )
    _configure(bounded, MemorySource(documents))
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
    _configure(bounded, MemorySource(documents))

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


def test_role_aware_search_reserves_serialized_space_for_complementary_evidence(
    settings,
    routing_documents,
):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_total_characters=4_200),
    )
    _configure(bounded, MemorySource(routing_documents))

    response = _run(
        server.call_tool(
            "search_docs",
            {"query": "generate item per region default behavior"},
        )
    )
    text = response[0].text
    payload = json.loads(text)
    headings = {result["heading_path"] for result in payload["results"]}

    assert len(text) <= 4_200
    assert "Preferences Configuration > Interface" in headings
    assert (
        "Runtime processing > Behavior > Changing generate item per region preference"
        in headings
    )


def test_search_rejects_budget_smaller_than_response_envelope(settings, documents):
    _configure(settings, MemorySource(documents))

    with pytest.raises(RuntimeError, match="too small for the search response envelope"):
        _run(
            server.call_tool(
                "search_docs",
                {"query": "retry", "max_total_characters": 1},
            )
        )


def test_scope_reports_read_only_access(settings, documents):
    _configure(settings, MemorySource(documents))
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
    service = _configure(bounded, source)
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
    service = _configure(bounded, source)
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
    service = _configure(settings, source)
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
    _configure(bounded, source)
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


def test_scope_info_cannot_mix_index_and_refresh_generations(
    monkeypatch,
    settings,
):
    bounded = replace(settings, allowed_statuses=(), allowed_types=())
    source = MemorySource(
        {"Documentation/old.md": "# Old\n\nstable searchable content"}
    )
    service = _configure(bounded, source)
    original_index = service.index
    original_snapshot = original_index.snapshot
    scope_started = Event()
    release_scope = Event()
    refresh_finished = Event()
    scope_result: dict[str, Any] = {}
    refresh_result: dict[str, Any] = {}
    original_scope_info = original_index.scope_info

    def blocking_scope_info() -> dict[str, Any]:
        payload = original_scope_info()
        scope_started.set()
        if not release_scope.wait(timeout=5):
            raise AssertionError("test scope_info was not released")
        return payload

    def read_scope() -> None:
        scope_result.update(service.dispatch("scope_info", {}))

    def run_refresh() -> None:
        try:
            refresh_result.update(service.refresh_index())
        finally:
            refresh_finished.set()

    monkeypatch.setattr(original_index, "scope_info", blocking_scope_info)
    scope_thread = Thread(target=read_scope)
    scope_thread.start()
    assert scope_started.wait(timeout=1)

    source.files = {"Documentation/new.md": "# New\n\nfresh replacement content"}
    refresh_thread = Thread(target=run_refresh)
    refresh_thread.start()
    try:
        assert not refresh_finished.wait(timeout=0.1)
    finally:
        release_scope.set()
    scope_thread.join(timeout=2)
    refresh_thread.join(timeout=2)

    assert not scope_thread.is_alive()
    assert not refresh_thread.is_alive()
    assert scope_result["index_snapshot"] == original_snapshot
    assert scope_result["refresh"]["status"] == "success"
    assert refresh_result["index_snapshot"] != original_snapshot


def test_initial_source_failure_starts_with_diagnosed_empty_index(settings):
    class UnavailableSource(MemorySource):
        def iter_markdown_files(self, *, deadline=None):
            raise SourceError("source unavailable")

    service = _configure(settings, UnavailableSource({}))
    response = _run(server.call_tool("scope_info", {}))
    payload = json.loads(response[0].text)

    assert service.index.documents == {}
    assert payload["refresh"]["status"] == "failed"
    assert payload["refresh"]["last_success_at"] is None
    assert payload["refresh"]["last_known_good_preserved"] is False
    assert payload["refresh"]["indexing_errors"]["count"] == 1
    with pytest.raises(RuntimeError, match="documentation index is not ready"):
        _run(server.call_tool("search_docs", {"query": "anything"}))


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
    _configure(bounded, MemorySource(duplicate_documents))
    response = _run(server.call_tool("scope_info", {}))
    payload = json.loads(response[0].text)

    assert payload["refresh"]["status"] == "success_with_warnings"
    assert payload["refresh"]["duration_ms"] >= 0
    assert payload["refresh"]["skipped_documents"] == 1
    assert payload["refresh"]["indexing_errors"]["count"] == 1
    assert payload["index_diagnostics"]["skipped_documents"] == 1


@pytest.mark.parametrize("tool_name", ("get_document_metadata", "get_related_documents"))
def test_metadata_tools_never_serialize_private_frontmatter(tool_name, settings, documents):
    _configure(settings, MemorySource(documents))
    response = _run(server.call_tool(tool_name, {"document_id": "preferences"}))
    assert "must-not-leak" not in response[0].text
    assert "frontmatter" not in response[0].text


def test_invalid_arguments_and_unknown_tools_are_rejected(settings, documents):
    _configure(settings, MemorySource(documents))
    with pytest.raises(RuntimeError, match="object"):
        _run(server.call_tool("scope_info", None))
    with pytest.raises(RuntimeError, match="Unknown tool"):
        _run(server.call_tool("missing", {}))
