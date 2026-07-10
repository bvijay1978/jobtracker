# Architecture & Decisions

How the Job Application Tracker is put together, what it deliberately does and
doesn't do, and the reasoning behind the key calls. New decisions are added as
short records (ADR style) at the end.

## The app in one paragraph

A local-first, single-user application tracker: a **SQLite** database (`jobs.db`)
holds the roles, and a **Streamlit** UI reads and edits them. Optional importers
feed it from a spreadsheet or an external database. It runs entirely on your
machine — no accounts, no server, no data leaves the computer.

## Capability boundary (read this first)

The **Streamlit app is a standalone local web app.** It can talk to its own
SQLite database and the local filesystem — and not much else. In particular it
**cannot**:

- call MCP connectors (Gmail, Jira, …),
- invoke Claude / Cowork or any LLM,
- reach a remote service without credentials wired in.

Anything that needs those lives in the **agent layer** — Claude in Cowork, the
job-hunt skill, scheduled routines. Those produce data (drafted CVs, rows in a
database) that the app then reads. The app and the automation are deliberately
**decoupled**: the agent writes, the app displays and edits.

This boundary is why several "buttons" in this project are deep-links or
import-from-database steps rather than direct integrations.

---

## Decision records

### ADR-001 — Local-first, single-user (SQLite + Streamlit)

**Context.** A personal job-search tool. Privacy matters; infrastructure is
overhead.
**Decision.** Store everything in one local SQLite file; render with Streamlit;
no auth, no hosting by default.
**Consequences.** Zero setup and full privacy, but no multi-user access control
and a single writer. A shared/hosted instance is possible later (see the
deployment backlog) but is out of scope for the default app.

### ADR-002 — The app is decoupled from the agent/connector layer

**Context.** Useful capabilities (search job boards, read Gmail, write Jira,
draft CVs/cover letters with an LLM) require MCP connectors or an LLM. A local
Streamlit process can reach none of these.
**Decision.** Keep the app to local data + UI. Capabilities that need an agent
run in Cowork / the job-hunt skill / scheduled routines and hand results to the
app via the database or files. In-app "buttons" for agent-side capabilities are
either (a) deep-links that open the relevant tool, or (b) imports of data an
agent produced.
**Consequences.** An honest, low-coupling design that works offline; the
trade-off is that "live" agent actions are triggered by asking Claude (or by a
schedule), not by a web button.

### ADR-003 — Gmail integration is minimal and outbound-focused

**Context.** Gmail can in principle tell us about application responses. But for
the way this tracker is actually used:

- genuine recruiter interest arrives **by phone first**, with email only as a
  follow-up — so an "you got a response" alert reports something already known;
- **rejections are not of interest**;
- the thing that matters is **knowing applications are going out** — it's a
  numbers game.

**Decision.**

- Keep a lightweight **"Search Gmail for replies"** deep-link in the app (it opens
  a pre-built Gmail search; it reads nothing and changes nothing).
- **Do not** build automated inbox *response*-reading into the app or a routine —
  low return for this workflow.
- If Gmail is ever automated, point it at the **outbound** side: confirming an
  application actually sent and auto-stamping `Applied` + date, which keeps the
  throughput metrics honest without manual entry.

**Consequences.** We avoid building an OAuth/response-parsing feature that would
mostly surface noise or already-known news. On-demand inbox scanning is still
available by simply asking Claude in Cowork (which has the Gmail connector). The
app's value stays centred on the **apply-and-track loop**, not response-chasing.

### ADR-004 — Status-driven pipeline with a derived "To action" queue

**Context.** The core job is tracking each role through a pipeline.
**Decision.** A single `status` field drives everything. The **To action** view
is *derived* (roles whose status isn't yet actioned), not a separate list — a
role leaves it automatically when its status changes. Closed or
not-to-be-actioned statuses (`Pass`, `Rejected`, `Expired`, …) drop a role out of
the queue.
**Consequences.** No manual "move between lists"; the queue and the metrics stay
consistent with status by construction.

### ADR-005 — De-duplicate on a stable job-id; importers feed the database

**Context.** The same role can be seen more than once, and an external automation
(the job-hunt skill, which runs sandboxed) produces roles the app must absorb
without duplicating.
**Decision.** Parse the numeric job-id from each link as the dedupe key (title +
company as a fallback). External tools write their own SQLite database;
`import_jobs.py` merges new rows into the canonical database and never overwrites
edits made in the app.
**Consequences.** Re-running searches and imports is safe and idempotent; the
canonical tracker stays authoritative.

### ADR-006 — SQLite in WAL mode; configuration via environment

**Context.** A script may write while the app is open, and paths differ per
machine.
**Decision.** Open the database in WAL mode with a busy-timeout (concurrent reads
+ a serialized write, no whole-file lock); read all machine-specific paths from
environment variables (optionally a git-ignored `.env`).
**Consequences.** Safe concurrent use, and a portable, shareable repo with
nothing machine-specific committed.

---

### ADR-007 — Draft CVs on demand, not during the sweep

**Context.** Generating a tailored CV for *every* role a job-hunt sweep turns up
is the most expensive step, and most of those roles are never applied to.
**Decision.** The sweep logs roles as `Found` only — no CVs. CV (and cover-letter)
drafting is triggered **per role, on demand**, by setting its status to
`Draft CV` or `Draft CV & Cover Letter` in the To-action queue; on save the app
generates the document(s), records the filenames, and settles the role to
`CV Drafted`. The in-app draft is a fast, **sector-aware** first cut: a rule-based
engine (`cv_builder.detect_sector`) reads the role's title/fit-notes and picks a
sector-appropriate profile paragraph and competency order (FS / AI / public /
default) — no LLM. Deep JD-tailoring on the few roles actually submitted stays an
agent task (ask Claude). The CV builder reads a **git-ignored `profile.json`**
(the single profile source for the app) so the shareable repo carries no personal
data.
**Consequences.** Effort is spent only on roles the user chooses to pursue;
the job-hunt skill was updated to stop auto-drafting in the sweep.

---

### ADR-008 — Two CVs (screening vs interview); the screening CV is JD-driven via an agent queue

**Context.** The first hurdle is automated screening — keyword/semantic matching of
the CV against the job description — and recruiters later search the ATS by exact
terms. A CV that reads well to a human and a CV that parses well for a machine have
*opposite* requirements: design (columns, tables, graphics) helps the human but
breaks ATS parsers.
**Decision.** Split the document in two.

- **Screening CV** — optimised to pass screening. Plain, single-column, standard
  headings, real text, **no tables/graphics** (`screening_cv.py`). Its content is
  **driven by the specific JD**: the advert's terminology is mirrored against the
  candidate's *genuine* experience, and `keyword_coverage()` reports real gaps. The
  honesty rule is absolute — only keywords for skills the candidate actually has;
  no invented terms (they get caught and collapse at interview). The user always
  reviews before sending.
- **Interview CV** — the polished, human-facing document (design/layout). Out of
  scope for now; this is where any "good-looking" work belongs.

**Delivery — agent queue (not an in-app button).** Reading a JD and authoring the
CV needs an LLM, which the app does not have (ADR-002). So setting a role to
`Draft CV` in the app is a **queue marker only** — it writes nothing. Claude
processes the queue (`screening_queue.list_queue`): reads each JD, writes the
screening CV, then `screening_queue.record_result` files the filename + coverage
back onto the role and settles it to `CV Drafted`.
**Consequences.** Keyword optimisation lives where the JD and the LLM are (the
agent), the app stays a pure local viewer/editor, and the offline sector-aware cut
(ADR-007) remains available as a no-JD fallback. The trade-off is that drafting is
*asynchronous* — it happens when Claude next runs, not on click.

---

### ADR-009 — Interview CV: a designed HTML→PDF, built in-house

**Context.** ADR-008 split the CV into a plain screening CV and a designed
"interview" CV for human readers, but deferred building the latter. Recruiters
increasingly AI-screen even the CVs sent directly to them, so the interview CV must
look polished **and** preserve keyword coverage.
**Decision.** Build it in-house (`interview_cv.py`): render a self-contained,
print-styled HTML and convert to PDF via the locally-installed **headless Chrome**
(`--headless --print-to-pdf`) — no pip/system dependencies, and nothing leaves the
machine. It renders the **same keyword-optimised `screening` payload** as
`screening_cv`, so the designed PDF carries identical AI-screening coverage
(verified with `keyword_coverage`); with no payload it falls back to the
sector-aware profile (ADR-007). Each role therefore has a plain `.docx` (pure-ATS
stage) **and** a designed `.pdf` (human / AI-screened recruiter stage).
**Considered and rejected — external builders (Manus, Lovable).** Manus is an MCP
*client* (can't be called to generate anything). Lovable exposes a server but
builds React *web apps* (a hosted URL, not a document), is OAuth-only (can't be
connected from a non-interactive session) and is gated behind a paid plan — so
neither is automatable here, and both would send personal data off-machine.
**Consequences.** Styling is free, private, repeatable and honest (same content,
just laid out well); the two-format output keeps ATS parsing clean while giving
humans a polished PDF. Requires Chrome/Chromium installed for the PDF export.

---

*Add new decisions as `ADR-NNN` records above this line, newest last.*
