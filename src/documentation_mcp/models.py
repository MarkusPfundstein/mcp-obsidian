from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Section:
    chunk_id: str
    document_id: str
    heading_path: str
    text: str
    summary: str
    evidence: str
    role: str
    source: str
    token_count: int


@dataclass
class Document:
    document_id: str
    source: str
    title: str
    summary: str
    status: str
    document_type: str
    area: str
    evidence: str
    tags: tuple[str, ...]
    related_documents: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)

    def public_metadata(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source": self.source,
            "title": self.title,
            "summary": self.summary,
            "status": self.status,
            "type": self.document_type,
            "area": self.area,
            "evidence": self.evidence,
            "tags": list(self.tags),
            "related_documents": list(self.related_documents),
            "section_count": len(self.sections),
        }
