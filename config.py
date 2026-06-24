"""Central configuration.

All environment-specific paths are read from environment variables (optionally
loaded from a local ``.env`` file) so nothing machine-specific is hardcoded in
the source. Copy ``.env.example`` to ``.env`` to override the defaults.
"""

from __future__ import annotations

import os
from pathlib import Path

try:  # python-dotenv is optional — plain environment variables work without it.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent


def _path_env(name: str, default: Path | None) -> Path | None:
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw else default


# The tracker database — the canonical store. Defaults to ./jobs.db in the repo.
DB_PATH = _path_env("JOBTRACKER_DB", PROJECT_ROOT / "jobs.db")

# Optional: a spreadsheet to import via migrate.py. No default — pass --xlsx or
# set JOBTRACKER_XLSX to your own file.
XLSX_PATH = _path_env("JOBTRACKER_XLSX", None)

# Optional: an external SQLite database that some other tool writes new roles
# into (e.g. a scraper or automation), for import_jobs.py to pull from.
IMPORT_DB_PATH = _path_env("JOBTRACKER_IMPORT_DB", None)

# Where generated cover-letter drafts are saved. Defaults to ./cover_letters.
COVER_LETTER_DIR = _path_env("JOBTRACKER_COVER_LETTER_DIR", PROJECT_ROOT / "cover_letters")

# Where generated CV drafts are saved. Defaults to ./cvs.
CV_DIR = _path_env("JOBTRACKER_CV_DIR", PROJECT_ROOT / "cvs")

# Profile data the in-app CV builder reads (kept out of the repo — copy
# profile.example.json to profile.json and fill it in).
PROFILE_PATH = _path_env("JOBTRACKER_PROFILE", PROJECT_ROOT / "profile.json")
