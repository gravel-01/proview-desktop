"""Structured content loader for career planning documents.

Phase 4 extends the loader to expose:

- :meth:`CareerPlanningDocumentRepository.list_sections_with_tags` —
  flatten all sections across all documents, each annotated with the
  structured taxonomy (skill_tags / gap_tags / task_types) and the
  document's own free-form tags.
- :meth:`CareerPlanningDocumentRepository.get_section` — fetch a
  single section by ``(doc_id, section_idx)``.
- :meth:`CareerPlanningDocumentRepository.search_sections` — filter
  sections by free-text query, structured ``gap_tags`` and structured
  ``task_types`` simultaneously.

The structured labels come from
:mod:`services.career_planning_doc_taxonomy`; when a section has no
known mapping the methods still return it, but with
``tag_known=False`` so the recommender can decide whether to surface
it in the gap-driven ranking or fall back to free-form text search.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from runtime_paths import get_resource_path

from services.career_planning_doc_taxonomy import (
    SectionTaxonomy,
    get_section_taxonomy,
)


@dataclass(frozen=True)
class CareerPlanningDocumentRepository:
    source_path: Path = get_resource_path("data", "career_planning_docs.json")

    def _load_raw(self) -> Dict[str, Any]:
        with self.source_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def list_documents(self) -> List[Dict[str, Any]]:
        payload = self._load_raw()
        return list(payload.get("documents", []))

    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        for document in self.list_documents():
            if document.get("id") == document_id:
                return document
        return None

    def get_catalog(self) -> Dict[str, Any]:
        payload = self._load_raw()
        return {
            "version": payload.get("version", "1.0.0"),
            "updated_at": payload.get("updated_at"),
            "documents": payload.get("documents", []),
        }

    # ------------------------------------------------------------------
    # Phase 4: section-level indexing and search
    # ------------------------------------------------------------------

    def list_sections_with_tags(
        self,
        documents: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Return a flat list of sections with their structured taxonomy.

        Each entry is a dict shaped like::

            {
                "doc_id": "...",
                "doc_title": "...",
                "doc_tags": [...],            # document-level free-form tags
                "doc_is_featured": bool,
                "doc_difficulty": "...",
                "doc_read_time": int,
                "section_idx": 0,
                "section_heading": "...",
                "section_paragraphs": [...],
                "section_bullets": [...],
                "section_action_items": [...],
                "section_tags": [...],        # free-form section tags (legacy)
                "skill_tags": [...],
                "gap_tags": [...],
                "task_types": [...],
                "tag_known": bool,
            }

        The method tolerates missing / malformed sections (they are
        skipped silently) and never raises.
        """
        docs = list(documents) if documents is not None else self.list_documents()
        out: List[Dict[str, Any]] = []
        for doc in docs:
            doc_id = str(doc.get("id") or "").strip()
            if not doc_id:
                continue
            sections = doc.get("sections") or []
            if not isinstance(sections, list):
                continue
            doc_tags = [str(t) for t in (doc.get("tags") or [])]
            for idx, section in enumerate(sections):
                if not isinstance(section, dict):
                    continue
                heading = str(section.get("heading") or "").strip()
                if not heading:
                    continue
                tax = get_section_taxonomy(heading)
                out.append(
                    {
                        "doc_id": doc_id,
                        "doc_title": str(doc.get("title") or ""),
                        "doc_subtitle": str(doc.get("subtitle") or ""),
                        "doc_tags": doc_tags,
                        "doc_is_featured": bool(doc.get("is_featured")),
                        "doc_difficulty": str(doc.get("difficulty") or ""),
                        "doc_read_time": int(doc.get("read_time") or 0),
                        "doc_category": str(doc.get("category") or ""),
                        "section_idx": int(idx),
                        "section_heading": heading,
                        "section_paragraphs": [
                            str(p) for p in (section.get("paragraphs") or [])
                        ],
                        "section_bullets": [
                            str(b) for b in (section.get("bullets") or [])
                        ],
                        "section_action_items": [
                            str(a) for a in (section.get("action_items") or [])
                        ],
                        "section_tags": [
                            str(t) for t in (section.get("tags") or [])
                        ],
                        "skill_tags": list(tax.skill_tags),
                        "gap_tags": list(tax.gap_tags),
                        "task_types": list(tax.task_types),
                        "tag_known": bool(tax.tag_known),
                    }
                )
        return out

    def get_section(self, doc_id: str, section_idx: int) -> Optional[Dict[str, Any]]:
        """Return a single section dict (with taxonomy) or ``None``."""
        for section in self.list_sections_with_tags():
            if section["doc_id"] == doc_id and section["section_idx"] == int(section_idx):
                return section
        return None

    def search_sections(
        self,
        *,
        query: str = "",
        gap_tags: Optional[Iterable[str]] = None,
        skill_tags: Optional[Iterable[str]] = None,
        task_types: Optional[Iterable[str]] = None,
        doc_id: Optional[str] = None,
        include_unknown: bool = True,
    ) -> List[Dict[str, Any]]:
        """Filter sections by query + structured tags.

        Args:
            query: free-text query; case-insensitive substring match
                against heading / paragraphs / bullets / action items /
                doc tags / section tags.
            gap_tags: if provided, sections must contain at least one
                of these ``gap_tags`` to pass. ``tag_known=False``
                sections are filtered out unless ``include_unknown``.
            skill_tags: if provided, sections must contain at least one
                of these ``skill_tags`` to pass.
            task_types: if provided, sections must contain at least one
                of these ``task_types`` to pass.
            doc_id: when set, restrict the search to a single document.
            include_unknown: if False, sections without a known
                taxonomy mapping are excluded when ``gap_tags`` is set.
        """
        gap_set: Set[str] = {str(t) for t in (gap_tags or [])}
        skill_set: Set[str] = {str(t) for t in (skill_tags or [])}
        task_set: Set[str] = {str(t) for t in (task_types or [])}
        q = (query or "").strip().lower()

        results: List[Dict[str, Any]] = []
        for section in self.list_sections_with_tags():
            if doc_id and section["doc_id"] != doc_id:
                continue
            if gap_set:
                if not include_unknown and not section["tag_known"]:
                    continue
                if not (set(section["gap_tags"]) & gap_set):
                    # Tolerate legacy gap keys that predate the taxonomy
                    # by also checking free-form section tags.
                    if not (set(section["section_tags"]) & gap_set):
                        continue
            if skill_set and not (set(section["skill_tags"]) & skill_set):
                if not (set(section["doc_tags"]) & skill_set):
                    continue
            if task_set and not (set(section["task_types"]) & task_set):
                continue
            if q:
                haystack_parts = [
                    section["section_heading"],
                    section["doc_title"],
                    section["doc_subtitle"],
                ]
                haystack_parts.extend(section["section_paragraphs"])
                haystack_parts.extend(section["section_bullets"])
                haystack_parts.extend(section["section_action_items"])
                haystack_parts.extend(section["section_tags"])
                haystack_parts.extend(section["doc_tags"])
                haystack = " ".join(haystack_parts).lower()
                if q not in haystack:
                    continue
            results.append(section)
        return results
