"""Streamlit frontend for the local job application tracker.

Run with:  streamlit run app.py
Data lives in jobs.db (SQLite); see migrate.py for the initial import.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

import db

st.set_page_config(page_title="Job Application Tracker", page_icon="🎯", layout="wide")

DISPLAY_COLS = ["id", *db.FIELDS]


# --------------------------------------------------------------------------- #
# Data access
# --------------------------------------------------------------------------- #
# ttl keeps the view live: rows written by an external script (e.g. import_jobs)
# surface within a few seconds on the next interaction/rerun.
@st.cache_data(ttl=5)
def load_df() -> pd.DataFrame:
    db.init_db()
    with db.connect() as conn:
        rows = [dict(r) for r in db.fetch_all(conn)]
    df = pd.DataFrame(rows, columns=[*DISPLAY_COLS, "source_job_id", "created_at", "updated_at"])
    return df[DISPLAY_COLS].copy()


def refresh() -> None:
    load_df.clear()


def _norm(v) -> str | None:
    """Normalise a cell for comparison / storage: blanks -> None."""
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    s = str(v).strip()
    return s or None


def persist_changes(edited: pd.DataFrame, shown_ids: set[int]) -> dict[str, int]:
    """Diff the edited grid against the DB and apply inserts/updates/deletes."""
    counts = {"added": 0, "updated": 0, "deleted": 0}
    with db.connect() as conn:
        originals = {r["id"]: dict(r) for r in db.fetch_all(conn)}
        edited_ids: set[int] = set()

        for _, row in edited.iterrows():
            rid = row.get("id")
            data = {f: _norm(row.get(f)) for f in db.FIELDS}
            if not data.get("title"):
                continue  # ignore empty trailing rows
            data.setdefault("status", None)
            data["status"] = data["status"] or "Found"
            data["source_job_id"] = _parse_job_id(data.get("link"))

            if rid is None or (isinstance(rid, float) and pd.isna(rid)):
                db.insert_job(conn, data)
                counts["added"] += 1
            else:
                rid = int(rid)
                edited_ids.add(rid)
                orig = originals.get(rid)
                if orig is None:
                    continue
                if any(_norm(orig.get(f)) != data.get(f) for f in db.FIELDS):
                    db.update_job(conn, rid, data)
                    counts["updated"] += 1

        # A row that was displayed but is now gone from the grid was deleted.
        for rid in shown_ids - edited_ids:
            db.delete_job(conn, rid)
            counts["deleted"] += 1
        conn.commit()
    return counts


def _parse_job_id(link: str | None) -> str | None:
    import re

    if not link:
        return None
    m = re.search(r"/(\d{6,})", link)
    return m.group(1) if m else None


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
df = load_df()

st.title("🎯 Job Application Tracker")
st.caption("Local SQLite + Streamlit · your job applications, tracked on your machine")

# --- Metrics --------------------------------------------------------------- #
today = dt.date.today()
week_ago = today - dt.timedelta(days=7)


def _applied_recently(s: pd.Series) -> int:
    dates = pd.to_datetime(s, errors="coerce").dt.date
    return int(((dates >= week_ago) & (dates <= today)).sum())


m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total roles", len(df))
m2.metric("Applied", int((df["status"] == "Applied").sum()))
m3.metric(
    "Shortlisted / Interview",
    int(df["status"].isin(["Shortlisted", "Interview", "Offer"]).sum()),
)
m4.metric("Open pipeline", int((df["status"] == "Found").sum()))
m5.metric("Applied this week", _applied_recently(df["date_applied"]))

# --- Filters --------------------------------------------------------------- #
_found_dates = pd.to_datetime(df["date_found"], errors="coerce").dt.date.dropna()
_min_found = _found_dates.min() if not _found_dates.empty else today
_max_found = _found_dates.max() if not _found_dates.empty else today

with st.sidebar:
    if st.button("🔄 Refresh data", width="stretch"):
        refresh()
        st.rerun()
    if st.button("⬇️ Import new roles", width="stretch",
                 help="Pull new roles from the external database set in JOBTRACKER_IMPORT_DB"):
        import import_jobs

        result = import_jobs.import_jobs()
        refresh()
        if not result["source_exists"]:
            st.warning(
                "No import source found. Set JOBTRACKER_IMPORT_DB in .env to an "
                "external SQLite database, then try again."
            )
        else:
            st.success(
                f"Imported {result['inserted']} new role(s); "
                f"{result['skipped']} already in the tracker."
            )
            st.rerun()
    st.caption("Live view · auto-refreshes every few seconds")
    st.divider()

    st.header("Filters")
    all_statuses = sorted(s for s in df["status"].dropna().unique())
    status_opts = list(dict.fromkeys([*db.STATUSES, *all_statuses]))
    status_sel = st.multiselect("Status", status_opts, default=[])
    type_opts = sorted(t for t in df["type"].dropna().unique())
    type_sel = st.multiselect("Type", type_opts, default=[])
    company_opts = sorted(c for c in df["company"].dropna().unique())
    company_sel = st.multiselect("Recruiter / company", company_opts, default=[])
    date_range = st.date_input(
        "Found between",
        value=(_min_found, _max_found),
        min_value=_min_found,
        max_value=_max_found,
        help="Filters on Date Found",
    )
    search = st.text_input("Search title / company / notes", "")
    st.divider()
    st.caption(
        "Edit cells inline, add a role in the blank bottom row, or select a "
        "row and press ⌫ to delete. Click **Save changes** to persist."
    )

view = df.copy()
if status_sel:
    view = view[view["status"].isin(status_sel)]
if type_sel:
    view = view[view["type"].isin(type_sel)]
if company_sel:
    view = view[view["company"].isin(company_sel)]
if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    lo, hi = date_range
    found = pd.to_datetime(view["date_found"], errors="coerce").dt.date
    view = view[(found.isna()) | ((found >= lo) & (found <= hi))]
if search.strip():
    q = search.strip().lower()
    hay = (
        view["title"].fillna("").str.lower()
        + " " + view["company"].fillna("").str.lower()
        + " " + view["fit_notes"].fillna("").str.lower()
    )
    view = view[hay.str.contains(q, regex=False)]

st.subheader(f"Roles ({len(view)})")

# --- Status breakdown ------------------------------------------------------ #
with st.expander("📊 Status breakdown", expanded=False):
    counts = df["status"].fillna("(none)").value_counts()
    st.bar_chart(counts)

# --- Editable grid --------------------------------------------------------- #
status_options = list(dict.fromkeys([*db.STATUSES, *all_statuses]))
type_options = list(dict.fromkeys(["Contract", "Permanent", *type_opts]))

column_config = {
    "id": st.column_config.NumberColumn("id", disabled=True, width="small"),
    "date_found": st.column_config.TextColumn("Found", help="YYYY-MM-DD", width="small"),
    "title": st.column_config.TextColumn("Title", width="large", required=True),
    "company": st.column_config.TextColumn("Company / Recruiter", width="medium"),
    "type": st.column_config.SelectboxColumn("Type", options=type_options, width="small"),
    "rate": st.column_config.TextColumn("Rate / Salary", width="small"),
    "location": st.column_config.TextColumn("Location", width="medium"),
    "posted": st.column_config.TextColumn("Posted", help="YYYY-MM-DD", width="small"),
    "link": st.column_config.LinkColumn("Link", display_text="open", width="small"),
    "fit_notes": st.column_config.TextColumn("Fit notes", width="large"),
    "status": st.column_config.SelectboxColumn("Status", options=status_options, width="small"),
    "cv_version": st.column_config.TextColumn("CV version", width="medium"),
    "date_applied": st.column_config.TextColumn("Applied", help="YYYY-MM-DD", width="small"),
    "outcome": st.column_config.TextColumn("Outcome / Next step", width="large"),
}

edited = st.data_editor(
    view,
    column_config=column_config,
    column_order=DISPLAY_COLS,
    num_rows="dynamic",
    hide_index=True,
    width="stretch",
    key="grid",
)

shown_ids = {int(i) for i in view["id"].dropna().tolist()}

col_save, col_export, _ = st.columns([1, 1, 4])
with col_save:
    if st.button("💾 Save changes", type="primary", width="stretch"):
        result = persist_changes(edited, shown_ids)
        refresh()
        st.success(
            f"Saved · {result['added']} added, {result['updated']} updated, "
            f"{result['deleted']} deleted."
        )
        st.rerun()
with col_export:
    st.download_button(
        "⬇️ Export CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"job_tracker_{today.isoformat()}.csv",
        mime="text/csv",
        width="stretch",
    )
