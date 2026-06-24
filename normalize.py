"""Small, pure normalisation helpers shared by the importer and the skill entry
point. No third-party deps so anything can import them cheaply.
"""

from __future__ import annotations

import datetime as dt
import re


def clean(value) -> str | None:
    """Trim to a non-empty string, or None."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def norm_date(value) -> str | None:
    """Coerce a date-ish value into an ISO string (YYYY-MM-DD) or None.

    Accepts datetime/date objects, UK ``dd/mm/yyyy`` strings, and ISO strings.
    Anything it can't parse is returned trimmed and unchanged.
    """
    if value is None:
        return None
    if isinstance(value, (dt.datetime, dt.date)):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    if not s:
        return None
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)  # dd/mm/yyyy
    if m:
        d, mth, y = (int(x) for x in m.groups())
        try:
            return dt.date(y, mth, d).strftime("%Y-%m-%d")
        except ValueError:
            return s
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)  # iso-ish
    if m:
        y, mth, d = (int(x) for x in m.groups())
        try:
            return dt.date(y, mth, d).strftime("%Y-%m-%d")
        except ValueError:
            return s
    return s


def norm_status(value) -> str:
    """Default to 'Found'; treat the legacy literal 'Not Applied' as 'Found'."""
    s = clean(value) or "Found"
    return "Found" if s.lower() == "not applied" else s


def parse_job_id(link: str | None) -> str | None:
    """Pull the numeric job-id out of a job URL (the stable dedupe key)."""
    if not link:
        return None
    m = re.search(r"/(\d{6,})", link)
    return m.group(1) if m else None


def tc_key(title: str | None, company: str | None) -> str:
    """Fallback dedupe key (normalised title|company) for rows with no job-id."""
    def n(x):
        return re.sub(r"\s+", " ", (x or "").strip().lower())

    return f"{n(title)}|{n(company)}"
