"""Document library helpers (ADR-014).

A general store for resumes, cover letters, certificates and anything else
worth keeping alongside the tracker — stored as bytes in the database (same
backend as everything else in db.py) so they survive restarts and redeploys
on the hosted deployment, unlike files written to local disk.

Generated documents (the offline cover-letter button, the AI-tailored
drafting section) are auto-tagged with the role's title and detected sector
so a CV drafted for one role can be found and reused for similar ones later.
"""

from __future__ import annotations

import db
from cv_builder import detect_sector

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

CATEGORIES = ["Resume", "Cover Letter", "Certificate", "Other"]

_SECTOR_LABELS = {"fs": "FS", "ai": "AI", "public": "Public", "default": "General"}


def role_tags(role: dict) -> str:
    """Auto-tags for a document generated against a role: detected sector +
    the role's title, so similar future roles are easy to find by tag."""
    tags = [_SECTOR_LABELS.get(detect_sector(role), "General")]
    title = (role.get("title") or "").strip()
    if title:
        tags.append(title)
    return ", ".join(tags)


def save(
    conn,
    *,
    name: str,
    category: str,
    tags: str,
    role_id: int | None,
    filename: str,
    data: bytes,
    mime_type: str | None = None,
) -> int:
    """Store a document and return its id."""
    return db.insert_document(conn, {
        "name": name,
        "category": category,
        "tags": tags,
        "role_id": role_id,
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": len(data),
        "data": data,
    })
