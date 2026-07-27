from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from time import monotonic
from typing import Any, Protocol

from .config import Settings
from .markdown import DocumentRejected, content_digest, parse_document
from .models import Document, Section
from .security import is_excluded, require_allowed_path
from .serialization import serialized_character_count, serialized_string_prefix
from .source import SourceDocumentError, SourceLimitError


TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
TABLE_SEPARATOR_CELL_RE = re.compile(r":?-{3,}:?")
SUPPORTED_FILTERS = {"status", "type", "area", "tags"}
MAX_REPORTED_INDEX_DIAGNOSTICS = 20
MAX_DIAGNOSTIC_SOURCE_CHARACTERS = 240
RELATED_SCORE_FLOOR = 0.30
SUPPLEMENT_SCORE_FLOOR = 0.42
COMPLEMENT_EXCERPT_RESERVE = 800
GENERIC_SECTION_LEAVES = frozenset(
    {"overview", "summary", "related documentation"}
)
CANONICAL_CONTEXT_TERMS = frozenset(
    {
        "configuration",
        "configure",
        "default",
        "field",
        "option",
        "parameter",
        "preference",
        "property",
        "setting",
    }
)
SETTING_HEADER_TERMS = frozenset(
    {"field", "option", "parameter", "preference", "property", "setting"}
)
COMPLEMENTARY_ROLES: dict[str, tuple[str, ...]] = {
    "interface": (
        "behavior",
        "validation",
        "edge-case",
        "configuration",
        "reference",
    ),
    "default": (
        "behavior",
        "validation",
        "edge-case",
        "interface",
        "configuration",
        "reference",
    ),
    "configuration": (
        "behavior",
        "validation",
        "edge-case",
        "interface",
        "default",
        "reference",
    ),
    "reference": (
        "behavior",
        "validation",
        "edge-case",
        "interface",
        "default",
        "configuration",
    ),
    "behavior": ("interface", "default", "configuration", "reference", "validation"),
    "validation": ("configuration", "interface", "default", "behavior", "edge-case", "reference"),
    "edge-case": ("validation", "behavior", "configuration", "interface", "default"),
    "integration": ("interface", "behavior", "configuration", "reference", "validation"),
    "acceptance": ("validation", "behavior", "configuration", "interface"),
    "test-coverage": ("validation", "behavior", "configuration", "interface"),
}
logger = logging.getLogger("documentation-mcp")


class DocumentationSource(Protocol):
    def iter_markdown_files(self, *, deadline: float | None = None) -> Iterator[str]: ...
    def read_file(self, path: str, *, deadline: float | None = None) -> str: ...


@dataclass(frozen=True)
class RankedSection:
    section: Section
    document: Document
    score: float
    route: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class IndexDiagnostic:
    source: str
    reason: str


def _tokens(value: str) -> list[str]:
    normalized: list[str] = []
    for token in TOKEN_RE.findall(value.lower()):
        if len(token) > 4 and token.endswith("ies"):
            token = f"{token[:-3]}y"
        elif len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        normalized.append(token)
    return normalized


def _filter_values(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return set(value)
    raise ValueError("Metadata filters must be strings or arrays of strings")


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _has_canonical_default_evidence(section: Section) -> bool:
    if section.role == "default":
        return True
    lines = section.text.splitlines()
    for position, line in enumerate(lines[:-1]):
        if "|" not in line or "|" not in lines[position + 1]:
            continue
        headers = _table_cells(line)
        separators = _table_cells(lines[position + 1])
        if (
            len(headers) < 2
            or len(headers) != len(separators)
            or not all(TABLE_SEPARATOR_CELL_RE.fullmatch(cell) for cell in separators)
        ):
            continue
        header_tokens = [set(_tokens(header)) for header in headers]
        if any(tokens & SETTING_HEADER_TERMS for tokens in header_tokens) and any(
            "default" in tokens for tokens in header_tokens
        ):
            return True
    return False


class DocumentationIndex:
    def __init__(
        self,
        settings: Settings,
        *,
        clock: Callable[[], float] = monotonic,
    ):
        self.settings = settings
        self.clock = clock
        self.documents: dict[str, Document] = {}
        self.documents_by_source: dict[str, Document] = {}
        self.sections: dict[str, Section] = {}
        self.snapshot = hashlib.sha256(b"").hexdigest()
        self._section_tokens: dict[str, list[str]] = {}
        self._document_frequency: Counter[str] = Counter()
        self._average_length = 1.0
        self.source_bytes_processed = 0
        self.index_token_count = 0
        self.index_diagnostics: list[IndexDiagnostic] = []
        self.index_diagnostic_count = 0
        self.skipped_document_count = 0
        self.build_completed = False

    def rebuild(self, source: DocumentationSource) -> None:
        self.build_completed = False
        self.index_diagnostics = []
        self.index_diagnostic_count = 0
        self.skipped_document_count = 0
        documents: dict[str, Document] = {}
        documents_by_source: dict[str, Document] = {}
        sections: dict[str, Section] = {}
        digests: list[str] = []
        source_bytes_processed = 0
        index_token_count = 0
        source_file_count = 0
        traversal_completed = False
        deadline = self.clock() + self.settings.limits.max_index_build_seconds

        def record_diagnostic(
            path: str,
            reason: str,
            *,
            skipped_document: bool = False,
        ) -> None:
            self.index_diagnostic_count += 1
            if skipped_document:
                self.skipped_document_count += 1
            reported_path = path
            if len(reported_path) > MAX_DIAGNOSTIC_SOURCE_CHARACTERS:
                reported_path = f"{reported_path[: MAX_DIAGNOSTIC_SOURCE_CHARACTERS - 1]}…"
            if len(self.index_diagnostics) < MAX_REPORTED_INDEX_DIAGNOSTICS:
                self.index_diagnostics.append(IndexDiagnostic(reported_path, reason))
            logger.warning("index status=skipped source=%r reason=%s", reported_path, reason)

        iterator = iter(source.iter_markdown_files(deadline=deadline))
        while True:
            if self.clock() >= deadline:
                record_diagnostic("<source>", "index_build_time_limit")
                break
            try:
                path = next(iterator)
            except StopIteration:
                traversal_completed = True
                break
            except SourceLimitError as exc:
                record_diagnostic("<source>", exc.reason)
                break

            source_file_count += 1
            if source_file_count > self.settings.limits.max_source_files:
                record_diagnostic(path, "source_file_limit", skipped_document=True)
                break
            allowed_path = require_allowed_path(path, self.settings.allowed_directories)
            if is_excluded(allowed_path, self.settings.excluded_directories):
                continue
            if len(documents) >= self.settings.limits.max_index_documents:
                record_diagnostic(
                    allowed_path,
                    "index_document_limit",
                    skipped_document=True,
                )
                break

            try:
                content = source.read_file(allowed_path, deadline=deadline)
            except SourceLimitError as exc:
                record_diagnostic(
                    allowed_path,
                    exc.reason,
                    skipped_document=exc.reason != "index_build_time_limit",
                )
                if exc.reason == "index_build_time_limit":
                    break
                continue
            except SourceDocumentError as exc:
                record_diagnostic(
                    allowed_path,
                    exc.reason,
                    skipped_document=True,
                )
                continue

            if len(content) > self.settings.limits.max_file_bytes:
                record_diagnostic(
                    allowed_path,
                    "file_too_large",
                    skipped_document=True,
                )
                continue
            try:
                content_bytes = len(content.encode("utf-8"))
            except UnicodeEncodeError:
                record_diagnostic(
                    allowed_path,
                    "invalid_utf8",
                    skipped_document=True,
                )
                continue
            if content_bytes > self.settings.limits.max_file_bytes:
                record_diagnostic(
                    allowed_path,
                    "file_too_large",
                    skipped_document=True,
                )
                continue
            if (
                source_bytes_processed + content_bytes
                > self.settings.limits.max_total_index_bytes
            ):
                record_diagnostic(
                    allowed_path,
                    "total_index_bytes_limit",
                    skipped_document=True,
                )
                break
            source_bytes_processed += content_bytes

            try:
                document = parse_document(allowed_path, content, self.settings.limits)
            except DocumentRejected as exc:
                record_diagnostic(
                    allowed_path,
                    exc.reason,
                    skipped_document=True,
                )
                continue
            if self.settings.allowed_statuses and document.status not in self.settings.allowed_statuses:
                continue
            if self.settings.allowed_types and document.document_type not in self.settings.allowed_types:
                continue
            if document.document_id in documents:
                record_diagnostic(
                    allowed_path,
                    "duplicate_document_id",
                    skipped_document=True,
                )
                continue
            document_token_count = sum(section.token_count for section in document.sections)
            if (
                len(sections) + len(document.sections)
                > self.settings.limits.max_index_sections
            ):
                record_diagnostic(
                    allowed_path,
                    "total_index_sections_limit",
                    skipped_document=True,
                )
                continue
            if (
                index_token_count + document_token_count
                > self.settings.limits.max_total_index_tokens
            ):
                record_diagnostic(
                    allowed_path,
                    "total_index_tokens_limit",
                    skipped_document=True,
                )
                continue
            chunk_ids = [section.chunk_id for section in document.sections]
            if len(set(chunk_ids)) != len(chunk_ids) or any(
                chunk_id in sections for chunk_id in chunk_ids
            ):
                record_diagnostic(
                    allowed_path,
                    "duplicate_chunk_id",
                    skipped_document=True,
                )
                continue
            for section in document.sections:
                sections[section.chunk_id] = section
            documents[document.document_id] = document
            documents_by_source[document.source] = document
            digests.append(content_digest(path, content))
            index_token_count += document_token_count

        self.documents = documents
        self.documents_by_source = documents_by_source
        self.sections = sections
        self.snapshot = hashlib.sha256("\n".join(sorted(digests)).encode("utf-8")).hexdigest()
        self.source_bytes_processed = source_bytes_processed
        self.index_token_count = index_token_count
        if not self._prepare_ranking(deadline=deadline):
            if not any(
                item.reason == "index_build_time_limit"
                for item in self.index_diagnostics
            ):
                record_diagnostic("<index>", "index_build_time_limit")
            self.documents = {}
            self.documents_by_source = {}
            self.sections = {}
            self.snapshot = hashlib.sha256(b"").hexdigest()
            self.index_token_count = 0
            self._section_tokens = {}
            self._document_frequency = Counter()
            self._average_length = 1.0
            return
        self.build_completed = traversal_completed

    def _prepare_ranking(self, *, deadline: float | None = None) -> bool:
        section_tokens: dict[str, list[str]] = {}
        document_frequency: Counter[str] = Counter()
        lengths: list[int] = []
        for chunk_id, section in self.sections.items():
            if deadline is not None and self.clock() >= deadline:
                return False
            tokens = _tokens(section.text)
            section_tokens[chunk_id] = tokens
            lengths.append(len(tokens))
            document_frequency.update(set(tokens))
        if deadline is not None and self.clock() >= deadline:
            return False
        self._section_tokens = section_tokens
        self._document_frequency = document_frequency
        self._average_length = sum(lengths) / len(lengths) if lengths else 1.0
        return True

    def _document_matches(self, document: Document, filters: Mapping[str, Any]) -> bool:
        unsupported = set(filters) - SUPPORTED_FILTERS
        if unsupported:
            raise ValueError(f"Unsupported metadata filters: {', '.join(sorted(unsupported))}")

        fields: dict[str, set[str]] = {
            "status": {document.status},
            "type": {document.document_type},
            "area": {document.area},
            "tags": set(document.tags),
        }
        return all(fields[name] & _filter_values(value) for name, value in filters.items())

    def _score(self, query: str, document: Document, section: Section) -> RankedSection | None:
        query_tokens = _tokens(query)
        if not query_tokens:
            raise ValueError("query must contain searchable terms")

        section_tokens = self._section_tokens.get(section.chunk_id, [])
        counts = Counter(section_tokens)
        total_sections = max(len(self.sections), 1)
        length = max(len(section_tokens), 1)
        score = 0.0
        reasons: list[str] = []

        for token in set(query_tokens):
            frequency = counts[token]
            if not frequency:
                continue
            document_frequency = self._document_frequency[token]
            inverse = math.log(1 + (total_sections - document_frequency + 0.5) / (document_frequency + 0.5))
            denominator = frequency + 1.5 * (0.25 + 0.75 * length / self._average_length)
            score += inverse * (frequency * 2.5) / denominator
        if score:
            reasons.append("body-term-match")

        heading_tokens = set(_tokens(section.heading_path))
        heading_hits = len(set(query_tokens) & heading_tokens)
        if heading_hits:
            score += heading_hits * 1.4
            reasons.append("heading-match")

        document_terms = set(
            _tokens(
                " ".join(
                    (
                        document.title,
                        document.summary,
                        document.area,
                        document.document_type,
                        " ".join(document.tags),
                    )
                )
            )
        )
        metadata_hits = len(set(query_tokens) & document_terms)
        if metadata_hits:
            score += metadata_hits * 0.55
            reasons.append("metadata-match")

        lowered_query = query.lower()
        if lowered_query in section.heading_path.lower():
            score += 2.0
            reasons.append("heading-phrase-match")

        role_terms = {
            "interface": {"interface", "field", "option", "parameter"},
            "default": {"default"},
            "configuration": {"setting", "configuration", "preference", "option"},
            "behavior": {"behavior", "work", "when", "how", "processing"},
            "validation": {"validation", "valid", "constraint", "requirement"},
            "reference": {"reference", "schema", "structure", "field"},
            "edge-case": {"error", "failure", "invalid", "edge", "cannot"},
            "integration": {"api", "integration", "connector"},
            "test-coverage": {"test", "coverage", "verify"},
        }
        if set(query_tokens) & role_terms.get(section.role, set()):
            score += 0.8
            reasons.append(f"section-role:{section.role}")

        if score <= 0:
            return None
        return RankedSection(section, document, score, "direct", tuple(reasons))

    def _resolve_document(self, reference: str) -> Document | None:
        return self.documents.get(reference) or self.documents_by_source.get(reference)

    def _ranked(self, query: str, filters: Mapping[str, Any]) -> list[RankedSection]:
        ranked: list[RankedSection] = []
        for document in self.documents.values():
            if not self._document_matches(document, filters):
                continue
            for section in document.sections:
                candidate = self._score(query, document, section)
                if candidate is not None:
                    ranked.append(candidate)
        ranked.sort(key=lambda item: (-item.score, item.section.source, item.section.heading_path))
        return ranked

    @staticmethod
    def _is_substantive(candidate: RankedSection) -> bool:
        parts = [part.strip().lower() for part in candidate.section.heading_path.split(" > ")]
        if not parts or parts[-1] in GENERIC_SECTION_LEAVES:
            return False
        return len(parts) > 1 or candidate.section.role != "general"

    def _related_complement(
        self,
        query: str,
        primary: RankedSection,
        ranked: list[RankedSection],
        filters: Mapping[str, Any],
    ) -> RankedSection | None:
        """Select at most one relevant complement from the primary's direct links."""
        if self.settings.limits.related_document_hops == 0:
            return None

        complementary = COMPLEMENTARY_ROLES.get(primary.section.role, ())
        if not complementary:
            return None
        role_positions = {role: position for position, role in enumerate(complementary)}
        related_documents: dict[str, Document] = {}
        for reference in primary.document.related_documents:
            related = self._resolve_document(reference)
            if (
                related is None
                or related.document_id == primary.document.document_id
                or not self._document_matches(related, filters)
            ):
                continue
            related_documents[related.document_id] = related
        if not related_documents:
            return None

        floor = primary.score * RELATED_SCORE_FLOOR
        options = [
            candidate
            for candidate in ranked
            if candidate.document.document_id in related_documents
            and self._is_substantive(candidate)
            and candidate.section.role in role_positions
            and candidate.score >= floor
        ]
        if not options:
            return None
        canonical_preferred = bool(
            set(_tokens(f"{query} {primary.section.heading_path}"))
            & CANONICAL_CONTEXT_TERMS
        )
        options.sort(
            key=lambda item: (
                0
                if canonical_preferred
                and _has_canonical_default_evidence(item.section)
                else 1,
                -item.score,
                role_positions[item.section.role],
                item.section.source,
                item.section.heading_path,
                item.section.chunk_id,
            )
        )
        best = options[0]
        canonical_reason = (
            ("canonical-default-evidence",)
            if canonical_preferred and _has_canonical_default_evidence(best.section)
            else ()
        )
        return RankedSection(
            section=best.section,
            document=best.document,
            score=best.score,
            route=f"related:{primary.document.document_id}",
            reasons=(
                best.reasons
                + (
                    "related-document-hop",
                    f"complementary-role:{primary.section.role}-to-{best.section.role}",
                )
                + canonical_reason
            ),
        )

    def _selection_order(
        self,
        query: str,
        ranked: list[RankedSection],
        filters: Mapping[str, Any],
        result_limit: int,
    ) -> list[RankedSection]:
        """Build a deterministic, limit-aware result order around one primary."""
        if not ranked:
            return []
        substantive = [candidate for candidate in ranked if self._is_substantive(candidate)]
        primary = (substantive or ranked)[0]
        routed = self._related_complement(query, primary, ranked, filters)

        selected: list[RankedSection] = []
        selected_chunks: set[str] = set()
        selected_documents: set[str] = set()
        document_counts: Counter[str] = Counter()

        def add(candidate: RankedSection) -> bool:
            document_id = candidate.document.document_id
            if candidate.section.chunk_id in selected_chunks or len(selected) >= result_limit:
                return False
            if (
                document_id not in selected_documents
                and len(selected_documents) >= self.settings.limits.max_documents
            ):
                return False
            if document_counts[document_id] >= self.settings.limits.max_sections_per_document:
                return False
            selected.append(candidate)
            selected_chunks.add(candidate.section.chunk_id)
            selected_documents.add(document_id)
            document_counts[document_id] += 1
            return True

        add(primary)
        if routed is not None:
            add(routed)

        complementary = set(COMPLEMENTARY_ROLES.get(primary.section.role, ()))
        local_supplements = [
            candidate
            for candidate in substantive
            if candidate.document.document_id == primary.document.document_id
            and candidate.section.role in complementary
            and candidate.score >= primary.score * SUPPLEMENT_SCORE_FLOOR
        ]
        if local_supplements:
            best_local = local_supplements[0]
            add(
                RankedSection(
                    section=best_local.section,
                    document=best_local.document,
                    score=best_local.score,
                    route="direct",
                    reasons=best_local.reasons + ("complementary-section",),
                )
            )

        routed_chunk = routed.section.chunk_id if routed is not None else None
        for candidate in ranked:
            if candidate.section.chunk_id == routed_chunk:
                continue
            add(candidate)
            if len(selected) >= result_limit:
                break
        return selected

    @staticmethod
    def _result_shell(candidate: RankedSection) -> dict[str, Any]:
        return {
            "chunk_id": candidate.section.chunk_id,
            "document_id": candidate.document.document_id,
            "heading_path": candidate.section.heading_path,
            "summary": candidate.section.summary,
            "evidence": candidate.section.evidence,
            "score": round(candidate.score, 6),
            "source": candidate.section.source,
            "route": candidate.route,
            "ranking_reasons": list(dict.fromkeys(candidate.reasons)),
            "excerpt": "",
        }

    @staticmethod
    def _is_selected_complement(candidate: RankedSection) -> bool:
        return any(
            reason == "related-document-hop" or reason == "complementary-section"
            for reason in candidate.reasons
        )

    def search(
        self,
        query: str,
        *,
        filters: Mapping[str, Any] | None = None,
        top_k: int | None = None,
        max_total_characters: int | None = None,
    ) -> list[dict[str, Any]]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        filter_map = filters or {}
        if not isinstance(filter_map, Mapping):
            raise ValueError("filters must be an object")

        requested_top_k = self.settings.limits.top_k if top_k is None else top_k
        if not isinstance(requested_top_k, int) or isinstance(requested_top_k, bool) or requested_top_k < 1:
            raise ValueError("top_k must be a positive integer")
        result_limit = min(requested_top_k, self.settings.limits.top_k, self.settings.limits.max_sections)

        requested_characters = (
            self.settings.limits.max_total_characters
            if max_total_characters is None
            else max_total_characters
        )
        if (
            not isinstance(requested_characters, int)
            or isinstance(requested_characters, bool)
            or requested_characters < 1
        ):
            raise ValueError("max_total_characters must be a positive integer")
        character_budget = min(requested_characters, self.settings.limits.max_total_characters)

        ranked = self._ranked(query.strip(), filter_map)
        selected = self._selection_order(
            query.strip(),
            ranked,
            filter_map,
            result_limit,
        )
        results: list[dict[str, Any]] = []
        for position, candidate in enumerate(selected):
            result = self._result_shell(candidate)

            available_excerpt_characters = (
                character_budget
                - serialized_character_count([*results, result])
            )
            if (
                position == 0
                and len(selected) > 1
                and self._is_selected_complement(selected[1])
            ):
                complement = selected[1]
                complement_shell = self._result_shell(complement)
                empty_pair_size = serialized_character_count(
                    [result, complement_shell]
                )
                available_pair_content = character_budget - empty_pair_size
                if available_pair_content >= 2:
                    reserve_budget = min(
                        COMPLEMENT_EXCERPT_RESERVE,
                        available_pair_content // 2,
                    )
                    reserved_excerpt = serialized_string_prefix(
                        complement.section.text,
                        reserve_budget,
                    ).rstrip()
                    if reserved_excerpt:
                        complement_shell["excerpt"] = reserved_excerpt
                        available_excerpt_characters = (
                            character_budget
                            - serialized_character_count(
                                [result, complement_shell]
                            )
                        )
            excerpt = serialized_string_prefix(
                candidate.section.text,
                available_excerpt_characters,
            ).rstrip()
            if not excerpt:
                continue

            result["excerpt"] = excerpt
            results.append(result)
            if (
                len(results) >= result_limit
                or serialized_character_count(results) >= character_budget
            ):
                break
        return results

    def document_metadata(self, document_id: str) -> dict[str, Any]:
        document = self._resolve_document(document_id)
        if document is None:
            raise KeyError("Document not found")
        return document.public_metadata()

    def document_section(
        self,
        *,
        chunk_id: str | None = None,
        document_id: str | None = None,
        heading_path: str | None = None,
        max_characters: int | None = None,
    ) -> dict[str, Any]:
        section: Section | None = None
        if chunk_id:
            section = self.sections.get(chunk_id)
        elif document_id and heading_path:
            document = self._resolve_document(document_id)
            if document is not None:
                section = next(
                    (item for item in document.sections if item.heading_path == heading_path),
                    None,
                )
        else:
            raise ValueError("Provide chunk_id or document_id with heading_path")
        if section is None:
            raise KeyError("Section not found")

        requested = self.settings.limits.max_total_characters if max_characters is None else max_characters
        if not isinstance(requested, int) or isinstance(requested, bool) or requested < 1:
            raise ValueError("max_characters must be a positive integer")
        maximum = min(requested, self.settings.limits.max_total_characters)
        return {
            "chunk_id": section.chunk_id,
            "document_id": section.document_id,
            "heading_path": section.heading_path,
            "text": section.text[:maximum],
            "truncated": len(section.text) > maximum,
            "evidence": section.evidence,
            "source": section.source,
        }

    def related_documents(self, document_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        document = self._resolve_document(document_id)
        if document is None:
            raise KeyError("Document not found")
        requested = self.settings.limits.top_k if limit is None else limit
        if not isinstance(requested, int) or isinstance(requested, bool) or requested < 1:
            raise ValueError("limit must be a positive integer")
        maximum = min(requested, self.settings.limits.top_k)
        related: list[dict[str, Any]] = []
        for reference in document.related_documents:
            target = self._resolve_document(reference)
            if target is not None:
                related.append(target.public_metadata())
            if len(related) >= maximum:
                break
        return related

    def scope_info(self) -> dict[str, Any]:
        from . import __version__

        return {
            "server_version": __version__,
            "backend": self.settings.backend,
            "access": "read-only",
            "allowed_directories": list(self.settings.allowed_directories),
            "allowed_statuses": list(self.settings.allowed_statuses),
            "allowed_types": list(self.settings.allowed_types),
            "excluded_directories": list(self.settings.excluded_directories),
            "limits": {
                "top_k": self.settings.limits.top_k,
                "max_total_characters": self.settings.limits.max_total_characters,
                "max_sections": self.settings.limits.max_sections,
                "max_documents": self.settings.limits.max_documents,
                "max_sections_per_document": self.settings.limits.max_sections_per_document,
                "related_document_hops": self.settings.limits.related_document_hops,
                "max_file_bytes": self.settings.limits.max_file_bytes,
                "max_total_index_bytes": self.settings.limits.max_total_index_bytes,
                "max_source_files": self.settings.limits.max_source_files,
                "max_source_directories": self.settings.limits.max_source_directories,
                "max_directory_entries": self.settings.limits.max_directory_entries,
                "max_directory_response_bytes": (
                    self.settings.limits.max_directory_response_bytes
                ),
                "max_index_documents": self.settings.limits.max_index_documents,
                "max_index_sections": self.settings.limits.max_index_sections,
                "max_index_sections_per_document": (
                    self.settings.limits.max_index_sections_per_document
                ),
                "max_tokens_per_section": self.settings.limits.max_tokens_per_section,
                "max_total_index_tokens": self.settings.limits.max_total_index_tokens,
                "max_frontmatter_bytes": self.settings.limits.max_frontmatter_bytes,
                "max_frontmatter_nodes": self.settings.limits.max_frontmatter_nodes,
                "max_frontmatter_depth": self.settings.limits.max_frontmatter_depth,
                "max_index_build_seconds": (
                    self.settings.limits.max_index_build_seconds
                ),
            },
            "index_snapshot": self.snapshot,
            "index_build_completed": self.build_completed,
            "document_count": len(self.documents),
            "section_count": len(self.sections),
            "source_bytes_processed": self.source_bytes_processed,
            "index_token_count": self.index_token_count,
            "index_diagnostics": {
                "count": self.index_diagnostic_count,
                "skipped_documents": self.skipped_document_count,
                "truncated": self.index_diagnostic_count > len(self.index_diagnostics),
                "entries": [
                    {"source": item.source, "reason": item.reason}
                    for item in self.index_diagnostics
                ],
            },
        }

    def debug_snapshot(self) -> str:
        """Return a deterministic internal representation for regression tests."""
        payload = {
            document_id: [section.chunk_id for section in document.sections]
            for document_id, document in sorted(self.documents.items())
        }
        return json.dumps(payload, sort_keys=True)
