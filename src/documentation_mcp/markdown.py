from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath
from typing import Any

import yaml
from yaml.events import (
    AliasEvent,
    MappingEndEvent,
    MappingStartEvent,
    ScalarEvent,
    SequenceEndEvent,
    SequenceStartEvent,
)

from .config import Limits
from .models import Document, Section


HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class DocumentRejected(ValueError):
    """Raised when one Markdown document exceeds a safe parsing bound."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason.replace("_", " "))


def _slug(value: str) -> str:
    words = WORD_RE.findall(value.lower())
    return "-".join(words) or "section"


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, list):
        return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    return ()


def _validate_frontmatter_structure(value: str, limits: Limits) -> None:
    depth = 0
    nodes = 0
    try:
        for event in yaml.parse(value):
            if isinstance(event, AliasEvent):
                raise DocumentRejected("frontmatter_alias_not_allowed")
            if isinstance(
                event,
                (
                    ScalarEvent,
                    SequenceStartEvent,
                    MappingStartEvent,
                ),
            ):
                nodes += 1
                if nodes > limits.max_frontmatter_nodes:
                    raise DocumentRejected("frontmatter_node_limit")
            if isinstance(
                event,
                (SequenceStartEvent, MappingStartEvent),
            ):
                depth += 1
                if depth > limits.max_frontmatter_depth:
                    raise DocumentRejected("frontmatter_depth_limit")
            elif isinstance(
                event,
                (SequenceEndEvent, MappingEndEvent),
            ):
                depth -= 1
    except DocumentRejected:
        raise
    except yaml.YAMLError:
        return


def _frontmatter(content: str, limits: Limits) -> tuple[dict[str, Any], str]:
    if not content.startswith("---"):
        return {}, content
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        return {}, content
    raw_frontmatter = "\n".join(lines[1:end])
    if (
        len(raw_frontmatter) > limits.max_frontmatter_bytes
        or len(raw_frontmatter.encode("utf-8")) > limits.max_frontmatter_bytes
    ):
        raise DocumentRejected("frontmatter_too_large")
    _validate_frontmatter_structure(raw_frontmatter, limits)
    try:
        parsed = yaml.safe_load(raw_frontmatter)
    except yaml.YAMLError:
        parsed = {}
    metadata = parsed if isinstance(parsed, dict) else {}
    return metadata, "\n".join(lines[end + 1 :])


def _summary(text: str, limit: int = 240) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _matches_heading_term(heading: str, terms: tuple[str, ...]) -> bool:
    heading_words = tuple(WORD_RE.findall(heading.lower()))
    for term in terms:
        term_words = tuple(WORD_RE.findall(term.lower()))
        if not term_words:
            continue
        width = len(term_words)
        if any(
            heading_words[position : position + width] == term_words
            for position in range(len(heading_words) - width + 1)
        ):
            return True
    return False


def _role(heading_path: str) -> str:
    parts = [part.strip().lower() for part in heading_path.split(" > ")]
    leaf = parts[-1]
    if _matches_heading_term(
        leaf,
        (
            "edge",
            "failure",
            "failures",
            "error",
            "errors",
            "exception",
            "exceptions",
            "limitation",
            "limitations",
        ),
    ):
        return "edge-case"
    if "interface" in parts:
        return "interface"
    if "behavior" in parts or leaf.startswith(("when ", "changing ")):
        return "behavior"
    if any(
        _matches_heading_term(
            part,
            ("validation", "constraint", "constraints"),
        )
        for part in parts
    ):
        return "validation"

    mappings = (
        ("interface", ("interface",)),
        ("default", ("default", "defaults")),
        (
            "configuration",
            ("configuration", "setting", "settings", "preference", "preferences"),
        ),
        ("behavior", ("behavior", "workflow", "processing", "runtime")),
        ("validation", ("validation", "constraint", "constraints")),
        ("reference", ("reference", "data structure", "schema")),
        ("acceptance", ("acceptance", "requirement", "requirements")),
        ("integration", ("integration", "api", "connector", "connectors")),
        ("test-coverage", ("test", "coverage")),
    )
    for heading in (leaf, *reversed(parts[:-1])):
        for role, terms in mappings:
            if _matches_heading_term(heading, terms):
                return role
    return "general"


def parse_document(source: str, content: str, limits: Limits | None = None) -> Document:
    active_limits = limits or Limits()
    if (
        len(content) > active_limits.max_file_bytes
        or len(content.encode("utf-8")) > active_limits.max_file_bytes
    ):
        raise DocumentRejected("file_too_large")

    metadata, body = _frontmatter(content, active_limits)
    path = PurePosixPath(source)
    fallback_id = _slug(path.with_suffix("").as_posix())
    document_id = _string(metadata.get("document_id")) or _string(metadata.get("id")) or fallback_id
    document_id = _slug(document_id)

    body_lines = body.splitlines()
    first_h1 = next(
        (match.group(2).strip() for line in body_lines if (match := HEADING_RE.match(line)) and len(match.group(1)) == 1),
        "",
    )
    title = _string(metadata.get("title")) or first_h1 or path.stem
    doc_summary = _string(metadata.get("summary"))
    evidence = _string(metadata.get("evidence")) or "documented"

    document = Document(
        document_id=document_id,
        source=source,
        title=title,
        summary=doc_summary,
        status=_string(metadata.get("status")),
        document_type=_string(metadata.get("type")),
        area=_string(metadata.get("area")),
        evidence=evidence,
        tags=_string_list(metadata.get("tags")),
        related_documents=_string_list(metadata.get("related_documents")),
        metadata=dict(metadata),
    )

    stack: list[tuple[int, str]] = []
    heading_path = "Overview"
    current_lines: list[str] = []
    occurrence: dict[str, int] = {}

    def flush() -> None:
        text = "\n".join(current_lines).strip()
        if not text:
            return
        if len(document.sections) >= active_limits.max_index_sections_per_document:
            raise DocumentRejected("document_section_limit")
        token_count = sum(1 for _ in WORD_RE.finditer(text))
        if token_count > active_limits.max_tokens_per_section:
            raise DocumentRejected("section_token_limit")
        base = _slug(heading_path)
        occurrence[base] = occurrence.get(base, 0) + 1
        suffix = "" if occurrence[base] == 1 else f"-{occurrence[base]}"
        chunk_id = f"{document_id}::{base}{suffix}"
        document.sections.append(
            Section(
                chunk_id=chunk_id,
                document_id=document_id,
                heading_path=heading_path,
                text=text,
                summary=_summary(text),
                evidence=evidence,
                role=_role(heading_path),
                source=source,
                token_count=token_count,
            )
        )

    for line in body_lines:
        match = HEADING_RE.match(line)
        if not match:
            current_lines.append(line)
            continue

        flush()
        current_lines = []
        level = len(match.group(1))
        heading = match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, heading))
        heading_path = " > ".join(item[1] for item in stack)

    flush()

    if not document.sections:
        fallback_text = body.strip() or title
        token_count = sum(1 for _ in WORD_RE.finditer(fallback_text))
        if token_count > active_limits.max_tokens_per_section:
            raise DocumentRejected("section_token_limit")
        document.sections.append(
            Section(
                chunk_id=f"{document_id}::overview",
                document_id=document_id,
                heading_path="Overview",
                text=fallback_text,
                summary=_summary(fallback_text),
                evidence=evidence,
                role="general",
                source=source,
                token_count=token_count,
            )
        )
    if not document.summary:
        document.summary = document.sections[0].summary
    return document


def content_digest(source: str, content: str) -> str:
    return hashlib.sha256(f"{source}\0{content}".encode("utf-8")).hexdigest()
