# User Guide

A practical walkthrough of using the tracker day to day. For installation and
configuration, see the [README](README.md).

---

## 1. Starting the app

From the project folder, with your virtual environment activated:

```bash
streamlit run app.py
```

Your browser opens at **http://localhost:8501**. Leave the terminal running while
you use it; press **Ctrl + C** there to stop.

Want some data to explore first? Run `python seed.py` once to load a handful of
sample roles (delete them, or run `python seed.py --reset`, when you're done).

---

## 2. Finding your way around

**Metrics (top row)** — totals at a glance: how many roles in all, how many
Applied, how many at Shortlisted/Interview, how many still open, and how many you
applied to in the last 7 days.

**The table (centre)** — every role, newest first, editable like a spreadsheet.

**Sidebar (left):**

| Control | What it does |
|---|---|
| 🔄 **Refresh data** | Reload the table (it also auto-refreshes every few seconds). |
| ⬇️ **Import new roles** | Pull roles from an external database (see [section 6](#6-importing-roles-from-another-tool)). |
| **Status / Type / Recruiter** filters | Show only matching roles. |
| **Found between** | Limit to roles found in a date range. |
| **Search** | Free-text search across title, company and fit notes. |

**📊 Status breakdown** — expand for a bar chart of roles per status.

**⬇️ Export CSV** — download a snapshot of the whole tracker as a spreadsheet.

---

## 3. Adding and editing roles

The table is editable in place:

- **Add** — scroll to the **blank row at the bottom**, type into it (Title is
  required), and click **💾 Save changes**. Paste the job URL and the tracker
  records its job-id automatically, so the same posting won't be added twice.
- **Edit** — click any cell and type. A typical "I applied" update sets
  **Status** → `Applied`, fills **Applied** (date, `YYYY-MM-DD`), **CV version**,
  and **Outcome / Next step** — then **💾 Save changes**.
- **Delete** — select the row and press **⌫**, then **💾 Save changes**.

> Nothing is saved until you click **💾 Save changes**. Refreshing or navigating
> away first discards unsaved edits.

---

## 4. What the statuses mean

| Status | Meaning |
|---|---|
| **Found** | Logged but not yet applied. |
| **Applied** | Application submitted. |
| **Shortlisted** | Positive response from the employer/recruiter. |
| **Interview** | Interview arranged or held. |
| **Offer** | Offer received. |
| **Pass** | You decided not to pursue it. |
| **Rejected** | They declined your application. |

You can also type your own status text if none of these fit.

---

## 5. Where your data lives

Everything is in **`jobs.db`** in the project folder (a single SQLite file) — the
one source of truth. To back it up, copy that file somewhere safe, or use
**⬇️ Export CSV**. To wipe and start over, delete `jobs.db` and restart the app.

The database location can be changed with the `JOBTRACKER_DB` setting (see the
README's configuration section).

---

## 6. Importing roles from another tool

If you have a scraper, automation, or another tracker that writes new roles into
a separate SQLite database, you can pull them in:

1. Point the tracker at that database by setting `JOBTRACKER_IMPORT_DB` in your
   `.env` file (see `.env.example`).
2. Click **⬇️ Import new roles** in the sidebar (or run `python import_jobs.py`).

Only genuinely new roles are added — anything already in your tracker is left
untouched, so your edits always win.

---

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| **App won't start** | Activate the virtual environment and `pip install -r requirements.txt`. Run from the project folder. |
| **My edits disappeared** | They weren't saved — click **💾 Save changes** after editing. |
| **"Import new roles" says no source** | Set `JOBTRACKER_IMPORT_DB` in `.env` to an external database first. |
| **A role appears twice** | Delete the duplicate row and save. Roles with a logged job-id won't be re-added by imports. |
| **The page looks frozen** | Click **🔄 Refresh data** or reload the tab. The terminal must still be running. |
