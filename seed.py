"""Load demo data into the tracker so a fresh install has something to show.

    python seed.py                 # load sample_jobs.csv into jobs.db
    python seed.py --reset         # wipe jobs.db first, then load

Reads a CSV whose header row matches the tracker's columns (see sample_jobs.csv).
This is for trying the app out — delete the rows (or the database) when you're
ready to track real applications.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import db
from normalize import clean, norm_date, norm_status, parse_job_id

DEFAULT_CSV = Path(__file__).with_name("sample_jobs.csv")
DATE_FIELDS = {"date_found", "posted", "date_applied"}


def load_csv(csv_path: Path | str = DEFAULT_CSV, target_db=None, reset: bool = False) -> int:
    csv_path = Path(csv_path)
    target_db = target_db if target_db is not None else db.DB_PATH
    if reset and Path(target_db).exists():
        with db.connect(target_db) as conn:
            conn.execute("DROP TABLE IF EXISTS jobs")
    db.init_db(target_db)

    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    inserted = 0
    with db.connect(target_db) as conn:
        for row in rows:
            data = {}
            for field in db.FIELDS:
                value = row.get(field)
                if field == "status":
                    data[field] = norm_status(value)
                elif field in DATE_FIELDS:
                    data[field] = norm_date(value)
                else:
                    data[field] = clean(value)
            if not data.get("title"):
                continue
            data["source_job_id"] = parse_job_id(data.get("link"))
            db.insert_job(conn, data)
            inserted += 1
        conn.commit()
    return inserted


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed the tracker with demo data.")
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--db", dest="target_db", type=Path, default=db.DB_PATH)
    ap.add_argument("--reset", action="store_true", help="Wipe the database first")
    args = ap.parse_args()

    count = load_csv(args.csv, args.target_db, reset=args.reset)
    print(f"Seeded {count} demo roles into {args.target_db}.")


if __name__ == "__main__":
    main()
