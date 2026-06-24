"""Generate a draft cover letter (.docx) for a tracked role.

The app runs offline, so this produces a structured *draft* — pre-filled with the
role's company, title and your fit notes, with bracketed placeholders to finish.
For a fully tailored letter, hand the role to Claude / the job-hunt skill, which
has your profile.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from docx import Document

import config


def _safe(name: str) -> str:
    """Make a string safe to use in a filename."""
    cleaned = re.sub(r'[\\/:*?"<>|]+', "", (name or "")).strip()
    return cleaned or "Untitled"


def cover_letter_path(job: dict, out_dir: Path | str | None = None) -> Path:
    out_dir = Path(out_dir) if out_dir else config.COVER_LETTER_DIR
    company = _safe(job.get("company") or "Company")
    title = _safe(job.get("title") or "Role")
    return out_dir / f"Cover Letter - {company} - {title}.docx"


def generate_cover_letter(job: dict, out_dir: Path | str | None = None) -> Path:
    """Write a draft cover letter for ``job`` and return the saved path."""
    out_dir = Path(out_dir) if out_dir else config.COVER_LETTER_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = cover_letter_path(job, out_dir)

    company = (job.get("company") or "the company").strip()
    title = (job.get("title") or "the role").strip()
    location = (job.get("location") or "").strip()
    fit = (job.get("fit_notes") or "").strip()
    today = dt.date.today().strftime("%d %B %Y")

    doc = Document()
    doc.add_paragraph(today)
    doc.add_paragraph("")
    doc.add_paragraph("Dear Hiring Manager,")

    intro = (
        f"I am writing to apply for the {title} position at {company}"
        + (f" ({location})" if location else "")
        + ". Having reviewed the role, I am confident that my background and "
        "experience make me a strong fit."
    )
    doc.add_paragraph(intro)

    body = (
        "In my career to date, [add two or three sentences on your most relevant "
        "experience, skills and achievements for this role]."
    )
    if fit:
        body += f" This role stood out to me in particular because {fit[0].lower()}{fit[1:]}."
    doc.add_paragraph(body)

    doc.add_paragraph(
        f"I would welcome the opportunity to discuss how I can contribute to {company}. "
        "Thank you for considering my application; I look forward to hearing from you."
    )
    doc.add_paragraph("")
    doc.add_paragraph("Yours sincerely,")
    doc.add_paragraph("[Your name]")

    doc.save(str(path))
    return path
