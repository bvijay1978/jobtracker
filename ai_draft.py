"""JD-tailored CV + cover-letter drafting via the Anthropic API (ADR-013).

The offline path (cv_builder.py, cover_letter.py) and the agent-queue path
(screening_queue.py / ADR-008, ADR-012) both still work with no LLM involved
at all — this module is a *third*, optional path: a direct, in-app call to
Claude for people who'd rather not leave the app to ask Claude separately.
It's gated entirely on ANTHROPIC_API_KEY being set; unset, the app behaves
exactly as before.

Only covers document generation (this needs the JD text + the profile — both
already in hand). Contact resolution and follow-up drafting still need Gmail,
which stays out of the app on purpose (ADR-002/ADR-003) — those remain
"ask Claude" only.
"""

from __future__ import annotations

from pydantic import BaseModel

from cv_builder import load_profile

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """You draft a screening CV and a cover letter for one job \
application. You will be given a job description and the candidate's real \
career profile (work history, competencies, achievements).

Honesty rule — absolute, no exceptions: only describe skills and experience \
the candidate genuinely has, drawn from their profile. Mirror the job \
description's terminology where the candidate's real experience genuinely \
supports it. Never invent a skill, tool, employer, metric, or achievement \
that isn't in the profile you were given. If the JD asks for something the \
profile doesn't support, simply don't claim it — do not paper over the gap.

Write the cover letter paragraphs in first person, ready to drop into a \
formal letter (no salutation or signature — those are added separately)."""


class ExperienceEntry(BaseModel):
    title: str
    company: str
    dates: str
    bullets: list[str]


class DraftPayload(BaseModel):
    target_title: str
    summary: str
    core_skills: list[str]
    experience: list[ExperienceEntry]
    cover_letter_paragraphs: list[str]


def _user_content(role: dict, jd_text: str, profile: dict) -> str:
    return (
        f"ROLE\nTitle: {role.get('title', '')}\nCompany: {role.get('company', '')}\n"
        f"Location: {role.get('location', '')}\n\n"
        f"JOB DESCRIPTION\n{jd_text}\n\n"
        f"CANDIDATE PROFILE (JSON)\n{profile}"
    )


def draft(role: dict, jd_text: str, profile_path=None) -> DraftPayload:
    """Call Claude once for both the screening-CV payload and cover-letter body.

    Returns a DraftPayload ready to pass straight into
    screening_cv.generate_screening_cv (target_title/summary/core_skills/
    experience) and cover_letter.generate_cover_letter (cover_letter_paragraphs
    as body_paragraphs) — no new rendering code, same documents either path
    produces.
    """
    import anthropic  # imported lazily — only needed when this path is used

    profile = load_profile(profile_path)
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    response = client.messages.parse(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_content(role, jd_text, profile)}],
        output_format=DraftPayload,
    )
    return response.parsed_output
