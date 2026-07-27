from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable, Iterator
from time import monotonic, sleep
from typing import Any
from urllib.parse import quote

import requests
from requests.exceptions import (
    ChunkedEncodingError,
    ContentDecodingError,
    SSLError,
)

from .config import Settings
from .security import is_excluded, normalize_vault_path, path_is_within, require_allowed_path


class SourceError(RuntimeError):
    """Raised when the configured documentation source cannot be read safely."""


class SourceLimitError(SourceError):
    """Raised when a source response or traversal exceeds a configured bound."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason.replace("_", " "))


class SourceDocumentError(SourceError):
    """Raised when one document is malformed and can be safely quarantined."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason.replace("_", " "))


class ObsidianSource:
    def __init__(
        self,
        settings: Settings,
        session: requests.Session | None = None,
        *,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ):
        self.settings = settings
        self.session = session or requests.Session()
        self.clock = clock
        self.sleeper = sleeper
        self.base_url = settings.obsidian.base_url.rstrip("/")
        self.verify = str(settings.obsidian.ca_certificate)
        self.timeout = (
            settings.obsidian.connect_timeout_seconds,
            settings.obsidian.read_timeout_seconds,
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.obsidian.api_key}"}

    def _check_deadline(self, deadline: float | None) -> None:
        if deadline is not None and self.clock() >= deadline:
            raise SourceLimitError("index_build_time_limit")

    def _request_timeout(self, deadline: float | None) -> tuple[float, float]:
        if deadline is None:
            return self.timeout
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise SourceLimitError("index_build_time_limit")
        return (
            min(self.timeout[0], remaining),
            min(self.timeout[1], remaining),
        )

    def _read_bytes_once(
        self,
        url: str,
        *,
        maximum: int,
        limit_reason: str,
        deadline: float | None = None,
    ) -> bytes:
        self._check_deadline(deadline)
        response = self.session.get(
            url,
            headers=self._headers(),
            verify=self.verify,
            timeout=self._request_timeout(deadline),
            stream=True,
        )
        try:
            self._check_deadline(deadline)
            response.raise_for_status()
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_length = int(content_length)
                except (TypeError, ValueError):
                    declared_length = -1
                if declared_length > maximum:
                    raise SourceLimitError(limit_reason)

            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=65_536):
                self._check_deadline(deadline)
                if not chunk:
                    continue
                total += len(chunk)
                if total > maximum:
                    raise SourceLimitError(limit_reason)
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            response.close()

    @staticmethod
    def _is_transient_request_error(exc: requests.RequestException) -> bool:
        if isinstance(exc, SSLError):
            return False
        if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
            return True
        if isinstance(exc, requests.HTTPError):
            status = getattr(exc.response, "status_code", None)
            return isinstance(status, int) and (
                status in (408, 425, 429) or 500 <= status <= 599
            )
        return isinstance(
            exc,
            (ChunkedEncodingError, ContentDecodingError),
        )

    def _wait_before_retry(self, failed_attempt: int, deadline: float | None) -> None:
        delay = min(
            self.settings.obsidian.retry_backoff_seconds * (2**failed_attempt),
            5.0,
        )
        if deadline is not None and self.clock() + delay >= deadline:
            raise SourceLimitError("index_build_time_limit")
        if delay:
            self.sleeper(delay)

    def _read_bytes(
        self,
        url: str,
        *,
        maximum: int,
        limit_reason: str,
        deadline: float | None = None,
    ) -> bytes:
        attempts = self.settings.obsidian.request_retry_attempts
        for attempt in range(attempts):
            try:
                return self._read_bytes_once(
                    url,
                    maximum=maximum,
                    limit_reason=limit_reason,
                    deadline=deadline,
                )
            except SourceLimitError:
                raise
            except requests.RequestException as exc:
                if deadline is not None and self.clock() >= deadline:
                    raise SourceLimitError("index_build_time_limit") from exc
                if (
                    not self._is_transient_request_error(exc)
                    or attempt + 1 >= attempts
                ):
                    raise SourceError(
                        f"Obsidian read request failed: {exc.__class__.__name__}"
                    ) from exc
                self._wait_before_retry(attempt, deadline)
        raise AssertionError("request retry loop exited unexpectedly")

    def _vault_url(self, path: str, *, directory: bool = False) -> str:
        allowed = require_allowed_path(path, self.settings.allowed_directories)
        encoded = quote(allowed, safe="/")
        suffix = "/" if directory else ""
        return f"{self.base_url}/vault/{encoded}{suffix}"

    def list_directory(self, path: str, *, deadline: float | None = None) -> list[str]:
        content = self._read_bytes(
            self._vault_url(path, directory=True),
            maximum=self.settings.limits.max_directory_response_bytes,
            limit_reason="directory_response_too_large",
            deadline=deadline,
        )
        try:
            payload: Any = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise SourceError("Obsidian directory response is not valid JSON") from exc
        files = payload.get("files") if isinstance(payload, dict) else None
        if not isinstance(files, list) or any(not isinstance(item, str) for item in files):
            raise SourceError("Obsidian directory response has an invalid files list")
        if len(files) > self.settings.limits.max_directory_entries:
            raise SourceLimitError("directory_entry_limit")
        return files

    def read_file(self, path: str, *, deadline: float | None = None) -> str:
        allowed = require_allowed_path(path, self.settings.allowed_directories)
        if is_excluded(allowed, self.settings.excluded_directories):
            raise SourceError("Path is excluded by documentation policy")
        content = self._read_bytes(
            self._vault_url(allowed),
            maximum=self.settings.limits.max_file_bytes,
            limit_reason="file_too_large",
            deadline=deadline,
        )
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SourceDocumentError("invalid_utf8") from exc

    def iter_markdown_files(self, *, deadline: float | None = None) -> Iterator[str]:
        queue: deque[str] = deque()
        scheduled: set[str] = set()
        visited: set[str] = set()
        emitted: set[str] = set()

        for configured_directory in self.settings.allowed_directories:
            directory = normalize_vault_path(configured_directory)
            if directory in scheduled or is_excluded(
                directory, self.settings.excluded_directories
            ):
                continue
            if len(scheduled) >= self.settings.limits.max_source_directories:
                raise SourceLimitError("source_directory_limit")
            scheduled.add(directory)
            queue.append(directory)

        while queue:
            self._check_deadline(deadline)
            directory = normalize_vault_path(queue.popleft())
            if directory in visited or is_excluded(directory, self.settings.excluded_directories):
                continue
            visited.add(directory)

            for entry in self.list_directory(directory, deadline=deadline):
                self._check_deadline(deadline)
                raw_entry = entry.strip()
                is_directory = raw_entry.endswith("/")
                entry_path = normalize_vault_path(raw_entry.rstrip("/"))
                if path_is_within(entry_path, self.settings.allowed_directories):
                    candidate = entry_path
                else:
                    candidate = normalize_vault_path(f"{directory}/{entry_path}")
                candidate = require_allowed_path(candidate, self.settings.allowed_directories)

                if is_excluded(candidate, self.settings.excluded_directories):
                    continue
                if is_directory:
                    if candidate in scheduled:
                        continue
                    if len(scheduled) >= self.settings.limits.max_source_directories:
                        raise SourceLimitError("source_directory_limit")
                    scheduled.add(candidate)
                    queue.append(candidate)
                elif candidate.lower().endswith(".md") and candidate not in emitted:
                    if len(emitted) >= self.settings.limits.max_source_files:
                        raise SourceLimitError("source_file_limit")
                    emitted.add(candidate)
                    yield candidate
