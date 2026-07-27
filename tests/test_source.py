from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
import requests
from requests.exceptions import SSLError

from documentation_mcp.security import SecurityError
from documentation_mcp.source import (
    ObsidianSource,
    SourceDocumentError,
    SourceError,
    SourceLimitError,
)


def _response(*, json_value=None, text="", content_length=None, chunks=None):
    response = MagicMock()
    content = (
        json.dumps(json_value).encode("utf-8")
        if json_value is not None
        else text.encode("utf-8")
    )
    response.headers = {}
    if content_length is not None:
        response.headers["Content-Length"] = str(content_length)
    response.iter_content.return_value = chunks if chunks is not None else [content]
    response.raise_for_status.return_value = None
    return response


def test_read_file_uses_get_tls_ca_and_timeout(settings):
    session = MagicMock()
    session.get.return_value = _response(text="# Title")
    source = ObsidianSource(settings, session=session)

    assert source.read_file("Documentation/a.md") == "# Title"
    session.get.assert_called_once()
    call = session.get.call_args
    assert call.args[0].endswith("/vault/Documentation/a.md")
    assert call.kwargs["verify"] == str(settings.obsidian.ca_certificate)
    assert call.kwargs["headers"]["Authorization"] == "Bearer synthetic-key"
    assert call.kwargs["timeout"] == (3.0, 10.0)
    assert call.kwargs["stream"] is True


def test_transient_request_failure_retries_with_bounded_backoff(settings):
    retrying = replace(
        settings,
        obsidian=replace(
            settings.obsidian,
            request_retry_attempts=3,
            retry_backoff_seconds=0.25,
        ),
    )
    session = MagicMock()
    session.get.side_effect = [
        requests.Timeout("temporary"),
        _response(text="# Title"),
    ]
    delays: list[float] = []
    source = ObsidianSource(retrying, session=session, sleeper=delays.append)

    assert source.read_file("Documentation/a.md") == "# Title"
    assert session.get.call_count == 2
    assert delays == [0.25]


def test_transient_request_retries_are_bounded(settings):
    retrying = replace(
        settings,
        obsidian=replace(
            settings.obsidian,
            request_retry_attempts=3,
            retry_backoff_seconds=0.25,
        ),
    )
    session = MagicMock()
    session.get.side_effect = requests.ConnectionError("offline")
    delays: list[float] = []
    source = ObsidianSource(retrying, session=session, sleeper=delays.append)

    with pytest.raises(SourceError, match="ConnectionError"):
        source.read_file("Documentation/a.md")

    assert session.get.call_count == 3
    assert delays == [0.25, 0.5]


def test_non_transient_http_error_is_not_retried(settings):
    session = MagicMock()
    response = _response()
    http_response = MagicMock(status_code=401)
    response.raise_for_status.side_effect = requests.HTTPError(
        "unauthorized",
        response=http_response,
    )
    session.get.return_value = response
    source = ObsidianSource(settings, session=session, sleeper=MagicMock())

    with pytest.raises(SourceError, match="HTTPError"):
        source.read_file("Documentation/a.md")

    session.get.assert_called_once()
    response.close.assert_called_once()


def test_transient_http_status_is_retried(settings):
    unavailable = _response()
    http_response = MagicMock(status_code=503)
    unavailable.raise_for_status.side_effect = requests.HTTPError(
        "unavailable",
        response=http_response,
    )
    session = MagicMock()
    session.get.side_effect = [unavailable, _response(text="# Recovered")]
    delays: list[float] = []
    source = ObsidianSource(settings, session=session, sleeper=delays.append)

    assert source.read_file("Documentation/a.md") == "# Recovered"
    assert session.get.call_count == 2
    assert delays == [0.25]
    unavailable.close.assert_called_once()


def test_tls_error_is_not_retried(settings):
    session = MagicMock()
    session.get.side_effect = SSLError("certificate rejected")
    source = ObsidianSource(settings, session=session, sleeper=MagicMock())

    with pytest.raises(SourceError, match="SSLError"):
        source.read_file("Documentation/a.md")

    session.get.assert_called_once()


def test_invalid_utf8_is_a_quarantinable_document_error(settings):
    session = MagicMock()
    session.get.return_value = _response(chunks=[b"\xff"])
    source = ObsidianSource(settings, session=session)

    with pytest.raises(SourceDocumentError, match="invalid utf8"):
        source.read_file("Documentation/a.md")


def test_read_file_rejects_declared_oversized_response(settings):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_file_bytes=5),
    )
    session = MagicMock()
    session.get.return_value = _response(text="small", content_length=6)
    source = ObsidianSource(bounded, session=session)

    with pytest.raises(SourceLimitError, match="file too large"):
        source.read_file("Documentation/a.md")

    session.get.return_value.iter_content.assert_not_called()
    session.get.return_value.close.assert_called_once()


def test_read_file_enforces_hard_streamed_byte_cutoff(settings):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_file_bytes=5),
    )
    session = MagicMock()
    session.get.return_value = _response(chunks=[b"1234", b"56"])
    source = ObsidianSource(bounded, session=session)

    with pytest.raises(SourceLimitError, match="file too large"):
        source.read_file("Documentation/a.md")

    session.get.return_value.close.assert_called_once()


def test_read_file_enforces_index_build_deadline_while_streaming(settings):
    now = [0.0]

    def chunks():
        yield b"first"
        now[0] = 2.0
        yield b"second"

    session = MagicMock()
    session.get.return_value = _response(chunks=chunks())
    source = ObsidianSource(settings, session=session, clock=lambda: now[0])

    with pytest.raises(SourceLimitError, match="index build time limit"):
        source.read_file("Documentation/a.md", deadline=1.0)

    session.get.return_value.close.assert_called_once()


def test_forbidden_path_is_rejected_before_request(settings):
    session = MagicMock()
    source = ObsidianSource(settings, session=session)
    with pytest.raises(SecurityError):
        source.read_file("Other/private.md")
    session.get.assert_not_called()


def test_excluded_path_is_not_read(settings):
    source = ObsidianSource(settings, session=MagicMock())
    with pytest.raises(SourceError, match="excluded"):
        source.read_file("Documentation/_meta/a.md")


def test_recursive_listing_returns_only_allowed_markdown(settings):
    session = MagicMock()
    session.get.side_effect = [
        _response(json_value={"files": ["a.md", "nested/", "image.png", "_meta/"]}),
        _response(json_value={"files": ["b.md"]}),
    ]
    source = ObsidianSource(settings, session=session)
    assert list(source.iter_markdown_files()) == [
        "Documentation/a.md",
        "Documentation/nested/b.md",
    ]
    assert session.get.call_count == 2


def test_scoped_exclusion_skips_only_the_exact_subtree(settings):
    scoped = replace(
        settings,
        excluded_directories=("Documentation/private",),
    )
    session = MagicMock()
    session.get.side_effect = [
        _response(
            json_value={
                "files": ["public.md", "private/", "private-notes/"],
            }
        ),
        _response(json_value={"files": ["visible.md"]}),
    ]
    source = ObsidianSource(scoped, session=session)

    assert list(source.iter_markdown_files()) == [
        "Documentation/public.md",
        "Documentation/private-notes/visible.md",
    ]
    assert session.get.call_count == 2


def test_invalid_directory_payload_fails_safely(settings):
    session = MagicMock()
    session.get.return_value = _response(json_value={"files": "not-a-list"})
    source = ObsidianSource(settings, session=session)
    with pytest.raises(SourceError, match="invalid files list"):
        list(source.iter_markdown_files())


def test_directory_entry_count_is_bounded(settings):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_directory_entries=1),
    )
    session = MagicMock()
    session.get.return_value = _response(json_value={"files": ["a.md", "b.md"]})
    source = ObsidianSource(bounded, session=session)

    with pytest.raises(SourceLimitError, match="directory entry limit"):
        list(source.iter_markdown_files())


def test_directory_response_bytes_are_bounded_before_json_parsing(settings):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_directory_response_bytes=5),
    )
    session = MagicMock()
    session.get.return_value = _response(chunks=[b'{"fil', b'es":[]}'])
    source = ObsidianSource(bounded, session=session)

    with pytest.raises(SourceLimitError, match="directory response too large"):
        list(source.iter_markdown_files())

    session.get.return_value.close.assert_called_once()


def test_directory_traversal_count_is_bounded(settings):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_source_directories=1),
    )
    session = MagicMock()
    session.get.return_value = _response(json_value={"files": ["nested/"]})
    source = ObsidianSource(bounded, session=session)

    with pytest.raises(SourceLimitError, match="source directory limit"):
        list(source.iter_markdown_files())
    assert session.get.call_count == 1


def test_directory_queue_is_bounded_when_entries_are_discovered(settings):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_source_directories=2),
    )
    session = MagicMock()
    session.get.return_value = _response(
        json_value={"files": ["first/", "second/", "third/"]}
    )
    source = ObsidianSource(bounded, session=session)

    with pytest.raises(SourceLimitError, match="source directory limit"):
        list(source.iter_markdown_files())

    assert session.get.call_count == 1


def test_duplicate_directories_are_not_added_to_the_queue(settings):
    session = MagicMock()
    session.get.side_effect = [
        _response(json_value={"files": ["nested/", "nested/"]}),
        _response(json_value={"files": ["a.md"]}),
    ]
    source = ObsidianSource(settings, session=session)

    assert list(source.iter_markdown_files()) == ["Documentation/nested/a.md"]
    assert session.get.call_count == 2


def test_source_file_count_is_bounded_during_discovery(settings):
    bounded = replace(
        settings,
        limits=replace(settings.limits, max_source_files=2),
    )
    session = MagicMock()
    session.get.return_value = _response(
        json_value={"files": ["a.md", "b.md", "c.md"]}
    )
    source = ObsidianSource(bounded, session=session)

    iterator = source.iter_markdown_files()
    assert next(iterator) == "Documentation/a.md"
    assert next(iterator) == "Documentation/b.md"
    with pytest.raises(SourceLimitError, match="source file limit"):
        next(iterator)
