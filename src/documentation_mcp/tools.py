from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock, RLock
from time import perf_counter
from typing import Any

from mcp.types import Tool

from .index import (
    MAX_REPORTED_INDEX_DIAGNOSTICS,
    DocumentationIndex,
    DocumentationSource,
    IndexDiagnostic,
)
from .security import SecurityError
from .serialization import serialized_character_count
from .source import SourceError, SourceLimitError


logger = logging.getLogger("documentation-mcp")
TOOL_NAMES = {
    "scope_info",
    "refresh_index",
    "search_docs",
    "get_document_metadata",
    "get_document_section",
    "get_related_documents",
}


def tool_definitions() -> list[Tool]:
    return [
        Tool(
            name="scope_info",
            description="Report the enforced read-only scope, retrieval limits, and index snapshot.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="refresh_index",
            description=(
                "Read the configured documentation source and atomically replace "
                "the index only when the bounded rebuild succeeds."
            ),
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="search_docs",
            description="Search ranked documentation sections under the enforced context budget.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "filters": {
                        "type": "object",
                        "properties": {
                            "status": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                            "type": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                            "area": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                            "tags": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                        },
                        "additionalProperties": False,
                    },
                    "top_k": {"type": "integer", "minimum": 1},
                    "max_total_characters": {"type": "integer", "minimum": 1},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="get_document_metadata",
            description="Return allowlisted metadata fields without returning the complete document body.",
            inputSchema={
                "type": "object",
                "properties": {"document_id": {"type": "string", "minLength": 1}},
                "required": ["document_id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="get_document_section",
            description="Return one bounded section by chunk ID or document and heading identity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string", "minLength": 1},
                    "document_id": {"type": "string", "minLength": 1},
                    "heading_path": {"type": "string", "minLength": 1},
                    "max_characters": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="get_related_documents",
            description="Return metadata for directly related documents, bounded by server policy.",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1},
                },
                "required": ["document_id"],
                "additionalProperties": False,
            },
        ),
    ]


class ToolService:
    def __init__(
        self,
        index: DocumentationIndex,
        source: DocumentationSource,
    ):
        self.index = index
        self.source = source
        self._refresh_lock = Lock()
        self._state_lock = RLock()
        self._has_successful_refresh = False
        self._refresh_status = "never"
        self._last_attempt_at: str | None = None
        self._last_success_at: str | None = None
        self._last_duration_ms: float | None = None
        self._last_known_good_preserved = False
        self._last_refresh_changed = False
        self._last_skipped_documents = 0
        self._last_error_count = 0
        self._last_errors: list[IndexDiagnostic] = []

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _failure_reason(exc: Exception) -> str:
        if isinstance(exc, SourceLimitError):
            return exc.reason
        if isinstance(exc, SourceError):
            return "source_error"
        if isinstance(exc, SecurityError):
            return "source_security_error"
        if isinstance(exc, (TypeError, ValueError, UnicodeError)):
            return "invalid_source_data"
        return "index_build_error"

    def _set_refresh_diagnostics(
        self,
        candidate: DocumentationIndex,
        fatal_reason: str | None,
    ) -> None:
        errors = list(candidate.index_diagnostics)
        error_count = candidate.index_diagnostic_count
        if (
            fatal_reason is not None
            and not any(item.reason == fatal_reason for item in errors)
        ):
            error_count += 1
            if len(errors) < MAX_REPORTED_INDEX_DIAGNOSTICS:
                errors.append(IndexDiagnostic("<refresh>", fatal_reason))
        self._last_skipped_documents = candidate.skipped_document_count
        self._last_error_count = error_count
        self._last_errors = errors

    def _refresh_info_unlocked(self) -> dict[str, Any]:
        return {
            "status": self._refresh_status,
            "last_attempt_at": self._last_attempt_at,
            "last_success_at": self._last_success_at,
            "duration_ms": self._last_duration_ms,
            "changed": self._last_refresh_changed,
            "last_known_good_preserved": self._last_known_good_preserved,
            "skipped_documents": self._last_skipped_documents,
            "indexing_errors": {
                "count": self._last_error_count,
                "truncated": self._last_error_count > len(self._last_errors),
                "entries": [
                    {"source": item.source, "reason": item.reason}
                    for item in self._last_errors
                ],
            },
        }

    def refresh_info(self) -> dict[str, Any]:
        with self._state_lock:
            return self._refresh_info_unlocked()

    def refresh_index(self) -> dict[str, Any]:
        with self._refresh_lock:
            started = perf_counter()
            with self._state_lock:
                settings = self.index.settings
                self._refresh_status = "running"
                self._last_attempt_at = self._timestamp()
                self._last_duration_ms = None
                self._last_refresh_changed = False
                self._last_known_good_preserved = False
            candidate = DocumentationIndex(settings)
            fatal_reason: str | None = None
            try:
                candidate.rebuild(self.source)
                if not candidate.build_completed:
                    fatal_reason = (
                        candidate.index_diagnostics[-1].reason
                        if candidate.index_diagnostics
                        else "index_build_incomplete"
                    )
            except Exception as exc:
                fatal_reason = self._failure_reason(exc)
                logger.warning(
                    "index refresh status=failed error_type=%s reason=%s",
                    exc.__class__.__name__,
                    fatal_reason,
                )

            with self._state_lock:
                completed_at = self._timestamp()
                self._last_duration_ms = round((perf_counter() - started) * 1000, 3)
                self._set_refresh_diagnostics(candidate, fatal_reason)
                self._last_refresh_changed = False

                if fatal_reason is None:
                    previous_snapshot = self.index.snapshot
                    self.index = candidate
                    self._has_successful_refresh = True
                    self._refresh_status = (
                        "success_with_warnings"
                        if self._last_error_count
                        else "success"
                    )
                    self._last_success_at = completed_at
                    self._last_known_good_preserved = False
                    self._last_refresh_changed = candidate.snapshot != previous_snapshot
                    logger.info(
                        "index refresh status=%s documents=%d sections=%d skipped=%d",
                        self._refresh_status,
                        len(candidate.documents),
                        len(candidate.sections),
                        candidate.skipped_document_count,
                    )
                else:
                    self._refresh_status = "failed"
                    self._last_known_good_preserved = self._has_successful_refresh

                return {
                    "index_snapshot": self.index.snapshot,
                    "refresh": self._refresh_info_unlocked(),
                }

    @staticmethod
    def _required_string(arguments: dict[str, Any], name: str) -> str:
        value = arguments.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    def dispatch(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in TOOL_NAMES:
            raise ValueError(f"Unknown tool: {name}")
        if name == "refresh_index":
            if arguments:
                raise ValueError("refresh_index does not accept arguments")
            return self.refresh_index()
        with self._state_lock:
            index = self.index
        if name == "scope_info":
            info = index.scope_info()
            info["refresh"] = self.refresh_info()
            return info
        if name == "search_docs":
            requested_characters = arguments.get(
                "max_total_characters",
                index.settings.limits.max_total_characters,
            )
            if (
                not isinstance(requested_characters, int)
                or isinstance(requested_characters, bool)
                or requested_characters < 1
            ):
                raise ValueError("max_total_characters must be a positive integer")
            response_budget = min(
                requested_characters,
                index.settings.limits.max_total_characters,
            )
            requested_top_k = arguments.get(
                "top_k",
                index.settings.limits.top_k,
            )
            if (
                not isinstance(requested_top_k, int)
                or isinstance(requested_top_k, bool)
                or requested_top_k < 1
            ):
                raise ValueError("top_k must be a positive integer")
            maximum_result_count = min(
                requested_top_k,
                index.settings.limits.top_k,
                index.settings.limits.max_sections,
            )
            empty_response = {
                "results": [],
                "retrieved_chunk_count": maximum_result_count,
                "index_snapshot": index.snapshot,
            }
            envelope_characters = (
                serialized_character_count(empty_response)
                - serialized_character_count([])
            )
            result_budget = response_budget - envelope_characters
            if result_budget < serialized_character_count([]):
                raise ValueError(
                    "max_total_characters is too small for the search response envelope"
                )
            results = index.search(
                self._required_string(arguments, "query"),
                filters=arguments.get("filters"),
                top_k=arguments.get("top_k"),
                max_total_characters=result_budget,
            )
            response = {
                "results": results,
                "retrieved_chunk_count": len(results),
                "index_snapshot": index.snapshot,
            }
            if serialized_character_count(response) > response_budget:
                raise RuntimeError("search response exceeded its serialized character budget")
            return response
        if name == "get_document_metadata":
            return index.document_metadata(self._required_string(arguments, "document_id"))
        if name == "get_document_section":
            return index.document_section(
                chunk_id=arguments.get("chunk_id"),
                document_id=arguments.get("document_id"),
                heading_path=arguments.get("heading_path"),
                max_characters=arguments.get("max_characters"),
            )
        return index.related_documents(
            self._required_string(arguments, "document_id"),
            arguments.get("limit"),
        )
