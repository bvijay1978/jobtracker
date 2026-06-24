# Job Tracker — Installation & Rollout Guide

Documentation for a team to install and roll out the Job Application Tracker.
Pair this with [BACKLOG.md](BACKLOG.md), which breaks the work into Jira-ready
epics and stories.

> **TL;DR for a single person:** `git clone` → `python3 -m venv .venv` →
> `pip install -r requirements.txt` → `python seed.py` → `streamlit run app.py`.
> The rest of this doc is for rolling it out properly across a team.

---

## 1. Decide the deployment model (do this first)

This is a **local-first SQLite + Streamlit app**. How the team uses it changes
the work, so agree on one of these up front:

| Model | What it means | Good when | Watch out for |
|---|---|---|---|
| **A — Local per person** | Everyone runs their own copy with their own `jobs.db`. | Each person tracks their own search; no shared data needed. | No shared view; each install maintained separately. |
| **B — Shared instance** | One Streamlit instance on a host, one shared `jobs.db`, team uses it via browser. | The team wants a single shared pipeline. | SQLite is single-writer; fine for a small team through one app process, but **no per-user auth** — put access control in front. Needs a backup plan. |

The backlog includes a spike (**PRE-3**) to make and record this decision.
Sections 2–4 cover the common install; section 5 covers the shared-instance extras.

---

## 2. Prerequisites

- **Python 3.9+** (`python3 --version`)
- **git**, with access to the repository (it is **private** — each team member
  needs to be added as a collaborator on `github.com/iainmacaskill/jobtracker`).
- ~200 MB free disk for the virtual environment.
- For the optional job-hunt automation: a Claude environment that can create
  skills + browse, and the **"Claude in Chrome" browser extension**.

---

## 3. Install (every model)

```bash
git clone https://github.com/iainmacaskill/jobtracker.git
cd jobtracker

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python seed.py                     # optional: demo data to confirm it works
streamlit run app.py
```

Open <http://localhost:8501>. You should see the tracker with the demo rows.
Clear them with `python seed.py --reset` (or delete `jobs.db`) before real use.

---

## 4. Configure

All machine-specific settings come from environment variables, optionally via a
local `.env` file (copy `.env.example` → `.env`). Nothing is hardcoded.

| Variable | Purpose | Default |
|---|---|---|
| `JOBTRACKER_DB` | Tracker database location | `./jobs.db` |
| `JOBTRACKER_XLSX` | Spreadsheet for `migrate.py` to import | _(none)_ |
| `JOBTRACKER_IMPORT_DB` | External SQLite DB for `import_jobs.py` | _(none)_ |

`.env` is git-ignored — local paths never get committed.

### Migrating existing data

```bash
python migrate.py --xlsx /path/to/tracker.xlsx --reset   # or set JOBTRACKER_XLSX
```

This de-duplicates by job-id and prints a summary. **Validate the row count**
against the source before relying on it.

---

## 5. Shared instance (Model B only)

Run one instance the team reaches over the network. Minimum viable approach:

1. **Host** — a small Linux VM (or container platform) the team can reach.
2. **Run it** as a long-lived service. A simple `Dockerfile`:

   ```dockerfile
   FROM python:3.12-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   EXPOSE 8501
   CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]
   ```

   Mount `jobs.db` on a **persistent volume** (`-e JOBTRACKER_DB=/data/jobs.db -v jobtracker-data:/data`) so data survives restarts.
3. **Access control** — Streamlit has no built-in auth. Put it behind a reverse
   proxy with basic auth/SSO, or restrict to the internal network/VPN. Everyone
   with access can see and edit all roles.
4. **Backups** — schedule a periodic copy of `jobs.db` (it's a single file).
   With WAL mode, copy via `sqlite3 jobs.db ".backup '/backups/jobs-$(date +%F).db'"`.

---

## 6. Optional — job-hunt automation

The tracker can be fed automatically. See
[../examples/generate-job-hunt-skill.md](../examples/generate-job-hunt-skill.md)
for the prompt that builds a personal job-hunt skill, then point it at the
tracker via `JOBTRACKER_IMPORT_DB` and use **⬇️ Import new roles** in the app.

---

## 7. Verify the install

```bash
pip install -r requirements-dev.txt
pytest          # 17 tests should pass
ruff check .    # lint should be clean
```

Then smoke-test in the UI: add a role, edit its status, filter, export CSV, and
(for a shared instance) confirm a write succeeds while another browser has the
app open.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `streamlit: command not found` | Activate the venv; re-run `pip install -r requirements.txt`. |
| App starts but is empty | Expected on a fresh DB — `python seed.py` or add a role. |
| `database is locked` | Shouldn't occur (WAL); ensure only one app instance writes, and you're not on a network filesystem. |
| Import button says no source | Set `JOBTRACKER_IMPORT_DB` in `.env`. |
| Can't clone | Confirm you've been added as a collaborator on the private repo. |
