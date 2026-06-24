# Job Tracker — Installation Backlog

The work to install and roll out the Job Application Tracker, broken into epics
and stories. Pair this with [INSTALL.md](INSTALL.md) (the how-to).

> **About Jira:** this backlog is provided as a Jira-importable file,
> [`jira-backlog.csv`](jira-backlog.csv), rather than created directly in Jira —
> no Jira/Atlassian connector is available in this environment. The
> [import steps](#importing-into-jira) below load it into a Jira project in a
> couple of minutes.

---

## Importing into Jira

1. Create (or pick) a Jira project for the install — e.g. **Job Tracker Install
   (`JTI`)**.
2. **Jira → your profile / project settings → System → External System Import →
   CSV** (or *Issues → Import issues from CSV*).
3. Upload [`jira-backlog.csv`](jira-backlog.csv) and select the target project.
4. Map the columns: `Issue Type`, `Summary`, `Epic Name`, `Epic Link`,
   `Priority`, `Story Points`, `Labels`, `Description` map to the matching Jira
   fields. Import **Epics first then Stories** (the file is already ordered that
   way) so `Epic Link` resolves against `Epic Name`.
5. For **team-managed** projects, map `Epic Link` → **Parent** instead (team-
   managed projects use Parent rather than Epic Link).

**Totals:** 8 epics, 30 stories/tasks. Remove the **Shared Deployment** epic and
its 4 stories if you choose Model A (local-per-person) in `PRE-3`.

---

## Suggested sequencing

| Phase | Focus | Epics |
|---|---|---|
| 1 | Get a working install | Prerequisites & Access → Local Installation → Configuration |
| 2 | Real data in | Data Migration |
| 3 | Make it a team service *(Model B)* | Shared Deployment |
| 4 | Optional automation | Automation Integration |
| 5 | Prove it & hand over | Validation & Acceptance → Documentation & Handover |

---

## Epics & stories

### EP1 · Prerequisites & Access  _(Highest)_
| Summary | Type | Pri | Pts | Acceptance criteria |
|---|---|---|---|---|
| Confirm system prerequisites | Task | High | 2 | Python 3.9+ and git present on each target; recorded per machine |
| Grant repository access to the team | Task | High | 1 | Every member can clone the private repo |
| **Decide and record the deployment model** | Task | Highest | 2 | Model A or B chosen with rationale and recorded; dependent stories enabled/disabled |
| Provision host or VM for shared instance | Task | Medium | 3 | _(Model B)_ Host reachable; runtime available; network access confirmed |

### EP2 · Local Installation  _(High)_
| Summary | Type | Pri | Pts | Acceptance criteria |
|---|---|---|---|---|
| Clone repository and create virtual environment | Story | High | 1 | Repo cloned; `.venv` created and activated |
| Install dependencies | Story | High | 1 | `pip install -r requirements.txt` completes cleanly |
| Launch the app and verify it loads | Story | High | 1 | `streamlit run app.py` serves the tracker at :8501 |
| Load demo data and validate the UI | Story | Medium | 1 | `seed.py` loads rows; metrics/table/filters render; cleared before real use |

### EP3 · Configuration  _(High)_
| Summary | Type | Pri | Pts | Acceptance criteria |
|---|---|---|---|---|
| Create `.env` from the template | Story | High | 1 | `.env` copied from `.env.example`; confirmed git-ignored |
| Set the database location | Story | Medium | 1 | App reads/writes the configured `JOBTRACKER_DB` |
| Configure the import source | Story | Low | 1 | _(Optional)_ `JOBTRACKER_IMPORT_DB` set; Import button finds it |

### EP4 · Data Migration  _(High)_
| Summary | Type | Pri | Pts | Acceptance criteria |
|---|---|---|---|---|
| Inventory and back up existing tracker data | Story | High | 2 | Source located; backup stored; row count noted |
| Run the spreadsheet import | Story | High | 2 | `migrate.py` completes; summary printed |
| Validate migrated data | Story | High | 2 | Count matches expected; 5+ records spot-checked; links/statuses correct |

### EP5 · Shared Deployment  _(Medium — Model B only)_
| Summary | Type | Pri | Pts | Acceptance criteria |
|---|---|---|---|---|
| Containerize the application | Story | Medium | 3 | Dockerfile builds; container serves :8501 |
| Deploy the instance with persistent storage | Story | Medium | 3 | App reachable; `jobs.db` persists across restarts |
| Add access control in front of the app | Story | High | 3 | Only authorized users reach the app; method documented |
| Configure automated database backups | Story | High | 2 | Scheduled backup runs; a restore has been tested |

### EP6 · Automation Integration  _(Medium — optional)_
| Summary | Type | Pri | Pts | Acceptance criteria |
|---|---|---|---|---|
| Install and connect the Claude in Chrome extension | Story | Medium | 1 | Extension installed and connected |
| Generate the job-hunt skill from the prompt | Story | Medium | 3 | Placeholders filled; skill created and runnable |
| Wire the skill output into the tracker | Story | Medium | 2 | Import source set; import works |
| Run an end-to-end job-hunt and import test | Story | Medium | 2 | Skill logs roles; import brings them in with no duplicates |

### EP7 · Validation & Acceptance  _(High)_
| Summary | Type | Pri | Pts | Acceptance criteria |
|---|---|---|---|---|
| Run the automated test suite | Story | High | 1 | `pytest` passes; `ruff check` clean |
| Smoke-test the core workflows | Story | High | 2 | Add/edit/delete/save, filters, CSV export all work |
| Verify concurrency behaviour | Story | Medium | 2 | Write succeeds while app open elsewhere; no lock errors |
| UAT sign-off with the team | Story | High | 2 | Users complete real workflows; sign-off recorded |

### EP8 · Documentation & Handover  _(Medium)_
| Summary | Type | Pri | Pts | Acceptance criteria |
|---|---|---|---|---|
| Write the team runbook | Story | Medium | 2 | Covers start/stop, add/edit, import, export; peer-reviewed |
| Define backup and recovery procedure | Story | High | 2 | Procedure written; a restore validated |
| Run a team walkthrough | Story | Medium | 2 | Session delivered; questions captured |
| Establish support and ownership | Task | Medium | 1 | Named owner; support channel agreed |

---

_If a Jira/Atlassian MCP connector is later connected, I can create the project
and these issues directly instead of via CSV — just ask._
