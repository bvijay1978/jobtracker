"""Streamlit frontend for the local job application tracker.

Run with:  streamlit run app.py
Data lives in jobs.db (SQLite); see migrate.py for the initial import.
"""

from __future__ import annotations

import datetime as dt
import hmac
import os
from urllib.parse import quote

import pandas as pd
import streamlit as st

import config
import db
import documents as doc_lib
import followup_queue

st.set_page_config(page_title="Job Application Tracker", page_icon="🎯", layout="wide")

# --------------------------------------------------------------------------- #
# Auth (optional — only active for the shared Render deployment)
# --------------------------------------------------------------------------- #
# Local single-user runs never set these, so _require_login() returns None
# immediately and the app behaves exactly as it always has.
APP_PASSWORD = os.environ.get("APP_PASSWORD")
APP_USERS = os.environ.get("APP_USERS", "")  # e.g. "Vijay:vijay,Radha:radha"


def _parsed_users() -> dict[str, str]:
    """{display name: slug} from APP_USERS."""
    users: dict[str, str] = {}
    for pair in APP_USERS.split(","):
        pair = pair.strip()
        if not pair:
            continue
        name, _, slug = pair.partition(":")
        users[name.strip()] = (slug or name).strip().lower()
    return users


def _require_login() -> str | None:
    """Gate the app behind a shared password, then (if configured) a 'who are
    you' picker. Returns the selected user's slug — used to pick their
    Postgres schema, profile file and CV/cover-letter folders — or None in
    local single-user mode or single-password-no-picker mode.
    """
    if not APP_PASSWORD:
        return None

    if not st.session_state.get("authed"):
        st.title("🎯 Job Application Tracker")
        pw = st.text_input("Password", type="password")
        if st.button("Log in"):
            if hmac.compare_digest(pw, APP_PASSWORD):
                st.session_state.authed = True
                st.rerun()
            else:
                st.error("Wrong password.")
        st.stop()

    users = _parsed_users()
    if not users:
        return None

    if not st.session_state.get("current_user"):
        st.title("🎯 Job Application Tracker")
        pick = st.selectbox("Who are you?", list(users))
        if st.button("Continue"):
            st.session_state.current_user = users[pick]
            st.rerun()
        st.stop()

    return st.session_state.current_user


current_user = _require_login()

DISPLAY_COLS = ["id", *db.FIELDS]


# --------------------------------------------------------------------------- #
# Data access
# --------------------------------------------------------------------------- #
# ttl keeps the view live: rows written by an external script (e.g. import_jobs)
# surface within a few seconds on the next interaction/rerun.
@st.cache_data(ttl=5)
def load_df(user: str | None) -> pd.DataFrame:
    db.init_db(schema=user)
    with db.connect(schema=user) as conn:
        rows = [dict(r) for r in db.fetch_all(conn)]
    cols = [*DISPLAY_COLS, *db.APP_COLUMNS]
    df = pd.DataFrame(rows, columns=[*cols, "source_job_id", "created_at", "updated_at"])
    return df[cols].copy()


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


def persist_changes(
    edited: pd.DataFrame, shown_ids: set[int], user: str | None
) -> dict[str, int]:
    """Diff the edited grid against the DB and apply inserts/updates/deletes."""
    counts = {"added": 0, "updated": 0, "deleted": 0}
    with db.connect(schema=user) as conn:
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


DRAFT_CV = "Draft CV"
DRAFT_CV_CL = "Draft CV & Cover Letter"


def persist_status_changes(edited: pd.DataFrame, user: str | None) -> dict:
    """Apply To-action status edits.

    'Draft CV' / 'Draft CV & Cover Letter' are a *queue only* — the app writes no
    document (it has no LLM and can't read the job description). Claude later reads
    each queued role's JD and writes the optimised screening CV, then settles the
    role to 'CV Drafted' (see screening_queue.py and ADR-008). All status changes
    are written through as-is.
    """
    result = {"updated": 0, "queued": 0, "errors": []}
    with db.connect(schema=user) as conn:
        originals = {r["id"]: dict(r) for r in db.fetch_all(conn)}
        for _, row in edited.iterrows():
            rid = row.get("id")
            if rid is None or (isinstance(rid, float) and pd.isna(rid)):
                continue
            rid = int(rid)
            orig = originals.get(rid)
            if orig is None or _norm(orig.get("status")) == (_norm(row.get("status")) or "Found"):
                continue
            new_status = _norm(row.get("status")) or "Found"
            db.update_job(conn, rid, {"status": new_status})
            if new_status in (DRAFT_CV, DRAFT_CV_CL):
                result["queued"] += 1
            else:
                result["updated"] += 1
        conn.commit()
    return result


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
df = load_df(current_user)

# Archived roles ("Ended"/closed) drop out of every active view below and live in
# the 📦 Archive section — still searchable if a recruiter calls about a closed role.
_all_df = df
_arch_mask = df["archived"].fillna(0).astype(int) == 1
archived_df = df[_arch_mask].sort_values("date_found", ascending=False, na_position="last")
df = df[~_arch_mask].copy()

st.title("🎯 Job Application Tracker")
st.caption("Local SQLite + Streamlit · your job applications, tracked on your machine")

# --- Metrics --------------------------------------------------------------- #
today = dt.date.today()
week_ago = today - dt.timedelta(days=7)


def _applied_recently(s: pd.Series) -> int:
    # Compare as Timestamps, not .dt.date — pandas/numpy version differences
    # between environments (e.g. local vs. Render's freshly resolved pandas)
    # can make .dt.date not reduce to plain python `date` objects, breaking a
    # `date`-vs-`date` comparison. Timestamp-vs-Timestamp is stable everywhere.
    dates = pd.to_datetime(s, errors="coerce")
    return int(((dates >= pd.Timestamp(week_ago)) & (dates <= pd.Timestamp(today))).sum())


def _follow_up_due_mask(d: pd.DataFrame) -> pd.Series:
    """Applied roles with a recruiter contact, ≥2 working days since applying,
    follow-up not yet sent. The due rule itself lives in followup_queue so the
    app and the agent can never disagree."""
    return (
        (d["status"] == "Applied")
        & (d["contact_email"].fillna("").astype(str).str.strip() != "")
        & ~d["follow_up_status"].fillna("").astype(str).str.strip()
            .str.lower().str.startswith("sent")
        & d["date_applied"].map(followup_queue.is_due)
    )


# "To action" = found but not yet applied to or passed — the work queue.
ACTIONED_STATUSES = {
    "Applied", "Shortlisted", "Interview", "Offer", "Pass", "Rejected",
    "Expired", "Not Applicable", "Not Applying",
}
to_action = df[~df["status"].isin(ACTIONED_STATUSES)].sort_values(
    "date_found", ascending=False, na_position="last"
)

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Active roles", len(df),
          help=f"{len(archived_df)} archived (Ended) — see the Archive section")
m2.metric("Applied", int((df["status"] == "Applied").sum()))
m3.metric(
    "Shortlisted / Interview",
    int(df["status"].isin(["Shortlisted", "Interview", "Offer"]).sum()),
)
m4.metric("🆕 To action", len(to_action))
m5.metric("Applied this week", _applied_recently(df["date_applied"]))
_fu_due = df[_follow_up_due_mask(df)].copy()
m6.metric(
    "📮 Follow-ups due",
    int((_fu_due["follow_up"].fillna(0).astype(int) != 2).sum()),
    help=(
        "Applied roles with a recruiter contact where 2+ working days have "
        "passed since applying, not yet sent or opted out — see the "
        "Follow-ups section."
    ),
)

# --- Screening-CV queue banner (persistent) ------------------------------- #
# Roles set to Draft CV are a queue only — the app writes nothing; Claude drafts
# them (ADR-008). "...& Cover Letter" additionally queues a JD-tailored letter,
# authored in the same pass (ADR-012). Surface the queue and the copy-prompt.
_cv_queued = df[df["status"].isin(["Draft CV", "Draft CV & Cover Letter"])]
_letter_queued = df[df["status"] == "Draft CV & Cover Letter"]
if not _cv_queued.empty:
    with st.container(border=True):
        st.markdown(f"#### 🤖 {len(_cv_queued)} role(s) queued for a screening CV")
        letter_note = (
            f" {len(_letter_queued)} also queued for a JD-tailored cover letter."
            if not _letter_queued.empty else ""
        )
        st.caption(
            "Set to **Draft CV** (or **Draft CV & Cover Letter**) but not yet written — "
            "the app queues, Claude drafts. Copy the prompt below into Claude (Cowork); it "
            "reads each job description and writes the optimised screening CV, then settles "
            f"the role to **CV Drafted**.{letter_note}"
        )
        st.code("draft the queued screening CVs", language=None)

# --- Contact-resolver queue ("Needs a contact") --------------------------- #
# A follow-up email needs a recruiter address. Live roles (Applied+) with no
# contact_email are queued here; the app can't reach Gmail/web/LinkedIn (ADR-002),
# so Claude resolves a *verified* address (inbox → LinkedIn → company site, never
# a guess) and files it via contact_queue.record_contact. Roles resolved to 'none'
# (no reachable email) drop out so the queue doesn't nag.
_needs_contact = df[
    df["status"].isin(["Applied", "Shortlisted", "Interview", "Offer"])
    & (df["contact_email"].fillna("").astype(str).str.strip() == "")
    & (df["contact_source"].fillna("").astype(str).str.strip() != "none")
]
if not _needs_contact.empty:
    with st.container(border=True):
        st.markdown(f"#### 📇 {len(_needs_contact)} live role(s) need a recruiter contact")
        st.caption(
            "Live applications with no recruiter email yet — needed before a follow-up "
            "can be drafted. The app can't reach Gmail or the web; copy the prompt into "
            "Claude (Cowork) and it resolves a **verified** address "
            "(your inbox → LinkedIn → company site), never a guess."
        )
        st.code("resolve contacts for the follow-up queue", language=None)
        with st.expander(f"Show the {len(_needs_contact)} role(s)", expanded=False):
            st.dataframe(
                _needs_contact[["id", "date_applied", "title", "company", "status", "link"]],
                column_config={
                    "date_applied": st.column_config.TextColumn("Applied", width="small"),
                    "link": st.column_config.LinkColumn(
                        "Link", display_text="open", width="small",
                    ),
                },
                hide_index=True,
                width="stretch",
            )

# --- Follow-ups due -------------------------------------------------------- #
# Applied roles with a verified contact, 2+ working days old, follow-up not yet
# sent. Everything starts ticked (opt-out) — untick to skip, Save, then copy the
# prompt. Claude sweeps Gmail for replies first (a reply beats a nudge), writes
# a short contextual Gmail DRAFT per ticked role (it never sends), and files the
# draft link here. You review and hit Send in Gmail, then mark the row sent.
if not _fu_due.empty:
    fu_df = _fu_due.copy()
    fu_df["send"] = fu_df["follow_up"].fillna(0).astype(int) != 2
    _fu_applied = pd.to_datetime(fu_df["date_applied"], errors="coerce")
    fu_df["days"] = (pd.Timestamp(today) - _fu_applied).dt.days
    fu_df = fu_df.sort_values("date_applied", na_position="last")
    _orig_send = dict(zip(fu_df["id"].astype(int), fu_df["send"]))

    with st.container(border=True):
        st.markdown(
            f"#### 📮 Follow-ups due — {int(fu_df['send'].sum())} ticked of {len(fu_df)} due"
        )
        st.caption(
            "Untick any role you'd rather not chase and **Save selections**. Then copy the "
            "prompt into Claude (Cowork): it checks Gmail for replies first, writes a short "
            "**draft** per ticked role (it never sends), and links each draft below. "
            "Open the draft, edit, hit **Send** in Gmail — then mark it sent here."
        )
        fu_edited = st.data_editor(
            fu_df[[
                "send", "id", "days", "date_applied", "title", "company",
                "contact_email", "contact_source", "follow_up_status", "follow_up_draft",
            ]],
            column_config={
                "send": st.column_config.CheckboxColumn(
                    "Send", help="Untick to skip this role", width="small",
                ),
                "id": st.column_config.NumberColumn("id", disabled=True, width="small"),
                "days": st.column_config.NumberColumn(
                    "Days", disabled=True, width="small",
                    help="Days since you applied",
                ),
                "date_applied": st.column_config.TextColumn(
                    "Applied", disabled=True, width="small",
                ),
                "title": st.column_config.TextColumn("Title", disabled=True, width="large"),
                "company": st.column_config.TextColumn(
                    "Company / Recruiter", disabled=True, width="medium",
                ),
                "contact_email": st.column_config.TextColumn(
                    "Contact", disabled=True, width="medium",
                ),
                "contact_source": st.column_config.TextColumn(
                    "Source", disabled=True, width="small",
                    help="How the contact was verified — named-inbox / named-verified / "
                         "dept-inbox (never guessed)",
                ),
                "follow_up_status": st.column_config.TextColumn(
                    "Status", disabled=True, width="small",
                ),
                "follow_up_draft": st.column_config.LinkColumn(
                    "Draft", display_text="open draft", disabled=True, width="small",
                ),
            },
            num_rows="fixed",
            hide_index=True,
            width="stretch",
            key="followup_grid",
        )

        fc1, fc2 = st.columns([1, 2.4])
        with fc1:
            if st.button("💾 Save selections", key="save_followups", width="stretch"):
                changed = 0
                with db.connect(schema=current_user) as conn:
                    for _, row in fu_edited.iterrows():
                        rid = int(row["id"])
                        new = bool(row["send"])
                        if new != bool(_orig_send.get(rid)):
                            db.update_job(conn, rid, {"follow_up": 1 if new else 2})
                            changed += 1
                    conn.commit()
                refresh()
                st.success(f"Saved — {changed} selection change(s).")
                st.rerun()
        with fc2:
            st.code("draft the due follow-up emails", language=None)

        _drafted = fu_df[
            fu_df["follow_up_status"].fillna("").str.lower().str.startswith("draft")
        ]
        if not _drafted.empty:
            sent_opts = {
                f"{int(r['id'])} · {r['title']} — {r['company']}": int(r["id"])
                for _, r in _drafted.iterrows()
            }
            sc1, sc2 = st.columns([3, 1])
            sent_pick = sc1.selectbox(
                "Mark a follow-up as sent", list(sent_opts),
                key="fu_sent_pick", label_visibility="collapsed",
            )
            if sc2.button("✅ Mark sent", key="fu_mark_sent", width="stretch"):
                with db.connect(schema=current_user) as conn:
                    followup_queue.mark_sent(conn, sent_opts[sent_pick])
                    conn.commit()
                refresh()
                st.rerun()

# --- To action: found, not yet applied or passed -------------------------- #
if not to_action.empty:
    _ta_status_opts = list(dict.fromkeys([*db.STATUSES, *sorted(df["status"].dropna().unique())]))
    with st.container(border=True):
        st.markdown(f"#### 🆕 To action — {len(to_action)} role(s) not yet applied to or passed")
        st.caption(
            "Set a **Status** and click **Save actions**. Choosing **Draft CV** *queues* "
            "the role — Claude later reads its job description and writes an optimised "
            "screening CV. Applied / Pass / … drop the role off this queue."
        )
        ta_edited = st.data_editor(
            to_action[[
                "id", "date_found", "title", "company", "type", "rate", "location",
                "link", "fit_notes", "cv_version", "status",
            ]],
            column_config={
                "id": st.column_config.NumberColumn("id", disabled=True, width="small"),
                "date_found": st.column_config.TextColumn("Found", disabled=True, width="small"),
                "title": st.column_config.TextColumn("Title", disabled=True, width="large"),
                "company": st.column_config.TextColumn(
                    "Company / Recruiter", disabled=True, width="medium",
                ),
                "type": st.column_config.TextColumn("Type", disabled=True, width="small"),
                "rate": st.column_config.TextColumn("Rate", disabled=True, width="small"),
                "location": st.column_config.TextColumn("Location", disabled=True, width="medium"),
                "link": st.column_config.LinkColumn(
                    "Link", display_text="open", disabled=True, width="small",
                ),
                "fit_notes": st.column_config.TextColumn("Fit notes", disabled=True, width="large"),
                "cv_version": st.column_config.TextColumn(
                    "CV draft", disabled=True, width="medium",
                    help="Drafted CV filename — open it from your CVs folder",
                ),
                "status": st.column_config.SelectboxColumn(
                    "Status", options=_ta_status_opts, width="small", required=True,
                ),
            },
            num_rows="fixed",
            hide_index=True,
            width="stretch",
            key="to_action_grid",
        )
        if st.button("✅ Save actions", type="primary", key="save_to_action"):
            res = persist_status_changes(ta_edited, current_user)
            refresh()
            parts = []
            if res["updated"]:
                parts.append(f"{res['updated']} status update(s)")
            if res["queued"]:
                parts.append(f"{res['queued']} role(s) queued for CV drafting")
            st.success("Saved — " + (", ".join(parts) if parts else "no changes") + ".")
            if res["queued"]:
                st.info(
                    "🤖 Queued for a screening CV (and a JD-tailored cover letter, if you "
                    "picked **Draft CV & Cover Letter**) — ask Claude in Cowork to "
                    "“draft the queued screening CVs”. It reads each job description "
                    "and writes the optimised draft(s) (you review before sending)."
                )
            for err in res["errors"]:
                st.warning(err)
            if not res["errors"]:
                st.rerun()

# --- Filters --------------------------------------------------------------- #
_found_ts = pd.to_datetime(df["date_found"], errors="coerce").dropna()
_min_found = _found_ts.min().date() if not _found_ts.empty else today
_max_found = _found_ts.max().date() if not _found_ts.empty else today

with st.sidebar:
    if st.button("🔄 Refresh data", width="stretch"):
        refresh()
        st.rerun()
    if st.button("⬇️ Import new roles", width="stretch",
                 help="Pull new roles from the external database set in JOBTRACKER_IMPORT_DB"):
        import import_jobs

        result = import_jobs.import_jobs(schema=current_user)
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
    found = pd.to_datetime(view["date_found"], errors="coerce")
    view = view[(found.isna()) | ((found >= pd.Timestamp(lo)) & (found <= pd.Timestamp(hi)))]
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
    "cover_letter": st.column_config.TextColumn(
        "Cover letter", width="medium", disabled=True,
        help="Generated draft filename — use the Generate cover letter button below",
    ),
    "date_applied": st.column_config.TextColumn("Applied", help="YYYY-MM-DD", width="small"),
    "outcome": st.column_config.TextColumn("Outcome / Next step", width="large"),
}

edited = st.data_editor(
    view[DISPLAY_COLS],
    column_config=column_config,
    column_order=DISPLAY_COLS,
    num_rows="dynamic",
    hide_index=True,
    width="stretch",
    key="grid",
)

shown_ids = {int(i) for i in view["id"].dropna().tolist()}

# Gmail deep-link: open Gmail searched for recent mail about active applications.
_active = df[df["status"].isin(["Applied", "Shortlisted", "Interview", "Offer"])]
_companies = [c for c in _active["company"].dropna().unique().tolist() if str(c).strip()][:15]
if _companies:
    _query = "newer_than:90d (" + " OR ".join(f'"{c}"' for c in _companies) + ")"
else:
    _query = (
        'newer_than:30d (subject:(application OR interview OR role OR vacancy) '
        'OR "your application" OR "next steps")'
    )
gmail_url = "https://mail.google.com/mail/u/0/#search/" + quote(_query)

col_save, col_export, col_gmail, _ = st.columns([1, 1, 1.4, 2.6])
with col_save:
    if st.button("💾 Save changes", type="primary", width="stretch"):
        result = persist_changes(edited, shown_ids, current_user)
        refresh()
        st.success(
            f"Saved · {result['added']} added, {result['updated']} updated, "
            f"{result['deleted']} deleted."
        )
        st.rerun()
with col_export:
    st.download_button(
        "⬇️ Export CSV",
        data=_all_df.to_csv(index=False).encode("utf-8"),
        file_name=f"job_tracker_{today.isoformat()}.csv",
        help="Full export, including archived roles.",
        mime="text/csv",
        width="stretch",
    )
with col_gmail:
    st.link_button(
        "📧 Search Gmail for replies", gmail_url, width="stretch",
        help=(
            "Opens Gmail in a new browser tab, pre-searched for emails from the last "
            "90 days mentioning the recruiters/companies you've applied to. It only "
            "opens a search — it does not read your inbox or change the tracker."
        ),
    )

# --- Archive --------------------------------------------------------------- #
st.divider()
with st.expander(f"📦 Archive — {len(archived_df)} ended / closed role(s)", expanded=False):
    st.caption(
        "Roles whose vacancy has **ended** (closed). They're off your active lists, "
        "but kept here — searchable if a recruiter follows up on a closed role. "
        "Un-archive any that come back to life."
    )
    if archived_df.empty:
        st.write("Nothing archived yet.")
    else:
        a_search = st.text_input("Search the archive", "", key="arch_search")
        a_view = archived_df
        if a_search.strip():
            q = a_search.strip().lower()
            hay = (a_view["title"].fillna("").str.lower() + " "
                   + a_view["company"].fillna("").str.lower())
            a_view = a_view[hay.str.contains(q, regex=False)]
        st.dataframe(
            a_view[["id", "date_found", "title", "company", "status", "contact_email", "link"]],
            column_config={
                "link": st.column_config.LinkColumn("Link", display_text="open", width="small"),
                "contact_email": st.column_config.TextColumn("Recruiter contact", width="medium"),
            },
            hide_index=True,
            width="stretch",
        )
        unarch = {f"{int(r['id'])} · {r['title']} — {r['company']}": int(r["id"])
                  for _, r in a_view.iterrows()}
        if unarch:
            uc1, uc2 = st.columns([3, 1])
            pick = uc1.selectbox("Un-archive", list(unarch), key="unarch_pick",
                                 label_visibility="collapsed")
            if uc2.button("♻️ Un-archive", width="stretch"):
                with db.connect(schema=current_user) as conn:
                    db.update_job(conn, unarch[pick], {"archived": 0})
                    conn.commit()
                refresh()
                st.rerun()

# --- Cover letters --------------------------------------------------------- #
st.divider()
st.subheader("✍️ Cover letters")
if df.empty:
    st.caption("Add a role first, then generate a cover-letter draft for it.")
else:
    role_map = {}
    for _, r in df.iterrows():
        company = r["company"] if pd.notna(r["company"]) else "—"
        title = r["title"] if pd.notna(r["title"]) else "(untitled)"
        role_map[f"{int(r['id'])} · {title} — {company}"] = int(r["id"])

    cl_pick, cl_btn = st.columns([3, 1])
    chosen = cl_pick.selectbox("Role", list(role_map), key="cl_role", label_visibility="collapsed")
    if cl_btn.button("✍️ Generate cover letter", width="stretch"):
        import cover_letter

        with db.connect(schema=current_user) as conn:
            row = dict(
                conn.execute("SELECT * FROM jobs WHERE id = ?", (role_map[chosen],)).fetchone()
            )
            path = cover_letter.generate_cover_letter(
                row,
                out_dir=config.cover_letter_dir_for(current_user),
                profile_path=config.profile_path_for(current_user),
            )
            db.update_job(conn, role_map[chosen], {"cover_letter": path.name})
            doc_bytes = path.read_bytes()
            doc_lib.save(
                conn, name=f"Cover Letter — {row['company']} — {row['title']}",
                category="Cover Letter", tags=doc_lib.role_tags(row), role_id=row["id"],
                filename=path.name, data=doc_bytes, mime_type=doc_lib.DOCX_MIME,
            )
            conn.commit()
        refresh()
        # Stash the bytes now — the rerun below re-executes the whole script, so
        # a download_button placed only inside this `if` would vanish immediately.
        st.session_state["last_cover_letter"] = (path.name, doc_bytes)
        st.rerun()

    if st.session_state.get("last_cover_letter"):
        cl_name, cl_bytes = st.session_state["last_cover_letter"]
        st.success(f"Draft saved — {cl_name}")
        st.download_button(
            "⬇️ Download cover letter", data=cl_bytes, file_name=cl_name, key="dl_cover_letter",
        )

    st.caption(
        "Drafts are saved to your cover-letters folder and the filename is "
        "recorded in the **Cover letter** column. It's a starting draft — finish "
        "the bracketed parts, or ask Claude for a fully tailored version."
    )

# --- AI-tailored CV & cover letter (optional — needs ANTHROPIC_API_KEY) --- #
# A third path alongside the offline button above and the "Draft CV & Cover
# Letter" agent queue (ADR-008/012): a direct in-app call to Claude, for a
# one-click JD-tailored draft with no separate chat needed. Entirely opt-in —
# unset, this section doesn't render and nothing else changes (ADR-013).
st.divider()
st.subheader("✨ AI-tailored CV & cover letter")
if not os.environ.get("ANTHROPIC_API_KEY"):
    st.caption(
        "Set `ANTHROPIC_API_KEY` to draft a JD-tailored CV and cover letter here in "
        "one click. Until then, use **Draft CV & Cover Letter** in the To-action queue "
        "above and ask Claude to process it — same output, via a chat instead of a button."
    )
elif df.empty:
    st.caption("Add a role first.")
else:
    ai_role_map = {}
    for _, r in df.iterrows():
        company = r["company"] if pd.notna(r["company"]) else "—"
        title = r["title"] if pd.notna(r["title"]) else "(untitled)"
        ai_role_map[f"{int(r['id'])} · {title} — {company}"] = int(r["id"])

    ai_pick = st.selectbox("Role", list(ai_role_map), key="ai_role", label_visibility="collapsed")
    jd_text = st.text_area(
        "Paste the job description", key="ai_jd_text", height=180,
        placeholder="Paste the full job ad here — the more detail, the better the draft.",
    )
    if st.button("✨ Draft tailored CV + cover letter", type="primary", width="stretch"):
        if not jd_text.strip():
            st.warning("Paste the job description first.")
        else:
            import ai_draft
            import cover_letter
            import screening_cv

            with db.connect(schema=current_user) as conn:
                row = dict(conn.execute(
                    "SELECT * FROM jobs WHERE id = ?", (ai_role_map[ai_pick],)
                ).fetchone())
            try:
                with st.spinner("Drafting with Claude…"):
                    payload = ai_draft.draft(
                        row, jd_text, profile_path=config.profile_path_for(current_user)
                    )
                screening = {
                    "target_title": payload.target_title,
                    "summary": payload.summary,
                    "core_skills": payload.core_skills,
                    "experience": [e.model_dump() for e in payload.experience],
                }
                cv_path = screening_cv.generate_screening_cv(
                    row, screening,
                    profile_path=config.profile_path_for(current_user),
                    out_dir=config.cv_dir_for(current_user),
                )
                cl_path = cover_letter.generate_cover_letter(
                    row, body_paragraphs=payload.cover_letter_paragraphs,
                    profile_path=config.profile_path_for(current_user),
                    out_dir=config.cover_letter_dir_for(current_user),
                )
                cv_bytes, cl_bytes = cv_path.read_bytes(), cl_path.read_bytes()
                with db.connect(schema=current_user) as conn:
                    db.update_job(conn, row["id"], {
                        "status": "CV Drafted", "cv_version": cv_path.name,
                        "cover_letter": cl_path.name,
                    })
                    tags = doc_lib.role_tags(row)
                    doc_lib.save(
                        conn, name=f"CV — {row['company']} — {row['title']}",
                        category="Resume", tags=tags, role_id=row["id"],
                        filename=cv_path.name, data=cv_bytes, mime_type=doc_lib.DOCX_MIME,
                    )
                    doc_lib.save(
                        conn, name=f"Cover Letter — {row['company']} — {row['title']}",
                        category="Cover Letter", tags=tags, role_id=row["id"],
                        filename=cl_path.name, data=cl_bytes, mime_type=doc_lib.DOCX_MIME,
                    )
                    conn.commit()
                refresh()
                st.session_state["last_ai_draft"] = {
                    "cv": (cv_path.name, cv_bytes),
                    "cl": (cl_path.name, cl_bytes),
                }
                st.rerun()
            except Exception as e:
                st.error(f"Drafting failed: {e}")

    if st.session_state.get("last_ai_draft"):
        draft_files = st.session_state["last_ai_draft"]
        st.success("Draft saved — status set to **CV Drafted**.")
        dl1, dl2 = st.columns(2)
        cv_name, cv_bytes = draft_files["cv"]
        cl_name, cl_bytes = draft_files["cl"]
        dl1.download_button("⬇️ Download CV", data=cv_bytes, file_name=cv_name, key="dl_ai_cv")
        dl2.download_button(
            "⬇️ Download cover letter", data=cl_bytes, file_name=cl_name, key="dl_ai_cl",
        )

    st.caption(
        "Reads the pasted job description and your profile, writes a keyword-matched "
        "screening CV and a tailored cover letter (same honesty rule as the agent queue — "
        "genuine experience only), and saves both. Review before sending."
    )

# --- Documents library ------------------------------------------------------ #
# Stored in the database (ADR-014), not local disk, so — unlike the generated
# files above — these survive restarts/redeploys on the hosted deployment.
# The two generation paths above auto-save into this same library, tagged by
# role, so a CV drafted for one role can be found and reused for similar ones.
st.divider()
st.subheader("📁 Documents")

with db.connect(schema=current_user) as conn:
    doc_rows = [dict(r) for r in db.fetch_documents(conn)]
doc_cols = [
    "id", "name", "category", "tags", "role_id", "filename",
    "mime_type", "size_bytes", "created_at",
]
docs_df = pd.DataFrame(doc_rows, columns=doc_cols)
role_lookup = {
    int(r["id"]): f"{r['title']} — {r['company']}"
    for _, r in _all_df.iterrows() if pd.notna(r["id"])
}

with st.expander("⬆️ Upload a document", expanded=docs_df.empty):
    up_file = st.file_uploader("File", key="doc_upload")
    up_name = st.text_input(
        "Name", value=(up_file.name if up_file else ""), key="doc_name",
    )
    up_cat = st.selectbox("Category", doc_lib.CATEGORIES, key="doc_cat")
    up_tags = st.text_input(
        "Tags (comma-separated)", key="doc_tags",
        help="e.g. FS, Senior PM — used to find and reuse this document for similar roles",
    )
    up_role_opts = {"— none —": None, **{v: k for k, v in role_lookup.items()}}
    up_role = st.selectbox("Linked role (optional)", list(up_role_opts), key="doc_role")
    if st.button("💾 Save document", key="doc_save"):
        if not up_file:
            st.warning("Choose a file first.")
        else:
            with db.connect(schema=current_user) as conn:
                doc_lib.save(
                    conn, name=up_name or up_file.name, category=up_cat, tags=up_tags,
                    role_id=up_role_opts[up_role], filename=up_file.name,
                    data=up_file.getvalue(), mime_type=up_file.type,
                )
                conn.commit()
            st.rerun()

if docs_df.empty:
    st.caption("No documents yet — upload one above, or generate a CV/cover letter for a role.")
else:
    all_tags = sorted({
        t.strip() for tags in docs_df["tags"].dropna() for t in tags.split(",") if t.strip()
    })
    tag_filter = st.multiselect("Filter by tag", all_tags, key="doc_tag_filter")
    view_docs = docs_df
    if tag_filter:
        view_docs = view_docs[view_docs["tags"].fillna("").apply(
            lambda t: any(tag in [x.strip() for x in t.split(",")] for tag in tag_filter)
        )]

    display_df = view_docs.copy()
    display_df["role"] = display_df["role_id"].map(
        lambda rid: role_lookup.get(int(rid), "") if pd.notna(rid) else ""
    )
    st.dataframe(
        display_df[["name", "category", "tags", "role", "size_bytes", "created_at"]],
        column_config={
            "size_bytes": st.column_config.NumberColumn("Size (bytes)"),
            "created_at": st.column_config.TextColumn("Uploaded"),
        },
        hide_index=True,
        width="stretch",
    )

    doc_pick_opts = {f"{int(r['id'])} · {r['name']}": int(r["id"]) for _, r in view_docs.iterrows()}
    doc_pick = st.selectbox("Select a document", list(doc_pick_opts), key="doc_pick")
    with db.connect(schema=current_user) as conn:
        picked = dict(db.fetch_document(conn, doc_pick_opts[doc_pick]))

    dcol1, dcol2 = st.columns(2)
    dcol1.download_button(
        "⬇️ Download", data=bytes(picked["data"]), file_name=picked["filename"],
        mime=picked["mime_type"] or "application/octet-stream", key="doc_dl", width="stretch",
    )
    if dcol2.button("🗑️ Delete", key="doc_delete_btn", width="stretch"):
        with db.connect(schema=current_user) as conn:
            db.delete_document(conn, doc_pick_opts[doc_pick])
            conn.commit()
        st.rerun()

    tcol1, tcol2 = st.columns([3, 1])
    edited_tags = tcol1.text_input("Tags", value=picked.get("tags") or "", key="doc_tags_edit")
    if tcol2.button("💾 Update tags", key="doc_tags_save", width="stretch"):
        with db.connect(schema=current_user) as conn:
            db.update_document(conn, doc_pick_opts[doc_pick], {"tags": edited_tags})
            conn.commit()
        st.rerun()
